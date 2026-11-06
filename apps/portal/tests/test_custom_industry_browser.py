"""Real-browser (Chromium) test of the «سایر (صنف آزاد)» custom-name field on the onboarding «صنف» step (FV2).

Opt-in — ``SFB_BROWSER_TESTS=1`` (Chromium path via ``SFB_CHROMIUM_PATH`` if not in ``/opt/pw-browsers``). Runs against Django's live test
server and a throw-away test database only; nothing is sent anywhere. Run it alone (``LiveServerTestCase`` flushes the test DB afterwards):

``SFB_BROWSER_TESTS=1 python manage.py test apps.portal.tests.test_custom_industry_browser``

What it proves: the name box is hidden until the «other» card is picked, hides again for another card, the install button stays disabled until a valid
name is typed, the server-validated name is stored, a rejected name (server side, JS bypassed) keeps the typed value and shows the error, and the page
has no console errors. It does NOT prove cross-browser rendering (Chromium only).
"""

import os
import unittest
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import StoreIndustryInstallation
from apps.portal.services import provisioning_service
from apps.portal.tests._industry import ensure_other_template
from apps.portal.tests.test_onboarding_journey import make_rich_template
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
HOST = "rastisi.localhost"
CANDIDATES = (os.environ.get("SFB_CHROMIUM_PATH", ""), "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome", "/opt/pw-browsers/chromium")


def _chromium():
    return next((c for c in CANDIDATES if c and Path(c).is_file()), None)


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "set SFB_BROWSER_TESTS=1 to run the Chromium onboarding test")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[HOST, "127.0.0.1", "localhost", "testserver"])
class CustomIndustryBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1"]}
        if _chromium():
            launch["executable_path"] = _chromium()
        try:
            cls.browser = cls.pw.chromium.launch(**launch)
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            super().tearDownClass()
            raise unittest.SkipTest(f"Chromium unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        owner = get_user_model().objects.create_user(username="cib@example.com", email="cib@example.com", password="a-very-strong-pass-1")
        self.store = provisioning_service.provision_trial_store(owner=owner, name="فروشگاهِ مرورگر")
        plan = Plan.objects.create(code="cib-plan", name="CIB")
        version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        StoreSubscription.objects.create(store=self.store, plan_version=version, status=StoreSubscription.Status.TRIALING, is_current=True, trial_end_at=timezone.now())
        self.other = ensure_other_template()
        self.rich = make_rich_template()
        client = Client(HTTP_HOST=HOST)
        client.force_login(owner)
        self.base = f"http://{HOST}:{self.live_server_url.rsplit(':', 1)[1]}"
        self.ctx = self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="fa-IR")
        self.ctx.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "domain": HOST, "path": "/"}])
        self.errors = []
        self.page = self.ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: self.errors.append(f"console: {m.text}") if m.type == "error" and "favicon" not in m.text else None)
        self.page.goto(f"{self.base}/app/stores/{self.store.public_id}/onboarding/industry/")
        self.page.wait_for_selector("[data-ob-card]")

    def tearDown(self):
        self.ctx.close()

    def _pick(self, template):
        self.page.locator(f'[data-ob-card][data-id="{template.pk}"]').click()

    def _confirm(self):
        self.page.locator("[data-ob-confirm-check]").check()

    def test_the_name_box_follows_the_selected_card(self):
        page = self.page
        box, name = page.locator("[data-ob-custom-industry]"), page.locator("#ob-custom-industry-name")
        self.assertFalse(box.is_visible())
        self._pick(self.rich)
        self.assertFalse(box.is_visible())
        self._pick(self.other)
        self.assertTrue(box.is_visible())
        self.assertTrue(name.is_enabled())
        self._pick(self.rich)
        self.assertFalse(box.is_visible())
        self.assertTrue(name.is_disabled())            # a disabled field is not submitted: no stale name rides along with another industry
        self.assertEqual(self.errors, [])

    def test_install_stays_disabled_until_other_has_a_valid_name_and_then_stores_it(self):
        page = self.page
        submit = page.locator("[data-ob-install-submit]")
        self._pick(self.other)
        self._confirm()
        self.assertTrue(submit.is_disabled())
        page.fill("#ob-custom-industry-name", "ا")
        self.assertTrue(submit.is_disabled())
        page.fill("#ob-custom-industry-name", "گالری سفال و سرامیک")
        self.assertTrue(submit.is_enabled())
        submit.click()
        page.wait_for_url("**/onboarding/template/**")
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.industry_template_id, self.other.pk)
        self.assertEqual(installation.custom_industry_name, "گالری سفال و سرامیک")
        self.assertEqual(self.errors, [])

    def test_an_ordinary_industry_installs_without_any_name(self):
        page = self.page
        self._pick(self.rich)
        self._confirm()
        self.assertTrue(page.locator("[data-ob-install-submit]").is_enabled())
        page.locator("[data-ob-install-submit]").click()
        page.wait_for_url("**/onboarding/template/**")
        self.assertEqual(StoreIndustryInstallation.objects.get(store=self.store).custom_industry_name, "")

    def test_the_server_still_rejects_a_bad_name_when_the_client_check_is_bypassed(self):
        page = self.page
        self._pick(self.other)
        self._confirm()
        page.fill("#ob-custom-industry-name", "ok name")
        page.evaluate("document.querySelector('[data-ob-install-submit]').disabled = false")
        page.evaluate("document.getElementById('ob-custom-industry-name').value = '<b>x</b>'")
        page.locator("[data-ob-install-submit]").click()
        page.wait_for_selector("#ob-custom-industry-error")
        self.assertIn("نامِ صنف", page.inner_text("#ob-custom-industry-error"))
        self.assertEqual(page.input_value("#ob-custom-industry-name"), "<b>x</b>")        # the typed value is kept (escaped in the markup)
        self.assertTrue(page.locator("[data-ob-custom-industry]").is_visible())
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())
        self.assertEqual(page.locator("b", has_text="x").count(), 0)                        # not injected as markup
