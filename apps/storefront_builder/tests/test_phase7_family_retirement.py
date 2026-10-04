"""Phase 7 — Legacy Family Migration/Retirement: تست‌هایی که مستقیماً
ادعاهایِ خاصِ این فاز را اثبات می‌کنند (نه صفتِ عمومیِ Draft/Published/
tenant/CSRF/auth که قبلاً در مجموعه‌تست‌هایِ فازهایِ ۴/۵/۶ اثبات شده‌اند
و بدون تغییر باقی مانده‌اند — نگاه کنید به
docs/architecture/STOREFRONT_BUILDER_V2_PHASE_7_REPORT.md برایِ نگاشتِ
کاملِ هرکدام از ۳۲ الزامِ تستیِ این فاز به تستِ مسئول).

پوششِ این فایل:
- ۱، ۲: هیچ انتخاب‌گرِ Familyی در UI مرچنت نیست؛ Layout Preset نقطه‌ی
  شروعِ اصلی است.
- ۳، ۴، ۲۸: family_slug/preset_slugِ باقی‌مانده (حتی اگر مستقیماً در
  appearance_config ذخیره شده باشد — دور زدنِ validator، دقیقاً همان
  چیزی که یک دیتابیسِ توسعه‌ایِ قدیمی ممکن است داشته باشد) نمی‌تواند
  Rendererِ عمومی را عوض کند.
- ۵-۱۰: هر ۶ نوع صفحه فقط از مسیرِ Universal V2 رد می‌شوند.
- ۱۱، ۱۲: هدر/فوتر همیشه از پیکربندیِ سراسریِ Universal می‌آیند.
- ۲۹: هیچ importِ فعالی به family_registry/preset_registryِ حذف‌شده
  نیاز ندارد."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-p7-retire.rastisi.localhost"
PUBLIC_HOST = "sfb-p7-retire.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}", is_active=True)
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), stock=5, status=Product.Status.ACTIVE,
    )


class RegistryModulesAreGoneTests(TestCase):
    """۲۹ — هیچ importِ فعالی به ماژول‌هایِ حذف‌شده نیاز ندارد؛ خودِ
    ماژول‌ها هم دیگر اصلاً وجود ندارند (شواهدِ ایستا — دقیقاً همان کلاسِ
    مرزِ معماری که تستِ رفتاری نمی‌تواند اثبات کند)."""

    def test_family_registry_module_does_not_exist(self):
        with self.assertRaises(ModuleNotFoundError):
            import apps.storefront_builder.family_registry  # noqa: F401

    def test_legacy_preset_registry_module_does_not_exist(self):
        with self.assertRaises(ModuleNotFoundError):
            import apps.storefront_builder.preset_registry  # noqa: F401

    def test_bootstrap_service_has_no_family_functions(self):
        from apps.storefront_builder.services import bootstrap_service

        self.assertFalse(hasattr(bootstrap_service, "apply_family_default_sections"))
        self.assertFalse(hasattr(bootstrap_service, "build_family_default_sections"))

    def test_layout_preset_registry_and_preset_service_still_exist(self):
        """Phase 6 (سیستمِ جایگزین) باید دست‌نخورده باقی مانده باشد."""
        from apps.storefront_builder import layout_preset_registry
        from apps.storefront_builder.services import preset_service

        self.assertGreaterEqual(len(layout_preset_registry.LAYOUT_PRESET_REGISTRY), 3)
        self.assertTrue(hasattr(preset_service, "apply_preset"))


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class Phase7RetirementTestCase(TestCase):
    def setUp(self):
        # چندین متدِ این کلاس get_or_create_draft/publish را (که هرکدام
        # پشتِ Rate Limitِ واقعیِ Production‌اند، بر رویِ همان
        # storeِ مشترکِ akhlaghi) صدا می‌زنند — cache (بر خلافِ
        # تراکنشِ دیتابیس) بینِ متدهای تست rollback نمی‌شود، پس بدونِ
        # این پاک‌سازی شمارنده‌ها از تست‌های دیگرِ همین Suite (که همان
        # Storeِ مشترک را با هم به اشتراک می‌گذارند) تجمیع می‌شوند —
        # دقیقاً همان الگویِ تثبیت‌شده در سراسرِ این پوشه (مثلاً
        # test_layout_service.py، test_appearance.py).
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="p7_retire_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="p7_retire_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)
        self.product = _product(self.store, "p7-retire-product")


class NoMerchantFacingFamilySelectorTests(Phase7RetirementTestCase):
    """۱، ۲ — هیچ انتخاب‌گرِ Family در UI مرچنت نیست؛ Layout Preset حاضر است."""

    def test_appearance_panel_has_no_family_selector(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """توجه: کلمه‌ی «خانواده» عمداً اینجا چک نمی‌شود — یکی از ۱۰
        Templateِ قدیمیِ باقی‌مانده (``playful``) از همین کلمه به‌عنوانِ
        برچسبِ گروهِ عمومی («سبک خانواده‌محور») استفاده می‌کند، کاملاً
        بی‌ربط به سیستمِ بازنشسته‌شده‌ی Family/Renderer."""
        svc.get_or_create_draft(self.store)
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("family_slug", body)
        self.assertNotIn("confirm_family_switch", body)
        self.assertNotIn("preview-candidate-family", body)

    def test_appearance_panel_has_layout_preset_gallery(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        svc.get_or_create_draft(self.store)
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertContains(resp, "پیش‌تنظیمِ صفحه‌آرایی")

    def test_apply_preset_url_exists_apply_family_url_does_not(self):
        self.assertTrue(reverse("dashboard:storefront-builder-apply-preset"))
        with self.assertRaises(Exception):
            reverse("dashboard:storefront-builder-apply-family")


class StaleFamilyConfigCannotSwitchRendererTests(Phase7RetirementTestCase):
    """۳، ۴، ۲۸ — یک appearance_configِ باقی‌مانده از قبلِ این فاز (که هنوز
    مستقیماً در دیتابیس family_slug/preset_slug دارد — دور زدنِ validator،
    دقیقاً شبیه‌سازیِ یک ردیفِ واقعیِ قدیمی) هرگز نباید Rendererِ عمومی را
    عوض کند."""

    def setUp(self):
        super().setUp()
        draft = svc.get_or_create_draft(self.store)
        # عمداً مستقیم روی appearance_config دستکاری می‌شود (نه از طریقِ
        # validate_appearance_config) تا حالتِ یک ردیفِ واقعاً قدیمی که
        # هرگز از این فاز عبور نکرده شبیه‌سازی شود.
        draft.appearance_config = {
            **draft.effective_appearance_config(),
            "family_slug": "modern_fashion", "preset_slug": "modern_fashion_default",
        }
        draft.save(update_fields=["appearance_config"])
        svc.publish(self.store)

    def test_home_renders_without_any_family_markup(self):
        resp = self.public_client.get(reverse("catalog:home"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("data-sfb-family=", body)
        self.assertNotIn("css/families/", body)

    def test_product_detail_renders_without_family_markup(self):
        resp = self.public_client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("data-sfb-family=", resp.content.decode())

    def test_listing_renders_without_family_markup(self):
        resp = self.public_client.get(reverse("catalog:product-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("data-sfb-family=", resp.content.decode())

    def test_cart_renders_without_family_markup(self):
        resp = self.public_client.get(reverse("cart:detail"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("data-sfb-family=", resp.content.decode())

    def test_stale_family_config_does_not_block_preset_application(self):
        """اعمالِ یک Layout Preset باید حتی با وجودِ کلیدهایِ باقی‌مانده‌ی
        family_slug/preset_slug در appearance_configِ فعلی، بدونِ خطا کار
        کند — کلیدهایِ ناشناخته صرفاً هنگامِ اعتبارسنجیِ بعدی بی‌صدا حذف
        می‌شوند."""
        from apps.storefront_builder import layout_preset_registry as lpr
        from apps.storefront_builder.services import preset_service

        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("clean_minimal")
        preset_service.apply_preset(draft, preset)  # نباید خطا بدهد
        draft.refresh_from_db()
        self.assertEqual(draft.appearance_config.get("layout_preset_key"), "clean_minimal")
        self.assertNotIn("family_slug", draft.appearance_config)
        self.assertNotIn("preset_slug", draft.appearance_config)


class AllSixPageTypesUseUniversalPathTests(Phase7RetirementTestCase):
    """۵-۱۲ — هر ۶ نوعِ صفحه فقط از مسیرِ Universal V2 رد می‌شوند؛ هدر/فوتر
    همیشه از پیکربندیِ سراسری می‌آیند (نه یک partial خاصِ Family)."""

    def setUp(self):
        super().setUp()
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_all_public_routes_render_200_with_universal_header_footer(self):
        routes = [
            reverse("catalog:home"),
            reverse("catalog:product-detail", args=[self.product.slug]),
            reverse("catalog:product-list"),
            reverse("catalog:collection-index"),
            reverse("cart:detail"),
        ]
        for url in routes:
            resp = self.public_client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            body = resp.content.decode()
            # هدر/فوتریِ Universal همیشه این نشانه‌های ساختاریِ مشترک را دارد
            self.assertIn('class="header', body, url)
            self.assertIn('class="footer', body, url)
            self.assertNotIn("data-sfb-family=", body, url)

    def test_search_uses_same_universal_listing_renderer(self):
        resp = self.public_client.get(reverse("catalog:product-list"), {"q": "کالای"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("data-sfb-family=", resp.content.decode())
