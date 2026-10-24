"""Convert independent SQLite store databases + media ZIPs into ONE validated bundle.

    source k:  <key>.sqlite3 + <key>_media.zip      (stand-alone, possibly colliding keys)
         |  read-only snapshot, migrate the COPY if it is older than this code
         |  collect the store's rows (no users/orders/secrets)
         |  remap: uniform id offset  ->  pk, FK, M2M, Studio JSON ids, combination_key
         |  merge media (same path+same bytes = shared, same path+other bytes = renamed + rewritten)
         v
    bundle/  (manifest.json, stores/<key>/..., media/...)  ->  validator (must PASS)

Nothing is written to ``out_dir`` unless the validator returns PASS; a rejected
build is removed (or kept under ``<out>.rejected`` with ``keep_rejected``).
No part of this needs a server, a shell or network access.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import contract, exporter, remap
from .exporter import Collected
from .files import file_fields, long_path, model_for
from .media_zip import MediaZip, MediaZipError
from .report import Report
from .sqlite_source import SourceError, choose_store, close_source, open_source
from .targets import TargetStore
from .validator import dangling_json_refs, validate_bundle


@dataclass
class SourceSpec:
    key: str
    sqlite: Path
    media_zip: Path
    store_slug: str | None = None
    media_prefix: str | None = None


@dataclass
class ConvertOptions:
    remap: remap.RemapOptions = field(default_factory=remap.RemapOptions)
    allow_unknown_migrations: bool = False
    keep_unreferenced_media: bool = True
    keep_rejected: bool = False
    decode_images: bool = True
    #: read + plan only: open the sources, remap in memory, probe the ZIPs - write nothing
    inspect_only: bool = False


@dataclass
class ConvertResult:
    report: Report
    out_dir: Path | None = None
    work_dir: Path | None = None
    stride: int = 0
    offsets: dict[str, int] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    #: per source key: {"alias", "store_slug", "sqlite_copy", "rename_map", "offset"}
    sources: dict[str, dict] = field(default_factory=dict)


def _sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_rename(rel: str, key: str, taken: set[str]) -> str:
    directory, name = posixpath.split(rel)
    stem, ext = posixpath.splitext(name)
    candidate = posixpath.join(directory, f"{stem}--{key}{ext}")
    n = 2
    while candidate in taken:
        candidate = posixpath.join(directory, f"{stem}--{key}-{n}{ext}")
        n += 1
    return candidate


def _rewrite_file_values(records: list[dict], rename: dict[str, str]) -> None:
    if not rename:
        return
    cache: dict[str, list[str]] = {}
    for rec in records:
        label = rec["model"]
        if label not in cache:
            cache[label] = [f.name for f in file_fields(model_for(label))]
        for name in cache[label]:
            value = rec["fields"].get(name)
            if value in rename:
                rec["fields"][name] = rename[value]


def convert(
    sources: list[SourceSpec],
    out_dir: Path,
    *,
    targets: dict[str, TargetStore] | None = None,
    options: ConvertOptions | None = None,
    work_dir: Path | None = None,
    log=lambda message: None,
) -> ConvertResult:
    options = options or ConvertOptions()
    out_dir = Path(out_dir)
    report = Report("convert")
    result = ConvertResult(report=report)
    keys = [s.key for s in sources]
    if len(set(keys)) != len(keys):
        report.fail("source.duplicate_key", f"duplicate source keys: {keys}")
        return result
    if targets is not None:
        for key in keys:
            if key not in targets:
                report.fail("source.unknown_key", f"{key!r} is not a target in the manifest ({sorted(targets)})")
        if report.failed:
            return result
    if out_dir.exists() and any(out_dir.iterdir()):
        report.fail("out.not_empty", f"{out_dir} exists and is not empty; refusing to overwrite")
        return result

    work_dir = Path(work_dir or tempfile.mkdtemp(prefix="rastisi-convert-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    result.work_dir = work_dir
    staging = work_dir / "bundle"
    aliases: list[str] = []
    zips: dict[str, MediaZip] = {}
    try:
        collected: dict[str, Collected] = {}
        identities: dict[str, dict] = {}
        migrations_applied: dict[str, int] = {}
        for spec in sources:
            alias = f"src_{spec.key}"
            aliases.append(alias)
            log(f"[{spec.key}] snapshotting {spec.sqlite.name} ...")
            db = open_source(spec.sqlite, alias, work_dir, allow_unknown_migrations=options.allow_unknown_migrations)
            store = choose_store(alias, spec.store_slug)
            log(f"[{spec.key}] store {store.slug!r}; collecting rows ...")
            collected[spec.key] = exporter.collect_store(store, alias)
            identities[spec.key] = exporter.store_identity(store, alias)
            result.sources[spec.key] = {"alias": alias, "store_slug": store.slug, "sqlite_copy": db.copy}
            migrations_applied[spec.key] = len(db.applied_migrations)
            zips[spec.key] = MediaZip(spec.media_zip)
            report.ok("source.opened", f"{store.slug}: {sum(collected[spec.key].counts.values())} row(s) from {spec.sqlite.name}", spec.key)
            if collected[spec.key].counts.get("core.ShopSettings", 0) != 1:
                report.warn("source.shopsettings", "source store has no ShopSettings row (will be BLOCKED by the validator)", spec.key)

        # ---- collision-free numbering
        stride = remap.plan_stride([remap.max_pk(c.records) for c in collected.values()])
        offsets = {key: index * stride for index, key in enumerate(keys)}
        result.stride, result.offsets = stride, offsets
        report.ok("remap.plan", f"stride={stride}, offsets={offsets}")

        remapped: dict[str, list[dict]] = {}
        stats: dict[str, remap.RemapStats] = {}
        for key in keys:
            before = len(dangling_json_refs(collected[key].records))
            try:
                new_records, st = remap.remap_records(collected[key].records, offsets[key], options.remap)
            except remap.UnmappedReference as exc:
                report.fail("remap.unmapped_json_key", str(exc), key)
                return result
            problems = remap.assert_lossless(collected[key].records, new_records, offsets[key])
            for problem in problems[:10]:
                report.fail("remap.not_lossless", problem, key)
            after = len(dangling_json_refs(new_records))
            if after != before:
                report.fail("remap.dangling_changed", f"Studio JSON dangling references changed {before} -> {after}", key)
            for w in st.warnings[:20]:
                report.warn("remap.note", w, key)
            if before:
                report.warn("source.dangling_json_refs", f"{before} Studio JSON reference(s) were already dangling in the source (kept as is)", key)
            remapped[key], stats[key] = new_records, st
            report.ok(
                "remap.done",
                f"offset {offsets[key]}: rows={st.rows}, fk={st.fk_values}, m2m={st.m2m_values}, "
                f"json={sum(st.json_refs.values())} {st.json_refs}, combination_keys={st.combination_keys}", key,
            )
        if report.failed:
            return result

        if options.inspect_only:
            for key in keys:
                zf = zips[key]
                referenced = {rel for rel, *_ in collected[key].file_refs}
                prefix = zf.detect_prefix(referenced, next(s.media_prefix for s in sources if s.key == key))
                missing_refs = [rel for rel in sorted(referenced) if zf.info_for(rel) is None]
                level = report.blocked if missing_refs else report.ok
                level("inspect.media", f"ZIP root {prefix!r}: {len(referenced)} referenced, {len(missing_refs)} missing"
                      + (f" (e.g. {missing_refs[:3]})" if missing_refs else "")
                      + f", {len(zf.rooted_files())} file(s) under the root, {zf.junk} junk, {len(zf.entries) - len(zf.rooted_files())} outside", key)
            report.ok("inspect.done", "inspection only - nothing was written")
            return result

        # ---- media merge
        (staging / contract.MEDIA_DIR).mkdir(parents=True, exist_ok=True)
        placed: dict[str, str] = {}  # final relative path -> sha256
        media_entries: dict[str, list[dict]] = {}
        missing: dict[str, list[dict]] = {}
        conversion_notes: dict[str, dict] = {}
        for key in keys:
            zf = zips[key]
            refs = collected[key].file_refs
            referenced = {rel for rel, *_ in refs}
            prefix = zf.detect_prefix(referenced, next(s.media_prefix for s in sources if s.key == key))
            rooted = zf.rooted_files()
            rename: dict[str, str] = {}
            entries: dict[str, dict] = {}
            shared = 0
            miss: list[dict] = []
            wanted = list(dict.fromkeys(rel for rel, *_ in refs))
            if options.keep_unreferenced_media:
                wanted += [rel for rel in sorted(rooted) if rel not in set(wanted)]
            missing_refs = {rel for rel in referenced if zf.info_for(rel) is None}
            for rel, label, pk, fname in refs:
                if rel in missing_refs and not any(m["path"] == rel for m in miss):
                    miss.append({"path": rel, "model": label, "pk": pk + offsets[key], "field": fname})
            log(f"[{key}] media: prefix {prefix!r}, {len(referenced)} referenced, {len(missing_refs)} missing, {len(rooted)} in zip")
            for rel in wanted:
                if rel in missing_refs:
                    continue
                info = zf.info_for(rel)
                tmp = staging / ".tmp-media"
                sha, size = zf.copy_to(info, tmp)
                final = rel
                if final in placed:
                    if placed[final] == sha:
                        shared += 1
                        long_path(tmp).unlink()
                        entries[final] = {"path": final, "sha256": sha, "size": size}
                        continue
                    final = _unique_rename(rel, key, set(placed))
                    rename[rel] = final
                dst = long_path(staging / contract.MEDIA_DIR / final)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(long_path(tmp), dst)
                placed[final] = sha
                entries[final] = {"path": final, "sha256": sha, "size": size}
            _rewrite_file_values(remapped[key], rename)
            _rewrite_missing = [{**m, "path": rename.get(m["path"], m["path"])} for m in miss]
            media_entries[key] = sorted(entries.values(), key=lambda m: m["path"])
            missing[key] = _rewrite_missing
            conversion_notes[key] = {
                "media_prefix_in_zip": prefix, "referenced": len(referenced), "missing": len(missing_refs),
                "in_zip": len(rooted), "bundled": len(entries), "shared_with_earlier_source": shared,
                "renamed_due_to_collision": rename, "ignored_junk": zf.junk,
                "outside_media_root": len(zf.entries) - len(rooted),
            }
            if rename:
                report.warn("media.renamed", f"{len(rename)} file(s) shared a path with different content in an earlier source and were renamed", key)
            if missing_refs:
                report.warn("media.missing_in_zip", f"{len(missing_refs)} referenced file(s) are not in the ZIP", key)
            result.sources[key]["rename_map"] = rename

        # ---- write the bundle
        for key in keys:
            store_dir = staging / contract.STORES_DIR / key
            store_dir.mkdir(parents=True, exist_ok=True)
            (store_dir / contract.DATA_FILE).write_text(
                json.dumps(remapped[key], ensure_ascii=False, default=str), encoding="utf-8")
            (store_dir / contract.STORE_FILE).write_text(
                json.dumps(identities[key], ensure_ascii=False, indent=2), encoding="utf-8")
        counts = {k: _counts(remapped[k]) for k in keys}
        entries_for_manifest = []
        for spec in sources:
            key = spec.key
            entries_for_manifest.append({
                "key": key, "identity": identities[key], "counts": counts[key],
                "media": media_entries[key], "missing_media": missing[key],
                "nulled_outside_references": collected[key].nulled_outside,
                "conversion": {
                    "source_sqlite": spec.sqlite.name, "source_sqlite_sha256": _sha256_bytes(spec.sqlite),
                    "source_media_zip": spec.media_zip.name, "source_media_zip_sha256": zips[key].sha256(),
                    "source_store_slug": result.sources[key]["store_slug"],
                    "id_offset": offsets[key], "applied_migrations_in_copy": migrations_applied[key],
                    "remapped": {"rows": stats[key].rows, "fk": stats[key].fk_values, "m2m": stats[key].m2m_values,
                                 "json": stats[key].json_refs, "combination_keys": stats[key].combination_keys},
                    "media": conversion_notes[key],
                },
            })
        exporter.write_manifest(
            staging, entries_for_manifest,
            note="built by build_demo_bundle from independent SQLite sources",
            extra={"conversion": {"tool": "build_demo_bundle", "stride": stride, "offsets": offsets,
                                  "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
        )

        # ---- full validation (nothing is published unless this passes)
        log("validating the bundle ...")
        validation = validate_bundle(staging, targets=targets, decode_images=options.decode_images)
        report.extend(validation)
        result.summary = {k: counts[k] for k in keys}
        if report.status != "PASS":
            if options.keep_rejected:
                rejected = out_dir.with_name(out_dir.name + ".rejected")
                if rejected.exists():
                    shutil.rmtree(rejected)
                shutil.move(str(staging), str(rejected))
                report.warn("out.rejected_kept", f"rejected bundle kept at {rejected}")
            return result
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        if out_dir.exists():
            out_dir.rmdir()
        shutil.move(str(staging), str(out_dir))
        result.out_dir = out_dir
        return result
    except (SourceError, MediaZipError, OSError) as exc:
        report.fail("convert.error", f"{type(exc).__name__}: {exc}")
        return result
    finally:
        for z in zips.values():
            z.close()
        for alias in aliases:
            close_source(alias)


def _counts(records: list[dict]) -> dict[str, int]:
    out = {label: 0 for label in contract.SPEC_BY_LABEL}
    lowered = {label.lower(): label for label in contract.SPEC_BY_LABEL}
    for rec in records:
        out[lowered[rec["model"]]] += 1
    return out
