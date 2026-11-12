"""Real PostgreSQL/Django non-atomic failure proof; disposable container only."""
import os
from pathlib import Path
if not Path('/.dockerenv').exists() or os.environ.get('PGDATABASE') != 'rastisi_test':
    raise SystemExit('requires disposable integration container')
from django.conf import settings
settings.configure(SECRET_KEY='local-test', INSTALLED_APPS=[], DATABASES={'default': {'ENGINE':'django.db.backends.postgresql', 'HOST':os.environ['PGHOST'], 'NAME':os.environ['PGDATABASE'], 'USER':os.environ['PGUSER'], 'PASSWORD':os.environ['PGPASSWORD']}})
import django
django.setup()
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState
from django.db.migrations.recorder import MigrationRecorder
MigrationRecorder(connection).ensure_schema()
migration = migrations.Migration('0001_non_atomic_probe', 'probe')
migration.atomic = False
migration.operations = [migrations.RunSQL('CREATE TABLE non_atomic_probe(id integer)'), migrations.RunSQL('SELECT column_that_does_not_exist')]
try:
    MigrationExecutor(connection).apply_migration(ProjectState(), migration)
except Exception:
    assert 'non_atomic_probe' in connection.introspection.table_names()
    assert not MigrationRecorder(connection).migration_qs.filter(app='probe', name='0001_non_atomic_probe').exists()
else:
    raise AssertionError('migration unexpectedly succeeded')
with connection.cursor() as cursor:
    cursor.execute('DROP TABLE non_atomic_probe')
print('PASS real non-atomic migration: partial SQL committed, recorder absent; automatic continuation would be unsafe')
