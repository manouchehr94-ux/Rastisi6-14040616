"""Merchant login regression: a single central credential endpoint.

The old /admin-portal/login/ page is a compatibility redirect, not an
independent password endpoint. A valid merchant host carries a signed
admin_return ticket; an ambiguous local dev host points at the central
login without guessing the store. Real unknown hosts still fail closed.
"""

from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services.handoff_service import decode_admin_return_token
from apps.stores.models import Store, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code

User = get_user_model()


def _grant_akhlaghi_membership(user, role=None):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"),
        user=user,
        role=role or StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


def _return_destination(response):
    params = parse_qs(urlsplit(response["Location"]).query)
    assert "admin_return" in params
    return decode_admin_return_token(params["admin_return"][0])


class AdminLoginRedirectTests(TestCase):
    def test_anonymous_dashboard_goes_to_central_login(self):
        response = self.client.get("/admin-portal/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("rastisi.localhost", response["Location"])
        self.assertEqual(_return_destination(response)[1], "/admin-portal/")

    def test_nested_admin_page_preserves_destination(self):
        response = self.client.get("/admin-portal/products/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_return_destination(response)[1], "/admin-portal/products/")

    def test_legacy_login_page_redirects_with_signed_return(self):
        response = self.client.get("/admin-portal/login/?next=/admin-portal/orders/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("rastisi.localhost", response["Location"])
        self.assertEqual(_return_destination(response)[1], "/admin-portal/orders/")

    @override_settings(DEBUG=True)
    def test_ambiguous_localhost_redirects_to_central_login(self):
        Store.objects.create(
            name="Second store", slug="second-admin-login-store",
            admin_subdomain="second-admin-login-store",
            platform_code=generate_unique_platform_code(),
            status=Store.Status.ACTIVE,
        )
        response = self.client.get(
            "/admin-portal/login/", HTTP_HOST="127.0.0.1:8000",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://rastisi.localhost:8000/login/")

    def test_unknown_merchant_host_still_returns_404(self):
        response = self.client.get(
            "/admin-portal/login/",
            HTTP_HOST="not-a-merchant.rastisi.localhost:8000",
        )
        self.assertEqual(response.status_code, 404)


class MerchantAccessTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="merchant_admin", password="StaffPass123!", is_staff=True,
        )
        _grant_akhlaghi_membership(self.staff_user)

    def test_member_can_access_dashboard(self):
        self.client.login(username="merchant_admin", password="StaffPass123!")
        self.assertEqual(self.client.get("/admin-portal/").status_code, 200)

    def test_authenticated_member_visiting_legacy_login_goes_to_dashboard(self):
        self.client.login(username="merchant_admin", password="StaffPass123!")
        response = self.client.get("/admin-portal/login/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin-portal/")

    def test_non_staff_member_can_access_dashboard(self):
        merchant = User.objects.create_user(
            username="real_owner_without_global_staff", password="StrongPass123!",
            is_staff=False,
        )
        _grant_akhlaghi_membership(merchant)
        self.client.force_login(merchant)
        self.assertEqual(self.client.get("/admin-portal/").status_code, 200)


class NonMemberDeniedTests(TestCase):
    def setUp(self):
        self.customer_user = User.objects.create_user(
            username="customer1", password="CustPass123!", is_staff=False,
        )

    def test_non_member_denied_dashboard(self):
        self.client.login(username="customer1", password="CustPass123!")
        response = self.client.get("/admin-portal/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/", response["Location"])

    def test_legacy_password_post_never_authenticates_directly(self):
        response = self.client.post("/admin-portal/login/", {
            "username": "customer1", "password": "CustPass123!",
            "next": "/admin-portal/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)


class LegacyLoginPostTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="manager", password="ManagerPass123!", is_staff=True,
        )
        _grant_akhlaghi_membership(self.member)

    def test_old_form_post_preserves_safe_destination_without_authentication(self):
        response = self.client.post("/admin-portal/login/", {
            "username": "manager", "password": "ManagerPass123!",
            "next": "/admin-portal/orders/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_return_destination(response)[1], "/admin-portal/orders/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_does_not_create_a_separate_login_path(self):
        response = self.client.post("/admin-portal/login/", {
            "username": "manager", "password": "wrong",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_untrusted_next_cannot_redirect_outside_admin(self):
        response = self.client.post("/admin-portal/login/", {
            "username": "manager", "password": "ManagerPass123!",
            "next": "https://evil.example.com/steal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(_return_destination(response)[1], "/admin-portal/")
