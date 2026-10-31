"""تست‌های چک‌لیست راه‌اندازی فروشگاه — apps.dashboard.services.checklist_service."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Attribute,
    Brand,
    Category,
    IndustryTemplate,
    Product,
    ProductImage,
    ProductVariant,
    StoreIndustryInstallation,
    Vendor,
)
from apps.core.models import ShopSettings
from apps.dashboard.services.checklist_service import build_industry_summary, build_setup_checklist
from apps.orders.models import PaymentGatewayConfig, ShippingMethod, TaxClass, TaxRate
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class BuildSetupChecklistTests(TestCase):
    """هر مرحله باید مستقیماً از داده‌ی واقعی تشخیص داده شود، نه یک پرچمِ ذخیره‌شده."""

    def setUp(self):
        self.store = Store.objects.create(name="New Shop", slug="new-shop", status=Store.Status.ACTIVE)
        self.request = RequestFactory().get("/")

    def test_brand_new_store_has_nothing_complete(self):
        result = build_setup_checklist(self.store, self.request)
        self.assertEqual(result["completed_count"], 0)
        self.assertEqual(result["total_count"], 21)      # + «دیده‌شدن در گوگل و بینگ» (growth)
        self.assertEqual(result["percent"], 0)
        self.assertFalse(result["all_complete"])

    def test_step_order_matches_catalog_dependency_chain(self):
        """اولین کالا هرگز نباید پیش از پیش‌نیازهایش (گروه/دسته/برند/ویژگی) ظاهر شود؛
        زنجیره‌ی اصلیِ ۱۲مرحله‌ای دقیقاً طبقِ ترتیبِ الزامیِ درخواست است."""
        result = build_setup_checklist(self.store, self.request)
        keys = [step["key"] for step in result["steps"]]
        expected_prefix = [
            "industry", "industry_template", "product_groups", "product_categories",
            "brands", "attributes", "first_product", "product_images", "variants",
            "inventory", "shipping", "publish",
        ]
        self.assertEqual(keys[: len(expected_prefix)], expected_prefix)

    def test_first_steps_are_unlocked_but_later_chain_steps_are_locked(self):
        """قفل صرفاً بصری است — همه‌ی مراحل همیشه قابل‌کلیک‌اند، اما مراحلِ
        بعدیِ زنجیره‌ی کاتالوگ تا تکمیل‌نشدنِ پیش‌نیازها «قفل» نشان داده می‌شوند."""
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertTrue(steps_by_key["industry"]["is_unlocked"])
        self.assertFalse(steps_by_key["product_groups"]["is_unlocked"])
        self.assertFalse(steps_by_key["publish"]["is_unlocked"])
        # مراحلِ تکمیلیِ خارج از زنجیره همیشه باز هستند، حتی وقتی زنجیره ناتمام است.
        self.assertTrue(steps_by_key["store_info"]["is_unlocked"])

    def test_chain_step_unlocks_once_its_prerequisites_are_done(self):
        template = IndustryTemplate.objects.create(
            slug="chain-unlock", name="زنجیره", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        Category.objects.create(store=self.store, name="گروه", slug="chk-unlock-group")
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertTrue(steps_by_key["product_groups"]["is_complete"])
        self.assertTrue(steps_by_key["product_categories"]["is_unlocked"])

    def test_locked_steps_explain_why_via_locked_reason(self):
        """کاربر باید همیشه بداند «چرا» یک مرحله قفل است، نه فقط اینکه قفل است."""
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertEqual(steps_by_key["industry"]["locked_reason"], "")
        self.assertIn("انتخاب صنف", steps_by_key["product_groups"]["locked_reason"])
        self.assertIn("انتخاب صنف", steps_by_key["publish"]["locked_reason"])

    def test_locked_reason_points_to_the_nearest_unfinished_prerequisite(self):
        """دلیلِ قفل باید نزدیک‌ترین مرحله‌ی ناتمام را نام ببرد، نه همیشه اولین مرحله‌ی زنجیره را."""
        template = IndustryTemplate.objects.create(
            slug="locked-reason", name="زنجیره۲", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        Category.objects.create(store=self.store, name="گروه", slug="chk-reason-group")
        result = build_setup_checklist(self.store, self.request)
        steps_by_key = {s["key"]: s for s in result["steps"]}
        self.assertIn("ایجاد دسته‌بندی‌ها", steps_by_key["brands"]["locked_reason"])

    def test_exactly_one_unlocked_incomplete_step_is_marked_next(self):
        """کاربر باید همیشه بداند «قدمِ بعدی» دقیقاً کدام است."""
        result = build_setup_checklist(self.store, self.request)
        next_steps = [s["key"] for s in result["steps"] if s["is_next"]]
        self.assertEqual(next_steps, ["industry"])

    def test_next_step_advances_once_current_step_completes(self):
        template = IndustryTemplate.objects.create(
            slug="next-step", name="زنجیره۳", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        next_steps = [s["key"] for s in result["steps"] if s["is_next"]]
        self.assertEqual(next_steps, ["product_groups"])

    def test_store_information_step_detects_description(self):
        shop = ShopSettings.objects.create(store=self.store, description="فروشگاهِ لباسِ آنلاین")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "store_info")
        self.assertTrue(step["is_complete"])

    def test_industry_step_detects_installation(self):
        template = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "industry")
        self.assertTrue(step["is_complete"])

    def test_contact_step_detects_phone_or_email(self):
        ShopSettings.objects.create(store=self.store, contact_phone="09121234567")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "contact")
        self.assertTrue(step["is_complete"])

    def test_theme_step_false_when_colors_are_default(self):
        ShopSettings.objects.create(store=self.store)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "theme")
        self.assertFalse(step["is_complete"])

    def test_theme_step_true_once_a_color_changed(self):
        ShopSettings.objects.create(store=self.store, primary_color="#111111")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "theme")
        self.assertTrue(step["is_complete"])

    def test_product_groups_step_detects_top_level_category(self):
        Category.objects.create(store=self.store, name="پوشاک", slug="clothing-group")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_groups")
        self.assertTrue(step["is_complete"])

    def test_product_categories_step_requires_subcategory_not_just_a_group(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-main")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_categories")
        self.assertFalse(step["is_complete"])

        Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub", parent=main)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "product_categories")
        self.assertTrue(step["is_complete"])

    def test_first_category_and_product_steps(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub2", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-checklist")
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt",
            sku="SKU-CHK1", price=Decimal("100000"),
        )
        result = build_setup_checklist(self.store, self.request)
        prod_step = next(s for s in result["steps"] if s["key"] == "first_product")
        self.assertTrue(prod_step["is_complete"])

    def test_industry_steps_stay_incomplete_when_only_onboarding_stage_advances(self):
        """قبلاً صرفِ عبورِ ``onboarding_stage`` از INDUSTRY (رد کردنِ مرحله در
        ویزارد، بدونِ نصبِ واقعی) هر دو مرحله را ✅ نشان می‌داد — دقیقاً همان
        باگِ گزارش‌شده: ``IndustryTemplate.objects.count() == 0`` و
        ``StoreIndustryInstallation.objects.count() == 0`` ولی چک‌لیست
        تکمیل‌شده نشان می‌داد. اکنون بدونِ یک نصبِ واقعی، این دو مرحله هرگز
        تکمیل نمی‌شوند، صرف‌نظر از ``onboarding_stage``."""
        self.store.onboarding_stage = Store.OnboardingStage.BRANDING
        self.store.save(update_fields=["onboarding_stage"])
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertFalse(industry_step["is_complete"])
        self.assertFalse(template_step["is_complete"])
        self.assertNotEqual(industry_step["url"], "")

    def test_industry_steps_incomplete_with_zero_templates_and_zero_installations(self):
        """سناریوی دقیقِ گزارشِ باگ: هیچ ``IndustryTemplate``ای در سامانه
        نیست و هیچ نصبی برایِ این Store وجود ندارد — هر دو مرحله باید
        ناتمام و قابل‌اقدام (دارای url) بمانند."""
        self.assertEqual(IndustryTemplate.objects.count(), 0)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 0)
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertFalse(industry_step["is_complete"])
        self.assertFalse(template_step["is_complete"])
        self.assertTrue(industry_step["url"])
        self.assertTrue(template_step["url"])

    def test_industry_template_step_completes_when_actually_installed(self):
        template = IndustryTemplate.objects.create(
            slug="home", name="خانه و آشپزخانه", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertTrue(industry_step["is_complete"])
        self.assertTrue(template_step["is_complete"])

    def test_industry_steps_incomplete_when_installation_failed(self):
        """نصبی که وضعیتش ``FAILED`` است، هرگز مرحله‌ی «نصب قالب صنف» را
        تکمیل‌شده نشان نمی‌دهد — حتی اگر یک رکوردِ نصب وجود داشته باشد."""
        template = IndustryTemplate.objects.create(
            slug="failed-install", name="صنعتِ ناموفق", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.FAILED,
        )
        result = build_setup_checklist(self.store, self.request)
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertFalse(template_step["is_complete"])

    def test_industry_steps_incomplete_when_template_is_inactive(self):
        """نصبی که به یک قالبِ غیرفعال وصل است، معتبر حساب نمی‌شود —
        الزام: «فقط وقتی به یک IndustryTemplate فعال وصل باشد»."""
        template = IndustryTemplate.objects.create(
            slug="deactivated", name="صنعتِ غیرفعال", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY, is_active=False,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertFalse(industry_step["is_complete"])
        self.assertFalse(template_step["is_complete"])

    def test_industry_installation_does_not_leak_across_stores(self):
        """نصبِ صنفِ یک فروشگاهِ دیگر هرگز نباید چک‌لیستِ این Store را تکمیل‌شده نشان دهد."""
        other_store = Store.objects.create(
            name="Other Shop", slug="other-shop-industry-isolation", status=Store.Status.ACTIVE,
        )
        template = IndustryTemplate.objects.create(
            slug="tenant-isolation", name="ایزوله", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=other_store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        industry_step = next(s for s in result["steps"] if s["key"] == "industry")
        template_step = next(s for s in result["steps"] if s["key"] == "industry_template")
        self.assertFalse(industry_step["is_complete"])
        self.assertFalse(template_step["is_complete"])

    def test_attributes_and_brands_steps(self):
        result = build_setup_checklist(self.store, self.request)
        attr_step = next(s for s in result["steps"] if s["key"] == "attributes")
        brand_step = next(s for s in result["steps"] if s["key"] == "brands")
        self.assertFalse(attr_step["is_complete"])
        self.assertFalse(brand_step["is_complete"])

        Attribute.objects.create(store=self.store, label="جنس", code="material-chk")
        Brand.objects.create(store=self.store, name="برند تست", slug="brand-chk")
        result = build_setup_checklist(self.store, self.request)
        attr_step = next(s for s in result["steps"] if s["key"] == "attributes")
        brand_step = next(s for s in result["steps"] if s["key"] == "brands")
        self.assertTrue(attr_step["is_complete"])
        self.assertTrue(brand_step["is_complete"])

    def test_images_variants_inventory_and_publish_steps(self):
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-piv")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub-piv", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-piv")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt-piv",
            sku="SKU-PIV1", price=Decimal("100000"), stock=0, status=Product.Status.DRAFT,
        )
        result = build_setup_checklist(self.store, self.request)
        for key in ("product_images", "variants", "inventory", "product_publish"):
            step = next(s for s in result["steps"] if s["key"] == key)
            self.assertFalse(step["is_complete"], msg=key)

        ProductImage.objects.create(product=product, image="products/tshirt-piv.jpg")
        ProductVariant.objects.create(
            store=self.store, product=product, attribute="رنگ", value="قرمز", sku="SKU-PIV1-RED",
        )
        product.stock = 5
        product.status = Product.Status.ACTIVE
        product.save(update_fields=["stock", "status"])

        result = build_setup_checklist(self.store, self.request)
        for key in ("product_images", "variants", "inventory", "product_publish"):
            step = next(s for s in result["steps"] if s["key"] == key)
            self.assertTrue(step["is_complete"], msg=key)

    def test_shipping_step(self):
        ShippingMethod.objects.create(store=self.store, name="پست پیشتاز", slug="post", cost=Decimal("50000"))
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "shipping")
        self.assertTrue(step["is_complete"])

    def test_shipping_step_label_and_description_and_url(self):
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "shipping")
        self.assertEqual(step["label"], "پیکربندی ارسال")
        self.assertIn("روش ارسال", step["description"])
        self.assertIn("دریافت حضوری", step["description"])
        self.assertEqual(step["url"], reverse("dashboard:shipping-setup"))

    def test_payment_gateway_step_requires_active_config(self):
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code=PaymentGatewayConfig.GatewayCode.COD, is_active=False,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "payment_gateway")
        self.assertFalse(step["is_complete"])

        PaymentGatewayConfig.objects.filter(store=self.store).update(is_active=True)
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "payment_gateway")
        self.assertTrue(step["is_complete"])

    def test_tax_step_incomplete_until_explicit_choice(self):
        """صرفِ وجودِ ``ShopSettings`` (که ``tax_enabled``اش پیش‌فرض True
        است) کافی نیست — مدیر باید صریحاً صفحه‌ی مالیات را ذخیره کند."""
        ShopSettings.objects.create(store=self.store, description="فروشگاه")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "tax")
        self.assertFalse(step["is_complete"])

    def test_tax_step_completes_when_merchant_explicitly_chooses_no_tax(self):
        shop = ShopSettings.objects.create(store=self.store, tax_enabled=False)
        shop.tax_setup_confirmed_at = timezone.now()
        shop.save(update_fields=["tax_setup_confirmed_at"])
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "tax")
        self.assertTrue(step["is_complete"])

    def test_tax_step_completes_when_merchant_explicitly_chooses_has_tax(self):
        tax_class = TaxClass.objects.create(store=self.store, name="عمومی")
        TaxRate.objects.create(store=self.store, tax_class=tax_class, rate_percent=9)
        shop = ShopSettings.objects.create(store=self.store, tax_enabled=True)
        shop.tax_setup_confirmed_at = timezone.now()
        shop.save(update_fields=["tax_setup_confirmed_at"])
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "tax")
        self.assertTrue(step["is_complete"])

    def test_tax_step_label_and_description(self):
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "tax")
        self.assertEqual(step["label"], "اطلاعات مالیاتی (اختیاری)")
        self.assertIn("مالیات ندارم", step["description"])

    def test_custom_domain_step_needs_an_ACTIVE_domain_not_just_a_verified_one(self):
        """«تکمیل‌شده» یعنی دامنه واقعاً فعال است (مالکیت + DNS + HTTPS + فعال‌سازی)؛ تأییدِ مالکیت تنها پیشرفت است، نه موفقیت."""
        StoreDomain.objects.create(
            store=self.store, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.PENDING, verification_requested_at=timezone.now(), verification_token="test-token-123",
        )
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertFalse(step["is_complete"])
        self.assertEqual(step["state"], "needs_action")            # the seller has to add the TXT record

        StoreDomain.objects.filter(store=self.store).update(
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertFalse(step["is_complete"], "verified ownership alone is NOT a connected domain")
        self.assertEqual(step["state"], "needs_action")            # DNS A/CNAME still missing

        StoreDomain.objects.filter(store=self.store).update(routing_status=StoreDomain.RoutingStatus.CONNECTED)
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertEqual(step["state"], "processing")                # DNS reaches RastiSi, HTTPS is being issued automatically

        StoreDomain.objects.filter(store=self.store).update(tls_status=StoreDomain.TlsStatus.READY)
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertFalse(step["is_complete"], "ready but not activated as the shop's address")
        self.assertEqual(step["state"], "needs_action")

        StoreDomain.objects.filter(store=self.store).update(is_primary=True)
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertTrue(step["is_complete"])
        self.assertEqual(step["state"], "done")

    def test_an_optional_step_is_never_labelled_done_unless_it_really_is(self):
        result = build_setup_checklist(self.store, self.request)
        for key in ("custom_domain", "tax", "brands", "attributes", "logo", "theme", "search_visibility"):
            step = next(s for s in result["steps"] if s["key"] == key)
            self.assertFalse(step["required"], key)
            self.assertNotEqual(step["state"], "done", key)
            self.assertEqual(step["state"], "optional", key)

    def test_custom_domain_step_is_marked_optional_and_never_locked(self):
        """دامنه‌ی اختصاصی هرگز نباید انتشار یا ورود به پنل را مسدود کند — طبقِ
        الزام؛ برچسب هم صراحتاً «اختیاری» بودنش را می‌گوید."""
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertIn("اختیاری", step["label"])
        self.assertTrue(step["is_unlocked"])

    def test_custom_domain_step_label_and_description_match_spec(self):
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertEqual(step["label"], "دامنه اختصاصی (اختیاری)")
        self.assertEqual(step["description"], "فروشگاه بدون دامنه اختصاصی نیز روی زیردامنه راستیسی قابل استفاده است.")

    def test_custom_domain_step_opens_the_domain_page_inside_the_seller_panel(self):
        """فروشنده برای شروعِ اتصالِ دامنه از پنلِ خودش خارج نمی‌شود."""
        step = next(s for s in build_setup_checklist(self.store, self.request)["steps"] if s["key"] == "custom_domain")
        self.assertEqual(step["url"], reverse("dashboard:settings") + "?section=domain")
        self.assertNotIn("/app/stores/", step["url"])

    def test_checklist_service_never_hardcodes_rastisi_ir(self):
        """الزام: «هرگز rastisi.ir در تمپلیت/کد هاردکد نشود» — میزبان همیشه
        باید از ``settings.RASTISI_PLATFORM_PRIMARY_HOST`` خوانده شود."""
        import inspect

        import apps.dashboard.services.checklist_service as checklist_service_module

        source = inspect.getsource(checklist_service_module)
        self.assertNotIn("rastisi.ir", source)

    def test_publish_step_requires_store_info_industry_product_and_shipping(self):
        """رفعِ تناقض: «فروشگاه منتشر شد» هرگز نباید هم‌زمان با ناتمام‌بودنِ
        صنف، ارسال، کالای فعال یا اطلاعاتِ پایه‌ی فروشگاه تکمیل‌شده نشان داده
        شود — حتی اگر ویزاردِ آنبوردینگ (onboarding_completed_at) از قبل طی
        شده باشد."""
        self.store.onboarding_completed_at = timezone.now()
        self.store.save(update_fields=["onboarding_completed_at"])
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"])

        ShopSettings.objects.create(store=self.store, description="فروشگاهِ لباسِ آنلاین")
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"], "still missing industry, an active product and a shipping method")

        template = IndustryTemplate.objects.create(
            slug="pub-industry", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"], "still missing an active product and a shipping method")

        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-pub")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub-pub", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-pub")
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt-pub",
            sku="SKU-PUB1", price=Decimal("100000"), stock=5, status=Product.Status.ACTIVE,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"], "still missing an active shipping method")

        ShippingMethod.objects.create(
            store=self.store, name="پست پیشتاز", slug="post-pub", cost=Decimal("50000"), is_active=True,
        )
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        # payment is NOT a publish prerequisite (the platform's own publish authority only needs a template); it gates READY TO SELL
        self.assertTrue(step["is_complete"], "a shop with no way to pay yet may still be published")
        self.assertTrue(result["ready_to_publish"])
        self.assertFalse(result["ready_to_sell"])
        self.assertIn("درگاه پرداخت", result["sell_blockers"])

    def test_publish_step_not_blocked_by_optional_tax_or_domain(self):
        """مالیات و دامنه‌ی اختصاصی هرگز نباید در چکِ انتشار باشند — حتی
        بدونِ هیچ‌کدام، فروشگاهی که بقیه‌ی پیش‌نیازها را دارد باید بتواند
        منتشر شود."""
        ShopSettings.objects.create(store=self.store, description="فروشگاهِ لباسِ آنلاین")
        template = IndustryTemplate.objects.create(
            slug="pub-optional", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        main = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-pub-opt")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="clothing-sub-pub-opt", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="vendor-pub-opt")
        Product.objects.create(
            store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="tshirt-pub-opt",
            sku="SKU-PUB-OPT1", price=Decimal("100000"), stock=5, status=Product.Status.ACTIVE,
        )
        ShippingMethod.objects.create(
            store=self.store, name="پست پیشتاز", slug="post-pub-opt", cost=Decimal("50000"), is_active=True,
        )
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code=PaymentGatewayConfig.GatewayCode.COD, is_active=True)
        result = build_setup_checklist(self.store, self.request)
        publish_step = next(s for s in result["steps"] if s["key"] == "publish")
        tax_step = next(s for s in result["steps"] if s["key"] == "tax")
        domain_step = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertTrue(publish_step["is_complete"])
        self.assertFalse(tax_step["is_complete"])
        self.assertFalse(domain_step["is_complete"])

    def test_publish_step_never_complete_without_onboarding_completed_at_either(self):
        """معکوسِ همان تناقض: onboarding_completed_at به‌تنهایی هم دیگر کافی
        نیست — اما این تست فقط اطمینان می‌دهد که بدونِ داده‌ی واقعی، هرگز ✅
        نشان داده نمی‌شود، حتی اگر ویزارد طی نشده باشد."""
        result = build_setup_checklist(self.store, self.request)
        step = next(s for s in result["steps"] if s["key"] == "publish")
        self.assertFalse(step["is_complete"])

    def test_step_urls_never_use_admin_subdomain_host(self):
        result = build_setup_checklist(self.store, self.request)
        for step in result["steps"]:
            self.assertNotIn(self.store.admin_subdomain + ".", step["url"])

    def test_all_complete_flag_true_only_when_every_step_done(self):
        result = build_setup_checklist(self.store, self.request)
        self.assertFalse(result["all_complete"])


class DashboardChecklistWidgetTests(TestCase):
    """چک‌لیست باید در صفحه‌ی داشبورد نمایش داده شود و با پیشرفتِ واقعی به‌روز شود."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.staff = User.objects.create_user(username="09121121099", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121099", password="pass12345")

    def test_dashboard_shows_checklist_widget(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "چک‌لیست راه‌اندازی فروشگاه")

    def test_dashboard_groups_steps_by_goal_with_one_primary_action_and_no_fake_success(self):
        html = self.client.get(reverse("dashboard:dashboard")).content.decode()
        self.assertIn('data-testid="setup-checklist"', html)
        self.assertEqual(html.count('class="setup-group"'), 5)
        self.assertEqual(html.count('data-testid="setup-primary"'), 1)
        self.assertIn("ادامه‌ی راه‌اندازی", html)
        for key in ("custom_domain", "tax", "brands"):
            self.assertRegex(html, rf'data-step="{key}" data-state="(optional|needs_action|processing)"')
        self.assertNotIn("فروشگاه شما آماده است!", html)

    def test_dashboard_success_state_when_all_complete_uses_the_new_wording(self):
        from unittest import mock

        with mock.patch("apps.dashboard.services.checklist_service.build_setup_checklist",
                        return_value={"steps": [], "completed_count": 1, "total_count": 1, "percent": 100, "all_complete": True}):
            response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "کارهای ضروری انجام شده")

    def test_dashboard_shows_success_state_when_all_complete(self):
        from unittest import mock

        with mock.patch(
            "apps.dashboard.services.checklist_service.build_setup_checklist",
            return_value={
                "steps": [], "completed_count": 12, "total_count": 12, "percent": 100, "all_complete": True,
            },
        ):
            response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "فروشگاه شما آماده است")
        self.assertNotContains(response, "چک‌لیست راه‌اندازی فروشگاه")


class BuildIndustrySummaryTests(TestCase):
    """صنفِ فروشگاه و قالبِ نصب‌شده باید مستقیماً از StoreIndustryInstallation
    خوانده شوند — هیچ متنی هاردکد نمی‌شود."""

    def setUp(self):
        self.store = Store.objects.create(name="New Shop", slug="industry-summary-shop", status=Store.Status.ACTIVE)

    def test_no_installation_returns_has_installation_false(self):
        summary = build_industry_summary(self.store)
        self.assertEqual(summary, {"has_installation": False})

    def test_installation_returns_real_industry_and_template_data(self):
        template = IndustryTemplate.objects.create(
            slug="clothing", name="پوشاک و مد", version=2, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        installation = StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=2,
            status=StoreIndustryInstallation.Status.COMPLETED, categories_created=5, attributes_created=3,
        )
        summary = build_industry_summary(self.store)
        self.assertTrue(summary["has_installation"])
        self.assertEqual(summary["industry_name"], "پوشاک و مد")
        self.assertEqual(summary["template_version"], 2)
        self.assertEqual(summary["status"], StoreIndustryInstallation.Status.COMPLETED)
        self.assertEqual(summary["installed_at"], installation.created_at)

    def test_failed_installation_status_surfaced(self):
        template = IndustryTemplate.objects.create(
            slug="test-shoes-summary", name="کفش", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.FAILED,
        )
        summary = build_industry_summary(self.store)
        self.assertEqual(summary["status"], StoreIndustryInstallation.Status.FAILED)


class DashboardIndustryCardTests(TestCase):
    """کارتِ صنفِ فروشگاه باید در صفحه‌ی داشبورد نمایش داده شود."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.staff = User.objects.create_user(username="09121121088", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121088", password="pass12345")

    def test_no_installation_shows_not_installed_message(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "هنوز قالب صنفی نصب نشده است")

    def test_installation_shows_industry_name_and_status(self):
        template = IndustryTemplate.objects.create(
            slug="mobile-dc", name="موبایل و تبلت", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
            status=StoreIndustryInstallation.Status.COMPLETED,
        )
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "موبایل و تبلت")
        self.assertContains(response, "نصب موفق")


class HonestChecklistAggregatesTests(TestCase):
    """Required vs optional, the honest progress, the ONE primary action, and «live» = really public."""

    def setUp(self):
        self.store = Store.objects.create(name="Honest Shop", slug="honest-checklist", status=Store.Status.ACTIVE)
        self.request = RequestFactory().get("/admin-portal/")

    def _result(self):
        return build_setup_checklist(self.store, self.request)

    def test_progress_counts_only_required_steps(self):
        result = self._result()
        required = [s for s in result["steps"] if s["required"]]
        self.assertEqual(result["required_total"], len(required))
        self.assertEqual(result["required_done"], 0)
        self.assertEqual(result["required_percent"], 0)
        ShopSettings.objects.create(store=self.store, description="x", logo="logo.png", contact_phone="021")     # optional + required info
        result = self._result()
        self.assertEqual(result["required_done"], 1)             # only «store_info» is required; logo / contact are optional
        self.assertEqual(result["steps"][[s["key"] for s in result["steps"]].index("logo")]["state"], "done")

    def test_there_is_exactly_one_primary_action_and_it_is_the_first_open_required_step(self):
        result = self._result()
        self.assertEqual([s["key"] for s in result["steps"] if s["is_next"]], [result["primary_action"]["key"]])
        self.assertTrue(result["primary_action"]["required"])
        self.assertEqual(result["primary_action"]["key"], "industry")

    def test_groups_follow_the_five_stage_structure(self):
        result = self._result()
        self.assertEqual([g["key"] for g in result["groups"]], ["business", "appearance", "sales", "launch", "growth"])
        self.assertEqual(sum(len(g["steps"]) for g in result["groups"]), len(result["steps"]))

    def test_a_started_domain_becomes_the_primary_action_once_required_work_is_done(self):
        StoreDomain.objects.create(
            store=self.store, hostname="mine.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.PENDING, verification_token="tok",
            verification_requested_at=timezone.now(),
        )
        result = self._result()
        domain = next(s for s in result["steps"] if s["key"] == "custom_domain")
        self.assertEqual(domain["state"], "needs_action")
        self.assertFalse(domain["required"])                      # …and it never blocks selling
        self.assertNotIn(domain["label"], result["sell_blockers"])

    def test_a_failed_template_install_asks_for_a_fix_not_a_silent_wait(self):
        template = IndustryTemplate.objects.create(slug="fail-ind", name="x", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY)
        StoreIndustryInstallation.objects.create(store=self.store, industry_template=template, installed_version=1,
                                                 status=StoreIndustryInstallation.Status.FAILED)
        step = next(s for s in self._result()["steps"] if s["key"] == "industry_template")
        self.assertEqual(step["state"], "needs_fix")

    def test_what_rastisi_did_for_the_seller_is_reported(self):
        template = IndustryTemplate.objects.create(slug="auto-ind", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY)
        StoreIndustryInstallation.objects.create(store=self.store, industry_template=template, installed_version=1,
                                                 status=StoreIndustryInstallation.Status.COMPLETED, categories_created=4, attributes_created=2)
        Category.objects.create(store=self.store, name="پوشاک", slug="auto-g")
        result = self._result()
        self.assertIn("نصب قالب صنف", result["auto_done_labels"])
        self.assertIn("ایجاد گروه‌های دسته‌بندی", result["auto_done_labels"])

    def test_ready_to_publish_and_live_are_different_things(self):
        result = self._result()
        self.assertFalse(result["ready_to_publish"])
        self.assertFalse(result["is_live"])
        self.assertIn("انتخاب صنف", result["sell_blockers"])
        self.assertFalse(result["all_complete"])

    def _publishable_store(self):
        """Everything except a payment method."""
        ShopSettings.objects.create(store=self.store, description="فروشگاه")
        template = IndustryTemplate.objects.create(slug="rs-ind", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY)
        StoreIndustryInstallation.objects.create(store=self.store, industry_template=template, installed_version=1,
                                                 status=StoreIndustryInstallation.Status.COMPLETED)
        main = Category.objects.create(store=self.store, name="پوشاک", slug="rs-main")
        sub = Category.objects.create(store=self.store, name="تیشرت", slug="rs-sub", parent=main)
        vendor = Vendor.objects.create(store=self.store, name="ف", slug="rs-vendor")
        Product.objects.create(store=self.store, vendor=vendor, category=sub, name="تیشرت", slug="rs-p", sku="RS-1",
                               price=Decimal("100000"), stock=5, status=Product.Status.ACTIVE)
        ShippingMethod.objects.create(store=self.store, name="پست", slug="rs-post", cost=Decimal("50000"), is_active=True)

    def test_ready_to_publish_does_not_need_payment_but_ready_to_sell_does(self):
        self._publishable_store()
        result = self._result()
        self.assertTrue(result["ready_to_publish"])
        self.assertFalse(result["ready_to_sell"])
        self.assertEqual(result["sell_blockers"], ["درگاه پرداخت"])

    def test_every_kind_of_active_payment_method_makes_the_shop_ready_to_sell(self):
        """Online gateway, cash on delivery and card-to-card are the same PaymentGatewayConfig rows — none is privileged, none is excluded."""
        self._publishable_store()
        for code in (PaymentGatewayConfig.GatewayCode.COD, PaymentGatewayConfig.GatewayCode.CARD_TO_CARD, PaymentGatewayConfig.GatewayCode.ZIBAL):
            PaymentGatewayConfig.objects.filter(store=self.store).delete()
            PaymentGatewayConfig.objects.create(store=self.store, gateway_code=code, is_active=True)
            result = self._result()
            self.assertTrue(result["ready_to_sell"], code)
            self.assertNotIn("درگاه پرداخت", result["sell_blockers"], code)

    def test_an_inactive_payment_method_does_not_make_the_shop_ready_to_sell(self):
        self._publishable_store()
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code=PaymentGatewayConfig.GatewayCode.COD, is_active=False)
        self.assertFalse(self._result()["ready_to_sell"])

    def test_a_public_shop_without_payment_is_live_but_not_ready_to_sell(self):
        self._publishable_store()
        self.store.onboarding_completed_at = timezone.now()
        self.store.save(update_fields=["onboarding_completed_at"])
        result = self._result()
        self.assertTrue(result["is_live"])                 # it IS public — the checklist says so truthfully
        self.assertFalse(result["ready_to_sell"])
        self.assertFalse(result["all_complete"])           # no celebration until a customer can actually buy

    def test_another_stores_payment_method_never_counts(self):
        self._publishable_store()
        other = Store.objects.create(name="Other", slug="rs-other", status=Store.Status.ACTIVE)
        PaymentGatewayConfig.objects.create(store=other, gateway_code=PaymentGatewayConfig.GatewayCode.COD, is_active=True)
        self.assertFalse(self._result()["ready_to_sell"])

    def test_a_store_that_is_not_public_is_never_reported_live(self):
        self.store.status = Store.Status.PROVISIONING
        self.store.save(update_fields=["status"])
        self.assertFalse(self._result()["is_live"])

    def test_checklist_never_reads_another_stores_domain(self):
        other = Store.objects.create(name="Other", slug="honest-other", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(
            store=other, hostname="theirs.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
            routing_status=StoreDomain.RoutingStatus.CONNECTED, tls_status=StoreDomain.TlsStatus.READY, is_primary=True,
        )
        step = next(s for s in self._result()["steps"] if s["key"] == "custom_domain")
        self.assertFalse(step["is_complete"])
        self.assertEqual(step["state"], "optional")
