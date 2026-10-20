"""Real-browser contract for the Studio's direct editing of the Preview + the drawer state machine (opt-in: SFB_BROWSER_TESTS=1).

* Direct editing — mouse: single click SELECTS a section, double-click opens its settings workspace; touch / pen: tap SELECTS,
  press-and-hold (≈550 ms) opens it; a hold is cancelled by movement (> 10 px), scrolling or an early release; genuinely
  interactive storefront controls (buttons, links, carousel arrows …) are never hijacked; the section id comes from
  [data-section-id]; the drawer closes before the workspace opens; the Preview geometry never changes.
* Drawer state machine — after EVERY transition the drawer is either closed (no visible area) or shows exactly one view with
  real content; 100+ randomised transitions (structure / global / settings / template peek / Escape / backdrop / rapid
  clicks), including after structure refreshes, with no JS exception and an unchanged Preview geometry."""

import os
import random
import unittest

from . import test_engine_parity_browser as _parity   # a module alias: the fixture class must not be collected twice

AUDIT_JS = """()=>{
  const root=document.querySelector('.rs-studio'); const panel=document.querySelector('[data-rs-context-panel]');
  const cs=getComputedStyle(panel); const r=panel.getBoundingClientRect();
  const shown=cs.display!=='none'&&r.width>0&&r.height>0;
  const views=[...panel.querySelectorAll(':scope > [data-rs-view]')].map(v=>({name:v.dataset.rsView,visible:getComputedStyle(v).display!=='none'&&!v.hidden}));
  const vis=views.filter(v=>v.visible);
  const st=document.getElementById('r4Structure'), gl=document.getElementById('r4GlobalDesign');
  const content={structure:!!st.querySelector('[data-rs-structure-scroll] .tree-row,[data-rs-structure-scroll] .empty'),
    global:!gl.hidden&&gl.children.length>0&&gl.getBoundingClientRect().height>40,
    'template-preview':!!((document.querySelector('[data-rs-peek-title]')||{}).textContent)};
  const f=document.getElementById('r4PreviewFrame'), fr=f.getBoundingClientRect();
  return {shown,panelClass:panel.classList.contains('panel-visible'),drawer:root.dataset.rsDrawer,nVis:vis.length,visName:vis[0]&&vis[0].name,content,
    ws:!document.querySelector('[data-rs-workspace]').hidden,backdrop:getComputedStyle(document.querySelector('.rs-drawer-backdrop')).display,
    frame:[fr.width,fr.height,fr.x,fr.y]}
}"""

# the Preview iframe point (in page coordinates) over a section's top-left corner, accounting for the frame's CSS scale
POINT_JS = """(args)=>{const f=document.getElementById('r4PreviewFrame'); const r=f.getBoundingClientRect(); const w=f.contentWindow;
  const s=f.contentDocument.querySelector(args.sel); const b=s.getBoundingClientRect(); const k=r.width/w.innerWidth;
  return {x:r.x+(b.x+args.dx)*k, y:r.y+(b.y+args.dy)*k}}"""


def _violations(audit, base_frame):
    problems = []
    if audit["shown"]:
        if audit["nVis"] != 1:
            problems.append(f"drawer shown with {audit['nVis']} visible views")
        elif not audit["content"].get(audit["visName"]):
            problems.append(f"drawer shown but its {audit['visName']} view is empty")
        if audit["drawer"] == "closed":
            problems.append("drawer shown while data-rs-drawer=closed")
        if audit["ws"]:
            problems.append("drawer and workspace open together")
    else:
        if audit["panelClass"]:
            problems.append("panel-visible class without a visible panel")
        if audit["drawer"] != "closed":
            problems.append(f"drawer hidden but data-rs-drawer={audit['drawer']}")
        if audit["backdrop"] != "none":
            problems.append("backdrop visible without a drawer")
    if audit["frame"] != base_frame:
        problems.append(f"Preview geometry changed {audit['frame']} != {base_frame}")
    return problems


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class StudioDirectEditBrowserTests(_parity.EngineGeometryParityBrowserTests):
    # the fixture/helpers come from the parity module; only this module's own tests run here
    def setUp(self):
        super().setUp()

    # -------------------------------------------------------------------------------------------- helpers
    def _studio(self, *, touch=False, viewport=(1440, 900)):
        _draft, band = self._band_in_draft()
        band.settings = {**band.settings, "display_mode": "campaign_band"}
        band.save()
        context = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale="fa-IR", has_touch=touch)
        context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(f"{self.base}/admin-portal/storefront-builder/r4/", wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        self.sel = f'[data-section-id="{band.pk}"]'
        self.band = band
        return context, page

    def _frame(self, page):
        return next(f for f in page.frames if f != page.main_frame and "/preview/" in f.url)

    def _state(self, page):
        return page.evaluate("""()=>({ws:!document.querySelector('[data-rs-workspace]').hidden,
          wsSection:(document.querySelector('[data-r4-section-inspector]')||{dataset:{}}).dataset.r4SectionId||null,
          drawer:document.querySelector('.rs-studio').dataset.rsDrawer,
          row:(document.querySelector('.tree-row.selected')||{dataset:{}}).dataset.r4StructureSectionId||null,
          frame:(()=>{const r=document.getElementById('r4PreviewFrame').getBoundingClientRect();return [r.width,r.height,r.x,r.y]})()})""")

    def _selected_in_preview(self, page, section_id):
        return self._frame(page).evaluate(f"document.querySelector('[data-section-id=\"{section_id}\"]').classList.contains('sfb-rsec-selected')")

    # -------------------------------------------------------------------------------------------- mouse
    def test_single_click_selects_only_and_double_click_opens_the_exact_section(self):
        context, page = self._studio()
        try:
            page.wait_for_load_state("networkidle")
            frame = self._frame(page)
            frame.locator(self.sel).first.scroll_into_view_if_needed()
            before = self._state(page)
            frame.locator(self.sel).first.click(position={"x": 40, "y": 40})
            page.wait_for_timeout(700)
            after = self._state(page)
            self.assertFalse(after["ws"], "a single click must not open settings")
            self.assertTrue(self._selected_in_preview(page, self.band.pk))
            self.assertEqual(after["row"], str(self.band.pk))                    # the structure row is selected too
            self.assertEqual(after["frame"], before["frame"])
            # a different section is selected by its own click (no stale selection)
            other = self._frame(page).evaluate("""(band)=>{const s=[...document.querySelectorAll('.rsec[data-section-id]')]
              .find(e=>e.dataset.sectionId!==band&&e.getBoundingClientRect().height>120&&!e.querySelector('.rsec')); return s?s.dataset.sectionId:null}""", str(self.band.pk))
            self.assertIsNotNone(other)
            # double click opens the large workspace for THAT exact section and keeps the Preview where it was
            frame.locator(self.sel).first.dblclick(position={"x": 40, "y": 40})
            page.wait_for_selector('[data-rs-workspace]:not([hidden]) input[data-r4-field-key="title"]')
            page.wait_for_timeout(500)
            opened = self._state(page)
            self.assertEqual((opened["ws"], opened["wsSection"], opened["drawer"]), (True, str(self.band.pk), "closed"))
            self.assertEqual(opened["frame"], before["frame"], "opening settings by double-click changed the Preview geometry")
            # Escape closes the workspace; focus returns to the top-bar settings button
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            self.assertFalse(self._state(page)["ws"])
            self.assertEqual(page.evaluate("document.activeElement.dataset.rastisiAction"), "section-settings")
            # …and a double-click on ANOTHER section opens that one
            frame = self._frame(page)
            frame.locator(f'[data-section-id="{other}"]').first.scroll_into_view_if_needed()
            frame.locator(f'[data-section-id="{other}"]').first.dblclick(position={"x": 30, "y": 30})
            page.wait_for_selector('[data-rs-workspace]:not([hidden]) [data-r4-section-inspector]')
            self.assertEqual(self._state(page)["wsSection"], other)
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    def test_interactive_storefront_controls_are_not_hijacked(self):
        context, page = self._studio()
        try:
            page.wait_for_load_state("networkidle")
            frame = self._frame(page)
            frame.locator(self.sel).first.scroll_into_view_if_needed()
            targets = frame.evaluate("""()=>{const pick=(sel)=>{const e=[...document.querySelectorAll(sel)].find(x=>{const r=x.getBoundingClientRect();
                return r.width>8&&r.height>8&&!x.closest('.sfb-rsec-toolbar,[data-cmd],[data-open-settings],.sfb-rsec-drag-handle')&&x.closest('[data-section-id]')});
                if(!e) return null; e.setAttribute('data-qa-target','1'); return e.closest('[data-section-id]').dataset.sectionId};
              return {button:(()=>{const id=pick('.rsec button');if(id){document.querySelector('[data-qa-target]').setAttribute('data-qa-kind','button');document.querySelector('[data-qa-target]').removeAttribute('data-qa-target')}return id})(),
                link:(()=>{const id=pick('.rsec a[href]');if(id){document.querySelector('[data-qa-target]').setAttribute('data-qa-kind','link');document.querySelector('[data-qa-target]').removeAttribute('data-qa-target')}return id})()}}""")
            self.assertTrue(targets["button"] and targets["link"], targets)
            for kind in ("button", "link"):
                locator = frame.locator(f'[data-qa-kind="{kind}"]').first
                locator.scroll_into_view_if_needed()
                locator.dblclick(timeout=5000, force=True)
                page.wait_for_timeout(900)
                state = self._state(page)
                self.assertFalse(state["ws"], f"a double-click on a storefront {kind} opened settings (hijacked)")
            # a plain click on a button still reaches the storefront (the page is not navigated away or frozen)
            self.assertIn("/preview/", self._frame(page).url)
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    # -------------------------------------------------------------------------------------------- touch / pen
    def test_touch_tap_selects_long_press_opens_and_cancels_on_move_scroll_or_early_release(self):
        context, page = self._studio(touch=True)
        try:
            page.wait_for_load_state("networkidle")
            frame = self._frame(page)
            frame.locator(self.sel).first.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            cdp = context.new_cdp_session(page)

            def point(dx=40, dy=30):
                return page.evaluate(POINT_JS, {"sel": self.sel, "dx": dx, "dy": dy})

            def touch(kind, p):
                cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": p["x"], "y": p["y"]}] if kind != "touchEnd" else []})

            before = self._state(page)
            p = point()
            # short tap: selects, opens nothing
            touch("touchStart", p); page.wait_for_timeout(80); touch("touchEnd", p)
            page.wait_for_timeout(900)
            self.assertFalse(self._state(page)["ws"])
            self.assertTrue(self._selected_in_preview(page, self.band.pk))
            # early release (300 ms < threshold) does not open
            touch("touchStart", p); page.wait_for_timeout(300); touch("touchEnd", p)
            page.wait_for_timeout(900)
            self.assertFalse(self._state(page)["ws"], "a hold released before the threshold opened settings")
            # movement beyond the slop cancels
            touch("touchStart", p); page.wait_for_timeout(150)
            touch("touchMove", {"x": p["x"] + 28, "y": p["y"]}); page.wait_for_timeout(900)
            touch("touchEnd", {"x": p["x"] + 28, "y": p["y"]}); page.wait_for_timeout(500)
            self.assertFalse(self._state(page)["ws"], "a moving press opened settings")
            # scrolling cancels
            p = point()
            touch("touchStart", p); page.wait_for_timeout(150)
            self._frame(page).evaluate("window.scrollBy(0, 60)")
            page.wait_for_timeout(900)
            touch("touchEnd", p); page.wait_for_timeout(500)
            self.assertFalse(self._state(page)["ws"], "scrolling during a press opened settings")
            # a real press-and-hold (> threshold) opens exactly this section, with a visible hold cue first
            self._frame(page).locator(self.sel).first.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            p = point()
            touch("touchStart", p); page.wait_for_timeout(300)
            self.assertTrue(self._frame(page).evaluate(f"document.querySelector('{self.sel}').classList.contains('sfb-rsec-hold')"))
            page.wait_for_timeout(500)
            touch("touchEnd", p)
            page.wait_for_selector('[data-rs-workspace]:not([hidden]) input[data-r4-field-key="title"]', timeout=15000)
            opened = self._state(page)
            self.assertEqual((opened["wsSection"], opened["drawer"]), (str(self.band.pk), "closed"))
            self.assertEqual(opened["frame"], before["frame"])
            # touch wording of the hint
            self.assertEqual(page.evaluate("document.querySelector('[data-rs-caption]').textContent"), "لمس برای انتخاب؛ نگه‌داشتن برای تنظیمات")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            self.assertFalse(self._state(page)["ws"])
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    def test_touch_hold_on_a_storefront_button_is_not_hijacked(self):
        context, page = self._studio(touch=True)
        try:
            page.wait_for_load_state("networkidle")
            frame = self._frame(page)
            frame.locator(self.sel).first.scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            found = frame.evaluate("""()=>{const e=[...document.querySelectorAll('.rsec button')].find(x=>{const r=x.getBoundingClientRect();
              return r.width>8&&r.height>8&&!x.closest('.sfb-rsec-toolbar,[data-cmd],[data-open-settings],.sfb-rsec-drag-handle')});
              if(!e) return false; e.setAttribute('data-qa-btn','1'); e.scrollIntoView({block:'center'}); return true}""")
            self.assertTrue(found)
            page.wait_for_timeout(300)
            p = page.evaluate("""()=>{const f=document.getElementById('r4PreviewFrame'),r=f.getBoundingClientRect(),w=f.contentWindow,
              b=f.contentDocument.querySelector('[data-qa-btn]').getBoundingClientRect(),k=r.width/w.innerWidth;
              return {x:r.x+(b.x+b.width/2)*k,y:r.y+(b.y+b.height/2)*k}}""")
            cdp = context.new_cdp_session(page)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": p["x"], "y": p["y"]}]})
            page.wait_for_timeout(900)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            page.wait_for_timeout(600)
            self.assertFalse(self._state(page)["ws"], "a long press on a storefront button opened settings")
        finally:
            context.close()

    # -------------------------------------------------------------------------------------------- drawer state machine
    def test_defensive_invariant_never_renders_a_blank_drawer(self):
        context, page = self._studio()
        try:
            page.wait_for_load_state("networkidle")
            base = self._state(page)["frame"]
            # (1) the structure list went missing: asking for the drawer must not open an empty shell
            page.evaluate("window.__saved = document.getElementById('r4Structure').innerHTML; document.getElementById('r4Structure').innerHTML=''")
            page.click('.top-nav [data-rastisi-action="structure"]')
            page.wait_for_timeout(300)
            audit = page.evaluate(AUDIT_JS)
            self.assertEqual(_violations(audit, base), [])
            self.assertEqual(audit["drawer"], "closed")
            page.evaluate("document.getElementById('r4Structure').innerHTML = window.__saved")
            # (2) Global Design closed underneath the Studio (what R4.openSection does): the drawer follows, never stays blank
            page.click('.top-nav [data-rastisi-action="global"]')
            page.wait_for_function("document.querySelector('.rs-studio').dataset.rsDrawer==='global'")
            self.assertEqual(_violations(page.evaluate(AUDIT_JS), base), [])
            page.evaluate("RastiSiR4.closeGlobalDesign()")
            page.wait_for_timeout(200)
            audit = page.evaluate(AUDIT_JS)
            self.assertEqual((audit["drawer"], _violations(audit, base)), ("closed", []))
            # (3) a refresh that returns an error page keeps the structure list
            page.click('.top-nav [data-rastisi-action="structure"]')
            page.wait_for_function("document.querySelector('.rs-studio').dataset.rsDrawer==='structure'")
            page.evaluate("""()=>{window.__fetch=window.fetch; window.fetch=()=>Promise.resolve(new Response('<html><body>500</body></html>',{status:500}));}""")
            page.evaluate("RastiSiR4.refreshStructure()")
            page.wait_for_timeout(400)
            page.evaluate("window.fetch=window.__fetch")
            self.assertEqual(_violations(page.evaluate(AUDIT_JS), base), [])
            self.assertEqual(page.evaluate(AUDIT_JS)["drawer"], "structure")
            # (4) a real refresh keeps content too, several times, also with the drawer open
            for _ in range(3):
                page.evaluate("RastiSiR4.refreshStructure()")
                page.wait_for_timeout(500)
                audit = page.evaluate(AUDIT_JS)
                self.assertEqual((audit["drawer"], audit["content"]["structure"], _violations(audit, base)), ("structure", True, []))
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    def test_one_hundred_randomised_drawer_transitions_never_show_a_blank_or_resize_the_preview(self):
        context, page = self._studio()
        try:
            page.wait_for_load_state("networkidle")
            base = self._state(page)["frame"]
            rng = random.Random(20260611)
            nav = lambda action: page.locator(f'.top-nav [data-rastisi-action="{action}"]')

            def safe(locator, timeout=1500):
                try:
                    locator.first.click(timeout=timeout)
                except Exception:   # an overlay may legitimately cover the control for a moment
                    pass

            def settle():
                page.wait_for_timeout(120)

            def calm():
                # networkidle may never come while the second (live) frame keeps loading: bounded wait, then a short pause
                try:
                    page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    page.wait_for_timeout(500)

            def structure(): safe(nav("structure"))
            def global_(): safe(nav("global"))
            def settings_nav(): safe(nav("section-settings")); page.wait_for_timeout(700)
            def gear(): safe(page.locator(".tree-row .rs-row-settings").nth(rng.randint(0, 3))); page.wait_for_timeout(700)
            def select(): safe(page.locator(".rs-row-select").nth(rng.randint(0, 5)))
            def close_btn(): safe(page.locator('[data-rs-context-panel].panel-visible [data-rastisi-action="panel-close"]'))
            def ws_close(): safe(page.locator("[data-rs-workspace]:not([hidden]) [data-r4-inspector-close]"))
            def escape(): page.keyboard.press("Escape")
            def backdrop():
                try:
                    page.mouse.click(300, 500)
                except Exception:
                    pass
            def double_click_section():
                try:
                    self._frame(page).locator(self.sel).first.dblclick(position={"x": 30, "y": 30}, timeout=1500)
                except Exception:
                    pass
                page.wait_for_timeout(700)
            def rapid_toggle():
                for _ in range(rng.randint(3, 6)):
                    safe(nav("structure"), 800)

            actions = [structure, global_, settings_nav, gear, select, close_btn, ws_close, escape, backdrop, double_click_section,
                       rapid_toggle, structure, global_, gear, escape]
            cycles = 0
            for i in range(110):
                action = rng.choice(actions)
                action()
                settle()
                cycles += 1
                audit = page.evaluate(AUDIT_JS)
                self.assertEqual(_violations(audit, base), [], f"transition {i} ({action.__name__}): {audit}")
                if i % 25 == 24:
                    page.evaluate("RastiSiR4.refreshStructure()")      # structure refresh in the middle of the storm
                    page.wait_for_timeout(500)
                    self.assertEqual(_violations(page.evaluate(AUDIT_JS), base), [])
                if i % 11 == 10:
                    calm()                                              # keep the in-process SQLite test server calm
            # template peek round trips (heavy server renders: sequential, not randomised)
            for _ in range(3):
                safe(nav("templates"))
                page.wait_for_selector('[data-rastisi-action="preview-template"]:not([disabled])')
                page.locator('[data-rastisi-action="preview-template"]:not([disabled])').first.click()
                page.wait_for_function("document.querySelector('.rs-studio').dataset.rsDrawer==='template-preview'", timeout=15000)
                calm()
                audit = page.evaluate(AUDIT_JS)
                self.assertEqual(audit["visName"], "template-preview")
                self.assertEqual(audit["content"]["template-preview"], True)
                safe(page.locator('[data-rastisi-action="cancel-template-preview"]'))
                page.wait_for_function("document.querySelector('.rs-studio').dataset.rsDrawer==='closed'", timeout=15000)
                calm()
                self.assertEqual(_violations(page.evaluate(AUDIT_JS), base), [])
            self.assertGreaterEqual(cycles, 100)
            self.assertEqual(self.errors, [])
        finally:
            context.close()


# this module reuses the parity module's fixture (store, draft, live server, browser) but must not re-run its tests
for _name in [n for n in dir(_parity.EngineGeometryParityBrowserTests) if n.startswith("test_") and n not in StudioDirectEditBrowserTests.__dict__]:
    setattr(StudioDirectEditBrowserTests, _name, None)
