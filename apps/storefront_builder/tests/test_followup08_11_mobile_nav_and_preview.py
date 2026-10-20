"""FOLLOWUP-08 / FOLLOWUP-11 — static contract of the fixes proven by the real-browser QA (the measurements themselves:
 widths 320/375/390/430/820, tap/Escape/route, scrollWidth vs clientWidth, are recorded in the follow-up evidence).

* every Global Header variant's opened mobile navigation is ONE wrapped, bounded, vertically scrollable panel (no hidden
  horizontal strip), links stay readable on the light surface, the category sheet sits above the floating bottom nav and
  Escape closes the toggled navigation;
(ARCH-02b: the second gallery page and its preview-frame script were retired with the old gallery; the Design Studio's own
gallery/preview is verified in the real browser — see the ARCH-02b evidence — and its tile/preview wiring by
``test_arch02b_gallery_unification``.)"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CSS = (APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")
HEADERS = APP / "templates/storefront_builder/partials/global_header"

from django.test import SimpleTestCase


def _contract_block():
    start = CSS.index("FOLLOWUP-08 — ONE mobile contract")
    return CSS[start:]


class MobileNavContractTests(SimpleTestCase):
    def test_contract_covers_every_toggled_variant_family(self):
        block = _contract_block()
        for cls in ("gh-premium-mobile-nav", "gh-boutique-nav", "gh-dark-mobile-nav", "gh-atelier-mobile-nav",
                    "gh-chocolate-nav", "gh-luxury-nav", "gh-kw-nav", "gh-row-nav", "gh-st-nav", "gh-beauty-nav"):
            self.assertIn(cls, block, cls)

    def test_opened_panel_wraps_instead_of_scrolling_sideways(self):
        block = _contract_block()
        self.assertIn("flex-wrap:wrap", block)
        self.assertIn("overflow-x:hidden", block)
        self.assertIn("overflow-y:auto", block)
        self.assertIn("max-height:min(55dvh", block)          # bounded: never taller than the viewport
        self.assertNotIn("overflow-x:auto", block)

    def test_category_sheet_clears_the_floating_bottom_nav(self):
        block = _contract_block()
        self.assertIn("body:has(.gmn) .gh-shell .gh-cat-mega-panel{bottom:calc(112px", block)
        self.assertIn("max-height:min(72dvh,calc(100dvh - 206px))", block)

    def test_every_variant_uses_the_fixed_bottom_sheet_for_categories(self):
        block = _contract_block()
        self.assertIn(".gh-shell .gh-cat-mega-panel{position:fixed;top:auto;right:10px;left:10px;bottom:10px", block)
        self.assertIn(".gh-shell .gh-cat-mega-rail{width:100%;max-height:190px", block)

    def test_chocolate_links_are_dark_on_the_light_row(self):
        self.assertIn(".gh--chocolate .gh-chocolate-nav .gh-nl", _contract_block())
        self.assertIn("background:#FFFDF9", CSS)

    def test_every_toggle_closes_on_escape(self):
        for template in sorted(HEADERS.glob("*.html")):
            text = template.read_text(encoding="utf-8")
            for flag in ("ghMobileOpen", "ghLuxuryOpen"):
                if f"x-data=\"{{ {flag}: false" in text:
                    self.assertIn(f'@keydown.escape.window="{flag} = false"', text, template.name)
        mega = (HEADERS / "_shared/category_mega_menu.html").read_text(encoding="utf-8")
        self.assertIn('@keydown.escape.window="catMenuOpen = false"', mega)

    def test_the_menu_keeps_every_variant_and_link(self):
        # the fix is presentation only: no variant template lost its navigation include
        for template in sorted(HEADERS.glob("*.html")):
            text = template.read_text(encoding="utf-8")
            if "gh-burger" in text:
                self.assertTrue("nav_header_items" in text or "category_link_row" in text or "category_mega_menu" in text
                                or "nav_categories" in text, template.name)
