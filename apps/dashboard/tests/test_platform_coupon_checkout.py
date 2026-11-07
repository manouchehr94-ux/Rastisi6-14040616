"""Merchant checkout with platform coupons: validate/apply/remove/replace, server-authoritative amounts, private-coupon
non-disclosure, tenant isolation, zero-value settlement through the internal path, and the no-coupon regression."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PlatformCoupon, PlatformCouponRedemption, SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import platform_coupon_service as svc
from apps.billing.tests.platform_payment_support import ready_platform_zibal
from apps.billing.tests.test_platform_card_to_card import enable_platform_card
from apps.billing.tests.test_platform_checkout import UP_HOST, CheckoutBase, SUB_PRICE
from apps.stores.models import Store
from apps.subscriptions.models import PlanVersion
from apps.subscriptions.services import subscription_service as ss
from apps.subscriptions.tests.test_pricing_dynamic import make_plan


def coupon(admin, code="OFF20", **kw):
    kw.setdefault("name", code or "auto")
    kw.setdefault("kind", "percent")
    if kw["kind"] == "percent":
        kw.setdefault("percent", 20)
    else:
        kw.setdefault("fixed_amount", Decimal("50000"))
    plans, stores = kw.pop("plans", ()), kw.pop("stores", ())
    return svc.create_coupon(actor=admin, code=code, plans=plans, stores=stores, **kw)


class CouponCheckoutTests(CheckoutBase):
    def url(self, kind="subscription", action="", invoice=None):
        pk = (invoice or self.invoice).pk
        name = {"": "platform-checkout", "apply": "platform-checkout-coupon-apply", "remove": "platform-checkout-coupon-remove",
                "pay": "platform-checkout-pay"}[action]
        return reverse(f"dashboard:{name}", args=[kind, pk])

    def apply(self, code, client=None, **extra):
        return (client or self.owner_client).post(self.url(action="apply"), {"coupon_code": code, **extra}, follow=True)

    def fresh(self):
        return SubscriptionInvoice.objects.get(pk=self.invoice.pk)

    def msgs(self, response):
        return [str(m) for m in response.context["messages"]]

    # ---- apply / remove / replace
    def test_page_renders_rtl_with_coupon_form_and_no_discount_by_default(self):
        html = self.owner_client.get(self.url()).content.decode()
        self.assertIn('name="coupon_code"', html)
        self.assertNotIn("price-breakdown", html)
        self.assertIn("پرداخت", html)

    def test_apply_shows_breakdown_and_server_recalculates(self):
        coupon(self.finance, "OFF20")
        r = self.apply("off20")                                              # case-insensitive
        inv = self.fresh()
        self.assertEqual(inv.discount_total, Decimal("60000"))
        self.assertEqual(inv.amount_due, Decimal(SUB_PRICE) - 60000)
        html = r.content.decode()
        self.assertIn('data-testid="price-breakdown"', html)
        self.assertIn("۳۰۰٬۰۰۰", html)                                          # original
        self.assertIn("۲۴۰٬۰۰۰", html)                                          # payable
        self.assertIn("فقط برایِ همین فاکتور", html)                            # no recurring promise
        self.assertNotIn("همیشه", html)
        self.assertEqual(PlatformCouponRedemption.objects.get(invoice=inv).status, "reserved")

    def test_remove_restores_full_price_and_releases_reservation(self):
        coupon(self.finance, "OFF20")
        self.apply("OFF20")
        r = self.owner_client.post(self.url(action="remove"), follow=True)
        inv = self.fresh()
        self.assertEqual((inv.discount_total, inv.amount_due), (Decimal(0), Decimal(SUB_PRICE)))
        self.assertEqual(PlatformCouponRedemption.objects.get(invoice=inv).status, "released")
        self.assertNotIn('data-testid="price-breakdown"', r.content.decode())

    def test_replace_coupon_and_failed_replacement_keeps_the_old_one(self):
        coupon(self.finance, "OFF20")
        coupon(self.finance, "FIX50", kind="fixed")
        self.apply("OFF20")
        r = self.apply("FIX50")
        self.assertEqual(self.fresh().discount_total, Decimal("50000"))
        self.assertEqual(self.fresh().coupon_snapshot["code"], "FIX50")
        r = self.apply("NOPE")
        self.assertIn(svc.MESSAGES["invalid_code"], self.msgs(r))
        self.assertEqual(self.fresh().coupon_snapshot["code"], "FIX50")        # untouched on failed replacement
        self.assertEqual(self.fresh().discount_total, Decimal("50000"))

    def test_reapplying_the_same_code_does_not_double_discount(self):
        coupon(self.finance, "OFF20")
        self.apply("OFF20")
        self.apply("OFF20")
        self.assertEqual(self.fresh().discount_total, Decimal("60000"))
        self.assertEqual(PlatformCouponRedemption.objects.filter(invoice=self.invoice).count(), 1)

    def test_blank_code_message(self):
        self.assertIn("کد تخفیف را وارد کنید.", self.msgs(self.apply("   ")))

    # ---- messages
    def test_persian_messages_for_each_failure(self):
        now = timezone.now()
        coupon(self.finance, "OLD", starts_at=now - timedelta(days=9), ends_at=now - timedelta(days=1))
        coupon(self.finance, "LATER", starts_at=now + timedelta(days=3))
        off = coupon(self.finance, "OFFD")
        svc.set_coupon_status(off, "disabled", actor=self.finance)
        full = coupon(self.finance, "FULL", max_redemptions=1)
        other_sub, other_inv = __import__("apps.billing.tests.platform_payment_support", fromlist=["x"]).open_invoice_for(
            self.other, code="pcother2", price=str(SUB_PRICE))
        svc.apply_coupon_to_invoice(other_inv, code="FULL", actor=self.finance)
        coupon(self.finance, "BIG", min_amount=Decimal("99999999"))
        coupon(self.finance, "RENEW", allow_initial=False, allow_renewal=True)
        cases = {"OLD": "expired", "LATER": "not_started", "OFFD": "inactive", "FULL": "limit_reached", "BIG": "min_amount",
                 "RENEW": "ineligible_purpose", "GHOST": "invalid_code"}
        for code, key in cases.items():
            with self.subTest(code=code):
                self.assertIn(svc.MESSAGES[key], self.msgs(self.apply(code)))
                self.assertEqual(self.fresh().discount_total, Decimal(0))

    def test_second_manual_coupon_while_paying_is_blocked_when_payment_in_progress(self):
        ready_platform_zibal(self)
        coupon(self.finance, "OFF20")
        self.apply("OFF20")
        self.owner_client.post(self.url(action="pay"), {"method": "zibal"})
        self.assertTrue(SubscriptionPaymentAttempt.objects.filter(invoice=self.invoice).exists())
        r = self.owner_client.post(self.url(action="remove"), follow=True)
        self.assertTrue({svc.MESSAGES["payment_in_progress"], svc.MESSAGES["invoice_locked"]} & set(self.msgs(r)))
        self.assertEqual(self.fresh().discount_total, Decimal("60000"))
        html = self.owner_client.get(self.url()).content.decode()
        self.assertNotIn('data-testid="coupon-remove"', html)               # controls hidden while a payment is in flight

    # ---- privacy / tenant isolation / tampering
    def test_private_coupon_of_another_merchant_is_not_disclosed(self):
        coupon(self.finance, "PRIVATE", stores=[self.other])
        r = self.apply("PRIVATE")
        messages = self.msgs(r)
        self.assertIn(svc.MESSAGES["invalid_code"], messages)
        self.assertEqual(self.msgs(self.apply("GHOSTCODE")), messages)       # indistinguishable from a non-existent code
        self.assertNotIn("PRIVATE", r.content.decode().replace('name="coupon_code"', ""))
        self.assertEqual(self.fresh().discount_total, Decimal(0))
        # the assigned merchant can use it
        sub, inv = __import__("apps.billing.tests.platform_payment_support", fromlist=["x"]).open_invoice_for(
            self.other, code="pcother3", price=str(SUB_PRICE))
        ok = self.other_client.post(reverse("dashboard:platform-checkout-coupon-apply", args=["subscription", inv.pk]),
                                    {"coupon_code": "PRIVATE"})
        self.assertEqual(ok.status_code, 302)
        inv.refresh_from_db()
        self.assertGreater(inv.discount_total, 0)

    def test_tampered_post_fields_are_ignored(self):
        coupon(self.finance, "OFF20")
        self.apply("OFF20", discount_amount="299999", discount="299999", amount="1", price="1", grand_total="0", amount_due="0",
                   final_amount="0", store="2", store_id=str(self.other.pk), invoice_id="999", percent="100")
        inv = self.fresh()
        self.assertEqual((inv.discount_total, inv.amount_due), (Decimal("60000"), Decimal("240000")))
        self.assertEqual(inv.store_id, self.store.pk)
        self.assertEqual(PlatformCouponRedemption.objects.get(invoice=inv).store_id, self.store.pk)

    def test_cross_tenant_invoice_access_is_denied(self):
        coupon(self.finance, "OFF20")
        r = self.other_client.post(self.url(action="apply"), {"coupon_code": "OFF20"})
        self.assertEqual(r.status_code, 404)
        r = self.other_client.post(self.url(action="remove"))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.fresh().discount_total, Decimal(0))
        self.assertEqual(self.other_client.get(self.url()).status_code, 404)

    def test_anonymous_and_get_are_not_allowed_and_csrf_is_enforced(self):
        coupon(self.finance, "OFF20")
        anon = Client(HTTP_HOST=self.owner_client.defaults["HTTP_HOST"])
        self.assertIn(anon.post(self.url(action="apply"), {"coupon_code": "OFF20"}).status_code, (302, 403, 404))
        self.assertEqual(self.owner_client.get(self.url(action="apply")).status_code, 405)
        strict = Client(HTTP_HOST=self.owner_client.defaults["HTTP_HOST"], enforce_csrf_checks=True)
        strict.login(username="pcout-owner", password="pass12345")
        self.assertEqual(strict.post(self.url(action="apply"), {"coupon_code": "OFF20"}).status_code, 403)
        self.assertEqual(strict.post(self.url(action="remove")).status_code, 403)
        self.assertEqual(self.fresh().discount_total, Decimal(0))

    def test_sms_checkout_does_not_accept_platform_coupons(self):
        coupon(self.finance, "OFF20")
        r = self.owner_client.post(reverse("dashboard:platform-checkout-coupon-apply", args=["sms", self.purchase.pk]),
                                   {"coupon_code": "OFF20"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(svc.MESSAGES["unsupported_invoice"], self.msgs(r))

    # ---- automatic campaign
    def test_automatic_campaign_is_shown_clearly(self):
        auto = svc.create_coupon(actor=self.finance, name="کمپین", code=None, is_automatic=True, kind="percent", percent=10)
        svc.apply_automatic_to_invoice(self.invoice)
        html = self.owner_client.get(self.url()).content.decode()
        self.assertIn('data-testid="auto-promo"', html)
        self.assertIn("تخفیفِ خودکار", html)
        # an explicit code replaces the automatic discount
        coupon(self.finance, "FIX50", kind="fixed")
        self.apply("FIX50")
        self.assertEqual(self.fresh().coupon_snapshot["code"], "FIX50")
        self.assertTrue(auto.pk)

    # ---- zero-value
    def test_full_discount_uses_internal_zero_value_settlement_without_gateway(self):
        ready_platform_zibal(self)
        coupon(self.finance, "FREE100", percent=100)
        self.apply("FREE100")
        inv = self.fresh()
        self.assertEqual(inv.amount_due, Decimal(0))
        html = self.owner_client.get(self.url()).content.decode()
        self.assertIn('data-testid="settle-free"', html)
        self.assertNotIn('name="method"', html)                                # no gateway choice at all
        with mock.patch("apps.billing.services.payment_flow_service.start_payment") as start:
            self.owner_client.post(self.url(action="pay"), {"method": "zibal", "amount": "300000"})
            start.assert_not_called()
        inv = self.fresh()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(PlatformCouponRedemption.objects.get(invoice=inv).status, "redeemed")
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=inv, provider="zibal").exists())
        self.owner_client.post(self.url(action="pay"), {"method": "zibal"})     # repeat is harmless
        self.assertEqual(PlatformCouponRedemption.objects.filter(invoice=inv, status="redeemed").count(), 1)

    def test_partial_discount_is_never_settled_for_free(self):
        coupon(self.finance, "OFF20")
        self.apply("OFF20")
        self.owner_client.post(self.url(action="pay"), {"method": "zibal", "amount": "0"})
        self.assertNotEqual(self.fresh().status, SubscriptionInvoice.Status.PAID)

    # ---- invoice detail
    def test_invoice_detail_shows_discount_breakdown(self):
        coupon(self.finance, "OFF20")
        self.apply("OFF20")
        html = self.owner_client.get(reverse("dashboard:billing-invoice-detail", args=[self.invoice.pk])).content.decode()
        self.assertIn('data-testid="invoice-discount"', html)
        self.assertIn("OFF20", html)

    # ---- no-coupon regression
    def test_no_coupon_checkout_pays_full_price(self):
        ready_platform_zibal(self)
        r = self.owner_client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertIn("۳۰۰٬۰۰۰", r.content.decode())
        self.owner_client.post(self.url(action="pay"), {"method": "zibal"})
        attempt = SubscriptionPaymentAttempt.objects.get(invoice=self.invoice)
        self.assertEqual(int(attempt.amount), SUB_PRICE)
        self.assertFalse(PlatformCouponRedemption.objects.filter(invoice=self.invoice).exists())


    def test_apply_endpoint_is_throttled_and_does_not_evaluate_when_limited(self):
        from django.core.cache import caches
        from django.test import override_settings

        caches["ratelimit"].clear()
        self.addCleanup(caches["ratelimit"].clear)
        coupon(self.finance, "OFF20")
        with override_settings(PLATFORM_COUPON_ATTEMPTS_PER_MINUTE=3):
            for _ in range(3):
                self.apply("NOPE")
            r = self.apply("OFF20")
        self.assertIn(svc.MESSAGES["rate_limited"], self.msgs(r))
        self.assertEqual(self.fresh().discount_total, Decimal(0))
        self.assertFalse(PlatformCouponRedemption.objects.exists())


class CouponPlanChangeTests(CheckoutBase):
    """Plan upgrade flow: the preview validates the code, the execute step creates the invoice and applies it server-side."""

    def setUp(self):
        super().setUp()
        _p1, self.v1 = make_plan("cpup-low", base=100000, order=1, limits={"catalog.products": 5})
        _p2, self.v2 = make_plan("cpup-high", base=300000, order=2, extra={"yearly": 3000000}, limits={"catalog.products": 50})
        self.store2 = Store.objects.create(name="ارتقا", slug="pcup", admin_subdomain="pcup", status=Store.Status.ACTIVE)
        self.owner2 = self._member(self.store2, "pcup-owner")
        self.sub2 = ss.activate_subscription(ss.create_subscription(self.store2, self.v1), period_end=timezone.now() + timedelta(days=20))
        self.client2 = Client(HTTP_HOST=UP_HOST)
        self.client2.login(username="pcup-owner", password="pass12345")
        ready_platform_zibal(self)
        enable_platform_card(self)
        coupon(self.finance, "UP20", allow_plan_change=True, allow_initial=False)

    def preview(self, code="", interval="yearly"):
        return self.client2.post("/admin-portal/subscription/plans/preview/",
                                 {"version_id": self.v2.pk, "billing_interval": interval, "coupon_code": code})

    def execute(self, code="", interval="yearly", **extra):
        token = self.preview(code, interval).context["preview"]["token"]
        return self.client2.post("/admin-portal/subscription/plans/change/", {
            "version_id": self.v2.pk, "preview_token": token, "billing_interval": interval, "coupon_code": code, **extra})

    def test_preview_shows_discount_and_final_without_writing(self):
        r = self.preview("up20")
        html = r.content.decode()
        self.assertEqual(r.context["coupon_eval"].discount_amount, Decimal("600000"))
        self.assertIn('data-testid="preview-final"', html)
        self.assertIn("۲٬۴۰۰٬۰۰۰", html)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2).count(), 0)
        self.assertEqual(PlatformCouponRedemption.objects.count(), 0)

    def test_preview_invalid_code_shows_persian_message(self):
        r = self.preview("NOPE")
        self.assertContains(r, svc.MESSAGES["invalid_code"])
        self.assertIsNone(r.context["coupon_eval"])

    def test_execute_applies_coupon_server_side_keeps_interval_and_ignores_tampering(self):
        r = self.execute("UP20", discount_amount="2999999", amount="1", store_id=str(self.store.pk))
        inv = SubscriptionInvoice.objects.get(store=self.store2, kind="plan_change")
        self.assertRedirects(r, reverse("dashboard:platform-checkout", args=["subscription", inv.pk]), fetch_redirect_response=False)
        self.assertEqual((inv.subtotal, inv.discount_total, inv.amount_due), (Decimal("3000000"), Decimal("600000"), Decimal("2400000")))
        self.assertEqual(self.client2.get(r["Location"]).context["back_url"], "/admin-portal/subscription/plans/?interval=yearly")
        self.client2.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        self.assertEqual(int(SubscriptionPaymentAttempt.objects.get(invoice=inv).amount), 2_400_000)

    def test_execute_with_invalid_code_creates_no_invoice(self):
        r = self.execute("NOPE")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2).count(), 0)

    def test_execute_without_code_is_unchanged(self):
        r = self.execute("")
        inv = SubscriptionInvoice.objects.get(store=self.store2, kind="plan_change")
        self.assertEqual((inv.discount_total, inv.amount_due), (Decimal(0), Decimal("3000000")))
        self.assertFalse(PlatformCouponRedemption.objects.exists())

    def test_private_coupon_for_another_store_is_not_disclosed_in_preview(self):
        coupon(self.finance, "SECRET", stores=[self.store], allow_plan_change=True, allow_initial=False)
        r = self.preview("SECRET")
        self.assertContains(r, svc.MESSAGES["invalid_code"])
        self.assertNotContains(r, "SECRET</")
        self.execute("SECRET")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2).count(), 0)

    def test_preview_is_throttled(self):
        from django.core.cache import caches
        from django.test import override_settings

        caches["ratelimit"].clear()
        self.addCleanup(caches["ratelimit"].clear)
        with override_settings(PLATFORM_COUPON_ATTEMPTS_PER_MINUTE=2):
            self.preview("NOPE1")
            self.preview("NOPE2")
            r = self.preview("UP20")
        self.assertContains(r, svc.MESSAGES["rate_limited"])
        self.assertIsNone(r.context["coupon_eval"])

    def test_execute_is_throttled_and_creates_no_invoice(self):
        from django.core.cache import caches
        from django.test import override_settings

        caches["ratelimit"].clear()
        self.addCleanup(caches["ratelimit"].clear)
        token = self.preview("UP20").context["preview"]["token"]
        with override_settings(PLATFORM_COUPON_ATTEMPTS_PER_MINUTE=1):
            self.preview("UP20")                                                 # consumes the single allowed attempt
            self.client2.post("/admin-portal/subscription/plans/change/", {
                "version_id": self.v2.pk, "preview_token": token, "billing_interval": "yearly", "coupon_code": "UP20"})
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2).count(), 0)

    def test_plan_change_coupon_failure_is_atomic_and_leaves_no_invoice(self):
        """Race: the code passed pre-validation but applying fails. The new invoice must be rolled back (no undiscounted
        invoice the user never saw), no redemption remains, and the user is told why."""
        from unittest import mock

        with mock.patch.object(svc, "apply_coupon_to_invoice", side_effect=svc.CouponError("limit_reached")):
            r = self.execute("UP20")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2, kind="plan_change").count(), 0)
        self.assertFalse(PlatformCouponRedemption.objects.exists())
        texts = [str(m) for m in self.client2.get(r["Location"]).context["messages"]]
        self.assertTrue(any(svc.MESSAGES["limit_reached"] in t and "فاکتور ایجاد نشد" in t for t in texts))
        self.execute("")                                                         # retry without a code still works
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2, kind="plan_change").count(), 1)

    def test_reused_plan_change_invoice_with_another_manual_coupon_reports_incompatible(self):
        coupon(self.finance, "OTHER10", percent=10, allow_plan_change=True, allow_initial=False)
        self.execute("UP20")
        r = self.execute("OTHER10")                                              # idempotent invoice reuse
        inv = SubscriptionInvoice.objects.get(store=self.store2, kind="plan_change")
        self.assertEqual(inv.discount_total, Decimal("600000"))                  # first coupon stays
        texts = [str(m) for m in self.client2.get(r["Location"]).context["messages"]]
        self.assertTrue(any(svc.MESSAGES["incompatible"] in t for t in texts))


TRIAL_HOST = f"pctrial.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[TRIAL_HOST, UP_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class CouponFirstPaidPurchaseAfterTrialTests(CheckoutBase):
    """The first paid purchase after Trial is a PLAN_CHANGE invoice (free trial plan -> paid plan). A default coupon
    (allow_initial only) must apply to it; once the store has paid, an ordinary upgrade is a plan change again."""

    def setUp(self):
        super().setUp()
        _t, self.trial_v = make_plan("cptrial-free", base=0, order=0, trial=14, limits={"catalog.products": 5})
        _p, self.paid_v = make_plan("cptrial-paid", base=300000, order=1, extra={"yearly": 3000000}, limits={"catalog.products": 50})
        _p3, self.top_v = make_plan("cptrial-top", base=900000, order=2, extra={"yearly": 9000000}, limits={"catalog.products": 500})
        self.store3 = Store.objects.create(name="تریال", slug="pctrial", admin_subdomain="pctrial", status=Store.Status.ACTIVE)
        self.owner3 = self._member(self.store3, "pctrial-owner")
        self.sub3 = ss.start_trial(ss.create_subscription(self.store3, self.trial_v))
        self.client3 = Client(HTTP_HOST=TRIAL_HOST)
        self.client3.login(username="pctrial-owner", password="pass12345")
        ready_platform_zibal(self)
        enable_platform_card(self)
        caches_clear()

    def buy(self, version, code="", interval="monthly"):
        r = self.client3.post("/admin-portal/subscription/plans/preview/",
                              {"version_id": version.pk, "billing_interval": interval, "coupon_code": code})
        token = r.context["preview"]["token"]
        return r, self.client3.post("/admin-portal/subscription/plans/change/", {
            "version_id": version.pk, "preview_token": token, "billing_interval": interval, "coupon_code": code})

    def test_default_coupon_applies_to_the_first_paid_purchase_after_trial_then_redeems_on_payment(self):
        from apps.billing.services import attempt_service, confirmation_service
        from apps.subscriptions.models import StoreSubscription

        c = coupon(self.finance, "TRIAL20")                                      # defaults: allow_initial=True, allow_plan_change=False
        preview, _ = self.buy(self.paid_v, "TRIAL20")
        self.assertEqual(preview.context["coupon_eval"].discount_amount, Decimal("60000"))
        inv = SubscriptionInvoice.objects.get(store=self.store3)
        self.assertEqual(inv.kind, SubscriptionInvoice.Kind.PLAN_CHANGE)
        self.assertEqual((inv.subtotal, inv.discount_total, inv.amount_due), (Decimal("300000"), Decimal("60000"), Decimal("240000")))
        self.assertEqual(inv.coupon_redemption.status, PlatformCouponRedemption.Status.RESERVED)
        attempt = attempt_service.create_attempt(inv, provider="manual")
        confirmation_service.confirm_payment(attempt=attempt, amount=inv.amount_due, currency="IRT", provider_payment_id="trial-pay-1")
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal("240000")))
        self.assertEqual(inv.coupon_redemption.status, PlatformCouponRedemption.Status.REDEEMED)
        self.assertEqual(StoreSubscription.objects.get(pk=self.sub3.pk).status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(c.counted_redemptions(), 1)

    def test_the_same_coupon_is_not_valid_for_a_later_ordinary_upgrade(self):
        from apps.billing.services import attempt_service, confirmation_service

        coupon(self.finance, "TRIAL20")
        self.buy(self.paid_v, "TRIAL20")
        inv = SubscriptionInvoice.objects.get(store=self.store3)
        confirmation_service.confirm_payment(attempt=attempt_service.create_attempt(inv, provider="manual"), amount=inv.amount_due,
                                             currency="IRT", provider_payment_id="trial-pay-2")
        result = svc.evaluate(self.store3, plan_version=self.top_v, interval="monthly",
                              purpose=svc.purpose_for(self.store3, "plan_change"), code="TRIAL20")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "ineligible_purpose")

    def test_a_plan_change_only_coupon_does_not_apply_to_the_first_paid_purchase(self):
        coupon(self.finance, "ONLYUP", allow_plan_change=True, allow_initial=False)
        preview, _ = self.buy(self.paid_v, "ONLYUP")
        self.assertContains(preview, svc.MESSAGES["ineligible_purpose"])
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store3).count(), 0)

    def test_first_purchase_only_coupon_accepts_trial_conversion(self):
        coupon(self.finance, "FIRSTONLY", first_purchase_only=True)
        _, r = self.buy(self.paid_v, "FIRSTONLY")
        self.assertEqual(SubscriptionInvoice.objects.get(store=self.store3).discount_total, Decimal("60000"))

    def test_active_store_with_no_trial_history_keeps_plan_change_purpose(self):
        active, _sub = (Store.objects.create(name="فعال", slug="pcact", admin_subdomain="pcact"), None)
        ss.activate_subscription(ss.create_subscription(active, self.paid_v), period_end=timezone.now() + timedelta(days=20))
        self.assertEqual(svc.purpose_for(active, "plan_change"), "plan_change")
        self.assertEqual(svc.purpose_for(self.store3, "plan_change"), "initial")
        self.assertEqual(svc.purpose_for(self.store3, "renewal"), "renewal")


def caches_clear():
    from django.core.cache import caches

    caches["ratelimit"].clear()
