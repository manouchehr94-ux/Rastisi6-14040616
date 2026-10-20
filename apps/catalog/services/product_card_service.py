"""Universal Product Card business-data resolver — U3.

``catalog/partials/product_card.html`` is reused, unmodified, from every
product-bearing surface in the storefront (homepage sections, listings,
collections, search, related products) — see the grep-confirmed include
sites in ``storefront_builder/templates/storefront_builder/sections/*.html``
and ``catalog/partials/product_grid.html``/``product_list_results.html``.
Before this module, the price/discount/badge/quick-add business rules lived
*inside that template* as direct ``product.discount_percent``/
``product.final_price``/``product.tag`` lookups — meaning any future visual
card variant would have had to re-derive (and could silently diverge on)
the same business semantics.

This module is the single place that turns a ``Product`` instance into the
plain, already-decided facts a card (any visual variant of it) needs to
render. It never queries the database itself — it only reads fields/
properties/prefetch caches the caller already loaded, exactly the way
``render_service``'s existing context builders already
``select_related("brand")``/``prefetch_related("images", "metafields")``
before handing products to a template. Calling this once per already-fetched
product is therefore O(1) queries added, regardless of grid size.

Capability boundary (documented, not silently guessed): ``Product`` has no
store/product-level low-stock threshold field — only ``ProductVariant.
low_stock_threshold``/``WarehouseInventory.low_stock_threshold`` do (Phase 1D).
Deriving a single "low stock" fact for a product-grid card would mean either
picking one arbitrary variant's threshold (misleading for a variable
product with many variants) or issuing a per-card variant query (an N+1
regression). Per the "no fabricated stock claims" rule, ``is_low_stock`` is
therefore always ``False`` today; a future phase can wire this up once a
product-level (or query-batched, N+1-safe) threshold exists.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

from django.urls import reverse

from . import availability_service


@dataclasses.dataclass(frozen=True)
class ProductCardBadge:
    """One real, data-backed badge — never free text a caller invents."""

    key: str
    label_fa: str


@dataclasses.dataclass(frozen=True)
class ProductCardData:
    """Resolved, render-ready business facts for one product card.

    Every visual card variant (``card_settings.card_style`` today; any
    future registered variant) reads from this same object, so pricing/
    badge/availability semantics can never diverge between variants."""

    product_id: int
    name: str
    url: str
    image_url: str | None
    image_alt: str
    secondary_image_url: str | None
    price: Decimal
    compare_at_price: Decimal | None
    is_on_sale: bool
    discount_percent: int
    badges: tuple[ProductCardBadge, ...]
    is_out_of_stock: bool
    is_low_stock: bool
    is_quick_add_eligible: bool
    is_wishlist_eligible: bool
    brand_name: str
    rating: Decimal
    reviews_count: int
    #: «استعلام قیمت»: قیمت/تخفیف/خریدِ مستقیم نمایش داده نمی‌شود؛ ``inquiry_url``
    #: صفحه‌ی «درباره ما»ی همین فروشگاه است (``None`` اگر نباشد).
    is_price_inquiry: bool = False
    inquiry_url: str | None = None


#: ``Product.Tag`` (marketing label) → badge key (== the existing
#: ``pill-{key}`` CSS class already shipped in ``product_card.css``).
#: ``sale`` intentionally maps to the same ``new`` visual treatment as
#: before this module existed (the pre-U3 template rendered
#: ``<span class="pill pill-new">حراج</span>`` for the ``sale`` tag too —
#: preserved verbatim here, not a new design decision). Labels reuse the
#: model's own ``get_tag_display()`` (single source of truth), never a
#: second hardcoded translation table. The discount-percent pill is
#: deliberately NOT one of these — its digits still need the template's
#: ``fa_number`` filter (Persian numerals), so it stays a dedicated
#: ``discount_percent``/``is_on_sale`` pair the template formats itself,
#: exactly as it did before this module existed.
_TAG_BADGE_KEYS = {"new": "new", "hot": "hot", "sale": "new"}


def _resolve_image(image) -> str | None:
    if image is None:
        return None
    # همان اولویتِ موجودِ template پیش از این تغییر: thumbnail در صورت وجود.
    return image.thumbnail.url if image.thumbnail else image.image.url


def build_product_card_data(product) -> ProductCardData:
    """Pure resolver — no DB query beyond what ``product`` already cached
    (``cover_image``/``secondary_image`` properties already read from the
    ``images`` prefetch cache, see ``Product.cover_image``)."""
    badges: list[ProductCardBadge] = []
    is_inquiry = bool(product.is_price_inquiry)
    active_discount = 0 if is_inquiry else product.active_discount_percent()
    is_on_sale = active_discount > 0
    tag_key = _TAG_BADGE_KEYS.get(product.tag)
    if tag_key is not None:
        badges.append(ProductCardBadge(key=tag_key, label_fa=product.get_tag_display()))

    # Same availability contract as the home rails / listing order (variants + reservations), never a second rule.
    is_out_of_stock = not availability_service.is_available(product)
    cover_image = product.cover_image
    secondary_image = product.secondary_image

    return ProductCardData(
        product_id=product.pk,
        name=product.name,
        url=reverse("catalog:product-detail", args=[product.slug]),
        image_url=_resolve_image(cover_image),
        image_alt=(cover_image.alt if cover_image and cover_image.alt else product.name),
        secondary_image_url=_resolve_image(secondary_image),
        price=product.final_price,
        compare_at_price=product.price if is_on_sale else None,
        is_on_sale=is_on_sale,
        discount_percent=active_discount,
        badges=tuple(badges),
        is_out_of_stock=is_out_of_stock,
        is_low_stock=False,
        is_quick_add_eligible=(not product.is_variable) and not is_out_of_stock and not is_inquiry,
        is_wishlist_eligible=True,
        brand_name=product.brand.name if product.brand_id else "",
        rating=product.rating,
        reviews_count=product.reviews_count,
        is_price_inquiry=is_inquiry,
        inquiry_url=_inquiry_url(product) if is_inquiry else None,
    )


def _inquiry_url(product):
    from apps.catalog.services import pricing_mode_service

    return pricing_mode_service.inquiry_destination_url(product.store)
