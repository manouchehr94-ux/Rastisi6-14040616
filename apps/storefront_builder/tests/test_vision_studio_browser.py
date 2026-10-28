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
              .map(c => ({stored: c.tagName === 'INPUT' ? c.checked : c.getAttribute('aria-pressed') === 'true',
                          shown: c.dataset.vsShown === 'on', inverted: !!c.__vsProxy, disabled: c.disabled,
                          text: c.__vsText ? c.__vsText.textContent : null,
                          proxy: c.__vsProxy ? c.__vsProxy.getAttribute('aria-checked') : null,
                          label: (c.closest('label, .r4-field, .r4-repeater-subfield, .r4-checkbox-row, .toggle-row') || c.parentElement).textContent.replace(/\\s+/g, ' ').trim()}))""",
            scope,
        )

    def _draft(self):
        from apps.storefront_builder.services import layout_service

        return layout_service.get_existing_draft(self.store)

    def _settings_of(self, region):
        draft = self._draft()
        return draft.effective_header_config() if region == "header" else draft.effective_footer_config()

    def _track(self, locator):
        return locator.evaluate("e=>{const s=getComputedStyle(e);return {bg:s.backgroundColor,border:s.borderTopStyle}}")

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

    # ---- the header / footer model galleries ---------------------------------------------------------------------------------------
    VARIANT_SELECT = {"header": "#r4GlobalHeaderVariant", "footer": "#r4GlobalFooterVariant"}

    def _gal(self, region):
        return f'.vs-gal[data-vs-gal="{region}"]'

    def _card(self, region, key):
        return self._gal(region) + f' .vs-gcard[data-key="{key}"]'

    def _other_key(self, page, region, prefer):
        current = page.eval_on_selector(self.VARIANT_SELECT[region], "s=>s.value")
        return prefer if current != prefer else next(
            i["key"] for i in __import__("apps.storefront_builder.vision_ux", fromlist=["x"]).gallery_data()[region]["items"] if i["key"] not in (current, prefer) and not i["same_as"]
        )

    def test_header_and_footer_galleries_show_every_registry_model_with_real_pictures(self):
        from apps.storefront_builder import vision_ux

        context, page = self._studio()
        for region_key, region in vision_ux.REGIONS.items():
            self._open_category(page, region_key)
            gallery = vision_ux.gallery_data()[region_key]["items"]
            cards = page.locator(self._gal(region_key) + " .vs-gcard")
            self.assertEqual(cards.count(), len(region.variants), "one card per registry model")
            found = cards.evaluate_all("els=>els.map(e=>[e.dataset.key,e.querySelector('h5').textContent])")
            self.assertEqual(sorted(found), sorted([[v.key, v.label_fa] for v in region.variants]))
            current = page.eval_on_selector(self.VARIANT_SELECT[region_key], "s=>s.value")
            badges = page.locator(self._gal(region_key) + " .vs-badge")
            self.assertEqual(badges.count(), 1, "exactly one «مدل فعلی»")
            self.assertEqual(badges.locator("xpath=ancestor::li").get_attribute("data-key"), current)
            self.assertEqual(page.locator(self._card(region_key, current) + " [data-vs-gal-pick]").is_disabled(), True)
            # every distinct model has its own picture, and every picture is really served
            distinct = cards.evaluate_all("els=>els.filter(e=>!e.classList.contains('is-twin')).map(e=>e.querySelector('.vs-gcard__media > img')?.getAttribute('src'))")
            self.assertTrue(all(distinct), distinct)
            self.assertEqual(len(set(distinct)), len(distinct), "distinct models never share a picture")
            for src in distinct:
                status, kind = page.evaluate("async u=>{const r=await fetch(u);return [r.status,r.headers.get('content-type')]}", src)
                self.assertEqual((status, kind), (200, "image/webp"), src)
            twins = [i for i in gallery if i["same_as"]]
            self.assertEqual(page.locator(self._gal(region_key) + " .vs-gal__twins .vs-gcard").count(), len(twins))
            for item in gallery:
                card = page.locator(self._card(region_key, item["key"]))
                if item["description"]:
                    self.assertEqual(card.locator(".vs-gcard__desc").text_content(), item["description"])
                if item["same_as"]:
                    self.assertIn(item["same_as_label"], card.locator(".vs-gcard__twin").text_content())
            self._shot(page, f"vision_11_{region_key}_gallery")
            self._close_category(page)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_the_large_view_is_a_read_only_live_preview(self):
        context, page = self._studio()
        seen = []
        page.on("request", lambda r: seen.append((r.method, r.url)))
        for region_key, prefer, marker in (("footer", "dark_tech", ".gf--dark"), ("header", "dark_tech", ".gh--dark")):
            self._open_category(page, region_key)
            key = self._other_key(page, region_key, prefer)
            before = (self._draft().edit_revision, self._settings_of(region_key))
            view = page.locator(self._card(region_key, key) + " [data-vs-gal-view]")
            view.scroll_into_view_if_needed()
            view.click()
            page.wait_for_selector("[data-vs-vp]:not([hidden])")
            frame = page.frame_locator("[data-vs-vp-frame]")
            frame.locator(f'[data-vs-region="{region_key}"][data-vs-candidate="1"]').wait_for(state="attached", timeout=15000)
            if key == prefer:
                self.assertGreater(frame.locator(marker).count(), 0, "the preview shows the REAL renderer of that model")
            self.assertIn(page.locator(self._card(region_key, key) + " h5").inner_text(), page.locator("[data-vs-vp-title]").inner_text())
            self.assertIn("فقط پیش‌نمایش", page.locator("[data-vs-vp-status]").inner_text())
            self.assertEqual(page.locator("[data-vs-vp-choose]").inner_text().strip(), "انتخاب این مدل")
            page.click('[data-vs-vp-device="mobile"]')
            self.assertEqual(page.eval_on_selector("[data-vs-vp-frame]", "f=>f.style.width"), "390px")
            self.assertEqual(page.get_attribute('[data-vs-vp-device="mobile"]', "aria-pressed"), "true")
            self._shot(page, f"vision_12_{region_key}_large_view")
            box = page.evaluate("()=>{const b=document.querySelector('[data-vs-vp-box]').getBoundingClientRect();return [b.left,b.top,b.right,b.bottom,innerWidth,innerHeight]}")
            self.assertTrue(box[0] >= 0 and box[1] >= 0 and box[2] <= box[4] and box[3] <= box[5], box)
            page.keyboard.press("Escape")
            page.wait_for_selector("[data-vs-vp]", state="hidden")
            page.wait_for_timeout(250)
            self.assertTrue(page.locator(".vs-design-modal").is_visible(), "Escape closes only the preview")
            self.assertEqual(page.evaluate("document.activeElement.getAttribute('data-vs-gal-view')"), key, "focus returns to «مشاهده بزرگ‌تر»")
            self.assertEqual((self._draft().edit_revision, self._settings_of(region_key)), before, "looking changes nothing")
            self._close_category(page)
        self.assertFalse([r for r in seen if "mutate" in r[1] or r[0] in ("POST", "PUT", "PATCH", "DELETE")], "no write request while looking")
        self.assertEqual(self.errors, [])
        context.close()

    def test_choosing_a_model_goes_through_the_real_variant_mutation_with_history(self):
        import json as _json

        context, page = self._studio()
        for region_key, mutation_type, field, prefer, marker in (
            ("footer", "footer.update", "footer_variant", "dark_tech", ".gf--dark"),
            ("header", "header.update", "header_variant", "dark_tech", ".gh--dark"),
        ):
            self._open_category(page, region_key)
            before = page.eval_on_selector(self.VARIANT_SELECT[region_key], "s=>s.value")
            key = self._other_key(page, region_key, prefer)
            pick = page.locator(self._card(region_key, key) + " [data-vs-gal-pick]")
            pick.scroll_into_view_if_needed()
            revision = page.evaluate("RastiSiR4.revision")
            with page.expect_request(lambda r: r.method == "POST" and r.url.rstrip("/").endswith("/vision-studio/mutate")) as sent:
                pick.click()
            body = _json.loads(sent.value.post_data)
            self.assertIn(mutation_type, _json.dumps(body))
            self.assertEqual(_json.dumps(body).count(key), 1, "exactly the picked key is sent")
            self._settled(page)
            self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
            self.assertEqual(self._settings_of(region_key)[field], key, "stored through the one R4 mutation")
            page.wait_for_selector(self._card(region_key, key) + ".is-current", timeout=15000)    # R4 re-renders the panel after saving
            self.assertEqual(page.locator(self._gal(region_key) + " .vs-badge").locator("xpath=ancestor::li").get_attribute("data-key"), key, "the card is marked as current")
            self.assertTrue(page.locator(self._card(region_key, key) + " [data-vs-gal-pick]").is_disabled())
            self.assertIn("اعمال شد", page.locator(self._card(region_key, key)).inner_text())
            if key == prefer:
                self.assertGreater(self._frame(page).locator(marker).count(), 0, "the Preview is updated")
            self._shot(page, f"vision_13_{region_key}_model_chosen")
            # refresh keeps it; Undo / Redo move through History
            page.reload(wait_until="networkidle")
            self._open_category(page, region_key)
            self.assertEqual(page.eval_on_selector(self.VARIANT_SELECT[region_key], "s=>s.value"), key)
            self._close_category(page)
            page.click("#r4UndoButton")
            page.wait_for_timeout(2500)
            self.assertEqual(self._settings_of(region_key)[field], before)
            self._open_category(page, region_key)
            self.assertEqual(page.locator(self._gal(region_key) + " .vs-badge").locator("xpath=ancestor::li").get_attribute("data-key"), before)
            self._close_category(page)
            page.click("#r4RedoButton")
            page.wait_for_timeout(2500)
            self.assertEqual(self._settings_of(region_key)[field], key)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_choosing_from_inside_the_large_view_applies_the_model(self):
        context, page = self._studio()
        self._open_category(page, "footer")
        key = self._other_key(page, "footer", "marketplace_dense")
        page.locator(self._card("footer", key) + " [data-vs-gal-view]").click()
        page.wait_for_selector("[data-vs-vp]:not([hidden])")
        page.click("[data-vs-vp-choose]")
        page.wait_for_selector("[data-vs-vp]", state="hidden")
        self._settled(page)
        self.assertEqual(self._settings_of("footer")["footer_variant"], key)
        context.close()

    # ---- clarity of every setting ---------------------------------------------------------------------------------------------------
    def test_design_modals_name_explain_and_scope_every_setting(self):
        from apps.storefront_builder import vision_ux
        from apps.storefront_builder.models import FOOTER_TOGGLE_FIELDS, HEADER_TOGGLE_FIELDS

        context, page = self._studio()
        for category, expected in (("header", "پیش‌نویس"), ("footer", "پیش‌نویس"), ("shape", "کل فروشگاه"), ("bottom_nav", "فقط موبایل")):
            self._open_category(page, category)
            chips = page.locator("[data-vs-scopebar] .vs-scopechip").all_inner_texts()
            self.assertTrue(any("کل فروشگاه" in c for c in chips), chips)
            self.assertTrue(any("پیش‌نویس" in c and "منتشر نمی‌شود" in c for c in chips), "the draft is not a publish: " + str(chips))
            self.assertTrue(any(expected in c for c in chips), chips)
            self._close_category(page)
        self._open_category(page, "header")
        for key in HEADER_TOGGLE_FIELDS:
            row = page.locator(f'#r4GlobalDesign input[data-r4-global-field="{key}"]').locator("xpath=ancestor::label[contains(@class,'r4-checkbox-row')]")
            title, effect = vision_ux.SETTING_COPY[key]
            self.assertIn(title, row.inner_text(), key)
            self.assertEqual(row.locator("xpath=following-sibling::p[contains(@class,'vs-help')][1]").inner_text(), effect, key)
        self._close_category(page)
        self._open_category(page, "footer")
        for key in FOOTER_TOGGLE_FIELDS:
            row = page.locator(f'#r4GlobalDesign input[data-r4-global-field="{key}"]').locator("xpath=ancestor::label[contains(@class,'r4-checkbox-row')]")
            self.assertIn(vision_ux.SETTING_COPY[key][0], row.inner_text(), key)
        self._close_category(page)
        # a changed control shows its own state: saving -> saved in the Draft
        self._open_category(page, "shape")
        select = page.locator("#r4GlobalDensity")
        options = page.eval_on_selector("#r4GlobalDensity", "s=>[...s.options].map(o=>o.value)")
        select.select_option(next(v for v in options if v != select.input_value()))
        badge = page.wait_for_selector(".vs-rowbadge--saved", timeout=15000)
        self.assertIn("پیش‌نویس", badge.inner_text())
        self.assertEqual(self.errors, [])
        context.close()

    def test_the_galleries_and_previews_hold_up_at_every_width(self):
        for width, height in ((1920, 1080), (1440, 900), (768, 1024), (390, 844)):
            context, page = self._studio(viewport=(width, height))
            if width <= 1023:
                page.click('[data-vs-toggle="panel"]')
            for region_key in ("header", "footer"):
                self._open_category(page, region_key)
                key = self._other_key(page, region_key, "dark_tech")
                card = page.locator(self._card(region_key, key))
                card.scroll_into_view_if_needed()
                box = card.bounding_box()
                self.assertGreaterEqual(box["width"], min(280, width * 0.8), f"{width}: a card stays readable")
                card.locator("[data-vs-gal-view]").click()
                page.wait_for_selector("[data-vs-vp]:not([hidden])")
                page.wait_for_timeout(800)
                vp = page.evaluate("()=>{const b=document.querySelector('[data-vs-vp-box]').getBoundingClientRect();return [b.left,b.top,b.right,b.bottom,innerWidth,innerHeight]}")
                self.assertTrue(vp[0] >= 0 and vp[2] <= vp[4] + 1 and vp[3] <= vp[5] + 1, f"{width}: {vp}")
                self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), f"{width}: no horizontal page scroll")
                if width == 390:
                    self._shot(page, f"vision_14_{region_key}_large_view_phone")
                page.keyboard.press("Escape")
                page.wait_for_selector("[data-vs-vp]", state="hidden")
                if width == 390:
                    card.scroll_into_view_if_needed()
                    self._shot(page, f"vision_15_{region_key}_gallery_phone")
                self._close_category(page)
            self.assertEqual(self.errors, [], width)
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

    POSITIVE_WORDS = ("روشن", "نمایش داده می‌شود", "قفل است")

    def test_every_switch_states_its_value_in_words_and_follows_change_refresh_undo_redo(self):
        context, page = self._studio()
        self._open_category(page, "images")
        switches = self._visible_switches(page, "#r4GlobalDesign")
        self.assertGreaterEqual(len(switches), 2)
        for item in switches:
            self.assertIn(item["text"], ("روشن", "خاموش", "غیرفعال", "نمایش داده می‌شود", "پنهان است", "قفل است", "باز است"), item)
            self.assertEqual(item["text"] in self.POSITIVE_WORDS, item["shown"] and not item["disabled"], item)
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
        # section settings: every visible switch states its value, and the words follow the SHOWN state of the real key
        rows = page.locator(".tree-row .rs-row-select")
        seen = 0
        for index in range(min(rows.count(), 12)):
            rows.nth(index).click()
            page.wait_for_selector("#r4Inspector [data-r4-section-inspector]", timeout=8000)
            page.wait_for_timeout(500)
            for item in self._visible_switches(page, "#r4Inspector"):
                seen += 1
                self.assertTrue(item["text"], item)
                self.assertEqual(item["text"] in self.POSITIVE_WORDS, item["shown"] and not item["disabled"], item)
            self._close_inspector(page)
        self.assertGreater(seen, 0)
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    # ---- «نمایش در موبایل / تبلت»: shown as visible, stored as hidden --------------------------------------------------------------
    MOBILE = '#r4GlobalDesign [data-r4-global-responsive-key="show_search"][data-r4-global-responsive-prop="hide_on_mobile"]'
    TABLET = '#r4GlobalDesign [data-r4-global-responsive-key="show_search"][data-r4-global-responsive-prop="hide_on_tablet"]'
    GREEN = "rgb(31, 157, 110)"

    def _proxy(self, page, selector):
        return page.locator(selector).locator("xpath=following-sibling::button[@role='switch']")

    def _search_hidden_in_preview(self, page, device):
        """What the REAL Preview does at that device width: the flagged header parts (with their effective visibility - any hidden ancestor
        counts) and whether any search field of the header can actually be seen."""
        page.evaluate(f"RastiSiR4.setDevice('{device}')")
        page.wait_for_timeout(2200)
        frame = [f for f in page.frames if f != page.main_frame and "preview" in f.url][0]
        return frame.evaluate(
            """()=>{
              const hiddenByChain = n => { for (let e = n; e; e = e.parentElement) { if (getComputedStyle(e).display === 'none' || getComputedStyle(e).visibility === 'hidden') return true; } return false; };
              const flagged = [...document.querySelectorAll('[data-shell-hide-mobile],[data-shell-hide-tablet]')].map(n => ({
                 tag: n.tagName + '.' + String(n.className).slice(0, 34), m: n.hasAttribute('data-shell-hide-mobile'), t: n.hasAttribute('data-shell-hide-tablet'),
                 display: getComputedStyle(n).display, hidden: hiddenByChain(n)}));
              const fields = [...document.querySelectorAll('header input[type="search"], header input[name="q"], header .gh-search input')];
              return {width: innerWidth, flagged, searchVisible: fields.some(f => !hiddenByChain(f) && f.getClientRects().length > 0)};
            }"""
        )

    def test_a_hide_on_mobile_field_is_shown_as_visible_and_stores_hidden_true(self):
        context, page = self._studio()
        self._open_category(page, "header")
        native = page.locator(self.MOBILE)
        proxy = self._proxy(page, self.MOBILE)
        # false in the Draft  ->  shown ON, green, «نمایش داده می‌شود», role=switch aria-checked=true
        self.assertFalse(native.is_checked())
        self.assertFalse(self._settings_of("header")["responsive"]["show_search"]["hide_on_mobile"])
        self.assertEqual(proxy.get_attribute("role"), "switch")
        self.assertEqual(proxy.get_attribute("aria-checked"), "true")
        self.assertEqual(proxy.get_attribute("aria-label"), "نمایش در موبایل")
        self.assertEqual(self._proxy(page, self.TABLET).get_attribute("aria-label"), "نمایش در تبلت")
        self.assertEqual(native.evaluate("e=>e.dataset.vsShown"), "on")
        self.assertEqual(page.locator(self.MOBILE + " + .vs-sw + .vs-sw-text").inner_text(), "نمایش داده می‌شود")
        on_look = self._track(proxy)
        self.assertEqual(on_look["bg"], self.GREEN)
        shown = self._search_hidden_in_preview(page, "mobile")
        self.assertEqual(shown["flagged"], [], "nothing is flagged hidden while every switch is shown")
        self.assertTrue(shown["searchVisible"])
        self._shot(page, "vision_09_show_on_mobile_switch_on")
        # switch it OFF: stored true, grey, «پنهان است», aria-checked=false - and the real phone Preview loses the search
        revision = page.evaluate("RastiSiR4.revision")
        page.evaluate("RastiSiR4.setDevice('desktop')")
        proxy.click()
        self._settled(page)
        self.assertGreater(page.evaluate("RastiSiR4.revision"), revision)
        self.assertTrue(native.is_checked())
        self.assertEqual(proxy.get_attribute("aria-checked"), "false")
        self.assertEqual(page.locator(self.MOBILE + " + .vs-sw + .vs-sw-text").inner_text(), "پنهان است")
        off_look = self._track(proxy)
        self.assertNotEqual(off_look["bg"], self.GREEN)
        self.assertEqual(native.evaluate("e=>e.dataset.vsShown"), "off")
        config = self._settings_of("header")["responsive"]["show_search"]
        self.assertTrue(config["hide_on_mobile"], "hidden is stored as true")
        self.assertFalse(config["hide_on_tablet"], "the sibling device is untouched")
        self._shot(page, "vision_10_show_on_mobile_switch_off")
        # the real Preview renders exactly the device flag the Draft stores: «hide on mobile» flags the mobile branch and never the tablet one.
        # (Whether a given header variant's own CSS then honours the flag is the storefront engine's business: see the Vision report, finding on
        # `[data-shell-hide-*]` vs class-level `display` rules.)
        phone = self._search_hidden_in_preview(page, "mobile")
        self.assertTrue(phone["flagged"] and all(n["m"] and not n["t"] for n in phone["flagged"]), phone)
        self.assertTrue(any(n["hidden"] for n in phone["flagged"]), f"the desktop search branch is hidden on a phone: {phone}")
        page.evaluate("RastiSiR4.setDevice('desktop')")
        # refresh keeps the value
        page.reload(wait_until="networkidle")
        self._open_category(page, "header")
        self.assertEqual(self._proxy(page, self.MOBILE).get_attribute("aria-checked"), "false")
        self.assertTrue(page.locator(self.MOBILE).is_checked())
        # Undo -> ON again, Redo -> OFF again, in the UI and in the Draft
        self._close_category(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "header")
        self.assertEqual(self._proxy(page, self.MOBILE).get_attribute("aria-checked"), "true")
        self.assertEqual(self._proxy(page, self.MOBILE).evaluate("e=>getComputedStyle(e).backgroundColor"), self.GREEN)
        self.assertFalse(self._settings_of("header")["responsive"]["show_search"]["hide_on_mobile"])
        self._close_category(page)
        page.click("#r4RedoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "header")
        self.assertEqual(self._proxy(page, self.MOBILE).get_attribute("aria-checked"), "false")
        self.assertTrue(self._settings_of("header")["responsive"]["show_search"]["hide_on_mobile"])
        self.assertEqual(self.errors, [])
        self.assertEqual(self.failed, [])
        context.close()

    def test_the_tablet_switch_has_the_same_inverted_mapping(self):
        context, page = self._studio()
        self._open_category(page, "header")
        proxy = self._proxy(page, self.TABLET)
        self.assertEqual(proxy.get_attribute("aria-checked"), "true")
        proxy.click()
        self._settled(page)
        config = self._settings_of("header")["responsive"]["show_search"]
        self.assertTrue(config["hide_on_tablet"])
        self.assertFalse(config["hide_on_mobile"])
        self.assertEqual(self._proxy(page, self.TABLET).get_attribute("aria-checked"), "false")
        self.assertEqual(self._proxy(page, self.MOBILE).get_attribute("aria-checked"), "true")
        tablet = self._search_hidden_in_preview(page, "tablet")
        self.assertTrue(tablet["flagged"] and all(n["t"] and not n["m"] for n in tablet["flagged"]), tablet)
        # the keyboard works: Space on the focused switch toggles it back
        self._proxy(page, self.TABLET).focus()
        page.keyboard.press("Space")
        self._settled(page)
        self.assertFalse(self._settings_of("header")["responsive"]["show_search"]["hide_on_tablet"])
        self.assertEqual(self._proxy(page, self.TABLET).get_attribute("aria-checked"), "true")
        context.close()

    def test_a_positive_field_stays_green_when_true_and_grey_when_false(self):
        context, page = self._studio()
        self._open_category(page, "header")
        native = page.locator('#r4GlobalDesign input[data-r4-global-field="show_search"]')
        self.assertTrue(native.is_checked())
        self.assertTrue(self._settings_of("header")["show_search"])
        self.assertEqual(native.get_attribute("role"), "switch")
        self.assertEqual(native.evaluate("e=>getComputedStyle(e).backgroundColor"), self.GREEN)
        self.assertEqual(native.evaluate("e=>e.dataset.vsShown"), "on")
        self.assertEqual(page.locator('#r4GlobalDesign input[data-r4-global-field="show_search"] + .vs-sw-text').inner_text(), "نمایش داده می‌شود")
        native.click()
        self._settled(page)
        self.assertFalse(self._settings_of("header")["show_search"])
        self.assertNotEqual(native.evaluate("e=>getComputedStyle(e).backgroundColor"), self.GREEN)
        self.assertEqual(page.locator('#r4GlobalDesign input[data-r4-global-field="show_search"] + .vs-sw-text').inner_text(), "پنهان است")
        page.reload(wait_until="networkidle")
        self._open_category(page, "header")
        self.assertFalse(page.locator('#r4GlobalDesign input[data-r4-global-field="show_search"]').is_checked())
        self._close_category(page)
        page.click("#r4UndoButton")
        page.wait_for_timeout(2500)
        self._open_category(page, "header")
        self.assertTrue(page.locator('#r4GlobalDesign input[data-r4-global-field="show_search"]').is_checked())
        context.close()

    def test_a_save_does_not_throw_the_dialog_back_to_the_top(self):
        context, page = self._studio()
        self._open_category(page, "header")
        page.evaluate("document.querySelector('#r4GlobalDesign .r4-responsive-row').scrollIntoView({block:'center'})")
        page.wait_for_timeout(500)
        before = page.evaluate("document.querySelector('.vs-modal__scroll').scrollTop")
        self.assertGreater(before, 500, "the control is far down the dialog")
        self._proxy(page, self.MOBILE).click()
        self._settled(page)
        page.wait_for_timeout(1500)
        after = page.evaluate("document.querySelector('.vs-modal__scroll').scrollTop")
        self.assertAlmostEqual(after, before, delta=24, msg="R4 re-renders the panel after saving; the dialog keeps its place")
        context.close()

    def test_disabled_and_off_look_different(self):
        context, page = self._studio()
        self._open_category(page, "header")
        proxy = self._proxy(page, self.MOBILE)
        native = page.locator(self.MOBILE)
        proxy.click()
        self._settled(page)
        page.wait_for_timeout(2000)    # R4 re-renders the panel from the server after saving; disable the FRESH control
        proxy = self._proxy(page, self.MOBILE)
        off = self._track(proxy)
        native.evaluate("e=>{e.disabled=true}")
        page.wait_for_timeout(200)
        disabled = self._track(self._proxy(page, self.MOBILE))
        self.assertEqual(page.locator(self.MOBILE + " + .vs-sw + .vs-sw-text").inner_text(), "غیرفعال")
        self.assertTrue(self._proxy(page, self.MOBILE).is_disabled())
        self.assertNotEqual((off["bg"], off["border"]), (disabled["bg"], disabled["border"]))
        self.assertEqual(disabled["border"], "dashed")
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
