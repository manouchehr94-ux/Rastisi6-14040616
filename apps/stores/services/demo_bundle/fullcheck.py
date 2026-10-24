"""End-to-end proof on one machine, in scratch databases: no server, no network.

1. fresh scratch database (SQLite) -> migrate -> import the converted bundle
   (twice: the second run must change nothing) -> integrity check with HTTP.
2. for every source store: render it from the snapshot of the ORIGINAL database
   and from the imported result, and compare the signatures page by page.

Everything runs in subprocesses of ``manage.py`` with ``DJANGO_SQLITE_PATH`` /
``DJANGO_MEDIA_ROOT`` pointing into the work directory, so the real project
database is never touched.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from django.conf import settings

from .report import Report
from .signature import diff_signatures
from .targets import TargetStore


def _run(args: list[str], env: dict, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), *args],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        cwd=str(settings.BASE_DIR),
    )


def _env(sqlite: Path, media: Path, hosts: list[str]) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "DJANGO_ALLOWED_HOSTS")}
    env.update({
        "DJANGO_DEBUG": "True", "DJANGO_SQLITE_PATH": str(sqlite), "DJANGO_MEDIA_ROOT": str(media),
        "DJANGO_STATIC_ROOT": str(media.parent / "static"), "DJANGO_PRIVATE_MEDIA_ROOT": str(media.parent / "private"),
        "DJANGO_ALLOWED_HOSTS": ",".join(hosts), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
    })
    return env


def run_full_check(
    bundle_dir: Path,
    targets: dict[str, TargetStore],
    sources: dict[str, dict],
    stride: int,
    offsets: dict[str, int],
    work_dir: Path,
    *,
    targets_path: Path | None = None,
    log=lambda m: None,
) -> Report:
    report = Report("full check (scratch import + render equivalence)")
    scratch = Path(work_dir) / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    sqlite, media = scratch / "scratch.sqlite3", scratch / "media"
    media.mkdir(exist_ok=True)
    hosts = sorted({t.hostname for t in targets.values()} | {"source-copy.rastisi.ir"})
    env = _env(sqlite, media, hosts)
    extra = ["--targets", str(targets_path)] if targets_path else []

    log("full check: migrating a scratch database ...")
    r = _run(["migrate", "-v0"], env)
    if r.returncode:
        report.fail("scratch.migrate", r.stderr[-800:])
        return report
    report.ok("scratch.migrate", "fresh scratch database migrated")

    totals = []
    for run in (1, 2):
        log(f"full check: import run {run} ...")
        r = _run(["import_demo_bundle", str(bundle_dir), *extra], env)
        if r.returncode != 0:
            report.fail("scratch.import", f"run {run} exit {r.returncode}: {(r.stdout + r.stderr)[-1200:]}")
            return report
        totals.append(re.findall(r"(\w+): store=([\w-]+) created=(\w+) rows=(\d+) media_copied=(\d+) media_identical=(\d+)", r.stdout))
    first = {m[0]: m for m in totals[0]}
    second = {m[0]: m for m in totals[1]}
    for key in targets:
        if key not in first or key not in second:
            report.fail("scratch.import", f"no import summary for {key}", key)
            continue
        f, s = first[key], second[key]
        if f[3] != s[3] or s[4] != "0" or s[2] != "False":
            report.fail("scratch.idempotency", f"second import differs: rows {f[3]} -> {s[3]}, media_copied {s[4]}, created {s[2]}", key)
        else:
            report.ok("scratch.idempotency", f"import #2 changed nothing (rows={s[3]}, media files already identical={s[5]})", key)

    log("full check: integrity + HTTP ...")
    r = _run(["verify_demo_integrity", *extra, "--http", "--json"], env)
    try:
        payload = json.loads(r.stdout[r.stdout.index("{"):])
        for f in payload["findings"]:
            report.add(f["level"], "integrity." + f["code"], f["message"], f.get("store", ""))
    except (ValueError, KeyError):
        report.fail("scratch.verify", f"unreadable output (exit {r.returncode}): {(r.stdout + r.stderr)[-800:]}")

    for key, info in sources.items():
        target = targets[key]
        log(f"full check: comparing {key} source vs import ...")
        src_json, dst_json = scratch / f"{key}.source.json", scratch / f"{key}.import.json"
        rename_path = scratch / f"{key}.rename.json"
        rename_path.write_text(json.dumps(info.get("rename_map", {}), ensure_ascii=False), encoding="utf-8")
        senv = _env(Path(info["sqlite_copy"]), media.parent / f"{key}_nomedia", hosts)
        (media.parent / f"{key}_nomedia").mkdir(exist_ok=True)
        r1 = _run(["render_store_signatures", "--store", info["store_slug"], "--host", "source-copy.rastisi.ir",
                   "--out", str(src_json), "--scratch-copy-confirmed"], senv)
        r2 = _run(["render_store_signatures", "--store", target.slug, "--host", target.hostname, "--out", str(dst_json),
                   "--offset", str(offsets[key]), "--stride", str(stride), "--rename-map", str(rename_path)], env)
        if r1.returncode or r2.returncode:
            report.fail("equivalence.render", f"render failed: {(r1.stderr + r2.stderr)[-800:]}", key)
            continue
        a = json.loads(src_json.read_text(encoding="utf-8"))
        b = json.loads(dst_json.read_text(encoding="utf-8"))
        bad = 0
        for url, sa in a.items():
            sb = b.get(url)
            if sb is None:
                bad += 1
                report.fail("equivalence.missing_url", f"{url} not rendered after import", key)
            elif sa["status"] != sb["status"]:
                bad += 1
                report.fail("equivalence.status", f"{url}: source {sa['status']} vs import {sb['status']}", key)
            elif "signature" in sa:
                diffs = diff_signatures(sa["signature"], sb.get("signature", {}))
                if diffs:
                    bad += 1
                    report.fail("equivalence.differs", f"{url}: " + "; ".join(diffs[:3]), key)
        non200 = [u for u, v in a.items() if v["status"] != 200]
        if non200:
            report.warn("equivalence.source_non200", f"{len(non200)} URL(s) did not answer 200 in the source either: {non200[:3]}", key)
        if bad == 0:
            report.ok("equivalence", f"{len(a)} page(s) render identically from the source database and from the imported bundle", key)
    return report
