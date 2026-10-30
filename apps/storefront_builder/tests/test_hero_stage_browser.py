"""Real-browser (Chromium) acceptance of the Hero Stage templates (opt-in: ``SFB_BROWSER_TESTS=1``).

On a throw-away Store/database (the parity fixture): the real Studio → «قالب‌ها» gallery → «اعمال» on each of the four templates → the
stage's real Inspector (controls changed through the actual inputs, auto-saved) → reload (values persist) → Undo / Redo buttons → the
customer-view Draft preview → «انتشار» → the live storefront of the same Store at 320 / 390 / 768 / 1440: the header is inside the
stage, no horizontal scroll, the slot hide flags really hide, the picture is the Store's own. Firefox is not available in this
environment (Chromium only) — see the report for the Windows scenario."""

import os
import unittest

from apps.catalog.models import Category
from apps.content.models import MediaAsset
from apps.storefront_builder.models import StorefrontLayout

from . import test_engine_parity_browser as _parity
from .test_hero_stage_templates import TEMPLATES, _png

WIDTHS = (320, 390, 768, 1440)
LABELS = {  # the Persian gallery titles (registry label_fa) the tiles show
    "dual_atelier": "آتلیه دوپنل", "editorial_noir": "نشریهٔ نوآر", "glass_commerce": "تجارت شیشه‌ای",
    "asymmetric_canvas": "بوم نامتقارن",
}

STAGE_AUDIT = """()=>{
  const s=document.querySelector('.hs-stage'); if(!s) return null;
  const q=sel=>s.querySelector(sel); const vis=e=>!!e&&e.getBoundingClientRect().width>0&&getComputedStyle(e).display!=='none';
  const r=s.getBoundingClientRect(); const bg=s.querySelector('.hs-bg').getBoundingClientRect();
  return {header:!!q('.hs-header header'), headers:document.querySelectorAll('header').length, title:vis(q('.hs-title')),
    subtitle:vis(q('.hs-subtitle')), cta:vis(q('.hs-cta')), mode:s.dataset.hsHeader, layout:s.dataset.hsLayout, scrim:getComputedStyle(s).getPropertyValue('--hs-scrim').trim(),
    top:Math.round(r.top), width:Math.round(r.width), bgWidth:Math.round(bg.width), vw:innerWidth, scrollW:document.documentElement.scrollWidth, clientW:document.documentElement.clientWidth,
    imgs:[...s.querySelectorAll('.hs-panel img')].map(i=>i.getAttribute('src')), titleBox:q('.hs-title')?(({left,right})=>({left,right}))(q('.hs-title').getBoundingClientRect()):null}
}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class HeroStageBrowserTests(_parity.EngineGeometryParityBrowserTests):
    # run with -k (the parity fixture's own tests are inherited): SFB_BROWSER_TESTS=1 DATABASE_URL=<throw-away PostgreSQL> … -k test_every_template
    # (the Studio fires parallel autosave requests, which an in-memory SQLite test database cannot serve)
    def setUp(self):
        super().setUp()
        self.asset = MediaAsset.objects.create(store=self.store, image=_png("browser-stage.png", (30, 110, 160)))
        self.asset2 = MediaAsset.objects.create(store=self.store, image=_png("browser-stage-2.png", (160, 80, 30)))

    # -------------------------------------------------------------------------------------------- helpers
    def _studio(self, width=1440):
        context = self.browser.new_context(viewport={"width": width, "height": 1000}, locale="fa-IR")
        context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(f"{self.base}/admin-portal/storefront-builder/r4/", wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        return context, page

    def _frame(self, page):
        for _ in range(40):                                                # the Preview iframe is re-created by every full-frame refresh
            found = next((f for f in page.frames if f != page.main_frame and "/preview/" in f.url), None)
            if found is not None:
                return found
            page.wait_for_timeout(250)
        raise AssertionError("the Studio Preview iframe never appeared")

    def _stage_audit(self, page):
        """The Preview iframe is swapped by an atomic full-frame refresh after a stage edit (the header lives in the stage): re-acquire the frame
        and retry until the new document has settled."""
        last = None
        for _ in range(12):
            try:
                frame = self._frame(page)
                frame.wait_for_selector(".hs-stage", timeout=4000)
                return frame.evaluate(STAGE_AUDIT)
            except Exception as exc:                                       # the frame is being replaced
                last = exc
                page.wait_for_timeout(500)
        raise last

    def _apply_through_the_gallery(self, page, key):
        page.locator('[data-rastisi-action="templates"]').first.click()
        page.wait_for_selector("[data-rs-gallery-grid]")
        tile = page.locator(f'[data-rs-gallery-grid] button[data-rastisi-action="switch-template"][data-key="{key}"]')
        self.assertEqual(tile.count(), 1, f"the gallery must list {key}")
        title = page.locator(f'[data-rs-gallery-grid] article.template-tile:has(button[data-key="{key}"]) strong').first.inner_text()
        self.assertIn(LABELS[key], title)
        self.assertTrue(page.evaluate(
            "k=>!!document.querySelector(`[data-rs-gallery-grid] article:has(button[data-key=\"${k}\"]) .rs-real-thumb svg`)", key),
            "the tile shows the registry thumbnail")
        tile.click()
        confirm = page.locator('[data-rastisi-action="confirm-template-replace"]')
        try:
            confirm.wait_for(state="visible", timeout=2500)
            confirm.click()
        except Exception:
            pass                                                            # nothing to confirm on an empty Draft
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)

    def _open_stage_inspector(self, page):
        section_id = None
        for _ in range(12):                                                # a template apply reloads the Studio: the frame may be replaced mid-wait
            try:
                frame = self._frame(page)
                frame.wait_for_selector(".hs-stage", timeout=4000)
                section_id = frame.evaluate("document.querySelector('.rsec[data-section-key=hero_stage]').dataset.sectionId")
                frame.locator(f'[data-section-id="{section_id}"]').first.dblclick(position={"x": 40, "y": 300})
                break
            except Exception:                                              # noqa: BLE001 - the frame is being replaced; re-acquire it
                page.wait_for_timeout(500)
        self.assertIsNotNone(section_id, "the Preview never showed the stage")
        page.wait_for_selector('[data-rs-workspace]:not([hidden]) [data-r4-section-inspector]', timeout=10000)
        page.wait_for_timeout(600)
        return section_id

    def _set(self, page, key, value):
        control = page.locator(f'[data-rs-workspace] [data-r4-section-inspector] :is(select,input,textarea)[data-r4-field-key="{key}"]').first
        tag = control.evaluate("e=>e.tagName")
        if tag == "SELECT":
            control.select_option(value)
        else:
            control.fill(str(value))
            control.dispatch_event("change")
        page.wait_for_timeout(700)                                         # the Studio auto-saves each change

    def _value(self, page, key):
        return page.locator(f'[data-rs-workspace] [data-r4-section-inspector] :is(select,input,textarea)[data-r4-field-key="{key}"]').first.input_value()

    def _tab(self, page, name):
        page.locator("[data-rs-workspace] button", has_text=name).first.click()
        page.wait_for_timeout(300)

    def _live_audit(self, width):
        context, page = self._page(width, "/")
        try:
            return page.evaluate(STAGE_AUDIT), page
        finally:
            context.close()

    # -------------------------------------------------------------------------------------------- the acceptance chain
    def test_every_template_from_the_gallery_to_the_published_storefront(self):
        published_before = StorefrontLayout.objects.get(store=self.store).published_version_id
        for key in TEMPLATES:
            with self.subTest(template=key):
                context, page = self._studio()
                try:
                    self._apply_through_the_gallery(page, key)
                    # only the Draft changed: the published page is still the old design
                    self.assertEqual(StorefrontLayout.objects.get(store=self.store).published_version_id, published_before)
                    section_id = self._open_stage_inspector(page)
                    before = {k: self._value(page, k) for k in ("header_mode", "bg_layout", "scrim_strength", "content_valign", "button_label")}

                    new_mode = "overlay" if before["header_mode"] != "overlay" else "merged"
                    new_layout = "dual" if before["bg_layout"] != "dual" else "single"
                    new_valign = "top" if before["content_valign"] != "top" else "bottom"
                    # six controls through the real inputs: header mode, background panels, overlay strength, position, typography, CTA
                    self._set(page, "header_mode", new_mode)
                    self._set(page, "bg_layout", new_layout)
                    self._set(page, "scrim_strength", "73")
                    self._set(page, "content_valign", new_valign)
                    self._set(page, "button_label", "دکمهٔ مرورگر")
                    self._tab(page, "طراحی")                                # typography lives under طراحی ← چیدمان و فاصله‌ها
                    self._tab(page, "چیدمان و فاصله")
                    self._set(page, "title_size", "sm")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)

                    # the Preview iframe (the Studio canvas) shows the change at once
                    stage = self._stage_audit(page)
                    self.assertEqual((stage["mode"], stage["layout"], stage["scrim"]), (new_mode, new_layout, "0.73"))
                    self.assertTrue(stage["header"] and stage["headers"] == 1, "one header, inside the stage")

                    # reload: nothing is lost
                    page.reload(wait_until="networkidle")
                    page.wait_for_selector("#r4PreviewFrame")
                    page.wait_for_timeout(1500)
                    self._open_stage_inspector(page)
                    self.assertEqual(self._value(page, "header_mode"), new_mode)
                    self.assertEqual(self._value(page, "scrim_strength"), "73")
                    self.assertEqual(self._value(page, "button_label"), "دکمهٔ مرورگر")
                    page.keyboard.press("Escape")

                    # Undo / Redo (the real buttons): six edits above = six history steps; Undo walks back to the template's own values
                    for _ in range(6):
                        page.locator('[data-rastisi-action="undo"]').first.click()
                        page.wait_for_timeout(900)
                    undone = self._stage_audit(page)
                    self.assertEqual((undone["mode"], undone["layout"]), (before["header_mode"], before["bg_layout"]))
                    for _ in range(6):
                        page.locator('[data-rastisi-action="redo"]').first.click()
                        page.wait_for_timeout(900)
                    redone = self._stage_audit(page)
                    self.assertEqual((redone["mode"], redone["layout"], redone["scrim"]), (new_mode, new_layout, "0.73"))

                    # make the final state deterministic regardless of how many history steps Undo/Redo walked
                    self._open_stage_inspector(page)
                    self._set(page, "header_mode", new_mode)
                    self._set(page, "bg_layout", new_layout)
                    self._set(page, "scrim_strength", "73")
                    self._set(page, "button_label", "دکمهٔ مرورگر")
                    self._set(page, "bg_a_media_asset_id", str(self.asset.pk))
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)

                    # «پیش‌نمایش»: the customer view of the saved Draft
                    context.close()
                    context, draft_page = self._page(1440, "/admin-portal/storefront-builder/draft-preview/?page=home", authed=True)
                    draft = draft_page.evaluate(STAGE_AUDIT)
                    self.assertEqual((draft["mode"], draft["layout"]), (new_mode, new_layout))
                    self.assertEqual(draft["headers"], 1)

                    # publish through the Studio
                    context.close()
                    context, page = self._studio()
                    page.locator('[data-rastisi-action="publish"]').first.click()
                    page.wait_for_timeout(1500)
                    for confirm in page.locator('[data-rastisi-action^="confirm"], [data-rastisi-action="publish-confirm"]').all():
                        if confirm.is_visible():
                            confirm.click()
                            page.wait_for_timeout(1500)
                            break
                    page.wait_for_load_state("networkidle")
                    self.assertNotEqual(StorefrontLayout.objects.get(store=self.store).published_version_id, published_before)
                    published_before = StorefrontLayout.objects.get(store=self.store).published_version_id
                finally:
                    context.close()

                for width in WIDTHS:                                       # the live Storefront of the same Store
                    live, _ = self._live_audit(width)
                    self.assertIsNotNone(live, f"{key}@{width}: the stage must be live")
                    self.assertEqual((live["mode"], live["layout"], live["scrim"]), (new_mode, new_layout, "0.73"), f"{key}@{width}")
                    self.assertTrue(live["header"] and live["headers"] == 1, f"{key}@{width}: header inside the stage")
                    self.assertEqual(live["scrollW"], live["clientW"], f"{key}@{width}: no horizontal scroll")
                    self.assertTrue(live["title"], f"{key}@{width}: the headline is visible")
                    self.assertTrue(any(src and self.asset.image.url in src for src in live["imgs"]), f"{key}@{width}: the Store's own picture")
                    self.assertLessEqual(live["bgWidth"], live["vw"] + 1)
                    self.assertGreaterEqual(live["titleBox"]["left"], -1)
                    self.assertLessEqual(live["titleBox"]["right"], live["vw"] + 1)
                self.assertEqual(self.errors, [], key)

    def test_the_stage_hides_what_the_merchant_hides_on_each_device(self):
        context, page = self._studio()
        try:
            self._apply_through_the_gallery(page, "editorial_noir")
        finally:
            context.close()
        from apps.storefront_builder.services import layout_service as svc
        draft = svc.get_or_create_draft(self.store, user=self.user)
        stage = draft.get_page("home").sections.get(section_key="hero_stage")
        stage.settings = {**stage.settings, "slots": [
            {"key": "title"}, {"key": "subtitle", "hide_mobile": True}, {"key": "cta", "hide_tablet": True}]}
        stage.save(update_fields=["settings"])
        svc.publish(self.store, user=self.user)
        shown = {}
        for width in (390, 768, 1440):
            context, page = self._page(width, "/")
            try:
                shown[width] = page.evaluate(STAGE_AUDIT)
            finally:
                context.close()
        self.assertEqual((shown[390]["subtitle"], shown[390]["cta"]), (False, True))
        self.assertEqual((shown[768]["subtitle"], shown[768]["cta"]), (True, False))
        self.assertEqual((shown[1440]["subtitle"], shown[1440]["cta"]), (True, True))

    def test_an_existing_template_keeps_its_independent_header(self):
        context, page = self._page(1440, "/")                         # the fixture store runs a pre-existing template
        try:
            audit = page.evaluate("()=>({stage:!!document.querySelector('.hs-stage'),headers:document.querySelectorAll('header').length,"
                                  "first:document.querySelector('header').closest('main')===null})")
        finally:
            context.close()
        self.assertEqual(audit, {"stage": False, "headers": 1, "first": True})
