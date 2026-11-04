"""Responsive contracts of the SHARED storefront CSS (no per-template patch): one gutter token, one page-width decision, a nested ``.wrap`` is
not a second page container, and the one product card is phone-sized. These are source contracts — the real rendering is verified in the
browser matrix (19 templates × 7 widths) documented in docs/admin-modernization."""

import re
from pathlib import Path

from django.test import SimpleTestCase

APPS = Path(__file__).resolve().parents[2]
BASE = (APPS / "core" / "static" / "css" / "base.css").read_text(encoding="utf-8")
LAYOUT = (APPS / "core" / "static" / "css" / "layout.css").read_text(encoding="utf-8")
CARD = (APPS / "catalog" / "static" / "css" / "product_card.css").read_text(encoding="utf-8")


class PageContainerContractTests(SimpleTestCase):
    def test_one_gutter_token_per_density_and_it_is_what_the_container_pads_with(self):
        for density, px in (("compact", "12px"), ("relaxed", "26px")):
            self.assertRegex(BASE, rf'html\[data-sfb-density="{density}"\]\{{--sfb-gutter:{px}\}}')
        self.assertIn(":root{--sfb-gutter:18px;--sfb-gutter-live:var(--sfb-gutter)}", BASE)
        self.assertRegex(BASE, r"\.wrap\{max-width:var\(--sfb-page-width, ?1240px\);margin:0 auto;padding:0 var\(--sfb-gutter-live\)\}")
        self.assertNotRegex(BASE, r'data-sfb-density="(?:compact|relaxed)"\] \.wrap\{padding')       # no second, per-density padding source

    def test_phones_never_use_more_than_12px_of_gutter(self):
        self.assertRegex(BASE, r"@media\(max-width:680px\)\{:root\{--sfb-gutter-live:min\(var\(--sfb-gutter\),12px\)\}\}")

    def test_the_page_width_is_one_reusable_decision_that_never_narrows_the_template(self):
        self.assertIn("--sfb-page-width:max(var(--sfb-content-width,1240px),min(84vw,var(--sfb-page-width-cap,1720px)))", BASE)
        self.assertIn(".wrap{width:min(var(--sfb-page-width,1320px),calc(100% - 28px))}", LAYOUT)
        self.assertNotIn("min(var(--sfb-content-width,1320px)", LAYOUT)                                # the old, narrowing formula is gone

    def test_a_wrap_inside_a_wrap_is_neutralised_once_for_every_section_template(self):
        self.assertIn(".wrap .wrap{width:auto;max-width:none;margin-inline:0;padding-inline:0}", LAYOUT)
        nested_in_sections = list((APPS / "storefront_builder" / "templates" / "storefront_builder" / "sections").glob("*.html"))
        self.assertTrue(any('class="wrap"' in p.read_text(encoding="utf-8") for p in nested_in_sections),
                        "the reason for the rule still exists in the section templates")

    def test_full_bleed_sections_use_the_same_live_gutter(self):
        self.assertIn('.rsec[data-width="full"] > .section{max-width:none;margin-inline:calc(-1 * var(--sfb-gutter-live))}', LAYOUT)
        self.assertNotRegex(LAYOUT, r'rsec\[data-width="full"\] > \.section\{[^}]*margin-inline:-(?:12|18|26)px')


class ProductCardContractTests(SimpleTestCase):
    def _phone_block(self):
        match = re.search(r"@media\(max-width:680px\)\{\s*html\[data-sfb-density\] \.pcard \.body,\.pcard \.body\{[^}]*\}.*?\n\}", CARD, re.S)
        self.assertIsNotNone(match, "the shared phone block of the product card exists")
        return match.group(0)

    def test_the_card_body_is_phone_sized_whatever_the_density(self):
        block = self._phone_block()
        self.assertIn("padding:10px 10px 12px", block)
        self.assertIn("html[data-sfb-density] .pcard .body", block)       # same specificity as the relaxed-density rule it overrides

    def test_the_price_and_its_unit_stay_together_and_the_old_price_has_its_own_line(self):
        block = self._phone_block()
        self.assertRegex(block, r"\.pcard \.price \.now\{[^}]*white-space:nowrap")
        self.assertRegex(block, r"\.pcard \.price \.old\{display:block")

    def test_quick_view_is_an_icon_button_on_touch_with_a_large_hit_area_and_keeps_its_accessible_name(self):
        self.assertRegex(CARD, r"@media\(max-width:680px\),\(hover:none\)\{\s*\.pcard-qv-trigger\{[^}]*width:32px;height:32px")
        self.assertIn(".pcard-qv-trigger .pcard-qv-trigger-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)", CARD)
        self.assertIn(".pcard-qv-trigger::after{content:\"\";position:absolute;inset:-6px}", CARD)
        template = (APPS / "catalog" / "templates" / "catalog" / "partials" / "product_card.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="نمای سریع {{ card.name }}"', template)
        self.assertIn("pcard-qv-trigger-label", template)

    def test_there_is_no_fixed_card_height_or_stretching_rule_on_phones(self):
        block = self._phone_block()
        self.assertNotRegex(block, r"\.pcard\{[^}]*(?:min-)?height:\s*\d+px")
