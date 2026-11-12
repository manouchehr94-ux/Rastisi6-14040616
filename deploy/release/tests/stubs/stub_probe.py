#!/usr/bin/env python3
"""Stand-in for rastisi_probe.py (the real one is exercised by the real-application self-test)."""

import json
import os
import sys

control = json.load(open(os.environ["STUB_CONTROL"])) if os.path.exists(os.environ.get("STUB_CONTROL", "")) else {}
db = json.load(open(os.environ["STUB_DB"]))
declared = json.load(open("migrations.json")) if os.path.exists("migrations.json") else []
mode = sys.argv[1]
pending = [m for m in declared if m not in db["applied"]]

if mode == "plan":
    print(json.dumps({"ok": True, "plan": pending}))
    sys.exit(0)

failures = []
if control.get("redis_down"):
    failures.append("redis_rate_limit_store: ConnectionError")
if "--post" in sys.argv and os.path.exists("REDIS_BREAKS"):          # a release whose code cannot talk to Redis
    failures.append("redis_rate_limit_store: ConnectionError")
if control.get("database_down"):
    failures.append("database: OperationalError")
if "--post" in sys.argv and pending:
    failures.append("migrations_fully_applied: %d unapplied" % len(pending))
print(json.dumps({"ok": not failures, "failures": failures, "checks": {}}))
sys.exit(0 if not failures else 1)
