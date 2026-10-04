"""H5: قابلیتِ اتکایِ jobهایِ cron — خروجِ غیرصفر در خطا (بدونِ دورانداختنِ کارِ بی‌ربط)، جداسازیِ خطایِ هر
آیتم، قفلِ تک‌نمونه (PostgreSQL) و بررسیِ سلامتِ فقط‌خواندنی."""

import json
import threading
from datetime import timedelta
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.job_lock import single_instance
from apps.core.models import ShopSettings
from apps.notifications.models import NotificationOutbox
from apps.stores.models import Store


def health():
    out = StringIO()
    code = 0
    try:
        call_command("check_background_jobs", "--json", stdout=out)
    except SystemExit as exc:
        code = exc.code
    return code, json.loads(out.getvalue())


class HealthCheckTests(TestCase):
    def test_clean_system_is_ok_and_reports_expiry_disabled(self):
        code, data = health()
        self.assertEqual((code, data["status"]), (0, "OK"))
        self.assertIn("disabled for all stores", next(c["detail"] for c in data["checks"] if c["check"] == "order_expiry"))

    def test_old_undelivered_notification_escalates_warning_then_critical(self):
        row = NotificationOutbox.objects.create(
            channel="email", store=Store.objects.get(slug="akhlaghi"), body="x", subject="s", recipient_email="a@example.com", event_key="order.created",
        )
        NotificationOutbox.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=45))
        self.assertEqual(health()[0], 1)
        NotificationOutbox.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=3))
        code, data = health()
        self.assertEqual((code, data["status"]), (2, "CRITICAL"))

    def test_stuck_claims_dead_rows_and_open_reconciliations_are_visible(self):
        store = Store.objects.get(slug="akhlaghi")
        NotificationOutbox.objects.create(
            channel="email", store=store, body="x", subject="s", recipient_email="a@example.com", event_key="order.created",
            status="sending", claimed_at=timezone.now() - timedelta(hours=1),
        )
        NotificationOutbox.objects.create(
            channel="email", store=store, body="x", subject="s", recipient_email="a@example.com", event_key="order.created", status="dead",
        )
        levels = {c["check"]: c["level"] for c in health()[1]["checks"]}
        self.assertEqual((levels["notification_stuck_sending"], levels["notification_dead_24h"]), ("WARNING", "WARNING"))


class JobExitCodeTests(TestCase):
    def test_expire_command_isolates_failing_order_and_exits_nonzero(self):
        with patch("apps.orders.management.commands.expire_unpaid_orders.expire_unpaid_orders", return_value={
            "candidates": 3, "expired": 2, "errors": 1, "skipped": {},
        }):
            out = StringIO()
            with self.assertRaises(CommandError):
                call_command("expire_unpaid_orders", stdout=out)
            self.assertIn("errors=1", out.getvalue())

    def test_engagement_jobs_deliver_even_if_campaigns_fail_then_exit_nonzero(self):
        with patch("apps.engagement.management.commands.run_engagement_jobs.run_due_campaigns", side_effect=RuntimeError("x")), \
                patch("apps.engagement.management.commands.run_engagement_jobs.deliver_pending",
                      return_value={"processed": 1, "sent": 1, "failed": 0, "skipped": 0}) as deliver:
            with self.assertRaises(CommandError) as ctx:
                call_command("run_engagement_jobs", stdout=StringIO())
        deliver.assert_called_once()
        self.assertIn("run_due_campaigns", str(ctx.exception))

    def test_engagement_jobs_clean_run_exits_zero(self):
        summary = {"campaigns": 0, "issued": 0, "errors": 0, "expired": 0}
        with patch("apps.engagement.management.commands.run_engagement_jobs.run_due_campaigns", return_value=summary), \
                patch("apps.engagement.management.commands.run_engagement_jobs.deliver_pending",
                      return_value={"processed": 0, "sent": 0, "failed": 0, "skipped": 0}):
            call_command("run_engagement_jobs", stdout=StringIO())

    def test_outbox_command_fails_only_when_whole_batch_failed(self):
        path = "apps.notifications.management.commands.process_notification_outbox.deliver_pending"
        with patch(path, return_value={"processed": 2, "sent": 0, "failed": 2, "skipped": 0}), self.assertRaises(CommandError):
            call_command("process_notification_outbox", stdout=StringIO())
        with patch(path, return_value={"processed": 2, "sent": 1, "failed": 1, "skipped": 0}):
            call_command("process_notification_outbox", stdout=StringIO())

    def test_expire_command_is_a_noop_when_ttl_not_configured(self):
        out = StringIO()
        call_command("expire_unpaid_orders", stdout=out)
        self.assertIn("candidates=0", out.getvalue())


@skipUnless(connection.vendor == "postgresql", "advisory locks need PostgreSQL")
class SingleInstanceLockTests(TransactionTestCase):
    def test_second_runner_is_refused_and_lock_is_released_afterwards(self):
        results = {}
        holding, release = threading.Event(), threading.Event()

        def holder():
            from django.db import close_old_connections

            with single_instance("h5-test") as ok:
                results["holder"] = ok
                holding.set()
                release.wait(10)
            close_old_connections()

        t = threading.Thread(target=holder)
        t.start()
        holding.wait(10)
        with single_instance("h5-test") as second:
            results["second"] = second
        release.set()
        t.join()
        with single_instance("h5-test") as third:
            results["third"] = third
        self.assertEqual((results["holder"], results["second"], results["third"]), (True, False, True))
