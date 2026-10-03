"""Parallel device polling (real threads, PostgreSQL only): a queued message is handed to exactly one poller."""

import threading
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from apps.core.models import ShopSettings
from apps.sms.models import SmsOutboxItem
from apps.stores.models import Store


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks")
class ParallelPollTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.store = Store.objects.create(name="poll-race", slug="poll-race", status=Store.Status.ACTIVE)
        shop = ShopSettings.provision_for(self.store)
        shop.smsrasti_device_token = "race-token-1"
        shop.save()
        for i in range(6):
            SmsOutboxItem.objects.create(store=self.store, phone=f"0912000{i:04d}", message=f"m{i}")

    def test_no_message_is_handed_to_two_pollers(self):
        results, errors, lock = [], [], threading.Lock()
        barrier = threading.Barrier(6)

        def poller():
            try:
                barrier.wait()
                response = Client().get(reverse("sms:smsrasti-poll"), {"token": "race-token-1"})
                with lock:
                    results.append(response.json())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=poller) for _ in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        ids = [r["id"] for r in results if r.get("status") == "ok"]
        self.assertEqual(len(ids), len(set(ids)))  # never the same message twice
        self.assertEqual(SmsOutboxItem.objects.filter(status="sending").count(), len(ids))
        self.assertEqual(sum(1 for r in results if r.get("status") == "empty"), 6 - len(ids))
