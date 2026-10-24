"""Unit pins for the generic composition primitives of the R4 engine (phone layout of a card row, vertical placement, finer image ratios,
container phone order / slider, hero picture side + column share, footer column order / count / gap, PDP info-column order).
All of them are sparse and default-off: a Store that never touches them renders exactly as before."""

from django.test import SimpleTestCase

from apps.storefront_builder import design_block, pdp_settings, section_registry, shell_geometry
from apps.storefront_builder.services import container_service


def _design(section_key, raw):
    return design_block.validate_design_settings(raw, design_block.applicable_properties(section_key))


class DesignCompositionPropertyTests(SimpleTestCase):
    def test_phone_layout_and_vertical_placement_are_validated_choices(self):
        cleaned = _design("multi_banner", {"mobile_layout": "slider2", "image_ratio": "ultrawide"})
        self.assertEqual(cleaned, {"mobile_layout": "slider2", "image_ratio": "ultrawide"})
        self.assertEqual(_design("rich_text", {"valign": "center"}), {"valign": "center"})
        for key, bad in (("multi_banner", {"mobile_layout": "carousel"}), ("rich_text", {"valign": "middle"}),
                         ("multi_banner", {"image_ratio": "7/5"})):
            with self.assertRaises(design_block.DesignSettingsError):
                _design(key, bad)

    def test_neutral_values_are_dropped_so_the_block_stays_sparse(self):
        self.assertEqual(_design("rich_text", {"valign": "", "align": None}), {})

    def test_render_attributes_expose_flags_and_variables_only_when_set(self):
        applicable = design_block.applicable_properties("rich_text") + design_block.applicable_properties("multi_banner")
        self.assertEqual(design_block.render_attributes({}, applicable).get("flags", ""), "")
        attrs = design_block.render_attributes({"mobile_layout": "slider", "valign": "end"}, applicable)
        flags = str(attrs.get("data_d") or attrs.get("flags") or "")
        self.assertIn("m-slider", flags)
        self.assertIn("valign", flags)
        self.assertIn("flex-end", str(attrs))

    def test_sections_without_the_capability_do_not_offer_the_property(self):
        # a section that never grants the capability rejects the key (never silently stored)
        with self.assertRaises(design_block.DesignSettingsError):
            _design("announcement_bar", {"mobile_layout": "slider"})

    def test_card_row_sections_offer_the_phone_layout(self):
        for key in ("multi_banner", "trust_features", "testimonials", "collection_tiles", "blog_posts", "quick_links"):
            self.assertIn("mobile_layout", design_block.applicable_properties(key), key)


class ContainerPhoneSettingsTests(SimpleTestCase):
    def test_mobile_order_and_slider_are_clamped_to_the_known_values(self):
        cleaned = container_service.effective_container_settings({"mobile_order": "reverse", "mobile_mode": "slider"})
        self.assertEqual((cleaned["mobile_order"], cleaned["mobile_mode"]), ("reverse", "slider"))
        cleaned = container_service.effective_container_settings({"mobile_order": "zigzag", "mobile_mode": "carousel"})
        self.assertEqual((cleaned["mobile_order"], cleaned["mobile_mode"]), ("normal", "stack"))

    def test_defaults_are_unchanged(self):
        cleaned = container_service.effective_container_settings({})
        self.assertEqual((cleaned["mobile_order"], cleaned["mobile_mode"]), ("normal", "stack"))


class HeroPictureCompositionTests(SimpleTestCase):
    def test_image_side_and_split_ratio_are_sparse_choices(self):
        definition = section_registry.get_definition("hero_banner")
        cleaned = definition.validate_settings({"hero_style": "split", "image_side": "start", "split_ratio": "image_wide"})
        self.assertEqual((cleaned["image_side"], cleaned["split_ratio"]), ("start", "image_wide"))
        default = definition.validate_settings({"hero_style": "split"})
        self.assertNotIn("image_side", default)
        self.assertNotIn("split_ratio", default)
        self.assertNotIn("image_side", definition.validate_settings({"hero_style": "split", "image_side": "diagonal"}))


class FooterCompositionGeometryTests(SimpleTestCase):
    def test_column_order_count_and_gap_are_bounded_integers(self):
        cleaned = shell_geometry.validate_geometry(
            {"order_contact": 1, "order_about": 99, "column_count": 12, "column_gap": 500}, "footer")
        self.assertEqual(cleaned["order_contact"], 1)
        self.assertEqual(cleaned["order_about"], 9)
        self.assertEqual(cleaned["column_count"], 6)
        self.assertLessEqual(cleaned["column_gap"], 120)

    def test_style_fragment_carries_the_variables(self):
        style = shell_geometry.geometry_style({"order_contact": 1, "column_count": 3}, "footer")
        self.assertIn("--gf-o-contact:1", style)
        self.assertIn("--gf-cols:3", style)

    def test_empty_geometry_adds_nothing(self):
        self.assertEqual(shell_geometry.geometry_style({}, "footer"), "")


class PdpInfoOrderTests(SimpleTestCase):
    def test_default_order_is_never_stored(self):
        defaults = pdp_settings.effective_info_order(None)
        cleaned = pdp_settings.clean_product_main_settings({"info_order": [{"key": k} for k in defaults]})
        self.assertNotIn("info_order", cleaned)

    def test_custom_order_is_stored_and_completed(self):
        cleaned = pdp_settings.clean_product_main_settings({"info_order": [{"key": "trust"}, {"key": "price"}]})
        self.assertEqual([item["key"] for item in cleaned["info_order"]][:2], ["trust", "price"])
        effective = pdp_settings.effective_info_order(cleaned.get("info_order"))
        self.assertEqual(set(effective), set(pdp_settings.PRODUCT_INFO_BLOCK_KEYS))

    def test_unknown_blocks_are_ignored(self):
        cleaned = pdp_settings.clean_product_main_settings({"info_order": [{"key": "rocket"}, {"key": "trust"}]})
        self.assertEqual([item["key"] for item in cleaned["info_order"]], ["trust"])
