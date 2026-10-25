"""Real-browser proof that a seller BUILDS and CHANGES the V5 compositions with the Design Studio's own buttons (Chromium + Playwright).

Nothing here calls the mutation service: every change is made by clicking, typing, selecting or dragging in the Studio UI, exactly as a
seller does — the Studio's own JS sends the mutations. The results are then read back from the Draft, from the Preview iframe, and (after
the real «انتشار» button) from the PUBLISHED page at desktop and phone widths, together with the real Undo / Redo buttons.

Opt-in: ``SFB_BROWSER_TESTS=1 python manage.py test apps.storefront_builder.tests.test_v5_studio_composition_browser`` (isolated test
database; use an isolated ``DJANGO_MEDIA_ROOT``). Screenshots: ``SFB_SCREENSHOT_DIR``."""

import os
import time
import unittest
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.content.models import PromotionalBanner
from apps.storefront_builder.models import StorefrontContainer, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service

from . import test_engine_parity_browser as _parity   # a module alias: the fixture class must not be collected twice

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82")
SHOTS = Path(os.environ.get("SFB_SCREENSHOT_DIR", "/tmp/sfb-studio-browser"))
STUDIO = "/admin-portal/storefront-builder/r4/"


class _StudioFixture(_parity.EngineGeometryParityBrowserTests):
    """The parity module's fixture (a published stationery store, owner login cookie, Chromium) WITHOUT its own tests."""


for _name in [n for n in dir(_parity.EngineGeometryParityBrowserTests) if n.startswith("test")]:
    setattr(_StudioFixture, _name, None)          # not callable → the loader skips it


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class StudioCompositionBrowserTests(_StudioFixture):
    # the fixture (a published stationery store, owner login cookie, Chromium) comes from the parity module

    def setUp(self):
        super().setUp()
        # a store with real footer content: two link menus + a contact phone, so every footer column has something to place
        from apps.content.models import FooterSettings, Menu, MenuItem

        footer = FooterSettings.provision_for(self.store)
        footer.is_enabled = True
        footer.show_contact = True
        footer.phone = "09120000000"
        footer.save()
        for location, title, labels in (("footer_1", "لینک‌های مفید", ("درباره ما", "تماس با ما", "قوانین")),
                                         ("footer_2", "دسترسی سریع", ("پیگیری سفارش", "سوالات متداول"))):
            menu, _ = Menu.objects.get_or_create(store=self.store, location=location, defaults={"title": title, "is_active": True})
            for order, label in enumerate(labels):
                MenuItem.objects.create(menu=menu, title=label, display_order=order, is_active=True, destination_type="search")

    # -------------------------------------------------------------------------------------------- helpers
    # NOTE: the test database is an in-memory SQLite shared with the live server's threads, so this test never reads the ORM while the
    # Studio works; every assertion reads what the SELLER sees — the Preview iframe, the Studio's own panels, then the published page.
    def _studio(self, page_param="home", viewport=(1440, 900)):
        context = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale="fa-IR")
        context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{self.base}{STUDIO}?page={page_param}", wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        return context, page

    def _frame(self, page, seconds=15):
        """The Studio's own Preview iframe (#r4PreviewFrame) once its storefront document is there."""
        end = time.time() + seconds
        while time.time() < end:
            try:
                found = page.locator("#r4PreviewFrame").element_handle().content_frame()
                if found is not None:
                    found.wait_for_selector(".rcontainer, .pdp", timeout=3000)
                    return found
            except Exception:
                pass
            page.wait_for_timeout(300)
        self.fail("the Preview frame did not come back: " + str([f.url for f in page.frames]))

    def _until(self, page, js, what, arg=None, seconds=15):
        """Poll ``js`` (an arrow function over the Preview document) until it returns something truthy."""
        end = time.time() + seconds
        last = None
        while time.time() < end:
            try:
                last = self._frame(page, 5).evaluate(js, arg)
                if last:
                    return last
            except Exception:
                pass
            page.wait_for_timeout(300)
        self.fail(f"timed out waiting for: {what} (last={last!r})")

    ROWS_JS = """()=>[...document.querySelectorAll('.rcontainer[data-container-id]')].map(c=>({
        id:Number(c.dataset.containerId), layout:c.dataset.layout, mode:c.dataset.mobileMode, order:c.dataset.mobileOrder||'normal',
        spans:[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))),
        keys:[...c.querySelectorAll('.rsec[data-section-key]')].map(e=>e.dataset.sectionKey),
        ids:[...c.querySelectorAll('.rsec[data-section-key]')].map(e=>Number(e.dataset.sectionId))}))"""

    def _rows(self, page):
        return self._frame(page).evaluate(self.ROWS_JS)

    def _open_structure(self, page):
        if not page.locator("[data-rs-structure-scroll]").is_visible():
            page.click('[data-rastisi-action="structure"]')
        page.wait_for_selector("[data-rs-structure-scroll]", state="visible")

    def _shot(self, page, name, selector=None):
        SHOTS.mkdir(parents=True, exist_ok=True)
        if selector:
            page.locator(selector).first.screenshot(path=str(SHOTS / f"{name}.png"))
        else:
            page.screenshot(path=str(SHOTS / f"{name}.png"))

    def _banners(self, count=4):
        for n in range(count):
            row = PromotionalBanner(store=self.store, is_active=True, display_order=n, title=f"کارت {n + 1}")
            row.desktop_image = SimpleUploadedFile(f"c{n}.png", _PNG, content_type="image/png")
            row.save()

    def _add_row_with_the_dialog(self, page, layout, first, second):
        before = len(self._rows(page))
        self._open_structure(page)
        page.click("[data-rs-add-row-top]")
        page.wait_for_selector("[data-rs-add-row-form]")
        page.check(f'input[name="rs_row_layout"][value="{layout}"]')
        page.select_option("[data-rs-add-row-first]", first)
        page.select_option("[data-rs-add-row-second]", second)
        page.click("[data-rs-add-row-submit]")
        self._until(page, f"()=>document.querySelectorAll('.rcontainer[data-container-id]').length === {before + 1}", "the new row in the Preview")
        page.wait_for_timeout(1000)
        return self._rows(page)[-1]

    def _close_drawer(self, page):
        close = page.locator('[data-rastisi-action="panel-close"]')
        if close.count() and close.first.is_visible():
            close.first.click()
            page.wait_for_timeout(600)

    def _hover_container(self, page, container_id):
        self._close_drawer(page)
        frame = self._frame(page)
        frame.locator(f'.rcontainer[data-container-id="{container_id}"]').first.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        point = page.evaluate("""(id)=>{const f=document.getElementById('r4PreviewFrame'); const r=f.getBoundingClientRect(); const w=f.contentWindow;
          const c=f.contentDocument.querySelector('.rcontainer[data-container-id="'+id+'"]'); const b=c.getBoundingClientRect(); const k=r.width/w.innerWidth;
          return {x:r.x+(b.x+b.width/2)*k, y:r.y+(b.y+Math.min(b.height/2,60))*k}}""", container_id)
        page.mouse.move(point["x"] - 40, point["y"])
        page.mouse.move(point["x"], point["y"], steps=4)
        page.wait_for_timeout(900)


    def _container_group(self, page, container_id):
        self._open_structure(page)
        if not page.locator("details.rs-rows").evaluate("d => d.open"):
            page.locator("details.rs-rows > summary").click()
        group = page.locator(f'[data-r4-structure-container-row][data-r4-structure-container-id="{container_id}"]')
        settings = group.locator("details.rs-container-settings")
        if not settings.evaluate("d => d.open"):
            settings.locator("summary").click()
        return group

    def _publish(self, page):
        page.click("#r4PublishButton")
        page.wait_for_timeout(800)
        for selector in ("[data-rs-confirm-publish]", "[data-r4-publish-confirm]", 'dialog[open] button.primary', '[role="dialog"] button.primary'):
            button = page.locator(selector)
            if button.count() and button.first.is_visible():
                button.first.click()
                break
        page.wait_for_timeout(2500)

    def _public(self, path, width, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="fa-IR")
        page = context.new_page()
        page.goto(f"{self.public_base}{path}", wait_until="networkidle")
        page.wait_for_timeout(800)
        return context, page

    # -------------------------------------------------------------------------------------------- the tests
    def test_row_cell_widths_and_phone_behaviour_from_the_studio(self):
        self._banners(4)
        context, page = self._studio()
        try:
            # 1) build a two-cell row with the «ردیف دو‌ستونه» dialog: a card row on one side, text on the other
            row = self._add_row_with_the_dialog(page, "half", "multi_banner", "rich_text")
            self.assertEqual((row["spans"], row["keys"]), ([6, 6], ["multi_banner", "rich_text"]))
            cid = row["id"]

            # 2) change the column widths by DRAGGING the real handle between the cells (one mutation = one Undo step)
            self._hover_container(page, cid)
            handle = page.locator('[data-rs-handle="c"]').first
            handle.wait_for(state="visible", timeout=8000)
            box = handle.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 140, box["y"] + box["height"] / 2, steps=8)
            page.mouse.up()
            self._until(page, f"()=>{{const c=document.querySelector('.rcontainer[data-container-id=\"{cid}\"]');"
                              "return c && [...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>e.style.getPropertyValue('--cell-span')).join()!=='6,6'}", "dragged widths")
            dragged = next(r for r in self._rows(page) if r["id"] == cid)["spans"]
            self.assertEqual(sum(dragged), 12)
            self.assertNotEqual(dragged[0], dragged[1])

            # 3) the row's own phone settings from the structure panel: order = reverse, mode = horizontal slider
            page.wait_for_timeout(900)
            group = self._container_group(page, cid)
            group.locator('[data-r4-container-settings-field="mobile_order"]').select_option("reverse")
            self._until(page, f"()=>document.querySelector('.rcontainer[data-container-id=\"{cid}\"]').dataset.mobileOrder==='reverse'", "mobile order")
            page.wait_for_timeout(900)
            group = self._container_group(page, cid)
            group.locator('[data-r4-container-settings-field="mobile_mode"]').select_option("slider")
            self._until(page, f"()=>document.querySelector('.rcontainer[data-container-id=\"{cid}\"]').dataset.mobileMode==='slider'", "mobile slider")
            self._shot(page, "studio_row_preview")

            # 4) the real Undo / Redo buttons: the last edit goes away and comes back
            page.wait_for_timeout(900)
            # (Undo / Redo restore the Draft's rows, so the row is found again by what it holds, not by its old id)
            find = "[...document.querySelectorAll('.rcontainer[data-container-id]')].find(c=>[...c.querySelectorAll('.rsec[data-section-key]')].map(e=>e.dataset.sectionKey).join()==='multi_banner,rich_text')"
            page.click("#r4UndoButton")
            self._until(page, f"()=>{{const c={find}; return !!c && c.dataset.mobileMode!=='slider' && c.dataset.mobileOrder==='reverse'}}", "Undo of the slider mode only")
            page.wait_for_timeout(900)
            page.click("#r4RedoButton")
            self._until(page, f"()=>{{const c={find}; return !!c && c.dataset.mobileMode==='slider' && c.dataset.mobileOrder==='reverse'}}", "Redo of the slider mode")
            self.assertEqual(self.errors, [])

            # 5) the real «انتشار» button, then the PUBLISHED page at desktop and phone widths
            page.wait_for_timeout(900)
            self._publish(page)
        finally:
            context.close()
        sel = '.rcontainer[data-mobile-mode="slider"][data-mobile-order="reverse"]'
        facts = """(s)=>{const c=document.querySelector(s); if(!c) return null; const cells=[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>{const r=e.getBoundingClientRect();return {l:r.left,w:r.width,t:r.top}});
          return {cells, scroll:c.scrollWidth, client:c.clientWidth, ox:getComputedStyle(c).overflowX, vw:innerWidth}}"""
        ctx, pub = self._public("/", 1440)
        try:
            desktop = pub.evaluate(facts, sel)
            self.assertIsNotNone(desktop, "the published page lost the row")
            ratio = desktop["cells"][0]["w"] / desktop["cells"][1]["w"]
            self.assertAlmostEqual(ratio, dragged[0] / dragged[1], delta=0.25)       # the dragged widths reached the storefront
        finally:
            ctx.close()
        ctx, phone = self._public("/", 390, 800)
        try:
            mobile = phone.evaluate(facts, sel)
            self.assertIn(mobile["ox"], ("auto", "scroll"))                          # one card at a time: a horizontal slider
            self.assertGreater(mobile["scroll"], mobile["client"] + 20)
            self.assertGreater(mobile["cells"][0]["w"], mobile["vw"] * 0.7)
            # reverse: the SECOND cell (text) is the first one a phone visitor meets (RTL: the right-most)
            self.assertGreater(mobile["cells"][1]["l"], mobile["cells"][0]["l"])
        finally:
            ctx.close()

    def _open_section_workspace(self, page, section_id):
        self._open_structure(page)
        page.locator(f'[data-rastisi-action="select-section"][data-id="{section_id}"]').click()
        page.wait_for_selector('[data-rs-workspace]:not([hidden]) [data-r4-section-inspector]')
        page.wait_for_timeout(500)

    def _set_design(self, page, sub, prop, value):
        """The seller's path: workspace → «طراحی» tab → sub-tab → the property's own control."""
        page.click('[data-rs-workspace] [data-r4-tab="design"]')
        page.wait_for_timeout(300)
        page.click(f'[data-rs-workspace] [data-r4-sub="{sub}"]')
        page.wait_for_timeout(300)
        control = page.locator(f'[data-rs-workspace] [data-r4-design-prop="{prop}"] [data-r4-design-input]')
        control.scroll_into_view_if_needed()
        control.select_option(value)
        page.wait_for_timeout(900)

    def test_a_card_row_becomes_a_one_card_slider_on_phones_from_the_workspace(self):
        self._banners(4)
        context, page = self._studio()
        try:
            row = self._add_row_with_the_dialog(page, "half", "multi_banner", "rich_text")
            banner_id = row["ids"][0]
            self._open_section_workspace(page, banner_id)
            self._set_design(page, "images", "image_ratio", "portrait")
            self._set_design(page, "layout", "mobile_layout", "slider")
            self._until(page, "(id)=>{const e=document.querySelector('.rsec[data-section-id=\"'+id+'\"]'); return !!e && /\\bm-slider\\b/.test(e.dataset.d||'') && /\\bratio\\b/.test(e.dataset.d||'')}",
                        "the card row's phone slider + portrait ratio in the Preview", arg=banner_id)
            page.keyboard.press("Escape")
            page.wait_for_timeout(700)
            # the Undo button takes the phone layout away again, Redo brings it back (rows are found by content afterwards)
            page.click("#r4UndoButton")
            page.wait_for_timeout(1500)
            undone = self._frame(page).evaluate("()=>[...document.querySelectorAll('.rsec[data-section-key=\"multi_banner\"]')].map(e=>e.dataset.d||'')")
            self.assertFalse(any("m-slider" in d for d in undone), undone)
            page.click("#r4RedoButton")
            page.wait_for_timeout(1500)
            redone = self._frame(page).evaluate("()=>[...document.querySelectorAll('.rsec[data-section-key=\"multi_banner\"]')].map(e=>e.dataset.d||'')")
            self.assertTrue(any("m-slider" in d for d in redone), redone)
            self.assertEqual(self.errors, [])
            self._publish(page)
        finally:
            context.close()
        probe = """()=>{const e=[...document.querySelectorAll('.rsec[data-d~="m-slider"]')][0]; if(!e) return null;
          const scrollers=[e,...e.querySelectorAll('*')].filter(x=>['auto','scroll'].includes(getComputedStyle(x).overflowX)&&x.scrollWidth>x.clientWidth+20);
          const s=scrollers[0]; if(!s) return {found:true, scroller:false};
          const kids=[...s.children].map(c=>c.getBoundingClientRect().width).filter(w=>w>0);
          return {found:true, scroller:true, vw:innerWidth, first:kids[0], count:kids.length, snap:getComputedStyle(s).scrollSnapType}}"""
        ctx, phone = self._public("/", 390, 800)
        try:
            result = phone.evaluate(probe)
            self.assertTrue(result and result["found"], "the published page lost the card row")
            self.assertTrue(result["scroller"], "the card row is not a horizontal slider on a phone")
            self.assertGreater(result["first"], result["vw"] * 0.6)                  # one card (not four) fills the screen
            self.assertGreaterEqual(result["count"], 4)
            self._shot(phone, "published_card_slider_phone", ".rsec[data-d~=\"m-slider\"]")
        finally:
            ctx.close()
        ctx, desk = self._public("/", 1440)
        try:
            self.assertFalse(desk.evaluate("""()=>{const e=document.querySelector('.rsec[data-d~="m-slider"]');
              return [e,...e.querySelectorAll('*')].some(x=>['auto','scroll'].includes(getComputedStyle(x).overflowX)&&x.scrollWidth>x.clientWidth+20)}"""),
                             "the phone slider must not exist on the desktop")
        finally:
            ctx.close()

    def _footer_field(self, page, key, value):
        field = page.locator(f'#rsGlobalFooter input[data-r4-global-geometry-key="{key}"]')
        field.scroll_into_view_if_needed()
        field.fill(str(value))
        field.press("Tab")                                   # blur → the field's own change handler sends footer.update
        page.wait_for_timeout(1100)

    def test_footer_column_count_order_and_gap_from_the_studio(self):
        context, page = self._studio()
        try:
            self._open_structure(page)
            page.click('[data-rs-global-focus="footer"]')
            page.wait_for_selector("#rsGlobalFooter", state="visible")
            if not page.locator("#rsGlobalFooter").evaluate("d => d.open"):
                page.locator("#rsGlobalFooter > summary").click()
            page.select_option("#r4GlobalFooterVariant", "marketplace_dense")
            page.wait_for_timeout(1500)
            for key, value in (("order_contact", 1), ("order_about", 4), ("column_count", 3), ("column_gap", 44)):
                self._footer_field(page, key, value)
            self._until(page, "()=>{const f=document.querySelector('footer.gf'); const st=f?f.getAttribute('style')||'':''; "
                              "return st.includes('--gf-o-contact:1')&&st.includes('--gf-o-about:4')&&st.includes('--gf-cols:3')&&st.includes('--gf-col-gap:44px')}",
                        "the footer geometry in the Preview")
            # the real Undo button takes the last field (gap) away, Redo brings it back
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            page.click("#r4UndoButton")
            self._until(page, "()=>{const st=(document.querySelector('footer.gf')||{getAttribute(){return ''}}).getAttribute('style')||''; return !st.includes('--gf-col-gap:44px')&&st.includes('--gf-cols:3')}", "Undo of the gap")
            page.wait_for_timeout(900)
            page.click("#r4RedoButton")
            self._until(page, "()=>((document.querySelector('footer.gf')||{getAttribute(){return ''}}).getAttribute('style')||'').includes('--gf-col-gap:44px')", "Redo of the gap")
            self.assertEqual(self.errors, [])
            page.wait_for_timeout(900)
            self._publish(page)
        finally:
            context.close()
        facts = """()=>{const blocks=[...document.querySelectorAll('footer.gf [data-gf-block]')].map(e=>{const r=e.getBoundingClientRect();
            return {k:e.dataset.gfBlock,l:Math.round(r.left),r:Math.round(r.right),t:Math.round(r.top),w:Math.round(r.width)}});
          return {blocks, overflow:document.documentElement.scrollWidth-innerWidth, vw:innerWidth}}"""
        ctx, desk = self._public("/", 1440)
        try:
            data = desk.evaluate(facts)
            self.assertEqual(sorted(b["k"] for b in data["blocks"]), ["about", "categories", "contact", "links"])
            first_row = [b for b in data["blocks"] if b["t"] == min(x["t"] for x in data["blocks"])]
            self.assertEqual(len(first_row), 3, data)                                    # three columns on a desktop
            self.assertEqual(max(first_row, key=lambda b: b["r"])["k"], "contact")      # RTL: the first column is on the right
            self.assertEqual([b["k"] for b in data["blocks"] if b["t"] > first_row[0]["t"]], ["about"])   # order 4 wraps last
            self.assertLessEqual(data["overflow"], 0)
            self._shot(desk, "published_footer_desktop", "footer.gf")
        finally:
            ctx.close()
        for width in (390, 768):
            ctx, phone = self._public("/", width, 800)
            try:
                data = phone.evaluate(facts)
                self.assertLessEqual(data["overflow"], 0, f"{width}px: the footer scrolls sideways")
                columns = {b["l"] for b in data["blocks"]}
                self.assertLessEqual(len(columns), 3, f"{width}px: {data['blocks']}")
                top_row = [b for b in data["blocks"] if b["t"] == min(x["t"] for x in data["blocks"])]
                self.assertEqual(max(top_row, key=lambda b: b["r"])["k"], "contact", f"{width}px: contact must stay first")
                if width == 390:
                    self.assertTrue(all(b["w"] >= 120 for b in data["blocks"]), f"390px: a footer column is too narrow: {data['blocks']}")
                    self._shot(phone, "published_footer_phone", "footer.gf")
            finally:
                ctx.close()

    def test_the_phone_quick_buy_bar_never_covers_the_buy_controls_while_scrolling(self):
        from django.urls import reverse

        path = reverse("catalog:product-detail", args=["parity-0"])
        ctx, phone = self._public(path, 390, 800)
        try:
            height = phone.evaluate("document.documentElement.scrollHeight")
            probe = """async (y)=>{ scrollTo(0,y); await new Promise(r=>setTimeout(r,330));
              const bar=document.querySelector('.pdp-satc'); const cs=getComputedStyle(bar);
              const shown = cs.display!=='none' && cs.visibility!=='hidden';
              const b=bar.getBoundingClientRect(); const covered=[];
              if (shown) for (const sel of ['.pricebox','.opt-block','.qty','.pdp-actions']) for (const e of document.querySelectorAll(sel)) {
                if (e.hidden || bar.contains(e)) continue; const r=e.getBoundingClientRect();
                const ov=Math.min(b.bottom,r.bottom)-Math.max(b.top,r.top);
                if (ov>2 && r.height>0 && r.bottom>0 && r.top<innerHeight) covered.push([sel,Math.round(ov)]);}
              return {shown, covered}}"""
            shown_somewhere, hidden_somewhere = False, False
            for y in range(0, height, 60):
                result = phone.evaluate(probe, y)
                self.assertEqual(result["covered"], [], f"scrollY={y}: the quick-buy bar covers {result['covered']}")
                shown_somewhere |= result["shown"]
                hidden_somewhere |= not result["shown"]
            self.assertTrue(shown_somewhere, "the quick-buy bar must still appear when no buy control is under it")
            self.assertTrue(hidden_somewhere, "the bar should step aside while the buy controls are in its strip")
            # at the very end of the page the bar is back and the last content is not hidden behind it
            tail = phone.evaluate(probe, height)
            self.assertTrue(tail["shown"])
        finally:
            ctx.close()
        # the desktop width never sees the phone bar
        ctx, desk = self._public(path, 1280)
        try:
            self.assertEqual(desk.evaluate("getComputedStyle(document.querySelector('.pdp-satc')).display"), "none")
        finally:
            ctx.close()

    def _reveal(self, page, selector):
        """Walk the workspace the way a seller does (tab → sub-tab) until the control is on screen; returns its locator."""
        base = f'[data-rs-workspace] {selector}'
        for tab in page.evaluate('[...document.querySelectorAll("[data-rs-workspace] [data-r4-tab]")].map(e=>e.dataset.r4Tab)'):
            page.click(f'[data-rs-workspace] [data-r4-tab="{tab}"]')
            page.wait_for_timeout(250)
            subs = page.evaluate(f'[...document.querySelectorAll("[data-rs-workspace] [data-r4-tab-panel=\'{tab}\'] [data-r4-sub]")].map(e=>e.dataset.r4Sub)')
            for sub in [None] + subs:
                if sub:
                    page.click(f'[data-rs-workspace] [data-r4-sub="{sub}"]')
                    page.wait_for_timeout(250)
                loc = page.locator(base)
                if loc.count() and loc.first.is_visible():
                    return loc.first
        self.fail(f"the control {selector} is not reachable in the workspace")

    def _pdp_main_id(self, page):
        return self._frame(page).evaluate('()=>{const e=[...document.querySelectorAll(".rsec[data-section-key]")].find(x=>x.dataset.sectionKey==="product_main"); return e&&e.dataset.sectionId}')

    def _pdp_facts(self, page):
        return self._frame(page).evaluate("""()=>{const p=document.querySelector('.pdp'); if(!p) return null;
          return {order:p.dataset.infoOrder||'', pos:p.dataset.galleryPos||'', split:p.dataset.gallerySplit||'', style:p.getAttribute('style')||''}}""")

    def test_the_product_page_composition_and_block_order_from_the_workspace(self):
        from django.urls import reverse

        context, page = self._studio("product_detail")
        try:
            self._open_section_workspace(page, self._pdp_main_id(page))
            # 1) reorder the buy-column blocks with the repeater's own ↑ buttons: «اعتماد» (last) goes to the top, then «قیمت» second
            rows = self._reveal(page, '[data-r4-field-key="info_order"] [data-r4-repeater-row]')
            names = lambda: page.evaluate('[...document.querySelectorAll("[data-rs-workspace] [data-r4-field-key=info_order] [data-r4-repeater-row]")].map(r=>r.querySelector("[data-r4-repeater-subfield]").value)')
            before = names()
            self.assertEqual(before[-1], "trust")
            for _ in range(len(before) - 1):
                position = names().index("trust")
                if position == 0:
                    break
                page.locator('[data-rs-workspace] [data-r4-field-key="info_order"] [data-r4-repeater-row]').nth(position).locator("[data-r4-repeater-move-up]").click()
                page.wait_for_timeout(1000)
            self._until(page, "()=>{const p=document.querySelector('.pdp'); return !!p && p.dataset.infoOrder==='custom'}", "a custom block order in the Preview")
            first_now = names()[0]
            self.assertEqual(first_now, "trust")
            # 2) gallery to the far side + wider buy column, from the same workspace
            self._reveal(page, 'select[data-r4-field-key="gallery_position"]').select_option("end")
            page.wait_for_timeout(1000)
            self._reveal(page, 'select[data-r4-field-key="gallery_split"]').select_option("info_wide")
            page.wait_for_timeout(1000)
            self._until(page, "()=>{const p=document.querySelector('.pdp'); return !!p && p.dataset.galleryPos==='end' && p.dataset.gallerySplit==='info_wide'}", "gallery position + split in the Preview")
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            # 3) real Undo / Redo of the LAST edit (the split)
            page.click("#r4UndoButton")
            self._until(page, "()=>{const p=document.querySelector('.pdp'); return !!p && !p.dataset.gallerySplit && p.dataset.galleryPos==='end' && p.dataset.infoOrder==='custom'}", "Undo of the split only")
            page.wait_for_timeout(800)
            page.click("#r4RedoButton")
            self._until(page, "()=>{const p=document.querySelector('.pdp'); return !!p && p.dataset.gallerySplit==='info_wide'}", "Redo of the split")
            self.assertEqual(self.errors, [])
            page.wait_for_timeout(800)
            self._publish(page)
        finally:
            context.close()
        path = reverse("catalog:product-detail", args=["parity-0"])
        facts = """()=>{const r=(s)=>{const e=document.querySelector(s); if(!e) return null; const b=e.getBoundingClientRect(); return {t:Math.round(b.top+scrollY),l:Math.round(b.left),w:Math.round(b.width)}};
          const p=document.querySelector('.pdp');
          return {order:p.dataset.infoOrder, pos:p.dataset.galleryPos, split:p.dataset.gallerySplit, gallery:r('.gallery'), trust:r('[data-blk=trust]'), price:r('[data-blk=price]'),
                  actions:r('.pdp-actions[data-blk=actions]'), overflow:document.documentElement.scrollWidth-innerWidth}}"""
        for width in (1440, 390):
            ctx, public = self._public(path, width, 900)
            try:
                data = public.evaluate(facts)
                self.assertEqual((data["order"], data["pos"], data["split"]), ("custom", "end", "info_wide"))
                self.assertLess(data["trust"]["t"], data["price"]["t"], f"{width}px: trust must come before price {data}")
                self.assertLess(data["price"]["t"], data["actions"]["t"], f"{width}px: price must stay above the buttons {data}")
                self.assertLessEqual(data["overflow"], 0)
                if width == 1440:
                    info_left = min(data[k]["l"] for k in ("trust", "price"))
                    self.assertLess(data["gallery"]["l"], info_left, "gallery 'end' = the far (left, RTL) side")
                    self._shot(public, "published_pdp_desktop")
            finally:
                ctx.close()
