#!/usr/bin/env python3
"""Build the deployable artifact of ONE commit (runs in CI, never on the server). Standard library + pip.

    build_release.py --repo . --sha <40hex> --from-sha <40hex|''> --out dist/ [--python-version 3.12]

Output (in --out):
    rastisi-<sha12>.tar.gz     app/ (git archive of exactly that commit, minus docs), requirements.lock (hashes), wheelhouse/,
                               release-manifest.json (commit, tree, python, per-file sha256, migration report)
    rastisi-<sha12>.tar.gz.sha256
    migration-report.json

The artifact is the ONLY thing that reaches the server. Its checksum is computed here, passed to the server out of band
(as a command argument), and re-verified there before anything is unpacked; the manifest then re-verifies every file.
Dependencies come from an offline wheelhouse with pinned hashes, so the server never talks to PyPI and a compromised or
changed upstream package cannot slip in between the CI run and the deployment.
"""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migration_guard  # noqa: E402

EXCLUDE_TOP = {"docs", ".claude", ".github", ".git", "graphify-out", ".graphify-venv"}
EXCLUDE_FILES = {".env", ".mcp.json", "CLAUDE.md", "SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md", "SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md"}
WHEEL_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.]+)-(?P<ver>[A-Za-z0-9_.+!]+?)(?:-\d[^-]*)?-(?P<py>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$")


def run(cmd, **kw):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise SystemExit("command failed: %s\n%s" % (" ".join(cmd[:4]), (proc.stderr or proc.stdout)[-1500:]))
    return proc.stdout


def sha256_file(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def export_tree(repo, sha, dest):
    data = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            top = m.name.split("/", 1)[0]
            if top in EXCLUDE_TOP or m.name in EXCLUDE_FILES:
                continue
            if m.name.endswith(".pyc") or "/__pycache__/" in m.name:
                continue
            tar.extract(m, str(dest))
    commit_time = int(run(["git", "-C", str(repo), "show", "-s", "--format=%ct", sha]).strip())
    return commit_time


def build_wheelhouse(requirements_files, wheelhouse, python_version):
    wheelhouse.mkdir(parents=True)
    abi = "cp" + python_version.replace(".", "")
    cmd = [sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--disable-pip-version-check", "-q", "-d", str(wheelhouse),
           "--python-version", python_version, "--implementation", "cp", "--abi", abi]
    for plat in ("manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64", "linux_x86_64"):
        cmd += ["--platform", plat]
    for req in requirements_files:
        cmd += ["-r", str(req)]
    run(cmd)
    lines = []
    seen = {}
    for wheel in sorted(wheelhouse.glob("*.whl")):
        m = WHEEL_RE.match(wheel.name)
        if not m:
            raise SystemExit("unrecognised wheel name: " + wheel.name)
        name = re.sub(r"[-_.]+", "-", m.group("name")).lower()
        if name in seen:
            raise SystemExit("two versions of %s in the wheelhouse: %s and %s" % (name, seen[name], m.group("ver")))
        seen[name] = m.group("ver")
        lines.append("%s==%s --hash=sha256:%s" % (name, m.group("ver"), sha256_file(wheel)))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--from-sha", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--python-version", default="3.12")
    ap.add_argument("--extra-requirements", default=str(Path(__file__).resolve().parent / "requirements-server.txt"))
    ap.add_argument("--run-id", default="")
    ap.add_argument("--actor", default="")
    args = ap.parse_args(argv)

    if not re.match(r"^[0-9a-f]{40}$", args.sha):
        raise SystemExit("--sha must be a full 40-hex commit id")
    resolved = run(["git", "-C", args.repo, "rev-parse", "--verify", args.sha + "^{commit}"]).strip()
    if resolved != args.sha:
        raise SystemExit("commit not found: " + args.sha)
    tree = run(["git", "-C", args.repo, "rev-parse", args.sha + "^{tree}"]).strip()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rastisi-build-") as tmp:
        root = Path(tmp) / "pkg"
        app = root / "app"
        app.mkdir(parents=True)
        commit_time = export_tree(args.repo, args.sha, app)
        if not (app / "manage.py").is_file():
            raise SystemExit("the commit has no manage.py")
        base_req = app / "requirements.txt"
        if not base_req.is_file():
            raise SystemExit("the commit has no requirements.txt")
        lock_text = build_wheelhouse([base_req, Path(args.extra_requirements)], root / "wheelhouse", args.python_version)
        (root / "requirements.lock").write_text(lock_text, encoding="utf-8")

        report = migration_guard.analyze_range(args.repo, args.from_sha, args.sha)
        (out / "migration-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        files = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                files[path.relative_to(root).as_posix()] = sha256_file(path)
        manifest = {
            "schema": 1, "platform": "linux_x86_64", "sha": args.sha, "tree_sha": tree, "from_sha": args.from_sha, "python": args.python_version,
            "lock_sha256": hashlib.sha256(lock_text.encode("utf-8")).hexdigest(),
            "migration_report": report, "built_by": {"run_id": args.run_id, "actor": args.actor},
            "commit_time": commit_time, "files": files,
        }
        (root / "release-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        artifact = out / ("rastisi-%s.tar.gz" % args.sha[:12])
        import gzip
        with open(str(artifact), "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=commit_time) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for path in sorted(root.rglob("*")):
                    info = tar.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = commit_time
                    if info.isreg():
                        with open(str(path), "rb") as fh:
                            tar.addfile(info, fh)
                    else:
                        tar.addfile(info)
    digest = sha256_file(artifact)
    (out / (artifact.name + ".sha256")).write_text("%s  %s\n" % (digest, artifact.name), encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), "sha256": digest, "size_mb": round(artifact.stat().st_size / 1048576, 1),
                      "sha": args.sha, "migration_level": report["level"], "new_migrations": len(report["new_migrations"]),
                      "wheels": len(lock_text.splitlines())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
