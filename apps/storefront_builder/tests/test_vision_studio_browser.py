"""Real-browser proof (Chromium + Playwright) that RastiSi Vision Studio drives the one R4 engine.

Two layers, both opt-in (``SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests python manage.py test
apps.storefront_builder.tests.test_vision_studio_browser``, isolated ``DJANGO_MEDIA_ROOT``):

* ``VisionBrowserTests`` - the Vision-specific journey: the sidebar «استودیو» entry, the real Preview inside the canvas, a section's
  settings in the properties panel, edit -> refresh -> Undo -> Redo, header / footer variants as elements, the network log (no 4xx,
  no JavaScript error) and the phone layout.
* ``VisionComposerScenarioTests`` - the V5 Composer scenarios A-H, UNCHANGED, run against the Vision page (only the URL differs):
  free nested layouts, Group design, proportional resize with Undo/refresh, registry components, header/footer on the canvas, the
  build/edit/refresh/undo/redo/draft-preview journey. If Vision broke a single hook the Composer, the resize handles or the dialogs rely
  on, one of these fails.

Every assertion reads what the seller sees (Preview iframe, Studio panels, network); nothing calls the ORM while the Studio works."""

import json
import os
import unittest

from . import test_v5_composer_browser as _composer
from . import test_v5_studio_composition_browser as _studio_tests

VISION = "/admin-portal/vision-studio/"
SHOTS = _studio_tests.SHOTS


class _VisionPage:
    """Opens the Vision page instead of the R4 one and records every failed request / JavaScript error."""

    def _studio(self, page_param="home", viewport=(1440, 900)):
        if viewport == (1440, 900):
            # Vision's canvas is narrower by its two side columns (navigator 255 + panel 300); at 1920x1080 the Preview is scaled like
            # R4's own 1440-wide canvas, so the Composer's chips / handles are the same size to hit.
            viewport = (1920, 1080)
        context = self.browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, locale="fa-IR")
        context.add_cookies([self.cookie])
        page = context.new_page()
        self.errors = []
        self.failed = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("response", lambda r: self.failed.append((r.status, r.url)) if r.status >= 400 and "/admin-portal/" in r.url else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(f"{self.base}{VISION}?page={page_param}", wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        page.wait_for_timeout(1500)
        return context, page


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class VisionBrowserTests(_VisionPage, _composer.ComposerBrowserTests):
    SECTION_FIELD = "#r4Inspector input[id^='r4Field-'][type='text']"

    def _open_a_section_with_a_text_field(self, page):
        rows = page.locator(".tree-row .rs-row-select")
        for index in range(min(rows.count(), 14)):
            rows.nth(index).click()
            page.wait_for_selector("#r4Inspector [data-r4-section-inspector]", timeout=8000)
            page.wait_for_timeout(500)
            field = page.locator(self.SECTION_FIELD)
            if field.count() and field.first.is_visible():
                return field.first
            page.click(".vs-workspace .vs-back")
            page.wait_for_timeout(300)
        self.fail("no section with a text field was found")

    def _settled(self, page):
        self._until(page, "()=>true", "preview")
        page.wait_for_function("() => !window.RastiSiR4.previewRefreshBusy() && window.RastiSiR4.saveState === 'saved'", timeout=15000)

    def test_the_sidebar_entry_opens_vision_with_the_real_preview_in_the_canvas(self):
        context = self.browser.new_context(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        context.add_cookies([self.cookie])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{self.base}/admin-portal/", wait_until="networkidle")
        entry = page.locator('.sidebar nav.nav a.nav-item[data-section="studio"]')
        self.assertEqual(entry.count(), 1)
        self.assertEqual(entry.locator(".nav-item-label").inner_text().strip(), "استودیو")
        entry.click()
        page.wait_for_selector(".rs-studio.vs[data-r4-shell]")
        self.assertTrue(page.url.rstrip("/").endswith("/admin-portal/vision-studio"))
        frame = self._frame(page)
        self.assertGreater(frame.locator(".rcontainer").count(), 0)
        # the preview lives INSIDE the canvas column, between the navigator and the properties panel
        boxes = page.evaluate("""()=>{const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return [b.left,b.right,b.top,b.bottom]};
          return {nav:r('.vs-nav'),frame:r('#r4PreviewFrame'),panel:r('.vs-panel'),bar:r('.vs-bar')}}""")
        self.assertLess(boxes["nav"][1], boxes["frame"][1] + 1)
        self.assertGreater(boxes["panel"][0] + 1, boxes["frame"][0])
        self.assertAlmostEqual(boxes["bar"][3] - boxes["bar"][2], 52, delta=1)
        self.assertAlmostEqual(boxes["nav"][1] - boxes["nav"][0], 255, delta=1)
        self.assertAlmostEqual(boxes["panel"][1] - boxes["panel"][0], 300, delta=1)
        self._shot(page, "vision_01_opened_from_the_sidebar")
        self.assertEqual(errors, [])
        context.close()

    def test_edit_refresh_undo_redo_through_the_properties_panel_with_a_clean_network_log(self):
        context, page = self._studio()
        field = self._open_a_section_with_a_text_field(page)
        before = field.input_value()
        revision = page.evaluate("RastiSiR4.revision")
        changed = "7" if before != "7" else "5"
        field.fill(changed)
        field.blur()
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        self._shot(page, "vision_02_section_settings_in_the_panel")
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        reopened = self._open_a_section_with_a_text_field(page)
        self.assertEqual(reopened.input_value(), changed, "the saved value must survive a refresh")
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        page.wait_for_selector("#r4PreviewFrame")
        self.assertEqual(self._open_a_section_with_a_text_field(page).input_value(), before)
        page.click("#r4RedoButton")
        page.wait_for_timeout(2500)
        page.wait_for_selector("#r4PreviewFrame")
        self.assertEqual(self._open_a_section_with_a_text_field(page).input_value(), changed)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [], "no 4xx (404/403/409/CSRF) from any Studio request")
        context.close()

    def test_the_back_button_and_escape_return_from_a_sections_settings_to_the_tabs(self):
        context, page = self._studio()
        self._open_a_section_with_a_text_field(page)
        self.assertTrue(page.locator(".vs-workspace").is_visible())
        self.assertTrue(page.evaluate("RastiSiR4.inspectorOpen"))
        page.click(".vs-workspace .vs-back")
        page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)
        self.assertFalse(page.locator(".vs-workspace").is_visible())
        self.assertTrue(page.locator('[data-vs-tab-button="templates"]').is_visible())
        self.assertEqual(page.locator(".tree-row.is-open").count(), 0)
        self._open_a_section_with_a_text_field(page)
        self.assertEqual(page.locator(".tree-row.is-open").count(), 1, "the open section stays highlighted in the navigator")
        page.keyboard.press("Escape")
        page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)
        self.assertEqual(self.errors, [])
        context.close()

    def test_the_resource_picker_opens_from_a_sections_settings_and_loads_through_the_vision_alias(self):
        context, page = self._studio()
        rows = page.locator(".tree-row .rs-row-select")
        opened = False
        for index in range(min(rows.count(), 14)):
            rows.nth(index).click()
            page.wait_for_selector("#r4Inspector [data-r4-section-inspector]", timeout=8000)
            page.wait_for_timeout(400)
            trigger = page.locator("#r4Inspector [data-r4-resource-picker-open]")
            if trigger.count() and trigger.first.is_visible():
                trigger.first.click()
                opened = True
                break
            page.click(".vs-workspace .vs-back")
            page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)
        self.assertTrue(opened, "a section with a product/resource picker was not found")
        page.wait_for_selector("#r4ResourcePicker [data-r4-picker-root] .r4-picker-dialog", state="visible", timeout=10000)
        page.wait_for_timeout(600)
        self.assertGreater(page.locator(".r4-picker-dialog button").count(), 3)
        self._shot(page, "vision_05_resource_picker")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [], "the picker request goes to .../vision-studio/resources/picker/ and succeeds")
        context.close()

    def test_header_and_footer_variants_are_chosen_as_elements_and_persist(self):
        context, page = self._studio()
        for region, select_id, name in (("header", "r4GlobalHeaderVariant", "سربرگ فروشگاه"), ("footer", "r4GlobalFooterVariant", "پایین صفحه (فوتر)")):
            page.click(f'.vs-regions [data-vs-region="{region}"]') if page.locator(".vs-regions").is_visible() else None
            if not page.locator(f"#{select_id}").is_visible():
                page.click('[data-vs-tab-button="design"]')
                page.click(f'.vs-regions [data-vs-region="{region}"]')
            page.wait_for_selector(f"#{select_id}", state="visible")
            self.assertEqual(page.locator("[data-vs-focus-name]").inner_text().strip(), name)
            options = page.eval_on_selector(f"#{select_id}", "s=>[...s.options].map(o=>o.value)")
            current = page.eval_on_selector(f"#{select_id}", "s=>s.value")
            target = next(value for value in options if value != current)
            revision = page.evaluate("RastiSiR4.revision")
            page.select_option(f"#{select_id}", target)
            self._settled(page)
            self.assertGreater(page.evaluate("RastiSiR4.revision"), revision, region)
            page.click("[data-vs-focus-back]")
            page.wait_for_timeout(400)
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.click('[data-vs-tab-button="design"]')
            page.click(f'.vs-regions [data-vs-region="{region}"]')
            page.wait_for_selector(f"#{select_id}", state="visible")
            self.assertEqual(page.eval_on_selector(f"#{select_id}", "s=>s.value"), target, f"{region} variant must survive a refresh")
        self._shot(page, "vision_03_footer_as_an_element")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_the_global_design_panel_changes_the_real_appearance(self):
        context, page = self._studio()
        page.click('[data-vs-tab-button="design"]')
        page.wait_for_selector("#r4GlobalDesign", state="visible")
        page.locator("#rsGlobalDetails > summary").click()
        select = page.locator("#r4GlobalDensity")
        options = page.eval_on_selector("#r4GlobalDensity", "s=>[...s.options].map(o=>o.value)")
        current = select.input_value()
        target = next(v for v in options if v != current)
        revision = page.evaluate("RastiSiR4.revision")
        select.select_option(target)
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        page.reload(wait_until="networkidle")
        page.click('[data-vs-tab-button="design"]')
        page.locator("#rsGlobalDetails > summary").click()
        self.assertEqual(page.locator("#r4GlobalDensity").input_value(), target)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_templates_pane_and_unsupported_reference_settings_are_honest(self):
        context, page = self._studio()
        self.assertTrue(page.locator('[data-vs-pane="templates"]').is_visible())
        self.assertIn("در دست توسعه", page.locator('[data-vs-pane="templates"]').inner_text())
        for tab in ("motion", "seo", "blog"):
            page.click(f'[data-vs-tab-button="{tab}"]')
            self.assertTrue(page.locator(f'[data-vs-pane="{tab}"]').is_visible())
        page.click('[data-vs-tab-button="seo"]')
        self.assertEqual(page.locator('[data-vs-pane="seo"] input, [data-vs-pane="seo"] textarea').count(), 0)
        page.click('[data-vs-tab-button="templates"]')
        page.click('#vsPane-templates [data-rastisi-action="templates"]')
        page.wait_for_selector("[data-rs-modal-root] .rs-modal, [data-rs-modal-root] [role='dialog']", timeout=8000)
        context.close()

    def test_the_phone_layout_shows_the_store_at_phone_width_with_drawers(self):
        context, page = self._studio(viewport=(390, 844))
        self.assertEqual(page.evaluate("RastiSiR4.getDevice()"), "mobile")
        self.assertFalse(page.locator(".vs-nav").is_visible())
        page.click('[data-vs-toggle="nav"]')
        self.assertTrue(page.locator(".vs-nav").is_visible())
        page.click('[data-vs-toggle="nav"]')
        page.click('[data-vs-toggle="panel"]')
        self.assertTrue(page.locator(".vs-panel").is_visible())
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), "no horizontal page scroll")
        self._shot(page, "vision_04_phone")
        self.assertEqual(self.errors, [])
        context.close()


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class VisionComposerScenarioTests(_VisionPage, _composer.ComposerScenarioTests):
    """The Composer scenarios A-H, unchanged, against Vision (``_studio`` opens the Vision page)."""
