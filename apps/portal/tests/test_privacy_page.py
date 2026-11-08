"""The public Privacy page publishes the owner's approved policy text (no draft wording, no old policy)."""

import re

from django.test import TestCase, override_settings

_HOST = "rastisi.localhost"
TITLE = "سیاست حفظ حریم خصوصی کاربران راستی\u200cسی"
DATE = "۱۶ آبان ۱۴۰۵"
SECTIONS = [
    "۱. اطلاعاتی که دریافت می\u200cکنیم",
    "۲. نحوه استفاده از اطلاعات",
    "۳. اطلاعات مشتریان فروشگاه\u200cها",
    "۴. امنیت و محرمانگی اطلاعات",
    "۵. پرداخت\u200cها و خدمات جانبی",
    "۶. کوکی\u200cها",
    "۷. نگهداری و حذف اطلاعات",
    "۸. ارائه اطلاعات به مراجع قانونی",
    "۹. تغییرات سیاست حریم خصوصی",
    "۱۰. ارتباط با راستی\u200cسی",
]
SAMPLES = [
    "حفظ حریم خصوصی و امنیت اطلاعات کاربران برای راستی\u200cسی اهمیت زیادی دارد.",
    "ایجاد و مدیریت حساب کاربران و فروشگاه\u200cها.",
    "مالک هر فروشگاه نیز موظف است اطلاعات مشتریان خود را به\u200cصورت مسئولانه و مطابق قوانین مربوط استفاده کند.",
    "رمزهای عبور حساب\u200cها به\u200cصورت هش\u200cشده ذخیره می\u200cشوند",
    "راستی\u200cسی نیازی به دریافت رمز بانکی کاربران ندارد.",
    "کاربران می\u200cتوانند از طریق تنظیمات مرورگر، کوکی\u200cهای خود را مدیریت یا حذف کنند.",
    "پایان اشتراک فروشگاه لزوماً به معنی حذف فوری تمام اطلاعات آن نیست.",
    "در صورت دریافت درخواست قانونی معتبر از مراجع ذی\u200cصلاح",
    "نسخه به\u200cروزشده همراه با تاریخ آخرین تغییر در وب\u200cسایت منتشر می\u200cشود",
    "تلاش می\u200cکنیم درخواست\u200cهای مرتبط با اطلاعات کاربران را با رعایت الزامات امنیتی و قانونی بررسی کنیم.",
    "ما تلاش می\u200cکنیم محیطی امن، قابل\u200cاعتماد و شفاف برای راه\u200cاندازی و مدیریت کسب\u200cوکارهای اینترنتی فراهم کنیم.",
]


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PrivacyPageTests(TestCase):
    design = None

    def setUp(self):
        response = self.client.get("/privacy/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_title_date_and_signoff(self):
        self.assertIn(TITLE, self.html)
        self.assertIn(f"آخرین به\u200cروزرسانی: {DATE}", self.html)
        self.assertIn("راستی\u200cسی | فروشگاه\u200cساز اینترنتی", self.html)
        self.assertEqual(self.html.count("<h1"), 1)
        self.assertIn('dir="rtl"', self.html)

    def test_ten_sections_in_order(self):
        headings = re.findall(r"<h2>([^<]+)</h2>", self.html)
        self.assertEqual(headings, SECTIONS)

    def test_verbatim_sentences_and_bullet_list(self):
        for sample in SAMPLES:
            with self.subTest(sample=sample):
                self.assertIn(sample, self.html)
        self.assertEqual(self.html.count("<li>ایجاد") + self.html.count("<li>ارائه") + self.html.count("<li>پردازش")
                         + self.html.count("<li>ارسال") + self.html.count("<li>حفظ"), 6)

    def test_contact_link_resolves(self):
        self.assertIn('«<a href="/contact/">تماس با ما</a>»', self.html)
        self.assertEqual(self.client.get("/contact/", HTTP_HOST=_HOST).status_code, 200)

    def test_old_policy_and_draft_wording_are_gone(self):
        for old in ("نمونهٔ ساختاری", "نمونهی ساختاری", "پیش از انتشار رسمی", "نیازمند بازبینی حقوقی",
                    "نسخه رسمی این سند", "data-legal-draft-notice", "این صفحه ساختار توضیح"):
            self.assertNotIn(old, self.html)
        self.assertNotRegex(self.html, r"پیش\u200cنویس")

    def test_no_script_injection(self):
        self.assertNotIn("<script>alert", self.html)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], PUBLIC_SITE_FORCE_DESIGN="legacy")
class PrivacyPageLegacyDesignTests(PrivacyPageTests):
    pass
