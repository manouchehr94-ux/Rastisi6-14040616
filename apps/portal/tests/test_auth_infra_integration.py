"""Production auth-infrastructure integration (hardening/production-auth-infra-v1).

* client-IP bucketing through the REAL public auth views behind/without a trusted proxy;
* rate-limit backend outage => controlled fail-closed on every anonymous endpoint;
* Turnstile provider outage / misconfiguration => no password auth, no SMS, no mail.

LocMem stands in for the shared store here; real Redis behaviour is covered by
``apps.core.tests.test_rate_limit_redis``.
"""

from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.content.models import NewsletterSubscriber
from apps.core.services import rate_limit
from apps.core.services.rate_limit import UNAVAILABLE_MESSAGE, RateLimitUnavailable
from apps.portal.models import ContactMessage, OwnerOtpChallenge, OwnerProfile
from apps.portal.services import owner_auth_service, owner_otp_service, turnstile_service
from apps.sms.services import otp_service as store_otp_service
from apps.sms.services.backends import SmsSendResult

User = get_user_model()
_HOST = "rastisi.localhost"
_ADMIN_HOST = "platformadmins.rastisi.localhost"
_PASSWORD = "a-very-strong-pass-1"
_THROTTLED = "تعداد تلاش ورود بیش از حد مجاز است"
_PROXY = "10.0.0.2"
_HOSTS = [_HOST, _ADMIN_HOST, "testserver"]


class _DownCounter:
    """A rate-limit backend whose every operation fails (Redis outage)."""

    def hit(self, key, window_seconds):
        raise ConnectionError("redis://:topsecret@10.0.0.9:6379/0 unreachable")


def _outage():
    return patch.object(rate_limit, "get_counter", return_value=_DownCounter())


class _Base(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)


# ---------------------------------------------------------------------------
# Client-IP buckets through the real views
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=_HOSTS)
class PasswordLoginIpBucketTests(_Base):
    def _post(self, remote_addr, xff=None):
        extra = {"REMOTE_ADDR": remote_addr, "HTTP_HOST": _HOST}
        if xff is not None:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        # An empty form is invalid (no password hashing => fast) yet still spends the IP budget.
        return self.client.post("/login/password/", {}, **extra)

    def _exhaust(self, remote_addr, xff=None, attempts=15):
        for _ in range(attempts):
            self.assertNotContains(self._post(remote_addr, xff), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_two_visitors_behind_one_trusted_proxy_get_separate_buckets(self):
        self._exhaust(_PROXY, "203.0.113.44")
        self.assertContains(self._post(_PROXY, "203.0.113.44"), _THROTTLED)
        self.assertNotContains(self._post(_PROXY, "203.0.113.45"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_same_client_stays_in_one_bucket_across_proxy_header_formatting(self):
        self._exhaust(_PROXY, "203.0.113.44", attempts=5)
        self._exhaust("10.9.9.9", "6.6.6.6, 203.0.113.44, 10.0.0.1", attempts=5)
        self._exhaust(_PROXY, "  203.0.113.44 ", attempts=5)
        self.assertContains(self._post(_PROXY, "198.51.100.1, 203.0.113.44"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_attacker_cannot_pick_a_fresh_bucket_by_prepending_to_xff(self):
        # the trusted proxy appends the attacker's real address; fake left entries are irrelevant
        for index in range(15):
            self._post(_PROXY, f"1.1.1.{index}, 203.0.113.99")
        self.assertContains(self._post(_PROXY, "9.9.9.9, 203.0.113.99"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_direct_attacker_cannot_rotate_spoofed_xff_to_bypass_the_budget(self):
        for index in range(15):
            self._post("203.0.113.10", f"1.2.3.{index}")
        self.assertContains(self._post("203.0.113.10", "7.7.7.7"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_direct_attacker_is_not_helped_by_a_trusted_network_in_xff(self):
        for index in range(15):
            self._post("203.0.113.10", f"10.0.0.{index}")
        self.assertContains(self._post("203.0.113.10", "10.0.0.250"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_without_trusted_proxies_distinct_peers_have_distinct_buckets(self):
        self._exhaust("203.0.113.10")
        self.assertContains(self._post("203.0.113.10"), _THROTTLED)
        self.assertNotContains(self._post("203.0.113.11"), _THROTTLED)

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_one_ipv6_64_is_one_bucket(self):
        for index in range(15):
            self._post(f"2001:db8:1:2:{index:x}::1")
        self.assertContains(self._post("2001:db8:1:2:ffff::9"), _THROTTLED)
        self.assertNotContains(self._post("2001:db8:1:3::1"), _THROTTLED)


@override_settings(ALLOWED_HOSTS=_HOSTS, RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
class OtherEndpointsUseTheResolverTests(_Base):
    def test_otp_request_budget_is_charged_to_the_resolved_client_ip(self):
        with patch.object(owner_otp_service, "request_otp") as request_otp:
            self.client.post(
                "/login/", {"phone": "09121234567"}, HTTP_HOST=_HOST,
                REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.44",
            )
            self.client.post(
                "/login/", {"phone": "09121234567"}, HTTP_HOST=_HOST,
                REMOTE_ADDR="203.0.113.10", HTTP_X_FORWARDED_FOR="1.2.3.4",
            )
        self.assertEqual(
            [call.kwargs["client_ip"] for call in request_otp.call_args_list],
            ["203.0.113.44", "203.0.113.10"],
        )

    def test_registration_otp_uses_the_resolver(self):
        with patch.object(owner_otp_service, "request_otp") as request_otp:
            self.client.post(
                "/register/", {"full_name": "Test User", "phone": "09121234567"}, HTTP_HOST=_HOST,
                REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR="203.0.113.77",
            )
        self.assertEqual(request_otp.call_args.kwargs["client_ip"], "203.0.113.77")

    def test_password_reset_budget_is_per_real_client(self):
        def post(xff):
            return self.client.post(
                "/reset-password/", {}, HTTP_HOST=_HOST, REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR=xff,
            )
        for _ in range(5):
            post("203.0.113.44")
        self.assertContains(post("203.0.113.44"), "بیش از حد مجاز")
        self.assertNotContains(post("203.0.113.45"), "بیش از حد مجاز")

    def test_contact_budget_is_per_real_client(self):
        def post(xff):
            return self.client.post(
                "/contact/", {}, HTTP_HOST=_HOST, REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR=xff,
            )
        for _ in range(5):
            post("203.0.113.44")
        self.assertContains(post("203.0.113.44"), "بیش از حد مجاز")
        self.assertNotContains(post("203.0.113.45"), "بیش از حد مجاز")

    def test_storefront_customer_otp_uses_the_resolver(self):
        with patch("apps.customers.views.Customer") as customer, \
                patch.object(store_otp_service, "request_otp", side_effect=store_otp_service.OtpRateLimitError("x")) as request_otp:
            customer.objects.filter.return_value.exists.return_value = True
            self.client.post(
                "/account/otp/request/", {"phone": "09121234567"},
                REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.88",
            )
        self.assertEqual(request_otp.call_args.kwargs["ip_address"], "203.0.113.88")

    def test_turnstile_remoteip_comes_from_the_resolver_not_raw_headers(self):
        request = RequestFactory().post(
            "/", {"cf-turnstile-response": "tok"},
            REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.44", HTTP_CF_CONNECTING_IP="6.6.6.6",
        )
        with patch.object(turnstile_service, "verify_token") as verify:
            turnstile_service.verify_request(request, expected_action="login_password")
        self.assertEqual(verify.call_args.kwargs["remote_ip"], "203.0.113.44")

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_turnstile_remoteip_ignores_forwarded_headers_from_a_direct_peer(self):
        request = RequestFactory().post(
            "/", {"cf-turnstile-response": "tok"},
            REMOTE_ADDR="203.0.113.10", HTTP_X_FORWARDED_FOR="1.2.3.4", HTTP_CF_CONNECTING_IP="6.6.6.6",
        )
        with patch.object(turnstile_service, "verify_token") as verify:
            turnstile_service.verify_request(request, expected_action="login_password")
        self.assertEqual(verify.call_args.kwargs["remote_ip"], "203.0.113.10")


# ---------------------------------------------------------------------------
# Shared-store outage => fail closed, controlled, no 500
# ---------------------------------------------------------------------------


@override_settings(ALLOWED_HOSTS=_HOSTS)
class RateLimitOutageFailsClosedTests(_Base):
    def setUp(self):
        super().setUp()
        self.owner = owner_auth_service.register_owner(
            full_name="Outage", email="outage@example.com", password=_PASSWORD,
        )

    def test_password_login_is_refused_even_with_correct_credentials(self):
        with _outage(), patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
            response = self.client.post(
                "/login/password/", {"identifier": "outage@example.com", "password": _PASSWORD}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotContains(response, "topsecret")
        self.assertNotContains(response, "Traceback")

    def test_identifier_budget_outage_after_ip_budget_succeeds_still_blocks_login(self):
        # IP counter works, the per-identifier counter then fails
        real = rate_limit.enforce_rate_limit
        def selective(action, *args, **kwargs):
            if action == "login_password_identifier":
                raise RateLimitUnavailable(UNAVAILABLE_MESSAGE)
            return real(action, *args, **kwargs)
        with patch("apps.portal.views.enforce_rate_limit", side_effect=selective), \
                patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
            response = self.client.post(
                "/login/password/", {"identifier": "outage@example.com", "password": _PASSWORD}, HTTP_HOST=_HOST,
            )
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_otp_request_sends_no_sms_and_creates_no_challenge(self):
        with _outage(), patch.object(owner_otp_service, "send_platform_otp") as send:
            response = self.client.post("/login/", {"phone": "09121234567"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        send.assert_not_called()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_registration_otp_request_sends_no_sms(self):
        with _outage(), patch.object(owner_otp_service, "send_platform_otp") as send:
            response = self.client.post(
                "/register/", {"full_name": "Test User", "phone": "09121234567"}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        send.assert_not_called()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_password_reset_sends_no_sms_when_the_counter_is_down(self):
        OwnerProfile.objects.filter(user=self.owner).update(phone="09121230001")
        with _outage(), patch.object(owner_otp_service, "send_platform_otp") as send:
            response = self.client.post("/reset-password/", {"phone": "09121230001"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        send.assert_not_called()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_legacy_per_email_budget_outage_sends_no_mail_and_stays_silent(self):
        with patch.object(owner_auth_service, "enforce_rate_limit", side_effect=RateLimitUnavailable("x")):
            owner_auth_service.request_password_reset(email="outage@example.com", base_url="http://rastisi.localhost")
        self.assertEqual(mail.outbox, [])

    def test_contact_form_is_refused_with_a_controlled_message(self):
        with _outage():
            response = self.client.post(
                "/contact/", {"name": "x", "email": "a@example.com", "message": "hello hello hello"}, HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_platform_admin_login_is_refused(self):
        staff = User.objects.create_user(
            username="pa@example.com", email="pa@example.com", password=_PASSWORD, is_staff=True, is_superuser=True,
        )
        with _outage(), patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
            response = self.client.post(
                "/login/", {"identifier": staff.email, "password": _PASSWORD}, HTTP_HOST=_ADMIN_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_storefront_newsletter_is_refused_not_a_500(self):
        with _outage():
            response = self.client.post(reverse("content:newsletter-subscribe"), {"email": "n@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, UNAVAILABLE_MESSAGE)
        self.assertFalse(NewsletterSubscriber.objects.filter(email="n@example.com").exists())

    def test_storefront_customer_otp_service_sends_no_sms(self):
        with _outage(), patch.object(store_otp_service, "send_event_sms") as send, \
                self.assertRaises(store_otp_service.OtpRateLimitError) as ctx:
            from apps.stores.models import Store
            store_otp_service.request_otp("09121234567", store=Store.objects.first(), ip_address="1.2.3.4")
        self.assertEqual(str(ctx.exception), UNAVAILABLE_MESSAGE)
        send.assert_not_called()

    def test_owner_otp_service_raises_the_controlled_delivery_error(self):
        with _outage(), patch.object(owner_otp_service, "send_platform_otp") as send:
            with self.assertRaises(owner_otp_service.OtpDeliveryError) as ctx:
                owner_otp_service.request_otp(phone="09121234567", purpose="login", client_ip="1.2.3.4")
        self.assertEqual(str(ctx.exception), UNAVAILABLE_MESSAGE)
        send.assert_not_called()

    def test_authenticated_and_marketing_pages_do_not_depend_on_the_rate_limit_store(self):
        self.client.force_login(self.owner)
        with _outage():
            self.assertEqual(self.client.get("/app/", HTTP_HOST=_HOST).status_code, 200)
            self.assertEqual(self.client.get("/", HTTP_HOST=_HOST).status_code, 200)
            self.assertEqual(self.client.get("/login/", HTTP_HOST=_HOST).status_code, 302)  # already authenticated

    def test_anonymous_pages_render_during_an_outage(self):
        with _outage():
            for path in ("/", "/login/", "/register/", "/contact/", "/reset-password/"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path, HTTP_HOST=_HOST).status_code, 200)

    def test_per_store_authenticated_throttles_are_explicitly_fail_open(self):
        from apps.storefront_builder.services import layout_service
        for limit in (layout_service._PUBLISH_RATE_LIMIT, layout_service._RESTORE_RATE_LIMIT,
                      layout_service._NEW_DRAFT_RATE_LIMIT):
            self.assertTrue(limit["fail_open"])
            with _outage():
                rate_limit.enforce_rate_limit("storefront_layout.publish", "1", **limit)  # must not raise


# ---------------------------------------------------------------------------
# Turnstile outage / misconfiguration => nothing protected happens
# ---------------------------------------------------------------------------

_TS = dict(
    TURNSTILE_ENABLED=True,
    TURNSTILE_SITE_KEY="1x00000000000000000000AA",
    TURNSTILE_SECRET_KEY="1x0000000000000000000000000000AA",
    TURNSTILE_EXPECTED_HOSTNAMES=(_HOST,),
    TURNSTILE_VERIFY_TIMEOUT_SECONDS=5,
    ALLOWED_HOSTS=_HOSTS,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _siteverify(**kwargs):
    return patch("apps.portal.services.turnstile_service.requests.post", **kwargs)


@override_settings(**_TS)
class TurnstileOutageFailsClosedTests(_Base):
    OUTAGES = (
        ("timeout", {"side_effect": requests.Timeout("t")}),
        ("connection", {"side_effect": requests.ConnectionError("c")}),
        ("unexpected exception", {"side_effect": RuntimeError("boom")}),
        ("invalid json", {"return_value": _Response(ValueError("not json"))}),
        ("non-dict json", {"return_value": _Response(["success"])}),
        ("odd error-codes", {"return_value": _Response({"success": False, "error-codes": {"x": 1}})}),
    )

    def setUp(self):
        super().setUp()
        owner_auth_service.register_owner(full_name="TS", email="ts@example.com", password=_PASSWORD)

    def test_password_login_never_authenticates(self):
        for label, kwargs in self.OUTAGES:
            with self.subTest(label), _siteverify(**kwargs), \
                    patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
                response = self.client.post(
                    "/login/password/",
                    {"identifier": "ts@example.com", "password": _PASSWORD, "cf-turnstile-response": "tok"},
                    HTTP_HOST=_HOST,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
                authenticate.assert_not_called()
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_otp_request_never_reaches_the_sms_provider(self):
        for path, data in (("/login/", {"phone": "09121234567"}),
                           ("/register/", {"full_name": "Test User", "phone": "09121234567"})):
            for label, kwargs in self.OUTAGES:
                with self.subTest(path=path, label=label), _siteverify(**kwargs), \
                        patch.object(owner_otp_service, "send_platform_otp") as send:
                    response = self.client.post(path, {**data, "cf-turnstile-response": "tok"}, HTTP_HOST=_HOST)
                    self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
                    send.assert_not_called()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)

    def test_password_reset_never_sends_sms_or_mail(self):
        OwnerProfile.objects.filter(user__email="ts@example.com").update(phone="09121230002")
        for label, kwargs in self.OUTAGES:
            cache.clear()  # six outages would otherwise exhaust the per-IP reset budget (5)
            with self.subTest(label), _siteverify(**kwargs), patch.object(owner_otp_service, "send_platform_otp") as send:
                response = self.client.post(
                    "/reset-password/", {"phone": "09121230002", "cf-turnstile-response": "tok"}, HTTP_HOST=_HOST,
                )
                self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
                send.assert_not_called()
        self.assertEqual(OwnerOtpChallenge.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_missing_token_never_calls_the_provider_or_the_protected_action(self):
        with _siteverify() as post, patch.object(owner_otp_service, "send_platform_otp") as send:
            self.client.post("/login/", {"phone": "09121234567"}, HTTP_HOST=_HOST)
        post.assert_not_called()
        send.assert_not_called()

    def test_wrong_action_and_hostname_are_rejected(self):
        for payload in (
            {"success": True, "hostname": _HOST, "action": "register"},      # wrong action for login
            {"success": True, "hostname": "evil.example", "action": "login_password"},
            {"success": True, "hostname": "", "action": "login_password"},
        ):
            with self.subTest(payload=payload), _siteverify(return_value=_Response(payload)), \
                    patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
                response = self.client.post(
                    "/login/password/",
                    {"identifier": "ts@example.com", "password": _PASSWORD, "cf-turnstile-response": "tok"},
                    HTTP_HOST=_HOST,
                )
                self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
                authenticate.assert_not_called()

    def test_valid_challenge_still_logs_in(self):
        ok = {"success": True, "hostname": _HOST, "action": "login_password"}
        with _siteverify(return_value=_Response(ok)):
            response = self.client.post(
                "/login/password/",
                {"identifier": "ts@example.com", "password": _PASSWORD, "cf-turnstile-response": "tok"},
                HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_remoteip_sent_to_the_provider_is_the_trusted_resolver_value(self):
        ok = {"success": True, "hostname": _HOST, "action": "login_password"}
        with override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",)), \
                _siteverify(return_value=_Response(ok)) as post:
            self.client.post(
                "/login/password/",
                {"identifier": "ts@example.com", "password": "x", "cf-turnstile-response": "tok"},
                HTTP_HOST=_HOST, REMOTE_ADDR=_PROXY, HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.44",
            )
        self.assertEqual(post.call_args.kwargs["data"]["remoteip"], "203.0.113.44")


@override_settings(ALLOWED_HOSTS=_HOSTS)
class TurnstileProductionRuntimeGuardTests(_Base):
    """Defence in depth behind the startup/system-check enforcement."""

    def setUp(self):
        super().setUp()
        owner_auth_service.register_owner(full_name="TS", email="ts@example.com", password=_PASSWORD)

    @override_settings(RASTISI_PRODUCTION_MODE=True, TURNSTILE_ENABLED=False)
    def test_production_with_turnstile_off_can_never_succeed(self):
        result = turnstile_service.verify_token(token="", expected_action="login_password")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "turnstile-misconfigured")
        with patch.object(owner_auth_service, "authenticate_owner_by_identifier") as authenticate:
            response = self.client.post(
                "/login/password/", {"identifier": "ts@example.com", "password": _PASSWORD}, HTTP_HOST=_HOST,
            )
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        authenticate.assert_not_called()

    @override_settings(RASTISI_PRODUCTION_MODE=True, **{**_TS, "TURNSTILE_EXPECTED_HOSTNAMES": ()})
    def test_production_without_expected_hostnames_fails_closed_even_on_provider_success(self):
        ok = {"success": True, "hostname": "anything.example", "action": "login_password"}
        with _siteverify(return_value=_Response(ok)):
            result = turnstile_service.verify_token(token="tok", expected_action="login_password")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "hostname-not-configured")

    @override_settings(RASTISI_PRODUCTION_MODE=False, TURNSTILE_ENABLED=False)
    def test_development_may_intentionally_run_without_turnstile(self):
        self.assertTrue(turnstile_service.verify_token(token="", expected_action="x").success)
        response = self.client.post(
            "/login/password/", {"identifier": "ts@example.com", "password": _PASSWORD}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
