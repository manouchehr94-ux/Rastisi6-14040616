#!/usr/bin/env python3
"""Run a tier of the Django test suite and apply the quality policy (standard library only).

    test_gate.py --tier fast [--parallel 4] [--registry tools/ci/known_failures.json] [--today 2026-11-12] [-- extra manage.py test args]

Policy (see known_failures.json):
  * every test of the tier RUNS, always; nothing is skipped or filtered out to get a green build;
  * a failure or error that is not in the registry fails the gate;
  * a registered test that now PASSES fails the gate (the entry is stale: remove it, so the fix is locked in);
  * a registry entry past its 'expires' date fails the gate (a tolerated defect needs a fresh, explicit decision);
  * a tier that ran zero tests, or crashed before finishing (no 'Ran N tests' line), fails the gate;
  * tolerated failures are still printed on every run, with their root cause.

Tiers are defined in tiers.json: Django test labels, the database they need, and what they protect.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAIL_LINE = re.compile(r"^(FAIL|ERROR): (\S+) \(([\w.]+)\)")
RAN_LINE = re.compile(r"^Ran (\d+) tests? in ")
SUMMARY = re.compile(r"^(OK|FAILED)(?: \((.*)\))?$")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_labels(tier, root="."):
    """Required labels plus the optional ones whose module/package exists in this checkout."""
    labels = list(tier["labels"])
    for label in tier.get("optional_labels", []):
        path = Path(root, *label.split("."))
        if path.with_suffix(".py").exists() or path.is_dir():
            labels.append(label)
    return labels


def parse_output(text):
    """Return (ran, failing_ids, summary_seen). Failing ids are 'module.Class.method' (subtests collapse to their parent test)."""
    ran, failing, summary = None, set(), False
    for line in text.splitlines():
        m = FAIL_LINE.match(line)
        if m:
            method, dotted = m.group(2), m.group(3)
            # Django prints "ERROR: setUpClass (module.Class)" and "FAIL: method (module.Class.method)"
            failing.add(dotted if dotted.endswith("." + method) else "%s.%s" % (dotted, method))
            continue
        m = RAN_LINE.match(line)
        if m:
            ran = int(m.group(1))
        if SUMMARY.match(line):
            summary = True
    return ran, failing, summary


def judge(failing, registry, tier, today):
    """Pure decision function (unit-tested). Returns (problems, tolerated)."""
    entries = {e["id"]: e for e in registry.get("entries", []) if tier in e.get("tiers", [])}
    problems, tolerated = [], []
    for test in sorted(failing):
        if test in entries:
            tolerated.append(entries[test])
        else:
            problems.append("UNEXPECTED FAILURE: %s" % test)
    for tid, entry in sorted(entries.items()):
        expires = datetime.date.fromisoformat(entry["expires"])
        if expires < today:
            problems.append("EXPIRED known failure (%s, expired %s, owner %s): %s" % (entry["kind"], entry["expires"], entry["owner"], tid))
        if tid not in failing:
            problems.append("STALE registry entry: %s now passes (or did not run). Remove it from known_failures.json." % tid)
    return problems, tolerated


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True)
    ap.add_argument("--tiers", default=str(HERE / "tiers.json"))
    ap.add_argument("--registry", default=str(HERE / "known_failures.json"))
    ap.add_argument("--parallel", type=int, default=0)
    ap.add_argument("--today", default="")
    ap.add_argument("--manage", default="manage.py")
    ap.add_argument("--output", default="", help="write the raw test output here (uploaded as a CI artifact)")
    ap.add_argument("--from-file", default="", help="judge an existing output file instead of running (used by the unit tests)")
    ap.add_argument("extra", nargs="*")
    args = ap.parse_args(argv)
    tiers = load(args.tiers)
    if args.tier not in tiers:
        print("unknown tier %r (known: %s)" % (args.tier, ", ".join(sorted(k for k in tiers if not k.startswith("_")))))
        return 2
    tier = tiers[args.tier]
    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    if args.from_file:
        text = Path(args.from_file).read_text(encoding="utf-8")
    else:
        cmd = [sys.executable, args.manage, "test"] + resolve_labels(tier, str(Path(args.manage).resolve().parent)) + ["--noinput"] + args.extra
        if args.parallel:
            cmd += ["--parallel", str(args.parallel)]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
        text = proc.stdout + "\n" + proc.stderr
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
    ran, failing, summary_seen = parse_output(text)
    problems, tolerated = judge(failing, load(args.registry), args.tier, today)
    if ran is None or not summary_seen:
        problems.append("the test run did not finish (no summary line): treat as a failed build")
    elif ran < tier.get("min_tests", 1):
        problems.append("only %d tests ran; the tier '%s' must run at least %d" % (ran, args.tier, tier.get("min_tests", 1)))
    print("tier %s: %s tests ran, %d failing, %d tolerated" % (args.tier, ran, len(failing), len(tolerated)))
    for entry in tolerated:
        print("  TOLERATED until %s (%s): %s\n      cause: %s" % (entry["expires"], entry["owner"], entry["id"], entry["root_cause"][:200]))
    for p in problems:
        print("  PROBLEM:", p)
    if problems:
        tail = [l for l in text.splitlines() if l.startswith(("FAIL:", "ERROR:"))][:20]
        print("\n".join(tail))
        return 1
    print("gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
