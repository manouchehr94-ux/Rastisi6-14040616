"""Real triggers → inbox: every event type that has a real source in the code base is wired through the same publish() path.
Uses the real services wherever a fixture is cheap (orders, stock, membership, domain, subscription, automation, store status); a few model-heavy triggers
(return/refund/review/late payment/card transfer/import) are exercised through the real ``business_events`` / ``admin_events`` functions with minimal stand-ins."""

import socket
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Product
from apps.catalog.services import inventory_service
from apps.core import automation
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase, _user_with_role
from apps.notifications import registry as R
from apps.notifications.models import InboxItem, NotificationEvent
from apps.notifications.services import admin_events, business_events
from apps.notifications.services import inbox_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services import domain_verification_service, membership_service, store_status_service
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service

User = get_user_model()


class _W(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        guard = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection attempted"))
        guard.start()
        self.addCleanup(guard.stop)
        self.platform = User.objects.create_user(username="wr-platform", password="x", is_staff=True, is_superuser=True)

    def events(self, key):
        return NotificationEvent.objects.filter(type_key=key)

    def who(self, key):
        return set(InboxItem.objects.filter(event__type_key=key).values_list("user__username", flat=True))


class OrderSideTests(_W):
    def test_a_new_order_notifies_exactly_the_order_viewers_once(self):
        business_events.order_created(self.order)
        business_events.order_created(self.order)                                                   # a re-run (retry) never duplicates
        ev = self.events("order.created").get()
        self.assertEqual(ev.link_kwargs, {"code": self.order.code})
        self.assertEqual(self.who("order.created"), {"perm-owner", "perm-admin", "perm-order", "perm-analyst"})
        self.assertNotIn(self.order.customer.full_name, ev.title + ev.summary + ev.details)           # no customer PII in the text
        self.assertNotIn(self.order.customer.phone, ev.title + ev.summary + ev.details)

    def test_order_creation_inside_a_failed_transaction_leaves_no_notification(self):
        try:
            with transaction.atomic():
                business_events.order_created(self.order)
                raise RuntimeError("checkout failed afterwards")
        except RuntimeError:
            pass
        self.assertFalse(self.events("order.created").exists())
        self.assertFalse(InboxItem.objects.exists())

    def test_cancel_and_failed_payment(self):
        business_events.order_status_changed(self.order, "canceled")
        business_events.order_status_changed(self.order, "shipped")                                  # not a notable admin event ⇒ nothing
        self.assertEqual(self.events("order.canceled").count(), 1)
        self.assertEqual(NotificationEvent.objects.filter(type_key__startswith="order.").exclude(type_key="order.canceled").count(), 0)
        business_events.payment_result(self.order, success=False)
        business_events.payment_result(self.order, success=False)
        business_events.payment_result(self.order, success=True)                                     # success is covered by order.created
        failed = self.events("payment.failed").get()
        self.assertEqual(failed.occurrence_count, 2)                                                  # grouped, not two rows

    def test_return_refund_review_late_payment_and_card_transfer_map_to_their_types(self):
        ret = SimpleNamespace(pk=5, order=self.order, store=self.store, customer=self.order.customer, return_number="RT-5")
        business_events.return_event(ret, "requested")
        business_events.return_event(ret, "approved")                                                # approval is the admin's own action ⇒ no admin notification
        self.assertEqual(self.events("return.requested").count(), 1)
        self.assertEqual(self.who("return.requested"), {"perm-owner", "perm-admin", "perm-order", "perm-analyst"})
        refund = SimpleNamespace(pk=3, order=self.order, store=self.store, approved_amount=Decimal("50000"))
        admin_events.refund_completed(refund)
        self.assertEqual(self.events("refund.completed").count(), 1)
        review = SimpleNamespace(pk=9, product=self.product)
        for _ in range(3):
            admin_events.review_pending(review, self.store)
        self.assertEqual(self.events("review.pending").get().occurrence_count, 3)
        self.assertEqual(self.who("review.pending"), {"perm-owner", "perm-admin", "perm-content"})       # CONTENT_MANAGE holders only
        rec = SimpleNamespace(pk=11, store=self.store, order=self.order, get_kind_display=lambda: "مغایرت مبلغ")
        admin_events.suspicious_payment(rec)
        admin_events.suspicious_payment(rec)
        ev = self.events("payment.suspicious").get()
        self.assertEqual(ev.severity, R.CRITICAL)
        self.assertEqual(self.who("payment.suspicious"), {"perm-owner", "perm-admin", "perm-order"})     # REFUND_MANAGE holders
        sub = SimpleNamespace(pk=2, store=self.store, order=self.order, amount=Decimal("1000000"))
        admin_events.card_transfer_submitted(sub)
        self.assertEqual(self.who("payment.card_transfer_submitted"), {"perm-owner", "perm-admin", "perm-order"})

    def test_import_failure_notifies_import_viewers(self):
        job = SimpleNamespace(pk=4, store=self.store, get_import_type_display=lambda: "کالاها")
        admin_events.import_failed(job)
        self.assertEqual(self.events("import.failed").count(), 1)
        self.assertIn("perm-owner", self.who("import.failed"))
        self.assertNotIn("perm-content", self.who("import.failed"))


class StockTests(_W):
    def decrement(self, qty):
        p = Product.objects.get(pk=self.product.pk)
        inventory_service.decrement_stock_for_order_item(store=self.store, product=p, variant=None, quantity=qty, order=self.order)

    def test_only_the_crossing_of_the_threshold_and_the_zero_point_notify(self):
        Product.objects.filter(pk=self.product.pk).update(stock=14)                                   # default threshold = dashboard LOW_STOCK_THRESHOLD (10)
        self.decrement(2)                                                                            # 14 → 12: above threshold ⇒ silent
        self.assertFalse(NotificationEvent.objects.filter(type_key__startswith="stock.").exists())
        self.decrement(3)                                                                            # 12 → 9: crossed
        self.assertEqual(self.events("stock.low").count(), 1)
        self.decrement(1)                                                                            # 9 → 8: already below ⇒ silent
        self.assertEqual(self.events("stock.low").count(), 1)
        self.decrement(8)                                                                            # → 0
        self.assertEqual(self.events("stock.out").count(), 1)
        self.assertEqual(self.who("stock.low"), {"perm-owner", "perm-admin", "perm-catalog"})           # INVENTORY_MANAGE holders (from ROLE_PERMISSIONS)


class AccessAndAccountTests(_W):
    def test_role_change_and_revocation_notify_staff_managers(self):
        m = StoreMembership.objects.get(user=self.content_editor, store=self.store)
        membership_service.change_role(m, new_role=StoreMembership.Role.ANALYST, actor=self.owner)
        ev = self.events("staff.role_changed").get()
        self.assertEqual(self.who("staff.role_changed"), {"perm-owner"})                                 # STAFF_MANAGE is owner-only (ROLE_PERMISSIONS)
        self.assertEqual(ev.severity, R.IMPORTANT)
        membership_service.revoke_membership(StoreMembership.objects.get(user=self.analyst, store=self.store), actor=self.owner)
        self.assertEqual(self.events("staff.access_revoked").count(), 1)
        self.assertEqual(svc.unread_count(self.analyst, self.store), 0)                                # the revoked user sees nothing at all

    def test_security_events_cannot_be_turned_off_by_the_user(self):
        from apps.notifications.models import NotificationPreference

        NotificationPreference.objects.create(user=self.owner, scope_key=f"store:{self.store.pk}", disabled_categories=["security", "account"], toast_enabled=False)
        m = StoreMembership.objects.get(user=self.content_editor, store=self.store)
        membership_service.change_role(m, new_role=StoreMembership.Role.ANALYST, actor=self.administrator)
        self.assertIn("perm-owner", self.who("staff.role_changed"))

    def test_domain_verification_success_and_failure(self):
        domain = StoreDomain.objects.create(store=self.store, hostname="shop.example.ir", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                            verification_status=StoreDomain.VerificationStatus.PENDING, verification_token="tok123", verification_requested_at=timezone.now())
        with mock.patch.object(domain_verification_service, "_txt_records_match", return_value=False):
            self.assertFalse(domain_verification_service.check_dns_verification(domain=domain, actor=self.owner))
            domain_verification_service.check_dns_verification(domain=domain, actor=self.owner)
        failed = self.events("domain.verification_failed").get()
        self.assertEqual(failed.occurrence_count, 2)                                                    # repeated tries are grouped
        with mock.patch.object(domain_verification_service, "_txt_records_match", return_value=True):
            self.assertTrue(domain_verification_service.check_dns_verification(domain=domain, actor=self.owner))
        self.assertEqual(self.events("domain.verified").count(), 1)
        self.assertEqual(self.who("domain.verified"), {"perm-owner"})                                     # DOMAIN_MANAGE is owner-only

    def test_automation_failure_notifies_settings_managers_and_never_leaks_the_exception_text(self):
        def boom(dry):
            raise automation.PermanentError("secret token sk_live_ABCDEF1234567890 failed")

        result = automation.run("indexnow_sync", self.store, boom, enabled=True, require_public=False)
        self.assertEqual(result.status, automation.FAILED)
        ev = self.events("integration.sync_failed").get()
        self.assertNotIn("sk_live_ABCDEF1234567890", ev.summary + ev.details + str(ev.metadata))
        self.assertEqual(self.who("integration.sync_failed"), {"perm-owner", "perm-admin"})

    def test_a_successful_automation_makes_no_notification(self):
        automation.run("indexnow_sync", self.store, lambda dry: {"urls": 0}, enabled=True, require_public=False)
        self.assertFalse(self.events("integration.sync_failed").exists())


class SubscriptionAndPlatformTests(TestCase):
    def setUp(self):
        guard = mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection attempted"))
        guard.start()
        self.addCleanup(guard.stop)
        self.store = Store.objects.create(name="فروشگاه اشتراک", slug="wr-sub", admin_subdomain="wr-sub")
        self.owner = _user_with_role(self.store, "wr-sub-owner", StoreMembership.Role.OWNER)
        self.analyst = _user_with_role(self.store, "wr-sub-analyst", StoreMembership.Role.ANALYST)
        self.order_manager = _user_with_role(self.store, "wr-sub-om", StoreMembership.Role.ORDER_MANAGER)
        self.platform = User.objects.create_user(username="wr-sub-platform", password="x", is_staff=True, is_superuser=True)
        plan = Plan.objects.create(code="pro", name="Pro")
        self.version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED, trial_days=14, grace_period_days=7)

    def test_past_due_and_suspension_are_critical_and_reach_only_subscription_viewers(self):
        sub = subscription_service.create_subscription(self.store, self.version, actor=self.platform)
        sub = subscription_service.start_trial(sub, actor=self.platform)
        sub = subscription_service.activate_subscription(sub, actor=self.platform)
        sub = subscription_service.mark_past_due(sub, actor=self.platform)
        sub = subscription_service.suspend_subscription(sub, actor=self.platform)
        for key in ("subscription.past_due", "subscription.suspended"):
            ev = NotificationEvent.objects.get(type_key=key)
            self.assertEqual(ev.severity, R.CRITICAL)
            users = set(InboxItem.objects.filter(event=ev).values_list("user__username", flat=True))
            self.assertIn("wr-sub-owner", users)
            self.assertNotIn("wr-sub-om", users)                                                        # ORDER_MANAGER has no SUBSCRIPTION_VIEW
            self.assertNotIn("wr-sub-platform", users)                                                  # store events never leak to the platform inbox

    def test_store_suspension_and_activation_notify_platform_staff_only(self):
        store_status_service.suspend_store(self.store, actor=self.platform, reason="نقض قوانین")
        store_status_service.activate_store(self.store, actor=self.platform)
        events = NotificationEvent.objects.filter(type_key="platform.store_status_changed")
        self.assertEqual(events.count(), 2)
        for ev in events:
            self.assertEqual(set(InboxItem.objects.filter(event=ev).values_list("user__username", flat=True)), {"wr-sub-platform"})
        self.assertEqual(svc.unread_count(self.owner, self.store), 0)

    def test_platform_store_creation_and_contact_message(self):
        admin_events.platform_store_created(self.store)
        admin_events.platform_contact_message(SimpleNamespace(pk=1))
        admin_events.platform_contact_message(SimpleNamespace(pk=2))
        self.assertEqual(svc.unread_count(self.platform, None), 2)                                       # contact messages grouped
        self.assertEqual(NotificationEvent.objects.get(type_key="platform.contact_message").occurrence_count, 2)

    def test_unhealthy_background_jobs_notify_platform_staff_but_ok_does_not(self):
        crit = [{"check": "notification_backlog", "level": "CRITICAL", "detail": "x"}]
        with mock.patch("apps.core.management.commands.check_background_jobs.collect", return_value=crit):
            with self.assertRaises(SystemExit):
                call_command("check_background_jobs", stdout=StringIO())
        ev = NotificationEvent.objects.get(type_key="platform.jobs_unhealthy")
        self.assertEqual(ev.severity, R.CRITICAL)
        ok = [{"check": "notification_backlog", "level": "OK", "detail": "x"}]
        with mock.patch("apps.core.management.commands.check_background_jobs.collect", return_value=ok):
            call_command("check_background_jobs", stdout=StringIO())
        self.assertEqual(NotificationEvent.objects.filter(type_key="platform.jobs_unhealthy").count(), 1)


class CatalogTruthTests(TestCase):
    def test_every_wired_event_type_has_a_real_source_and_nothing_planned_is_registered(self):
        wired = {k for k, t in R.EVENT_TYPES.items() if t.wired}
        self.assertTrue(wired)
        for key in wired:
            self.assertTrue(R.EVENT_TYPES[key].source, key)
        self.assertFalse(set(R.PLANNED) & set(R.EVENT_TYPES))
        for key in R.PLANNED:
            self.assertFalse(NotificationEvent.objects.filter(type_key=key).exists())

    def test_every_registered_type_is_published_by_some_trigger_in_the_code_base(self):
        """A registered type nobody publishes would be a fake catalog entry — grep the code for each key (the engine's own tests/registry excluded)."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2]
        text = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in root.rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts and p.name != "registry.py")
        for key in R.EVENT_TYPES:
            if key in ("system.test", "platform.test"):
                continue
            self.assertTrue(re.search(re.escape('"' + key + '"'), text) or key in {"subscription.past_due", "subscription.suspended"}, key)
