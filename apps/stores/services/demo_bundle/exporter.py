"""Export one Store's presentation content into a bundle directory.

Run on the machine that still holds the original data (same code base, same
schema). The export contains no users, customers, orders, passwords or tokens:
every foreign key that points outside the bundle scope (users, industry
templates, ...) is nulled in the file.
"""

from __future__ import annotations

import json
import re
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


def rows_for(spec: contract.ModelSpec, store):
    model = model_for(spec.label)
    return model.objects.filter(_store_q(spec, store)).distinct().order_by("pk")


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


def export_store(store, out_dir: Path, *, key: str, media_root: Path) -> dict:
    out_dir = Path(out_dir)
    store_dir = out_dir / contract.STORES_DIR / key
    store_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / contract.MEDIA_DIR).mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    counts: dict[str, int] = {}
    media: dict[str, dict] = {}
    missing_media: list[dict] = []
    nulled_outside: dict[str, int] = {}

    for spec in contract.MODEL_SPECS:
        model = model_for(spec.label)
        qs = rows_for(spec, store)
        outside = _outside_fk_names(model)
        fields_with_files = [f.name for f in file_fields(model)]
        n = 0
        for rec in serializers.serialize("python", qs, fields=exportable_field_names(model, spec.label)):
            for name in outside:
                if rec["fields"].get(name) is not None:
                    nulled_outside[f"{spec.label}.{name}"] = nulled_outside.get(f"{spec.label}.{name}", 0) + 1
                    rec["fields"][name] = None
            for fname in fields_with_files:
                rel = rec["fields"].get(fname)
                if not rel:
                    continue
                if rel in media:
                    continue
                src = Path(media_root) / rel
                if not src.is_file():
                    missing_media.append({"path": rel, "model": spec.label, "pk": rec["pk"], "field": fname})
                    continue
                dst = out_dir / contract.MEDIA_DIR / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
                media[rel] = {"path": rel, "sha256": sha256_file(dst), "size": dst.stat().st_size}
            records.append(rec)
            n += 1
        counts[spec.label] = n

    (store_dir / contract.DATA_FILE).write_text(
        json.dumps(records, ensure_ascii=False, default=str), encoding="utf-8"
    )
    identity = {
        "source_slug": store.slug,
        "name": store.name,
        "admin_subdomain": store.admin_subdomain,
        "status": store.status,
        "source_hostnames": sorted(store.domains.values_list("hostname", flat=True)),
    }
    (store_dir / contract.STORE_FILE).write_text(
        json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "key": key,
        "identity": identity,
        "counts": counts,
        "media": sorted(media.values(), key=lambda m: m["path"]),
        "missing_media": missing_media,
        "nulled_outside_references": nulled_outside,
    }


def write_manifest(out_dir: Path, store_entries: list[dict], *, note: str = "") -> Path:
    manifest = {
        "format": contract.FORMAT_NAME,
        "version": contract.FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": note,
        "stores": {entry["key"]: entry for entry in store_entries},
    }
    path = Path(out_dir) / contract.MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
