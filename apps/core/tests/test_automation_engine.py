"""The shared automation engine: guards, dry run, de-duplication, mutual exclusion, bounded retries, honest recorded results, store scoping."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.core import automation
from apps.core.models import AuditLogEntry
from apps.stores.models import Store

PUBLIC = "shop.brand-example.ir"


class AutomationEngineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(name="A", slug="auto-a", status=Store.Status.ACTIVE)
        self.other = Store.objects.create(name="B", slug="auto-b", status=Store.Status.ACTIVE)
        patcher = mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_op(self, fn, **kw):
        kw.setdefault("host", PUBLIC)
        return automation.run("demo", self.store, fn, sleep=lambda s: None, **kw)

    # ---- guards ------------------------------------------------------------------------------------------------------------
    def test_disabled_does_nothing_and_records_nothing(self):
        fn = mock.Mock()
        result = self.run_op(fn, enabled=False)
        self.assertEqual((result.status, result.reason), (automation.DISABLED, "platform_disabled"))
        fn.assert_not_called()
        self.assertFalse(AuditLogEntry.objects.exists())

    def test_localhost_unknown_host_unpublished_and_inactive_stores_are_blocked(self):
        for host in ("localhost:8000", "shop.rastisi.localhost", "127.0.0.1", ""):
            fn = mock.Mock()
            self.assertEqual(self.run_op(fn, host=host).reason, "test_host", host)
            fn.assert_not_called()
        with mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=False):
            self.assertEqual(self.run_op(mock.Mock()).reason, "store_not_public")
        self.store.status = next(value for value in Store.Status.values if value != Store.Status.ACTIVE)
        self.assertEqual(self.run_op(mock.Mock()).reason, "store_inactive")
        self.assertFalse(AuditLogEntry.objects.exists())

    # ---- dry run -----------------------------------------------------------------------------------------------------------
    def test_dry_run_reports_without_side_effects(self):
        seen = []
        result = self.run_op(lambda dry: seen.append(dry) or {"urls": 3}, dry_run=True)
        self.assertEqual((result.status, result.metrics), (automation.DRY_RUN, {"urls": 3}))
        self.assertEqual(seen, [True])
        self.assertFalse(AuditLogEntry.objects.exists())

    # ---- de-duplication / mutual exclusion ---------------------------------------------------------------------------------
    def test_the_same_key_never_runs_twice(self):
        calls = []
        first = self.run_op(lambda dry: calls.append(1) or {"n": 1}, key="run-1")
        second = self.run_op(lambda dry: calls.append(1), key="run-1")
        self.assertEqual((first.status, second.status, second.reason), (automation.DONE, automation.SKIPPED, "duplicate"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.run_op(lambda dry: {}, key="run-2").status, automation.DONE)

    def test_a_running_operation_blocks_a_second_one(self):
        cache.add(automation._lock_key("demo", self.store, "-"), 1, 60)
        fn = mock.Mock()
        self.assertEqual(self.run_op(fn).reason, "already_running")
        fn.assert_not_called()

    def test_the_lock_is_released_even_when_the_operation_fails(self):
        self.run_op(mock.Mock(side_effect=RuntimeError("boom")))
        self.assertTrue(cache.add(automation._lock_key("demo", self.store, "-"), 1, 5))

    # ---- retries ------------------------------------------------------------------------------------------------------------
    def test_transient_failures_are_retried_with_backoff_then_succeed(self):
        attempts, sleeps = [], []
        def fn(dry):
            attempts.append(1)
            if len(attempts) < 3:
                raise automation.TransientError("503")
            return {"ok": True}
        result = automation.run("demo", self.store, fn, host=PUBLIC, sleep=sleeps.append, backoff=2)
        self.assertEqual((result.status, result.attempts), (automation.DONE, 3))
        self.assertEqual(sleeps, [1, 2])

    def test_transient_failures_stop_after_the_bound_and_are_reported_as_failed(self):
        fn = mock.Mock(side_effect=automation.TransientError("timeout"))
        result = self.run_op(fn, attempts=99)
        self.assertEqual((result.status, result.reason), (automation.FAILED, "transient_exhausted"))
        self.assertEqual(fn.call_count, automation.MAX_ATTEMPTS)
        self.assertFalse(automation.last_result(self.store, "demo")["ok"])

    def test_permanent_failures_are_not_retried(self):
        fn = mock.Mock(side_effect=automation.PermanentError("key rejected"))
        result = self.run_op(fn)
        self.assertEqual((result.status, result.reason, fn.call_count), (automation.FAILED, "permanent", 1))

    def test_an_unexpected_error_never_escapes_or_reaches_the_log(self):
        with self.assertLogs("apps.core.automation", level="ERROR") as logs:
            result = self.run_op(mock.Mock(side_effect=ValueError("secret-token-123")))
        self.assertNotIn("secret-token-123", "\n".join(logs.output))
        self.assertEqual((result.status, result.reason), (automation.FAILED, "unexpected"))
        self.assertNotIn("secret-token-123", result.detail)            # only the exception class is kept, never its message

    # ---- the record ---------------------------------------------------------------------------------------------------------
    def test_the_real_outcome_is_recorded_redacted_and_store_scoped(self):
        self.run_op(lambda dry: {"submitted": 4, "token": "SUPERSECRET", "nested": {"api_key": "K"}})
        info = automation.last_result(self.store, "demo")
        self.assertTrue(info["ok"])
        self.assertEqual(info["metadata"]["metrics"]["submitted"], 4)
        flat = str(info["metadata"])
        self.assertNotIn("SUPERSECRET", flat)
        self.assertNotIn("'K'", flat)
        self.assertIsNone(automation.last_result(self.other, "demo"))
        self.assertIsNone(automation.last_result(self.store, "never-ran"))
