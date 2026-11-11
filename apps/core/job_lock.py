"""Single-instance guard for cron-driven management commands (ADR-49: no queue/scheduler framework).

Every job here is already idempotent and row-lock safe; this only avoids two overlapping cron runs
doing the same (possibly slow) batch twice. PostgreSQL: session-level advisory lock, auto-released
if the process dies. Other databases (SQLite in dev/tests): no-op (always acquired)."""

import functools
import zlib
from contextlib import contextmanager

from django.db import connection


@contextmanager
def single_instance(name: str):
    """Yield ``True`` when this process owns the named job lock, ``False`` if another run holds it."""
    if connection.vendor != "postgresql":
        yield True
        return
    key = zlib.crc32(f"rastisi-job:{name}".encode()) & 0x7FFFFFFF
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cur.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [key])


def exclusive(name: str):
    """Decorator for ``BaseCommand.handle``: run under ``single_instance(name)``; when another run holds the lock print the
    standard «skipped» line and exit 0 (a skipped overlap is not a failure)."""

    def decorate(handle):
        @functools.wraps(handle)
        def wrapper(self, *args, **options):
            with single_instance(name) as acquired:
                if not acquired:
                    self.stdout.write(f"skipped: another {name} is still running")
                    return None
                return handle(self, *args, **options)

        return wrapper

    return decorate
