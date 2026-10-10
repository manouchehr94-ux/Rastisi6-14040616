import re
from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry
from apps.storefront_builder.palette_pack_64 import CURATED_PALETTE_PACK_64_ADDITIONS
from apps.storefront_builder.services import layout_service


class Palette64RegistryContractTests(SimpleTestCase):
    def test_public_palette_library_has_the_release_palettes(self):
        # 64 release palettes + the three reference-template palettes
        # (``spectrum-stationery`` 51, ``orchid-retail`` 52, ``pastel-lilac`` 53).
        self.assertEqual(len(appearance_registry.list_palettes()), 67)
        for slug in ("spectrum-stationery", "orchid-retail", "pastel-lilac"):
            self.assertIsNotNone(appearance_registry.get_palette(slug))

    def test_curated_pack_adds_26_stable_palettes(self):
        self.assertEqual(len(CURATED_PALETTE_PACK_64_ADDITIONS), 26)
        slugs = [entry["slug"] for entry in CURATED_PALETTE_PACK_64_ADDITIONS]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(slug.startswith("uupm-") for slug in slugs))
        self.assertTrue(all(appearance_registry.get_palette(slug) is not None for slug in slugs))

    def test_all_64_palettes_have_valid_storefront_tokens(self):
        color_keys = {"primary", "secondary", "accent", "background", "surface", "text", "muted", "border"}
        role_keys = {"header_bg", "header_text", "nav_bg", "nav_text", "card_bg", "footer_bg", "footer_text", "price"}
        hex_color = re.compile(r"^#[0-9A-F]{6}$")
        for palette in appearance_registry.list_palettes():
            self.assertEqual(set(palette.colors), color_keys, palette.slug)
            self.assertTrue(all(hex_color.match(value) for value in palette.colors.values()), palette.slug)
            roles = appearance_registry.resolve_theme_roles({"palette_slug": palette.slug})
            self.assertEqual(set(roles), role_keys, palette.slug)
            self.assertTrue(all(hex_color.match(value) for value in roles.values()), palette.slug)

    def test_every_palette_is_accepted_with_every_template(self):
        for template in appearance_registry.list_templates():
            for palette in appearance_registry.list_palettes():
                cleaned = layout_service.validate_appearance_config({
                    "template_slug": template.slug,
                    "palette_slug": palette.slug,
                })
                self.assertEqual(cleaned["template_slug"], template.slug)
                self.assertEqual(cleaned["palette_slug"], palette.slug)

    def test_single_color_override_changes_only_that_token(self):
        slug = "uupm-trust-blue"
        base = appearance_registry.resolve_colors({"palette_slug": slug, "color_overrides": {}})
        changed = appearance_registry.resolve_colors({
            "palette_slug": slug,
            "color_overrides": {"text": "#123456"},
        })
        self.assertEqual(changed["text"], "#123456")
        for key in set(base) - {"text"}:
            self.assertEqual(changed[key], base[key], key)

    def test_single_region_override_changes_only_that_region(self):
        slug = "uupm-trust-blue"
        base = appearance_registry.resolve_theme_roles({"palette_slug": slug, "theme_overrides": {}})
        changed = appearance_registry.resolve_theme_roles({
            "palette_slug": slug,
            "theme_overrides": {"footer_bg": "#123456"},
        })
        self.assertEqual(changed["footer_bg"], "#123456")
        for key in set(base) - {"footer_bg"}:
            self.assertEqual(changed[key], base[key], key)

    def test_palette_gallery_has_search_and_no_template_filter_contract(self):
        template_path = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "storefront_builder" / "partials" / "appearance_panel.html"
        source = template_path.read_text(encoding="utf-8")
        self.assertIn('id="sfbPaletteSearch"', source)
        self.assertIn("paletteQuery", source)
        self.assertNotIn("palette.allowed_templates", source)
        self.assertNotIn("template_palette", source)
