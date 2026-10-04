"""End-to-end Merchant Admin Portal host-enforcement tests (Phase 1C).

Phase 1B left this open (see the Phase 1B report's Known Limitations): a
Store's dashboard was reachable through *any* Host that resolved to it,
including its own public storefront domain. This file proves the fix
(``apps.stores.resolution.resolve_store_for_admin_request``, wired into
``apps.dashboard.decorators.staff_required``/``admin_host_required``):

* the real admin host (``<admin_subdomain>.rastisi.ir``) works
* the Store's own public/custom storefront domain does NOT expose the portal
* an unrelated ``*.rastisi.ir`` host (unknown or another Store's subdomain)
  does NOT expose the portal
* a suspended/inactive Store's admin host stops working
* the ``/admin-panel/`` compatibility redirect obeys the identical rule
* host validity and StoreMembership are independent gates — a valid host
  with no membership still gets the (non-404) "not a member" redirect, and
  an invalid host 404s regardless of membership or auth state
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

PUBLIC_DOMAIN = "digilool-ahe.ir"
ADMIN_HOST = "digilool-ahe.rastisi.ir"
OTHER_STORE_ADMIN_HOST = "otherstore-ahe.rastisi.ir"
UNKNOWN_ADMIN_HOST = "nonexistent-ahe.rastisi.ir"


@override_settings(
    ALLOWED_HOSTS=[PUBLIC_DOMAIN, ADMIN_HOST, OTHER_STORE_ADMIN_HOST, UNKNOWN_ADMIN_HOST, "testserver"],
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class AdminHostEnforcementTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Digilool", slug="digilool-ahe", status=Store.Status.ACTIVE, admin_subdomain="digilool-ahe",
        )
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_DOMAIN, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.other_store = Store.objects.create(
            name="Other Store", slug="other-store-ahe", status=Store.Status.ACTIVE,
            admin_subdomain="otherstore-ahe",
        )
        ShopSettings.provision_for(self.store)
        FooterSettings.provision_for(self.store)
        ShopSettings.provision_for(self.other_store)
        FooterSettings.provision_for(self.other_store)

        self.member = User.objects.create_user(username="ahe-member", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.member, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    # ---------------------------------------------------------- correct admin host

    def test_correct_admin_host_with_membership_works(self):
        self.client.login(username="ahe-member", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 200)

    def test_correct_admin_host_login_page_redirects_to_central_login(self):
        # The legacy merchant login URL is a compatibility redirect: on the
        # store's own admin host it hands off to the one canonical login with a
        # signed, store-bound admin_return (never a second password form).
        response = self.client.get(reverse("dashboard:login"), HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?admin_return=", response["Location"])

    # ---------------------------------------------------------- public domain blocked

    def test_public_custom_domain_blocks_dashboard(self):
        self.client.login(username="ahe-member", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_public_custom_domain_blocks_login_page_too(self):
        """The login page itself is part of the portal — a public domain
        must not even reveal that a login form exists there."""
        response = self.client.get(reverse("dashboard:login"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_public_custom_domain_blocks_even_without_login(self):
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_storefront_itself_still_works_on_public_domain(self):
        """Blocking the admin portal on the public domain must not break
        the storefront that domain is actually for."""
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 200)

    # ---------------------------------------------------------- other/unknown admin hosts

    def test_another_stores_admin_host_does_not_expose_this_store(self):
        """A member of Store A visiting Store B's real admin host reaches
        Store B's (correctly isolated) dashboard, not Store A's — proven by
        denial, since this member has no membership in Store B."""
        self.client.login(username="ahe-member", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=OTHER_STORE_ADMIN_HOST)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_unknown_admin_subdomain_returns_404(self):
        self.client.login(username="ahe-member", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=UNKNOWN_ADMIN_HOST)
        self.assertEqual(response.status_code, 404)

    def test_bare_admin_suffix_with_no_subdomain_returns_404(self):
        with self.settings(ALLOWED_HOSTS=[*ALLOWED_HOSTS_WITH_BARE_SUFFIX(), "testserver"]):
            self.client.login(username="ahe-member", password="pass12345")
            response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST="rastisi.ir")
            self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------- inactive store

    def test_suspended_store_admin_host_returns_404(self):
        self.client.login(username="ahe-member", password="pass12345")
        Store.objects.filter(pk=self.store.pk).update(status=Store.Status.SUSPENDED)
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 404)

    def test_provisioning_store_admin_host_returns_404(self):
        self.client.login(username="ahe-member", password="pass12345")
        Store.objects.filter(pk=self.store.pk).update(status=Store.Status.PROVISIONING)
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------- compat redirect obeys the same rule

    def test_compat_redirect_works_on_correct_admin_host(self):
        response = self.client.get("/admin-panel/", HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/")

    def test_compat_redirect_blocked_on_public_domain(self):
        response = self.client.get("/admin-panel/", HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_compat_redirect_blocked_on_unknown_subdomain(self):
        response = self.client.get("/admin-panel/", HTTP_HOST=UNKNOWN_ADMIN_HOST)
        self.assertEqual(response.status_code, 404)

    def test_compat_redirect_no_open_redirect_via_rest_param(self):
        """The redirect target is built server-side from the fixed
        '/admin-portal/' prefix plus the matched path — an attacker-supplied
        sub-path can never escape that prefix to redirect off-site."""
        response = self.client.get("/admin-panel/products/", HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin-portal/products/")
        self.assertTrue(response.url.startswith("/admin-portal/"))

    # ---------------------------------------------------------- host and membership are independent gates

    def test_valid_host_but_no_membership_is_redirect_not_404(self):
        """An invalid *host* 404s; a valid host with a non-member user gets
        the ordinary 'not a member of this Store' redirect — these are
        deliberately different failure modes."""
        nomember = User.objects.create_user(username="ahe-nomember", password="pass12345", is_staff=True)
        self.client.login(username="ahe-nomember", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=ADMIN_HOST)
        self.assertRedirects(response, reverse("catalog:home"), fetch_redirect_response=False)

    def test_invalid_host_404s_even_for_a_real_member(self):
        """Even a legitimate member of the Store gets 404 (not the
        membership redirect) on a host that isn't the Store's admin host —
        host validity is checked first."""
        self.client.login(username="ahe-member", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_invalid_host_404s_for_anonymous_user_too(self):
        """A disallowed host 404s before the authentication check — an
        anonymous visitor to the public domain never even sees a redirect
        to the login page."""
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)

    def test_invalid_host_404s_for_superuser_too(self):
        superuser = User.objects.create_superuser(
            username="ahe-super", email="ahe-super@example.com", password="pass12345",
        )
        self.client.login(username="ahe-super", password="pass12345")
        response = self.client.get(reverse("dashboard:dashboard"), HTTP_HOST=PUBLIC_DOMAIN)
        self.assertEqual(response.status_code, 404)


def ALLOWED_HOSTS_WITH_BARE_SUFFIX():
    return [PUBLIC_DOMAIN, ADMIN_HOST, OTHER_STORE_ADMIN_HOST, UNKNOWN_ADMIN_HOST, "rastisi.ir"]


@override_settings(
    ALLOWED_HOSTS=["dgs-store-real.ir", "dgs-store-real.rastisi.ir", "testserver"],
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
)
class RealMultiStoreProductionShapeTests(TestCase):
    """One more end-to-end sanity check with realistic catalog data —
    proves host enforcement doesn't interfere with actually using the
    dashboard, not just with denying access to it."""

    def setUp(self):
        self.store = Store.objects.create(
            name="Real Shape Store", slug="dgs-store-real", status=Store.Status.ACTIVE,
            admin_subdomain="dgs-store-real",
        )
        StoreDomain.objects.create(
            store=self.store, hostname="dgs-store-real.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        ShopSettings.provision_for(self.store)
        FooterSettings.provision_for(self.store)
        self.vendor = Vendor.objects.create(store=self.store, name="Vendor", slug="vendor-dgsr")
        self.category = Category.objects.create(store=self.store, name="Cat", slug="cat-dgsr")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="Product",
            slug="product-dgsr", sku="SKU-DGSR1", price=Decimal("100000"),
        )
        self.owner = User.objects.create_user(username="dgsr-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def test_product_list_works_on_admin_host(self):
        self.client.login(username="dgsr-owner", password="pass12345")
        response = self.client.get(reverse("dashboard:product-list"), HTTP_HOST="dgs-store-real.rastisi.ir")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product")

    def test_product_list_blocked_on_public_domain(self):
        self.client.login(username="dgsr-owner", password="pass12345")
        response = self.client.get(reverse("dashboard:product-list"), HTTP_HOST="dgs-store-real.ir")
        self.assertEqual(response.status_code, 404)

    def test_storefront_product_page_still_works_on_public_domain(self):
        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product.slug]), HTTP_HOST="dgs-store-real.ir",
        )
        self.assertEqual(response.status_code, 200)
