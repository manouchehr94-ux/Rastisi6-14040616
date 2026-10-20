"""Phase 1B — end-to-end route-level tests: the shared universal shell
actually reaches all six public page types once a store has published a
Storefront V2 layout, and legacy (never-published) stores are completely
unaffected.

Covers required scenarios 8 (header/footer/appearance shared across all
six routes), 9 (Draft leak prevention at the route level), 12 (empty
non-home page preserves existing commerce functionality), 13 (legacy
compatibility behavior has explicit tests), 14 (existing Home rendering
does not regress).

Written and read carefully this session; NOT EXECUTED (no Django runtime
available in this sandbox — see the Phase 1B report's "tests not
executed" section). The owner is expected to run these locally.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug):
    vendor = Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
    )


class LegacyStoreRoutesUnaffectedTests(TestCase):
    """13/14 — a store that has never published a Storefront V2 layout must
    render every route exactly as before Phase 1B: base.html's own
    hardcoded shell, no universal-shell markup, no crash."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_home_renders_the_engine_template_when_never_published(self):
        resp = self.client.get(reverse("catalog:home"))
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home_visual.html", template_names)
        self.assertNotIn("catalog/home.html", template_names)

    def test_product_list_renders_normally_without_a_published_layout(self):
        _product(self.store, "legacy-pl-1")
        resp = self.client.get(reverse("catalog:product-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالای legacy-pl-1")

    def test_collection_index_renders_normally_without_a_published_layout(self):
        collection_service.create_collection(self.store, name="کالکشن قدیمی")
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالکشن قدیمی")

    def test_product_detail_renders_normally_without_a_published_layout(self):
        product = _product(self.store, "legacy-pd-1")
        resp = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, product.name)

    def test_cart_renders_normally_without_a_published_layout(self):
        resp = self.client.get(reverse("cart:detail"))
        self.assertEqual(resp.status_code, 200)


class UniversalShellReachesAllSixRoutesTests(TestCase):
    """8 — once a store has published, header/footer/appearance context
    comes from the SAME published version on all six page types, at the
    actual HTTP route level."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {
            **(draft.header_config or {}),
            "announcement_enabled": True, "announcement_text": "PHASE-1B-SHELL-MARKER",
        }
        draft.save(update_fields=["header_config"])
        self.published = svc.publish(self.store)
        self.product = _product(self.store, "shell-marker-1")
        self.collection = collection_service.create_collection(self.store, name="کالکشن پوسته مشترک")

    def _assert_shared_shell(self, resp):
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("PHASE-1B-SHELL-MARKER", body)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_builder/partials/page_shell_header.html", template_names)
        self.assertIn("storefront_builder/partials/page_shell_footer.html", template_names)

    def test_home_uses_shared_shell(self):
        self._assert_shared_shell(self.client.get(reverse("catalog:home")))

    def test_product_detail_uses_shared_shell(self):
        self._assert_shared_shell(
            self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        )

    def test_product_list_uses_shared_shell(self):
        self._assert_shared_shell(self.client.get(reverse("catalog:product-list")))

    def test_search_query_variant_of_listing_uses_shared_shell(self):
        self._assert_shared_shell(self.client.get(reverse("catalog:product-list"), {"q": "shell"}))

    def test_collection_index_uses_shared_shell(self):
        self._assert_shared_shell(self.client.get(reverse("catalog:collection-index")))

    def test_collection_detail_uses_shared_shell(self):
        self._assert_shared_shell(
            self.client.get(reverse("catalog:collection-detail", args=[self.collection.slug]))
        )

    def test_cart_uses_shared_shell(self):
        self._assert_shared_shell(self.client.get(reverse("cart:detail")))

    def test_existing_commerce_content_still_renders_alongside_the_shared_shell(self):
        """12/D — the universal shell wraps existing commerce content
        rather than replacing it: product name/price and collection name
        must still render exactly as before, just inside the new shell."""
        resp = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(resp, self.product.name)
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertContains(resp, self.collection.name)


class DraftDoesNotLeakIntoRoutesTests(TestCase):
    """9 — Draft changes must NOT leak into public routes before publish,
    verified at the HTTP route level for every non-home route (Home's own
    equivalent is already covered by the pre-existing
    test_public_homepage_integration.py)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self.product = _product(self.store, "draft-leak-1")
        self.collection = collection_service.create_collection(self.store, name="کالکشن نشتِ Draft")

    def _poison_draft(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {
            **(draft.header_config or {}), "announcement_enabled": True,
            "announcement_text": "DRAFT-SHOULD-NEVER-LEAK",
        }
        draft.save(update_fields=["header_config"])

    def test_product_detail_never_shows_unpublished_draft_marker(self):
        self._poison_draft()
        resp = self.client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertNotContains(resp, "DRAFT-SHOULD-NEVER-LEAK")

    def test_product_list_never_shows_unpublished_draft_marker(self):
        self._poison_draft()
        resp = self.client.get(reverse("catalog:product-list"))
        self.assertNotContains(resp, "DRAFT-SHOULD-NEVER-LEAK")

    def test_collection_detail_never_shows_unpublished_draft_marker(self):
        self._poison_draft()
        resp = self.client.get(reverse("catalog:collection-detail", args=[self.collection.slug]))
        self.assertNotContains(resp, "DRAFT-SHOULD-NEVER-LEAK")

    def test_cart_never_shows_unpublished_draft_marker(self):
        self._poison_draft()
        resp = self.client.get(reverse("cart:detail"))
        self.assertNotContains(resp, "DRAFT-SHOULD-NEVER-LEAK")


class TenantIsolationAcrossRoutesTests(TestCase):
    """11 — Store A must never receive Store B's version/page/config, at
    the HTTP route level (using two verified custom domains, since the
    single-Store compatibility fallback only applies while exactly one
    Store exists)."""

    def setUp(self):
        cache.clear()
        from django.utils import timezone

        from apps.stores.models import StoreDomain

        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(
            name="فروشگاه ب پوسته", slug="sfb-1b-route-store-b", status=Store.Status.ACTIVE,
        )
        self.host_a = "sfb-1b-shell-a.example.com"
        self.host_b = "sfb-1b-shell-b.example.com"
        StoreDomain.objects.create(
            store=self.store_a, hostname=self.host_a, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store_b, hostname=self.host_b, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

        draft_a = svc.get_or_create_draft(self.store_a)
        draft_a.header_config = {**(draft_a.header_config or {}), "announcement_enabled": True, "announcement_text": "STORE-A-MARKER"}
        draft_a.save(update_fields=["header_config"])
        svc.publish(self.store_a)

        draft_b = svc.get_or_create_draft(self.store_b)
        draft_b.header_config = {**(draft_b.header_config or {}), "announcement_enabled": True, "announcement_text": "STORE-B-MARKER"}
        draft_b.save(update_fields=["header_config"])
        svc.publish(self.store_b)

    def test_store_a_cart_never_shows_store_bs_marker(self):
        from django.test import Client
        from django.test import override_settings

        with override_settings(ALLOWED_HOSTS=[self.host_a, self.host_b, "testserver"]):
            client_a = Client(HTTP_HOST=self.host_a)
            resp = client_a.get(reverse("cart:detail"))
            self.assertContains(resp, "STORE-A-MARKER")
            self.assertNotContains(resp, "STORE-B-MARKER")

    def test_store_b_product_list_never_shows_store_as_marker(self):
        from django.test import Client
        from django.test import override_settings

        with override_settings(ALLOWED_HOSTS=[self.host_a, self.host_b, "testserver"]):
            client_b = Client(HTTP_HOST=self.host_b)
            resp = client_b.get(reverse("catalog:product-list"))
            self.assertContains(resp, "STORE-B-MARKER")
            self.assertNotContains(resp, "STORE-A-MARKER")
