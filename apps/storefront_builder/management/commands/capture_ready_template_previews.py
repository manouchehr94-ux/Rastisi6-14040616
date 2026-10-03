"""دستورِ dev/build-time (هرگز بخشی از یک درخواستِ عادیِ Gallery) برایِ
ساختنِ اسکرین‌شاتِ واقعیِ Ready Template Gallery — مأموریتِ «Rasti Mode
Demo — COMPLETE REAL CATALOG + MEDIA + CONTENT + ALL 8 READY TEMPLATE REAL
PREVIEWS».

معماری (Step 23 کار):
    فروشگاهِ نمایشیِ واقعیِ Rasti Mode Demo
        -> رندررِ واقعیِ Storefrontِ عمومی (یک ``manage.py runserver``یِ
           واقعی که اپراتور جداگانه بالا می‌آورد — این دستور هرگز خودش
           سرور را بالا/پایین نمی‌کند)
        -> Captureِ مرورگر در همین ابزارِ dev/build (Playwright +
           Chromiumِ از‌قبل‌نصب‌شده — با fallback به ``playwright install
           chromium`` اگر موجود نبود)
        -> WebPِ استاتیکِ نسخه‌دارِ (key/version) + یک متادیتایِ کوچکِ
           هش‌شده (برایِ کشفِ Stale شدن — نگاه کنید به
           ``template_preview_service.resolve_real_screenshot``)
        -> Ready Template Gallery

ایمنی:
    - فقط رویِ Storeِ ثابتِ ``rasti-mode-demo`` کار می‌کند — هیچ آرگومانی
      برایِ هدف‌گیریِ Storeِ دیگر وجود ندارد.
    - Draft/Published همینِ یک Storeِ Demo را (به‌ازایِ هر Template، یک
      Apply+Publish واقعی) mutate می‌کند — این دقیقاً همان ابزارِ
      dev/build است که معماریِ بالا آن را صریحاً مجاز کرده؛ یک درخواستِ
      عادیِ Gallery هرگز این دستور یا Playwright را صدا نمی‌زند.
    - Idempotent نسبت به rate limit: اگر Preset فعلاً‌منتشرشده همان
      Presetِ هدف باشد، Apply/Publishِ تازه صدا زده نمی‌شود (دقیقاً همان
      الگویِ ``seed_rastisi_fashion_demo._seed_builder``).

استفاده (اپراتور باید یک سرورِ واقعی را از قبل بالا آورده باشد):
    python manage.py runserver 127.0.0.1:8000     # در یک ترمینالِ جدا
    python manage.py capture_ready_template_previews --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import layout_service, preset_service
from apps.storefront_builder.services.template_preview_service import (
    APP_STATIC_DIR,
    meta_relpath,
    preview_content_hash,
    preview_input_fingerprint,
    screenshot_relpath,
)
from apps.stores.models import Store

STORE_SLUG = "rasti-mode-demo"

CANONICAL_VIEWPORT = {"width": 1440, "height": 1100}
QA_VIEWPORTS = {
    "home_mobile": {"width": 390, "height": 844},
    "listing_desktop": {"width": 1440, "height": 1100},
    "pdp_desktop": {"width": 1440, "height": 1100},
}

_CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]


def _find_chromium_executable() -> str | None:
    """Resolve an already-installed Chromium-family browser cross-platform.

    The preview pipeline is a dev/build tool and should not require a Playwright
    browser download when Chrome/Edge is already installed on the operator's
    machine. Linux CI keeps its existing /opt/pw-browsers lookup, while Windows
    QA can reuse the locally installed Chrome/Edge executable.
    """
    import glob

    candidates = [Path(candidate) for candidate in _CHROMIUM_CANDIDATES]

    program_files = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for base in filter(None, program_files):
        base_path = Path(base)
        candidates.extend([
            base_path / "Google/Chrome/Application/chrome.exe",
            base_path / "Chromium/Application/chrome.exe",
            base_path / "Microsoft/Edge/Application/msedge.exe",
        ])

    for executable_name in (
        "chrome", "chrome.exe", "chromium", "chromium.exe",
        "msedge", "msedge.exe",
    ):
        resolved = shutil.which(executable_name)
        if resolved:
            candidates.append(Path(resolved))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    for match in glob.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome"):
        return match
    return None


class Command(BaseCommand):
    help = (
        "ابزارِ dev/build (نه بخشی از Runtime عادی) — برایِ هر ۸ Ready "
        "Templateِ رسمی، یک اسکرین‌شاتِ کانونیکِ HOME از فروشگاهِ نمایشیِ "
        "واقعیِ Rasti Mode Demo می‌گیرد و به‌عنوانِ WebPِ نسخه‌دار ذخیره "
        "می‌کند."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url", default="http://127.0.0.1:8000",
            help="آدرسِ یک سرورِ واقعیِ از‌قبل‌درحالِ‌اجرا (این دستور خودش سرور را بالا نمی‌آورد).",
        )
        parser.add_argument(
            "--full-qa", action="store_true",
            help="علاوه‌بر اسکرین‌شاتِ کانونیکِ Gallery، عکس‌هایِ QAیِ اضافی (موبایلِ HOME، LISTING، PDP) هم بگیر.",
        )
        parser.add_argument(
            "--qa-output-dir", default="docs/qa_evidence/ready_template_previews",
            help="پوشه‌یِ عکس‌هایِ QAیِ اضافی (--full-qa).",
        )
        parser.add_argument(
            "--only", default=None,
            help=(
                "فقط همین یک کلیدِ Ready Template را Apply/Publish/Capture کن "
                "(بقیه‌یِ ۷ اسکرین‌شاتِ کامیت‌شده کاملاً دست‌نخورده می‌مانند) — "
                "برایِ زمانی که فقط یک قالب در یک فازِ Overhaul تغییر کرده است، "
                "نه هر ۸ تا."
            ),
        )

    def handle(self, *args, **options):
        store = Store.objects.filter(slug=STORE_SLUG).first()
        if store is None:
            raise CommandError(
                f"Storeِ Demo «{STORE_SLUG}» وجود ندارد — اول "
                "seed_ready_template_fashion_demo را اجرا کنید."
            )

        chromium_path = _find_chromium_executable()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CommandError(
                "پکیجِ playwright نصب نیست — ``pip install playwright`` را اجرا کنید "
                "(نیازی به ``playwright install`` نیست اگر Chromiumِ از‌قبل‌نصب‌شده در "
                "دسترس باشد؛ در غیرِ این صورت ``playwright install chromium``)."
            ) from exc

        raw_base_url = options["base_url"].rstrip("/")
        self._check_server_reachable(raw_base_url)

        public_host = self._resolve_public_host(store)
        parsed = urlsplit(raw_base_url)
        port_suffix = f":{parsed.port}" if parsed.port else ""
        # حیاتی: باید واقعاً به میزبانِ عمومیِ Store مرور کنیم (نه به IPِ
        # خامِ --base-url) — Djangoِ Host-based routing، Store را از رویِ
        # هدرِ Host تشخیص می‌دهد؛ مرور به IP باعث می‌شد Django به‌جایِ
        # rasti-mode-demo یک Storeِ دیگر/پیش‌فرض را برگرداند، و همه‌یِ ۸
        # Captureِ خروجی (فارغ از هر Presetی) یکی می‌شدند — دقیقاً همان
        # علتِ ریشه‌ایِ باگِ «هر ۸ WebP بایت‌به‌بایت یکسان» که حینِ اجرایِ
        # واقعی کشف شد. --host-resolver-rules فقط تضمین می‌کند که همین
        # درخواستِ نام‌محور همچنان به IP محلیِ سرور برسد.
        base_url = f"{parsed.scheme}://{public_host}{port_suffix}"
        self.stdout.write(f"Storeِ Demo: {store.slug}  میزبانِ عمومی: {public_host}  سرور: {raw_base_url}")

        launch_kwargs = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {public_host} 127.0.0.1"]}
        if chromium_path:
            launch_kwargs["executable_path"] = chromium_path

        templates = lpr.list_ready_templates()
        only_key = options.get("only")
        if only_key:
            templates = [t for t in templates if t.key == only_key]
            if not templates:
                raise CommandError(f"کلیدِ Ready Templateِ «{only_key}» در فهرستِ رسمی نیست.")
        self.stdout.write(f"تعدادِ Ready Templateِ رسمی: {len(templates)}")

        # sync_playwright() یک asyncio event loopِ درحالِ‌اجرا در همینِ
        # Threadِ فراخوان نصب می‌کند — Djangoِ ORM هر Queryِ sync را از
        # داخلِ چنین Threadی رد می‌کند (SynchronousOnlyOperation، کشف‌شده
        # حینِ اجرایِ واقعی). راه‌حل: هر نوشتنِ ORM که باید داخلِ بلاکِ
        # Playwright اجرا شود از طریقِ یک Threadِ واقعاً جداگانه اجرا
        # می‌شود — Djangoِ خودش برای هر Threadِ تازه یک Connectionِ تازه
        # باز می‌کند.
        #
        # یک Processِ Chromiumِ تازه به‌ازایِ هر Template (به‌جایِ یک
        # Browserِ مشترک) — احتیاطِ اضافیِ ساده در برابرِ هر کشِ سطحِ
        # Browser، مستقل از رفعِ باگِ اصلیِ بالا.
        with ThreadPoolExecutor(max_workers=1) as db_executor:
            for preset in templates:
                db_executor.submit(self._apply_and_publish_if_needed, store, preset).result()
                with sync_playwright() as p:
                    browser = p.chromium.launch(**launch_kwargs)
                    try:
                        self._process_one(store, preset, browser, base_url, public_host, options)
                    finally:
                        browser.close()

        self.stdout.write(self.style.SUCCESS(f"همه‌یِ {len(templates)} Ready Template پردازش شد."))

    # ------------------------------------------------------------------

    def _check_server_reachable(self, base_url: str) -> None:
        try:
            urllib.request.urlopen(base_url, timeout=5.0)
        except urllib.error.HTTPError:
            return  # هر پاسخِ HTTP (حتی ۴xx/۵xx) یعنی سرور واقعاً در حالِ اجراست.
        except (urllib.error.URLError, OSError) as exc:
            raise CommandError(
                f"سرورِ واقعی روی {base_url} در دسترس نیست — این دستور خودش سرور را بالا "
                "نمی‌آورد؛ یک ترمینالِ جدا با ``python manage.py runserver`` باز کنید."
            ) from exc

    def _resolve_public_host(self, store: Store) -> str:
        from django.conf import settings

        prefix = f"shop-{store.admin_subdomain}"
        return f"{prefix}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

    def _apply_and_publish_if_needed(self, store: Store, preset) -> None:
        """دقیقاً همان الگویِ rate-limit-آگاهِ ``seed_rastisi_fashion_demo.
        _seed_builder``: اگر Presetِ منتشرشده‌یِ فعلی از قبل همینِ preset
        است و Draftِ نیمه‌کاره‌ای باقی نمانده، هیچ Apply/Publishِ تازه‌ای
        صدا زده نمی‌شود."""
        layout = layout_service.get_or_create_layout(store)
        if layout.published_version_id and not layout.draft_version_id:
            current = layout.published_version.effective_appearance_config()
            if current.get("layout_preset_key") == preset.key:
                self.stdout.write(f"  [{preset.key}] از قبل منتشر شده — بدونِ Apply/Publishِ تازه.")
                return
        # Controlled preview setup: apply the Ready Template through the
        # lower-level ``apply_preset`` primitive on the active Draft (the
        # merchant-facing checkpoint wrapper is fail-closed for Ready Templates —
        # Architecture Convergence / Phase 1 single-authority rule).
        preview_draft = layout_service.get_or_create_draft(store)
        preset_service.apply_preset(preview_draft, preset)
        layout_service.publish(store)
        self.stdout.write(f"  [{preset.key}] Apply + Publish شد.")

    def _process_one(self, store, preset, browser, base_url, public_host, options) -> None:
        # هر Template یک Processِ Chromiumِ کاملاً تازه می‌گیرد (نگاه کنید
        # به توضیحِ بالا در ``handle``) — پس این‌جا دیگر نیازی به هدرهایِ
        # ضدِ‌کش نیست، اما برایِ ایمنیِ مضاعف نگه داشته می‌شوند.
        context = browser.new_context(
            viewport=CANONICAL_VIEWPORT,
            extra_http_headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        )
        page = context.new_page()
        page.goto(f"{base_url}/", wait_until="networkidle", timeout=20000)
        # اسکرین‌شاتِ ویوپورت (نه صفحه‌یِ کاملِ اسکرول‌شده) — طبقِ الزامِ
        # صریحِ کار: "Do not shrink an extremely long full-page screenshot
        # into unreadability."
        image_bytes = page.screenshot(type="jpeg", quality=90)
        context.close()

        # Part 2B follow-up (version-mismatch bug): the artifact's own
        # version identity is always the Ready Template's REAL registry
        # ``preset.version`` — never a separate, independently-tracked
        # screenshot-format constant. That older design let a Preset reach
        # registry version 2 while its committed preview stayed forever
        # named/labeled version 1, which is exactly the drift a merchant
        # audit correctly flagged as inconsistent.
        target_relpath = screenshot_relpath(preset.key, preset.version)
        target_path = APP_STATIC_DIR / target_relpath
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_as_webp(image_bytes, target_path)

        meta_path = APP_STATIC_DIR / meta_relpath(preset.key, preset.version)
        meta_path.write_text(json.dumps({
            "template_key": preset.key,
            "version": preset.version,
            "content_hash": preview_content_hash(preset),
            # Post-demo hardening pass (Issue 3) — the canonical staleness
            # identity ``resolve_real_screenshot`` actually validates against;
            # covers the Demo Store's real catalog/media/content too, not
            # just the Template registry (see that function's own docstring).
            "preview_input_fingerprint": preview_input_fingerprint(preset),
            "capture_source": "rasti-mode-demo",
            "viewport": CANONICAL_VIEWPORT,
        }, ensure_ascii=False, indent=2))
        self.stdout.write(f"  [{preset.key}] ذخیره شد: {target_relpath}")

        if options["full_qa"]:
            self._capture_qa_extra(preset, browser, base_url, options["qa_output_dir"])

    def _save_as_webp(self, image_bytes: bytes, target_path: Path) -> None:
        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image.save(target_path, format="WEBP", quality=88)

    def _capture_qa_extra(self, preset, browser, base_url, qa_output_dir: str) -> None:
        out_dir = Path(qa_output_dir) / preset.key
        out_dir.mkdir(parents=True, exist_ok=True)

        # HOME mobile
        no_cache = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        context = browser.new_context(viewport=QA_VIEWPORTS["home_mobile"], extra_http_headers=no_cache)
        page = context.new_page()
        page.goto(f"{base_url}/", wait_until="networkidle", timeout=20000)
        page.screenshot(path=str(out_dir / "home_mobile.jpg"), type="jpeg", quality=85)
        context.close()

        # LISTING desktop
        context = browser.new_context(viewport=QA_VIEWPORTS["listing_desktop"], extra_http_headers=no_cache)
        page = context.new_page()
        page.goto(f"{base_url}/products/", wait_until="networkidle", timeout=20000)
        page.screenshot(path=str(out_dir / "listing_desktop.jpg"), type="jpeg", quality=85)
        context.close()

        # PDP desktop — first product found on the listing page
        context = browser.new_context(viewport=QA_VIEWPORTS["pdp_desktop"], extra_http_headers=no_cache)
        page = context.new_page()
        page.goto(f"{base_url}/products/", wait_until="networkidle", timeout=20000)
        link = page.query_selector("a.pcard-hitarea")
        if link is not None:
            href = link.get_attribute("href")
            if href:
                page.goto(f"{base_url}{href}", wait_until="networkidle", timeout=20000)
        page.screenshot(path=str(out_dir / "pdp_desktop.jpg"), type="jpeg", quality=85)
        context.close()

        self.stdout.write(f"  [{preset.key}] عکس‌هایِ QAی اضافی در {out_dir}")
