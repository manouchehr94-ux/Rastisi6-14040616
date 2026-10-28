"""Dev/build-time command (never part of a normal request): photographs every registered header / footer model of ``global_region_registry``
as it is REALLY rendered, for the Vision Studio model gallery.

    python manage.py runserver 127.0.0.1:8000                      # a real server, started separately by the operator
    python manage.py capture_global_region_previews --base-url http://rasti-mode-demo.rastisi.localhost:8000 --user <staff username>

How: the staff-only, read-only ``vision-studio/region-preview/`` view renders the store's own shell with exactly one region swapped for the
asked registry variant; this command opens it in headless Chromium at a desktop and a phone width, crops the candidate region and stores
``region_previews/<region>/<key>.<device>.webp`` + ``manifest.json`` (fingerprint of the renderer and the templates it includes, plus ``same_as``
when two models render pixel-identically). Run it against a store with fixed sample data (the canonical Rasti Mode Demo store); images that
the environment cannot load are removed before the shot so no broken-image icon is photographed.

It writes only these static files - no Draft, no database row - and requires a staff user (the session is minted with the test client)."""

import hashlib
import io
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder import vision_ux

from .capture_ready_template_previews import _find_chromium_executable

VIEWPORTS = {"desktop": {"width": 1280, "height": 900, "scale": 1}, "mobile": {"width": 390, "height": 844, "scale": 2}}
_FREEZE_CSS = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"
#: two photographs count as the same look when their mean per-channel difference is below this (0-255): capture noise (anti-aliasing, a
#: sub-pixel shift) must not make a look-alike pass for a distinct model
_SAME_LOOK_MEAN_DIFF = 0.6
_DROP_BROKEN_IMAGES = """() => { document.querySelectorAll('img').forEach(i => { if (i.complete && i.naturalWidth === 0) i.remove(); }); }"""


class Command(BaseCommand):
    help = "Capture the real renders of the registered header / footer models for the Vision Studio gallery (dev/build tool)."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", required=True, help="a running server on the demo store's host, e.g. http://rasti-mode-demo.rastisi.localhost:8000")
        parser.add_argument("--user", required=True, help="username of a staff member who may manage this store's layout")
        parser.add_argument("--region", choices=("header", "footer", "all"), default="all")
        parser.add_argument("--only", help="capture just this variant key (keeps the other manifest entries)")

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from playwright.sync_api import sync_playwright

        executable = _find_chromium_executable()
        if not executable:
            raise CommandError("no Chromium / Chrome executable found")
        user = get_user_model().objects.filter(username=options["user"]).first()
        if user is None:
            raise CommandError("unknown user")
        client = Client()
        client.force_login(user)
        session_id = client.cookies["sessionid"].value
        base = options["base_url"].rstrip("/")
        host = base.split("//", 1)[1].split(":")[0]

        regions = ("header", "footer") if options["region"] == "all" else (options["region"],)
        manifest = vision_ux.load_manifest()
        out_root = Path(vision_ux.PREVIEWS_DIR)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=executable)
            for region_key in regions:
                region = vision_ux.REGIONS[region_key]
                entries = manifest.setdefault(region_key, {})
                seen_images = []   # one (key, markup hash, desktop png, mobile png) per DISTINCT look so far
                for variant in region.variants:
                    if options["only"] and variant.key != options["only"]:
                        continue
                    shots = {}
                    for device, vp in VIEWPORTS.items():
                        context = browser.new_context(
                            viewport={"width": vp["width"], "height": vp["height"]}, device_scale_factor=vp["scale"], locale="fa-IR",
                        )
                        context.add_cookies([{"name": "sessionid", "value": session_id, "domain": host, "path": "/"}])
                        page = context.new_page()
                        response = page.goto(f"{base}/admin-portal/vision-studio/region-preview/?region={region_key}&variant={variant.key}", wait_until="networkidle")
                        if response is None or response.status != 200:
                            raise CommandError(f"{region_key}/{variant.key}/{device}: HTTP {response.status if response else '?'}")
                        page.add_style_tag(content=_FREEZE_CSS)
                        page.evaluate(_DROP_BROKEN_IMAGES)
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(250)
                        target = page.locator(f'[data-vs-region="{region_key}"]')
                        shots[device] = target.screenshot()
                        if device == "desktop":
                            markup = re.sub(r"\s+", " ", target.evaluate("e => e.outerHTML"))
                        context.close()
                    self._save(out_root, region_key, variant.key, shots)
                    same_as = self._twin_of(seen_images, variant.key, shots, hashlib.sha256(markup.encode("utf-8")).hexdigest())
                    entries[variant.key] = {"fingerprint": vision_ux.variant_fingerprint(region_key, variant), "same_as": same_as}
                    self.stdout.write(f"{region_key}/{variant.key}" + (f"  (renders identically to {same_as})" if same_as else ""))
            browser.close()
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "manifest.json").write_text(
            json.dumps({"version": vision_ux.MANIFEST_VERSION, "regions": manifest}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS("done"))

    @staticmethod
    def _mean_diff(a_png, b_png):
        from PIL import Image, ImageChops, ImageStat

        a = Image.open(io.BytesIO(a_png)).convert("RGB")
        b = Image.open(io.BytesIO(b_png)).convert("RGB")
        if a.size != b.size:
            return 255.0
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3

    def _twin_of(self, distinct, key, shots, markup_hash):
        """The key of an earlier DISTINCT model this one looks like (same markup, or a near-identical photograph on both devices), else None;
        a model with a new look is added to ``distinct``."""
        for other_key, other_markup, desktop, mobile in distinct:
            if other_markup == markup_hash or (
                self._mean_diff(shots["desktop"], desktop) < _SAME_LOOK_MEAN_DIFF and self._mean_diff(shots["mobile"], mobile) < _SAME_LOOK_MEAN_DIFF
            ):
                return other_key
        distinct.append((key, markup_hash, shots["desktop"], shots["mobile"]))
        return None

    def _save(self, out_root, region_key, variant_key, shots):
        from PIL import Image

        folder = out_root / region_key
        folder.mkdir(parents=True, exist_ok=True)
        for device, png in shots.items():
            image = Image.open(io.BytesIO(png)).convert("RGB")
            image.save(folder / f"{variant_key}.{device}.webp", "WEBP", quality=80, method=6)
