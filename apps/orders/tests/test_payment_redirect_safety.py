"""A provider-supplied payment-page URL is followed only when it is a plain HTTPS URL without credentials and (live mode, documented hosts) inside the provider's own domains."""

from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import PaymentCreationResult
from apps.orders.models import PaymentAttempt
from apps.orders.services.gateway_payment_service import PaymentInitiationError, initiate_payment, is_safe_gateway_redirect
from apps.orders.tests.test_payment_redirect_integration import PASARGAD_CREDS, SNAPPAY_CREDS, RedirectIntegrationBase


class UrlPolicyTests(SimpleTestCase):
    def setUp(self):
        self.pasargad = get_adapter("pasargad")

    def test_documented_provider_hosts_and_subdomains_are_accepted_in_live_mode(self):
        for url in ("https://pep.shaparak.ir/dorsa1/pay?urlId=1", "https://shaparak.ir/x", "https://a.b.shaparak.ir/x"):
            self.assertTrue(is_safe_gateway_redirect(url, self.pasargad), url)

    def test_lookalikes_userinfo_and_other_schemes_are_refused(self):
        bad = (
            "http://pep.shaparak.ir/x",                        # no TLS
            "https://evil.example/x", "https://evilshaparak.ir/x", "https://shaparak.ir.evil.example/x",
            "https://pep.shaparak.ir@evil.example/x", "https://user:pw@pep.shaparak.ir/x",
            "https://evil.example\\@pep.shaparak.ir/x", "javascript:alert(1)", "data:text/html,x", "//pep.shaparak.ir/x",
            "https://pep.shaparak.ir/x y", "https://pep.shaparak.ir/\nx", "", "   ", None,
        )
        for url in bad:
            self.assertFalse(is_safe_gateway_redirect(url, self.pasargad), repr(url))

    def test_sandbox_still_requires_https_without_credentials_but_not_the_live_host_list(self):
        self.assertTrue(is_safe_gateway_redirect("https://sandbox.example/pay", self.pasargad, sandbox=True))
        self.assertFalse(is_safe_gateway_redirect("http://sandbox.example/pay", self.pasargad, sandbox=True))
        self.assertFalse(is_safe_gateway_redirect("https://u:p@sandbox.example/pay", self.pasargad, sandbox=True))

    def test_providers_without_a_documented_page_domain_are_https_only_and_ops_can_widen_others(self):
        snappay = get_adapter("snappay")
        self.assertEqual(snappay.redirect_host_suffixes, ())
        self.assertTrue(is_safe_gateway_redirect("https://anything.example/pay", snappay))
        self.assertFalse(is_safe_gateway_redirect("http://anything.example/pay", snappay))
        with override_settings(PAYMENT_REDIRECT_EXTRA_HOST_SUFFIXES={"pasargad": ("psp-new.ir",)}):
            self.assertTrue(is_safe_gateway_redirect("https://pay.psp-new.ir/x", self.pasargad))
            self.assertFalse(is_safe_gateway_redirect("https://pay.other.ir/x", self.pasargad))


class ServiceAndViewTests(RedirectIntegrationBase):
    def test_an_unsafe_url_from_the_provider_fails_the_attempt_and_is_never_stored_or_followed(self):
        config = self._ready_config("pasargad", PASARGAD_CREDS, sandbox=False)
        order = self.new_order()
        bad = PaymentCreationResult(track_id="T1", gateway_url="https://evil.example/steal", extra=None)
        with patch("apps.orders.gateways.pasargad.PasargadAdapter.create_payment", return_value=bad):
            with self.assertRaises(PaymentInitiationError):
                initiate_payment(order=order, gateway_config=config, callback_url="https://x/cb", store=self.store)
        attempt = PaymentAttempt.objects.get(order=order)
        self.assertEqual((attempt.status, attempt.failure_code, attempt.gateway_redirect_url), (PaymentAttempt.Status.FAILED, "unsafe_redirect", ""))

    def test_the_view_refuses_to_redirect_to_an_unsafe_stored_url(self):
        config = self._ready_config("pasargad", PASARGAD_CREDS, sandbox=False)
        order = self.new_order()
        PaymentAttempt.objects.create(store=self.store, order=order, gateway_config=config, amount=order.grand_total, currency="TOMAN",
                                      status=PaymentAttempt.Status.REDIRECT_READY, gateway_track_id="T2", gateway_redirect_url="http://evil.example/x")
        response = self._post_initiate(order)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("Location", response)

    def test_the_view_redirects_to_a_safe_url(self):
        config = self._ready_config("pasargad", PASARGAD_CREDS, sandbox=False)
        order = self.new_order()
        PaymentAttempt.objects.create(store=self.store, order=order, gateway_config=config, amount=order.grand_total, currency="TOMAN",
                                      status=PaymentAttempt.Status.REDIRECT_READY, gateway_track_id="T3",
                                      gateway_redirect_url="https://pep.shaparak.ir/dorsa1/pay?urlId=9")
        response = self._post_initiate(order)
        # Pasargad requires Referer = merchant domain on the browser navigation ⇒ origin-referrer interstitial (same safe URL).
        self.assertEqual(response.status_code, 200)
        self.assertIn('content="origin"', response.content.decode())
        self.assertIn("https://pep.shaparak.ir/dorsa1/pay?urlId=9", response.content.decode())
