from django.test import TestCase, override_settings

from apps.catalog.models import IndustryTemplate

_HOST = "rastisi.localhost"


def _make_template(**kwargs):
    defaults = {
        "slug": "pub-test-industry", "name": "صنفِ آزمایشیِ عمومی", "icon": "🧪",
        "sector": IndustryTemplate.Sector.RETAIL, "version": 1, "is_active": True,
        "readiness": IndustryTemplate.Readiness.PRODUCTION_READY,
    }
    defaults.update(kwargs)
    return IndustryTemplate.objects.create(**defaults)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SupportedIndustriesPageTests(TestCase):
    """بخشِ ۶ (صفحه‌ی عمومیِ صنوفِ پشتیبانی‌شده) + بخشِ ۱۷ (تست‌های صفحه‌ی عمومی).

    از مسیرِ لفظی (نه ``reverse()``) استفاده می‌کند — همان الگویِ سایرِ
    تست‌هایِ پورتالِ عمومی (مثلاً ``test_seo.py``)، چون ``ROOT_URLCONF``ِ
    پیش‌فرض شامل namespace ``portal`` نیست (این namespace فقط از طریقِ
    ``PlatformHostRoutingMiddleware`` و ``request.urlconf`` بارگذاری
    می‌شود، نه در سطحِ ماژول)."""

    def setUp(self):
        self.active_template = _make_template(slug="pub-active", name="صنفِ فعالِ آزمایشی")
        self.inactive_template = _make_template(
            slug="pub-inactive", name="صنفِ غیرفعالِ آزمایشی", is_active=False,
        )
        self.draft_template = _make_template(
            slug="pub-draft", name="صنفِ پیش‌نویسِ آزمایشی", readiness=IndustryTemplate.Readiness.DRAFT,
        )

    def test_page_loads_and_shows_only_offerable_templates(self):
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "صنفِ فعالِ آزمایشی")
        self.assertNotContains(response, "صنفِ غیرفعالِ آزمایشی")
        self.assertNotContains(response, "صنفِ پیش‌نویسِ آزمایشی")

    def test_review_required_templates_are_not_listed_publicly(self):
        """The completeness gate: a structurally valid but skeletal template is
        REVIEW_REQUIRED and must not be advertised on the public page."""
        _make_template(
            slug="pub-review", name="صنفِ نیازمندِ بازبینیِ آزمایشی",
            readiness=IndustryTemplate.Readiness.REVIEW_REQUIRED,
        )
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "صنفِ نیازمندِ بازبینیِ آزمایشی")
        self.assertEqual(response.context["industry_count"], 1)

    def test_hero_count_matches_real_active_count(self):
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertEqual(response.context["industry_count"], 1)

    def test_sector_tabs_rendered(self):
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertContains(response, "خرده‌فروشی و پوشاک")
        self.assertContains(response, "همه صنوف")

    def test_cta_uses_url_reverse_not_static_link(self):
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertContains(response, 'href="/register/"')
        self.assertNotContains(response, "register.html")

    def test_empty_search_state_markup_present(self):
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertContains(response, "صنف مورد نظر یافت نشد")

    def test_no_industries_still_returns_200(self):
        IndustryTemplate.objects.all().delete()
        response = self.client.get("/supported-industries/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["industry_count"], 0)
