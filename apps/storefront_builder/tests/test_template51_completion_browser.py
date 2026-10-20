"""Ready Template 51 — finished-storefront layout integrity in a REAL browser (Chromium + Playwright), three viewports.

Audited against the PUBLISHED storefront (the surface customers see), on the shared engine only:

* no horizontal page overflow, no section overflowing its row, no overlapping rows (1440 / 820 / 390);
* no reserved-empty placeholder anywhere (blank panels, empty blog cards, empty credential squares, blank strip);
* equal-height pair rows end on one line AND the panel surface of the shorter side fills the row (the sibling panel's
  rail stretches into the free height, inside the panel's own padding) — a generic equal-height contract, not a Template 51 rule;
* the visible gap above every section equals its authored gap (the shared compact-density row margin is not paid twice);
* the stationery header's nav chips stay inside the viewport at tablet width;
* a stacked (single-column) offer card is bounded by the viewport instead of growing with the column width.

Opt-in: ``SFB_BROWSER_TESTS=1 python manage.py test apps.storefront_builder.tests.test_template51_completion_browser``."""

import os
import unittest

from django.test import override_settings

from apps.catalog.models import Category, Product
from apps.storefront_builder.services import layout_service

from .test_background_contract_browser import BackgroundBrowserFixture, HOST, PUBLIC_HOST, sync_playwright
from .test_template51_palette_workflow_browser import OVERLAP_JS

VIEWPORTS = ((1440, 900), (820, 1100), (390, 844))

PLACEHOLDER_JS = """()=>{const sel=['.blog-card--empty','.gf-trust-badge-item--empty','.category-grey-item--empty','.decor-strip',
  'section.surface-panel']; return sel.filter(s=>document.querySelector(s))}"""

#: equal-height rows: panels share one bottom, and each panel's own surface (the bordered .section) reaches that bottom
PAIR_JS = """()=>{const out=[]; for(const c of document.querySelectorAll('.rcontainer[data-height-mode="equal"]')){
  const cells=[...c.querySelectorAll(':scope > .rcontainer-cell')]; if(cells.length!==2) continue;
  const rs=cells.map(x=>x.querySelector(':scope > .rsec')); if(rs.some(r=>!r)) continue;
  if(!rs.every(r=>r.querySelector(':scope > .product-section--hs-underlined'))) continue;
  out.push({rsecBottoms:rs.map(r=>Math.round(r.getBoundingClientRect().bottom)),
            inner:rs.map(r=>parseFloat(getComputedStyle(r).paddingBottom)),
            sectionBottoms:rs.map(r=>Math.round(r.querySelector(':scope > .section').getBoundingClientRect().bottom)),
            stacked:Math.abs(cells[0].getBoundingClientRect().top-cells[1].getBoundingClientRect().top)>5})} return out}"""

#: per row: the section's own margin-top, the row margin under the previous row, and the visible gap between the two
GAP_JS = """()=>{const rows=[...document.querySelectorAll('.rcontainer')]
  .filter((e,i,a)=>!a.some(o=>o!==e&&o.contains(e))).sort((a,b)=>a.getBoundingClientRect().top-b.getBoundingClientRect().top);
  const out=[]; for(let i=1;i<rows.length;i++){const first=rows[i].querySelector('.rsec'); if(!first) continue;
    out.push({margin:parseFloat(getComputedStyle(first).marginTop), rowMargin:parseFloat(getComputedStyle(rows[i-1]).marginBottom),
              visible:Math.round(first.getBoundingClientRect().top-rows[i-1].getBoundingClientRect().bottom)})} return out}"""

CHIPS_JS = """()=>{const w=document.documentElement.clientWidth; return [...document.querySelectorAll('.gh-nl--chip')].map(e=>{
  const b=e.getBoundingClientRect(); return {left:Math.round(b.left), right:Math.round(b.right), w}})}"""

OFFER_JS = """()=>{const e=document.querySelector('.product-section--spotlight .pcard .img'); return e?Math.round(e.getBoundingClientRect().height):null}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class Template51CompletionBrowserTests(BackgroundBrowserFixture):
    def setUp(self):
        super().setUp()
        layout_service.publish(self.store)

    def _realistic_catalogue(self):
        """The shared demo's real-world unevenness: out-of-stock cards carry no add-to-cart control (shorter cards) and
        category names are long enough to fill the nav row."""
        Product.objects.filter(store=self.store, discount_percent__gt=0).update(stock=0)
        names = ["کتانی رانینگ", "کتانی کژوال", "شلوار جین", "کیف دوشی و مجلسی"]
        for category, name in zip(Category.objects.filter(store=self.store, parent__isnull=True).order_by("pk"), names):
            category.name = name
            category.save(update_fields=["name"])
        Category.objects.create(store=self.store, name=names[3], slug="root-3", order=3, is_active=True)

    def _public(self, width, height):
        context, page = self._page("/", authed=False, width=width, height=height)
        return context, page

    def test_no_overflow_overlap_or_empty_placeholder_at_three_viewports(self):
        for width, height in VIEWPORTS:
            context, page = self._public(width, height)
            try:
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth"), 0,
                                 f"horizontal overflow at {width}px")
                self.assertEqual(page.evaluate(OVERLAP_JS), [], f"layout integrity at {width}px")
                self.assertEqual(page.evaluate(PLACEHOLDER_JS), [], f"empty placeholder at {width}px")
            finally:
                context.close()

    def test_equal_height_pairs_end_together_and_the_panel_surface_fills_the_row(self):
        self._realistic_catalogue()
        context, page = self._public(1440, 900)
        try:
            pairs = page.evaluate(PAIR_JS)
            self.assertEqual(len(pairs), 4, "four paired-rail rows")
            for pair in pairs:
                self.assertFalse(pair["stacked"])
                self.assertLessEqual(abs(pair["rsecBottoms"][0] - pair["rsecBottoms"][1]), 1, pair)
                # the bordered panel of each side reaches the row's bottom edge (no short panel floating in a tall row)
                for side in (0, 1):
                    self.assertLessEqual(abs(pair["sectionBottoms"][side] - (pair["rsecBottoms"][side] - pair["inner"][side])),
                                         1, pair)
        finally:
            context.close()

    def test_visible_gap_above_each_section_is_its_authored_gap(self):
        from apps.storefront_builder import layout_preset_registry as lpr

        # authored visible gap per row, in order: the recipe states the gap, the engine adds its shared 10px row margin once
        authored, seen = [], set()
        for entry in lpr.get_layout_preset("stationery_spectrum").pages["home"]:
            if entry.section_key == "amazing_offers":
                continue  # the fixture replaces the preset's offers with its own section
            key = entry.row_key or id(entry)
            if key in seen:
                continue
            seen.add(key)
            spacing = (entry.settings.get("spacing") or {}).get("advanced") or {}
            margin = spacing.get("margin_top", (entry.settings.get("design") or {}).get("margin_top", 0))
            authored.append(margin + 10)
        context, page = self._public(1440, 900)
        try:
            rows = page.evaluate(GAP_JS)
            self.assertGreaterEqual(len(rows), len(authored) - 1)
            for index, expected in enumerate(authored[1:]):
                self.assertEqual(rows[index]["rowMargin"], 10, rows[index])
                self.assertEqual(rows[index]["visible"], expected, (index, rows[index]))
        finally:
            context.close()

    def test_tablet_nav_chips_stay_inside_the_viewport(self):
        self._realistic_catalogue()
        context, page = self._public(820, 1100)
        try:
            chips = page.evaluate(CHIPS_JS)
            for chip in chips:
                self.assertGreaterEqual(chip["left"], 0, chip)
                self.assertLessEqual(chip["right"], chip["w"], chip)
        finally:
            context.close()

    def test_stacked_offer_card_is_bounded_by_the_viewport(self):
        for width, height in ((820, 1100), (390, 844)):
            context, page = self._public(width, height)
            try:
                image_height = page.evaluate(OFFER_JS)
                self.assertIsNotNone(image_height)
                self.assertLessEqual(image_height, 421, f"offer image {image_height}px tall at {width}px")
            finally:
                context.close()
