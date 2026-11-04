"""Shared password visibility component (M1 / Part 1 of the Admin Experience Upgrade).

* ``PasswordToggleWiringTests`` - no browser: every admin / platform-admin / portal page that renders a password input loads the ONE shared
  stylesheet + script, and the retired portal-only control is gone (a second implementation is how the eye ended up on top of the text).
* ``PasswordToggleBrowserTests`` - opt-in Chromium (``SFB_BROWSER_TESTS=1``): real files, RTL + LTR, desktop + phone width. The eye sits in the
  reserved gutter at the inline end of the INPUT's own direction, is a >=44px target, never overlaps the typed text, flips password<->text,
  keeps the value, and the field is hidden by default and again after submit."""

import os
import re
import unittest
from pathlib import Path

from django.test import SimpleTestCase

APPS = Path(__file__).resolve().parents[2]
CSS = APPS / "core" / "static" / "core" / "password_toggle.css"
JS = APPS / "core" / "static" / "core" / "password_toggle.js"
ADMIN_CSS = APPS / "dashboard" / "static" / "css" / "admin.css"

#: bases that every password-bearing page extends (or is itself standalone and must load the component directly)
HOSTS = {
    "dashboard/templates/dashboard/base_admin.html": "admin shell (payment gateway secrets, every admin page)",
    "dashboard/templates/dashboard/login.html": "admin login (standalone)",
    "portal/templates/portal/platform_admin/base.html": "platform admin (login, SMS credentials)",
    "portal/templates/portal/public/base_public.html": "portal login / signup / password reset",
}


class PasswordToggleWiringTests(SimpleTestCase):
    def test_every_password_host_loads_the_shared_component(self):
        for rel, what in HOSTS.items():
            text = (APPS / rel).read_text(encoding="utf-8")
            self.assertIn("core/password_toggle.css", text, f"{rel} ({what}) must load the shared stylesheet")
            self.assertIn("core/password_toggle.js", text, f"{rel} ({what}) must load the shared script")

    def test_storefront_base_loads_the_component_for_the_customer_login_and_signup_modal(self):
        text = (APPS.parent / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("core/password_toggle.css", text)
        self.assertIn("core/password_toggle.js", text)
        self.assertEqual(text.count("core/password_toggle.js"), 1)

    def test_accessible_names_are_the_short_persian_words(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("var SHOW = 'نمایش رمز';", js)
        self.assertIn("var HIDE = 'پنهان\u200cکردن رمز';", js)

    def test_every_template_with_a_password_input_extends_a_host(self):
        """A template that renders ``type="password"`` (or a Django password widget field) must be a host or extend one."""
        hosts = {Path(rel).name for rel in HOSTS}
        bases = hosts | {"base_admin.html", "base_public.html", "base.html"}
        offenders = []
        for path in APPS.rglob("templates/**/*.html"):
            rel = path.relative_to(APPS).as_posix()
            if rel.startswith(("customers/", "storefront_builder/")) or "/tests/" in rel:
                continue  # customer-facing storefront auth is out of scope for the admin component
            if "/partials/" in rel:
                continue  # included by pages that extend a host (settings.html -> base_admin.html); covered by the host check
            text = path.read_text(encoding="utf-8")
            if not re.search(r'type="password"|form\.password|password_form\.password', text):
                continue
            if rel in HOSTS or re.search(r'{%\s*extends\s+"[^"]*(' + "|".join(re.escape(b) for b in bases) + r')"', text):
                continue
            offenders.append(rel)
        self.assertEqual(offenders, [], "password inputs on pages that do not load the shared toggle")

    def test_the_old_portal_only_control_is_retired(self):
        portal_css = (APPS / "portal/static/portal/css/public-site-v2.css").read_text(encoding="utf-8")
        auth_js = (APPS / "portal/static/portal/js/auth-forms.js").read_text(encoding="utf-8")
        self.assertNotIn("r-password-toggle", portal_css + auth_js)
        self.assertNotIn("padding-right:68px", portal_css)

    def test_css_reserves_the_gutter_on_the_inline_end_and_is_a_large_target(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("padding-inline-end: var(--pw-gutter) !important", css)
        self.assertIn("inset-inline-end", css)
        self.assertRegex(css, r"--pw-size:\s*44px")
        self.assertNotRegex(css, r"\bright\s*:\s*\d")      # physical offsets would put the eye over the text in one of the two directions
        self.assertNotRegex(css, r"\bleft\s*:\s*\d")

    def test_script_never_touches_name_value_or_autocomplete(self):
        js = re.sub(r"/\*.*?\*/|//[^\n]*", "", JS.read_text(encoding="utf-8"), flags=re.S)   # code only, not the explanatory comments
        for forbidden in (".name =", ".value =", "autocomplete", "removeAttribute('name')", "cloneNode"):
            self.assertNotIn(forbidden, js)
        self.assertIn("input.type = show ? 'text' : 'password'", js)


PAGE = """<!doctype html><html lang="fa" dir="{page_dir}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;font-family:sans-serif">
<form id="f" method="post" action="#" onsubmit="return false" style="max-width:420px">
  <div class="form-group"><label>RTL</label><input class="inp" id="rtl" type="password" name="p1" dir="rtl" value="abcdefghijklmnopqrstuvwxyz0123456789-long-secret-value"></div>
  <div class="form-group"><label>LTR</label><input class="inp" id="ltr" type="password" name="p2" dir="ltr" value="abcdefghijklmnopqrstuvwxyz0123456789-long-secret-value"></div>
  <div class="form-group"><label>inherit</label><input class="inp" id="inh" type="password" name="p3" autocomplete="current-password"></div>
  <button type="submit" id="go">go</button>
</form></body></html>"""

BROWSER = os.environ.get("SFB_BROWSER_TESTS") == "1"


@unittest.skipUnless(BROWSER, "browser test is opt-in: SFB_BROWSER_TESTS=1")
class PasswordToggleBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls._pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox"]}
        for candidate in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome"):
            if os.path.exists(candidate):
                launch["executable_path"] = candidate
                break
        cls.browser = cls._pw.chromium.launch(**launch)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def _page(self, page_dir, width):
        ctx = self.browser.new_context(viewport={"width": width, "height": 800})
        page = ctx.new_page()
        page.set_content(PAGE.format(page_dir=page_dir))
        page.add_style_tag(path=str(ADMIN_CSS))
        page.add_style_tag(path=str(CSS))
        page.add_script_tag(path=str(JS))
        page.wait_for_selector(".pw-toggle")
        return ctx, page

    def test_geometry_in_both_directions_and_widths(self):
        for page_dir in ("rtl", "ltr"):
            for width in (1440, 390):
                ctx, page = self._page(page_dir, width)
                try:
                    for field_id, expected_end in (("rtl", "left"), ("ltr", "right")):
                        g = page.evaluate(
                            """(id) => {
                              const input = document.getElementById(id);
                              const wrap = input.parentElement, btn = wrap.querySelector('.pw-toggle');
                              const i = input.getBoundingClientRect(), b = btn.getBoundingClientRect();
                              const cs = getComputedStyle(input);
                              const rtl = getComputedStyle(wrap).direction === 'rtl';
                              const padEnd = parseFloat(rtl ? cs.paddingLeft : cs.paddingRight);
                              // the typed text's own box: the input's content area on the text side
                              const textLeft = i.left + (rtl ? padEnd : parseFloat(cs.paddingLeft)) + parseFloat(cs.borderLeftWidth);
                              const textRight = i.right - (rtl ? parseFloat(cs.paddingRight) : padEnd) - parseFloat(cs.borderRightWidth);
                              return {bw: b.width, bh: b.height, inside: b.left >= i.left && b.right <= i.right && b.top >= i.top && b.bottom <= i.bottom,
                                      overlap: Math.max(0, Math.min(b.right, textRight) - Math.max(b.left, textLeft)), side: (b.left + b.width / 2) < (i.left + i.width / 2) ? 'left' : 'right', padEnd};
                            }""",
                            field_id,
                        )
                        where = f"page={page_dir} field={field_id} width={width}"
                        self.assertGreaterEqual(g["bw"], 44, where)
                        self.assertGreaterEqual(g["bh"], 44, where)
                        self.assertTrue(g["inside"], where)
                        self.assertEqual(g["overlap"], 0, f"the eye overlaps the text area: {where}")
                        self.assertEqual(g["side"], expected_end, f"eye must sit at the input's own inline end: {where}")
                    self.assertEqual(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), True, "no horizontal page scroll")
                finally:
                    ctx.close()

    def test_toggle_flips_type_keeps_value_and_resets_on_submit(self):
        ctx, page = self._page("rtl", 390)
        try:
            btn = page.locator("#rtl").locator("xpath=..").locator(".pw-toggle")
            self.assertEqual(page.eval_on_selector("#rtl", "e => e.type"), "password")          # default hidden
            self.assertEqual(btn.get_attribute("aria-pressed"), "false")
            before = page.eval_on_selector("#rtl", "e => e.value")
            btn.click()
            self.assertEqual(page.eval_on_selector("#rtl", "e => e.type"), "text")
            self.assertEqual(btn.get_attribute("aria-pressed"), "true")
            self.assertEqual(page.eval_on_selector("#rtl", "e => e.value"), before)
            self.assertEqual(page.eval_on_selector("#rtl", "e => [e.name, e.getAttribute('autocomplete')]"), ["p1", None])
            self.assertEqual(page.eval_on_selector("#inh", "e => e.getAttribute('autocomplete')"), "current-password")
            btn.click()
            self.assertEqual(page.eval_on_selector("#rtl", "e => e.type"), "password")
            btn.click()
            page.click("#go")                                                                    # submit hides again
            self.assertEqual(page.eval_on_selector("#rtl", "e => e.type"), "password")
        finally:
            ctx.close()

    def test_keyboard_operable_and_labelled(self):
        ctx, page = self._page("ltr", 1440)
        try:
            page.focus("#ltr")
            page.keyboard.press("Tab")
            self.assertEqual(page.evaluate("document.activeElement.className"), "pw-toggle")
            page.keyboard.press("Enter")
            self.assertEqual(page.eval_on_selector("#ltr", "e => e.type"), "text")
            self.assertEqual(page.evaluate("document.activeElement.getAttribute('aria-label')"), "پنهان‌کردن رمز")
        finally:
            ctx.close()

    def test_late_inserted_fields_are_enhanced_and_opt_out_is_respected(self):
        ctx, page = self._page("rtl", 1440)
        try:
            page.evaluate("""() => { const d = document.createElement('div');
              d.innerHTML = '<input id="late" type="password"><input id="skip" type="password" data-pw-toggle="off">'; document.body.appendChild(d); }""")
            page.wait_for_selector("#late ~ .pw-toggle")
            self.assertEqual(page.eval_on_selector("#skip", "e => e.parentElement.classList.contains('pw-field')"), False)
            self.assertEqual(page.locator("#skip ~ .pw-toggle").count(), 0)
        finally:
            ctx.close()
