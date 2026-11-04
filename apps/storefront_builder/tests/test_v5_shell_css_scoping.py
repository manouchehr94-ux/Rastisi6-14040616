"""V5-02A-R1: the shell layer is appended to r4_studio.css, scoped to .rs-studio, honours the token/disabled contracts and
matches the V5 reference geometry (70px bar, 92px rail, reference colours; the reference's own ≤800px values below that)."""

import re
import unittest

from ._v5_shell_support import STUDIO_CSS, V5_MARKER, declarations, parse_rules, strip_comments, v5_layer

NARROW = "@media (max-width:800px)"


class V5ShellCssScopingTests(unittest.TestCase):
    def setUp(self):
        self.rules = parse_rules(v5_layer())

    def test_layer_is_present_once_and_is_the_last_layer(self):
        self.assertEqual(STUDIO_CSS.count(V5_MARKER), 1)
        self.assertGreater(len(self.rules), 60)

    def test_every_selector_is_scoped_under_rs_studio(self):
        for _media, selectors, _decls in self.rules:
            for sel in (s.strip() for s in selectors.split(",")):
                self.assertTrue(sel.startswith(".rs-studio"), f"unscoped selector in V5 layer: {sel!r}")

    def test_layer_declares_no_custom_properties_and_no_important(self):
        body = strip_comments(v5_layer())
        self.assertIsNone(re.search(r"(^|[;{\s])--[a-z0-9-]+\s*:", body), "V5 layer must not declare custom properties (token contract)")
        for forbidden in ("!important", "url(", "@import", "r4-cp-"):
            self.assertNotIn(forbidden, body)

    def test_disabled_states_never_use_element_opacity(self):
        for _media, selectors, decls in self.rules:
            if ":disabled" in selectors or "[disabled" in selectors or "aria-disabled" in selectors:
                self.assertNotRegex(decls, r"(^|;)\s*opacity\s*:", f"opacity on disabled selector {selectors!r}")

    def test_pinned_studio_layout_column_rule_is_not_extended(self):
        # test_studio_structure_drawer / test_settings_workspace read the LAST grid-template-columns of `.rs-studio .studio-layout{}`
        self.assertEqual(re.findall(r"\.rs-studio \.studio-layout\{[^}]*grid-template-columns", v5_layer()), [])
        all_rules = re.findall(r"\.rs-studio \.studio-layout\{[^}]*grid-template-columns:([^;}]*)", STUDIO_CSS)
        self.assertEqual(all_rules[-1].strip(), "minmax(0,1fr)")

    # ---- reference geometry (RastiSi_Studio_V5.html: .top 70px/#151a25, .tools 92px/#191f2c, accent #94edc4) ----------------------
    def test_desktop_bar_and_rail_match_the_reference(self):
        bar = declarations(self.rules, ".rs-studio .app-top")
        self.assertIn("height:70px", bar)
        self.assertIn("min-height:70px", bar)
        self.assertIn("background:#151a25", bar)
        rail = declarations(self.rules, ".rs-studio .rs-rail")
        self.assertIn("width:92px", rail)
        self.assertIn("flex:0 0 92px", rail)
        self.assertIn("box-sizing:border-box", rail)
        self.assertIn("background:#191f2c", rail)
        tool = declarations(self.rules, ".rs-studio .rs-rail .rail-btn")
        self.assertIn("width:76px", tool)
        self.assertIn("min-height:69px", tool)
        self.assertIn("#94edc4", v5_layer())

    def test_narrow_values_come_from_the_reference_800px_breakpoint(self):
        self.assertIn("height:65px", declarations(self.rules, ".rs-studio .app-top", NARROW))
        self.assertIn("width:67px", declarations(self.rules, ".rs-studio .rs-rail", NARROW))
        self.assertIn("width:57px", declarations(self.rules, ".rs-studio .rs-rail .rail-btn", NARROW))

    def test_drawer_and_backdrop_anchor_to_the_bar_and_rail_at_every_width(self):
        for selector in (".rs-studio .context-panel", ".rs-studio .rs-drawer-backdrop"):
            decls = declarations(self.rules, selector)
            self.assertIn("top:70px", decls)
            self.assertIn("right:92px", decls)
            narrow = declarations(self.rules, selector, NARROW)
            self.assertIn("top:65px", narrow)
            self.assertIn("right:67px", narrow)

    def test_the_rail_and_its_tools_are_never_hidden_by_any_media_query(self):
        for media, selectors, decls in self.rules:
            names = [s.strip() for s in selectors.split(",")]
            if ".rs-studio .rs-rail" in names or ".rs-studio .rs-rail .rail-btn" in names:
                self.assertNotRegex(decls, r"display\s*:\s*none", f"rail hidden in {media}")
                self.assertNotRegex(decls, r"visibility\s*:\s*hidden", f"rail hidden in {media}")

    def test_the_primary_publish_and_undo_controls_are_never_hidden(self):
        # the header may drop labels / secondary text on narrow screens, never the controls that carry data hooks
        for media, selectors, decls in self.rules:
            if re.search(r"display\s*:\s*none", decls):
                for hidden in (".rs-studio .app-top .project-actions .primary", ".rs-studio .app-top .history-buttons",
                               ".rs-studio .app-top .project-actions", ".rs-studio .app-top .top-nav", ".rs-studio .app-top .top-nav button"):
                    self.assertNotIn(hidden, [s.strip() for s in selectors.split(",")], f"{hidden} hidden in {media}")


if __name__ == "__main__":
    unittest.main()
