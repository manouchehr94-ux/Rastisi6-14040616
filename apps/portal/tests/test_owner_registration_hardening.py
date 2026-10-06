"""Owner registration / signup hardening (audit/owner-registration-v1).

Covers: required & normalized registration name, registration vs. login form
separation, server-session-authoritative name, first-time-owner (not
first-time-User) store provisioning, ``new_store_registration_enabled``
enforcement (view + verify + service layer), OTP single-use under races,
provisioning guarantees, existing-identity matrix, and the onboarding handoff.

The ``ConcurrencyTests`` class uses real threads and therefore only runs on
PostgreSQL (SQLite cannot do concurrent writers); every other class, including
the deterministic "interleaved request" race tests, runs on any database.
"""

import logging
import threading
import unittest
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Warehouse
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.portal.forms import OwnerPhoneRequestForm, OwnerRegistrationRequestForm
from apps.portal.models import OwnerOtpChallenge, OwnerProfile, PlatformConfiguration
from apps.portal.services import (
    owner_auth_service,
    owner_otp_service,
    platform_config_service,
    provisioning_service,
    turnstile_service,
)
from apps.sms.models import SmsLog
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09121230001"
_NAME = "سارا احمدی"


class _OtpTestMixin:
    """Captures the real OTP code handed to the SMS layer (no monkeypatching of
    the generator), so every request gets a genuinely random code."""

    def setUp(self):
        super().setUp()
        cache.clear()  # OTP IP rate-limit counters are cache-backed
        # Data migrations may leave a pre-existing default Store; every count
        # below is about rows created *by the test*.
        self.base_store_ids = set(Store.objects.values_list("pk", flat=True))
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._fake_send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        return SmsSendResult(success=True, provider_ref_id="test")

    @property
    def last_code(self):
        return self.sent[-1]["code"]

    def register(self, name=_NAME, phone=_PHONE, client=None, **extra):
        client = client or self.client
        return client.post("/register/", {"full_name": name, "phone": phone, **extra}, HTTP_HOST=_HOST)

    def login_otp(self, phone=_PHONE, client=None):
        client = client or self.client
        return (client).post("/login/", {"phone": phone}, HTTP_HOST=_HOST)

    def verify(self, code=None, client=None, **extra):
        client = client or self.client
        return client.post(
            "/verify/", {"code": code if code is not None else self.last_code, **extra}, HTTP_HOST=_HOST,
        )

    def set_registration(self, enabled: bool):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.new_store_registration_enabled = enabled
        config.save()
        cache.clear()

    def stores(self):
        return Store.objects.exclude(pk__in=self.base_store_ids)

    def new_rows(self, model):
        if model is Store:
            return self.stores()
        return model.objects.exclude(store_id__in=self.base_store_ids)

    def owner_store_count(self, user):
        return StoreMembership.objects.filter(
            user=user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        ).count()


# ---------------------------------------------------------------------------
# 1. Registration name & form separation
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegistrationNameTests(_OtpTestMixin, TestCase):
    def assertRejected(self, response, field_error_id="id_full_name_error"):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="{field_error_id}"')
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertEqual(self.sent, [])
        self.assertNotIn("portal_otp_phone", self.client.session)

    def test_missing_name_is_rejected_beside_the_field(self):
        response = self.client.post("/register/", {"phone": _PHONE}, HTTP_HOST=_HOST)
        self.assertRejected(response)
        self.assertContains(response, "نام و نام خانوادگی را وارد کنید.")

    def test_empty_name_is_rejected(self):
        self.assertRejected(self.register(name=""))

    def test_whitespace_only_names_are_rejected(self):
        for blank in ("   ", "\t\n ", "  ", "‌‌", "​ ‏"):
            with self.subTest(blank=repr(blank)):
                self.assertRejected(self.register(name=blank))

    def test_too_short_or_letterless_names_are_rejected(self):
        for bad in ("ا", "12345", "!!!!", "۱۲۳"):
            with self.subTest(bad=bad):
                self.assertRejected(self.register(name=bad))

    def test_overlong_name_is_rejected_and_boundary_is_accepted(self):
        for too_long in ("a" * 101, "a" * 151, "س" * 5000):
            response = self.register(name=too_long)
            self.assertRejected(response)
            self.assertContains(response, "نام نباید بیشتر از 100 نویسه باشد")
            self.assertNotContains(response, "Ensure this value")
        self.assertEqual(self.register(name="a" * 100).status_code, 302)

    def test_persian_and_latin_names_are_stored_normalized(self):
        cases = [
            ("سارا احمدی", "سارا احمدی"),
            ("Sara Ahmadi", "Sara Ahmadi"),
            ("  Ali    Reza Karimi  ", "Ali Reza Karimi"),
            ("می‌ترا  رضایی", "می‌ترا رضایی"),  # ZWNJ (half-space) is preserved
            ("Sara سارا", "Sara سارا"),
        ]
        for index, (raw, expected) in enumerate(cases):
            phone = f"0912123{index:04d}"
            with self.subTest(raw=raw):
                client = Client()
                self.register(name=raw, phone=phone, client=client)
                self.verify(client=client)
                self.assertEqual(OwnerProfile.objects.get(phone=phone).full_name, expected)

    def test_name_survives_resend_and_is_saved_on_verification(self):
        self.register(name=_NAME)
        self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.sent), 2)
        self.verify()
        self.assertEqual(OwnerProfile.objects.get(phone=_PHONE).full_name, _NAME)

    def test_hidden_full_name_posted_to_verify_is_ignored(self):
        self.register(name="Real Name")
        self.verify(full_name="Attacker Chosen")
        self.assertEqual(OwnerProfile.objects.get(phone=_PHONE).full_name, "Real Name")

    def test_login_does_not_require_or_accept_a_name(self):
        self.assertNotIn("full_name", OwnerPhoneRequestForm().fields)
        self.assertIn("full_name", OwnerRegistrationRequestForm().fields)
        self.assertTrue(OwnerRegistrationRequestForm().fields["full_name"].required)
        response = self.login_otp()
        self.assertEqual(response.status_code, 302)
        self.verify(full_name="Ignored On Login")
        self.assertEqual(OwnerProfile.objects.get(phone=_PHONE).full_name, "")

    def test_a_login_request_clears_a_stale_registration_name(self):
        self.register(name="Stale Name")
        self.login_otp(phone="09121230099")
        self.verify()
        self.assertEqual(OwnerProfile.objects.get(phone="09121230099").full_name, "")

    def test_registration_without_a_session_name_restarts_registration(self):
        self.register()
        session = self.client.session
        session["portal_otp_full_name"] = ""
        session.save()
        response = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertRedirects(response, "/register/", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username=_PHONE).exists())


# ---------------------------------------------------------------------------
# 2. Phone input validation
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegistrationPhoneTests(_OtpTestMixin, TestCase):
    def test_every_accepted_spelling_yields_the_same_canonical_phone(self):
        spellings = [
            "09121230002", "۰۹۱۲۱۲۳۰۰۰۲", "+989121230002", "00989121230002",
            "9121230002", "0912 123 0002", "0912-123-0002", " 0912 123-0002 ",
        ]
        for raw in spellings:
            with self.subTest(raw=raw):
                cache.clear()
                OwnerOtpChallenge.objects.all().delete()
                response = self.register(phone=raw)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.client.session["portal_otp_phone"], "09121230002")
                self.assertEqual(OwnerOtpChallenge.objects.get().phone, "09121230002")

    def test_invalid_phones_are_rejected_beside_the_field_with_no_sms(self):
        bad = ["", "   ", "0912", "09121230", "0912123000200", "02112345678", "۰۲۱۱۲۳۴۵۶۷۸", "abc", "0812123000", "9" * 21, "0912123000x"]
        for raw in bad:
            with self.subTest(raw=raw):
                response = self.register(phone=raw)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_phone_error"')
                self.assertNotContains(response, "Ensure this value")
                self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_repeated_form_submission_never_yields_two_working_accounts(self):
        self.register()
        self.register()
        self.assertEqual(len(self.sent), 2)
        first, second = self.sent
        # Only the newest code works; the earlier one was superseded.
        self.assertEqual(self.verify(code=first["code"]).status_code, 200)
        self.assertEqual(self.verify(code=second["code"]).status_code, 302)
        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(phone=_PHONE).count(), 1)
        self.assertEqual(self.stores().count(), 1)


# ---------------------------------------------------------------------------
# 3. Fresh signup acceptance + provisioning guarantees
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class FreshSignupTests(_OtpTestMixin, TestCase):
    def test_fresh_signup_produces_the_complete_first_run_state(self):
        self.register()
        response = self.verify()

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get()
        self.assertEqual(user.username, _PHONE)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(OwnerProfile.objects.count(), 1)
        profile = OwnerProfile.objects.get()
        self.assertEqual((profile.user_id, profile.phone, profile.full_name), (user.pk, _PHONE, _NAME))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        self.assertEqual(self.stores().count(), 1)
        store = self.stores().get()
        self.assertEqual(store.name, "فروشگاه من")
        self.assertEqual(store.status, Store.Status.ACTIVE)
        self.assertTrue(store.platform_code)
        self.assertEqual(store.onboarding_stage, Store.OnboardingStage.IDENTITY)
        self.assertIsNone(store.onboarding_completed_at)

        membership = self.new_rows(StoreMembership).get()
        self.assertEqual(
            (membership.user_id, membership.store_id, membership.role, membership.status),
            (user.pk, store.pk, StoreMembership.Role.OWNER, StoreMembership.MembershipStatus.ACTIVE),
        )

        domain = StoreDomain.objects.get(store=store)
        self.assertEqual(domain.domain_type, StoreDomain.DomainType.GENERATED_TRIAL)
        self.assertTrue(domain.is_primary)
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)
        from django.conf import settings

        self.assertEqual(domain.hostname, f"{store.platform_code}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")

        self.assertEqual(ShopSettings.objects.filter(store=store).count(), 1)
        warehouse = Warehouse.objects.get(store=store)
        self.assertEqual((warehouse.code, warehouse.is_default, warehouse.is_active), ("main", True, True))

        self.assertRedirects(
            response, f"/app/stores/{store.public_id}/onboarding/", fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(response["Location"], HTTP_HOST=_HOST),
            f"/app/stores/{store.public_id}/onboarding/identity/",
        )

    def test_no_default_plan_configured_means_no_subscription_fail_open(self):
        self.register()
        self.verify()
        self.assertEqual(self.new_rows(StoreSubscription).count(), 0)

    @override_settings(RASTISI_DEFAULT_PLAN_CODE="trial")
    def test_default_trial_subscription_is_preserved_when_a_plan_is_configured(self):
        call_command("seed_default_plans", stdout=StringIO())
        self.register()
        self.verify()
        subscription = self.new_rows(StoreSubscription).get()
        self.assertEqual(subscription.store_id, self.stores().get().pk)
        self.assertEqual(subscription.status, StoreSubscription.Status.TRIALING)

    def test_a_failed_provisioning_leaves_no_partial_store(self):
        with patch.object(ShopSettings, "provision_for", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                user = User.objects.create_user(username="09120000999")
                provisioning_service.provision_trial_store(owner=user, name="x")
        for model in (Store, StoreMembership, StoreDomain, ShopSettings, Warehouse):
            self.assertEqual(self.new_rows(model).count(), 0, model.__name__)

    def test_provisioning_error_in_the_view_keeps_the_account_but_no_store_rows(self):
        self.register()
        with patch.object(
            provisioning_service, "_create_store_with_unique_platform_code",
            side_effect=provisioning_service.ProvisioningError("boom"),
        ):
            response = self.verify()
            follow = self.client.get(response["Location"], HTTP_HOST=_HOST)
        self.assertContains(follow, "ساخت فروشگاه آزمایشی کامل نشد")
        self.assertEqual(OwnerProfile.objects.count(), 1)
        self.assertIn("_auth_user_id", self.client.session)
        for model in (Store, StoreMembership, StoreDomain, ShopSettings, Warehouse):
            self.assertEqual(self.new_rows(model).count(), 0, model.__name__)

    def test_provision_initial_trial_store_is_idempotent(self):
        user = User.objects.create_user(username="09120000555")
        first, created_first = provisioning_service.provision_initial_trial_store(owner=user, name="فروشگاه من")
        second, created_second = provisioning_service.provision_initial_trial_store(owner=user, name="فروشگاه من")
        self.assertEqual((created_first, created_second), (True, False))
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.stores().count(), 1)


# ---------------------------------------------------------------------------
# 4. Existing-identity matrix
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ExistingIdentityTests(_OtpTestMixin, TestCase):
    def test_resolve_result_distinguishes_user_created_from_owner_created(self):
        brand_new = owner_auth_service.resolve_owner_identity_by_phone(phone="09120001001", full_name="A")
        self.assertEqual((brand_new.user_created, brand_new.owner_created), (True, True))

        customer_user = User.objects.create_user(username="09120001002", password="x")
        Customer.objects.create(user=customer_user, full_name="Cust", phone="09120001002")
        from_customer = owner_auth_service.resolve_owner_identity_by_phone(phone="09120001002", full_name="B")
        self.assertEqual((from_customer.user_created, from_customer.owner_created), (False, True))
        self.assertEqual(from_customer.user.pk, customer_user.pk)

        again = owner_auth_service.resolve_owner_identity_by_phone(phone="09120001002", full_name="C")
        self.assertEqual((again.user_created, again.owner_created), (False, False))

    def test_existing_customer_registering_as_owner_gets_the_first_owner_experience(self):
        customer_user = User.objects.create_user(username=_PHONE, password="customer-pass")
        customer = Customer.objects.create(
            user=customer_user, full_name="Customer Person", phone=_PHONE, city="Shiraz",
        )

        self.register(name="Owner Person")
        response = self.verify()

        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(user=customer_user).count(), 1)
        self.assertEqual(OwnerProfile.objects.get().full_name, "Owner Person")
        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(self.owner_store_count(customer_user), 1)
        self.assertIn("/onboarding/", response["Location"])
        # Customer data is untouched, and the customer's own password survives.
        customer.refresh_from_db()
        customer_user.refresh_from_db()
        self.assertEqual((customer.full_name, customer.city, customer.phone), ("Customer Person", "Shiraz", _PHONE))
        self.assertTrue(customer_user.check_password("customer-pass"))

    def test_existing_customer_via_login_otp_also_becomes_a_first_time_owner_once(self):
        customer_user = User.objects.create_user(username=_PHONE, password="customer-pass")
        Customer.objects.create(user=customer_user, full_name="Customer Person", phone=_PHONE)
        self.login_otp()
        self.verify()
        self.assertEqual(self.stores().count(), 1)

    def test_existing_owner_registering_again_gets_no_extra_store_and_keeps_their_name(self):
        self.register(name="First Name")
        self.verify()
        self.client.post("/logout/", HTTP_HOST=_HOST)
        store = self.stores().get()

        self.register(name="A Different Name")
        response = self.verify()

        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(OwnerProfile.objects.count(), 1)
        self.assertEqual(OwnerProfile.objects.get().full_name, "First Name")
        self.assertEqual(self.owner_store_count(User.objects.get()), 1)
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)
        self.assertEqual(self.stores().get().pk, store.pk)

    def test_existing_owner_login_never_provisions_a_store(self):
        user = User.objects.create_user(username=_PHONE)
        OwnerProfile.objects.create(user=user, phone=_PHONE, full_name="Has No Store")
        self.login_otp()
        response = self.verify()
        self.assertEqual(self.stores().count(), 0)
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)

    def test_customer_plus_owner_identity_stays_one_user_one_profile(self):
        user = User.objects.create_user(username=_PHONE, password="pw")
        Customer.objects.create(user=user, full_name="Both", phone=_PHONE)
        OwnerProfile.objects.create(user=user, phone=_PHONE, full_name="Both Owner")
        self.login_otp()
        self.verify()
        self.assertEqual((User.objects.count(), OwnerProfile.objects.count(), Customer.objects.count()), (1, 1, 1))
        self.assertEqual(self.stores().count(), 0)

    def test_legacy_email_owner_is_not_merged_and_a_phoneless_profile_keeps_its_name(self):
        email_owner = owner_auth_service.register_owner(
            full_name="Email Owner", email="legacy@example.com", password="a-very-strong-pass-1",
        )
        self.register(name="Phone Person")
        self.verify()
        email_owner.refresh_from_db()
        self.assertEqual(email_owner.owner_profile.full_name, "Email Owner")
        self.assertIsNone(email_owner.owner_profile.phone)
        self.assertEqual(OwnerProfile.objects.count(), 2)  # two distinct identities, no silent merge

        # A phone-named User whose OwnerProfile has no phone yet: the phone is
        # attached, the stored name is NOT overwritten, and no store appears.
        legacy_user = User.objects.create_user(username="09120002001")
        OwnerProfile.objects.create(user=legacy_user, phone=None, full_name="Legacy Name")
        result = owner_auth_service.resolve_owner_identity_by_phone(phone="09120002001", full_name="New Name")
        self.assertEqual((result.user_created, result.owner_created), (False, False))
        legacy_user.owner_profile.refresh_from_db()
        self.assertEqual((legacy_user.owner_profile.phone, legacy_user.owner_profile.full_name), ("09120002001", "Legacy Name"))

    def test_inactive_user_cannot_log_in_or_get_anything_created(self):
        User.objects.create_user(username=_PHONE, is_active=False)
        self.register()
        response = self.verify()
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual((OwnerProfile.objects.count(), self.stores().count()), (0, 0))
        follow = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(follow, "ورود با این شماره امکان‌پذیر نیست")

    def test_inactive_existing_owner_cannot_log_in(self):
        user = User.objects.create_user(username=_PHONE, is_active=False)
        OwnerProfile.objects.create(user=user, phone=_PHONE, full_name="Inactive Owner")
        self.login_otp()
        self.verify()
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.stores().count(), 0)


# ---------------------------------------------------------------------------
# 5. /login/ with a never-seen phone (documented, intentionally unchanged)
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class LoginWithUnknownPhoneTests(_OtpTestMixin, TestCase):
    def test_new_phone_via_login_creates_an_owner_and_one_trial_store(self):
        """Product behavior kept as-is and pinned here: a never-seen phone
        submitted to /login/ becomes an Owner (empty name) with one trial
        Store (also covered by test_owner_otp)."""
        self.login_otp()
        response = self.verify()
        self.assertEqual(OwnerProfile.objects.get().full_name, "")
        self.assertEqual(self.stores().count(), 1)
        self.assertIn("/onboarding/", response["Location"])

    def test_login_page_truthfully_says_otp_can_create_an_account(self):
        page = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(page, "حسابی ندارید، بعد از تأیید کد، حساب مالک و فروشگاه آزمایشی شما ساخته می‌شود")
        self.assertContains(page, "/register/")

    def test_login_page_does_not_promise_account_creation_when_registration_is_closed(self):
        self.set_registration(False)
        page = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertNotContains(page, "حساب مالک و فروشگاه آزمایشی شما ساخته می‌شود")
        self.assertContains(page, "ساخت حساب جدید فعلاً در دسترس نیست")


# ---------------------------------------------------------------------------
# 6. Registration availability policy
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RegistrationPolicyTests(_OtpTestMixin, TestCase):
    def test_enabled_by_default(self):
        self.assertTrue(platform_config_service.is_new_store_registration_enabled())

    def test_closed_register_page_says_so_clearly_and_has_no_signup_form(self):
        self.set_registration(False)
        page = self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        self.assertContains(page, "ورود شما و دسترسی به فروشگاه‌های موجودتان تغییری نکرده است")
        self.assertNotContains(page, 'name="full_name"')
        self.assertNotContains(page, 'name="phone"')
        self.assertContains(page, 'href="/login/"')

    def test_closed_register_post_issues_no_otp_and_never_reaches_turnstile_or_sms(self):
        self.set_registration(False)
        with patch.object(turnstile_service, "verify_request") as turnstile:
            response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        turnstile.assert_not_called()
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertNotIn("portal_otp_phone", self.client.session)

    def test_challenge_issued_while_open_cannot_bypass_a_later_close(self):
        self.register()
        self.set_registration(False)
        response = self.verify()
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual((User.objects.count(), OwnerProfile.objects.count(), self.stores().count()), (0, 0, 0))

    def test_resend_after_close_issues_nothing_for_registration(self):
        self.register()
        self.set_registration(False)
        response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertRedirects(response, "/register/", fetch_redirect_response=False)
        self.assertEqual(len(self.sent), 1)

    def test_closed_policy_does_not_lock_existing_owners_out_of_login_or_their_stores(self):
        self.register(name="Existing Owner")
        self.verify()
        store = self.stores().get()
        self.client.post("/logout/", HTTP_HOST=_HOST)

        self.set_registration(False)
        self.login_otp()
        response = self.verify()
        self.assertRedirects(response, "/app/", fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)
        page = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertContains(page, store.name)
        self.assertEqual(self.stores().count(), 1)

    def test_closed_policy_blocks_a_brand_new_phone_on_login_without_enumeration(self):
        self.set_registration(False)
        response = self.login_otp(phone="09125550000")
        # The OTP is issued exactly as for any phone: no account-existence oracle.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.sent), 1)
        verified = self.verify()
        self.assertRedirects(verified, "/login/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual((User.objects.count(), OwnerProfile.objects.count(), self.stores().count()), (0, 0, 0))
        self.assertContains(self.client.get("/login/", HTTP_HOST=_HOST), "ساخت فروشگاه تازه موقتاً در دسترس نیست")

    def test_closed_policy_does_not_turn_a_customer_only_phone_into_an_owner(self):
        customer_user = User.objects.create_user(username=_PHONE, password="pw")
        Customer.objects.create(user=customer_user, full_name="Only Customer", phone=_PHONE)
        self.set_registration(False)
        self.login_otp()
        self.verify()
        self.assertEqual((OwnerProfile.objects.count(), self.stores().count()), (0, 0))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_service_layer_refuses_store_creation_for_direct_callers(self):
        owner = User.objects.create_user(username="09120003001")
        self.set_registration(False)
        with self.assertRaises(provisioning_service.RegistrationClosedError):
            provisioning_service.provision_trial_store(owner=owner, name="Direct")
        with self.assertRaises(provisioning_service.RegistrationClosedError):
            provisioning_service.provision_initial_trial_store(owner=owner, name="Direct")
        self.assertEqual((self.stores().count(), self.new_rows(StoreMembership).count()), (0, 0))
        # …and re-opening restores service behaviour with no other change.
        self.set_registration(True)
        provisioning_service.provision_trial_store(owner=owner, name="Direct")
        self.assertEqual(self.stores().count(), 1)

    def test_existing_owner_cannot_create_an_additional_store_while_closed(self):
        owner = User.objects.create_user(username="09120003002")
        provisioning_service.provision_trial_store(owner=owner, name="Old Store")
        self.client.force_login(owner)
        self.set_registration(False)
        self.client.get("/app/stores/new/", HTTP_HOST=_HOST)
        token = self.client.session["portal_store_create_token"]
        response = self.client.post(
            "/app/stores/new/", {"name": "Second", "submission_token": token}, HTTP_HOST=_HOST, follow=True,
        )
        self.assertContains(response, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        self.assertEqual(self.stores().count(), 1)
        self.assertContains(self.client.get("/app/", HTTP_HOST=_HOST), "Old Store")

    def test_policy_read_is_never_served_from_a_stale_cache(self):
        platform_config_service.get_platform_configuration()  # prime the 5-minute cache
        PlatformConfiguration.objects.filter(pk=1).update(new_store_registration_enabled=False)
        self.assertFalse(platform_config_service.is_new_store_registration_enabled())

    def test_ownership_transfer_identity_creation_is_not_affected_by_the_policy(self):
        self.set_registration(False)
        user, owner_created = owner_auth_service.get_or_create_owner_by_phone(phone="09120003003")
        self.assertTrue(owner_created)
        self.assertEqual(self.stores().count(), 0)

    def test_maintenance_mode_is_not_enforced_by_signup_today(self):
        """Documents reality: ``maintenance_mode_enabled`` is only a stored
        flag (help text promises more) — nothing reads it. If it is ever
        enforced this test must be revisited deliberately."""
        PlatformConfiguration.objects.update_or_create(pk=1, defaults={"maintenance_mode_enabled": True})
        cache.clear()
        self.register()
        response = self.verify()
        self.assertIn("/onboarding/", response["Location"])


# ---------------------------------------------------------------------------
# 7. OTP behaviour, limits, failures, secrecy
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OtpVerificationTests(_OtpTestMixin, TestCase):
    def test_correct_code_succeeds_once_and_immediate_replay_fails(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        code = self.last_code
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=code))
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=code))
        self.assertIs(
            owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=code),
            owner_otp_service.OtpCheckResult.EXPIRED,
        )

    def test_interleaved_double_verification_consumes_the_challenge_exactly_once(self):
        """Deterministic race: while request #1 is mid-flight (after it read the
        challenge and reserved an attempt, during the slow hash check) request
        #2 runs to completion. Only one may succeed — on any database."""
        owner_otp_service.request_otp(phone=_PHONE, purpose="register", client_ip="1.1.1.1")
        code = self.last_code
        results = {}
        real_check_password = owner_otp_service.check_password
        state = {"nested": False}

        def racing_check_password(raw, encoded):
            outcome = real_check_password(raw, encoded)
            if not state["nested"]:
                state["nested"] = True
                results["second"] = owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=code)
            return outcome

        with patch.object(owner_otp_service, "check_password", racing_check_password):
            results["first"] = owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=code)

        self.assertEqual(sorted(results.values()), [False, True])
        self.assertEqual(OwnerOtpChallenge.objects.filter(consumed_at__isnull=False).count(), 1)

    def test_a_superseded_code_is_dead_and_cannot_resurface_after_the_newer_one_is_used(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        old_code = self.last_code
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        new_code = self.last_code
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=old_code))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=new_code))
        # The old code must not become "the latest active" once the new one is consumed.
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=old_code))
        self.assertEqual(OwnerOtpChallenge.objects.filter(consumed_at__isnull=True, expires_at__gt=timezone.now()).count(), 0)

    def test_consuming_the_newest_code_invalidates_every_outstanding_challenge(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        old_code = self.last_code
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        # Force the older challenge back to "active" (as if supersession had
        # not happened) — consuming the newest must still kill it.
        old = OwnerOtpChallenge.objects.order_by("created_at").first()
        OwnerOtpChallenge.objects.filter(pk=old.pk).update(expires_at=timezone.now() + timedelta(minutes=2))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=self.last_code))
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=old_code))

    def test_results_for_wrong_expired_and_locked_codes(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        code = self.last_code
        wrong = "000000" if code != "000000" else "111111"
        self.assertIs(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=wrong), owner_otp_service.OtpCheckResult.INVALID)

        for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS - 1):
            owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=wrong)
        challenge = OwnerOtpChallenge.objects.get()
        self.assertEqual(challenge.attempt_count, owner_otp_service.MAX_VERIFY_ATTEMPTS)
        # The correct code no longer works once the attempt budget is spent.
        self.assertIs(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=code), owner_otp_service.OtpCheckResult.TOO_MANY_ATTEMPTS)
        self.assertEqual(OwnerOtpChallenge.objects.get().attempt_count, owner_otp_service.MAX_VERIFY_ATTEMPTS)
        self.assertIsNone(OwnerOtpChallenge.objects.get().consumed_at)

    def test_the_last_permitted_attempt_can_still_succeed(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        code = self.last_code
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS - 1):
            owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=wrong)
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=code))

    def test_expired_code_is_rejected(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        OwnerOtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIs(
            owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=self.last_code),
            owner_otp_service.OtpCheckResult.EXPIRED,
        )

    def test_a_code_for_one_purpose_never_verifies_another(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=self.last_code))
        self.assertFalse(owner_otp_service.verify_otp(phone="09129999999", purpose="login", code=self.last_code))

    def test_resend_timing_is_informational(self):
        self.assertEqual(owner_otp_service.resend_timing(phone=_PHONE, purpose="login"), {"expires_in": 0, "resend_in": 0})
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        timing = owner_otp_service.resend_timing(phone=_PHONE, purpose="login")
        self.assertTrue(0 < timing["expires_in"] <= owner_otp_service.OTP_TTL_SECONDS)
        self.assertTrue(0 < timing["resend_in"] <= owner_otp_service.RESEND_UX_COOLDOWN_SECONDS)

    # --- view level -------------------------------------------------------

    def test_wrong_code_shows_the_error_beside_the_code_field(self):
        self.register()
        wrong = "000000" if self.last_code != "000000" else "111111"
        response = self.verify(code=wrong)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_code_error"')
        self.assertContains(response, "کد واردشده درست نیست")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_expired_code_message_at_the_view(self):
        self.register()
        OwnerOtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.verify()
        self.assertContains(response, "این کد منقضی یا قبلاً استفاده شده است")
        # One message only: the validity hint is hidden when the error already says so.
        self.assertNotContains(response, 'id="id_code_hint"')

    def test_locked_code_message_at_the_view(self):
        self.register()
        wrong = "000000" if self.last_code != "000000" else "111111"
        for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS):
            self.verify(code=wrong)
        response = self.verify()
        self.assertContains(response, "تعداد تلاش‌های این کد به حد مجاز رسید")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_persian_digits_are_accepted_as_the_code(self):
        self.register()
        persian = self.last_code.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        self.assertEqual(self.verify(code=persian).status_code, 302)

    def test_malformed_codes_are_form_errors_not_attempts(self):
        self.register()
        for bad in ("", "12345", "1234567", "abcdef", "12 34"):
            with self.subTest(bad=bad):
                response = self.verify(code=bad)
                self.assertEqual(response.status_code, 200)
        self.assertEqual(OwnerOtpChallenge.objects.get().attempt_count, 0)

    def test_replaying_the_successful_post_never_creates_a_second_store(self):
        self.register()
        code = self.last_code
        self.verify(code=code)
        self.assertEqual(self.stores().count(), 1)
        replay = self.verify(code=code)  # back-button / double submit
        self.assertEqual(replay.status_code, 302)
        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(self.new_rows(StoreMembership).count(), 1)
        # A reload of the verify page after success has nothing to verify.
        self.assertEqual(self.client.get("/verify/", HTTP_HOST=_HOST).status_code, 302)

    def test_phone_request_limit_blocks_the_fourth_code_with_no_sms(self):
        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW):
            self.assertEqual(self.register().status_code, 302)
        sent_before = len(self.sent)
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تعداد درخواست کد برای این شماره بیش از حد مجاز است")
        self.assertEqual(len(self.sent), sent_before)

    def test_ip_request_limit_blocks_further_codes_from_the_same_ip(self):
        for index in range(owner_otp_service.IP_MAX_REQUESTS):
            owner_otp_service.request_otp(phone=f"0912000{index:04d}", purpose="register", client_ip="8.8.8.8")
        with self.assertRaises(owner_otp_service.OtpRateLimitError):
            owner_otp_service.request_otp(phone="09120009999", purpose="register", client_ip="8.8.8.8")
        owner_otp_service.request_otp(phone="09120009998", purpose="register", client_ip="8.8.4.4")

    def test_failed_deliveries_do_not_consume_the_successful_issuance_quota(self):
        """Documented policy: only delivered codes (plus in-flight attempts)
        count toward the per-phone budget; a failed delivery frees its slot."""
        failure = SmsSendResult(success=False, error_message="provider down")
        with patch.object(owner_otp_service, "send_platform_otp", return_value=failure):
            for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW + 2):
                with self.assertRaises(owner_otp_service.OtpDeliveryError):
                    owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        with self.assertRaises(owner_otp_service.OtpRateLimitError) as caught:
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        self.assertNotIsInstance(caught.exception, owner_otp_service.OtpDeliveryError)
        self.assertEqual(OwnerOtpChallenge.objects.count(), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)

    # --- in-flight issuance (deterministic: the SMS callback runs the interleaving) ---

    def _wrong(self, code):
        return "000000" if code != "000000" else "111111"

    def test_an_in_flight_challenge_is_invisible_to_verification_and_gets_no_attempts(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        old_code = self.last_code
        seen = {}

        def in_flight_send(*, to, code, purpose, expire_minutes, **_):
            pending = OwnerOtpChallenge.objects.order_by("-pk").first()
            seen["pending_marker"] = pending.expires_at
            seen["timing"] = owner_otp_service.resend_timing(phone=_PHONE, purpose="login")
            # Hammer verification while the new SMS has not been delivered yet.
            seen["guesses"] = [
                owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=self._wrong(old_code))
                for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS + 1)
            ]
            seen["undelivered_code_result"] = owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=code)
            seen["pending_attempts"] = OwnerOtpChallenge.objects.get(pk=pending.pk).attempt_count
            self.sent.append({"to": to, "code": code, "purpose": purpose})
            return SmsSendResult(success=True, provider_ref_id="x")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=in_flight_send):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertEqual(seen["pending_marker"], owner_otp_service.PENDING_EXPIRES_AT)
        # resend_timing describes the usable (old) code, not the reservation.
        self.assertTrue(0 < seen["timing"]["expires_in"] <= owner_otp_service.OTP_TTL_SECONDS)
        # The guesses landed on the OLD challenge (5 wrong, then locked)…
        OtpResult = owner_otp_service.OtpCheckResult
        self.assertEqual(seen["guesses"], [OtpResult.INVALID] * 5 + [OtpResult.TOO_MANY_ATTEMPTS])
        # …the undelivered new code did not verify, and its attempt counter is untouched.
        self.assertIsNot(seen["undelivered_code_result"], OtpResult.OK)
        self.assertEqual(seen["pending_attempts"], 0)
        # Once delivered it is fully usable (it supersedes the locked old code).
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=self.last_code))

    def test_the_old_code_stays_valid_while_a_resend_is_in_flight_and_dies_only_after_delivery(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        old_code = self.last_code
        old_row = OwnerOtpChallenge.objects.get()
        states = {}

        def in_flight_send(*, to, code, purpose, expire_minutes, **_):
            old_row.refresh_from_db()
            states["old_active_in_flight"] = old_row.expires_at > timezone.now()
            self.sent.append({"to": to, "code": code, "purpose": purpose})
            return SmsSendResult(success=True, provider_ref_id="x")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=in_flight_send):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertTrue(states["old_active_in_flight"])
        old_row.refresh_from_db()
        new_row = OwnerOtpChallenge.objects.order_by("-pk").first()
        self.assertLessEqual(old_row.expires_at, timezone.now())  # superseded after success
        self.assertGreater(new_row.expires_at, timezone.now())  # activated with a fresh TTL
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=old_code))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=self.last_code))

    def test_a_failed_in_flight_resend_never_disturbs_the_previous_code(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        old_code = self.last_code
        before = OwnerOtpChallenge.objects.get()
        timings = []

        guesses = []

        def failing_send(*, to, code, purpose, expire_minutes, **_):
            timings.append(owner_otp_service.resend_timing(phone=_PHONE, purpose="login")["expires_in"])
            # During the in-flight window a guess is judged against the OLD code.
            guesses.append(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=self._wrong(old_code)))
            return SmsSendResult(success=False, error_message="down")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=failing_send):
            with self.assertRaises(owner_otp_service.OtpDeliveryError):
                owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertTrue(all(value > 0 for value in timings))  # usable during the in-flight window
        self.assertEqual(guesses, [owner_otp_service.OtpCheckResult.INVALID])
        after = OwnerOtpChallenge.objects.get()  # reservation row was removed; the old one remains
        self.assertEqual((after.pk, after.expires_at, after.attempt_count), (before.pk, before.expires_at, 1))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=old_code))

    def test_a_provider_crash_releases_the_reserved_slot(self):
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_an_older_request_finishing_after_a_newer_one_does_not_take_over(self):
        """A is admitted first but its delivery finishes last (B completes inside A's SMS call)."""
        codes = {}

        def send(*, to, code, purpose, expire_minutes, **_):
            if "A" not in codes:
                codes["A"] = code
                owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="2.2.2.2")  # B, nested
                return SmsSendResult(success=True, provider_ref_id="A")
            codes["B"] = code
            return SmsSendResult(success=True, provider_ref_id="B")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=send):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["A"]))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["B"]))
        # …and A cannot resurface after B was consumed.
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["A"]))
        self.assertEqual(OwnerOtpChallenge.objects.count(), 2)

    def test_a_newer_request_that_fails_does_not_destroy_the_older_successful_code(self):
        codes = {}

        def send(*, to, code, purpose, expire_minutes, **_):
            if "A" not in codes:
                codes["A"] = code
                with self.assertRaises(owner_otp_service.OtpDeliveryError):
                    owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="2.2.2.2")  # B fails
                return SmsSendResult(success=True, provider_ref_id="A")
            return SmsSendResult(success=False, error_message="down")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=send):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertEqual(OwnerOtpChallenge.objects.count(), 1)
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["A"]))

    def test_a_late_older_request_cannot_activate_after_the_newer_code_was_consumed(self):
        codes = {}

        def send(*, to, code, purpose, expire_minutes, **_):
            if "A" not in codes:
                codes["A"] = code
                owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="2.2.2.2")  # B delivered
                self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["B"]))
                return SmsSendResult(success=True, provider_ref_id="A")  # A finishes after B was used
            codes["B"] = code
            return SmsSendResult(success=True, provider_ref_id="B")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=send):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")

        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=codes["A"]))

    def test_provider_failure_shows_a_controlled_error_and_leaves_no_challenge(self):
        with patch.object(
            owner_otp_service, "send_platform_otp",
            return_value=SmsSendResult(success=False, error_message="provider down"),
        ):
            response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ارسال کد تأیید موقتاً انجام نشد")
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertNotIn("portal_otp_phone", self.client.session)

    def test_a_failed_resend_does_not_invalidate_the_previous_working_code(self):
        self.register()
        first_code = self.last_code
        with patch.object(
            owner_otp_service, "send_platform_otp",
            return_value=SmsSendResult(success=False, error_message="provider down"),
        ):
            self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(self.verify(code=first_code).status_code, 302)

    @override_settings(
        TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="1x00000000000000000000AA",
        TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    )
    def test_turnstile_failure_blocks_registration_before_any_sms(self):
        failure = turnstile_service.TurnstileValidationResult(False, "missing-token")
        with patch.object(turnstile_service, "verify_request", return_value=failure):
            response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    @override_settings(
        TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="1x00000000000000000000AA",
        TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    )
    def test_resend_works_with_turnstile_enabled_and_is_bound_to_the_session(self):
        """Regression: the resend form used to POST to /register/ without a
        Turnstile token, so with Turnstile enabled resend always failed."""
        ok = turnstile_service.TurnstileValidationResult(True)
        with patch.object(turnstile_service, "verify_request", return_value=ok) as verify_request:
            self.register()
            self.assertEqual(verify_request.call_count, 1)
            response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
            self.assertEqual(verify_request.call_count, 1)  # resend is not a new Turnstile gate
        self.assertRedirects(response, "/verify/", fetch_redirect_response=False)
        self.assertEqual(len(self.sent), 2)
        page = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(page, "کد جدید ارسال شد.")

    def test_resend_rate_limit_is_enforced_by_the_backend_and_flashed_once(self):
        self.register()
        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW - 1):
            self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        sent_before = len(self.sent)
        self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.sent), sent_before)
        page = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(page, "تعداد درخواست کد برای این شماره بیش از حد مجاز است")
        self.assertNotContains(self.client.get("/verify/", HTTP_HOST=_HOST), "تعداد درخواست کد برای این شماره")

    def test_resend_requires_post_a_session_and_csrf(self):
        self.assertEqual(self.client.get("/verify/resend/", HTTP_HOST=_HOST).status_code, 405)
        self.assertRedirects(
            self.client.post("/verify/resend/", HTTP_HOST=_HOST), "/login/", fetch_redirect_response=False,
        )
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post("/verify/resend/", HTTP_HOST=_HOST).status_code, 403)
        self.assertEqual(strict.post("/register/", {"full_name": _NAME, "phone": _PHONE}, HTTP_HOST=_HOST).status_code, 403)
        self.assertEqual(strict.post("/verify/", {"code": "123456"}, HTTP_HOST=_HOST).status_code, 403)
        self.assertEqual(self.sent, [])

    def test_stale_verify_page_for_a_different_phone_is_refused(self):
        self.register()
        response = self.client.post("/verify/", {"phone": "09129998888", "code": self.last_code}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "صفحه را دوباره باز کنید")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_otp_is_never_stored_or_logged_in_plaintext(self):
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _Capture(level=logging.DEBUG)
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            self.register()
            code = self.last_code
            self.verify(code="000000" if code != "000000" else "111111")
            self.verify(code=code)
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)

        challenge = OwnerOtpChallenge.objects.get()
        self.assertNotIn(code, challenge.code_hash)
        self.assertNotRegex(challenge.code_hash, r"^\d{6}$")
        self.assertFalse([m for m in records if code in m], "OTP leaked into logs")
        for log in SmsLog.objects.all():
            self.assertNotIn(code, log.message)
            self.assertNotIn(code, log.error_message)


# ---------------------------------------------------------------------------
# 8. Onboarding handoff
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OnboardingHandoffTests(_OtpTestMixin, TestCase):
    def test_signup_walks_the_whole_first_run_wizard_and_back_or_reload_never_adds_a_store(self):
        self.register()
        self.verify()
        store = self.stores().get()
        base = f"/app/stores/{store.public_id}/onboarding"

        for _ in range(2):  # reload / back-forward on the dispatcher
            self.assertRedirects(self.client.get(f"{base}/", HTTP_HOST=_HOST), f"{base}/identity/")
        self.assertRedirects(
            self.client.post(f"{base}/identity/", {"name": "فروشگاه سارا"}, HTTP_HOST=_HOST), f"{base}/industry/",
        )
        self.assertRedirects(
            self.client.post(f"{base}/industry/", {"action": "skip"}, HTTP_HOST=_HOST), f"{base}/branding/",
        )
        self.assertRedirects(
            self.client.post(f"{base}/branding/", {"action": "skip"}, HTTP_HOST=_HOST), f"{base}/review/",
        )
        # Resubmitting an earlier stage after progress never rewinds or re-provisions.
        self.client.post(f"{base}/identity/", {"name": "فروشگاه سارا"}, HTTP_HOST=_HOST)
        store.refresh_from_db()
        self.assertEqual(store.onboarding_stage, Store.OnboardingStage.REVIEW)
        self.client.post(f"{base}/review/", {}, HTTP_HOST=_HOST)
        self.client.post(f"{base}/review/", {}, HTTP_HOST=_HOST)  # double submit of the final step

        store.refresh_from_db()
        self.assertIsNotNone(store.onboarding_completed_at)
        self.assertEqual(store.name, "فروشگاه سارا")
        self.assertEqual((self.stores().count(), self.new_rows(StoreMembership).count()), (1, 1))

        # Replaying the OTP POST at any point after signup cannot provision again.
        self.verify(code="123456")
        self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertEqual(self.stores().count(), 1)

    def test_another_owner_cannot_open_the_new_owners_onboarding(self):
        self.register()
        self.verify()
        store = self.stores().get()
        intruder = User.objects.create_user(username="09120004444")
        OwnerProfile.objects.create(user=intruder, phone="09120004444", full_name="Intruder")
        other = Client()
        other.force_login(intruder)
        response = other.get(f"/app/stores/{store.public_id}/onboarding/identity/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_an_already_authenticated_visitor_is_sent_away_from_register(self):
        self.register()
        self.verify()
        self.assertRedirects(self.client.get("/register/", HTTP_HOST=_HOST), "/app/", fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# 9. Pages render the purpose-aware UX
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class AuthPageContentTests(_OtpTestMixin, TestCase):
    def test_register_page_fields_are_mobile_friendly_and_accessible(self):
        page = self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertContains(page, 'autocomplete="name"')
        self.assertContains(page, 'autocomplete="tel"')
        self.assertContains(page, 'inputmode="tel"')
        self.assertContains(page, 'placeholder="0912 123 4567"')
        self.assertContains(page, 'aria-describedby="id_phone_hint"')
        self.assertContains(page, "required")
        self.assertContains(page, "r-auth-shell--form-first")
        self.assertContains(page, "auth-forms.js")

    def test_register_page_marks_field_errors_for_assistive_tech(self):
        page = self.client.post("/register/", {"full_name": "", "phone": "x"}, HTTP_HOST=_HOST)
        self.assertContains(page, 'aria-invalid="true"')
        self.assertContains(page, "id_full_name_error")
        self.assertContains(page, "id_phone_error")

    def test_verify_page_is_purpose_aware(self):
        self.register()
        registration = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(registration, "تأیید شماره و ادامه")
        self.assertNotContains(registration, "تأیید و ورود")
        self.assertContains(registration, _PHONE)
        self.assertContains(registration, 'autocomplete="one-time-code"')
        self.assertContains(registration, 'inputmode="numeric"')
        self.assertContains(registration, 'data-otp-expires="')
        self.assertContains(registration, 'action="/verify/resend/"')
        self.assertContains(registration, 'href="/register/"')  # change number

        self.client.post("/logout/", HTTP_HOST=_HOST)
        self.login_otp(phone="09121230077")
        login = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(login, "تأیید و ورود")
        self.assertNotContains(login, "تأیید شماره و ادامه")
        self.assertContains(login, "09121230077")
        self.assertContains(login, 'href="/login/"')


# ---------------------------------------------------------------------------
# 10. Real concurrency (PostgreSQL only)
# ---------------------------------------------------------------------------


def _run_concurrently(count, target):
    """Run ``target(index)`` in ``count`` threads released together by a barrier.
    Returns the list of results/exceptions in index order."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(index):
        try:
            barrier.wait(timeout=30)
            results[index] = target(index)
        except Exception as exc:  # noqa: BLE001 — surfaced to the assertion
            results[index] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "real-thread race tests need PostgreSQL row locking")
@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ConcurrencyTests(_OtpTestMixin, TransactionTestCase):
    serialized_rollback = True

    def test_parallel_verification_of_one_challenge_succeeds_exactly_once(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="register", client_ip="1.1.1.1")
        code = self.last_code
        results = _run_concurrently(
            8, lambda _i: owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=code),
        )
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)
        self.assertEqual(OwnerOtpChallenge.objects.filter(consumed_at__isnull=False).count(), 1)

    def test_parallel_wrong_guesses_cannot_exceed_the_attempt_budget(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        code = self.last_code
        wrong = "000000" if code != "000000" else "111111"
        results = _run_concurrently(
            14, lambda _i: owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=wrong),
        )
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        invalid = [r for r in results if r is owner_otp_service.OtpCheckResult.INVALID]
        self.assertEqual(len(invalid), owner_otp_service.MAX_VERIFY_ATTEMPTS)  # the other 9 never even hashed
        self.assertEqual(OwnerOtpChallenge.objects.get().attempt_count, owner_otp_service.MAX_VERIFY_ATTEMPTS)
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="login", code=code))

    def test_concurrent_signup_verification_yields_one_profile_one_store(self):
        self.register()
        code = self.last_code
        template = self.client  # same server-side session, replayed by N "tabs"
        cookies = template.cookies
        clients = []
        for _ in range(8):
            c = Client()
            c.cookies = cookies.__class__()
            c.cookies.update(cookies)
            clients.append(c)

        results = _run_concurrently(
            8, lambda i: clients[i].post("/verify/", {"code": code}, HTTP_HOST=_HOST),
        )
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        winners = [r for r in results if r.status_code == 302 and "/onboarding/" in r["Location"]]
        self.assertEqual(len(winners), 1)
        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(phone=_PHONE).count(), 1)
        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(self.new_rows(StoreMembership).count(), 1)
        self.assertEqual(self.new_rows(StoreDomain).count(), 1)

    def test_concurrent_identity_resolution_and_provisioning_without_otp_still_yields_one_store(self):
        """Defence in depth: even if two callers got past OTP, the DB-level
        uniqueness + the user-row lock still produce one owner and one store."""

        def signup(_i):
            identity = owner_auth_service.resolve_owner_identity_by_phone(phone=_PHONE, full_name=_NAME)
            if identity.owner_created:
                provisioning_service.provision_initial_trial_store(owner=identity.user, name="فروشگاه من")
            return identity.owner_created

        results = _run_concurrently(8, signup)
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(phone=_PHONE).count(), 1)
        self.assertEqual(self.stores().count(), 1)

    def test_concurrent_initial_provisioning_for_one_owner_creates_one_store(self):
        owner = User.objects.create_user(username="09120007777")
        results = _run_concurrently(
            6, lambda _i: provisioning_service.provision_initial_trial_store(owner=owner, name="فروشگاه من")[1],
        )
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(StoreMembership.objects.filter(user=owner).count(), 1)

    def test_a_customer_first_owner_race_still_creates_exactly_one_owner_profile_and_store(self):
        customer_user = User.objects.create_user(username=_PHONE, password="pw")
        Customer.objects.create(user=customer_user, full_name="Customer", phone=_PHONE)

        def signup(_i):
            identity = owner_auth_service.resolve_owner_identity_by_phone(phone=_PHONE, full_name=_NAME)
            if identity.owner_created:
                provisioning_service.provision_initial_trial_store(owner=identity.user, name="فروشگاه من")
            return identity.owner_created

        results = _run_concurrently(6, signup)
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual((User.objects.count(), OwnerProfile.objects.count(), self.stores().count()), (1, 1, 1))


# ---------------------------------------------------------------------------
# 11. Per-phone request budget under real concurrency (PostgreSQL only)
# ---------------------------------------------------------------------------


def _issue(phone, purpose, index):
    """One OTP request → 'ok' | 'limit' | 'delivery' (or the unexpected exception)."""
    try:
        owner_otp_service.request_otp(phone=phone, purpose=purpose, client_ip=f"10.0.0.{index}")
    except owner_otp_service.OtpDeliveryError:
        return "delivery"
    except owner_otp_service.OtpRateLimitError:
        return "limit"
    return "ok"


@unittest.skipUnless(connection.vendor == "postgresql", "real-thread race tests need PostgreSQL advisory locks")
@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PhoneRequestBudgetConcurrencyTests(_OtpTestMixin, TransactionTestCase):
    serialized_rollback = True
    LIMIT = owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW

    def _newest_code(self):
        from django.contrib.auth.hashers import check_password

        newest = OwnerOtpChallenge.objects.order_by("-pk").first()
        return next(item["code"] for item in self.sent if check_password(item["code"], newest.code_hash))

    def test_a_burst_never_exceeds_the_phone_budget_and_only_the_newest_code_works(self):
        burst = 12
        self.assertEqual(self.LIMIT, 3)
        results = _run_concurrently(burst, lambda i: _issue(_PHONE, "register", i))

        self.assertEqual([r for r in results if r not in ("ok", "limit")], [])
        self.assertEqual(results.count("ok"), self.LIMIT)
        self.assertEqual(results.count("limit"), burst - self.LIMIT)  # controlled rate-limit error
        self.assertEqual(len(self.sent), self.LIMIT)  # at most 3 SMS were ever sent
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)

        newest = self._newest_code()
        older = [item["code"] for item in self.sent if item["code"] != newest]
        self.assertEqual(len(older), self.LIMIT - 1)
        for code in older:  # superseded codes are dead…
            self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=code))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=newest))
        for code in older:  # …and cannot resurface once the newest was consumed
            self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose="register", code=code))

    def test_in_flight_attempts_hold_their_slot_until_delivery_resolves(self):
        burst = 10
        release = threading.Event()
        inside = []
        lock = threading.Lock()

        def gated_send(*, to, code, purpose, expire_minutes, **_):
            with lock:
                inside.append(code)
                self.sent.append({"to": to, "code": code, "purpose": purpose})
            release.wait(60)
            return SmsSendResult(success=True, provider_ref_id="gated")

        results = [None] * burst

        def worker(i):
            try:
                results[i] = _issue(_PHONE, "login", i)
            except Exception as exc:  # noqa: BLE001
                results[i] = exc
            finally:
                connections.close_all()

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=gated_send):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(burst)]
            for thread in threads:
                thread.start()
            deadline = timezone.now() + timedelta(seconds=60)
            # Everyone beyond the budget is rejected while the admitted ones are still blocked in "SMS".
            while sum(1 for r in results if r == "limit") < burst - self.LIMIT and timezone.now() < deadline:
                threading.Event().wait(0.05)
            self.assertEqual(sum(1 for r in results if r == "limit"), burst - self.LIMIT)
            self.assertEqual(len(inside), self.LIMIT)
            self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)
            release.set()
            for thread in threads:
                thread.join(timeout=60)

        self.assertEqual([r for r in results if r not in ("ok", "limit")], [])
        self.assertEqual(results.count("ok"), self.LIMIT)
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)

    def test_provider_failures_never_burn_the_successful_quota_under_a_burst(self):
        failure = SmsSendResult(success=False, error_message="provider down")
        with patch.object(owner_otp_service, "send_platform_otp", return_value=failure):
            results = _run_concurrently(8, lambda i: _issue(_PHONE, "login", i))
        self.assertEqual([r for r in results if r not in ("delivery", "limit")], [])
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), 0)  # nothing counted

        # The whole budget is still available once the provider recovers…
        after = [_issue(_PHONE, "login", 100 + i) for i in range(self.LIMIT + 2)]
        self.assertEqual(after.count("ok"), self.LIMIT)
        self.assertEqual(after.count("limit"), 2)
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)

    def test_a_mixed_burst_counts_only_delivered_codes(self):
        calls = {"n": 0}
        lock = threading.Lock()

        def flaky_send(*, to, code, purpose, expire_minutes, **_):
            with lock:
                calls["n"] += 1
                n = calls["n"]
            if n <= 2:  # the first two SMS attempts fail
                return SmsSendResult(success=False, error_message="provider down")
            with lock:
                self.sent.append({"to": to, "code": code, "purpose": purpose})
            return SmsSendResult(success=True, provider_ref_id="ok")

        with patch.object(owner_otp_service, "send_platform_otp", side_effect=flaky_send):
            results = _run_concurrently(8, lambda i: _issue(_PHONE, "login", i))
            self.assertEqual([r for r in results if r not in ("ok", "delivery", "limit")], [])
            delivered = results.count("ok")
            self.assertLessEqual(delivered, self.LIMIT)
            self.assertEqual(len(self.sent), delivered)
            # Rows left == delivered codes only (failed attempts deleted their rows).
            self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), delivered)

            # Top up sequentially: the failed attempts did not consume quota, so
            # the total delivered always lands on exactly the budget.
            while _issue(_PHONE, "login", 200) == "ok":
                pass
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)
        self.assertEqual(len(self.sent), self.LIMIT)

    def test_the_database_lock_itself_closes_a_deliberately_widened_race_window(self):
        """Stretch the gap between "count" and "insert" (every count is followed
        by a pause) so that, without the advisory lock, every request would see
        an empty budget. The lock must still hold the line at exactly LIMIT."""
        real_count = owner_otp_service._recent_request_count

        def slow_count(phone, purpose):
            value = real_count(phone, purpose)
            threading.Event().wait(0.25)
            return value

        with patch.object(owner_otp_service, "_recent_request_count", side_effect=slow_count):
            results = _run_concurrently(10, lambda i: _issue(_PHONE, "register", i))

        self.assertEqual([r for r in results if r not in ("ok", "limit")], [])
        self.assertEqual(results.count("ok"), self.LIMIT)
        self.assertEqual(len(self.sent), self.LIMIT)
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), self.LIMIT)

    def test_different_phones_do_not_block_each_other(self):
        phones = [f"0912000{n:04d}" for n in range(4)]
        results = _run_concurrently(
            len(phones) * self.LIMIT, lambda i: _issue(phones[i % len(phones)], "register", i),
        )
        self.assertEqual(results.count("ok"), len(phones) * self.LIMIT)


# ---------------------------------------------------------------------------
# 12. In-flight SMS delivery (PostgreSQL real threads)
# ---------------------------------------------------------------------------


def _wait_until(predicate, timeout=60):
    deadline = timezone.now() + timedelta(seconds=timeout)
    while not predicate():
        if timezone.now() > deadline:
            raise AssertionError("timed out waiting for a concurrent condition")
        threading.Event().wait(0.02)


class _GatedSms:
    """SMS provider stand-in whose calls block until the test releases them,
    individually and in any order — a controllable in-flight window."""

    def __init__(self, test):
        self.test = test
        self.lock = threading.Lock()
        self.gates = {}      # code -> Event
        self.outcome = {}    # code -> success?

    def __call__(self, *, to, code, purpose, expire_minutes, **_):
        gate = threading.Event()
        with self.lock:
            self.gates[code] = gate
        gate.wait(60)
        ok = self.outcome.get(code, True)
        if ok:
            with self.lock:
                self.test.sent.append({"to": to, "code": code, "purpose": purpose})
            return SmsSendResult(success=True, provider_ref_id="gated")
        return SmsSendResult(success=False, error_message="provider down")

    @property
    def in_flight(self):
        with self.lock:
            return list(self.gates)

    def release(self, code, success=True):
        self.outcome[code] = success
        self.gates[code].set()


class _IssueThread(threading.Thread):
    def __init__(self, phone, purpose, index):
        super().__init__(daemon=True)
        self.args = (phone, purpose, index)
        self.result = None

    def run(self):
        try:
            self.result = _issue(*self.args)
        except Exception as exc:  # noqa: BLE001
            self.result = exc
        finally:
            connections.close_all()


@unittest.skipUnless(connection.vendor == "postgresql", "real-thread race tests need PostgreSQL advisory locks")
@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class InFlightDeliveryConcurrencyTests(_OtpTestMixin, TransactionTestCase):
    serialized_rollback = True
    PURPOSE = "login"

    def setUp(self):
        super().setUp()
        self.gated = _GatedSms(self)

    def _issue_delivered(self, index=1):
        """A normal, already-delivered code (the mixin's immediate fake SMS)."""
        owner_otp_service.request_otp(phone=_PHONE, purpose=self.PURPOSE, client_ip=f"9.9.9.{index}")
        return self.last_code

    def _start(self, index):
        thread = _IssueThread(_PHONE, self.PURPOSE, index)
        thread.start()
        return thread

    def _row(self, code):
        from django.contrib.auth.hashers import check_password

        for row in OwnerOtpChallenge.objects.filter(phone=_PHONE, purpose=self.PURPOSE):
            if check_password(code, row.code_hash):
                return row
        raise AssertionError("no challenge row for that code")

    def _state(self, code):
        row = self._row(code)
        if row.expires_at == owner_otp_service.PENDING_EXPIRES_AT:
            return "pending"
        if row.consumed_at is not None:
            return "consumed"
        return "active" if row.expires_at > timezone.now() else "dead"

    def _two_in_flight(self):
        """Two concurrent requests, both blocked in the provider. Returns (older, newer) codes by admission order."""
        first, second = self._start(1), self._start(2)
        _wait_until(lambda: len(self.gated.in_flight) == 2)
        codes = sorted(self.gated.in_flight, key=lambda c: self._row(c).pk)
        return (codes[0], codes[1]), (first, second)

    # 1 + 2
    def test_the_old_code_works_while_a_resend_is_in_flight_and_no_attempts_hit_the_new_one(self):
        old_code = self._issue_delivered()
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            resend = self._start(2)
            _wait_until(lambda: len(self.gated.in_flight) == 1)
            new_code = self.gated.in_flight[0]
            self.assertEqual(self._state(new_code), "pending")
            self.assertEqual(self._state(old_code), "active")
            wrong = "000000" if old_code != "000000" else "111111"
            for _ in range(3):
                self.assertIs(
                    owner_otp_service.check_otp(phone=_PHONE, purpose=self.PURPOSE, code=wrong),
                    owner_otp_service.OtpCheckResult.INVALID,
                )
            self.assertEqual(self._row(new_code).attempt_count, 0)   # nothing counted against the undelivered code
            self.assertEqual(self._row(old_code).attempt_count, 3)
            self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=old_code))
            self.gated.release(new_code)
            resend.join(60)
        self.assertEqual(resend.result, "ok")

    # 3
    def test_parallel_old_code_guesses_cannot_lock_an_undelivered_new_challenge(self):
        old_code = self._issue_delivered()
        wrong = "000000" if old_code != "000000" else "111111"
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            resend = self._start(2)
            _wait_until(lambda: len(self.gated.in_flight) == 1)
            new_code = self.gated.in_flight[0]
            results = _run_concurrently(
                8, lambda _i: owner_otp_service.check_otp(phone=_PHONE, purpose=self.PURPOSE, code=wrong),
            )
            self.assertEqual([r for r in results if isinstance(r, Exception)], [])
            self.assertEqual(
                results.count(owner_otp_service.OtpCheckResult.INVALID), owner_otp_service.MAX_VERIFY_ATTEMPTS,
            )
            self.assertEqual(self._row(new_code).attempt_count, 0)
            self.gated.release(new_code)
            resend.join(60)
        # The new code was never locked: it works as soon as it is delivered.
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=new_code))

    # 4
    def test_a_failed_in_flight_resend_leaves_the_previous_code_continuously_usable(self):
        old_code = self._issue_delivered()
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            resend = self._start(2)
            _wait_until(lambda: len(self.gated.in_flight) == 1)
            new_code = self.gated.in_flight[0]
            self.assertEqual(self._state(old_code), "active")
            wrong = "000000" if old_code != "000000" else "111111"
            self.assertIs(  # judged against the old code while the resend is in flight
                owner_otp_service.check_otp(phone=_PHONE, purpose=self.PURPOSE, code=wrong),
                owner_otp_service.OtpCheckResult.INVALID,
            )
            self.assertEqual((self._row(old_code).attempt_count, self._row(new_code).attempt_count), (1, 0))
            self.gated.release(new_code, success=False)
            resend.join(60)
        self.assertEqual(resend.result, "delivery")
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), 1)   # reservation gone
        self.assertEqual(self._state(old_code), "active")
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=old_code))

    # 5
    def test_a_successful_resend_supersedes_the_old_code_only_after_delivery(self):
        old_code = self._issue_delivered()
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            resend = self._start(2)
            _wait_until(lambda: len(self.gated.in_flight) == 1)
            new_code = self.gated.in_flight[0]
            self.assertEqual((self._state(old_code), self._state(new_code)), ("active", "pending"))
            timing = owner_otp_service.resend_timing(phone=_PHONE, purpose=self.PURPOSE)
            self.assertEqual(timing["expires_in"], int((self._row(old_code).expires_at - timezone.now()).total_seconds()))
            self.gated.release(new_code)
            resend.join(60)
        self.assertEqual(resend.result, "ok")
        self.assertEqual((self._state(old_code), self._state(new_code)), ("dead", "active"))
        self.assertGreater(self._row(new_code).expires_at, timezone.now() + timedelta(seconds=owner_otp_service.OTP_TTL_SECONDS - 10))
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=old_code))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=new_code))

    # 6a
    def test_provider_calls_finishing_out_of_order_newer_first_then_older(self):
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            (older, newer), (t1, t2) = self._two_in_flight()
            self.assertEqual((self._state(older), self._state(newer)), ("pending", "pending"))
            self.gated.release(newer)
            _wait_until(lambda: self._state(newer) == "active")
            self.assertEqual(self._state(older), "pending")   # still in flight, never verifiable
            self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=older))
            self.gated.release(older)
            t1.join(60), t2.join(60)
        self.assertEqual((t1.result, t2.result), ("ok", "ok"))
        # The late, older request did not take the newer one's place.
        self.assertEqual((self._state(older), self._state(newer)), ("dead", "active"))
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=older))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=newer))

    # 6b
    def test_provider_calls_finishing_in_order_older_first_then_newer(self):
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            (older, newer), (t1, t2) = self._two_in_flight()
            self.gated.release(older)
            _wait_until(lambda: self._state(older) == "active")
            self.assertEqual(self._state(newer), "pending")   # an older code may stay usable meanwhile
            self.gated.release(newer)
            t1.join(60), t2.join(60)
        self.assertEqual((self._state(older), self._state(newer)), ("dead", "active"))
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=older))
        self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=newer))

    # 6c
    def test_an_older_late_request_cannot_resurface_after_the_newer_code_was_used(self):
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
            (older, newer), (t1, t2) = self._two_in_flight()
            self.gated.release(newer)
            _wait_until(lambda: self._state(newer) == "active")
            self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=newer))
            self.gated.release(older)
            t1.join(60), t2.join(60)
        self.assertEqual(self._state(older), "dead")
        self.assertFalse(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=older))

    # 7
    def test_a_newer_failed_request_does_not_destroy_an_older_successful_code(self):
        for newer_finishes_first in (True, False):
            with self.subTest(newer_finishes_first=newer_finishes_first):
                OwnerOtpChallenge.objects.all().delete()
                cache.clear()
                self.gated = _GatedSms(self)
                with patch.object(owner_otp_service, "send_platform_otp", side_effect=self.gated):
                    (older, newer), (t1, t2) = self._two_in_flight()
                    if newer_finishes_first:
                        self.gated.release(newer, success=False)
                        # The failed reservation disappears; the older one is still in flight.
                        _wait_until(lambda: OwnerOtpChallenge.objects.filter(phone=_PHONE).count() == 1)
                        self.gated.release(older)
                    else:
                        self.gated.release(older)
                        _wait_until(lambda: self._state(older) == "active")
                        self.gated.release(newer, success=False)
                    t1.join(60), t2.join(60)
                results = sorted(r for r in (t1.result, t2.result))
                self.assertEqual(results, ["delivery", "ok"])
                self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), 1)
                self.assertTrue(owner_otp_service.verify_otp(phone=_PHONE, purpose=self.PURPOSE, code=older))

    # 8 — the burst budget is unchanged by the activation step
    def test_the_burst_budget_is_still_capped_at_three_with_activation(self):
        results = _run_concurrently(12, lambda i: _issue(_PHONE, self.PURPOSE, i))
        self.assertEqual(results.count("ok"), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)
        self.assertEqual(len(self.sent), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE).count(), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)
        active = [r for r in OwnerOtpChallenge.objects.filter(phone=_PHONE) if r.expires_at > timezone.now()]
        self.assertEqual(len(active), 1)   # exactly one usable code: the newest admitted
        self.assertEqual(active[0].pk, OwnerOtpChallenge.objects.filter(phone=_PHONE).order_by("-pk").first().pk)
