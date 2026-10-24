"""Export one Store's presentation content into a bundle directory.

Run on the machine that still holds the original data (same code base, same
schema). The export contains no users, customers, orders, passwords or tokens:
every foreign key that points outside the bundle scope (users, industry
templates, ...) is nulled in the file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from django.core import serializers
from django.db.models import Q

from . import contract
from .files import file_fields, model_for, sha256_file


def _store_q(spec: contract.ModelSpec, store) -> Q:
    q = Q()
    for path in spec.store_paths:
        q |= Q(**{path: store})
    return q


def rows_for(spec: contract.ModelSpec, store, using: str = "default"):
    model = model_for(spec.label)
    return model.objects.using(using).filter(_store_q(spec, store)).distinct().order_by("pk")


def _store_field_names(model) -> set[str]:
    return {
        f.name for f in model._meta.concrete_fields
        if f.is_relation and f.related_model._meta.label == "stores.Store"
    }


def _outside_fk_names(model) -> set[str]:
    inside = set(contract.SPEC_BY_LABEL)
    names = set()
    for f in model._meta.concrete_fields:
        if f.is_relation and f.related_model._meta.label not in inside | {"stores.Store"}:
            names.add(f.name)
    return names


def exportable_field_names(model, label: str) -> list[str]:
    """Concrete non-PK field names minus credential-bearing columns."""
    pattern = re.compile(contract.SECRET_FIELD_PATTERN, re.I)
    dropped = set(contract.SECRET_FIELDS.get(label, ()))
    return [
        f.name for f in model._meta.concrete_fields
        if not f.primary_key and f.name not in dropped and not pattern.search(f.name)
    ]


@dataclass
class Collected:
    """Everything one store contributes, before any file is written."""

    records: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    #: ``(media-relative path, model label, pk, field name)`` for every non-empty FileField value
    file_refs: list[tuple[str, str, int, str]] = field(default_factory=list)
    nulled_outside: dict[str, int] = field(default_factory=dict)
    skipped_models: dict[str, int] = field(default_factory=dict)


def collect_store(store, using: str = "default") -> Collected:
    """Serialize one store's in-scope rows from database ``using`` (read-only).

    Credential columns are never serialized and foreign keys that leave the
    bundle scope (users, industry templates, ...) are nulled.
    """
    out = Collected()
    for spec in contract.MODEL_SPECS:
        model = model_for(spec.label)
        qs = rows_for(spec, store, using)
        outside = _outside_fk_names(model)
        fields_with_files = [f.name for f in file_fields(model)]
        n = 0
        for rec in serializers.serialize("python", qs, fields=exportable_field_names(model, spec.label)):
            for name in outside:
                if rec["fields"].get(name) is not None:
                    key = f"{spec.label}.{name}"
                    out.nulled_outside[key] = out.nulled_outside.get(key, 0) + 1
                    rec["fields"][name] = None
            for fname in fields_with_files:
                rel = rec["fields"].get(fname)
                if rel:
                    out.file_refs.append((rel, spec.label, rec["pk"], fname))
            out.records.append(rec)
            n += 1
        out.counts[spec.label] = n
    return out


def store_identity(store, using: str = "default") -> dict:
    return {
        "source_slug": store.slug,
        "name": store.name,
        "admin_subdomain": store.admin_subdomain,
        "status": store.status,
        "source_hostnames": sorted(store.domains.using(using).values_list("hostname", flat=True)),
    }


def export_store(store, out_dir: Path, *, key: str, media_root: Path, using: str = "default") -> dict:
    out_dir = Path(out_dir)
    store_dir = out_dir / contract.STORES_DIR / key
    store_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / contract.MEDIA_DIR).mkdir(parents=True, exist_ok=True)

    collected = collect_store(store, using)
    media: dict[str, dict] = {}
    missing_media: list[dict] = []
    for rel, label, pk, fname in collected.file_refs:
        if rel in media or any(m["path"] == rel for m in missing_media):
            continue
        src = Path(media_root) / rel
        if not src.is_file():
            missing_media.append({"path": rel, "model": label, "pk": pk, "field": fname})
            continue
        dst = out_dir / contract.MEDIA_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        media[rel] = {"path": rel, "sha256": sha256_file(dst), "size": dst.stat().st_size}

    (store_dir / contract.DATA_FILE).write_text(
        json.dumps(collected.records, ensure_ascii=False, default=str), encoding="utf-8"
    )
    identity = store_identity(store, using)
    (store_dir / contract.STORE_FILE).write_text(
        json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "key": key,
        "identity": identity,
        "counts": collected.counts,
        "media": sorted(media.values(), key=lambda m: m["path"]),
        "missing_media": missing_media,
        "nulled_outside_references": collected.nulled_outside,
    }


def write_manifest(out_dir: Path, store_entries: list[dict], *, note: str = "", extra: dict | None = None) -> Path:
    manifest = {
        "format": contract.FORMAT_NAME,
        "version": contract.FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": note,
        "stores": {entry["key"]: entry for entry in store_entries},
    }
    if extra:
        manifest.update(extra)
    path = Path(out_dir) / contract.MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
