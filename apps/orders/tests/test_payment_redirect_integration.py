"""BLOCKER 1 — end-to-end payment redirect integration.

These tests prove the authoritative payment-page URL that an adapter returns
from ``create_payment`` (``PaymentCreationResult.gateway_url``) survives all the
way to the HTTP ``302 Location`` the customer's browser follows, and is never
confused with the bare provider tracking id (``gateway_track_id``).

Every gateway HTTP call is MOCKED: for each online provider we patch the
adapter's ``create_payment`` to return a KNOWN ``gateway_url`` (the provider's
real host pattern) and then drive the REAL Django view
(``orders:payment-initiate``) via ``self.client.post``. We assert:

- the response is HTTP 302,
- ``response['Location']`` equals the mocked ``gateway_url`` (NOT the track_id),
- the new ``gateway_redirect_url`` field is persisted on the attempt.

For Zibal/Zarinpal (which DERIVE the redirect URL from the track_id and return
no ``gateway_url``), we assert the fallback through ``build_redirect_url`` still
produces the derived URL and that the persisted ``gateway_redirect_url`` stays
blank.

No expected URL is hardcoded anywhere in production code — the known URLs below
live ONLY in this test as the mock return value and the assertion.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import Client
from django.urls import reverse

from apps.orders.gateways.base import PaymentCreationResult
from apps.orders.gateways.zibal import ZIBAL_REDIRECT_URL
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig
from apps.orders.tests.test_lifecycle import LifecycleBase

# Known provider payment-page URLs. These exist ONLY here (mock return +
# assertion); production code never hardcodes a redirect URL.
PASARGAD_URL = "https://pep.shaparak.ir/dorsa1/payment/start?urlId=URL-ID-123"
SNAPPAY_URL = "https://fms.snapppay.ir/pay/token/SP-TOKEN-456"
TOROBPAY_URL = "https://tpay.ir/landing/TP-TOKEN-789"

# Valid credential dicts per adapter (so the config is selectable at checkout).
PASARGAD_CREDS = {
    "username": "merchant-user",
    "password": "s3cr3t-pass",
    "terminalNumber": "123456",
    "serviceCode": "8",
}
SNAPPAY_CREDS = {"client_id": "snapp-client", "client_secret": "s3cr3t"}
TOROBPAY_CREDS = {
    "client_id": "torob-client",
    "client_secret": "t0p-s3cr3t",
    "client_username": "merchant",
    "client_password": "p@ss",
}
ZIBAL_CREDS = {"merchant": "zbl-merchant"}


class RedirectIntegrationBase(LifecycleBase):
    """Drives the real payment-initiate view with mocked create_payment."""

    def _ready_config(self, gateway_code, creds, *, sandbox):
        config = PaymentGatewayConfig.objects.create(
            store=self.store,
            gateway_code=gateway_code,
            is_active=True,
            is_sandbox=sandbox,
        )
        config.set_credentials(creds)
        config.save()
        # Guard: the view only auto-selects a config that is selectable.
        self.assertTrue(
            config.is_selectable_at_checkout,
            f"{gateway_code} config must be selectable for the view to pick it",
        )
        return config

    def _post_initiate(self, order):
        client = Client()
        client.force_login(self.customer.user)
        return client.post(reverse("orders:payment-initiate", args=[order.code]))

    def _single_attempt(self, order):
        attempts = list(PaymentAttempt.objects.filter(order=order))
        self.assertEqual(len(attempts), 1, "exactly one attempt must be created")
        return attempts[0]


class PersistedUrlRedirectTests(RedirectIntegrationBase):
    """Pasargad / SnappPay / TorobPay: redirect to the persisted gateway_url."""

    def _assert_redirects_to_persisted_url(
        self, gateway_code, creds, known_url, *, sandbox, extra=None
    ):
        self._ready_config(gateway_code, creds, sandbox=sandbox)
        order = self.new_order()
        track_id = f"TRK-{gateway_code}-001"
        result = PaymentCreationResult(
            track_id=track_id, gateway_url=known_url, extra=extra
        )
        target = f"apps.orders.gateways.{gateway_code}.{self._adapter_cls(gateway_code)}.create_payment"
        with patch(target, return_value=result):
            response = self._post_initiate(order)

        if gateway_code == "pasargad":
            # Dorsa contract: the browser must arrive with Referer = merchant domain. A bare cross-origin 302 sends none
            # under Django's default Referrer-Policy, so Pasargad goes through an origin-referrer interstitial that
            # navigates to the SAME authoritative URL (never the track_id).
            self.assertEqual(response.status_code, 200, gateway_code)
            body = response.content.decode()
            self.assertIn('<meta name="referrer" content="origin">', body)
            self.assertIn(known_url.replace("&", "&amp;"), body)
            self.assertEqual(response["Referrer-Policy"], "origin")
        else:
            self.assertEqual(response.status_code, 302, gateway_code)
            # Redirects to the authoritative payment-page URL, NOT the track_id.
            self.assertEqual(response["Location"], known_url, gateway_code)
            self.assertNotEqual(response["Location"], track_id, gateway_code)

        attempt = self._single_attempt(order)
        self.assertEqual(attempt.gateway_track_id, track_id, gateway_code)
        self.assertEqual(attempt.gateway_redirect_url, known_url, gateway_code)

    @staticmethod
    def _adapter_cls(gateway_code):
        return {
            "pasargad": "PasargadAdapter",
            "snappay": "SnappPayAdapter",
            "torobpay": "TorobPayAdapter",
        }[gateway_code]

    def test_pasargad_redirects_to_persisted_payment_page_url(self):
        self._assert_redirects_to_persisted_url(
            "pasargad",
            PASARGAD_CREDS,
            PASARGAD_URL,
            sandbox=False,
            extra={"urlId": "URL-ID-123", "invoice": "INV-1", "gateway_url": PASARGAD_URL},
        )

    def test_snappay_redirects_to_persisted_payment_page_url(self):
        self._assert_redirects_to_persisted_url(
            "snappay",
            SNAPPAY_CREDS,
            SNAPPAY_URL,
            sandbox=True,
            extra={"paymentPageUrl": SNAPPAY_URL},
        )

    def test_torobpay_redirects_to_persisted_payment_page_url(self):
        self._assert_redirects_to_persisted_url(
            "torobpay",
            TOROBPAY_CREDS,
            TOROBPAY_URL,
            sandbox=True,
            extra={"paymentPageUrl": TOROBPAY_URL},
        )

    def test_gateway_url_falls_back_to_extra_payment_page_url(self):
        """If gateway_url is empty, the service persists extra['paymentPageUrl']."""
        self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        result = PaymentCreationResult(
            track_id="TRK-FALLBACK",
            gateway_url=None,
            extra={"paymentPageUrl": SNAPPAY_URL},
        )
        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.create_payment",
            return_value=result,
        ):
            response = self._post_initiate(order)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], SNAPPAY_URL)
        attempt = self._single_attempt(order)
        self.assertEqual(attempt.gateway_redirect_url, SNAPPAY_URL)


class DerivedUrlFallbackTests(RedirectIntegrationBase):
    """Zibal / Zarinpal: no gateway_url returned, URL derived from track_id."""

    def test_zibal_uses_build_redirect_url_fallback_from_track_id(self):
        self._ready_config("zibal", ZIBAL_CREDS, sandbox=False)
        order = self.new_order()
        track_id = "ZBL-TRACK-55"
        result = PaymentCreationResult(track_id=track_id, gateway_url=None, extra=None)
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            return_value=result,
        ):
            response = self._post_initiate(order)

        self.assertEqual(response.status_code, 302)
        expected = f"{ZIBAL_REDIRECT_URL}{track_id}"
        self.assertEqual(response["Location"], expected)
        # The derived URL contains the track id (that is by design for zibal).
        self.assertIn(track_id, response["Location"])

        attempt = self._single_attempt(order)
        self.assertEqual(attempt.gateway_track_id, track_id)
        # No authoritative URL was returned, so the persisted field stays blank
        # and the view fell back to build_redirect_url.
        self.assertEqual(attempt.gateway_redirect_url, "")

    def test_zarinpal_uses_build_redirect_url_fallback_from_track_id(self):
        from apps.orders.gateways.zarinpal import ZARINPAL_STARTPAY_URL

        self._ready_config("zarinpal", {"merchant_id": "x" * 36}, sandbox=False)
        order = self.new_order()
        track_id = "ZP-AUTHORITY-77"
        result = PaymentCreationResult(track_id=track_id, gateway_url=None, extra=None)
        with patch(
            "apps.orders.gateways.zarinpal.ZarinpalAdapter.create_payment",
            return_value=result,
        ):
            response = self._post_initiate(order)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{ZARINPAL_STARTPAY_URL}{track_id}")
        attempt = self._single_attempt(order)
        self.assertEqual(attempt.gateway_redirect_url, "")


class ProductionCodeHasNoHardcodedUrlTests(LifecycleBase):
    """Guard: the production redirect path must not fabricate a URL."""

    def test_views_payment_initiate_has_no_hardcoded_provider_url(self):
        import inspect
        import re

        from apps.orders import views

        source = inspect.getsource(views.payment_initiate)
        # Strip comments so provider NAMES mentioned in explanatory comments
        # (e.g. "zibal callback") are not counted; only real code matters.
        code_only = "\n".join(
            line.split("#", 1)[0] for line in source.splitlines()
        )
        # A fabricated redirect URL would appear as an http(s) literal in code.
        self.assertIsNone(
            re.search(r"https?://", code_only),
            "payment_initiate must not contain any hardcoded http(s) URL",
        )

    def test_service_persistence_has_no_hardcoded_provider_url(self):
        import inspect
        import re

        from apps.orders.services import gateway_payment_service

        source = inspect.getsource(gateway_payment_service.initiate_payment)
        code_only = "\n".join(
            line.split("#", 1)[0] for line in source.splitlines()
        )
        self.assertIsNone(
            re.search(r"https?://", code_only),
            "initiate_payment must not contain any hardcoded http(s) URL",
        )
