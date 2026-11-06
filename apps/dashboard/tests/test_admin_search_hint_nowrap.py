"""The Merchant Admin header search shows its shortcut ("Ctrl K"). It is one key combination: it must stay on a single line (it used to wrap to "Ctrl" / "K", 35x38px)."""

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/css/admin_v2.css").read_text(encoding="utf-8")


class AdminSearchHintTests(SimpleTestCase):
    def test_the_shortcut_hint_cannot_wrap_or_shrink(self):
        rule = re.search(r"\.search-box \.admin-v2-kbd\s*\{([^}]*)\}", CSS).group(1)
        self.assertIn("white-space:nowrap", rule.replace(" ", ""))
        self.assertIn("flex:0 0 auto", rule)

    def test_the_stylesheet_is_versioned_so_the_fix_is_not_served_stale(self):
        base = (ROOT / "templates/dashboard/base_admin.html").read_text(encoding="utf-8")
        self.assertRegex(base, r"admin_v2\.css' %\}\?v=")
