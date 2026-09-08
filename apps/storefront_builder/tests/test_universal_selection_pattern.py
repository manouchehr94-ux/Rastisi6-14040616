from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.storefront_builder.section_registry import (
    _validate_brand_carousel_settings,
    _validate_category_grid_settings,
    _validate_collection_tiles_settings,
    _validate_product_section_settings,
    default_brand_carousel_settings,
    default_category_grid_settings,
    default_collection_tiles_settings,
)


BASE = Path(settings.BASE_DIR)


class UniversalSelectionPatternTests(SimpleTestCase):
    def _read(self, rel):
        return (BASE / rel).read_text(encoding="utf-8")

    def test_ordered_ids_are_preserved_by_existing_validators(self):
        self.assertEqual(
            _validate_brand_carousel_settings({"brand_ids": [7, 3, 9], "display_mode": "grid"})["brand_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_category_grid_settings({"category_ids": [7, 3, 9], "display_mode": "grid", "item_limit": 12})["category_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_collection_tiles_settings({"collection_ids": [7, 3, 9], "tile_style": "grid"})["collection_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_product_section_settings({
                "data_source": "manual", "product_ids": [7, 3, 9], "item_limit": 8,
                "display_mode": "carousel", "show_view_all": True,
            })["product_ids"],
            [7, 3, 9],
        )

    def test_existing_validators_dedupe_without_reordering_and_keep_caps(self):
        self.assertEqual(
            _validate_brand_carousel_settings({"brand_ids": [7, 3, 7, 9], "display_mode": "grid"})["brand_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            len(_validate_brand_carousel_settings({"brand_ids": list(range(1, 40)), "display_mode": "grid"})["brand_ids"]),
            24,
        )
        self.assertEqual(
            len(_validate_category_grid_settings({"category_ids": list(range(1, 30)), "display_mode": "grid", "item_limit": 12})["category_ids"]),
            12,
        )
        self.assertEqual(
            len(_validate_collection_tiles_settings({"collection_ids": list(range(1, 30)), "tile_style": "grid"})["collection_ids"]),
            12,
        )

    def test_empty_non_product_ids_keep_automatic_compatibility(self):
        self.assertEqual(default_brand_carousel_settings()["brand_ids"], [])
        self.assertEqual(default_category_grid_settings()["category_ids"], [])
        self.assertEqual(default_collection_tiles_settings()["collection_ids"], [])
        self.assertEqual(_validate_brand_carousel_settings({"display_mode": "grid"})["brand_ids"], [])
        self.assertEqual(_validate_category_grid_settings({"display_mode": "grid", "item_limit": 12})["category_ids"], [])
        self.assertEqual(_validate_collection_tiles_settings({"tile_style": "grid"})["collection_ids"], [])

    def test_shared_picker_is_wired_for_all_four_sections(self):
        form = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html")
        picker = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html")
        self.assertEqual(form.count("universal_selection_picker.html"), 4)
        for marker in ("انتخاب خودکار", "انتخاب دستی", "انتخاب‌شده:", "selectionMode", "selectionQuery"):
            self.assertIn(marker, picker)
        for field in ("product_ids", "brand_ids", "category_ids", "collection_ids"):
            self.assertIn(field, self._read("apps/storefront_builder/views.py"))
        self.assertIn("productSectionForm", form)
        self.assertIn("multiPickerForm", form)

    def test_store_ownership_guard_is_called_before_settings_save(self):
        # Phase 4 (Task 2) — the guard now delegates to the ONE shared,
        # DB-backed check (``section_data_service.validate_resource_source_ownership``)
        # via a typed ``ResourceSource`` projection, instead of an inline
        # per-model dict lookup — the same check the R4 mutation service
        # uses, so legacy and R4 can no longer disagree on ownership
        # semantics for these four sections.
        views = self._read("apps/storefront_builder/views.py")
        call = "_validate_universal_selection_ownership(request, section.section_key, cleaned)"
        self.assertIn(call, views)
        self.assertLess(views.index(call), views.index("section.settings = cleaned"))
        self.assertIn("resource_source_from_section_settings", views)
        self.assertIn("section_data_service.validate_resource_source_ownership", views)

        section_data_service = self._read(
            "apps/storefront_builder/services/section_data_service.py"
        )
        self.assertIn("filter(store=store, pk__in=", section_data_service)
        for model in ("Brand", "Category", "MerchantCollection"):
            self.assertIn(model, section_data_service)
        # Product ownership is checked via ``searchable_products(store)``,
        # not a bare ``Product.objects.filter`` — the same Store-scoped query
        # every other product ownership check in this domain uses.
        self.assertIn("searchable_products(store)", section_data_service)

    def test_universal_context_uses_existing_picker_data_and_limits(self):
        views = self._read("apps/storefront_builder/views.py")
        self.assertIn("def _universal_selection_context(section, context)", views)
        for marker in (
            '"product_section": ("product", "product_ids", 60',
            '"category_grid": ("category", "category_ids", 12',
            '"brand_carousel": ("brand", "brand_ids", 24',
            '"collection_tiles": ("collection", "collection_ids", 12',
        ):
            self.assertIn(marker, views)

    def test_product_automatic_sources_remain_available(self):
        form = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html")
        for value in ("newest", "discounted", "best_sellers", "most_viewed", "collection", "category", "brand"):
            self.assertIn(f'value="{value}"', form)
        self.assertNotIn('value="manual">کالاهای دستی', form)
        self.assertIn("selectionMode === 'automatic'", form)

    def test_shared_picker_does_not_link_to_customer_login(self):
        picker = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html")
        self.assertNotIn("login", picker.lower())
        self.assertNotIn("account", picker.lower())
        self.assertNotIn("href=", picker.lower())

    def test_r3_modal_contract_remains_unchanged(self):
        css = self._read("apps/storefront_builder/static/css/storefront_builder_r3.css")
        modal = self._read("apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html")
        self.assertIn("width:min(70vw,1100px)", css)
        self.assertIn('id="sfbR3ModalBody"', modal)
        self.assertIn("بازگشت", modal)
        self.assertIn('x-teleport="body"', modal)


class UniversalSelectionSourceIsolationTests(SimpleTestCase):
    def test_no_model_or_migration_contract_is_required(self):
        # The feature stays on StorefrontSection.settings JSON and existing fields.
        form = (BASE / "apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html").read_text(encoding="utf-8")
        self.assertIn("selection_input_name", form)
