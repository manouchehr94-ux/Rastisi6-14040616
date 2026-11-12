"""The dependency-audit decisions (pure logic, canned pip-audit reports)."""

import datetime
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_policy as A  # noqa: E402

TODAY = datetime.date(2026, 11, 12)
EXC = {"exceptions": [{"package": "Pillow", "version": "12.3.0", "advisories": ["CVE-1", "CVE-2"], "owner": "o", "reason": "r", "expires": "2026-12-12"}]}


for entry in EXC['exceptions']:
    entry['security_review'] = {'approved': True, 'evidence': 'unit-test fixture only'}

def report(*vulns):
    deps = {}
    for name, version, vid in vulns:
        deps.setdefault((name, version), []).append({"id": vid, "fix_versions": ["13.0.0"], "aliases": []})
    return {"dependencies": [{"name": n, "version": v, "vulns": vs} for (n, v), vs in deps.items()] + [{"name": "django", "version": "5.2", "vulns": []}]}


class JudgeTests(unittest.TestCase):
    def test_listed_advisories_are_tolerated(self):
        problems, tolerated = A.judge(A.findings(report(("pillow", "12.3.0", "CVE-1"), ("pillow", "12.3.0", "CVE-2"))), EXC, TODAY)
        self.assertEqual((problems, len(tolerated)), ([], 2))

    def test_unreviewed_exception_blocks_even_when_id_matches(self):
        import copy
        exc = copy.deepcopy(EXC)
        for item in exc['exceptions']:
            item.pop('security_review', None)
        problems, tolerated = A.judge(A.findings(report(('pillow', '12.3.0', 'CVE-1'), ('pillow', '12.3.0', 'CVE-2'))), exc, TODAY)
        self.assertEqual(tolerated, [])
        self.assertTrue(all('UNREVIEWED' in p for p in problems))

    def test_a_new_advisory_fails(self):
        problems, _ = A.judge(A.findings(report(("pillow", "12.3.0", "CVE-1"), ("pillow", "12.3.0", "CVE-2"), ("pillow", "12.3.0", "CVE-9"))), EXC, TODAY)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("NEW advisory CVE-9"))

    def test_a_new_package_fails(self):
        problems, _ = A.judge(A.findings(report(("requests", "2.34.0", "CVE-5"))), {"exceptions": []}, TODAY)
        self.assertTrue(problems[0].startswith("NEW advisory"))

    def test_expired_exception_fails(self):
        problems, _ = A.judge(A.findings(report(("pillow", "12.3.0", "CVE-1"), ("pillow", "12.3.0", "CVE-2"))), EXC, datetime.date(2026, 12, 13))
        self.assertTrue(all(p.startswith("EXPIRED") for p in problems) and len(problems) == 2)

    def test_a_different_installed_version_needs_a_new_review(self):
        problems, _ = A.judge(A.findings(report(("pillow", "12.4.0", "CVE-1"), ("pillow", "12.4.0", "CVE-2"))), EXC, TODAY)
        self.assertIn("re-review", problems[0])

    def test_an_exception_for_a_fixed_package_is_stale_and_fails(self):
        problems, _ = A.judge(A.findings(report()), EXC, TODAY)
        self.assertEqual(len(problems), 2)
        self.assertTrue(all(p.startswith("STALE exception") for p in problems))


class ShippedExceptionsTests(unittest.TestCase):
    def test_well_formed_and_short_lived(self):
        d = json.loads((Path(A.__file__).parent / "audit_exceptions.json").read_text())
        for e in d["exceptions"]:
            for key in ("package", "version", "advisories", "owner", "reason", "expires", "fixed_in"):
                self.assertTrue(e.get(key), key)
            self.assertNotIn("TODO", e["owner"] + e["reason"])
            self.assertLessEqual((datetime.date.fromisoformat(e["expires"]) - datetime.date(2026, 11, 12)).days, 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
