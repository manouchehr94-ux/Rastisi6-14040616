"""«اطلاعات حساب» — a NEW owner must set a REQUIRED email + password before any Owner/Store exists.

Journey: ``/register/`` (name + phone + Terms) → OTP → «اطلاعات حساب» (email, password, confirmation) → Owner + first
Store → onboarding. ``/login/`` with an unknown phone converges on the SAME step. The password is submitted only AFTER
the OTP succeeded, is validated/hashed by Django's canonical system inside the account-creation transaction, and is never
kept in the session, a pending row, a log, a URL or a hidden field.

Shared-identity rules (the repo deliberately shares ``User.username == phone`` with storefront customers): an existing
usable password or an existing email is NEVER overwritten; only what is missing is asked for/filled.
"""

import re
import threading
import unittest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings

from apps.portal.models import OwnerOtpChallenge, OwnerProfile, OwnerTermsAcceptance, PlatformConfiguration
from apps.portal.services import owner_auth_service, owner_otp_service
from apps.portal.terms import CURRENT_TERMS_VERSION, TERMS_ACCEPTANCE_REQUIRED_MESSAGE
from apps.portal.tests._owner_signup import GOOD_PASSWORD, age_otp_cooldown, email_for
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09128880001"
_NAME = "سارا احمدی"
URL = "/signup/complete/"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class _Base(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.base_store_ids = set(Store.objects.values_list("pk", flat=True))
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        return SmsSendResult(success=True, provider_ref_id="t")

    # -- helpers -------------------------------------------------------------
    def stores(self):
        return Store.objects.exclude(pk__in=self.base_store_ids)

    def register(self, phone=_PHONE, client=None, name=_NAME):
        client = client or self.client
        return client.post("/register/", {"full_name": name, "phone": phone, "accept_terms": "1"}, HTTP_HOST=_HOST)

    def login_otp(self, phone=_PHONE, client=None):
        return (client or self.client).post("/login/", {"phone": phone}, HTTP_HOST=_HOST)

    def verify(self, client=None):
        return (client or self.client).post("/verify/", {"code": self.sent[-1]["code"]}, HTTP_HOST=_HOST)

    def verified_via_register(self, phone=_PHONE, client=None):
        self.register(phone=phone, client=client)
        response = self.verify(client=client)
        self.assertEqual(response["Location"], URL)
        return response

    def verified_via_login(self, phone=_PHONE, client=None):
        self.login_otp(phone=phone, client=client)
        response = self.verify(client=client)
        self.assertEqual(response["Location"], URL)
        return response

    def submit(self, for_phone=_PHONE, client=None, **overrides):
        data = {
            "email": email_for(for_phone), "password": GOOD_PASSWORD, "password_confirm": GOOD_PASSWORD, **overrides,
        }
        data = {k: v for k, v in data.items() if v is not None}
        return (client or self.client).post(URL, data, HTTP_HOST=_HOST)

    def assertNothingCreated(self, phone=_PHONE):
        self.assertFalse(User.objects.filter(username=phone).exists())
        self.assertFalse(OwnerProfile.objects.filter(phone=phone).exists())
        self.assertEqual(self.stores().count(), 0)
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)

    def assertRejectedKeepingProof(self, response, text=None):
        self.assertEqual(response.status_code, 200)
        if text:
            self.assertContains(response, text)
        self.assertIn("portal_signup_pending", self.client.session)  # a form error never burns the OTP proof
        self.assertNothingCreated()


class RegisterJourneyTests(_Base):
    def test_the_new_owner_journey_end_to_end(self):
        # 1) phone + Terms + name → OTP. Nothing exists yet.
        response = self.register()
        self.assertEqual(response["Location"], "/verify/")
        self.assertNothingCreated()
        # 2) OTP proves the phone and goes to «اطلاعات حساب». STILL nothing exists, and nobody is logged in.
        response = self.verify()
        self.assertEqual(response["Location"], URL)
        self.assertNothingCreated()
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)
        # 3) the credential page
        page = self.client.get(URL, HTTP_HOST=_HOST)
        self.assertContains(page, "اطلاعات حساب")
        self.assertContains(page, "شماره موبایل شما تأیید شد")
        self.assertContains(page, _PHONE)
        self.assertContains(page, 'name="email"')
        self.assertContains(page, 'name="password"')
        self.assertContains(page, 'name="password_confirm"')
        self.assertContains(page, "ایمیل")
        self.assertContains(page, "تکرار رمز عبور")
        self.assertContains(page, 'id="id_password_hint"')  # the existing password-policy guidance
        self.assertNotContains(page, 'name="phone"')  # the phone is never a client field
        self.assertNotContains(page, 'id="id_accept_terms"')  # /register/ already captured the Terms server-side
        self.assertNotContains(page, 'name="full_name"')  # …and the name
        self.assertNothingCreated()
        # 4) credentials → account + first Store + onboarding
        response = self.submit(email="  Owner@Example.COM ")
        store = self.stores().get()
        self.assertRedirects(response, f"/app/stores/{store.public_id}/onboarding/", fetch_redirect_response=False)
        user = User.objects.get(username=_PHONE)
        self.assertEqual(user.email, "owner@example.com")  # trimmed + lower-cased
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(GOOD_PASSWORD))
        profile = OwnerProfile.objects.get(user=user)
        self.assertEqual((profile.phone, profile.full_name), (_PHONE, _NAME))
        self.assertEqual(StoreMembership.objects.filter(user=user, role=StoreMembership.Role.OWNER).count(), 1)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        row = OwnerTermsAcceptance.objects.get()
        self.assertEqual((row.user_id, row.terms_version, row.source), (
            user.pk, CURRENT_TERMS_VERSION, OwnerTermsAcceptance.Source.REGISTRATION,
        ))
        self.assertNotIn("portal_signup_pending", self.client.session)  # single use

    def test_password_login_and_otp_login_both_work_afterwards(self):
        self.verified_via_register()
        self.submit(email="Owner@Example.com")
        self.client.post("/logout/", HTTP_HOST=_HOST)
        cache.clear()
        for identifier in (_PHONE, "owner@example.com", "OWNER@EXAMPLE.COM"):
            with self.subTest(identifier=identifier):
                client = Client()
                response = client.post(
                    "/login/password/", {"identifier": identifier, "password": GOOD_PASSWORD}, HTTP_HOST=_HOST,
                )
                self.assertEqual(response["Location"], "/app/", identifier)
                self.assertIn("_auth_user_id", client.session)
        wrong = Client().post(
            "/login/password/", {"identifier": _PHONE, "password": GOOD_PASSWORD + "x"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(wrong.status_code, 200)
        # phone OTP login is unchanged and skips the credential step entirely
        age_otp_cooldown(_PHONE)
        client = Client()
        self.assertEqual(self.login_otp(client=client)["Location"], "/verify/")
        self.assertEqual(self.verify(client=client)["Location"], "/app/")

    def test_the_password_is_never_kept_in_the_session_or_any_pending_state(self):
        self.verified_via_register()
        self.submit(password="Another-Strong-Pass-55!", password_confirm="Another-Strong-Pass-55!", email="x@example.com")
        dump = repr(dict(self.client.session.items()))
        self.assertNotIn("Another-Strong-Pass-55!", dump)
        # and, while the step is pending, only the verified phone & trusted registration state are stored
        self.client = Client()
        self.verified_via_register(phone="09128880002")
        pending = self.client.session["portal_signup_pending"]
        self.assertEqual(set(pending), {
            "phone", "verified_at", "next", "admin_return", "remember_me", "full_name", "terms_version", "origin",
        })
        self.assertNotIn("password", repr(pending).lower())
        self.assertNotIn("email", set(pending))

    def test_a_double_submit_and_replay_create_exactly_one_owner_one_store_one_acceptance(self):
        self.verified_via_register()
        replay = Client()
        replay.cookies = self.client.cookies.__class__()
        replay.cookies.update(self.client.cookies)
        first = self.submit()
        self.assertIn("/onboarding/", first["Location"])
        again = self.submit()  # refresh / double click in the same browser
        self.assertEqual(again.status_code, 302)
        self.assertNotIn("/onboarding/", again["Location"])
        late = self.submit(client=replay)  # a stale copy of the same session
        self.assertEqual(late.status_code, 302)
        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(phone=_PHONE).count(), 1)
        self.assertEqual(self.stores().count(), 1)
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)


class CredentialValidationTests(_Base):
    def setUp(self):
        super().setUp()
        self.verified_via_register()

    def test_email_is_required(self):
        for missing in (None, "", "   "):
            with self.subTest(email=repr(missing)):
                response = self.submit(email=missing)
                self.assertRejectedKeepingProof(response, "ایمیل را وارد کنید.")
                self.assertContains(response, 'id="id_email_error"')

    def test_invalid_and_overlong_emails_are_rejected(self):
        for bad in ("not-an-email", "a@", "@b.com", "a b@example.com", "a@b", "x" * 250 + "@example.com"):
            with self.subTest(email=bad[:40]):
                self.assertRejectedKeepingProof(self.submit(email=bad), "ایمیل واردشده معتبر نیست")

    def test_email_conflicts_are_case_insensitive_and_keep_the_proof(self):
        other = User.objects.create_user(username="09000000001", email="Taken@Example.com")
        stored_email = other.email  # Django normalises only the domain part; the point is it is never touched
        for clash in ("taken@example.com", "TAKEN@EXAMPLE.COM", "  Taken@example.com  "):
            with self.subTest(email=clash):
                self.assertRejectedKeepingProof(self.submit(email=clash), "این ایمیل قبلاً برای حساب دیگری ثبت شده است")
        self.assertEqual(User.objects.filter(email__iexact="taken@example.com").count(), 1)
        self.assertEqual(User.objects.get(pk=other.pk).email, stored_email)  # never touched
        # the proof was kept, so correcting the form works
        response = self.submit(email="free@example.com")
        self.assertIn("/onboarding/", response["Location"])

    def test_password_and_confirmation_are_required(self):
        self.assertRejectedKeepingProof(self.submit(password=None, password_confirm=None), "رمز عبور را وارد کنید.")
        self.assertRejectedKeepingProof(self.submit(password_confirm=None), "رمز عبور را یک بار دیگر وارد کنید.")
        self.assertRejectedKeepingProof(self.submit(password="", password_confirm=""), "رمز عبور را وارد کنید.")

    def test_mismatched_confirmation_is_rejected(self):
        self.assertRejectedKeepingProof(
            self.submit(password_confirm=GOOD_PASSWORD + "!"), "رمز عبور و تکرار آن یکسان نیستند.",
        )

    def test_django_password_validators_are_applied_not_a_weaker_policy(self):
        cases = {
            "short": "Ab1!",  # MinimumLengthValidator
            "common": "password123",  # CommonPasswordValidator
            "numeric": "7391846205",  # NumericPasswordValidator
            "similar_to_email": "owner09128880001",  # UserAttributeSimilarityValidator (email/username)
        }
        for label, password in cases.items():
            with self.subTest(case=label):
                response = self.submit(password=password, password_confirm=password)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_password_error"')
                self.assertNothingCreated()

    def test_nothing_is_created_by_any_rejected_submit(self):
        for overrides in ({"email": "bad"}, {"password": "x", "password_confirm": "x"}, {"password_confirm": "nope"}):
            self.submit(**overrides)
        self.assertNothingCreated()

    def test_a_posted_phone_user_or_terms_version_is_ignored(self):
        other = User.objects.create_user(username="09000000002")
        response = self.submit(
            phone="09999999999", username="09999999999", user=other.pk, user_id=other.pk,
            terms_version="1999-forged", accepted_terms_version="1999-forged", full_name="Attacker",
        )
        self.assertIn("/onboarding/", response["Location"])
        self.assertTrue(OwnerProfile.objects.filter(phone=_PHONE, full_name=_NAME).exists())
        self.assertFalse(User.objects.filter(username="09999999999").exists())
        self.assertEqual(OwnerTermsAcceptance.objects.get().terms_version, CURRENT_TERMS_VERSION)


class ProofTests(_Base):
    def test_the_step_cannot_be_reached_or_used_without_a_verified_phone(self):
        for method in ("get", "post"):
            with self.subTest(method=method):
                client = Client()
                if method == "get":
                    response = client.get(URL, HTTP_HOST=_HOST)
                else:
                    response = self.submit(client=client, email="a@b.com")
                self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertNothingCreated()

    def test_an_expired_proof_creates_nothing(self):
        self.verified_via_register()
        session = self.client.session
        pending = session["portal_signup_pending"]
        pending["verified_at"] -= 10_000
        session["portal_signup_pending"] = pending
        session.save()
        self.assertRedirects(self.submit(), "/login/", fetch_redirect_response=False)
        self.assertNothingCreated()
        self.assertNotIn("portal_signup_pending", self.client.session)

    def test_a_malformed_or_tampered_proof_fails_safely(self):
        for label, value in (
            ("not a dict", "09128880001"), ("empty phone", {"phone": "", "verified_at": 1}),
            ("no timestamp", {"phone": _PHONE}), ("string timestamp", {"phone": _PHONE, "verified_at": "now"}),
            ("future timestamp", {"phone": _PHONE, "verified_at": 4_000_000_000}),
        ):
            with self.subTest(case=label):
                self.client = Client()
                session = self.client.session
                session["portal_signup_pending"] = value
                session.save()
                self.assertRedirects(self.submit(), "/login/", fetch_redirect_response=False)
                self.assertNothingCreated()

    def test_a_terms_version_bump_between_register_and_the_step_asks_for_the_checkbox_again(self):
        self.verified_via_register()
        with patch("apps.portal.views.CURRENT_TERMS_VERSION", "2099-01-v9"):
            page = self.client.get(URL, HTTP_HOST=_HOST)
            self.assertContains(page, 'id="id_accept_terms"')
            refused = self.submit()
            self.assertEqual(refused.status_code, 200)
            self.assertContains(refused, TERMS_ACCEPTANCE_REQUIRED_MESSAGE)
        self.assertNothingCreated()

    def test_registration_closed_creates_nothing(self):
        self.verified_via_register()
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.new_store_registration_enabled = False
        config.save()
        cache.clear()
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ساخت فروشگاه تازه موقتاً در دسترس نیست")
        self.assertNothingCreated()


class LoginUnknownPhoneConvergesTests(_Base):
    def test_unknown_phone_via_login_asks_for_name_terms_email_and_password_on_the_same_step(self):
        self.verified_via_login()
        self.assertNothingCreated()
        page = self.client.get(URL, HTTP_HOST=_HOST)
        for needle in ('name="full_name"', 'id="id_accept_terms"', 'name="email"', 'name="password"', 'name="password_confirm"'):
            self.assertContains(page, needle)
        # Terms must be explicit here: credentials alone are not enough
        refused = self.submit(full_name=_NAME)
        self.assertRejectedKeepingProof(refused, TERMS_ACCEPTANCE_REQUIRED_MESSAGE)
        # missing credentials are not enough either
        self.assertRejectedKeepingProof(self.submit(full_name=_NAME, accept_terms="1", email=None), "ایمیل را وارد کنید.")
        response = self.submit(full_name=_NAME, accept_terms="1")
        store = self.stores().get()
        self.assertRedirects(response, f"/app/stores/{store.public_id}/onboarding/", fetch_redirect_response=False)
        user = User.objects.get(username=_PHONE)
        self.assertEqual(user.email, email_for(_PHONE))
        self.assertTrue(user.check_password(GOOD_PASSWORD))
        row = OwnerTermsAcceptance.objects.get()
        self.assertEqual((row.terms_version, row.source), (CURRENT_TERMS_VERSION, OwnerTermsAcceptance.Source.SIGNUP_COMPLETE))
        self.assertEqual(OwnerProfile.objects.get(user=user).full_name, _NAME)

    def test_the_name_is_validated_on_this_path_too(self):
        self.verified_via_login()
        for bad in ("", "   ", "ا", "12345"):
            with self.subTest(name=bad):
                self.assertRejectedKeepingProof(self.submit(full_name=bad, accept_terms="1"))


class ExistingOwnerStaysFastTests(_Base):
    def make_owner(self, phone=_PHONE):
        user = User.objects.create_user(username=phone, email=email_for(phone), password=GOOD_PASSWORD)
        OwnerProfile.objects.create(user=user, phone=phone, full_name="Existing Owner")
        return user

    def test_otp_login_of_an_existing_owner_is_never_routed_through_the_credential_step(self):
        owner = self.make_owner()
        self.login_otp()
        response = self.verify()
        self.assertEqual(response["Location"], "/app/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), owner.pk)
        self.assertNotIn("portal_signup_pending", self.client.session)

    def test_registering_with_an_existing_owner_phone_just_logs_in_and_changes_nothing(self):
        owner = self.make_owner()
        self.register()
        response = self.verify()
        self.assertEqual(response["Location"], "/app/")
        owner.refresh_from_db()
        self.assertTrue(owner.check_password(GOOD_PASSWORD))
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)
        self.assertEqual(self.stores().count(), 0)

    def test_an_existing_owner_without_a_password_is_not_forced_to_set_one_on_otp_login(self):
        owner = self.make_owner()
        owner.set_unusable_password()
        owner.save()
        self.login_otp()
        self.assertEqual(self.verify()["Location"], "/app/")  # password-less OTP owners keep their fast login


class SharedExistingUserTests(_Base):
    """A verified phone that already belongs to a User (e.g. a storefront customer) but has no OwnerProfile."""

    def make_user(self, *, email="", password=None, phone=_PHONE):
        user = User.objects.create_user(username=phone, email=email)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def requirements(self, phone=_PHONE):
        return owner_auth_service.signup_requirements_for_phone(phone)

    def test_requirements_for_each_shape_of_account(self):
        self.assertEqual(
            (lambda r: (r.existing_owner, r.need_email, r.need_password))(self.requirements()), (False, True, True),
        )
        self.make_user(email="", password=None)
        self.assertEqual((self.requirements().need_email, self.requirements().need_password), (True, True))
        User.objects.all().delete()
        self.make_user(email="a@example.com", password="Strong-Existing-77!")
        self.assertEqual((self.requirements().need_email, self.requirements().need_password), (False, False))
        User.objects.all().delete()
        self.make_user(email="", password="Strong-Existing-77!")
        self.assertEqual((self.requirements().need_email, self.requirements().need_password), (True, False))
        User.objects.all().delete()
        self.make_user(email="a@example.com", password=None)
        self.assertEqual((self.requirements().need_email, self.requirements().need_password), (False, True))

    def test_a_usable_password_and_an_email_are_preserved_and_not_even_asked_for(self):
        user = self.make_user(email="Customer@Example.com", password="Customer-Pass-77!")
        original_email = user.email
        self.register()
        response = self.verify()
        # nothing else is needed, and /register/ captured name + Terms: the account completes immediately
        self.assertIn("/onboarding/", response["Location"])
        user.refresh_from_db()
        self.assertTrue(user.check_password("Customer-Pass-77!"))  # NOT replaced
        self.assertEqual(user.email, original_email)  # NOT replaced
        self.assertEqual(User.objects.filter(username=_PHONE).count(), 1)
        self.assertTrue(OwnerProfile.objects.filter(user=user).exists())
        self.assertEqual(OwnerTermsAcceptance.objects.get().user_id, user.pk)

    def test_via_login_a_customer_with_credentials_is_only_asked_for_name_and_terms(self):
        user = self.make_user(email="c@example.com", password="Customer-Pass-77!")
        self.verified_via_login()
        page = self.client.get(URL, HTTP_HOST=_HOST)
        self.assertContains(page, 'name="full_name"')
        self.assertContains(page, 'id="id_accept_terms"')
        self.assertNotContains(page, 'name="email"')
        self.assertNotContains(page, 'name="password"')
        response = self.client.post(URL, {"full_name": _NAME, "accept_terms": "1", "password": "Hijack-Pass-99!", "password_confirm": "Hijack-Pass-99!", "email": "h@example.com"}, HTTP_HOST=_HOST)
        self.assertIn("/onboarding/", response["Location"])
        user.refresh_from_db()
        self.assertTrue(user.check_password("Customer-Pass-77!"))  # posted credentials for a complete account are ignored
        self.assertEqual(user.email, "c@example.com")

    def test_a_user_without_a_usable_password_must_set_one_but_keeps_their_email(self):
        user = self.make_user(email="keep@example.com", password=None)
        self.verified_via_register()
        page = self.client.get(URL, HTTP_HOST=_HOST)
        self.assertNotContains(page, 'name="email"')
        self.assertContains(page, 'name="password"')
        self.assertRejectedKeepingProof_existing(self.client.post(URL, {}, HTTP_HOST=_HOST))
        response = self.client.post(URL, {"email": "ignored@example.com", "password": GOOD_PASSWORD, "password_confirm": GOOD_PASSWORD}, HTTP_HOST=_HOST)
        self.assertIn("/onboarding/", response["Location"])
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password(GOOD_PASSWORD))
        self.assertEqual(user.email, "keep@example.com")  # an existing email is never overwritten

    def assertRejectedKeepingProof_existing(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIn("portal_signup_pending", self.client.session)
        self.assertFalse(OwnerProfile.objects.filter(phone=_PHONE).exists())

    def test_a_user_without_an_email_must_give_one_but_keeps_their_password(self):
        user = self.make_user(email="", password="Customer-Pass-77!")
        self.verified_via_register()
        page = self.client.get(URL, HTTP_HOST=_HOST)
        self.assertContains(page, 'name="email"')
        self.assertNotContains(page, 'name="password"')
        self.assertRejectedKeepingProof_existing(self.client.post(URL, {"email": ""}, HTTP_HOST=_HOST))
        response = self.client.post(URL, {"email": "New@Example.com"}, HTTP_HOST=_HOST)
        self.assertIn("/onboarding/", response["Location"])
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("Customer-Pass-77!"))  # password untouched

    def test_an_email_that_belongs_to_another_user_is_never_stolen(self):
        other = User.objects.create_user(username="09000000009", email="Someone@Example.com")
        stored_email = other.email
        user = self.make_user(email="", password="Customer-Pass-77!")
        self.verified_via_register()
        response = self.client.post(URL, {"email": "someone@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این ایمیل قبلاً برای حساب دیگری ثبت شده است")
        user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((user.email, other.email), ("", stored_email))
        self.assertFalse(OwnerProfile.objects.filter(user=user).exists())

    def test_the_users_own_email_is_not_a_conflict_with_itself(self):
        user = self.make_user(email="mine@example.com", password=None)
        self.assertFalse(owner_auth_service.email_belongs_to_another_user("MINE@example.com", exclude_user=user))
        self.assertTrue(owner_auth_service.email_belongs_to_another_user("MINE@example.com"))
        self.assertFalse(owner_auth_service.email_belongs_to_another_user("free@example.com"))

    def test_an_inactive_user_never_gets_an_owner(self):
        user = self.make_user(email="i@example.com", password="Customer-Pass-77!")
        user.is_active = False
        user.save()
        self.register()
        response = self.verify()
        self.assertEqual(response["Location"], "/login/")
        self.assertFalse(OwnerProfile.objects.filter(user=user).exists())


class ServiceContractTests(TestCase):
    """``require_credentials`` is the single policy: nothing is created unless email + password are valid."""

    def resolve(self, **kwargs):
        defaults = dict(phone=_PHONE, full_name=_NAME, require_credentials=True, accepted_terms_version=CURRENT_TERMS_VERSION)
        return owner_auth_service.resolve_owner_identity_by_phone(**{**defaults, **kwargs})

    def assertNothing(self):
        self.assertFalse(User.objects.filter(username=_PHONE).exists())
        self.assertFalse(OwnerProfile.objects.filter(phone=_PHONE).exists())
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 0)

    def test_missing_or_bad_credentials_create_nothing(self):
        with self.assertRaises(owner_auth_service.OwnerEmailError):
            self.resolve(email="", password=GOOD_PASSWORD)
        with self.assertRaises(owner_auth_service.OwnerEmailError):
            self.resolve(email="nope", password=GOOD_PASSWORD)
        with self.assertRaises(owner_auth_service.PasswordPolicyError):
            self.resolve(email="a@example.com", password="")
        with self.assertRaises(owner_auth_service.PasswordPolicyError):
            self.resolve(email="a@example.com", password="12345678")
        User.objects.create_user(username="09000000007", email="dup@example.com")
        with self.assertRaises(owner_auth_service.OwnerEmailConflictError):
            self.resolve(email="DUP@example.com", password=GOOD_PASSWORD)
        self.assertNothing()

    def test_valid_credentials_create_a_complete_owner(self):
        result = self.resolve(email="V@Example.com", password=GOOD_PASSWORD)
        self.assertTrue(result.user_created and result.owner_created)
        self.assertEqual(result.user.email, "v@example.com")
        self.assertTrue(result.user.check_password(GOOD_PASSWORD))
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)

    def test_a_failure_after_the_user_is_created_rolls_everything_back(self):
        with patch.object(OwnerProfile.objects, "create", side_effect=RuntimeError("boom")), self.assertRaises(RuntimeError):
            self.resolve(email="r@example.com", password=GOOD_PASSWORD)
        self.assertNothing()

    def test_internal_callers_keep_the_legacy_behaviour_without_credentials(self):
        user, created = owner_auth_service.get_or_create_owner_by_phone(phone="09128880077", full_name="X")
        self.assertTrue(created)
        self.assertFalse(user.has_usable_password())  # only the public signup views pass require_credentials=True

    def test_the_public_views_always_require_credentials(self):
        import inspect

        from apps.portal import views

        source = inspect.getsource(views._finish_account_completion)
        self.assertIn("require_credentials=True", source)
        # and /verify/ no longer creates an Owner on its own
        self.assertIn("allow_new_owner=False", inspect.getsource(views.otp_verify))


@unittest.skipUnless(connection.vendor == "postgresql", "real-thread race tests need PostgreSQL row locking")
class ConcurrentSignupTests(TransactionTestCase):
    def test_parallel_account_completion_for_one_phone_yields_one_owner_and_one_email(self):
        barrier = threading.Barrier(8)
        results = [None] * 8

        def worker(index):
            try:
                barrier.wait(timeout=30)
                identity = owner_auth_service.resolve_owner_identity_by_phone(
                    phone=_PHONE, full_name=_NAME, require_credentials=True,
                    email="race@example.com", password=GOOD_PASSWORD, accepted_terms_version=CURRENT_TERMS_VERSION,
                )
                results[index] = identity.owner_created
            except Exception as exc:  # noqa: BLE001 — surfaced to the assertion
                results[index] = exc
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        self.assertEqual(results.count(True), 1)
        self.assertEqual(User.objects.filter(email__iexact="race@example.com").count(), 1)
        self.assertEqual(OwnerProfile.objects.filter(phone=_PHONE).count(), 1)
        self.assertEqual(OwnerTermsAcceptance.objects.count(), 1)
