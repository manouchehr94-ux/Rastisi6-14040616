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
        # overlay scrollbars (``--hide-scrollbars`` is Playwright's default): the reference pictures are exactly the viewport wide
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {HOST} 127.0.0.1"]}
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
                lab_name = preset if preset.startswith("lab_") else ""
                store, owner, products = rc.seed_store(site, image_mode=os.environ.get("SFB_IMAGE_MODE", "reference"),
                                                       preset_key=None if lab_name else (preset or None), host=HOST)
                if lab_name:
                    from apps.content.models import PromotionalBanner
                    from apps.storefront_builder.qa import composition_lab

                    pool = (rc.reference_images(site, rc.PACKS[site].get("exclude_images", "")) if os.environ.get("SFB_IMAGE_MODE", "reference") == "reference" else {})
                    pictures = (pool.get("products") or []) + (pool.get("squares") or []) + (pool.get("wide") or [])
                    counter = {"n": 0}

                    def picture(section, _store=store):
                        path = pictures[counter["n"] % len(pictures)] if pictures else None
                        counter["n"] += 1
                        row = PromotionalBanner(store=_store, section=section, is_active=True, display_order=0)
                        row.desktop_image = rc.uploaded(path, "lab.jpg", max_side=1400, size=(1200, 800))
                        row.save()

                    composition_lab.build(lab_name, store, owner, picture=picture)
                print('SEEDED', len(products), flush=True)
                pack = rc.PACKS[site]
                at = rc.pdp_product_index(pack)
                pdp = reverse("catalog:product-detail", args=[products[at].slug])
                with rc.patched_best_sellers(products):
                    for name, path in (("home", "/"), ("product", pdp)):
                        for viewport in ("desktop", "mobile"):
                            geometry = rc.capture_page(self.browser, base, HOST, path, viewport, out / (f"{site}-{lab_name}" if lab_name else site) / f"{name}-{viewport}.png", site=site)
                            print(f"CAPTURE {site} {name}-{viewport} {geometry}")
