"""Store-admin notification management: sender-identity diagnostics, channel switches, HTML templates, inheritance,
RBAC and tenant isolation."""

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailSenderIdentity, NotificationTemplate
from apps.notifications.services import template_service as ts
from apps.notifications.tests.helpers import give_active_sender
from apps.stores.models import Store, StoreDomain, StoreMembership


def custom_domain(store, host, **kw):
    return StoreDomain.objects.create(
        store=store, hostname=host, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.UNVERIFIED, **kw)


class SenderPageTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        FakeTransport.reset()
        self.url = reverse("dashboard:notification-sender")

    def test_inactive_shows_status_reason_action_responsible_party_and_last_check(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="sender-status" data-status="inactive"')
        for needle in ("فروشگاه هنوز دامنه‌ی اختصاصی ندارد", "یک دامنه‌ی اختصاصی برای فروشگاه ثبت کنید",
                       'id="sender-responsible">مالکِ دامنه', 'id="sender-owner-action">بله', 'id="sender-platform-fix">خیر',
                       "آخرین بررسی: هنوز انجام نشده", "بررسیِ دوباره"):
            self.assertContains(r, needle)

    def test_pending_state_lists_exact_provider_generated_dns_records_and_both_verifications(self):
        custom_domain(self.store, "mybikestore.test")
        self.client.post(reverse("dashboard:notification-sender-retry"))
        r = self.client.get(self.url)
        self.assertContains(r, 'data-status="pending"')
        self.assertContains(r, "رکوردهایِ DNS که باید اضافه شود")
        identity = EmailSenderIdentity.objects.get(store=self.store)
        self.assertEqual(len(identity.dns_records), 3)
        for rec in identity.dns_records:
            self.assertContains(r, rec["name"])
            self.assertContains(r, rec["value"])
            self.assertContains(r, "CNAME")
        self.assertContains(r, 'id="two-verifications"')
        self.assertContains(r, 'id="site-verification"')
        self.assertContains(r, 'id="email-verification">تأییدنشده')
        self.assertNotContains(r, "موفق فرض نمی‌شود")  # no auto-DNS claim when nothing was requested
        self.assertContains(r, 'id="sender-responsible"')

    def test_retry_activates_only_after_provider_confirms_and_is_audited(self):
        custom_domain(self.store, "mybikestore.test")
        self.client.post(reverse("dashboard:notification-sender-retry"))
        self.assertEqual(EmailSenderIdentity.objects.get(store=self.store).status, "pending")
        self.client.post(reverse("dashboard:notification-sender-retry"))
        self.assertEqual(EmailSenderIdentity.objects.get(store=self.store).status, "pending")  # still not verified
        FakeTransport.verify("mybikestore.test")
        r = self.client.post(reverse("dashboard:notification-sender-retry"), follow=True)
        self.assertEqual(EmailSenderIdentity.objects.get(store=self.store).status, "active")
        self.assertContains(r, "info@mybikestore.test")
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="notifications.sender_retry").exists())
        self.assertTrue(AuditLogEntry.objects.filter(
            store=self.store, action_code="notifications.sender_identity_status_changed").exists())

    def test_provider_error_shows_error_state_and_who_can_fix_it(self):
        custom_domain(self.store, "mybikestore.test")
        self.client.post(reverse("dashboard:notification-sender-retry"))
        FakeTransport.fail_domain("mybikestore.test")
        self.client.post(reverse("dashboard:notification-sender-retry"))
        r = self.client.get(self.url)
        self.assertContains(r, 'data-status="error"')
        self.assertContains(r, "نامعتبر یا ناموجود")
        self.assertContains(r, 'id="sender-owner-action">بله')

    def test_retry_requires_post_and_login(self):
        self.assertEqual(self.client.get(reverse("dashboard:notification-sender-retry")).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(reverse("dashboard:notification-sender-retry")).status_code, 302)

    def test_role_without_settings_permission_is_forbidden(self):
        self._login_as(StoreMembership.Role.ANALYST, "501")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(reverse("dashboard:notification-sender-retry")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:notification-channels")).status_code, 403)

    def test_another_stores_sender_is_never_visible(self):
        other = Store.objects.create(name="دیگر", slug="snd-other", status=Store.Status.ACTIVE)
        custom_domain(other, "secret-b-store.test")
        svc.sync_sender_identity(other)
        custom_domain(self.store, "mine.test")
        svc.sync_sender_identity(self.store)
        r = self.client.get(self.url)
        self.assertContains(r, "mine.test")
        self.assertNotContains(r, "secret-b-store.test")
        self.assertNotContains(r, EmailSenderIdentity.objects.get(store=other).dns_records[0]["name"])

    def test_sender_page_links_exist_in_all_tabs(self):
        for name in ("notification-templates", "notification-history", "notification-channels", "notification-sender"):
            r = self.client.get(reverse(f"dashboard:{name}"))
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, reverse("dashboard:notification-sender"))


class ChannelSettingsTests(CouponViewsTestCase):
    def post_channels(self, **flags):
        data = {}
        for k, v in flags.items():
            key = k.replace("__", "__")
            data[f"seen__{key}"] = "1"
            if v:
                data[key] = "on"
        return self.client.post(reverse("dashboard:notification-channels"), data)

    def test_email_and_sms_switches_are_independent_and_persist(self):
        self.post_channels(**{"return.approved__email": False, "return.approved__sms": True})
        self.assertFalse(ts.get_template(self.store, "return.approved", "email")["enabled"])
        self.assertTrue(ts.get_template(self.store, "return.approved", "sms")["enabled"])
        self.post_channels(**{"return.approved__email": True, "return.approved__sms": False})
        self.assertTrue(ts.get_template(self.store, "return.approved", "email")["enabled"])
        self.assertFalse(ts.get_template(self.store, "return.approved", "sms")["enabled"])

    def test_switch_keeps_current_text_untouched(self):
        ts.save_template(self.store, "return.approved", "email", enabled=True, subject="موضوع {return_number}", body="متن {order_number}")
        self.post_channels(**{"return.approved__email": False})
        t = ts.get_template(self.store, "return.approved", "email")
        self.assertEqual((t["enabled"], t["subject"], t["body"]), (False, "موضوع {return_number}", "متن {order_number}"))

    def test_security_event_cannot_be_switched_off_even_by_a_forged_post(self):
        self.post_channels(**{"account.sensitive_changed__email": False, "account.sensitive_changed__sms": False})
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "email")["enabled"])
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "sms")["enabled"])

    def test_platform_locked_template_cannot_be_toggled_by_the_store(self):
        ts.save_platform_template("return.approved", "email", enabled=True, subject="s {return_number}", body="b {order_number}",
                                  locked_for_stores=True)
        self.post_channels(**{"return.approved__email": False})
        self.assertTrue(ts.get_template(self.store, "return.approved", "email")["enabled"])
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, event_key="return.approved").exists())

    def test_platform_sender_events_are_not_listed_to_stores(self):
        r = self.client.get(reverse("dashboard:notification-channels"))
        self.assertNotContains(r, "platform.email_sender_problem")
        self.assertContains(r, "return.approved")

    def test_switches_are_scoped_to_the_current_store(self):
        other = Store.objects.create(name="دیگر", slug="chn-other", status=Store.Status.ACTIVE)
        self.post_channels(**{"return.approved__email": False})
        self.assertTrue(ts.get_template(other, "return.approved", "email")["enabled"])

    def test_forged_unrendered_switch_is_ignored(self):
        """A field without its ``seen__`` marker (not rendered as editable) is never applied."""
        self.client.post(reverse("dashboard:notification-channels"), {})
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store).exists())


class TemplateEditorTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()  # the test-send view rate-limits per store through the shared cache; keep tests order-independent

    def edit(self, key="return.approved", **data):
        return self.client.post(reverse("dashboard:notification-template-edit", args=[key]), data)

    def test_store_can_customize_subject_html_and_plain_text_and_script_is_stripped(self):
        r = self.edit(email_enabled="on", email_subject="تأیید {return_number}", email_body="سلام {customer_name}",
                      email_html="<p>سلام <b>{customer_name}</b></p><script>x()</script>", sms_enabled="on", sms_body="پیامک {return_number}")
        self.assertEqual(r.status_code, 302)
        t = ts.get_template(self.store, "return.approved", "email")
        self.assertEqual((t["subject"], t["body"], t["source"]), ("تأیید {return_number}", "سلام {customer_name}", "store"))
        self.assertIn("<b>{customer_name}</b>", t["body_html"])
        self.assertNotIn("script", t["body_html"])
        page = self.client.get(reverse("dashboard:notification-template-edit", args=["return.approved"]))
        self.assertContains(page, "بازنویسیِ این فروشگاه")
        self.assertContains(page, 'id="revisions"')

    def test_invalid_variable_is_rejected_and_nothing_is_saved(self):
        r = self.edit(email_enabled="on", email_subject="s", email_body="{password}")
        self.assertContains(r, "متغیرِ ناشناخته")
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, channel="email").exists())

    def test_inheritance_platform_default_then_store_override_then_reset(self):
        ts.save_platform_template("return.approved", "email", enabled=True, subject="پلتفرم {return_number}", body="متن پلتفرم {order_number}")
        self.assertEqual(ts.get_template(self.store, "return.approved", "email")["source"], "platform")
        self.edit(email_enabled="on", email_subject="فروشگاه {return_number}", email_body="متن فروشگاه {order_number}",
                  sms_enabled="on", sms_body="x {return_number}")
        self.assertEqual(ts.get_template(self.store, "return.approved", "email")["subject"], "فروشگاه {return_number}")
        self.client.post(reverse("dashboard:notification-template-edit", args=["return.approved"]), {"action": "reset", "channel": "email"})
        t = ts.get_template(self.store, "return.approved", "email")
        self.assertEqual((t["source"], t["subject"]), ("platform", "پلتفرم {return_number}"))  # back to PLATFORM default

    def test_platform_locked_template_ignores_store_edits(self):
        ts.save_platform_template("return.approved", "email", enabled=True, subject="قفل {return_number}", body="بدنه {order_number}",
                                  locked_for_stores=True)
        self.edit(email_enabled="on", email_subject="هک {return_number}", email_body="هک {order_number}", sms_enabled="on", sms_body="x {return_number}")
        t = ts.get_template(self.store, "return.approved", "email")
        self.assertEqual((t["subject"], t["locked"]), ("قفل {return_number}", True))
        page = self.client.get(reverse("dashboard:notification-template-edit", args=["return.approved"]))
        self.assertContains(page, "فقط راستی‌سی مدیریت می‌کند")

    def test_security_email_keeps_protected_variable_and_stays_enabled(self):
        r = self.edit("account.sensitive_changed", email_subject="s", email_body="سلام بدون متغیر", sms_enabled="on", sms_body="{changed_field}")
        self.assertContains(r, "متغیرِ ضروری")
        self.edit("account.sensitive_changed", email_subject="s {changed_field}", email_body="x {changed_field}", sms_body="{changed_field}")
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "email")["enabled"])

    def test_preview_renders_sample_data_and_sandboxed_html_iframe(self):
        r = self.client.post(reverse("dashboard:notification-template-preview", args=["order.shipped"]), {
            "channel": "email", "email_subject": "ارسال {order_number}", "email_body": "کد {tracking_number}",
            "email_html": "<p>کد <b>{tracking_number}</b></p><script>1</script>"})
        self.assertContains(r, "ارسال DM-12345")
        self.assertContains(r, "RX123456789IR")
        self.assertContains(r, 'sandbox=""')
        self.assertNotContains(r, "<script>1")

    def test_test_email_via_view_uses_the_stores_own_sender_only(self):
        give_active_sender(self.store, "info@mybikestore.test")
        self.client.post(reverse("dashboard:notification-template-test", args=["order.created"]), {"channel": "email", "recipient": "qa@example.com"})
        self.assertEqual(FakeTransport.sent[0]["message"].from_address, "info@mybikestore.test")
        self.assertEqual(mail.outbox, [])

    def test_templates_are_isolated_between_stores(self):
        other = Store.objects.create(name="دیگر", slug="tpl-other", status=Store.Status.ACTIVE)
        self.edit(email_enabled="on", email_subject="فقط من {return_number}", email_body="b {order_number}", sms_enabled="on", sms_body="x {return_number}")
        self.assertNotEqual(ts.get_template(other, "return.approved", "email")["subject"], "فقط من {return_number}")
        self.assertFalse(NotificationTemplate.objects.filter(store=other).exists())
        self.assertEqual(ts.list_revisions(scope="store", store=other), [])

    def test_revision_history_records_actor_and_versions(self):
        for i in range(2):
            self.edit(email_enabled="on", email_subject=f"v{i} {{return_number}}", email_body="b {order_number}", sms_enabled="on", sms_body="x {return_number}")
        revs = ts.list_revisions(scope="store", store=self.store, event_key="return.approved", channel="email")
        self.assertEqual([r.version for r in revs], [2, 1])
        self.assertEqual(revs[0].actor, self.owner)

    def test_viewer_role_cannot_modify_templates(self):
        self._login_as(StoreMembership.Role.ANALYST, "502")
        r = self.edit(email_enabled="on", email_subject="x {return_number}", email_body="y {order_number}")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(NotificationTemplate.objects.exists())
