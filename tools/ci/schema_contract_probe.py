"""N-1 ORM/schema contract on CI's disposable upgrade_test_* database only.

Select every mapped column, validate UPDATE statements for every managed model,
then prove an old-code INSERT still works. UPDATE ... WHERE FALSE never changes
rows. This checks schema compatibility, not business workflow correctness.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shop_core.settings')
import django
django.setup()
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction

if not str(connection.settings_dict['NAME']).startswith('upgrade_test_'):
    raise SystemExit('schema contract probe requires a disposable upgrade_test_* database')

quote = connection.ops.quote_name
count = 0
with transaction.atomic():
    for model in apps.get_models():
        meta = model._meta
        if not meta.managed or meta.proxy:
            continue
        list(model._base_manager.all().values()[:1])
        columns = [f.column for f in meta.local_concrete_fields if not f.primary_key and not f.generated]
        if columns:
            sql = 'UPDATE %s SET %s WHERE FALSE' % (quote(meta.db_table), ', '.join('%s=%s' % (quote(c), quote(c)) for c in columns))
            with connection.cursor() as cursor:
                cursor.execute(sql)
        count += 1
    get_user_model().objects.create_user(username='n-minus-one-insert-probe', password='local-ci-only')
    transaction.set_rollback(True)
print('N-1 schema read/write contract passed for %d managed models; INSERT rolled back' % count)
