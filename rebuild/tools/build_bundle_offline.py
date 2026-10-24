#!/usr/bin/env python3
"""One-command offline launcher for ``manage.py build_demo_bundle`` (Windows, macOS, Linux).

    py -3 rebuild\\tools\\build_bundle_offline.py ^
        --v5-sqlite D:\\in\\demo_v5.sqlite3     --v5-media-zip D:\\in\\demo_v5_media.zip ^
        --arch02-sqlite D:\\in\\demo_arch02.sqlite3 --arch02-media-zip D:\\in\\demo_arch02_media.zip ^
        --out D:\\out\\rastisi-demo-bundle

What it does (and nothing else):
  1. creates ``<repo>/.venv`` once (git-ignored) and installs ``requirements.txt`` into it
     (``--wheel-dir DIR`` = fully offline install from a folder of pre-downloaded wheels);
  2. runs ``manage.py build_demo_bundle`` with UTF-8 forced and the project database pointed at a
     throw-away temp file, so no server, no PostgreSQL and no existing database is ever touched.

Every other option is passed straight through to ``build_demo_bundle`` (see its --help).
Exit code is the command's: 0 = bundle written, 1 = FAIL, 2 = BLOCKED.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def venv_python(env_dir: Path) -> Path:
    return env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_environment(env_dir: Path, wheel_dir: str | None) -> Path:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ is required (found {sys.version.split()[0]})")
    python = venv_python(env_dir)
    requirements = ROOT / "requirements.txt"
    stamp = env_dir / ".rebuild-requirements.sha256"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not python.exists():
        print(f"[offline] creating virtual environment {env_dir} ...", file=sys.stderr)
        venv.EnvBuilder(with_pip=True, clear=False).create(env_dir)
    if not stamp.exists() or stamp.read_text().strip() != digest:
        cmd = [str(python), "-m", "pip", "install", "--quiet", "-r", str(requirements)]
        if wheel_dir:
            cmd[4:4] = ["--no-index", "--find-links", wheel_dir]
        print("[offline] installing requirements ...", file=sys.stderr)
        subprocess.run(cmd, check=True)
        stamp.write_text(digest)
    return python


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--venv", default=str(ROOT / ".venv"))
    parser.add_argument("--no-venv", action="store_true", help="use the current Python (dependencies already installed)")
    parser.add_argument("--wheel-dir", default=None)
    parser.add_argument("-h", "--help", action="store_true")
    known, rest = parser.parse_known_args()
    if known.help:
        print(__doc__)
        return 0
    python = Path(sys.executable) if known.no_venv else ensure_environment(Path(known.venv), known.wheel_dir)
    scratch = Path(tempfile.mkdtemp(prefix="rastisi-offline-"))
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "DJANGO_DEBUG": "True",
        "DJANGO_SQLITE_PATH": str(scratch / "unused-project.sqlite3"),  # never the project's db.sqlite3
        "DJANGO_MEDIA_ROOT": str(scratch / "media"), "DJANGO_STATIC_ROOT": str(scratch / "static"),
        "DJANGO_PRIVATE_MEDIA_ROOT": str(scratch / "private"),
    })
    try:
        return subprocess.run([str(python), str(ROOT / "manage.py"), "build_demo_bundle", *rest], env=env, cwd=str(ROOT)).returncode
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
