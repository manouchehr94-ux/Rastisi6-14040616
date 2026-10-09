"""Owner login / authentication audit (audit/owner-login-v1).

Regression tests for the findings of the login audit:

* open redirect via backslash / control-character ``next`` values;
* timing- and message-level account enumeration on password login;
* a plain Customer (or any non-Owner) account must never pass the Owner password gate,
  whichever identifier it is addressed by;
* per-identifier throttling that cannot be bypassed by rotating IPs, and that a
  script without a solved Turnstile cannot use to lock somebody out;
* password reset: only active Owner-eligible accounts get mail, per-email limit,
  link/session behaviour, Persian policy messages, Referrer-Policy;
* session behaviour (fixation, logout, remember-me) and signed ``admin_return``;
* login page markup that does not depend on JavaScript.
"""

import re
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.portal import views as portal_views
from apps.portal.tests._owner_signup import age_otp_cooldown, complete_account
from apps.portal.forms import OwnerIdentifierLoginForm
from apps.portal.models import OwnerOtpChallenge, OwnerProfile
from apps.portal.services import owner_auth_service, owner_otp_service, turnstile_service
from apps.portal.services.handoff_service import build_admin_return_token
from apps.sms.services.backends import SmsSendResult
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"
_PASSWORD = "a-very-strong-pass-1"


def _store(sub="audit-store"):
    return Store.objects.create(name=f"Store {sub}", slug=sub, admin_subdomain=sub, status=Store.Status.ACTIVE)


def _member(store, user, status=StoreMembership.MembershipStatus.ACTIVE, role=StoreMembership.Role.OWNER):
    extra = {"revoked_at": timezone.now()} if status == StoreMembership.MembershipStatus.REVOKED else {}
    return StoreMembership.objects.create(
        store=store, user=user, role=role, status=status, accepted_at=timezone.now(), **extra,
    )


def _post_login(client, identifier, password=_PASSWORD, **extra):
    return client.post(
        "/login/password/", {"identifier": identifier, "password": password, **extra}, HTTP_HOST=_HOST,
    )


class _Base:
    def setUp(self):
        super().setUp()
        cache.clear()


# ---------------------------------------------------------------------------
# Safe `next`
# ---------------------------------------------------------------------------


class SafeNextUnitTests(SimpleTestCase):
    def test_accepts_only_local_paths(self):
        for ok in ("/app/", "/app/stores/new/", "/app/stores/?page=2", "/help/", "/%5Cevil.example"):
            with self.subTest(ok=ok):
                self.assertTrue(portal_views._is_safe_next(ok))

    def test_rejects_every_known_open_redirect_shape(self):
        bad = (
            "", "evil.example", "//evil.example", "///evil.example", "////evil.example",
            "https://evil.example", "http://evil.example/x", "javascript:alert(1)", "data:text/html,x",
            "/\\evil.example", "/\\/evil.example", "\\\\evil.example", "\\/evil.example",
            "/\t/evil.example", "/\n/evil.example", "/\r\nLocation: https://evil.example",
            " //evil.example", "\t//evil.example", "%2F%2Fevil.example", "https:evil.example",
            "/" + "a" * 3000,
        )
        for value in bad:
            with self.subTest(value=value):
                self.assertFalse(portal_views._is_safe_next(value))


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SafeNextEndToEndTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(full_name="Next Owner", email="next@example.com", password=_PASSWORD)

    def test_password_login_never_redirects_off_site(self):
        for value in ("//evil.example", "/\\evil.example", "/\t/evil.example", "https://evil.example", "///evil.example"):
            with self.subTest(value=value):
                cache.clear()
                response = _post_login(self.client, "next@example.com", next=value)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/app/")
                self.client.post("/logout/", HTTP_HOST=_HOST)

    def test_local_destination_is_honoured(self):
        response = _post_login(self.client, "next@example.com", next="/app/stores/new/")
        self.assertEqual(response["Location"], "/app/stores/new/")

    def test_already_signed_in_visit_honours_only_a_safe_next(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/login/?next=/app/stores/new/", HTTP_HOST=_HOST)["Location"], "/app/stores/new/")
        self.assertEqual(self.client.get("/login/?next=/%5Cevil.example", HTTP_HOST=_HOST).status_code, 302)
        self.assertEqual(self.client.get("/login/?next=//evil.example", HTTP_HOST=_HOST)["Location"], "/app/")
        self.assertEqual(self.client.get("/login/?next=/\\evil.example", HTTP_HOST=_HOST)["Location"], "/app/")

    def test_login_page_does_not_echo_an_unsafe_next_as_an_unescaped_attribute(self):
        page = self.client.get('/login/?next="><script>alert(1)</script>', HTTP_HOST=_HOST)
        self.assertNotContains(page, "<script>alert(1)</script>")


class OtpNextEndToEndTests(_Base, TestCase):
    """The OTP path stores ``next`` server-side and validates it at redirect time too."""

    def setUp(self):
        super().setUp()
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._send)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = User.objects.create_user(username="09125550001")
        self.owner.set_unusable_password()
        self.owner.save()
        OwnerProfile.objects.create(user=self.owner, phone="09125550001", full_name="OTP Owner")

    def _send(self, *, to, code, **_):
        self.sent.append(code)
        return SmsSendResult(success=True, provider_ref_id="t")

    def _login(self, nxt):
        with override_settings(ALLOWED_HOSTS=[_HOST, "testserver"]):
            self.client.post("/login/", {"phone": "09125550001", "next": nxt}, HTTP_HOST=_HOST)
            return self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)

    def test_unsafe_next_is_ignored_after_otp(self):
        for value in ("//evil.example", "/\\evil.example"):
            with self.subTest(value=value):
                cache.clear()
                self.assertEqual(self._login(value)["Location"], "/app/")
                self.client.post("/logout/", HTTP_HOST=_HOST)

    def test_safe_next_is_followed_after_otp(self):
        self.assertEqual(self._login("/app/stores/new/")["Location"], "/app/stores/new/")


# ---------------------------------------------------------------------------
# Password login: identifiers, eligibility, enumeration, timing, limits
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PasswordLoginMatrixTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.email_owner = owner_auth_service.register_owner(
            full_name="Email Owner", email="Legacy@Example.com", password=_PASSWORD,
        )
        self.phone_owner = User.objects.create_user(username="phone_owner", password=_PASSWORD)
        OwnerProfile.objects.create(user=self.phone_owner, phone="09123334455", full_name="Phone Owner")
        # A storefront Customer: username == phone, usable password, an email on the User row.
        self.customer = User.objects.create_user(
            username="09127776655", email="shopper@example.com", password=_PASSWORD,
        )
        self.customer_profile = Customer.objects.create(
            user=self.customer, full_name="Shopper", phone="09127776655",
        )
        self.inactive = owner_auth_service.register_owner(full_name="Inactive", email="off@example.com", password=_PASSWORD)
        self.inactive.is_active = False
        self.inactive.save()
        self.otp_only = User.objects.create_user(username="09128889900")
        self.otp_only.set_unusable_password()
        self.otp_only.save()
        OwnerProfile.objects.create(user=self.otp_only, phone="09128889900", full_name="OTP Only")
        self.superuser = User.objects.create_superuser(username="root", email="root@example.com", password=_PASSWORD)

    def assertLoggedIn(self, response, user):
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:200])
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def assertGenericFailure(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_every_supported_identifier_logs_in(self):
        cases = (
            ("legacy@example.com", self.email_owner),      # email, lower-case
            ("LEGACY@EXAMPLE.COM", self.email_owner),      # case-insensitive email
            ("  Legacy@Example.com  ", self.email_owner),  # surrounding whitespace
            ("09123334455", self.phone_owner),             # canonical mobile
            ("۰۹۱۲۳۳۳۴۴۵۵", self.phone_owner),             # Persian digits
            ("+989123334455", self.phone_owner),           # international
            ("9123334455", self.phone_owner),              # without leading zero
            ("phone_owner", self.phone_owner),             # username
            ("PHONE_OWNER", self.phone_owner),             # username, case-insensitive
        )
        for identifier, user in cases:
            with self.subTest(identifier=identifier):
                cache.clear()
                self.assertLoggedIn(_post_login(self.client, identifier), user)
                self.client.post("/logout/", HTTP_HOST=_HOST)

    def test_superuser_still_logs_in_through_the_shared_resolver(self):
        self.assertLoggedIn(_post_login(self.client, "root"), self.superuser)
        self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertLoggedIn(_post_login(self.client, "root@example.com"), self.superuser)

    def test_customer_only_account_cannot_pass_by_any_identifier(self):
        for identifier in ("shopper@example.com", "SHOPPER@example.com", "09127776655", "۰۹۱۲۷۷۷۶۶۵۵", "+989127776655"):
            with self.subTest(identifier=identifier):
                cache.clear()
                self.assertGenericFailure(_post_login(self.client, identifier))

    def test_customer_who_is_also_an_owner_logs_in_with_the_shared_identity(self):
        OwnerProfile.objects.create(user=self.customer, phone="09127776655", full_name="Both")
        self.assertLoggedIn(_post_login(self.client, "09127776655"), self.customer)

    def test_active_store_member_without_owner_profile_can_use_email_but_not_an_invited_one(self):
        member = User.objects.create_user(username="staff1", email="staff1@example.com", password=_PASSWORD)
        _member(_store("staff-store"), member, role=StoreMembership.Role.ANALYST)
        invited = User.objects.create_user(username="staff2", email="staff2@example.com", password=_PASSWORD)
        _member(_store("staff-store2"), invited, status=StoreMembership.MembershipStatus.INVITED)
        self.assertLoggedIn(_post_login(self.client, "staff1@example.com"), member)
        self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertGenericFailure(_post_login(self.client, "staff2@example.com"))

    def test_all_failure_kinds_produce_the_same_public_response(self):
        shapes = {
            "wrong password": ("legacy@example.com", "not-the-password"),
            "unknown email": ("nobody@example.com", _PASSWORD),
            "unknown phone": ("09120000000", _PASSWORD),
            "unknown username": ("nobody_here", _PASSWORD),
            "customer only": ("shopper@example.com", _PASSWORD),
            "inactive": ("off@example.com", _PASSWORD),
            "otp-only owner": ("09128889900", _PASSWORD),
            "malformed": ("@@@", _PASSWORD),
        }
        bodies = {}
        for name, (identifier, password) in shapes.items():
            cache.clear()
            response = _post_login(self.client, identifier, password)
            self.assertGenericFailure(response)
            html = response.content.decode()
            # Strip the echoed identifier and CSRF token; the rest must be byte-identical.
            html = re.sub(r'csrfmiddlewaretoken" value="[^"]+"', "", html)
            html = re.sub(r'name="identifier"[^>]*value="[^"]*"', 'name="identifier"', html)
            html = re.sub(r'value="[^"]*"', "", html)
            bodies[name] = html
        self.assertEqual(len(set(bodies.values())), 1, "failure responses differ between account states")

    def test_every_failure_path_pays_for_one_password_hash(self):
        """Unknown / ineligible / OTP-only accounts must cost the same as a wrong password."""
        with patch("django.contrib.auth.base_user.make_password", wraps=__import__("django.contrib.auth.hashers", fromlist=["x"]).make_password) as hashed:
            for identifier in ("nobody@example.com", "09120000000", "nobody_here", "shopper@example.com", "09128889900"):
                hashed.reset_mock()
                self.assertIsNone(
                    owner_auth_service.authenticate_owner_by_identifier(None, identifier=identifier, password=_PASSWORD),
                    identifier,
                )
                self.assertGreaterEqual(hashed.call_count, 1, f"{identifier}: failed without hashing (timing oracle)")

    def test_empty_blank_and_oversized_input(self):
        self.assertEqual(_post_login(self.client, "", _PASSWORD).status_code, 200)
        self.assertContains(_post_login(self.client, "legacy@example.com", ""), "رمز عبور را وارد کنید.")
        self.assertContains(_post_login(self.client, "   ", _PASSWORD), "را وارد کنید.")
        long_id = _post_login(self.client, "a" * 5000 + "@example.com", _PASSWORD)
        self.assertEqual(long_id.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        long_pw = _post_login(self.client, "legacy@example.com", "p" * 5000)
        self.assertEqual(long_pw.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNone(owner_auth_service.authenticate_owner_by_identifier(None, identifier="x" * 500, password=_PASSWORD))

    def test_inactive_user_never_authenticates(self):
        self.assertGenericFailure(_post_login(self.client, "off@example.com"))

    def test_login_does_not_apply_password_creation_validators(self):
        weak = owner_auth_service.register_owner  # creation is validated…
        with self.assertRaises(owner_auth_service.OwnerAuthError):
            weak(full_name="Weak", email="weak@example.com", password="123")
        # …but a legacy account whose stored password would fail today's validators can still log in.
        legacy = User.objects.create_user(username="legacy_weak", email="lw@example.com", password="12345")
        OwnerProfile.objects.create(user=legacy, full_name="Legacy Weak")
        self.assertLoggedIn(_post_login(self.client, "lw@example.com", "12345"), legacy)

    def test_double_submit_is_harmless(self):
        first = _post_login(self.client, "legacy@example.com")
        second = _post_login(self.client, "legacy@example.com")
        self.assertEqual((first.status_code, second.status_code), (302, 302))
        self.assertEqual(Session.objects.count(), 1)

    def test_login_form_marks_both_fields_invalid_and_links_the_alert(self):
        response = _post_login(self.client, "legacy@example.com", "wrong")
        html = response.content.decode()
        self.assertIn('id="id_form_error"', html)
        self.assertEqual(html.count('aria-invalid="true"'), 2)
        self.assertRegex(html, r'name="identifier"[^>]*aria-describedby="id_form_error"')
        self.assertNotIn("wrong", html)  # the password is never echoed back

    def test_get_on_the_password_endpoint_redirects_to_the_login_page_and_never_logs_in(self):
        response = self.client.get(
            "/login/password/?next=/app/stores/new/&identifier=legacy@example.com&password=" + _PASSWORD, HTTP_HOST=_HOST,
        )
        self.assertEqual(response["Location"], "/login/?next=%2Fapp%2Fstores%2Fnew%2F")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.put("/login/password/", HTTP_HOST=_HOST).status_code, 405)


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class LoginThrottleTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(full_name="Throttle", email="throttle@example.com", password=_PASSWORD)

    def _attempt(self, identifier, password, ip):
        return self.client.post(
            "/login/password/", {"identifier": identifier, "password": password}, HTTP_HOST=_HOST, REMOTE_ADDR=ip,
        )

    def test_identifier_budget_cannot_be_bypassed_by_rotating_ips(self):
        for index in range(portal_views.LOGIN_IDENTIFIER_MAX_ATTEMPTS):
            self.assertContains(self._attempt("throttle@example.com", "bad", f"10.0.0.{index}"), owner_auth_service.GENERIC_LOGIN_ERROR)
        blocked = self._attempt("throttle@example.com", _PASSWORD, "10.0.9.9")  # right password, fresh IP
        self.assertContains(blocked, portal_views._LOGIN_THROTTLED_MESSAGE)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_throttle_key_ignores_case_spacing_and_digit_script(self):
        key = owner_auth_service.login_identifier_throttle_key
        self.assertEqual(key("Throttle@Example.com"), key("  throttle@example.COM "))
        self.assertEqual(key("09121234567"), key("۰۹۱۲۱۲۳۴۵۶۷"))
        self.assertNotIn("throttle", key("throttle@example.com"))

    def test_the_same_throttle_applies_to_unknown_identifiers_so_it_reveals_nothing(self):
        for index in range(portal_views.LOGIN_IDENTIFIER_MAX_ATTEMPTS):
            self._attempt("ghost@example.com", "bad", f"10.1.0.{index}")
        self.assertContains(self._attempt("ghost@example.com", "bad", "10.1.9.9"), portal_views._LOGIN_THROTTLED_MESSAGE)

    def test_a_failed_turnstile_does_not_spend_the_identifier_budget(self):
        denied = turnstile_service.TurnstileValidationResult(False, "missing-token")
        with patch.object(portal_views.turnstile_service, "verify_request", return_value=denied):
            for index in range(portal_views.LOGIN_IDENTIFIER_MAX_ATTEMPTS + 3):
                response = self._attempt("throttle@example.com", _PASSWORD, f"10.2.0.{index}")
                self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertEqual(self._attempt("throttle@example.com", _PASSWORD, "10.2.9.9").status_code, 302)

    def test_per_ip_budget_still_applies(self):
        for _ in range(15):
            self._attempt(f"user{_}@example.com", "bad", "10.3.0.1")
        self.assertContains(self._attempt("other@example.com", "bad", "10.3.0.1"), "بیش از حد مجاز")

    def test_throttled_request_never_reaches_authenticate(self):
        for index in range(portal_views.LOGIN_IDENTIFIER_MAX_ATTEMPTS):
            self._attempt("throttle@example.com", "bad", f"10.4.0.{index}")
        with patch.object(owner_auth_service, "authenticate_owner_by_identifier") as auth:
            self._attempt("throttle@example.com", _PASSWORD, "10.4.9.9")
        auth.assert_not_called()


# ---------------------------------------------------------------------------
# Turnstile on the login surface (end-to-end through the real service)
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=[_HOST, "testserver"], TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="1x00000000000000000000AA",
    TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA", TURNSTILE_EXPECTED_HOSTNAMES=(_HOST,),
)
class LoginTurnstileTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        owner_auth_service.register_owner(full_name="TS", email="ts@example.com", password=_PASSWORD)

    def _siteverify(self, **result):
        class _Response:
            def raise_for_status(self):
                pass

            def json(self_inner):
                return result

        return patch.object(turnstile_service.requests, "post", return_value=_Response())

    def test_missing_token_means_no_authentication_attempt_at_all(self):
        with patch.object(owner_auth_service, "authenticate_owner_by_identifier") as auth:
            response = _post_login(self.client, "ts@example.com")
        auth.assert_not_called()
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)

    def test_wrong_action_or_hostname_is_rejected_by_the_backend(self):
        for result in (
            {"success": True, "action": "register", "hostname": _HOST},
            {"success": True, "action": "login_password", "hostname": "evil.example"},
            {"success": False, "error-codes": ["invalid-input-response"]},
        ):
            with self.subTest(result=result), self._siteverify(**result):
                cache.clear()
                response = _post_login(self.client, "ts@example.com", **{"cf-turnstile-response": "tok"})
                self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_token_for_the_right_action_logs_in(self):
        with self._siteverify(success=True, action="login_password", hostname=_HOST):
            response = _post_login(self.client, "ts@example.com", **{"cf-turnstile-response": "tok"})
        self.assertEqual(response.status_code, 302)

    def test_otp_request_sends_no_sms_until_turnstile_passes(self):
        with patch.object(owner_otp_service, "send_platform_otp") as send:
            denied = self.client.post("/login/", {"phone": "09125550123"}, HTTP_HOST=_HOST)
            self.assertContains(denied, turnstile_service.PUBLIC_ERROR_MESSAGE)
            send.assert_not_called()
            self.assertFalse(OwnerOtpChallenge.objects.exists())
            self.assertContains(denied, 'data-action="login_otp"')

    def test_reset_request_sends_no_sms_until_turnstile_passes(self):
        with patch.object(owner_otp_service, "send_platform_otp") as send:
            denied = self.client.post("/reset-password/", {"phone": "09125550123"}, HTTP_HOST=_HOST)
        self.assertContains(denied, turnstile_service.PUBLIC_ERROR_MESSAGE)
        send.assert_not_called()
        self.assertFalse(OwnerOtpChallenge.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.assertContains(denied, 'value="09125550123"')  # the typed value is preserved


# ---------------------------------------------------------------------------
# Session security
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS=2592000, AUTH_SESSION_DEFAULT_EXPIRY_SECONDS=0)
class SessionSecurityTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(full_name="Sess", email="sess@example.com", password=_PASSWORD)

    def test_session_key_rotates_on_login_and_preloaded_data_does_not_authenticate(self):
        self.client.get("/login/", HTTP_HOST=_HOST)
        session = self.client.session
        session["pre_login"] = "x"
        session.save()
        before = self.client.session.session_key
        _post_login(self.client, "sess@example.com")
        after = self.client.session.session_key
        self.assertNotEqual(before, after)
        self.assertFalse(Session.objects.filter(session_key=before).exists())

    def test_logout_destroys_the_server_side_session(self):
        _post_login(self.client, "sess@example.com")
        key = self.client.session.session_key
        self.assertEqual(self.client.get("/logout/", HTTP_HOST=_HOST).status_code, 405)
        self.assertTrue(Session.objects.filter(session_key=key).exists())  # GET did not log out
        self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        self.assertEqual(self.client.get("/app/", HTTP_HOST=_HOST).status_code, 302)

    def test_remember_me_sets_server_side_expiry_for_password_login(self):
        _post_login(self.client, "sess@example.com", remember_me="on")
        age = Session.objects.get(session_key=self.client.session.session_key).expire_date - timezone.now()
        self.assertAlmostEqual(age.total_seconds(), 2592000, delta=120)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_without_remember_me_the_cookie_is_a_browser_session_cookie(self):
        _post_login(self.client, "sess@example.com")
        self.assertTrue(self.client.session.get_expire_at_browser_close())


# ---------------------------------------------------------------------------
# Merchant Admin hand-off (admin_return)
# ---------------------------------------------------------------------------


@override_settings(
    ALLOWED_HOSTS=[_HOST, "audit-store.rastisi.localhost", "testserver"],
    RASTISI_PLATFORM_PRIMARY_HOST=_HOST, RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.localhost",
)
class AdminReturnLoginTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.store = _store("audit-store")
        self.other = _store("audit-other")
        self.owner = owner_auth_service.register_owner(full_name="Adm", email="adm@example.com", password=_PASSWORD)
        _member(self.store, self.owner)
        self.stranger = owner_auth_service.register_owner(full_name="Str", email="str@example.com", password=_PASSWORD)
        self.token = build_admin_return_token(admin_subdomain="audit-store", destination_path="/admin-portal/orders/")

    def _ticket_target(self, response):
        return urlsplit(response["Location"])

    def test_active_member_gets_a_ticket_for_exactly_that_store_and_path(self):
        response = _post_login(self.client, "adm@example.com", admin_return=self.token)
        target = self._ticket_target(response)
        self.assertEqual(target.hostname, "audit-store.rastisi.localhost")
        self.assertTrue(target.path.startswith("/admin-portal/handoff/"))
        ticket = self.owner.admin_handoff_tickets.get()
        self.assertEqual((ticket.store_id, ticket.destination_path), (self.store.pk, "/admin-portal/orders/"))

    def test_non_member_gets_no_ticket_and_falls_back_to_my_stores(self):
        response = _post_login(self.client, "str@example.com", admin_return=self.token)
        self.assertEqual(response["Location"], "/app/")
        self.assertFalse(self.stranger.admin_handoff_tickets.exists())

    def test_non_member_with_next_falls_back_to_the_safe_next(self):
        response = _post_login(self.client, "str@example.com", admin_return=self.token, next="/app/stores/new/")
        self.assertEqual(response["Location"], "/app/stores/new/")

    def test_inactive_membership_gets_no_ticket(self):
        revoked = owner_auth_service.register_owner(full_name="Rv", email="rv@example.com", password=_PASSWORD)
        _member(self.store, revoked, status=StoreMembership.MembershipStatus.REVOKED)
        self.assertEqual(_post_login(self.client, "rv@example.com", admin_return=self.token)["Location"], "/app/")
        self.assertFalse(revoked.admin_handoff_tickets.exists())

    def test_member_of_another_store_gets_no_ticket_for_this_one(self):
        _member(self.other, self.stranger)
        response = _post_login(self.client, "str@example.com", admin_return=self.token)
        self.assertEqual(response["Location"], "/app/")

    def test_tampered_malformed_and_empty_tokens_are_ignored(self):
        for value in (self.token[:-2] + "xx", "garbage", "a:b:c", "", self.token.split(":")[0]):
            with self.subTest(value=value):
                cache.clear()
                self.assertEqual(_post_login(self.client, "adm@example.com", admin_return=value)["Location"], "/app/")
                self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertFalse(self.owner.admin_handoff_tickets.exists())

    def test_expired_token_is_ignored(self):
        with patch("django.core.signing.time.time", return_value=__import__("time").time() + 601):
            response = _post_login(self.client, "adm@example.com", admin_return=self.token)
        self.assertEqual(response["Location"], "/app/")
        self.assertFalse(self.owner.admin_handoff_tickets.exists())

    def test_token_is_not_a_credential_it_only_names_a_destination(self):
        """Replaying a captured token as a different, authenticated non-member yields nothing."""
        self.client.force_login(self.stranger)
        response = self.client.get(f"/login/?admin_return={self.token}", HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/app/")
        self.assertFalse(self.stranger.admin_handoff_tickets.exists())

    def test_admin_return_takes_precedence_over_next_for_a_member(self):
        response = _post_login(self.client, "adm@example.com", admin_return=self.token, next="/app/stores/new/")
        self.assertIn("/admin-portal/handoff/", response["Location"])

    def test_failed_password_login_issues_no_ticket(self):
        _post_login(self.client, "adm@example.com", "wrong", admin_return=self.token)
        self.assertFalse(self.owner.admin_handoff_tickets.exists())

    def test_destination_outside_the_admin_portal_is_not_decodable(self):
        evil = build_admin_return_token(admin_subdomain="audit-store", destination_path="//evil.example/")
        self.assertEqual(_post_login(self.client, "adm@example.com", admin_return=evil)["Location"], "/app/")


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PasswordResetAuditTests(_Base, TestCase):
    """LEGACY email-token reset. The public ``/reset-password/`` page is mobile + SMS OTP now (see
    ``test_password_reset_sms.py``); ``request_password_reset`` is retained for already-issued email
    links and internal use, so these tests drive the service directly and then the token URL."""

    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(full_name="Reset", email="rst@example.com", password=_PASSWORD)

    def _request(self, email):
        owner_auth_service.request_password_reset(email=email, base_url=f"http://{_HOST}")

    def _link(self):
        return re.search(r"/reset-password/[\w-]+/[\w-]+/", mail.outbox[-1].body).group(0)

    def test_case_insensitive_email(self):
        self._request("RST@Example.COM")
        self.assertEqual(len(mail.outbox), 1)

    def test_no_mail_for_customer_only_inactive_otp_only_or_ambiguous_accounts(self):
        customer = User.objects.create_user(username="09127770000", email="cust@example.com", password=_PASSWORD)
        Customer.objects.create(user=customer, full_name="C", phone="09127770000")
        off = owner_auth_service.register_owner(full_name="Off", email="off2@example.com", password=_PASSWORD)
        off.is_active = False
        off.save()
        otp_only = User.objects.create_user(username="09127770001", email="otp@example.com")
        otp_only.set_unusable_password()
        otp_only.save()
        OwnerProfile.objects.create(user=otp_only, phone="09127770001", full_name="Otp")
        a = User.objects.create_user(username="dup_a", email="dup@example.com", password=_PASSWORD)
        b = User.objects.create_user(username="dup_b", email="DUP@example.com", password=_PASSWORD)
        OwnerProfile.objects.create(user=a, full_name="A")
        OwnerProfile.objects.create(user=b, full_name="B")
        for email in ("cust@example.com", "off2@example.com", "otp@example.com", "dup@example.com"):
            with self.subTest(email=email):
                self._request(email)  # silently nothing
        self.assertEqual(mail.outbox, [])

    def test_superuser_and_member_accounts_can_reset(self):
        root = User.objects.create_superuser(username="root2", email="root2@example.com", password=_PASSWORD)
        member = User.objects.create_user(username="m1", email="m1@example.com", password=_PASSWORD)
        _member(_store("m-store"), member, role=StoreMembership.Role.ANALYST)
        for email in ("root2@example.com", "m1@example.com"):
            self._request(email)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(root.pk)

    def test_known_email_gets_mail_and_unknown_is_silent(self):
        self._request("nobody@example.com")
        self.assertEqual(mail.outbox, [])
        self._request("rst@example.com")
        self.assertEqual(len(mail.outbox), 1)

    def test_per_email_limit_is_silent(self):
        for _ in range(owner_auth_service.PASSWORD_RESET_EMAIL_MAX_PER_HOUR + 2):
            self._request("rst@example.com")
        self.assertEqual(len(mail.outbox), owner_auth_service.PASSWORD_RESET_EMAIL_MAX_PER_HOUR)

    def test_mail_link_uses_the_given_base_url(self):
        self._request("rst@example.com")
        self.assertRegex(mail.outbox[-1].body, r"https?://rastisi\.localhost/reset-password/")

    def test_a_forged_host_header_is_rejected_before_anything_happens(self):
        response = self.client.post("/reset-password/", {"phone": "09121234567"}, HTTP_HOST="evil.example")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_the_public_reset_page_no_longer_sends_email_at_all(self):
        response = self.client.post("/reset-password/", {"email": "rst@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)  # email is not a field any more: form re-renders
        self.assertEqual(mail.outbox, [])

    def test_full_flow_old_password_dies_new_works_link_is_single_use_and_sessions_are_revoked(self):
        other_session = self.client_class()
        _post_login(other_session, "rst@example.com")
        self.assertIn("_auth_user_id", other_session.session)

        self._request("rst@example.com")
        link = self._link()
        page = self.client.get(link, HTTP_HOST=_HOST)
        self.assertEqual(page.status_code, 200)
        # `origin`: neither `no-referrer` (browsers then POST with `Origin: null`, which Django's CSRF
        # origin check rejects) nor `same-origin` (sends the token-bearing path to our own logs).
        self.assertEqual(page["Referrer-Policy"], "origin")
        self.assertIn("no-store", page["Cache-Control"])
        self.assertContains(page, 'autocomplete="new-password"', count=2)
        done = self.client.post(link, {"password": "brand-new-strong-pass-9", "password_confirm": "brand-new-strong-pass-9"}, HTTP_HOST=_HOST)
        self.assertEqual(done.status_code, 302)

        self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 400)  # opened twice
        self.assertEqual(
            self.client.post(link, {"password": "another-strong-pass-8", "password_confirm": "another-strong-pass-8"}, HTTP_HOST=_HOST).status_code,
            400,
        )
        cache.clear()
        self.assertEqual(_post_login(self.client, "rst@example.com", _PASSWORD).status_code, 200)  # old password
        self.assertEqual(_post_login(self.client, "rst@example.com", "brand-new-strong-pass-9").status_code, 302)
        # Django's session auth hash: the session that existed before the reset is no longer authenticated.
        self.assertEqual(other_session.get("/app/", HTTP_HOST=_HOST).status_code, 302)

    def test_validation_errors_are_persian_use_the_configured_validators_and_sit_beside_the_field(self):
        self._request("rst@example.com")
        link = self._link()
        cases = {
            "short": ("abc", "abc"),
            "numeric": ("123456789012", "123456789012"),
            "common": ("password", "password"),
            "similar": ("rst@example.com", "rst@example.com"),
        }
        for name, (password, confirm) in cases.items():
            with self.subTest(name=name):
                response = self.client.post(link, {"password": password, "password_confirm": confirm}, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="id_password_error"')
                errors = re.search(r'id="id_password_error">(.*?)</ul>', response.content.decode(), re.S).group(1)
                text = re.sub(r"<[^>]+>", " ", errors)
                self.assertRegex(text, r"[؀-ۿ]")
                self.assertNotRegex(text, r"[A-Za-z]{4,}")
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(_PASSWORD))

    def test_mismatch_is_reported_on_the_confirmation_field(self):
        self._request("rst@example.com")
        response = self.client.post(self._link(), {"password": "brand-new-strong-pass-9", "password_confirm": "different-strong-pass-7"}, HTTP_HOST=_HOST)
        self.assertContains(response, 'id="id_password_confirm_error"')
        self.assertContains(response, "یکسان نیستند")

    def test_malformed_expired_and_foreign_tokens_are_rejected(self):
        self._request("rst@example.com")
        link = self._link()
        _, _, uid, token, _ = link.split("/")
        for path in (
            "/reset-password/!!!/abc-def/", f"/reset-password/{uid}/{token[:-3]}xyz/", "/reset-password/MQ/zzz-zzzz/",
            f"/reset-password/{'A' * 5000}/{token}/", f"/reset-password/{uid}/{'t' * 3000}/",
        ):
            with self.subTest(path=path[:60]):
                self.assertEqual(self.client.get(path, HTTP_HOST=_HOST).status_code, 400)
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 400)

    def test_link_dies_when_the_account_is_deactivated_or_stops_being_an_owner(self):
        self._request("rst@example.com")
        link = self._link()
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 400)

    def test_a_login_after_the_mail_invalidates_the_link(self):
        self._request("rst@example.com")
        link = self._link()
        _post_login(self.client, "rst@example.com")  # last_login changes → token invalid (Django behaviour)
        self.assertEqual(self.client.get(link, HTTP_HOST=_HOST).status_code, 400)


# ---------------------------------------------------------------------------
# Reset-confirm: the token is in the URL path, so it must never become a Referer
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class ResetConfirmReferrerPolicyAndCsrfTests(_Base, TestCase):
    """Pins ``Referrer-Policy: origin`` and proves the form still passes real CSRF checks.

    * ``no-referrer`` is wrong: browsers then send ``Origin: null`` on the form POST and Django's
      CSRF origin check (correctly) rejects it.
    * ``same-origin`` is wrong: the full ``/reset-password/<uid>/<token>/`` path would be sent as the
      Referer of every same-origin CSS/JS request and land in access/proxy/CDN logs.
    * ``origin`` sends scheme+host+port only and keeps a real ``Origin`` on the POST.
    """

    ORIGIN = f"http://{_HOST}"
    NEW = "brand-new-strong-pass-9"

    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(full_name="Ref", email="ref@example.com", password=_PASSWORD)
        owner_auth_service.request_password_reset(email="ref@example.com", base_url=f"http://{_HOST}")
        self.link = re.search(r"/reset-password/[\w-]+/[\w-]+/", mail.outbox[-1].body).group(0)
        self.csrf_client = self.client_class(enforce_csrf_checks=True)

    def assertSafeHeaders(self, response):
        self.assertEqual(response["Referrer-Policy"], "origin")
        self.assertIn("no-store", response["Cache-Control"])

    def _csrf_token(self, page):
        return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)

    def _form(self, token, password=None):
        password = password or self.NEW
        return {"csrfmiddlewaretoken": token, "password": password, "password_confirm": password}

    def test_valid_link_response_sends_origin_only_and_is_not_cacheable(self):
        self.assertSafeHeaders(self.client.get(self.link, HTTP_HOST=_HOST))

    def test_failed_validation_rerender_keeps_the_policy(self):
        response = self.client.post(self.link, {"password": "abc", "password_confirm": "abc"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertSafeHeaders(response)

    def test_every_invalid_link_response_has_the_same_policy(self):
        _, _, uid, token, _ = self.link.split("/")
        paths = {
            "garbage uid": f"/reset-password/!!!/{token}/",
            "tampered token": f"/reset-password/{uid}/{token[:-3]}xyz/",
            "unknown user": f"/reset-password/{'Mzk5OTk5'}/{token}/",
            "oversized": f"/reset-password/{'A' * 5000}/{'t' * 3000}/",
        }
        for name, path in paths.items():
            with self.subTest(name=name):
                response = self.client.get(path, HTTP_HOST=_HOST)
                self.assertEqual(response.status_code, 400)
                self.assertSafeHeaders(response)
                self.assertNotIn('rel="canonical"', response.content.decode())
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):  # expired
            expired = self.client.get(self.link, HTTP_HOST=_HOST)
        self.assertEqual(expired.status_code, 400)
        self.assertSafeHeaders(expired)

    def test_policy_is_exactly_origin_not_a_weaker_value(self):
        self.assertEqual(portal_views.RESET_CONFIRM_REFERRER_POLICY, "origin")
        response = self.client.get(self.link, HTTP_HOST=_HOST)
        self.assertNotIn(response["Referrer-Policy"], {"same-origin", "unsafe-url", "no-referrer-when-downgrade", "origin-when-cross-origin", ""})

    def test_page_cannot_override_the_header_and_never_echoes_the_token(self):
        html = self.client.get(self.link, HTTP_HOST=_HOST).content.decode()
        self.assertNotRegex(html, r'(?i)<meta[^>]+name=["\']referrer["\']')  # a <meta> would override the header
        self.assertNotRegex(html, r'(?i)referrerpolicy=["\'](?!origin["\'])')
        self.assertNotIn(self.link.strip("/").split("/")[-1], html)  # token is not rendered anywhere (incl. <link rel=canonical>)
        self.assertNotIn('rel="canonical"', html)
        self.assertNotIn(self.link, html)  # the token path is not linked or embedded either

    def test_real_csrf_enforced_post_succeeds_with_the_real_origin(self):
        page = self.csrf_client.get(self.link, HTTP_HOST=_HOST)
        done = self.csrf_client.post(self.link, self._form(self._csrf_token(page)), HTTP_HOST=_HOST, HTTP_ORIGIN=self.ORIGIN)
        self.assertEqual(done.status_code, 302)
        self.assertEqual(done["Location"], "/login-email/")  # legacy alias that forwards to /login/
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(self.NEW))

    def test_csrf_is_not_weakened_missing_token_null_origin_and_foreign_origin_are_rejected(self):
        page = self.csrf_client.get(self.link, HTTP_HOST=_HOST)
        token = self._csrf_token(page)
        cases = {
            "no csrf token": ({"password": self.NEW, "password_confirm": self.NEW}, self.ORIGIN),
            "Origin: null (what no-referrer produces)": (self._form(token), "null"),
            "foreign Origin": (self._form(token), "https://evil.example"),
        }
        for name, (data, origin) in cases.items():
            with self.subTest(name=name):
                response = self.csrf_client.post(self.link, data, HTTP_HOST=_HOST, HTTP_ORIGIN=origin)
                self.assertEqual(response.status_code, 403)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(_PASSWORD))  # nothing changed, token not consumed
        self.assertEqual(self.client.get(self.link, HTTP_HOST=_HOST).status_code, 200)

    def test_token_is_single_use_with_real_csrf_enforcement(self):
        page = self.csrf_client.get(self.link, HTTP_HOST=_HOST)
        token = self._csrf_token(page)
        first = self.csrf_client.post(self.link, self._form(token), HTTP_HOST=_HOST, HTTP_ORIGIN=self.ORIGIN)
        self.assertEqual(first.status_code, 302)
        replay_get = self.csrf_client.get(self.link, HTTP_HOST=_HOST)
        self.assertEqual(replay_get.status_code, 400)
        self.assertSafeHeaders(replay_get)
        replay_post = self.csrf_client.post(
            self.link, self._form(token, "another-strong-pass-8"), HTTP_HOST=_HOST, HTTP_ORIGIN=self.ORIGIN,
        )
        self.assertEqual(replay_post.status_code, 400)
        self.assertSafeHeaders(replay_post)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password(self.NEW))


# ---------------------------------------------------------------------------
# Login page markup (no JavaScript required, accessible)
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class LoginPageMarkupTests(_Base, TestCase):
    def test_method_tabs_are_real_links_and_work_without_javascript_or_alpine(self):
        password_page = self.client.get("/login/?next=/app/stores/new/", HTTP_HOST=_HOST)
        html = password_page.content.decode()
        self.assertNotIn("x-show", html.split("<main>")[1].split("</main>")[0])
        self.assertNotIn("x-cloak", html.split("<main>")[1].split("</main>")[0])
        self.assertContains(password_page, 'href="/login/?mode=otp&amp;next=/app/stores/new/"')
        self.assertRegex(html, r'id="login-panel-otp"[^>]*\bhidden\b')
        self.assertNotRegex(html, r'id="login-panel-password"[^>]*\bhidden\b')
        otp_page = self.client.get("/login/?mode=otp", HTTP_HOST=_HOST)
        otp_html = otp_page.content.decode()
        self.assertRegex(otp_html, r'id="login-panel-password"[^>]*\bhidden\b')
        self.assertNotRegex(otp_html, r'id="login-panel-otp"[^>]*\bhidden\b')
        self.assertEqual(otp_html.count('aria-current="true"'), 1)

    def test_otp_failure_reopens_the_otp_tab_and_password_failure_keeps_the_password_tab(self):
        otp = self.client.post("/login/", {"phone": "123"}, HTTP_HOST=_HOST)
        self.assertNotRegex(otp.content.decode(), r'id="login-panel-otp"[^>]*\bhidden\b')
        self.assertContains(otp, 'id="id_phone_error"')
        password = _post_login(self.client, "x@example.com", "bad")
        self.assertNotRegex(password.content.decode(), r'id="login-panel-password"[^>]*\bhidden\b')

    def test_field_attributes_for_password_managers_keyboards_and_direction(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertRegex(html, r'name="identifier"[^>]*autocomplete="username"[^>]*dir="ltr"')
        self.assertRegex(html, r'name="password"[^>]*autocomplete="current-password"')
        self.assertRegex(html, r'name="phone"[^>]*autocomplete="tel" inputmode="tel" dir="ltr"')
        self.assertNotIn("new-password", html)
        self.assertEqual(html.count('name="csrfmiddlewaretoken"'), 3)  # base + 2 forms

    def test_copy_is_user_facing_and_truthful(self):
        html = self.client.get("/login/", HTTP_HOST=_HOST).content.decode()
        self.assertNotIn("جریان‌های امنیتی موجود پروژه", html)
        self.assertIn("کد پیامکی", html)
        self.assertIn("نام و نام خانوادگی شما را می‌پرسیم", html)

    def test_flash_messages_render_inline_not_as_a_bottom_toast(self):
        owner = owner_auth_service.register_owner(full_name="Flash", email="flash@example.com", password=_PASSWORD)
        owner.is_active = False
        owner.save()
        page = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertNotContains(page, "position:fixed;bottom:16px")

    def test_reset_pages_share_the_auth_design_system(self):
        for url in ("/reset-password/",):
            html = self.client.get(url, HTTP_HOST=_HOST).content.decode()
            self.assertIn("rs-btn rs-btn-primary", html)
            self.assertNotIn('class="r-wrap"', html)
            self.assertRegex(html, r'name="phone"[^>]*autocomplete="tel"')
            self.assertNotIn('name="email"', html)

    def test_password_form_class_has_no_creation_validation(self):
        form = OwnerIdentifierLoginForm({"identifier": "someone", "password": "1"})
        self.assertTrue(form.is_valid())


# ---------------------------------------------------------------------------
# OTP login through the real /login/ view (regression of the hardened engine)
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OtpLoginThroughViewTests(_Base, TestCase):
    def setUp(self):
        super().setUp()
        self.sent = []
        patcher = patch.object(owner_otp_service, "send_platform_otp", side_effect=self._send)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _send(self, *, to, code, **_):
        self.sent.append(code)
        return SmsSendResult(success=True, provider_ref_id="t")

    def _request(self, phone):
        return self.client.post("/login/", {"phone": phone}, HTTP_HOST=_HOST)

    def test_persian_digit_phone_and_code_work(self):
        owner = User.objects.create_user(username="09124440001")
        OwnerProfile.objects.create(user=owner, phone="09124440001", full_name="Fa")
        self.assertEqual(self._request("۰۹۱۲۴۴۴۰۰۰۱")["Location"], "/verify/")
        fa_code = self.sent[-1].translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        response = self.client.post("/verify/", {"code": fa_code}, HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/app/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), owner.pk)

    def test_customer_only_phone_is_sent_to_signup_completion_and_stays_anonymous(self):
        customer = User.objects.create_user(username="09124440002", password="cust-pass-123")
        before = customer.password
        self._request("09124440002")
        response = self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/signup/complete/")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(OwnerProfile.objects.filter(user=customer).exists())
        customer.refresh_from_db()
        self.assertEqual(customer.password, before)

    def test_inactive_owner_cannot_log_in_with_otp_and_sees_an_inline_message(self):
        owner = User.objects.create_user(username="09124440003", is_active=False)
        OwnerProfile.objects.create(user=owner, phone="09124440003", full_name="Off")
        self._request("09124440003")
        response = self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)
        page = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(page, "ورود با این شماره امکان‌پذیر نیست")
        self.assertContains(page, 'role="alert"')

    def test_verify_without_a_started_login_redirects_and_a_posted_phone_is_never_trusted(self):
        self.assertEqual(self.client.post("/verify/", {"code": "123456", "phone": "09124440009"}, HTTP_HOST=_HOST)["Location"], "/login/")
        owner = User.objects.create_user(username="09124440004")
        OwnerProfile.objects.create(user=owner, phone="09124440004", full_name="O")
        self._request("09124440004")
        stale = self.client.post("/verify/", {"code": self.sent[-1], "phone": "09124440005"}, HTTP_HOST=_HOST)
        self.assertEqual(stale.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_code_attempt_cap_and_expiry_messages(self):
        owner = User.objects.create_user(username="09124440006")
        OwnerProfile.objects.create(user=owner, phone="09124440006", full_name="O")
        self._request("09124440006")
        wrong = "000000" if self.sent[-1] != "000000" else "111111"
        for _ in range(owner_otp_service.MAX_VERIFY_ATTEMPTS):
            response = self.client.post("/verify/", {"code": wrong}, HTTP_HOST=_HOST)
            self.assertContains(response, "id_code_error")
        locked = self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)
        self.assertContains(locked, "تعداد تلاش")
        self.assertNotIn("_auth_user_id", self.client.session)
        OwnerOtpChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)
        self.assertContains(expired, "منقضی")

    def test_new_phone_login_creates_nothing_before_the_name_step(self):
        self._request("09124440007")
        response = self.client.post("/verify/", {"code": self.sent[-1]}, HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/signup/complete/")
        self.assertFalse(User.objects.filter(username="09124440007").exists())
        self.assertFalse(OwnerProfile.objects.filter(phone="09124440007").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_otp_request_budget_per_phone_applies_through_the_login_view(self):
        for _ in range(owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW):
            self.assertEqual(self._request("09124440008")["Location"], "/verify/")
            age_otp_cooldown("09124440008")  # past the per-request resend cooldown; the 10-minute window still counts
            self.client.get("/login/", HTTP_HOST=_HOST)
        blocked = self._request("09124440008")
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "بیش از حد مجاز")
        self.assertEqual(len(self.sent), owner_otp_service.MAX_REQUESTS_PER_PHONE_WINDOW)

    def test_provider_failure_is_a_controlled_error_not_a_500(self):
        with patch.object(owner_otp_service, "send_platform_otp", return_value=SmsSendResult(success=False, error_message="down")):
            response = self._request("09124440010")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ارسال کد تأیید موقتاً انجام نشد")
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone="09124440010").exists())
