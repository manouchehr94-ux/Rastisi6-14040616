"""Forwarded-proto (``SECURE_PROXY_SSL_HEADER``) must only be honoured from a trusted proxy."""

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.core.middleware import TrustedProxyHeaderMiddleware
from shop_core.checks import check_trusted_proxy

_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


def _scheme_after_sanitising(remote_addr, proto="https"):
    request = RequestFactory().get("/", REMOTE_ADDR=remote_addr, HTTP_X_FORWARDED_PROTO=proto)
    TrustedProxyHeaderMiddleware(lambda r: None).process_request(request)
    return request.scheme, request.is_secure()


@override_settings(SECURE_PROXY_SSL_HEADER=_HEADER, RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
class ForwardedProtoTests(SimpleTestCase):
    def test_untrusted_direct_peer_cannot_spoof_https(self):
        self.assertEqual(_scheme_after_sanitising("203.0.113.10"), ("http", False))

    def test_trusted_proxy_can_still_report_https(self):
        self.assertEqual(_scheme_after_sanitising("10.1.2.3"), ("https", True))

    def test_trusted_proxy_http_stays_http(self):
        self.assertEqual(_scheme_after_sanitising("10.1.2.3", proto="http"), ("http", False))

    def test_garbage_peer_cannot_spoof_https(self):
        self.assertEqual(_scheme_after_sanitising("garbage"), ("http", False))

    @override_settings(RASTISI_TRUSTED_PROXY_CIDRS=())
    def test_without_trusted_proxies_the_header_is_never_honoured(self):
        self.assertEqual(_scheme_after_sanitising("10.1.2.3"), ("http", False))

    def test_unsanitised_django_would_have_been_fooled(self):
        # proves the middleware is what closes the hole (Django alone trusts the header)
        request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.10", HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(request.is_secure())

    @override_settings(SECURE_PROXY_SSL_HEADER=None)
    def test_no_header_configured_is_a_noop(self):
        self.assertEqual(_scheme_after_sanitising("203.0.113.10"), ("http", False))


class MiddlewareWiringTests(TestCase):
    def test_sanitiser_runs_before_security_middleware(self):
        middleware = list(settings.MIDDLEWARE)
        self.assertEqual(middleware[0], "apps.core.middleware.TrustedProxyHeaderMiddleware")
        self.assertLess(
            middleware.index("apps.core.middleware.TrustedProxyHeaderMiddleware"),
            middleware.index("django.middleware.security.SecurityMiddleware"),
        )

    def test_full_stack_rejects_spoofed_https_from_untrusted_peer(self):
        with override_settings(
            SECURE_PROXY_SSL_HEADER=_HEADER, RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
            SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["testserver"],
        ):
            from django.test import Client
            client = Client()
            spoofed = client.get("/", REMOTE_ADDR="203.0.113.10", HTTP_X_FORWARDED_PROTO="https")
            self.assertEqual(spoofed.status_code, 301)  # still treated as plain HTTP -> redirected
            trusted = client.get("/", REMOTE_ADDR="10.1.2.3", HTTP_X_FORWARDED_PROTO="https")
            self.assertNotEqual(trusted.status_code, 301)

    def test_check_flags_wrong_middleware_order(self):
        bad = [
            "django.middleware.security.SecurityMiddleware",
            "apps.core.middleware.TrustedProxyHeaderMiddleware",
        ]
        with override_settings(
            MIDDLEWARE=bad, SECURE_PROXY_SSL_HEADER=_HEADER, RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
        ):
            self.assertEqual([e.id for e in check_trusted_proxy(None)], ["rastisi.E004"])
        with override_settings(
            MIDDLEWARE=["django.middleware.security.SecurityMiddleware"],
            SECURE_PROXY_SSL_HEADER=_HEADER, RASTISI_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",),
        ):
            self.assertEqual([e.id for e in check_trusted_proxy(None)], ["rastisi.E004"])
