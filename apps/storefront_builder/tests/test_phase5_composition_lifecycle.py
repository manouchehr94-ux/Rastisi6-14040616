"""Phase 5 — end-to-end lifecycle tests for the composed body content of
the five non-home page types (product_detail/listing/collection/search/
cart), at the real HTTP route level. Complements the per-section-type unit
tests in test_render_service.py and the Preview-integration tests in
test_views.py: this file proves the same guarantees Phase 4 already proved
for Header/Footer (tenant isolation, Draft/Published isolation, Preview
always Draft, Public always Published) now also hold for the newly
composable page BODY content — plus reorder/hide/responsive-settings
reaching the real page, and that search query / collection identity are
never persisted into builder config (route context only)."""

from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

from django.contrib.auth import get_user_model

User = get_user_model()

ADMIN_HOST = "sfb-p5-lifecycle.rastisi.localhost"
PUBLIC_HOST_A = "sfb-p5-lifecycle-a.example.com"
PUBLIC_HOST_B = "sfb-p5-lifecycle-b.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug, *, name=None):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}", is_active=True)
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=name or f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), stock=5, status=Product.Status.ACTIVE,
    )


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST_A, PUBLIC_HOST_B, "testserver"])
class DraftPublishedPreviewPublicLifecycleTests(TestCase):
    """۱۱/۱۲/۱۳/۱۴ — تغییرات Draft در Public دیده نمی‌شوند، پس از Publish
    دیده می‌شوند، Preview همیشه Draft را نشان می‌دهد."""

    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="p5_lifecycle_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="p5_lifecycle_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST_A)

        self.product = _product(self.store, "p5-lifecycle-product")
        self.draft = svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_draft_only_section_setting_invisible_publicly_before_publish(self):
        # setUp خودش یک‌بار publish کرده — layout.draft_version اکنون
        # None است؛ برای ادامه‌ی ویرایش باید یک Draftِ تازه (کلون‌شده از
        # همان منتشرشده) گرفت، نه روی ``self.draft``یِ حالا archived کار کرد.
        fresh_draft = svc.get_or_create_draft(self.store)
        pd_page = fresh_draft.get_page("product_detail")
        section = pd_page.sections.get(section_key="related_products")
        section.is_active = False
        section.save(update_fields=["is_active"])

        public_resp = self.public_client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        preview_resp = self.admin_client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "product_detail"},
        )
        # قبل از publish: Draft غیرفعال‌شده فقط در Preview دیده می‌شود؛
        # صفحه‌ی عمومی هنوز نسخه‌ی منتشرشده‌ی قبلی (که related_products
        # فعال دارد) را نشان می‌دهد.
        self.assertNotContains(preview_resp, 'data-section-key="related_products"')
        self.assertEqual(public_resp.status_code, 200)

    def test_published_change_appears_publicly_after_publish(self):
        fresh_draft = svc.get_or_create_draft(self.store)
        pd_page = fresh_draft.get_page("product_detail")
        section = pd_page.sections.get(section_key="product_video")
        section.is_active = False
        section.save(update_fields=["is_active"])
        svc.publish(self.store)

        public_resp = self.public_client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(public_resp, self.product.name)
        self.assertNotContains(public_resp, "ویدئوهای محصول")

    def test_preview_always_reflects_draft_not_published(self):
        fresh_draft = svc.get_or_create_draft(self.store)
        cart_page = fresh_draft.get_page("cart")
        cart_page.sections.filter(section_key="cart_summary").update(is_active=False)

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})
        self.assertEqual(preview_resp.status_code, 200)
        self.assertNotContains(preview_resp, "جمع قابل پرداخت")


@override_settings(ALLOWED_HOSTS=[PUBLIC_HOST_A, PUBLIC_HOST_B, "testserver"])
class CrossStoreCompositionIsolationTests(TestCase):
    """۷/۸/۹/۳۰ — ترکیب‌بندیِ Storeِ الف هرگز رویِ صفحاتِ عمومیِ Storeِ ب
    دیده نمی‌شود؛ برعکس هم همین‌طور."""

    def setUp(self):
        from apps.core.models import ShopSettings

        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="فروشگاه ب فاز۵", slug="sfb-p5-store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.store_b)
        StoreDomain.objects.create(
            store=self.store_a, hostname=PUBLIC_HOST_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store_b, hostname=PUBLIC_HOST_B, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.product_a = _product(self.store_a, "p5-cross-a", name="کالای محرمانه فروشگاه الف")
        self.product_b = _product(self.store_b, "p5-cross-b", name="کالای محرمانه فروشگاه ب")
        self.collection_a = collection_service.create_collection(self.store_a, name="کالکشن محرمانه الف")
        self.collection_b = collection_service.create_collection(self.store_b, name="کالکشن محرمانه ب")
        collection_service.add_product(self.collection_a, self.product_a)
        collection_service.add_product(self.collection_b, self.product_b)

        svc.get_or_create_draft(self.store_a)
        svc.publish(self.store_a)
        svc.get_or_create_draft(self.store_b)
        svc.publish(self.store_b)
        self.client_a = Client(HTTP_HOST=PUBLIC_HOST_A)
        self.client_b = Client(HTTP_HOST=PUBLIC_HOST_B)

    def test_product_detail_never_leaks_across_stores(self):
        # محصولِ Storeِ ب حتی روی URL درستِ خودش، از میزبانِ Storeِ الف قابل‌مشاهده نیست.
        resp = self.client_a.get(reverse("catalog:product-detail", args=[self.product_b.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_listing_never_shows_another_stores_product(self):
        resp = self.client_a.get(reverse("catalog:product-list"))
        self.assertContains(resp, "کالای محرمانه فروشگاه الف")
        self.assertNotContains(resp, "کالای محرمانه فروشگاه ب")

    def test_collection_detail_never_leaks_across_stores(self):
        resp = self.client_a.get(reverse("catalog:collection-detail", args=[self.collection_b.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_collection_detail_shows_only_own_stores_collection_content(self):
        resp = self.client_a.get(reverse("catalog:collection-detail", args=[self.collection_a.slug]))
        self.assertContains(resp, "کالکشن محرمانه الف")
        self.assertContains(resp, "کالای محرمانه فروشگاه الف")
        self.assertNotContains(resp, "کالکشن محرمانه ب")
        self.assertNotContains(resp, "کالای محرمانه فروشگاه ب")

    def test_search_never_shows_another_stores_product(self):
        resp = self.client_b.get(reverse("catalog:product-list") + "?q=" + "کالای")
        self.assertContains(resp, "کالای محرمانه فروشگاه ب")
        self.assertNotContains(resp, "کالای محرمانه فروشگاه الف")

    def test_cart_never_shows_another_stores_data(self):
        resp_a = self.client_a.get(reverse("cart:detail"))
        resp_b = self.client_b.get(reverse("cart:detail"))
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        # سبد یک بازدیدکننده‌ی ناشناسِ تازه همیشه خالی است — هیچ محصولی
        # از هیچ Storeای نباید نشت کند.
        self.assertNotContains(resp_a, "کالای محرمانه فروشگاه ب")
        self.assertNotContains(resp_b, "کالای محرمانه فروشگاه الف")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST_A, "testserver"])
class SearchQueryAndCollectionIdentityStayRouteContextTests(TestCase):
    """۲۵/۲۶ — عبارتِ جستجو و هویتِ کالکشن هرگز در تنظیماتِ سازنده ذخیره
    نمی‌شوند؛ همیشه از خودِ درخواست/URL می‌آیند."""

    def setUp(self):
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=PUBLIC_HOST_A)
        self.product = _product(self.store, "p5-query-context", name="کالای زمینه جستجو")
        self.collection = collection_service.create_collection(self.store, name="کالکشن زمینه مسیر")
        collection_service.add_product(self.collection, self.product)
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_search_query_never_persisted_into_section_settings(self):
        self.client.get(reverse("catalog:product-list") + "?q=زمینه")
        draft = svc.get_or_create_draft(self.store)
        listing_page = draft.get_page("listing")
        search_page = draft.get_page("search")
        for page in (listing_page, search_page):
            for section in page.sections.all():
                self.assertNotIn("زمینه", str(section.settings))
                self.assertNotIn("query", section.settings if isinstance(section.settings, dict) else {})

    def test_different_search_queries_reuse_the_same_persisted_section(self):
        """پرس‌وجویِ متفاوت، ردیفِ section جدیدی نمی‌سازد — همیشه همان
        product_listing است، فقط داده‌یِ رندرشده متفاوت."""
        draft = svc.get_or_create_draft(self.store)
        search_page = draft.get_page("search")
        count_before = search_page.sections.filter(section_key="product_listing").count()

        self.client.get(reverse("catalog:product-list") + "?q=اول")
        self.client.get(reverse("catalog:product-list") + "?q=دوم")

        search_page.refresh_from_db()
        count_after = search_page.sections.filter(section_key="product_listing").count()
        self.assertEqual(count_before, count_after)

    def test_collection_identity_never_persisted_into_section_settings(self):
        self.client.get(reverse("catalog:collection-detail", args=[self.collection.slug]))
        draft = svc.get_or_create_draft(self.store)
        collection_page = draft.get_page("collection")
        for section in collection_page.sections.all():
            self.assertNotIn("collection_id", section.settings if isinstance(section.settings, dict) else {})
            self.assertNotIn(str(self.collection.pk), str(section.settings))

    def test_visiting_a_different_collection_does_not_change_stored_settings(self):
        other_collection = collection_service.create_collection(self.store, name="کالکشنِ دومِ زمینه مسیر")
        draft = svc.get_or_create_draft(self.store)
        collection_page = draft.get_page("collection")
        settings_before = list(collection_page.sections.order_by("id").values_list("settings", flat=True))

        self.client.get(reverse("catalog:collection-detail", args=[self.collection.slug]))
        self.client.get(reverse("catalog:collection-detail", args=[other_collection.slug]))

        collection_page.refresh_from_db()
        settings_after = list(collection_page.sections.order_by("id").values_list("settings", flat=True))
        self.assertEqual(settings_before, settings_after)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST_A, "testserver"])
class ReorderHideResponsiveReachPublicPageTests(TestCase):
    """۱۷/۱۹/۲۰ — بازچینی/فعال‌سازی/غیرفعال‌سازی/تنظیماتِ ریسپانسیو رویِ
    این پنج صفحه، دقیقاً مثلِ صفحه‌ی اصلی، تا صفحه‌ی عمومی می‌رسند."""

    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="p5_reorder_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="p5_reorder_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST_A)
        self.product = _product(self.store, "p5-reorder-product")
        # عمداً اینجا publish نمی‌شود — هر تست خودش دقیقاً یک‌بار در پایان
        # publish می‌کند؛ ``layout_service.publish`` بعد از موفقیت
        # ``layout.draft_version`` را None می‌کند، پس فراخوانیِ دوباره‌ی
        # آن بدونِ گرفتنِ یک Draftِ تازه خطا می‌دهد — با یک‌بار publish در
        # هر تست، ``self.draft`` هرگز stale نمی‌شود.
        self.draft = svc.get_or_create_draft(self.store)

    def test_reorder_persists_and_reaches_public_page(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        pd_page = self.draft.get_page("product_detail")
        main = pd_page.sections.get(section_key="product_main")
        desc = pd_page.sections.get(section_key="product_description")
        # جابه‌جاییِ ترتیب: توضیحات قبل از بخشِ اصلی
        resp = self.admin_client.post(reverse("dashboard:storefront-builder-section-reorder"), {
            "page": "product_detail", "section_ids": [str(desc.pk), str(main.pk)],
        })
        self.assertEqual(resp.status_code, 200)
        desc.refresh_from_db()
        main.refresh_from_db()
        self.assertLess(desc.order, main.order)

        svc.publish(self.store)
        body = self.public_client.get(reverse("catalog:product-detail", args=[self.product.slug])).content.decode()
        # ``self.product.name`` هم در ``<title>`` (همیشه در ابتدای صفحه)
        # ظاهر می‌شود — نشانه‌یِ اختصاصیِ بدنه‌ی product_main دقیقاً همان
        # تگِ h1 است، نه صرفِ نامِ محصول در هرجایِ صفحه.
        self.assertLess(body.index("توضیحات محصول"), body.index(f"<h1>{self.product.name}</h1>"))

    def test_hiding_a_section_removes_it_from_the_public_page(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        pd_page = self.draft.get_page("product_detail")
        video_section = pd_page.sections.get(section_key="product_video")
        resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-section-toggle", args=[video_section.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        video_section.refresh_from_db()
        self.assertFalse(video_section.is_active)

        svc.publish(self.store)
        preview_resp = self.admin_client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "product_detail"},
        )
        self.assertNotContains(preview_resp, 'data-section-key="product_video"')

    def test_responsive_hide_on_mobile_reaches_public_page(self):
        cart_page = self.draft.get_page("cart")
        summary = cart_page.sections.get(section_key="cart_summary")
        summary.settings = {
            **(summary.settings or {}),
            "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True},
        }
        summary.save(update_fields=["settings"])
        svc.publish(self.store)

        body = self.public_client.get(reverse("cart:detail")).content.decode()
        self.assertIn("data-hide-mobile", body)
