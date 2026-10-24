"""Run through ``manage.py shell`` (see make_sample_sources.py): adds Studio sections
that reference real products/collections/menus/media of the seeded demo store, so
the converter is exercised with every kind of numeric reference. Sample data only."""
import os

from django.core.cache import cache
from django.core.files.base import ContentFile

from apps.catalog.models import Brand, Category, MerchantCollection, Product, ProductImage
from apps.content.models import MediaAsset, Menu
from apps.storefront_builder import section_registry
from apps.storefront_builder.services import layout_service, section_structure_service
from apps.stores.models import Store

store = Store.objects.get(slug="rasti-mode-demo")
products = list(Product.objects.filter(store=store).order_by("pk")[:8])
collection = MerchantCollection.objects.filter(store=store).order_by("pk").first()
category = Category.objects.filter(store=store, parent__isnull=False).order_by("pk").first()
brand = Brand.objects.filter(store=store).order_by("pk").first()
menu = Menu.objects.filter(store=store).order_by("pk").first()
cover = ProductImage.objects.filter(product__store=store).order_by("pk").first()
asset = MediaAsset(store=store)
asset.image.save("sample-background.webp", ContentFile(cover.image.read()), save=False)
asset.save()


def add(draft, key, patch):
    section = section_structure_service.add_section(draft=draft, section_key=key, page_type="home")
    definition = section_registry.SECTION_REGISTRY[key]
    section.settings = definition.validate_settings({**definition.default_settings(), **patch})
    section.save(update_fields=["settings"])


cache.clear()
draft = layout_service.get_or_create_draft(store)
add(draft, "product_section", {"data_source": "manual", "product_ids": [p.pk for p in products[:6]], "title": "manual picks"})
add(draft, "product_section", {"data_source": "collection", "source_id": collection.pk, "title": "from collection"})
add(draft, "product_section", {"data_source": "category", "source_id": category.pk, "title": "from category"})
add(draft, "category_grid", {"category_ids": [category.pk], "title": "categories"})
add(draft, "brand_carousel", {"brand_ids": [brand.pk], "title": "brands"})
add(draft, "collection_tiles", {"collection_ids": [collection.pk], "title": "collections"})
add(draft, "quick_links", {"menu_id": menu.pk, "title": "quick links"})
add(draft, "rich_text", {"body_html": "<p>sample</p>", "background": {"mode": "image", "media_asset_id": asset.pk}})
add(draft, "image_text", {"title": "promo", "body_html": "<p>x</p>",
                          "destination": {"destination_type": "product", "destination_id": products[1].pk}})
layout_service.publish(store)
cache.clear()
draft = layout_service.get_or_create_draft(store)
add(draft, "product_section", {"data_source": "manual", "product_ids": [p.pk for p in products[::-1]], "title": "WIP draft list"})
print("augmented", store.slug, "versions:", store.storefront_layout.versions.count())
