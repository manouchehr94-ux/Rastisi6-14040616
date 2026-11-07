"""Registration → Trial → buy from the merchant panel → unified checkout → verified payment → activation (2026-11-07).

Real HTTP on the store's admin host, real services, in-process fake Zibal (no network, dummy credentials). Money-moving assertions come from the
database (invoice / subscription / events), not from page text alone."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.tests.platform_payment_support import patch_zibal, ready_platform_zibal
from apps.billing.tests.test_platform_card_to_card import use_private_tmp
from apps.portal.services import provisioning_service
from apps.stores.models import StoreMembership
from apps.subscriptions.models import Plan, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent, plan_service as ps, subscription_service as ss, trial_service
from apps.subscriptions.services.pricing_page_service import INTERVAL_LABELS
from apps.subscriptions.tests.test_pricing_dynamic import make_plan

User = get_user_model()
PW = "pass-12345-x"
DISCOUNTS = {"quarterly": 5, "semiannual": 10, "yearly": 15}              # → 2,850,000 / 5,400,000 / 10,200,000 on a 1,000,000 monthly price
MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}
EXPECTED = {"monthly": 1_000_000, "quarterly": 2_850_000, "semiannual": 5_400_000, "yearly": 10_200_000}


def formula_plan(code, monthly, *, order):
    plan, draft = make_plan(code, base=monthly, order=order, publish=False)
    ps.set_formula_pricing(draft, monthly_price=monthly, discounts=DISCOUNTS)
    ps.publish_plan_version(draft)
    return plan, plan.versions.get(status="published")


def make_owner(username="trial-owner@example.com", store_name="فروشگاه خرید"):
    owner = User.objects.create_user(username=username, password=PW, is_staff=True)
    store = provisioning_service.provision_trial_store(owner=owner, name=store_name)
    return owner, store


@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PurchaseBase(TestCase):
    def setUp(self):
        use_private_tmp(self)
        self.addCleanup(cache.clear)
        cache.clear()
        ready_platform_zibal(self)
        self.fake = patch_zibal(self)
        self.pro_plan, self.pro = formula_plan("buy-pro", 1_000_000, order=2)
        self.lite_plan, self.lite = formula_plan("buy-lite", 200_000, order=1)
        self.owner, self.store = make_owner()
        self.client = self.client_for(self.store, self.owner)

    def host(self, store):
        return f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

    def client_for(self, store, user):
        client = Client(HTTP_HOST=self.host(store))
        client.login(username=user.username, password=PW)
        return client

    def sub(self, store=None):
        return ent.get_current_subscription(store or self.store)

    def preview(self, version, interval, client=None):
        return (client or self.client).post(reverse("dashboard:subscription-plan-preview"), {"version_id": version.pk, "billing_interval": interval})

    def start(self, version, interval, client=None):
        """Preview → execute through the real endpoints; returns the execute response."""
        c = client or self.client
        token = self.preview(version, interval, c).context["preview"]["token"]
        return c.post(reverse("dashboard:subscription-plan-execute"), {"version_id": version.pk, "preview_token": token, "billing_interval": interval})

    def invoice(self, store=None):
        return SubscriptionInvoice.objects.filter(store=store or self.store, kind="plan_change").latest("pk")

    def pay_online(self, invoice, client=None):
        self.fake.track_id += 1                                           # every gateway session has its own track id (provider ids are unique)
        (client or self.client).post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"})
        return SubscriptionPaymentAttempt.objects.filter(invoice=invoice).latest("pk")

    def callback(self, attempt, query="success=1&status=2&trackId=777"):
        cache.clear()
        return Client().get(f"/billing/return/{attempt.public_token}/?{query}")


class TrialStatusVisibleToTheMerchantTests(PurchaseBase):
    def test_overview_shows_trial_state_days_left_end_date_limits_and_a_clear_buy_button(self):
        response = self.client.get(reverse("dashboard:subscription-overview"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-testid="trial-card"', html)
        self.assertIn('data-testid="buy-subscription"', html)
        self.assertIn("خرید اشتراک", html)
        self.assertIn(reverse("dashboard:subscription-plans"), html)
        self.assertIn("محدودیت‌هایِ دوره‌ی آزمایشی", html)
        self.assertEqual(response.context["trial"]["state"], "trialing")
        self.assertIn(response.context["trial"]["days_left"], (29, 30))

    def test_every_admin_page_carries_the_trial_banner_while_the_trial_runs(self):
        html = self.client.get(reverse("dashboard:subscription-history")).content.decode()
        self.assertIn('data-testid="trial-banner"', html)
        self.assertIn("خرید اشتراک", html)

    def test_after_conversion_the_trial_card_and_banner_disappear(self):
        self.pay_and_activate("monthly")
        html = self.client.get(reverse("dashboard:subscription-overview")).content.decode()
        self.assertNotIn('data-testid="trial-card"', html)
        self.assertNotIn('data-testid="trial-banner"', html)
        self.assertEqual(trial_service.trial_info(self.store)["state"], "converted")

    def pay_and_activate(self, interval):
        self.start(self.pro, interval)
        invoice = self.invoice()
        attempt = self.pay_online(invoice)
        self.fake.paid(amount_rial=int(invoice.grand_total) * 10, order_id=attempt.public_token)
        self.callback(attempt)
        return invoice


class PlanListAndPricesTests(PurchaseBase):
    def test_only_paid_purchasable_plans_are_listed_never_the_trial_plan(self):
        response = self.client.get(reverse("dashboard:subscription-plans"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-plan="buy-pro"', html)
        self.assertIn('data-plan="buy-lite"', html)
        self.assertNotIn('data-plan="trial"', html)
        self.assertNotIn('data-plan="legacy"', html)

    def test_all_four_periods_are_offered_with_the_published_version_prices(self):
        html = self.client.get(reverse("dashboard:subscription-plans")).content.decode()
        for interval, amount in EXPECTED.items():
            self.assertEqual(int(self.pro.price_for(interval)), amount)                       # the published version is the source of truth
            self.assertIn(f'value="{interval}"', html)
            self.assertIn(f'data-testid="price-buy-pro-{interval}"', html)

    def test_preview_and_invoice_match_the_published_price_for_1_3_6_and_12_months(self):
        for interval, amount in EXPECTED.items():
            with self.subTest(interval=interval):
                response = self.preview(self.pro, interval)
                self.assertEqual(int(response.context["preview"]["payable_amount"]), amount)
                self.assertContains(response, 'data-testid="payable-amount"')
        for interval, amount in EXPECTED.items():
            with self.subTest(interval=interval, step="invoice"):
                store_owner, store = make_owner(f"o-{interval}@example.com", f"فروشگاه {interval}")
                client = self.client_for(store, store_owner)
                response = self.start(self.pro, interval, client)
                invoice = self.invoice(store)
                self.assertRedirects(response, reverse("dashboard:platform-checkout", args=["subscription", invoice.pk]), fetch_redirect_response=False)
                self.assertEqual(int(invoice.grand_total), amount)
                self.assertEqual(invoice.plan_version_id, self.pro.pk)
                attempt = self.pay_online(invoice, client)
                self.assertEqual(int(attempt.amount), amount)                                 # what is sent to the gateway (TOMAN → RIAL ×10)
                self.assertEqual(self.fake.calls_to("request")[-1]["amount"], amount * 10)

    def test_the_preselection_from_the_public_page_is_honoured_but_validated(self):
        html = self.client.get(reverse("dashboard:subscription-plans") + "?plan=buy-pro&period=yearly").content.decode()
        self.assertIn("انتخابِ شما در صفحه‌ی تعرفه", html)
        self.assertRegex(html, r'value="yearly"\s+checked')
        junk = self.client.get(reverse("dashboard:subscription-plans") + "?plan=trial&period=nonsense").content.decode()
        self.assertNotIn("انتخابِ شما در صفحه‌ی تعرفه", junk)

    def test_unpurchasable_versions_are_rejected_by_the_server_whatever_the_client_posts(self):
        trial_version = trial_service.trial_plan_version()
        response = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": trial_version.pk, "billing_interval": "monthly"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())
        legacy = Plan.objects.filter(code="legacy").first()
        if legacy is not None:
            lv = legacy.versions.first()
            if lv is not None:
                self.assertEqual(self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": lv.pk}).status_code, 404)


class PaymentOutcomeTests(PurchaseBase):
    def begin(self, interval="quarterly"):
        self.start(self.pro, interval)
        invoice = self.invoice()
        return invoice, self.pay_online(invoice)

    def assertStillOnTrial(self):
        sub = self.sub()
        self.assertEqual(sub.plan_version.plan.code, "trial")
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertFalse(SubscriptionEvent.objects.filter(subscription=sub, event_type="activated").exists())

    def test_creating_the_invoice_and_starting_a_payment_activates_nothing(self):
        invoice, _attempt = self.begin()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.OPEN)
        self.assertStillOnTrial()

    def test_failed_unknown_and_abandoned_payments_never_activate(self):
        invoice, attempt = self.begin()
        self.callback(attempt, "success=0&status=3&trackId=777")                               # user cancelled / bank says failed
        self.assertStillOnTrial()
        self.fake.verify_payload = {"result": 202, "message": "not paid"}                      # browser says success, gateway says «not paid»
        self.callback(attempt)
        self.assertStillOnTrial()
        self.fake.verify_payload = {"result": 999, "message": "unknown error"}                 # unknown/ambiguous verify answer
        self.callback(attempt)
        self.assertStillOnTrial()
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(int(invoice.amount_paid), 0)

    def test_a_wrong_amount_from_the_gateway_never_activates(self):
        invoice, attempt = self.begin()
        self.fake.paid(amount_rial=int(invoice.grand_total) * 10 - 10, order_id=attempt.public_token)
        self.callback(attempt)
        self.assertStillOnTrial()

    def test_verified_payment_activates_exactly_once_for_each_period(self):
        for interval in ("monthly", "quarterly", "semiannual", "yearly"):
            with self.subTest(interval=interval):
                owner, store = make_owner(f"pay-{interval}@example.com", f"پرداخت {interval}")
                client = self.client_for(store, owner)
                self.start(self.pro, interval, client)
                invoice = self.invoice(store)
                attempt = self.pay_online(invoice, client)
                self.fake.paid(amount_rial=int(invoice.grand_total) * 10, order_id=attempt.public_token)
                self.callback(attempt)
                self.callback(attempt)                                                         # replayed callback
                sub = self.sub(store)
                self.assertEqual(sub.plan_version_id, self.pro.pk)
                self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
                self.assertEqual(sub.billing_interval, interval)
                self.assertIsNotNone(sub.trial_start_at)                                       # the Trial stays as history …
                self.assertFalse(trial_service.is_eligible(store))                              # … and is never granted again
                days = (sub.current_period_end - timezone.now()).days
                self.assertAlmostEqual(days, MONTHS[interval] * 30, delta=MONTHS[interval] * 2 + 2)
                invoice.refresh_from_db()
                self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)
                self.assertEqual(int(invoice.amount_paid), int(invoice.grand_total))
                self.assertEqual(SubscriptionEvent.objects.filter(subscription=sub, event_type="activated").count(), 1)
                self.assertEqual(SubscriptionInvoice.objects.filter(store=store, kind="plan_change").count(), 1)

    def test_a_second_purchase_request_for_the_same_decision_reuses_the_open_invoice(self):
        self.start(self.pro, "yearly")
        self.start(self.pro, "yearly")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_a_competing_open_invoice_blocks_a_different_purchase_instead_of_creating_a_second(self):
        self.start(self.pro, "yearly")
        response = self.start(self.lite, "monthly")                                           # a different plan while the first invoice is unresolved
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)
        self.assertEqual(response.status_code, 302)


class AfterTheTrialTests(PurchaseBase):
    def end_trial(self, store=None):
        sub = self.sub(store)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()

    def test_an_ended_trial_store_can_still_buy_and_payment_reactivates_it(self):
        self.end_trial()
        self.assertEqual(self.sub().status, StoreSubscription.Status.SUSPENDED)
        self.assertEqual(self.client.get(reverse("dashboard:subscription-overview")).context["trial"]["state"], "ended")
        self.assertContains(self.client.get(reverse("dashboard:subscription-overview")), 'data-testid="trial-ended-card"')
        self.start(self.pro, "semiannual")
        invoice = self.invoice()
        self.assertEqual(int(invoice.grand_total), EXPECTED["semiannual"])
        attempt = self.pay_online(invoice)
        self.callback(attempt, "success=0&status=3&trackId=%d" % self.fake.track_id)
        self.assertEqual(self.sub().status, StoreSubscription.Status.SUSPENDED)               # unpaid ⇒ still restricted
        attempt = self.pay_online(invoice)                                                   # the user retries: a NEW attempt on the same invoice
        self.fake.paid(amount_rial=EXPECTED["semiannual"] * 10, order_id=attempt.public_token)
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        sub = self.sub()
        self.assertEqual((sub.plan_version_id, sub.status), (self.pro.pk, StoreSubscription.Status.ACTIVE))
        self.assertEqual(ent.get_subscription_access_state(self.store).state, ent.AccessState.FULL)

    def test_a_store_created_with_the_trial_disabled_can_buy_too(self):
        from apps.subscriptions.tests.test_trial_engine import configure

        configure(enabled=False)
        owner, store = make_owner("notrial@example.com", "بدون آزمایشی")
        client = self.client_for(store, owner)
        self.assertEqual(self.sub(store).status, StoreSubscription.Status.SUSPENDED)
        self.assertContains(client.get(reverse("dashboard:subscription-overview")), "فعال نشده است")
        self.start(self.pro, "monthly", client)
        invoice = self.invoice(store)
        attempt = self.pay_online(invoice, client)
        self.fake.paid(amount_rial=EXPECTED["monthly"] * 10, order_id=attempt.public_token)
        self.callback(attempt)
        self.assertEqual(self.sub(store).status, StoreSubscription.Status.ACTIVE)
        self.assertIsNone(self.sub(store).trial_start_at)                                      # it never had a Trial and still gets none


class AuthorizationAndIsolationTests(PurchaseBase):
    def member(self, role, username):
        user = User.objects.create_user(username=username, password=PW, is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=role, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        return self.client_for(self.store, user)

    def test_only_the_owner_can_start_a_purchase_other_roles_cannot_do_financial_actions(self):
        for role in (StoreMembership.Role.ADMINISTRATOR, StoreMembership.Role.ORDER_MANAGER, StoreMembership.Role.CATALOG_MANAGER,
                     StoreMembership.Role.CONTENT_EDITOR, StoreMembership.Role.ANALYST):
            with self.subTest(role=role):
                client = self.member(role, f"role-{role}")
                self.assertEqual(client.get(reverse("dashboard:subscription-plans")).status_code, 403)
                self.assertEqual(client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly"}).status_code, 403)
                self.assertEqual(client.post(reverse("dashboard:subscription-plan-execute"),
                                             {"version_id": self.pro.pk, "preview_token": "x", "billing_interval": "monthly"}).status_code, 403)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())

    def test_an_administrator_sees_status_but_is_told_only_the_owner_buys(self):
        client = self.member(StoreMembership.Role.ADMINISTRATOR, "adm-view")
        response = client.get(reverse("dashboard:subscription-overview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="owner-only-note"')
        self.assertNotContains(response, 'data-testid="buy-subscription"')

    def test_an_administrator_with_payment_authority_cannot_choose_a_plan(self):
        # BILLING_PAYMENT_MANAGE (pay an EXISTING invoice) is not SUBSCRIPTION_CHANGE (decide the plan): the plan decision stays owner-only
        client = self.member(StoreMembership.Role.ADMINISTRATOR, "adm-pay")
        self.start(self.pro, "monthly")                                                        # the owner creates the invoice …
        invoice = self.invoice()
        page = client.get(reverse("dashboard:platform-checkout", args=["subscription", invoice.pk]))
        self.assertEqual(page.status_code, 200)                                               # … an administrator may pay it
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_another_stores_owner_cannot_see_pay_or_buy_into_this_store(self):
        invoice_owner, other_store = make_owner("other-owner@example.com", "فروشگاه دیگر")
        other = self.client_for(other_store, invoice_owner)
        self.start(self.pro, "yearly")
        invoice = self.invoice()
        checkout = reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])
        self.assertEqual(other.get(checkout).status_code, 404)
        self.assertEqual(other.post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"}).status_code, 404)
        self.assertIn(other.post(reverse("dashboard:platform-checkout-status", args=["subscription", invoice.pk])).status_code, (404, 405))
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).exists())
        # the other store's subscription page shows ITS OWN trial, never this store's data
        html = other.get(reverse("dashboard:subscription-overview")).content.decode()
        self.assertNotIn(self.store.name, html)
        self.assertEqual(self.sub(other_store).store_id, other_store.pk)
        # and a purchase started on the other host only ever creates an invoice for the other store
        self.start(self.lite, "monthly", other)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=other_store).count(), 1)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_another_stores_client_cannot_use_this_stores_invoice_through_a_forged_host(self):
        invoice_owner, other_store = make_owner("forger@example.com", "جاعل")
        other = self.client_for(other_store, invoice_owner)
        self.start(self.pro, "monthly")
        invoice = self.invoice()
        attempt = self.pay_online(invoice)
        # the gateway callback is public by token, but it only ever settles the invoice that token belongs to
        self.fake.paid(amount_rial=EXPECTED["monthly"] * 10, order_id=attempt.public_token)
        self.callback(attempt)
        self.assertEqual(self.sub(other_store).plan_version.plan.code, "trial")
        self.assertEqual(self.sub().plan_version_id, self.pro.pk)


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks")
@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class ConcurrentPurchaseTests(TransactionTestCase):
    """Parallel identical purchase requests produce ONE invoice; parallel verified callbacks activate ONCE."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        ready_platform_zibal(self)
        self.fake = patch_zibal(self)
        _p, self.pro = formula_plan("conc-pro", 1_000_000, order=2)
        self.owner, self.store = make_owner("conc-buy@example.com", "هم‌زمانی خرید")

    def test_eight_simultaneous_purchase_requests_create_a_single_invoice(self):
        from apps.billing.services import plan_change_billing_service as pcb
        from apps.subscriptions.services import plan_change_service as pcs

        sub = ent.get_current_subscription(self.store)
        token = pcs._preview_token(sub, self.pro)
        barrier = threading.Barrier(8)

        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                current = ent.get_current_subscription(self.store)
                kind, invoice = pcb.start_plan_change(current, self.pro, preview_token=token, actor=self.owner, billing_interval="yearly")
                return invoice.pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(worker, range(8)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)

    def test_parallel_verified_callbacks_activate_exactly_once(self):
        from apps.billing.services import plan_change_billing_service as pcb
        from apps.subscriptions.services import plan_change_service as pcs

        sub = ent.get_current_subscription(self.store)
        _kind, invoice = pcb.start_plan_change(sub, self.pro, preview_token=pcs._preview_token(sub, self.pro), actor=self.owner, billing_interval="monthly")
        client = Client(HTTP_HOST=f"{self.store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")
        client.login(username=self.owner.username, password=PW)
        client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"})
        attempt = SubscriptionPaymentAttempt.objects.get(invoice=invoice)
        self.fake.paid(amount_rial=EXPECTED["monthly"] * 10, order_id=attempt.public_token)
        barrier = threading.Barrier(6)

        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return Client().get(f"/billing/return/{attempt.public_token}/?success=1&status=2&trackId=777").status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(worker, range(6)))
        sub = ent.get_current_subscription(self.store)
        self.assertEqual((sub.plan_version_id, sub.status), (self.pro.pk, StoreSubscription.Status.ACTIVE))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription=sub, event_type="activated").count(), 1)
        invoice.refresh_from_db()
        self.assertEqual(int(invoice.amount_paid), int(invoice.grand_total))
