import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings


PUBLIC_TEMPLATE_DIR = Path("apps/portal/templates/portal/public")
PUBLIC_CSS = Path("apps/portal/static/portal/css/public-site-v2.css")
_HOST = "rastisi.localhost"


class PublicSiteThemeContractTests(SimpleTestCase):
    def test_public_templates_do_not_define_local_styles_or_colors(self):
        offenders = []
        for path in sorted(PUBLIC_TEMPLATE_DIR.glob("*.html")):
            content = path.read_text(encoding="utf-8")
            reasons = []
            if re.search(r"<style\b", content, flags=re.IGNORECASE):
                reasons.append("<style>")
            if re.search(r"\sstyle\s*=", content, flags=re.IGNORECASE):
                reasons.append("style=")
            if re.search(r"#[0-9a-fA-F]{3,8}\b", content):
                reasons.append("hex-color")
            if reasons:
                offenders.append(f"{path}: {', '.join(reasons)}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_public_css_keeps_literal_colors_inside_root_tokens(self):
        content = PUBLIC_CSS.read_text(encoding="utf-8")
        match = re.search(r":root\s*\{.*?\}", content, flags=re.DOTALL)
        self.assertIsNotNone(match, "public-site-v2.css must define a :root token block")

        outside_root = content[: match.start()] + content[match.end() :]
        literal_patterns = [
            r"#[0-9a-fA-F]{3,8}\b",
            r"rgba?\([^)]*\)",
            r"hsla?\([^)]*\)",
        ]
        for pattern in literal_patterns:
            self.assertIsNone(
                re.search(pattern, outside_root),
                f"Theme color literal found outside :root: {pattern}",
            )


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PublicSitePageSmokeTests(TestCase):
    def test_marketing_pages_render(self):
        for path in [
            "/",
            "/features/",
            "/design/",
            "/plans/",
            "/about/",
            "/contact/",
            "/help/",
            "/supported-industries/",
            "/terms/",
            "/privacy/",
            "/register/",
            "/login/",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "public-site-v2.css")
