"""Server-side math CAPTCHA on the public account and contact forms (replaces Cloudflare Turnstile).

Covered: rendering (both public designs, no external widget, answer never in the page), every protected form (success, wrong answer,
missing answer/token, expiry, reuse, other session, other form), digit scripts, concurrency of the single-use guarantee, budgets,
shared-store outage (fail closed), production runtime guard, and that the existing OTP/CSRF/rate-limit controls still apply.
No SMS, mail or network call is made: the OTP provider is always replaced.
"""

import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import caches
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitUnavailable
from apps.portal.models import ContactMessage, OwnerOtpChallenge, OwnerProfile
from apps.portal.services import captcha_service, owner_auth_service, owner_otp_service
from apps.portal.tests import _captcha as C
from apps.sms.services.backends import SmsSendResult

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09121230001"
_PASSWORD = "a-very-strong-pass-1"
_CONTACT = {"full_name": "Visitor", "email": "visitor@example.com", "subject": "Hello", "message": "A genuine question about plans."}


class _Base(TestCase):
    def setUp(self):
        super().setUp()
        C.reset_store()
        self.addCleanup(C.reset_store)
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._fake_send)
        patcher.start()
        self.addCleanup(patcher.stop)
        cooldown = patch.object(owner_otp_service, "RESEND_COOLDOWN_SECONDS", 0)
        cooldown.start()
        self.addCleanup(cooldown.stop)

    def _fake_send(self, *, to, code, purpose, expire_minutes, **_):
        self.sent.append({"to": to, "code": code, "purpose": purpose})
        return SmsSendResult(success=True, provider_ref_id="t")

    def fields(self, path, action, client=None, **kw):
        return C.solve(client or self.client, path, action, _HOST, **kw)

    def owner(self, phone=_PHONE, password=_PASSWORD):
        user = User.objects.create_user(username=phone)
        user.set_password(password)
        user.save()
        OwnerProfile.objects.create(user=user, phone=phone, full_name="Owner")
        return user

    # one callable per protected form: (path to GET, action, POST callable(client, captcha_fields) -> response)
    def post_register(self, client, f):
        return client.post("/register/", {"full_name": "سارا احمدی", "phone": _PHONE, "accept_terms": "1", **f}, HTTP_HOST=_HOST)

    def post_login_otp(self, client, f):
        return client.post("/login/", {"phone": _PHONE, **f}, HTTP_HOST=_HOST)

    def post_login_password(self, client, f):
        return client.post("/login/password/", {"identifier": _PHONE, "password": _PASSWORD, **f}, HTTP_HOST=_HOST)

    def post_reset(self, client, f):
        return client.post("/reset-password/", {"phone": _PHONE, **f}, HTTP_HOST=_HOST)

    def post_contact(self, client, f):
        return client.post("/contact/", {**_CONTACT, **f}, HTTP_HOST=_HOST)

    FORMS = (
        ("register", "/register/", "post_register"),
        ("login_otp", "/login/", "post_login_otp"),
        ("login_password", "/login/", "post_login_password"),
        ("password_reset", "/reset-password/", "post_reset"),
        ("contact", "/contact/", "post_contact"),
    )

    def effects(self):
        """Everything a protected action could do: SMS sent, challenge rows, contact rows, mail, login."""
        return (len(self.sent), OwnerOtpChallenge.objects.count(), ContactMessage.objects.count(), len(mail.outbox),
                "_auth_user_id" in self.client.session)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class RenderingTests(_Base):
    PAGES = (("/register/", ("register",)), ("/login/", ("login_password", "login_otp")),
             ("/reset-password/", ("password_reset",)), ("/contact/", ("contact",)))

    def test_every_form_shows_a_two_digit_question_and_no_external_widget_in_both_designs(self):
        for design in ("v2", "legacy"):
            for path, actions in self.PAGES:
                with self.subTest(design=design, path=path), override_settings(PUBLIC_SITE_FORCE_DESIGN=design):
                    page = self.client.get(path, HTTP_HOST=_HOST)
                    self.assertEqual(page.status_code, 200)
                    html = page.content.decode()
                    for action in actions:
                        left, right, token = C.read_challenge(html, action)
                        self.assertTrue(10 <= left <= 49 and 10 <= right <= 49)
                        self.assertGreaterEqual(len(token), 16)
                    for banned in ("cloudflare", "turnstile", "cf-turnstile", "challenges."):
                        self.assertNotIn(banned, html.lower())
                    self.assertIn('inputmode="numeric"', html)
                    self.assertIn("= ؟", html)
                    # Persian digits in the visible question
                    self.assertRegex(html, r'<bdi dir="ltr">[۱-۴][۰-۹] \+ [۱-۴][۰-۹] = ؟</bdi>')

    def test_the_answer_and_its_digest_are_never_in_the_page(self):
        page = self.client.get("/register/", HTTP_HOST=_HOST)
        html = page.content.decode()
        left, right, token = C.read_challenge(html, "register")
        total = left + right
        # the sum appears nowhere as a value, data attribute, script or comment
        for form in (str(total), str(total).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))):
            self.assertNotRegex(html, rf'(value|data-[a-z-]+|content)="{form}"')
        self.assertNotIn("<script>", html.split("captcha")[1][:3000])
        # the stored challenge holds a digest, not the number, and the token is not derived from the answer
        stored = caches["ratelimit"].get(captcha_service._storage_key(token))
        self.assertEqual(set(stored), {"h", "s", "a", "t"})
        self.assertNotIn(total, stored.values())
        self.assertNotIn(str(total), stored.values())
        self.assertRegex(stored["h"], r"^[0-9a-f]{40}$")            # an HMAC digest, not the number
        self.assertNotIn(stored["h"], html)                          # and the digest is not in the page either

    def test_each_render_issues_a_fresh_token_and_the_pages_are_not_cacheable(self):
        a = C.read_challenge(self.client.get("/register/", HTTP_HOST=_HOST).content.decode(), "register")[2]
        page = self.client.get("/register/", HTTP_HOST=_HOST)
        b = C.read_challenge(page.content.decode(), "register")[2]
        self.assertNotEqual(a, b)
        for path in ("/register/", "/login/", "/reset-password/", "/contact/"):
            self.assertIn("no-store", self.client.get(path, HTTP_HOST=_HOST)["Cache-Control"])

    def test_the_two_login_forms_get_independent_questions(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertNotEqual(C.read_challenge(html, "login_password")[2], C.read_challenge(html, "login_otp")[2])

    @override_settings(RASTISI_CAPTCHA_ENABLED=False)
    def test_disabled_in_development_renders_nothing(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertNotIn("captcha", html)

    def test_captcha_markup_is_rtl_friendly(self):
        html = self.client.get("/register/", HTTP_HOST=_HOST).content.decode()
        self.assertIn('dir="ltr"', html)           # the numeric expression and input are isolated LTR inside the RTL form
        self.assertIn('<bdi dir="ltr">', html)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class ProtectedFormsTests(_Base):
    def test_a_correct_answer_lets_each_form_proceed(self):
        for action, path, poster in self.FORMS:
            with self.subTest(action=action):
                C.reset_store()
                OwnerOtpChallenge.objects.all().delete()
                ContactMessage.objects.all().delete()
                self.sent.clear()
                client = Client()
                if action in {"login_otp", "login_password", "password_reset"}:
                    User.objects.filter(username=_PHONE).delete()
                    self.owner()
                response = getattr(self, poster)(client, self.fields(path, action, client))
                if action == "contact":
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(ContactMessage.objects.count(), 1)
                elif action == "login_password":
                    self.assertEqual(response.status_code, 302)
                    self.assertIn("_auth_user_id", client.session)
                else:
                    self.assertRedirects(response, "/verify/", fetch_redirect_response=False)
                    self.assertEqual(len(self.sent), 1)

    def test_a_wrong_answer_does_nothing_and_shows_the_standard_message(self):
        self.owner()
        for action, path, poster in self.FORMS:
            with self.subTest(action=action):
                before = self.effects()
                client = Client()
                response = getattr(self, poster)(client, self.fields(path, action, client, answer_delta=1))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
                self.assertEqual(self.effects(), before)
                self.assertNotIn("_auth_user_id", client.session)

    def test_a_missing_answer_or_token_does_nothing(self):
        self.owner()
        for action, path, poster in self.FORMS:
            with self.subTest(action=action):
                before = self.effects()
                for label in ("no fields", "no answer", "empty answer", "no token", "garbage token", "short token"):
                    with self.subTest(label=label):
                        C.reset_store()                      # the per-endpoint limits (5 per 10 min) would otherwise stop the sixth try
                        client = Client()
                        good = self.fields(path, action, client)
                        f = {
                            "no fields": {},
                            "no answer": {"captcha_token": good["captcha_token"]},
                            "empty answer": {**good, "captcha_answer": ""},
                            "no token": {"captcha_answer": good["captcha_answer"]},
                            "garbage token": {**good, "captcha_token": "x" * 500},
                            "short token": {**good, "captcha_token": "abc"},
                        }[label]
                        response = getattr(self, poster)(client, f)
                        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
                self.assertEqual(self.effects(), before)

    def test_a_wrong_answer_burns_the_token_so_the_right_answer_for_it_no_longer_works(self):
        client = Client()
        good = self.fields("/contact/", "contact", client)
        wrong = {**good, "captcha_answer": str(int(good["captcha_answer"]) + 1)}
        self.post_contact(client, wrong)
        response = self.post_contact(client, good)
        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_an_invalid_form_does_not_pass_the_captcha_check_and_is_never_a_free_pass(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        response = client.post("/contact/", {"full_name": "", "email": "bad", "subject": "", "message": "", **f}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        # a fresh question is rendered with the re-displayed form
        self.assertIn("captcha_token", response.content.decode())

    def test_a_new_question_is_shown_after_every_failure(self):
        client = Client()
        f = self.fields("/contact/", "contact", client, answer_delta=3)
        response = self.post_contact(client, f)
        html = response.content.decode()
        new_token = C.read_challenge(html, "contact")[2]
        self.assertNotEqual(new_token, f["captcha_token"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class SingleUseSessionAndActionTests(_Base):
    def test_a_solved_challenge_cannot_be_replayed(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        self.assertEqual(self.post_contact(client, f).status_code, 302)
        for _ in range(3):
            response = self.post_contact(client, f)
            self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_a_replay_from_another_client_or_session_is_rejected(self):
        a, b = Client(), Client()
        f = self.fields("/contact/", "contact", a)
        b.get("/contact/", HTTP_HOST=_HOST)               # B has its own session
        response = self.post_contact(b, f)
        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)
        # ... and it is burned: even the legitimate owner of the token cannot use it afterwards
        self.assertContains(self.post_contact(a, f), captcha_service.PUBLIC_ERROR_MESSAGE)

    def test_a_client_without_any_session_cannot_use_a_token(self):
        a = Client()
        f = self.fields("/contact/", "contact", a)
        response = self.post_contact(Client(), f)
        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_a_token_for_one_form_is_rejected_on_another(self):
        self.owner()
        client = Client()
        html = client.get("/login/", HTTP_HOST=_HOST).content.decode()
        left, right, token = C.read_challenge(html, "login_otp")
        f = {"captcha_token": token, "captcha_answer": str(left + right)}
        # the OTP-form token on the password-login form: refused, no authentication
        response = self.post_login_password(client, f)
        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertNotIn("_auth_user_id", client.session)
        # and it is burned
        self.assertContains(self.post_login_otp(client, f), captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(self.sent, [])

    def test_an_expired_challenge_is_rejected(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        stored_at = caches["ratelimit"].get(captcha_service._storage_key(f["captcha_token"]))["t"]
        with patch.object(captcha_service.time, "time", return_value=stored_at + 301):
            response = self.post_contact(client, f)
        self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_the_cache_entry_itself_expires(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        caches["ratelimit"].delete(captcha_service._storage_key(f["captcha_token"]))   # what the store does at TTL
        self.assertContains(self.post_contact(client, f), captcha_service.PUBLIC_ERROR_MESSAGE)

    @override_settings(RASTISI_CAPTCHA_TTL_SECONDS=60)
    def test_the_lifetime_is_configurable(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        stored_at = caches["ratelimit"].get(captcha_service._storage_key(f["captcha_token"]))["t"]
        with patch.object(captcha_service.time, "time", return_value=stored_at + 61):
            self.assertContains(self.post_contact(client, f), captcha_service.PUBLIC_ERROR_MESSAGE)
        f2 = self.fields("/contact/", "contact", client)
        self.assertEqual(self.post_contact(client, f2).status_code, 302)


class DigitScriptTests(SimpleTestCase):
    def test_persian_arabic_and_ascii_digits_are_equivalent(self):
        for raw in ("49", "۴۹", "٤٩", " ۴۹ ", "4۹", "\u200f۴۹\u200c", "٤9", "۴٩\n"):
            with self.subTest(raw=raw):
                self.assertEqual(captcha_service.normalize_answer(raw), 49)

    def test_everything_else_is_rejected(self):
        for raw in ("", " ", "abc", "4a", "-49", "+49", "49.0", "4,9", "٤٫٩", "۴ ۹۰۰۰", "١٢٣٤", "²", "٪", "49" * 20, None, "۴۹۹۹"):
            with self.subTest(raw=raw):
                self.assertIsNone(captcha_service.normalize_answer(raw))


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class DigitScriptEndToEndTests(_Base):
    def test_each_script_is_accepted_by_the_real_form(self):
        to = {"persian": "۰۱۲۳۴۵۶۷۸۹", "arabic": "٠١٢٣٤٥٦٧٨٩", "ascii": "0123456789"}
        for name, digits in to.items():
            with self.subTest(script=name):
                ContactMessage.objects.all().delete()
                client = Client()
                f = self.fields("/contact/", "contact", client)
                f["captcha_answer"] = "".join(digits[int(ch)] for ch in f["captcha_answer"])
                self.assertEqual(self.post_contact(client, f).status_code, 302)
                self.assertEqual(ContactMessage.objects.count(), 1)


def _request(session_key="s-1", ip="203.0.113.7", **post):
    request = RequestFactory().post("/x/", post, REMOTE_ADDR=ip)
    request.session = SimpleNamespace(session_key=session_key, create=lambda: None)
    return request


@override_settings(**C.ENABLED)
class ServiceConcurrencyTests(SimpleTestCase):
    """No database: the store is the process-local cache standing in for Redis; atomicity is in ``cache.delete()``."""

    def setUp(self):
        C.reset_store()
        self.addCleanup(C.reset_store)

    def _issued(self, action="contact", session_key="s-1"):
        data = captcha_service.issue(_request(session_key), action)
        stored = caches["ratelimit"].get(captcha_service._storage_key(data["token"]))
        # derive the answer the way a visitor does: from the two shown operands
        left, right = (int(str(data[k]).translate(C._PERSIAN)) for k in ("left", "right"))
        self.assertIsNotNone(stored)
        return data["token"], left + right

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)      # the per-IP budget is tested separately
    def test_many_simultaneous_submissions_of_one_solved_challenge_pass_exactly_once(self):
        for round_ in range(5):
            token, answer = self._issued()
            results, barrier = [], threading.Barrier(16)

            def work():
                barrier.wait()
                results.append(captcha_service.verify_request(
                    _request(captcha_token=token, captcha_answer=str(answer)), action="contact").success)

            threads = [threading.Thread(target=work) for _ in range(16)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(results.count(True), 1, f"round {round_}: {results}")

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)
    def test_simultaneous_wrong_and_right_answers_never_let_a_wrong_one_through(self):
        token, answer = self._issued()
        results, barrier = [], threading.Barrier(12)

        def work(i):
            barrier.wait()
            guess = answer if i == 0 else answer + 1 + i
            results.append((i, captcha_service.verify_request(
                _request(captcha_token=token, captcha_answer=str(guess)), action="contact").success))

        threads = [threading.Thread(target=work, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertTrue(all(i == 0 for i, ok in results if ok))
        self.assertLessEqual(sum(ok for _, ok in results), 1)

    def test_simultaneous_issuance_makes_distinct_tokens(self):
        tokens, barrier = [], threading.Barrier(20)

        def work():
            barrier.wait()
            tokens.append(captcha_service.issue(_request("s-9"), "contact")["token"])

        threads = [threading.Thread(target=work) for _ in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(set(tokens)), 20)


@override_settings(**C.ENABLED)
class BudgetTests(SimpleTestCase):
    def setUp(self):
        C.reset_store()
        self.addCleanup(C.reset_store)

    def test_verification_attempts_are_budgeted_per_client_ip(self):
        with patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 3):
            outcomes = [captcha_service.verify_request(_request(captcha_token="x" * 20, captcha_answer="1"), action="contact")
                        for _ in range(5)]
        self.assertEqual([o.error_code for o in outcomes], ["unknown-or-used-token"] * 3 + ["rate-limited"] * 2)
        self.assertEqual(outcomes[-1].message, captcha_service.RATE_LIMITED_MESSAGE)

    def test_another_ip_is_not_affected(self):
        with patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 1):
            captcha_service.verify_request(_request(ip="198.51.100.1", captcha_token="x" * 20), action="contact")
            blocked = captcha_service.verify_request(_request(ip="198.51.100.1", captcha_token="x" * 20), action="contact")
            other = captcha_service.verify_request(_request(ip="198.51.100.2", captcha_token="x" * 20), action="contact")
        self.assertEqual(blocked.error_code, "rate-limited")
        self.assertNotEqual(other.error_code, "rate-limited")

    def test_issuing_questions_is_budgeted_and_fails_closed(self):
        with patch.object(captcha_service, "ISSUE_MAX", 2):
            first = [captcha_service.issue(_request(), "contact") for _ in range(2)]
            third = captcha_service.issue(_request(), "contact")
        self.assertTrue(all(not d["unavailable"] for d in first))
        self.assertTrue(third["unavailable"])
        self.assertNotIn("token", third)

    def test_unknown_actions_are_a_programming_error(self):
        with self.assertRaises(ValueError):
            captcha_service.issue(_request(), "nope")
        with self.assertRaises(ValueError):
            captcha_service.verify_request(_request(), action="nope")


class _DownStore:
    """A shared store whose every operation fails the way a lost Redis connection does (no secret in the message)."""

    def __getattr__(self, name):
        def fail(*a, **k):
            raise ConnectionError("redis://:topsecret@10.0.0.9:6379/0 unreachable")
        return fail


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class SharedStoreOutageTests(_Base):
    def _down(self):
        return patch.object(captcha_service, "_store", return_value=_DownStore())

    def test_pages_still_render_and_say_the_check_is_unavailable_without_a_500(self):
        with self._down():
            for path in ("/register/", "/login/", "/reset-password/", "/contact/"):
                with self.subTest(path=path):
                    page = self.client.get(path, HTTP_HOST=_HOST)
                    self.assertEqual(page.status_code, 200)
                    self.assertContains(page, "سرویس تأیید امنیتی موقتاً در دسترس نیست")
                    self.assertNotIn("topsecret", page.content.decode())
                    self.assertNotIn('name="captcha_token"', page.content.decode())

    def test_a_submission_during_an_outage_is_refused_and_nothing_happens(self):
        self.owner()
        good = {}
        for action, path, poster in self.FORMS:      # questions were issued while the store was still healthy
            good[action] = self.fields(path, action, Client())
        before = self.effects()
        with self._down():
            for action, path, poster in self.FORMS:
                with self.subTest(action=action):
                    response = getattr(self, poster)(self.client, good[action])
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertEqual(self.effects(), before)

    def test_a_down_rate_limit_counter_also_fails_closed(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        with patch.object(captcha_service, "enforce_rate_limit", side_effect=RateLimitUnavailable(UNAVAILABLE_MESSAGE)):
            response = self.post_contact(client, f)
            page = client.get("/contact/", HTTP_HOST=_HOST)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(page, "سرویس تأیید امنیتی موقتاً در دسترس نیست")

    def test_the_service_never_leaks_connection_details_into_logs_or_results(self):
        with self._down(), self.assertLogs("apps.portal.services.captcha_service", level="ERROR") as logs:
            result = captcha_service.verify_request(
                _request(captcha_token="t" * 24, captcha_answer="5"), action="contact")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "store-unavailable")
        self.assertNotIn("topsecret", "\n".join(logs.output) + result.message)

    def test_recovery_after_the_outage_needs_no_restart(self):
        with self._down():
            self.assertTrue(captcha_service.issue(_request(), "contact")["unavailable"])
        data = captcha_service.issue(_request(), "contact")
        self.assertFalse(data["unavailable"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ProductionRuntimeGuardTests(_Base):
    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_CAPTCHA_ENABLED=False)
    def test_production_with_the_captcha_off_can_never_succeed(self):
        result = captcha_service.verify_request(_request(), action="login_password")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "captcha-misconfigured")
        self.owner()
        with patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
            response = self.post_login_password(self.client, {})
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        authenticate.assert_not_called()

    @override_settings(RASTISI_PRODUCTION_MODE=False, RASTISI_CAPTCHA_ENABLED=False)
    def test_development_may_run_without_it(self):
        self.assertTrue(captcha_service.verify_request(_request(), action="contact").success)
        self.assertEqual(self.post_contact(self.client, {}).status_code, 302)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class ExistingProtectionsStillApplyTests(_Base):
    def test_csrf_is_still_enforced_and_a_forged_post_does_not_even_consume_the_token(self):
        client = Client(enforce_csrf_checks=True)
        f = self.fields("/contact/", "contact", client)
        forged = client.post("/contact/", {**_CONTACT, **f}, HTTP_HOST=_HOST)
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertIsNotNone(caches["ratelimit"].get(captcha_service._storage_key(f["captcha_token"])))

    def test_the_per_ip_otp_budget_and_phone_budget_still_cap_requests_after_a_solved_captcha(self):
        results = []
        for index in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW + 2):
            f = self.fields("/register/", "register")
            response = self.post_register(self.client, f)
            results.append(response.status_code)
        # registrations past the per-phone cap are refused by the OTP service, not by the CAPTCHA
        self.assertLessEqual(len(self.sent), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)
        self.assertEqual(results[-1], 200)

    def test_the_existing_login_ip_limit_still_applies(self):
        self.owner()
        client = Client()
        for i in range(17):
            f = self.fields("/login/", "login_password", client)
            r = client.post("/login/password/", {"identifier": f"nobody{i}@example.com", "password": "bad", **f}, HTTP_HOST=_HOST)
        self.assertContains(r, "بیش از حد مجاز")

    def test_a_failed_captcha_does_not_spend_the_identifier_login_budget(self):
        from apps.portal import views as portal_views

        self.owner()
        for i in range(portal_views.LOGIN_IDENTIFIER_MAX_ATTEMPTS + 3):
            client = Client()
            f = self.fields("/login/", "login_password", client, answer_delta=1)
            response = self.post_login_password(client, f)
            self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
        client = Client()
        f = self.fields("/login/", "login_password", client)
        self.assertEqual(self.post_login_password(client, f).status_code, 302)

    def test_the_otp_resend_and_verify_pages_do_not_need_a_captcha(self):
        self.post_register(self.client, self.fields("/register/", "register"))
        response = self.client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertRedirects(response, "/verify/", fetch_redirect_response=False)
        self.assertEqual(len(self.sent), 2)
        page = self.client.get("/verify/", HTTP_HOST=_HOST)
        self.assertNotIn("captcha", page.content.decode())

    def test_the_full_sign_in_journey_with_otp_works_end_to_end(self):
        self.post_register(self.client, self.fields("/register/", "register"))
        code = self.sent[-1]["code"]
        response = self.client.post("/verify/", {"code": code}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("captcha", response.get("Location", ""))


# ---------------------------------------------------------------------------
# The same guarantees against a REAL Redis (opt-in: RASTISI_TEST_REDIS_URL=redis://127.0.0.1:<port>/<db>, a disposable server)
# ---------------------------------------------------------------------------

_REDIS_URL = os.environ.get("RASTISI_TEST_REDIS_URL", "")
_REDIS_BACKEND = "django.core.cache.backends.redis.RedisCache"
_LOCMEM = "django.core.cache.backends.locmem.LocMemCache"


def _caches(url):
    return {"default": {"BACKEND": _LOCMEM, "LOCATION": "captcha-default"}, "ratelimit": {"BACKEND": _REDIS_BACKEND, "LOCATION": url}}


@unittest.skipUnless(_REDIS_URL, "real-Redis CAPTCHA tests need RASTISI_TEST_REDIS_URL")
@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class RealRedisTests(_Base):
    def setUp(self):
        self._cfg = override_settings(CACHES=_caches(_REDIS_URL))
        self._cfg.enable()
        self.addCleanup(self._cfg.disable)
        super().setUp()                                   # flushes the (Redis) store through reset_store()

    def test_the_whole_flow_and_replay_protection_work_on_redis(self):
        client = Client()
        f = self.fields("/contact/", "contact", client)
        self.assertEqual(self.post_contact(client, f).status_code, 302)
        self.assertContains(self.post_contact(client, f), captcha_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_the_stored_challenge_expires_in_redis_itself(self):
        data = captcha_service.issue(_request(), "contact")
        store = caches["ratelimit"]
        ttl = store.ttl(captcha_service._storage_key(data["token"])) if hasattr(store, "ttl") else None
        if ttl is None:
            import redis

            ttl = redis.Redis.from_url(_REDIS_URL).ttl(store.make_and_validate_key(captcha_service._storage_key(data["token"])))
        self.assertTrue(0 < ttl <= 300, ttl)

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)
    def test_simultaneous_submissions_pass_exactly_once_on_redis(self):
        for _ in range(5):
            data = captcha_service.issue(_request(), "contact")
            answer = sum(int(str(data[k]).translate(C._PERSIAN)) for k in ("left", "right"))
            results, barrier = [], threading.Barrier(16)

            def work():
                barrier.wait()
                results.append(captcha_service.verify_request(
                    _request(captcha_token=data["token"], captcha_answer=str(answer)), action="contact").success)

            threads = [threading.Thread(target=work) for _ in range(16)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(results.count(True), 1, results)

    def test_an_unreachable_redis_fails_closed_with_no_secret_in_the_output(self):
        with override_settings(CACHES=_caches("redis://:topsecretpw@127.0.0.1:1/0")):
            page = self.client.get("/contact/", HTTP_HOST=_HOST)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "سرویس تأیید امنیتی موقتاً در دسترس نیست")
            self.assertNotContains(page, "topsecretpw")
            response = self.post_contact(self.client, {"captcha_token": "t" * 24, "captcha_answer": "5"})
            self.assertContains(response, UNAVAILABLE_MESSAGE)
            self.assertNotContains(response, "topsecretpw")
        self.assertEqual(ContactMessage.objects.count(), 0)
