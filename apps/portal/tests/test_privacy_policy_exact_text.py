"""The published privacy body must equal the owner's Appendix A (docs/legal/PRIVACY_POLICY_APPENDIX_A.md) block by block.
Only whitespace and markdown markers are normalized; ZWNJ (U+200C) and every Persian character must match exactly."""

import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup
from django.conf import settings
from django.test import TestCase, override_settings

APPENDIX = Path(settings.BASE_DIR) / "docs" / "legal" / "PRIVACY_POLICY_APPENDIX_A.md"


def _norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _expected():
    title, blocks = "", []
    for line in APPENDIX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line == "---":
            continue
        if line.startswith("# "):
            title = _norm(line[2:])
            continue
        blocks.append(_norm(re.sub(r"^(##\s+|-\s+)", "", line).replace("**", "")))
    return title, blocks


_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PrivacyPolicyExactTextTests(TestCase):
    def setUp(self):
        response = self.client.get("/privacy/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        page = BeautifulSoup(response.content.decode("utf-8"), "html.parser")
        self.h1 = _norm(page.find("h1").get_text())
        self.soup = page.select_one("article") or page.select_one(".legal-doc")

    def test_every_block_matches_appendix_a_exactly(self):
        _title, expected = _expected()
        rendered = [_norm(e.get_text()) for e in self.soup.find_all(["p", "h2", "li"])]
        self.assertEqual(len(expected), len(rendered))
        for index, (want, got) in enumerate(zip(expected, rendered)):
            self.assertEqual(want, got, f"block {index} differs")

    def test_title_and_contact_link(self):
        title, _ = _expected()
        self.assertEqual(self.h1, title)
        links = [(a.get_text(), a["href"]) for a in self.soup.find_all("a")]
        self.assertEqual(links, [("تماس با ما", "/contact/")])
