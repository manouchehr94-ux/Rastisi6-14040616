#!/usr/bin/env python3
"""RastiSi backup, verification and restore drill (standard library + pg_dump/pg_restore/psql + restic).

    run            dump PostgreSQL, snapshot media + essential config into an ENCRYPTED restic repository (off-server), verify, then prune
    verify         check the newest snapshots again (catalogue of the stored dump, integrity subset)
    restore-drill  restore the newest dump into a SCRATCH database, compare with the live one, drop the scratch database
    status         what the last backup/drill did and how old it is

Safety rules:
  * retention (forget/prune) runs ONLY after the new backup passed verification, so a failed run never deletes the last good one;
  * the restore drill can only create and drop databases named <live>_drill_<timestamp>; it refuses the live database name;
  * a deployment never needs a restore: the release tool just reads state/last_backup.json (written only for a verified backup);
  * secrets: DATABASE_URL is read from the application's environment file, passed to pg_* via PG* environment variables (never on the
    command line); the restic password and off-site credentials come from files outside the repository; nothing is printed.

Configuration: /etc/rastisi/backup.conf ([backup] section, no secrets; paths to the secret files). Run as the application user
(it already owns the environment file) from a systemd timer; see docs/deployment/BACKUP_AND_RECOVERY.md.
"""

import argparse
import calendar
import configparser
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))
import rastisi_common as C  # noqa: E402

DEFAULT_CONF = "/etc/rastisi/backup.conf"
CONF_ENV = "RASTISI_BACKUP_CONF"
DRILL_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}_drill_\d{8}t\d{6}$")


class BackupError(Exception):
    pass


class Conf:
    def __init__(self, path=None):
        path = path or os.environ.get(CONF_ENV) or DEFAULT_CONF
        parser = configparser.ConfigParser(interpolation=None)
        if not Path(path).is_file():
            raise BackupError("backup config not found: %s" % path)
        parser.read(path, encoding="utf-8")
        if not parser.has_section("backup"):
            raise BackupError("backup config has no [backup] section")
        self.v = dict(parser.items("backup"))
        for key in ("env_file", "state_dir", "restic_repository", "restic_password_file", "media_root"):
            if not self.v.get(key):
                raise BackupError("backup config is missing %s" % key)

    def get(self, key, default=None):
        return self.v.get(key) or default

    def int(self, key, default):
        return int(self.get(key, default))

    @property
    def state(self):
        return Path(self.v["state_dir"])


def say(msg, secrets=()):
    sys.stdout.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), C.redact(msg, secrets)))
    sys.stdout.flush()


class Tools:
    def __init__(self, conf):
        self.conf = conf
        self.app_env = C.parse_env_file(conf.get("env_file"))
        self.secrets = C.secret_values(self.app_env)
        url = self.app_env.get("DATABASE_URL", "")
        parsed = urlparse(url)
        if parsed.scheme not in ("postgres", "postgresql") or not parsed.path.strip("/"):
            raise BackupError("DATABASE_URL in the environment file is not a postgres:// URL")
        self.db = parsed.path.strip("/")
        self.pg_env = {"PGHOST": parsed.hostname or "", "PGPORT": str(parsed.port or 5432), "PGUSER": unquote(parsed.username or ""),
                       "PGPASSWORD": unquote(parsed.password or ""), "PGDATABASE": self.db, "PGCONNECT_TIMEOUT": "15"}
        self.pg_bin = conf.get("pg_bin_dir") or ""
        restic_env = C.parse_env_file(conf.get("restic_env_file")) if conf.get("restic_env_file") else {}
        self.restic_env = dict(restic_env, RESTIC_REPOSITORY=conf.get("restic_repository"), RESTIC_PASSWORD_FILE=conf.get("restic_password_file"))
        self.secrets |= C.secret_values(restic_env)
        self.restic = conf.get("restic_cmd", "restic").split()

    def pg(self, name):
        return os.path.join(self.pg_bin, name) if self.pg_bin else name

    def base_env(self):
        return {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR")}

    def run(self, cmd, env_extra=None, timeout=3600, stdin=None, stdout=None, check=True, what=""):
        env = self.base_env()
        env.update(env_extra or {})
        proc = subprocess.run(cmd, env=env, capture_output=stdout is None, text=stdout is None, timeout=timeout, stdin=stdin, stdout=stdout)
        if check and proc.returncode != 0:
            err = C.redact(((proc.stderr or "") if stdout is None else "")[-800:], self.secrets)
            raise BackupError("%s failed (exit %d): %s" % (what or cmd[0], proc.returncode, err.strip()))
        return proc

    def restic_run(self, *args, **kw):
        return self.run(self.restic + list(args), env_extra=self.restic_env, what="restic " + (args[0] if args else ""), **kw)


# ======================================================================================================================== run
def lock_file(conf):
    conf.state.mkdir(parents=True, exist_ok=True)
    fh = open(str(conf.state / "backup.lock"), "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise BackupError("another backup/drill is running")
    return fh


def write_state(conf, name, data):
    C.atomic_write_json(conf.state / name, data, mode=0o640)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def snapshot_info(tools, tag):
    proc = tools.restic_run("snapshots", "--json", "--tag", tag, "--latest", "1")
    snaps = json.loads(proc.stdout or "[]")
    if not snaps:
        raise BackupError("no %s snapshot found after backup" % tag)
    return snaps[-1]


def cmd_run(conf, args):
    lock = lock_file(conf)
    tools = Tools(conf)
    started = time.time()
    failure_marker = conf.state / "BACKUP_FAILED"
    work = Path(tempfile.mkdtemp(prefix="rastisi-backup-", dir=conf.get("tmp_dir") or None))
    os.chmod(str(work), 0o700)
    try:
        say("backup started (database %s)" % tools.db, tools.secrets)
        # 1. database
        dump = work / "db" / "rastisi.dump"
        dump.parent.mkdir()
        tools.run([tools.pg("pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(dump)], env_extra=tools.pg_env, what="pg_dump")
        size = dump.stat().st_size
        if size < conf.int("min_dump_bytes", 2048):
            raise BackupError("the dump is suspiciously small (%d bytes)" % size)
        toc = tools.run([tools.pg("pg_restore"), "--list", str(dump)], what="pg_restore --list").stdout
        tables = len(re.findall(r"\bTABLE DATA\b", toc))
        if tables < conf.int("min_tables", 1):
            raise BackupError("the dump contains only %d tables" % tables)
        digest = C.sha256_file(dump)
        (work / "db" / "MANIFEST.json").write_text(json.dumps({"database": tools.db, "taken_at": now_iso(), "bytes": size, "sha256": digest,
                                                              "tables_with_data": tables}, indent=2) + "\n")
        say("database dumped: %d bytes, %d tables with data, sha256 %s" % (size, tables, digest[:12]))
        # 2. config (secrets: it lands only in the encrypted repository)
        cfgdir = work / "config"
        cfgdir.mkdir()
        for label in filter(None, [x.strip() for x in (conf.get("config_files") or "").split(",")]):
            src = Path(label)
            if src.is_file():
                shutil.copy2(str(src), str(cfgdir / src.name))
        # 3. snapshots
        tools.restic_run("backup", "--tag", "db", "--host", conf.get("host_label", "rastisi"), str(work / "db"), timeout=7200)
        if any(cfgdir.iterdir()):
            tools.restic_run("backup", "--tag", "config", "--host", conf.get("host_label", "rastisi"), str(cfgdir), timeout=1800)
        media = Path(conf.get("media_root"))
        if media.is_dir():
            tools.restic_run("backup", "--tag", "media", "--host", conf.get("host_label", "rastisi"), str(media), timeout=14400)
        else:
            raise BackupError("media_root %s does not exist" % media)
        # 4. verification BEFORE anything is pruned
        db_snap = snapshot_info(tools, "db")
        media_snap = snapshot_info(tools, "media")
        verify_stored_dump(tools, conf, digest)
        subset = conf.get("check_read_data_subset", "5%")
        tools.restic_run("check", "--read-data-subset", subset, timeout=7200)
        say("verification passed (stored dump catalogue + restic integrity subset %s)" % subset)
        write_state(conf, "last_backup.json", {
            "finished_at": now_iso(), "verified": True, "db_snapshot": db_snap["short_id"], "media_snapshot": media_snap["short_id"],
            "db_bytes": size, "db_sha256": digest, "seconds": int(time.time() - started),
        })
        if failure_marker.exists():
            failure_marker.unlink()
        # 5. retention only now
        if conf.get("retention", "yes") == "yes":
            tools.restic_run("forget", "--prune", "--keep-daily", conf.get("keep_daily", "14"), "--keep-weekly", conf.get("keep_weekly", "8"),
                             "--keep-monthly", conf.get("keep_monthly", "12"), "--group-by", "tags", timeout=7200)
            say("retention applied")
        say("backup finished OK in %ds" % (time.time() - started))
        return 0
    except BackupError as exc:
        failure_marker.write_text("%s %s\n" % (now_iso(), C.redact(str(exc), tools.secrets)))
        info = C.read_json(conf.state / "last_backup.json", {})
        if info:
            info["verified_newer_failed_at"] = now_iso()
            write_state(conf, "last_backup.json", info)
        say("BACKUP FAILED: %s (the previous good backup was not touched)" % exc, tools.secrets)
        alert(conf, "RastiSi backup FAILED", str(exc), tools.secrets)
        return 1
    finally:
        shutil.rmtree(str(work), ignore_errors=True)
        lock.close()


def find_dump_path(tools):
    """Path of the dump inside the newest db snapshot."""
    ls = tools.restic_run("ls", "latest", "--tag", "db", "--json").stdout
    path = None
    for line in ls.splitlines():
        try:
            node = json.loads(line)
        except ValueError:
            continue
        if node.get("type") == "file" and node.get("path", "").endswith("/rastisi.dump"):
            path = node["path"]
    if not path:
        raise BackupError("the dump is missing from the newest snapshot")
    return path


def fetch_stored_dump(tools, dest):
    path = find_dump_path(tools)
    with open(str(dest), "wb") as out:
        tools.run(tools.restic + ["dump", "latest", "--tag", "db", path], env_extra=tools.restic_env, stdout=out, what="restic dump")


def verify_stored_dump(tools, conf, expected_sha):
    """Read the dump back OUT of the repository: it must be the one we made and pg_restore must be able to read its catalogue."""
    tmp = Path(tempfile.mkdtemp(prefix="rastisi-verify-", dir=conf.get("tmp_dir") or None))
    try:
        os.chmod(str(tmp), 0o700)
        fetch_stored_dump(tools, tmp / "d.dump")
        if C.sha256_file(tmp / "d.dump") != expected_sha:
            raise BackupError("the dump read back from the repository does not match what was dumped")
        tools.run([tools.pg("pg_restore"), "--list", str(tmp / "d.dump")], what="pg_restore --list (stored dump)")
    finally:
        shutil.rmtree(str(tmp), ignore_errors=True)


def alert(conf, subject, body, secrets=()):
    cmd = conf.get("alert_cmd")
    to = conf.get("alert_to")
    if not cmd or not to:
        return
    try:
        subprocess.run(cmd.split() + [subject, to], input=C.redact(body, secrets), text=True, timeout=60, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        sys.stderr.write("ALERT DELIVERY FAILED\n")


# =============================================================================================================== verify / drill
def cmd_verify(conf, args):
    lock = lock_file(conf)
    tools = Tools(conf)
    try:
        info = C.read_json(conf.state / "last_backup.json", {})
        if not info.get("db_sha256"):
            raise BackupError("no verified backup is recorded")
        verify_stored_dump(tools, conf, info["db_sha256"])
        tools.restic_run("check", "--read-data-subset", conf.get("check_read_data_subset", "5%"), timeout=7200)
        say("stored backup re-verified")
        return 0
    except BackupError as exc:
        say("VERIFY FAILED: %s" % exc, tools.secrets)
        alert(conf, "RastiSi backup verification FAILED", str(exc), tools.secrets)
        return 1
    finally:
        lock.close()


def psql(tools, db, sql, admin_env=None):
    env = dict(admin_env or tools.pg_env, PGDATABASE=db)
    proc = tools.run([tools.pg("psql"), "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], env_extra=env, what="psql")
    return proc.stdout.strip()


def cmd_restore_drill(conf, args):
    lock = lock_file(conf)
    tools = Tools(conf)
    scratch = "%s_drill_%s" % (tools.db[:30].lower(), time.strftime("%Y%m%dt%H%M%S", time.gmtime()))
    if scratch == tools.db or not DRILL_NAME_RE.match(scratch):
        raise BackupError("refusing: %r is not a valid scratch database name" % scratch)
    admin_env = dict(tools.pg_env)
    admin_url = conf.get("drill_admin_url")
    if admin_url:
        p = urlparse(admin_url)
        admin_env.update(PGHOST=p.hostname or "", PGPORT=str(p.port or 5432), PGUSER=unquote(p.username or ""), PGPASSWORD=unquote(p.password or ""))
        tools.secrets.add(unquote(p.password or ""))
    tmp = Path(tempfile.mkdtemp(prefix="rastisi-drill-", dir=conf.get("tmp_dir") or None))
    os.chmod(str(tmp), 0o700)
    created = False
    started = time.time()
    try:
        say("restore drill: restoring the newest dump into scratch database %s" % scratch)
        fetch_stored_dump(tools, tmp / "d.dump")
        psql(tools, "postgres", 'CREATE DATABASE "%s"' % scratch, admin_env)
        created = True
        tools.run([tools.pg("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", scratch, str(tmp / "d.dump")],
                  env_extra=dict(admin_env, PGDATABASE=scratch), timeout=7200, what="pg_restore")
        # compare with the live database
        tables = [t for t in psql(tools, scratch, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1", admin_env).splitlines() if t]
        live_tables = [t for t in psql(tools, tools.db, "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1").splitlines() if t]
        missing = sorted(set(live_tables) - set(tables))
        if missing:
            raise BackupError("tables missing from the restored copy: %s" % ", ".join(missing[:10]))
        critical = [t for t in (conf.get("critical_tables") or "stores_store,orders_order,auth_user,subscriptions_storesubscription,billing_subscriptioninvoice").split(",") if t.strip() in tables]
        report = {}
        for table in critical:
            live = int(psql(tools, tools.db, 'SELECT count(*) FROM "%s"' % table))
            restored = int(psql(tools, scratch, 'SELECT count(*) FROM "%s"' % table, admin_env))
            report[table] = {"live_now": live, "restored": restored}
            if restored == 0 and live > 0 and live > conf.int("drill_empty_tolerance_rows", 0):
                raise BackupError("critical table %s is empty in the restored copy but has %d rows live" % (table, live))
        # sample media files against the live tree
        sample = verify_media_sample(tools, conf, tmp)
        write_state(conf, "last_restore_drill.json", {"finished_at": now_iso(), "ok": True, "scratch_db": scratch, "tables": len(tables),
                                                       "critical": report, "media_sample": sample, "seconds": int(time.time() - started)})
        say("restore drill OK: %d tables, critical counts %s, media sample %s" % (len(tables), json.dumps(report), sample))
        return 0
    except BackupError as exc:
        write_state(conf, "last_restore_drill.json", {"finished_at": now_iso(), "ok": False, "error": C.redact(str(exc), tools.secrets)})
        say("RESTORE DRILL FAILED: %s" % exc, tools.secrets)
        alert(conf, "RastiSi restore drill FAILED", str(exc), tools.secrets)
        return 1
    finally:
        if created:
            try:
                assert DRILL_NAME_RE.match(scratch) and scratch != tools.db
                psql(tools, "postgres", 'DROP DATABASE IF EXISTS "%s"' % scratch, admin_env)
                say("scratch database dropped")
            except Exception as exc:   # noqa: BLE001
                say("WARNING: could not drop %s: %s" % (scratch, exc.__class__.__name__))
        shutil.rmtree(str(tmp), ignore_errors=True)
        lock.close()


def verify_media_sample(tools, conf, tmp):
    """Compare a sample of live media files with the copies inside the backup. Files are streamed out one by one with ``restic dump``:
    no directory tree and no extended attributes are restored (that fails on SELinux hosts and is pointless for a content check)."""
    media = Path(conf.get("media_root"))
    files = sorted(p for p in media.rglob("*") if p.is_file())
    if not files:
        return {"checked": 0, "mismatched": 0}
    step = max(1, len(files) // conf.int("media_sample", 20))
    picked = files[::step][: conf.int("media_sample", 20)]
    taken_at = C.read_json(conf.state / "last_backup.json", {}).get("finished_at", "")
    taken = calendar.timegm(time.strptime(taken_at, "%Y-%m-%dT%H:%M:%SZ")) if taken_at else 0
    bad, newer, checked = 0, 0, 0
    for f in picked:
        out_path = tmp / "media-sample"
        with open(str(out_path), "wb") as out:
            proc = tools.run(tools.restic + ["dump", "latest", "--tag", "media", str(f)], env_extra=tools.restic_env, stdout=out, check=False)
        if proc.returncode != 0:
            if f.stat().st_mtime > taken:
                newer += 1                                   # uploaded after the backup: expected, not a failure
                continue
            raise BackupError("a media file that existed at backup time is missing from the backup: %s" % f.relative_to(media))
        checked += 1
        if C.sha256_file(out_path) != C.sha256_file(f):
            if f.stat().st_mtime > taken:
                newer += 1
            else:
                bad += 1
    if bad:
        raise BackupError("%d restored media files differ from the live ones" % bad)
    return {"checked": checked, "mismatched": bad, "newer_than_backup": newer}


def cmd_status(conf, args):
    last = C.read_json(conf.state / "last_backup.json", {})
    drill = C.read_json(conf.state / "last_restore_drill.json", {})
    age = None
    if last.get("finished_at"):
        age = int((time.time() - calendar.timegm(time.strptime(last["finished_at"], "%Y-%m-%dT%H:%M:%SZ"))) / 60)
    print(json.dumps({"last_backup": last, "backup_age_minutes": age, "last_restore_drill": drill,
                      "backup_failed_marker": (conf.state / "BACKUP_FAILED").exists()}, indent=2, sort_keys=True))
    max_age = conf.int("max_age_minutes", 26 * 60)
    return 0 if last.get("verified") and age is not None and age <= max_age and not (conf.state / "BACKUP_FAILED").exists() else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rastisi_backup")
    ap.add_argument("cmd", choices=["run", "verify", "restore-drill", "status"])
    args = ap.parse_args(argv)
    try:
        conf = Conf()
        return {"run": cmd_run, "verify": cmd_verify, "restore-drill": cmd_restore_drill, "status": cmd_status}[args.cmd](conf, args)
    except BackupError as exc:
        sys.stderr.write("backup error: %s\n" % C.redact(str(exc)))
        return 2


if __name__ == "__main__":
    sys.exit(main())
