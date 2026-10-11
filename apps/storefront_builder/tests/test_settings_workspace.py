"""The section settings WORKSPACE — the large overlay that replaced the permanently docked right Inspector.

Owner UX correction: opening a section's settings must launch ONE large, premium workspace overlay on every device
(desktop 86–94vw x 86–92vh capped at ~1550px; a full-screen sheet on a phone), never a narrow modal and never a sidebar that
squeezes the Preview. Pinned here:

* structure — three primary tabs (محتوا / طراحی / پیشرفته), each a two-column set of titled cards, arranged from field TYPE +
  KEY by ``workspace_layout`` (generic: no section-key / template-key branch), every schema field exactly once;
* the overlay is ``position:fixed`` above the Studio and the settings form no longer lives in the right-edge panel, so the
  Preview column can never change width (the real-browser delta-0 measurement is in ``test_engine_parity_browser.py``);
* the optional live view is the SAME canonical server-rendered page / fragment — no second rendering authority;
* the mutation pipeline, schema validation and ``visible_when`` rules are untouched."""

import re
from pathlib import Path

from django.urls import reverse

from apps.storefront_builder import section_registry, workspace_layout

from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
STUDIO_CSS = (STATIC / "r4_studio.css").read_text(encoding="utf-8")
LAYOUT_SOURCE = (APP / "workspace_layout.py").read_text(encoding="utf-8")


def _panel(html, name):
    start = html.index(f'data-r4-tab-panel="{name}"')
    ends = [e for e in (html.find('data-r4-tab-panel="', start + 10), html.find('<footer class="r4-ws-footer"', start)) if e != -1]
    return html[start:min(ends)]


# --------------------------------------------------------------------------------------------- the arrangement engine
class WorkspaceLayoutEngineTests(_BandBase):
    def test_every_schema_field_lands_in_exactly_one_card_for_every_section(self):
        checked = 0
        for key, definition in section_registry.SECTION_REGISTRY.items():
            schema = definition.settings_schema
            if schema is None:
                continue
            tabs = workspace_layout.build_workspace_tabs(schema.fields, has_media_manager=False)
            assert [t.key for t in tabs] == ["content", "design", "advanced"], key
            placed = [f.key for tab in tabs for card in tab.cards for f in card.fields]
            self.assertEqual(sorted(placed), sorted(f.key for f in schema.fields), f"{key}: a field was dropped or duplicated")
            self.assertEqual(len(placed), len(set(placed)), key)
            checked += 1
        self.assertGreater(checked, 20)

    def test_arrangement_is_generic_not_keyed_to_a_section_or_template(self):
        for forbidden in ("section_key", "template_key", "preset", "stationery", "product_section", "hero_banner"):
            self.assertNotIn(forbidden, LAYOUT_SOURCE, f"workspace_layout must stay generic ({forbidden})")

    def test_product_section_design_tab_has_the_owner_groups(self):
        schema = section_registry.SECTION_REGISTRY["product_section"].settings_schema
        tabs = {t.key: t for t in workspace_layout.build_workspace_tabs(schema.fields)}
        design = {c.key: [f.key for f in c.fields] for c in tabs["design"].cards}
        # main column: background, product-card style; side column: layout, campaign panel, spacing
        self.assertEqual([c.key for c in tabs["design"].main], ["background", "style"])
        self.assertEqual([c.key for c in tabs["design"].side], ["layout", "campaign", "spacing"])
        self.assertEqual(design["background"], ["background"])
        self.assertEqual(design["style"], ["design"])
        self.assertIn("desktop_columns", design["layout"])
        self.assertIn("heading_style", design["layout"])
        self.assertEqual(design["spacing"], ["gap"])
        self.assertTrue(all(k.startswith("campaign_") for k in design["campaign"]))
        self.assertEqual(len(design["campaign"]), 16)
        content = {c.key: [f.key for f in c.fields] for c in tabs["content"].cards}
        self.assertEqual(content["text"], ["title"])
        self.assertIn("display_mode", content["source"])
        self.assertIn("source", content["source"])
        # motion/behaviour and section management are Advanced
        self.assertIn("behavior", {c.key for c in tabs["advanced"].cards})
        self.assertTrue(any(c.is_manage for c in tabs["advanced"].cards))

    def test_schema_group_is_respected_for_behaviour_keys(self):
        # ``autoplay`` is a *basic* hero field (the schema author put it in the main group): it stays in Content.
        schema = section_registry.SECTION_REGISTRY["hero_banner"].settings_schema
        tabs = {t.key: t for t in workspace_layout.build_workspace_tabs(schema.fields)}
        self.assertIn("autoplay", [f.key for c in tabs["content"].cards for f in c.fields])
        self.assertIn("interval_ms", [f.key for c in tabs["advanced"].cards for f in c.fields])


# --------------------------------------------------------------------------------------------- the rendered workspace
class WorkspaceMarkupTests(_BandBase):
    def _inspector(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk])).content.decode()

    def test_inspector_is_a_workspace_with_header_tabs_two_columns_and_footer(self):
        html = self._inspector()
        for needle in ("r4-ws-header", "data-rs-inspector-title", "data-rs-inspector-scope", "data-r4-ws-search",
                       "data-r4-ws-save", "data-r4-inspector-close", 'role="tablist"', "r4-ws-footer", "r4-ws-cols",
                       "r4-ws-col--main", "r4-ws-col--side"):
            self.assertIn(needle, html)
        self.assertEqual(html.count('role="tab"'), 3)
        for label in ("محتوا", "طراحی", "پیشرفته"):
            self.assertIn(f">{label}<", html.replace('<span class="r4-ws-tab-count" data-r4-ws-tab-count hidden></span>', ""))
        # only the Content panel starts visible
        def opening_tag(name):
            at = html.index(f'data-r4-tab-panel="{name}"')
            return html[html.rindex("<section", 0, at):html.index(">", at)]
        self.assertIn(" hidden", opening_tag("design"))
        self.assertIn(" hidden", opening_tag("advanced"))
        self.assertNotIn(" hidden", opening_tag("content"))

    def test_design_tab_shows_the_owner_groups_in_two_columns(self):
        design = _panel(self._inspector(), "design")
        order = [design.index(f'data-r4-ws-card="{k}"') for k in ("background", "style", "layout", "campaign", "spacing")]
        self.assertEqual(order, sorted(order))
        self.assertLess(design.index("r4-ws-col--main"), design.index("r4-ws-col--side"))
        for label in ("پس‌زمینه", "ظاهر و استایل", "چیدمان", "پنل کمپین", "فاصله‌ها"):
            self.assertIn(f"<h3>{label}</h3>", design)

    def test_every_control_is_still_the_schema_driven_field_renderer(self):
        html = self._inspector()
        schema = section_registry.SECTION_REGISTRY["product_section"].settings_schema
        for field in schema.fields:
            self.assertEqual(html.count(f'data-r4-field-row data-r4-field-key="{field.key}"'), 1, field.key)

    def test_advanced_tab_hosts_section_management_and_conditional_cards_are_hidable(self):
        html = self._inspector()
        advanced = _panel(html, "advanced")
        self.assertIn("data-r4-ws-manage", advanced)
        self.assertIn("data-rs-section-actions", advanced)
        # the engine hides a card whose every control is dormant (visible_when): the hook exists in the editor script
        self.assertIn("function syncWorkspaceCards", EDITOR_JS)
        self.assertIn("syncWorkspaceCards();", EDITOR_JS)

    def test_workspace_search_never_touches_the_visible_when_hidden_state(self):
        self.assertIn("ws-filtered-out", STUDIO_JS)
        self.assertIn("!row.hidden", STUDIO_JS)   # a dormant (hidden) row is never reported as a search hit


class WorkspaceShellTests(_BandBase):
    def _editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()

    def test_form_lives_in_the_overlay_not_in_the_right_edge_panel(self):
        html = self._editor()
        overlay_start = html.index("data-rs-workspace")
        overlay = html[overlay_start:]
        self.assertIn('id="r4Inspector"', overlay)
        panel = html[html.index("data-rs-context-panel"):overlay_start]
        self.assertNotIn('id="r4Inspector"', panel)
        self.assertNotIn('data-rs-view="inspector"', html)
        self.assertIn('role="dialog"', overlay)
        self.assertIn('aria-modal="true"', overlay)
        self.assertIn("workspace-backdrop", html)

    def test_the_overlay_sits_above_the_studio_and_takes_no_layout_width(self):
        css = STUDIO_CSS
        match = re.search(r"\.rs-studio \.rs-workspace\{[^}]*\}", css)
        self.assertIsNotNone(match)
        self.assertIn("position:fixed", match.group(0))
        self.assertIn("inset:0", match.group(0))
        dialog = re.search(r"\.rs-studio \.rs-workspace-dialog\{[^}]*\}", css, re.S).group(0)
        self.assertIn("min(92vw,1520px)", dialog)      # 86–94vw, capped inside ~1400–1550px
        self.assertIn("min(90vh", dialog)              # 86–92vh
        self.assertIn("overflow:hidden", dialog)
        body = re.search(r"\.rs-studio \.r4-ws-body\{[^}]*\}", css).group(0)
        self.assertIn("overflow-y:auto", body)          # internal scrolling only
        # phone: the SAME workspace becomes full-screen
        self.assertRegex(css, r"@media \(max-width:850px\)\{[^@]*\.rs-workspace-dialog\{width:100vw;height:100vh;height:100dvh;border-radius:0")
        # z-order: workspace under dialogs (50) and the resource picker (60)
        self.assertIn("z-index:40", match.group(0))

    def test_opening_settings_never_changes_the_studio_grid(self):
        # the right edge is a floating drawer (see test_studio_structure_drawer): the Studio grid is ONE column in every state
        grid = re.findall(r"\.rs-studio \.studio-layout\{[^}]*grid-template-columns:([^;}]*)", STUDIO_CSS)
        self.assertEqual(grid[-1].strip(), "minmax(0,1fr)")
        self.assertNotIn("data-r4-inspector-open", STUDIO_CSS.replace("body:has(.rs-studio[data-r4-sidebar-expanded", ""))
        # the Studio handles Escape / focus return / focus trap for the overlay
        for needle in ("trapWorkspaceFocus", "workspaceReturnFocus", "R4.closeInspector()"):
            self.assertIn(needle, STUDIO_JS)

    def test_live_view_reuses_the_canonical_fragment_and_page(self):
        # one swap routine serves BOTH frames; the live frame is the same draft preview URL — no JS storefront renderer
        self.assertEqual(EDITOR_JS.count("function swapFragmentIn"), 1)
        self.assertIn("swapFragmentIn(live.frame, fragment)", EDITOR_JS)
        self.assertIn("swapFragmentIn(previewFrame, fragment)", EDITOR_JS)
        self.assertIn("data-rs-draft-src", EDITOR_JS)
        self.assertIn("reloadLive();", EDITOR_JS)     # a full refresh of the main Preview refreshes the live view too
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn("data-r4-ws-live", html)
        # the live column is a SIBLING of the Inspector body, so a re-rendered Inspector never reloads the frame
        self.assertLess(html.index('id="r4Inspector"'), html.index("data-r4-ws-live"))

    def test_the_last_used_tab_is_remembered_across_sections(self):
        self.assertIn("lastWorkspaceTab", EDITOR_JS)
        self.assertNotIn("activateTab('basic')", EDITOR_JS)


class WorkspaceRefinementTests(_BandBase):
    def _inspector(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[self.band.pk])).content.decode()

    def test_footer_copy_and_save_feedback(self):
        html = self._inspector()
        footer = html[html.index('<footer class="r4-ws-footer"'):]
        self.assertIn("انجام شد</button>", footer)
        self.assertIn("تغییرات به‌صورت خودکار ذخیره می‌شوند", footer)
        self.assertNotIn("تمام؛ بازگشت به صفحه", html)
        self.assertIn("data-r4-ws-save", html)             # save-state feedback stays (subtle, in the header)

    def test_header_tabs_and_live_column_stay_put_and_columns_stack_naturally(self):
        css = STUDIO_CSS
        self.assertRegex(css, r"\.rs-studio \.r4-ws-live\{[^}]*position:sticky;top:0")
        self.assertRegex(css, r"\.rs-studio \.r4-ws-live-stage\{[^}]*flex:0 1 auto")     # natural height, no big empty stage
        cols = re.search(r"\.rs-studio \.r4-ws-cols\{([^}]*)\}", css).group(1)
        self.assertIn("align-items:start", cols)                                           # columns are NOT stretched to equal heights
        # only the body scrolls; header + tabs + footer are fixed flex rows of the workspace
        self.assertIn("overflow-y:auto", re.search(r"\.rs-studio \.r4-ws-body\{([^}]*)\}", css).group(1))
        self.assertIn("flex:0 0 auto", re.search(r"\.rs-studio \.r4-ws-tabs\{([^}]*)\}", css).group(1))

    def test_live_frame_is_display_only_with_a_subtle_selection_ring(self):
        block = EDITOR_JS[EDITOR_JS.index("function focusLive()"):EDITOR_JS.index("function closeLive()")]
        for hidden in (".sfb-rsec-toolbar", ".sfb-rsec-drag-handle", ".sfb-rcontainer-toolbar", ".sfb-cell-add-more"):
            self.assertIn(hidden, block)
        self.assertIn("body{pointer-events:none!important}", block)
        self.assertIn("outline:2px solid rgba(44,98,81,.34)", block)
