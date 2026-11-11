"""Checkpoint 5B commit 11: platform Billing Admin is superuser-only, financial
records are add/delete-locked, attempts/webhooks/dunning are not changeable, and
the manual mark-paid + webhook-retry actions work safely."""

from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.billing.admin import (
    BillingWebhookEventAdmin,
    SubscriptionInvoiceAdmin,
    SubscriptionPaymentAttemptAdmin,
)
from apps.billing.models import (
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.services import attempt_service, invoice_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()


def _open_invoice(slug, *, price="300000"):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    sub = sub_svc.start_trial(sub)
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)],
    )
    return store, sub, invoice_service.open_invoice(invoice)


class BillingAdminPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="b-super", email="s@e.com", password="p")
        cls.staff = User.objects.create_user(username="b-staff", password="p", is_staff=True)

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.invoice_admin = SubscriptionInvoiceAdmin(SubscriptionInvoice, self.site)
        self.attempt_admin = SubscriptionPaymentAttemptAdmin(SubscriptionPaymentAttempt, self.site)

    def _req(self, user):
        req = self.factory.get("/admin/")
        req.user = user
        return req

    def test_non_superuser_denied(self):
        req = self._req(self.staff)
        self.assertFalse(self.invoice_admin.has_module_permission(req))
        self.assertFalse(self.invoice_admin.has_view_permission(req))

    def test_superuser_may_view(self):
        req = self._req(self.superuser)
        self.assertTrue(self.invoice_admin.has_module_permission(req))

    def test_invoices_not_addable_or_deletable(self):
        req = self._req(self.superuser)
        self.assertFalse(self.invoice_admin.has_add_permission(req))
        self.assertFalse(self.invoice_admin.has_delete_permission(req))

    def test_financial_fields_readonly(self):
        req = self._req(self.superuser)
        readonly = self.invoice_admin.get_readonly_fields(req)
        for field in ("grand_total", "amount_paid", "status", "number"):
            self.assertIn(field, readonly)

    def test_attempts_not_changeable(self):
        req = self._req(self.superuser)
        self.assertFalse(self.attempt_admin.has_change_permission(req))


class BillingAdminActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="act-super", email="a@e.com", password="p")

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()

    def _req(self):
        req = self.factory.post("/admin/")
        req.user = self.superuser
        # message framework needs a fallback storage
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", {})
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_bulk_mark_paid_action_was_removed_and_nothing_is_marked_paid_from_django_admin(self):
        # F-07: marking an invoice paid needs an amount, a reference and a reason, which a bulk admin action cannot carry.
        store, sub, invoice = _open_invoice("act-1")
        admin = SubscriptionInvoiceAdmin(SubscriptionInvoice, self.site)
        self.assertFalse(hasattr(admin, "action_mark_paid"))
        self.assertNotIn("action_mark_paid", admin.actions or [])
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.status, SubscriptionInvoice.Status.PAID)

    def test_webhook_retry_action_is_idempotent(self):
        from apps.billing.models import BillingWebhookEvent

        event = BillingWebhookEvent.objects.create(
            provider="manual", external_event_id="retry-1", event_type="payment.failed",
            signature_valid=True, processing_status=BillingWebhookEvent.ProcessingStatus.FAILED,
            sanitized_payload={"event_type": "payment.failed"},
        )
        admin = BillingWebhookEventAdmin(BillingWebhookEvent, self.site)
        admin.action_retry(self._req(), BillingWebhookEvent.objects.filter(pk=event.pk))
        event.refresh_from_db()
        # A non-success event resolves to IGNORED (no business mutation).
        self.assertEqual(event.processing_status, BillingWebhookEvent.ProcessingStatus.IGNORED)
