set -e
cd /home/user/Rastisi6-14040616
export DATABASE_URL="postgres://postgres@127.0.0.1:5544/stg_e2e" DJANGO_DEBUG=True DJANGO_SECRET_KEY=e2e-secret-key-not-for-prod
fuser -k 8765/tcp 2>/dev/null || true; sleep 1
/usr/bin/psql -q -h 127.0.0.1 -p 5544 -U postgres -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='stg_e2e'" >/dev/null; /usr/bin/psql -q -h 127.0.0.1 -p 5544 -U postgres -c "drop database if exists stg_e2e" -c "create database stg_e2e" >/dev/null
/usr/local/bin/python manage.py migrate -v0
/usr/local/bin/python manage.py shell < tools/engagement_e2e/seed_e2e.py >/dev/null
/usr/local/bin/python manage.py shell -c "
import json
from django.test import Client
from apps.cart.models import Coupon; from apps.stores.models import Store
s=Store.objects.get(slug='akhlaghi'); Coupon.objects.create(store=s, code='E2E10', type='percent', value=10, label='ده درصد')
c=Client(); c.login(username='09120000000', password='pass12345')
st=json.load(open('/tmp/e2e_state.json')); st['sessionid']=c.cookies['sessionid'].value; json.dump(st, open('/tmp/e2e_state.json','w'))" >/dev/null
(nohup /usr/local/bin/python manage.py runserver 127.0.0.1:8765 --noreload > /tmp/e2e_server.log 2>&1 &)
sleep 6
