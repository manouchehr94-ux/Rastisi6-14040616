#!/usr/bin/env python3
"""Prove that the migrations of a release apply on a database that is already at the previous release's schema (PostgreSQL).

    migration_upgrade_test.py --base <commit-the-server-runs> --head <commit-to-release> --admin-url postgresql://u:p@host:5432/postgres

1. create a scratch database,
2. check out BASE in a worktree and `migrate` with BASE's own code  -> the schema production has today,
3. add a few rows through BASE's models (so the upgrade runs on non-empty tables),
4. check out HEAD in a worktree and `migrate` with HEAD's code       -> the upgrade,
5. `migrate --check` (nothing pending), `makemigrations --check` (models agree), and BASE's code still passes `manage.py check` against the NEW schema
   (the N-1 code must keep working against the N schema, which is what makes an automatic code rollback safe),
6. drop the scratch database.

Exit 0 only when every step passed. Uses the interpreter running this script (the CI job installs the dependencies once; if BASE and HEAD
differ in requirements, run the script twice with the right environment).
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse


def run(cmd, cwd, env, timeout=3600):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--admin-url", required=True)
    ap.add_argument("--psql", default="psql")
    args = ap.parse_args(argv)
    repo = str(Path(args.repo).resolve())
    u = urlparse(args.admin_url)
    pg = {"PGHOST": u.hostname or "", "PGPORT": str(u.port or 5432), "PGUSER": u.username or "", "PGPASSWORD": u.password or ""}
    db = "upgrade_test_%d" % int(time.time())
    url = "postgresql://%s%s@%s:%s/%s" % (u.username or "", (":" + u.password) if u.password else "", u.hostname, u.port or 5432, db)
    base_env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "VIRTUAL_ENV", "TMPDIR")}
    env = dict(base_env, DATABASE_URL=url, DJANGO_DEBUG="True", PYTHONDONTWRITEBYTECODE="1")
    work = Path(tempfile.mkdtemp(prefix="upgrade-test-"))
    problems = []

    def step(name, proc):
        ok = proc.returncode == 0
        print(("PASS  " if ok else "FAIL  ") + name)
        if not ok:
            problems.append(name)
            print((proc.stdout + proc.stderr)[-1500:])
        return ok

    def psql(sql, dbname="postgres"):
        return run([args.psql, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-c", sql], repo, dict(base_env, **pg))

    try:
        step("create scratch database", psql('CREATE DATABASE "%s"' % db))
        for label, rev in (("base", args.base), ("head", args.head)):
            tree = work / label
            r = run(["git", "worktree", "add", "-q", "--detach", str(tree), rev], repo, base_env)
            if not step("check out %s (%s)" % (label, rev[:12]), r):
                return 1
        ok = step("migrate with BASE code (today's production schema)", run([sys.executable, "manage.py", "migrate", "--noinput"], work / "base", env))
        if ok:
            seed = ("from django.contrib.auth import get_user_model;U=get_user_model();"
                    "[U.objects.create_user(username='upgrade-%d' % i, password='x') for i in range(3)]")
            step("write rows through BASE code", run([sys.executable, "manage.py", "shell", "-c", seed], work / "base", env))
            before = psql("SELECT count(*) FROM django_migrations", db).stdout.strip()
            step("migrate with HEAD code (the upgrade)", run([sys.executable, "manage.py", "migrate", "--noinput"], work / "head", env))
            after = psql("SELECT count(*) FROM django_migrations", db).stdout.strip()
            print("      migrations recorded: %s -> %s" % (before, after))
            step("nothing left to migrate (migrate --check)", run([sys.executable, "manage.py", "migrate", "--check"], work / "head", env))
            step("models agree with migrations (makemigrations --check)", run([sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"], work / "head", env))
            count = psql("SELECT count(*) FROM auth_user WHERE username LIKE 'upgrade-%'", db).stdout.strip()
            print(("PASS  " if count == "3" else "FAIL  ") + "rows written before the upgrade are intact (%s of 3)" % count)
            if count != "3":
                problems.append("rows intact")
            step("BASE code still loads against the HEAD schema (N-1 code on N schema)",
                 run([sys.executable, "manage.py", "check"], work / "base", env))
            probe = Path(__file__).resolve().parent / "schema_contract_probe.py"
            step("BASE code reads every model and validates writes on the HEAD schema",
                 run([sys.executable, str(probe)], work / "base", env))
    finally:
        for label in ("base", "head"):
            run(["git", "worktree", "remove", "--force", str(work / label)], repo, base_env)
        psql('DROP DATABASE IF EXISTS "%s"' % db)
    print("\nmigration upgrade test: %s" % ("FAILED: " + ", ".join(problems) if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
