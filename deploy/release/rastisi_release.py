#!/usr/bin/env python3
"""RastiSi release orchestrator (standard library only, Python 3.8+). Runs as the unprivileged deploy user, never as root.

    stage     unpack a verified artifact into an immutable release directory and build/reuse its virtualenv
    activate  gate -> migrate (only when allowed) -> publish static -> atomic switch -> restart -> verify -> keep or roll back
    rollback  switch back to the previous (or a named) release and verify it
    status    what is running, what can be rolled back to, any incident
    list / prune / resolve / cutover / check-config

Design rules (the reasons are in docs/deployment/RELEASE_PIPELINE.md):
  * one deployment at a time: an exclusive flock; a second one exits 75 immediately;
  * the code is immutable and keyed by commit; configuration, media, database, Redis and secrets live outside the release;
  * the previous release is switched back to automatically ONLY when that is provably safe (no migration was applied, or only
    additive ones). Otherwise the tool stops, writes state/INCIDENT and exits 2 for a human;
  * an interrupted run (SSH loss does not matter, the run is detached; a killed process does) leaves an in_progress marker, which the
    next run turns into an INCIDENT instead of guessing;
  * nothing here prints a secret: the environment file is read only by the app-side helper, output is redacted.
"""

import argparse
import calendar
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rastisi_common as C  # noqa: E402

DESTRUCTIVE_PHRASE_PREFIX = "I-ACCEPT-DESTRUCTIVE-MIGRATION-"
UNSAFE_ROLLBACK_PHRASE = "I-UNDERSTAND-THE-DATABASE-MAY-NOT-MATCH-THE-OLD-CODE"


class Abort(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# =================================================================================================================== state
class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.dir = cfg.state
        self.status_file = self.dir / "status.json"
        self.active_file = self.dir / "active.json"
        self.history_file = self.dir / "history.jsonl"
        self.incident_file = self.dir / "INCIDENT"
        self.in_progress_file = self.dir / "in_progress.json"
        self.lock_file = self.dir / "deploy.lock"

    def ensure(self):
        for d in (self.cfg.base, self.cfg.releases, self.cfg.venvs, self.cfg.staging, self.dir, self.dir / "runs"):
            d.mkdir(parents=True, exist_ok=True)

    def statuses(self):
        return C.read_json(self.status_file, {})

    def set_status(self, release_id, status, **extra):
        data = self.statuses()
        data[release_id] = dict(extra, status=status, updated=C.utc_stamp())
        C.atomic_write_json(self.status_file, data)

    def active(self):
        return C.read_json(self.active_file, {})

    def set_active(self, **data):
        C.atomic_write_json(self.active_file, data)

    def history(self, **event):
        event.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        line = json.dumps(event, sort_keys=True)
        with open(str(self.history_file), "a", encoding="utf-8") as fh:
            fh.write(C.redact(line) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def incident(self):
        return self.incident_file.read_text(encoding="utf-8") if self.incident_file.exists() else None

    def raise_incident(self, reason, **details):
        body = {"reason": reason, "at": C.utc_stamp(), "details": details}
        self.incident_file.write_text(C.redact(json.dumps(body, indent=2, sort_keys=True)) + "\n", encoding="utf-8")
        self.history(event="incident", reason=reason)

    def mark_in_progress(self, run_id, release_id, phase):
        C.atomic_write_json(self.in_progress_file, {"run_id": run_id, "release": release_id, "phase": phase, "at": C.utc_stamp()})

    def clear_in_progress(self):
        try:
            self.in_progress_file.unlink()
        except FileNotFoundError:
            pass


class Lock:
    """Exclusive, non-blocking, released automatically when the process dies."""

    def __init__(self, path):
        self.path = path
        self.fh = None

    def acquire(self):
        self.fh = open(str(self.path), "a+")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            self.fh = None
            return False
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write("pid=%d since=%s\n" % (os.getpid(), C.utc_stamp()))
        self.fh.flush()
        return True

    def release(self):
        if self.fh:
            try:
                fcntl.flock(self.fh, fcntl.LOCK_UN)
            finally:
                self.fh.close()
                self.fh = None


# =================================================================================================================== helpers
class Tool:
    """The three outside worlds the orchestrator talks to: the app-side helper (as the app user), systemctl, and the smoke runner."""

    def __init__(self, cfg, say):
        self.cfg = cfg
        self.say = say

    def _run(self, cmd, timeout, input_text=None):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)
        except subprocess.TimeoutExpired:
            return 124, "", "timed out after %ss" % timeout
        return proc.returncode, proc.stdout, proc.stderr

    def app(self, *args, timeout=600):
        """Run the privileged-boundary helper. Returns (ok, json_result)."""
        cmd = self.cfg.command("app_runner", "") + list(args)
        rc, out, err = self._run(cmd, timeout)
        for line in (err or "").splitlines():
            self.say("    | " + line)
        result = {}
        for line in reversed((out or "").strip().splitlines()):
            try:
                result = json.loads(line)
                break
            except ValueError:
                continue
        ok = rc == 0 and bool(result.get("ok", False))
        if not ok and not result:
            result = {"ok": False, "error": "helper exited %s without a result" % rc}
        return ok, result

    def systemctl(self, verb):
        cmd = self.cfg.command("systemctl", "sudo -n /usr/bin/systemctl") + [verb, self.cfg.get("service")]
        rc, out, err = self._run(cmd, 120)
        return rc, (out or "").strip(), (err or "").strip()

    def service_active(self):
        rc, out, _ = self.systemctl("is-active")
        return rc == 0 and out == "active"


def release_dir(cfg, release_id):
    if not C.RELEASE_ID_RE.match(release_id or ""):
        raise Abort(C.EXIT_POLICY, "invalid release id: %r" % release_id)
    return cfg.releases / release_id


def read_release(cfg, release_id):
    meta = C.read_json(release_dir(cfg, release_id) / "release.json")
    if not meta:
        raise Abort(C.EXIT_POLICY, "release %s is not staged" % release_id)
    return meta


def current_release_id(cfg):
    link = cfg.current_link
    if not link.is_symlink():
        return None
    name = os.path.basename(os.readlink(str(link)).rstrip("/"))
    return name if C.RELEASE_ID_RE.match(name) else None


def previous_release_id(cfg):
    link = cfg.previous_link
    if not link.is_symlink():
        return None
    name = os.path.basename(os.readlink(str(link)).rstrip("/"))
    return name if C.RELEASE_ID_RE.match(name) else None


# ===================================================================================================================== stage
def cmd_stage(cfg, args):
    st = State(cfg)
    st.ensure()
    artifact = Path(args.artifact)
    if not artifact.is_file():
        raise Abort(C.EXIT_POLICY, "artifact not found: %s" % artifact)
    if not C.SHA256_RE.match(args.sha256 or ""):
        raise Abort(C.EXIT_POLICY, "--sha256 must be the 64-hex digest computed by the build job")
    if not C.SHA_RE.match(args.sha or ""):
        raise Abort(C.EXIT_POLICY, "--sha must be a full 40-hex commit id")
    actual = C.sha256_file(artifact)
    if actual != args.sha256:
        raise Abort(C.EXIT_POLICY, "artifact checksum mismatch (expected %s, got %s)" % (args.sha256, actual))
    release_id = "%s-%s" % (C.utc_stamp(), args.sha[:12])
    final = cfg.releases / release_id
    work = cfg.releases / (".staging-" + release_id)
    if work.exists():
        shutil.rmtree(str(work))
    work.mkdir(parents=True)
    try:
        try:
            C.safe_extract_tar(artifact, work)
        except (ValueError, tarfile.TarError, OSError) as exc:
            raise Abort(C.EXIT_POLICY, "artifact rejected: %s" % exc)
        manifest = C.read_json(work / "release-manifest.json")
        if not manifest or manifest.get("schema") != 1:
            raise Abort(C.EXIT_POLICY, "artifact has no valid release-manifest.json")
        if manifest.get("sha") != args.sha:
            raise Abort(C.EXIT_POLICY, "manifest commit %s does not match the requested commit" % manifest.get("sha"))
        wanted_python = manifest.get("python")
        have_python = "%d.%d" % sys.version_info[:2]
        configured = cfg.get("python")
        if wanted_python and not configured and wanted_python != have_python:
            raise Abort(C.EXIT_POLICY, "artifact was built for Python %s, this host's python3 is %s (set python= in the config)" % (wanted_python, have_python))
        bad = []
        for rel, digest in sorted(manifest.get("files", {}).items()):
            p = work / rel
            if not p.is_file() or C.sha256_file(p) != digest:
                bad.append(rel)
                if len(bad) >= 5:
                    break
        if bad:
            raise Abort(C.EXIT_POLICY, "artifact content does not match its manifest: %s" % ", ".join(bad))
        lock_text = (work / "requirements.lock").read_text(encoding="utf-8")
        import hashlib
        lock_key = hashlib.sha256(lock_text.encode("utf-8")).hexdigest()[:16]
        if manifest.get("lock_sha256") and not manifest["lock_sha256"].startswith(lock_key):
            raise Abort(C.EXIT_POLICY, "requirements.lock does not match the manifest")
        venv = ensure_venv(cfg, work, lock_key, manifest)
        # compile now so the app user never needs write access to the code
        subprocess.run([str(venv / "bin" / "python"), "-m", "compileall", "-q", str(work / "app")], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (work / "venv").symlink_to(os.path.relpath(str(venv), str(work)))
        meta = dict(manifest, id=release_id, staged_at=C.utc_stamp(), venv_key=lock_key, kind="release")
        meta.pop("files", None)
        C.atomic_write_json(work / "release.json", meta, mode=0o644)
        for sub in (work / "wheelhouse",):
            if sub.exists():
                shutil.rmtree(str(sub))                      # only needed to build the venv
        os.rename(str(work), str(final))
        make_readonly(final)
    except BaseException:
        shutil.rmtree(str(work), ignore_errors=True)
        raise
    st.set_status(release_id, "staged", sha=args.sha)
    st.history(event="staged", release=release_id, sha=args.sha, actor=args.actor or "")
    C.log("staged release %s (commit %s, migrations: %s)" % (release_id, args.sha[:12], (manifest.get("migration_report") or {}).get("level", "?")))
    print(json.dumps({"ok": True, "release": release_id}))
    return C.EXIT_OK


def make_readonly(path):
    """Code is read-only once staged: directories r-x for owner and group, files r-- (r-x when executable). Failure to chmod is not fatal."""
    for root, dirs, files in os.walk(str(path), followlinks=False):
        for name in files:
            p = os.path.join(root, name)
            if not os.path.islink(p):
                try:
                    os.chmod(p, 0o550 if os.stat(p).st_mode & 0o111 else 0o440)
                except OSError:
                    pass
        for name in dirs:
            p = os.path.join(root, name)
            if not os.path.islink(p):
                try:
                    os.chmod(p, 0o550)
                except OSError:
                    pass
    try:
        os.chmod(str(path), 0o550)
    except OSError:
        pass


def ensure_venv(cfg, work, lock_key, manifest):
    """The virtualenv is keyed by the hash of the lock file and shared by every release that uses the same dependencies.

    It is built IN PLACE (never built elsewhere and renamed: console scripts such as gunicorn hard-code the interpreter path in
    their shebang, so a renamed venv would fail at service start with 'bad interpreter'). A blocking flock serialises concurrent
    stages; the '.complete' marker is written last, so a half-built directory is never used."""
    venv = cfg.venvs / lock_key
    cfg.venvs.mkdir(parents=True, exist_ok=True)
    guard = open(str(cfg.state / "venv.lock"), "a+")
    try:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if (venv / ".complete").exists():
            return venv
        if venv.exists():
            shutil.rmtree(str(venv))
        python = cfg.get("python") or sys.executable
        C.log("building virtualenv %s from the hashed lock file (offline wheelhouse)" % lock_key)
        cmds = [
            [python, "-m", "venv", str(venv)],
            [str(venv / "bin" / "pip"), "install", "--no-index", "--find-links", str(work / "wheelhouse"), "--require-hashes", "--no-deps",
             "--disable-pip-version-check", "-q", "-r", str(work / "requirements.lock")],
            [str(venv / "bin" / "pip"), "check"],
        ]
        for cmd in cmds:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                shutil.rmtree(str(venv), ignore_errors=True)
                raise Abort(C.EXIT_POLICY, "virtualenv build failed at '%s': %s" % (" ".join(cmd[:3]), C.redact((proc.stderr or proc.stdout).strip()[-600:])))
        (venv / ".complete").write_text(C.utc_stamp() + "\n", encoding="utf-8")
        return venv
    finally:
        guard.close()


# ================================================================================================================== activate
def new_run_id():
    import binascii
    return "%s-%s" % (C.utc_stamp(), binascii.hexlify(os.urandom(4)).decode())


class Runner:
    """One activation or rollback. Keeps the log, the run record and the phase markers."""

    def __init__(self, cfg, st, run_id, action):
        self.cfg, self.st, self.run_id, self.action = cfg, st, run_id, action
        self.started = time.time()
        self.run_dir = st.dir / "runs" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.tool = Tool(cfg, self.say)

    def say(self, msg):
        C.log(msg)

    def finish(self, code, result, **extra):
        data = dict(extra, run_id=self.run_id, action=self.action, exit_code=code, result=result,
                    seconds=int(time.time() - self.started), finished=C.utc_stamp())
        C.atomic_write_json(self.run_dir / "result.json", data, mode=0o644)
        (self.run_dir / "exit_code").write_text("%d\n" % code, encoding="utf-8")
        self.st.history(event=self.action, **{k: v for k, v in data.items() if k != "action"})
        return code


def write_exit_only(st, run_id, code):
    run_dir = st.dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "exit_code").write_text("%d\n" % code, encoding="utf-8")


def preflight(cfg, st, runner, rel_id, rel_meta, args):
    inc = st.incident()
    if inc:
        raise Abort(C.EXIT_NEEDS_HUMAN, "an unresolved INCIDENT exists (state/INCIDENT). A person must verify the system and run 'resolve'. " + inc.strip()[:300])
    if st.in_progress_file.exists():
        marker = C.read_json(st.in_progress_file, {})
        st.raise_incident("a previous deployment was interrupted", marker=marker)
        raise Abort(C.EXIT_NEEDS_HUMAN, "a previous run died mid-way (%s). INCIDENT written; verify the system, then 'resolve'." % marker)
    min_free = cfg.int("min_free_mb", 500) * 1024 * 1024
    for path in (cfg.base, Path(cfg.get("static_root") or cfg.base)):
        if path.exists():
            usage = shutil.disk_usage(str(path))
            if usage.free < min_free:
                raise Abort(C.EXIT_POLICY, "less than %d MB free on %s" % (min_free // (1024 * 1024), path))
    ok, res = runner.tool.app("envcheck", timeout=60)
    if not ok:
        raise Abort(C.EXIT_POLICY, "environment check failed: %s" % res.get("error", res))
    ok, res = runner.tool.app("check", "--release", rel_id, timeout=300)
    if not ok:
        raise Abort(C.EXIT_POLICY, "the new release does not pass 'manage.py check' with the production environment: %s" % res.get("error", ""))
    ok, res = runner.tool.app("healthcheck", "--release", rel_id, "--pre", timeout=120)
    if not ok:
        raise Abort(C.EXIT_POLICY, "pre-flight health check failed (database/Redis/paths): %s" % res.get("failures", res))
    runner.say("pre-flight OK")


def backup_is_fresh(cfg, st):
    info = C.read_json(cfg.get("backup_record") or (st.dir / "last_backup.json"), {})
    if not info.get("verified"):
        return False, "no verified backup recorded"
    try:
        finished = calendar.timegm(time.strptime(info["finished_at"], "%Y-%m-%dT%H:%M:%SZ"))
    except (KeyError, ValueError):
        return False, "backup record is unreadable"
    age = (time.time() - finished) / 60.0
    limit = cfg.int("backup_max_age_minutes", 90)
    if age > limit:
        return False, "last verified backup is %d min old (limit %d)" % (age, limit)
    return True, "verified backup %d min old" % age


def plan_migrations(cfg, st, runner, rel_id, rel_meta, args):
    ok, res = runner.tool.app("migrate-plan", "--release", rel_id, timeout=300)
    if not ok:
        raise Abort(C.EXIT_POLICY, "could not compute the migration plan: %s" % res.get("error", res))
    plan = res.get("plan", [])
    report = rel_meta.get("migration_report") or {}
    announced = set(report.get("new_migrations", []))
    # A database that is behind (for example after a skipped release) shows up as migrations the report did not announce.
    unexpected = sorted(set(plan) - announced)
    if unexpected:
        raise Abort(C.EXIT_POLICY, "Django would apply migrations that the reviewed release report does not list: %s" % ", ".join(unexpected[:8]))
    return plan, report


def migration_policy(cfg, st, runner, plan, report, rel_meta, args):
    if not plan:
        runner.say("no pending migrations: the database schema is not touched")
        return
    level = report.get("level", "REVIEW")
    runner.say("pending migrations (%d, level %s): %s" % (len(plan), level, ", ".join(plan[:10])))
    if level not in ("NONE", "ADDITIVE"):
        raise Abort(C.EXIT_POLICY, "online migration level %s is unsafe: use the documented offline migration procedure with web and background writers stopped" % level)
    if level in ("REVIEW", "DESTRUCTIVE") and not args.allow_migrations:
        raise Abort(C.EXIT_POLICY, "migration level %s needs --allow-migrations (explicit owner approval)" % level)
    if level == "DESTRUCTIVE":
        phrase = DESTRUCTIVE_PHRASE_PREFIX + rel_meta["sha"][:12]
        if args.destructive_ack != phrase:
            raise Abort(C.EXIT_POLICY, "destructive migration needs --destructive-ack %s" % phrase)
    fresh, why = backup_is_fresh(cfg, st)
    if not fresh and not args.skip_backup_check_ack:
        raise Abort(C.EXIT_POLICY, "a verified, recent backup is required before migrating: %s" % why)
    runner.say("backup gate: %s" % why)


def verify_release(cfg, runner, rel_id, deadline_seconds):
    """Service active + deploy_healthcheck reports THIS release + version-specific HTTP smoke tests; retried until the deadline."""
    deadline = time.time() + deadline_seconds
    last = "not started"
    while True:
        if runner.tool.service_active():
            ok, res = runner.tool.app("healthcheck", "--release", rel_id, "--post", "--expect-release", rel_id, timeout=120)
            if ok:
                ok2, res2 = runner.tool.app(
                    "smoke", "--release", rel_id, "--base-url", cfg.get("smoke_base_url") or "http://127.0.0.1:%s" % cfg.get("port"),
                    "--host", cfg.get("smoke_host") or "", "--expect-release", rel_id, timeout=240)
                if ok2:
                    return True, res2
                last = "smoke: %s" % (res2.get("failures") or res2.get("error") or res2)
            else:
                last = "healthcheck: %s" % (res.get("failures") or res.get("error") or res)
        else:
            last = "service %s is not active" % cfg.get("service")
        if time.time() >= deadline:
            return False, last
        time.sleep(3)


def switch_to(cfg, st, runner, target_id, previous_id):
    """Atomic symlink flip, static publish, restart. Raises on failure to restart."""
    ok, res = runner.tool.app("publish-static", "--release", target_id, timeout=600)
    if not ok:
        raise Abort(C.EXIT_FAILED_SAFE, "static publish failed: %s" % res.get("error", res))
    if previous_id:
        C.atomic_symlink(os.path.join("releases", previous_id), cfg.previous_link)
    C.atomic_symlink(os.path.join("releases", target_id), cfg.current_link)
    runner.say("current -> %s" % target_id)
    rc, out, err = runner.tool.systemctl("restart")
    if rc != 0:
        raise Abort(C.EXIT_FAILED_SAFE, "restart of %s failed: %s" % (cfg.get("service"), C.redact(err or out)))


def restore_link(cfg, st, runner, restore_id, previous_id):
    """Put ``current`` back on a known release (used by rollback and by failed activations)."""
    C.atomic_symlink(os.path.join("releases", restore_id), cfg.current_link)
    if previous_id:
        C.atomic_symlink(os.path.join("releases", previous_id), cfg.previous_link)
    ok, res = runner.tool.app("publish-static", "--release", restore_id, timeout=600)
    if not ok:
        runner.say("WARNING: could not republish static files of %s: %s" % (restore_id, res.get("error", res)))
    rc, out, err = runner.tool.systemctl("restart")
    return rc == 0


def cmd_activate(cfg, args):
    st = State(cfg)
    st.ensure()
    run_id = args.run_id or new_run_id()
    lock = Lock(st.lock_file)
    if not lock.acquire():
        print(json.dumps({"ok": False, "busy": True, "message": "another deployment is running"}))
        C.log("another deployment holds the lock; nothing was changed")
        write_exit_only(st, run_id, C.EXIT_BUSY)
        return C.EXIT_BUSY
    runner = Runner(cfg, st, run_id, "activate")
    try:
        return do_activate(cfg, st, runner, args)
    except Abort as exc:
        runner.say("STOPPED: %s" % exc.message)
        print(json.dumps({"ok": False, "message": exc.message, "exit": exc.code}))
        return runner.finish(exc.code, "stopped", message=C.redact(exc.message), release=args.id)
    except BaseException as exc:                                  # noqa: BLE001 — any crash must be recorded
        runner.say("INTERNAL ERROR: %s" % exc.__class__.__name__)
        runner.say(C.redact(traceback.format_exc()))
        st.raise_incident("internal error during activation", release=args.id, error=exc.__class__.__name__)
        print(json.dumps({"ok": False, "message": "internal error", "exit": C.EXIT_NEEDS_HUMAN}))
        return runner.finish(C.EXIT_NEEDS_HUMAN, "internal-error", release=args.id)
    finally:
        lock.release()


def do_activate(cfg, st, runner, args):
    rel_id = args.id
    rel_meta = read_release(cfg, rel_id)
    if args.expect_sha and rel_meta.get("sha") != args.expect_sha:
        raise Abort(C.EXIT_POLICY, "release %s is commit %s, not the approved %s" % (rel_id, rel_meta.get("sha", "")[:12], args.expect_sha[:12]))
    cur_id = current_release_id(cfg)
    cur_meta = C.read_json(cfg.releases / cur_id / "release.json", {}) if cur_id else {}
    runner.say("activate %s (commit %s); running now: %s" % (rel_id, rel_meta["sha"][:12], cur_id or "nothing"))
    if args.from_sha and cur_meta.get("sha") != args.from_sha:
        raise Abort(C.EXIT_POLICY, "the plan was made against commit %s but %s is running; re-plan" % (args.from_sha[:12], (cur_meta.get("sha") or "none")[:12]))
    if st.incident() or st.in_progress_file.exists():
        raise Abort(C.EXIT_NEEDS_HUMAN, "unresolved incident or interrupted deployment; verify database before continuing")
    if cur_id == rel_id:
        runner.say("this release is already active; verifying only")
        ok, why = verify_release(cfg, runner, rel_id, cfg.int("health_timeout", 90))
        if not ok:
            raise Abort(C.EXIT_NEEDS_HUMAN, "the active release is not healthy: %s" % why)
        return runner.finish(C.EXIT_OK, "already-active", release=rel_id)

    preflight(cfg, st, runner, rel_id, rel_meta, args)
    plan, report = plan_migrations(cfg, st, runner, rel_id, rel_meta, args)
    migration_policy(cfg, st, runner, plan, report, rel_meta, args)

    if args.dry_run:
        runner.say("dry run: stopping before any change")
        print(json.dumps({"ok": True, "dry_run": True, "plan": plan, "level": report.get("level", "NONE")}))
        return runner.finish(C.EXIT_OK, "dry-run", release=rel_id, plan=plan)

    st.mark_in_progress(runner.run_id, rel_id, "migrate" if plan else "switch")
    applied = []
    if plan:
        runner.say("applying %d migration(s)" % len(plan))
        ok, res = runner.tool.app("migrate", "--release", rel_id, timeout=cfg.int("migrate_timeout", 1800))
        if not ok:
            ok2, after = runner.tool.app("migrate-plan", "--release", rel_id, timeout=300)
            remaining = after.get("plan", plan) if ok2 else plan
            applied = [m for m in plan if m not in remaining]
            runner.say("migration FAILED: %s" % res.get("error", res))
            # A recorder row is not evidence of transaction rollback: non-atomic
            # SQL and a timed-out descendant can have changed data already.
            st.raise_incident("migration failed; database state is unknown", applied=applied, release=rel_id)
            st.set_status(rel_id, "failed", why="migration failed; operator verification required")
            raise Abort(C.EXIT_NEEDS_HUMAN, "migration failed; in_progress retained. Verify database and terminate surviving migration processes before resolve")
        applied = list(plan)
    rollback_safe = (not applied) or report.get("level") in ("NONE", "ADDITIVE")

    st.mark_in_progress(runner.run_id, rel_id, "switch")
    try:
        switch_to(cfg, st, runner, rel_id, cur_id)
    except Abort as exc:
        return handle_failure(cfg, st, runner, rel_id, cur_id, rollback_safe, applied, exc.message)
    st.mark_in_progress(runner.run_id, rel_id, "verify")
    ok, why = verify_release(cfg, runner, rel_id, cfg.int("health_timeout", 90))
    if not ok:
        return handle_failure(cfg, st, runner, rel_id, cur_id, rollback_safe, applied, why)

    st.set_status(rel_id, "active", sha=rel_meta["sha"])
    if cur_id:
        st.set_status(cur_id, "superseded", sha=cur_meta.get("sha", ""))
    st.set_active(current=rel_id, previous=cur_id, sha=rel_meta["sha"], activated_at=C.utc_stamp(), migrations_applied=applied,
                  rollback_safe_to_previous=bool(cur_id) and rollback_safe, run_id=runner.run_id)
    st.clear_in_progress()
    prune_releases(cfg, st, runner)
    runner.say("DONE: %s is serving and verified" % rel_id)
    print(json.dumps({"ok": True, "release": rel_id, "migrations_applied": applied}))
    return runner.finish(C.EXIT_OK, "activated", release=rel_id, sha=rel_meta["sha"], previous=cur_id, migrations_applied=applied)


def handle_failure(cfg, st, runner, rel_id, cur_id, rollback_safe, applied, why):
    runner.say("FAILED after switching: %s" % why)
    st.set_status(rel_id, "failed", why=C.redact(str(why))[:300])
    if not cur_id:
        st.raise_incident("first release failed verification and there is nothing to roll back to", release=rel_id, why=str(why))
        st.clear_in_progress()
        print(json.dumps({"ok": False, "message": "failed; no previous release"}))
        return runner.finish(C.EXIT_NEEDS_HUMAN, "failed-no-previous", release=rel_id, why=C.redact(str(why)))
    if not rollback_safe:
        st.raise_incident("verification failed and an automatic rollback is NOT safe", release=rel_id, migrations_applied=applied,
                          previous=cur_id, why=str(why))
        st.clear_in_progress()
        runner.say("automatic rollback is NOT safe (migrations %s were applied). Nothing further was changed. See state/INCIDENT." % applied)
        print(json.dumps({"ok": False, "message": "failed; rollback unsafe; manual intervention", "exit": C.EXIT_NEEDS_HUMAN}))
        return runner.finish(C.EXIT_NEEDS_HUMAN, "failed-rollback-unsafe", release=rel_id, previous=cur_id,
                             migrations_applied=applied, why=C.redact(str(why)))
    runner.say("rolling back to %s (no migration or only additive ones were applied)" % cur_id)
    restored = restore_link(cfg, st, runner, cur_id, st.active().get("previous"))
    ok, why2 = verify_release(cfg, runner, cur_id, cfg.int("health_timeout", 90)) if restored else (False, "restart failed")
    if ok:
        st.set_status(cur_id, "active")
        st.clear_in_progress()
        print(json.dumps({"ok": False, "rolled_back": True, "release": cur_id}))
        return runner.finish(C.EXIT_FAILED_SAFE, "rolled-back", release=rel_id, restored=cur_id, why=C.redact(str(why)))
    st.raise_incident("rollback target failed verification", release=rel_id, restored=cur_id, why=str(why2))
    st.clear_in_progress()
    print(json.dumps({"ok": False, "message": "rollback target unhealthy"}))
    return runner.finish(C.EXIT_NEEDS_HUMAN, "rollback-failed", release=rel_id, restored=cur_id, why=C.redact(str(why2)))


# ================================================================================================================== rollback
def cmd_rollback(cfg, args):
    st = State(cfg)
    st.ensure()
    run_id = args.run_id or new_run_id()
    lock = Lock(st.lock_file)
    if not lock.acquire():
        print(json.dumps({"ok": False, "busy": True}))
        write_exit_only(st, run_id, C.EXIT_BUSY)
        return C.EXIT_BUSY
    runner = Runner(cfg, st, run_id, "rollback")
    try:
        if st.in_progress_file.exists():
            st.raise_incident("rollback refused: interrupted deployment; database state unknown",
                              marker=C.read_json(st.in_progress_file, {}))
            raise Abort(C.EXIT_NEEDS_HUMAN, "in_progress exists: verify database and running processes, then resolve before rollback")
        cur_id = current_release_id(cfg)
        active = st.active()
        if active.get("current") != cur_id:
            st.raise_incident("rollback refused: current link and active record disagree")
            raise Abort(C.EXIT_NEEDS_HUMAN, "database compatibility is unknown: current link and active record disagree")
        target = args.to if args.to and args.to != "previous" else (st.active().get("previous") or previous_release_id(cfg))
        if not target:
            raise Abort(C.EXIT_POLICY, "there is no previous release to roll back to")
        read_release(cfg, target)
        if target == cur_id:
            raise Abort(C.EXIT_POLICY, "%s is already the active release" % target)
        inc = st.incident()
        if inc and not args.ignore_incident:
            raise Abort(C.EXIT_NEEDS_HUMAN, "an INCIDENT is open; a person must decide (use --ignore-incident only after checking the database)")
        active = st.active()
        safe = bool(active.get("rollback_safe_to_previous")) if target == active.get("previous") else False
        if not safe and args.unsafe_ack != UNSAFE_ROLLBACK_PHRASE:
            raise Abort(C.EXIT_POLICY, "rolling back to %s is not known to be database-compatible (migrations applied by the current release: %s). "
                        "Verify, then pass --unsafe-ack %s" % (target, active.get("migrations_applied"), UNSAFE_ROLLBACK_PHRASE))
        runner.say("rollback %s -> %s" % (cur_id, target))
        st.mark_in_progress(run_id, target, "rollback")
        ok = restore_link(cfg, st, runner, target, cur_id)
        if ok:
            ok, why = verify_release(cfg, runner, target, cfg.int("health_timeout", 90))
        else:
            why = "restart failed"
        if not ok:
            st.raise_incident("rollback target failed verification", target=target, why=str(why))
            st.clear_in_progress()
            print(json.dumps({"ok": False, "message": "rollback target unhealthy"}))
            return runner.finish(C.EXIT_NEEDS_HUMAN, "rollback-failed", target=target, why=C.redact(str(why)))
        st.set_status(target, "active")
        if cur_id:
            st.set_status(cur_id, "rolled-back")
        st.set_active(current=target, previous=cur_id, sha=read_release(cfg, target).get("sha", ""), activated_at=C.utc_stamp(),
                      migrations_applied=[], rollback_safe_to_previous=False, run_id=run_id, via="rollback")
        st.clear_in_progress()
        print(json.dumps({"ok": True, "release": target}))
        return runner.finish(C.EXIT_OK, "rolled-back", target=target, from_release=cur_id)
    except Abort as exc:
        runner.say("STOPPED: %s" % exc.message)
        print(json.dumps({"ok": False, "message": exc.message}))
        return runner.finish(exc.code, "stopped", message=C.redact(exc.message))
    finally:
        lock.release()


# ================================================================================================= status / list / prune / misc
def collect_status(cfg):
    st = State(cfg)
    statuses = st.statuses()
    cur, prev = current_release_id(cfg), previous_release_id(cfg)
    releases = []
    if cfg.releases.is_dir():
        for p in sorted(cfg.releases.iterdir()):
            if p.name.startswith(".") or not C.RELEASE_ID_RE.match(p.name):
                continue
            meta = C.read_json(p / "release.json", {})
            releases.append({"id": p.name, "sha": meta.get("sha", ""), "status": statuses.get(p.name, {}).get("status", "unknown"),
                             "migration_level": (meta.get("migration_report") or {}).get("level", "?")})
    lock = Lock(st.lock_file)
    busy = not lock.acquire() if st.dir.exists() else False
    if not busy:
        lock.release()
    return {
        "current": cur, "previous": prev, "current_sha": (C.read_json(cfg.releases / cur / "release.json", {}) if cur else {}).get("sha", ""),
        "active": st.active(), "incident": st.incident(), "busy": busy, "in_progress": C.read_json(st.in_progress_file, None),
        "releases": releases,
    }


def cmd_status(cfg, args):
    print(json.dumps(collect_status(cfg), indent=2, sort_keys=True))
    return C.EXIT_OK


def prune_releases(cfg, st, runner):
    keep = cfg.int("keep_releases", 5)
    cur, prev = current_release_id(cfg), previous_release_id(cfg)
    protected = {cur, prev, st.active().get("current"), st.active().get("previous")}
    dirs = sorted([p for p in cfg.releases.iterdir() if C.RELEASE_ID_RE.match(p.name)], key=lambda p: p.name, reverse=True)
    kept = 0
    for p in dirs:
        if p.name in protected or p.name.startswith("legacy-"):
            kept += 1
            continue
        kept += 1
        if kept > keep:
            runner.say("pruning old release %s" % p.name)
            for root, dd, ff in os.walk(str(p)):
                try:
                    os.chmod(root, 0o750)
                except OSError:
                    pass
            shutil.rmtree(str(p), ignore_errors=True)
    used = set()
    for p in cfg.releases.iterdir():
        v = p / "venv"
        if v.is_symlink():
            used.add(os.path.basename(os.readlink(str(v))))
    if cfg.venvs.is_dir():
        for v in cfg.venvs.iterdir():
            if v.name not in used and not v.name.startswith("."):
                runner.say("removing unused virtualenv %s" % v.name)
                shutil.rmtree(str(v), ignore_errors=True)


def cmd_prune(cfg, args):
    st = State(cfg)
    st.ensure()
    lock = Lock(st.lock_file)
    if not lock.acquire():
        return C.EXIT_BUSY
    try:
        prune_releases(cfg, st, Runner(cfg, st, new_run_id(), "prune"))
    finally:
        lock.release()
    return C.EXIT_OK


def cmd_resolve(cfg, args):
    st = State(cfg)
    if not args.note or len(args.note) < 10:
        raise Abort(C.EXIT_POLICY, "--note must describe what was checked (at least 10 characters)")
    lock = Lock(st.lock_file)
    if not lock.acquire():
        return C.EXIT_BUSY
    try:
        inc = st.incident()
        st.history(event="incident-resolved", note=args.note, incident=(inc or "")[:300])
        for f in (st.incident_file, st.in_progress_file):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
    finally:
        lock.release()
    C.log("incident cleared")
    return C.EXIT_OK


def cmd_list(cfg, args):
    for r in collect_status(cfg)["releases"]:
        print("%s  %s  %-10s migrations=%s" % (r["id"], r["sha"][:12], r["status"], r["migration_level"]))
    return C.EXIT_OK


def cmd_check_config(cfg, args):
    problems = []
    for key in ("base_dir", "app_user", "service", "env_file", "port", "app_runner", "systemctl"):
        if not cfg.get(key):
            problems.append("missing %s" % key)
    if cfg.get("app_runner") and "sudo" in cfg.get("app_runner") and "root" in (cfg.get("app_runner") or "").split():
        problems.append("app_runner must not run as root")
    if os.geteuid() == 0 and not os.environ.get("RASTISI_ALLOW_ROOT_FOR_TESTS"):
        problems.append("the release tool must not run as root")
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return C.EXIT_POLICY
    print("configuration OK")
    return C.EXIT_OK


def cmd_cutover(cfg, args):
    """One-time registration of the CURRENT, already running deployment as release 'legacy-<sha12>' (nothing is moved or restarted)."""
    st = State(cfg)
    legacy_app, legacy_venv = Path(args.legacy_app), Path(args.legacy_venv)
    rid = "legacy-%s" % args.sha[:12]
    plan = [
        "create %s/{releases,venvs,staging,state}" % cfg.base,
        "register %s as %s/%s/app (symlink, the directory is NOT moved or modified)" % (legacy_app, cfg.releases, rid),
        "link its virtualenv %s as %s/%s/venv" % (legacy_venv, cfg.releases, rid),
        "point %s -> releases/%s" % (cfg.current_link, rid),
        "write state/active.json (rollback target for the first new release = this legacy release)",
        "NOT done here: switch the systemd unit to %s/current/venv/bin/gunicorn and WorkingDirectory=%s/current/app (owner step)" % (cfg.base, cfg.base),
    ]
    if not C.SHA_RE.match(args.sha):
        raise Abort(C.EXIT_POLICY, "--sha must be the 40-hex commit currently running")
    if not legacy_app.is_dir() or not (legacy_app / "manage.py").is_file():
        raise Abort(C.EXIT_POLICY, "%s has no manage.py" % legacy_app)
    if not (legacy_venv / "bin" / "python").exists():
        raise Abort(C.EXIT_POLICY, "%s is not a virtualenv" % legacy_venv)
    if cfg.current_link.exists() or cfg.current_link.is_symlink():
        raise Abort(C.EXIT_POLICY, "%s already exists: cutover was already done" % cfg.current_link)
    for line in plan:
        print(("PLAN  " if not args.apply else "DO    ") + line)
    if not args.apply:
        print("dry run: pass --apply to execute")
        return C.EXIT_OK
    st.ensure()
    rdir = cfg.releases / rid
    rdir.mkdir()
    (rdir / "app").symlink_to(str(legacy_app))
    (rdir / "venv").symlink_to(str(legacy_venv))
    C.atomic_write_json(rdir / "release.json", {"id": rid, "sha": args.sha, "kind": "legacy", "staged_at": C.utc_stamp(),
                                                "migration_report": {"level": "NONE", "new_migrations": []}}, mode=0o644)
    C.atomic_symlink(os.path.join("releases", rid), cfg.current_link)
    st.set_status(rid, "active", sha=args.sha)
    st.set_active(current=rid, previous=None, sha=args.sha, activated_at=C.utc_stamp(), migrations_applied=[], rollback_safe_to_previous=False, via="cutover")
    st.history(event="cutover", release=rid, sha=args.sha)
    print("registered %s" % rid)
    return C.EXIT_OK


# ====================================================================================================================== CLI
def build_parser():
    ap = argparse.ArgumentParser(prog="rastisi_release", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stage")
    p.add_argument("--artifact", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--actor", default="")
    p = sub.add_parser("activate")
    p.add_argument("--id", required=True)
    p.add_argument("--expect-sha", default="")
    p.add_argument("--from-sha", default="")
    p.add_argument("--allow-migrations", action="store_true")
    p.add_argument("--destructive-ack", default="")
    p.add_argument("--skip-backup-check-ack", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run-id", default="")
    p = sub.add_parser("rollback")
    p.add_argument("--to", default="previous")
    p.add_argument("--unsafe-ack", default="")
    p.add_argument("--ignore-incident", action="store_true")
    p.add_argument("--run-id", default="")
    for name in ("status", "list", "prune", "check-config"):
        sub.add_parser(name)
    p = sub.add_parser("resolve")
    p.add_argument("--note", required=True)
    p = sub.add_parser("cutover")
    p.add_argument("--legacy-app", required=True)
    p.add_argument("--legacy-venv", required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--apply", action="store_true")
    return ap


HANDLERS = {
    "stage": cmd_stage, "activate": cmd_activate, "rollback": cmd_rollback, "status": cmd_status, "list": cmd_list,
    "prune": cmd_prune, "resolve": cmd_resolve, "cutover": cmd_cutover, "check-config": cmd_check_config,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        cfg = C.Config()
        return HANDLERS[args.cmd](cfg, args)
    except C.ConfigError as exc:
        sys.stderr.write("configuration error: %s\n" % exc)
        return C.EXIT_POLICY
    except Abort as exc:
        sys.stderr.write("%s\n" % C.redact(exc.message))
        print(json.dumps({"ok": False, "message": C.redact(exc.message)}))
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
