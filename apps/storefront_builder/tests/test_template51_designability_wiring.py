"""Template 51 — designability + display-mode wiring.

The owner's manual QA found that choosing a different "نوع نمایش" in the Inspector left the Preview unchanged and that a
product band's colour could not be redesigned. The root cause of the display-type "no-op" was in the editor shell: an
accepted ``section.update_settings`` mutation never refreshed the Preview iframe (only structural mutations did), so the
stored/effective value had changed while the visible frame still showed the old render. These tests pin the whole chain
(Inspector field -> mutation payload -> stored ``settings`` -> render service -> Preview == Published) for the generic
background system and the display type, with the Template 51 band as the real example. Nothing here is template-key
specific: the recipe is only DATA that the merchant's explicit choice must beat.

Real-browser checks (overflow with an image background, Preview == Published geometry) live in
``test_engine_parity_browser.py`` (opt-in, needs Chromium)."""

import re
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse
from PIL import Image

from apps.content.models import MediaAsset
from apps.core.color_utils import contrast_ratio
from apps.storefront_builder import layout_preset_registry as lpr, section_registry, settings_schema
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc, preset_service
from apps.storefront_builder.services.render_service import build_render_items
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase

APP = Path(__file__).resolve().parents[1]
EDITOR_JS = (APP / "static" / "storefront_builder" / "r4_editor.js").read_text(encoding="utf-8")
WRAPPER = "storefront_builder/partials/responsive_section_wrapper.html"


def _png(name="band.png", size=(400, 120)):
    buf = BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _wrapper_signature(html):
    """Everything about the section wrapper that carries the background: attributes + layer spans."""
    opening = re.search(r'<div class="rsec[^"]*"([^>]*)>', html, re.S).group(1)
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', opening))
    keep = {k: v for k, v in attrs.items() if k.startswith("data-bg") or k in ("data-palette-role", "data-pattern", "style")}
    layers = re.findall(r'<span class="rsec-(?:bleed|overlay)"[^>]*>', html)
    return keep, layers


class _BandBase(R4MutationApiTestCase):
    """A Draft holding Template 51's real red band (a palette_pattern + bleed product_section)."""

    def setUp(self):
        super().setUp()
        self.section.delete()
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("stationery_spectrum"))
        bands = StorefrontSection.objects.filter(page__version=self.draft, section_key="product_section").order_by("order")
        self.band = next(s for s in bands if (s.settings.get("background") or {}).get("mode") == "palette_pattern")

    def _patch(self, patch_value):
        self.draft.refresh_from_db()
        return self._post_json({"base_revision": self.draft.edit_revision, "mutation": {
            "type": "section.update_settings", "section_id": self.band.pk, "patch": patch_value}})

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()

    def _band_html(self, html=None):
        html = html or self._preview()
        start = html.index(f'data-section-id="{self.band.pk}"')
        start = html.rindex('<div class="rsec', 0, start)
        end = html.find('<div class="rsec', start + 10)
        return html[start:end if end != -1 else len(html)]

    def _items(self, version):
        return {i["section"].section_key + str(i["section"].pk): i for i in build_render_items(version, self.store)}

    def _inspector(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk]))

    def _publish_and_pair(self):
        """(preview wrapper html, published wrapper html) of the band, rendered by the ONE shared wrapper template."""
        layout = svc.get_or_create_layout(self.store)
        svc.publish(self.store)
        layout.refresh_from_db()
        published = layout.published_version
        draft_item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == self.band.pk)
        published_band = published.sections.get(section_key="product_section", order=self.band.order, page__page_type="home")
        published_item = next(i for i in build_render_items(published, self.store) if i["section"].pk == published_band.pk)
        return (
            render_to_string(WRAPPER, {"item": draft_item, "is_preview": True}),
            render_to_string(WRAPPER, {"item": published_item, "is_preview": False}),
        )


# ------------------------------------------------------------------------------------------ background field
class ProductBandBackgroundIsDesignableTests(_BandBase):
    def test_background_field_is_offered_in_the_basic_tab_not_buried_in_advanced(self):
        response = self._inspector()
        self.assertEqual(response.status_code, 200)
        basic = [f.key for f in response.context["basic_fields"]]
        advanced = [f.key for f in response.context["advanced_fields"]]
        self.assertIn("background", basic)
        self.assertNotIn("background", advanced)
        self.assertContains(response, "پس‌زمینه این بخش")
        self.assertContains(response, 'data-r4-field-type="background"')
        for hook in ("data-r4-background-mode", "data-r4-background-color", "data-r4-background-palette-role",
                     "data-r4-background-pattern", "data-r4-background-media", "data-r4-background-image-fit",
                     "data-r4-background-position-x", "data-r4-background-position-y",
                     "data-r4-background-overlay-color", "data-r4-background-overlay-opacity",
                     "data-r4-background-bleed"):
            self.assertContains(response, hook)
        # the Template 51 band itself shows its CURRENT palette/pattern choice
        self.assertContains(response, 'value="commerce-doodle" selected')

    def test_background_groups_follow_the_current_mode(self):
        html = self._inspector().content.decode()
        # palette_pattern band: palette role + pattern + bleed offered; custom colour and image controls are not
        self.assertTrue(re.search(r'data-r4-bg-modes="palette palette_pattern"\s*>', html))
        self.assertTrue(re.search(r'data-r4-bg-modes="pattern palette_pattern"\s*>', html))
        self.assertTrue(re.search(r'data-r4-bg-modes="color pattern"\s+hidden', html))
        self.assertTrue(re.search(r'data-r4-bg-modes="image"\s+hidden', html))

    def test_custom_colour_round_trip_red_to_blue(self):
        self.assertEqual(self._patch({"background": {"mode": "color", "color": "#d62828", "bleed": True}}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["background"]["color"], "#d62828")
        red = self._band_html()
        self.assertIn("--sfb-section-bg-color:#d62828", red)
        self.assertEqual(self._patch({"background": {"mode": "color", "color": "#2f6fed", "bleed": True}}).status_code, 200)
        blue = self._band_html()
        self.assertIn("--sfb-section-bg-color:#2f6fed", blue)
        self.assertNotIn("#d62828", blue)
        self.assertIn('data-bg-bleed="1"', blue)  # still an edge-to-edge band
        self.assertNotIn("data-pattern", blue)    # a custom colour is a plain fill

    def test_palette_role_round_trip_tone_1_to_tone_4(self):
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-1", "bleed": True}}).status_code, 200)
        self.assertIn('data-palette-role="tone-1"', self._band_html())
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-4", "bleed": True}}).status_code, 200)
        html = self._band_html()
        self.assertIn('data-palette-role="tone-4"', html)
        self.assertNotIn('data-palette-role="tone-1"', html)
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-99"}}).status_code, 200)  # invalid -> theme
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["background"]["mode"], "theme")

    def test_pattern_on_and_off(self):
        on = {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle", "bleed": True}
        self.assertEqual(self._patch({"background": on}).status_code, 200)
        self.assertIn('data-pattern="commerce-doodle"', self._band_html())
        self.assertEqual(self._patch({"background": {**on, "mode": "palette", "pattern_slug": ""}}).status_code, 200)
        self.assertNotIn("data-pattern", self._band_html())

    def test_band_layout_does_not_depend_on_which_background_fills_it(self):
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        # a custom colour / palette / picture band keeps the band geometry and the heading look of a patterned one,
        # and the white "paired panel" look belongs to the surface background only
        self.assertIn('.rsec:is([data-bg-mode="palette"],[data-bg-mode="color"],[data-bg-mode="image"]):has(>.section.product-section)', css)
        self.assertIn('.rsec:is([data-pattern],[data-bg-mode="palette"],[data-bg-mode="color"])>.section.product-section--hs-plain>.sec-head', css)
        self.assertNotIn(".rcontainer-cell>.rsec:not([data-pattern])>.product-section:has(.pcard.style-center_stepper)", css)
        self.assertIn('.rsec:is(:not([data-bg-mode]),[data-bg-mode="surface"])>.product-section:has(.pcard.style-center_stepper)', css)


# --------------------------------------------------------------------------------------- image background
class ImageBackgroundIsARealDesignControlTests(_BandBase):
    def setUp(self):
        super().setUp()
        self.asset = MediaAsset.objects.create(store=self.store, image=_png())

    def _image_bg(self, **extra):
        return {"mode": "image", "media_asset_id": self.asset.pk, **extra}

    def test_media_library_image_round_trip_with_every_presentation_control(self):
        response = self._patch({"background": self._image_bg(
            bleed=True, image_fit="contain", image_position_x="left", image_position_y="top",
            overlay_color="token:text", overlay_opacity=40)})
        self.assertEqual(response.status_code, 200, response.content)
        self.band.refresh_from_db()
        stored = self.band.settings["background"]
        self.assertEqual(stored["media_asset_id"], self.asset.pk)
        self.assertEqual((stored["image_fit"], stored["image_position_x"], stored["image_position_y"]), ("contain", "left", "top"))
        self.assertEqual((stored["overlay_color"], stored["overlay_opacity"], stored["bleed"]), ("token:text", 40, True))
        html = self._band_html()
        self.assertIn(f"url('{self.asset.image.url}')", html)
        self.assertIn("background-size:contain;background-position:0% 0%", html)
        self.assertIn('class="rsec-bleed"', html)
        self.assertIn('class="rsec-overlay"', html)
        self.assertIn("background-color:var(--brand-text);opacity:0.4", html)
        self.assertIn('data-bg-overlay="1"', html)
        # the Inspector shows the stored choices back
        inspector = self._inspector().content.decode()
        self.assertRegex(inspector, r'<option value="contain"\s+selected')
        self.assertRegex(inspector, r'<option value="left"\s+selected')
        self.assertRegex(inspector, r'data-r4-background-overlay-opacity value="40"')

    def test_defaults_are_not_stored_and_the_historical_output_is_unchanged(self):
        self.assertEqual(self._patch({"background": self._image_bg(image_fit="cover", image_position_x="center", overlay_opacity=0)}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(set(self.band.settings["background"]), {"mode", "color", "media_asset_id", "pattern_slug", "palette_role"})
        self.assertIn("background-size:cover;background-position:center", self._band_html())

    def test_image_only_controls_are_dropped_for_other_modes(self):
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-3", "image_fit": "contain",
                                                      "overlay_opacity": 50}}).status_code, 200)
        self.band.refresh_from_db()
        self.assertNotIn("image_fit", self.band.settings["background"])
        self.assertNotIn("overlay_opacity", self.band.settings["background"])
        self.assertNotIn("rsec-overlay", self._band_html())

    def test_no_raw_url_and_no_foreign_store_asset(self):
        self.assertContains(self._inspector(), "data-r4-background-media")
        self.assertNotContains(self._inspector(), 'name="background_image_url"')
        self.assertEqual(self._patch({"background": {"mode": "image", "image_url": "https://evil.example/x.png",
                                                      "media_asset_id": self.asset.pk}}).status_code, 200)
        self.band.refresh_from_db()
        self.assertNotIn("image_url", self.band.settings["background"])
        self.assertNotIn("evil.example", self._band_html())
        other = Store.objects.create(name="فروشگاه ب", slug="td-cross", admin_subdomain="td-cross")
        foreign = MediaAsset.objects.create(store=other, image=_png("foreign.png"))
        self.assertEqual(self._patch({"background": {"mode": "image", "media_asset_id": foreign.pk}}).status_code, 400)
        self.band.refresh_from_db()
        self.assertNotEqual(self.band.settings["background"].get("media_asset_id"), foreign.pk)
        self.assertNotIn(foreign.image.url, self._band_html())  # and the URL resolver enforces the scope again at render time

    def test_invalid_overlay_colour_is_rejected_and_nothing_is_stored(self):
        before = dict(self.band.settings["background"])
        self.assertEqual(self._patch({"background": self._image_bg(overlay_color="red", overlay_opacity=30)}).status_code, 400)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["background"], before)

    def test_image_with_no_asset_falls_back_to_the_theme_instead_of_storing_nothing_useful(self):
        self.assertEqual(self._patch({"background": {"mode": "image"}}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["background"]["mode"], "theme")
        self.assertIn("mode === 'image' && !background.media_asset_id", EDITOR_JS)  # the Inspector waits for the picture

    def test_overlay_and_image_layers_are_bounded_by_the_canvas(self):
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn(".rsec[data-bg-bleed]>.rsec-overlay{inset:0 auto 0 50%;width:var(--sfb-canvas-width,100vw);transform:translateX(-50%)", css)
        self.assertRegex(css, r"\.rsec>\.rsec-overlay\{position:absolute;inset:0;z-index:-1;pointer-events:none")
        self.assertNotRegex(css, r"rsec-overlay::")  # never a pseudo-element (builder chrome cannot collide with it)

    def test_preview_and_published_render_the_same_background(self):
        self.assertEqual(self._patch({"background": self._image_bg(
            bleed=True, image_fit="contain", image_position_x="right", overlay_color="#112233", overlay_opacity=25)}).status_code, 200)
        preview, published = self._publish_and_pair()
        self.assertEqual(_wrapper_signature(preview), _wrapper_signature(published))
        self.assertIn(f"url('{self.asset.image.url}')", published)


class BackgroundPreviewEqualsPublishedTests(_BandBase):
    def test_colour_and_palette_bands_match_between_preview_and_published(self):
        for background in (
            {"mode": "color", "color": "#2f6fed", "bleed": True},
            {"mode": "palette", "palette_role": "tone-4", "bleed": True},
            {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle", "bleed": True},
        ):
            with self.subTest(background=background):
                self.assertEqual(self._patch({"background": background}).status_code, 200)
                preview, published = self._publish_and_pair()
                self.assertEqual(_wrapper_signature(preview), _wrapper_signature(published))
                self.draft = svc.get_or_create_draft(self.store, user=self.staff)  # publishing consumed the draft
                self.band = self.draft.sections.get(section_key="product_section", order=self.band.order, page__page_type="home")

    def test_custom_colours_keep_an_accessible_foreground(self):
        for colour in ("#d62828", "#2f6fed", "#ffd60a", "#ffffff", "#000000", "#808080", "#767676", "#e0e0e0", "#1b4332"):
            with self.subTest(colour=colour):
                self.assertEqual(self._patch({"background": {"mode": "color", "color": colour, "bleed": True}}).status_code, 200)
                html = self._band_html()
                foreground = re.search(r"--sfb-section-bg-color:%s;--sfb-section-fg:(#[0-9A-Fa-f]{6})" % colour, html)
                self.assertIsNotNone(foreground, html[:400])
                self.assertGreaterEqual(contrast_ratio(colour, foreground.group(1)), 4.5)


# ------------------------------------------------------------------------------------------- display type
class DisplayTypeWiringTests(_BandBase):
    MODES = ("carousel", "grid", "campaign_band", "catalog_grid")

    def _markers(self, html):
        return {
            "pcarousel": 'class="pcarousel rsec-cols"' in html,
            "grid": bool(re.search(r'class="grid rsec-cols"', html)),
            "campaign": "product-campaign-band" in html,
            "catalog": "catalog-grid-products" in html,
            "catalog_bar": "catalog-grid-bar-row" in html,
        }

    def test_every_display_type_round_trips_and_changes_the_markup(self):
        seen = {}
        for mode in self.MODES:
            response = self._patch({"display_mode": mode})
            self.assertEqual(response.status_code, 200, (mode, response.content))
            # persisted StorefrontSection.settings
            self.band.refresh_from_db()
            self.assertEqual(self.band.settings["display_mode"], mode)
            self.assertTrue(self.band.settings["appearance_overrides"]["variant_explicit"])
            # effective render settings (what the template receives)
            item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == self.band.pk)
            self.assertEqual(item["context"]["settings"]["display_mode"], mode)
            seen[mode] = self._markers(self._band_html())
        self.assertEqual(seen["carousel"], {"pcarousel": True, "grid": False, "campaign": False, "catalog": False, "catalog_bar": False})
        self.assertEqual(seen["grid"], {"pcarousel": False, "grid": True, "campaign": False, "catalog": False, "catalog_bar": False})
        self.assertEqual(seen["campaign_band"], {"pcarousel": False, "grid": False, "campaign": True, "catalog": False, "catalog_bar": False})
        self.assertEqual(seen["catalog_grid"], {"pcarousel": False, "grid": False, "campaign": False, "catalog": True, "catalog_bar": True})
        self.assertEqual(len({tuple(sorted(v.items())) for v in seen.values()}), 4)  # four visibly different renders

    def test_campaign_band_has_a_promo_region_and_catalog_grid_a_closing_bar(self):
        self._patch({"display_mode": "campaign_band", "campaign_panel_subtitle": "تا ۳۰٪ تخفیف"})
        html = self._band_html()
        self.assertIn("product-campaign-copy", html)
        self.assertIn("تا ۳۰٪ تخفیف", html)
        self._patch({"display_mode": "catalog_grid"})
        html = self._band_html()
        self.assertIn("catalog-grid-head", html)
        self.assertIn("catalog-grid-bar-row", html)

    def test_a_stale_row_setting_of_another_composition_never_hijacks_the_variant(self):
        self.assertEqual(self._patch({"desktop_layout": "grid", "overflow_mode": "clip", "carousel_navigation": "dots"}).status_code, 200)
        self.assertEqual(self._patch({"display_mode": "campaign_band"}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["desktop_layout"], "grid")  # dormant, not destroyed
        html = self._band_html()
        self.assertIn("product-campaign-band", html)
        self.assertNotIn("data-desktop-layout", html)
        self.assertNotIn("pcarousel-shell", html)
        item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == self.band.pk)
        for dormant in ("desktop_layout", "overflow_mode", "carousel_navigation"):
            self.assertNotIn(dormant, item["context"]["settings"])
        # back to a carousel: the merchant's earlier row choices are live again
        self.assertEqual(self._patch({"display_mode": "carousel"}).status_code, 200)
        html = self._band_html()
        self.assertIn('data-desktop-layout="grid"', html)
        self.assertIn('data-overflow="clip"', html)

    def test_effective_presentation_projection(self):
        project = section_registry.effective_product_section_settings
        stale = {"display_mode": "grid", "carousel_autoplay": True, "desktop_layout": "carousel", "overflow_mode": "visible"}
        self.assertEqual(project(stale), {"display_mode": "grid"})
        spotlight = project({"display_mode": "carousel", "carousel_autoplay": True, "overflow_mode": "clip", "gap": 9})
        self.assertEqual(spotlight, {"display_mode": "carousel", "carousel_autoplay": True, "gap": 9})
        plain = {"display_mode": "carousel", "overflow_mode": "clip"}
        self.assertIs(project(plain), plain)

    def test_gap_and_columns_apply_to_every_composition_that_offers_them(self):
        self._patch({"gap": 30, "desktop_columns": 3})
        for mode, needle in (("grid", "gap:30px"), ("campaign_band", "gap:30px"), ("catalog_grid", "gap:30px"), ("carousel", "--pcarousel-gap:30px")):
            self.assertEqual(self._patch({"display_mode": mode}).status_code, 200)
            html = self._band_html()
            self.assertIn(needle, html, mode)
            self.assertIn("--cols-desktop:3", html, mode)


# ----------------------------------------------------------------------------------- conditional Inspector
class ConditionalInspectorTests(_BandBase):
    CAROUSEL_ONLY = ("carousel_autoplay", "desktop_layout", "overflow_mode", "carousel_navigation")

    def _hidden(self, response=None):
        response = response or self._inspector()
        return set(response.context["field_hidden_map"]), response

    def test_carousel_offers_row_controls(self):
        hidden, response = self._hidden()
        self.assertEqual(hidden & set(self.CAROUSEL_ONLY), set())
        self.assertNotIn("show_scrollbar", hidden)
        self.assertIn("carousel_interval_ms", hidden)  # autoplay is off
        self.assertContains(response, 'data-r4-visible-when=')

    def test_grid_hides_carousel_controls_and_keeps_columns(self):
        self._patch({"display_mode": "grid"})
        hidden, _ = self._hidden()
        self.assertTrue(set(self.CAROUSEL_ONLY + ("show_scrollbar", "carousel_interval_ms", "carousel_show_arrows")) <= hidden)
        self.assertEqual(hidden & {"desktop_columns", "tablet_columns", "mobile_columns", "gap", "heading_style", "header_position"}, set())

    def test_campaign_band_and_catalog_grid_show_only_what_they_consume(self):
        for mode in ("campaign_band", "catalog_grid"):
            self._patch({"display_mode": mode})
            hidden, response = self._hidden()
            self.assertTrue(set(self.CAROUSEL_ONLY + ("show_scrollbar", "heading_style", "header_position")) <= hidden, mode)
            self.assertEqual(hidden & {"title", "source", "item_limit", "show_view_all", "desktop_columns", "gap", "background", "design"}, set(), mode)
            self.assertEqual("subtitle" in hidden, mode == "campaign_band", mode)  # the panel owns the copy of a campaign band
            html = response.content.decode()
            self.assertRegex(html, r'data-r4-field-key="desktop_layout"[^>]*data-r4-visible-when=[^>]* hidden')

    def test_autoplay_replaces_the_row_controls_with_the_slider_controls(self):
        self._patch({"carousel_autoplay": True})
        hidden, _ = self._hidden()
        self.assertTrue({"desktop_layout", "overflow_mode", "carousel_navigation", "show_scrollbar", "desktop_columns", "gap"} <= hidden)
        self.assertEqual(hidden & {"carousel_interval_ms", "carousel_show_arrows"}, set())

    def test_scrollbar_control_only_for_a_scrolling_row(self):
        self._patch({"overflow_mode": "visible"})
        hidden, _ = self._hidden()
        self.assertIn("show_scrollbar", hidden)
        self._patch({"overflow_mode": "scroll"})
        hidden, _ = self._hidden()
        self.assertNotIn("show_scrollbar", hidden)

    def test_background_widget_only_offers_controls_for_the_current_mode(self):
        for background, visible, hidden in (
            ({"mode": "color", "color": "#336699"}, ("color pattern",), ("palette palette_pattern", "image")),
            ({"mode": "palette", "palette_role": "tone-2"}, ("palette palette_pattern",), ("color pattern", "image", "pattern palette_pattern")),
            ({"mode": "theme"}, (), ("color pattern", "palette palette_pattern", "image", "pattern palette_pattern")),
        ):
            self._patch({"background": background})
            html = self._inspector().content.decode()
            for group in visible:
                self.assertTrue(re.search(r'data-r4-bg-modes="%s"\s*>' % group, html), (background, group))
            for group in hidden:
                self.assertTrue(re.search(r'data-r4-bg-modes="%s"\s+hidden' % group, html), (background, group))

    def test_visibility_rules_are_pure_metadata_and_validate(self):
        fields = {f.key: f for f in section_registry.PRODUCT_SECTION_SCHEMA.fields}
        self.assertEqual(settings_schema.compute_field_visibility(fields.values(), {"display_mode": "grid"})["overflow_mode"], False)
        self.assertEqual(settings_schema.compute_field_visibility(fields.values(), {"display_mode": "carousel"})["overflow_mode"], True)
        serialized = settings_schema.serialize_schema(section_registry.PRODUCT_SECTION_SCHEMA)
        by_key = {f["key"]: f for f in serialized["fields"]}
        self.assertEqual(by_key["overflow_mode"]["visible_when"], {"display_mode": ["carousel"], "carousel_autoplay": ["false"]})
        self.assertEqual(by_key["title"]["visible_when"], {})

    def test_editor_re_evaluates_visibility_live(self):
        self.assertIn("function applyFieldVisibility()", EDITOR_JS)
        self.assertIn("data-r4-visible-when", EDITOR_JS)
        self.assertIn("applyFieldVisibility();", EDITOR_JS)


# ----------------------------------------------------------------------------- recipe vs merchant override
class MerchantOverrideBeatsTheRecipeTests(_BandBase):
    def test_recipe_value_is_only_a_default(self):
        self.assertEqual(self.band.settings["display_mode"], "carousel")  # Template 51's recipe default
        response = self._patch({"display_mode": "campaign_band",
                                "background": {"mode": "color", "color": "#2f6fed", "bleed": True},
                                "design": {"radius": 14}})
        self.assertEqual(response.status_code, 200, response.content)
        for _ in range(2):  # reloading the Preview never restores the recipe
            html = self._preview()
            band = self._band_html(html)
            self.assertIn("product-campaign-band", band)
            self.assertIn("--sfb-section-bg-color:#2f6fed", band)
        item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == self.band.pk)
        self.assertEqual(item["context"]["settings"]["display_mode"], "campaign_band")
        self.assertEqual(item["context"]["settings"]["background"]["color"], "#2f6fed")
        self.assertEqual(item["context"]["settings"]["design"]["radius"], 14)

    def test_unrelated_edits_keep_the_merchants_choices(self):
        self._patch({"display_mode": "catalog_grid", "background": {"mode": "palette", "palette_role": "tone-4", "bleed": True}})
        self.assertEqual(self._patch({"title": "عنوان جدید"}).status_code, 200)
        self.assertEqual(self._patch({"item_limit": 4}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["display_mode"], "catalog_grid")
        self.assertEqual(self.band.settings["background"]["palette_role"], "tone-4")
        self.assertIn("catalog-grid-products", self._band_html())

    def test_the_store_appearance_family_cannot_overlay_an_explicit_display_type(self):
        self._patch({"display_mode": "campaign_band"})
        self.band.refresh_from_db()
        self.assertTrue(self.band.settings["appearance_overrides"]["variant_explicit"])
        # the Store-level family default for the variant axis is ignored for an explicit local choice
        from apps.storefront_builder.services import render_service

        with_appearance = [i for i in render_service.build_render_items(self.draft, self.store) if i["section"].pk == self.band.pk]
        self.assertEqual(with_appearance[0]["context"]["settings"]["display_mode"], "campaign_band")

    def test_only_reapplying_the_whole_template_replaces_the_settings(self):
        self._patch({"display_mode": "grid", "background": {"mode": "color", "color": "#2f6fed", "bleed": True}})
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("stationery_spectrum"))
        bands = StorefrontSection.objects.filter(page__version=self.draft, section_key="product_section").order_by("order")
        recipe_band = next(s for s in bands if (s.settings.get("background") or {}).get("mode") == "palette_pattern")
        self.assertEqual(recipe_band.settings["display_mode"], "carousel")
        self.assertEqual(recipe_band.settings["background"]["pattern_slug"], "commerce-doodle")


# ----------------------------------------------------------------------------------------- editor contract
class PreviewRefreshAfterEveryInspectorWriteTests(R4MutationApiTestCase):
    """Root cause of the display-type "no-op": an accepted ``section.update_settings`` changed the stored and effective
    value but never refreshed the visible Preview iframe."""

    def test_accepted_inspector_mutations_refresh_the_preview(self):
        match = re.search(r"var PREVIEW_REFRESH_MUTATIONS = \{(.*?)\};", EDITOR_JS, re.S)
        self.assertIsNotNone(match)
        for mutation_type in ("section.update_settings", "container.update_settings", "section.reset_setting_to_baseline"):
            self.assertIn(f"'{mutation_type}': true", match.group(1))
        # the refresh sits in the accepted (200 + ok) branch, after the revision cursor advanced: a canonical fragment
        # swap when the server returned one, otherwise the atomic full-frame refresh
        self.assertIn("if (PREVIEW_REFRESH_MUTATIONS[mutation.type]) {", EDITOR_JS)
        self.assertIn("reloadPreviewFrame();\n              path = 'full';", EDITOR_JS)
        ok_branch = EDITOR_JS.index("setSaveState('saved');")
        self.assertLess(ok_branch, EDITOR_JS.index("if (PREVIEW_REFRESH_MUTATIONS[mutation.type]) {"))
        self.assertLess(EDITOR_JS.index("if (PREVIEW_REFRESH_MUTATIONS[mutation.type]) {"), EDITOR_JS.index("if (result.status === 409)"))

    def test_the_refresh_is_the_atomic_twin_frame_swap(self):
        self.assertIn("function runPreviewRefresh(nextSrc)", EDITOR_JS)
        self.assertIn("twin.style.opacity = '0'", EDITOR_JS)
        self.assertIn("R4.reloadPreview = reloadPreviewFrame;", EDITOR_JS)

    def test_the_resource_picker_no_longer_double_refreshes(self):
        picker = EDITOR_JS[EDITOR_JS.index("function applyResourcePicker()"):EDITOR_JS.index("R4.openResourcePicker = ")]
        self.assertNotIn("reloadPreviewFrame()", picker)

    def test_display_type_change_reopens_the_inspector_for_server_authoritative_visibility(self):
        self.assertIn("var isVariantChange = key === 'display_mode';", EDITOR_JS)
        self.assertIn("if (result && result.ok && stillCurrent) R4.openSection(sectionId);", EDITOR_JS)
        self.assertIn("R4.pendingWrites === 0", EDITOR_JS)  # an older response never overwrites a newer choice
