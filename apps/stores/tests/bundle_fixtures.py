"""Test support: build realistic little stores and independent SQLite "source" files.

NOT production code and NOT real demo data. Everything here is generated.
"""

from __future__ import annotations

import sqlite3
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image

from apps.catalog.models import (
    Brand, Category, MerchantCollection, MerchantCollectionItem, Product, ProductImage, ProductOption,
    ProductOptionValue, ProductVariant, VariantOptionValue, Vendor,
)
from apps.content.models import FooterSettings, HeroSlide, MediaAsset, Menu, MenuItem
from apps.core.models import ShopSettings
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service, section_structure_service
from apps.stores.models import Store, StoreDomain


def png_bytes(color, size=(32, 32)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _add_section(draft, key: str, patch: dict, page_type: str = "home"):
    section = section_structure_service.add_section(draft=draft, section_key=key, page_type=page_type)
    definition = section_registry.SECTION_REGISTRY[key]
    raw = {**definition.default_settings(), **patch}
    section.settings = definition.validate_settings(raw)
    section.save(update_fields=["settings"])
    return section


def build_rich_store(slug: str, *, color: str = "#112233", product_count: int = 4, host: str | None = None) -> Store:
    """A store that uses every kind of reference the converter must renumber.

    Catalogue with variants (``combination_key``), a collection, menus, media
    assets, a hero slide, and Studio versions: one archived, one published and
    one draft - each referencing products/collections/categories/brands/menus/
    media by id.
    """
    cache.clear()
    store = Store.objects.create(
        name=f"Demo {slug}", slug=slug, admin_subdomain=slug, status=Store.Status.ACTIVE,
        onboarding_completed_at=timezone.now(),
    )
    StoreDomain.objects.create(
        store=store, hostname=host or f"{slug}.rastisi.ir", is_primary=True,
        domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )
    shop = ShopSettings.provision_for(store)
    shop.primary_color, shop.tagline = color, f"tagline of {slug}"
    shop.kavenegar_api_key = "SECRET-DO-NOT-EXPORT"
    shop.logo.save(f"{slug}-logo.png", ContentFile(png_bytes((10, 20, 30))), save=False)
    shop.favicon.save(f"{slug}-fav.png", ContentFile(png_bytes((30, 20, 10))), save=False)
    shop.save()
    footer = FooterSettings.provision_for(store)
    footer.about_text = f"about {slug}"
    footer.save()

    vendor = Vendor.objects.create(store=store, name="V", slug=f"v-{slug}")
    parent = Category.objects.create(store=store, name="Parent", slug=f"parent-{slug}")
    category = Category.objects.create(store=store, name="Child", slug=f"child-{slug}", parent=parent)
    brand = Brand.objects.create(store=store, name="B", slug=f"b-{slug}")
    products = []
    for i in range(product_count):
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, brand=brand, name=f"{slug} P{i}",
            slug=f"p{i}-{slug}", sku=f"SKU-{slug}-{i}", price=Decimal("1000") * (i + 1), stock=10,
        )
        for order in range(2):
            image = ProductImage(product=product, order=order, is_cover=order == 0, alt=f"a{order}")
            image.image.save(f"{slug}-{i}-{order}.png", ContentFile(png_bytes((200, i * 30, order * 90))), save=False)
            image.thumbnail.save(f"{slug}-{i}-{order}-t.png", ContentFile(png_bytes((i, order, 9))), save=False)
            image.save()
        products.append(product)

    # variants whose ``combination_key`` is made of option-value ids
    option = ProductOption.objects.create(product=products[0], label="Size", normalized_label="size", position=1)
    values = [ProductOptionValue.objects.create(option=option, label=label, normalized_label=label.lower()) for label in ("S", "M")]
    for value in values:
        variant = ProductVariant.objects.create(
            product=products[0], store=store, attribute="Size", value=value.label, normalized_attribute="size",
            normalized_value=value.label.lower(), combination_key=str(value.pk),
        )
        VariantOptionValue.objects.create(variant=variant, option=option, option_value=value)

    collection = MerchantCollection.objects.create(store=store, name="Coll", slug=f"coll-{slug}")
    for product in products[:2]:
        MerchantCollectionItem.objects.create(collection=collection, product=product)

    header = Menu.objects.create(store=store, title="Main", location=Menu.Location.HEADER)
    MenuItem.objects.create(menu=header, title="Child", destination_type="category", destination_category=category)
    footer_menu = Menu.objects.create(store=store, title="Foot", location=Menu.Location.FOOTER_1)
    MenuItem.objects.create(menu=footer_menu, title="Prod", destination_type="product", destination_product=products[0])

    asset = MediaAsset(store=store)
    asset.image.save(f"{slug}-bg.png", ContentFile(png_bytes((5, 6, 7), (64, 32))), save=False)
    asset.save()
    banner_asset = MediaAsset(store=store)
    banner_asset.image.save("shared-banner.png", ContentFile(png_bytes((1, 2, 3), (64, 32))), save=False)
    banner_asset.save()
    HeroSlide.objects.create(store=store, title=f"hero {slug}", desktop_asset=banner_asset, destination_type="product",
                             destination_product=products[1])

    ids = [p.pk for p in products]

    # ---- v1 (will be archived): product list + media background
    draft = layout_service.get_or_create_draft(store)
    _add_section(draft, "product_section", {"data_source": "manual", "product_ids": ids[:3], "title": "manual picks"})
    _add_section(draft, "rich_text", {"body_html": "<p>hello</p>", "background": {"mode": "image", "media_asset_id": asset.pk}})
    layout_service.publish(store)
    # ---- v2 (published): collection source, grids, quick links, destination
    cache.clear()
    draft = layout_service.get_or_create_draft(store)
    _add_section(draft, "product_section", {"data_source": "collection", "source_id": collection.pk, "title": "from collection"})
    _add_section(draft, "product_section", {"data_source": "category", "source_id": category.pk, "title": "from category"})
    _add_section(draft, "category_grid", {"category_ids": [category.pk], "title": "cats"})
    _add_section(draft, "brand_carousel", {"brand_ids": [brand.pk], "title": "brands"})
    _add_section(draft, "collection_tiles", {"collection_ids": [collection.pk], "title": "tiles"})
    _add_section(draft, "quick_links", {"menu_id": header.pk, "title": "links"})
    _add_section(draft, "image_text", {
        "title": "promo", "body_html": "<p>x</p>",
        "destination": {"destination_type": "product", "destination_id": products[2 % product_count].pk},
    })
    layout_service.publish(store)
    # ---- v3 (draft, unpublished work in progress)
    cache.clear()
    draft = layout_service.get_or_create_draft(store)
    _add_section(draft, "product_section", {"data_source": "manual", "product_ids": ids[::-1], "title": "WIP draft list"})
    return store


def wipe_store(store: Store) -> None:
    from apps.catalog.models import ProductVariant as PV
    from apps.catalog.models import Product as P

    PV.objects.filter(product__store=store).delete()
    MenuItem.objects.filter(menu__store=store).delete()
    P.objects.filter(store=store).delete()
    store.delete()


def snapshot_default_db(destination: Path) -> None:
    """Write the CURRENT state (including uncommitted test data) of the default
    in-memory/test SQLite database to ``destination`` as an independent file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    # ``backup()`` stalls on the shared-cache in-memory test database while a
    # transaction is open; ``iterdump`` reads through the same connection.
    target = sqlite3.connect(str(destination))
    try:
        target.executescript("\n".join(connection.connection.iterdump()))
        target.commit()
    finally:
        target.close()


def build_source_sqlite(destination: Path, media_root: Path, builder) -> Store:
    """Run ``builder()`` inside a savepoint, snapshot the database to
    ``destination`` and roll the savepoint back. Two calls therefore produce two
    independent SQLite files whose auto-increment keys START AT THE SAME VALUES
    (deliberately colliding)."""
    sid = transaction.savepoint()
    try:
        store = builder()
        snapshot_default_db(destination)
    finally:
        transaction.savepoint_rollback(sid)
    return store


def zip_media(root: Path, destination: Path, *, wrapper: str = "", backslashes: bool = False, extras: dict | None = None) -> None:
    """Zip a MEDIA_ROOT folder like a person would: optionally inside a wrapping
    folder and/or with Windows ``\\`` separators, plus some OS junk."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                arc = (wrapper.rstrip("/") + "/" if wrapper else "") + path.relative_to(root).as_posix()
                zf.write(path, arc.replace("/", "\\") if backslashes else arc)
        zf.writestr((wrapper + "/" if wrapper else "") + "Thumbs.db", b"junk")
        zf.writestr("__MACOSX/._junk", b"junk")
        for name, data in (extras or {}).items():
            zf.writestr((wrapper.rstrip("/") + "/" if wrapper else "") + name, data)


__all__ = [
    "build_rich_store", "build_source_sqlite", "png_bytes", "snapshot_default_db", "wipe_store", "zip_media",
    "StorefrontLayout", "StorefrontPage", "StorefrontSection",
]
