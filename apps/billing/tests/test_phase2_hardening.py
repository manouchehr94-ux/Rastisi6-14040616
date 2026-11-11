"""Phase 2 hardening: F-18 (return redirect allowlist), F-19 (receipt size check before reading), F-07 (no reference-less bulk
«mark paid» in Django admin), F-12 (webhook secret strength check). Synthetic data only."""

from unittest import mock

from django.contrib import admin
from django.contrib.admin.sites import site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from apps.billing.admin import SubscriptionInvoiceAdmin
from apps.billing.checks import MIN_SECRET_LENGTH, check_billing_webhook_secret, weak_secret_reason
from apps.billing.models import SubscriptionInvoice
from apps.billing.services import manual_card_service as mcs
from apps.billing.services import payment_flow_service as pfs
from apps.billing.tests.test_platform_card_to_card import PNG, CardToCardBase
from apps.stores.models import Store

OWN = "shopa"


class _Store:
    def __init__(self, sub):
        self.admin_subdomain = sub


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", RASTISI_ADMIN_DOMAIN_SUFFIX="rastisi.ir",
                   RASTISI_PLATFORM_ADMIN_HOSTS=frozenset({"platformadmin.rastisi.ir"}), ALLOWED_HOSTS=["*"],
                   RASTISI_PRODUCTION_MODE=True)
class ReturnRedirectAllowlistTests(SimpleTestCase):
    """Production-style settings, and the worst ALLOWED_HOSTS (a wildcard)."""

    store = _Store(OWN)

    def ok(self, url, store="default"):
        return pfs.safe_return_to(url, store=self.store if store == "default" else store)

    def test_a_wildcard_allowed_hosts_no_longer_authorises_foreign_hosts(self):
        for url in ("https://evil.example/x", "https://rastisi.ir.evil.example/x", "https://evilrastisi.ir/x"):
            self.assertEqual(self.ok(url), "", url)

    def test_another_tenants_host_is_refused_and_the_own_store_host_is_accepted(self):
        self.assertEqual(self.ok("https://other.rastisi.ir/billing/"), "")
        self.assertEqual(self.ok("https://shopa.rastisi.ir/billing/?a=1"), "https://shopa.rastisi.ir/billing/?a=1")
        self.assertEqual(self.ok("https://rastisi.ir/app/x/"), "https://rastisi.ir/app/x/")
        self.assertEqual(self.ok("https://platformadmin.rastisi.ir/p/"), "https://platformadmin.rastisi.ir/p/")

    def test_without_a_store_only_platform_hosts_are_accepted(self):
        self.assertEqual(self.ok("https://shopa.rastisi.ir/x", store=None), "")
        self.assertEqual(self.ok("https://rastisi.ir/x", store=None), "https://rastisi.ir/x")

    def test_http_and_arbitrary_ports_are_refused_in_production(self):
        self.assertEqual(self.ok("http://shopa.rastisi.ir/x"), "")
        self.assertEqual(self.ok("https://shopa.rastisi.ir:8443/x"), "")

    def test_encoded_protocol_relative_and_credential_forms_stay_refused(self):
        for url in ("//shopa.rastisi.ir/x", "/\\shopa.rastisi.ir", "https://u:p@shopa.rastisi.ir/x", "javascript:alert(1)",
                    "https://shopa.rastisi.ir%2f@evil.example/", "https://shopa.rastisi.ir@evil.example/", "/x\r\nSet-Cookie: a=b", ""):
            self.assertEqual(self.ok(url), "", url)

    def test_relative_paths_still_work(self):
        self.assertEqual(self.ok("/admin-portal/billing/?a=1"), "/admin-portal/billing/?a=1")

    @override_settings(RASTISI_PRODUCTION_MODE=False)
    def test_development_and_qa_may_use_http_and_a_port_on_an_allowed_host_only(self):
        self.assertEqual(self.ok("http://shopa.rastisi.ir:8000/x"), "http://shopa.rastisi.ir:8000/x")
        self.assertEqual(self.ok("http://evil.example:8000/x"), "")                       # ALLOWED_HOSTS=["*"] authorises nothing

    @override_settings(RASTISI_PRODUCTION_MODE=False, ALLOWED_HOSTS=["testserver", ".rastisi.localhost", "*"])
    def test_development_accepts_exact_allowed_hosts_but_never_wildcards_or_suffixes(self):
        self.assertEqual(self.ok("http://testserver/x"), "http://testserver/x")
        self.assertEqual(self.ok("http://other.rastisi.localhost/x"), "")
        self.assertEqual(self.ok("http://evil.example/x"), "")

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_production_ignores_allowed_hosts_entirely(self):
        self.assertEqual(self.ok("https://testserver/x"), "")


class ReceiptSizeTests(CardToCardBase):
    def test_an_oversize_declared_size_is_refused_without_reading_the_body(self):
        big = mock.Mock()
        big.size = mcs.MAX_RECEIPT_BYTES + 1
        big.read.side_effect = AssertionError("the body must not be read")
        with self.assertRaises(mcs.ClaimError):
            self.claim(ref="TRK-BIG-0001", receipt=big)
        big.read.assert_not_called()

    def test_a_lying_size_is_still_bounded_by_the_read_limit(self):
        liar = mock.Mock()
        liar.size = 10
        liar.read.return_value = b"x" * (mcs.MAX_RECEIPT_BYTES + 1)
        with self.assertRaises(mcs.ClaimError):
            self.claim(ref="TRK-LIAR-0002", receipt=liar)
        liar.read.assert_called_once_with(mcs.MAX_RECEIPT_BYTES + 1)

    def test_a_valid_small_receipt_is_still_accepted(self):
        claim = self.claim(ref="TRK-OK-0003", receipt=SimpleUploadedFile("r.png", PNG, content_type="image/png"))
        self.assertEqual(claim.receipt_content_type, "image/png")


class DjangoAdminMarkPaidTests(TestCase):
    def test_the_bulk_mark_paid_action_is_gone(self):
        model_admin = site._registry[SubscriptionInvoice]
        self.assertIsInstance(model_admin, SubscriptionInvoiceAdmin)
        self.assertNotIn("action_mark_paid", getattr(model_admin, "actions", None) or [])
        self.assertFalse(hasattr(SubscriptionInvoiceAdmin, "action_mark_paid"))

    def test_the_audited_platform_admin_path_still_exists(self):
        from apps.portal import platform_admin_urls

        self.assertIn("payment-manual-add", {p.name for p in platform_admin_urls.urlpatterns if p.name})


class WebhookSecretCheckTests(SimpleTestCase):
    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_BILLING_WEBHOOK_SECRET="short")
    def test_a_short_secret_warns_in_production(self):
        found = check_billing_webhook_secret(None)
        self.assertEqual([w.id for w in found], ["rastisi.W020"])
        self.assertNotIn("short", found[0].msg.replace("shorter", ""))                # the secret itself is never echoed

    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_BILLING_WEBHOOK_SECRET="a" * 40)
    def test_a_low_variety_secret_warns(self):
        self.assertEqual(len(check_billing_webhook_secret(None)), 1)

    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_BILLING_WEBHOOK_SECRET="Zx9-QpL2vB7nR4tYw8Ke3Hc6Jm1Ud5Fs0GaXiNoPrTz")
    def test_a_strong_secret_is_silent(self):
        self.assertEqual(check_billing_webhook_secret(None), [])

    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_BILLING_WEBHOOK_SECRET="")
    def test_an_empty_secret_is_not_this_checks_concern_because_the_channel_fails_closed(self):
        self.assertEqual(check_billing_webhook_secret(None), [])
        self.assertEqual(weak_secret_reason(""), "")

    @override_settings(RASTISI_PRODUCTION_MODE=False, RASTISI_BILLING_WEBHOOK_SECRET="short")
    def test_development_is_not_nagged(self):
        self.assertEqual(check_billing_webhook_secret(None), [])
        self.assertGreaterEqual(MIN_SECRET_LENGTH, 32)
