"""تستِ مرورگریِ واقعیِ رابطِ ساده‌ی ساختِ کمپین/مناسبت (Chromium + Playwright).

روی سرورِ زنده‌ی تستِ Django و دیتابیسِ آزمایشیِ تست اجرا می‌شود (هیچ دیتابیسِ محلی/عملیاتی لمس نمی‌شود)
و هیچ پیامک/ایمیلی ارسال نمی‌شود. اگر Playwright/Chromium نصب نباشد، تست‌ها SKIP می‌شوند (نه PASS).

اجرا: ``python manage.py test apps.dashboard.tests.test_campaign_wizard_browser``
مسیرِ Chromium را می‌توان با ``CW_BROWSER_PATH`` تعیین کرد؛ عکس‌ها در ``CW_SCREENSHOT_DIR`` (در صورتِ تعریف) ذخیره می‌شوند."""

import os
import unittest
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.engagement.models import Campaign
from apps.notifications.models import NotificationOutbox
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

try:  # pragma: no cover - وابسته به محیط
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
HOST = f"wizard-browser.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
BROWSER_CANDIDATES = (
    os.environ.get("CW_BROWSER_PATH", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium",
)


def _browser_path():
    for path in BROWSER_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


@unittest.skipIf(sync_playwright is None, "Playwright نصب نیست")
@override_settings(ALLOWED_HOSTS=[HOST, "127.0.0.1", "localhost", "testserver"])
class CampaignWizardBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1"]}
        path = _browser_path()
        if path:
            launch["executable_path"] = path
        try:
            cls.browser = cls.pw.chromium.launch(**launch)
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            super().tearDownClass()
            raise unittest.SkipTest(f"Chromium در دسترس نیست: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        # فروشگاهِ اختصاصیِ تست (فروشگاهِ مهاجرتیِ akhlaghi پس از flushِ TransactionTestCase در دسترس نیست)
        self.store = Store.objects.create(
            name="فروشگاه تست مرورگر", slug="wizard-browser-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain=HOST.split(".")[0],
        )
        ShopSettings.provision_for(self.store)
        user = get_user_model().objects.create_user(username="09125550001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="09125550001", password="pass12345")
        port = self.live_server_url.rsplit(":", 1)[1]
        self.base = f"http://{HOST}:{port}"
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900}, locale="fa-IR")
        self.context.add_cookies([{"name": "sessionid", "value": client.cookies["sessionid"].value, "domain": HOST, "path": "/"}])
        self.errors = []
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: self.errors.append(f"console: {m.text}") if m.type == "error" and "favicon" not in m.text else None)
        self.page.on("dialog", lambda d: d.accept())

    def tearDown(self):
        self.context.close()

    def shot(self, name):
        directory = os.environ.get("CW_SCREENSHOT_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(directory) / f"{name}.png"), full_page=True)

    def open(self, kind):
        self.page.goto(f"{self.base}/admin-portal/campaigns/add/?kind={kind}")
        self.page.wait_for_selector("#cw-root")

    def next_step(self):
        self.page.locator(".cw-panel:not(.cw-hidden) [data-next]").click()

    def assert_no_js_errors(self):
        self.assertEqual(self.errors, [])

    # ------------------------------------------------------------------ مناسبت
    def test_occasion_full_flow_creates_a_draft_with_read_only_platform_sms_preview(self):
        page = self.page
        self.open("occasions")
        self.assertIn("یک مناسبت جدید بسازیم", page.inner_text(".cw-intro h1"))
        # نمایش شرطی: مناسبتِ «مشتری که برنگشته» فیلدِ روزِ عدمِ خرید را نشان می‌دهد
        self.assertFalse(page.locator("#id_occ_days").is_visible())
        page.click('[data-field="occasion_kind"][data-value="reactivation"]')
        self.assertTrue(page.locator("#id_occ_days").is_visible())
        page.fill("#id_occ_days", "۶۰")
        page.click('[data-field="occasion_kind"][data-value="registration_anniversary"]')
        self.assertFalse(page.locator("#id_occ_days").is_visible())
        # اعتبارسنجی سمت کاربر: نامِ خالی
        page.fill("#id_name", "")
        self.next_step()
        self.assertTrue(page.locator("#cw-name-error").is_visible())
        page.fill("#id_name", "سالگرد عضویت مشتریان")
        self.assertIn("سالگرد ثبت‌نام", page.inner_text("#cw-sum-audience"))
        self.next_step()
        # مرحله ۲: انواع هدیه
        page.click('[data-reward="none"]')
        self.assertFalse(page.locator("#cw-reward-details").is_visible())
        page.click('[data-reward="free_ship"]')
        self.assertTrue(page.locator("#cw-validity-block").is_visible())
        self.assertFalse(page.locator("#id_coupon_value").is_visible())
        page.click('[data-reward="fixed"]')
        self.assertEqual(page.input_value("#id_coupon_value"), "100000")
        page.fill("#id_coupon_value", "۱۵۰٬۰۰۰")
        page.select_option("#id_code_valid_days", "14")
        self.assertIn("۱۵۰٬۰۰۰ تومان تخفیف", page.inner_text("#cw-sum-reward"))
        self.next_step()
        # مرحله ۳: پیامک
        self.assertEqual(page.locator("#cw-step3 textarea[name*=sms], #cw-step3 input[name*=sms_body]").count(), 0)
        page.wait_for_function("document.getElementById('cw-sms-bubble').textContent.includes('عزیز')")
        bubble = page.inner_text("#cw-sms-bubble")
        self.assertIn("سارا احمدی", bubble)
        self.assertIn("سالگرد عضویت شما", bubble)
        self.assertIn("۱۵۰٬۰۰۰ تومان", bubble)
        self.assertNotRegex(bubble, r"\{|\}")
        self.assertTrue(page.locator("#cw-sms-bubble .cw-var").count() >= 4)
        self.assertEqual(page.locator("#cw-sms-bubble").get_attribute("contenteditable"), None)
        self.assertEqual(page.locator("#cw-sms-bubble[role=note]").count(), 1)
        self.assertIn("ارسال پیامک خاموش", page.inner_text("#cw-sms-state"))
        page.check("#cw-notify-sms")
        page.wait_for_function("document.getElementById('cw-sms-state').textContent.includes('روشن')|| document.getElementById('cw-sms-state').textContent.includes('فعال')")
        # تغییرِ زمان‌بندی ⇒ قالبِ دیگر (و همیشه از سرور)
        page.click('[data-offset="-3"]')
        page.wait_for_function("document.getElementById('cw-sms-bubble').textContent.includes('نزدیک است')")
        page.click('[data-offset="0"]')
        page.wait_for_function("!document.getElementById('cw-sms-bubble').textContent.includes('نزدیک است')")
        self.shot("occasion_step3")
        page.click("#cw-view-review")
        page.wait_for_selector("#cw-review-overlay.cw-open")
        review = page.inner_text("#cw-review-list")
        self.assertIn("سالگرد عضویت مشتریان", review)
        self.assertIn("غیرقابل ویرایش", review)
        self.shot("occasion_review")
        page.click("#cw-save")
        page.wait_for_url("**/campaigns/*/")
        campaign = Campaign.objects.get()
        self.assertEqual(
            (campaign.name, campaign.status, campaign.trigger_type, campaign.occasion_kind, campaign.coupon_type, int(campaign.coupon_value), campaign.code_valid_days, campaign.channels, campaign.channels_explicit),
            ("سالگرد عضویت مشتریان", "draft", "occasion", "registration_anniversary", "fixed", 150000, 14, ["sms"], True),
        )
        self.assertEqual(NotificationOutbox.objects.count(), 0)
        self.assert_no_js_errors()

    def test_reward_none_message_has_no_gift_in_the_browser(self):
        page = self.page
        self.open("occasions")
        self.next_step()
        page.click('[data-reward="none"]')
        self.next_step()
        page.wait_for_function("document.getElementById('cw-sms-bubble').textContent.includes('عزیز')")
        bubble = page.inner_text("#cw-sms-bubble")
        for word in ("کد", "تخفیف", "هدیه", "اعتبار تا"):
            self.assertNotIn(word, bubble)
        self.assertEqual(page.locator("#cw-sms-vars .cw-chip-tag").count(), 2)  # فقط نام مشتری و نام فروشگاه
        self.assert_no_js_errors()

    # ------------------------------------------------------------------ کمپین
    def test_campaign_flow_with_specific_audience_and_scheduled_timing(self):
        from apps.engagement.tests.base import EngagementBase  # noqa: F401  (فقط برای اطمینان از وجودِ ابزارها)
        from apps.customers.models import Customer

        for i, city in enumerate(("شیراز", "تهران")):
            user = get_user_model().objects.create_user(username=f"0912666000{i}", password="x12345678")
            Customer.objects.create(user=user, full_name=f"مشتری {i}", phone=f"0912666000{i}", city=city)
        # مشتری باید با این Store ارتباط داشته باشد تا شهرش در فهرست بیاید: سفارش لازم است؛ پس فقط ساختارِ فرم را بررسی می‌کنیم
        page = self.page
        self.open("campaigns")
        self.assertIn("یک کمپین جذاب بسازیم", page.inner_text(".cw-intro h1"))
        page.fill("#id_name", "جشن تخفیف پاییزی")
        page.click('[data-field="audience_kind"][data-value="loyal"]')
        self.assertIn("حداقل ۳ سفارش", page.inner_text("#cw-sum-audience"))
        # «مخاطب خاص»: انتخابِ دسته‌ی کالا بدون انتخابِ مورد ⇒ خطای سمتِ کاربر
        page.click("summary:has-text('مخاطب خاص می‌خواهم')")
        page.select_option("#id_audience_extra_kind", "tag")
        self.next_step()
        self.assertTrue(page.locator("#cw-toast.cw-show").count() == 1)
        page.select_option("#id_audience_extra_kind", "")
        self.next_step()
        page.click('[data-reward="percent"]')
        page.fill("#id_coupon_value", "150")
        self.next_step()
        self.assertTrue(page.locator("#cw-amount-error").is_visible())  # بیش از ۱۰۰٪
        page.fill("#id_coupon_value", "۲۰")
        page.click("#cw-advanced-reward summary")
        page.fill("#id_coupon_max_discount", "۱٬۰۰۰٬۰۰۰")
        page.fill("#id_code_prefix", "pay")
        self.next_step()
        page.wait_for_function("document.getElementById('cw-sms-bubble').textContent.includes('جشن تخفیف پاییزی')")
        bubble = page.inner_text("#cw-sms-bubble")
        self.assertIn("«جشن تخفیف پاییزی»", bubble)
        self.assertIn("PAY-", bubble)
        self.assertIn("۲۰٪", bubble)
        page.click('[data-timing="scheduled"]')
        self.assertTrue(page.locator("#id_active_from").is_visible())
        page.fill("#id_active_from", "")
        page.click("#cw-view-review")
        page.wait_for_selector("#cw-toast.cw-show")
        self.assertEqual(page.locator("#cw-review-overlay.cw-open").count(), 0)  # تاریخ شروع الزامی است
        page.fill("#id_active_from", "۱۴۰۶/۰۸/۱۵")
        page.check("#cw-notify-email")
        page.click("#cw-view-review")
        page.wait_for_selector("#cw-review-overlay.cw-open")
        page.click("#cw-save")
        page.wait_for_url("**/campaigns/*/")
        campaign = Campaign.objects.get()
        self.assertEqual((campaign.status, campaign.trigger_type, campaign.coupon_type, int(campaign.coupon_value), campaign.code_prefix, campaign.channels), ("draft", "scheduled", "percent", 20, "PAY", ["email"]))
        self.assertEqual(campaign.rules, {"type": "lifetime_orders", "op": "gte", "value": "3"})
        self.assertIsNotNone(campaign.active_from)
        self.assert_no_js_errors()

    def test_edit_reopens_saved_values_and_keeps_them(self):
        page = self.page
        campaign = Campaign.objects.create(
            store=self.store, name="قبلی", trigger_type="occasion", occasion_kind="holiday", occasion_params={"month": 9, "day": 30},
            occasion_offset_days=-3, reward_type="coupon", coupon_type="percent", coupon_value=30, code_valid_days=30, channels=["sms"],
            channels_explicit=True, personalized=True,
        )
        page.goto(f"{self.base}/admin-portal/campaigns/{campaign.pk}/edit/")
        page.wait_for_selector("#cw-root")
        self.assertEqual(page.input_value("#id_name"), "قبلی")
        self.assertTrue(page.locator('[data-field="occasion_kind"][data-value="holiday"].cw-active').count() == 1)
        self.assertEqual(page.input_value("#id_occ_day"), "30")
        self.assertEqual(page.locator("#cw-more-occ.cw-hidden").count(), 0)  # مناسبتِ «بیشتر» باز شده است
        self.next_step()
        self.assertEqual(page.input_value("#id_coupon_value"), "30")
        self.assertEqual(page.input_value("#id_code_valid_days"), "30")
        self.next_step()
        self.assertTrue(page.is_checked("#cw-notify-sms"))
        self.assertFalse(page.is_checked("#cw-notify-email"))
        self.assertTrue(page.locator('[data-offset="-3"].cw-active').count() == 1)
        page.wait_for_function("document.getElementById('cw-sms-bubble').textContent.includes('«قبلی»')")
        page.click("#cw-view-review")
        page.wait_for_selector("#cw-review-overlay.cw-open")
        page.click("#cw-save")
        page.wait_for_url("**/campaigns/*/")
        campaign.refresh_from_db()
        self.assertEqual((campaign.name, campaign.occasion_params, campaign.occasion_offset_days, int(campaign.coupon_value), campaign.channels, campaign.status), ("قبلی", {"month": 9, "day": 30}, -3, 30, ["sms"], "draft"))
        self.assert_no_js_errors()

    def test_server_validation_errors_return_to_the_right_step(self):
        page = self.page
        self.open("campaigns")
        page.fill("#id_name", "ک")
        # خطای سمتِ سرور را با مقداری که JS رد نمی‌کند ولی سرور رد می‌کند می‌سازیم (سقفِ تخفیفِ غیرعددی)
        page.evaluate("document.getElementById('id_coupon_max_discount').value = 'abc'")
        page.evaluate("HTMLFormElement.prototype.submit.call(document.getElementById('cw-form'))")
        page.wait_for_selector(".cw-errors")
        self.assertIn("عدد صحیح", page.inner_text(".cw-errors"))
        self.assertTrue(page.locator("#cw-step2:not(.cw-hidden)").count() == 1)  # برگشت به مرحله‌ی مربوط
        self.assertEqual(Campaign.objects.count(), 0)

    def test_layout_is_rtl_and_fits_desktop_and_phone(self):
        page = self.page
        for width, height, label in ((1280, 900, "desktop"), (390, 800, "phone")):
            page.set_viewport_size({"width": width, "height": height})
            self.open("occasions")
            self.assertEqual(page.evaluate("getComputedStyle(document.getElementById('cw-root')).direction"), "rtl")
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1, f"overflow at {label}")
            self.shot(f"occasion_step1_{label}")
            self.next_step()
            self.shot(f"occasion_step2_{label}")
            self.next_step()
            self.shot(f"occasion_step3_{label}")
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1, f"overflow step3 at {label}")
        self.assert_no_js_errors()

    def test_keyboard_flow_enter_goes_next_and_escape_closes_review(self):
        page = self.page
        self.open("occasions")
        page.focus("#id_name")
        page.keyboard.press("Enter")
        self.assertTrue(page.locator("#cw-step2:not(.cw-hidden)").count() == 1)
        self.assertEqual(Campaign.objects.count(), 0)  # Enter هرگز فرم را ناقص ارسال نمی‌کند
        page.click("[data-next='3']")
        page.click("#cw-view-review")
        page.wait_for_selector("#cw-review-overlay.cw-open")
        page.keyboard.press("Escape")
        self.assertEqual(page.locator("#cw-review-overlay.cw-open").count(), 0)
        self.assert_no_js_errors()
