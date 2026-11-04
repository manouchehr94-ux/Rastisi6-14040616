"""Notification Engine (Inbox): publish → policy → recipients → inbox → deliveries; tenant isolation, permission, rollback, dedupe, retry, access revocation.
No external service is ever contacted (socket guard); Web Push goes through an injected fake transport."""

import base64
import socket
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase, _user_with_role
from apps.notifications import registry as R
from apps.notifications.models import InboxItem, NotificationDelivery, NotificationEvent, NotificationPreference, WebPushSubscription
from apps.notifications.services import channel_delivery as cd
from apps.notifications.services import inbox_engine as eng
from apps.notifications.services import inbox_service as inbox
from apps.notifications.services import scope as S
from apps.notifications.services import webpush
from apps.stores.models import Store, StoreMembership

User = get_user_model()
VALID_SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123", "keys": {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}}


class _Base(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        guard = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection attempted"))
        guard.start()
        self.addCleanup(guard.stop)
        self.other = Store.objects.create(name="Other", slug="nt-other", status=Store.Status.ACTIVE)
        self.other_owner = _user_with_role(self.other, "nt-other-owner", StoreMembership.Role.OWNER)
        self.platform = User.objects.create_user(username="nt-platform", password="x", is_staff=True, is_superuser=True)

    def pub(self, key="order.created", store=None, **kw):
        kw.setdefault("title", "سفارش DM-1")
        kw.setdefault("link_kwargs", {"code": self.order.code} if key in ("order.created", "order.canceled") else {})
        return eng.publish(key, store=store if store is not None else self.store, **kw)

    def users_with_item(self, event):
        return set(InboxItem.objects.filter(event=event).values_list("user__username", flat=True))


class RecipientAndIsolationTests(_Base):
    def test_only_members_with_the_types_permission_receive_it(self):
        ev = self.pub("order.created")
        got = self.users_with_item(ev)
        self.assertEqual(got, {"perm-owner", "perm-admin", "perm-order", "perm-analyst"})          # ORDER_VIEW holders
        self.assertNotIn("perm-catalog", got)
        self.assertNotIn("perm-content", got)

    def test_another_stores_users_never_receive_or_see_it(self):
        ev = self.pub("order.created")
        self.assertNotIn("nt-other-owner", self.users_with_item(ev))
        self.assertEqual(inbox.visible(self.other_owner, self.other).count(), 0)
        self.assertEqual(inbox.visible(self.other_owner, self.store).count(), 0)                  # not a member of this store at all
        item = InboxItem.objects.filter(event=ev, user=self.owner).first()
        self.assertIsNone(inbox.get_item(self.other_owner, self.other, item.public_id))
        self.assertIsNone(inbox.get_item(self.other_owner, self.store, item.public_id))

    def test_an_item_is_invisible_to_a_different_user_even_in_the_same_store(self):
        ev = self.pub("order.created")
        mine = InboxItem.objects.get(event=ev, user=self.owner)
        self.assertIsNone(inbox.get_item(self.administrator, self.store, mine.public_id))

    def test_platform_events_go_only_to_platform_staff(self):
        ev = eng.publish("platform.store_created", title="فروشگاه تازه")
        self.assertEqual(self.users_with_item(ev), {"nt-platform"})
        self.assertEqual(inbox.visible(self.owner, self.store).count(), 0)
        self.assertEqual(inbox.visible(self.owner, None).count(), 0)                              # a store owner is not platform staff
        self.assertEqual(inbox.visible(self.platform, None).count(), 1)

    def test_scope_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            eng.publish("order.created", title="x")                                              # store type without a store
        with self.assertRaises(ValueError):
            eng.publish("platform.store_created", store=self.store, title="x")
        with self.assertRaises(KeyError):
            eng.publish("made.up.event", store=self.store)

    def test_revoking_access_cuts_visibility_at_once(self):
        self.pub("order.created")
        self.assertEqual(inbox.unread_count(self.order_manager, self.store), 1)
        m = StoreMembership.objects.get(user=self.order_manager, store=self.store)
        m.status = StoreMembership.MembershipStatus.REVOKED
        m.revoked_at = timezone.now()
        m.save()
        self.assertEqual(inbox.unread_count(self.order_manager, self.store), 0)
        self.assertEqual(inbox.visible(self.order_manager, self.store).count(), 0)

    def test_a_role_change_removes_types_the_new_role_may_not_see(self):
        self.pub("order.created")
        self.assertEqual(inbox.unread_count(self.order_manager, self.store), 1)
        m = StoreMembership.objects.get(user=self.order_manager, store=self.store)
        m.role = StoreMembership.Role.CONTENT_EDITOR
        m.save()
        self.assertEqual(inbox.unread_count(self.order_manager, self.store), 0)

    def test_event_text_never_carries_secrets_or_raw_markup_issues(self):
        ev = self.pub("order.created", title="x\x00y", details="token sk_live_ABCDEF1234567890 phone 09123456789 mail a@b.com " + "A" * 40)
        self.assertNotIn("\x00", ev.title)
        for secret in ("sk_live_ABCDEF1234567890", "09123456789", "a@b.com", "A" * 40):
            self.assertNotIn(secret, ev.details)


class DedupeRollbackGroupingTests(_Base):
    def test_the_same_dedupe_key_creates_one_event_and_one_inbox_row_per_user(self):
        first = self.pub("order.created", dedupe_key="order:1")
        second = self.pub("order.created", dedupe_key="order:1")
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(NotificationEvent.objects.filter(dedupe_key="order:1").count(), 1)
        self.assertEqual(InboxItem.objects.filter(event=first, user=self.owner).count(), 1)

    def test_dedupe_is_per_scope_not_global(self):
        a = self.pub("order.created", dedupe_key="order:7")
        b = eng.publish("order.created", store=self.other, title="x", dedupe_key="order:7")
        self.assertTrue(a and b)

    def test_groupable_repeats_bump_a_counter_instead_of_creating_rows(self):
        first = self.pub("payment.failed", group_key="pay:1", summary="تلاش ۱")
        InboxItem.objects.filter(event=first).update(read_at=timezone.now())
        again = self.pub("payment.failed", group_key="pay:1", summary="تلاش ۲")
        self.assertEqual(again.pk, first.pk)
        first.refresh_from_db()
        self.assertEqual(first.occurrence_count, 2)
        self.assertEqual(NotificationEvent.objects.filter(group_key="pay:1").count(), 1)
        self.assertFalse(InboxItem.objects.filter(event=first, read_at__isnull=False).exists())    # resurfaces as unread

    def test_a_flood_of_one_type_is_capped(self):
        with mock.patch.object(eng, "MAX_EVENTS_PER_HOUR", 3):
            made = [self.pub("order.created", dedupe_key=f"o:{i}") for i in range(6)]
        self.assertEqual(len([m for m in made if m]), 3)

    def test_safe_publish_never_raises_and_never_breaks_the_outer_transaction(self):
        with transaction.atomic():
            self.assertIsNone(eng.safe_publish("no.such.type", store=self.store))
            self.assertIsNone(eng.safe_publish("order.created"))                                  # store missing
            self.assertTrue(self.store.pk)                                                       # outer transaction still usable


class RollbackTests(TransactionTestCase):
    def test_nothing_exists_after_a_rollback(self):
        store = Store.objects.create(name="RB", slug="rb-store", status=Store.Status.ACTIVE)
        owner = _user_with_role(store, "rb-owner", StoreMembership.Role.OWNER)
        try:
            with transaction.atomic():
                eng.publish("system.test", store=store, title="x")
                raise RuntimeError("business failure")
        except RuntimeError:
            pass
        self.assertFalse(NotificationEvent.objects.exists())
        self.assertFalse(InboxItem.objects.filter(user=owner).exists())
        self.assertFalse(NotificationDelivery.objects.exists())

    def test_committed_work_keeps_the_notification(self):
        store = Store.objects.create(name="CM", slug="cm-store", status=Store.Status.ACTIVE)
        _user_with_role(store, "cm-owner", StoreMembership.Role.OWNER)
        with transaction.atomic():
            eng.publish("system.test", store=store, title="x")
        self.assertEqual(NotificationEvent.objects.count(), 1)


class PolicyTests(_Base):
    def pref(self, user, **kw):
        return NotificationPreference.objects.update_or_create(user=user, scope_key=S.key_for(self.store), defaults=kw)[0]

    def test_defaults_toast_only_for_important_or_urgent_and_never_for_low(self):
        d = eng.decide(R.get_type("order.canceled"), R.IMPORTANT, NotificationPreference())
        self.assertTrue(d["inbox"] and d["toast"])
        d = eng.decide(R.get_type("payment.failed"), R.NORMAL, NotificationPreference())          # normal, not urgent → inbox only
        self.assertTrue(d["inbox"])
        self.assertFalse(d["toast"])
        d = eng.decide(R.get_type("order.created"), R.NORMAL, NotificationPreference())           # urgent type → toast
        self.assertTrue(d["toast"])
        d = eng.decide(R.get_type("order.created"), R.INFO, NotificationPreference())             # muted low + urgent: still shown (urgent)
        self.assertTrue(d["toast"])

    def test_disabling_a_category_stops_inbox_rows_but_never_for_security_or_critical(self):
        self.pref(self.owner, disabled_categories=["orders", "security", "finance"])
        self.pref(self.administrator, disabled_categories=["orders"])
        ev = self.pub("order.created")
        self.assertNotIn("perm-owner", self.users_with_item(ev))
        self.assertIn("perm-admin" if False else "perm-order", self.users_with_item(ev))
        sec = eng.publish("staff.role_changed", store=self.store, title="نقش تغییر کرد")
        self.assertIn("perm-owner", self.users_with_item(sec))                                    # security is never switchable off
        crit = eng.publish("payment.suspicious", store=self.store, title="مشکوک")
        self.assertIn("perm-owner", self.users_with_item(crit))                                   # critical neither

    def test_toast_off_still_records_in_the_inbox(self):
        self.pref(self.owner, toast_enabled=False)
        ev = self.pub("order.canceled")
        item = InboxItem.objects.get(event=ev, user=self.owner)
        self.assertFalse(item.popup)
        self.assertEqual(inbox.unread_count(self.owner, self.store), 1)

    def test_preferences_are_per_user_and_per_scope(self):
        self.pref(self.owner, disabled_categories=["orders"])
        eng.publish("order.created", store=self.other, title="x")
        self.assertEqual(NotificationPreference.objects.filter(user=self.owner).count(), 1)
        self.assertEqual(S.key_for(self.store), f"store:{self.store.pk}")
        self.assertNotEqual(S.key_for(self.store), S.key_for(self.other))
        self.assertEqual(S.key_for(None), "platform")


class InboxServiceTests(_Base):
    def make(self, n=3, key="order.canceled"):
        return [self.pub(key, title=f"اعلان {i}", dedupe_key=f"k{i}") for i in range(n)]

    def test_read_unread_archive_pin_snooze_persist_in_the_database(self):
        self.make(2)
        item = InboxItem.objects.filter(user=self.owner).first()
        self.assertEqual(inbox.unread_count(self.owner, self.store), 2)
        inbox.mark(item, "read")
        self.assertEqual(inbox.unread_count(self.owner, self.store), 1)
        InboxItem.objects.get(pk=item.pk).read_at                                                   # persisted (fresh row)
        self.assertIsNotNone(InboxItem.objects.get(pk=item.pk).read_at)
        inbox.mark(item, "unread")
        self.assertEqual(inbox.unread_count(self.owner, self.store), 2)
        inbox.mark(item, "archive")
        self.assertEqual(inbox.unread_count(self.owner, self.store), 1)
        self.assertEqual(inbox.filtered(self.owner, self.store, {"view": "archived"}).count(), 1)
        self.assertEqual(inbox.filtered(self.owner, self.store, {}).count(), 1)
        inbox.mark(item, "unarchive")
        inbox.mark(item, "unread")
        inbox.mark(item, "snooze", snooze="1h")
        self.assertEqual(inbox.unread_count(self.owner, self.store), 1)                           # snoozed → hidden…
        self.assertEqual(inbox.filtered(self.owner, self.store, {}).count(), 1)
        later = timezone.now() + timedelta(hours=2)
        self.assertEqual(inbox.unread_count(self.owner, self.store, now=later), 2)                # …and back later
        self.assertEqual(inbox.filtered(self.owner, self.store, {}, now=later).count(), 2)
        self.assertFalse(inbox.mark(item, "snooze", snooze="nonsense"))
        self.assertFalse(inbox.mark(item, "explode"))

    def test_snooze_lifecycle_preserves_read_state_updates_counter_and_prevents_duplicate_toast(self):
        ev_unread = self.pub("order.canceled", title="اعلان خوانده‌نشده", dedupe_key="snz-u")
        ev_read = self.pub("order.canceled", title="اعلان خوانده‌شده", dedupe_key="snz-r")
        item_u = InboxItem.objects.get(event=ev_unread, user=self.owner)
        item_r = InboxItem.objects.get(event=ev_read, user=self.owner)
        t0 = item_u.created_at
        inbox.mark(item_r, "read", now=t0)

        # Initially at t0: unread item is eligible for toast
        initial_summary = inbox.summary(self.owner, self.store, since_ms=0, now=t0)
        self.assertEqual(initial_summary["unread"], 1)
        self.assertEqual([t["id"] for t in initial_summary["toasts"]], [str(item_u.public_id)])

        # At t0 + 1 min: snooze both items for 1 hour
        t1 = t0 + timedelta(minutes=1)
        self.assertTrue(inbox.mark(item_u, "snooze", now=t1, snooze="1h"))
        self.assertTrue(inbox.mark(item_r, "snooze", now=t1, snooze="1h"))
        self.assertFalse(InboxItem.objects.get(pk=item_u.pk).popup)
        self.assertEqual(inbox.unread_count(self.owner, self.store, now=t1), 0)
        self.assertEqual(inbox.filtered(self.owner, self.store, {}, now=t1).count(), 0)
        self.assertEqual(inbox.filtered(self.owner, self.store, {"view": "snoozed"}, now=t1).count(), 2)
        self.assertTrue(inbox.serialize(item_u, now=t1)["snoozed"])
        self.assertEqual(inbox.unread_count(self.administrator, self.store, now=t1), 2)

        # At t0 + 2 min (< 5 min window): unsnooze item_u and poll with since_ms=0 -> NO duplicate toast
        t2 = t0 + timedelta(minutes=2)
        self.assertTrue(inbox.mark(item_u, "unsnooze", now=t2))
        sum_unsnoozed = inbox.summary(self.owner, self.store, since_ms=0, now=t2)
        self.assertEqual(sum_unsnoozed["unread"], 1)
        self.assertEqual([i["id"] for i in sum_unsnoozed["items"]], [str(item_u.public_id)])
        self.assertEqual(sum_unsnoozed["toasts"], [])

        # Re-snooze item_u at t2 for 1h; mark_all_read while snoozed must not touch snoozed items
        self.assertTrue(inbox.mark(item_u, "snooze", now=t2, snooze="1h"))
        inbox.mark_all_read(self.owner, self.store, now=t2)
        item_u.refresh_from_db()
        self.assertIsNone(item_u.read_at)

        # After snooze expires (t2 + 61 min): automatically returns to active inbox; read state preserved
        t_after = t2 + timedelta(minutes=61)
        self.assertEqual(inbox.filtered(self.owner, self.store, {"view": "snoozed"}, now=t_after).count(), 0)
        self.assertEqual(inbox.filtered(self.owner, self.store, {}, now=t_after).count(), 2)
        self.assertEqual(inbox.unread_count(self.owner, self.store, now=t_after), 1)
        self.assertFalse(inbox.serialize(item_u, now=t_after)["snoozed"])

    def test_groupable_repeat_respects_active_snooze_until_it_expires(self):
        now = timezone.now()
        ev = self.pub("payment.failed", group_key="pay:snz", summary="تلاش ۱")
        item = InboxItem.objects.get(event=ev, user=self.owner)
        inbox.mark(item, "read", now=now)
        inbox.mark(item, "snooze", now=now, snooze="1h")
        self.pub("payment.failed", group_key="pay:snz", summary="تلاش ۲")
        item.refresh_from_db()
        self.assertIsNone(item.read_at)
        self.assertEqual(inbox.unread_count(self.owner, self.store, now=now + timedelta(minutes=10)), 0)
        self.assertEqual(inbox.unread_count(self.owner, self.store, now=now + timedelta(hours=2)), 1)

    def test_mark_all_read_only_touches_the_callers_visible_items(self):
        self.make(3)
        other_item_count = InboxItem.objects.filter(user=self.administrator, read_at__isnull=True).count()
        self.assertEqual(inbox.mark_all_read(self.owner, self.store), 3)
        self.assertEqual(inbox.unread_count(self.owner, self.store), 0)
        self.assertEqual(InboxItem.objects.filter(user=self.administrator, read_at__isnull=True).count(), other_item_count)

    def test_filters_search_sort_and_pagination_inputs(self):
        self.pub("order.canceled", title="لغو سفارش الف", dedupe_key="a")
        self.pub("refund.completed", title="بازپرداخت ب", dedupe_key="b")
        self.pub("order.created", title="سفارش جدید ج", dedupe_key="c")
        f = lambda **p: [i.event.title for i in inbox.filtered(self.owner, self.store, p)]
        self.assertEqual(len(f()), 3)
        self.assertEqual(f(category="finance"), ["بازپرداخت ب"])
        self.assertEqual(f(severity="3"), ["لغو سفارش الف"])
        self.assertEqual(set(f(severity="2", sev_mode="min")), {"لغو سفارش الف", "بازپرداخت ب", "سفارش جدید ج"})
        self.assertEqual(f(q="بازپرداخت"), ["بازپرداخت ب"])
        self.assertEqual(f(sort="oldest")[0], "لغو سفارش الف")
        self.assertEqual(f()[0], "سفارش جدید ج")
        self.assertEqual(f(**{"range": "1"}).__len__(), 3)
        InboxItem.objects.filter(user=self.owner, event__title="بازپرداخت ب").update(read_at=timezone.now())
        self.assertEqual(len(f(view="unread")), 2)
        self.assertEqual(f(category="nonsense").__len__(), 3)                                      # unknown filter values are ignored, never an error

    def test_search_cannot_reach_other_users_or_stores_content(self):
        eng.publish("order.created", store=self.other, title="راز فروشگاه دیگر")
        self.assertEqual(inbox.filtered(self.owner, self.store, {"q": "راز"}).count(), 0)

    def test_summary_returns_counter_latest_and_fresh_toasts_once(self):
        ev = self.pub("order.canceled", title="لغو مهم", dedupe_key="s1")
        first = inbox.summary(self.owner, self.store)
        self.assertEqual(first["unread"], 1)
        self.assertEqual([t["title"] for t in first["toasts"]], ["لغو مهم"])
        again = inbox.summary(self.owner, self.store, since_ms=first["now_ms"])
        self.assertEqual(again["toasts"], [])                                                      # nothing new since the cursor → no repeat
        self.assertEqual(again["unread"], 1)
        inbox.mark(InboxItem.objects.get(event=ev, user=self.owner), "read")
        self.assertEqual(inbox.summary(self.owner, self.store)["unread"], 0)

    def test_pinned_items_sort_first_in_the_dropdown(self):
        self.make(3)
        old = InboxItem.objects.filter(user=self.owner).order_by("id").first()
        inbox.mark(old, "pin")
        self.assertEqual(inbox.summary(self.owner, self.store)["items"][0]["id"], str(old.public_id))


@override_settings(RASTISI_NOTIF_WEBPUSH_ENABLED=True, RASTISI_VAPID_SUBJECT="mailto:ops@example.test")
class WebPushDeliveryTests(_Base):
    def setUp(self):
        super().setUp()
        keys = webpush.generate_keypair()
        patcher = override_settings(RASTISI_VAPID_PRIVATE_KEY=keys["private"])
        patcher.enable()
        self.addCleanup(patcher.disable)
        self.keys = keys
        self.key = S.key_for(self.store)
        NotificationPreference.objects.update_or_create(user=self.owner, scope_key=self.key, defaults={"browser_enabled": True})
        self.sub = webpush.register(self.owner, self.key, VALID_SUB, device_label="Chrome")

    def deliveries(self):
        return NotificationDelivery.objects.filter(channel="web_push")

    def run_worker(self, status=201, now=None):
        calls = []
        def transport(endpoint, headers):
            calls.append((endpoint, headers))
            return webpush.PushResult(status, "" if status else "ConnectionError")
        return cd.deliver_pending(now=now, transports={"web_push": transport}), calls

    def test_a_push_row_is_created_only_for_users_with_browser_on_and_an_active_subscription(self):
        self.pub("order.canceled", dedupe_key="p1")
        self.assertEqual(self.deliveries().count(), 1)
        self.assertEqual(self.deliveries().get().inbox_item.user, self.owner)

    def test_delivery_sends_an_empty_vapid_signed_request_and_marks_it_delivered(self):
        self.pub("order.canceled", dedupe_key="p2", title="لغو سفارش با نام مشتری محرمانه", summary="مبلغ ۵۰٬۰۰۰٬۰۰۰")
        result, calls = self.run_worker(201)
        self.assertEqual(result["delivered"], 1)
        endpoint, headers = calls[0]
        self.assertEqual(endpoint, VALID_SUB["endpoint"])
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        self.assertEqual(headers["Content-Length"], "0")                                           # no payload: nothing sensitive leaves the server
        self.assertEqual(self.deliveries().get().status, "delivered")

    def test_vapid_jwt_is_a_valid_es256_signature_for_the_public_key(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        header = webpush.vapid_headers(VALID_SUB["endpoint"])["Authorization"]
        token = header.split("t=")[1].split(",")[0]
        signing_input, sig = token.rsplit(".", 1)
        raw = webpush._b64u_decode(sig)
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush._b64u_decode(self.keys["public"]))
        pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")), signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        import json
        claims = json.loads(webpush._b64u_decode(signing_input.split(".")[1]))
        self.assertEqual(claims["aud"], "https://fcm.googleapis.com")
        self.assertEqual(claims["sub"], "mailto:ops@example.test")

    def test_transient_errors_retry_with_backoff_then_die(self):
        self.pub("order.canceled", dedupe_key="p3")
        now = timezone.now()
        for attempt in range(1, 6):
            result, _ = self.run_worker(503, now=now)
            d = self.deliveries().get()
            if attempt < 5:
                self.assertEqual(d.status, "failed")
                self.assertGreater(d.next_attempt_at, now)
                self.assertEqual(self.run_worker(503, now=now)[0]["processed"], 0)                 # not due yet → no hammering
                now = d.next_attempt_at + timedelta(seconds=1)
        d = self.deliveries().get()
        self.assertEqual((d.status, d.attempts), ("dead", 5))

    def test_gone_subscription_is_revoked_and_never_retried(self):
        self.pub("order.canceled", dedupe_key="p4")
        self.run_worker(410)
        d = self.deliveries().get()
        self.assertEqual((d.status, d.skip_reason), ("skipped", "subscription_gone"))
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.revoked_at)
        self.pub("order.canceled", dedupe_key="p5")
        self.assertEqual(self.deliveries().count(), 1)                                             # no new rows for a revoked device

    def test_a_worker_failure_in_the_transport_is_contained(self):
        self.pub("order.canceled", dedupe_key="p6")
        def boom(endpoint, headers):
            raise RuntimeError("boom 09123456789")
        result = cd.deliver_pending(transports={"web_push": boom})
        self.assertEqual(result["failed"], 1)
        d = self.deliveries().get()
        self.assertEqual(d.status, "failed")
        self.assertNotIn("09123456789", d.last_error)

    def test_revoked_access_before_delivery_skips_it(self):
        self.pub("order.canceled", dedupe_key="p7")
        m = StoreMembership.objects.get(user=self.owner, store=self.store)
        StoreMembership.objects.filter(pk=m.pk).update(status=StoreMembership.MembershipStatus.REVOKED, revoked_at=timezone.now())
        result, calls = self.run_worker(201)
        self.assertEqual(calls, [])
        self.assertEqual(self.deliveries().get().skip_reason, "access_revoked")

    def test_an_already_read_item_is_not_pushed(self):
        ev = self.pub("order.canceled", dedupe_key="p8")
        inbox.mark(InboxItem.objects.get(event=ev, user=self.owner), "read")
        result, calls = self.run_worker(201)
        self.assertEqual(calls, [])
        self.assertEqual(self.deliveries().get().skip_reason, "already_seen")

    def test_turning_the_preference_off_before_delivery_skips_it(self):
        self.pub("order.canceled", dedupe_key="p9")
        NotificationPreference.objects.filter(user=self.owner).update(browser_enabled=False)
        _, calls = self.run_worker(201)
        self.assertEqual(calls, [])

    def test_per_user_push_rate_limit(self):
        for i in range(cd.MAX_PUSH_PER_10_MIN + 2):
            self.pub("order.canceled", dedupe_key=f"r{i}")
        result, calls = self.run_worker(201)
        self.assertEqual(len(calls), cd.MAX_PUSH_PER_10_MIN)
        self.assertEqual(NotificationDelivery.objects.filter(skip_reason="rate_limited").count(), 2)

    @override_settings(RASTISI_NOTIF_WEBPUSH_ENABLED=False)
    def test_flag_off_creates_no_delivery_rows_and_calls_no_transport(self):
        self.pub("order.canceled", dedupe_key="f1")
        self.assertEqual(NotificationDelivery.objects.count(), 0)
        transport = mock.Mock()
        cd.deliver_pending(transports={"web_push": transport})
        transport.assert_not_called()

    @override_settings(RASTISI_VAPID_PRIVATE_KEY="")
    def test_without_vapid_keys_nothing_is_queued(self):
        self.pub("order.canceled", dedupe_key="f2")
        self.assertEqual(NotificationDelivery.objects.count(), 0)
        self.assertEqual(webpush.public_key_b64u(), "")


class SubscriptionTests(_Base):
    def test_validation_rejects_ssrf_and_malformed_subscriptions(self):
        bad = [
            {"endpoint": "http://fcm.googleapis.com/x", "keys": VALID_SUB["keys"]},
            {"endpoint": "https://169.254.169.254/latest", "keys": VALID_SUB["keys"]},
            {"endpoint": "https://localhost/x", "keys": VALID_SUB["keys"]},
            {"endpoint": "https://evil.example.com/fcm.googleapis.com", "keys": VALID_SUB["keys"]},
            {"endpoint": "https://fcm.googleapis.com.evil.com/x", "keys": VALID_SUB["keys"]},
            {"endpoint": VALID_SUB["endpoint"], "keys": {}},
            {"endpoint": VALID_SUB["endpoint"], "keys": {"p256dh": "***", "auth": "x"}},
            {},
        ]
        for payload in bad:
            with self.assertRaises(webpush.SubscriptionError, msg=payload):
                webpush.validate_subscription(payload)

    def test_endpoint_and_keys_are_encrypted_at_rest_and_never_stored_plain(self):
        sub = webpush.register(self.owner, S.key_for(self.store), VALID_SUB)
        raw = WebPushSubscription.objects.get(pk=sub.pk)
        for secret in (VALID_SUB["endpoint"], VALID_SUB["keys"]["auth"], VALID_SUB["keys"]["p256dh"], "abc123"):
            self.assertNotIn(secret, raw.secret_blob)
            self.assertNotIn(secret, raw.endpoint_hash)
        self.assertEqual(webpush.decrypt(raw)["endpoint"], VALID_SUB["endpoint"])

    def test_register_is_idempotent_unregister_revokes_and_can_be_reregistered(self):
        key = S.key_for(self.store)
        webpush.register(self.owner, key, VALID_SUB)
        webpush.register(self.owner, key, VALID_SUB)
        self.assertEqual(WebPushSubscription.objects.count(), 1)
        self.assertEqual(webpush.unregister(self.owner, VALID_SUB["endpoint"]), 1)
        self.assertEqual(WebPushSubscription.objects.filter(revoked_at__isnull=True).count(), 0)
        webpush.register(self.owner, key, VALID_SUB)
        self.assertEqual(WebPushSubscription.objects.filter(revoked_at__isnull=True).count(), 1)

    def test_a_user_cannot_unregister_someone_elses_device(self):
        webpush.register(self.owner, S.key_for(self.store), VALID_SUB)
        self.assertEqual(webpush.unregister(self.administrator, VALID_SUB["endpoint"]), 0)

    def test_generated_keys_are_well_formed_and_not_the_repo(self):
        keys = webpush.generate_keypair()
        self.assertEqual(len(base64.urlsafe_b64decode(keys["private"] + "==")), 32)
        self.assertEqual(len(base64.urlsafe_b64decode(keys["public"] + "==")), 65)


class OtherChannelsTests(_Base):
    @override_settings(RASTISI_NOTIF_EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_channel_contract_with_the_locmem_backend_only(self):
        self.owner.email = "owner@example.test"
        self.owner.save()
        NotificationPreference.objects.update_or_create(user=self.owner, scope_key=S.key_for(self.store), defaults={"email_enabled": True})
        self.pub("order.canceled", dedupe_key="e1", title="لغو سفارش", summary="خلاصه")
        self.assertEqual(NotificationDelivery.objects.filter(channel="email").count(), 1)
        result = cd.deliver_pending()
        self.assertEqual(result["delivered"], 1)
        self.assertEqual([m.to for m in mail.outbox], [["owner@example.test"]])
        self.assertEqual(cd.deliver_pending()["processed"], 0)                                     # never sent twice
        self.assertEqual(NotificationDelivery.objects.filter(channel="email", status="delivered").count(), 1)

    def test_email_is_off_by_default_and_creates_nothing(self):
        self.owner.email = "owner@example.test"
        self.owner.save()
        NotificationPreference.objects.update_or_create(user=self.owner, scope_key=S.key_for(self.store), defaults={"email_enabled": True})
        self.pub("order.canceled", dedupe_key="e2")
        self.assertEqual(NotificationDelivery.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    @override_settings(RASTISI_NOTIF_MOBILE_ENABLED=True)
    def test_mobile_channel_has_no_provider_and_never_sends(self):
        NotificationPreference.objects.update_or_create(user=self.owner, scope_key=S.key_for(self.store), defaults={"mobile_enabled": True})
        self.pub("order.canceled", dedupe_key="m1")
        result = cd.deliver_pending()
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(NotificationDelivery.objects.get().skip_reason, "no_provider_configured")

    def test_project_defaults_for_all_external_channels_are_off(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[3] / "shop_core" / "settings.py").read_text(encoding="utf-8")
        for flag in ("RASTISI_NOTIF_WEBPUSH_ENABLED", "RASTISI_NOTIF_EMAIL_ENABLED", "RASTISI_NOTIF_MOBILE_ENABLED"):
            self.assertIn(f'{flag} = env_bool("{flag}", default=False)', source)
        self.assertIn('RASTISI_VAPID_PRIVATE_KEY = env_str("RASTISI_VAPID_PRIVATE_KEY", "")', source)


class PruneTests(_Base):
    def test_expired_events_are_deleted_pinned_ones_survive(self):
        old = self.pub("system.test", title="old", dedupe_key="x1")
        keep = self.pub("system.test", title="keep", dedupe_key="x2")
        NotificationEvent.objects.filter(pk__in=[old.pk, keep.pk]).update(expires_at=timezone.now() - timedelta(days=1))
        InboxItem.objects.filter(event=keep).update(pinned=True)
        self.assertEqual(eng.prune()["deleted_events"], 1)
        self.assertTrue(NotificationEvent.objects.filter(pk=keep.pk).exists())
        self.assertFalse(NotificationEvent.objects.filter(pk=old.pk).exists())

    def test_registry_is_consistent(self):
        from django.urls import reverse

        for key, t in R.EVENT_TYPES.items():
            self.assertIn(t.category, R.CATEGORIES, key)
            self.assertIn(t.severity, (1, 2, 3, 4), key)
            self.assertTrue(t.source, key)
            ns = "portal_platform_admin" if t.scope == R.PLATFORM else "dashboard"
            if t.link_name:
                try:
                    reverse(f"{ns}:{t.link_name}", urlconf="shop_core.urls_platform_admin" if t.scope == R.PLATFORM else None)
                except Exception as exc:                                                                 # needs kwargs ⇒ accept NoReverseMatch with args, fail on unknown name
                    self.assertIn("arguments", str(exc), key)
        self.assertFalse(set(R.EVENT_TYPES) & set(R.PLANNED))
