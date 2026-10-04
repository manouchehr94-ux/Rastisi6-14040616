"""Landing page (/) positioning contract.

The redesigned home page must read as a *store-builder platform* within the
first screen, must not present sample products as RastiSi's own inventory, and
must not invent commercial claims (prices, trials, customer counts).
"""

import re

from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PublicHomeLandingTests(TestCase):
    def setUp(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.response = response
        self.html = response.content.decode()

    def _hero(self):
        start = self.html.index('class="rh-hero"')
        return self.html[start:self.html.index('id="stores"')]

    def test_hero_states_the_store_builder_message(self):
        hero = self._hero()
        self.assertEqual(self.html.count("<h1"), 1)
        self.assertIn("با راستی‌سی فروشگاه اینترنتی", hero)
        self.assertIn("خودت را بساز و مدیریت کن", hero)
        self.assertIn("فروشگاه‌ساز", hero)
        self.assertIn("شروع ساخت فروشگاه", hero)

    def test_hero_ctas_point_at_real_destinations(self):
        hero = self._hero()
        self.assertIn('href="/register/"', hero)
        self.assertIn('href="#demo"', hero)
        self.assertIn('id="demo"', self.html)

    def test_hero_does_not_show_a_product_catalogue(self):
        hero = self._hero()
        self.assertNotIn("portal/images/public/", hero)
        self.assertNotIn("<img", hero)

    def test_sample_stores_are_labelled_as_samples(self):
        self.assertEqual(self.html.count("فروشگاه نمونه ساخته‌شده با راستی‌سی"), 3)
        self.assertIn("مشتری یا نمونه‌کار واقعی نیستند", self.html)

    def test_demo_is_clearly_a_demo_and_has_working_controls(self):
        for marker in (
            "data-rh-input-name", "data-rh-layout=", "data-rh-palette=",
            "data-rh-device=", "data-rh-reset",
        ):
            self.assertIn(marker, self.html)
        self.assertIn("حسابی ساخته نمی‌شود و چیزی ذخیره نمی‌شود", self.html)

    def test_no_invented_commercial_claims(self):
        text = re.sub(r"<script.*?</script>", "", self.html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        for claim in ("۲۴ ساعته", "۲۴ساعته", "رایگان", "تومان", "مشتری راضی", "هزار فروشگاه"):
            self.assertNotIn(claim, text, claim)

    def test_page_assets_and_metadata(self):
        self.assertContains(self.response, "public-home-v3.css")
        self.assertContains(self.response, "public-home-v3.js")
        self.assertContains(self.response, 'rel="canonical"')
        self.assertNotContains(self.response, "noindex")


class PublicHomeCssContractTests(SimpleTestCase):
    def test_home_css_keeps_literal_colors_inside_root_tokens(self):
        content = Path("apps/portal/static/portal/css/public-home-v3.css").read_text(encoding="utf-8")
        match = re.search(r":root\s*\{.*?\n\}", content, flags=re.DOTALL)
        self.assertIsNotNone(match)
        outside_root = content[: match.start()] + content[match.end():]
        for pattern in (r"#[0-9a-fA-F]{3,8}\b", r"rgba?\([^)]*\)", r"hsla?\([^)]*\)"):
            self.assertIsNone(re.search(pattern, outside_root), pattern)
