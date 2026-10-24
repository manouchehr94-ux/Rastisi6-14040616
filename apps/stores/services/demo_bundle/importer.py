"""Import one store of a validated bundle into the current database.

Properties:

* **Idempotent** - rows are upserted by their preserved primary key inside one
  transaction; a second import changes nothing and creates no duplicates.
* **Tenant-safe** - a primary key that already belongs to a *different* store
  aborts the whole import; foreign keys to the Store are rewritten to the
  target store; nothing outside the bundle scope is ever touched.
* **Never fabricates settings silently** - a missing ``ShopSettings`` /
  ``FooterSettings`` in the bundle is provisioned empty via the platform's own
  ``provision_for`` and reported as ``MISSING SOURCE``.
* **Media verified** - files are copied with their sha256 re-checked; an
  existing file with different content is a conflict, never overwritten.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.db import connection, transaction
from django.core.management.color import no_style
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.content.models import FooterSettings
from apps.stores.models import Store, StoreDomain

from . import contract
from .exporter import _store_q
from .files import copy_atomic, model_for, safe_relative_media_path, sha256_file
from .report import Report
from .targets import TargetStore
from .validator import load_manifest, load_records, validate_bundle

#: One row per store, referenced by other rows: reuse an existing row's pk.
SINGLETONS = ("core.ShopSettings", "content.FooterSettings", "storefront_builder.StorefrontLayout")


class ImportAborted(Exception):
    def __init__(self, report: Report):
        super().__init__(report.to_text(show_pass=False))
        self.report = report


@dataclass
class ImportResult:
    store: Store | None = None
    created_store: bool = False
    rows: dict[str, int] = field(default_factory=dict)
    media_copied: int = 0
    media_identical: int = 0
    provisioned_empty: list[str] = field(default_factory=list)
    report: Report = field(default_factory=lambda: Report("import"))


def ensure_target_store(target: TargetStore) -> tuple[Store, bool]:
    from apps.stores.hostnames import normalize_admin_subdomain

    store, created = Store.objects.get_or_create(
        slug=target.slug,
        defaults={
            "name": target.name,
            "admin_subdomain": normalize_admin_subdomain(target.admin_subdomain),
            "status": Store.Status.ACTIVE,
            "onboarding_stage": Store.OnboardingStage.DONE,
            "onboarding_completed_at": timezone.now(),
        },
    )
    domain, domain_created = StoreDomain.objects.get_or_create(
        store=store,
        hostname=target.hostname,
        defaults={
            "is_primary": True,
            "domain_type": StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
            "verification_status": StoreDomain.VerificationStatus.VERIFIED,
            "verified_at": timezone.now(),
        },
    )
    return store, created


def _plan_records(records, store, report, key):
    """Rewrite store FKs, null out-of-scope FKs, map singleton pks.

    Returns (records, pk_remap). Raises ImportAborted on tenant conflicts.
    """
    records = copy.deepcopy(records)
    pk_remap: dict[str, dict[int, int]] = {}

    for label in SINGLETONS:
        model = model_for(label)
        existing = model.objects.filter(store=store).first()
        if existing is None:
            continue
        for rec in records:
            if rec["model"].lower() == label.lower() and rec["pk"] != existing.pk:
                pk_remap.setdefault(label, {})[rec["pk"]] = existing.pk
                rec["pk"] = existing.pk

    inside = {l.lower() for l in contract.SPEC_BY_LABEL}
    for rec in records:
        label = rec["model"]
        model = model_for(label)
        for f in model._meta.concrete_fields:
            if not f.is_relation:
                continue
            target = f.related_model._meta.label
            if target == "stores.Store":
                rec["fields"][f.name] = store.pk
            elif target.lower() not in inside:
                rec["fields"][f.name] = None
            else:
                remap = pk_remap.get(target)
                value = rec["fields"].get(f.name)
                if remap and value in remap:
                    rec["fields"][f.name] = remap[value]

    # Tenant guard: an existing row with this pk must already belong to `store`.
    conflicts = 0
    by_label: dict[str, list] = {}
    for rec in records:
        by_label.setdefault(_canon(rec["model"]), []).append(rec["pk"])
    for label, pks in by_label.items():
        model = model_for(label)
        spec = contract.SPEC_BY_LABEL[label]
        present = set(model.objects.filter(pk__in=pks).values_list("pk", flat=True))
        if not present:
            continue
        mine = set(
            model.objects.filter(pk__in=present).filter(_store_q(spec, store)).values_list("pk", flat=True)
        )
        for pk in sorted(present - mine):
            conflicts += 1
            report.fail(
                "tenant.pk_conflict",
                f"{label} pk={pk} already exists and belongs to another store; refusing to overwrite",
                key,
            )
    if conflicts:
        raise ImportAborted(report)
    return records, pk_remap


def _canon(label: str) -> str:
    for known in contract.SPEC_BY_LABEL:
        if known.lower() == label.lower():
            return known
    return label


def _copy_media(bundle_dir: Path, entry: dict, media_root: Path, report: Report, key: str, result: ImportResult, *, dry_run: bool):
    conflicts = 0
    for meta in entry.get("media", []):
        rel = safe_relative_media_path(meta["path"])
        src = bundle_dir / contract.MEDIA_DIR / rel
        dst = media_root / rel
        if dst.exists():
            if sha256_file(dst) == meta["sha256"]:
                result.media_identical += 1
                continue
            conflicts += 1
            report.fail("media.conflict", f"{rel} already exists in MEDIA_ROOT with different content", key)
            continue
        if not dry_run:
            copy_atomic(src, dst)
            if sha256_file(dst) != meta["sha256"]:
                dst.unlink(missing_ok=True)
                report.fail("media.copy_hash", f"{rel} corrupted during copy", key)
                conflicts += 1
                continue
        result.media_copied += 1
    if conflicts:
        raise ImportAborted(report)


def _reset_sequences(labels):
    models_ = [model_for(l) for l in labels]
    statements = connection.ops.sequence_reset_sql(no_style(), models_)
    if statements:
        with connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)


def import_store(
    bundle_dir,
    key: str,
    target: TargetStore,
    *,
    media_root: Path | None = None,
    dry_run: bool = False,
    prune: bool = False,
    allow_blocked: tuple[str, ...] = (),
) -> ImportResult:
    bundle_dir = Path(bundle_dir)
    media_root = Path(media_root or settings.MEDIA_ROOT)
    result = ImportResult()
    report = result.report
    report.title = f"import {key} -> {target.slug}"

    validation = validate_bundle(bundle_dir, targets={key: target})
    # only this store's findings can block this store's import
    own = [f for f in validation.findings if f.store in ("", key)]
    for f in own:
        report.add(f.level, f.code, f.message, f.store)
    if any(f.level == "FAIL" or (f.level == "BLOCKED" and f.code not in allow_blocked) for f in own):
        raise ImportAborted(report)
    manifest = load_manifest(bundle_dir)
    entry = manifest["stores"][key]
    records = load_records(bundle_dir, key)

    with transaction.atomic():
        store, created = ensure_target_store(target)
        result.store, result.created_store = store, created
        planned, _ = _plan_records(records, store, report, key)
        _copy_media(bundle_dir, entry, media_root, report, key, result, dry_run=dry_run)

        # Raw save (same mechanics as ``loaddata``): primary keys and timestamps
        # are preserved and model.save() overrides / signals are not run.
        # Foreign keys are DEFERRABLE INITIALLY DEFERRED, so row order inside
        # this transaction does not matter; constraints are checked at commit.
        objects = list(serializers.deserialize("python", planned))
        for obj in objects:
            obj.save()
            label = obj.object._meta.label
            result.rows[label] = result.rows.get(label, 0) + 1
        connection.check_constraints()

        if prune:
            _prune(store, planned, report, key)

        for label, provision in (("core.ShopSettings", ShopSettings), ("content.FooterSettings", FooterSettings)):
            if not provision.objects.filter(store=store).exists():
                provision.provision_for(store)
                result.provisioned_empty.append(label)
                report.blocked("settings.missing_source", f"{label} was not in the bundle; provisioned empty defaults only", key)
        if connection.vendor == "postgresql":
            _reset_sequences(list(contract.SPEC_BY_LABEL))
        if dry_run:
            transaction.set_rollback(True)
    report.ok("import.done", f"{sum(result.rows.values())} row(s) upserted for {target.slug}", key)
    return result


def _prune(store, planned, report, key):
    keep: dict[str, set] = {}
    for rec in planned:
        keep.setdefault(_canon(rec["model"]), set()).add(rec["pk"])
    for spec in reversed(contract.MODEL_SPECS):
        model = model_for(spec.label)
        stale = model.objects.filter(_store_q(spec, store)).exclude(pk__in=keep.get(spec.label, set()))
        n = stale.count()
        if n:
            stale.delete()
            report.warn("prune", f"deleted {n} stale {spec.label} row(s) not present in the bundle", key)
