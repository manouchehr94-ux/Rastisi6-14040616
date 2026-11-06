"""Jalali date-picker popup placement (UI-DATE-01).

The popup used to be ``position:absolute`` inside the field, so any ancestor with ``overflow:hidden|auto`` (Platform Admin cards, fieldsets, modal bodies)
clipped it and nothing kept it inside the viewport. ``jalali_picker.js`` now places the open popup with viewport coordinates.

* ``PickerSourceGuardTests`` - no browser: the placement engine and the Escape-from-text handler exist.
* ``PickerPlacementBrowserTests`` - opt-in Chromium (``SFB_BROWSER_TESTS=1``, optionally ``SFB_CHROMIUM_PATH``): real files in synthetic hostile layouts.
  "Reachable" = every sample point inside the popup (inset past its rounded corners) is the popup itself according to ``elementFromPoint``, i.e. not clipped,
  covered or off-screen.
"""

import os
import unittest
from pathlib import Path

from django.test import SimpleTestCase

CORE = Path(__file__).resolve().parents[1] / "static" / "core"
JS = CORE / "jalali_picker.js"
CSS = CORE / "jalali_picker.css"


class PickerSourceGuardTests(SimpleTestCase):
    def test_the_open_popup_is_placed_with_viewport_coordinates_and_follows_scroll_and_resize(self):
        js = JS.read_text(encoding="utf-8")
        for needle in ("pop.style.position = 'fixed'", "function place()", "addEventListener('scroll', place, true)", "addEventListener('resize', place)",
                       "openBelow", "maxHeight"):
            self.assertIn(needle, js)

    def test_close_releases_the_inline_placement_and_the_listeners(self):
        js = JS.read_text(encoding="utf-8")
        close = js[js.index("function close(returnFocus)"):js.index("function today()")]
        self.assertIn("stopPlacing()", close)
        self.assertIn("unplace()", close)

    def test_escape_in_the_text_field_closes_an_open_popup(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("e.key === 'Escape' && !pop.hidden", js)

    def test_css_keeps_absolute_only_as_the_documented_fallback(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("no-JS fallback", css)


PAGE = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;font-family:sans-serif}
.clip{overflow:hidden;border:1px solid #ccc;margin:@@MARGIN@@;padding:8px;height:70px;width:@@BOXW@@px}
.xf{transform:translateZ(0);margin:60px 40px;padding:10px;border:1px solid #ccc}
.spacer{height:@@SPACER@@px}.tail{height:1600px}</style>
<style>@@CSS@@</style></head><body>
<div class="spacer"></div>
<div class="clip" id="box"><input type="date" id="d1" name="d1"></div>
<div class="xf"><input type="date" id="d2" name="d2"></div>
<form><input type="text" id="after"></form><div class="tail"></div>
<script>@@JS@@</script></body></html>"""

JS_REACH = """(id) => {
  const pop = document.getElementById(id).closest('.jdp').querySelector('.jdp-pop'); if (pop.hidden) return {open: false};
  const r = pop.getBoundingClientRect(), W = innerWidth, H = innerHeight, INS = 16; let n = 0, ok = 0;
  for (let a = 0; a < 7; a++) for (let b = 0; b < 7; b++) {
    const x = r.left + INS + (r.width - 2 * INS) * a / 6, y = r.top + INS + (r.height - 2 * INS) * b / 6; n++;
    if (x < 0 || y < 0 || x >= W || y >= H) continue;
    const el = document.elementFromPoint(x, y); if (el && (el === pop || pop.contains(el))) ok++;
  }
  return {open: true, reach: ok / n, pos: getComputedStyle(pop).position, top: r.top, bottom: r.bottom, left: r.left, right: r.right, W, H};
}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "set SFB_BROWSER_TESTS=1 to run the Chromium picker tests")
class PickerPlacementBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls._pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox"]}
        for candidate in (os.environ.get("SFB_CHROMIUM_PATH", ""), "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome",
                          "/opt/pw-browsers/chromium"):
            if candidate and os.path.isfile(candidate):
                launch["executable_path"] = candidate
                break
        cls.browser = cls._pw.chromium.launch(**launch)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def _page(self, width, height, *, spacer=0, margin="20px", boxw=320):
        ctx = self.browser.new_context(viewport={"width": width, "height": height}, locale="fa-IR")
        page = ctx.new_page()
        html = (PAGE.replace("@@CSS@@", CSS.read_text(encoding="utf-8")).replace("@@JS@@", JS.read_text(encoding="utf-8")).replace("@@SPACER@@", str(spacer))
                .replace("@@MARGIN@@", margin).replace("@@BOXW@@", str(boxw)))
        page.set_content(html, wait_until="load")
        page.wait_for_selector(".jdp")
        return ctx, page

    def _open(self, page, field_id):
        page.locator(f"#{field_id}").locator("xpath=ancestor::*[contains(@class,'jdp')][1]").locator(".jdp-btn").click()
        page.wait_for_timeout(150)
        return page.evaluate(JS_REACH, field_id)

    def test_a_popup_is_not_clipped_by_an_overflow_hidden_ancestor(self):
        ctx, page = self._page(1280, 900)
        try:
            g = self._open(page, "d1")                    # the field sits in a 70px-high overflow:hidden box: the popup is far taller
            self.assertTrue(g["open"])
            self.assertEqual(g["pos"], "fixed")
            self.assertGreaterEqual(g["reach"], 0.999, g)
        finally:
            ctx.close()

    def test_it_flips_above_and_stays_inside_the_viewport_when_there_is_no_room_below(self):
        ctx, page = self._page(1280, 640, spacer=380)
        try:
            page.evaluate("window.scrollTo(0, 0)")
            g = self._open(page, "d1")
            self.assertGreaterEqual(g["reach"], 0.999, g)
            self.assertGreaterEqual(g["top"], 0)
            self.assertLessEqual(g["bottom"], g["H"])
        finally:
            ctx.close()

    def test_it_is_clamped_horizontally_near_either_edge(self):
        for margin in ("20px 0 20px 0", "20px 0 20px auto"):          # hard against the right edge in RTL / hard against the left edge
            ctx, page = self._page(1024, 800, margin=margin, boxw=200)
            try:
                g = self._open(page, "d1")
                self.assertGreaterEqual(g["left"], 0, g)
                self.assertLessEqual(g["right"], g["W"], g)
                self.assertGreaterEqual(g["reach"], 0.999, g)
            finally:
                ctx.close()

    def test_a_transformed_ancestor_does_not_misplace_the_fixed_popup(self):
        ctx, page = self._page(1280, 900)
        try:
            g = self._open(page, "d2")
            anchor = page.evaluate("(() => { const r = document.getElementById('d2').closest('.jdp').getBoundingClientRect(); return {b: r.bottom, l: r.left, r: r.right}; })()")
            self.assertGreaterEqual(g["reach"], 0.999, g)
            self.assertAlmostEqual(g["top"], anchor["b"] + 6, delta=2, msg="popup must sit directly under its field despite the transformed ancestor")
        finally:
            ctx.close()

    def test_phone_width_keeps_the_bottom_sheet_inside_the_viewport(self):
        ctx, page = self._page(390, 800)
        try:
            g = self._open(page, "d1")
            self.assertGreaterEqual(g["left"], 0)
            self.assertLessEqual(g["right"], g["W"])
            self.assertLessEqual(g["bottom"], g["H"])
            self.assertGreaterEqual(g["reach"], 0.999, g)
        finally:
            ctx.close()

    def test_it_follows_the_field_when_the_page_scrolls_and_resets_when_closed(self):
        ctx, page = self._page(1280, 900, spacer=40)                      # room below: the popup opens under its field and is not edge-clamped
        try:
            self._open(page, "d1")
            before = page.evaluate("document.querySelector('.jdp-pop').getBoundingClientRect().top")
            page.evaluate("window.scrollBy(0, 30)")
            page.wait_for_timeout(150)
            after = page.evaluate("document.querySelector('.jdp-pop').getBoundingClientRect().top")
            self.assertAlmostEqual(before - after, 30, delta=2, msg="the popup must move with its field instead of detaching from it")
            page.keyboard.press("Escape")
            page.wait_for_timeout(80)
            self.assertEqual(page.evaluate("document.querySelector('.jdp-pop').hidden"), True)
            self.assertEqual(page.evaluate("document.querySelector('.jdp-pop').style.position"), "")   # inline placement released
        finally:
            ctx.close()

    def test_escape_closes_the_popup_when_focus_is_in_the_text_field_and_selection_updates_the_iso_value(self):
        ctx, page = self._page(1280, 900)
        try:
            self._open(page, "d1")
            page.locator("#d1").focus()
            self.assertEqual(page.evaluate("document.activeElement.className.includes('jdp-text')"), True)
            page.keyboard.press("Escape")
            page.wait_for_timeout(80)
            self.assertEqual(page.evaluate("document.querySelector('.jdp-pop').hidden"), True)
            self._open(page, "d1")
            page.locator(".jdp-day:not([disabled])").nth(10).click()
            iso = page.evaluate("document.querySelector('input[name=d1]').value")
            self.assertRegex(iso, r"^\d{4}-\d{2}-\d{2}$")                 # the server still receives the Gregorian ISO date
        finally:
            ctx.close()
