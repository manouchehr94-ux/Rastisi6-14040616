"""Trial-to-paid transition: conversion, period dates, history rendering, overview, duplicate protection, tenant isolation.

Real HTTP on the store's admin host, real provisioning (30-day Trial), real settlement path, in-process fake gateway.
Every assertion about money or state reads the database; the two display tests read the rendered page."""

import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PlatformCouponRedemption as Redemption, SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.tests.test_platform_coupon_financial_acceptance import Base
from apps.billing.tests.test_trial_purchase_flow import EXPECTED, make_owner
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as ss
from apps.subscriptions.services import trial_service


class Convert(Base):
    def free_purchase(self, version=None, interval="monthly", client=None, store=None):
        """Real preview -> execute with a 100% coupon -> checkout 'pay' (server settles the zero-value invoice internally)."""
        c, version, store = client or self.client, version or self.pro, store or self.store
        if not hasattr(self, "_q"):
            self._q = self.coupon("QA100", percent=100)
        token = c.post(reverse("dashboard:subscription-plan-preview"),
                       {"version_id": version.pk, "billing_interval": interval, "coupon_code": "QA100"}).context["preview"]["token"]
        c.post(reverse("dashboard:subscription-plan-execute"),
               {"version_id": version.pk, "preview_token": token, "billing_interval": interval, "coupon_code": "QA100"})
        inv = SubscriptionInvoice.objects.filter(store=store, kind="plan_change").latest("pk")
        c.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        inv.refresh_from_db()
        return inv

    def current(self, store=None):
        return StoreSubscription.objects.get(store=store or self.store, is_current=True)

    def events(self, store=None):
        return list(SubscriptionEvent.objects.filter(subscription__store=store or self.store).order_by("created_at", "pk"))


class DefaultTrialTests(Convert):
    def test_default_trial_is_30_days_on_the_internal_trial_plan(self):
        sub = self.current()
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(sub.plan_version.plan.code, trial_service.TRIAL_PLAN_CODE)
        self.assertEqual(sub.trial_end_at - sub.trial_start_at, timedelta(days=30))
        self.assertEqual(ent.get_entitlement_limit(self.store, "catalog.products"), 20)


class ConversionTests(Convert):
    def test_zero_value_conversion_switches_status_plan_and_entitlements_on_the_same_row(self):
        before = self.current()
        inv = self.free_purchase()
        after = self.current()
        self.assertEqual(after.pk, before.pk)                                              # converted, not replaced
        self.assertEqual(StoreSubscription.objects.filter(store=self.store).count(), 1)
        self.assertEqual((after.status, after.plan_version_id), (StoreSubscription.Status.ACTIVE, self.pro.pk))
        self.assertEqual((inv.status, inv.amount_due, inv.amount_paid, inv.subscription_id), ("paid", Decimal(0), Decimal(0), before.pk))
        ent.clear_entitlement_cache()
        self.assertIsNone(ent.get_entitlement_limit(self.store, "catalog.products"))      # Trial limit of 20 is gone (unlimited)
        self.assertEqual(ent.get_effective_plan_version(self.store).plan.code, self.pro.plan.code)

    def test_creating_the_invoice_alone_does_not_convert_anything(self):
        token = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly"}).context["preview"]["token"]
        self.client.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": token, "billing_interval": "monthly"})
        sub = self.current()
        self.assertEqual((sub.status, sub.plan_version.plan.code), (StoreSubscription.Status.TRIALING, trial_service.TRIAL_PLAN_CODE))
        self.assertEqual(ent.get_entitlement_limit(self.store, "catalog.products"), 20)

    def test_the_leftover_trial_end_can_never_downgrade_the_paid_subscription(self):
        self.free_purchase(interval="yearly")
        sub = self.current()
        self.assertIsNotNone(sub.trial_end_at)                                              # kept on purpose: trial history
        result = ss.evaluate_subscription_states(now=sub.trial_end_at + timedelta(days=3))   # past the old trial end, inside the paid year
        self.assertEqual((result["grace"], result["suspended"], result["expired"], result["cancelled"]), (0, 0, 0, 0))
        self.assertEqual(self.current().status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(trial_service.trial_info(self.store)["state"], "converted")
        self.assertEqual(ss.check_subscription_consistency(), [])

    def test_trial_expiry_then_conversion(self):
        sub = self.current()
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()
        self.assertEqual(self.current().status, StoreSubscription.Status.SUSPENDED)       # Trial really expired, still current
        self.free_purchase()
        self.assertEqual(self.current().status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.current().plan_version_id, self.pro.pk)


class PeriodCalculationTests(Convert):
    def _period(self, interval, days_into_trial=0):
        if days_into_trial:
            now = timezone.now()
            StoreSubscription.objects.filter(pk=self.current().pk).update(
                trial_start_at=now - timedelta(days=days_into_trial), trial_end_at=now + timedelta(days=30 - days_into_trial))
        before = timezone.now()
        self.free_purchase(interval=interval)
        return before, self.current()

    def test_the_paid_period_follows_the_purchase_date_and_interval_never_the_trial_end(self):
        for interval, months in (("monthly", 1), ("quarterly", 3), ("semiannual", 6), ("yearly", 12)):
            with self.subTest(interval=interval):
                owner, store = make_owner(f"per-{interval}@example.com", f"دوره {interval}")
                c = self.client_for(store, owner)
                StoreSubscription.objects.filter(store=store).update(trial_start_at=timezone.now() - timedelta(days=7),
                                                                     trial_end_at=timezone.now() + timedelta(days=23))
                self.free_purchase(interval=interval, client=c, store=store)
                sub = self.current(store)
                self.assertEqual(sub.billing_interval, interval)
                start, end = sub.current_period_start, sub.current_period_end
                self.assertLess(abs((start - timezone.now()).total_seconds()), 120)           # starts at the purchase, not at the Trial start
                self.assertNotEqual(end.date(), sub.trial_end_at.date()) if months != 1 else None
                expected_month = (start.month - 1 + months) % 12 + 1
                self.assertEqual(end.month, expected_month)
                self.assertGreater(end, start)

    def test_a_30_day_trial_bought_on_day_zero_with_a_monthly_plan_ends_on_the_same_day_as_the_trial(self):
        """The QA observation (both dates showing the same day) is a coincidence of the inputs, not a period-calculation bug."""
        self.free_purchase(interval="monthly")
        sub = self.current()
        self.assertEqual(sub.trial_end_at.date(), sub.current_period_end.date())
        self.assertGreaterEqual(sub.current_period_end, sub.trial_end_at - timedelta(seconds=5))
        self.assertGreater(sub.current_period_end, sub.current_period_start)

    def test_a_purchase_later_in_the_trial_gets_a_period_that_ends_after_the_trial_end(self):
        _, sub = self._period("monthly", days_into_trial=10)
        self.assertGreater(sub.current_period_end, sub.trial_end_at)


class SubscriptionHistoryTests(Convert):
    def _rows(self):
        html = self.client.get(reverse("dashboard:subscription-history")).content.decode()
        out = []
        for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
            frm = re.search(r'data-testid="event-from-status">(.*?)</td>', tr, re.S)
            to = re.search(r'data-testid="event-to-status">(.*?)</td>', tr, re.S)
            if frm and to:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                out.append((re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cells[1])).strip(), frm.group(1).strip(), to.group(1).strip(),
                            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cells[4])).strip()))
        return out

    def test_persisted_events_carry_statuses_and_the_invoice_keys(self):
        self.free_purchase()
        evs = [(e.event_type, e.from_status, e.to_status) for e in self.events()]
        self.assertEqual(evs, [("created", "", "pending"), ("trial_started", "pending", "trialing"),
                               ("plan_changed", "trialing", "trialing"), ("activated", "trialing", "active")])
        inv = SubscriptionInvoice.objects.get(store=self.store)
        keys = {e.event_type: e.idempotency_key for e in self.events()}
        self.assertEqual(keys["plan_changed"], f"invoice-{inv.pk}")
        self.assertEqual(keys["activated"], f"invoice-{inv.pk}-activate")

    def test_history_page_shows_the_from_and_to_status_of_every_event(self):
        self.free_purchase()
        rows = self._rows()
        self.assertEqual(len(rows), 4)
        by_event = {r[0]: r for r in rows}
        labels = {str(s.label) for s in StoreSubscription.Status}
        for name, frm, to, _ in rows:
            self.assertIn(to, labels, f"{name}: to-status must be a real status label, got {to!r}")
        activated = [r for r in rows if r[2] == str(StoreSubscription.Status.ACTIVE.label)]
        self.assertEqual(len(activated), 1)
        self.assertEqual(activated[0][1], str(StoreSubscription.Status.TRIALING.label))        # trialing -> active is visible
        created = [r for r in rows if r[1] == "—"]
        self.assertEqual(len(created), 1)                                                       # only the creation event has no previous status
        self.assertEqual(len(by_event), 4)

    def test_status_labels_are_safe_for_empty_and_unknown_values(self):
        e = SubscriptionEvent(from_status="", to_status="legacy_unknown")
        self.assertEqual(e.from_status_label, "")
        self.assertEqual(e.to_status_label, "legacy_unknown")
        self.assertEqual(SubscriptionEvent(to_status="active").to_status_label, str(StoreSubscription.Status.ACTIVE.label))

    def test_plan_column_has_no_dangling_arrow_for_the_creation_event_and_keeps_the_change_for_plan_changes(self):
        self.free_purchase()
        plans = {r[0]: r[3] for r in self._rows()}
        created_plan = [v for k, v in plans.items() if "←" not in v and v != "—"]
        self.assertTrue(created_plan, "creation row shows just the plan name")
        self.assertEqual(sum("←" in v for v in plans.values()), 1)                              # exactly the plan change


class OverviewTests(Convert):
    TRIAL_END = "پایان دورهی آزمایشی"
    PERIOD_END = "پایان دورهی جاری"

    def _overview(self):
        """Page text with zero-width non-joiners removed and the Persian ezafe marks dropped, so labels compare by their words."""
        html = self.client.get(reverse("dashboard:subscription-overview")).content.decode()
        text = html.replace("\u200c", "").replace("\u0650", "")
        return re.sub(r"\s+", " ", text)

    def _has(self, html, label):
        return re.sub(r"\s+", " ", label) in html

    def test_running_trial_shows_its_end_date(self):
        self.assertTrue(self._has(self._overview(), self.TRIAL_END))

    def test_converted_paid_subscription_does_not_show_a_stale_trial_end_but_shows_the_period_end(self):
        self.free_purchase()
        html = self._overview()
        self.assertFalse(self._has(html, self.TRIAL_END))
        self.assertTrue(self._has(html, self.PERIOD_END))
        self.assertIsNotNone(self.current().trial_end_at)                                       # data kept; only the display changed

    def test_expired_trial_still_shows_when_it_ended(self):
        StoreSubscription.objects.filter(pk=self.current().pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()
        self.assertTrue(self._has(self._overview(), self.TRIAL_END))


class DuplicateProtectionAndFailureTests(Convert):
    def test_repeated_settlement_requests_change_nothing_further(self):
        inv = self.free_purchase()
        snapshot = (self.current().current_period_end, self.current().status, len(self.events()),
                    SubscriptionPaymentAttempt.objects.filter(invoice=inv).count(), Redemption.objects.filter(invoice=inv).count())
        pay = reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk])
        with mock.patch("apps.billing.services.payment_flow_service.start_payment") as start:
            for _ in range(3):
                self.client.post(pay, {"method": "zibal"})
            start.assert_not_called()
        again = (self.current().current_period_end, self.current().status, len(self.events()),
                 SubscriptionPaymentAttempt.objects.filter(invoice=inv).count(), Redemption.objects.filter(invoice=inv).count())
        self.assertEqual(snapshot, again)
        self.assertEqual(snapshot[2:], (4, 1, 1))

    def test_only_one_activation_event_exists_after_settlement_and_repeats(self):
        inv = self.free_purchase()
        self.client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)

    def test_coupon_is_redeemed_once_and_a_second_purchase_gets_no_discount(self):
        inv = self.free_purchase(version=self.lite)                                              # cheap plan first, so pro is a real upgrade
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REDEEMED)
        self.portal_buy(self.store, self.owner, self.pro)
        second = SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").latest("pk")
        self.assertNotEqual(second.pk, inv.pk)
        self.assertEqual(second.discount_total, Decimal(0))
        self.assertEqual(Redemption.objects.filter(store=self.store).count(), 1)

    def test_failed_payment_leaves_the_trial_untouched_and_the_retry_converts_once(self):
        self.coupon("PART20", percent=20)
        token = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly", "coupon_code": "PART20"}).context["preview"]["token"]
        self.client.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": token, "billing_interval": "monthly", "coupon_code": "PART20"})
        inv = self.invoice()
        failed = self.pay_online(inv)
        self.callback(failed, "success=0&status=3&trackId=%d" % self.fake.track_id)
        self.assertEqual((self.current().status, self.current().plan_version.plan.code), (StoreSubscription.Status.TRIALING, trial_service.TRIAL_PLAN_CODE))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 0)
        self.settle_online(inv)
        self.assertEqual(self.current().status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)

    def test_an_abandoned_open_invoice_converts_nothing_and_keeps_the_reservation_only(self):
        self.coupon("PART20", percent=20)
        token = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly", "coupon_code": "PART20"}).context["preview"]["token"]
        self.client.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": token, "billing_interval": "monthly", "coupon_code": "PART20"})
        self.pay_online(self.invoice())                                                        # started, never completed
        self.assertEqual(self.current().status, StoreSubscription.Status.TRIALING)
        self.assertEqual(Redemption.objects.get(invoice=self.invoice()).status, Redemption.Status.RESERVED)


class TenantIsolationTests(Convert):
    def test_another_stores_owner_cannot_see_or_settle_this_stores_free_conversion(self):
        self.coupon("QA100", percent=100)
        token = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly", "coupon_code": "QA100"}).context["preview"]["token"]
        self.client.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": token, "billing_interval": "monthly", "coupon_code": "QA100"})
        inv = self.invoice()
        other_owner, other_store = make_owner("iso-other@example.com", "دیگری")
        other = self.client_for(other_store, other_owner)
        self.assertEqual(other.get(reverse("dashboard:platform-checkout", args=["subscription", inv.pk])).status_code, 404)
        self.assertEqual(other.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"}).status_code, 404)
        inv.refresh_from_db()
        self.assertNotEqual(inv.status, "paid")
        self.assertEqual(self.current().status, StoreSubscription.Status.TRIALING)
        self.assertEqual(self.current(other_store).status, StoreSubscription.Status.TRIALING)

    def test_history_page_lists_only_this_stores_events(self):
        self.free_purchase()
        other_owner, other_store = make_owner("iso-hist@example.com", "تاریخچه")
        other = self.client_for(other_store, other_owner)
        html = other.get(reverse("dashboard:subscription-history")).content.decode()
        self.assertEqual(html.count('data-testid="event-to-status"'), 2)                       # its own created + trial_started only
