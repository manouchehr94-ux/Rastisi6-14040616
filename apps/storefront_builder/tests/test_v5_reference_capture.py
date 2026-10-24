"""Opt-in reference capture (``SFB_REFERENCE_CAPTURE="Site:preset_key[,Site:preset_key]"``): renders the published Home and one
product page of a throw-away Store with the given Ready Template and saves full-page screenshots to ``SFB_SCREENSHOT_DIR``.
Skipped in normal runs; never touches a real Store/database/media (use an isolated ``DJANGO_MEDIA_ROOT``)."""

import os

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
import unittest
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from apps.storefront_builder.qa import reference_capture as rc
from apps.storefront_builder.qa import reference_packs  # noqa: F401  (registers the packs)

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

SPEC = os.environ.get("SFB_REFERENCE_CAPTURE", "")
HOST = "ref-capture.example.com"


def _browser_path():
    for candidate in ("/opt/pw-browsers/chromium",):
        if os.path.exists(candidate):
            return candidate
    return None


@unittest.skipUnless(SPEC and sync_playwright, "set SFB_REFERENCE_CAPTURE=Site:preset_key to run")
@override_settings(ALLOWED_HOSTS=[HOST, "testserver", "localhost", "127.0.0.1"])
class ReferenceCaptureTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1"],
                  "ignore_default_args": ["--hide-scrollbars"]}
        path = _browser_path()
        if path:
            launch["executable_path"] = path
        cls.browser = cls.pw.chromium.launch(**launch)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def test_capture(self):
        out = Path(os.environ.get("SFB_SCREENSHOT_DIR", "/tmp/sfb-capture"))
        port = self.live_server_url.rsplit(":", 1)[1]
        base = f"http://{HOST}:{port}"
        for item in SPEC.split(","):
            site, _, preset = item.partition(":")
            with self.subTest(site=site, preset=preset):
                from apps.stores.models import Store

                Store.objects.filter(slug=f"cap-{site.lower()}").delete()
                print('SEEDING', site, flush=True)
                store, owner, products = rc.seed_store(site, image_mode=os.environ.get("SFB_IMAGE_MODE", "reference"),
                                                       preset_key=preset or None, host=HOST)
                print('SEEDED', len(products), flush=True)
                pdp = reverse("catalog:product-detail", args=[products[0].slug])
                with rc.patched_best_sellers(products):
                    for name, path in (("home", "/"), ("product", pdp)):
                        for viewport in ("desktop", "mobile"):
                            geometry = rc.capture_page(self.browser, base, HOST, path, viewport, out / site / f"{name}-{viewport}.png")
                            print(f"CAPTURE {site} {name}-{viewport} {geometry}")
