"""Exhaustive audit: every SMS-triggered business event has an email counterpart (subject to a valid recipient email),
and phone-possession OTPs are the single deliberate exception. The matrix is COMPUTED (``apps.notifications.parity``)
from the code registries, then verified against the real trigger source files."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer
from apps.notifications import events as ev
from apps.notifications import parity
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import template_service as ts
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.tests.helpers import give_active_sender
from apps.sms.events import SmsEvent
from apps.stores.models import Store

User = get_user_model()
ROOT = Path(settings.BASE_DIR)


class InventoryTests(TestCase):
    def setUp(self):
        self.rows = parity.build()

    def test_every_sms_event_is_either_wired_to_an_email_event_or_a_documented_exception(self):
        wired = {d.legacy_sms_event or d.platform_sms_event for d in ev.EVENTS.values()} - {""}
        for sms in SmsEvent:
            if str(sms.value) in {str(w) for w in wired}:
                continue
            self.assertIn(sms, parity.OTP_EVENTS | parity.INFRA_SMS_EVENTS,
                          f"SMS event {sms.value} has no email counterpart and is not a documented exception")

    def test_otp_events_are_the_only_customer_or_owner_facing_sms_without_email(self):
        no_email = {r["sms_event"] for r in self.rows if not r["event_key"] and r["category"] == "otp"}
        self.assertEqual(no_email, {str(s.value) for s in parity.OTP_EVENTS})

    def test_every_notification_event_defines_email_content(self):
        missing = [r["event_key"] for r in self.rows if r["event_key"] and not r["has_email"]]
        self.assertEqual(missing, [])

    def test_every_sms_notification_event_has_an_email_with_the_same_recipient_class(self):
        for r in self.rows:
            if r["event_key"] and r["has_sms"]:
                self.assertTrue(r["has_email"], r["event_key"])

    def test_every_trigger_call_site_really_exists_in_source(self):
        for r in self.rows:
            if not r["event_key"]:
                continue
            self.assertTrue(r["trigger_file"], f"{r['event_key']}: no trigger recorded")
            text = (ROOT / r["trigger_file"]).read_text(encoding="utf-8")
            self.assertIn(r["trigger_text"], text, f"{r['event_key']}: call site not found in {r['trigger_file']}")

    def test_extra_trigger_sites_are_verified_when_their_file_exists(self):
        checked = 0
        for r in self.rows:
            for path, text, _desc, optional in r.get("extra_triggers", []):
                file = ROOT / path
                if not file.exists():
                    self.assertTrue(optional, f"{path} is required but missing")
                    continue
                self.assertIn(text, file.read_text(encoding="utf-8"), path)
                checked += 1
        self.assertGreaterEqual(checked, 0)

    def test_every_dispatch_site_in_the_codebase_is_in_the_inventory(self):
        """Scan production code for ``business_events.<fn>(`` and ``safe_dispatch/dispatch_event(`` — a new, unlisted
        trigger fails here so the matrix cannot silently go stale."""
        import re

        known_files = {r["trigger_file"] for r in self.rows if r["trigger_file"]}
        known_files |= {t[0] for r in self.rows for t in r.get("extra_triggers", [])}
        found = set()
        for path in (ROOT / "apps").rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or rel.endswith("tests.py") or "/migrations/" in rel or "/management/" in rel:
                continue
            txt = path.read_text(encoding="utf-8")
            if re.search(r"business_events\.\w+\(|safe_dispatch\(|(?<![\w.])dispatch_event\(", txt):
                found.add(rel)
        allowed_infra = {
            "apps/notifications/services/dispatcher.py", "apps/notifications/services/business_events.py",
            "apps/dashboard/engagement_views.py",  # template TEST-send (is_test), not a business event
            "apps/portal/notification_admin_views.py",  # platform-admin TEST-send (is_test), not a business event
            "apps/notifications/parity.py",  # the matrix itself quotes these strings as data, not calls
            "apps/notifications/registry.py",  # admin-Inbox trigger registry (payment-engine branch): names call sites in a string
        }
        self.assertEqual(found - known_files - allowed_infra, set(), "unlisted notification trigger call sites")

    def test_markdown_matrix_renders(self):
        md = parity.to_markdown(self.rows)
        self.assertIn("order.created", md)
        self.assertIn("عمدی", md)


class EmailCounterpartBehaviourTests(TestCase):
    """For EVERY customer-audience event: with a valid email an email row is created; without one, none is."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        give_active_sender(self.store)
        user = User.objects.create_user(username="09127770001", password="x12345678")
        self.customer = Customer.objects.create(
            user=user, full_name="سارا", phone="09127770001", email="sara@example.com",
            accepts_promotional_email=True, accepts_promotional_sms=True,
        )

    def _ctx(self, event):
        ctx = dict(event.sample)
        ctx.setdefault("customer_name", "سارا")
        return ctx

    def test_customer_events_create_one_email_row_with_valid_email(self):
        for key, event in ev.EVENTS.items():
            if event.audience != ev.AUDIENCE_CUSTOMER or event.sender != "store":
                continue
            rows = dispatch_event(key, store=self.store, customer=self.customer, context=self._ctx(event),
                                  channels=["email"], dedupe_key=f"parity-{key}")
            email_defaulted_off = not event.email_enabled_default
            if email_defaulted_off:
                self.assertEqual(rows, [], f"{key}: email default OFF must create nothing")
                continue
            self.assertEqual(len(rows), 1, key)
            self.assertEqual(rows[0].channel, "email", key)
            self.assertEqual(rows[0].status, NotificationOutbox.Status.PENDING, f"{key}: {rows[0].skip_reason}")
            self.assertEqual(rows[0].recipient_email, "sara@example.com")
            self.assertEqual(rows[0].is_security, event.category == ev.SECURITY)
            self.assertNotIn("{", rows[0].subject + rows[0].body, f"{key}: unresolved placeholder")

    def test_customer_without_email_gets_no_email_row_but_sms_still_works(self):
        self.customer.email = ""
        self.customer.save()
        for key, event in ev.EVENTS.items():
            if event.audience != ev.AUDIENCE_CUSTOMER or event.sender != "store":
                continue
            rows = dispatch_event(key, store=self.store, customer=self.customer, context=self._ctx(event),
                                  channels=["email"], dedupe_key=f"noemail-{key}")
            self.assertEqual(rows, [], f"{key}: no recipient email -> no email row")

    def test_missing_customer_creates_nothing(self):
        rows = dispatch_event("order.created", store=self.store, customer=None, context=self._ctx(ev.EVENTS["order.created"]),
                              channels=["email"], dedupe_key="nocust")
        self.assertEqual(rows, [])

    def test_persian_plain_and_html_render_for_every_email_event(self):
        for key, event in ev.EVENTS.items():
            out = ts.preview(self.store, key, "email")
            self.assertTrue(out["subject"], key)
            self.assertIn('dir="rtl"', out["html_document"], key)
            self.assertIn("lang=\"fa\"", out["html_document"], key)
            self.assertNotIn("{", out["subject"] + out["body"], key)


class OtpNeverEmailedTests(TestCase):
    def test_no_notification_event_carries_an_otp_variable(self):
        for key, event in ev.EVENTS.items():
            self.assertFalse({v for v in event.variables if "otp" in v.lower() or v in ("code", "token")}, key)

    def test_otp_sms_keys_have_no_event_def_and_cannot_be_dispatched(self):
        store = Store.objects.get(slug="akhlaghi")
        for sms in parity.OTP_EVENTS:
            with self.assertRaises(KeyError):
                dispatch_event(str(sms.value), store=store)

    def test_otp_flow_still_goes_through_sms_only(self):
        import inspect

        from apps.portal.services import owner_otp_service
        from apps.sms.services import otp_service

        for module in (owner_otp_service, otp_service):
            src = inspect.getsource(module)
            self.assertNotIn("send_mail", src)
            self.assertNotIn("EmailMultiAlternatives", src)
            self.assertNotIn("dispatch_event", src)
