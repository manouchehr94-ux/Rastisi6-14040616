"""Snooze × Web Push at the delivery-worker boundary: a currently snoozed item is never pushed; no attempt is burned, no dead-letter; after the snooze ends the usual checks
(read / archived / access / preference) decide; no duplicate delivery. Fake transport only."""

from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.notifications.models import InboxItem, NotificationDelivery, NotificationPreference
from apps.notifications.services import channel_delivery as cd
from apps.notifications.services import inbox_engine as eng
from apps.notifications.services import inbox_service as inbox
from apps.notifications.services import scope as S
from apps.notifications.services import webpush
from apps.notifications.tests.test_inbox_engine import VALID_SUB


@override_settings(RASTISI_NOTIF_WEBPUSH_ENABLED=True, RASTISI_VAPID_SUBJECT="mailto:ops@example.test")
class SnoozeVsPushTests(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        patcher = override_settings(RASTISI_VAPID_PRIVATE_KEY=webpush.generate_keypair()["private"])
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.key = S.key_for(self.store)
        NotificationPreference.objects.update_or_create(user=self.owner, scope_key=self.key, defaults={"browser_enabled": True})
        webpush.register(self.owner, self.key, VALID_SUB)
        self.n = 0

    def item(self, severity=None):
        self.n += 1
        kw = {"severity": severity} if severity else {}
        ev = eng.publish("order.canceled", store=self.store, title=f"لغو {self.n}", link_kwargs={"code": self.order.code}, dedupe_key=f"sn{self.n}", **kw)
        return InboxItem.objects.get(event=ev, user=self.owner)

    def delivery(self, item):
        return NotificationDelivery.objects.get(inbox_item=item, channel="web_push")

    def work(self, now=None):
        calls = []
        def transport(endpoint, headers):
            calls.append(endpoint)
            return webpush.PushResult(201)
        return cd.deliver_pending(now=now, transports={"web_push": transport}), calls

    def test_a_snoozed_item_is_not_pushed_and_nothing_is_burned_or_dead_lettered(self):
        item = self.item()
        inbox.mark(item, "snooze", snooze="1h")
        result, calls = self.work()
        self.assertEqual(calls, [])
        d = self.delivery(item)
        self.assertEqual((d.status, d.attempts, d.last_error), ("pending", 0, ""))
        self.assertGreater(d.next_attempt_at, timezone.now() + timedelta(minutes=50))      # deferred to the end of the snooze
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(result["failed"] + result["skipped"], 0)

    def test_the_worker_does_not_touch_it_again_before_the_snooze_ends(self):
        item = self.item()
        inbox.mark(item, "snooze", snooze="1h")
        self.work()
        result, calls = self.work()
        self.assertEqual((result["processed"], calls), (0, []))

    def test_after_the_snooze_expires_an_unread_item_is_pushed_exactly_once(self):
        item = self.item()
        inbox.mark(item, "snooze", snooze="1h")
        self.work()
        later = timezone.now() + timedelta(hours=1, minutes=5)
        result, calls = self.work(now=later)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.delivery(item).status, "delivered")
        self.assertEqual(self.work(now=later + timedelta(minutes=10))[1], [])                # never twice

    def test_after_the_snooze_a_read_or_archived_item_is_skipped_not_pushed(self):
        read, archived = self.item(), self.item()
        for it in (read, archived):
            inbox.mark(it, "snooze", snooze="1h")
        self.work()
        inbox.mark(read, "read")
        inbox.mark(archived, "archive")
        _, calls = self.work(now=timezone.now() + timedelta(hours=2))
        self.assertEqual(calls, [])
        self.assertEqual(self.delivery(read).skip_reason, "already_seen")
        self.assertEqual(self.delivery(archived).skip_reason, "already_seen")

    def test_unsnoozing_early_keeps_the_push_deferred_until_the_original_end_then_delivers_it_once(self):
        """Conservative by design: a deferred push is re-evaluated at the ORIGINAL snooze end (the in-app item becomes visible immediately; the OS push never fires earlier)."""
        item = self.item()
        inbox.mark(item, "snooze", snooze="1h")
        self.work()
        inbox.mark(item, "unsnooze")
        self.assertEqual(self.work()[1], [])                                               # not pushed early
        _, calls = self.work(now=timezone.now() + timedelta(hours=1, minutes=5))
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.work(now=timezone.now() + timedelta(hours=2))[1], [])         # exactly once

    def test_a_very_long_snooze_is_skipped_instead_of_pushing_a_stale_reminder_later(self):
        item = self.item()
        inbox.mark(item, "snooze", snooze="week")
        result, calls = self.work()
        self.assertEqual(calls, [])
        d = self.delivery(item)
        self.assertEqual((d.status, d.skip_reason), ("skipped", "snoozed_beyond_window"))
        self.assertNotEqual(d.status, "dead")

    def test_critical_items_also_honour_an_explicit_snooze(self):
        item = self.item(severity=4)
        inbox.mark(item, "snooze", snooze="1h")
        _, calls = self.work()
        self.assertEqual(calls, [])
        self.assertEqual(self.delivery(item).status, "pending")

    def test_preferences_and_access_still_win_after_a_snooze(self):
        item = self.item()
        inbox.mark(item, "snooze", snooze="1h")
        self.work()
        NotificationPreference.objects.filter(user=self.owner).update(browser_enabled=False)
        _, calls = self.work(now=timezone.now() + timedelta(hours=2))
        self.assertEqual(calls, [])
        self.assertEqual(self.delivery(item).skip_reason, "preference_off")

    def test_an_unsnoozed_item_is_unaffected(self):
        item = self.item()
        _, calls = self.work()
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.delivery(item).status, "delivered")
