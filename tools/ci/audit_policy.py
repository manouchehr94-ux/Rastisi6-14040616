#!/usr/bin/env python3
"""Dependency vulnerability gate (standard library; runs pip-audit, which the CI job installs).

    audit_policy.py --requirements requirements.txt [--exceptions tools/ci/audit_exceptions.json] [--today 2026-11-12]

Same philosophy as the test gate: a known advisory is tolerated only when it is listed (by advisory id) with an owner, a reason and an expiry
date. A NEW advisory, an EXPIRED exception, or an exception that no longer matches anything (the package was upgraded) fails the gate.
Findings that are tolerated are still printed on every run.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_pip_audit(requirements):
    proc = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(requirements), "--no-deps", "--disable-pip", "-f", "json", "--progress-spinner", "off"],
                          capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise SystemExit("pip-audit produced no JSON (exit %s): %s" % (proc.returncode, proc.stderr[-800:]))


def findings(report):
    out = {}
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            out[(dep["name"].lower(), vuln["id"])] = {"version": dep["version"], "fix": sorted(vuln.get("fix_versions", [])), "aliases": vuln.get("aliases", [])}
    return out


def judge(found, exceptions, today):
    """Pure decision function (unit-tested)."""
    problems, tolerated = [], []
    index = {}
    for exc in exceptions.get("exceptions", []):
        for vid in exc["advisories"]:
            index[(exc["package"].lower(), vid)] = exc
    for key, info in sorted(found.items()):
        exc = index.get(key)
        if exc is None:
            problems.append("NEW advisory %s in %s %s (fixed in %s)" % (key[1], key[0], info["version"], ", ".join(info["fix"]) or "no fix yet"))
        elif datetime.date.fromisoformat(exc["expires"]) < today:
            problems.append("EXPIRED exception for %s in %s (expired %s, owner %s)" % (key[1], key[0], exc["expires"], exc["owner"]))
        elif exc.get("version") and exc["version"] != info["version"]:
            problems.append("exception for %s was granted for %s %s but %s is installed: re-review" % (key[1], key[0], exc["version"], info["version"]))
        elif not exc.get("security_review", {}).get("approved") or not exc["security_review"].get("evidence"):
            problems.append("UNREVIEWED security exception: %s in %s" % (key[1], key[0]))
        else:
            tolerated.append((key, exc))
    for key, exc in sorted(index.items()):
        if key not in found:
            problems.append("STALE exception: %s in %s no longer applies; remove it from audit_exceptions.json" % (key[1], key[0]))
    return problems, tolerated


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--requirements", required=True)
    ap.add_argument("--exceptions", default=str(HERE / "audit_exceptions.json"))
    ap.add_argument("--today", default="")
    ap.add_argument("--report", default="", help="use an existing pip-audit JSON report instead of running pip-audit (unit tests)")
    ap.add_argument("--write-baseline", default="", help="write an exceptions file for the CURRENT findings (a one-time, reviewed action)")
    args = ap.parse_args(argv)
    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    report = json.loads(Path(args.report).read_text()) if args.report else run_pip_audit(args.requirements)
    found = findings(report)
    if args.write_baseline:
        by_pkg = {}
        for (pkg, vid), info in found.items():
            by_pkg.setdefault((pkg, info["version"], tuple(info["fix"])), []).append(vid)
        data = {"_policy": "see tools/ci/audit_policy.py", "exceptions": [
            {"package": p, "version": v, "advisories": sorted(ids), "fixed_in": list(f), "owner": "TODO", "reason": "TODO",
             "expires": (today + datetime.timedelta(days=30)).isoformat()} for (p, v, f), ids in sorted(by_pkg.items())]}
        Path(args.write_baseline).write_text(json.dumps(data, indent=2) + "\n")
        print("baseline written: %d packages" % len(by_pkg))
        return 0
    exceptions = json.loads(Path(args.exceptions).read_text(encoding="utf-8"))
    problems, tolerated = judge(found, exceptions, today)
    print("dependency audit: %d advisories, %d tolerated by explicit exception" % (len(found), len(tolerated)))
    seen = set()
    for (pkg, _), exc in tolerated:
        if pkg not in seen:
            seen.add(pkg)
            print("  TOLERATED until %s (%s): %s %s: %s" % (exc["expires"], exc["owner"], pkg, exc.get("version", ""), exc["reason"][:220]))
    for p in problems:
        print("  PROBLEM:", p)
    if not problems:
        print("gate passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
