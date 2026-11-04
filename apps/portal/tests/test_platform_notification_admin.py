"""Platform-admin notification management: catalog, platform default templates, test sending, sender oversight,
delivery review, audit — with granular RBAC."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import (
    EmailSenderIdentity, NotificationOutbox, NotificationTemplateRevision, PlatformNotificationTemplate,
)
from apps.notifications.services import template_service as ts
from apps.notifications.tests.helpers import give_active_sender
from apps.portal.models import PlatformAuditLogEntry
from apps.stores.models import Store, StoreDomain

User = get_user_model()
HOST = "platformadmins.rastisi.localhost"
URLCONF = "shop_core.urls_platform_admin"


def url(name, *args):
    return reverse(f"portal_platform_admin:{name}", args=args, urlconf=URLCONF)


def grant(user, *codenames):
    for c in codenames:
        user.user_permissions.add(Permission.objects.get(content_type__app_label="notifications", codename=c))
    return User.objects.get(pk=user.pk)  # drop the per-instance permission cache


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PlatformNotificationAdminBase(TestCase):
    def setUp(self):
        FakeTransport.reset()
        self.owner = User.objects.create_user(username="owner@p.test", email="owner@p.test", password="a-very-strong-pass-1",
                                              is_staff=True, is_superuser=True)
        self.store = Store.objects.get(slug="akhlaghi")

    def login(self, user):
        self.client.force_login(user)

    def get(self, name, *args, **kw):
        return self.client.get(url(name, *args), HTTP_HOST=HOST, **kw)

    def post(self, name, data=None, args=()):
        return self.client.post(url(name, *args), data or {}, HTTP_HOST=HOST)


class AccessControlTests(PlatformNotificationAdminBase):
    PAGES = (("notification-catalog", ()), ("notification-senders", ()), ("notification-delivery", ()),
             ("notification-audit", ()), ("notification-platform-template", ("order.created",)))

    def test_anonymous_is_sent_to_platform_login(self):
        for name, args in self.PAGES:
            r = self.get(name, *args)
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/login/", r["Location"], name)

    def test_store_owner_and_plain_staff_get_403_on_every_page(self):
        ordinary = User.objects.create_user(username="o@x.test", password="a-very-strong-pass-1")
        staff = User.objects.create_user(username="s@x.test", password="a-very-strong-pass-1", is_staff=True)
        for user in (staff,):
            self.login(user)
            for name, args in self.PAGES:
                self.assertEqual(self.get(name, *args).status_code, 403, name)
        self.client.logout()
        self.login(ordinary)  # not even staff: redirected to login, never served
        for name, args in self.PAGES:
            self.assertIn(self.get(name, *args).status_code, (302, 403), name)

    def test_superuser_owner_can_open_every_page(self):
        self.login(self.owner)
        for name, args in self.PAGES:
            self.assertEqual(self.get(name, *args).status_code, 200, name)

    def test_each_permission_unlocks_exactly_its_own_pages(self):
        matrix = {
            "view_notification_catalog": {"notification-catalog"},
            "manage_platform_templates": {"notification-platform-template"},
            "view_notification_delivery": {"notification-delivery", "notification-audit"},
            "manage_email_senders": {"notification-senders"},
        }
        for perm, allowed in matrix.items():
            user = grant(User.objects.create_user(username=f"{perm}@x.test", password="a-very-strong-pass-1", is_staff=True), perm)
            self.client.logout()
            self.login(user)
            for name, args in self.PAGES:
                expected = 200 if name in allowed else 403
                self.assertEqual(self.get(name, *args).status_code, expected, f"{perm} -> {name}")

    def test_mutating_endpoints_need_their_own_permission(self):
        reader = grant(User.objects.create_user(username="reader@x.test", password="a-very-strong-pass-1", is_staff=True),
                       "view_notification_catalog", "view_notification_delivery")
        self.login(reader)
        self.assertEqual(self.post("notification-platform-template", {"email_subject": "x"}, ("order.created",)).status_code, 403)
        self.assertEqual(self.post("notification-platform-template-preview", {"channel": "email"}, ("order.created",)).status_code, 403)
        self.assertEqual(self.post("notification-platform-template-test", {"recipient": "a@b.co"}, ("order.created",)).status_code, 403)
        identity = EmailSenderIdentity.objects.create(store=self.store)
        self.assertEqual(self.post("notification-sender-toggle", args=(identity.pk,)).status_code, 403)
        identity.refresh_from_db()
        self.assertFalse(identity.platform_disabled)
        self.assertFalse(PlatformNotificationTemplate.objects.exists())

    def test_team_member_with_a_notification_permission_lands_on_the_catalog_not_the_full_admin(self):
        member = grant(User.objects.create_user(username="team@x.test", password="a-very-strong-pass-1", is_staff=True),
                       "view_notification_catalog")
        self.login(member)
        r = self.client.get("/login/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/notifications/", r["Location"])
        self.assertEqual(self.client.get("/", HTTP_HOST=HOST).status_code, 302)       # home stays superuser-only
        self.assertEqual(self.client.get("/stores/", HTTP_HOST=HOST).status_code, 302)  # other sections too

    def test_team_member_without_any_notification_permission_gets_no_special_access(self):
        member = User.objects.create_user(username="plain@x.test", password="a-very-strong-pass-1", is_staff=True)
        self.login(member)
        r = self.client.get("/login/", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)  # login form, no redirect

    def test_inactive_user_with_permissions_is_denied(self):
        user = grant(User.objects.create_user(username="gone@x.test", password="a-very-strong-pass-1", is_staff=True),
                     "view_notification_catalog")
        user.is_active = False
        user.save()
        self.client.force_login(user) if False else None
        self.assertFalse(__import__("apps.portal.notification_admin_views", fromlist=["x"]).has_platform_perm(user, "view_notification_catalog"))


class CatalogAndTemplateTests(PlatformNotificationAdminBase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)

    def save(self, key="return.approved", **extra):
        data = {"email_enabled": "on", "email_subject": "پلتفرم {return_number}", "email_body": "متن {order_number}",
                "email_html": "<p>سلام <b>{customer_name}</b></p><script>x()</script>", "sms_enabled": "on", "sms_body": "پیامک {return_number}"}
        data.update(extra)
        return self.post("notification-platform-template", data, (key,))

    def test_catalog_lists_every_event_with_category_audience_and_sender(self):
        r = self.get("notification-catalog")
        from apps.notifications.events import EVENTS

        for key in EVENTS:
            self.assertContains(r, key)
        self.assertContains(r, "دامنه‌ی فروشگاه")
        self.assertContains(r, "راستی‌سی")

    def test_platform_default_is_saved_sanitized_versioned_and_audited(self):
        self.assertEqual(self.save().status_code, 302)
        row = PlatformNotificationTemplate.objects.get(event_key="return.approved", channel="email")
        self.assertNotIn("script", row.body_html)
        self.assertEqual((row.version, row.updated_by), (1, self.owner))
        self.save(email_subject="دوم {return_number}")
        row.refresh_from_db()
        self.assertEqual(row.version, 2)
        self.assertEqual(NotificationTemplateRevision.objects.filter(scope="platform", event_key="return.approved", channel="email").count(), 2)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="notifications.platform_template_saved", actor=self.owner).exists())

    def test_platform_default_reaches_stores_until_they_override_it(self):
        self.save()
        self.assertEqual(ts.get_template(self.store, "return.approved", "email")["subject"], "پلتفرم {return_number}")
        other = Store.objects.create(name="دیگر", slug="pl-other", status=Store.Status.ACTIVE)
        self.assertEqual(ts.get_template(other, "return.approved", "email")["subject"], "پلتفرم {return_number}")

    def test_lock_for_stores_prevents_store_overrides(self):
        self.save(email_locked="on")
        self.assertTrue(ts.get_template(self.store, "return.approved", "email")["locked"])
        from apps.notifications.services.template_service import PlatformManagedError

        with self.assertRaises(PlatformManagedError):
            ts.save_template(self.store, "return.approved", "email", enabled=True, subject="x {return_number}", body="y {order_number}")

    def test_reset_removes_the_platform_default_and_records_it(self):
        self.save()
        self.post("notification-platform-template", {"action": "reset", "channel": "email"}, ("return.approved",))
        self.assertFalse(PlatformNotificationTemplate.objects.filter(channel="email").exists())
        self.assertTrue(NotificationTemplateRevision.objects.filter(scope="platform", action="reset").exists())

    def test_security_event_cannot_be_disabled_or_stripped_of_its_protected_variable_by_the_platform(self):
        r = self.post("notification-platform-template", {"email_subject": "s", "email_body": "بدون متغیر"}, ("account.sensitive_changed",))
        self.assertContains(r, "متغیرِ ضروری")
        self.post("notification-platform-template", {"email_subject": "s {changed_field}", "email_body": "{changed_field}",
                                                     "sms_body": "{changed_field}"}, ("account.sensitive_changed",))
        row = PlatformNotificationTemplate.objects.get(event_key="account.sensitive_changed", channel="email")
        self.assertTrue(row.is_enabled)

    def test_invalid_variable_is_rejected(self):
        r = self.save(email_body="{secret_token}")
        self.assertContains(r, "متغیرِ ناشناخته")
        self.assertFalse(PlatformNotificationTemplate.objects.exists())

    def test_preview_uses_sample_data_and_renders_sandboxed_html(self):
        r = self.post("notification-platform-template-preview", {
            "channel": "email", "email_subject": "ارسال {order_number}", "email_body": "ب", "email_html": "<p>{order_number}</p>"},
            ("order.shipped",))
        self.assertContains(r, "ارسال DM-12345")
        self.assertContains(r, 'sandbox=""')

    def test_legacy_sms_text_is_not_editable_here(self):
        self.post("notification-platform-template", {"email_subject": "s {order_number}", "email_body": "b", "sms_body": "HACK"}, ("order.created",))
        self.assertFalse(PlatformNotificationTemplate.objects.filter(event_key="order.created", channel="sms").exists())

    def test_unknown_event_is_404(self):
        self.assertEqual(self.get("notification-platform-template", "no.such").status_code, 404)

    def test_controlled_test_send_goes_through_the_target_stores_own_sender(self):
        give_active_sender(self.store, "info@mybikestore.test")
        self.post("notification-platform-template-test", {"channel": "email", "recipient": "qa@example.com", "store_id": str(self.store.pk)},
                  ("order.created",))
        self.assertEqual(len(FakeTransport.sent), 1)
        self.assertEqual(FakeTransport.sent[0]["message"].from_address, "info@mybikestore.test")
        self.assertTrue(NotificationOutbox.objects.get(is_test=True).is_test)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="notifications.platform_test_sent").exists())

    def test_test_send_without_an_active_store_sender_is_held_not_sent_from_a_shared_domain(self):
        self.post("notification-platform-template-test", {"channel": "email", "recipient": "qa@example.com", "store_id": str(self.store.pk)},
                  ("order.created",))
        self.assertEqual((FakeTransport.sent, mail.outbox), ([], []))
        self.assertEqual(NotificationOutbox.objects.get(is_test=True).last_error, "sender_not_active")

    def test_test_send_requires_a_store_and_a_recipient(self):
        self.post("notification-platform-template-test", {"channel": "email", "recipient": "qa@example.com"}, ("order.created",))
        self.post("notification-platform-template-test", {"channel": "email", "store_id": str(self.store.pk)}, ("order.created",))
        self.assertFalse(NotificationOutbox.objects.exists())


class SendersDeliveryAuditTests(PlatformNotificationAdminBase):
    def setUp(self):
        super().setUp()
        self.login(self.owner)
        StoreDomain.objects.create(store=self.store, hostname="mybikestore.test", domain_type="custom_domain")
        svc.sync_sender_identity(self.store)
        self.identity = EmailSenderIdentity.objects.get(store=self.store)

    def test_senders_overview_lists_all_stores_with_status_and_reason(self):
        r = self.get("notification-senders")
        self.assertContains(r, self.store.name)
        self.assertContains(r, "mybikestore.test")
        self.assertContains(r, "dns_pending")
        self.assertContains(self.get("notification-senders", **{"QUERY_STRING": "status=active"}), "موردی نیست")

    def test_platform_can_disable_then_reenable_a_stores_email_sender(self):
        FakeTransport.verify("mybikestore.test")
        svc.sync_sender_identity(self.store)
        self.assertEqual(svc.active_sender_address(self.store), "info@mybikestore.test")
        self.post("notification-sender-toggle", args=(self.identity.pk,))
        self.identity.refresh_from_db()
        self.assertTrue(self.identity.platform_disabled)
        self.assertEqual(svc.active_sender_address(self.store), "")  # blocked immediately
        self.post("notification-sender-toggle", args=(self.identity.pk,))
        self.assertEqual(svc.active_sender_address(self.store), "info@mybikestore.test")

    def test_delivery_page_shows_usage_and_failures_and_filters_attention(self):
        NotificationOutbox.objects.create(channel="email", store=self.store, status="dead", last_error="boom", event_key="order.created",
                                          body="b", recipient_email="a@b.co")
        NotificationOutbox.objects.create(channel="sms", store=self.store, status="sent", event_key="order.created", body="b",
                                          recipient_phone="09120000000")
        r = self.get("notification-delivery")
        self.assertContains(r, "email/dead")
        self.assertContains(r, "sms/sent")
        self.assertContains(r, "boom")
        r = self.client.get(url("notification-delivery") + "?attention=1", HTTP_HOST=HOST)
        self.assertContains(r, "boom")
        self.assertNotContains(r, "09120000000")

    def test_delivery_page_never_prints_message_bodies_or_recipient_addresses(self):
        NotificationOutbox.objects.create(channel="email", store=self.store, status="failed", last_error="x", event_key="order.created",
                                          body="PRIVATE-BODY-TEXT", recipient_email="private.person@example.com")
        r = self.get("notification-delivery")
        self.assertNotContains(r, "PRIVATE-BODY-TEXT")
        self.assertNotContains(r, "private.person@example.com")

    def test_audit_page_lists_template_revisions_and_audit_entries(self):
        ts.save_platform_template("return.approved", "email", enabled=True, subject="s {return_number}", body="b {order_number}", actor=self.owner)
        self.post("notification-platform-template", {"email_enabled": "on", "email_subject": "s {return_number}", "email_body": "b {order_number}"},
                  ("return.approved",))
        r = self.get("notification-audit")
        self.assertContains(r, "return.approved")
        self.assertContains(r, "notifications.platform_template_saved")
