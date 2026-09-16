"""P5-W4A — Wishlist converges onto the canonical universal storefront shell
(``storefront_shell.html`` + ``build_universal_storefront_context(...,
shell_only=True)``), while its own domain body/state (login-prompt, empty
state, ``ProductCard`` reuse) and its write-path tenant isolation
(``wishlist_toggle`` — already correct, see ``test_wishlist_store_isolation.py``)
stay exactly as they are. Reuses that same file's real two-Store/verified-
``StoreDomain``/distinct-``HTTP_HOST`` fixture pattern for the new read-path
isolation proof — no ``request.store`` mocking."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Customer, Wishlist
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

User = get_user_model()

HOST_A = "wsc-a.example.com"
HOST_B = "wsc-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


def _publish_with_header_variant(store, header_variant):
    draft = svc.get_or_create_draft(store)
    draft.header_config = {**(draft.header_config or {}), "header_variant": header_variant}
    draft.save(update_fields=["header_config"])
    svc.publish(store)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class WishlistShellConvergenceTwoStoreTests(TestCase):
    """A/B/C/F/G/H — canonical shell presence + cross-Store read/shell
    isolation, on two real Stores with real verified StoreDomains."""

    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="wsc-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-wsc-a")
        category_a = Category.objects.create(store=self.store_a, name="Cat A", slug="cat-wsc-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=vendor_a, category=category_a,
            name="Product A", slug="product-wsc-a", sku="SKU-WSC-A",
            price=Decimal("100000"), status=Product.Status.ACTIVE,
        )
        vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-wsc-b")
        category_b = Category.objects.create(store=self.store_b, name="Cat B", slug="cat-wsc-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=vendor_b, category=category_b,
            name="Product B", slug="product-wsc-b", sku="SKU-WSC-B",
            price=Decimal("200000"), status=Product.Status.ACTIVE,
        )

        _publish_with_header_variant(self.store_a, "editorial_row")
        _publish_with_header_variant(self.store_b, "community_shortcuts")

        user = User.objects.create_user(username="wsc-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121112233")
        Wishlist.objects.create(customer=self.customer, product=self.product_a)
        Wishlist.objects.create(customer=self.customer, product=self.product_b)
        self.client.login(username="wsc-user", password="pass12345")

    def _get(self, host):
        return self.client.get(reverse("customers:wishlist"), HTTP_HOST=host)

    # A/B/C — canonical shell present.
    def test_canonical_shell_templates_present_on_published_store(self):
        resp = self._get(HOST_A)
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_shell.html", template_names)
        self.assertIn("storefront_builder/partials/global_header/editorial_row.html", template_names)

    # G — cross-Store READ isolation (must fail on the certified base:
    # wishlist_list today filters only by customer, no product__store).
    def test_wishlist_shows_only_current_store_products(self):
        resp_a = self._get(HOST_A)
        self.assertContains(resp_a, "Product A")
        self.assertNotContains(resp_a, "Product B")

        resp_b = self._get(HOST_B)
        self.assertContains(resp_b, "Product B")
        self.assertNotContains(resp_b, "Product A")

    # H — shell isolation: Store A's header variant never appears on Store
    # B's Wishlist render and vice versa.
    def test_shell_isolation_between_stores(self):
        template_names_a = [t.name for t in self._get(HOST_A).templates if t.name]
        self.assertIn("storefront_builder/partials/global_header/editorial_row.html", template_names_a)
        self.assertNotIn("storefront_builder/partials/global_header/community_shortcuts.html", template_names_a)

        template_names_b = [t.name for t in self._get(HOST_B).templates if t.name]
        self.assertIn("storefront_builder/partials/global_header/community_shortcuts.html", template_names_b)
        self.assertNotIn("storefront_builder/partials/global_header/editorial_row.html", template_names_b)

    # ProductCard reuse preserved (no wishlist_product_card.html).
    def test_product_card_partial_reused(self):
        template_names = [t.name for t in self._get(HOST_A).templates if t.name]
        self.assertIn("catalog/partials/product_card.html", template_names)
        self.assertNotIn("wishlist_product_card.html", template_names)


class WishlistShellConvergenceStateTests(TestCase):
    """D/E — domain state (anonymous, empty) preserved under the new shell,
    on the single-Store compatibility fixture the rest of the Wishlist test
    suite already uses."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_anonymous_state_preserved_under_canonical_shell(self):
        resp = self.client.get(reverse("customers:wishlist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ابتدا وارد حساب کاربری خود شوید")
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_shell.html", template_names)

    def test_empty_authenticated_state_preserved_under_canonical_shell(self):
        user = User.objects.create_user(username="wsc-empty-user", password="pass12345")
        Customer.objects.create(user=user, full_name="مشتری خالی", phone="09121110099")
        self.client.login(username="wsc-empty-user", password="pass12345")
        resp = self.client.get(reverse("customers:wishlist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "لیست علاقه‌مندی‌های شما خالی است")
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_shell.html", template_names)


class WishlistShellConvergenceFallbackTests(TestCase):
    """I — a Store with no published universal layout: Wishlist still 200s
    with its domain state; storefront_shell.html falls through to
    base.html's own header/footer via block.super, no crash."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        # Deliberately no get_or_create_draft/publish call.

    def test_wishlist_renders_without_published_layout(self):
        resp = self.client.get(reverse("customers:wishlist"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ابتدا وارد حساب کاربری خود شوید")
