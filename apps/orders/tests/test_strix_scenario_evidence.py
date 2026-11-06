"""Evidence recorder for the three historical external-audit ("Strix") scenarios (FV3, 2026-11-06).

The original harness test ids do not exist in this repository, so each scenario is REBUILT from its description (same user + two stores; the same
client-supplied refund key used by two stores). This module is a *recording* variant of ``test_tenant_isolation_regression``: it asserts the same
contracts, and — when ``STRIX_EVIDENCE_DIR`` is set — also writes machine-readable evidence (fixtures, every HTTP request/response summary, DB side effects,
PostgreSQL backend pids of the concurrent workers) to ``<dir>/strix_evidence_<engine>.json``.

What this proves: on the fixture below, in THIS code, the cross-tenant outcomes are as recorded. What it does NOT prove: absence of other cross-tenant
paths, production-data behaviour, or behaviour under a different proxy/host configuration. Run against the pre-fix refund code it FAILS (see the
evidence document) — that is the demonstration that the test reproduces the historical scenario.
"""

import atexit
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse

from apps.orders.models import Order, Refund
from apps.orders.services.refund_service import RefundError, execute_order_refund
from apps.orders.tests import test_tenant_isolation_regression as base

EVIDENCE: list[dict] = []
ENGINE = connection.vendor


def rec(scenario, step, **data):
    EVIDENCE.append({"scenario": scenario, "step": step, **data})


def _flush():
    directory = os.environ.get("STRIX_EVIDENCE_DIR")
    if directory and EVIDENCE:
        Path(directory).mkdir(parents=True, exist_ok=True)
        path = Path(directory) / f"strix_evidence_{ENGINE}_{os.environ.get('STRIX_LABEL', 'run')}.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        path.write_text(json.dumps(existing + EVIDENCE, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


atexit.register(_flush)


def http_summary(response, *, secrets):
    body = response.content.decode("utf-8", "replace")
    return {
        "status": response.status_code, "content_length": len(body), "body_sha256": hashlib.sha256(response.content).hexdigest()[:16],
        "is_generic_not_found": "صفحه پیدا نشد" in body,
        "leaks": {name: (needle in body.replace("/checkout/order/TI-A-1/", "")) for name, needle in secrets.items()},
        "location": response.headers.get("Location", ""),
    }


SECRETS = {"order_code": "TI-A-1", "amount_plain": base.SECRET_AMOUNT_A, "amount_fa": "۷٬۶۵۴٬۳۲۱", "customer_name": "مشتریِ مشترک"}


class FixtureRecordingMixin:
    def record_fixture(self, scenario):
        rec(scenario, "fixture", stores={t: {"pk": v["store"].pk, "slug": v["store"].slug, "host": v["host"]} for t, v in self.t.items()},
            orders={t: {"code": v["order"].code, "store_id": v["order"].store_id, "customer_id": v["order"].customer_id,
                        "grand_total": str(v["order"].grand_total), "payment_status": v["order"].payment_status} for t, v in self.t.items()},
            users={"shared_customer_user": self.user.pk, "stranger": self.stranger.pk, "staff": self.staff.pk},
            note="SAME global Customer owns an order in Store A and one in Store B; each store has its own host.")


class StrixScenario2SameUserDifferentStoreHttp(FixtureRecordingMixin, base.TenantFixture):
    """http_payment_result_other_store_same_user — the exact scenario: user U owns an order in A; U is logged in on B's host and asks for A's order."""

    def test_same_user_other_store_host_for_every_payment_view_and_the_controls(self):
        self.record_fixture("payment_result_same_user_other_store")
        snapshot = {o.code: (o.payment_status, o.status, str(o.grand_total)) for o in Order.objects.all()}
        self.client.force_login(self.user)
        for name in ("orders:payment-result", "orders:payment-start", "orders:payment-initiate"):
            session_before = sorted(self.client.session.keys())
            response = self.client.get(reverse(name, kwargs={"code": "TI-A-1"}), HTTP_HOST=base.HOST_B)
            summary = http_summary(response, secrets=SECRETS)
            rec("payment_result_same_user_other_store", "request", view=name, requested_host=base.HOST_B, acting_user="shared_customer_user", **summary,
                session_keys_changed=sorted(self.client.session.keys()) != session_before)
            self.assertEqual(summary["status"], 404, name)
            self.assertTrue(summary["is_generic_not_found"])
            self.assertFalse(any(summary["leaks"].values()), summary["leaks"])
        # controls: wrong user on the right host, anonymous, and the positive control (owner on own host)
        self.client.force_login(self.stranger)
        stranger = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=base.HOST_A)
        self.client.logout()
        anon = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=base.HOST_A)
        self.client.force_login(self.user)
        owner = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=base.HOST_A)
        for label, response, expect in (("other_user_right_host", stranger, 404), ("anonymous_right_host", anon, 404), ("owner_own_host_POSITIVE_CONTROL", owner, 200)):
            summary = http_summary(response, secrets=SECRETS)
            rec("payment_result_same_user_other_store", "control", case=label, **summary)
            self.assertEqual(summary["status"], expect, label)
        after = {o.code: (o.payment_status, o.status, str(o.grand_total)) for o in Order.objects.all()}
        rec("payment_result_same_user_other_store", "side_effects", orders_before=snapshot, orders_after=after, unchanged=snapshot == after)
        self.assertEqual(snapshot, after)


class StrixScenario3RefundKeyAcrossStores(FixtureRecordingMixin, base.TenantFixture):
    """refund_idempotency_cross_tenant — the exact scenario: Store A uses client key K; Store B uses the SAME key K for its own order."""

    KEY = "strix-shared-key-0001"

    def refund(self, tag, qty=1):
        order = self.t[tag]["order"]
        return execute_order_refund(order, store=self.t[tag]["store"], actor=self.staff,
                                    line_requests=[{"order_item_id": order.items.get().pk, "quantity": qty}], idempotency_key=self.KEY)

    def test_store_b_reusing_store_a_key(self):
        self.record_fixture("refund_idempotency_cross_store")
        constraints = {name: {"columns": c["columns"], "unique": c["unique"]} for name, c in
                       connection.introspection.get_constraints(connection.cursor(), Refund._meta.db_table).items() if "idempot" in name}
        rec("refund_idempotency_cross_store", "db_constraint", constraints=constraints)
        first = self.refund("a")
        a_before = {f: str(getattr(first, f)) for f in ("pk", "status", "approved_amount", "store_id", "order_id", "idempotency_key")}
        rec("refund_idempotency_cross_store", "store_a_refund_created", refund=a_before)
        try:
            second = self.refund("b")
            outcome = {"result": "independent_refund", "pk": second.pk, "store_id": second.store_id, "order_id": second.order_id}
        except RefundError as exc:
            second, outcome = None, {"result": "RefundError (collision / existence oracle)", "message": str(exc)}
        rec("refund_idempotency_cross_store", "store_b_reuses_key", outcome=outcome)
        first.refresh_from_db()
        a_after = {f: str(getattr(first, f)) for f in a_before}
        rows = {"store_a": Refund.objects.filter(store=self.a).count(), "store_b": Refund.objects.filter(store=self.b).count()}
        rec("refund_idempotency_cross_store", "side_effects", store_a_refund_unchanged=a_after == a_before, refund_rows=rows,
            store_b_order_payment_status=Order.objects.get(code="TI-B-1").payment_status)
        # contract of the fix: B gets ITS OWN refund (no error, no oracle); A's refund is never read, returned or altered
        self.assertIsNotNone(second, f"Store B was refused because Store A used the same key — cross-tenant collision / existence oracle: {outcome}")
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(second.store_id, self.b.pk)
        self.assertEqual(a_after, a_before)
        self.assertEqual(rows, {"store_a": 1, "store_b": 1})
        # idempotent retries inside each store keep working
        self.assertEqual(self.refund("b").pk, second.pk)
        self.assertEqual(self.refund("a").pk, first.pk)
        with self.assertRaises(RefundError):                       # same store + same key + a DIFFERENT request is still refused
            self.refund("a", qty=2)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL (real concurrent transactions)")
class StrixScenario3ConcurrentPostgres(base.RefundIdempotencyConcurrencyAcrossTenantsTests):
    """The same key used concurrently — two stores (must both succeed, independently) and one store ×3 (exactly one refund) — with the PostgreSQL backend pid
    of every worker recorded to show the workers really ran on separate connections/transactions."""

    def _run(self, tags, key="conc-shared-key"):
        barrier = threading.Barrier(len(tags))
        started = time.perf_counter()

        def worker(tag):
            close_old_connections()
            store, order, item = self.stores[tag]
            try:
                with connection.cursor() as cursor:
                    cursor.execute("select pg_backend_pid()")
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=15)
                t0 = round(time.perf_counter() - started, 4)
                try:
                    refund = execute_order_refund(order, store=store, actor=self.staff, line_requests=[{"order_item_id": item.pk, "quantity": 1}], idempotency_key=key)
                    result = ("ok", refund.pk, refund.store_id)
                except RefundError as exc:
                    result = ("refund_error", str(exc), None)
                rec("refund_idempotency_concurrent_postgres", "worker", tag=tag, pg_backend_pid=pid, released_at_s=t0,
                    finished_at_s=round(time.perf_counter() - started, 4), result=list(result))
                return result
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(tags)) as pool:
            results = list(pool.map(worker, tags))
        pids = {e["pg_backend_pid"] for e in EVIDENCE[-len(tags):] if e["scenario"] == "refund_idempotency_concurrent_postgres"}
        rec("refund_idempotency_concurrent_postgres", "summary", tags=tags, distinct_pg_backends=len(pids), db_rows={
            "store_a": Refund.objects.filter(store=self.stores["a"][0]).count(), "store_b": Refund.objects.filter(store=self.stores["b"][0]).count()})
        self.assertEqual(len(pids), len(tags), "workers did not run on distinct PostgreSQL connections")
        return results
