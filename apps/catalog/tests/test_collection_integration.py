"""تست‌های یکپارچگیِ کالکشن — سناریوی واقعیِ مرچنت از ابتدا تا انتها،
عبور از سرویس + view دشبورد + صفحه‌ی عمومی با هم، برای گرفتنِ باگ‌های
درزِ بین لایه‌ها که تست‌های تک‌واحدی ممکن است نبینند."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, MerchantCollection, Product, Vendor
from apps.catalog.services import collection_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "coll-integration.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
    )


class FullMerchantWorkflowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="coll_flow_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="coll_flow_owner", password="pass12345")

    def test_create_add_reorder_publish_and_view_publicly(self):
        # ۱. ساختِ کالکشن از داشبورد
        create_resp = self.client.post(reverse("dashboard:collection-add"), {
            "name": "وایر شمع", "description": "توضیح کامل کالکشن", "seo_title": "وایر شمع اورجینال",
            "seo_description": "بهترین وایر شمع‌های بازار",
        })
        collection = MerchantCollection.objects.get(store=self.store, name="وایر شمع")
        self.assertRedirects(create_resp, reverse("dashboard:collection-products", args=[collection.pk]))

        # ۲. افزودنِ چند کالا
        products = [_product(self.store, f"flow-p{i}") for i in range(3)]
        self.client.post(reverse("dashboard:collection-products-add", args=[collection.pk]), {
            "product_ids": [p.pk for p in products],
        })
        self.assertEqual(collection.items.count(), 3)

        # ۳. مرتب‌سازی — آخرین کالا به جایگاه اول
        items = list(collection.items.order_by("order"))
        new_order = [items[2].pk, items[0].pk, items[1].pk]
        self.client.post(reverse("dashboard:collection-products-reorder", args=[collection.pk]), {
            "item_ids": new_order,
        })

        # ۴. غیرفعال‌سازی — صفحه‌ی عمومی نباید در دسترس باشد
        self.client.post(reverse("dashboard:collection-toggle", args=[collection.pk]))
        collection.refresh_from_db()
        self.assertFalse(collection.is_active)
        public_client = Client(HTTP_HOST="localhost")
        resp = public_client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 404)

        # ۵. فعال‌سازی دوباره
        self.client.post(reverse("dashboard:collection-toggle", args=[collection.pk]))
        collection.refresh_from_db()
        self.assertTrue(collection.is_active)

        # ۶. حالا صفحه‌ی عمومی باید نمایش دهد، با ترتیبِ دستیِ درست و سئو
        resp = public_client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "وایر شمع اورجینال")
        self.assertContains(resp, "بهترین وایر شمع‌های بازار")
        body = resp.content.decode()
        self.assertLess(body.index(products[2].name), body.index(products[0].name))
        self.assertLess(body.index(products[0].name), body.index(products[1].name))

        # ۷. غیرفعال‌سازی دوباره — صفحه باید ۴۰۴ برگردد
        self.client.post(reverse("dashboard:collection-toggle", args=[collection.pk]))
        resp = public_client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 404)


class CrossStoreProductRejectionEndToEndTests(TestCase):
    """سناریوی C کار (ایزوله‌سازی): آی‌دیِ کالای فروشگاه دیگر هرگز نباید در
    هیچ نقطه‌ای (سرویس یا view) واقعاً چیزی در دیتابیس تغییر دهد."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.other_store = Store.objects.create(
            name="فروشگاه بیگانه", slug="coll-flow-foreign", admin_subdomain="coll-flow-foreign",
        )
        self.staff = User.objects.create_user(username="coll_flow_isolation", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="coll_flow_isolation", password="pass12345")
        self.collection = svc.create_collection(self.store, name="ایزوله")

    def test_foreign_product_id_rejected_no_mutation(self):
        foreign_product = _product(self.other_store, "foreign-flow-1")
        before_count = self.collection.items.count()

        resp = self.client.post(reverse("dashboard:collection-products-add", args=[self.collection.pk]), {
            "product_ids": [foreign_product.pk],
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.collection.items.count(), before_count)
        self.assertFalse(self.collection.items.filter(product=foreign_product).exists())


class CollectionTypeContractTests(TestCase):
    """collection_type از روز اول رزرو شده اما فقط manual قابل‌استفاده است —
    هیچ مسیرِ سرویس/فرمی راهی برای ساختنِ نوعِ smart باز نمی‌گذارد."""

    def test_create_collection_service_has_no_type_parameter(self):
        import inspect

        signature = inspect.signature(svc.create_collection)
        self.assertNotIn("collection_type", signature.parameters)

    def test_created_collection_is_always_manual(self):
        store = _akhlaghi()
        collection = svc.create_collection(store, name="همیشه دستی")
        self.assertEqual(collection.collection_type, MerchantCollection.CollectionType.MANUAL)



class CollectionDetailForeignHostPaginationTests(TestCase):
    """Task 5 — a collection detail page (including ``?page=2``) is reachable
    ANONYMOUSLY through a store's verified public custom domain (the existing
    domain resolution fixture), served entirely by the domain-owned view: the
    tenant is resolved from the host, the visible-membership list is
    paginated, and page 2 carries the remaining members with no HTMX branch.
    """

    PUBLIC_HOST = "coll-foreign-public.example.com"

    def setUp(self):
        from django.test import override_settings
        from apps.stores.models import StoreDomain

        cache.clear()
        self._override = override_settings(ALLOWED_HOSTS=[self.PUBLIC_HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)

        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=self.PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.collection = svc.create_collection(self.store, name="کالکشنِ میزبانِ بیگانه")
        for i in range(15):
            svc.add_product(self.collection, _product(self.store, f"foreign-page-{i:02d}"))
        # Anonymous client on the store's verified public host.
        self.public_client = Client(HTTP_HOST=self.PUBLIC_HOST)

    def test_anonymous_foreign_host_page2_renders_domain_membership(self):
        url = reverse("catalog:collection-detail", args=[self.collection.slug])
        resp = self.public_client.get(f"{url}?page=2")
        self.assertEqual(resp.status_code, 200)
        # Resolved via the host to the right tenant/collection.
        self.assertEqual(resp.context["collection"], self.collection)
        page_obj = resp.context["page_obj"]
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.num_pages, 2)
        self.assertEqual(len(resp.context["products"]), 3)

    def test_foreign_store_collection_slug_is_404_on_this_host(self):
        other_store = Store.objects.create(
            name="فروشگاهِ کاملاً دیگر", slug="coll-foreign-other", admin_subdomain="coll-foreign-other",
        )
        other_collection = svc.create_collection(other_store, name="کالکشنِ فروشگاهِ دیگر")
        url = reverse("catalog:collection-detail", args=[other_collection.slug])
        resp = self.public_client.get(url)
        self.assertEqual(resp.status_code, 404)
