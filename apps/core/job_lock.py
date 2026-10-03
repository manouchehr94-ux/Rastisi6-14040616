"""Single-instance guard for cron-driven management commands (ADR-49: no queue/scheduler framework).

Every job here is already idempotent and row-lock safe; this only avoids two overlapping cron runs
doing the same (possibly slow) batch twice. PostgreSQL: session-level advisory lock, auto-released
if the process dies. Other databases (SQLite in dev/tests): no-op (always acquired)."""

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
