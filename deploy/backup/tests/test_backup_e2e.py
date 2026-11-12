"""End-to-end backup/restore tests against a REAL PostgreSQL and a REAL restic repository (local directory standing in for off-site storage).

Needs:  RASTISI_TEST_PG_BIN   directory with pg_dump, pg_restore, psql
        RASTISI_TEST_PG_ADMIN_URL  postgresql://user[:pw]@host:port/postgres  (a role that may CREATE DATABASE; a disposable server!)
        restic on PATH or RASTISI_TEST_RESTIC
They are skipped (not passed) when any is missing. CI provides all three; locally: deploy/backup/tests/run_with_throwaway_pg.sh.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "release"))
import rastisi_backup as B  # noqa: E402
import rastisi_common as C  # noqa: E402

PG_BIN = os.environ.get("RASTISI_TEST_PG_BIN", "")
ADMIN_URL = os.environ.get("RASTISI_TEST_PG_ADMIN_URL", "")
RESTIC = os.environ.get("RASTISI_TEST_RESTIC") or shutil.which("restic") or ""
SKIP = not (PG_BIN and ADMIN_URL and RESTIC)

DB_PASSWORD = "CANARY-db-pw-93f1"
RESTIC_PASSWORD = "CANARY-restic-pw-5d2c"
PII = "CANARY-CUSTOMER-PII-+989121234567"


def admin_env():
    u = urlparse(ADMIN_URL)
    return dict(os.environ, PGHOST=u.hostname or "", PGPORT=str(u.port or 5432), PGUSER=u.username or "", PGPASSWORD=u.password or "", PGDATABASE="postgres")


def psql(db, sql):
    env = admin_env()
    env["PGDATABASE"] = db
    proc = subprocess.run([os.path.join(PG_BIN, "psql"), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


@unittest.skipIf(SKIP, "needs PostgreSQL client tools, an admin URL and restic")
class BackupEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rastisi-bk-"))
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.db = "bk_live_%d" % int(time.time() * 1000)
        psql("postgres", 'CREATE DATABASE "%s"' % self.db)
        self.addCleanup(lambda: psql("postgres", 'DROP DATABASE IF EXISTS "%s"' % self.db))
        psql(self.db, """
            CREATE TABLE stores_store(id serial primary key, name text);
            CREATE TABLE orders_order(id serial primary key, buyer text, total int);
            CREATE TABLE auth_user(id serial primary key, username text);
            INSERT INTO stores_store(name) SELECT 'store-' || g FROM generate_series(1,40) g;
            INSERT INTO orders_order(buyer,total) SELECT '%s', g*1000 FROM generate_series(1,300) g;
            INSERT INTO auth_user(username) SELECT 'user' || g FROM generate_series(1,25) g;
        """ % PII)
        self.media = self.root / "media"
        (self.media / "stores").mkdir(parents=True)
        for i in range(30):
            (self.media / "stores" / ("p%02d.jpg" % i)).write_bytes(os.urandom(2000) + b"MEDIA%d" % i)
        u = urlparse(ADMIN_URL)
        self.env_file = self.root / "app.env"
        self.write_env(DB_PASSWORD_URL=True)
        self.pw_file = self.root / "restic.pw"
        self.pw_file.write_text(RESTIC_PASSWORD)
        os.chmod(str(self.pw_file), 0o600)
        self.repo = self.root / "offsite-repo"
        self.state = self.root / "state"
        self.conf_path = self.root / "backup.conf"
        self.conf_path.write_text("\n".join([
            "[backup]", "env_file = %s" % self.env_file, "state_dir = %s" % self.state, "restic_repository = %s" % self.repo,
            "restic_password_file = %s" % self.pw_file, "restic_cmd = %s" % RESTIC, "media_root = %s" % self.media, "pg_bin_dir = %s" % PG_BIN,
            "config_files = %s" % self.env_file, "check_read_data_subset = 100%", "min_dump_bytes = 1024", "critical_tables = stores_store,orders_order,auth_user",
            "drill_admin_url = %s" % ADMIN_URL, "tmp_dir = %s" % self.root, "keep_daily = 14",
        ]) + "\n")
        self.env = dict(os.environ, RASTISI_BACKUP_CONF=str(self.conf_path))
        subprocess.run([RESTIC, "init"], env=dict(self.env, RESTIC_REPOSITORY=str(self.repo), RESTIC_PASSWORD_FILE=str(self.pw_file)),
                       check=True, capture_output=True)

    def write_env(self, DB_PASSWORD_URL=True, bad_password=False):
        """``bad_password`` points the URL at a database that does not exist (fails under any auth method) and puts a canary secret in it."""
        u = urlparse(ADMIN_URL)
        pw = "CANARY-wrong-pw-7741" if bad_password else (u.password or "")
        db = "no_such_database_%d" % os.getpid() if bad_password else self.db
        url = "postgres://%s%s@%s:%s/%s" % (u.username or "", (":" + pw) if pw else "", u.hostname, u.port or 5432, db)
        self.env_file.write_text("DATABASE_URL=%s\nDJANGO_SECRET_KEY=CANARY-secret-key-0000\n" % url)

    def script(self, *args, check=None):
        proc = subprocess.run([sys.executable, str(HERE.parent / "rastisi_backup.py")] + list(args), capture_output=True, text=True, env=self.env, timeout=900)
        if check is not None:
            self.assertEqual(proc.returncode, check, proc.stdout + proc.stderr)
        return proc

    def snapshots(self, tag=None):
        cmd = [RESTIC, "snapshots", "--json"] + (["--tag", tag] if tag else [])
        out = subprocess.run(cmd, env=dict(self.env, RESTIC_REPOSITORY=str(self.repo), RESTIC_PASSWORD_FILE=str(self.pw_file)), capture_output=True, text=True, check=True).stdout
        return json.loads(out or "[]")

    def drill_databases(self):
        return [l for l in psql("postgres", "SELECT datname FROM pg_database WHERE datname LIKE '%_drill_%'").splitlines() if l]

    # ----------------------------------------------------------------------------------------------------------------
    def test_backup_verifies_itself_and_records_a_verified_state_the_release_tool_can_use(self):
        proc = self.script("run", check=0)
        self.assertIn("verification passed", proc.stdout)
        record = json.loads((self.state / "last_backup.json").read_text())
        self.assertTrue(record["verified"])
        self.assertEqual({s["tags"][0] for s in self.snapshots()}, {"db", "media", "config"})
        status = self.script("status")
        self.assertEqual(status.returncode, 0, status.stdout)

    def test_everything_in_the_repository_is_encrypted(self):
        self.script("run", check=0)
        hits = []
        for p in self.repo.rglob("*"):
            if p.is_file():
                blob = p.read_bytes()
                if PII.encode() in blob or b"store-17" in blob or b"MEDIA7" in blob or b"CANARY-secret-key-0000" in blob:
                    hits.append(p.name)
        self.assertEqual(hits, [], "plaintext found in the off-site repository")
        leftovers = [p for p in self.root.rglob("*") if p.is_file() and p.name.endswith(".dump")]
        self.assertEqual(leftovers, [], "temporary plaintext dumps must be removed")

    def test_restore_drill_restores_into_a_scratch_database_compares_and_cleans_up(self):
        self.script("run", check=0)
        psql(self.db, "INSERT INTO orders_order(buyer,total) VALUES ('after-backup', 1)")           # live moves on; the drill must tolerate it
        (self.media / "stores" / "uploaded-after-backup.jpg").write_bytes(b"new")
        proc = self.script("restore-drill", check=0)
        self.assertIn("restore drill OK", proc.stdout)
        drill = json.loads((self.state / "last_restore_drill.json").read_text())
        self.assertTrue(drill["ok"])
        self.assertEqual(drill["critical"]["orders_order"]["restored"], 300)
        self.assertEqual(drill["critical"]["orders_order"]["live_now"], 301)
        self.assertEqual(self.drill_databases(), [], "the scratch database must be dropped")
        self.assertEqual(psql(self.db, "SELECT count(*) FROM orders_order"), "301", "the live database is untouched by the drill")

    def test_a_failed_backup_keeps_the_previous_good_one_and_prunes_nothing(self):
        self.script("run", check=0)
        good = json.loads((self.state / "last_backup.json").read_text())
        before = {s["id"] for s in self.snapshots()}
        self.write_env(bad_password=True)                     # pg_dump will now fail
        proc = self.script("run")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue((self.state / "BACKUP_FAILED").exists())
        self.assertEqual({s["id"] for s in self.snapshots()}, before, "no snapshot may be removed by a failed run")
        now = json.loads((self.state / "last_backup.json").read_text())
        self.assertEqual(now["db_sha256"], good["db_sha256"], "the record of the last GOOD backup is preserved")
        self.assertNotEqual(self.script("status").returncode, 0, "status must flag the failed run")

    def test_corruption_in_the_repository_is_detected_and_blocks_retention(self):
        self.script("run", check=0)
        for p in (self.repo / "data").rglob("*"):
            if p.is_file():
                os.chmod(str(p), 0o600)                      # restic writes repository files read-only (root in a sandbox hides that)
                blob = bytearray(p.read_bytes())
                blob[len(blob) // 2] ^= 0xFF
                p.write_bytes(bytes(blob))
        proc = self.script("verify")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        again = self.script("run")
        self.assertEqual(again.returncode, 1, "a run on a damaged repository must fail verification, and must not prune")
        self.assertNotIn("retention applied", again.stdout)

    def test_an_empty_or_tiny_dump_is_rejected(self):
        psql("postgres", 'CREATE DATABASE "%s_empty"' % self.db)
        self.addCleanup(lambda: psql("postgres", 'DROP DATABASE IF EXISTS "%s_empty"' % self.db))
        u = urlparse(ADMIN_URL)
        self.env_file.write_text("DATABASE_URL=postgres://%s%s@%s:%s/%s_empty\n" % (u.username, (":" + u.password) if u.password else "", u.hostname, u.port or 5432, self.db))
        proc = self.script("run")
        self.assertEqual(proc.returncode, 1)
        self.assertRegex(proc.stdout + proc.stderr, "suspiciously small|only 0 tables|contains only")
        self.assertFalse((self.state / "last_backup.json").exists())

    def test_no_secret_appears_in_any_output_or_state_file(self):
        self.write_env(bad_password=True)
        outputs = [self.script("run").stdout + self.script("run").stderr]
        self.write_env()
        outputs.append(self.script("run").stdout)
        outputs.append(self.script("restore-drill").stdout)
        outputs.append(self.script("status").stdout)
        for p in self.state.rglob("*"):
            if p.is_file():
                outputs.append(p.read_text(errors="replace"))
        text = "\n".join(outputs)
        for secret in (RESTIC_PASSWORD, "CANARY-wrong-pw-7741", "CANARY-secret-key-0000", urlparse(ADMIN_URL).password or "\0"):
            self.assertNotIn(secret, text)

    def test_the_drill_cannot_target_the_live_database_or_odd_names(self):
        for name in (self.db, "postgres", "rastisi", "bk_live_1; DROP DATABASE x", "x_drill_20260101t000000; --"):
            self.assertFalse(B.DRILL_NAME_RE.match(name) and name == self.db, name)
        self.assertTrue(B.DRILL_NAME_RE.match("rastisi_rc_20261111_drill_20261112t010203"))
        self.assertFalse(B.DRILL_NAME_RE.match("rastisi_rc_20261111"))

    def test_a_second_run_is_refused_while_one_is_in_progress(self):
        import fcntl
        self.state.mkdir(parents=True, exist_ok=True)
        fh = open(str(self.state / "backup.lock"), "a+")
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            proc = self.script("run")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("another backup", proc.stderr)
        finally:
            fh.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
