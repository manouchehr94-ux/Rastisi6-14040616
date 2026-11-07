"""Checkout shows the AUTHORITATIVE invoice billing interval and the selected period survives the whole flow.

The server stays authoritative: the interval of an invoice comes from its plan-line snapshot
(``invoice_service.invoice_billing_interval``), never from the plan version's default and never from the browser."""

from django.test import Client
from django.urls import reverse

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.billing.tests.test_platform_checkout import PlanChangeThroughCheckoutTests, UP_HOST
from apps.billing.tests.platform_payment_support import ready_platform_zibal
from apps.billing.tests.test_platform_card_to_card import enable_platform_card

PLANS = "/admin-portal/subscription/plans/"


class CheckoutIntervalTests(PlanChangeThroughCheckoutTests):
    def _yearly_invoice(self):
        ready_platform_zibal(self)
        enable_platform_card(self)
        self.execute("yearly")
        return SubscriptionInvoice.objects.get(store=self.store2, kind="plan_change")

    def test_yearly_invoice_checkout_shows_yearly_label_not_monthly(self):
        invoice = self._yearly_invoice()
        self.assertEqual(self.v2.billing_interval, "monthly")                       # plan default is monthly
        self.assertEqual(invoice_service.invoice_billing_interval(invoice), "yearly")
        target = __import__("apps.billing.services.platform_checkout_service", fromlist=["x"]).invoice_target(invoice)
        self.assertIn("سالانه", target.subtitle)
        self.assertNotIn("ماهانه", target.subtitle)
        page = self.client2.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])).content.decode()
        self.assertIn("سالانه", page)
        self.assertIn("سالانه", page)

    def test_checkout_back_link_restores_the_invoice_interval(self):
        invoice = self._yearly_invoice()
        response = self.client2.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk]))
        self.assertEqual(response.context["back_url"], PLANS + "?interval=yearly")

    def test_plans_page_preselects_valid_interval_and_ignores_tampered_one(self):
        ok = self.client2.get(PLANS, {"interval": "yearly"}).content.decode()
        self.assertRegex(ok, r'<option value="yearly" selected>')
        for bad in ("bogus", "none", "<script>"):
            html = self.client2.get(PLANS, {"interval": bad}).content.decode()
            self.assertRegex(html, r'<option value="monthly" selected>')

    def test_preview_cancel_link_keeps_interval_and_validation_error_redirect_keeps_it(self):
        response = self.client2.post(PLANS + "preview/", {"version_id": self.v2.pk, "billing_interval": "yearly"})
        self.assertEqual(response.context["plans_url"], PLANS + "?interval=yearly")
        self.assertIn(f'href="{PLANS}?interval=yearly"', response.content.decode())
        bad = self.client2.post(PLANS + "preview/", {"version_id": self.v2.pk, "billing_interval": "weekly"})
        self.assertEqual(bad.status_code, 302)
        self.assertEqual(bad["Location"], PLANS)                                    # unknown interval is dropped, not echoed

    def test_failed_payment_return_and_retry_keep_the_invoice_interval_and_amount(self):
        invoice = self._yearly_invoice()
        url = reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])
        self.client2.post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"})
        before = SubscriptionInvoice.objects.get(pk=invoice.pk)
        page = self.client2.get(url).content.decode()                               # returning after the gateway
        self.assertIn("سالانه", page)
        # retry never creates a second invoice nor changes interval/amount
        self.execute("yearly")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2, kind="plan_change").count(), 1)
        after = SubscriptionInvoice.objects.get(pk=invoice.pk)
        self.assertEqual(invoice_service.invoice_billing_interval(after), "yearly")
        self.assertEqual(after.grand_total, before.grand_total)

    def test_a_paid_invoice_is_not_altered_by_viewing_checkout_or_plans(self):
        invoice = self._yearly_invoice()
        SubscriptionInvoice.objects.filter(pk=invoice.pk).update(status=SubscriptionInvoice.Status.PAID)
        snap = list(invoice.lines.values_list("plan_version_snapshot", flat=True))
        self.client2.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk]))
        self.client2.get(PLANS, {"interval": "monthly"})
        self.assertEqual(list(invoice.lines.values_list("plan_version_snapshot", flat=True)), snap)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice.pk).status, SubscriptionInvoice.Status.PAID)
