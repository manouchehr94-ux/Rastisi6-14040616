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

    def _close_inspector(self, page):
        page.click(".vs-workspace .r4-ws-close")
        page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)

    def _open_a_section_with_a_text_field(self, page):
        rows = page.locator(".tree-row .rs-row-select")
        for index in range(min(rows.count(), 14)):
            rows.nth(index).click()
            page.wait_for_selector("#r4Inspector [data-r4-section-inspector]", timeout=8000)
            page.wait_for_timeout(500)
            field = page.locator(self.SECTION_FIELD)
            if field.count() and field.first.is_visible():
                return field.first
            self._close_inspector(page)
            page.wait_for_timeout(300)
        self.fail("no section with a text field was found")

    def _settled(self, page):
        self._until(page, "()=>true", "preview")
        page.wait_for_function("() => !window.RastiSiR4.previewRefreshBusy() && window.RastiSiR4.saveState === 'saved'", timeout=15000)

    def _open_category(self, page, category):
        if not page.locator('[data-vs-pane="design"]').is_visible():
            page.click('[data-vs-tab-button="design"]')
        page.click(f'[data-vs-open-cat="{category}"]')
        page.wait_for_selector(".vs-design-modal", state="visible")
        page.wait_for_timeout(500)

    def _close_category(self, page):
        page.click(".vs-design-modal [data-vs-design-head] [data-rastisi-action='panel-close']")
        page.wait_for_selector(".vs-design-modal", state="hidden")

    def _visible_switches(self, page, scope):
        return page.evaluate(
            """(scope) => [...document.querySelectorAll(scope + ' input.r4-switch, ' + scope + ' button.switch')]
              .filter(c => c.getClientRects().length)
              .map(c => ({on: c.tagName === 'INPUT' ? c.checked : c.getAttribute('aria-pressed') === 'true', disabled: c.disabled,
                          text: c.__vsText ? c.__vsText.textContent : null,
                          label: (c.closest('label, .r4-field, .r4-repeater-subfield, .r4-checkbox-row, .toggle-row') || c.parentElement).textContent.replace(/\\s+/g, ' ').trim()}))""",
            scope,
        )

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

    def test_a_sections_settings_open_in_a_large_modal_and_edit_refresh_undo_redo_work(self):
        context, page = self._studio()
        field = self._open_a_section_with_a_text_field(page)
        geometry = page.evaluate(
            """()=>{const b=document.querySelector('.vs-workspace .r4-ws').getBoundingClientRect();
              return {w:b.width,h:b.height,vh:innerHeight,vw:innerWidth,title:document.querySelector('.vs-workspace .r4-ws-title, .vs-workspace .r4-ws-head h3, .vs-workspace .r4-ws-head h2').textContent.trim()}}"""
        )
        self.assertGreaterEqual(geometry["w"], 800)
        self.assertLessEqual(geometry["w"], 1000)
        self.assertLessEqual(geometry["h"], geometry["vh"] * 0.92)
        self.assertTrue(geometry["title"], "the dialog names the element being edited")
        self.assertTrue(page.locator(".vs-workspace .r4-ws-close").is_visible())
        self.assertTrue(page.locator(".vs-workspace [data-vs-modal-status], .vs-workspace .r4-ws-save").first.is_visible(), "saving status is visible")
        before = field.input_value()
        revision = page.evaluate("RastiSiR4.revision")
        changed = "7" if before != "7" else "5"
        field.fill(changed)
        field.blur()
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        self._shot(page, "vision_02_section_settings_in_a_large_modal")
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        reopened = self._open_a_section_with_a_text_field(page)
        self.assertEqual(reopened.input_value(), changed, "the saved value must survive a refresh")
        self._close_inspector(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        page.wait_for_selector("#r4PreviewFrame")
        self.assertEqual(self._open_a_section_with_a_text_field(page).input_value(), before)
        self._close_inspector(page)
        page.click("#r4RedoButton")
        page.wait_for_timeout(2500)
        page.wait_for_selector("#r4PreviewFrame")
        self.assertEqual(self._open_a_section_with_a_text_field(page).input_value(), changed)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [], "no 4xx (404/403/409/CSRF) from any Studio request")
        context.close()

    def test_escape_and_the_close_button_close_a_sections_modal_and_give_focus_back(self):
        context, page = self._studio()
        self._open_a_section_with_a_text_field(page)
        self.assertTrue(page.locator(".vs-workspace").is_visible())
        page.click(".vs-workspace .r4-ws-close")
        page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)
        self.assertFalse(page.locator(".vs-workspace").is_visible())
        self.assertEqual(page.locator(".tree-row.is-open").count(), 0)
        self._open_a_section_with_a_text_field(page)
        self.assertEqual(page.locator(".tree-row.is-open").count(), 1, "the open section stays highlighted in the navigator")
        page.keyboard.press("Escape")
        page.wait_for_function("() => !window.RastiSiR4.inspectorOpen", timeout=8000)
        page.wait_for_timeout(300)
        self.assertTrue(page.evaluate("document.activeElement.classList.contains('rs-row-select')"), "focus returns to the row that opened the modal")
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
            self._close_inspector(page)
        self.assertTrue(opened, "a section with a product/resource picker was not found")
        page.wait_for_selector("#r4ResourcePicker [data-r4-picker-root] .r4-picker-dialog", state="visible", timeout=10000)
        page.wait_for_timeout(600)
        self.assertGreater(page.locator(".r4-picker-dialog button").count(), 3)
        self._shot(page, "vision_05_resource_picker")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [], "the picker request goes to .../vision-studio/resources/picker/ and succeeds")
        context.close()

    def test_the_design_tab_is_an_ordered_list_and_each_row_opens_only_its_own_large_modal(self):
        context, page = self._studio()
        page.click('[data-vs-tab-button="design"]')
        cards = page.locator('[data-vs-pane="design"] [data-vs-open-cat]')
        titles = [t.strip() for t in cards.evaluate_all("els=>els.map(e=>e.querySelector('strong').textContent)")]
        self.assertEqual(
            titles[:8],
            ["برند و رنگ‌ها", "نوع نوشته و فونت‌ها", "دکمه‌ها", "شکل و تراکم", "تصاویر و رسانه‌ها", "سربرگ فروشگاه", "پابرگ فروشگاه", "ناوبری موبایل"],
        )
        self.assertEqual(page.locator("[data-vs-summary]").first.inner_text().strip() != "", True, "each row summarises the current value")
        self._shot(page, "vision_06_design_list")
        # what each category's dialog may show (the real control ids / fields of the one R4 Global Design panel)
        expectations = {
            "colors": ("input[data-r4-global-field='palette_slug']", ["#r4GlobalFont", "#r4GlobalHeaderVariant", "#r4GlobalFooterVariant"]),
            "typography": ("#r4GlobalFont", ["input[data-r4-global-field='palette_slug']", "#r4GlobalHeaderVariant"]),
            "header": ("#r4GlobalHeaderVariant", ["#r4GlobalFont", "#r4GlobalFooterVariant"]),
            "footer": ("#r4GlobalFooterVariant", ["#r4GlobalFont", "#r4GlobalHeaderVariant"]),
        }
        for category, (shown, hidden) in expectations.items():
            self._open_category(page, category)
            geometry = page.evaluate("()=>{const b=document.querySelector('.vs-design-modal').getBoundingClientRect();return {w:b.width,h:b.height,vh:innerHeight}}")
            self.assertGreaterEqual(geometry["w"], 800, category)
            self.assertLessEqual(geometry["w"], 1000, category)
            self.assertLessEqual(geometry["h"], geometry["vh"] * 0.92, category)
            self.assertTrue(page.locator(shown).first.is_visible(), f"{category} shows {shown}")
            for selector in hidden:
                self.assertFalse(page.locator(selector).first.is_visible(), f"{category} must not show {selector}")
            self.assertEqual(page.locator(".vs-design-modal [data-vs-design-title]").inner_text().strip(), dict(zip(["colors", "typography", "buttons", "shape", "images", "header", "footer", "bottom_nav"], titles))[category])
            page.keyboard.press("Escape")
            page.wait_for_selector(".vs-design-modal", state="hidden")
            page.wait_for_timeout(200)
            self.assertEqual(
                page.evaluate("document.activeElement.getAttribute('data-vs-open-cat')"), category, f"focus returns to the {category} row after Escape"
            )
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_header_and_footer_variants_are_chosen_from_the_design_list_and_persist(self):
        context, page = self._studio()
        for region, select_id in (("header", "r4GlobalHeaderVariant"), ("footer", "r4GlobalFooterVariant")):
            self._open_category(page, region)
            page.wait_for_selector(f"#{select_id}", state="visible")
            options = page.eval_on_selector(f"#{select_id}", "s=>[...s.options].map(o=>o.value)")
            current = page.eval_on_selector(f"#{select_id}", "s=>s.value")
            target = next(value for value in options if value != current)
            revision = page.evaluate("RastiSiR4.revision")
            page.select_option(f"#{select_id}", target)
            self._settled(page)
            self.assertGreater(page.evaluate("RastiSiR4.revision"), revision, region)
            self._close_category(page)
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            self._open_category(page, region)
            self.assertEqual(page.eval_on_selector(f"#{select_id}", "s=>s.value"), target, f"{region} variant must survive a refresh")
            self._close_category(page)
        self._shot(page, "vision_03_footer_from_the_design_list")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_the_shape_category_changes_the_real_appearance_and_survives_refresh_and_undo(self):
        context, page = self._studio()
        self._open_category(page, "shape")
        select = page.locator("#r4GlobalDensity")
        options = page.eval_on_selector("#r4GlobalDensity", "s=>[...s.options].map(o=>o.value)")
        current = select.input_value()
        target = next(v for v in options if v != current)
        revision = page.evaluate("RastiSiR4.revision")
        select.select_option(target)
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        page.reload(wait_until="networkidle")
        self._open_category(page, "shape")
        self.assertEqual(page.locator("#r4GlobalDensity").input_value(), target)
        self._close_category(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "shape")
        self.assertEqual(page.locator("#r4GlobalDensity").input_value(), current)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_the_colours_modal_offers_rich_real_palettes_and_saves_the_choice(self):
        context, page = self._studio()
        self._open_category(page, "colors")
        cards = page.locator("#r4GlobalDesign label.swatch")
        self.assertGreaterEqual(cards.count(), 24, "the real palette registry is shown in full")
        self.assertEqual(page.locator("#r4GlobalDesign label.swatch .vs-pal__bar i").count(), cards.count() * 6, "each card shows six real colours")
        self.assertGreaterEqual(page.locator("#r4GlobalDesign .r4-color-row").count(), 8, "main / complementary / accent / background / text colours")
        self._shot(page, "vision_07_colours_modal")
        current = page.eval_on_selector("input[data-r4-global-field='palette_slug']:checked", "i=>i.value")
        # search narrows the grid by name, an empty search shows everything again
        page.fill("[data-vs-palette-search]", "zzzz-no-such-palette")
        self.assertEqual(page.locator("#r4GlobalDesign label.swatch:visible").count(), 0)
        page.fill("[data-vs-palette-search]", "")
        self.assertGreaterEqual(page.locator("#r4GlobalDesign label.swatch:visible").count(), 24)
        target = page.evaluate(
            "(c)=>{const i=[...document.querySelectorAll('input[data-r4-global-field=palette_slug]')].find(x=>x.value!==c);return i.value}", current
        )
        revision = page.evaluate("RastiSiR4.revision")
        page.locator(f"#r4GlobalDesign label.swatch:has(input[value='{target}'])").scroll_into_view_if_needed()
        page.locator(f"#r4GlobalDesign label.swatch:has(input[value='{target}'])").click()
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        self.assertTrue(page.locator(f"#r4GlobalDesign label.swatch:has(input[value='{target}']:checked)").count() == 1)
        self._close_category(page)
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#r4PreviewFrame")
        self._open_category(page, "colors")
        self.assertEqual(page.eval_on_selector("input[data-r4-global-field='palette_slug']:checked", "i=>i.value"), target, "the palette is in the real Draft")
        self._close_category(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "colors")
        self.assertEqual(page.eval_on_selector("input[data-r4-global-field='palette_slug']:checked", "i=>i.value"), current)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_every_switch_states_its_value_in_words_and_follows_change_refresh_undo_redo(self):
        context, page = self._studio()
        self._open_category(page, "images")
        switches = self._visible_switches(page, "#r4GlobalDesign")
        self.assertGreaterEqual(len(switches), 2)
        for item in switches:
            self.assertIn(item["text"], ("روشن", "خاموش", "غیرفعال", "نمایش داده می‌شود", "پنهان است", "قفل است", "باز است"), item)
            self.assertEqual(item["text"] in ("روشن", "نمایش داده می‌شود", "قفل است"), item["on"] and not item["disabled"], item)
        # the visual state differs: knob on the other side + a different track colour
        zoom = page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom']")
        look = "(el)=>{const k=getComputedStyle(el,'::after'),t=getComputedStyle(el);return [t.backgroundColor,k.transform,el.checked]}"
        was_on = zoom.is_checked()
        off_look = zoom.evaluate(look)
        revision = page.evaluate("RastiSiR4.revision")
        zoom.click()
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        self.assertNotEqual(zoom.evaluate(look)[:2], off_look[:2], "track colour / knob position change with the value")
        self.assertEqual(zoom.is_checked(), not was_on)
        self.assertEqual(page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom'] + .vs-sw-text").inner_text(), "خاموش" if was_on else "روشن")
        self._shot(page, "vision_08_switch_states")
        self._close_category(page)
        page.reload(wait_until="networkidle")
        self._open_category(page, "images")
        self.assertEqual(page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom']").is_checked(), not was_on, "refresh keeps the stored value")
        self._close_category(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "images")
        self.assertEqual(page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom']").is_checked(), was_on, "Undo restores the previous state and look")
        self.assertEqual(page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom'] + .vs-sw-text").inner_text(), "روشن" if was_on else "خاموش")
        self._close_category(page)
        page.click("#r4RedoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "images")
        self.assertEqual(page.locator("#r4GlobalDesign input[data-r4-global-field='card_image_zoom']").is_checked(), not was_on, "Redo")
        self._close_category(page)
        # section settings: every visible switch states its value too, and «hide» switches keep the backend meaning (on = hidden)
        rows = page.locator(".tree-row .rs-row-select")
        seen = 0
        for index in range(min(rows.count(), 12)):
            rows.nth(index).click()
            page.wait_for_selector("#r4Inspector [data-r4-section-inspector]", timeout=8000)
            page.wait_for_timeout(500)
            for item in self._visible_switches(page, "#r4Inspector"):
                seen += 1
                self.assertTrue(item["text"], item)
                if item["label"].startswith(("پنهان", "مخفی")) and not item["disabled"]:
                    self.assertEqual(item["text"], "پنهان است" if item["on"] else "نمایش داده می‌شود", item)
            self._close_inspector(page)
        self.assertGreater(seen, 0)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_a_failed_save_keeps_the_modal_open_instead_of_dropping_the_change(self):
        context, page = self._studio()
        self._open_category(page, "shape")
        page.route("**/mutate/", lambda route: route.abort())
        select = page.locator("#r4GlobalDensity")
        options = page.eval_on_selector("#r4GlobalDensity", "s=>[...s.options].map(o=>o.value)")
        select.select_option(next(v for v in options if v != select.input_value()))
        page.wait_for_function("() => ['error','conflict'].includes(window.RastiSiR4.saveState)", timeout=15000)
        page.click(".vs-design-modal [data-vs-design-head] [data-rastisi-action='panel-close']")
        page.wait_for_timeout(500)
        self.assertTrue(page.locator(".vs-design-modal").is_visible(), "an unsaved change keeps the dialog open")
        self.assertIn(page.locator(".vs-design-modal [data-vs-modal-status]").first.get_attribute("data-state"), ("error", "conflict"))
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

    def test_the_phone_layout_shows_the_store_at_phone_width_with_full_screen_modals(self):
        context, page = self._studio(viewport=(390, 844))
        self.assertEqual(page.evaluate("RastiSiR4.getDevice()"), "mobile")
        self.assertFalse(page.locator(".vs-nav").is_visible())
        page.click('[data-vs-toggle="nav"]')
        self.assertTrue(page.locator(".vs-nav").is_visible())
        page.click('[data-vs-toggle="nav"]')
        page.click('[data-vs-toggle="panel"]')
        self.assertTrue(page.locator(".vs-panel").is_visible())
        self._open_category(page, "colors")
        box = page.evaluate("()=>{const b=document.querySelector('.vs-design-modal').getBoundingClientRect();return {w:b.width,h:b.height,vw:innerWidth,vh:innerHeight}}")
        self.assertGreaterEqual(box["w"], box["vw"] * 0.95, "near full-screen on a phone")
        self.assertGreaterEqual(box["h"], box["vh"] * 0.9)
        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), "no horizontal page scroll")
        self._shot(page, "vision_04_phone_colours_modal")
        self.assertEqual(self.errors, [])
        context.close()

    def test_the_modals_hold_up_at_every_desktop_and_tablet_width(self):
        for width, height in ((1920, 1080), (1440, 900), (768, 1024)):
            context, page = self._studio(viewport=(width, height))
            if width <= 1023:
                page.click('[data-vs-toggle="panel"]')
            self._open_category(page, "colors")
            box = page.evaluate("()=>{const b=document.querySelector('.vs-design-modal').getBoundingClientRect();return {l:b.left,r:b.right,t:b.top,b:b.bottom,vw:innerWidth,vh:innerHeight}}")
            self.assertGreaterEqual(box["l"], 0, width)
            self.assertLessEqual(box["r"], box["vw"] + 1, width)
            self.assertLessEqual(box["b"], box["vh"] + 1, width)
            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), f"{width}: no horizontal page scroll")
            self._close_category(page)
            self.assertEqual(self.errors, [], width)
            context.close()


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class VisionComposerScenarioTests(_VisionPage, _composer.ComposerScenarioTests):
    """The Composer scenarios A-H, unchanged, against Vision (``_studio`` opens the Vision page)."""
