"""RS-01 — an existing MerchantCollection can be the source of a ``product_section`` (reference only, no copied
memberships), selected / changed / cleared through the one R4 Resource Picker + mutation queue."""

from pathlib import Path

from apps.catalog.models import Product
from apps.catalog.services import collection_service
from apps.storefront_builder.r4_views import _summary_collection_label
from apps.storefront_builder.resource_source import resource_source_from_section_settings
from apps.storefront_builder.services import section_data_service

from .test_r4_resource_picker import R4ResourcePickerTestCase, _second_store


class CollectionSourceBase(R4ResourcePickerTestCase):
    def setUp(self):
        super().setUp()
        self.coll = self._make_collection(name="تخفیف‌های منتخب", slug="rs01-picks")
        self.products = [
            self._make_product(name=f"کالای {i}", slug=f"rs01-p{i}", sku=f"RS01-{i}") for i in range(3)
        ]
        for product in self.products:
            collection_service.add_product(self.coll, product)

    def _pick(self, collection_id, **extra):
        patch = self._source_patch(
            kind="product", mode="auto", auto_rule="by_collection", auto_parameters={"source_id": collection_id},
        )
        patch.update(extra)
        return self._post_mutation({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings", "section_id": self.product_section.pk, "patch": patch,
            },
        })


class PickerOffersCollectionsTests(CollectionSourceBase):
    def test_product_picker_lists_active_same_store_collections_with_visible_counts(self):
        self._make_collection(name="غیرفعال", slug="rs01-off").__class__.objects.filter(slug="rs01-off").update(is_active=False)
        self._make_collection(store=_second_store(), name="کالکشن بیگانه", slug="rs01-foreign")
        html = self.client.get(self._picker_url(kind="product")).content.decode()
        self.assertIn('data-r4-picker-mode="collection"', html)
        self.assertIn("تخفیف‌های منتخب", html)
        self.assertIn("3 کالای قابل نمایش", html)
        self.assertNotIn("غیرفعال", html)
        self.assertNotIn("کالکشن بیگانه", html)

    def test_brand_picker_has_no_collection_tab(self):
        html = self.client.get(self._picker_url(kind="brand")).content.decode()
        self.assertNotIn('data-r4-picker-mode="collection"', html)

    def test_invisible_members_are_not_counted(self):
        Product.objects.filter(pk=self.products[0].pk).update(status=Product.Status.DRAFT)
        html = self.client.get(self._picker_url(kind="product")).content.decode()
        self.assertIn("2 کالای قابل نمایش", html)

    def test_editor_script_wires_the_collection_mode(self):
        js = (Path(__file__).resolve().parents[1] / "static/storefront_builder/r4_editor.js").read_text(encoding="utf-8")
        self.assertIn("auto_rule: 'by_collection'", js)
        self.assertIn("data-r4-picker-collection", js)


class SelectChangeClearTests(CollectionSourceBase):
    def test_pick_stores_a_reference_not_a_copy_and_keeps_title_and_limit(self):
        self.product_section.settings = {**self.product_section.settings, "title": "تخفیف‌ها", "item_limit": 8}
        self.product_section.save(update_fields=["settings"])
        resp = self._pick(self.coll.pk)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product_section.refresh_from_db()
        settings = self.product_section.settings
        self.assertEqual(settings["data_source"], "collection")
        self.assertEqual(settings["source_id"], self.coll.pk)
        self.assertEqual(settings["product_ids"], [])
        self.assertEqual(settings["title"], "تخفیف‌ها")
        self.assertEqual(settings["item_limit"], 8)

    def test_membership_changes_are_reflected_without_reselecting(self):
        self._pick(self.coll.pk)
        self.product_section.refresh_from_db()
        store = self.store
        got = [p.pk for p in section_data_service.resolve_products(store, self.product_section.settings)[0]]
        self.assertEqual(sorted(got), sorted(p.pk for p in self.products))
        extra = self._make_product(name="تازه", slug="rs01-new", sku="RS01-NEW")
        collection_service.add_product(self.coll, extra)
        got = [p.pk for p in section_data_service.resolve_products(store, self.product_section.settings)[0]]
        self.assertIn(extra.pk, got)
        self.assertEqual(len(got), 4)

    def test_collection_order_and_item_limit_are_honoured(self):
        self.product_section.settings = {**self.product_section.settings, "item_limit": 2}
        self.product_section.save(update_fields=["settings"])
        self._pick(self.coll.pk)
        self.product_section.refresh_from_db()
        got = section_data_service.resolve_products(self.store, self.product_section.settings)[0]
        self.assertEqual(len(got), 2)

    def test_changing_to_another_collection(self):
        other = self._make_collection(name="دوم", slug="rs01-second")
        collection_service.add_product(other, self.products[0])
        self._pick(self.coll.pk)
        self.draft.refresh_from_db()
        self.assertEqual(self._pick(other.pk).status_code, 200)
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["source_id"], other.pk)
        got = section_data_service.resolve_products(self.store, self.product_section.settings)[0]
        self.assertEqual([p.pk for p in got], [self.products[0].pk])

    def test_clearing_returns_to_automatic_without_a_dangling_reference(self):
        self._pick(self.coll.pk)
        self.draft.refresh_from_db()
        resp = self._post_mutation({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings", "section_id": self.product_section.pk,
                "patch": self._source_patch(kind="product", mode="auto", auto_rule="newest"),
            },
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["data_source"], "newest")
        self.assertIsNone(self.product_section.settings.get("source_id"))

    def test_manual_selection_still_works_after_a_collection(self):
        self._pick(self.coll.pk)
        self.draft.refresh_from_db()
        resp = self._post_mutation({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.update_settings", "section_id": self.product_section.pk,
                "patch": self._source_patch(kind="product", mode="manual", manual_ids=[self.products[1].pk]),
            },
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.product_section.refresh_from_db()
        self.assertEqual(self.product_section.settings["data_source"], "manual")
        self.assertEqual(self.product_section.settings["product_ids"], [self.products[1].pk])


class TenancyAndEmptyStateTests(CollectionSourceBase):
    def test_foreign_collection_is_rejected_and_nothing_changes(self):
        foreign = self._make_collection(store=_second_store(), name="بیگانه", slug="rs01-alien")
        before = dict(self.product_section.settings)
        revision = self.draft.edit_revision
        resp = self._pick(foreign.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "invalid_resource_ownership")
        self.product_section.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(self.product_section.settings, before)
        self.assertEqual(self.draft.edit_revision, revision)

    def test_empty_inactive_or_deleted_collection_renders_nothing_not_other_data(self):
        self._pick(self.coll.pk)
        self.product_section.refresh_from_db()
        settings = self.product_section.settings
        self.coll.items.all().delete()
        self.assertEqual(section_data_service.resolve_products(self.store, settings)[0], [])
        for product in self.products:
            collection_service.add_product(self.coll, product)
        collection_service.deactivate_collection(self.coll)
        self.assertEqual(section_data_service.resolve_products(self.store, settings)[0], [])
        self.coll.delete()
        self.assertEqual(section_data_service.resolve_products(self.store, settings)[0], [])

    def test_summary_label_names_the_collection_or_explains_the_problem(self):
        self._pick(self.coll.pk)
        self.product_section.refresh_from_db()
        source = resource_source_from_section_settings("product_section", self.product_section.settings)
        self.assertEqual(_summary_collection_label(self.store, source), "تخفیف‌های منتخب")
        collection_service.deactivate_collection(self.coll)
        self.assertIn("غیرفعال", _summary_collection_label(self.store, source))
        self.coll.delete()
        self.assertIn("پیدا نشد", _summary_collection_label(self.store, source))
        self.assertIsNone(_summary_collection_label(
            self.store, resource_source_from_section_settings("product_section", {"data_source": "newest"}),
        ))
