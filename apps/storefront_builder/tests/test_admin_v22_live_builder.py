from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class AdminV22LiveBuilderContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def _read(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")


    def test_builder_drawers_overlay_instead_of_taking_canvas_columns(self):
        css = self._read("apps/storefront_builder/static/css/storefront_builder_v22.css")
        self.assertIn(".sfb-v22-workspace .sfb-v3-sidebar-right", css)
        self.assertIn(".sfb-v22-workspace .sfb-v3-inspector", css)
        self.assertIn("position:absolute !important", css)
        self.assertIn(".sfb-v22-drawer-backdrop", css)
        self.assertIn("width:370px", css)
        self.assertIn("width:430px", css)

    def test_edit_preview_uses_one_obvious_edit_action_and_exact_entity_labels(self):
        css = self._read("apps/storefront_builder/static/css/storefront_builder_preview_v22.css")
        self.assertIn("button:not([data-open-settings])", css)
        self.assertIn("[data-open-settings]::after", css)
        self.assertIn('content:"ویرایش"', css)
        self.assertIn("[data-admin-edit-kind]::after", css)
        self.assertIn('content:"✎ ویرایش"', css)
        self.assertIn("ویرایش هدر", css)
        self.assertIn("ویرایش فوتر", css)


    def test_visible_storefront_items_expose_exact_edit_metadata_in_builder_preview(self):
        contracts = {
            "apps/storefront_builder/templates/storefront_builder/partials/hero_slider_body.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="hero-slides"'),
            "apps/storefront_builder/templates/storefront_builder/sections/single_banner.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="banners"'),
            "apps/storefront_builder/templates/storefront_builder/sections/multi_banner.html": ('data-admin-edit-kind="media"', 'data-admin-media-kind="banners"'),
            "apps/storefront_builder/templates/storefront_builder/sections/category_grid.html": ('data-admin-edit-kind="category"', 'data-admin-edit-id'),
            "apps/storefront_builder/templates/storefront_builder/sections/brand_carousel.html": ('data-admin-edit-kind="brand"', 'data-admin-edit-id'),
            "apps/storefront_builder/templates/storefront_builder/sections/collection_tiles.html": ('data-admin-edit-kind="collection"', 'data-admin-edit-id'),
        }
        for relpath, needles in contracts.items():
            source = self._read(relpath)
            for needle in needles:
                self.assertIn(needle, source, relpath)

    def test_preview_understands_clean_preview_and_edit_modes(self):
        preview = self._read("apps/storefront_builder/templates/storefront_builder/preview.html")
        self.assertIn("sfb:setMode", preview)
        self.assertIn("builderMode", preview)
        self.assertIn("sfb:openFooterSettings", preview)
        self.assertIn("css/storefront_builder_preview_v22.css", preview)
