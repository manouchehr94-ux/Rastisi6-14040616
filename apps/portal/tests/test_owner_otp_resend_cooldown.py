"""Server-authoritative 120-second OTP resend cooldown.

The cooldown is enforced by ``owner_otp_service.request_otp`` itself (per (phone, purpose), under the same DB/advisory
lock as the per-phone request budget), so a client can never bypass it by POSTing ``/verify/resend/`` (or ``/login/`` /
``/register/``) directly. ``resend_timing()``, the page countdown and the error message all read the SAME constant,
``RESEND_COOLDOWN_SECONDS``.
"""

import re
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

import apps.portal as portal_app_module
from apps.portal.models import OwnerOtpChallenge, OwnerProfile
from apps.portal.services import owner_otp_service as svc
from apps.portal.tests._owner_signup import age_otp_cooldown
from apps.sms.services.backends import SmsSendResult
from django.contrib.auth import get_user_model

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09127770001"
_IP = "10.1.1.1"


class _Base:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.sent = []
        self.deliver = True
        patcher = patch.object(svc, "send_platform_otp", side_effect=self._send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        if not self.deliver:
            return SmsSendResult(success=False, error_message="down")
        return SmsSendResult(success=True, provider_ref_id="t")

    def request(self, phone=_PHONE, purpose="login", ip=_IP):
        svc.request_otp(phone=phone, purpose=purpose, client_ip=ip)


class CooldownConstantTests(TestCase):
    def test_the_cooldown_is_120_seconds_and_is_the_single_authority(self):
        self.assertEqual(svc.RESEND_COOLDOWN_SECONDS, 120)
        self.assertEqual(svc.OTP_TTL_SECONDS, 120)
        self.assertEqual(svc.RESEND_COOLDOWN_SECONDS, svc.OTP_TTL_SECONDS)  # derived, not a second literal

    def test_no_second_hardcoded_120_in_views_templates_or_js(self):
        base = Path(portal_app_module.__file__).resolve().parent
        for relative in (
            "views.py", "templates/portal/public/otp_verify.html", "static/portal/js/auth-forms.js",
        ):
            text = (base / relative).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?<![\w.])120(?![\w])", relative)
        self.assertNotIn("RESEND_UX_COOLDOWN_SECONDS", (base / "views.py").read_text(encoding="utf-8"))


class ServiceCooldownTests(_Base, TestCase):
    def test_the_first_request_works_and_an_immediate_second_one_is_rejected(self):
        self.request()
        with self.assertRaises(svc.OtpCooldownError) as ctx:
            self.request()
        self.assertTrue(isinstance(ctx.exception, svc.OtpRateLimitError))  # existing callers show it as a controlled error
        self.assertTrue(1 <= ctx.exception.retry_after <= svc.RESEND_COOLDOWN_SECONDS)
        self.assertIn(str(ctx.exception.retry_after), str(ctx.exception))
        self.assertEqual(len(self.sent), 1)  # no second SMS
        self.assertEqual(OwnerOtpChallenge.objects.count(), 1)  # no second challenge

    def test_boundary_119_seconds_is_still_blocked_and_120_is_allowed(self):
        self.request()
        age_otp_cooldown(_PHONE, seconds=119)
        with self.assertRaises(svc.OtpCooldownError) as ctx:
            self.request()
        self.assertEqual(ctx.exception.retry_after, 1)
        self.assertEqual(len(self.sent), 1)
        age_otp_cooldown(_PHONE, seconds=1)  # now exactly 120 seconds old
        self.request()
        self.assertEqual(len(self.sent), 2)

    def test_the_remaining_seconds_helper_at_the_exact_boundaries(self):
        self.request()
        challenge = OwnerOtpChallenge.objects.get()
        for age, expected in ((0, 120), (1, 119), (60, 60), (119, 1), (119.4, 1), (120, 0), (500, 0)):
            now = challenge.created_at + timedelta(seconds=age)
            with self.subTest(age=age):
                self.assertEqual(svc.resend_cooldown_remaining(_PHONE, "login", now=now), expected)

    def test_purposes_do_not_share_a_cooldown(self):
        self.request(purpose="login")
        for purpose in ("register", "password_reset", "step_up"):
            with self.subTest(purpose=purpose):
                self.request(purpose=purpose, ip=f"10.2.2.{len(self.sent)}")
        with self.assertRaises(svc.OtpCooldownError):
            self.request(purpose="login")

    def test_another_phone_is_not_affected(self):
        self.request(phone="09127770001")
        self.request(phone="09127770002")
        self.assertEqual(len(self.sent), 2)

    def test_a_failed_delivery_does_not_start_a_cooldown(self):
        self.deliver = False
        with self.assertRaises(svc.OtpDeliveryError):
            self.request()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)  # the reserved row is removed
        self.assertEqual(svc.resend_cooldown_remaining(_PHONE, "login"), 0)
        self.deliver = True
        self.request()  # immediately possible
        self.assertEqual(len(self.sent), 2)

    def test_a_provider_exception_does_not_start_a_cooldown(self):
        with patch.object(svc, "send_platform_otp", side_effect=RuntimeError("boom")), self.assertRaises(RuntimeError):
            self.request()
        self.assertEqual(svc.resend_cooldown_remaining(_PHONE, "login"), 0)
        self.request()

    def test_a_failed_resend_does_not_extend_or_reset_the_previous_cooldown(self):
        self.request()
        age_otp_cooldown(_PHONE, seconds=svc.RESEND_COOLDOWN_SECONDS + 1)
        self.deliver = False
        with self.assertRaises(svc.OtpDeliveryError):
            self.request()
        self.deliver = True
        self.request()  # the earlier code was already past its cooldown, so the retry is allowed at once
        self.assertEqual(len(self.sent), 3)

    def test_a_fresh_in_flight_request_blocks_but_a_stale_crashed_one_does_not(self):
        pending = OwnerOtpChallenge.objects.create(
            phone=_PHONE, purpose="login", code_hash="x", expires_at=svc.PENDING_EXPIRES_AT,
        )
        with self.assertRaises(svc.OtpCooldownError):  # a concurrent sender is still delivering
            self.request()
        age_otp_cooldown(_PHONE, seconds=svc.IN_FLIGHT_GRACE_SECONDS + 5)
        self.assertEqual(svc.resend_cooldown_remaining(_PHONE, "login"), 0)  # crashed worker: never verifiable, never locks
        self.request()
        self.assertEqual(len(self.sent), 1)

    def test_a_verified_code_never_blocks_the_next_request(self):
        self.request()
        self.assertTrue(svc.verify_otp(phone=_PHONE, purpose="login", code=self.sent[-1]["code"]))
        self.assertEqual(svc.resend_cooldown_remaining(_PHONE, "login"), 0)
        self.request()
        self.assertEqual(len(self.sent), 2)

    def test_a_blocked_request_spends_no_ip_budget_and_no_code_hash(self):
        self.request()
        with patch.object(svc, "charge_ip_budget") as charge, patch.object(svc, "make_password") as hasher:
            with self.assertRaises(svc.OtpCooldownError):
                self.request()
        charge.assert_not_called()
        hasher.assert_not_called()

    def test_the_phone_and_ip_budgets_still_apply_once_the_cooldown_has_passed(self):
        for _ in range(svc.MAX_REQUESTS_PER_PHONE_WINDOW):
            self.request()
            age_otp_cooldown(_PHONE)
        with self.assertRaises(svc.OtpRateLimitError) as ctx:
            self.request()
        self.assertNotIsInstance(ctx.exception, svc.OtpCooldownError)  # the 10-minute budget, not the cooldown

        for index in range(svc.IP_MAX_REQUESTS):
            self.request(phone=f"0912000{index:04d}", ip="9.9.9.9")
        with self.assertRaises(svc.OtpRateLimitError):
            self.request(phone="09120009999", ip="9.9.9.9")

    def test_a_race_that_passes_the_unlocked_pre_check_is_caught_under_the_lock(self):
        """Simulate two requests that both passed the fast pre-check: the loser is stopped by the re-check that runs
        inside the same advisory-locked transaction as the insert."""
        real_count = svc._recent_request_count

        def count_after_a_concurrent_winner(phone, purpose):
            if not OwnerOtpChallenge.objects.filter(phone=phone, purpose=purpose).exists():
                OwnerOtpChallenge.objects.create(
                    phone=phone, purpose=purpose, code_hash="winner",
                    expires_at=timezone.now() + timedelta(seconds=svc.OTP_TTL_SECONDS),
                )
                return 0  # what the loser's unlocked count saw before the winner committed
            return real_count(phone, purpose)

        with patch.object(svc, "_recent_request_count", side_effect=count_after_a_concurrent_winner):
            with self.assertRaises(svc.OtpCooldownError):
                self.request()
        self.assertEqual(self.sent, [])
        self.assertEqual(OwnerOtpChallenge.objects.count(), 1)  # only the winner's row

    def test_resend_timing_reads_the_same_authority(self):
        self.assertEqual(svc.resend_timing(phone=_PHONE, purpose="login")["resend_in"], 0)
        self.request()
        timing = svc.resend_timing(phone=_PHONE, purpose="login")
        self.assertTrue(svc.RESEND_COOLDOWN_SECONDS - 2 <= timing["resend_in"] <= svc.RESEND_COOLDOWN_SECONDS)
        self.assertEqual(timing["cooldown_seconds"], svc.RESEND_COOLDOWN_SECONDS)
        self.assertEqual(timing["resend_in"], svc.resend_cooldown_remaining(_PHONE, "login"))
        age_otp_cooldown(_PHONE, seconds=60)
        self.assertTrue(58 <= svc.resend_timing(phone=_PHONE, purpose="login")["resend_in"] <= 60)

    def test_the_raw_code_is_never_stored_or_logged_by_the_cooldown_path(self):
        self.request()
        code = self.sent[-1]["code"]
        with self.assertLogs("apps.portal.services.owner_otp_service", level="DEBUG") as logs:
            import logging

            logging.getLogger("apps.portal.services.owner_otp_service").debug("probe")
            with self.assertRaises(svc.OtpCooldownError):
                self.request()
        self.assertNotIn(code, " ".join(logs.output))
        self.assertNotIn(code, OwnerOtpChallenge.objects.get().code_hash)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ViewEnforcementTests(_Base, TestCase):
    """A direct POST is rejected by the SERVER — the UI countdown is only a display of the same number."""

    def start_registration(self, phone=_PHONE):
        return self.client.post(
            "/register/", {"full_name": "نام آزمایشی", "phone": phone, "accept_terms": "1"}, HTTP_HOST=_HOST,
        )

    def test_direct_resend_post_inside_the_cooldown_is_rejected_with_a_clear_message(self):
        self.assertEqual(self.start_registration()["Location"], "/verify/")
        for _ in range(3):  # hammering the endpoint never produces a second SMS
            response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
            self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
        self.assertEqual(len(self.sent), 1)
        page = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertContains(page, "ثانیه‌یِ دیگر صبر کنید")
        self.assertNotContains(page, "کد جدید ارسال شد")

    def test_resend_works_once_the_cooldown_has_elapsed_and_is_not_possible_at_119(self):
        self.start_registration()
        age_otp_cooldown(_PHONE, seconds=svc.RESEND_COOLDOWN_SECONDS - 1)
        self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.sent), 1)
        age_otp_cooldown(_PHONE, seconds=1)
        self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.sent), 2)
        self.assertContains(self.client.get("/verify/", HTTP_HOST=_HOST), "کد جدید ارسال شد")

    def test_resubmitting_the_register_or_login_form_cannot_bypass_the_cooldown(self):
        self.start_registration()
        again = self.start_registration()
        self.assertEqual(again.status_code, 200)
        self.assertContains(again, "ثانیه‌یِ دیگر صبر کنید")
        self.assertEqual(len(self.sent), 1)
        login = self.client.post("/login/", {"phone": "09127770003"}, HTTP_HOST=_HOST)
        self.assertEqual(login["Location"], "/verify/")
        cache.clear()
        self.client.post("/logout/", HTTP_HOST=_HOST)
        retry = self.client.post("/login/", {"phone": "09127770003"}, HTTP_HOST=_HOST)
        self.assertEqual(retry.status_code, 200)
        self.assertContains(retry, "ثانیه‌یِ دیگر صبر کنید")
        self.assertEqual([m["to"] for m in self.sent].count("09127770003"), 1)

    def test_the_verify_page_states_when_resend_becomes_available_from_the_server_value(self):
        self.start_registration()
        html = self.client.get("/verify/", HTTP_HOST=_HOST).content.decode()
        match = re.search(r'data-resend-in="(\d+)"', html)
        self.assertTrue(svc.RESEND_COOLDOWN_SECONDS - 3 <= int(match.group(1)) <= svc.RESEND_COOLDOWN_SECONDS)
        self.assertIn("ارسال دوباره‌ی کد پس از", html)
        self.assertIn('data-cooldown="120"', html)  # rendered from the service constant, not typed in the template
        age_otp_cooldown(_PHONE)
        html = self.client.get("/verify/", HTTP_HOST=_HOST).content.decode()
        self.assertIn('data-resend-in="0"', html)
        self.assertNotIn("ارسال دوباره‌ی کد پس از", html)

    def test_a_failed_first_delivery_does_not_lock_the_visitor_out(self):
        self.deliver = False
        response = self.start_registration()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ارسال کد تأیید موقتاً انجام نشد")
        self.deliver = True
        self.assertEqual(self.start_registration()["Location"], "/verify/")

    def test_the_reset_flow_judges_the_cooldown_from_the_session_so_it_cannot_reveal_an_account(self):
        owner = User.objects.create_user(username=_PHONE)
        owner.set_password("Old-pass-word-77!")
        owner.save()
        OwnerProfile.objects.create(user=owner, phone=_PHONE, full_name="Owner")
        outcomes = []
        for phone in (_PHONE, "09127779999"):  # a real owner and an unknown number
            self.client = self.client_class()
            cache.clear()
            self.client.post("/reset-password/", {"phone": phone}, HTTP_HOST=_HOST)
            sent_before = len(self.sent)
            response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
            self.assertEqual((response.status_code, response["Location"]), (302, "/verify/"))
            self.assertEqual(len(self.sent), sent_before)  # the cooldown held for both…
            page = self.client.get("/verify/", HTTP_HOST=_HOST)
            self.assertContains(page, "ثانیه‌یِ دیگر صبر کنید")  # …with the same, account-independent wording
            html = page.content.decode()
            seconds = int(re.search(r'data-resend-in="(\d+)"', html).group(1))
            self.assertTrue(svc.RESEND_COOLDOWN_SECONDS - 3 <= seconds <= svc.RESEND_COOLDOWN_SECONDS)
            outcomes.append(re.sub(r"\d+", "N", re.search(r'class="p-alert[^"]*"[^>]*>([^<]+)<', html).group(1)))
        self.assertEqual(outcomes[0], outcomes[1])


@unittest.skipUnless(connection.vendor == "postgresql", "real-thread race tests need PostgreSQL advisory locks")
class ConcurrentCooldownTests(_Base, TransactionTestCase):
    def test_parallel_requests_for_one_phone_and_purpose_send_exactly_one_code(self):
        barrier = threading.Barrier(8)
        results = [None] * 8

        def worker(index):
            try:
                barrier.wait(timeout=30)
                self.request(ip=f"10.9.9.{index}")
                results[index] = "sent"
            except svc.OtpCooldownError:
                results[index] = "cooldown"
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
        self.assertEqual(results.count("sent"), 1)
        self.assertEqual(results.count("cooldown"), 7)
        self.assertEqual(len(self.sent), 1)
