"""Canonical owner login: mobile, username or email with the same password flow."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.portal.models import OwnerProfile
from apps.stores.models import Store, StoreMembership

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["rastisi.localhost", "testserver"],
    RASTISI_PLATFORM_PRIMARY_HOST="rastisi.localhost",
)
class ThreeIdentifierOwnerLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.user = User.objects.create_user(
            username="legacy_merchant", email="merchant@example.com",
            password="StrongPass123!", is_staff=False,
        )
        OwnerProfile.objects.create(
            user=self.user, full_name="Merchant", phone="09123456780",
        )
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )

    def _login(self, identifier, password="StrongPass123!"):
        return self.client.post(
            "/login/password/",
            {"identifier": identifier, "password": password},
            HTTP_HOST="rastisi.localhost",
        )

    def test_same_account_accepts_username(self):
        response = self._login("LEGACY_MERCHANT")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_same_account_accepts_email_case_insensitively(self):
        response = self._login("MERCHANT@EXAMPLE.COM")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_same_account_accepts_mobile(self):
        response = self._login("09123456780")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_invalid_password_returns_generic_error_without_session(self):
        response = self._login("legacy_merchant", password="incorrect")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اطلاعات ورود صحیح نیست")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_non_owner_customer_username_cannot_use_merchant_login(self):
        stranger = User.objects.create_user(
            username="customer_only", password="StrongPass123!",
        )
        Customer.objects.create(
            user=stranger, full_name="Customer", phone="09123456781",
        )
        response = self._login("customer_only")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_legacy_phone_username_with_active_membership(self):
        legacy = User.objects.create_user(
            username="09123456782", password="StrongPass123!",
        )
        StoreMembership.objects.create(
            store=self.store, user=legacy,
            role=StoreMembership.Role.ORDER_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        response = self._login("09123456782")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), legacy.pk)

    def test_ambiguous_case_insensitive_usernames_fail_closed(self):
        other = User.objects.create_user(
            username="LEGACY_MERCHANT", password="StrongPass123!",
        )
        StoreMembership.objects.create(
            store=self.store, user=other,
            role=StoreMembership.Role.ORDER_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        response = self._login("legacy_merchant")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ambiguous_email_fails_closed(self):
        User.objects.create_user(
            username="different_merchant", email="MERCHANT@example.com",
            password="StrongPass123!",
        )
        response = self._login("merchant@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
