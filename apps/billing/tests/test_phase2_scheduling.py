"""Phase 2 / F-03: the platform billing jobs are scheduled, single-instance and visible to the health check.

The repository cannot prove what runs on a production server; these tests prove the repository side: every money-relevant job is in
``deploy/cron/rastisi.crontab`` with a command that exists, overlapping runs skip instead of doubling, and a missing/stalled job
shows up as a WARNING/CRITICAL symptom in ``check_background_jobs``."""

import io
import json
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.management import call_command, get_commands
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.billing.models import BillingWebhookEvent, SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.billing.services import refund_service
from apps.billing.tests.test_phase2_financial_suspension import FinBase, renewal, pay
from apps.core.management.commands.check_background_jobs import collect
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc

ROOT = Path(__file__).resolve().parents[3]
CRONTAB = ROOT / "deploy" / "cron" / "rastisi.crontab"

#: Every platform-billing command that must run on a schedule, with the cadence the runbook documents.
REQUIRED_JOBS = {
    "reconcile_platform_payments": "*/10",
    "reprocess_billing_webhooks": "*/5",
    "recover_stale_refunds": "*/10",
    "expire_platform_card_claims": "*/10",
    "release_expired_platform_coupon_reservations": "*/10",
    "evaluate_subscription_states": "10 *",
    "generate_subscription_renewals": "30 2",
    "process_subscription_dunning": "0 3",
    "verify_billing_consistency": "0 4",
    "verify_subscription_consistency": "15 4",
}


def scheduled_lines():
    return [l for l in CRONTAB.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")
            and "$JOB" in l and not l.startswith(("JOB=", "RASTISI"))]


class CrontabContractTests(SimpleTestCase):
    def test_every_required_billing_job_is_scheduled_with_an_existing_command(self):
        lines = scheduled_lines()
        commands = get_commands()
        for name, cadence in REQUIRED_JOBS.items():
            with self.subTest(job=name):
                self.assertIn(name, commands, "the command does not exist")
                matching = [l for l in lines if re.search(rf"\s{re.escape(name)}(\s|$)", l)]
                self.assertEqual(len(matching), 1, f"{name} must be scheduled exactly once")
                self.assertEqual(" ".join(matching[0].split()[:len(cadence.split())]), cadence, f"{name}: {matching[0]}")

    def test_every_scheduled_command_exists(self):
        commands = get_commands()
        for line in scheduled_lines():
            name = re.split(r"\s+", line.split("$JOB", 1)[1].strip())[1]
            self.assertIn(name, commands, line)

    def test_strict_verification_jobs_use_strict_so_findings_alert(self):
        text = CRONTAB.read_text(encoding="utf-8")
        for name in ("verify_billing_consistency", "verify_subscription_consistency"):
            self.assertRegex(text, rf"{name} --strict")

    def test_the_validation_script_dry_runs_the_billing_jobs(self):
        text = (ROOT / "deploy" / "cron" / "validate_jobs.sh").read_text(encoding="utf-8")
        for name in ("reconcile_platform_payments", "reprocess_billing_webhooks", "evaluate_subscription_states",
                     "generate_subscription_renewals", "process_subscription_dunning"):
            self.assertIn(f"{name} --dry-run", text)


class SingleInstanceTests(TestCase):
    def test_an_overlapping_run_skips_without_working_and_exits_zero(self):
        from apps.core import job_lock

        class Held:
            def __enter__(self):
                return False

            def __exit__(self, *a):
                return False

        for name in ("reprocess_billing_webhooks", "recover_stale_refunds", "evaluate_subscription_states",
                     "reconcile_platform_payments", "generate_subscription_renewals", "process_subscription_dunning"):
            with self.subTest(job=name), mock.patch.object(job_lock, "single_instance", return_value=Held()):
                out = io.StringIO()
                call_command(name, stdout=out)
                self.assertIn(f"skipped: another {name} is still running", out.getvalue())

    def test_a_free_lock_runs_the_job(self):
        out = io.StringIO()
        call_command("reprocess_billing_webhooks", stdout=out)
        self.assertIn("reprocess_billing_webhooks: due=0", out.getvalue())


def billing_checks(now=None):
    return {c["check"]: c for c in collect(now or timezone.now()) if c["check"].startswith(("billing_", "subscription_"))}


class BillingHealthTests(FinBase):
    def test_a_clean_system_reports_every_billing_check_ok(self):
        checks = billing_checks()
        self.assertGreaterEqual(len(checks), 10)
        self.assertEqual({c["level"] for c in checks.values()}, {"OK"}, checks)

    def test_a_stalled_online_attempt_escalates_when_reconciliation_is_not_running(self):
        inv = pay(renewal(self.sub, self.day(1), self.day(31)))
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=inv, provider="zibal", status=SubscriptionPaymentAttempt.Status.PENDING, amount=Decimal("1"),
            currency="IRT", provider_session_id="s1", idempotency_key="hc-1")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(billing_checks()["billing_stale_attempts"]["level"], "WARNING")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(billing_checks()["billing_stale_attempts"]["level"], "CRITICAL")

    def test_parked_confirmed_money_is_flagged_after_a_day_and_critical_after_three(self):
        inv = pay(renewal(self.sub, self.day(1), self.day(31)))
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=inv, provider="zibal", status=SubscriptionPaymentAttempt.Status.REQUIRES_ACTION,
            amount=Decimal("1"), currency="IRT", failure_code="late_payment_void", idempotency_key="hc-2")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(hours=30))
        self.assertEqual(billing_checks()["billing_requires_action"]["level"], "WARNING")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(hours=80))
        self.assertEqual(billing_checks()["billing_requires_action"]["level"], "CRITICAL")

    def test_stuck_and_exhausted_webhooks_are_visible(self):
        P = BillingWebhookEvent.ProcessingStatus
        ev = BillingWebhookEvent.objects.create(
            provider="manual", external_event_id="hc-wh", signature_valid=True, sanitized_payload={}, received_at=timezone.now())
        BillingWebhookEvent.objects.filter(pk=ev.pk).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(billing_checks()["billing_webhooks_stuck"]["level"], "WARNING")
        BillingWebhookEvent.objects.filter(pk=ev.pk).update(processing_status=P.FAILED, retry_count=5)
        checks = billing_checks()
        self.assertEqual(checks["billing_webhooks_exhausted"]["level"], "CRITICAL")
        self.assertEqual(checks["billing_webhooks_stuck"]["level"], "OK")

    def test_an_unknown_refund_outcome_escalates_until_finance_resolves_it(self):
        sub_svc.activate_subscription(self.sub, period_end=self.day(30))
        inv = pay(renewal(self.sub, self.day(-30), self.day(30)))
        row = SubscriptionRefund.objects.create(
            store=self.store, invoice=inv, provider="manual", status=SubscriptionRefund.Status.PENDING, amount=Decimal("1"),
            currency="IRT", requested_at=timezone.now(), idempotency_key="hc-rf", failure_code=refund_service.UNKNOWN_OUTCOME)
        SubscriptionRefund.objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(billing_checks()["billing_refund_unknown_outcome"]["level"], "WARNING")
        SubscriptionRefund.objects.filter(pk=row.pk).update(updated_at=timezone.now() - timedelta(hours=30))
        self.assertEqual(billing_checks()["billing_refund_unknown_outcome"]["level"], "CRITICAL")

    def test_an_unevaluated_expired_subscription_shows_when_the_evaluator_is_not_running(self):
        sub_svc.activate_subscription(self.sub, period_end=timezone.now() - timedelta(hours=5))
        self.assertEqual(billing_checks()["subscription_transitions_overdue"]["level"], "WARNING")
        StoreSubscription.objects.filter(pk=self.sub.pk).update(current_period_end=timezone.now() - timedelta(days=3))
        self.assertEqual(billing_checks()["subscription_transitions_overdue"]["level"], "CRITICAL")
        call_command("evaluate_subscription_states", stdout=io.StringIO())
        self.assertEqual(billing_checks()["subscription_transitions_overdue"]["level"], "OK")

    def test_a_financially_suspended_subscription_whose_paid_period_began_is_critical_until_restored(self):
        sub_svc.activate_subscription(self.sub, period_end=self.day(-30))
        current = pay(renewal(self.sub, self.day(-30), self.day(30)))
        pay(renewal(self.sub, self.day(30), self.day(60)))
        self.full_refund(current)
        later = self.day(31)
        self.assertEqual(billing_checks(later)["billing_financial_suspension_unrestored"]["level"], "CRITICAL")
        self.assertEqual(billing_checks(self.now)["billing_financial_suspension_unrestored"]["level"], "OK")

    def test_the_command_exit_code_reflects_the_worst_billing_symptom(self):
        inv = pay(renewal(self.sub, self.day(1), self.day(31)))
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=inv, provider="zibal", status=SubscriptionPaymentAttempt.Status.PENDING, amount=Decimal("1"),
            currency="IRT", provider_session_id="s2", idempotency_key="hc-3")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=5))
        out = io.StringIO()
        code = 0
        try:
            call_command("check_background_jobs", "--json", stdout=out)
        except SystemExit as exc:
            code = exc.code
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "CRITICAL")


class RenewalsAndDunningAreFlaggedWhenInvoicesStallTests(FinBase):
    def test_a_payment_pending_invoice_older_than_a_day_is_reported(self):
        inv = renewal(self.sub, self.day(1), self.day(31))
        from apps.billing.services import invoice_service

        inv = invoice_service.open_invoice(inv)
        SubscriptionInvoice.objects.filter(pk=inv.pk).update(
            status=SubscriptionInvoice.Status.PAYMENT_PENDING, updated_at=timezone.now() - timedelta(hours=30))
        self.assertEqual(billing_checks()["billing_payment_pending_invoices"]["level"], "WARNING")
