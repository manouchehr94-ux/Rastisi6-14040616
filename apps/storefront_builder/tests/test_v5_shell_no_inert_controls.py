"""V5-02A: every control the shell shows is wired — each data-rastisi-action in the Studio template has a handler."""

import re
import unittest

from ._v5_shell_support import EDITOR_HTML, EDITOR_JS, STUDIO_JS, rail_and_float_markup

#: Pre-existing controls owned by r4_editor.js (the single write/history/preview owner) rather than the r4_studio.js switch.
EDITOR_OWNED = {"undo": "undoButton", "redo": "redoButton", "device": "[data-r4-device]"}


class V5ShellNoInertControlsTests(unittest.TestCase):
    def test_every_template_action_has_a_studio_handler(self):
        actions = set(re.findall(r'data-rastisi-action="([a-z-]+)"', EDITOR_HTML))
        self.assertGreater(len(actions), 20)
        for action in sorted(actions):
            if action in EDITOR_OWNED:
                self.assertIn(EDITOR_OWNED[action], EDITOR_JS, action)
            else:
                self.assertRegex(STUDIO_JS, rf"case '{re.escape(action)}'", f"action {action!r} has no handler in r4_studio.js")

    def test_every_rail_and_float_button_is_a_real_button_with_label_and_action(self):
        markup = rail_and_float_markup()
        buttons = re.findall(r"<button\b[^>]*>.*?</button>", markup, flags=re.S)
        self.assertEqual(len(buttons), 10)                                 # 8 rail tools (incl. help) + 2 floating shortcuts
        for button in buttons:
            self.assertIn('type="button"', button)
            self.assertRegex(button, r'data-rastisi-action="[a-z-]+"')
            visible = re.sub(r"<svg.*?</svg>|<[^>]+>", "", button, flags=re.S).strip()
            self.assertTrue(visible or "aria-label=" in button, button)

    def test_rail_has_no_placeholder_for_blocked_features(self):
        markup = rail_and_float_markup()
        for blocked in ("سه بخشی", "ورود طرح", "بارگذاری طرح", "خروجی طرح", "disabled", "soon", "به‌زودی"):
            self.assertNotIn(blocked, markup, blocked)

    def test_help_and_every_tool_stay_reachable_when_the_header_collapses(self):
        # ≤560px hides .user-menu (help + avatar) and ≤1100px hides nav labels: the rail (never hidden, see css test) carries help,
        # structure, templates, global design, open-add-section and add-row; the top-nav (icon-only / scrollable) carries the rest.
        rail = EDITOR_HTML[EDITOR_HTML.index('<aside class="rs-rail"'):EDITOR_HTML.index("</aside>", EDITOR_HTML.index('<aside class="rs-rail"'))]
        nav = EDITOR_HTML[EDITOR_HTML.index('class="top-nav"'):EDITOR_HTML.index("</nav>")]
        reachable = set(re.findall(r'data-rastisi-action="([a-z-]+)"', rail + nav))
        self.assertGreaterEqual(reachable, {"help", "structure", "templates", "global", "open-add-section", "add-row", "section-settings"})
        for button in re.findall(r"<button\b[^>]*>", nav):
            self.assertIn("title=", button)          # icon-only on narrow screens: the accessible name must survive

    def test_icons_used_by_the_shell_exist(self):
        from apps.storefront_builder.studio_icons import STUDIO_ICON_PATHS  # pure-python module, no Django needed

        for name in set(re.findall(r'rs_icon "([a-z_]+)"', rail_and_float_markup())):
            self.assertIn(name, STUDIO_ICON_PATHS, name)


if __name__ == "__main__":
    unittest.main()
