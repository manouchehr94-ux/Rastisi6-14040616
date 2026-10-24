"""Open an independent SQLite database of a RastiSi store as a READ-ONLY source.

The original file is never opened for writing and never modified: it is
snapshotted (SQLite online-backup API, so a ``-wal`` journal is honoured) into
a scratch directory, and only that copy is registered as an extra Django
database alias. If the copy was produced by an older revision of this code base
the missing migrations are applied to the COPY so the current models can read it.

Works on any OS (no shell, no server); the only requirements are Python and the
packages in ``requirements.txt``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

SQLITE_MAGIC = b"SQLite format 3\x00"


class SourceError(Exception):
    pass


@dataclass
class SourceDb:
    alias: str
    original: Path
    copy: Path
    applied_migrations: list[str] = field(default_factory=list)
    unknown_applied: list[str] = field(default_factory=list)


def _register_alias(alias: str, path: Path) -> None:
    """Attach the snapshot as a *dynamic* connection (not listed in ``settings.DATABASES``).

    Dynamic connections never leak into the project configuration and are exempt
    from Django's test-isolation guards, exactly like the clones the test runner makes.
    """
    from django.db.utils import load_backend

    settings_dict = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(path),
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
        "TEST": {"CHARSET": None, "COLLATION": None, "MIGRATE": True, "MIRROR": None, "NAME": None},
    }
    connections[alias] = load_backend(settings_dict["ENGINE"]).DatabaseWrapper(settings_dict, alias)


def snapshot_sqlite(original: Path, destination: Path) -> None:
    """Consistent copy of ``original`` using the SQLite backup API (read-only source)."""
    original = Path(original)
    if not original.is_file():
        raise SourceError(f"SQLite file not found: {original}")
    with open(original, "rb") as handle:
        if handle.read(16) != SQLITE_MAGIC:
            raise SourceError(f"{original} is not an SQLite 3 database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"{original.resolve().as_uri()}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    check = sqlite3.connect(str(destination))
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        check.close()
    if result != "ok":
        raise SourceError(f"{original}: SQLite integrity_check failed: {result}")
    if "django_migrations" not in tables or "stores_store" not in tables:
        raise SourceError(f"{original}: not a RastiSi database (no django_migrations / stores_store table)")


def open_source(original: Path, alias: str, work_dir: Path, *, allow_unknown_migrations: bool = False) -> SourceDb:
    copy = Path(work_dir) / f"{alias}.sqlite3"
    snapshot_sqlite(Path(original), copy)
    _register_alias(alias, copy)
    connection = connections[alias]
    executor = MigrationExecutor(connection)
    known = set(executor.loader.graph.nodes)
    applied = sorted(f"{app}.{name}" for app, name in executor.loader.applied_migrations)
    unknown = sorted(f"{app}.{name}" for app, name in executor.loader.applied_migrations if (app, name) not in known
                     and app in {a for a, _ in known})
    if unknown and not allow_unknown_migrations:
        raise SourceError(
            f"{original}: {len(unknown)} applied migration(s) are unknown to this code base "
            f"(e.g. {unknown[:3]}); it was produced by a different revision. "
            "Use the matching revision to export it, or pass --allow-unknown-migrations if you accept the risk."
        )
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        # Upgrade the COPY (never the original) so today's models can read it.
        call_command("migrate", database=alias, interactive=False, verbosity=0)
        executor = MigrationExecutor(connections[alias])
        applied = sorted(f"{app}.{name}" for app, name in executor.loader.applied_migrations)
    return SourceDb(alias=alias, original=Path(original), copy=copy, applied_migrations=applied, unknown_applied=unknown)


def close_source(alias: str) -> None:
    try:
        connections[alias].close()
    except Exception:  # noqa: BLE001 - closing is best effort
        pass
    try:
        del connections[alias]
    except AttributeError:
        pass


def list_stores(alias: str) -> list[dict]:
    from apps.catalog.models import Product
    from apps.stores.models import Store

    rows = []
    for store in Store.objects.using(alias).order_by("pk"):
        rows.append({
            "slug": store.slug,
            "name": store.name,
            "status": store.status,
            "products": Product.objects.using(alias).filter(store=store).count(),
            "hostnames": sorted(store.domains.using(alias).values_list("hostname", flat=True)),
        })
    return rows


def choose_store(alias: str, slug: str | None = None):
    """The demo store of a source database.

    ``slug`` wins when given. Otherwise the single store that has products is
    used (the empty ``akhlaghi`` store that migration ``stores.0002`` seeds in
    every database is ignored); more than one candidate is an error, never a guess.
    """
    from apps.stores.models import Store

    stores = list_stores(alias)
    if slug:
        store = Store.objects.using(alias).filter(slug=slug).first()
        if store is None:
            raise SourceError(f"store {slug!r} not found; stores in this database: {[s['slug'] for s in stores]}")
        return store
    candidates = [s for s in stores if s["products"] > 0]
    if len(candidates) == 1:
        return Store.objects.using(alias).get(slug=candidates[0]["slug"])
    if not candidates:
        raise SourceError(f"no store with products in this database (stores: {[s['slug'] for s in stores]})")
    raise SourceError(
        "more than one store has products; choose with --v5-store / --arch02-store: "
        + ", ".join(f"{s['slug']} ({s['products']} products)" for s in candidates)
    )
