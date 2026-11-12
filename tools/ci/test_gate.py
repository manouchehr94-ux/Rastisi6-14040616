#!/usr/bin/env python3
"""Run a tier of the Django test suite and apply the quality policy (standard library only).

    test_gate.py --tier fast [--parallel 4] [--registry tools/ci/known_failures.json] [--today 2026-11-12] [-- extra manage.py test args]

Policy (see known_failures.json):
  * every test of the tier RUNS, always; nothing is skipped or filtered out to get a green build;
  * a failure or error that is not in the registry fails the gate;
  * a registered test that now PASSES fails the gate (the entry is stale: remove it, so the fix is locked in);
  * a registry entry past its 'expires' date fails the gate (a tolerated defect needs a fresh, explicit decision);
  * a tier that ran zero tests, or crashed before finishing (no 'Ran N tests' line), fails the gate;
  * a failing test that is on the FLAKY allow-list (flaky_tests.json: wall-clock timing tests, with owner, reason and expiry) is re-run once,
    alone and serially; if it passes it is reported as FLAKY and does not block, if it fails again it blocks. A test that is not on the
    list or without an exact reviewed diagnostic signature is never retried: an intermittent failure of a concurrency or data test is a hard failure;
  * tolerated and flaky tests are printed on every run, with their cause.

Tiers are defined in tiers.json: Django test labels, the database they need, and what they protect.
"""

import argparse
import hashlib
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


def failure_signatures(text):
    """Hash each failure's complete diagnostic, not just its test identifier.

    Keep assertion text, source location and exception type. Only checkout/venv
    prefixes and trailing whitespace are normalised for different runners.
    Multiple subtest diagnostics must ALL match the reviewed signatures.
    """
    blocks, current, body = {}, None, []
    def finish():
        if current is not None:
            diagnostic = '\n'.join(line.rstrip() for line in body).strip()
            diagnostic = re.sub(r'File "[^"\n]*?/(apps|shop_core)/', r'File "\1/', diagnostic)
            diagnostic = re.sub(r'File "[^"\n]*/site-packages/', 'File "site-packages/', diagnostic)
            digest = hashlib.sha256(diagnostic.encode()).hexdigest()
            blocks.setdefault(current, []).append(digest)
    for line in text.splitlines():
        match = FAIL_LINE.match(line)
        if match:
            finish()
            method, dotted = match.group(2), match.group(3)
            current = dotted if dotted.endswith('.' + method) else dotted + '.' + method
            body = [line]
        elif re.match(r'^=+$', line) or RAN_LINE.match(line):
            finish()
            current, body = None, []
        elif current is not None and not re.match(r'^-+$', line):
            body.append(line)
    finish()
    return {key: sorted(set(value)) for key, value in blocks.items()}


def judge(failing, registry, tier, today, signatures=None):
    """Pure decision function (unit-tested). Returns (problems, tolerated)."""
    entries = {e["id"]: e for e in registry.get("entries", []) if tier in e.get("tiers", [])}
    problems, tolerated = [], []
    for test in sorted(failing):
        if test in entries:
            if entries[test].get("release_blocker"):
                problems.append("RELEASE BLOCKER: %s: %s" % (test, entries[test]["root_cause"]))
                continue
            expected = entries[test].get("expected_failure_sha256", [])
            actual = (signatures or {}).get(test, [])
            if not expected or not actual or set(actual) != set(expected):
                problems.append("CHANGED OR UNREVIEWED FAILURE: %s (diagnostic SHA256 %s)" % (test, actual))
            else:
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


def split_flaky(failing, flaky_registry, tier, today, signatures=None):
    """Pure (unit-tested): returns (still_failing, flaky_candidates, problems). Expired flaky entries are not honoured and are reported."""
    entries = {e["id"]: e for e in flaky_registry.get("entries", []) if tier in e.get("tiers", [])}
    problems, candidates, rest = [], {}, set()
    for test in failing:
        entry = entries.get(test)
        if entry is None:
            rest.add(test)
        elif datetime.date.fromisoformat(entry["expires"]) < today:
            problems.append("EXPIRED flaky-test entry (owner %s): %s" % (entry["owner"], test))
            rest.add(test)
        elif not entry.get('expected_failure_sha256') or set((signatures or {}).get(test, [])) != set(entry['expected_failure_sha256']):
            problems.append('CHANGED OR UNREVIEWED FLAKY FAILURE: %s' % test)
            rest.add(test)
        else:
            candidates[test] = entry
    return rest, candidates, problems


def rerun_alone(manage, test_id):
    """Run ONE test serially in a fresh process. True when it passes."""
    proc = subprocess.run([sys.executable, manage, "test", test_id, "--noinput"], capture_output=True, text=True, env=dict(os.environ))
    return proc.returncode == 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True)
    ap.add_argument("--tiers", default=str(HERE / "tiers.json"))
    ap.add_argument("--registry", default=str(HERE / "known_failures.json"))
    ap.add_argument("--flaky", default=str(HERE / "flaky_tests.json"))
    ap.add_argument("--rerun-result", default="", help="unit tests: 'pass' or 'fail' instead of really re-running the flaky candidates")
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
    process_code = None
    if args.from_file:
        text = Path(args.from_file).read_text(encoding="utf-8")
    else:
        cmd = [sys.executable, args.manage, "test"] + resolve_labels(tier, str(Path(args.manage).resolve().parent)) + ["--noinput"] + args.extra
        if args.parallel:
            cmd += ["--parallel", str(args.parallel)]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
        process_code = proc.returncode
        text = proc.stdout + "\n" + proc.stderr
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
    ran, failing, summary_seen = parse_output(text)
    still_failing, flaky_candidates, flaky_problems = split_flaky(failing, load(args.flaky) if Path(args.flaky).exists() else {}, args.tier, today, failure_signatures(text))
    flaky_passed = []
    for test_id, entry in sorted(flaky_candidates.items()):
        if args.rerun_result:
            passed = args.rerun_result == "pass"
        else:
            passed = rerun_alone(args.manage, test_id)
        if passed:
            flaky_passed.append((test_id, entry))
        else:
            still_failing.add(test_id)
    problems, tolerated = judge(still_failing, load(args.registry), args.tier, today, failure_signatures(text))
    problems = flaky_problems + problems
    if process_code not in (None, 0, 1):
        problems.append("test process exited abnormally: %s" % process_code)
    if process_code == 1 and not failing:
        problems.append("test process failed without parsed failure diagnostics")
    if ran is None or not summary_seen:
        problems.append("the test run did not finish (no summary line): treat as a failed build")
    elif ran < tier.get("min_tests", 1):
        problems.append("only %d tests ran; the tier '%s' must run at least %d" % (ran, args.tier, tier.get("min_tests", 1)))
    print("tier %s: %s tests ran, %d failing, %d tolerated, %d flaky (passed on isolated re-run)" % (args.tier, ran, len(failing), len(tolerated), len(flaky_passed)))
    for test_id, entry in flaky_passed:
        print("  FLAKY until %s (%s): %s\n      cause: %s" % (entry["expires"], entry["owner"], test_id, entry["reason"][:200]))
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
