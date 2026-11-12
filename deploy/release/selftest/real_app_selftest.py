#!/usr/bin/env python3
"""Real-application rehearsal of the whole release system. NO mocks of the application, database, cache, web server or probes:

  real Django project (the production commit), real Gunicorn, real PostgreSQL, real Redis, real rastisi_probe.py / rastisi_smoke.py,
  real build_release.py artifacts (hashed wheelhouse), real stage/activate/rollback through the SSH gate code path, real restic backup.

Only systemd is replaced by selftest/fake_service_manager.py (one unit, restart semantics identical in the way that matters:
the working directory is resolved from <base>/current at restart time).

Scenario (each step asserts and prints):
  0  production-as-it-is: commit PROD deployed the OLD way (checkout + venv + gunicorn), DB migrated, customer data created
  1  cutover: register the running deployment as release 'legacy-*' (nothing moved, nothing restarted by the tool)
  2  deploy the CAPTCHA commit through the gate (stage over stdin, detached activate, follow): no migrations, verified, previous kept
  3  roll back to the legacy release; verified; roll forward again
  4  deploy a deliberately broken commit: post-switch smoke fails -> automatic rollback to the CAPTCHA release
  5  Redis down -> pre-flight stops the deploy, nothing changes; Redis back
  6  additive migration: refused without a verified backup; real restic backup; deployed; rollback of the CODE keeps the column and the
     old code runs against the new schema
  7  persistent data (database rows, media, uploaded files) identical to step 0 throughout; no secret anywhere in logs/history

Needs: RASTISI_TEST_PG_BIN, RASTISI_TEST_PG_ADMIN_URL (disposable server), RASTISI_TEST_REDIS_BIN (redis-server), RASTISI_TEST_RESTIC,
       network for pip (only when the wheelhouse is built), PROD_SHA / CAPTCHA_SHA (default: this repository's known commits).
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))
import rastisi_common as C  # noqa: E402

PY = sys.executable
PROD_SHA = os.environ.get("PROD_SHA", "6a6897b7f7b034d6b80d3e693a2aa4e82b1039f4")
CAPTCHA_SHA = os.environ.get("CAPTCHA_SHA", "fa416ddbf1ff31652dd7accb9576097fbab0405a")
PG_BIN = os.environ.get("RASTISI_TEST_PG_BIN", "")
ADMIN_URL = os.environ.get("RASTISI_TEST_PG_ADMIN_URL", "")
REDIS_BIN = os.environ.get("RASTISI_TEST_REDIS_BIN", "")
RESTIC = os.environ.get("RASTISI_TEST_RESTIC", "")
PORT = 18992
REDIS_PORT = 6393
HOST = "rastisi.localhost"
CANARY_DB_PW = "CANARYselftestdbpw8841"
SKIP = not (PG_BIN and ADMIN_URL and REDIS_BIN and RESTIC)


def sh(cmd, env=None, cwd=None, check=True, timeout=1800, input_bytes=None):
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout, input=input_bytes)
    if check and proc.returncode != 0:
        raise AssertionError("command failed (%d): %s\n%s\n%s" % (proc.returncode, " ".join(map(str, cmd))[:200],
                                                                  proc.stdout.decode(errors="replace")[-1500:], proc.stderr.decode(errors="replace")[-2500:]))
    return proc


@unittest.skipIf(SKIP, "needs PostgreSQL, Redis, restic (see module docstring)")
class RealApplicationRehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="rastisi-real-"))
        cls.base = cls.root / "srv"
        cls.state = cls.base / "state"
        cls.media = cls.root / "media"
        cls.static = cls.root / "static"
        cls.svc_state = cls.root / "svc"
        cls.backup_state = cls.root / "backup-state"
        cls.dist = cls.root / "dist"
        cls.db = "selftest_%d" % int(time.time())
        u = urlparse(ADMIN_URL)
        cls.pg_env = dict(os.environ, PGHOST=u.hostname or "", PGPORT=str(u.port or 5432), PGUSER=u.username or "", PGPASSWORD=u.password or "", PGDATABASE=cls.db)
        for d in (cls.base, cls.media, cls.static, cls.svc_state, cls.backup_state, cls.dist):
            d.mkdir(parents=True)
        cls.redis_dir = cls.root / "redis"
        cls.redis_dir.mkdir()
        cls.redis = None
        cls.start_redis()
        sh([os.path.join(PG_BIN, "psql"), "-X", "-c", 'CREATE DATABASE "%s"' % cls.db], env=dict(cls.pg_env, PGDATABASE="postgres"))
        pw = (":" + CANARY_DB_PW) if False else (":" + u.password if u.password else "")
        cls.database_url = "postgres://%s%s@%s:%s/%s" % (u.username or "", pw, u.hostname, u.port or 5432, cls.db)
        cls.env_file = cls.root / "app.env"
        cls.env_file.write_text("\n".join([
            "DJANGO_DEBUG=False", "DJANGO_SECRET_KEY=CANARY-selftest-secret-%s" % hashlib.sha1(os.urandom(8)).hexdigest(),
            "DATABASE_URL=%s" % cls.database_url, "DJANGO_ALLOWED_HOSTS=%s,127.0.0.1" % HOST,
            "RASTISI_RATE_LIMIT_CACHE_URL=redis://:localtestpw@127.0.0.1:%d/1" % REDIS_PORT,
            "TURNSTILE_SITE_KEY=1x00000000000000000000AA", "TURNSTILE_SECRET_KEY=1x0000000000000000000000000000AA", "TURNSTILE_EXPECTED_HOSTNAMES=%s" % HOST,
            "PAYMENT_CREDENTIAL_KEY=%s" % subprocess.check_output([PY, "-c", "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"], text=True).strip(),
            "DJANGO_STATIC_ROOT=%s" % cls.static, "DJANGO_MEDIA_ROOT=%s" % cls.media, "DJANGO_PRIVATE_MEDIA_ROOT=%s" % (cls.root / "private"),
            "RASTISI_PLATFORM_PRIMARY_HOST=%s" % HOST, "RASTISI_CAPTCHA_ENABLED=true",
        ]) + "\n")
        (cls.root / "private").mkdir()
        os.chmod(str(cls.env_file), 0o600)
        cls.manager = [PY, str(HERE / "fake_service_manager.py"), str(cls.svc_state), str(cls.base), str(cls.env_file), str(PORT)]
        cls.conf = cls.root / "deploy.conf"
        cls.conf.write_text("\n".join([
            "[rastisi]", "base_dir = %s" % cls.base, "app_user = tester", "service = rastisi-selftest.service", "env_file = %s" % cls.env_file,
            "port = %d" % PORT, "static_root = %s" % cls.static, "python = %s" % PY,
            "app_runner = %s %s" % (PY, TOOLS / "rastisi_app_task.py"), "systemctl = %s" % " ".join(cls.manager),
            "systemctl_show = %s" % " ".join(cls.manager), "smoke_host = %s" % HOST, "health_timeout = 60", "migrate_timeout = 900",
            "backup_record = %s" % (cls.backup_state / "last_backup.json"), "backup_max_age_minutes = 30", "min_free_mb = 50", "keep_releases = 4",
        ]) + "\n")
        cls.env = dict(os.environ, RASTISI_DEPLOY_CONF=str(cls.conf), RASTISI_ALLOW_ROOT_FOR_TESTS="1", PYTHONDONTWRITEBYTECODE="1")
        # scratch clone for synthetic commits (a broken one, one with an additive migration)
        cls.clone = cls.root / "clone"
        sh(["git", "clone", "-q", "--shared", "--no-checkout", str(REPO), str(cls.clone)])
        sh(["git", "-C", str(cls.clone), "config", "user.email", "selftest@example.com"])
        sh(["git", "-C", str(cls.clone), "config", "user.name", "selftest"])
        cls.logs = []
        cls.ids = {}

    @classmethod
    def tearDownClass(cls):
        sh(cls.manager + ["stop"], check=False)
        if cls.redis:
            cls.redis.terminate()
            try:
                cls.redis.wait(10)
            except subprocess.TimeoutExpired:
                cls.redis.kill()
        sh([os.path.join(PG_BIN, "psql"), "-X", "-c", 'DROP DATABASE IF EXISTS "%s"' % cls.db], env=dict(cls.pg_env, PGDATABASE="postgres"), check=False)
        for p in sorted(cls.base.rglob("*"), reverse=True):
            try:
                if p.is_dir() and not p.is_symlink():
                    os.chmod(str(p), 0o755)
            except OSError:
                pass
        if not os.environ.get("KEEP_SELFTEST_DIR"):
            shutil.rmtree(str(cls.root), ignore_errors=True)

    # ------------------------------------------------------------------------------------------------------- infrastructure
    @classmethod
    def start_redis(cls):
        cls.redis = subprocess.Popen([REDIS_BIN, "--port", str(REDIS_PORT), "--bind", "127.0.0.1", "--requirepass", "localtestpw", "--save", "", "--appendonly", "no",
                                      "--dir", str(cls.redis_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                import socket
                socket.create_connection(("127.0.0.1", REDIS_PORT), 0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        raise AssertionError("redis did not start")

    @classmethod
    def stop_redis(cls):
        cls.redis.terminate()
        cls.redis.wait(10)

    def tool(self, script, *args, check=True, input_bytes=None, env=None):
        proc = sh([PY, str(TOOLS / script)] + [str(a) for a in args], env=dict(self.env, **(env or {})), check=check, input_bytes=input_bytes)
        self.logs += [proc.stdout.decode(errors="replace"), proc.stderr.decode(errors="replace")]
        return proc

    def gate(self, command, input_bytes=None):
        return sh([PY, str(TOOLS / "rastisi_gate.py")], env=dict(self.env, SSH_ORIGINAL_COMMAND=command), input_bytes=input_bytes, check=False)

    def status(self):
        return json.loads(self.tool("rastisi_release.py", "status").stdout)

    def psql(self, sql, db=None):
        env = dict(self.pg_env)
        if db:
            env["PGDATABASE"] = db
        return sh([os.path.join(PG_BIN, "psql"), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], env=env).stdout.decode().strip()

    def http(self, path, host=HOST, timeout=15):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), headers={"Host": host, "X-Forwarded-Proto": "https"})
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def build(self, repo, sha, from_sha):
        out = self.dist / sha[:12]
        sh([PY, str(TOOLS / "build_release.py"), "--repo", str(repo), "--sha", sha, "--from-sha", from_sha, "--out", str(out), "--python-version",
            "%d.%d" % sys.version_info[:2]], timeout=900)
        art = next(out.glob("*.tar.gz"))
        return art, hashlib.sha256(art.read_bytes()).hexdigest()

    def stage_via_gate(self, art, sha, digest):
        proc = self.gate("stage %s %s" % (sha, digest), input_bytes=art.read_bytes())
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        return json.loads(proc.stdout.decode().strip().splitlines()[-1])["release"]

    def activate_via_gate(self, rid, sha, from_sha, flags=""):
        proc = self.gate("activate %s %s %s %s" % (rid, sha, from_sha or "-", flags))
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        run_id = proc.stdout.decode().split()[1]
        offset, text = 0, ""
        for _ in range(900):
            f = self.gate("follow %s %d" % (run_id, offset)).stdout.decode().splitlines()
            text += "\n".join(l for l in f if not l.startswith(("OFFSET ", "STATE ")))
            offset = int([l for l in f if l.startswith("OFFSET ")][-1].split()[1])
            state = [l for l in f if l.startswith("STATE ")][-1]
            if state.startswith("STATE done"):
                self.logs.append(text)
                return int(state.split()[2]), text
            time.sleep(1)
        self.fail("activation did not finish")

    def serving_release(self):
        pid = int(sh(self.manager + ["show", "-p", "MainPID", "--value", "x"]).stdout.decode().strip())
        cwd = os.path.realpath(os.readlink("/proc/%d/cwd" % pid))
        return cwd

    def fingerprint(self):
        rows = self.psql("SELECT (SELECT count(*) FROM auth_user)||'/'||(SELECT count(*) FROM stores_store)||'/'||(SELECT count(*) FROM portal_contactmessage)||'/'||"
                         "(SELECT md5(string_agg(username, ',' ORDER BY id)) FROM auth_user)||'/'||(SELECT md5(string_agg(slug, ',' ORDER BY id)) FROM stores_store)")
        files = hashlib.sha256()
        for p in sorted(self.media.rglob("*")):
            if p.is_file():
                files.update(p.relative_to(self.media).as_posix().encode() + p.read_bytes())
        return rows, files.hexdigest()

    # ------------------------------------------------------------------------------------------------------------ the scenario
    def test_00_production_as_it_is_today_old_style_deployment(self):
        art, digest = self.build(REPO, PROD_SHA, "")
        legacy_app = self.root / "legacy" / "app"
        legacy_venv = self.root / "legacy" / "venv"
        legacy_app.parent.mkdir()
        legacy_app.mkdir()
        sh(["tar", "-xzf", str(art), "-C", str(legacy_app.parent), "app", "requirements.lock", "wheelhouse"])
        # `app` came out as legacy/app already
        sh([PY, "-m", "venv", str(legacy_venv)])
        sh([str(legacy_venv / "bin" / "pip"), "install", "-q", "--no-index", "--find-links", str(legacy_app.parent / "wheelhouse"), "--require-hashes", "--no-deps",
            "-r", str(legacy_app.parent / "requirements.lock")], timeout=900)
        env = dict(os.environ, **C.parse_env_file(str(self.env_file)), PYTHONDONTWRITEBYTECODE="1")
        sh([str(legacy_venv / "bin" / "python"), "manage.py", "migrate", "--noinput"], cwd=str(legacy_app), env=env, timeout=1800)
        sh([str(legacy_venv / "bin" / "python"), "manage.py", "collectstatic", "--noinput", "-v", "0"], cwd=str(legacy_app), env=env, timeout=600)
        # customer data that no deployment may ever disturb
        script = ("from django.contrib.auth import get_user_model; from apps.stores.models import Store; from apps.portal.models import ContactMessage;"
                  "U=get_user_model(); [U.objects.create_user(username='customer-%d' % i, password='x-%d-Zz9!' % i) for i in range(5)];"
                  "[Store.objects.create(name='Shop %d' % i, slug='shop-selftest-%d' % i, status=Store.Status.ACTIVE) for i in range(3)];"
                  "ContactMessage.objects.create(full_name='Real Customer', email='c@example.com', subject='hello', message='an actual message from a customer')")
        sh([str(legacy_venv / "bin" / "python"), "manage.py", "shell", "-c", script], cwd=str(legacy_app), env=env, timeout=300)
        (self.media / "stores").mkdir()
        for i in range(12):
            (self.media / "stores" / ("logo-%d.png" % i)).write_bytes(os.urandom(3000))
        type(self).fp_before = self.fingerprint()
        self.assertTrue(self.fp_before[0].startswith("5/4/1/"), self.fp_before)    # 3 created + the migration-seeded akhlaghi store
        type(self).legacy = (legacy_app, legacy_venv)

    def test_01_cutover_registers_the_running_deployment_without_touching_it(self):
        legacy_app, legacy_venv = self.legacy
        before = sorted((p.name, p.stat().st_mtime_ns) for p in legacy_app.iterdir())
        dry = self.tool("rastisi_release.py", "cutover", "--legacy-app", legacy_app, "--legacy-venv", legacy_venv, "--sha", PROD_SHA)
        self.assertIn("dry run", dry.stdout.decode())
        self.assertFalse((self.base / "current").exists())
        self.tool("rastisi_release.py", "cutover", "--legacy-app", legacy_app, "--legacy-venv", legacy_venv, "--sha", PROD_SHA, "--apply")
        self.assertEqual(before, sorted((p.name, p.stat().st_mtime_ns) for p in legacy_app.iterdir()), "the legacy directory must not be modified")
        # what the systemd drop-in change does on the real server: start the service from <base>/current
        sh(self.manager + ["restart"])
        for _ in range(60):
            code, body = self.http("/login/")
            if code == 200:
                break
            time.sleep(1)
        self.assertEqual(code, 200)
        self.assertIn("cf-turnstile", body, "production still runs the Turnstile build")
        self.assertEqual(self.status()["current"], "legacy-" + PROD_SHA[:12])

    def test_02_deploy_the_captcha_release_through_the_gate(self):
        art, digest = self.build(REPO, CAPTCHA_SHA, PROD_SHA)
        report = json.loads(next((self.dist / CAPTCHA_SHA[:12]).glob("migration-report.json")).read_text())
        self.assertEqual((report["level"], report["new_migrations"]), ("NONE", []))
        rid = self.stage_via_gate(art, CAPTCHA_SHA, digest)
        self.ids["captcha"] = rid
        # make sure an old backup/none does not matter for a release without migrations
        code, text = self.activate_via_gate(rid, CAPTCHA_SHA, PROD_SHA)
        self.assertEqual(code, 0, text)
        self.assertIn("no pending migrations", text)
        self.assertIn("DONE", text)
        self.assertTrue(self.serving_release().endswith("%s/app" % rid), self.serving_release())
        status, body = self.http("/login/")
        self.assertEqual(status, 200)
        self.assertIn("captcha_token", body)
        self.assertNotIn("cf-turnstile", body)
        self.assertNotIn("challenges.cloudflare.com", body)
        st = self.status()
        self.assertEqual(st["previous"], "legacy-" + PROD_SHA[:12])
        self.assertTrue(st["active"]["rollback_safe_to_previous"])
        self.assertEqual(self.fingerprint(), self.fp_before)

    def test_03_rollback_to_the_legacy_release_and_forward_again(self):
        proc = self.tool("rastisi_release.py", "rollback", "--to", "previous")
        self.assertIn('"ok": true', proc.stdout.decode())
        self.assertTrue(self.serving_release().endswith("legacy/app"), self.serving_release())
        status, body = self.http("/login/")
        self.assertEqual(status, 200)
        self.assertIn("cf-turnstile", body)
        self.assertEqual(self.fingerprint(), self.fp_before)
        self.tool("rastisi_release.py", "rollback", "--to", self.ids["captcha"], "--unsafe-ack", "I-UNDERSTAND-THE-DATABASE-MAY-NOT-MATCH-THE-OLD-CODE")
        self.assertTrue(self.serving_release().endswith("%s/app" % self.ids["captcha"]))
        self.assertIn("captcha_token", self.http("/login/")[1])

    def synthetic_commit(self, message, edits):
        sh(["git", "-C", str(self.clone), "fetch", "-q", "--no-tags", str(REPO), CAPTCHA_SHA])
        sh(["git", "-C", str(self.clone), "checkout", "-q", "--detach", CAPTCHA_SHA])
        for rel, mutate in edits.items():
            p = self.clone / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(mutate(p.read_text() if p.exists() else ""))
        sh(["git", "-C", str(self.clone), "add", "-A"])
        sh(["git", "-C", str(self.clone), "commit", "-q", "-m", message])
        return sh(["git", "-C", str(self.clone), "rev-parse", "HEAD"]).stdout.decode().strip()

    def test_04_a_broken_release_is_rolled_back_automatically(self):
        def break_login(src):
            marker = "def login_view(request):\n"
            assert marker in src
            return src.replace(marker, marker + "    raise RuntimeError('selftest: simulated bad release')\n", 1)
        sha = self.synthetic_commit("selftest: break the login page", {"apps/portal/views.py": break_login})
        art, digest = self.build(self.clone, sha, CAPTCHA_SHA)
        rid = self.stage_via_gate(art, sha, digest)
        code, text = self.activate_via_gate(rid, sha, CAPTCHA_SHA)
        self.assertEqual(code, C.EXIT_FAILED_SAFE, text)
        self.assertIn("rolling back", text)
        self.assertTrue(self.serving_release().endswith("%s/app" % self.ids["captcha"]), self.serving_release())
        self.assertEqual(self.http("/login/")[0], 200, "the site must be back to normal")
        st = self.status()
        self.assertIsNone(st["incident"])
        self.assertEqual({r["id"]: r["status"] for r in st["releases"]}[rid], "failed")
        self.assertEqual(self.fingerprint(), self.fp_before)

    def test_05_redis_outage_stops_the_deploy_before_anything_changes(self):
        art, digest = self.build(REPO, CAPTCHA_SHA, PROD_SHA)
        rid = self.stage_via_gate(art, CAPTCHA_SHA, digest)            # a second copy of the same commit as a staged release
        restarts_marker = self.serving_release()
        self.stop_redis()
        try:
            proc = self.tool("rastisi_release.py", "activate", "--id", rid, check=False)
            text = proc.stdout.decode() + proc.stderr.decode()
            self.assertEqual(proc.returncode, C.EXIT_POLICY, text)
            self.assertIn("redis", text.lower())
        finally:
            type(self).start_redis()
        self.assertEqual(self.serving_release(), restarts_marker)

    def test_06_additive_migration_needs_a_real_backup_and_survives_a_code_rollback(self):
        def add_migration(_old):
            return ("from django.db import migrations, models\n\n\nclass Migration(migrations.Migration):\n    dependencies = [('portal', '0020_platformconfiguration_trial_enabled')]\n"
                    "    operations = [\n        migrations.AddField(model_name='contactmessage', name='selftest_note', field=models.CharField(max_length=40, null=True, blank=True)),\n    ]\n")
        sha = self.synthetic_commit("selftest: additive migration", {"apps/portal/migrations/0021_selftest_note.py": add_migration})
        art, digest = self.build(self.clone, sha, CAPTCHA_SHA)
        report = json.loads(next((self.dist / sha[:12]).glob("migration-report.json")).read_text())
        self.assertEqual((report["level"], report["new_migrations"]), ("ADDITIVE", ["portal.0021_selftest_note"]))
        rid = self.stage_via_gate(art, sha, digest)
        code, text = self.activate_via_gate(rid, sha, CAPTCHA_SHA)
        self.assertEqual(code, C.EXIT_POLICY, "must be refused without a verified backup:\n" + text)
        self.assertIn("backup", text.lower())
        self.assertNotIn("selftest_note", self.psql("SELECT column_name FROM information_schema.columns WHERE table_name='portal_contactmessage'"))
        # real backup of the real database and media into a real (local) restic repository
        repo = self.root / "offsite"
        pwf = self.root / "restic.pw"
        pwf.write_text("selftest-restic-password")
        sh([RESTIC, "init"], env=dict(os.environ, RESTIC_REPOSITORY=str(repo), RESTIC_PASSWORD_FILE=str(pwf)))
        bconf = self.root / "backup.conf"
        bconf.write_text("\n".join(["[backup]", "env_file = %s" % self.env_file, "state_dir = %s" % self.backup_state, "restic_repository = %s" % repo,
                                    "restic_password_file = %s" % pwf, "restic_cmd = %s" % RESTIC, "media_root = %s" % self.media, "pg_bin_dir = %s" % PG_BIN,
                                    "config_files = %s" % self.env_file, "tmp_dir = %s" % self.root, "check_read_data_subset = 20%"]) + "\n")
        sh([PY, str(TOOLS.parent / "backup" / "rastisi_backup.py"), "run"], env=dict(os.environ, RASTISI_BACKUP_CONF=str(bconf)), timeout=1800)
        code, text = self.activate_via_gate(rid, sha, CAPTCHA_SHA)
        self.assertEqual(code, 0, text)
        self.assertIn("portal.0021_selftest_note", text)
        self.assertIn("selftest_note", self.psql("SELECT column_name FROM information_schema.columns WHERE table_name='portal_contactmessage'"))
        st = self.status()
        self.assertEqual(st["active"]["migrations_applied"], ["portal.0021_selftest_note"])
        self.assertTrue(st["active"]["rollback_safe_to_previous"])
        # the NEW code wrote a row using the new column ...
        self.psql("UPDATE portal_contactmessage SET selftest_note='written by new code'")
        # ... now roll the CODE back: the old code must run happily against the newer (additive) schema and the data must stay
        self.tool("rastisi_release.py", "rollback", "--to", "previous", "--unsafe-ack", "I-UNDERSTAND-THE-DATABASE-MAY-NOT-MATCH-THE-OLD-CODE")
        self.assertTrue(self.serving_release().endswith("%s/app" % self.ids["captcha"]))
        self.assertEqual(self.http("/login/")[0], 200)
        self.assertEqual(self.http("/contact/")[0], 200, "old code must serve forms against the additive schema")
        self.assertEqual(self.psql("SELECT selftest_note FROM portal_contactmessage"), "written by new code")
        # and the drill proves the backup could really bring everything back
        drill = sh([PY, str(TOOLS.parent / "backup" / "rastisi_backup.py"), "restore-drill"], env=dict(os.environ, RASTISI_BACKUP_CONF=str(bconf)), timeout=1800)
        self.assertIn("restore drill OK", drill.stdout.decode())

    def test_07_persistent_data_untouched_and_no_secret_anywhere(self):
        self.assertEqual(self.fingerprint()[1], self.fp_before[1], "media files must be byte-identical")
        rows_now = self.fingerprint()[0]
        self.assertEqual(rows_now, self.fp_before[0], "customer rows must be identical")
        text = "\n".join(self.logs)
        for p in list(self.state.rglob("*")):
            if p.is_file() and p.stat().st_size < 3_000_000:
                text += p.read_text(errors="replace")
        env = C.parse_env_file(str(self.env_file))
        for name in ("DJANGO_SECRET_KEY", "PAYMENT_CREDENTIAL_KEY"):
            self.assertNotIn(env[name], text, name + " leaked")
        self.assertNotIn("localtestpw", text)
        events = [json.loads(l)["event"] for l in (self.state / "history.jsonl").read_text().splitlines()]
        self.assertIn("cutover", events)
        self.assertGreaterEqual(events.count("activate"), 3)
        self.assertGreaterEqual(events.count("rollback"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2, failfast=True)
