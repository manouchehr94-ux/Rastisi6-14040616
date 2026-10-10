"""Template 51 ENGINE STABILIZATION — focused regression coverage.

Everything here is a generic ENGINE contract (semantic colours, the sparse ``design`` block, the product-row
presentation contract, ``decorative_strip``, ``category_source``, header/footer geometry, canvas-bound bleed,
layout-neutral builder chrome, the atomic preview refresh); the Template 51 recipe is asserted last and only as
DATA that uses those contracts. The real-browser geometry parity checks live in
``test_engine_parity_browser.py`` (opt-in, needs Chromium)."""

import json
import re
from pathlib import Path
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.catalog.models import Category
from apps.storefront_builder import (
    design_block,
    layout_preset_registry as lpr,
    section_registry,
    semantic_colors,
    shell_geometry,
)
from apps.storefront_builder.decorative_strip import build_view
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import category_selection, layout_service as svc
from apps.storefront_builder.services.render_service import build_render_items

from .test_r4_mutation_api import R4MutationApiTestCase
from .test_views import StorefrontBuilderViewsTestCase

APP = Path(__file__).resolve().parents[1]
BUILDER_CSS = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
LAYOUT_CSS = (APP.parent / "core" / "static" / "css" / "layout.css").read_text(encoding="utf-8")
EDITOR_JS = (APP / "static" / "storefront_builder" / "r4_editor.js").read_text(encoding="utf-8")


def _css_rules(css, needle):
    """(selector, body) pairs of the top-level and @media-nested rules whose selector contains ``needle``."""
    out = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = match.group(1).strip()
        if needle in selector:
            out.append((selector, match.group(2)))
    return out


# --------------------------------------------------------------------------------------------- colours
class SemanticColorTests(SimpleTestCase):
    def test_clean_accepts_empty_token_and_hex(self):
        self.assertEqual(semantic_colors.clean_semantic_color(""), "")
        self.assertEqual(semantic_colors.clean_semantic_color(None), "")
        self.assertEqual(semantic_colors.clean_semantic_color("token:accent"), "token:accent")
        self.assertEqual(semantic_colors.clean_semantic_color("#aabbcc"), "#AABBCC")

    def test_clean_rejects_free_css_and_unknown_tokens(self):
        for bad in ("red", "url(x)", "#abc", "token:nope", "var(--x)", "#GGGGGG"):
            with self.assertRaises(semantic_colors.SemanticColorError, msg=bad):
                semantic_colors.clean_semantic_color(bad)

    def test_tokens_resolve_to_the_appearance_variables_and_hex_gets_an_accessible_foreground(self):
        self.assertEqual(semantic_colors.semantic_color_css("token:primary"), "var(--brand-primary)")
        self.assertEqual(semantic_colors.semantic_foreground_css("token:primary"), "var(--brand-primary-fg)")
        self.assertEqual(semantic_colors.semantic_foreground_css("#000000"), "#FFFFFF")
        self.assertEqual(semantic_colors.semantic_foreground_css("#FFFFFF"), "#000000")
        self.assertEqual(semantic_colors.semantic_color_css(""), "")

    def test_every_token_has_a_label_and_a_foreground(self):
        self.assertEqual(set(semantic_colors.SEMANTIC_COLOR_TOKENS), set(semantic_colors.SEMANTIC_COLOR_TOKEN_LABELS_FA))
        for color_var, fg_var in semantic_colors.SEMANTIC_COLOR_TOKENS.values():
            self.assertTrue(color_var.startswith("--") and fg_var.startswith("--"))


class DesignBlockTests(SimpleTestCase):
    def test_validator_is_sparse_clamped_and_semantic(self):
        applicable = design_block.applicable_properties("product_section")
        cleaned = design_block.validate_design_settings(
            {"radius": "99", "heading_color": "token:accent", "border_width": "", "shadow": "on", "price_color": "#112233"},
            applicable,
        )
        self.assertEqual(cleaned, {
            "radius": 40, "heading_color": "token:accent", "shadow": "on", "price_color": "#112233",
        })
        self.assertEqual(design_block.validate_design_settings(None, applicable), {})

    def test_inapplicable_or_unknown_property_is_rejected(self):
        with self.assertRaises(design_block.DesignSettingsError):
            design_block.validate_design_settings({"gap": 4}, design_block.applicable_properties("surface_panel"))
        with self.assertRaises(design_block.DesignSettingsError):
            design_block.validate_design_settings({"nope": 1}, design_block.applicable_properties("product_section"))
        with self.assertRaises(design_block.DesignSettingsError):
            design_block.validate_design_settings({"accent_color": "red"}, design_block.applicable_properties("product_section"))

    def test_render_attributes_are_empty_without_a_block_and_token_based_with_one(self):
        empty = design_block.render_attributes({})
        self.assertEqual((empty["flags"], empty["style"]), ("", ""))
        self.assertFalse(any(empty[k] for k in ("hide_desktop", "hide_tablet", "hide_mobile")))
        attrs = design_block.render_attributes({
            "surface_color": "token:surface", "radius": 12, "shadow": "on", "border_width": 2,
            "button_fill": "#336699", "columns_desktop": 3,
        })
        for flag in ("surface", "radius", "shadow", "border", "btnfill", "cols"):
            self.assertIn(flag, attrs["flags"].split())
        self.assertIn("--d-surface:var(--brand-surface)", attrs["style"])
        self.assertIn("--d-radius:12px", attrs["style"])
        self.assertIn("--d-btn-bg:#336699", attrs["style"])
        self.assertIn("--d-btn-fg:#FFFFFF", attrs["style"])
        self.assertIn("--cols-desktop:3", attrs["style"])

    def test_every_registry_property_is_applicable_somewhere_and_applicable_keys_exist(self):
        used = {key for keys in design_block.DESIGN_APPLICABLE.values() for key in keys}
        self.assertTrue(used <= set(design_block.DESIGN_PROPERTIES))
        for section_key in design_block.DESIGN_APPLICABLE:
            groups = design_block.serialize_registry_for_inspector(section_key)
            shown = {p["key"] for g in groups for p in g["properties"]}
            self.assertEqual(shown, set(design_block.applicable_properties(section_key)))

    def test_design_field_is_projected_onto_the_schema_before_background(self):
        for key in design_block.DESIGN_APPLICABLE:
            fields = section_registry.get_definition(key).settings_schema.fields
            keys = [f.key for f in fields]
            self.assertIn("design", keys, key)
            if "background" in keys:
                self.assertEqual(keys[-1], "background", key)


# ---------------------------------------------------------------------------- product-row presentation
class ProductPresentationContractTests(SimpleTestCase):
    def _clean(self, **extra):
        raw = {"data_source": "newest"} | extra
        return section_registry.get_definition("product_section").validate_settings(raw)

    def test_defaults_write_nothing(self):
        cleaned = self._clean()
        for key in ("desktop_layout", "overflow_mode", "show_scrollbar", "carousel_navigation", "gap",
                    "desktop_columns", "tablet_columns", "mobile_columns"):
            self.assertNotIn(key, cleaned)

    def test_presentation_keys_round_trip_and_are_clamped(self):
        cleaned = self._clean(
            desktop_layout="grid", overflow_mode="visible", show_scrollbar=False, carousel_navigation="dots",
            desktop_columns="9", tablet_columns=2, mobile_columns="۱", gap="۲۲",
        )
        self.assertEqual(cleaned["desktop_layout"], "grid")
        self.assertEqual(cleaned["overflow_mode"], "visible")
        self.assertIs(cleaned["show_scrollbar"], False)
        self.assertEqual(cleaned["carousel_navigation"], "dots")
        self.assertEqual((cleaned["desktop_columns"], cleaned["tablet_columns"], cleaned["mobile_columns"]), (8, 2, 1))
        self.assertEqual(cleaned["gap"], 22)

    def test_neutral_and_invalid_choices_are_dropped(self):
        cleaned = self._clean(desktop_layout="inherit", overflow_mode="scroll", show_scrollbar=True,
                              carousel_navigation="none")
        for key in ("desktop_layout", "overflow_mode", "show_scrollbar", "carousel_navigation"):
            self.assertNotIn(key, cleaned)
        self.assertNotIn("overflow_mode", self._clean(overflow_mode="hidden-nonsense"))

    def test_schema_exposes_every_presentation_control_in_the_inspector(self):
        keys = {f.key for f in section_registry.get_definition("product_section").settings_schema.fields}
        self.assertTrue({"desktop_layout", "overflow_mode", "show_scrollbar", "carousel_navigation",
                         "desktop_columns", "tablet_columns", "mobile_columns", "gap", "design"} <= keys)

    def test_css_contract_hides_the_rail_and_makes_a_non_scrolling_grid(self):
        css = (APP.parent / "catalog" / "static" / "css" / "product_card.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'\.pcarousel\[data-scrollbar="off"\]\{[^}]*scrollbar-width:none')
        self.assertRegex(css, r'\.pcarousel\[data-overflow="visible"\]\{[^}]*flex-wrap:wrap')
        self.assertRegex(css, r'\.pcarousel\[data-desktop-layout="grid"\]\{[^}]*display:grid[^}]*overflow:visible')


class ProductPresentationRenderTests(R4MutationApiTestCase):
    def _preview_html(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()

    def test_attributes_and_navigation_markup_follow_the_settings(self):
        self.section.delete()
        StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0, settings={
            "data_source": "newest", "item_limit": 6, "desktop_layout": "grid", "overflow_mode": "visible",
            "show_scrollbar": False, "carousel_navigation": "arrows", "gap": 22, "desktop_columns": 3,
        })
        html = self._preview_html()
        self.assertIn('data-desktop-layout="grid"', html)
        self.assertIn('data-overflow="visible"', html)
        self.assertIn('data-scrollbar="off"', html)
        self.assertIn("--pcarousel-gap:22px", html)
        self.assertIn("--cols-desktop:3", html)
        self.assertIn("pcarousel-shell", html)
        self.assertIn("pcarousel-prev", html)

    def test_dots_navigation_and_defaults(self):
        self.section.delete()
        StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0,
                                         settings={"data_source": "newest", "item_limit": 8, "carousel_navigation": "dots"})
        html = self._preview_html()
        self.assertIn("pcarousel-dots", html)
        self.assertNotIn("pcarousel-prev", html)
        StorefrontSection.objects.filter(page__version=self.draft).delete()
        StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0,
                                         settings={"data_source": "newest", "item_limit": 8})
        html = self._preview_html()
        self.assertNotIn("data-desktop-layout", html)
        self.assertNotIn("data-scrollbar", html)
        self.assertNotIn("pcarousel-shell", html)

    def test_inspector_round_trip_for_every_presentation_control(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0,
                                                   settings={"data_source": "newest", "item_limit": 8, "responsive": {"desktop_columns": 5}})
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        self.assertEqual(inspector.status_code, 200)
        for key in ("desktop_layout", "overflow_mode", "show_scrollbar", "carousel_navigation", "desktop_columns", "gap"):
            self.assertContains(inspector, f'data-r4-field-key="{key}"')
        self.assertContains(inspector, 'data-r4-field-type="design"')
        content = inspector.content.decode()
        start = content.index('id="r4InspectorFieldValues"')
        values = json.loads(content[content.index(">", start) + 1:content.index("</script>", start)])
        self.assertEqual(values["desktop_columns"], 5)  # legacy responsive value is what the control shows
        revision = self.draft.edit_revision
        for patch_value in ({"desktop_layout": "grid"}, {"overflow_mode": "clip"}, {"show_scrollbar": False},
                            {"carousel_navigation": "arrows"}, {"gap": 18}, {"desktop_columns": 3}):
            response = self._post_json({"base_revision": revision, "mutation": {
                "type": "section.update_settings", "section_id": section.pk, "patch": patch_value}})
            self.assertEqual(response.status_code, 200, patch_value)
            revision = response.json()["new_revision"]
        section.refresh_from_db()
        self.assertEqual(section.settings["desktop_layout"], "grid")
        self.assertEqual(section.settings["overflow_mode"], "clip")
        self.assertIs(section.settings["show_scrollbar"], False)
        self.assertEqual(section.settings["carousel_navigation"], "arrows")
        self.assertEqual((section.settings["gap"], section.settings["desktop_columns"]), (18, 3))
        # switching a control back to its neutral value removes the stored key again
        response = self._post_json({"base_revision": revision, "mutation": {
            "type": "section.update_settings", "section_id": section.pk, "patch": {"show_scrollbar": True}}})
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertNotIn("show_scrollbar", section.settings)


# ---------------------------------------------------------------------------------- design block (round trips)
class DesignBlockRoundTripTests(R4MutationApiTestCase):
    def _patch(self, section, patch_value, revision=None):
        return self._post_json({"base_revision": revision if revision is not None else self._refresh_revision(),
                                "mutation": {"type": "section.update_settings", "section_id": section.pk,
                                             "patch": patch_value}})

    def test_surface_panel_inspector_round_trip_with_semantic_colours(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="surface_panel", order=0)
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        self.assertContains(inspector, 'data-r4-field-key="min_height"')
        self.assertContains(inspector, 'data-r4-field-type="design"')
        for prop in ("surface_color", "border_color", "border_width", "radius", "shadow", "shadow_color",
                     "shadow_blur", "padding_top", "margin_top"):
            self.assertContains(inspector, f'data-r4-design-prop="{prop}"')
        self.assertNotContains(inspector, 'data-r4-design-prop="gap"')  # not applicable to a surface panel
        self.assertContains(inspector, "data-r4-color-token")
        self.assertContains(inspector, 'value="token:accent"')
        response = self._patch(section, {"design": {
            "surface_color": "token:tone-2", "radius": 20, "border_width": 2, "border_color": "#445566",
            "shadow": "on", "shadow_color": "token:text", "shadow_blur": 24,
        }, "min_height": 150})
        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        design = section.settings["design"]
        self.assertEqual(design["surface_color"], "token:tone-2")
        self.assertEqual(design["border_color"], "#445566")
        self.assertEqual(section.settings["min_height"], 150)
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("--d-surface:var(--brand-tone-2)", html)
        self.assertIn("--d-border-c:#445566", html)
        self.assertIn("--d-radius:20px", html)
        self.assertRegex(html, r'data-d="[^"]*surface[^"]*"')

    def test_inapplicable_design_property_is_rejected_with_nothing_stored(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="surface_panel", order=0)
        response = self._patch(section, {"design": {"gap": 10}})
        self.assertEqual(response.status_code, 400)
        section.refresh_from_db()
        self.assertNotIn("design", section.settings)

    def test_invalid_colour_is_rejected_and_neutral_values_reset_the_block(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0,
                                                   settings={"data_source": "newest", "item_limit": 8})
        self.assertEqual(self._patch(section, {"design": {"heading_color": "javascript:1"}}).status_code, 400)
        self.assertEqual(self._patch(section, {"design": {"heading_color": "token:accent", "radius": 6}}).status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.settings["design"], {"heading_color": "token:accent", "radius": 6})
        self.assertEqual(self._patch(section, {"design": {}}).status_code, 200)
        section.refresh_from_db()
        self.assertNotIn("design", section.settings)

    def test_responsive_visibility_is_a_design_property_that_reaches_the_wrapper(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="surface_panel", order=0)
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        for prop in ("hide_desktop", "hide_tablet", "hide_mobile"):
            self.assertContains(inspector, f'data-r4-design-prop="{prop}"')
        self.assertEqual(self._patch(section, {"design": {"hide_mobile": "hidden", "hide_tablet": "maybe"}}).status_code, 400)
        self.assertEqual(self._patch(section, {"design": {"hide_mobile": "hidden"}}).status_code, 200)
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("data-hide-mobile", html)
        self.assertNotIn("data-hide-desktop", html)
        attrs = design_block.render_attributes({"hide_desktop": "hidden"})
        self.assertTrue(attrs["hide_desktop"])
        self.assertFalse(attrs["hide_mobile"])

    def test_decorative_strip_page_rhythm_is_editable_through_the_design_block(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0)
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        for prop in ("margin_top", "margin_bottom", "padding_top", "padding_bottom"):
            self.assertContains(inspector, f'data-r4-design-prop="{prop}"')
        self.assertNotContains(inspector, 'data-r4-design-prop="radius"')  # the strip has its own radius field
        self.assertEqual(self._patch(section, {"design": {"margin_top": 28}}).status_code, 200)
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("margin-top:28px", html)

    def test_standalone_colour_field_round_trip_semantic_override(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0)
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        self.assertContains(inspector, 'data-r4-field-type="color"')
        self.assertContains(inspector, 'data-r4-field-key="background_color"')
        self.assertContains(inspector, 'data-r4-field-key="foreground_color"')
        self.assertEqual(self._patch(section, {"background_color": "token:tone-4"}).status_code, 200)
        self.assertEqual(self._patch(section, {"foreground_color": "#FFFFFF"}).status_code, 200)
        self.assertEqual(self._patch(section, {"overlay_color": "red"}).status_code, 400)
        section.refresh_from_db()
        self.assertEqual(section.settings["background_color"], "token:tone-4")
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("--ds-bg:var(--brand-tone-4)", html)
        self.assertIn("--ds-fg:#FFFFFF", html)


# ------------------------------------------------------------------------------------- decorative strip
class DecorativeStripTests(R4MutationApiTestCase):
    def test_schema_covers_the_full_primitive(self):
        keys = {f.key for f in section_registry.get_definition("decorative_strip").settings_schema.fields}
        required = {
            "enabled", "desktop_height", "tablet_height", "mobile_height", "background_mode", "background_color",
            "foreground_color", "image_media_asset_id", "image_fit", "image_position_x", "image_position_y",
            "image_repeat", "pattern_slug", "overlay_color", "overlay_opacity", "radius", "border_width",
            "border_color", "shadow_enabled", "shadow_color", "shadow_blur", "bleed", "alignment", "optional_text",
            "visible_desktop", "visible_tablet", "visible_mobile",
        }
        self.assertTrue(required <= keys, required - keys)

    def test_settings_are_sparse_and_validated(self):
        definition = section_registry.get_definition("decorative_strip")
        self.assertEqual(definition.validate_settings({}).get("desktop_height"), None)
        cleaned = definition.validate_settings({
            "desktop_height": "٦٠", "background_mode": "image", "image_media_asset_id": "7", "image_fit": "contain",
            "image_position_x": 120, "overlay_color": "token:text", "overlay_opacity": 40, "radius": 0,
            "optional_text": "x" * 500, "bleed": "true", "visible_mobile": False, "pattern_slug": "unknown",
        })
        self.assertEqual(cleaned["desktop_height"], 60)
        self.assertEqual(cleaned["image_media_asset_id"], 7)
        self.assertEqual(cleaned["image_position_x"], 100)
        self.assertEqual(len(cleaned["optional_text"]), 120)
        self.assertIs(cleaned["bleed"], True)
        self.assertIs(cleaned["visible_mobile"], False)
        self.assertNotIn("pattern_slug", cleaned)
        for bad in ({"background_color": "blue"}, {"image_media_asset_id": "x"}, {"image_media_asset_id": 0}):
            with self.assertRaises(ValueError, msg=bad):
                definition.validate_settings(bad)

    def test_view_model_resolves_tokens_image_overlay_and_visibility(self):
        view = build_view({
            "background_mode": "image", "background_color": "token:primary", "image_fit": "stretch",
            "image_position_x": 10, "image_position_y": 90, "image_repeat": "repeat-x", "overlay_opacity": 30,
            "overlay_color": "#000000", "radius": 12, "border_width": 2, "border_color": "token:accent",
            "shadow_enabled": True, "shadow_blur": 20, "alignment": "end", "visible_tablet": False,
            "optional_text": "متن",
        }, "/media/s.jpg")
        style = view["style"]
        self.assertIn("--ds-img:url('/media/s.jpg')", style)
        self.assertIn("--ds-fit:100% 100%", style)
        self.assertIn("--ds-pos:10% 90%", style)
        self.assertIn("--ds-repeat:repeat-x", style)
        self.assertIn("--ds-ov:color-mix(in srgb, #000000 30%, transparent)", style)
        self.assertIn("--ds-bc:var(--brand-accent)", style)
        self.assertIn("--ds-ja:flex-end", style)
        self.assertEqual(view["hide"], "tablet")
        self.assertEqual(view["text"], "متن")
        self.assertIn("--ds-fg:var(--brand-primary-fg)", style)

    def test_image_without_a_resolved_url_falls_back_to_the_colour_fill(self):
        view = build_view({"background_mode": "image", "image_media_asset_id": 99}, None)
        self.assertNotIn("--ds-img", view["style"])
        self.assertIn("--ds-bg:", view["style"])

    def test_bleed_and_pattern_flags(self):
        view = build_view({"background_mode": "pattern", "pattern_slug": "commerce-doodle", "bleed": True,
                           "radius": 14, "border_width": 3, "shadow_enabled": True})
        self.assertEqual(view["pattern"], "commerce-doodle")
        self.assertTrue(view["bleed"])
        self.assertIn("--ds-r:0px", view["style"])  # a full-bleed strip is square and borderless
        self.assertNotIn("--ds-bw", view["style"])
        self.assertNotIn("--ds-sh", view["style"])

    def test_renders_in_preview_and_public_with_the_same_markup_and_hides_when_disabled(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0, settings={
            "desktop_height": 52, "background_color": "token:surface", "optional_text": "نوار", "visible_mobile": False})
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn('class="section decor-strip"', html)
        self.assertIn("--ds-h-d:52px", html)
        self.assertIn('data-hide="mobile"', html)
        self.assertIn("decor-strip-text", html)
        self.assertNotIn("strip-art", html)
        self.assertNotIn("strip-art", section_registry.MULTI_BANNER_KNOWN_LAYOUT_VARIANTS)
        section.settings = {**section.settings, "enabled": False}
        section.save(update_fields=["settings"])
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertNotIn('class="section decor-strip"', html)

    def test_image_resolution_is_store_scoped_and_fail_closed(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0, settings={
            "background_mode": "image", "image_media_asset_id": 987654})
        items = build_render_items(self.draft, self.store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertNotIn("--ds-img", item["context"]["strip"]["style"])  # unknown / foreign asset -> no image
        with patch("apps.content.services.resolve_background_media_url", return_value="/media/ok.jpg") as resolver:
            items = build_render_items(self.draft, self.store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertIn("--ds-img:url('/media/ok.jpg')", item["context"]["strip"]["style"])
        self.assertIn("image", [(call.args[1] or {}).get("mode") for call in resolver.call_args_list])

    def test_inspector_exposes_every_applicable_control_and_the_media_picker(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0)
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
        self.assertEqual(response.status_code, 200)
        for key in ("desktop_height", "tablet_height", "mobile_height", "background_mode", "image_media_asset_id",
                    "image_fit", "image_position_x", "image_position_y", "image_repeat", "overlay_opacity", "radius",
                    "border_width", "shadow_enabled", "shadow_blur", "bleed", "alignment", "optional_text",
                    "visible_desktop", "visible_tablet", "visible_mobile"):
            self.assertContains(response, f'data-r4-field-key="{key}"', msg_prefix=key)
        self.assertContains(response, 'data-r4-field-type="media"')
        for key in ("background_color", "foreground_color", "overlay_color", "border_color", "shadow_color"):
            self.assertContains(response, f'data-r4-field-key="{key}"')

    def test_inspector_mutation_round_trip(self):
        self.section.delete()
        section = StorefrontSection.objects.create(version=self.draft, section_key="decorative_strip", order=0)
        revision = self.draft.edit_revision
        for patch_value in ({"desktop_height": 70}, {"background_mode": "solid"}, {"radius": 0}, {"bleed": True},
                            {"alignment": "start"}, {"optional_text": "سلام"}, {"visible_tablet": False}):
            response = self._post_json({"base_revision": revision, "mutation": {
                "type": "section.update_settings", "section_id": section.pk, "patch": patch_value}})
            self.assertEqual(response.status_code, 200, patch_value)
            revision = response.json()["new_revision"]
        section.refresh_from_db()
        self.assertEqual(section.settings["desktop_height"], 70)
        self.assertEqual(section.settings["background_mode"], "solid")
        self.assertEqual(section.settings["radius"], 0)
        self.assertIs(section.settings["bleed"], True)
        self.assertEqual(section.settings["optional_text"], "سلام")
        self.assertIs(section.settings["visible_tablet"], False)

    def test_bleed_strip_draws_its_own_canvas_wide_layer_inside_the_canvas_clip(self):
        rules = dict(_css_rules(BUILDER_CSS, ".decor-strip[data-bleed] .decor-strip-bg"))
        body = next(iter(rules.values()))
        self.assertIn("var(--sfb-canvas-width,100vw)", body)


# ------------------------------------------------------------------------------------------- categories
class CategorySourceTests(TestCase):
    def setUp(self):
        from apps.stores.models import Store

        self.store = Store.objects.create(name="دسته‌ها", slug="cat-source-store", admin_subdomain="cat-source-store")
        self.roots = [Category.objects.create(store=self.store, name=f"ریشه {i}", slug=f"r{i}", order=i, is_active=True)
                      for i in range(3)]
        self.kids = {}
        for index, root in enumerate(self.roots):
            self.kids[root.pk] = [Category.objects.create(store=self.store, name=f"زیر {index}-{j}", slug=f"k{index}{j}",
                                                          parent=root, order=j, is_active=True) for j in range(2)]
        self.grandchild = Category.objects.create(store=self.store, name="نوه", slug="g0", parent=self.kids[self.roots[0].pk][0],
                                                  order=0, is_active=True)

    def _names(self, mode):
        return [c.slug for c in category_selection.select_categories(self.store, mode)]

    def test_top_level_is_the_default_and_unchanged(self):
        self.assertEqual(self._names("top_level"), ["r0", "r1", "r2"])
        self.assertEqual(self._names("does-not-exist"), ["r0", "r1", "r2"])

    def test_top_then_descendants_is_roots_first_then_breadth_first(self):
        self.assertEqual(self._names("top_then_descendants"),
                         ["r0", "r1", "r2", "k00", "k01", "k10", "k11", "k20", "k21", "g0"])

    def test_all_is_depth_first_and_leaf_has_no_children(self):
        self.assertEqual(self._names("all"), ["r0", "k00", "g0", "k01", "r1", "k10", "k11", "r2", "k20", "k21"])
        self.assertEqual(self._names("leaf"), ["g0", "k01", "k10", "k11", "k20", "k21"])

    def test_inactive_parent_hides_its_whole_subtree_and_selection_is_store_scoped(self):
        self.roots[1].is_active = False
        self.roots[1].save()
        self.assertNotIn("k10", self._names("top_then_descendants"))
        from apps.stores.models import Store

        other = Store.objects.create(name="دیگر", slug="cat-source-other", admin_subdomain="cat-source-other")
        Category.objects.create(store=other, name="بیگانه", slug="foreign", is_active=True)
        self.assertNotIn("foreign", self._names("all"))

    def test_selection_is_deterministic(self):
        self.assertEqual(self._names("all"), self._names("all"))

    def test_six_real_categories_fill_the_six_positions_before_any_empty_slot(self):
        section = StorefrontSection.__new__(StorefrontSection)
        from apps.storefront_builder.services.render_service import _category_grid_context

        section.settings = {"display_mode": "grey_circles", "item_limit": 6, "min_slots": 6,
                            "category_source": "top_then_descendants"}
        context = _category_grid_context(self.store, section)
        self.assertEqual(len(context["top_categories"]), 6)
        self.assertEqual(list(context["category_empty_slots"]), [])
        # only the top level (historical default): three real + three reserved, nothing invented
        section.settings = {"display_mode": "grey_circles", "item_limit": 6, "min_slots": 6}
        context = _category_grid_context(self.store, section)
        self.assertEqual([c.slug for c in context["top_categories"]], ["r0", "r1", "r2"])
        self.assertEqual(len(list(context["category_empty_slots"])), 3)

    def test_validator_stores_the_mode_only_when_it_is_not_the_default(self):
        definition = section_registry.get_definition("category_grid")
        self.assertNotIn("category_source", definition.validate_settings({"category_source": "top_level"}))
        self.assertEqual(definition.validate_settings({"category_source": "leaf"})["category_source"], "leaf")
        self.assertNotIn("category_source", definition.validate_settings({"category_source": "bogus"}))
        self.assertIn("category_source", {f.key for f in definition.settings_schema.fields})


# --------------------------------------------------------------------------------------- shell geometry
class ShellGeometryTests(R4MutationApiTestCase):
    def test_validator_clamps_rejects_unknown_and_stays_sparse(self):
        cleaned = shell_geometry.validate_geometry(
            {"search_max_width": "5000", "nav_item_limit": "۴", "chip_fill": "token:primary", "util_height": ""}, "header")
        self.assertEqual(cleaned, {"search_max_width": 900, "nav_item_limit": 4, "chip_fill": "token:primary"})
        with self.assertRaises(shell_geometry.ShellGeometryError):
            shell_geometry.validate_geometry({"bar_height": 1}, "header")  # a footer property
        with self.assertRaises(shell_geometry.ShellGeometryError):
            shell_geometry.validate_geometry({"chip_fill": "red"}, "header")

    def test_merge_patch_resets_a_single_key(self):
        self.assertEqual(shell_geometry.merge_patch({"a": 1, "b": 2}, {"a": "", "c": 3}), {"b": 2, "c": 3})

    def test_style_fragment_uses_tokens_and_derives_the_chip_text(self):
        style = shell_geometry.geometry_style({"search_max_width": 600, "chip_fill": "token:accent"}, "header")
        self.assertIn("--gh-search-max:600px", style)
        self.assertIn("--gh-chip-fill:var(--brand-accent)", style)
        self.assertIn("--gh-chip-text:var(--brand-accent-fg)", style)
        self.assertEqual(shell_geometry.geometry_style({}, "footer"), "")

    def test_controls_are_offered_only_for_variants_that_draw_them(self):
        header_keys = {p.key for p in shell_geometry.properties_for("header", "stationery_search")}
        self.assertIn("search_max_width", header_keys)
        self.assertEqual(shell_geometry.properties_for("header", "legacy_default"), [])
        self.assertEqual(shell_geometry.properties_for("footer", "legacy_default"), [])
        self.assertIn("badge_size", {p.key for p in shell_geometry.properties_for("footer", "stationery_dark")})

    def test_header_and_footer_geometry_round_trip_through_the_mutation_api(self):
        revision = self.draft.edit_revision
        response = self._post_json({"base_revision": revision, "mutation": {
            "type": "header.update", "patch": {"header_variant": "stationery_search",
                                               "geometry": {"search_max_width": 600, "chip_fill": "token:accent"}}}})
        self.assertEqual(response.status_code, 200, response.content)
        revision = response.json()["new_revision"]
        response = self._post_json({"base_revision": revision, "mutation": {
            "type": "footer.update", "patch": {"footer_variant": "stationery_dark",
                                               "geometry": {"badge_size": 80, "badge_fill": "#FFFFFF"}}}})
        self.assertEqual(response.status_code, 200, response.content)
        revision = response.json()["new_revision"]
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["geometry"], {"search_max_width": 600, "chip_fill": "token:accent"})
        self.assertEqual(self.draft.footer_config["geometry"], {"badge_size": 80, "badge_fill": "#FFFFFF"})
        # a partial patch merges; an empty value resets just that key
        response = self._post_json({"base_revision": revision, "mutation": {
            "type": "header.update", "patch": {"geometry": {"search_max_width": ""}}}})
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["geometry"], {"chip_fill": "token:accent"})
        bad = self._post_json({"base_revision": response.json()["new_revision"], "mutation": {
            "type": "header.update", "patch": {"geometry": {"nonsense": 5}}}})
        self.assertEqual(bad.status_code, 400)

    def test_geometry_reaches_the_rendered_header_and_footer(self):
        self.draft.header_config = {"header_variant": "stationery_search", "geometry": {"search_max_width": 600, "chip_count": 1}}
        self.draft.footer_config = {"footer_variant": "stationery_dark", "geometry": {"badge_size": 80, "column_count": 3}}
        self.draft.save(update_fields=["header_config", "footer_config"])
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("--gh-search-max:600px", html)
        self.assertIn("--gf-badge-size:80px", html)
        self.assertIn("--gf-cols:3", html)

    def test_stored_geometry_survives_the_global_design_panel_context_and_controls_render(self):
        self.draft.header_config = {"header_variant": "stationery_search", "geometry": {"nav_item_limit": 4}}
        self.draft.save(update_fields=["header_config"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-r4-global-geometry-key="search_max_width"')
        self.assertContains(response, 'data-r4-geometry-prop="chip_fill"')
        self.assertContains(response, 'value="4"')

    def test_nav_limit_and_chip_count_are_applied_by_the_shared_nav_partial(self):
        items = [{"title": f"لینک {i}", "url": f"/l{i}/", "children": [], "open_in_new_tab": False} for i in range(1, 9)]
        context = {"NAV_HEADER": {"items": items}}
        html = render_to_string("storefront_builder/partials/global_header/_shared/nav_header_items.html",
                                context | {"nav_limit": 3, "nav_chip_count": 2})
        self.assertEqual(html.count('class="gh-nl'), 5)  # 3 plain + 2 chips
        self.assertEqual(html.count("gh-nl--chip"), 3)  # chip + chip + (alt carries both classes)
        self.assertEqual(html.count("gh-nl--chip-alt"), 1)
        self.assertIn("لینک 8", html)  # chips are never dropped by the limit
        self.assertNotIn("لینک 4<", html)
        plain = render_to_string("storefront_builder/partials/global_header/_shared/nav_header_items.html", context)
        self.assertEqual(plain.count("gh-nl--chip"), 0)
        self.assertEqual(plain.count('class="gh-nl"'), 8)


# --------------------------------------------------------------- bleed / canvas / chrome neutrality
class CanvasBoundBleedTests(R4MutationApiTestCase):
    def test_bleed_is_a_real_layer_bounded_by_the_storefront_canvas(self):
        self.assertNotIn("body:has(.rsec[data-bg-bleed])", BUILDER_CSS)
        self.assertNotRegex(BUILDER_CSS, r"\[data-bg-bleed\]::before")
        rule = dict(_css_rules(BUILDER_CSS, ".rsec[data-bg-bleed]>.rsec-bleed"))
        self.assertTrue(rule)
        self.assertIn("var(--sfb-canvas-width,100vw)", next(iter(rule.values())))
        self.assertRegex(LAYOUT_CSS, r"main\.sfb-storefront-canvas\{overflow-x:clip\}")
        base = (APP.parents[1] / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn('<main class="sfb-storefront-canvas">', base)

    def test_wrapper_emits_the_layer_only_for_full_width_cells(self):
        self.section.delete()
        StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0, settings={
            "data_source": "newest", "item_limit": 6,
            "background": {"mode": "palette", "palette_role": "tone-1", "bleed": True}})
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn('data-bg-bleed="1"', html)
        self.assertIn('class="rsec-bleed"', html)

    def test_bleed_still_requires_a_bleedable_mode(self):
        cleaned = section_registry.get_definition("product_section").validate_settings({
            "data_source": "newest", "background": {"mode": "surface", "bleed": True}})
        self.assertNotIn("bleed", cleaned["background"])


class BuilderChromeIsLayoutNeutralTests(SimpleTestCase):
    FORBIDDEN = re.compile(r"(^|;)\s*(margin[a-z-]*|padding[a-z-]*|border(?!-radius)[a-z-]*|min-height|height|width|display)\s*:", re.I)

    def test_builder_container_and_cell_chrome_never_adds_box_geometry(self):
        for selector, body in _css_rules(BUILDER_CSS, ".sfb-builder-container"):
            if "toolbar" in selector or "select" in selector:
                continue
            self.assertIsNone(self.FORBIDDEN.search(body), f"{selector} {{{body.strip()[:120]}}}")

    def test_no_preview_only_row_geometry_override_exists(self):
        self.assertNotIn('.sfb-builder-container[data-height-mode="equal"]', BUILDER_CSS)
        for selector, body in _css_rules(BUILDER_CSS, ".sfb-builder-container > .rcontainer-cell"):
            self.assertNotIn("!important", body.replace("outline", ""), selector)
            self.assertNotRegex(body, r"display\s*:", selector)

    def test_add_controls_and_hidden_cell_notices_are_absolute_overlays(self):
        for needle in (".sfb-cell-add-more", ".sfb-empty-cell-add", ".sfb-hidden-cell-content"):
            bodies = " ".join(body for selector, body in _css_rules(BUILDER_CSS, needle) if selector.strip() == needle)
            self.assertIn("position:absolute", bodies.replace(" ", ""), needle)
        self.assertNotRegex(BUILDER_CSS, r"\.sfb-empty-cell\s*\{[^}]*min-height")

    def test_edit_mode_does_not_reposition_storefront_elements(self):
        css = (APP / "static" / "css" / "storefront_builder_preview_v22.css").read_text(encoding="utf-8")
        self.assertNotRegex(css, r"\[data-admin-edit-kind\]\{[^}]*position:relative\s*!important")
        self.assertIn(":where(html[data-sfb-builder-mode=\"edit\"] [data-admin-edit-kind])", css)
        self.assertIn(':where(html[data-sfb-builder-mode="edit"] header', css)

    def test_preview_and_published_load_one_stylesheet_url(self):
        from apps.storefront_builder.templatetags.storefront_builder_extras import sfb_static

        self.assertRegex(sfb_static("css/storefront_builder.css"), r"\?v=\d+$")


# ------------------------------------------------------------------------------------ editor refresh
class AtomicPreviewRefreshContractTests(SimpleTestCase):
    def test_no_mutation_path_reloads_the_visible_preview_iframe(self):
        self.assertNotRegex(EDITOR_JS, r"previewFrame\.contentWindow\.location\.reload\(\)")
        self.assertIn("function runPreviewRefresh(nextSrc)", EDITOR_JS)
        self.assertGreaterEqual(EDITOR_JS.count("reloadPreviewFrame("), 7)

    def test_refresh_builds_a_hidden_twin_waits_for_readiness_and_restores_by_section_id(self):
        for needle in ("cloneNode(false)", "doc.fonts", "capturePreviewAnchor", "restorePreviewAnchor",
                       "data-section-id", "twin.style.opacity = '0'", "R4.reloadPreview = reloadPreviewFrame",
                       "previewRefresh.again"):
            self.assertIn(needle, EDITOR_JS, needle)

    def test_editor_script_is_syntactically_valid(self):
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run([node, "--check", str(APP / "static" / "storefront_builder" / "r4_editor.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


# --------------------------------------------------------------------------------------- Template 51 recipe
class Template51UsesOnlyEngineContractsTests(SimpleTestCase):
    def _home(self):
        return lpr.get_layout_preset("stationery_spectrum").pages["home"]

    def test_decor_strip_is_the_generic_primitive_not_an_abused_banner(self):
        first = self._home()[0]
        self.assertEqual(first.section_key, "decorative_strip")
        self.assertEqual(first.settings["desktop_height"], 52)
        self.assertFalse([e for e in self._home() if e.settings.get("layout_variant") == "strip-art"])
        for definition_key in ("decorative_strip",):
            section_registry.get_definition(definition_key).validate_settings(first.settings)

    def test_pair_panels_use_the_non_scrolling_grid_contract(self):
        pair_panels = [e for e in self._home() if e.section_key == "product_section"
                       and e.settings.get("background", {}).get("mode") == "surface"]
        self.assertEqual(len(pair_panels), 4)
        for entry in pair_panels:
            self.assertEqual(entry.settings["desktop_layout"], "grid")
            self.assertEqual(entry.settings["overflow_mode"], "visible")
            self.assertIs(entry.settings["show_scrollbar"], False)
            self.assertEqual(entry.settings["item_limit"], 3)

    def test_category_circles_take_real_descendants_before_reserved_slots(self):
        grid = next(e for e in self._home() if e.section_key == "category_grid")
        self.assertEqual(grid.settings["category_source"], "top_then_descendants")
        self.assertEqual(grid.settings["min_slots"], 6)

    def test_header_and_footer_dimensions_are_recipe_data(self):
        preset = lpr.get_layout_preset("stationery_spectrum")
        self.assertEqual(preset.header["geometry"]["search_max_width"], 655)
        self.assertEqual(preset.header["geometry"]["nav_item_limit"], 4)
        self.assertEqual(preset.footer["geometry"]["badge_size"], 62)
        layout = svc  # noqa: F841 - the validators accept exactly the recipe's data
        svc.validate_header_config({**preset.header})
        svc.validate_footer_config({**preset.footer})

    def test_engine_modules_contain_no_template_identity(self):
        for name in ("design_block.py", "semantic_colors.py", "shell_geometry.py", "decorative_strip.py",
                     "services/category_selection.py"):
            source = (APP / name).read_text(encoding="utf-8")
            for key in ("stationery_spectrum", "magenta_beauty_retail", "pastel_kawaii_stationery", "template_key"):
                self.assertNotIn(key, source, f"{name} mentions {key}")

    def test_template_51_css_has_no_template_key_selector_and_literal_fills_are_tokenised(self):
        for key in ("stationery_spectrum", ".template-51", "data-template"):
            self.assertNotIn(key, BUILDER_CSS.split("REF-TEMPLATES-51-53 BEGIN")[1])
        tokenised = {
            ".category-grey-media{": "var(--d-item",
            ".gf--stationery{": "var(--theme-footer-text",
        }
        for needle, token in tokenised.items():
            line = next(l for l in BUILDER_CSS.splitlines() if l.startswith(needle))
            self.assertIn(token, line)
            self.assertNotRegex(line, r"background:#[0-9a-fA-F]{3,6}[;}]")
        self.assertNotIn("#e6e7eb", BUILDER_CSS)
        self.assertNotIn("#e9eaee", BUILDER_CSS)
        self.assertNotIn("background:var(--green);color:#fff", BUILDER_CSS)


class LegacyShellFormsPreserveGeometryTests(StorefrontBuilderViewsTestCase):
    """The legacy full-page header/footer forms have no geometry controls; saving them must not erase the block
    a merchant (or a Ready Template) set through Design Studio."""

    def test_header_form_keeps_stored_geometry(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {"header_variant": "stationery_search", "geometry": {"search_max_width": 600}}
        draft.save(update_fields=["header_config"])
        response = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_search": "on", "show_cart": "on", "header_variant": "stationery_search"})
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.header_config["geometry"], {"search_max_width": 600})

    def test_footer_form_keeps_stored_geometry(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = {"footer_variant": "stationery_dark", "geometry": {"badge_size": 80}}
        draft.save(update_fields=["footer_config"])
        response = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_about": "on", "footer_variant": "stationery_dark"})
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config["geometry"], {"badge_size": 80})
