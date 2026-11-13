"""Local ALTCHA regressions. Historical module path retained for downstream test labels.

All former security guarantees remain tested; arithmetic/digit assertions are
replaced by real PoW, strict payload and algorithm-tampering assertions.
"""

import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import caches
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)

from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitUnavailable
from apps.portal.models import ContactMessage, OwnerOtpChallenge, OwnerProfile
from apps.portal.services import captcha_service, owner_auth_service, owner_otp_service
from apps.portal.tests import _captcha as C
from apps.sms.services.backends import SmsSendResult

User = get_user_model()
_HOST = "rastisi.localhost"
_PHONE = "09121230001"
_PASSWORD = "a-very-strong-pass-1"
_CONTACT = {
    "full_name": "Visitor",
    "email": "visitor@example.com",
    "subject": "Hello",
    "message": "A genuine question about plans.",
}


class _Base(TestCase):
    def setUp(self):
        super().setUp()
        C.reset_store()
        self.addCleanup(C.reset_store)
        self.sent = []
        patcher = patch.object(
            owner_otp_service, "send_platform_otp", side_effect=self._fake_send
        )
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
        return client.post(
            "/register/",
            {"full_name": "سارا احمدی", "phone": _PHONE, "accept_terms": "1", **f},
            HTTP_HOST=_HOST,
        )

    def post_login_otp(self, client, f):
        return client.post("/login/", {"phone": _PHONE, **f}, HTTP_HOST=_HOST)

    def post_login_password(self, client, f):
        return client.post(
            "/login/password/",
            {"identifier": _PHONE, "password": _PASSWORD, **f},
            HTTP_HOST=_HOST,
        )

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
        return (
            len(self.sent),
            OwnerOtpChallenge.objects.count(),
            ContactMessage.objects.count(),
            len(mail.outbox),
            "_auth_user_id" in self.client.session,
        )


import base64
import copy
import json
from bs4 import BeautifulSoup


def _request(session_key="s-1", ip="203.0.113.7", **post):
    request = RequestFactory().post("/x/", post, REMOTE_ADDR=ip)
    request.session = SimpleNamespace(session_key=session_key, create=lambda: None)
    return request


def _issued(action="contact", session="s-1", wrong=False):
    data = captcha_service.issue(_request(session), action)
    return data, C.solve_data(data["challenge"], answer_delta=int(wrong))


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class RenderingTests(_Base):
    PAGES = (
        ("/register/", ("register",)),
        ("/login/", ("login_password", "login_otp")),
        ("/reset-password/", ("password_reset",)),
        ("/contact/", ("contact",)),
    )

    def test_every_form_shows_a_local_checkbox_in_both_designs(self):
        for design in ("v2", "legacy"):
            for path, actions in self.PAGES:
                with self.subTest(design=design, path=path), override_settings(
                    PUBLIC_SITE_FORCE_DESIGN=design
                ):
                    response = self.client.get(path, HTTP_HOST=_HOST)
                    self.assertEqual(response.status_code, 200)
                    soup = BeautifulSoup(response.content, "html.parser")
                    for action in actions:
                        widget = soup.find("altcha-widget", id="captcha-" + action)
                        self.assertIsNotNone(widget)
                        self.assertEqual(widget["type"], "checkbox")
                        self.assertEqual(widget["language"], "fa")
                        self.assertEqual(widget["name"], "altcha")
                        self.assertTrue(
                            widget["challenge"].startswith("/security/altcha/")
                        )
                    html = response.content.decode().lower()
                    for banned in (
                        "turnstile",
                        "cloudflare",
                        "cdn.jsdelivr",
                        "unpkg.com",
                        "captcha_answer",
                        "captcha-question",
                    ):
                        self.assertNotIn(banned, html)
                    self.assertEqual(
                        len(
                            soup.find_all(
                                "script", src=lambda s: s and "altcha-forms.js" in s
                            )
                        ),
                        1,
                    )

    def test_issuer_exposes_no_solution_signing_secret_or_session_key(self):
        challenge = C.challenge_for(self.client, "/register/", "register", _HOST)
        self.assertEqual(set(challenge), {"parameters", "signature"})
        self.assertEqual(challenge["parameters"]["algorithm"], "PBKDF2/SHA-256")
        self.assertNotIn("solution", challenge)
        encoded = json.dumps(challenge)
        self.assertNotIn(self.client.session.session_key, encoded)
        self.assertNotIn(captcha_service._secret("sign").hex(), encoded)
        stored = caches["ratelimit"].get(
            captcha_service._storage_key(challenge["parameters"]["nonce"])
        )
        self.assertEqual(set(stored), {"s", "a", "t", "c", "m"})
        self.assertNotIn("derivedKey", json.dumps(stored))

    def test_fresh_challenges_and_pages_are_not_cacheable(self):
        a = C.challenge_for(self.client, "/register/", "register", _HOST)
        b = C.challenge_for(self.client, "/register/", "register", _HOST)
        self.assertNotEqual(a["parameters"]["nonce"], b["parameters"]["nonce"])
        for path in (
            "/register/",
            "/login/",
            "/reset-password/",
            "/contact/",
            "/security/altcha/register/",
        ):
            response = self.client.get(path, HTTP_HOST=_HOST)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("Cookie", response.get("Vary", ""))

    def test_two_login_widgets_have_separate_actions(self):
        a = C.challenge_for(self.client, "/login/", "login_password", _HOST)
        b = C.challenge_for(self.client, "/login/", "login_otp", _HOST)
        self.assertEqual(a["parameters"]["data"], {"action": "login_password"})
        self.assertEqual(b["parameters"]["data"], {"action": "login_otp"})
        self.assertNotEqual(a["parameters"]["nonce"], b["parameters"]["nonce"])

    @override_settings(RASTISI_CAPTCHA_ENABLED=False)
    def test_disabled_development_has_no_widget_or_assets(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertNotIn("altcha", html)
        self.assertEqual(
            self.client.get("/security/altcha/register/", HTTP_HOST=_HOST).status_code,
            503,
        )

    def test_rtl_keyboard_and_no_javascript_help(self):
        response = self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, "<noscript>")
        self.assertContains(response, "جاوااسکریپت")
        self.assertNotContains(response, "حاصل جمع")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class ProtectedFormsTests(_Base):
    def test_real_proof_lets_every_protected_action_proceed(self):
        for action, path, poster in self.FORMS:
            with self.subTest(action=action):
                C.reset_store()
                self.sent.clear()
                OwnerOtpChallenge.objects.all().delete()
                ContactMessage.objects.all().delete()
                client = Client()
                if action in {"login_password", "login_otp", "password_reset"}:
                    User.objects.filter(username=_PHONE).delete()
                    self.owner()
                response = getattr(self, poster)(
                    client, self.fields(path, action, client)
                )
                self.assertEqual(response.status_code, 302)
                if action == "contact":
                    self.assertEqual(ContactMessage.objects.count(), 1)
                elif action == "login_password":
                    self.assertIn("_auth_user_id", client.session)
                else:
                    self.assertEqual(response["Location"], "/verify/")
                    self.assertEqual(len(self.sent), 1)

    def test_invalid_proof_executes_no_sensitive_action_on_any_form(self):
        self.owner()
        for action, path, poster in self.FORMS:
            with self.subTest(action=action):
                before = self.effects()
                client = Client()
                response = getattr(self, poster)(
                    client, self.fields(path, action, client, answer_delta=1)
                )
                self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
                self.assertEqual(self.effects(), before)
                self.assertNotIn("_auth_user_id", client.session)

    def test_missing_malformed_test_mode_and_checkbox_only_are_rejected(self):
        self.owner()
        invalid = [
            {},
            {"altcha": ""},
            {"altcha": "true"},
            {"altcha": "on"},
            {"captcha_answer": "42", "captcha_token": "old-math-token"},
            {"altcha": C.encode({"challenge": None, "solution": None, "test": True})},
            {"altcha": "x" * 10000},
        ]
        for action, path, poster in self.FORMS:
            for fields in invalid:
                with self.subTest(action=action, fields=list(fields)):
                    C.reset_store()
                    before = self.effects()
                    response = getattr(self, poster)(Client(), fields)
                    self.assertContains(response, captcha_service.PUBLIC_ERROR_MESSAGE)
                    self.assertEqual(self.effects(), before)

    def test_wrong_solution_burns_challenge_before_a_later_correct_attempt(self):
        client = Client()
        good = self.fields("/contact/", "contact", client)
        wrong = C.decode(good)
        wrong["solution"]["derivedKey"] = "0" * 64
        self.post_contact(client, {"altcha": C.encode(wrong)})
        self.assertContains(
            self.post_contact(client, good), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_invalid_business_form_never_performs_the_sensitive_action(self):
        f = self.fields("/contact/", "contact")
        response = self.client.post(
            "/contact/", {"full_name": "", "email": "bad", **f}, HTTP_HOST=_HOST
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "<altcha-widget")

    def test_failure_allows_fetching_a_fresh_challenge(self):
        f = self.fields("/contact/", "contact", answer_delta=1)
        self.post_contact(self.client, f)
        fresh = self.fields("/contact/", "contact")
        self.assertNotEqual(C.nonce(f), C.nonce(fresh))
        self.assertEqual(self.post_contact(self.client, fresh).status_code, 302)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class SingleUseSessionAndActionTests(_Base):
    def test_replay_is_rejected(self):
        f = self.fields("/contact/", "contact")
        self.assertEqual(self.post_contact(self.client, f).status_code, 302)
        self.assertContains(
            self.post_contact(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_other_session_rejected_and_consumed(self):
        a, b = Client(), Client()
        f = self.fields("/contact/", "contact", a)
        b.get("/contact/", HTTP_HOST=_HOST)
        self.assertContains(
            self.post_contact(b, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertContains(
            self.post_contact(a, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_no_session_is_rejected(self):
        a = Client()
        f = self.fields("/contact/", "contact", a)
        self.assertContains(
            self.post_contact(Client(), f), captcha_service.PUBLIC_ERROR_MESSAGE
        )

    def test_cross_action_rejected_and_burned(self):
        self.owner()
        f = self.fields("/login/", "login_otp")
        self.assertContains(
            self.post_login_password(self.client, f),
            captcha_service.PUBLIC_ERROR_MESSAGE,
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(
            self.post_login_otp(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertEqual(self.sent, [])

    def test_expiration_is_checked_server_side(self):
        f = self.fields("/contact/", "contact")
        issued = caches["ratelimit"].get(captcha_service._storage_key(C.nonce(f)))["t"]
        with patch.object(captcha_service.time, "time", return_value=issued + 301):
            self.assertContains(
                self.post_contact(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
            )
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_expired_cache_entry_is_rejected(self):
        f = self.fields("/contact/", "contact")
        caches["ratelimit"].delete(captcha_service._storage_key(C.nonce(f)))
        self.assertContains(
            self.post_contact(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )

    @override_settings(RASTISI_CAPTCHA_TTL_SECONDS=60)
    def test_configurable_lifetime(self):
        f = self.fields("/contact/", "contact")
        issued = caches["ratelimit"].get(captcha_service._storage_key(C.nonce(f)))["t"]
        with patch.object(captcha_service.time, "time", return_value=issued + 61):
            self.assertContains(
                self.post_contact(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
            )


@override_settings(**C.ENABLED)
class PayloadSecurityTests(SimpleTestCase):
    def setUp(self):
        C.reset_store()
        self.addCleanup(C.reset_store)

    def test_malformed_base64_json_and_duplicate_keys_are_rejected(self):
        raw = [
            None,
            42,
            "",
            "not base64",
            C.encode([]),
            C.encode({"verified": True}),
            base64.b64encode(b'{"challenge":{},"challenge":{},"solution":{}}').decode(),
            base64.b64encode(
                b'{"challenge":{"parameters":{"nonce":"'
                + b"1" * 32
                + b'"}},"solution":NaN}'
            ).decode(),
        ]
        for value in raw:
            with self.subTest(value=str(value)[:40]):
                self.assertIsNone(captcha_service.decode_payload(value))

    def test_invalid_counter_and_key_types_fail_closed(self):
        for counter, key in [
            (True, "0" * 64),
            (-1, "0" * 64),
            (2**100, "0" * 64),
            ("5", "0" * 64),
            (1, []),
            (1, "ff"),
        ]:
            data, fields = _issued()
            decoded = C.decode(fields)
            decoded["solution"].update(counter=counter, derivedKey=key)
            self.assertFalse(
                captcha_service.verify_request(
                    _request(altcha=C.encode(decoded)), action="contact"
                ).success
            )

    def test_tampered_signed_challenge_is_rejected_before_library_work(self):
        for field, value in [
            ("cost", 10**20),
            ("algorithm", "ARGON2ID"),
            ("expiresAt", 2**60),
            ("nonce", "a" * 32),
            ("keySignature", "0" * 64),
        ]:
            data, fields = _issued()
            decoded = C.decode(fields)
            decoded["challenge"]["parameters"][field] = value
            with patch.object(captcha_service.LocalVerifier, "verify") as verify:
                result = captcha_service.verify_request(
                    _request(altcha=C.encode(decoded)), action="contact"
                )
            self.assertFalse(result.success)
            verify.assert_not_called()

    def test_tampered_signature_and_solution_are_rejected(self):
        for target in ("signature", "derivedKey"):
            data, fields = _issued()
            decoded = C.decode(fields)
            if target == "signature":
                decoded["challenge"]["signature"] = "0" * 64
            else:
                decoded["solution"]["derivedKey"] = "0" * 64
            self.assertFalse(
                captcha_service.verify_request(
                    _request(altcha=C.encode(decoded)), action="contact"
                ).success
            )

    def test_forged_counter_cannot_replace_a_valid_derived_key(self):
        data, fields = _issued()
        decoded = C.decode(fields)
        decoded["solution"] = {"counter": 0, "derivedKey": "0" * 64, "time": 0}
        self.assertFalse(
            captcha_service.verify_request(
                _request(altcha=C.encode(decoded)), action="contact"
            ).success
        )

    def test_invalid_library_result_does_not_raise_or_accept(self):
        data, fields = _issued()
        with patch.object(
            captcha_service.LocalVerifier,
            "verify",
            side_effect=ValueError("bad response"),
        ):
            result = captcha_service.verify_request(
                _request(**fields), action="contact"
            )
        self.assertFalse(result.success)

    def test_challenge_endpoint_only_accepts_known_actions_and_get(self):
        # Route-level cases live in EndpointTests (database/session aware).
        for action in ("", "wrong", "LOGIN"):
            with self.assertRaises(ValueError):
                captcha_service.issue(_request(), action)
            with self.assertRaises(ValueError):
                captcha_service.verify_request(_request(), action=action)


@override_settings(**C.ENABLED)
class ServiceConcurrencyTests(SimpleTestCase):
    def setUp(self):
        C.reset_store()
        self.addCleanup(C.reset_store)

    def _race(self, fields, count=16, mix=False):
        results, errors, barrier = [], [], threading.Barrier(count)

        def work(i):
            try:
                submitted = fields
                if mix and i:
                    bad = C.decode(fields)
                    bad["solution"]["derivedKey"] = "0" * 64
                    submitted = {"altcha": C.encode(bad)}
                barrier.wait(timeout=10)
                ok = captcha_service.verify_request(
                    _request(**submitted), action="contact"
                ).success
                results.append((i, ok))
            except Exception as exc:
                errors.append(type(exc).__name__)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), count)
        return results

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)
    def test_many_simultaneous_solutions_pass_exactly_once(self):
        for _ in range(5):
            _, f = _issued()
            self.assertEqual(sum(ok for _, ok in self._race(f)), 1)

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)
    def test_simultaneous_wrong_proofs_never_pass(self):
        _, f = _issued()
        results = self._race(f, mix=True)
        self.assertTrue(all(i == 0 for i, ok in results if ok))
        self.assertLessEqual(sum(ok for _, ok in results), 1)

    def test_simultaneous_issuance_uses_unique_nonces(self):
        tokens = []
        barrier = threading.Barrier(20)

        def work():
            barrier.wait()
            tokens.append(captcha_service.issue(_request(), "contact")["token"])

        threads = [threading.Thread(target=work) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(tokens), 20)
        self.assertEqual(len(set(tokens)), 20)


@override_settings(**C.ENABLED)
class BudgetTests(SimpleTestCase):
    def setUp(self):
        C.reset_store()
        self.addCleanup(C.reset_store)

    def test_every_verification_attempt_is_budgeted(self):
        with patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 3):
            results = [
                captcha_service.verify_request(
                    _request(altcha="invalid"), action="contact"
                )
                for _ in range(5)
            ]
        self.assertEqual(
            [r.error_code for r in results],
            ["invalid-payload"] * 3 + ["rate-limited"] * 2,
        )

    def test_ip_budgets_are_independent(self):
        with patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 1):
            captcha_service.verify_request(
                _request(ip="198.51.100.1"), action="contact"
            )
            a = captcha_service.verify_request(
                _request(ip="198.51.100.1"), action="contact"
            )
            b = captcha_service.verify_request(
                _request(ip="198.51.100.2"), action="contact"
            )
        self.assertEqual(a.error_code, "rate-limited")
        self.assertNotEqual(b.error_code, "rate-limited")

    def test_challenge_issuance_is_budgeted(self):
        with patch.object(captcha_service, "ISSUE_MAX", 2):
            first = [captcha_service.issue(_request(), "contact") for _ in range(2)]
            last = captcha_service.issue(_request(), "contact")
        self.assertTrue(all(not r["unavailable"] for r in first))
        self.assertTrue(last["unavailable"])
        self.assertTrue(last["rate_limited"])

    def test_unknown_actions_are_rejected(self):
        with self.assertRaises(ValueError):
            captcha_service.issue(_request(), "nope")
        with self.assertRaises(ValueError):
            captcha_service.verify_request(_request(), action="nope")


class _DownStore:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError("redis://:topsecret@10.0.0.9:6379/0 unreachable")

        return fail


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class SharedStoreOutageTests(_Base):
    def _down(self):
        return patch.object(captcha_service, "_store", return_value=_DownStore())

    def test_pages_render_unavailable_without_connection_details(self):
        with self._down():
            for path in ("/register/", "/login/", "/reset-password/", "/contact/"):
                response = self.client.get(path, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "سرویس تأیید امنیتی موقتاً در دسترس نیست")
                self.assertNotContains(response, "<altcha-widget")
                self.assertNotContains(response, "topsecret")

    def test_outage_blocks_all_sensitive_forms(self):
        self.owner()
        fields = {action: self.fields(path, action) for action, path, _ in self.FORMS}
        before = self.effects()
        with self._down():
            for action, path, poster in self.FORMS:
                response = getattr(self, poster)(self.client, fields[action])
                self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertEqual(self.effects(), before)

    def test_counter_outage_blocks_post_and_challenge_endpoint(self):
        f = self.fields("/contact/", "contact")
        with patch.object(
            captcha_service,
            "enforce_rate_limit",
            side_effect=RateLimitUnavailable(UNAVAILABLE_MESSAGE),
        ):
            self.assertContains(self.post_contact(self.client, f), UNAVAILABLE_MESSAGE)
            self.assertEqual(
                self.client.get(
                    "/security/altcha/contact/", HTTP_HOST=_HOST
                ).status_code,
                503,
            )
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_no_connection_secret_is_logged(self):
        _, f = _issued()
        with self._down(), self.assertLogs(
            "apps.portal.services.captcha_service", level="ERROR"
        ) as logs:
            result = captcha_service.verify_request(_request(**f), action="contact")
        self.assertFalse(result.success)
        self.assertNotIn("topsecret", "\n".join(logs.output) + result.message)

    def test_recovery_does_not_require_restart(self):
        with self._down():
            self.assertTrue(captcha_service.issue(_request(), "contact")["unavailable"])
        self.assertFalse(captcha_service.issue(_request(), "contact")["unavailable"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class EndpointTests(_Base):
    def test_post_and_unknown_action_are_rejected(self):
        self.assertEqual(
            self.client.post("/security/altcha/contact/", HTTP_HOST=_HOST).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(
                "/security/altcha/not-an-action/", HTTP_HOST=_HOST
            ).status_code,
            404,
        )

    def test_endpoint_outage_returns_uncached_503(self):
        with patch.object(captcha_service, "_store", return_value=_DownStore()):
            response = self.client.get("/security/altcha/contact/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 503)
        self.assertIn("no-store", response["Cache-Control"])

    def test_endpoint_budget_returns_429_without_new_challenge(self):
        with patch.object(captcha_service, "ISSUE_MAX", 1):
            self.assertEqual(
                self.client.get(
                    "/security/altcha/contact/", HTTP_HOST=_HOST
                ).status_code,
                200,
            )
            response = self.client.get("/security/altcha/contact/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("parameters", response.json())


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ProductionRuntimeGuardTests(_Base):
    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_CAPTCHA_ENABLED=False)
    def test_production_with_the_captcha_off_can_never_succeed(self):
        result = captcha_service.verify_request(_request(), action="login_password")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "captcha-misconfigured")
        self.owner()
        with patch.object(
            owner_auth_service, "authenticate_owner_by_identifier"
        ) as authenticate:
            response = self.post_login_password(self.client, {})
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        authenticate.assert_not_called()

    @override_settings(RASTISI_PRODUCTION_MODE=False, RASTISI_CAPTCHA_ENABLED=False)
    def test_development_may_run_without_it(self):
        self.assertTrue(
            captcha_service.verify_request(_request(), action="contact").success
        )
        self.assertEqual(self.post_contact(self.client, {}).status_code, 302)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class ExistingProtectionsStillApplyTests(_Base):
    def test_csrf_is_still_enforced_and_a_forged_post_does_not_even_consume_the_token(
        self,
    ):
        client = Client(enforce_csrf_checks=True)
        f = self.fields("/contact/", "contact", client)
        forged = client.post("/contact/", {**_CONTACT, **f}, HTTP_HOST=_HOST)
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertIsNotNone(
            caches["ratelimit"].get(captcha_service._storage_key(C.nonce(f)))
        )

    def test_the_per_ip_otp_budget_and_phone_budget_still_cap_requests_after_a_solved_captcha(
        self,
    ):
        results = []
        for index in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW + 2):
            f = self.fields("/register/", "register")
            response = self.post_register(self.client, f)
            results.append(response.status_code)
        # registrations past the per-phone cap are refused by the OTP service, not by the CAPTCHA
        self.assertLessEqual(
            len(self.sent), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW
        )
        self.assertEqual(results[-1], 200)

    def test_the_existing_login_ip_limit_still_applies(self):
        self.owner()
        client = Client()
        for i in range(17):
            f = self.fields("/login/", "login_password", client)
            r = client.post(
                "/login/password/",
                {"identifier": f"nobody{i}@example.com", "password": "bad", **f},
                HTTP_HOST=_HOST,
            )
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


# Use only a disposable Redis database: these regressions clear its contents.
_REDIS_URL = os.environ.get("RASTISI_TEST_REDIS_URL", "")


def _caches(url):
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "altcha-default",
        },
        "ratelimit": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": url,
            "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
        },
    }


@unittest.skipUnless(_REDIS_URL, "requires a disposable RASTISI_TEST_REDIS_URL")
@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **C.ENABLED)
class RealRedisTests(_Base):
    def setUp(self):
        cfg = override_settings(CACHES=_caches(_REDIS_URL))
        cfg.enable()
        self.addCleanup(cfg.disable)
        super().setUp()

    def test_real_proof_and_replay(self):
        f = self.fields("/contact/", "contact")
        self.assertEqual(self.post_contact(self.client, f).status_code, 302)
        self.assertContains(
            self.post_contact(self.client, f), captcha_service.PUBLIC_ERROR_MESSAGE
        )
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_redis_owns_the_expiry(self):
        import redis

        data, _ = _issued()
        store = caches["ratelimit"]
        ttl = redis.Redis.from_url(_REDIS_URL).ttl(
            store.make_and_validate_key(captcha_service._storage_key(data["token"]))
        )
        self.assertTrue(0 < ttl <= 300, ttl)

    @patch.object(captcha_service, "VERIFY_MAX_ATTEMPTS", 100000)
    def test_atomic_single_use_with_real_redis(self):
        for _ in range(5):
            _, f = _issued()
            results = ServiceConcurrencyTests()._race(f)
            self.assertEqual(sum(ok for _, ok in results), 1)

    def test_unreachable_redis_cannot_trigger_sensitive_action(self):
        f = self.fields("/contact/", "contact")
        with override_settings(
            CACHES=_caches("redis://:dummy-private-marker@127.0.0.1:1/15")
        ):
            page = self.client.get("/contact/", HTTP_HOST=_HOST)
            self.assertContains(page, "سرویس تأیید امنیتی موقتاً در دسترس نیست")
            self.assertNotContains(page, "dummy-private-marker")
            response = self.post_contact(self.client, f)
            self.assertContains(response, UNAVAILABLE_MESSAGE)
            self.assertNotContains(response, "dummy-private-marker")
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_independent_python_workers_consume_a_proof_only_once(self):
        import subprocess
        import sys

        _, fields = _issued()
        worker = """import json, os, sys
import django
django.setup()
from types import SimpleNamespace
from django.test import RequestFactory
from apps.portal.services.captcha_service import verify_request
fields = json.loads(sys.stdin.readline())
print('ready', flush=True)
sys.stdin.readline()
request = RequestFactory().post('/contact/', fields, REMOTE_ADDR='203.0.113.7')
request.session = SimpleNamespace(session_key='s-1')
print(json.dumps(verify_request(request, action='contact').success), flush=True)
"""
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "shop_core.settings",
            "DJANGO_DEBUG": "true",
            "RASTISI_RATE_LIMIT_CACHE_URL": _REDIS_URL,
            "RASTISI_CAPTCHA_ENABLED": "true",
        }
        processes = []
        try:
            for _ in range(4):
                proc = subprocess.Popen(
                    [sys.executable, "-c", worker],
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                processes.append(proc)
                proc.stdin.write(json.dumps(fields) + "\n")
                proc.stdin.flush()
            for proc in processes:
                self.assertEqual(proc.stdout.readline().strip(), "ready")
            for proc in processes:
                proc.stdin.write("go\n")
                proc.stdin.flush()
            results = []
            for proc in processes:
                stdout, stderr = proc.communicate(timeout=30)
                self.assertEqual(proc.returncode, 0, stderr)
                results.append(json.loads(stdout.strip()))
            self.assertEqual(results.count(True), 1)
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
