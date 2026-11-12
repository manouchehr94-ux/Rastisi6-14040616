"""A throwaway 'server' for testing the release tooling end to end without a server, root, systemd, SSH or a real database.

What is REAL: rastisi_release.py, rastisi_app_task.py, rastisi_gate.py, rastisi_common.py (the code that will run in production),
the on-disk layout, the atomic symlink switch, flock-based locking, venv creation, tar extraction, checksums, redaction.
What is STUBBED: systemctl (fake_systemctl.py), the Django project and database (stubs/), the probe and the HTTP smoke test.
The real probe/smoke/Django are exercised by deploy/release/selftest/real_app_selftest.py.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
STUBS = HERE / "stubs"
PY = sys.executable

CANARIES = {
    "DJANGO_SECRET_KEY": "CANARY-secret-key-7f3a91c2d8e54b60",
    "DATABASE_URL": "postgres://rastisi_app:CANARYdbpassw0rd9x@127.0.0.1:5432/rastisi_test",
    "RASTISI_RATE_LIMIT_CACHE_URL": "redis://:CANARYredispw42@127.0.0.1:6380/1",
    "PAYMENT_CREDENTIAL_KEY": "CANARY-fernet-key-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
}

_VENV_TEMPLATE = {}


def venv_template():
    """One real virtualenv per test process (python -m venv is slow); each sandbox gets a copy under its hashed name."""
    if "path" not in _VENV_TEMPLATE:
        root = Path(tempfile.mkdtemp(prefix="rastisi-venv-template-"))
        subprocess.run([PY, "-m", "venv", str(root / "v")], check=True, capture_output=True)
        _VENV_TEMPLATE["path"] = root / "v"
        _VENV_TEMPLATE["root"] = root
    return _VENV_TEMPLATE["path"]


def cleanup_templates():
    if "root" in _VENV_TEMPLATE:
        shutil.rmtree(str(_VENV_TEMPLATE["root"]), ignore_errors=True)
        _VENV_TEMPLATE.clear()


LOCK_TEXT = "# empty on purpose: the stub application has no third-party dependencies\n"
LOCK_KEY = hashlib.sha256(LOCK_TEXT.encode()).hexdigest()[:16]


def make_artifact(dest_dir, *, sha=None, broken=False, migrations=(), level="NONE", static_version="1", extra_files=None,
                  tamper=None, python=None, new_migrations=None):
    """Build a stub release artifact (same structure and checks as the real one). ``tamper`` modifies it after the manifest is written."""
    sha = sha or hashlib.sha1(os.urandom(16)).hexdigest()
    root = Path(tempfile.mkdtemp(prefix="rastisi-art-"))
    app = root / "app"
    app.mkdir()
    shutil.copy(str(STUBS / "manage.py"), str(app / "manage.py"))
    (app / "migrations.json").write_text(json.dumps(list(migrations)))
    (app / "static_version").write_text(static_version)
    if broken:
        (app / "BROKEN").write_text("this release fails its smoke test\n")
    for name, content in (extra_files or {}).items():
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        (app / name).write_text(content)
    (root / "requirements.lock").write_text(LOCK_TEXT)
    (root / "wheelhouse").mkdir()
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema": 1, "sha": sha, "tree_sha": "0" * 40, "python": python or "%d.%d" % sys.version_info[:2],
        "lock_sha256": hashlib.sha256(LOCK_TEXT.encode()).hexdigest(),
        "migration_report": {"level": level, "new_migrations": list(new_migrations if new_migrations is not None else migrations),
                             "rollback_safe": level in ("NONE", "ADDITIVE")},
        "files": files,
    }
    (root / "release-manifest.json").write_text(json.dumps(manifest))
    if tamper:
        tamper(root)
    out = Path(dest_dir) / ("art-%s.tar.gz" % sha[:12])
    with tarfile.open(str(out), "w:gz") as tar:
        for path in sorted(root.rglob("*")):
            tar.add(str(path), arcname=path.relative_to(root).as_posix(), recursive=False)
    shutil.rmtree(str(root))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    return out, sha, digest


class Sandbox:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="rastisi-sbx-"))
        self.base = self.root / "srv"
        self.fake = self.root / "fake"
        self.static = self.root / "static"
        self.media = self.root / "media"
        self.logs = self.root / "out"
        self.env_file = self.root / "env"
        self.conf = self.root / "deploy.conf"
        self.control = self.root / "control.json"
        self.db = self.root / "db.json"
        for d in (self.base, self.fake, self.static, self.media, self.logs):
            d.mkdir()
        (self.fake / "flags.json").write_text(json.dumps({"base": str(self.base)}))
        self.set_control({})
        # persistent customer data that no deployment may ever touch
        self.db.write_text(json.dumps({"rows": ["order-1001", "order-1002", "store-akhlaghi"], "applied": ["core.0001_initial"]}))
        (self.media / "logo.png").write_bytes(b"\x89PNG customer upload\n" * 50)
        (self.media / "stores").mkdir()
        (self.media / "stores" / "product-1.jpg").write_bytes(b"jpegdata" * 100)
        env_lines = ["%s=%s" % (k, v) for k, v in CANARIES.items()]
        env_lines += ["DJANGO_DEBUG=False", "DJANGO_ALLOWED_HOSTS=rastisi.test", "DJANGO_STATIC_ROOT=%s" % self.static,
                      "DJANGO_MEDIA_ROOT=%s" % self.media, "STUB_CONTROL=%s" % self.control, "STUB_DB=%s" % self.db]
        self.env_file.write_text("\n".join(env_lines) + "\n")
        os.chmod(str(self.env_file), 0o600)
        self.conf.write_text("\n".join([
            "[rastisi]", "jobs_follow_current = true", "edge_probe_enabled = false", "base_dir = %s" % self.base, "app_user = tester", "service = rastisi-test.service",
            "env_file = %s" % self.env_file, "port = 18999", "static_root = %s" % self.static, "python = %s" % PY,
            "app_runner = %s %s" % (PY, TOOLS / "rastisi_app_task.py"),
            "systemctl = %s %s %s" % (PY, STUBS / "fake_systemctl.py", self.fake),
            "systemctl_show = %s %s %s" % (PY, STUBS / "fake_systemctl.py", self.fake),
            "proc_root = %s" % (self.fake / "proc"),
            "probe_script = %s" % (STUBS / "stub_probe.py"), "smoke_script = %s" % (STUBS / "stub_smoke.py"),
            "health_timeout = 6", "min_free_mb = 1", "keep_releases = 3", "backup_max_age_minutes = 90", "smoke_host = rastisi.test",
        ]) + "\n")
        self.env = dict(os.environ, RASTISI_DEPLOY_CONF=str(self.conf), RASTISI_ALLOW_ROOT_FOR_TESTS="1", PYTHONDONTWRITEBYTECODE="1")
        self.counter = 0

    # --- control -----------------------------------------------------------------------------------------------------
    def set_control(self, data):
        self.control.write_text(json.dumps(data))

    def set_flags(self, **flags):
        path = self.fake / "flags.json"
        cur = json.loads(path.read_text())
        cur.update(flags)
        path.write_text(json.dumps(cur))

    def db_state(self):
        return json.loads(self.db.read_text())

    def data_fingerprint(self):
        """Hash of everything that must never change because of a deployment: customer rows and every media file."""
        h = hashlib.sha256()
        rows = self.db_state()["rows"]
        h.update(json.dumps(rows).encode())
        for p in sorted(self.media.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(self.media).as_posix().encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    # --- running the tools -------------------------------------------------------------------------------------------
    def tool(self, script, *args, stdin=None, env=None, timeout=300):
        proc = subprocess.run([PY, str(TOOLS / script)] + [str(a) for a in args], capture_output=True, text=True,
                              env=dict(self.env, **(env or {})), input=stdin, timeout=timeout)
        return proc

    def release(self, *args, **kw):
        return self.tool("rastisi_release.py", *args, **kw)

    def stage(self, artifact, sha, digest):
        self._seed_venv()
        proc = self.release("stage", "--artifact", artifact, "--sha", sha, "--sha256", digest)
        release_id = None
        if proc.returncode == 0:
            release_id = json.loads(proc.stdout.strip().splitlines()[-1])["release"]
        return proc, release_id

    def _seed_venv(self):
        """Pre-seed the hashed venv from the process-wide template so stage does not pay for 'python -m venv' every time."""
        target = self.base / "venvs" / LOCK_KEY
        if target.exists():
            return
        (self.base / "venvs").mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(venv_template()), str(target), symlinks=True)
        (target / ".complete").write_text("seeded\n")

    def make_and_stage(self, **kw):
        art, sha, digest = make_artifact(self.root, **kw)
        proc, rid = self.stage(art, sha, digest)
        if proc.returncode != 0:
            raise AssertionError("stage failed: %s %s" % (proc.stdout, proc.stderr))
        return rid, sha

    def activate(self, rid, *args, **kw):
        return self.release("activate", "--id", rid, *args, **kw)

    def cutover(self, sha=None):
        """Register a pre-existing 'legacy' deployment as the running release (what the one-time cutover does on the real server)."""
        sha = sha or hashlib.sha1(b"legacy").hexdigest()
        legacy_app = self.root / "legacy-app"
        legacy_app.mkdir(exist_ok=True)
        shutil.copy(str(STUBS / "manage.py"), str(legacy_app / "manage.py"))
        (legacy_app / "migrations.json").write_text("[]")
        (legacy_app / "static_version").write_text("0")
        legacy_venv = self.root / "legacy-venv"
        if not legacy_venv.exists():
            shutil.copytree(str(venv_template()), str(legacy_venv), symlinks=True)
        proc = self.release("cutover", "--legacy-app", legacy_app, "--legacy-venv", legacy_venv, "--sha", sha, "--apply")
        if proc.returncode != 0:
            raise AssertionError(proc.stdout + proc.stderr)
        self.restart_service()
        return sha

    def restart_service(self):
        subprocess.run([PY, str(STUBS / "fake_systemctl.py"), str(self.fake), "restart"], check=True)

    def status(self):
        return json.loads(self.release("status").stdout)

    def history(self):
        p = self.base / "state" / "history.jsonl"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def restarts(self):
        p = self.fake / "service.json"
        return json.loads(p.read_text()).get("restarts", 0) if p.exists() else 0

    def record_backup(self, minutes_ago=5, verified=True):
        t = time.gmtime(time.time() - minutes_ago * 60)
        (self.base / "state").mkdir(parents=True, exist_ok=True)
        (self.base / "state" / "last_backup.json").write_text(json.dumps(
            {"finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", t), "verified": verified}))

    def all_text_outputs(self):
        """Every text file the tooling wrote (logs, history, results, incident)."""
        blobs = []
        for p in list(self.base.rglob("*")):
            if p.is_file() and p.stat().st_size < 5_000_000 and "venvs" not in p.parts and "releases" not in p.parts:
                try:
                    blobs.append(p.read_text(errors="replace"))
                except OSError:
                    pass
        return "\n".join(blobs)

    def close(self):
        for p in sorted(self.base.rglob("*"), reverse=True):
            try:
                if p.is_dir() and not p.is_symlink():
                    os.chmod(str(p), 0o755)
            except OSError:
                pass
        shutil.rmtree(str(self.root), ignore_errors=True)


class SandboxTestCase(unittest.TestCase):
    def setUp(self):
        self.sbx = Sandbox()
        self.addCleanup(self.sbx.close)
        self.legacy_sha = self.sbx.cutover()

    # convenience
    def current(self):
        return self.sbx.status()["current"]

    def assertServing(self, release_id):
        st = self.sbx.status()
        self.assertEqual(st["current"], release_id)
        want = os.path.realpath(str(self.sbx.base / "releases" / release_id / "app"))
        pid = json.loads((self.sbx.fake / "service.json").read_text())["pid"]
        self.assertEqual(os.path.realpath(str(self.sbx.fake / "proc" / str(pid) / "cwd")), want)
