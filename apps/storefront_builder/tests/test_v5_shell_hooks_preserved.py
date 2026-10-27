"""V5-02A: the restructured Studio shell keeps every id / data hook / pinned literal the engine and existing tests rely on."""

import re
import unittest

from ._v5_shell_support import EDITOR_HTML

REQUIRED_IDS = (
    "r4PageSwitcher", "r4PageSwitcherSelect", "r4UndoButton", "r4RedoButton", "r4PublishButton", "r4SaveState",
    "r4GlobalDesignToggle", "r4SidebarToggle", "r4PreviewFrame", "r4Structure", "r4GlobalDesign", "r4Inspector",
    "rsStructureDrawer",
)
REQUIRED_HOOKS = (
    "data-r4-shell", "data-rs-mode", "data-rs-global-tab", "data-rs-device", "data-rs-draft-changed", "data-rs-has-published",
    "data-rs-status-pill", "data-rs-project-sub", "data-rs-save-feedback", "data-rs-public-url", "data-rs-scope-tag",
    "data-r4-device-switcher", "data-rs-device-width", "data-control=\"page\"", "data-control=\"zoom\"", "data-rs-view-controls",
    "data-rs-browser-url", "data-rs-browser-state", "data-rs-caption", "data-rs-caption-side", "data-rs-context-panel",
    "data-rastisi-panel=\"structure\"", "data-rs-view=\"structure\"", "data-rs-view=\"global\"", "data-rs-view=\"template-preview\"",
    "data-rs-workspace", "data-rs-workspace-dialog", "data-rs-modal-root", "data-rs-toast", "data-r4-ws-live",
)
PINNED_LITERALS = ('class="top-nav"', 'class="stage-toolbar"', 'class="canvas"', 'class="rs-app"', 'class="app-top"',
                   'class="project-actions"', 'class="history-buttons"', 'class="studio-layout"', 'class="context-panel"')


class V5ShellHooksPreservedTests(unittest.TestCase):
    def test_ids_exist_exactly_once(self):
        for ident in REQUIRED_IDS:
            self.assertEqual(len(re.findall(rf'\bid="{ident}"', EDITOR_HTML)), 1, ident)

    def test_data_hooks_and_pinned_literals_exist(self):
        for hook in REQUIRED_HOOKS:
            self.assertIn(hook, EDITOR_HTML, hook)
        for literal in PINNED_LITERALS:
            self.assertIn(literal, EDITOR_HTML, literal)

    def test_top_nav_order_and_labels_are_unchanged(self):
        nav = EDITOR_HTML[EDITOR_HTML.index('class="top-nav"'):EDITOR_HTML.index("</nav>")]
        self.assertEqual(re.findall(r'data-rastisi-action="([a-z-]+)"', nav)[:4], ["structure", "section-settings", "templates", "global"])
        for label in ("ساختار صفحه", "تنظیمات بخش", "قالب‌ها", "طراحی سراسری"):
            self.assertIn(f'<span class="nav-label">{label}</span>', nav)

    def test_stage_toolbar_has_no_templates_opener(self):
        stage = EDITOR_HTML[EDITOR_HTML.index('class="stage-toolbar"'):EDITOR_HTML.index('class="canvas"')]
        self.assertNotIn('data-rastisi-action="templates"', stage)

    def test_dom_order_is_the_visual_order(self):
        order = [EDITOR_HTML.index(token) for token in (
            '<header class="app-top">', '<aside class="rs-rail"', '<div class="rs-main">', '<div class="studio-layout">',
            'id="rsStructureDrawer"', '<div class="rs-float-bar"', "data-rs-workspace",
        )]
        self.assertEqual(order, sorted(order))

    def test_no_id_is_duplicated_in_the_template(self):
        ids = re.findall(r'\bid="([^"{]+)"', EDITOR_HTML)
        self.assertEqual(sorted(i for i in set(ids) if ids.count(i) > 1), [])

    def test_global_focus_targets_used_by_the_rail_are_handled_by_the_studio_script(self):
        from ._v5_shell_support import APP, STUDIO_JS

        rail = EDITOR_HTML[EDITOR_HTML.index('<aside class="rs-rail"'):EDITOR_HTML.index("</aside>", EDITOR_HTML.index('<aside class="rs-rail"'))]
        targets = set(re.findall(r'data-rs-global-focus="([a-z]+)"', rail))
        self.assertEqual(targets, {"header", "footer"})
        focus = STUDIO_JS[STUDIO_JS.index("function focusGlobalRegion"):][:600]
        self.assertIn("region === 'footer' ? 'rsGlobalFooter' : 'rsGlobalHeader'", focus)
        partial = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "studio_global_design.html").read_text(encoding="utf-8")
        for region_id in ("rsGlobalHeader", "rsGlobalFooter"):
            self.assertIn(f'id="{region_id}"', partial, region_id)

    def test_rail_and_drawer_live_inside_the_inert_app_container(self):
        app_open = EDITOR_HTML.index('<div class="rs-app">')
        workspace = EDITOR_HTML.index("data-rs-workspace")
        for token in ('<aside class="rs-rail"', 'id="rsStructureDrawer"', '<div class="rs-float-bar"'):
            self.assertTrue(app_open < EDITOR_HTML.index(token) < workspace, token)

    def test_script_and_style_asset_order_is_unchanged(self):
        css = [EDITOR_HTML.index(f"storefront_builder/{name}'") for name in ("r4_editor.css", "r4_studio.css", "r4_color_picker.css")]
        js = [EDITOR_HTML.index(f"storefront_builder/{name}'") for name in ("destination_picker.js", "r4_editor.js", "r4_color_picker.js", "r4_studio.js")]
        self.assertEqual(css, sorted(css))
        self.assertEqual(js, sorted(js))

    def test_helper_and_publish_controls_stay_in_the_top_bar(self):
        header = EDITOR_HTML[EDITOR_HTML.index('<header class="app-top">'):EDITOR_HTML.index("</header>")]
        for token in ('id="r4PublishButton"', 'id="r4UndoButton"', 'id="r4RedoButton"', 'data-rastisi-action="public-preview"',
                      'data-rastisi-action="history"', 'data-rastisi-action="help"', 'id="r4SidebarToggle"', "data-rs-status-pill"):
            self.assertIn(token, header, token)


if __name__ == "__main__":
    unittest.main()
