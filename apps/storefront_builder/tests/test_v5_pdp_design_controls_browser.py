"""Real-browser proof of the PDP design controls (V5 بستهٔ ۱) — Chromium + Playwright, on the PUBLISHED storefront.

What the Django tests cannot prove is geometry: that a stored choice really moves things on a real page, that the defaults still look
like before, that the description modes keep their accessible behaviour (click, arrow keys, accordion at every width, no overlap in the
JS-enhanced vertical tabs) and that nothing ever scrolls horizontally at 1440 / 768 / 390.

Opt-in (needs a browser and a live server): ``SFB_BROWSER_TESTS=1 python manage.py test
apps.storefront_builder.tests.test_v5_pdp_design_controls_browser``. Chromium path: ``SFB_BROWSER_PATH``; screenshots:
``SFB_SCREENSHOT_DIR``. Runs only on an isolated test database."""

import os
import unittest
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.catalog.services.variant_engine_service import add_option_value, add_product_option, generate_variants
from apps.core.models import ShopSettings
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.qa import geometry_parity as gp
from apps.storefront_builder.services import layout_service, preset_service, r4_mutation_service
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
ADMIN_HOST = f"sfb-pdpc.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
PUBLIC_HOST = "sfb-pdpc-public.example.com"
BROWSER_CANDIDATES = (
    os.environ.get("SFB_BROWSER_PATH", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium",
)
RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
  return {x: r.x, y: r.y, w: r.width, h: r.height, r: r.right, b: r.bottom, visible: !!(e.offsetWidth || e.offsetHeight)}; }"""


def _browser_path():
    for path in BROWSER_CANDIDATES:
        if path and Path(path).exists():
            return path
    return None


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "127.0.0.1", "localhost", "testserver"])
class PdpDesignControlsBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pw = sync_playwright().start()
        launch = {"args": ["--no-sandbox", f"--host-resolver-rules=MAP {PUBLIC_HOST} 127.0.0.1, MAP {ADMIN_HOST} 127.0.0.1"],
                  "ignore_default_args": ["--hide-scrollbars"]}
        path = _browser_path()
        if path:
            launch["executable_path"] = path
        try:
            cls.browser = cls.pw.chromium.launch(**launch)
        except Exception as exc:  # pragma: no cover
            cls.pw.stop()
            super().tearDownClass()
            raise unittest.SkipTest(f"Chromium is not available: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.store = Store.objects.create(
            name="فروشگاه کنترل‌های محصول", slug="sfb-pdpc-store", status=Store.Status.ACTIVE,
            platform_code=generate_unique_platform_code(), admin_subdomain=ADMIN_HOST.split(".")[0],
        )
        ShopSettings.provision_for(self.store)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="pdpc-b-vendor")
        category = Category.objects.create(store=self.store, name="دسته", slug="pdpc-b-cat", is_active=True)
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای آزمایشی مرورگر", slug="pdpc-b-product", sku="PDPC-B-1",
            price=Decimal("250000"), discount_percent=10, stock=7, status=Product.Status.ACTIVE,
            description="<p>توضیحات کامل و واقعیِ کالای آزمایشی برای بررسیِ چیدمان.</p>",
        )
        self.user = get_user_model().objects.create_user(username="09125550888", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.draft = layout_service.get_or_create_draft(self.store, user=self.user)
        layout_service.get_or_create_layout(self.store)
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("stationery_spectrum"))
        layout_service.publish(self.store)
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.base = f"http://{PUBLIC_HOST}:{self.live_server_url.rsplit(':', 1)[1]}"

    # -------------------------------------------------------------------------------------------- helpers
    def _edit(self, section_key, patch):
        """Edit through the real R4 mutation, then publish — the Published storefront is what a customer sees."""
        draft = layout_service.get_or_create_draft(self.store, user=self.user)
        section = draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL).sections.get(section_key=section_key)
        r4_mutation_service.apply_mutation(
            store=self.store, actor=self.user, base_revision=draft.edit_revision,
            mutation={"type": "section.update_settings", "section_id": section.pk, "patch": patch},
        )
        layout_service.publish(self.store)

    def _variable_product(self):
        """A real multi-axis product: a colour axis (hex colours -> swatches by default) and a size axis, every variant purchasable."""
        vendor, category = self.product.vendor, self.product.category
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای متغیر مرورگر", slug="pdpc-b-variable", sku="PDPC-B-V",
            price=Decimal("300000"), stock=0, status=Product.Status.ACTIVE, product_type=Product.ProductType.VARIABLE,
        )
        colour = add_product_option(product, label="رنگ", values=["قرمز", "آبی", "سبز"])
        for value, hex_code in zip(colour.values.order_by("id"), ("#d00000", "#0050d0", "#10a040")):
            value.color_hex = hex_code
            value.save(update_fields=["color_hex"])
        add_product_option(product, label="سایز", values=["S", "M"])
        generate_variants(product)
        ProductVariant.objects.filter(product=product).update(stock=5)
        return product

    def _open(self, width, height=1000, product=None):
        context = self.browser.new_context(viewport={"width": width, "height": height}, locale="fa-IR")
        page = context.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.base + reverse("catalog:product-detail", args=[(product or self.product).slug]), wait_until="networkidle")
        gp.settle(page)
        return context, page

    def _shot(self, page, name):
        directory = os.environ.get("SFB_SCREENSHOT_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(directory) / f"{name}.png"), full_page=True)

    def _no_horizontal_overflow(self, page, label):
        self.assertEqual(page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, label)

    # ------------------------------------------------------------------------------------------- product_main
    def test_defaults_look_like_before_and_never_overflow(self):
        for width in (1440, 768, 390):
            context, page = self._open(width)
            try:
                self._no_horizontal_overflow(page, f"{width}px default")
                self.assertEqual(self.errors, [])
                gallery, info = page.evaluate(RECT, ".pdp .gallery"), page.evaluate(RECT, ".pdp .pinfo")
                if width == 1440:
                    self.assertGreater(gallery["x"], info["x"], "RTL default: the gallery is the first (right-hand) column")
                    main, thumbs = page.evaluate(RECT, ".gallery .main"), page.evaluate(RECT, ".gallery .thumbs")
                    self.assertGreaterEqual(thumbs["y"], main["b"] - 1, "default: thumbnails sit below the main image")
                else:
                    self.assertLess(gallery["b"], info["y"] + 2, "narrow: gallery above the buying panel")
                self._shot(page, f"pdp-default-{width}")
            finally:
                context.close()

    def test_controls_really_move_the_layout_on_desktop(self):
        self._edit("product_main", {
            "gallery_position": "end", "gallery_split": "gallery_wide", "thumbs_position": "side", "info_panel": "card",
            "qty_layout": "inline", "cta_width": "auto", "cta_size": "compact", "cta_shape": "pill", "price_layout": "plain",
        })
        context, page = self._open(1440)
        try:
            self._no_horizontal_overflow(page, "controls @1440")
            gallery, info = page.evaluate(RECT, ".pdp .gallery"), page.evaluate(RECT, ".pdp .pinfo")
            self.assertLess(gallery["x"], info["x"], "gallery moved to the end side")
            self.assertGreater(gallery["w"], info["w"], "gallery is the wider column")
            main, thumbs = page.evaluate(RECT, ".gallery .main"), page.evaluate(RECT, ".gallery .thumbs")
            self.assertLess(abs(thumbs["y"] - main["y"]), 4, "thumbnails beside the main image")
            qty, cta = page.evaluate(RECT, ".pdp-actions"), page.evaluate(RECT, ".pdp .qty")
            self.assertLess(abs(qty["y"] - cta["y"]), 30, "quantity and the add-to-cart button share one row")
            button = page.evaluate(RECT, ".pdp-actions .btn-primary")
            self.assertLess(button["w"], info["w"] * 0.8, "button hugs its text")
            self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.pdp .pinfo')).borderTopWidth"), "1px")
            self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.pdp-actions .btn-primary')).borderTopLeftRadius"), "999px")
            self._shot(page, "pdp-controls-1440")
        finally:
            context.close()

    def test_hidden_thumbnails_and_non_sticky_gallery(self):
        self._edit("product_main", {"thumbs_position": "hidden", "gallery_sticky": False, "show_mobile_sticky_bar": False})
        context, page = self._open(390)
        try:
            self.assertFalse(page.evaluate(RECT, ".gallery .thumbs")["visible"])
            self.assertEqual(page.locator(".pdp-satc").count(), 0)
            self._no_horizontal_overflow(page, "hidden thumbs @390")
        finally:
            context.close()
        context, page = self._open(1440)
        try:
            self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.pdp .gallery')).position"), "static")
        finally:
            context.close()

    def test_the_real_add_to_cart_form_still_works_with_the_quantity_control_hidden(self):
        self._edit("product_main", {"show_quantity": False, "qty_layout": "inline", "cta_width": "auto"})
        context, page = self._open(1440)
        try:
            self.assertFalse(page.evaluate(RECT, ".pdp .qty")["visible"])
            self.assertEqual(page.evaluate("() => document.querySelector('.pdp form [name=quantity]').value"), "1")
            self.assertEqual(page.locator(".pdp form").count(), 1)
            self.assertTrue(page.locator(".pdp-actions .btn-primary").is_enabled())
        finally:
            context.close()

    # ------------------------------------------------------------------------------------- product_description
    def test_tabs_click_and_keyboard_in_the_default_mode(self):
        context, page = self._open(1440)
        try:
            headers = page.locator(".pdp-acc-header")
            self.assertEqual(headers.count(), 3)
            self.assertEqual(headers.nth(0).get_attribute("aria-selected"), "true")
            headers.nth(0).focus()
            page.keyboard.press("ArrowRight")
            self.assertEqual(headers.nth(1).get_attribute("aria-selected"), "true")
            page.wait_for_selector("#pdp-panel-spec-%d" % self.product.pk, state="visible")      # Alpine flushes x-show asynchronously
            self.assertTrue(page.evaluate(RECT, "#pdp-panel-spec-%d" % self.product.pk)["visible"])
            self.assertFalse(page.evaluate(RECT, "#pdp-panel-desc-%d" % self.product.pk)["visible"])
            headers.nth(2).click()
            self.assertEqual(headers.nth(2).get_attribute("aria-selected"), "true")
            self._shot(page, "pdp-tabs-default-1440")
        finally:
            context.close()

    def test_vertical_accordion_and_stacked_modes_geometry(self):
        pk = self.product.pk
        self._edit("product_description", {"layout_mode": "tabs_vertical"})
        context, page = self._open(1440)
        try:
            first, panel = page.evaluate(RECT, ".pdp-acc-header"), page.evaluate(RECT, "#pdp-panel-desc-%d" % pk)
            self.assertLess(first["w"], 300, "vertical tabs: a narrow header column")
            self.assertTrue(first["r"] <= panel["x"] + 1 or panel["r"] <= first["x"] + 1, "header column and panel never overlap")
            second = page.evaluate(RECT, ".pdp-acc-header:nth-of-type(2)")
            self.assertLess(second["y"] - first["b"], 24, "the header column is one tight list, never spread over the tall panel's height")
            page.locator(".pdp-acc-header").nth(1).focus()
            page.keyboard.press("ArrowDown")
            self.assertEqual(page.locator(".pdp-acc-header").nth(2).get_attribute("aria-selected"), "true")
            self._shot(page, "pdp-tabs-vertical-1440")
        finally:
            context.close()
        context, page = self._open(390)
        try:
            header, container = page.evaluate(RECT, ".pdp-acc-header"), page.evaluate(RECT, ".pdp-tabs")
            self.assertGreaterEqual(header["w"], container["w"] * 0.95, "vertical tabs fall back to the full-width accordion on a phone")
            self._no_horizontal_overflow(page, "vertical @390")
        finally:
            context.close()

        self._edit("product_description", {"layout_mode": "accordion"})
        context, page = self._open(1440)
        try:
            headers = page.locator(".pdp-acc-header")
            widths = [page.evaluate(RECT, ".pdp-acc-header:nth-of-type(%d)" % 1)["w"]]
            container = page.evaluate(RECT, ".pdp-tabs")
            self.assertGreater(widths[0], container["w"] * 0.9, "accordion at desktop width: full-width headers")
            self.assertEqual(headers.count(), 3)
            self._shot(page, "pdp-accordion-1440")
        finally:
            context.close()

        self._edit("product_description", {"layout_mode": "stacked"})
        context, page = self._open(1440)
        try:
            self.assertEqual(page.locator(".pdp-sec-title").count(), 3)
            for key in ("desc", "spec", "review"):
                self.assertTrue(page.evaluate(RECT, f"#pdp-panel-{key}-{pk}")["visible"], key)
            self.assertEqual(page.locator("[role=tab]").count(), 0)
            self._no_horizontal_overflow(page, "stacked @1440")
            self._shot(page, "pdp-stacked-1440")
        finally:
            context.close()

    def test_hidden_and_reordered_sections_are_really_not_there(self):
        self._edit("product_description", {"sections": [
            {"key": "review", "label": "دیدگاه‌های خریداران", "visible": True},
            {"key": "desc", "visible": False},
        ]})
        context, page = self._open(1440)
        try:
            texts = page.locator(".pdp-acc-header").all_inner_texts()
            self.assertEqual([t.strip() for t in texts], ["دیدگاه‌های خریداران", "مشخصات فنی"])
            self.assertEqual(page.locator("#pdp-panel-desc-%d" % self.product.pk).count(), 0)
        finally:
            context.close()

    # ----------------------------------------------------------------------------- variants (the unified variantSelector)
    def test_variant_options_swatches_by_default_text_chips_on_request_and_selection_still_works(self):
        product = self._variable_product()
        context, page = self._open(1440, product=product)
        try:
            self.assertEqual(self.errors, [])
            self.assertEqual(page.locator(".opt-block .swatch").count(), 3, "default: the colour axis renders swatches")
            self.assertEqual(page.locator(".opt-block .size").count(), 2, "default: the size axis renders text chips")
            self._shot(page, "pdp-variants-default-1440")
        finally:
            context.close()
        self._edit("product_main", {"option_style": "chips", "option_shape": "pill", "price_position": "before_options", "qty_layout": "inline"})
        context, page = self._open(1440, product=product)
        try:
            self.assertEqual(self.errors, [])
            self.assertEqual(page.locator(".opt-block .swatch").count(), 0, "chips mode: colours become text chips")
            self.assertEqual(page.locator(".opt-block .size").count(), 5, "3 colours + 2 sizes as chips")
            self.assertEqual(page.evaluate("() => getComputedStyle(document.querySelector('.opt-block .size')).borderTopLeftRadius"), "999px")
            price, first_option = page.evaluate(RECT, ".pricebox"), page.evaluate(RECT, ".opt-block")
            self.assertLess(price["y"], first_option["y"], "price moved before the options")
            # the one real variantSelector still drives selection, price and the button
            page.locator(".opt-block").nth(0).locator(".size").nth(1).click()
            page.locator(".opt-block").nth(1).locator(".size").nth(0).click()
            page.wait_for_function("() => document.querySelectorAll('.opt-block .size.active').length === 2")
            self.assertTrue(page.locator(".pdp-actions .btn-primary").is_enabled())
            self.assertEqual(self.errors, [])
            self._shot(page, "pdp-variants-chips-1440")
        finally:
            context.close()
