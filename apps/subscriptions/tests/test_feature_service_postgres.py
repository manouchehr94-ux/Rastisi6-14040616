"""PostgreSQL regression: ``select_for_update()`` must never lock the nullable side of an outer join.

``PricingFeature.entitlement`` is a nullable FK, so ``select_related("entitlement")`` becomes a LEFT OUTER JOIN and PostgreSQL rejects
``SELECT ... FOR UPDATE`` on it (``NotSupportedError``). SQLite ignores row locks, so the defect was invisible there. The fix locks only
the feature row: ``select_related(...).select_for_update(of=("self",))``.

* ``LockingQueryContractTests`` runs on every database (static guard over the service modules).
* ``FeatureTransitionsOnPostgresTests`` runs only on PostgreSQL (both affected operations + the emitted SQL)."""

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from apps.subscriptions import capability_registry as registry
from apps.subscriptions.models import PricingFeature
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import feature_service as fs

SERVICES = Path(__file__).resolve().parents[1] / "services"


class LockingQueryContractTests(SimpleTestCase):
    def test_no_service_locks_a_row_while_joining_through_select_related_without_of(self):
        offenders = []
        for path in SERVICES.glob("*.py"):
            text = path.read_text()
            for m in re.finditer(r"\.select_for_update\(([^)]*)\)", text):
                statement = text[max(0, text.rfind("\n", 0, m.start())):text.find("\n", m.end())]
                if "select_related(" in statement and "of=" not in m.group(1):
                    offenders.append(f"{path.name}: {statement.strip()[:110]}")
        self.assertEqual(offenders, [], "select_for_update() + select_related() must restrict the lock with of=('self',)")


class FeatureTransitionsOnPostgresTests(TestCase):
    KEY = "pg.regression"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            from unittest import SkipTest

            raise SkipTest("PostgreSQL-only regression (SQLite ignores row locks)")

    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="pg-owner@example.com", password="a-very-strong-pass-1", is_staff=True)
        self.feature = fs.create_feature(actor=self.owner, key="pg_regression", title="قابلیتِ آزمون", category="marketing", entitlement_key=self.KEY)
        self.capability = registry.Capability(key=self.KEY, enforced_by="test double", tests=("test_feature_service_postgres",))

    def test_set_technical_status_locks_only_the_feature_row_and_keeps_readiness_rules(self):
        with self.assertRaises(fs.FeatureError):
            fs.set_technical_status(actor=self.owner, feature=self.feature, status="ready")      # unregistered key: still refused on PG
        with registry.registered_for_test(self.capability):
            with CaptureQueriesContext(connection) as queries:
                fs.set_technical_status(actor=self.owner, feature=self.feature, status="ready")
            locking = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
            self.assertTrue(locking, "the feature row must be locked")
            self.assertTrue(all('FOR UPDATE OF "subscriptions_pricingfeature"' in sql for sql in locking), locking)
            feature = PricingFeature.objects.get(pk=self.feature.pk)
            self.assertEqual(feature.technical_status, "ready")
            self.assertFalse(feature.grants_access)          # technically ready ≠ commercially available

    def test_set_commercial_status_locks_only_the_feature_row_and_preserves_the_access_gate(self):
        with registry.registered_for_test(self.capability):
            fs.set_technical_status(actor=self.owner, feature=self.feature, status="ready")
            with CaptureQueriesContext(connection) as queries:
                fs.set_commercial_status(actor=self.owner, feature=self.feature, status="available")
            self.assertTrue(all('FOR UPDATE OF "subscriptions_pricingfeature"' in q["sql"] for q in queries if "FOR UPDATE" in q["sql"]))
            feature = PricingFeature.objects.get(pk=self.feature.pk)
            self.assertEqual((feature.commercial_status, feature.public_state), ("available", "available"))
            self.assertIsNotNone(feature.activated_at)
            self.assertTrue(feature.grants_access)
            ent.clear_entitlement_cache()
            with self.assertRaises(fs.FeatureError):          # no silent rollback to "coming soon"
                fs.set_commercial_status(actor=self.owner, feature=self.feature, status="coming_soon")

    def test_the_other_audited_feature_operations_also_work_on_postgresql(self):
        fs.update_feature(actor=self.owner, feature=self.feature, title="عنوانِ تازه")
        fs.set_kill_switch(actor=self.owner, feature=self.feature, on=True, reason="incident")
        fs.set_kill_switch(actor=self.owner, feature=self.feature, on=False)
        self.assertEqual(PricingFeature.objects.get(pk=self.feature.pk).title, "عنوانِ تازه")
