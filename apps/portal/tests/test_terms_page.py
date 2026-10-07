"""The public Terms page is a real (draft) document, not the old four-item placeholder."""

import re

from django.test import TestCase, override_settings

_HOST = "rastisi.localhost"

#: the sections the brief requires, as (anchor id, heading text)
SECTIONS = [
    ("scope", "محدوده و پذیرش قوانین"),
    ("account", "ثبت‌نام و امنیت حساب"),
    ("mobile", "تأیید موبایل و مسئولیت دسترسی"),
    ("stores", "ساخت و مدیریت فروشگاه"),
    ("merchant-duty", "مسئولیت مالک درباره‌ی کالا، خدمت و محتوا"),
    ("commitments", "قیمت، موجودی، ارسال، بازگشت و تعهد به مشتری"),
    ("role", "نقش راستی‌سی؛ زیرساخت فنی، نه فروشنده"),
    ("plans", "پلن‌ها، دوره‌ی آزمایشی، صورتحساب و محدودیت‌های سرویس"),
    ("notifications", "پیامک، ایمیل و اعلان‌ها و رضایت"),
    ("abuse", "استفاده مجاز و موارد ممنوع"),
    ("content", "دامنه، محتوای بارگذاری‌شده و دارایی‌های مالک"),
    ("availability", "در دسترس‌بودن، نگه‌داری و وابستگی به خدمات ثالث"),
    ("suspension", "تعلیق، محدودسازی و حذف فروشگاه"),
    ("privacy", "داده‌ها و حریم خصوصی"),
    ("ip", "مالکیت فکری پلتفرم و محتوای مالک"),
    ("changes", "تغییر در خدمات و قوانین"),
    ("support", "پشتیبانی و راه ارتباط"),
    ("disclaimer", "وضعیت این متن؛ پیش‌نویس و نیازمند بازبینی حقوقی"),
]


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class TermsPageTests(TestCase):
    def setUp(self):
        response = self.client.get("/terms/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.html = response.content.decode()

    def test_every_required_section_renders_with_an_anchor_and_a_toc_entry(self):
        for anchor, title in SECTIONS:
            with self.subTest(anchor=anchor):
                self.assertIn(f'id="{anchor}"', self.html)
                self.assertIn(f'<a href="#{anchor}">{title}</a>', self.html)
                self.assertRegex(self.html, rf'<h2 id="{anchor}-title"><span class="r-legal-num">\d+</span>{re.escape(title)}</h2>')
        self.assertEqual(self.html.count('class="r-legal-section"'), len(SECTIONS))

    def test_the_old_placeholder_is_gone_and_the_page_is_substantial(self):
        self.assertNotIn("نمونهٔ ساختاری", self.html)
        self.assertNotIn("زیرساخت فنی فروشگاه‌سازی را فراهم می‌کند و طرف معامله خرید و فروش نیست.</li>", self.html)
        body = re.sub(r"<[^>]+>", " ", self.html)
        self.assertGreater(len(body.split()), 1200)
        self.assertGreaterEqual(self.html.count("<p>"), 30)

    def test_the_draft_and_legal_review_notice_is_prominent_and_repeated_at_the_end(self):
        top = self.html.index("data-legal-draft-notice")
        self.assertLess(top, self.html.index('id="scope"'))
        self.assertRegex(self.html, r"پیش‌نویس[^<]*نیازمند بازبینی حقوقی")
        self.assertIn("تأیید حقوقی", self.html)
        disclaimer = self.html[self.html.index('id="disclaimer"'):]
        self.assertIn("هنوز توسط مشاور حقوقی یا صاحب پلتفرم بازبینی و تأیید نشده است", disclaimer)
        self.assertIn("مشاوره‌ی حقوقی", disclaimer)

    def test_the_merchant_is_the_seller_and_rastisi_is_infrastructure(self):
        role = self.html[self.html.index('id="role"'):self.html.index('id="plans"')]
        self.assertIn("فروشنده", role)
        self.assertIn("طرف قرارداد خرید و فروشی", role)
        self.assertIn("زیرساخت فنی", role)

    def test_links_to_privacy_and_contact_resolve(self):
        self.assertIn('href="/privacy/"', self.html)
        self.assertIn('href="/contact/"', self.html)
        for path in ("/privacy/", "/contact/"):
            self.assertEqual(self.client.get(path, HTTP_HOST=_HOST).status_code, 200)

    def test_no_unsupported_claims(self):
        for claim in ("99.9", "۹۹٫۹", "ضمانت آپتایم", "کاملاً مطابق", "دارای مجوز", "تأییدشده توسط", "ای‌نماد", "گواهی"):
            self.assertNotIn(claim, self.html)

    def test_rtl_document_with_the_shared_public_layout(self):
        self.assertIn('dir="rtl"', self.html)
        self.assertIn('class="r-legal"', self.html)
        self.assertIn('class="r-legal-toc"', self.html)
        self.assertEqual(self.html.count("<h1"), 1)
        self.assertIn('aria-label="فهرست مطالب"', self.html)
