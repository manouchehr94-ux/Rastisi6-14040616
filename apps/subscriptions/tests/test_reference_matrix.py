"""ماتریسِ ۷۶ ردیفِ مرجع در برابرِ کدِ واقعی: کامل بودن، مدرکِ موجود، تستِ رفتاری، سازگاری با کاتالوگِ عمومی و نبودِ drift در سند."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.subscriptions import feature_catalog as catalog
from apps.subscriptions import reference_matrix as rm
from apps.subscriptions.models import PricingFeature
from apps.subscriptions.services import pricing_page_service as page

ROOT = Path(settings.BASE_DIR)
DOC = ROOT / "docs" / "pricing" / "PRICING_REFERENCE_76_GAP_MATRIX_20261105.md"


class ReferenceMatrixIntegrityTests(TestCase):
    def test_all_76_reference_rows_are_present_once_in_their_seven_categories(self):
        self.assertEqual([r.n for r in rm.ROWS], list(range(1, 77)))
        for key, (_label, expected) in rm.REFERENCE_CATEGORIES.items():
            self.assertEqual(len([r for r in rm.ROWS if r.category == key]), expected, key)
        self.assertEqual(sum(c for _l, c in rm.REFERENCE_CATEGORIES.values()), 76)
        for r in rm.ROWS:
            self.assertTrue(r.title.strip(), r.n)
            self.assertIn(r.status, rm.STATUS_LABELS, r.n)
            self.assertIn(r.gating, ("plan", "all", "none"), r.n)

    def test_every_claimed_capability_has_existing_evidence_files_and_tests(self):
        for r in rm.ROWS:
            if r.status in (rm.IMPLEMENTED, rm.PARTIAL, rm.EXTERNAL) and r.catalog != "api":
                self.assertTrue(r.evidence, f"row {r.n}: claimed but no evidence")
            for path in r.evidence + r.tests:
                self.assertTrue((ROOT / path).exists(), f"row {r.n}: missing path {path}")
            if r.status == rm.IMPLEMENTED:
                self.assertTrue(r.tests, f"row {r.n}: Implemented without a behavioural test")
            if r.status in (rm.MISSING, rm.NA):
                self.assertEqual(r.gating, "none", r.n)

    def test_the_public_catalog_never_runs_ahead_of_the_audited_reality(self):
        by_key = {f.key: f for f in catalog.CATALOG}
        for r in rm.ROWS:
            if not r.catalog:
                continue
            self.assertIn(r.catalog, by_key, f"row {r.n}: unknown catalog key {r.catalog}")
            self.assertIn(by_key[r.catalog].availability, rm.ALLOWED_CATALOG_AVAILABILITY[r.status],
                          f"row {r.n} ({r.status}) is advertised as {by_key[r.catalog].availability}")
        self.assertEqual(by_key["redirects"].availability, catalog.PLANNED)           # the corrected, previously overstated row

    def test_plan_gated_rows_use_really_enforced_entitlements(self):
        by_key = {f.key: f for f in catalog.CATALOG}
        for r in rm.ROWS:
            if r.gating == "plan":
                feature = by_key[r.catalog]
                self.assertIn(feature.entitlement, catalog.ENFORCED_ENTITLEMENT_KEYS, r.n)
        for f in catalog.CATALOG:
            if f.entitlement:
                self.assertIn(f.entitlement, catalog.ENFORCED_ENTITLEMENT_KEYS, f.key)

    def test_missing_capabilities_never_reach_the_public_matrix(self):
        catalog.sync_feature_catalog()
        visible = {r["feature"].key for cat in page.build_pricing_page()["matrix"] for r in cat["rows"]}
        for key in visible:
            self.assertTrue(PricingFeature.objects.get(key=key).is_publishable, key)
        self.assertNotIn("api", visible)
        self.assertNotIn("redirects", visible)
        # structural guarantee: rows whose only reference rows are Missing/NA are planned (hence never publishable)
        keys_by_row = {}
        for r in rm.ROWS:
            if r.catalog:
                keys_by_row.setdefault(r.catalog, []).append(r.status)
        for key, statuses in keys_by_row.items():
            if set(statuses) == {rm.MISSING}:
                self.assertFalse(PricingFeature.objects.get(key=key).is_publishable, key)

    def test_the_gap_document_is_generated_from_this_data_and_cannot_drift(self):
        self.assertTrue(DOC.exists(), "run: python manage.py shell -c 'from apps.subscriptions import reference_matrix as m; open(path,\"w\").write(m.render_markdown())'")
        self.assertEqual(DOC.read_text(encoding="utf-8"), rm.render_markdown())

    def test_status_counts_are_consistent(self):
        counts = {k: len(v) for k, v in rm.by_status().items()}
        self.assertEqual(sum(counts.values()), 76)
        self.assertEqual(counts[rm.NA], 11)                  # domain registration, bespoke template, rival panel + 8 human services
