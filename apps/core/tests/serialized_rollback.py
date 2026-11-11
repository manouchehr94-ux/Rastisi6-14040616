"""Order-independent ``serialized_rollback`` for ``TransactionTestCase`` classes.

Why this exists (root cause of the recurring ``apps.sms.tests.test_gateway_live`` setUpClass error)
---------------------------------------------------------------------------------------------------
``serialized_rollback = True`` makes Django replay a snapshot of the migration-seeded rows (taken when the
test database was built) before each test of the class. A *plain* ``TransactionTestCase`` (no
``serialized_rollback``) flushes every table when it finishes and, unlike a serialized one, lets the flush
fire ``post_migrate``. That re-creates ``django_content_type`` / ``auth_permission`` rows with NEW primary
keys. Even a test that merely calls ``self.skipTest(...)`` from its body (the PostgreSQL-only concurrency
tests, skipped on SQLite) still runs that flush.

If the next ``serialized_rollback`` class then replays the snapshot, the snapshot's content types collide with
the freshly re-created ones on ``UNIQUE (app_label, model)`` and the class errors in ``setUpClass``. Whether it
happens depends only on which plain ``TransactionTestCase`` ran earlier in the same process (so it appears in
large or ``--parallel`` runs and never when the class runs alone).

Fix: before the snapshot is replayed, remove the rows ``post_migrate`` may have re-created. The cascade also
removes their permissions; the snapshot restores all of them with their original keys. When the database is
already empty (the normal case between two tests of the same class) this is a no-op. Tests only; no
application code or schema is involved.
"""

from django.db import connections


class SerializedRollbackSafeMixin:
    """Put FIRST in the bases of a ``TransactionTestCase`` that sets ``serialized_rollback = True``."""

    serialized_rollback = True

    @classmethod
    def _fixture_setup(cls):
        from django.contrib.contenttypes.models import ContentType

        for db_name in cls._databases_names(include_mirrors=False):
            if hasattr(connections[db_name], "_test_serialized_contents"):
                ContentType.objects.using(db_name).all().delete()
        ContentType.objects.clear_cache()
        super()._fixture_setup()
