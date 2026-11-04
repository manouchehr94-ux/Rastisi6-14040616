"""Registry truth — verified by AST, not by searching for strings.

For every registered event type: its production chain (``producers.CHAINS``) must exist hop by hop — each function really calls the next callee — and the last hop must
publish with that very event key. Production-lifecycle types must also have a non-test entry caller; dormant ones must have none (so a silent change forces a review).
``payment.refund_failed`` stays PLANNED: neither refund domain has an authoritative producer of a definitive failure, and this guard fails if anyone wires one by accident."""

import ast
import importlib.util
import pathlib

from django.test import SimpleTestCase

from apps.notifications import producers as P
from apps.notifications import registry as R

ROOT = pathlib.Path(__file__).resolve().parents[3]
LIFECYCLES = {"production", "feature_flagged", "cron_dependent", "dormant", "test_only"}


def _tree(module):
    spec = importlib.util.find_spec(module)
    assert spec and spec.origin, module
    return ast.parse(pathlib.Path(spec.origin).read_text(encoding="utf-8"))


def _function(module, name):
    nodes = [n for n in ast.walk(_tree(module)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    return nodes[0] if nodes else None


def _called_names(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None))
    return names


def _strings(fn):
    return {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _production_files():
    return [p for p in (ROOT / "apps").rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts]


def _non_test_callers(callee, *, exclude_def=True):
    hits = []
    for path in _production_files():
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="ignore"))):
            if isinstance(fn, ast.FunctionDef) and fn.name != callee and callee in _called_names(fn):
                hits.append(f"{path.relative_to(ROOT)}::{fn.name}")
    return hits


class ProducerChainTests(SimpleTestCase):
    def test_every_registered_type_has_a_chain_and_every_chain_belongs_to_a_registered_type(self):
        self.assertEqual(set(P.CHAINS), set(R.EVENT_TYPES))

    def test_each_hop_really_calls_the_next_callee_and_the_last_hop_publishes_the_same_key(self):
        for key, hops in P.CHAINS.items():
            for module, function, callee in hops:
                fn = _function(module, function)
                self.assertIsNotNone(fn, f"{key}: {module}.{function} not found")
                self.assertIn(callee, _called_names(fn), f"{key}: {function} does not call {callee}")
            module, function, callee = hops[-1]
            self.assertIn(callee, ("safe_publish", "publish"), key)
            self.assertIn(key, _strings(_function(module, function)), f"{key}: {function} does not publish that event key")

    def test_production_entry_points_are_reachable_from_non_test_code(self):
        for key, entries in P.ENTRIES.items():
            ok = [e for e in entries if (fn := _function(e[0], e[1])) is not None and e[2] in _called_names(fn)]
            self.assertTrue(ok, f"{key}: no production caller found among {entries}")


class LifecycleClassificationTests(SimpleTestCase):
    def test_lifecycle_values_and_special_classes_are_explicit(self):
        for key, t in R.EVENT_TYPES.items():
            self.assertIn(t.lifecycle, LIFECYCLES, key)
        by = lambda lc: {k for k, t in R.EVENT_TYPES.items() if t.lifecycle == lc}
        self.assertEqual(by("test_only"), {"system.test", "platform.test"})
        self.assertEqual(by("dormant"), {"subscription.past_due"})
        self.assertEqual(by("feature_flagged"), {"integration.sync_failed"})
        self.assertEqual(by("cron_dependent"), {"platform.jobs_unhealthy"})

    def test_a_dormant_event_has_no_production_caller_so_a_new_caller_forces_a_reclassification(self):
        self.assertEqual(_non_test_callers("mark_past_due"), [], "mark_past_due now has a production caller — promote subscription.past_due to production")

    def test_feature_flagged_event_is_reachable_only_through_flag_gated_runners(self):
        callers = {c.split("::")[0] for c in _non_test_callers("run") if "automation" not in c}
        self.assertTrue(any("indexnow_sync" in c or "search_console" in c or "domain_autocheck" in c for c in callers))

    def test_planned_events_are_not_registered_and_no_production_code_publishes_them(self):
        self.assertFalse(set(R.PLANNED) & set(R.EVENT_TYPES))
        text = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in _production_files() if p.name != "registry.py")
        for key in R.PLANNED:
            self.assertNotIn(f'"{key}"', text, key)


class RefundFailureGuardTests(SimpleTestCase):
    """``payment.refund_failed`` must not be activated without a real, authoritative producer of a definitive failure."""

    def test_it_stays_planned_with_the_documented_dependency(self):
        self.assertIn("payment.refund_failed", R.PLANNED)
        self.assertNotIn("payment.refund_failed", R.EVENT_TYPES)
        self.assertIn("refund_service", R.PLANNED["payment.refund_failed"])

    def test_no_production_code_can_currently_produce_a_final_refund_failure(self):
        self.assertEqual([c for c in _non_test_callers("record_refund_result")], [], "record_refund_result gained a caller — review before enabling payment.refund_failed")
        offenders = []
        for path in _production_files():
            src = path.read_text(encoding="utf-8", errors="ignore")
            if "Status.FAILED" not in src or "Refund" not in src:
                continue
            for node in ast.walk(ast.parse(src)):
                text = ast.unparse(node) if isinstance(node, (ast.Assign, ast.Call)) else ""
                is_write = (isinstance(node, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == "status" for t in node.targets)) or (
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("create", "update", "update_or_create", "get_or_create")
                    and any(k.arg == "status" for k in node.keywords))
                if is_write and "Refund" in text and "Status.FAILED" in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {text[:90]}")
        self.assertEqual(offenders, [], "a refund FAILED assignment exists — review before enabling payment.refund_failed")

    def test_gateway_refund_execution_is_still_unsupported_and_orders_and_billing_stay_independent(self):
        order_src = (ROOT / "apps/orders/services/refund_service.py").read_text(encoding="utf-8")
        billing_src = (ROOT / "apps/billing/services/refund_service.py").read_text(encoding="utf-8")
        self.assertIn("هنوز پیاده‌سازی نشده", order_src)                      # GATEWAY refund raises RefundError
        self.assertNotIn("apps.billing", order_src)
        self.assertNotIn("apps.orders", billing_src)
        for prov in ("zibal", "manual"):
            body = (ROOT / f"apps/billing/providers/{prov}.py").read_text(encoding="utf-8")
            self.assertIn("succeeded=False", body)                            # unsupported capability ⇒ pending/manual, never FAILED
