#!/usr/bin/env python3
"""Create two INDEPENDENT sample SQLite databases + media ZIPs (same primary keys!) from the
repository's own reference catalogue, to rehearse ``build_demo_bundle`` end to end.

    python rebuild/tools/make_sample_sources.py D:\\rehearsal

Produces  demo_v5.sqlite3 / demo_v5_media.zip  and  demo_arch02.sqlite3 / demo_arch02_media.zip.
This is SAMPLE data built from rasti-mode-demo - never the real demo stores.
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args, env):
    subprocess.run([sys.executable, str(ROOT / "manage.py"), *args], check=True, cwd=ROOT, env=env)


def build(out: Path, name: str, template: str, wrapper: str) -> None:
    sqlite, media = out / f"{name}.sqlite3", out / f"{name}_media_root"
    media.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update(DJANGO_DEBUG="True", DJANGO_SQLITE_PATH=str(sqlite), DJANGO_MEDIA_ROOT=str(media), PYTHONUTF8="1")
    run(["migrate", "-v0"], env)
    run(["seed_ready_template_fashion_demo", "--ready-template", template], env)
    run(["shell", "-c", (ROOT / "rebuild" / "tools" / "augment_sample_store.py").read_text(encoding="utf-8")], env)
    with zipfile.ZipFile(out / f"{name}_media.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(media.rglob("*")):
            if path.is_file():
                zf.write(path, f"{wrapper}/{path.relative_to(media).as_posix()}" if wrapper else path.relative_to(media).as_posix())


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_sources").resolve()
    out.mkdir(parents=True, exist_ok=True)
    build(out, "demo_v5", "warm_boutique", "media")
    build(out, "demo_arch02", "premium_leather", "")
    print("sample sources written to", out)


if __name__ == "__main__":
    main()
