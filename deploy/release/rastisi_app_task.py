#!/usr/bin/env python3
"""The privilege boundary. Installed root-owned (0755) in /usr/local/lib/rastisi/ and reachable ONLY through sudoers:

    rastisi-deploy ALL=(rastisi) NOPASSWD: /usr/bin/python3 /usr/local/lib/rastisi/rastisi_app_task.py *

It runs as the APPLICATION user (the one that already owns the environment file), so the deploy user never reads secrets.
The caller chooses a verb and a release id; everything else (paths, interpreter, environment file, port) comes from the root-owned
configuration. It accepts nothing that can be turned into an arbitrary command, file path or environment variable.

Output contract: logs (redacted) on stderr, exactly one JSON line on stdout, exit code 0 only when ``ok`` is true.
"""

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rastisi_common as C  # noqa: E402

REQUIRED_ENV = ("DJANGO_SECRET_KEY", "DATABASE_URL", "DJANGO_ALLOWED_HOSTS", "RASTISI_RATE_LIMIT_CACHE_URL")
RECOMMENDED_ENV = ("PAYMENT_CREDENTIAL_KEY", "DJANGO_CSRF_TRUSTED_ORIGINS")
VERBS = ("envcheck", "check", "migrate-plan", "migrate", "healthcheck", "publish-static", "smoke", "edge-health", "who")


def probe_script(ctx):
    """The Django-side probe. Overridable only through the root-owned config (the unit tests use a stub)."""
    return ctx.cfg.get("probe_script") or str(Path(__file__).resolve().parent / "rastisi_probe.py")


def smoke_script(ctx):
    return ctx.cfg.get("smoke_script") or str(Path(__file__).resolve().parent / "rastisi_smoke.py")


def emit(ok, **data):
    data["ok"] = bool(ok)
    print(json.dumps(data, sort_keys=True))
    return 0 if ok else 1


class Ctx:
    def __init__(self, cfg, release_id=None):
        self.cfg = cfg
        self.env_values = {}
        self.secrets = set()
        self.release_id = release_id
        env_file = cfg.get("env_file")
        try:
            self.env_values = C.parse_env_file(env_file)
        except OSError as exc:
            self.env_error = "cannot read the environment file (%s)" % exc.__class__.__name__
        else:
            self.env_error = ""
        self.secrets = C.secret_values(self.env_values)

    def release_paths(self):
        if not C.RELEASE_ID_RE.match(self.release_id or ""):
            raise ValueError("invalid release id")
        root = self.cfg.releases / self.release_id
        app = root / "app"
        py = root / "venv" / "bin" / "python"
        if not app.is_dir() or not py.exists():
            raise ValueError("release %s is incomplete" % self.release_id)
        # the release root must be a real directory directly under releases/ (legacy releases symlink app/venv out of it, never the root)
        if os.path.islink(str(root)) or os.path.dirname(os.path.realpath(str(root))) != os.path.realpath(str(self.cfg.releases)):
            raise ValueError("release path escapes the releases directory")
        return app, py

    def env(self, extra=None):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TZ", "HOME", "TMPDIR")}
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env.update(self.env_values)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.setdefault("DJANGO_SETTINGS_MODULE", "shop_core.settings")
        env.update(extra or {})
        return env

    def run(self, args, cwd, timeout=600, extra_env=None):
        try:
            proc = subprocess.run(args, cwd=str(cwd), env=self.env(extra_env), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            sys.stderr.write("timed out after %ss\n" % timeout)
            return 124, ""
        text = (proc.stderr or "") + (("\n" + proc.stdout) if proc.returncode != 0 else "")
        for line in C.redact(text, self.secrets).splitlines()[-60:]:
            sys.stderr.write(line + "\n")
        return proc.returncode, proc.stdout


def last_json(text):
    for line in reversed((text or "").strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


# ---------------------------------------------------------------------------------------------------------------------- verbs
def v_who(ctx, args):
    return emit(True, user=os.environ.get("USER") or str(os.getuid()), uid=os.getuid())


def v_envcheck(ctx, args):
    if ctx.env_error:
        return emit(False, error=ctx.env_error)
    missing = [k for k in REQUIRED_ENV if not ctx.env_values.get(k)]
    problems = []
    if ctx.env_values.get("DJANGO_DEBUG", "").strip().lower() not in ("false", "0", "no", "off"):
        problems.append("DJANGO_DEBUG must be explicitly false")
    if not ctx.env_values.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        problems.append("DATABASE_URL must be a postgres:// URL")
    if ctx.env_values.get("PAYMENTS_SIMULATION_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
        problems.append("PAYMENTS_SIMULATION_ENABLED must be off")
    if ctx.env_values.get("RASTISI_SMS_REFUND_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
        problems.append("RASTISI_SMS_REFUND_ENABLED must stay off")
    if ctx.env_values.get("RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS", "").strip():
        problems.append("RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS must stay empty")
    warnings = ["%s is not set" % k for k in RECOMMENDED_ENV if not ctx.env_values.get(k)]
    ok = not missing and not problems
    return emit(ok, missing=missing, problems=problems, warnings=warnings,
                error="; ".join(["missing: " + ", ".join(missing)] * bool(missing) + problems))


def v_check(ctx, args):
    app, py = ctx.release_paths()
    rc, out = ctx.run([str(py), "manage.py", "check", "--deploy", "--fail-level", "ERROR"], app, timeout=300)
    return emit(rc == 0, error="" if rc == 0 else "manage.py check reported errors")


def v_migrate_plan(ctx, args):
    app, py = ctx.release_paths()
    rc, out = ctx.run([str(py), probe_script(ctx), "plan"], app, timeout=300)
    data = last_json(out)
    if (rc != 0 or not isinstance(data, dict) or data.get('ok') is not True
            or not isinstance(data.get('plan'), list) or not all(isinstance(m, str) for m in data['plan'])):
        return emit(False, error="could not read a valid migration state")
    return emit(True, plan=data['plan'], error='')


def v_migrate(ctx, args):
    app, py = ctx.release_paths()
    lock_ms = ctx.cfg.int('migration_lock_timeout_ms', 5000)
    statement_ms = ctx.cfg.int('migration_statement_timeout_ms', 600000)
    if not 1 <= lock_ms <= statement_ms:
        return emit(False, error='invalid migration database timeouts')
    rc, out = ctx.run([str(py), "manage.py", "migrate", "--noinput"], app,
                      timeout=ctx.cfg.int("migrate_timeout", 1800),
                      extra_env={'PGOPTIONS': '-c lock_timeout=%d -c statement_timeout=%d' % (lock_ms, statement_ms)})
    return emit(rc == 0, error="" if rc == 0 else "migrate exited %d" % rc)


def _main_pid_cwd(ctx):
    cmd = ctx.cfg.command("systemctl_show", "systemctl") + ["show", "-p", "MainPID", "--value", ctx.cfg.get("service")]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    pid = (proc.stdout or "").strip()
    if proc.returncode != 0 or not pid.isdigit() or pid == "0":
        return None, "service has no main process"
    proc_root = ctx.cfg.get("proc_root", "/proc")
    try:
        return os.path.realpath(os.readlink(os.path.join(proc_root, pid, "cwd"))), ""
    except OSError as exc:
        return None, "cannot inspect the service process (%s)" % exc.__class__.__name__


def v_healthcheck(ctx, args):
    app, py = ctx.release_paths()
    mode = "--post" if args.post else "--pre"
    rc, out = ctx.run([str(py), probe_script(ctx), "health", mode], app, timeout=120)
    data = last_json(out)
    if (not isinstance(data, dict) or rc != 0 or data.get("ok") is not True
            or not isinstance(data.get("failures"), list) or not isinstance(data.get("checks"), dict)
            or not data['checks'] or not all(value is True for value in data['checks'].values())):
        return emit(False, failures=["health probe failed or returned an invalid result"], checks={})
    failures = list(data["failures"])
    if args.expect_release:
        cwd, why = _main_pid_cwd(ctx)
        want = os.path.realpath(str(ctx.cfg.releases / args.expect_release / "app"))
        if cwd is None:
            failures.append("running release: %s" % why)
        elif cwd != want:
            failures.append("the service is running %s, expected %s" % (os.path.basename(os.path.dirname(cwd)) or cwd, args.expect_release))
    if rc != 0 and not data:
        failures.append(data.get("error") or "probe did not run")
    return emit(not failures, failures=failures, checks=data.get("checks", {}))


def _sync_tree(src, dst):
    """Copy files whose CONTENT differs (collectstatic skips by mtime, which would leave new files in place after a rollback).
    Never deletes: old assets keep working for pages cached by browsers during the switch."""
    copied = 0
    for root, dirs, files in os.walk(str(src)):
        rel = os.path.relpath(root, str(src))
        target_dir = Path(dst) / rel if rel != "." else Path(dst)
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            s, d = Path(root) / name, target_dir / name
            if d.exists() and filecmp.cmp(str(s), str(d), shallow=False):
                continue
            tmp = target_dir / (".%s.tmp-%d" % (name, os.getpid()))
            shutil.copyfile(str(s), str(tmp))
            os.chmod(str(tmp), 0o644)
            os.replace(str(tmp), str(d))
            copied += 1
    return copied


def v_publish_static(ctx, args):
    app, py = ctx.release_paths()
    live = ctx.env_values.get("DJANGO_STATIC_ROOT")
    if not live:
        return emit(False, error="DJANGO_STATIC_ROOT is not set in the environment file")
    scratch = ctx.cfg.state / "static-build" / ctx.release_id
    if scratch.exists():
        shutil.rmtree(str(scratch))
    scratch.mkdir(parents=True)
    try:
        rc, _ = ctx.run([str(py), "manage.py", "collectstatic", "--noinput", "-v", "0"], app, timeout=600,
                        extra_env={"DJANGO_STATIC_ROOT": str(scratch)})
        if rc != 0:
            return emit(False, error="collectstatic failed")
        copied = _sync_tree(scratch, live)
    finally:
        shutil.rmtree(str(scratch), ignore_errors=True)
    return emit(True, files_updated=copied)


def v_smoke(ctx, args):
    app, py = ctx.release_paths()
    cmd = [str(py), smoke_script(ctx), "--base-url", args.base_url,
           "--release-dir", str(app), "--expect-release", args.expect_release or ""]
    if args.host:
        cmd += ["--host", args.host]
    rc, out = ctx.run(cmd, app, timeout=240)
    data = last_json(out)
    return emit(rc == 0 and data.get("ok", False), failures=data.get("failures", [] if rc == 0 else ["smoke runner failed"]), passed=data.get("passed", []))


def v_edge_health(ctx, args):
    app, py = ctx.release_paths()
    script = Path(__file__).resolve().parent / 'rastisi_edge_probe.py'
    rc, out = ctx.run([str(py), str(script), '--host', ctx.cfg.get('smoke_host') or '', '--port', str(ctx.cfg.int('edge_port', 443))], app, timeout=100)
    data = last_json(out)
    return emit(rc == 0 and isinstance(data, dict) and data.get('ok') is True, failures=data.get('failures', ['edge probe failed']) if isinstance(data, dict) else ['invalid edge result'])


HANDLERS = {"who": v_who, "envcheck": v_envcheck, "check": v_check, "migrate-plan": v_migrate_plan, "migrate": v_migrate,
            "healthcheck": v_healthcheck, "publish-static": v_publish_static, "smoke": v_smoke, "edge-health": v_edge_health}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rastisi_app_task")
    ap.add_argument("verb", choices=VERBS)
    ap.add_argument("--release", default="")
    ap.add_argument("--pre", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--expect-release", default="")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--host", default="")
    args = ap.parse_args(argv)
    try:
        cfg = C.Config()
    except C.ConfigError as exc:
        return emit(False, error="configuration error: %s" % exc)
    if args.expect_release and not C.RELEASE_ID_RE.match(args.expect_release):
        return emit(False, error="invalid --expect-release")
    if args.base_url:
        from urllib.parse import urlsplit
        parsed = urlsplit(args.base_url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
            return emit(False, error="smoke tests may only target the local host")
    ctx = Ctx(cfg, args.release)
    try:
        return HANDLERS[args.verb](ctx, args)
    except ValueError as exc:
        return emit(False, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(C.redact(repr(exc), ctx.secrets) + "\n")
        return emit(False, error="%s" % exc.__class__.__name__)


if __name__ == "__main__":
    sys.exit(main())
