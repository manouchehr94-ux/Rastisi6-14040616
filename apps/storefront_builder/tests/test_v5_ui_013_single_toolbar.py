"""V5-UI-013 — the Studio shows ONE section toolbar (the dark/green one of ``r4_resize.js``); the old in-page ``.sfb-rsec-toolbar`` never returns.

Root cause (proved in a real browser): the preview document marks itself ``body[data-sfb-studio-host]`` from its own inline script, but only while
its frame element still has ``id="r4PreviewFrame"``. A refreshed preview is loaded in a hidden TWIN iframe whose id is removed until it is swapped
in (r4_editor.js), so after the FIRST refresh (any mutation, resize, device switch …) the new document had no marker, the Studio-only hiding rules
did not apply, and the old strip showed next to the new one. The Studio now (re)asserts the marker on every preview load.

* always-on checks pin the mechanism (marker asserted on every load before anything else, hiding rule kept, the facts that caused the bug);
* the opt-in real-browser check (SFB_BROWSER_TESTS=1) drives hover → select → refresh → resize and counts every visible / clickable old toolbar."""

import os
import re
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from . import test_engine_parity_browser as _parity   # a module alias: the fixture class must not be collected twice

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static"


class SingleToolbarContractTests(SimpleTestCase):
    JS = (STATIC / "storefront_builder/r4_resize.js").read_text(encoding="utf-8")
    CSS = (STATIC / "css/storefront_builder.css").read_text(encoding="utf-8")
    EDITOR = (STATIC / "storefront_builder/r4_editor.js").read_text(encoding="utf-8")
    PREVIEW = (APP / "templates/storefront_builder/preview.html").read_text(encoding="utf-8")

    def test_the_studio_reasserts_the_host_marker_on_every_preview_load_before_anything_else(self):
        body = self.JS[self.JS.index("function bindFrame(f) {"):][:700]
        self.assertIn("markStudioHost(win);", body)
        self.assertLess(body.index("markStudioHost(win);"), body.index("__rsResizeBound"))        # not skipped by the «already bound» guard
        mark = self.JS[self.JS.index("function markStudioHost(win) {"):][:420]
        self.assertIn("setAttribute('data-sfb-studio-host', '1')", mark)
        self.assertIn("querySelector('.sfb-preview-sections')", mark)                            # builder previews only, never a storefront document
        # every preview load reaches it: the capture-phase load listener covers the swapped-in TWIN frame as well as the first frame
        self.assertIn("f.hasAttribute('data-rs-draft-src')) { bindFrame(f);", self.JS)
        self.assertIn("bindFrame(frame());", self.JS)

    def test_the_old_in_page_toolbar_is_removed_from_layout_whenever_the_studio_hosts_the_preview(self):
        self.assertRegex(self.CSS, r"body\[data-sfb-studio-host\] \.rsec > \.sfb-rsec-toolbar \{ display: none !important; \}")
        # the rule outranks the strip's own «selected» rule (.rsec.sfb-rsec-selected > .sfb-rsec-toolbar { display:flex !important })
        self.assertIn(".rsec.sfb-rsec-selected > .sfb-rsec-toolbar { display:flex !important; }", self.CSS)
        # (0,3,1) = body + [attr] + .rsec + .toolbar beats (0,3,0); only the Studio marker gates it, so the standalone Preview and the
        # legacy editor keep the strip they still use
        self.assertNotRegex(self.CSS, r"(?m)^\.rsec > \.sfb-rsec-toolbar \{ display: none !important;")

    def test_the_facts_that_caused_the_bug_are_still_what_the_fix_assumes(self):
        # the refreshed preview is a TWIN frame without an id until swapped in …
        self.assertIn("twin.removeAttribute('id');", self.EDITOR)
        self.assertIn("twin.id = old.id;", self.EDITOR)
        # … and the preview only marks itself from that id, at its own load time
        self.assertIn("window.frameElement.id === 'r4PreviewFrame'", self.PREVIEW)
        self.assertIn("document.body.setAttribute('data-sfb-studio-host', '1')", self.PREVIEW)

    def test_the_new_toolbar_is_the_only_one_the_studio_builds_and_it_never_lies_in_the_storefront(self):
        self.assertEqual(len(re.findall(r'class="rs-sel-toolbar"', self.JS)), 1)
        self.assertNotIn("sfb-rsec-toolbar", self.JS.replace("`.sfb-rsec-toolbar`", ""))        # the layer never re-uses or re-creates the old strip


AUDIT_JS = """()=>{
  const out=[...document.querySelectorAll('.sfb-rsec-toolbar')].map(t=>{
    const cs=getComputedStyle(t), r=t.getBoundingClientRect();
    const shown=cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;
    let clickable=false;
    if(shown){const e=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); clickable=!!e&&t.contains(e);}
    const focusable=[...t.querySelectorAll('button')].some(b=>{const c=getComputedStyle(b);return c.display!=='none'&&b.getBoundingClientRect().width>0});
    return {shown,clickable,focusable};
  });
  return {marker:document.body.getAttribute('data-sfb-studio-host'),count:out.length,shown:out.filter(x=>x.shown).length,
          clickable:out.filter(x=>x.clickable).length,focusable:out.filter(x=>x.focusable).length};
}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class SingleStudioToolbarBrowserTests(_parity.EngineGeometryParityBrowserTests):
    def _studio(self):
        draft, band = self._band_in_draft()
        context = self.browser.new_context(viewport={"width": 1460, "height": 950}, locale="fa-IR")
        context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(f"{self.base}/admin-portal/storefront-builder/r4/", wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        return context, page, band

    def _frame(self, page):
        return next(f for f in page.frames if f != page.main_frame and "/preview/" in f.url)

    def _audit(self, page):
        for _ in range(8):
            try:
                return self._frame(page).evaluate(AUDIT_JS)
            except Exception:  # the frame is being swapped
                page.wait_for_timeout(400)
        return self._frame(page).evaluate(AUDIT_JS)

    def _assert_one_toolbar(self, page, label, *, selected):
        audit = self._audit(page)
        self.assertEqual(audit["marker"], "1", f"{label}: the Studio-host marker is missing")
        self.assertEqual((audit["shown"], audit["clickable"], audit["focusable"]), (0, 0, 0), f"{label}: an old toolbar is visible/clickable: {audit}")
        visible_new = page.evaluate("()=>{const t=document.querySelector('[data-rs-sel-toolbar]');return t&&!t.hidden&&t.getBoundingClientRect().width>0?1:0}")
        self.assertEqual(visible_new, 1 if selected else 0, f"{label}: the new toolbar state is wrong")

    def _point(self, page, selector):
        return page.evaluate("""(sel)=>{const f=document.getElementById('r4PreviewFrame'),r=f.getBoundingClientRect(),w=f.contentWindow,
          e=f.contentDocument.querySelector(sel);e.scrollIntoView({block:'center'});const b=e.getBoundingClientRect(),k=r.width/w.innerWidth;
          return {x:r.x+(b.x+Math.min(b.width/2,300))*k,y:r.y+(b.y+Math.min(b.height/2,120))*k}}""", selector)

    def test_only_the_new_toolbar_exists_through_hover_select_edit_refresh_resize_and_a_second_refresh(self):
        context, page, band = self._studio()
        try:
            sel = f'[data-section-id="{band.pk}"]'
            self._assert_one_toolbar(page, "fresh load", selected=False)
            point = self._point(page, sel)
            page.mouse.move(point["x"], point["y"])
            page.wait_for_timeout(400)
            self._assert_one_toolbar(page, "hover without selection", selected=False)
            page.mouse.click(point["x"], point["y"])
            page.wait_for_timeout(800)
            self._assert_one_toolbar(page, "selected", selected=True)
            page.mouse.move(point["x"] + 6, point["y"] + 6)
            page.wait_for_timeout(400)
            self._assert_one_toolbar(page, "selected + hovered", selected=True)
            # a preview refresh swaps in a TWIN iframe — the old strip used to return exactly here
            page.evaluate("()=>RastiSiR4.reloadPreview()")
            page.wait_for_timeout(5000)
            self._assert_one_toolbar(page, "after a preview refresh", selected=True)
            # a real resize mutation (what the handle sends) refreshes the preview again
            result = page.evaluate("""(id)=>RastiSiR4.enqueueStructuralMutation({type:'section.resize',section_id:id,height:520}).then(r=>!!(r&&r.ok))""", band.pk)
            self.assertTrue(result)
            page.wait_for_timeout(4000)
            self._assert_one_toolbar(page, "after a resize", selected=True)
            # close hides the new one only; the old one stays gone
            page.click('[data-rs-sel="close"]')
            page.wait_for_timeout(500)
            self._assert_one_toolbar(page, "after close", selected=False)
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            point = self._point(page, sel)
            page.mouse.click(point["x"], point["y"])
            page.wait_for_timeout(800)
            self._assert_one_toolbar(page, "after a page refresh + reselect", selected=True)
            self.assertEqual(self.errors, [])
        finally:
            context.close()
