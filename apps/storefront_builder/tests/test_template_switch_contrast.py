"""Live Template switching in Design Studio is its own contrast contract.

``switch_ready_template_preserving`` replaces the Draft's appearance (palette, overrides, role overrides) with the target
Ready Template's, but keeps merchant-modified sections together with their presentation. So a page can end up with an OLD
presentation (e.g. the ``image_strip`` category rail) on a NEW palette (e.g. a black page). These tests drive the real
switch path (``r4_mutation_service.switch_template``) on one Draft and check, after every transition, that

* the palette/overrides follow the documented switch contract (target palette applied, old overrides dropped);
* every derived accessible usage token the preview emits equals what the server derives from the CURRENT appearance —
  nothing is carried over from the previous template;
* the text colour of the preserved category presentations still reads on the new page.

The browser-level counterpart is ``tools/contrast_audit/run_audit.py --suite template-switch``.
"""

import re

from django.urls import reverse

from apps.core.tests.css_tokens import read_css, ratio
from apps.core.tests.test_css_token_contrast import CategoryComponentSurfaceOwnershipTests as _Css
from apps.storefront_builder import appearance_registry as ar
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.accessible_colors import build_accessible_theme, failing_pairs
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service, preset_service, r4_mutation_service

from .test_views import StorefrontBuilderViewsTestCase

LIGHT, DARK, WARM, SATURATED = "editorial_jewelry", "night_catalog", "warm_boutique", "kite_playful"
#: the usage tokens the storefront shell emits on <html>; each must equal the server derivation for the current appearance
TOKENS = ("--brand-background", "--brand-surface", "--brand-primary", "--brand-text", "--brand-muted", "--brand-primary-text",
          "--brand-accent-text", "--brand-secondary-text", "--brand-primary-fg", "--brand-primary-hover",
          "--brand-primary-hover-fg", "--theme-header-text", "--theme-nav-text", "--theme-footer-text", "--theme-price-text")
CATEGORY_RULES = (".category-image-tile", ".category-beauty-tile", ".category-chocolate-story-item", ".tile-circle-label",
                  ".category-fashion-tile")


class TemplateSwitchTestCase(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        layout = layout_service.get_or_create_layout(self.store)
        layout.r4_editor_enabled = True
        layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, lpr.get_layout_preset(LIGHT))

    # -- helpers ---------------------------------------------------------------------------------------------------
    def switch(self, key):
        self.draft.refresh_from_db()
        preset = lpr.get_layout_preset(key)
        r4_mutation_service.switch_template(
            store=self.store, actor=self.staff, base_revision=self.draft.edit_revision,
            template_key=key, template_version=preset.version,
        )
        self.draft.refresh_from_db()
        return preset

    def preview_vars(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        self.assertEqual(response.status_code, 200)
        style = re.search(r'<html[^>]*style="([^"]*)"', response.content.decode()).group(1)
        return dict(item.split(":", 1) for item in style.split(";") if item.startswith("--"))

    def expected(self):
        """What the server derives from the Draft's CURRENT effective appearance (the contract the preview must match)."""
        config = self.draft.effective_appearance_config()
        colors, roles, tones = ar.resolve_colors(config), ar.resolve_theme_roles(config), ar.resolve_section_tones(config)
        theme = build_accessible_theme(dict(colors), roles, tones=tones)
        return colors, roles, tones, theme, {
            "--brand-background": colors["background"], "--brand-surface": colors["surface"], "--brand-primary": colors["primary"],
            "--brand-text": theme["text"], "--brand-muted": theme["muted_text"], "--brand-primary-text": theme["primary_text"],
            "--brand-accent-text": theme["accent_text"], "--brand-secondary-text": theme["secondary_text"],
            "--brand-primary-fg": theme["primary_fg"], "--brand-primary-hover": theme["primary_hover"],
            "--brand-primary-hover-fg": theme["primary_hover_fg"], "--theme-header-text": theme["header_text"],
            "--theme-nav-text": theme["nav_text"], "--theme-footer-text": theme["footer_text"],
            "--theme-price-text": theme["price_text"],
        }

    def assertTokensFollowCurrentAppearance(self, label=""):
        colors, roles, tones, theme, expected = self.expected()
        actual = self.preview_vars()
        for name in TOKENS:
            self.assertEqual(actual[name].upper(), expected[name].upper(), f"{label}: stale/incorrect {name}")
        self.assertEqual(failing_pairs(colors, roles, theme, tones), [], label)
        for name in ("--brand-text", "--brand-muted", "--brand-primary-text", "--brand-accent-text", "--brand-secondary-text",
                     "--theme-price-text"):
            for surface in ("--brand-background", "--brand-surface"):
                self.assertGreaterEqual(ratio(actual[name], actual[surface], {}), 4.5, f"{label}: {name} on {surface}")
        return actual

    def assertSwitchContract(self, preset):
        """Documented contract: the target template's palette is APPLIED and the previous palette's overrides are dropped."""
        provenance = self.draft.template_provenance["template"]
        self.assertEqual((provenance["key"], provenance["version"]), (preset.key, preset.version))
        config = self.draft.appearance_config
        self.assertEqual(config["palette_slug"], preset.default_palette_slug)
        self.assertFalse(config.get("color_overrides"))
        self.assertFalse(config.get("theme_overrides"))

    def set_category_mode(self, mode):
        for section in StorefrontSection.objects.filter(page__version=self.draft, page__page_type="home", section_key="category_grid"):
            settings = dict(section.settings or {})
            settings.update({"display_mode": mode, "category_ids": []})
            section.settings = settings
            section.save(update_fields=["settings"])

    def category_modes(self):
        return [(s.settings or {}).get("display_mode") for s in StorefrontSection.objects.filter(
            page__version=self.draft, page__page_type="home", section_key="category_grid")]


class LiveTemplateSwitchTokenTests(TemplateSwitchTestCase):
    def test_light_to_dark_replaces_palette_and_refreshes_every_usage_token(self):
        light = self.assertTokensFollowCurrentAppearance("light (start)")
        preset = self.switch(DARK)
        self.assertSwitchContract(preset)
        dark = self.assertTokensFollowCurrentAppearance("light -> dark")
        self.assertNotEqual(light["--brand-background"], dark["--brand-background"])
        self.assertLess(ratio(dark["--brand-background"], "#000000", {}), 2.0, "the target page really is dark")
        for name in ("--brand-text", "--brand-muted", "--brand-primary-text"):
            self.assertNotEqual(light[name].upper(), dark[name].upper(), f"{name} was copied from the previous template")

    def test_dark_to_light(self):
        self.switch(DARK)
        self.assertTokensFollowCurrentAppearance("dark")
        preset = self.switch(LIGHT)
        self.assertSwitchContract(preset)
        light = self.assertTokensFollowCurrentAppearance("dark -> light")
        self.assertGreater(ratio(light["--brand-background"], "#000000", {}), 15.0)
        self.assertLess(ratio(light["--brand-text"], "#000000", {}), 3.0, "text is dark again on the light page")

    def test_custom_merchant_palette_is_replaced_by_the_target_template_and_tokens_follow(self):
        # A merchant palette with MIXED surfaces (black page, white card): the case ensure_contrast's multi-backdrop search fixed.
        config = dict(self.draft.appearance_config)
        config["color_overrides"] = {"primary": "#FF0000", "background": "#000000", "surface": "#FFFFFF", "text": "#767676"}
        self.draft.appearance_config = config
        self.draft.save(update_fields=["appearance_config"])
        custom = self.assertTokensFollowCurrentAppearance("custom mixed-surface palette")
        self.assertEqual(custom["--brand-background"].upper(), "#000000")
        preset = self.switch(WARM)
        self.assertSwitchContract(preset)  # overrides are not carried over a Ready Template switch
        warm = self.assertTokensFollowCurrentAppearance("custom -> warm")
        self.assertNotEqual(warm["--brand-background"].upper(), "#000000")
        self.assertNotEqual(warm["--brand-primary"].upper(), "#FF0000")

    def test_round_trip_a_b_a_has_no_leftovers(self):
        first = self.assertTokensFollowCurrentAppearance("A")
        self.switch(DARK)
        middle = self.assertTokensFollowCurrentAppearance("B")
        self.switch(LIGHT)
        again = self.assertTokensFollowCurrentAppearance("A again")
        self.assertEqual({k: first[k].upper() for k in TOKENS}, {k: again[k].upper() for k in TOKENS})
        self.assertNotEqual(first["--brand-text"].upper(), middle["--brand-text"].upper())

    def test_every_pair_of_the_four_template_classes_keeps_tokens_current(self):
        sequence = (DARK, WARM, SATURATED, LIGHT, DARK, LIGHT, SATURATED, DARK)
        for key in sequence:
            preset = self.switch(key)
            self.assertSwitchContract(preset)
            self.assertTokensFollowCurrentAppearance(f"-> {key}")


class PreservedCategoryPresentationTests(TemplateSwitchTestCase):
    """The reported defect: a preserved ``image_strip`` category rail kept dark label text on the new black page."""

    MODES = ("image_strip", "chocolate_story", "circular", "beauty_icons", "fashion_flat")

    def test_switch_keeps_the_merchant_presentation_and_its_label_colour_still_reads_on_the_new_page(self):
        css_files = [read_css(path) for path in _Css.FILES]
        for mode in self.MODES:
            self.switch(LIGHT)
            self.set_category_mode(mode)
            self.switch(DARK)
            self.assertEqual(self.category_modes(), [mode], "the merchant's presentation is preserved across the switch")
            actual = self.assertTokensFollowCurrentAppearance(f"{mode} on dark")
            props = {"--brand-text": actual["--brand-text"], "--ink": actual["--brand-text"]}
            for css in css_files:
                for selector in CATEGORY_RULES:
                    value = _Css.final_colour(css, selector)
                    if value is not None:
                        got = ratio(value, actual["--brand-background"], props)
                        self.assertGreaterEqual(got, 4.5, f"{mode}: {selector} {{color:{value}}} on the switched page = {got:.2f}")

    def test_preserved_presentation_also_reads_when_switching_back_to_light(self):
        css = read_css(_Css.FILES[0])
        self.switch(DARK)
        self.set_category_mode("image_strip")
        self.switch(LIGHT)
        actual = self.assertTokensFollowCurrentAppearance("image_strip on light")
        value = _Css.final_colour(css, ".category-image-tile")
        self.assertGreaterEqual(ratio(value, actual["--brand-background"], {"--brand-text": actual["--brand-text"]}), 4.5)
