"""Storefront password login accepts mobile, username and email, Customer-scoped."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.customers.forms import LoginForm
from apps.customers.models import Customer
from apps.customers.services.auth_service import authenticate_customer_by_identifier

User = get_user_model()


class ThreeIdentifierCustomerLoginTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().post("/account/login/")
        self.user = User.objects.create_user(
            username="legacy_customer", password="StrongPass123!",
        )
        self.customer = Customer.objects.create(
            user=self.user, full_name="Customer",
            phone="09121231234", email="customer@example.com",
        )

    def _authenticate(self, identifier, password="StrongPass123!"):
        return authenticate_customer_by_identifier(
            self.request, identifier=identifier, password=password,
        )

    def test_login_form_accepts_username(self):
        form = LoginForm({
            "identifier": "legacy_customer", "password": "StrongPass123!",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["identifier"], "legacy_customer")

    def test_mobile_identifier_authenticates_customer(self):
        self.assertEqual(self._authenticate("09121231234"), self.user)

    def test_email_identifier_authenticates_customer(self):
        self.assertEqual(self._authenticate("CUSTOMER@example.com"), self.user)

    def test_legacy_username_identifier_authenticates_customer(self):
        self.assertEqual(self._authenticate("LEGACY_CUSTOMER"), self.user)

    def test_wrong_password_does_not_authenticate(self):
        self.assertIsNone(self._authenticate("legacy_customer", password="wrong"))

    def test_non_customer_username_cannot_use_storefront_login(self):
        User.objects.create_user(
            username="owner_only", password="StrongPass123!",
        )
        self.assertIsNone(self._authenticate("owner_only"))

    def test_ambiguous_case_insensitive_username_fails_closed(self):
        other = User.objects.create_user(
            username="LEGACY_CUSTOMER", password="StrongPass123!",
        )
        Customer.objects.create(
            user=other, full_name="Another Customer", phone="09121231235",
        )
        self.assertIsNone(self._authenticate("legacy_customer"))

    def test_duplicate_customer_email_fails_closed(self):
        other = User.objects.create_user(
            username="other_customer", password="StrongPass123!",
        )
        Customer.objects.create(
            user=other, full_name="Another Customer",
            phone="09121231236", email="CUSTOMER@example.com",
        )
        self.assertIsNone(self._authenticate("customer@example.com"))
