"""Template 51 — interaction performance (partial refresh) + campaign panel designability.

Owner QA: some Inspector controls looked dead, working ones updated the Preview slowly (every write reloaded the whole
storefront document) and the campaign band's promotional panel (copy + a hard-coded gift SVG) could be neither removed
nor edited. Pinned here:

* partial refresh — the mutation response carries the CANONICAL server-rendered fragment of the affected section /
  container (same templates as the full Preview), the Studio swaps only that region (Alpine re-initialised) and falls back
  to the atomic full refresh otherwise; rapid input is coalesced (latest value wins);
* the campaign panel is engine configuration (``campaign_*`` settings + ``icon_registry`` + Store-scoped media), with no
  hard-coded SVG or merchant-facing copy, removable (the product region expands) and independently colourable;
* no visible product-section control is dead (data-driven check over the schema) and hidden controls never leak.

Real-browser latency / Alpine / coalescing checks live in ``test_engine_parity_browser.py`` (opt-in)."""

import json
import re
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.content.models import MediaAsset
from apps.core.color_utils import contrast_ratio
from apps.storefront_builder import icon_registry, section_registry, settings_schema
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store

from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
EDITOR_JS = (APP / "static" / "storefront_builder" / "r4_editor.js").read_text(encoding="utf-8")
BUILDER_CSS = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
SECTION_TEMPLATE = (APP / "templates" / "storefront_builder" / "sections" / "product_section.html").read_text(encoding="utf-8")


def _png(name="panel.png"):
    buf = BytesIO()
    Image.new("RGB", (200, 200), (10, 120, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _element(html, start_marker):
    """The balanced ``<div ...>...</div>`` element that begins at ``start_marker`` (a section / container wrapper)."""
    start = html.rindex("<div", 0, html.index(start_marker))
    depth, pos = 0, start
    for match in re.finditer(r"<div\b|</div>", html[start:]):
        depth += 1 if match.group(0) != "</div>" else -1
        pos = start + match.end()
        if depth == 0:
            break
    return html[start:pos]


def _norm(html):
    return re.sub(r"\s+", " ", html).strip()


class _CampaignBase(_BandBase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self._patch({"display_mode": "campaign_band", "title": "پیشنهادهای ویژه",
                                      "campaign_panel_title": "هنر، نقاشی و کاردستی"}).status_code, 200)

    def _fragment(self, patch_value=None):
        self.draft.refresh_from_db()
        if patch_value is None:
            patch_value = {"title": "پیشنهادهای ویژه"}
        response = self._post_json({"base_revision": self.draft.edit_revision, "fragment": True, "mutation": {
            "type": "section.update_settings", "section_id": self.band.pk, "patch": patch_value}})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _panel(self, html=None):
        html = html or self._band_html()
        match = re.search(r'<aside class="product-campaign-copy".*?</aside>', html, re.S)
        return match.group(0) if match else ""


# ------------------------------------------------------------------------------------------- partial refresh
class PartialRefreshTests(_CampaignBase):
    def test_mutation_response_carries_the_canonical_section_fragment(self):
        body = self._fragment({"campaign_panel_title": "عنوان تازه"})
        fragment = body["fragment"]
        self.assertEqual((fragment["kind"], fragment["id"]), ("section", self.band.pk))
        self.assertIn("عنوان تازه", fragment["html"])
        # canonical: byte-for-byte (whitespace-normalised) the SAME markup the full Preview renders for that section
        full = _element(self._preview(), f'data-section-id="{self.band.pk}"')
        self.assertEqual(_norm(fragment["html"]), _norm(full))

    def test_fragment_is_only_returned_on_request_and_for_eligible_mutation_types(self):
        self.draft.refresh_from_db()
        plain = self._post_json({"base_revision": self.draft.edit_revision, "mutation": {
            "type": "section.update_settings", "section_id": self.band.pk, "patch": {"title": "الف"}}}).json()
        self.assertNotIn("fragment", plain)
        self.draft.refresh_from_db()
        other = self._post_json({"base_revision": self.draft.edit_revision, "fragment": True, "mutation": {
            "type": "section.toggle_active", "section_id": self.band.pk}}).json()
        self.assertNotIn("fragment", other)  # structural / non-settings writes use the full refresh

    def test_rejected_write_returns_no_fragment_and_changes_nothing(self):
        self.band.refresh_from_db()
        before = dict(self.band.settings)
        self.draft.refresh_from_db()
        response = self._post_json({"base_revision": self.draft.edit_revision, "fragment": True, "mutation": {
            "type": "section.update_settings", "section_id": self.band.pk, "patch": {"campaign_panel_bg": "red"}}})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("fragment", response.json())
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings, before)

    def test_container_fragment_is_the_canonical_container(self):
        container_id = int(re.search(rf'data-cell-id="{self.band.pk}" data-container-id="(\d+)"', self._preview()).group(1))
        self.draft.refresh_from_db()
        body = self._post_json({"base_revision": self.draft.edit_revision, "fragment": True, "mutation": {
            "type": "container.update_settings", "container_id": container_id, "patch": {"gap": 24}}}).json()
        fragment = body["fragment"]
        self.assertEqual((fragment["kind"], fragment["id"]), ("container", container_id))
        full = _element(self._preview(), f'data-container-id="{container_id}"')
        self.assertEqual(_norm(fragment["html"]), _norm(full))
        self.assertIn("--container-gap:24px", fragment["html"])

    def test_fragment_of_an_unknown_or_foreign_target_is_none_not_an_error(self):
        from apps.storefront_builder.views import render_preview_fragment

        class _Req:
            pass

        self.assertIsNone(render_preview_fragment(_Req(), self.store, self.draft, section_id=99999999))
        self.assertIsNone(render_preview_fragment(_Req(), self.store, self.draft, container_id=99999999))
        self.assertIsNone(render_preview_fragment(_Req(), self.store, self.draft))

    def test_only_the_requested_sections_are_built(self):
        from apps.storefront_builder.services.render_service import build_page_render_items

        page = self.band.page
        everything = build_page_render_items(page, self.store)
        only = build_page_render_items(page, self.store, only_section_ids={self.band.pk})
        self.assertGreater(len(everything), 1)
        self.assertEqual([item["section"].pk for item in only], [self.band.pk])

    def test_studio_applies_fragments_with_alpine_reinitialisation_and_safe_fallbacks(self):
        self.assertIn("function applyPreviewFragment(fragment)", EDITOR_JS)
        self.assertIn("alpine.destroyTree(current)", EDITOR_JS)
        self.assertIn("current.replaceWith(next)", EDITOR_JS)
        self.assertIn("alpine.initTree(next)", EDITOR_JS)
        self.assertLess(EDITOR_JS.index("alpine.destroyTree(current)"), EDITOR_JS.index("current.replaceWith(next)"))
        self.assertLess(EDITOR_JS.index("current.replaceWith(next)"), EDITOR_JS.index("alpine.initTree(next)"))
        # fall back to the atomic full refresh for anything that cannot be applied faithfully
        self.assertIn("if (/<script[\\s>]/i.test(fragment.html)) return false;", EDITOR_JS)
        self.assertIn("src.indexOf('design_lab=') === -1", EDITOR_JS)
        self.assertIn("previewRefresh.busy", EDITOR_JS[EDITOR_JS.index("function canPartialRefresh()"):EDITOR_JS.index("function applyPreviewFragment")])
        self.assertIn("fragment: wantFragment", EDITOR_JS)
        self.assertIn("reloadPreviewFrame();\n              path = 'full';", EDITOR_JS)
        # no storefront rendering lives in JavaScript: the swap only inserts the server's HTML
        self.assertIn("holder.innerHTML = fragment.html;", EDITOR_JS)

    def test_rapid_input_is_coalesced_latest_value_wins(self):
        for needle in ("var COALESCE_DELAY_MS = 110;", "function flushPendingSlot(slotKey)", "R4.flushPending = function",
                       "slot.mutation.patch[key] = mutation.patch[key];", "R4.inputPhase"):
            self.assertIn(needle, EDITOR_JS)
        # continuous controls feed the same change path in "input phase"; integers commit on change only
        self.assertIn("inspector.addEventListener('input'", EDITOR_JS)
        self.assertIn("control.getAttribute('data-r4-field-type') === 'integer') return;", EDITOR_JS)
        # a non-settings write flushes pending edits first, preserving the order of writes
        self.assertRegex(EDITOR_JS, r"R4\.flushPending\(\);\s+lastSent = \{\};\s+return enqueueNow\(mutation\);")

    def test_history_snapshot_uses_a_constant_number_of_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.storefront_builder.services import edit_history_service

        with CaptureQueriesContext(connection) as small:
            edit_history_service.snapshot_draft(self.draft)
        for index in range(12):  # many more sections must not mean many more queries
            StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=100 + index)
        with CaptureQueriesContext(connection) as large:
            edit_history_service.snapshot_draft(self.draft)
        self.assertLessEqual(len(large), len(small) + 2)


# ------------------------------------------------------------------------------------------- icon registry
class IconRegistryTests(_CampaignBase):
    def test_registry_is_generic_and_fails_closed(self):
        for key in ("gift", "star", "sparkles", "shopping_bag", "heart"):
            self.assertIn(key, icon_registry.ICON_KEYS)
            svg = icon_registry.icon_svg(key)
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("currentColor", svg)
        self.assertEqual(icon_registry.icon_svg("<script>"), "")
        self.assertEqual(icon_registry.icon_svg(None), "")
        self.assertEqual([key for key, _label in icon_registry.icon_choices()], list(icon_registry.ICON_KEYS))
        self.assertNotIn("stationery", Path(icon_registry.__file__).read_text(encoding="utf-8").lower())

    def test_template_embeds_no_fixed_svg_and_no_invented_copy(self):
        campaign = SECTION_TEMPLATE[SECTION_TEMPLATE.index('{% if settings.display_mode == "campaign_band" %}'):
                                    SECTION_TEMPLATE.index('{% elif settings.display_mode == "catalog_grid" %}')]
        self.assertNotIn("<svg", campaign)
        self.assertNotIn("<path", campaign)
        self.assertNotIn("پیشنهادهای فروشگاه", SECTION_TEMPLATE)
        self.assertNotIn('|default:"محصولات"', SECTION_TEMPLATE[SECTION_TEMPLATE.index("catalog-grid-head"):SECTION_TEMPLATE.index("catalog-grid-products")])

    def test_icon_choice_round_trip_and_unknown_key_rejected_silently(self):
        self.assertEqual(self._patch({"campaign_icon_key": "heart"}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["campaign_icon_key"], "heart")
        self.assertIn(str(icon_registry.icon_svg("heart"))[:120], self._panel())
        self.assertEqual(self._patch({"campaign_icon_key": "gift"}).status_code, 200)  # the default is not stored
        self.band.refresh_from_db()
        self.assertNotIn("campaign_icon_key", self.band.settings)
        self.assertEqual(self._patch({"campaign_icon_key": "not-an-icon"}).status_code, 400)  # not a registry key
        self.band.refresh_from_db()
        self.assertNotIn("campaign_icon_key", self.band.settings)


# ------------------------------------------------------------------------------------------- campaign panel
class CampaignPanelContractTests(_CampaignBase):
    def test_section_title_and_panel_title_are_independent(self):
        self.assertEqual(self._patch({"title": "پیشنهادهای ویژه", "campaign_panel_title": "هنر، نقاشی و کاردستی"}).status_code, 200)
        html = self._band_html()
        self.assertRegex(html, re.compile(r'<div class="beauty-section-title product-campaign-heading".*?<h2>پیشنهادهای ویژه</h2>', re.S))
        self.assertIn("<h2>هنر، نقاشی و کاردستی</h2>", self._panel(html))
        self.assertEqual(self._patch({"title": "عنوان تازه"}).status_code, 200)
        html = self._band_html()
        self.assertIn("<h2>عنوان تازه</h2>", html)
        self.assertIn("<h2>هنر، نقاشی و کاردستی</h2>", self._panel(html))  # editing one never rewrites the other

    def test_a_legacy_section_follows_its_title_until_the_first_edit_pins_it(self):
        self.band.refresh_from_db()
        legacy = {k: v for k, v in self.band.settings.items() if not k.startswith("campaign_")}
        legacy.update(title="عنوان قدیمی", subtitle="توضیح قدیمی")
        self.band.settings = legacy
        self.band.save()
        html = self._band_html()
        self.assertIn("<h2>عنوان قدیمی</h2>", self._panel(html))   # historical behaviour: the panel shows the section copy
        self.assertIn("<p>توضیح قدیمی</p>", self._panel(html))
        inspector = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk]))
        self.assertEqual(inspector.context["field_values"]["campaign_panel_title"], "عنوان قدیمی")  # shows what the renderer uses
        self.assertEqual(inspector.context["field_values"]["campaign_panel_subtitle"], "توضیح قدیمی")
        self.assertEqual(self._patch({"title": "عنوان جدید"}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["campaign_panel_title"], "عنوان قدیمی")  # pinned: no silent rewrite
        self.assertNotIn("campaign_panel_subtitle", self.band.settings)  # only what the patch changes is pinned
        self.assertIn("<p>توضیح قدیمی</p>", self._panel())
        self.assertEqual(self._patch({"subtitle": "توضیح جدید"}).status_code, 200)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["campaign_panel_subtitle"], "توضیح قدیمی")
        self.assertIn("<p>توضیح قدیمی</p>", self._panel())

    def test_no_copy_is_invented_when_the_merchant_clears_it(self):
        self.assertEqual(self._patch({"title": "", "campaign_panel_title": "", "campaign_panel_subtitle": ""}).status_code, 200)
        html = self._band_html()
        self.assertNotIn("product-campaign-heading", html)
        panel = self._panel(html)
        self.assertNotIn("<h2>", panel)
        self.assertNotIn("<p>", panel)
        self.assertNotIn("پیشنهادهای فروشگاه", html)

    def test_panel_removal_removes_the_panel_and_the_product_region_takes_the_width(self):
        self.assertIn('class="product-campaign-copy"', self._band_html())
        self.assertEqual(self._patch({"campaign_panel_enabled": False}).status_code, 200)
        html = self._band_html()
        self.assertNotIn("product-campaign-copy", html)
        self.assertNotIn("<aside", html)
        self.assertIn("product-campaign-band product-campaign-band--no-panel", html)
        self.assertRegex(BUILDER_CSS, r"\.product-campaign-band--no-panel\{grid-template-columns:minmax\(0,1fr\)\}")
        self.band.refresh_from_db()
        self.assertIs(self.band.settings["campaign_panel_enabled"], False)
        self.assertEqual(self._patch({"campaign_panel_enabled": True}).status_code, 200)  # restore: default not stored
        self.band.refresh_from_db()
        self.assertNotIn("campaign_panel_enabled", self.band.settings)
        self.assertIn('class="product-campaign-copy"', self._band_html())

    def test_visual_none_icon_media_and_store_scoped_media(self):
        asset = MediaAsset.objects.create(store=self.store, image=_png())
        self.assertIn("product-campaign-gift", self._band_html())
        self.assertEqual(self._patch({"campaign_visual_mode": "none"}).status_code, 200)
        self.assertNotIn("product-campaign-gift", self._band_html())
        self.assertEqual(self._patch({"campaign_visual_mode": "media", "campaign_media_asset_id": asset.pk}).status_code, 200)
        html = self._band_html()
        self.assertIn(f'<img src="{asset.image.url}"', html)
        self.assertNotIn("<svg", self._panel(html))
        # a foreign Store's asset is rejected at write time and never stored
        other = Store.objects.create(name="فروشگاه ج", slug="cp-cross", admin_subdomain="cp-cross")
        foreign = MediaAsset.objects.create(store=other, image=_png("foreign.png"))
        self.assertEqual(self._patch({"campaign_media_asset_id": foreign.pk}).status_code, 400)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings["campaign_media_asset_id"], asset.pk)
        # an id that is no longer a valid asset renders NO visual rather than a broken image / a foreign picture
        MediaAsset.objects.filter(pk=asset.pk).delete()
        self.assertNotIn("<img", self._panel())
        self.assertNotIn("product-campaign-gift", self._panel())

    def test_there_is_no_raw_url_field_for_the_panel_visual(self):
        keys = {field.key for field in section_registry.PRODUCT_SECTION_SCHEMA.fields}
        self.assertNotIn("campaign_media_url", keys)
        self.assertEqual({f.key: f.field_type for f in section_registry.PRODUCT_SECTION_SCHEMA.fields}["campaign_media_asset_id"], "media")
        cleaned = section_registry.get_definition("product_section").validate_settings(
            {"data_source": "newest", "campaign_media_url": "https://evil.example/x.png", "campaign_visual_mode": "media"})
        self.assertNotIn("campaign_media_url", cleaned)

    def test_panel_design_controls_round_trip_and_reach_the_markup(self):
        patch_value = {
            "campaign_panel_bg": "token:tone-4", "campaign_panel_fg": "#FFE08A", "campaign_panel_accent": "token:accent",
            "campaign_panel_border_color": "#112233", "campaign_panel_border_width": 2, "campaign_panel_radius": 28,
            "campaign_panel_padding": 30, "campaign_visual_size": 96, "campaign_panel_width": 24, "campaign_panel_align": "start",
        }
        self.assertEqual(self._patch(patch_value).status_code, 200)
        self.band.refresh_from_db()
        for key, value in patch_value.items():
            self.assertEqual(self.band.settings[key], value, key)
        html = self._band_html()
        for needle in ("--cp-bg:var(--brand-tone-4)", "--cp-fg:#FFE08A", "--cp-accent:var(--brand-accent)", "--cp-bc:#112233",
                       "--cp-bw:2px", "--cp-radius:28px", "--cp-pad:30px", "--cp-visual:96px", 'data-align="start"', "--cp-w:24%"):
            self.assertIn(needle, html)
        # each variable has a consumer in the generic CSS (no control without an effect)
        for var in ("--cp-bg", "--cp-fg", "--cp-accent", "--cp-bc", "--cp-bw", "--cp-radius", "--cp-pad", "--cp-visual", "--cp-w"):
            self.assertIn(f"var({var}", BUILDER_CSS, var)
        for out_of_range in ({"campaign_panel_width": 99}, {"campaign_visual_size": 5}, {"campaign_panel_radius": -3}):
            self.assertEqual(self._patch(out_of_range).status_code, 400, out_of_range)  # the schema bounds are authoritative
        self.band.refresh_from_db()
        self.assertEqual((self.band.settings["campaign_panel_width"], self.band.settings["campaign_visual_size"]), (24, 96))

    def test_invalid_panel_colours_are_rejected_and_nothing_is_stored(self):
        self.band.refresh_from_db()
        before = dict(self.band.settings)
        for bad in ({"campaign_panel_bg": "red"}, {"campaign_panel_fg": "javascript:1"}, {"campaign_panel_accent": "token:nope"}):
            self.assertEqual(self._patch(bad).status_code, 400, bad)
        self.band.refresh_from_db()
        self.assertEqual(self.band.settings, before)

    def test_automatic_foreground_keeps_the_panel_readable_for_any_custom_fill(self):
        for fill in ("#d62828", "#2f6fed", "#ffd60a", "#ffffff", "#000000", "#808080", "#767676", "#1b4332", "#e0e0e0"):
            with self.subTest(fill=fill):
                self.assertEqual(self._patch({"campaign_panel_bg": fill, "campaign_panel_fg": ""}).status_code, 200)
                panel = self._panel()
                match = re.search(r"--cp-bg:%s;--cp-fg:(#[0-9A-Fa-f]{6})" % fill, panel, re.I)
                self.assertIsNotNone(match, panel[:300])
                self.assertGreaterEqual(contrast_ratio(fill, match.group(1)), 4.5)

    def test_panel_colour_is_independent_of_the_section_background(self):
        self.assertEqual(self._patch({"campaign_panel_bg": "token:tone-4"}).status_code, 200)
        self.assertEqual(self._patch({"background": {"mode": "color", "color": "#2f6fed", "bleed": True}}).status_code, 200)
        html = self._band_html()
        self.assertIn("--sfb-section-bg-color:#2f6fed", html)
        self.assertIn("--cp-bg:var(--brand-tone-4)", self._panel(html))

    def test_campaign_band_fill_comes_from_the_section_background_for_every_mode(self):
        # a custom colour, a palette role, a pattern and a picture all fill the band box (not only a palette role)
        self.assertRegex(BUILDER_CSS, r"\.product-campaign-band\{\s*padding:14px;border-radius:22px;color:var\(--sfb-section-fg,#fff\);\s*"
                                      r"background-color:var\(--sfb-section-bg-color,var\(--sfb-section-palette-bg,var\(--brand-primary\)\)\);\s*"
                                      r"background-image:linear-gradient\(var\(--sfb-overlay,transparent\)")
        self.assertEqual(self._patch({"background": {"mode": "color", "color": "#2f6fed"}}).status_code, 200)
        self.assertIn("--sfb-section-bg-color:#2f6fed", self._band_html())
        asset = MediaAsset.objects.create(store=self.store, image=_png("band.png"))
        self.assertEqual(self._patch({"background": {"mode": "image", "media_asset_id": asset.pk, "image_fit": "contain",
                                                      "overlay_color": "token:text", "overlay_opacity": 40}}).status_code, 200)
        import html as html_lib

        html = html_lib.unescape(self._band_html())
        self.assertIn(f"--sfb-bg-image:url('{asset.image.url}')", html)
        self.assertIn("--sfb-bg-size:contain", html)
        self.assertIn("--sfb-overlay:color-mix(in srgb,var(--brand-text) 40%,transparent)", html)

    def test_preview_equals_published_for_the_final_panel_state(self):
        asset = MediaAsset.objects.create(store=self.store, image=_png())
        self.assertEqual(self._patch({
            "campaign_panel_title": "عنوان نهایی", "campaign_panel_subtitle": "زیرعنوان", "campaign_visual_mode": "media",
            "campaign_media_asset_id": asset.pk, "campaign_panel_bg": "token:tone-2", "campaign_panel_radius": 18,
        }).status_code, 200)
        preview, published = self._publish_and_pair()
        section = lambda html: _norm(re.search(r"<section class=\"section product-section.*?</section>", html, re.S).group(0))  # noqa: E731
        self.assertEqual(section(preview), section(published))  # builder chrome aside, the rendered section is identical
        self.assertIn("عنوان نهایی", published)
        self.assertIn("--cp-radius:18px", published)


# --------------------------------------------------------------------------------------- conditional controls
class CampaignInspectorConditionalTests(_CampaignBase):
    CAMPAIGN_KEYS = ("campaign_panel_enabled", "campaign_panel_title", "campaign_panel_subtitle", "campaign_visual_mode",
                     "campaign_icon_key", "campaign_media_asset_id", "campaign_visual_size", "campaign_panel_width",
                     "campaign_panel_align", "campaign_panel_bg", "campaign_panel_fg", "campaign_panel_accent",
                     "campaign_panel_border_color", "campaign_panel_border_width", "campaign_panel_radius", "campaign_panel_padding")

    def _hidden(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk]))
        self.assertEqual(response.status_code, 200)
        return set(response.context["field_hidden_map"]), response

    def test_campaign_controls_exist_only_for_the_campaign_band(self):
        hidden, response = self._hidden()
        self.assertFalse(hidden & set(self.CAMPAIGN_KEYS) - {"campaign_media_asset_id"})  # media hidden: visual mode is icon
        for key in self.CAMPAIGN_KEYS:
            self.assertContains(response, f'data-r4-field-key="{key}"')
        for mode in ("carousel", "grid", "catalog_grid"):
            self.assertEqual(self._patch({"display_mode": mode}).status_code, 200)
            hidden, _ = self._hidden()
            self.assertTrue(set(self.CAMPAIGN_KEYS) <= hidden, mode)
        self.assertEqual(self._patch({"display_mode": "campaign_band"}).status_code, 200)

    def test_panel_disabled_hides_every_panel_content_control_and_the_dead_view_all(self):
        self.assertEqual(self._patch({"campaign_panel_enabled": False}).status_code, 200)
        hidden, _ = self._hidden()
        self.assertEqual(hidden & set(self.CAMPAIGN_KEYS), set(self.CAMPAIGN_KEYS) - {"campaign_panel_enabled"})
        self.assertIn("show_view_all", hidden)  # the only "view all" of a campaign band lives in the panel

    def test_visual_mode_selects_the_right_picker(self):
        for mode, hidden_keys, shown_keys in (
            ("icon", {"campaign_media_asset_id"}, {"campaign_icon_key", "campaign_visual_size"}),
            ("media", {"campaign_icon_key"}, {"campaign_media_asset_id", "campaign_visual_size"}),
            ("none", {"campaign_icon_key", "campaign_media_asset_id", "campaign_visual_size"}, set()),
        ):
            self.assertEqual(self._patch({"campaign_visual_mode": mode}).status_code, 200)
            hidden, _ = self._hidden()
            self.assertTrue(hidden_keys <= hidden, (mode, hidden))
            self.assertFalse(shown_keys & hidden, (mode, hidden))

    def test_subtitle_is_hidden_where_the_campaign_panel_owns_the_copy(self):
        hidden, _ = self._hidden()
        self.assertIn("subtitle", hidden)
        self.assertEqual(self._patch({"display_mode": "grid"}).status_code, 200)
        hidden, _ = self._hidden()
        self.assertNotIn("subtitle", hidden)

    def test_basic_tab_holds_the_panel_content_controls(self):
        _hidden, response = self._hidden()
        basic = {f.key for f in response.context["basic_fields"]}
        self.assertTrue({"campaign_panel_enabled", "campaign_panel_title", "campaign_panel_subtitle", "campaign_visual_mode",
                         "campaign_icon_key", "campaign_media_asset_id", "background"} <= basic)
        advanced = {f.key for f in response.context["advanced_fields"]}
        self.assertTrue({"campaign_panel_bg", "campaign_panel_fg", "campaign_panel_radius", "campaign_panel_width"} <= advanced)


# --------------------------------------------------------------------------- no dead control (data driven)
class NoDeadProductSectionControlTests(_CampaignBase):
    """For every visible schema control of a product section, in every display type: changing it must change the
    canonical rendered section. (The real-browser audit of the Rasti Mode Demo band is recorded in the report.)"""

    ALTERNATIVES = {
        "boolean": lambda value: not value,
        "integer": lambda value: (value or 3) + 2,
        "text": lambda value: (value or "") + "x",
        "color": lambda value: "#12A4B8",
    }
    SKIP = {"source", "item_limit", "background", "design"}  # compound / data controls: covered by their own tests

    def _alternative(self, field, current):
        if field.key in ("desktop_columns", "tablet_columns", "mobile_columns"):
            return min(field.max_value, (current or 2) + 1) if (current or 2) < field.max_value else field.max_value - 1
        if field.field_type == "choice":
            return next(value for value, _label in field.choices if value != current)
        if field.field_type == "media":
            return MediaAsset.objects.create(store=self.store, image=_png(f"{field.key}.png")).pk
        return self.ALTERNATIVES[field.field_type](current)

    def test_every_visible_control_changes_the_render(self):
        for mode in ("carousel", "grid", "campaign_band", "catalog_grid"):
            self.assertEqual(self._patch({"display_mode": mode, "carousel_autoplay": False}).status_code, 200)
            self.band.refresh_from_db()
            base_settings = dict(self.band.settings)
            fields = section_registry.PRODUCT_SECTION_SCHEMA.fields
            responsive = base_settings.get("responsive") or {}
            values = {f.key: base_settings.get(f.key, responsive.get(f.key, f.default)) for f in fields}
            visible = settings_schema.compute_field_visibility(fields, values)
            dead = []
            for field in fields:
                if field.key in self.SKIP or field.key == "display_mode" or not visible[field.key]:
                    continue
                if field.key == "carousel_autoplay" and mode != "carousel":
                    continue
                baseline = _norm(self._fragment({})["fragment"]["html"])
                new_value = self._alternative(field, values[field.key])
                response = self._post_json({"base_revision": self._refresh_revision(), "fragment": True, "mutation": {
                    "type": "section.update_settings", "section_id": self.band.pk, "patch": {field.key: new_value}}})
                self.assertEqual(response.status_code, 200, (mode, field.key, new_value, response.content))
                changed = _norm(response.json()["fragment"]["html"])
                if changed == baseline:
                    dead.append(field.key)
                # restore the baseline for the next control
                self.band.settings = dict(base_settings)
                self.band.save()
            self.assertEqual(dead, [], f"{mode}: visible controls with no effect: {dead}")

    def test_every_design_property_and_panel_variable_has_a_css_consumer(self):
        from apps.storefront_builder import design_block

        for prop_key in design_block.applicable_properties("product_section"):
            prop = design_block.DESIGN_PROPERTIES[prop_key]
            attrs = design_block.render_attributes({prop.key: "token:accent" if prop.kind == "color" else (
                prop.choices[1][0] if prop.kind == "choice" else max(prop.min_value, 1))})
            produced = (attrs["flags"] + " " + attrs["style"]).strip()
            if not produced and prop.key.startswith("hide_"):
                continue  # responsive visibility is wired through data-hide-* attributes (own test)
            self.assertTrue(produced, prop.key)
            for var in re.findall(r"(--d-[\w-]+):", attrs["style"]):
                self.assertIn(f"var({var}", BUILDER_CSS, f"{prop.key}: {var} has no consumer")


class ExistingPanelCopyIsUnchangedForLegacySectionsTests(_CampaignBase):
    def test_default_markup_keeps_the_historical_panel_when_nothing_was_customised(self):
        self.band.refresh_from_db()
        settings_without_panel = {k: v for k, v in self.band.settings.items() if not k.startswith("campaign_")}
        settings_without_panel.update(title="تیتر", subtitle="توضیح")
        self.band.settings = settings_without_panel
        self.band.save()
        panel = self._panel()
        self.assertIn("product-campaign-gift", panel)
        self.assertIn(str(icon_registry.icon_svg("gift"))[:200], panel)
        self.assertIn("<h2>تیتر</h2>", panel)
        self.assertIn("<p>توضیح</p>", panel)


class DesignControlsOfferedOnlyWhereTheyActTests(_CampaignBase):
    def _design_rows(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        rows = {}
        for match in re.finditer(r'<div class="r4-design-prop" data-r4-design-prop="(\w+)"([^>]*)>', html):
            rows[match.group(1)] = " hidden" in match.group(2)
        return rows

    def test_carousel_item_width_is_not_offered_for_other_display_types(self):
        for mode, hidden in (("carousel", False), ("grid", True), ("campaign_band", True), ("catalog_grid", True)):
            self.assertEqual(self._patch({"display_mode": mode, "background": {"mode": "palette", "palette_role": "tone-1"}}).status_code, 200)
            self.assertEqual(self._design_rows()["item_width"], hidden, mode)
        self.assertIn("data-r4-design-modes", EDITOR_JS)

    def test_box_styling_is_not_offered_for_an_edge_to_edge_background(self):
        box = ("radius", "border_width", "border_color", "shadow", "shadow_color", "shadow_blur")
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-1", "bleed": True}}).status_code, 200)
        rows = self._design_rows()
        self.assertTrue(all(rows[key] for key in box), rows)
        self.assertFalse(rows["padding_top"])
        self.assertEqual(self._patch({"background": {"mode": "palette", "palette_role": "tone-1", "bleed": False}}).status_code, 200)
        rows = self._design_rows()
        self.assertFalse(any(rows[key] for key in box), rows)
        self.assertIn("function applyDesignBoxVisibility(bleed)", EDITOR_JS)

    def test_design_overrides_beat_card_style_defaults_in_the_css(self):
        for needle in (
            '.rsec[data-d~="price"] .pcard :is(.price .now,.price .now *){color:var(--d-price)!important}',
            '.rsec[data-d~="fit"] .pcard .img :is(img.cover-photo,img.cover-photo-2){object-fit:var(--d-fit)!important}',
            ".rsec.rsec[data-d~=\"text\"]{color:var(--d-text)}",
            "color:var(--d-heading,var(--sfb-section-fg,#fff))!important",
            "justify-content:var(--d-align,flex-start)",
        ):
            self.assertIn(needle, BUILDER_CSS)

    def test_design_overrides_reach_every_background_band_and_the_campaign_box(self):
        for needle in (
            '.rsec[data-d~="heading"][data-bg-mode]:not([data-pattern])>.section>.sec-head h2{color:var(--d-heading)!important}',
            '.rsec[data-bg-mode="image"][data-d~="heading"]>.section>.sec-head h2{color:var(--d-heading)}',
            ".rsec:has(.product-section--campaign-band) .product-campaign-heading h2{color:var(--d-heading,var(--brand-text))!important",
            ".rsec.rsec[data-d~=\"radius\"] .product-campaign-band{border-radius:var(--d-radius)}",
            ".rsec.rsec[data-d~=\"shadow\"] .product-campaign-band{box-shadow:var(--d-shadow)}",
            ".rsec.rsec[data-d~=\"surface\"]:has(.product-campaign-band) .product-campaign-band{background:var(--d-surface)",
            "border-radius:var(--d-radius,0)}",
            '.rsec[data-d~="surface"][data-bg-mode="color"]:not(:has(.product-campaign-band)){background-color:var(--d-surface)!important}',
            '.rsec[data-d~="ratio"] .pcard .img,.rsec[data-d~="ratio"] .blog-card .th{aspect-ratio:var(--d-ratio)!important}',
        ):
            self.assertIn(needle, BUILDER_CSS)
