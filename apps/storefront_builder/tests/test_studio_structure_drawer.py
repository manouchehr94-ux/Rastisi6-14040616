"""Studio layout: no permanently docked right panel — the page structure is an ON-DEMAND floating drawer.

Owner decision: with every overlay closed the storefront Preview must use the whole Design Studio workspace. The page-structure
list (and Global Design / the template peek, which shared that column) is a temporary drawer that floats above the Studio
(``position:fixed``), is closed by default, never consumes layout width and is mutually exclusive with the large settings
workspace. Real-browser delta-0 measurements (A none / B drawer / C workspace at 1920, 1440, 1280, 1024, 390) live in
``test_engine_parity_browser.py`` (opt-in); this module pins the static contract and the markup."""

import re
from pathlib import Path

from django.urls import reverse

from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
STUDIO_CSS = (STATIC / "r4_studio.css").read_text(encoding="utf-8")


class StructureDrawerMarkupTests(_BandBase):
    def _editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()

    def test_the_panel_is_closed_by_default_and_is_a_drawer(self):
        html = self._editor()
        panel = html[html.index('id="rsStructureDrawer"'):][:260]
        self.assertNotIn("panel-visible", panel)                      # nothing open on load
        self.assertIn('role="complementary"', panel)
        self.assertIn("panelVisible: false", STUDIO_JS)               # UI state default
        self.assertIn('id="rsStructureDrawer"', html)
        self.assertIn('data-rastisi-action="panel-close"', html[html.index('id="rsStructureDrawer"'):])
        self.assertIn("ساختار صفحه", html)

    def test_top_level_navigation_is_obvious_and_not_duplicated(self):
        html = self._editor()
        nav = html[html.index('class="top-nav"'):html.index("</nav>", html.index('class="top-nav"'))]
        actions = re.findall(r'data-rastisi-action="([a-z-]+)"', nav)
        self.assertEqual(actions[:4], ["structure", "section-settings", "templates", "global"])
        for label in ("ساختار صفحه", "تنظیمات بخش", "قالب‌ها", "طراحی سراسری"):
            self.assertIn(f'<span class="nav-label">{label}</span>', nav)
        # public preview and publish stay in the project bar
        self.assertIn('data-rastisi-action="public-preview"', html)
        self.assertIn('id="r4PublishButton"', html)
        # the old duplicate openers are gone: no stage-toolbar «قالب‌ها» and no mobile-only panel toggle
        self.assertNotIn('data-rastisi-action="panel-toggle"', html)
        stage = html[html.index('class="stage-toolbar"'):html.index('class="canvas"')]
        self.assertNotIn('data-rastisi-action="templates"', stage)

    def test_structure_rows_expose_select_settings_and_every_quick_action(self):
        html = self._editor()
        row = html[html.index("data-r4-structure-row"):html.index("data-r4-structure-row") + 6000]
        for hook in ('data-rastisi-action="row-select"', 'class="r4-structure-label rs-row-settings"', 'data-r4-structure-move="up"',
                     'data-r4-structure-move="down"', "data-r4-structure-toggle-active", "data-r4-structure-toggle-locked",
                     "data-r4-structure-duplicate", "data-r4-structure-remove"):
            self.assertIn(hook, row)
        # the first row cannot move up, the last cannot move down
        rows = html.split("data-r4-structure-row ")[1:]
        self.assertIn("disabled", re.search(r'data-r4-structure-move="up"[^>]*>', rows[0]).group(0))
        last = re.findall(r'data-r4-structure-move="down"[^>]*>', rows[-1])[0]
        self.assertIn("disabled", last)
        self.assertIn('data-rastisi-action="add-section"', html)
        self.assertIn("data-rs-structure-search", html)

    def test_selecting_a_row_is_not_opening_settings(self):
        # the row label only selects (studio action); the gear is the one control that goes through R4.openSection
        self.assertIn("case 'row-select'", STUDIO_JS)
        self.assertIn("R4.previewSelect", STUDIO_JS)
        self.assertIn("R4.previewSelect = function", EDITOR_JS)
        self.assertNotIn(".scrollIntoView(", EDITOR_JS[EDITOR_JS.index("R4.previewSelect = function"):EDITOR_JS.index("R4.openSection = function")])


class StructureDrawerContractTests(_BandBase):
    def test_the_studio_grid_is_one_column_and_the_drawer_floats(self):
        grid = re.findall(r"\.rs-studio \.studio-layout\{[^}]*grid-template-columns:([^;}]*)", STUDIO_CSS)
        self.assertEqual(grid[-1].strip(), "minmax(0,1fr)")           # the last word: a single full-width column
        panel = [m for m in re.findall(r"\.rs-studio \.context-panel\{([^}]*)\}", STUDIO_CSS) if "position:fixed" in m][-1]
        self.assertIn("position:fixed", panel)
        self.assertIn("display:none", panel)                           # closed unless .panel-visible
        self.assertRegex(panel, r"width:min\(400px,92vw\)")           # 360–420px on desktop
        self.assertIn("z-index:30", panel)                             # under the workspace (40) / dialogs (50)
        self.assertIn(".rs-studio .context-panel.panel-visible{display:flex}", STUDIO_CSS)

    def test_drawer_and_workspace_are_mutually_exclusive(self):
        opened = STUDIO_JS[STUDIO_JS.index("root.addEventListener('r4:inspector-opened'"):]
        opened = opened[:opened.index("});")]
        self.assertIn("ui.panelVisible = false", opened)               # opening settings closes the drawer
        closed = STUDIO_JS[STUDIO_JS.index("root.addEventListener('r4:inspector-closed'"):]
        closed = closed[:closed.index("});")]
        self.assertIn("ui.panelVisible = false", closed)               # closing settings = full canvas, no drawer
        self.assertIn("if (R4.inspectorOpen) R4.closeInspector();", STUDIO_JS)   # opening the drawer closes settings
        # the visible drawer is gated on the mode too
        self.assertIn("ui.panelVisible && !contextPanel.hidden && ui.mode !== 'inspector'", STUDIO_JS)

    def test_escape_and_focus_return_for_the_drawer(self):
        self.assertIn("ui.panelVisible && ui.mode !== 'inspector' && ui.mode !== 'lab'", STUDIO_JS)
        self.assertIn("drawerReturnFocus", STUDIO_JS)
        self.assertIn("function closeDrawer", STUDIO_JS)
        # the workspace falls back to the top-bar button when its opener lived inside the closed drawer
        self.assertIn('.top-nav [data-rastisi-action="section-settings"]', STUDIO_JS)

    def test_section_settings_button_reopens_the_selected_section_or_guides_the_owner(self):
        case = STUDIO_JS[STUDIO_JS.index("case 'section-settings':"):STUDIO_JS.index("case 'row-select'")]
        self.assertIn("R4.openSection(Number(ui.selectedSectionId))", case)
        self.assertIn("setMode('structure', { drawer: true })", case)

    def test_partial_refresh_pipeline_is_untouched(self):
        self.assertIn("var FRAGMENT_MUTATIONS = { 'section.update_settings': 'section_id', 'container.update_settings': 'container_id' };", EDITOR_JS)
        self.assertEqual(EDITOR_JS.count("function swapFragmentIn"), 1)
        self.assertIn("applyPreviewFragment(result.body.fragment)", EDITOR_JS)


class StructureDrawerRefinementTests(_BandBase):
    def test_backdrop_is_very_subtle_fixed_and_closes_the_drawer(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn('class="rs-drawer-backdrop" data-rastisi-action="panel-close"', html)
        rule = re.search(r"\.rs-studio \.rs-drawer-backdrop\{([^}]*)\}", STUDIO_CSS).group(1)
        self.assertIn("position:fixed", rule)
        self.assertRegex(rule, r"background:#14201a14")      # ~8 % tint
        self.assertIn('data-rs-drawer="structure"] .rs-drawer-backdrop', STUDIO_CSS)
        # elevation is clearly stronger than before and the drawer width stays 380–420 px
        panel = [m for m in re.findall(r"\.rs-studio \.context-panel\{([^}]*)\}", STUDIO_CSS) if "position:fixed" in m][-1]
        self.assertIn("box-shadow:-26px 0 72px", panel)
        self.assertIn("width:min(400px,92vw)", panel)
