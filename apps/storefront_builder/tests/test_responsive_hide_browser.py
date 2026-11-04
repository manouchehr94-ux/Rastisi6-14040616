"""Regression: «نمایش در موبایل / تبلت» must REALLY hide the component on that device (Chromium, computed style - not the Boolean, not the attribute).

Bug: the templates add ``data-shell-hide-tablet`` / ``data-shell-hide-mobile`` to the one component a merchant switched off, and ``layout.css`` hides
it with ``[data-shell-hide-*]{display:none}``. The header variant sheet (``storefront_builder.css``) loads later and declares class-level ``display``
(``.gh-inline-block{display:contents}``, the mobile-search rows, ``.gh-beauty-mobile-account{display:contents!important}``) with the SAME
specificity, which won - so the stationery / premium / atelier / ... headers kept showing the search, account and wishlist on the very device
the seller had turned them off for. Fixed by making the attribute rule win (scoped ``!important``, attribute only) and by letting the beauty
header's own forced rule step aside for a flagged component.

* ``ResponsiveHideCssRuleTests`` - no browser: the rules in the stylesheet.
* ``ResponsiveHideBrowserTests`` - opt-in Chromium (``SFB_BROWSER_TESTS=1``): for header models x {phone, tablet} x {390, 768, 1440}, the flagged
  components are rendered / hidden exactly as asked, nothing else changes, and desktop never loses anything."""

import os
import re
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.storefront_builder.models import FOOTER_RESPONSIVE_AWARE_KEYS, HEADER_RESPONSIVE_AWARE_KEYS
from apps.storefront_builder.services import layout_service

from . import test_v5_studio_composition_browser as _studio_tests

CORE_CSS = Path(__file__).resolve().parents[2] / "core" / "static" / "css" / "layout.css"
VARIANT_CSS = Path(__file__).resolve().parents[1] / "static" / "css" / "storefront_builder.css"
PREVIEW = "/admin-portal/vision-studio/region-preview/"
WIDTHS = {"mobile": 390, "tablet": 768, "desktop": 1440}
PROP_WIDTH = {"hide_on_mobile": 390, "hide_on_tablet": 768}

#: the three models named in the bug report + a spread of different structures (search row, centered brand, dark, promo bar, floating card, ...)
HEADERS = (
    "stationery_search", "premium_three_column", "atelier_nav", "legacy_default", "marketplace_search_first", "boutique_centered",
    "dark_tech", "promo_search_nav", "beauty_search_nav", "luxury_search", "kawaii_center", "floating_card",
)
FOOTERS = ("legacy_default", "dark_tech", "premium_columns", "marketplace_dense", "beauty_retail_columns")

PROBE = """(region) => {
  const visible = n => { for (let e = n; e; e = e.parentElement) { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false; } return true; };
  const root = document.querySelector('[data-vs-region="' + region + '"]');
  const rendered = n => visible(n) && n.getClientRects().length > 0;
  const seen = sel => [...root.querySelectorAll(sel)].some(rendered);
  return {
    shown: [...root.querySelectorAll('*')].filter(rendered).length,
    flagged: [...root.querySelectorAll('[data-shell-hide-mobile],[data-shell-hide-tablet]')].map(n => ({
      name: (n.tagName + '.' + String(n.className)).slice(0, 40), mobile: n.hasAttribute('data-shell-hide-mobile'), tablet: n.hasAttribute('data-shell-hide-tablet'), visible: visible(n)})),
    search: seen('input[type="search"], input[name="q"]'),
    account: seen('a[href*="login"], a[href*="account"], a[href*="profile"]'),
    wishlist: seen('a[href*="wishlist"]'),
    announce: seen('.gh-announce:not(.sfb-builder-announcement--off)'),   // the «disabled» placeholder is a Studio affordance, not the strip
  };
}"""


class ResponsiveHideCssRuleTests(SimpleTestCase):
    def test_the_hide_rules_win_over_class_level_display_rules(self):
        css = CORE_CSS.read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\(max-width:1000px\) and \(min-width:681px\)\{\s*\[data-shell-hide-tablet\]\{display:none!important\}\s*\}")
        self.assertRegex(css, r"@media\(max-width:680px\)\{\s*\[data-shell-hide-mobile\]\{display:none!important\}\s*\}")

    def test_no_variant_rule_forces_display_on_a_flagged_component(self):
        """A variant rule that forces ``display`` with ``!important`` must step aside for a flagged component (the file's own :not() idiom)."""
        css = VARIANT_CSS.read_text(encoding="utf-8")
        self.assertIn(".gh-beauty-mobile-account:not([data-shell-hide-mobile]){display:contents!important}", css)
        self.assertNotIn("  .gh-beauty-mobile-account{display:contents!important}", css)


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class ResponsiveHideBrowserTests(_studio_tests._StudioFixture):
    def setUp(self):
        super().setUp()
        layout_service.get_or_create_draft(self.store)   # the Studio always works on a Draft; the model preview reads it

    def _set(self, region, prop=None, keys=None):
        draft = layout_service.get_existing_draft(self.store)
        attr = f"{region}_config"
        config = dict(getattr(draft, attr) or {})
        every = HEADER_RESPONSIVE_AWARE_KEYS if region == "header" else FOOTER_RESPONSIVE_AWARE_KEYS
        config["responsive"] = {
            key: {"hide_on_tablet": prop == "hide_on_tablet" and key in (keys or every), "hide_on_mobile": prop == "hide_on_mobile" and key in (keys or every)}
            for key in every
        }
        setattr(draft, attr, config)
        draft.save(update_fields=[attr])

    def _measure(self, context, region, variant, width):
        page = context.new_page()
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(f"{self.base}{PREVIEW}?region={region}&variant={variant}", wait_until="load")
        page.wait_for_timeout(350)
        data = page.evaluate(PROBE, region)
        page.close()
        return data

    def _context(self):
        context = self.browser.new_context(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        context.add_cookies([self.cookie])
        return context

    def _check_region(self, region, variants, keys_seen):
        context = self._context()
        try:
            for variant in variants:
                self._set(region)
                base = {device: self._measure(context, region, variant, width) for device, width in WIDTHS.items()}
                for prop, target_width in PROP_WIDTH.items():
                    self._set(region, prop)
                    for device, width in WIDTHS.items():
                        got = self._measure(context, region, variant, width)
                        where = f"{region}/{variant} {prop} @{width}"
                        if width == target_width:
                            flagged = [f for f in got["flagged"] if f["mobile" if prop == "hide_on_mobile" else "tablet"]]
                            self.assertTrue(flagged, f"{where}: the template flags the component")
                            self.assertEqual([f["name"] for f in flagged if f["visible"]], [], f"{where}: a flagged component is still rendered")
                            self.assertLess(got["shown"], base[device]["shown"], f"{where}: something really disappeared")
                            for key in keys_seen:
                                if base[device][key]:
                                    self.assertFalse(got[key], f"{where}: {key} is still visible")
                        else:
                            self.assertEqual(got["shown"], base[device]["shown"], f"{where}: switching it off for another device must change nothing here")
                            for key in keys_seen:
                                self.assertEqual(got[key], base[device][key], f"{where}: {key}")
        finally:
            self._set(region)
            context.close()

    def test_every_header_component_is_hidden_on_exactly_the_device_it_is_switched_off_for(self):
        self._check_region("header", HEADERS, ("search", "account", "wishlist", "announce"))

    def test_every_footer_component_is_hidden_on_exactly_the_device_it_is_switched_off_for(self):
        self._check_region("footer", FOOTERS, ())

    def test_switching_off_one_component_leaves_the_others_alone(self):
        context = self._context()
        try:
            for variant in ("stationery_search", "premium_three_column", "atelier_nav"):
                self._set("header")
                base = {width: self._measure(context, "header", variant, width) for width in WIDTHS.values()}
                for key, probe in (("show_search", "search"), ("show_account", "account"), ("show_wishlist", "wishlist")):
                    self._set("header", "hide_on_mobile", keys=(key,))
                    got = {width: self._measure(context, "header", variant, width) for width in WIDTHS.values()}
                    if base[390][probe]:
                        self.assertFalse(got[390][probe], f"{variant}: {key} is hidden on a phone")
                    for other in {"search", "account", "wishlist"} - {probe}:
                        self.assertEqual(got[390][other], base[390][other], f"{variant}: hiding {key} must not hide {other}")
                    for width in (768, 1440):   # still there on a tablet and on the desktop
                        self.assertEqual(got[width][probe], base[width][probe], f"{variant}: {key} @{width}")
                        self.assertEqual(got[width]["shown"], base[width]["shown"], f"{variant}: {key} @{width}")
        finally:
            self._set("header")
            context.close()
