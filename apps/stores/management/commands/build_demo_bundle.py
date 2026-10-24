"""Build the final demo bundle from two INDEPENDENT SQLite databases + media ZIPs.

    python manage.py build_demo_bundle ^
        --v5-sqlite D:\\in\\demo_v5.sqlite3     --v5-media-zip D:\\in\\demo_v5_media.zip ^
        --arch02-sqlite D:\\in\\demo_arch02.sqlite3 --arch02-media-zip D:\\in\\demo_arch02_media.zip ^
        --out D:\\out\\rastisi-demo-bundle

* The originals are only read (snapshotted); nothing on any server is touched.
* Colliding primary keys are resolved by a deterministic uniform offset; every
  foreign key, many-to-many value, Studio JSON id and variant combination key is
  rewritten with it. Nothing is dropped (all template versions, drafts, branding,
  banners, stories, media - also unreferenced files).
* ``--out`` is created ONLY if the bundle validates (exit 0). Exit 1 = FAIL,
  2 = BLOCKED (input missing/incomplete).
* By default a full scratch check runs too: a fresh scratch database imports the
  bundle twice (idempotency), integrity + HTTP are verified, and every page is
  rendered from the ORIGINAL database and from the import and compared.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.stores.services.demo_bundle import contract
from apps.stores.services.demo_bundle.converter import ConvertOptions, SourceSpec, convert
from apps.stores.services.demo_bundle.fullcheck import run_full_check
from apps.stores.services.demo_bundle.remap import RemapOptions
from apps.stores.services.demo_bundle.report import Report
from apps.stores.services.demo_bundle.targets import DEFAULT_TARGETS_PATH, load_targets


class Command(BaseCommand):
    help = "Convert two independent SQLite store databases + media ZIPs into one validated bundle."
    requires_system_checks = []  # never touches the project database

    def add_arguments(self, parser):
        for key, label in (("v5", "demo_v5"), ("arch02", "demo_arch02")):
            parser.add_argument(f"--{key}-sqlite", required=True, help=f"{label}.sqlite3")
            parser.add_argument(f"--{key}-media-zip", required=True, help=f"{label}_media.zip")
            parser.add_argument(f"--{key}-store", default=None, help="store slug inside that database (auto-detected when it is the only store with products)")
            parser.add_argument(f"--{key}-media-prefix", default=None, help="folder inside the ZIP that is MEDIA_ROOT (auto-detected)")
        parser.add_argument("--out", required=True, help="final bundle directory (must not exist / be empty; with --inspect-only it is not created)")
        parser.add_argument("--targets", default=None, help=f"targets manifest (default {DEFAULT_TARGETS_PATH.name})")
        parser.add_argument("--work-dir", default=None)
        parser.add_argument("--keep-work", action="store_true")
        parser.add_argument("--no-full-check", action="store_true", help="skip the scratch import + render-equivalence check")
        parser.add_argument("--skip-image-decode", action="store_true")
        parser.add_argument("--drop-unreferenced-media", action="store_true", help="omit ZIP files that no database row references")
        parser.add_argument("--allow-unknown-migrations", action="store_true")
        parser.add_argument("--map-json-key", action="append", default=[], metavar="KEY", help="Studio JSON key holding ONE id")
        parser.add_argument("--map-json-list-key", action="append", default=[], metavar="KEY", help="Studio JSON key holding a LIST of ids")
        parser.add_argument("--ignore-json-key", action="append", default=[], metavar="KEY", help="id-looking key that is NOT a reference")
        parser.add_argument("--keep-rejected", action="store_true")
        parser.add_argument("--report", default=None, help="write the JSON report here")
        parser.add_argument("--inspect-only", action="store_true", help="read + plan only (stores, ids, ZIP layout, unknown JSON keys); writes nothing")

    def handle(self, *args, **o):
        targets_path = Path(o["targets"]) if o["targets"] else DEFAULT_TARGETS_PATH
        targets = load_targets(targets_path)
        missing_keys = [k for k in ("demo_v5", "demo_arch02") if k not in targets]
        if missing_keys:
            raise CommandError(f"targets manifest lacks {missing_keys}")
        for stream in (sys.stdout, sys.stderr):  # Persian names must not crash a legacy Windows console
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass
        out = Path(o["out"])
        sources = []
        for opt, key in (("v5", "demo_v5"), ("arch02", "demo_arch02")):
            sources.append(SourceSpec(
                key=key, sqlite=Path(o[f"{opt}_sqlite"]), media_zip=Path(o[f"{opt}_media_zip"]),
                store_slug=o[f"{opt}_store"], media_prefix=o[f"{opt}_media_prefix"],
            ))
        absent = [str(p) for s in sources for p in (s.sqlite, s.media_zip) if not p.is_file()]
        if absent:
            report = Report("build_demo_bundle")
            for p in absent:
                report.blocked("input.missing", f"input file not found: {p}")
            self.stdout.write(report.to_text())
            sys.exit(2)

        work = Path(o["work_dir"]) if o["work_dir"] else Path(tempfile.mkdtemp(prefix="rastisi-build-"))
        options = ConvertOptions(
            remap=RemapOptions(
                extra_scalar_keys=frozenset(o["map_json_key"]), extra_list_keys=frozenset(o["map_json_list_key"]),
                ignore_keys=frozenset(o["ignore_json_key"]),
            ),
            allow_unknown_migrations=o["allow_unknown_migrations"], keep_unreferenced_media=not o["drop_unreferenced_media"],
            keep_rejected=o["keep_rejected"], decode_images=not o["skip_image_decode"], inspect_only=o["inspect_only"],
        )
        log = lambda m: self.stderr.write(m)  # noqa: E731 - progress goes to stderr, report to stdout
        try:
            result = convert(sources, out, targets=targets, options=options, work_dir=work, log=log)
            report = result.report
            if result.out_dir is not None and not o["no_full_check"] and not o["inspect_only"]:
                full = run_full_check(
                    result.out_dir, targets, result.sources, result.stride, result.offsets, work,
                    targets_path=targets_path if o["targets"] else None, log=log,
                )
                report.extend(full)
                if report.status != "PASS":
                    shutil.rmtree(result.out_dir, ignore_errors=True)
                    if o["keep_rejected"]:
                        self.stderr.write("note: --keep-rejected only applies to validator rejections; the bundle was removed")
            if result.out_dir is not None and report.status == "PASS":
                (result.out_dir / "CONVERSION_REPORT.json").write_text(report.to_json(), encoding="utf-8")
                (result.out_dir / "CONVERSION_REPORT.txt").write_text(report.to_text(), encoding="utf-8")
        finally:
            if not o["keep_work"]:
                shutil.rmtree(work, ignore_errors=True)
        text = report.to_text(show_pass=True)
        self.stdout.write(text)
        if o["report"]:
            Path(o["report"]).write_text(report.to_json(), encoding="utf-8")
        if report.status == "PASS" and o["inspect_only"]:
            self.stdout.write("\nINSPECTION ONLY - no bundle was written")
        elif report.status == "PASS":
            self.stdout.write(f"\nBUNDLE READY: {out}")
            self.stdout.write(f"  contains: {contract.MANIFEST_NAME}, {contract.STORES_DIR}/, {contract.MEDIA_DIR}/ (+ CONVERSION_REPORT.*)")
        sys.exit({"PASS": 0, "FAIL": 1, "BLOCKED": 2}[report.status])

