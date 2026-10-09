"""First-run structural placeholders for a brand-new, still-empty Store's public Home page.

Problem this solves: a Ready Template is mostly *data-driven composition* — Hero slides, the category
rail, product rows and the catalog wall all read merchant-owned rows. A Store that was just created
through the portal onboarding has none of them, so the public renderer (correctly) drops/renders-nothing
for each of those sections and the customer is left with the template's shell only (palette, header,
footer) and an almost blank page. The shell survives; the *recognisable composition* does not.

This module keeps the selected template's composition visible WITHOUT inventing any data:

* it is a pure, NON-PERSISTENT render-time substitution — it never creates a Product, Category,
  HeroSlide, Banner, Order or Customer, and never writes to the Storefront Layout;
* it only applies to the public **home** page of a Store provisioned through the modern portal flow
  (``Store.onboarding_required_at`` set — legacy/ad-hoc Stores are untouched) that has NO storefront-listable
  product yet. The moment the first product exists the normal data-driven rules apply again (empty optional
  product rows are hidden as before);
* it replaces only the three data-dependent section kinds that carry a template's visual identity
  (hero/slider, category rail, product rows/wall) and only when that section would otherwise render empty.
  Everything else (static sections, header/footer, appearance) is rendered exactly as before;
* the placeholder markup is neutral, tokenised (``--card``/``--border``/``--muted``/``--primary``/``--radius``
  from the selected template's own palette) and honestly worded — it never pretends to be real catalog.
"""

from apps.catalog.services.product_publish_service import storefront_listing_products

PLACEHOLDER_TEMPLATE = "storefront_builder/sections/first_run_placeholder.html"

KIND_HERO = "hero"
KIND_CATEGORIES = "categories"
KIND_PRODUCTS = "products"

_HERO_KEYS = frozenset({"hero_banner", "image_slider"})
_CATEGORY_KEYS = frozenset({"category_grid"})
_PRODUCT_KEYS = frozenset({
    "product_section", "featured_products", "newest_products", "best_sellers", "discounted_products",
    "amazing_offers",
})
_PRODUCT_WALL_KEY = "catalog_product_wall"


def _is_modern(store) -> bool:
    return store is not None and getattr(store, "onboarding_required_at", None) is not None


def is_first_run_store(store) -> bool:
    """A modern-portal Store whose catalog is still empty (no storefront-listable product)."""
    return _is_modern(store) and not storefront_listing_products(store).exists()


def has_as_delivered_composition(store) -> bool:
    """True while the Store's published layout is still the FIRST version it ever published — the one
    onboarding published — i.e. the merchant has not published any later (deliberate) layout edit."""
    from ..models import StorefrontLayout, StorefrontLayoutVersion

    if not _is_modern(store):
        return False
    layout = StorefrontLayout.objects.filter(store=store).select_related("published_version").first()
    if layout is None or layout.published_version is None:
        return False
    return not StorefrontLayoutVersion.objects.filter(
        layout=layout, published_at__isnull=False,
    ).exclude(pk=layout.published_version_id).exists()


def _is_empty(item, kind_key) -> bool:
    context = item["context"]
    value = context.get(kind_key)
    if value is None:
        return True
    exists = getattr(value, "exists", None)
    if callable(exists):
        return not exists()
    return not value


def _kind_for(item):
    key = item["section"].section_key
    if key in _HERO_KEYS and _is_empty(item, "hero_slides"):
        return KIND_HERO
    if key in _CATEGORY_KEYS and _is_empty(item, "top_categories"):
        return KIND_CATEGORIES
    if key in _PRODUCT_KEYS and _is_empty(item, "products"):
        return KIND_PRODUCTS
    if key == _PRODUCT_WALL_KEY and _is_empty(item, "catalog_product_wall_groups"):
        return KIND_PRODUCTS
    return None


def apply_first_run_placeholders(items: list[dict], store, *, page_type: str) -> list[dict]:
    """Return ``items`` with empty hero/category/product sections swapped for the neutral placeholder
    partial, for a first-run Store's public home page (see the module docstring for the per-kind rules).
    Any other input is returned unchanged."""
    if page_type != "home" or not items or not _is_modern(store):
        return items
    gates = {}

    def allowed(kind):
        if kind not in gates:
            gates[kind] = (
                is_first_run_store(store) if kind == KIND_PRODUCTS else has_as_delivered_composition(store)
            )
        return gates[kind]

    result = []
    for item in items:
        kind = _kind_for(item)
        if kind is None or not allowed(kind):
            result.append(item)
            continue
        result.append({
            **item,
            "template_name": PLACEHOLDER_TEMPLATE,
            "context": dict(item["context"]),
            "first_run_placeholder": kind,
        })
    return result
