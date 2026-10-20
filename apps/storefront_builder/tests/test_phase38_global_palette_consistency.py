from pathlib import Path

from django.conf import settings as django_settings

from apps.storefront_builder import appearance_registry, layout_preset_registry, section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase38GlobalPaletteRegistryTests(StorefrontBuilderViewsTestCase):
    def test_catalog_colorful_has_exact_reference_rail_tones(self):
        palette = appearance_registry.get_palette("catalog-colorful")
        self.assertIsNotNone(palette)
        self.assertEqual(
            palette.section_tones,
            ("#F53247", "#16B95F", "#C56B00", "#352196", "#056CAE"),
        )

    def test_one_click_palette_changes_semantic_section_tones(self):
        catalog = appearance_registry.resolve_section_tones({"palette_slug": "catalog-colorful"})
        ocean = appearance_registry.resolve_section_tones({"palette_slug": "ocean"})
        self.assertNotEqual(catalog, ocean)
        self.assertEqual(catalog[0], "#F53247")

    def test_reference_preset_uses_palette_roles_not_fixed_hex(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        self.assertEqual(preset.default_palette_slug, "catalog-colorful")
        rails = [
            entry.settings["background"]
            for entry in preset.pages["home"]
            if entry.section_key == "product_section"
            and (entry.settings or {}).get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertEqual(len(rails), 5)
        self.assertEqual(
            {item["palette_role"] for item in rails},
            {"tone-1", "tone-2", "tone-3", "tone-4", "tone-5"},
        )
        self.assertTrue(all("color" not in item for item in rails))


class Phase38PaletteBackgroundEditorTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.sections.all().delete()
        self.page.containers.all().delete()

    def test_palette_pattern_background_validates(self):
        cleaned = section_registry.validate_background_settings({
            "mode": "palette_pattern",
            "palette_role": "tone-3",
            "pattern_slug": "commerce-doodle",
        })
        self.assertEqual(cleaned["mode"], "palette_pattern")
        self.assertEqual(cleaned["palette_role"], "tone-3")
        self.assertEqual(cleaned["color"], "")

    def test_custom_colour_remains_independent(self):
        cleaned = section_registry.validate_background_settings({
            "mode": "color",
            "color": "#123456",
        })
        self.assertEqual(cleaned["mode"], "color")
        self.assertEqual(cleaned["color"], "#123456")
        self.assertEqual(cleaned["palette_role"], "")


class Phase38GlobalCssContractTests(StorefrontBuilderViewsTestCase):
    def test_core_shell_uses_brand_tokens(self):
        root = Path(django_settings.BASE_DIR)
        layout_css = (root / "apps/core/static/css/layout.css").read_text(encoding="utf-8")
        tokens_css = (root / "apps/core/static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn("background:var(--brand-primary,#10b981)", layout_css)
        self.assertIn("background:var(--brand-text,#4b4b53)", layout_css)
        self.assertIn('.rsec[data-bg-mode="palette_pattern"]', tokens_css)
        self.assertIn("--palette-tone-5:", tokens_css)
