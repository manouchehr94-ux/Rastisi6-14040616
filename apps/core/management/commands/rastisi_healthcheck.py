"""Deployment health check: database, migrations, shared cache, file roots.

Read-only except for a short create-and-delete probe file in each writable root.
Exit code: 0 = healthy, 1 = at least one check failed.
"""

import os
import sys
import uuid
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Check database, pending migrations, cache and static/media roots."

    def handle(self, *args, **opts):
        failures = []

        def record(name, ok, detail=""):
            self.stdout.write(f"{'OK  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
            if not ok:
                failures.append(name)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            record("database", True, connection.vendor)
        except Exception as exc:  # noqa: BLE001
            record("database", False, str(exc))

        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            record("migrations", not pending, f"{len(pending)} pending" if pending else "all applied")
        except Exception as exc:  # noqa: BLE001
            record("migrations", False, str(exc))

        try:
            key = f"rastisi-health-{uuid.uuid4().hex}"
            cache.set(key, "1", 5)
            record("cache", cache.get(key) == "1")
            cache.delete(key)
        except Exception as exc:  # noqa: BLE001
            record("cache", False, str(exc))

        static_root = Path(settings.STATIC_ROOT)
        collected = static_root.is_dir() and any(static_root.iterdir())
        record("static_root", collected, f"{static_root} ({'collected' if collected else 'empty or missing - run collectstatic'})")
        for label, root in (("media_root", settings.MEDIA_ROOT), ("private_media_root", settings.PRIVATE_MEDIA_ROOT)):
            root = Path(root)
            try:
                root.mkdir(parents=True, exist_ok=True)
                probe = root / f".health-{uuid.uuid4().hex}"
                probe.write_text("x")
                probe.unlink()
                record(label, True, str(root))
            except OSError as exc:
                record(label, False, f"{root}: {exc}")

        if settings.DEBUG and not os.environ.get("RASTISI_HEALTHCHECK_ALLOW_DEBUG"):
            record("debug_off", False, "DJANGO_DEBUG is on")
        sys.exit(1 if failures else 0)
