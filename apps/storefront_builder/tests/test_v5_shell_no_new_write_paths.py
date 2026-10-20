"""V5-02A: the shell redesign is presentation only — no form, request, storage or script was added to the Studio template,
and the rail / floating bar can only fire existing Studio actions."""

import re
import unittest

from ._v5_shell_support import EDITOR_HTML, STUDIO_JS, rail_and_float_markup, v5_layer

#: Studio actions the rail and the floating bar are allowed to trigger (all pre-existing).
ALLOWED_SHELL_ACTIONS = {"add-section", "add-row", "global", "structure", "templates", "help"}


class V5ShellNoNewWritePathsTests(unittest.TestCase):
    def test_rail_and_float_bar_only_use_existing_ui_actions(self):
        markup = rail_and_float_markup()
        actions = set(re.findall(r'data-rastisi-action="([a-z-]+)"', markup))
        self.assertTrue(actions)
        self.assertLessEqual(actions, ALLOWED_SHELL_ACTIONS)
        for action in actions:
            self.assertIn(f"case '{action}'", STUDIO_JS, action)

    def test_shell_markup_has_no_forms_links_handlers_or_requests(self):
        markup = rail_and_float_markup()
        for forbidden in ("<form", "<a ", "href=", "onclick", "fetch(", "XMLHttpRequest", "csrf", "hx-", "action=\"/"):
            self.assertFalse(forbidden in markup, forbidden)

    def test_template_gained_no_inline_script_or_form(self):
        self.assertEqual(len(re.findall(r"<script\b", EDITOR_HTML)), 4)          # the four asset scripts; data is json_script tags
        self.assertNotIn("<form", EDITOR_HTML)

    def test_v5_layer_has_no_behaviour(self):
        layer = v5_layer()
        for forbidden in ("@import", "url(", "expression(", "javascript:"):
            self.assertNotIn(forbidden, layer)

    def test_studio_script_still_never_writes_or_stores(self):
        for forbidden in ("new XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "method: 'POST'", 'method: "POST"', "FormData("):
            self.assertFalse(forbidden in STUDIO_JS, forbidden)
        # the single pre-existing fetch is the read-only GET of the current page
        self.assertEqual(STUDIO_JS.count("fetch("), 1)
        self.assertIn("fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })", STUDIO_JS)


if __name__ == "__main__":
    unittest.main()
