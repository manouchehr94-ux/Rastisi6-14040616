"""Checkpoint 5B commit 10: Merchant Billing UI — overview, account, invoices,
detail, printable invoice, payment start, payment result, cancellation, and
permission gating (BILLING_VIEW / BILLING_ACCOUNT_MANAGE / BILLING_PAYMENT_MANAGE
/ SUBSCRIPTION_CANCEL)."""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import invoice_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
HOST = f"billui.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BillingViewTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = "billui"
        self.store.save(update_fields=["admin_subdomain"])
        # akhlaghi has a legacy subscription; create an open invoice on it.
        plan = Plan.objects.create(code="billui-plan", name="Plan")
        self.version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("250000"), currency="IRT",
        )
        self.subscription = self.store.subscriptions.filter(is_current=True).first()
        self.invoice = invoice_service.create_invoice(
            self.subscription, kind=SubscriptionInvoice.Kind.RENEWAL, plan_version=self.version,
            lines=[invoice_service.plan_line_spec(self.version)], period_start=timezone.now(),
        )
        self.invoice = invoice_service.open_invoice(self.invoice)
        self.owner = self._member("bill-owner", StoreMembership.Role.OWNER)
        self.client.login(username="bill-owner", password="pass12345")

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        return user

    def _login(self, username, role):
        self._member(username, role)
        self.client.logout()
        self.client.login(username=username, password="pass12345")

    def test_owner_sees_overview(self):
        self.assertEqual(self.client.get(reverse("dashboard:billing-overview")).status_code, 200)

    def test_invoices_and_detail(self):
        self.assertEqual(self.client.get(reverse("dashboard:billing-invoices")).status_code, 200)
        resp = self.client.get(reverse("dashboard:billing-invoice-detail", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.invoice.number)

    def test_printable_invoice(self):
        resp = self.client.get(reverse("dashboard:billing-invoice-print", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.invoice.number)

    def test_account_edit(self):
        resp = self.client.post(reverse("dashboard:billing-account"), {
            "legal_name": "شرکتِ تست", "billing_email": "b@example.com", "city": "تهران",
        })
        self.assertEqual(resp.status_code, 302)
        self.store.billing_account.refresh_from_db()
        self.assertEqual(self.store.billing_account.legal_name, "شرکتِ تست")

    def test_pay_without_any_ready_platform_method_is_refused_and_creates_no_dead_attempt(self):
        resp = self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk]))
        self.assertRedirects(resp, reverse("dashboard:platform-checkout", args=["subscription", self.invoice.pk]), fetch_redirect_response=False)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.OPEN)
        self.assertFalse(self.invoice.payment_attempts.exists())

    def test_payment_result_renders(self):
        self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk]))
        resp = self.client.get(reverse("dashboard:billing-payment-result"))
        self.assertEqual(resp.status_code, 200)

    def test_cancel_at_period_end(self):
        resp = self.client.post(reverse("dashboard:billing-cancel"), {"mode": "period_end"})
        self.assertEqual(resp.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)

    def test_content_editor_forbidden(self):
        self._login("bill-editor", StoreMembership.Role.CONTENT_EDITOR)
        self.assertEqual(self.client.get(reverse("dashboard:billing-overview")).status_code, 403)

    def test_analyst_can_view_but_not_pay_or_cancel(self):
        self._login("bill-analyst", StoreMembership.Role.ANALYST)
        self.assertEqual(self.client.get(reverse("dashboard:billing-invoices")).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk])).status_code, 403,
        )
        self.assertEqual(self.client.get(reverse("dashboard:billing-cancel")).status_code, 403)

    def test_administrator_can_pay_but_not_cancel(self):
        self._login("bill-admin", StoreMembership.Role.ADMINISTRATOR)
        # Payment allowed.
        self.assertEqual(
            self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk])).status_code, 302,
        )
        # Cancellation is Owner-only.
        self.assertEqual(self.client.get(reverse("dashboard:billing-cancel")).status_code, 403)

    def test_cross_store_invoice_404(self):
        other = Store.objects.create(name="B", slug="billui-other", admin_subdomain="billui-other")
        oplan = Plan.objects.create(code="other-pl", name="O")
        over = PlanVersion.objects.create(plan=oplan, version_number=1, status=PlanVersion.Status.PUBLISHED)
        osub = sub_svc.create_subscription(other, over)
        sub_svc.activate_subscription(osub)
        oinv = invoice_service.create_invoice(
            osub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(over)],
        )
        # Owner of `akhlaghi` must not see another store's invoice.
        resp = self.client.get(reverse("dashboard:billing-invoice-detail", args=[oinv.pk]))
        self.assertEqual(resp.status_code, 404)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class ZibalBrowserReturnFlowTests(TestCase):
    """Phase 3: end-to-end merchant-facing flow through the dashboard when
    the platform's active billing provider is Zibal — the browser-return
    endpoint must trigger a real server-side verify (mocked HTTP here) and
    never trust query params as payment proof."""

    def setUp(self):
        from django.core.cache import cache

        from apps.portal.services.platform_config_service import get_platform_configuration

        cache.clear()
        self.addCleanup(cache.clear)
        config = get_platform_configuration()
        config.default_payment_provider = "zibal"
        config.zibal_sandbox_mode = False
        config.set_zibal_credentials(merchant="platform-merchant-1")
        config.save()
        cache.clear()

        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = "billui"
        self.store.save(update_fields=["admin_subdomain"])
        plan = Plan.objects.create(code="billui-zibal-plan", name="Plan")
        self.version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("150000"), currency="IRT",
        )
        self.subscription = self.store.subscriptions.filter(is_current=True).first()
        self.invoice = invoice_service.open_invoice(invoice_service.create_invoice(
            self.subscription, kind=SubscriptionInvoice.Kind.RENEWAL, plan_version=self.version,
            lines=[invoice_service.plan_line_spec(self.version)], period_start=timezone.now(),
        ))
        self.owner = User.objects.create_user(username="bill-zibal-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="bill-zibal-owner", password="pass12345")

    def _pay(self, mock_post):
        mock_post.return_value.json.return_value = {"result": 100, "trackId": 5150}
        resp = self.client.post(reverse("dashboard:billing-pay", args=[self.invoice.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "https://gateway.zibal.ir/start/5150")

    @patch("apps.billing.providers.zibal.requests.post")
    def test_pay_redirects_to_zibal_gateway_url(self, mock_post):
        self._pay(mock_post)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_browser_return_verifies_server_side_and_marks_paid(self, mock_post):
        self._pay(mock_post)
        mock_post.return_value.json.return_value = {"result": 100, "amount": 1_500_000}
        resp = self.client.get(reverse("dashboard:billing-payment-result"))
        self.assertEqual(resp.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_browser_return_query_params_alone_never_confirm_payment(self, mock_post):
        """Even if a malicious/duplicated GET claims success=1 in the query
        string, the view must ignore it and only trust the real verify call."""
        self._pay(mock_post)
        mock_post.return_value.json.return_value = {"result": 202, "message": "not paid yet"}
        resp = self.client.get(
            reverse("dashboard:billing-payment-result") + "?success=1&status=1&trackId=5150",
        )
        self.assertEqual(resp.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertNotEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)

    @patch("apps.billing.providers.zibal.requests.post")
    def test_cross_store_owner_cannot_trigger_verification_on_others_attempt(self, mock_post):
        self._pay(mock_post)
        from apps.core.models import ShopSettings

        other_store = Store.objects.create(
            name="دیگر", slug="billui-zibal-other", admin_subdomain="billui-zibal-other",
            status=Store.Status.ACTIVE,
        )
        ShopSettings.provision_for(other_store)
        other_owner = User.objects.create_user(username="bill-zibal-other", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=other_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        other_host = f"billui-zibal-other.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        other_client = Client(HTTP_HOST=other_host)
        with override_settings(ALLOWED_HOSTS=[HOST, other_host, "testserver"]):
            other_client.login(username="bill-zibal-other", password="pass12345")
            resp = other_client.get(reverse("dashboard:billing-payment-result"))
        self.assertEqual(resp.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertNotEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)
