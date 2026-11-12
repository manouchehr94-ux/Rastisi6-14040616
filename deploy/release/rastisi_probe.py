#!/usr/bin/env python3
"""Django-side probe, run by rastisi_app_task.py with the RELEASE'S virtualenv inside the release directory.

Lives with the deployment tooling, not inside the application, so it works for every commit (including ones that predate it).
Prints exactly one JSON line. Never prints settings values: only names, counts and pass/fail.

    rastisi_probe.py health [--pre|--post]    database, Redis (rate-limit store), paths, debug flag, migration state
    rastisi_probe.py plan                      unapplied migrations as "app.migration" names
"""

import json
import os
import sys
import tempfile
import time


def _setup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
    sys.path.insert(0, os.getcwd())
    import django

    django.setup()


def plan():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    conflicts = executor.loader.detect_conflicts()
    pending = ["%s.%s" % (m.app_label, m.name) for m, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes()) if not backwards]
    return {"ok": not conflicts, "plan": pending, "conflicts": sorted(conflicts) if conflicts else [],
            "error": "conflicting migrations: %s" % sorted(conflicts) if conflicts else ""}


def health(mode):
    from django.conf import settings
    from django.core.cache import caches
    from django.db import connection

    failures = []
    checks = {}

    def record(name, ok, why=""):
        checks[name] = bool(ok)
        if not ok:
            failures.append("%s%s" % (name, (": " + why) if why else ""))

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        record("database", True)
        record("database_is_postgresql", connection.vendor == "postgresql", "vendor is %s" % connection.vendor)
    except Exception as exc:  # noqa: BLE001
        record("database", False, exc.__class__.__name__)

    try:
        alias = getattr(settings, "RASTISI_RATE_LIMIT_CACHE_ALIAS", "ratelimit")
        store = caches[alias]
        key = "deploy-probe:%d:%s" % (os.getpid(), time.time())
        store.set(key, "1", timeout=30)
        record("redis_rate_limit_store", store.get(key) == "1", "read-back mismatch")
        store.delete(key)
    except Exception as exc:  # noqa: BLE001
        record("redis_rate_limit_store", False, exc.__class__.__name__)

    record("production_mode", getattr(settings, "RASTISI_PRODUCTION_MODE", False) is True, "DJANGO_DEBUG is not False")
    record("secret_key_set", bool(getattr(settings, "SECRET_KEY", "")) and "django-insecure" not in str(settings.SECRET_KEY))
    record("simulated_payments_off", not getattr(settings, "PAYMENTS_SIMULATION_ENABLED", False))
    record("refund_kill_switches_off", not getattr(settings, "RASTISI_SMS_REFUND_ENABLED", False) and not getattr(settings, "RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS", ""))
    for name in ("STATIC_ROOT", "MEDIA_ROOT"):
        path = str(getattr(settings, name, ""))
        record(name.lower() + "_exists", bool(path) and os.path.isdir(path), "missing directory")
    media = str(getattr(settings, "MEDIA_ROOT", ""))
    if media and os.path.isdir(media):
        try:
            with tempfile.NamedTemporaryFile(dir=media, prefix=".probe-", delete=True):
                pass
            record("media_writable", True)
        except OSError as exc:
            record("media_writable", False, exc.__class__.__name__)

    if mode == "post":
        try:
            info = plan()
            record("migrations_fully_applied", not info["plan"], "%d unapplied" % len(info["plan"]))
        except Exception as exc:  # noqa: BLE001
            record("migrations_fully_applied", False, exc.__class__.__name__)
    return {"ok": not failures, "failures": failures, "checks": checks, "mode": mode}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        _setup()
        if cmd == "plan":
            result = plan()
        elif cmd == "health":
            result = health("post" if "--post" in sys.argv else "pre")
        else:
            result = {"ok": False, "error": "unknown probe command"}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": "%s while loading the application" % exc.__class__.__name__}
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
