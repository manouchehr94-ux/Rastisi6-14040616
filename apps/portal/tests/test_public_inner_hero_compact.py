"""Internal public pages (design, features, plans, about, contact, help, privacy, terms, supported industries) use ONE shared compact introduction (`.pg-sign`).

It used to be 64px+60px of padding and a 76px headline - 39% to 65% of a 1366x768 laptop viewport. These guards keep it compact (the measured heights at 1366x768 after the
change were 154-290px = 20-38%); they are static so they run everywhere. The HOME hero is a different component and is deliberately not constrained here.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

CSS = (Path(__file__).resolve().parents[1] / "static/portal/css/public-v2.css").read_text(encoding="utf-8")
TEMPLATES = Path(__file__).resolve().parents[1] / "templates/portal/public_v2"


def rule(selector):
    return re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS).group(1)


class InnerHeroCompactTests(SimpleTestCase):
    def test_vertical_padding_is_small(self):
        top, bottom = [int(x) for x in re.search(r"padding:\s*(\d+)px\s+0\s+(\d+)px", rule(".pg-sign")).groups()]
        self.assertLessEqual(top + bottom, 80)

    def test_the_headline_is_capped_well_below_the_old_76px(self):
        size = re.search(r"font-size:\s*clamp\((\d+)px\s*,\s*[\d.]+vw\s*,\s*(\d+)px\)", rule(".pg-sign h1"))
        self.assertIsNotNone(size)
        self.assertLessEqual(int(size.group(2)), 48)

    def test_lead_and_cta_spacing_stay_tight_and_no_later_rule_reopens_it(self):
        self.assertLessEqual(int(re.search(r"margin-top:\s*(\d+)px", rule(".pg-sign .btn")).group(1)), 20)
        later = re.findall(r"\.pg-sign p\+\.btn,\.pg-sign \.btn\{margin-top:(\d+)px\}", CSS)
        self.assertTrue(all(int(v) <= 20 for v in later), later)

    def test_every_inner_page_uses_the_shared_class_not_a_private_hero(self):
        for name in ("about", "contact", "design", "features", "plans", "help", "privacy", "terms", "supported_industries"):
            text = (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
            self.assertTrue('class="pg-sign"' in text or "_pghead.html" in text, f"{name}.html must use the shared .pg-sign introduction")

    def test_the_stylesheet_version_was_bumped(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        self.assertNotIn("public-v2.css' %}?v=20261020-1", base)
