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

    def test_no_absolute_tenant_isolation_claim(self):
        """The repo's own deployment doc still lists Store-boundary hardening as an open item, so the
        public Terms must not promise complete data isolation (regression guard for the reviewed text)."""
        for banned in (
            "فروشگاه‌ها از یکدیگر جدا هستند",
            "هر فروشگاه فقط به داده‌های خودش دسترسی دارد",
            "فقط به داده‌های خودش دسترسی دارد",
            "کاملاً جدا",
            "ایزوله",
            "هیچ فروشگاهی به داده",
            "دسترسی غیرمجاز غیرممکن",
        ):
            self.assertNotIn(banned, self.html)
        stores = self.html[self.html.index('id="stores"'):self.html.index('id="merchant-duty"')]
        self.assertIn("طراحی شده", stores)  # described as design intent…
        self.assertIn("تضمین نمی‌کند", stores)  # …explicitly not a guarantee
        self.assertIn("هنوز در دست تکمیل یا بازبینی", stores)  # consistent with the repo's recorded open work
        self.assertIn("مسئول اقدامات همکاران خود است", stores)  # merchant owns staff access decisions

    def test_other_absolute_security_or_legal_guarantees_are_absent(self):
        for banned in ("کاملاً امن", "صددرصد", "۱۰۰٪", "100%", "بدون هیچ خطر", "هیچ‌گونه نقص", "خطای صفر", "تا زمانی که خلاف آن ثابت نشده"):
            self.assertNotIn(banned, self.html)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class TermsLayoutContractTests(TestCase):
    """Layout contract: full-width head, TOC column + document column, anchors clear the sticky header."""

    def setUp(self):
        self.html = self.client.get("/terms/", HTTP_HOST=_HOST).content.decode()
        from pathlib import Path

        css_path = Path(__file__).resolve().parents[1] / "static" / "portal" / "css" / "public-site-v2.css"
        self.css = css_path.read_text(encoding="utf-8")

    def test_page_is_a_two_column_layout_not_a_narrow_body(self):
        self.assertIn('class="r-legal-layout"', self.html)
        self.assertIn('class="r-legal-aside"', self.html)
        # the old pattern (780px head/body inside a 1248px container) must not return
        self.assertNotRegex(self.css, r"\.r-legal-(head|body)\{[^}]*max-width:780px")
        self.assertNotIn("r-legal-body", self.html)

    def test_toc_is_a_single_collapsible_nav_with_one_link_per_section(self):
        self.assertEqual(self.html.count("data-legal-toc"), 2)  # attribute + script lookup
        toc = self.html[self.html.index("<details"):self.html.index("</details>")]
        self.assertEqual(toc.count('href="#'), len(SECTIONS))
        self.assertIn(f"{len(SECTIONS)} بخش".replace("18", "۱۸"), toc)

    def test_every_anchor_target_has_a_scroll_margin_below_the_sticky_header(self):
        rule = re.search(r"\.r-legal-section\{[^}]*\}", self.css).group(0)
        self.assertIn("scroll-margin-top:calc(var(--r-legal-header) + var(--r-legal-gap))", rule)
        self.assertRegex(self.css, r"\.r-legal\{--r-legal-header:86px")
        self.assertRegex(self.css, r"max-width:720px\)\{\.r-legal\{--r-legal-header:74px\}")
        # anchors are on the section element that carries the scroll margin
        self.assertEqual(self.html.count('class="r-legal-section" id='), len(SECTIONS))

    def test_toc_is_sticky_on_desktop_and_static_below_the_tablet_breakpoint(self):
        self.assertRegex(self.css, r"\.r-legal-aside\{position:sticky;top:calc\(var\(--r-legal-header\)")
        self.assertRegex(self.css, r"max-width:960px\)\{[^@]*\.r-legal-aside\{position:static")

    def test_stylesheet_is_cache_busted_for_this_change(self):
        self.assertIn("public-site-v2.css?v=20261009-a11y", self.html)
