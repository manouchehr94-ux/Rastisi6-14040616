"""PR #21 completion tests: gaps found while reviewing the unified login.

Unusable passwords on every surface, an already signed-in owner following a
signed admin_return, public storefront domains never serving merchant
administration, and non-ACTIVE memberships never receiving a handoff.
"""
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.customers.services.auth_service import authenticate_customer_by_identifier
from apps.portal.models import OwnerProfile
from apps.portal.services import owner_auth_service
from apps.portal.services.handoff_service import build_admin_return_token
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()
PORTAL = "rastisi.localhost"
ADMIN_SUB = "hardening"
ADMIN_HOST = f"{ADMIN_SUB}.rastisi.localhost"
SHOP_HOST = "hardening-shop.example.com"
PASSWORD = "a-very-strong-pass-1"


def _store(sub=ADMIN_SUB):
    return Store.objects.create(
        name=f"Store {sub}", slug=f"store-{sub}", status=Store.Status.ACTIVE,
        platform_code=generate_unique_platform_code(), admin_subdomain=sub,
    )


def _member(store, username, status=StoreMembership.MembershipStatus.ACTIVE, role=StoreMembership.Role.OWNER):
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password=PASSWORD)
    extra = {"revoked_at": timezone.now()} if status == StoreMembership.MembershipStatus.REVOKED else {}
    StoreMembership.objects.create(
        store=store, user=user, role=role, status=status, accepted_at=timezone.now(), **extra,
    )
    return user


class UnusablePasswordTests(TestCase):
    """An account with set_unusable_password() never authenticates by any identifier."""

    def setUp(self):
        self.request = RequestFactory().post("/login/")

    def test_owner_identifiers_reject_unusable_password(self):
        user = User.objects.create_user(username="owner_unusable", email="ou@example.com")
        user.set_unusable_password()
        user.save()
        OwnerProfile.objects.create(user=user, phone="09125550001")
        for identifier in ("owner_unusable", "ou@example.com", "09125550001"):
            for password in (PASSWORD, "", "!", "None"):
                self.assertIsNone(
                    owner_auth_service.authenticate_owner_by_identifier(
                        self.request, identifier=identifier, password=password,
                    ), (identifier, password),
                )

    def test_customer_identifiers_reject_unusable_password(self):
        user = User.objects.create_user(username="cust_unusable")
        user.set_unusable_password()
        user.save()
        Customer.objects.create(user=user, full_name="C", phone="09125550002", email="cu@example.com")
        for identifier in ("cust_unusable", "cu@example.com", "09125550002"):
            self.assertIsNone(
                authenticate_customer_by_identifier(self.request, identifier=identifier, password=PASSWORD),
                identifier,
            )

    @override_settings(ALLOWED_HOSTS=["testserver", "platformadmins.rastisi.localhost"])
    def test_platform_admin_login_rejects_unusable_password(self):
        cache.clear()
        user = User.objects.create_user(
            username="padmin_unusable", email="pu@example.com", is_staff=True, is_superuser=True,
        )
        user.set_unusable_password()
        user.save()
        for identifier in ("padmin_unusable", "pu@example.com"):
            response = self.client.post(
                "/login/", {"identifier": identifier, "password": PASSWORD},
                HTTP_HOST="platformadmins.rastisi.localhost",
            )
            self.assertNotEqual(response.status_code, 302, identifier)
            self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(
    ALLOWED_HOSTS=[PORTAL, ADMIN_HOST, SHOP_HOST, "testserver"],
    RASTISI_PLATFORM_PRIMARY_HOST=PORTAL,
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.localhost",
)
class SignedHandoffForAuthenticatedOwnerTests(TestCase):
    """An owner already signed in at the central portal follows the signed return."""

    def setUp(self):
        cache.clear()
        self.store = _store()
        self.owner = _member(self.store, "hand_owner")
        self.token = build_admin_return_token(admin_subdomain=ADMIN_SUB, destination_path="/admin-portal/orders/")

    def test_member_is_sent_to_the_store_handoff(self):
        self.client.force_login(self.owner)
        response = self.client.get(f"/login/?admin_return={self.token}", HTTP_HOST=PORTAL)
        self.assertEqual(response.status_code, 302)
        parts = urlsplit(response["Location"])
        self.assertEqual(parts.hostname, ADMIN_HOST)
        self.assertTrue(parts.path.startswith("/admin-portal/handoff/"))

    def test_signed_in_user_without_return_still_goes_to_my_stores(self):
        self.client.force_login(self.owner)
        response = self.client.get("/login/", HTTP_HOST=PORTAL)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/handoff/", response["Location"])

    def test_non_member_gets_no_ticket(self):
        stranger = User.objects.create_user(username="stranger", password=PASSWORD)
        self.client.force_login(stranger)
        response = self.client.get(f"/login/?admin_return={self.token}", HTTP_HOST=PORTAL)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/handoff/", response["Location"])

    def test_invited_or_revoked_member_gets_no_ticket(self):
        for status in (StoreMembership.MembershipStatus.INVITED, StoreMembership.MembershipStatus.REVOKED):
            user = _member(self.store, f"inactive_{status}", status=status, role=StoreMembership.Role.ANALYST)
            self.client.force_login(user)
            response = self.client.get(f"/login/?admin_return={self.token}", HTTP_HOST=PORTAL)
            self.assertNotIn("/handoff/", response["Location"], status)

    def test_tampered_return_is_ignored(self):
        self.client.force_login(self.owner)
        bad = self.token[:-1] + ("a" if self.token[-1] != "a" else "b")
        response = self.client.get(f"/login/?admin_return={bad}", HTTP_HOST=PORTAL)
        self.assertNotIn("/handoff/", response["Location"])

    def test_return_bound_to_a_different_store_does_not_grant_this_owner_access(self):
        other = _store("hardening2")
        token = build_admin_return_token(admin_subdomain=other.admin_subdomain, destination_path="/admin-portal/")
        self.client.force_login(self.owner)  # member of ADMIN_SUB only
        response = self.client.get(f"/login/?admin_return={token}", HTTP_HOST=PORTAL)
        self.assertNotIn("/handoff/", response["Location"])


@override_settings(
    ALLOWED_HOSTS=[PORTAL, ADMIN_HOST, SHOP_HOST, "testserver", "localhost", "127.0.0.1"],
    RASTISI_PLATFORM_PRIMARY_HOST=PORTAL,
    RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.localhost",
)
class LegacyMerchantLoginHostSafetyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _store()
        _store("hardening3")  # multi-store database
        StoreDomain.objects.create(
            store=self.store, hostname=SHOP_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_public_storefront_domain_does_not_serve_merchant_login(self):
        for method in ("get", "post"):
            response = getattr(self.client, method)("/admin-portal/login/", HTTP_HOST=SHOP_HOST)
            self.assertEqual(response.status_code, 404, method)

    def test_inactive_store_admin_host_is_404(self):
        Store.objects.filter(pk=self.store.pk).update(status=Store.Status.SUSPENDED)
        response = self.client.get("/admin-portal/login/", HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 404)

    @override_settings(DEBUG=False)
    def test_localhost_without_debug_never_redirects_or_guesses_a_store(self):
        for host in ("localhost:8000", "127.0.0.1:8000"):
            response = self.client.get("/admin-portal/login/", HTTP_HOST=host)
            self.assertEqual(response.status_code, 404, host)

    @override_settings(DEBUG=True)
    def test_localhost_in_debug_goes_to_central_login_without_a_store_token(self):
        for host in ("localhost:8000", "127.0.0.1:8000"):
            response = self.client.get("/admin-portal/login/?next=/admin-portal/orders/", HTTP_HOST=host)
            self.assertEqual(response.status_code, 302, host)
            self.assertEqual(response["Location"], f"http://{PORTAL}:8000/login/", host)

    def test_valid_admin_host_return_is_store_bound_and_open_redirect_safe(self):
        for evil in ("//evil.example/x", "https://evil.example/", "/admin-portal/../x", "/other/"):
            response = self.client.get("/admin-portal/login/", {"next": evil}, HTTP_HOST=ADMIN_HOST)
            self.assertEqual(response.status_code, 302, evil)
            query = parse_qs(urlsplit(response["Location"]).query)
            from apps.portal.services.handoff_service import decode_admin_return_token
            sub, path = decode_admin_return_token(query["admin_return"][0])
            self.assertEqual(sub, ADMIN_SUB)
            self.assertTrue(path.startswith("/admin-portal/"), (evil, path))
            self.assertNotIn("evil", path)

    def test_staff_flag_alone_never_grants_merchant_access(self):
        stranger = User.objects.create_user(username="staff_no_membership", password=PASSWORD, is_staff=True)
        self.client.force_login(stranger)
        response = self.client.get("/admin-portal/login/", HTTP_HOST=ADMIN_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("admin_return=", response["Location"])  # sent to central login, not into the dashboard
        self.assertNotEqual(urlsplit(response["Location"]).path, "/admin-portal/")
