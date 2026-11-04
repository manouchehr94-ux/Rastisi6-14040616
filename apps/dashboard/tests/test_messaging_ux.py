"""Unified «پیام‌رسانی» (Settings → Messaging) UX consolidation contract.

This suite guards the *redesign* — that the Notifications / Email / SMS management is one coherent experience with a single
shared five-subsection sub-navigation — on top of the behavioural coverage in ``test_notification_admin.py`` (independent
channel switches, locked/security templates, inheritance, isolation, RBAC, revisions, provider id) which this does not repeat.

The five subsections (spec order and exact Persian labels):
  رویدادها و قالب‌ها · کانال‌های ارسال · فرستنده‌ی ایمیل و دامنه · سرویس پیامک و اعتبار · تاریخچه و صف ارسال
"""

from django.urls import reverse

from apps.dashboard import navigation
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.services import template_service as ts
from apps.stores.models import Store, StoreMembership

SUBSECTION_LABELS = (
    "رویدادها و قالب‌ها", "کانال‌های ارسال", "فرستنده‌ی ایمیل و دامنه",
    "سرویس پیامک و اعتبار", "تاریخچه و صف ارسال",
)
#: every page that belongs to the unified messaging section and must carry the shared sub-navigation
MESSAGING_PAGES = (
    ("dashboard:notification-templates", ()),
    ("dashboard:notification-channels", ()),
    ("dashboard:notification-sender", ()),
    ("dashboard:notification-history", ()),
)


class UnifiedSubNavigationTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        FakeTransport.reset()

    def test_every_messaging_page_shows_the_same_five_subsection_bar(self):
        for name, args in MESSAGING_PAGES:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, 'class="msg-subnav"', msg_prefix=name)
            for label in SUBSECTION_LABELS:
                self.assertContains(r, label, msg_prefix=f"{name}:{label}")

    def test_sms_provider_settings_page_is_part_of_the_same_messaging_section(self):
        """The SMS provider/credits page was the fragmented outlier; it must now carry the identical sub-navigation."""
        r = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="msg-subnav"')
        for label in SUBSECTION_LABELS:
            self.assertContains(r, label)
        self.assertContains(r, "سرویس پیامک و اعتبار")

    def test_subsection_links_point_at_the_real_working_views(self):
        r = self.client.get(reverse("dashboard:notification-templates"))
        for target in ("dashboard:notification-templates", "dashboard:notification-channels",
                       "dashboard:notification-sender", "dashboard:notification-history"):
            self.assertContains(r, reverse(target))
        self.assertContains(r, reverse("dashboard:settings") + "?section=sms")

    def test_active_subsection_is_marked_for_screen_readers(self):
        r = self.client.get(reverse("dashboard:notification-channels"))
        self.assertContains(r, 'aria-current="page"')


class SingleMessagingDestinationTests(CouponViewsTestCase):
    """The redesign must not create two competing notification admin systems."""

    def test_sms_provider_page_does_not_offer_a_second_event_template_editor(self):
        """SMS per-event text is edited only in the unified editor; the SMS settings page links there instead of
        presenting its own editable channel switches (which would conflict with the unified editor)."""
        r = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(r, reverse("dashboard:notification-templates"))
        self.assertContains(r, "یک ویرایشگرِ واحد")

    def test_navigation_has_exactly_one_tab_per_destination(self):
        seen = {}
        for section in navigation.SECTIONS:
            for tab in section.tabs:
                key = (tab.url_name, tab.query)
                self.assertNotIn(key, seen, f"{tab.key} duplicates {seen.get(key)}")
                seen[key] = tab.key

    def test_both_entry_points_resolve_without_error(self):
        """Marketing shortcut and the Settings SMS subsection are both valid entries into the same experience."""
        self.assertEqual(self.client.get(reverse("dashboard:notification-templates")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:settings") + "?section=sms").status_code, 200)


class UnifiedEventEditorTests(CouponViewsTestCase):
    """One event → one editor showing SMS and Email together (the core acceptance criterion)."""

    def _give_sender(self):
        from apps.notifications.tests.helpers import give_active_sender

        give_active_sender(self.store, "info@editor-test.example")

    def test_order_created_editor_shows_both_channels_and_all_required_controls(self):
        self._give_sender()
        r = self.client.get(reverse("dashboard:notification-template-edit", args=["order.created"]))
        self.assertEqual(r.status_code, 200)
        # both channel cards present (labelled sections) and shown side by side via the two-column grid
        self.assertContains(r, 'id="sms-h"')
        self.assertContains(r, 'id="email-h"')
        self.assertContains(r, "پیامک")
        self.assertContains(r, "ایمیل")
        self.assertContains(r, "ev-grid")   # the side-by-side layout
        # SMS controls
        self.assertContains(r, 'name="sms_enabled"')
        self.assertContains(r, 'name="sms_body"')
        # Email controls: enable, subject, plain-text body, HTML editor
        self.assertContains(r, 'name="email_enabled"')
        self.assertContains(r, 'name="email_subject"')
        self.assertContains(r, 'name="email_body"')
        self.assertContains(r, 'name="email_html"')
        # one save action, revision history, test-send
        self.assertContains(r, "ذخیره")
        self.assertContains(r, "تاریخچه‌ی نسخه‌ها")
        self.assertContains(r, "ارسالِ آزمایشی")
        # allowed variables surfaced for this event
        self.assertContains(r, "order_number")

    def test_saving_one_channel_does_not_reset_the_other(self):
        """Regression guard for the spec's «saving must not reset the other channel»."""
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="پیامک {order_number}")
        ts.save_template(self.store, "order.created", "email", enabled=True, subject="موضوع", body="ایمیل {order_number}")
        # edit only the email side through the unified editor
        self.client.post(reverse("dashboard:notification-template-edit", args=["order.created"]), {
            "action": "save", "channel": "",
            "sms_enabled": "on", "sms_body": "پیامک {order_number}",
            "email_enabled": "on", "email_subject": "موضوعِ تازه", "email_body": "ایمیلِ تازه {order_number}", "email_html": "",
        })
        sms = ts.get_template(self.store, "order.created", "sms")
        email = ts.get_template(self.store, "order.created", "email")
        self.assertEqual(sms["body"], "پیامک {order_number}")          # SMS untouched
        self.assertTrue(sms["enabled"])
        self.assertEqual(email["subject"], "موضوعِ تازه")               # email updated
        self.assertEqual(email["body"], "ایمیلِ تازه {order_number}")

    def test_event_list_shows_both_sms_and_email_status_per_event(self):
        r = self.client.get(reverse("dashboard:notification-templates"))
        self.assertEqual(r.status_code, 200)
        # the list has an SMS column and an Email column header
        self.assertContains(r, "<th>پیامک</th>", html=False)
        self.assertContains(r, "<th>ایمیل</th>", html=False)
        self.assertContains(r, reverse("dashboard:notification-template-edit", args=["order.created"]))


class MessagingRbacTests(CouponViewsTestCase):
    def test_role_without_settings_permission_cannot_reach_any_messaging_page(self):
        self._login_as(StoreMembership.Role.ANALYST, "771")
        for name, args in MESSAGING_PAGES:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)
        self.assertEqual((self.client.get(reverse("dashboard:settings") + "?section=sms")).status_code, 403)

    def test_messaging_is_scoped_to_the_current_store(self):
        other = Store.objects.create(name="مستأجر دیگر", slug="msgux-other", status=Store.Status.ACTIVE)
        ts.save_template(other, "order.created", "email", enabled=True, subject="SECRET-OTHER", body="b {order_number}")
        r = self.client.get(reverse("dashboard:notification-template-edit", args=["order.created"]))
        self.assertNotContains(r, "SECRET-OTHER")
