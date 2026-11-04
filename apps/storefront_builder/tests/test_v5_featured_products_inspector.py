"""«محصولات ویژه» (featured_products) opens its REAL R4 Inspector, also inside a nested Group, saves its product count, keeps everything else
a stored section already carried, and a Section of another Draft / store is still refused (404) — the contract the Windows QA 404 broke."""

import re
from decimal import Decimal
from pathlib import Path

from django.urls import reverse

from apps.catalog.models import Product
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service

from .test_v5_groups_service import _GroupBase

STATIC = Path(__file__).resolve().parents[1] / "static" / "storefront_builder"


class FeaturedProductsInspectorTests(_GroupBase):
    def setUp(self):
        super().setUp()
        for n in range(6):
            Product.objects.create(
                store=self.store, vendor=self.vendor, category=self.category, name=f"کالای ویژه {n}", slug=f"feat-{n}",
                sku=f"FEAT-{n}", price=Decimal("100000"), stock=5, status=Product.Status.ACTIVE,
            )

    def inspector(self, section):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))

    def featured_in_group(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        cell = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": cell.pk, "axis": "vertical", "count": 2})
        inner = self.cells(self.nested(cell))[0]
        return self.put(inner, "featured_products")

    def cards_in(self, html):
        block = html.split('data-section-key="featured_products"', 1)[1]
        block = re.split(r'data-section-key="', block, 1)[0]
        return len(re.findall(r'class="pcard(?:\s[^"]*)?"', block))

    def test_the_registry_gives_it_a_valid_schema_default_and_clamped_limit(self):
        definition = section_registry.get_definition("featured_products")
        self.assertIsNotNone(definition.settings_schema)
        keys = [f.key for f in definition.settings_schema.fields]
        self.assertIn("item_limit", keys)
        field = next(f for f in definition.settings_schema.fields if f.key == "item_limit")
        self.assertEqual((field.min_value, field.max_value, field.default), (2, 24, 8))
        self.assertEqual(definition.default_settings()["item_limit"], 8)    # plus the generic blocks the capability wrappers add
        self.assertEqual(definition.validate_settings({"item_limit": 999})["item_limit"], 24)
        self.assertEqual(definition.validate_settings({"item_limit": 0})["item_limit"], 2)
        with self.assertRaises(ValueError):
            definition.validate_settings({"item_limit": "x"})
        with self.assertRaises(ValueError):
            definition.validate_settings([])

    def test_the_real_inspector_answers_200_for_a_normal_row_and_for_a_nested_group(self):
        plain_section = self.put(self.cells(self.row())[0], "featured_products")
        response = self.inspector(plain_section)
        self.assertEqual(response.status_code, 200)
        self.assertIn("item_limit", response.content.decode())
        nested = self.featured_in_group()
        self.assertEqual(self.inspector(nested).status_code, 200)

    def test_the_limit_is_saved_and_changes_what_the_preview_shows(self):
        section = self.featured_in_group()
        self.mutate({"type": "section.update_settings", "section_id": section.pk, "patch": {"item_limit": 2}})
        section.refresh_from_db()
        self.assertEqual(section.settings["item_limit"], 2)
        self.assertEqual(self.cards_in(self.home_preview()), 2)
        self.mutate({"type": "section.update_settings", "section_id": section.pk, "patch": {"item_limit": 5}})
        self.assertEqual(self.cards_in(self.home_preview()), 5)

    def test_a_first_save_keeps_every_other_stored_setting(self):
        section = self.put(self.cells(self.row())[0], "featured_products")
        stored = {
            "title": "عنوان قدیمی", "card": {"style": "compact"}, "background": {"mode": "color", "color": "#EEF6F2"},
            "spacing": {"advanced": {"padding_top": 24}}, "design": {"radius": 18}, "responsive": {"hide_mobile": True},
            "custom_recipe_marker": "keep-me",
        }
        section.settings = {**stored}
        section.save(update_fields=["settings"])
        self.mutate({"type": "section.update_settings", "section_id": section.pk, "patch": {"item_limit": 4}})
        section.refresh_from_db()
        self.assertEqual(section.settings["item_limit"], 4)
        for key in ("title", "custom_recipe_marker"):
            self.assertEqual(section.settings[key], stored[key], key)
        for key in ("card", "background", "spacing", "design", "responsive"):
            self.assertIn(key, section.settings, f"{key} was dropped by the first Inspector save")

    def test_product_section_and_linked_image_still_open_their_inspectors(self):
        shelf = self.put(self.cells(self.row())[0], "product_section")
        image = self.put(self.cells(self.row())[0], "linked_image")
        self.assertEqual(self.inspector(shelf).status_code, 200)
        self.assertEqual(self.inspector(image).status_code, 200)

    def test_a_section_of_another_draft_or_store_is_still_refused(self):
        from apps.stores.models import Store

        section = self.featured_in_group()
        # the same id seen from a store that does not own it
        other = Store.objects.create(name="فروشگاه دیگر", slug="other-feat-store")
        foreign_layout = layout_service.get_or_create_layout(other)
        foreign_draft = layout_service.get_or_create_draft(other)
        foreign = layout_service.get_or_create_draft(other).get_page("home")
        stray = StorefrontSection.objects.create(page=foreign, section_key="featured_products", order=0, settings={})
        self.assertEqual(self.inspector(stray).status_code, 404)
        # a Section that is not in the ACTIVE Draft (e.g. a published version's copy) is refused too
        published_copy = StorefrontSection.objects.get(pk=section.pk)
        layout = layout_service.get_or_create_layout(self.store)
        layout_service.publish(self.store)
        self.assertEqual(self.inspector(published_copy).status_code, 404)
        self.assertEqual(foreign_layout.store_id, other.pk)
        self.assertEqual(foreign_draft.layout_id, foreign_layout.pk)
        self.assertEqual(layout.store_id, self.store.pk)

    def test_a_failed_inspector_request_is_reported_to_the_seller_not_swallowed(self):
        js = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
        helper = js[js.index("function reportInspectorFailure"):js.index("R4.openSection = function")]
        self.assertIn("R4.notify(message)", helper)
        self.assertIn("console.warn('R4 openSection failed'", helper)
        for status in ("404", "403", "500"[:2] + "0"):
            self.assertIn(status, helper)
        body = js[js.index("R4.openSection = function"):js.index("R4.closeInspector = closeInspector")]
        self.assertIn("reportInspectorFailure(url, response.status)", body)
        self.assertNotIn("the shell simply stays as it already was", body)
