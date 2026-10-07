"""Public password recovery is mobile + SMS OTP (replaces the public email reset).

    /reset-password/ -> OTP (purpose "reset") -> /verify/ -> /reset-password/new/ -> /login/

Everything runs through the real Django views. The SMS provider is faked at
``owner_otp_service.send_platform_otp`` (the exact seam the other owner-OTP tests use).
"""

import logging
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.services import rate_limit
from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE
from apps.customers.models import Customer
from apps.portal import views as portal_views
from apps.portal.models import OwnerOtpChallenge, OwnerProfile
from apps.portal.services import owner_auth_service, owner_otp_service, owner_sms_service, turnstile_service
from apps.sms.models import SmsLog
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09121230001"
_OTHER = "09121230002"
_UNKNOWN = "09129990000"
_OLD = "an-old-strong-pass-1"
_NEW = "a-brand-new-strong-pass-7"
_RESET = OwnerOtpChallenge.Purpose.PASSWORD_RESET


class _DownCounter:
    def hit(self, key, window_seconds):
        raise ConnectionError("redis://:topsecret@10.0.0.9:6379/0 unreachable")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class _Base(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.sent = []
        self.send_ok = True
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._fake_send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _fake_send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        if not self.send_ok:
            return SmsSendResult(success=False, error_message="provider down", provider="test")
        return SmsSendResult(success=True, provider_ref_id="t")

    @property
    def code(self):
        return self.sent[-1]["code"]

    def owner(self, phone=_PHONE, password=_OLD, name="Owner", active=True):
        user = User.objects.create_user(username=phone)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.is_active = active
        user.save()
        OwnerProfile.objects.create(user=user, phone=phone, full_name=name)
        return user

    def request_reset(self, phone=_PHONE, client=None, **extra):
        return (client or self.client).post("/reset-password/", {"phone": phone}, HTTP_HOST=_HOST, **extra)

    def verify(self, code=None, client=None):
        client = client or self.client
        return client.post("/verify/", {"code": code if code is not None else self.code}, HTTP_HOST=_HOST)

    def set_password(self, password=_NEW, confirm=None, client=None):
        client = client or self.client
        return client.post(
            "/reset-password/new/", {"password": password, "password_confirm": confirm or password}, HTTP_HOST=_HOST,
        )

    def login(self, identifier, password, client=None):
        return (client or self.client).post(
            "/login/password/", {"identifier": identifier, "password": password}, HTTP_HOST=_HOST,
        )

    def snapshot(self):
        return {
            "users": User.objects.count(), "profiles": OwnerProfile.objects.count(),
            "stores": Store.objects.count(), "challenges": OwnerOtpChallenge.objects.count(),
            "smslogs": SmsLog.objects.count(), "mail": len(mail.outbox), "sent": len(self.sent),
        }

    def active_challenges(self, phone=_PHONE):
        return OwnerOtpChallenge.objects.filter(
            phone=phone, purpose=_RESET, consumed_at__isnull=True, expires_at__gt=timezone.now(),
        )


# ---------------------------------------------------------------------------
# The happy paths
# ---------------------------------------------------------------------------


class ResetHappyPathTests(_Base):
    def test_existing_mobile_owner_resets_and_logs_in_with_phone_and_new_password(self):
        self.owner()
        response = self.request_reset()
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
        self.assertEqual([(m["to"], m["purpose"]) for m in self.sent], [(_PHONE, "reset")])

        verified = self.verify()
        self.assertEqual((verified.status_code, verified["Location"]), (302, "/reset-password/new/"))
        self.assertNotIn("_auth_user_id", self.client.session)  # a reset OTP never logs anyone in

        page = self.client.get("/reset-password/new/", HTTP_HOST=_HOST)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'autocomplete="new-password"', count=2)
        self.assertIn("no-store", page["Cache-Control"])

        done = self.set_password()
        self.assertEqual((done.status_code, done["Location"]), (302, "/login/"))
        self.assertNotIn("_auth_user_id", self.client.session)  # no auto-login
        landing = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(landing, "رمز عبور با موفقیت تعیین شد")

        self.assertEqual(self.login(_PHONE, _OLD).status_code, 200)  # old password is dead
        cache.clear()
        ok = self.login(_PHONE, _NEW)
        self.assertRedirects(ok, "/app/", fetch_redirect_response=False)

    def test_otp_created_owner_with_an_unusable_password_can_set_a_first_password(self):
        user = self.owner(password=None)
        self.assertFalse(user.has_usable_password())
        self.request_reset()
        self.verify()
        self.set_password()
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        cache.clear()
        self.assertRedirects(self.login(_PHONE, _NEW), "/app/", fetch_redirect_response=False)

    def test_a_legacy_email_password_owner_can_replace_the_password_by_phone(self):
        user = owner_auth_service.register_owner(full_name="Legacy", email="legacy@example.com", password=_OLD)
        profile = user.owner_profile
        profile.phone = _PHONE
        profile.save()
        self.request_reset()
        self.verify()
        self.set_password()
        cache.clear()
        self.assertEqual(self.login("legacy@example.com", _OLD).status_code, 200)
        cache.clear()
        self.assertRedirects(self.login("legacy@example.com", _NEW), "/app/", fetch_redirect_response=False)
        cache.clear()
        self.assertRedirects(self.login(_PHONE, _NEW), "/app/", fetch_redirect_response=False)

    def test_persian_digits_in_phone_and_code_work(self):
        self.owner()
        self.request_reset("۰۹۱۲۱۲۳۰۰۰۱")
        digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        verified = self.verify(self.code.translate(digits))
        self.assertEqual(verified["Location"], "/reset-password/new/")

    def test_reset_page_asks_for_a_mobile_number_not_an_email(self):
        html = self.client.get("/reset-password/", HTTP_HOST=_HOST).content.decode()
        self.assertRegex(html, r'name="phone"[^>]*autocomplete="tel"')
        self.assertNotIn('name="email"', html)
        self.assertIn("شماره موبایل", html)
        self.assertNotIn("پیوند بازیابی", html)
        self.assertNotIn("ایمیل", html)
        self.assertNotIn("رمز عبور ندارند", html)  # mobile-only users are told how to GET a password


# ---------------------------------------------------------------------------
# Creates nothing / enumeration safety
# ---------------------------------------------------------------------------


class ResetEnumerationAndNoCreationTests(_Base):
    def _public_shape(self, response):
        verify_page = self.client.get(response["Location"], HTTP_HOST=_HOST)
        html = re.sub(r'value="[^"]*"', "", verify_page.content.decode())  # csrf tokens etc.
        return response.status_code, response["Location"], re.sub(r"\s+", " ", html), dict(self.client.session)

    def test_unknown_phone_creates_nothing_sends_nothing_and_looks_identical(self):
        self.owner(_PHONE)
        known = self.request_reset(_PHONE)
        known_shape = self._public_shape(known)
        self.assertEqual(len(self.sent), 1)

        other = self.client_class()
        before = self.snapshot()
        unknown = self.request_reset(_UNKNOWN, client=other)
        after = self.snapshot()
        self.assertEqual(after, before)  # nothing created, no SMS, no challenge, no log, no mail
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone=_UNKNOWN).exists())
        self.assertFalse(User.objects.filter(username=_UNKNOWN).exists())
        self.assertFalse(OwnerProfile.objects.filter(phone=_UNKNOWN).exists())

        self.client = other
        unknown_shape = self._public_shape(unknown)
        # status, redirect target and the whole rendered verify page (minus the phone) are identical
        self.assertEqual(known_shape[:2], unknown_shape[:2])
        strip = lambda text, phone: text.replace(phone, "PHONE")
        self.assertEqual(strip(known_shape[2], _PHONE), strip(unknown_shape[2], _UNKNOWN))
        self.assertIn("اگر حساب فعالی با این شماره وجود داشته باشد", known_shape[2])

    def test_wrong_codes_give_the_same_message_for_known_and_unknown_phones(self):
        self.owner()
        known_client, unknown_client = self.client_class(), self.client_class()
        self.request_reset(_PHONE, client=known_client)
        self.request_reset(_UNKNOWN, client=unknown_client)
        a = known_client.post("/verify/", {"code": "000000"}, HTTP_HOST=_HOST)
        b = unknown_client.post("/verify/", {"code": "000000"}, HTTP_HOST=_HOST)
        for response in (a, b):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, portal_views._RESET_OTP_FAILURE_MESSAGE)

    def test_inactive_customer_only_and_profileless_accounts_are_treated_as_unknown(self):
        self.owner(_PHONE, active=False)
        customer = User.objects.create_user(username=_OTHER, password=_OLD)
        Customer.objects.create(user=customer, full_name="C", phone=_OTHER)
        for phone in (_PHONE, _OTHER):
            with self.subTest(phone=phone):
                before = self.snapshot()
                response = self.request_reset(phone)
                self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
                self.assertEqual(self.snapshot(), before)
        self.assertFalse(OwnerProfile.objects.filter(phone=_OTHER).exists())  # the customer did NOT become an owner
        customer.refresh_from_db()
        self.assertTrue(customer.check_password(_OLD))  # customer data/password untouched

    def test_nothing_in_the_flow_can_create_an_owner_user_or_store(self):
        before = self.snapshot()
        self.request_reset(_UNKNOWN)
        self.client.post("/verify/", {"code": "123456"}, HTTP_HOST=_HOST)
        self.client.get("/reset-password/new/", HTTP_HOST=_HOST)
        self.client.post("/reset-password/new/", {"password": _NEW, "password_confirm": _NEW}, HTTP_HOST=_HOST)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_phone_is_a_field_error_and_sends_nothing(self):
        for bad in ("123", "not-a-phone", "0912123", "09" + "1" * 30):
            with self.subTest(bad=bad):
                response = self.request_reset(bad)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_phone_error"')
        self.assertEqual(self.sent, [])

    def test_timing_numbers_on_the_verify_page_do_not_depend_on_the_account(self):
        self.owner()
        a, b = self.client_class(), self.client_class()
        self.request_reset(_PHONE, client=a)
        self.request_reset(_UNKNOWN, client=b)
        pat = r'data-otp-expires="(\d+)"'
        ea = int(re.search(pat, a.get("/verify/", HTTP_HOST=_HOST).content.decode()).group(1))
        eb = int(re.search(pat, b.get("/verify/", HTTP_HOST=_HOST).content.decode()).group(1))
        self.assertGreater(ea, 0)
        self.assertLessEqual(abs(ea - eb), 2)


# ---------------------------------------------------------------------------
# OTP security: wrong / expired / attempts / replay / cross purpose
# ---------------------------------------------------------------------------


class ResetOtpSecurityTests(_Base):
    def setUp(self):
        super().setUp()
        self.user = self.owner()

    def assertNoAuthorization(self):
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        response = self.client.get("/reset-password/new/", HTTP_HOST=_HOST)
        self.assertEqual((response.status_code, response["Location"]), (302, "/reset-password/"))

    def test_wrong_code_is_rejected_and_grants_nothing(self):
        self.request_reset()
        wrong = "000000" if self.code != "000000" else "111111"
        response = self.verify(wrong)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, portal_views._RESET_OTP_FAILURE_MESSAGE)
        self.assertNoAuthorization()

    def test_expired_code_is_rejected(self):
        self.request_reset()
        OwnerOtpChallenge.objects.filter(phone=_PHONE, purpose=_RESET).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.verify()
        self.assertContains(response, portal_views._RESET_OTP_FAILURE_MESSAGE)
        self.assertNoAuthorization()

    def test_attempt_cap_locks_the_code_even_for_the_right_value(self):
        self.request_reset()
        real = self.code
        wrong = "000000" if real != "000000" else "111111"
        for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS):
            self.verify(wrong)
        response = self.verify(real)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, portal_views._RESET_OTP_FAILURE_MESSAGE)
        self.assertNoAuthorization()

    def test_a_consumed_code_cannot_be_replayed(self):
        self.request_reset()
        code = self.code
        self.assertEqual(self.verify()["Location"], "/reset-password/new/")
        self.set_password()
        replay = self.client.post("/verify/", {"code": code}, HTTP_HOST=_HOST)  # session OTP state is gone
        self.assertEqual((replay.status_code, replay["Location"]), (302, "/login/"))
        self.assertEqual(
            owner_otp_service.check_otp(phone=_PHONE, purpose=_RESET, code=code),
            owner_otp_service.OtpCheckResult.EXPIRED,
        )

    def test_login_register_and_step_up_codes_are_not_reset_codes(self):
        for purpose in ("login", "register", "step_up"):
            with self.subTest(purpose=purpose):
                owner_otp_service.request_otp(phone=_PHONE, purpose=purpose, client_ip=f"9.9.9.{len(self.sent)}")
                other_purpose_code = self.code
                self.assertEqual(
                    owner_otp_service.check_otp(phone=_PHONE, purpose=_RESET, code=other_purpose_code),
                    owner_otp_service.OtpCheckResult.EXPIRED,  # no reset challenge exists at all
                )
        # …and through the views: a login code typed on the reset verify page is rejected
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="9.9.9.200")
        login_code = self.code
        self.request_reset()
        if self.code == login_code:  # 1-in-a-million collision: re-roll
            self.request_reset()
        response = self.verify(login_code)
        self.assertEqual(response.status_code, 200)
        self.assertNoAuthorization()

    def test_a_reset_code_cannot_log_in_or_register(self):
        self.request_reset()
        reset_code = self.code
        # attacker now starts a LOGIN flow for the same phone and types the reset code
        patched = patch.object(owner_otp_service, "_generate_code", return_value="777777")
        with patched:
            self.client.post("/login/", {"phone": _PHONE}, HTTP_HOST=_HOST)
        response = self.verify(reset_code if reset_code != "777777" else "888888")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        # and the OTP engine itself refuses the cross-purpose use
        for purpose in ("login", "register"):
            self.assertIsNot(
                owner_otp_service.check_otp(phone=_PHONE, purpose=purpose, code=reset_code),
                owner_otp_service.OtpCheckResult.OK,
            )

    def test_reset_otp_success_never_authenticates_and_clears_otp_session_state(self):
        self.request_reset()
        self.verify()
        session = self.client.session
        self.assertNotIn("_auth_user_id", session)
        for key in ("portal_otp_phone", "portal_otp_purpose", "portal_otp_started_at"):
            self.assertNotIn(key, session)


# ---------------------------------------------------------------------------
# Resend
# ---------------------------------------------------------------------------


class ResetResendTests(_Base):
    def resend(self, client=None):
        return (client or self.client).post("/verify/resend/", HTTP_HOST=_HOST)

    def test_resend_sends_a_new_reset_code_to_an_eligible_owner_and_the_old_one_dies(self):
        self.owner()
        self.request_reset()
        first = self.code
        response = self.resend()
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
        self.assertEqual([m["purpose"] for m in self.sent], ["reset", "reset"])
        second = self.code
        page = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(page, portal_views._RESET_RESEND_NOTICE)
        if first != second:
            self.assertContains(self.verify(first), portal_views._RESET_OTP_FAILURE_MESSAGE)
        self.assertEqual(self.verify(second)["Location"], "/reset-password/new/")

    def test_resend_for_an_unknown_phone_sends_nothing_and_answers_the_same(self):
        self.request_reset(_UNKNOWN)
        before = self.snapshot()
        response = self.resend()
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
        self.assertEqual(self.snapshot(), before)
        self.assertContains(self.client.get("/verify/", HTTP_HOST=_HOST), portal_views._RESET_RESEND_NOTICE)

    def test_resend_rechecks_eligibility_deactivated_after_the_first_request(self):
        user = self.owner()
        self.request_reset()
        user.is_active = False
        user.save()
        before = self.snapshot()
        self.resend()
        self.assertEqual(self.snapshot(), before)

    def test_resend_never_uses_the_generic_sender_for_reset(self):
        self.request_reset(_UNKNOWN)
        with patch.object(owner_otp_service, "request_otp") as generic:
            self.resend()
        generic.assert_not_called()

    def test_per_phone_budget_is_enforced_without_revealing_the_account(self):
        self.owner()
        self.request_reset()
        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW + 2):
            response = self.resend()
            self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.sent), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)  # the cap held
        self.assertContains(self.client.get("/verify/", HTTP_HOST=_HOST), portal_views._RESET_RESEND_NOTICE)


# ---------------------------------------------------------------------------
# Failure policy: provider, shared store, SMS not configured, Turnstile, IP budget
# ---------------------------------------------------------------------------


class ResetFailurePolicyTests(_Base):
    def test_provider_failure_leaves_no_active_challenge_and_no_authorization(self):
        self.owner()
        self.send_ok = False
        response = self.request_reset()
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))  # controlled, no 500
        self.assertEqual(len(self.sent), 1)  # it was attempted…
        self.assertEqual(self.active_challenges().count(), 0)  # …and nothing usable remains
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone=_PHONE).exists())
        for code in ("000000", "123456"):
            self.assertContains(self.verify(code), portal_views._RESET_OTP_FAILURE_MESSAGE)
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        self.assertEqual(self.client.get("/reset-password/new/", HTTP_HOST=_HOST).status_code, 302)

    def test_service_removes_the_in_flight_challenge_when_the_provider_raises(self):
        """SERVICE boundary only: ``request_otp`` cleans up and re-raises. (The HTTP behaviour is
        proven by ``ResetProviderExceptionAtTheViewTests``.)"""
        self.owner()
        with patch.object(owner_otp_service, "send_platform_otp", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                owner_otp_service.request_otp(phone=_PHONE, purpose=_RESET, client_ip="1.1.1.1")
        self.assertEqual(self.active_challenges().count(), 0)
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone=_PHONE).exists())

    def test_shared_store_outage_sends_no_sms_and_shows_the_controlled_message(self):
        self.owner()
        with patch.object(rate_limit, "get_counter", return_value=_DownCounter()):
            response = self.request_reset()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertNotContains(response, "topsecret")
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertNotIn("portal_otp_phone", self.client.session)

    def test_outage_during_resend_sends_nothing(self):
        self.owner()
        self.request_reset()
        before = len(self.sent)
        with patch.object(rate_limit, "get_counter", return_value=_DownCounter()):
            self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.sent), before)
        self.assertContains(self.client.get("/verify/", HTTP_HOST=_HOST), UNAVAILABLE_MESSAGE)

    def test_the_per_ip_reset_budget_is_kept(self):
        for index in range(5):
            self.assertEqual(self.request_reset(_UNKNOWN).status_code, 302)
        blocked = self.request_reset(_UNKNOWN)
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "بیش از حد مجاز")

    def test_the_otp_ip_budget_is_charged_and_enforced_for_unknown_phones_too(self):
        with patch.object(owner_otp_service, "charge_ip_budget", wraps=owner_otp_service.charge_ip_budget) as charge:
            self.request_reset(_UNKNOWN)
        self.assertEqual(charge.call_count, 1)
        self.assertEqual(charge.call_args.kwargs["purpose"], _RESET)
        # exhaust the OTP-request IP bucket for purpose=reset, then an unknown phone is refused identically
        key = rate_limit.build_key("owner_otp_request_ip:reset", "203.0.113.77")
        for _ in range(owner_otp_service.IP_MAX_REQUESTS):
            rate_limit.get_counter().hit(key, 600)
        fresh = self.client_class()
        blocked = self.request_reset(_UNKNOWN, client=fresh, REMOTE_ADDR="203.0.113.77")
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "بیش از حد مجاز")
        self.assertNotIn("portal_otp_phone", fresh.session)

    def test_sms_not_deliverable_at_all_is_one_error_for_every_phone(self):
        self.owner()
        with override_settings(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False, RASTISI_DEV_OTP_CODE=""):
            known = self.request_reset(_PHONE)
            unknown = self.request_reset(_UNKNOWN, client=self.client_class())
        for response in (known, unknown):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, portal_views._SMS_UNAVAILABLE_MESSAGE)
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_turnstile_failure_sends_no_sms(self):
        self.owner()
        ts = dict(
            TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="1x00000000000000000000AA",
            TURNSTILE_SECRET_KEY="1x0000000000000000000000000000AA", TURNSTILE_EXPECTED_HOSTNAMES=(_HOST,),
        )
        denied = turnstile_service.TurnstileValidationResult(success=False, error_code="verification-failed")
        with override_settings(**ts), patch.object(turnstile_service, "verify_request", return_value=denied):
            response = self.request_reset()
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_turnstile_is_still_required_in_production_mode(self):
        self.owner()
        with override_settings(RASTISI_PRODUCTION_MODE=True, TURNSTILE_ENABLED=False):
            response = self.request_reset()
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(self.sent, [])


# ---------------------------------------------------------------------------
# The password-setting page: session proof
# ---------------------------------------------------------------------------


class ResetNewPasswordPageTests(_Base):
    def setUp(self):
        super().setUp()
        self.user = self.owner()

    def authorize(self):
        self.request_reset()
        self.assertEqual(self.verify()["Location"], "/reset-password/new/")

    def test_direct_access_without_a_verified_otp_redirects_and_changes_nothing(self):
        for method in ("get", "post"):
            response = getattr(self.client, method)("/reset-password/new/", {"password": _NEW, "password_confirm": _NEW}, HTTP_HOST=_HOST)
            self.assertEqual((response.status_code, response["Location"]), (302, "/reset-password/"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_OLD))
        self.assertContains(self.client.get("/reset-password/", HTTP_HOST=_HOST), "زمانِ تعیینِ رمز عبور به پایان رسید")

    def test_an_expired_authorization_is_refused_and_cleared(self):
        self.authorize()
        session = self.client.session
        session["portal_password_reset_pending"]["verified_at"] -= portal_views.RESET_PENDING_TTL_SECONDS + 1
        session.save()
        response = self.set_password()
        self.assertEqual((response.status_code, response["Location"]), (302, "/reset-password/"))
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_OLD))

    def test_the_authorization_is_single_use(self):
        self.authorize()
        self.assertEqual(self.set_password()["Location"], "/login/")
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        again = self.set_password("yet-another-strong-pass-3")
        self.assertEqual((again.status_code, again["Location"]), (302, "/reset-password/"))
        self.assertEqual(self.client.get("/reset-password/new/", HTTP_HOST=_HOST).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_NEW))
        self.assertFalse(self.user.check_password("yet-another-strong-pass-3"))

    def test_the_target_user_comes_only_from_the_server_side_proof(self):
        victim = self.owner(_OTHER, password=_OLD, name="Victim")
        self.authorize()
        response = self.client.post(
            "/reset-password/new/",
            {"password": _NEW, "password_confirm": _NEW, "user_id": victim.pk, "uid": victim.pk, "phone": _OTHER, "username": _OTHER},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response["Location"], "/login/")
        victim.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(victim.check_password(_OLD))  # untouched
        self.assertTrue(self.user.check_password(_NEW))

    def test_each_otp_only_authorizes_its_own_phone(self):
        other = self.owner(_OTHER, password=_OLD, name="Other")
        self.request_reset(_OTHER)
        self.verify()
        self.set_password()
        other.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(other.check_password(_NEW))
        self.assertTrue(self.user.check_password(_OLD))

    def test_eligibility_is_rechecked_when_the_password_is_set(self):
        self.authorize()
        self.user.is_active = False
        self.user.save()
        for response in (self.client.get("/reset-password/new/", HTTP_HOST=_HOST), self.set_password()):
            self.assertEqual((response.status_code, response["Location"]), (302, "/reset-password/"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_OLD))

    def test_password_validation_errors_render_in_persian_beside_the_field_and_keep_the_authorization(self):
        self.authorize()
        cases = {"short": ("abc", "abc"), "numeric": ("123456789012", "123456789012"), "common": ("password", "password")}
        for name, (password, confirm) in cases.items():
            with self.subTest(name=name):
                response = self.set_password(password, confirm)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_password_error"')
                errors = re.search(r'id="id_password_error">(.*?)</ul>', response.content.decode(), re.S).group(1)
                text = re.sub(r"<[^>]+>", " ", errors)
                self.assertRegex(text, r"[؀-ۿ]")
                self.assertNotRegex(text, r"[A-Za-z]{4,}")
        mismatch = self.set_password(_NEW, "different-strong-pass-9")
        self.assertContains(mismatch, 'id="id_password_confirm_error"')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_OLD))
        self.assertEqual(self.set_password()["Location"], "/login/")  # still authorized after the failed tries

    def test_other_sessions_of_the_account_are_logged_out_by_the_change(self):
        other = self.client_class()
        self.login(_PHONE, _OLD, client=other)
        self.assertIn("_auth_user_id", other.session)
        self.authorize()
        self.set_password()
        self.assertEqual(other.get("/app/", HTTP_HOST=_HOST).status_code, 302)

    def test_a_new_reset_request_invalidates_an_earlier_authorization(self):
        self.authorize()
        self.request_reset()  # starts over: the old proof is dropped until the new code is verified
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        self.assertEqual(self.client.get("/reset-password/new/", HTTP_HOST=_HOST).status_code, 302)


# ---------------------------------------------------------------------------
# Legacy compatibility + login copy
# ---------------------------------------------------------------------------


class LegacyAndCopyTests(_Base):
    def test_old_email_token_links_still_work_end_to_end(self):
        user = owner_auth_service.register_owner(full_name="Old", email="old@example.com", password=_OLD)
        owner_auth_service.request_password_reset(email="old@example.com", base_url=f"http://{_HOST}")
        link = re.search(r"/reset-password/[\w-]+/[\w-]+/", mail.outbox[-1].body).group(0)
        self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 200)
        done = self.client.post(link, {"password": _NEW, "password_confirm": _NEW}, HTTP_HOST=_HOST)
        self.assertEqual(done.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password(_NEW))
        self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 400)  # single use

    def test_the_reset_new_route_does_not_shadow_the_token_route(self):
        self.assertEqual(self.client.get("/reset-password/new/", HTTP_HOST=_HOST).status_code, 302)
        self.assertEqual(self.client.get("/reset-password/abc/def/", HTTP_HOST=_HOST).status_code, 400)

    def test_the_public_page_never_calls_the_email_reset_service(self):
        self.owner()
        with patch.object(owner_auth_service, "request_password_reset") as legacy:
            self.request_reset()
            self.client.post("/reset-password/", {"email": "x@example.com"}, HTTP_HOST=_HOST)
        legacy.assert_not_called()
        self.assertEqual(mail.outbox, [])

    def test_login_page_forgot_password_link_is_coherent(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertIn("فراموشی رمز عبور؟ تعیین رمز با کد پیامکی", html)
        self.assertIn('href="/reset-password/"', html)

    def test_verify_page_for_reset_has_its_own_copy_and_change_phone_link(self):
        self.owner()
        self.request_reset()
        html = self.client.get("/verify/", HTTP_HOST=_HOST).content.decode()
        self.assertIn("تأیید برای تعیین رمز", html)
        self.assertIn('href="/reset-password/"', html)
        self.assertNotIn("تأیید و ورود", html)

    def test_otp_challenge_purpose_choice_is_reset(self):
        self.assertEqual(OwnerOtpChallenge.Purpose.PASSWORD_RESET.value, "reset")
        self.assertLessEqual(len("reset"), OwnerOtpChallenge._meta.get_field("purpose").max_length)

    def test_stored_challenge_is_hashed(self):
        self.owner()
        self.request_reset()
        row = OwnerOtpChallenge.objects.get(phone=_PHONE, purpose=_RESET)
        self.assertNotEqual(row.code_hash, self.code)
        self.assertNotIn(self.code, row.code_hash)


# ---------------------------------------------------------------------------
# An unexpected provider EXCEPTION at the real public view must not be a 500
# ---------------------------------------------------------------------------

_SECRET_TEXT = "provider exploded: redis://:s3cretpw@10.0.0.9:6379/0 token=ABC123 code=654321"


class ResetProviderExceptionAtTheViewTests(_Base):
    def setUp(self):
        super().setUp()
        self.user = self.owner()
        gen = patch.object(owner_otp_service, "_generate_code", return_value="654321")
        gen.start()
        self.addCleanup(gen.stop)

    def exploding(self):
        return patch.object(owner_otp_service, "send_platform_otp", side_effect=RuntimeError(_SECRET_TEXT))

    def public_shape(self, client, response):
        page = client.get(response["Location"], HTTP_HOST=_HOST)
        html = re.sub(r'value="[^"]*"', "", page.content.decode())
        return response.status_code, response["Location"], re.sub(r"\s+", " ", html)

    def test_post_with_a_provider_exception_is_controlled_and_leaves_nothing_behind(self):
        before = {"users": User.objects.count(), "profiles": OwnerProfile.objects.count(), "stores": Store.objects.count()}
        with self.exploding() as send, self.assertLogs(level="DEBUG") as logs:
            logging.getLogger("probe").debug("probe")  # assertLogs needs at least one record
            response = self.request_reset()  # the Django test client re-raises any view exception
        send.assert_called_once()  # the provider WAS reached (eligible owner)…
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))  # …and it is no 500

        # no usable or pending reset challenge survives; a code cannot be verified
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone=_PHONE).exists())
        self.assertEqual(self.active_challenges().count(), 0)
        self.assertEqual(
            owner_otp_service.check_otp(phone=_PHONE, purpose=_RESET, code="654321"),
            owner_otp_service.OtpCheckResult.EXPIRED,
        )
        self.assertContains(self.verify("654321"), portal_views._RESET_OTP_FAILURE_MESSAGE)

        # no authorization, no login, nothing created or modified
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/reset-password/new/", HTTP_HOST=_HOST).status_code, 302)
        self.assertEqual(
            before, {"users": User.objects.count(), "profiles": OwnerProfile.objects.count(), "stores": Store.objects.count()},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(_OLD))
        self.assertEqual(SmsLog.objects.count(), 0)

        # logs: the exception CLASS is recorded, never its text, the code, credentials or the phone
        joined = "\n".join(logs.output)
        self.assertIn("RuntimeError", joined)
        for leaked in ("provider exploded", "s3cretpw", "ABC123", "654321", "10.0.0.9", _PHONE):
            self.assertNotIn(leaked, joined)

    def test_the_public_response_is_the_same_as_for_an_unknown_phone(self):
        with self.exploding():
            known_client = self.client_class()
            known = self.request_reset(_PHONE, client=known_client)
        unknown_client = self.client_class()
        unknown = self.request_reset(_UNKNOWN, client=unknown_client)
        strip = lambda text, phone: text.replace(phone, "PHONE")
        k, u = self.public_shape(known_client, known), self.public_shape(unknown_client, unknown)
        self.assertEqual(k[:2], u[:2])
        self.assertEqual(strip(k[2], _PHONE), strip(u[2], _UNKNOWN))

    def test_a_provider_exception_during_resend_is_equally_controlled(self):
        self.request_reset()  # a normal first send succeeds
        with self.exploding():
            response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
        self.assertContains(self.client.get("/verify/", HTTP_HOST=_HOST), portal_views._RESET_RESEND_NOTICE)
        self.assertNotIn("portal_password_reset_pending", self.client.session)
        # only the first (successful) challenge exists: the failed resend left nothing behind
        self.assertEqual(OwnerOtpChallenge.objects.filter(phone=_PHONE, purpose=_RESET).count(), 1)

    def test_keyboard_interrupt_and_system_exit_are_not_swallowed(self):
        for exc in (KeyboardInterrupt, SystemExit):
            with self.subTest(exc=exc.__name__):
                cache.clear()
                with patch.object(owner_otp_service, "send_platform_otp", side_effect=exc()):
                    with self.assertRaises(exc):
                        self.request_reset()
                self.assertEqual(self.active_challenges().count(), 0)  # an interrupted send is never verifiable
                self.assertEqual(
                    owner_otp_service.check_otp(phone=_PHONE, purpose=_RESET, code="654321"),
                    owner_otp_service.OtpCheckResult.EXPIRED,
                )

    def test_register_and_login_otp_behaviour_is_unchanged_by_the_reset_boundary(self):
        # the broad catch lives only in the reset helper: the generic OTP service still re-raises
        with self.exploding(), self.assertRaises(RuntimeError):
            owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="2.2.2.2")
