#!/usr/bin/env python3
"""Stand-in for the Django project's manage.py inside a stub release. Controlled by the JSON file named in $STUB_CONTROL.

The 'database' is $STUB_DB (db.json): {"rows": [...customer data...], "applied": [migration names]}.
The release declares its migrations in app/migrations.json. Behaviour flags in the control file:
  check_fail, migrate: "ok"|"fail_first"|"fail_after_first", leak_secret_on_failure, migrate_delay
"""

import json
import os
import sys
import time

control = json.load(open(os.environ["STUB_CONTROL"])) if os.path.exists(os.environ.get("STUB_CONTROL", "")) else {}
db_path = os.environ["STUB_DB"]
db = json.load(open(db_path))
here = os.path.dirname(os.path.abspath(__file__))
declared = json.load(open(os.path.join(here, "migrations.json"))) if os.path.exists(os.path.join(here, "migrations.json")) else []
cmd = sys.argv[1]

if cmd == "check":
    if control.get("check_fail"):
        sys.stderr.write("SystemCheckError: simulated\n")
        sys.exit(1)
    sys.exit(0)

if cmd == "migrate":
    pending = [m for m in declared if m not in db["applied"]]
    mode = control.get("migrate", "ok")
    time.sleep(float(control.get("migrate_delay", 0)))
    for i, name in enumerate(pending):
        if mode == "fail_first" or (mode == "fail_after_first" and i >= 1):
            sys.stderr.write("django.db.utils.OperationalError: could not apply %s (simulated) DATABASE_URL=%s\n" % (name, os.environ.get("DATABASE_URL", "")))
            sys.exit(1)
        db["applied"].append(name)
        json.dump(db, open(db_path, "w"))
    sys.exit(0)

if cmd == "collectstatic":
    target = os.environ["DJANGO_STATIC_ROOT"]
    os.makedirs(target, exist_ok=True)
    version = open(os.path.join(here, "static_version")).read().strip() if os.path.exists(os.path.join(here, "static_version")) else "0"
    open(os.path.join(target, "app.css"), "w").write("/* css v%s */\n" % version)
    open(os.path.join(target, "release-%s.txt" % version), "w").write("v%s\n" % version)
    sys.exit(0)

sys.stderr.write("unknown command %s\n" % cmd)
sys.exit(2)
