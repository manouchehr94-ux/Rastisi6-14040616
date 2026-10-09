"""Unit contract of ``first_run_placeholder_service`` — pure render-time substitution, no persistence."""

from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Product, Vendor
from apps.storefront_builder.services import first_run_placeholder_service as svc
from apps.storefront_builder.services import layout_service, render_service, store_template_service
from apps.stores.models import Store
from apps.stores.services.platform_code_service import generate_unique_platform_code


def _store(**kwargs):
    kwargs.setdefault("name", "S")
    kwargs.setdefault("slug", f"frp-{Store.objects.count()}")
    kwargs.setdefault("status", Store.Status.ACTIVE)
    kwargs.setdefault("platform_code", generate_unique_platform_code())
    return Store.objects.create(**kwargs)


def _publish_template(store, key="dark_digital"):
    """What onboarding does: apply a Ready Template to the Draft and publish it (the store's FIRST published version)."""
    store_template_service.select_ready_template(store=store, actor=None, template_key=key)
    return layout_service.publish(store)


def _product(store, slug="p"):
    vendor = Vendor.objects.create(store=store, name=f"v-{slug}", slug=f"v-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, name=slug, slug=slug, sku=f"SKU-{slug}", price=Decimal("1"),
        status=Product.Status.ACTIVE,
    )


def _item(section_key, **context):
    return {
        "section": SimpleNamespace(section_key=section_key, pk=None),
        "template_name": f"storefront_builder/sections/{section_key}.html",
        "context": context,
    }


class IsFirstRunStoreTests(TestCase):
    def test_modern_store_without_products_is_first_run(self):
        self.assertTrue(svc.is_first_run_store(_store(onboarding_required_at=timezone.now())))

    def test_legacy_store_is_never_first_run(self):
        self.assertFalse(svc.is_first_run_store(_store()))

    def test_none_is_never_first_run(self):
        self.assertFalse(svc.is_first_run_store(None))

    def test_a_listable_product_ends_the_first_run_state(self):
        store = _store(onboarding_required_at=timezone.now())
        vendor = Vendor.objects.create(store=store, name="v", slug="v-u")
        Product.objects.create(
            store=store, vendor=vendor, name="p", slug="p-u", sku="SKU-U", price=Decimal("1"),
            status=Product.Status.ACTIVE,
        )
        self.assertFalse(svc.is_first_run_store(store))

    def test_a_non_active_product_does_not_end_it(self):
        store = _store(onboarding_required_at=timezone.now())
        vendor = Vendor.objects.create(store=store, name="v", slug="v-u2")
        Product.objects.create(
            store=store, vendor=vendor, name="p", slug="p-u2", sku="SKU-U2", price=Decimal("1"),
            status=Product.Status.INACTIVE,
        )
        self.assertTrue(svc.is_first_run_store(store))


class ApplyFirstRunPlaceholdersTests(TestCase):
    def setUp(self):
        self.store = _store(onboarding_required_at=timezone.now())
        _publish_template(self.store)

    def apply(self, items, page_type="home", store=None):
        return svc.apply_first_run_placeholders(items, store or self.store, page_type=page_type)

    def test_empty_hero_category_and_product_sections_are_replaced_by_the_placeholder_partial(self):
        out = self.apply([
            _item("hero_banner", hero_slides=[]),
            _item("category_grid", top_categories=[]),
            _item("product_section", products=[]),
            _item("catalog_product_wall", catalog_product_wall_groups=[]),
        ])
        self.assertEqual([i["first_run_placeholder"] for i in out], ["hero", "categories", "products", "products"])
        self.assertTrue(all(i["template_name"] == svc.PLACEHOLDER_TEMPLATE for i in out))

    def test_sections_with_real_data_are_left_alone(self):
        items = [
            _item("hero_banner", hero_slides=[object()]),
            _item("category_grid", top_categories=[object()]),
            _item("product_section", products=[object()]),
        ]
        out = self.apply(items)
        self.assertEqual(out, items)
        self.assertTrue(all("first_run_placeholder" not in i for i in out))

    def test_static_and_unrelated_sections_are_never_replaced(self):
        items = [_item("newsletter"), _item("trust_features"), _item("rich_text"), _item("testimonials")]
        self.assertEqual(self.apply(items), items)

    def test_the_input_items_are_not_mutated(self):
        item = _item("hero_banner", hero_slides=[])
        self.apply([item])
        self.assertNotIn("first_run_placeholder", item)
        self.assertEqual(item["template_name"], "storefront_builder/sections/hero_banner.html")

    def test_non_home_pages_and_legacy_stores_are_untouched(self):
        items = [_item("product_section", products=[])]
        self.assertEqual(self.apply(items, page_type="product_list"), items)
        self.assertEqual(self.apply(items, store=_store()), items)

    def test_a_placeholder_item_survives_the_public_empty_section_filter(self):
        placeholder = self.apply([_item("product_section", products=[])])
        self.assertEqual(render_service.hide_empty_public_sections(placeholder), placeholder)

    def test_an_unreplaced_empty_product_section_is_still_hidden_as_before(self):
        plain = [_item("product_section", products=[])]
        self.assertEqual(render_service.hide_empty_public_sections(plain), [])


class SectionLevelReadinessTests(TestCase):
    """Follow-up: hero/category placeholders do not collapse just because the first product was added; product
    rows do (their data now exists); a deliberate later layout publish ends the as-delivered composition."""

    def setUp(self):
        self.store = _store(onboarding_required_at=timezone.now())
        _publish_template(self.store)

    def apply(self, items):
        return svc.apply_first_run_placeholders(items, self.store, page_type="home")

    def kinds(self, out):
        return [i.get("first_run_placeholder") for i in out]

    def test_the_first_product_keeps_the_hero_and_category_placeholders_but_not_the_product_row(self):
        _product(self.store)
        out = self.apply([
            _item("hero_banner", hero_slides=[]),
            _item("category_grid", top_categories=[]),
            _item("product_section", products=[]),
        ])
        self.assertEqual(self.kinds(out), ["hero", "categories", None])

    def test_a_section_with_real_content_never_gets_a_placeholder_even_in_the_as_delivered_composition(self):
        out = self.apply([_item("hero_banner", hero_slides=[object()]), _item("category_grid", top_categories=[object()])])
        self.assertEqual(self.kinds(out), [None, None])

    def test_a_later_published_layout_version_ends_hero_and_category_placeholders(self):
        self.assertTrue(svc.has_as_delivered_composition(self.store))
        store_template_service.select_ready_template(store=self.store, actor=None, template_key="warm_boutique")
        layout_service.publish(self.store)  # a deliberate later publish by the merchant
        self.assertFalse(svc.has_as_delivered_composition(self.store))
        out = self.apply([_item("hero_banner", hero_slides=[]), _item("category_grid", top_categories=[])])
        self.assertEqual(self.kinds(out), [None, None])

    def test_a_draft_that_is_not_published_does_not_end_the_as_delivered_composition(self):
        layout_service.get_or_create_draft(self.store)
        self.assertTrue(svc.has_as_delivered_composition(self.store))

    def test_a_store_that_never_published_has_no_as_delivered_composition(self):
        store = _store(onboarding_required_at=timezone.now())
        self.assertFalse(svc.has_as_delivered_composition(store))

    def test_legacy_stores_are_never_as_delivered(self):
        legacy = _store()
        _publish_template(legacy)
        self.assertFalse(svc.has_as_delivered_composition(legacy))
