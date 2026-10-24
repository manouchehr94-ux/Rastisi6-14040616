"""Validate a bundle directory WITHOUT touching the database.

Everything the importer relies on is checked here first: format, JSON, model
scope, counts, media presence and hashes, image decodability, reference closure
(foreign keys and Studio JSON ids), Studio completeness (published version with
all six page types) and primary-key disjointness across the stores of one bundle.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from . import contract
from .files import UnsafeMediaPath, file_fields, model_for, safe_relative_media_path, sha256_file
from .report import Report

_JSON_CONFIG_FIELDS = {
    "storefront_builder.StorefrontLayoutVersion": ("header_config", "footer_config", "appearance_config"),
    "storefront_builder.StorefrontPage": ("page_appearance_overrides",),
    "storefront_builder.StorefrontSection": ("settings",),
    "storefront_builder.StorefrontContainer": ("settings",),
    "storefront_builder.StorefrontCell": ("settings",),
}


def load_manifest(bundle_dir: Path) -> dict:
    return json.loads((Path(bundle_dir) / contract.MANIFEST_NAME).read_text(encoding="utf-8"))


def load_records(bundle_dir: Path, key: str) -> list[dict]:
    path = Path(bundle_dir) / contract.STORES_DIR / key / contract.DATA_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_json_refs(value, found):
    if isinstance(value, dict):
        for k, v in value.items():
            target = contract.JSON_REFERENCE_KEYS.get(k)
            if target is not None:
                ids = v if isinstance(v, list) else [v]
                for item in ids:
                    if isinstance(item, bool):
                        continue
                    if isinstance(item, int) and item > 0:
                        found.append((k, target, item))
                    elif isinstance(item, str) and item.isdigit() and int(item) > 0:
                        found.append((k, target, int(item)))
            _walk_json_refs(v, found)
    elif isinstance(value, list):
        for item in value:
            _walk_json_refs(item, found)


def validate_bundle(
    bundle_dir,
    *,
    targets: dict | None = None,
    strict_expected: bool = False,
    decode_images: bool = True,
) -> Report:
    bundle_dir = Path(bundle_dir)
    report = Report(f"bundle {bundle_dir}")

    if not (bundle_dir / contract.MANIFEST_NAME).is_file():
        report.blocked(
            "bundle.missing",
            f"{contract.MANIFEST_NAME} not found in {bundle_dir} - the original store data bundle has not been supplied",
        )
        return report
    try:
        manifest = load_manifest(bundle_dir)
    except (OSError, ValueError) as exc:
        report.fail("manifest.unreadable", str(exc))
        return report
    if manifest.get("format") != contract.FORMAT_NAME or manifest.get("version") != contract.FORMAT_VERSION:
        report.fail("manifest.format", f"unsupported format {manifest.get('format')!r} v{manifest.get('version')!r}")
        return report
    report.ok("manifest.format", f"{contract.FORMAT_NAME} v{contract.FORMAT_VERSION}")

    stores = manifest.get("stores") or {}
    if targets is not None:
        for key in targets:
            if key not in stores:
                report.blocked("store.missing", f"bundle has no data for target store {key!r}", key)
    if not stores:
        report.fail("manifest.empty", "bundle contains no stores")
        return report

    pks_by_store: dict[str, dict[str, set]] = {}
    for key, entry in stores.items():
        pks_by_store[key] = _validate_store(
            bundle_dir, key, entry, report, targets=targets, strict_expected=strict_expected,
            decode_images=decode_images,
        )

    # Primary keys are preserved => they must not collide between stores of one bundle.
    seen: dict[tuple[str, int], str] = {}
    collisions = 0
    for key, by_label in pks_by_store.items():
        for label, pks in by_label.items():
            for pk in pks:
                owner = seen.setdefault((label, pk), key)
                if owner != key:
                    collisions += 1
                    if collisions <= 10:
                        report.fail("pk.collision", f"{label} pk={pk} exists in stores {owner!r} and {key!r}", key)
    if collisions:
        report.fail(
            "pk.collision.total",
            f"{collisions} primary-key collision(s) between stores; export both stores from the SAME source database",
        )
    elif len(pks_by_store) > 1:
        report.ok("pk.disjoint", "primary keys are disjoint between the stores in this bundle")
    return report


def _validate_store(bundle_dir, key, entry, report, *, targets, strict_expected, decode_images):
    pks: dict[str, set] = defaultdict(set)
    data_path = bundle_dir / contract.STORES_DIR / key / contract.DATA_FILE
    if not data_path.is_file():
        report.fail("data.missing", f"{data_path} not found", key)
        return pks
    try:
        records = json.loads(data_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        report.fail("data.unreadable", str(exc), key)
        return pks

    by_label: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        label = rec.get("model", "")
        if label.lower() not in {l.lower() for l in contract.SPEC_BY_LABEL}:
            report.fail("model.out_of_scope", f"record of model {label!r} is not part of the bundle scope", key)
            continue
        by_label[_canonical(label)].append(rec)
        pks[_canonical(label)].add(rec["pk"])

    # counts
    declared = entry.get("counts", {})
    for label in contract.SPEC_BY_LABEL:
        if len(by_label.get(label, [])) != declared.get(label, 0):
            report.fail(
                "count.mismatch",
                f"{label}: manifest says {declared.get(label, 0)}, data.json has {len(by_label.get(label, []))}",
                key,
            )
    report.ok("count.summary", ", ".join(f"{l.split('.')[-1]}={len(by_label.get(l, []))}" for l in contract.SPEC_BY_LABEL if by_label.get(l)), key)

    _check_secrets(key, by_label, report)
    _check_media(bundle_dir, key, entry, by_label, report, decode_images=decode_images)
    _check_fk_closure(key, by_label, pks, report)
    _check_json_refs(key, by_label, pks, report)
    _check_studio(key, by_label, report)
    _check_singletons(key, by_label, report)
    _check_expected(key, by_label, entry, targets, strict_expected, report)
    return pks


def _check_secrets(key, by_label, report):
    pattern = re.compile(contract.SECRET_FIELD_PATTERN, re.I)
    leaks = 0
    for label, recs in by_label.items():
        dropped = set(contract.SECRET_FIELDS.get(label, ()))
        for rec in recs:
            for name, value in rec["fields"].items():
                if value not in (None, "", [], {}) and (name in dropped or pattern.search(name)):
                    leaks += 1
                    if leaks <= 10:
                        report.fail("secret.in_bundle", f"{label} pk={rec['pk']} carries credential field {name!r}", key)
    if not leaks:
        report.ok("secret.none", "no credential-bearing field carries a value", key)


def _canonical(label: str) -> str:
    for known in contract.SPEC_BY_LABEL:
        if known.lower() == label.lower():
            return known
    return label


def _check_media(bundle_dir, key, entry, by_label, report, *, decode_images):
    declared = {m["path"]: m for m in entry.get("media", [])}
    referenced: dict[str, tuple[str, int, str]] = {}
    for label, recs in by_label.items():
        model = model_for(label)
        for field in file_fields(model):
            for rec in recs:
                rel = rec["fields"].get(field.name)
                if rel:
                    referenced.setdefault(rel, (label, rec["pk"], field.name))
    for item in entry.get("missing_media", []):
        report.blocked(
            "media.missing_at_export",
            f"{item['model']} pk={item['pk']} {item['field']} -> {item['path']} was already absent on the source",
            key,
        )
    bad = 0
    for rel, (label, pk, fname) in sorted(referenced.items()):
        try:
            safe = safe_relative_media_path(rel)
        except UnsafeMediaPath as exc:
            report.fail("media.unsafe_path", str(exc), key)
            bad += 1
            continue
        if any(m["path"] == rel for m in entry.get("missing_media", [])):
            continue
        meta = declared.get(rel)
        path = bundle_dir / contract.MEDIA_DIR / safe
        if meta is None or not path.is_file():
            report.fail("media.missing", f"{label} pk={pk}.{fname} references {rel} which is not in the bundle", key)
            bad += 1
            continue
        if path.stat().st_size == 0:
            report.fail("media.empty", f"{rel} is zero bytes", key)
            bad += 1
            continue
        if sha256_file(path) != meta["sha256"]:
            report.fail("media.hash", f"{rel} sha256 differs from manifest", key)
            bad += 1
            continue
        if decode_images and rel.lower().rsplit(".", 1)[-1] in {"jpg", "jpeg", "png", "webp", "gif"}:
            try:
                from PIL import Image

                with Image.open(path) as img:
                    img.verify()
            except Exception as exc:  # noqa: BLE001 - any decode problem is a failure
                report.fail("media.undecodable", f"{rel}: {exc}", key)
                bad += 1
    unused = set(declared) - set(referenced)
    if unused:
        report.warn("media.unreferenced", f"{len(unused)} bundled file(s) are not referenced by any row", key)
    if not bad:
        report.ok("media.ok", f"{len(referenced)} referenced file(s) present, hashed and decodable", key)


def _check_fk_closure(key, by_label, pks, report):
    broken = 0
    for label, recs in by_label.items():
        model = model_for(label)
        for field in model._meta.concrete_fields:
            if not field.is_relation:
                continue
            target = _canonical(field.related_model._meta.label)
            if target not in contract.SPEC_BY_LABEL:
                continue
            for rec in recs:
                value = rec["fields"].get(field.name)
                if value is None:
                    continue
                if value not in pks[target]:
                    broken += 1
                    if broken <= 20:
                        report.fail(
                            "fk.broken",
                            f"{label} pk={rec['pk']}.{field.name} -> {target} pk={value} is not in this store's data",
                            key,
                        )
        for m2m in model._meta.many_to_many:
            target = _canonical(m2m.related_model._meta.label)
            for rec in recs:
                for value in rec["fields"].get(m2m.name, []) or []:
                    if value not in pks[target]:
                        broken += 1
                        if broken <= 20:
                            report.fail("fk.broken", f"{label} pk={rec['pk']}.{m2m.name} -> {target} pk={value} missing", key)
    if broken:
        report.fail("fk.broken.total", f"{broken} broken or cross-store reference(s)", key)
    else:
        report.ok("fk.closed", "every foreign key points to a row of the same store", key)


def _check_json_refs(key, by_label, pks, report):
    missing = 0
    for label, fields in _JSON_CONFIG_FIELDS.items():
        for rec in by_label.get(label, []):
            for fname in fields:
                found: list = []
                _walk_json_refs(rec["fields"].get(fname), found)
                for jkey, target, pk in found:
                    if pk not in pks[target]:
                        missing += 1
                        if missing <= 20:
                            report.warn(
                                "json.ref_missing",
                                f"{label} pk={rec['pk']}.{fname}[{jkey}] -> {target} pk={pk} not in this store (fails closed at render time)",
                                key,
                            )
    if missing:
        report.warn("json.ref_missing.total", f"{missing} Studio JSON reference(s) do not resolve", key)
    else:
        report.ok("json.refs", "all Studio JSON id references resolve inside the store", key)


def _check_studio(key, by_label, report):
    layouts = by_label.get("storefront_builder.StorefrontLayout", [])
    if not layouts:
        report.blocked("studio.layout_missing", "no StorefrontLayout in the bundle: the original Studio design is absent", key)
        return
    layout = layouts[0]
    published_id = layout["fields"].get("published_version")
    versions = {v["pk"]: v for v in by_label.get("storefront_builder.StorefrontLayoutVersion", [])}
    if not published_id or published_id not in versions:
        report.fail("studio.no_published", "layout has no published version in the bundle", key)
        return
    if versions[published_id]["fields"].get("status") != "published":
        report.fail("studio.published_status", "layout.published_version is not in status 'published'", key)
    types = {
        p["fields"]["page_type"]
        for p in by_label.get("storefront_builder.StorefrontPage", [])
        if p["fields"]["version"] == published_id
    }
    absent = [t for t in contract.REQUIRED_PAGE_TYPES if t not in types]
    if absent:
        report.fail("studio.pages", f"published version lacks page type(s): {', '.join(absent)}", key)
    else:
        report.ok("studio.pages", f"published version v{versions[published_id]['fields'].get('version_number')} has all six page types", key)
    draft_id = layout["fields"].get("draft_version")
    if draft_id and draft_id not in versions:
        report.fail("studio.draft_missing", "layout.draft_version is not in the bundle", key)
    statuses = defaultdict(int)
    for v in versions.values():
        statuses[v["fields"].get("status")] += 1
    report.ok("studio.versions", ", ".join(f"{k}={n}" for k, n in sorted(statuses.items())), key)


def _check_singletons(key, by_label, report):
    for label in ("core.ShopSettings", "content.FooterSettings"):
        n = len(by_label.get(label, []))
        if n == 1:
            report.ok("singleton", f"exactly one {label}", key)
        elif n == 0:
            report.blocked(
                "singleton.missing",
                f"{label} absent from the bundle (source settings missing); the importer would only provision an empty default",
                key,
            )
        else:
            report.fail("singleton.multiple", f"{n} rows of {label} for one store", key)


def _check_expected(key, by_label, entry, targets, strict, report):
    if not targets or key not in targets:
        return
    for label, expected in targets[key].expected.items():
        if label == "media_files":
            actual = len(entry.get("media", []))
        else:
            actual = len(by_label.get(label, []))
        if actual == expected:
            report.ok("expected.match", f"{label}: {actual} == reported {expected}", key)
        else:
            msg = f"{label}: bundle has {actual}, previous deployment reported {expected}"
            (report.fail if strict else report.warn)("expected.differs", msg, key)
