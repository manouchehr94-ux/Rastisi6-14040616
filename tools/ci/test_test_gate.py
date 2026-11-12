"""The test-quality gate's decisions, from canned Django output (no Django needed)."""

import datetime
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gate as G  # noqa: E402

TODAY = datetime.date(2026, 11, 12)
KNOWN = "apps.portal.tests.test_seo.PublicPageIndexabilityTests.test_terms_and_privacy_are_indexable"
REGISTRY = {"entries": [{"id": KNOWN, "tiers": ["fast"], "kind": "k", "owner": "o", "expires": "2026-12-15", "root_cause": "because"}]}

OUT_KNOWN_ONLY = """..F....
======================================================================
FAIL: test_terms_and_privacy_are_indexable (apps.portal.tests.test_seo.PublicPageIndexabilityTests.test_terms_and_privacy_are_indexable)
----------------------------------------------------------------------
Ran 2052 tests in 100.0s

FAILED (failures=1, skipped=68)
"""


class ParseTests(unittest.TestCase):
    def test_parses_failures_errors_setupclass_and_subtests(self):
        text = ("ERROR: setUpClass (apps.sms.tests.test_gateway_live.LiveProtocolTests)\n"
                "FAIL: test_a (apps.x.tests.T.test_a) (label='x')\n"
                "FAIL: test_a (apps.x.tests.T.test_a) (label='y')\n"
                "ERROR: test_b (apps.x.tests.T.test_b)\nRan 10 tests in 1s\n\nFAILED (failures=2, errors=2)\n")
        ran, failing, summary = G.parse_output(text)
        self.assertEqual(ran, 10)
        self.assertTrue(summary)
        self.assertEqual(failing, {"apps.sms.tests.test_gateway_live.LiveProtocolTests.setUpClass", "apps.x.tests.T.test_a", "apps.x.tests.T.test_b"})

    def test_a_crashed_run_has_no_summary(self):
        ran, failing, summary = G.parse_output("Traceback (most recent call last):\nTypeError: cannot pickle 'traceback' object\n")
        self.assertEqual((ran, summary), (None, False))


class JudgeTests(unittest.TestCase):
    def test_only_the_registered_failure_is_tolerated(self):
        problems, tolerated = G.judge({KNOWN}, REGISTRY, "fast", TODAY)
        self.assertEqual((problems, len(tolerated)), ([], 1))

    def test_an_unregistered_failure_fails_the_gate(self):
        problems, _ = G.judge({KNOWN, "apps.billing.tests.test_x.T.test_y"}, REGISTRY, "fast", TODAY)
        self.assertEqual(problems, ["UNEXPECTED FAILURE: apps.billing.tests.test_x.T.test_y"])

    def test_a_registered_test_that_now_passes_fails_the_gate_so_the_fix_is_locked_in(self):
        problems, _ = G.judge(set(), REGISTRY, "fast", TODAY)
        self.assertTrue(problems[0].startswith("STALE registry entry"))

    def test_an_expired_entry_fails_the_gate_even_if_the_test_still_fails(self):
        problems, _ = G.judge({KNOWN}, REGISTRY, "fast", datetime.date(2026, 12, 16))
        self.assertTrue(problems[0].startswith("EXPIRED known failure"))
        self.assertIn("owner o", problems[0])

    def test_the_last_valid_day_still_passes(self):
        self.assertEqual(G.judge({KNOWN}, REGISTRY, "fast", datetime.date(2026, 12, 15))[0], [])

    def test_entries_apply_only_to_their_tier(self):
        problems, tolerated = G.judge({KNOWN}, REGISTRY, "tenant", TODAY)
        self.assertEqual((len(tolerated), problems), (0, ["UNEXPECTED FAILURE: " + KNOWN]))


class EndToEndTests(unittest.TestCase):
    def run_gate(self, text, today="2026-11-12", min_tests=1000, tier_name="fast"):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(d)]))
        (d / "out.txt").write_text(text)
        (d / "tiers.json").write_text(json.dumps({"fast": {"labels": ["x"], "min_tests": min_tests}}))
        (d / "reg.json").write_text(json.dumps(REGISTRY))
        proc = subprocess.run([sys.executable, str(Path(G.__file__)), "--tier", tier_name, "--tiers", str(d / "tiers.json"), "--registry", str(d / "reg.json"),
                               "--from-file", str(d / "out.txt"), "--today", today], capture_output=True, text=True)
        return proc.returncode, proc.stdout

    def test_known_failure_only_passes_and_is_still_reported(self):
        code, out = self.run_gate(OUT_KNOWN_ONLY)
        self.assertEqual(code, 0, out)
        self.assertIn("TOLERATED until 2026-12-15", out)
        self.assertIn("gate passed", out)

    def test_a_tier_that_lost_its_tests_fails(self):
        code, out = self.run_gate(OUT_KNOWN_ONLY.replace("Ran 2052", "Ran 12"), min_tests=1000)
        self.assertEqual(code, 1)
        self.assertIn("only 12 tests ran", out)

    def test_a_crash_fails(self):
        code, out = self.run_gate("Traceback (most recent call last):\nboom\n")
        self.assertEqual(code, 1)
        self.assertIn("did not finish", out)

    def test_a_clean_run_with_a_stale_entry_fails(self):
        code, out = self.run_gate("Ran 2052 tests in 1s\n\nOK (skipped=3)\n")
        self.assertEqual(code, 1)
        self.assertIn("STALE", out)

    def test_unknown_tier(self):
        code, _ = self.run_gate("", tier_name="nope")
        self.assertEqual(code, 2)


class RegistryHygieneTests(unittest.TestCase):
    def test_the_shipped_registry_is_well_formed(self):
        reg = json.loads((Path(G.__file__).parent / "known_failures.json").read_text(encoding="utf-8"))
        tiers = json.loads((Path(G.__file__).parent / "tiers.json").read_text(encoding="utf-8"))
        for e in reg["entries"]:
            for key in ("id", "tiers", "kind", "root_cause", "resolution", "owner", "since", "expires"):
                self.assertTrue(e.get(key), "%s missing %s" % (e.get("id"), key))
            self.assertTrue(set(e["tiers"]) <= set(tiers))
            self.assertLessEqual((datetime.date.fromisoformat(e["expires"]) - datetime.date.fromisoformat(e["since"])).days, 60,
                                 "a tolerated defect may not be accepted for more than 60 days at a time")


if __name__ == "__main__":
    unittest.main(verbosity=2)
