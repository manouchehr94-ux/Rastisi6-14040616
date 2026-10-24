#!/usr/bin/env python3
"""Build the clean RastiSi release ZIP from git-tracked files.

    python rebuild/tools/build_release_zip.py --out dist/rastisi-release.zip
    python rebuild/tools/build_release_zip.py --out dist/rastisi-release.zip --bundle /path/to/validated/bundle

What goes in
    application code (apps/, shop_core/, templates/, static/, manage.py,
    requirements.txt), rebuild/ (importers, checks, deployment, manifests),
    docs/rebuild/ and the production configuration reference.
What stays out
    QA evidence / reference screenshots (docs/qa_evidence, docs/references,
    docs/reference-kits, ...), graphify output, virtualenvs, SQLite databases,
    media, .env files, private keys and anything else secret-shaped. The 345 raw
    demo photos (apps/stores/demo_assets/**/raw_user_catalog) are provenance only
    and are excluded unless --include-raw-demo-assets is given.
A store data bundle is added under ``data/bundle`` only when --bundle is given;
it is re-validated first (``manage.py validate_demo_bundle``) and the build is
refused unless that returns PASS. The ZIP contains a MANIFEST.json with the git
commit and a SHA-256 for every file, plus a sibling ``.sha256`` file.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INCLUDE_PREFIXES = (
    "apps/", "shop_core/", "templates/", "static/", "rebuild/", "docs/rebuild/",
    "docs/docs/product/deployment/", "deploy/",
)
INCLUDE_FILES = ("manage.py", "requirements.txt", ".env.example", "CLAUDE.md")
EXCLUDE_GLOBS = (
    "*/__pycache__/*", "*.pyc", "*.sqlite3", "*.sqlite3-journal", "*.log", "*.bak",
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    "graphify-out/*", ".graphify-venv/*", ".venv*/*", "venv/*", "media/*", "private_media/*",
)
RAW_DEMO_GLOB = "apps/stores/demo_assets/*/raw_user_catalog/*"
SECRET_NAME_HINTS = ("secret", "passwd", "credential", "token")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def wanted(path: str, *, include_raw: bool) -> bool:
    if path == ".env.example":
        return True
    if not (path in INCLUDE_FILES or path.startswith(INCLUDE_PREFIXES)):
        return False
    if any(fnmatch.fnmatch(path, g) for g in EXCLUDE_GLOBS):
        return False
    if not include_raw and fnmatch.fnmatch(path, RAW_DEMO_GLOB):
        return False
    return True


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_bundle(bundle: Path) -> None:
    cmd = [sys.executable, "manage.py", "validate_demo_bundle", str(bundle)]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.exit(f"refusing to package: bundle validation exited {result.returncode} "
                 f"(1=FAIL, 2=BLOCKED); fix or supply the missing inputs first")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output .zip path")
    ap.add_argument("--bundle", help="validated store data bundle directory to embed under data/bundle")
    ap.add_argument("--include-raw-demo-assets", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true", help="package even with uncommitted changes")
    args = ap.parse_args()

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if dirty and not args.allow_dirty:
        sys.exit("working tree has uncommitted changes; commit first or pass --allow-dirty")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    files = [p for p in tracked_files() if wanted(p, include_raw=args.include_raw_demo_assets)]
    suspicious = [p for p in files if any(h in Path(p).name.lower() for h in SECRET_NAME_HINTS)
                  and not p.endswith((".py", ".md", ".html", ".js", ".css", ".txt", ".json", ".sh"))]
    if suspicious:
        sys.exit(f"refusing: secret-looking file name(s): {suspicious}")

    entries: dict[str, str] = {}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in sorted(files):
            data = (ROOT / rel).read_bytes()
            info = zipfile.ZipInfo(f"rastisi/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o755 if rel.endswith(".sh") else 0o644) << 16)
            zf.writestr(info, data)
            entries[rel] = sha256(data)
        if args.bundle:
            bundle = Path(args.bundle).resolve()
            validate_bundle(bundle)
            for p in sorted(x for x in bundle.rglob("*") if x.is_file()):
                rel = f"data/bundle/{p.relative_to(bundle).as_posix()}"
                data = p.read_bytes()
                zf.writestr(zipfile.ZipInfo(f"rastisi/{rel}", date_time=(2026, 1, 1, 0, 0, 0)), data)
                entries[rel] = sha256(data)
        manifest = {
            "name": "rastisi-release",
            "git_commit": commit,
            "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "contains_store_data_bundle": bool(args.bundle),
            "raw_demo_assets_included": args.include_raw_demo_assets,
            "file_count": len(entries),
            "files": entries,
        }
        zf.writestr("rastisi/MANIFEST.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    digest = sha256(out.read_bytes())
    Path(str(out) + ".sha256").write_text(f"{digest}  {out.name}\n")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(entries)} files, commit {commit[:12]})")
    print(f"sha256 {digest}")
    if not args.bundle:
        print("NOTE: no data bundle embedded - this is a CODE-ONLY package (demo data not included).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
