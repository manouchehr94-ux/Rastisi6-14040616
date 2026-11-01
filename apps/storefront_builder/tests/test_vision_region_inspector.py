"""Header / Footer are edited in a docked Studio Inspector, never in an auto-opened big modal.

Contract tests for the Vision layer (the real-browser proof lives in the Chromium QA of the Studio report):

* the Vision page carries the Inspector's tab bar and the SAME ``#rsGlobalHeader`` / ``#rsGlobalFooter`` forms (no second picker, no second select);
* ``vision.js`` marks exactly the header and footer categories as docked, tags the real form nodes by tab (models / content / design / advanced) and
  keeps every other design category a modal;
* the docked layer neither dims nor blocks the canvas (``pointer-events:none`` on the layer, the panel itself stays interactive);
* a model is applied through the native select's ``change`` (R4's own ``header.update`` / ``footer.update``), never by a Vision-only write.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
from django.urls import reverse

from .test_views import StorefrontBuilderViewsTestCase

VISION = Path(__file__).resolve().parents[1] / "static" / "storefront_builder" / "vision"
JS = (VISION / "vision.js").read_text(encoding="utf-8")
CSS = (VISION / "vision.css").read_text(encoding="utf-8")


class RegionInspectorContractTests(StorefrontBuilderViewsTestCase):
    def _soup(self):
        return BeautifulSoup(self.client.get(reverse("dashboard:vision-studio")).content.decode(), "html.parser")

    def test_the_tab_bar_and_the_one_real_form_per_region_are_in_the_page(self):
        soup = self._soup()
        self.assertIsNotNone(soup.select_one("[data-vs-rtabs][role=tablist]"))
        for select_id in ("r4GlobalHeaderVariant", "r4GlobalFooterVariant"):
            self.assertEqual(len(soup.select("#" + select_id)), 1, select_id)
        self.assertEqual(len(soup.select("#rsGlobalHeader")), 1)
        self.assertEqual(len(soup.select("#rsGlobalFooter")), 1)

    def test_only_header_and_footer_categories_are_docked(self):
        block = JS[JS.index("var CATS = {"):JS.index("// which dialog category each real appearance field")]
        docked = re.findall(r"(\w+): \{[^}]*dock: true[^}]*\}", block)
        self.assertEqual(sorted(docked), ["footer", "header"])
        for key in ("colors", "typography", "buttons", "shape", "images", "motion", "bottom_nav", "theme"):
            self.assertIn(key, block)

    def test_the_four_inspector_tabs_exist_and_are_derived_from_the_real_form(self):
        for key, label in (("models", "مدل‌ها"), ("content", "محتوا و نمایش"), ("design", "طراحی"), ("advanced", "پیشرفته")):
            self.assertIn("['%s', '%s']" % (key, label), JS)
        # structure-driven tagging of the real form's children, not a second copy of the controls
        for hook in ("label.r4-checkbox-row", ".r4-announce-entry", ".r4-geometry-group", ".r4-repeater, .r4-responsive-row"):
            self.assertIn(hook, JS)
        self.assertIn("role', 'tab'", JS)
        self.assertIn("aria-selected", JS)

    def test_a_docked_inspector_is_not_modal_and_does_not_trap_focus(self):
        self.assertIn("'complementary'", JS)
        self.assertRegex(JS, r"root\.dataset\.rsDrawer !== 'global' \|\| isDocked\(\)\) return;")

    def test_the_docked_layer_does_not_dim_or_block_the_canvas(self):
        rule = re.search(r'\[data-vs-dock="region"\] \.vs-dlayer\.context-panel\{([^}]*)\}', CSS)
        self.assertIsNotNone(rule)
        self.assertIn("background:transparent", rule.group(1))
        self.assertIn("pointer-events:none", rule.group(1))
        self.assertRegex(CSS, r'\[data-vs-dock="region"\] \.vs-design-modal\{[^}]*pointer-events:auto')

    def test_applying_a_model_goes_through_the_native_select_change(self):
        pick = JS[JS.index("function pickModel(region, key)"):]
        pick = pick[:pick.index("// ---- the large read-only preview")]
        self.assertIn("select.value = key", pick)
        self.assertIn("dispatchEvent(new Event('change'", pick)
        self.assertNotIn("fetch(", pick)
        self.assertNotIn("XMLHttpRequest", pick)
