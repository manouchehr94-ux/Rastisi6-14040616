"""H2: سیاستِ واحدِ رضایتِ تبلیغاتی — رضایتِ نامعلوم = عدمِ رضایت، کانال‌های مستقل، ثبتِ منبع/زمان،
پس‌گرفتنِ رضایت بعد از صف‌شدن مانعِ ارسال می‌شود، پیام‌هایِ تراکنشی/امنیتی بی‌تأثیرند."""

import io
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.core.models import AuditLogEntry
from apps.customers.models import Customer
from apps.customers.services import auth_service, consent_service
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.services.notification_service import deliver_pending, retry_notification
from apps.stores.models import Store

User = get_user_model()
S = NotificationOutbox.Status
CS = Customer.ConsentSource
CTX = {"discount_code": "GIFT-1", "discount_amount": "۳۰٪", "discount_max": "", "discount_expires_at": "۱۴۰۵/۱/۱",
       "campaign_name": "کمپین", "occasion_name": "مناسبت", "customer_name": "سارا"}


def make_customer(phone="09120009001", **kw):
    user = User.objects.create_user(username=phone, password="x12345678")
    return Customer.objects.create(user=user, full_name="سارا", phone=phone, email=f"{phone}@example.com", **kw)


class PolicyDefaultsTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_new_customer_has_no_promotional_consent(self):
        c = make_customer()
        self.assertEqual((c.accepts_promotional_sms, c.accepts_promotional_email), (False, False))
        self.assertEqual((c.promo_sms_consent_source, c.promo_email_consent_source), ("", ""))
        self.assertFalse(consent_service.has_promotional_consent(c, "sms"))
        self.assertFalse(consent_service.has_promotional_consent(None, "sms"))
        self.assertFalse(consent_service.has_promotional_consent(c, "carrier-pigeon"))

    def test_signup_without_ticks_records_nothing_and_with_one_tick_only_that_channel(self):
        plain = auth_service.signup(full_name="الف", phone="09120009002", password="Str0ng-pass-91", store=self.store)
        self.assertEqual((plain.accepts_promotional_sms, plain.accepts_promotional_email), (False, False))
        sms_only = auth_service.signup(
            full_name="ب", phone="09120009003", password="Str0ng-pass-91", store=self.store, accepts_promotional_sms=True,
        )
        sms_only.refresh_from_db()
        self.assertEqual((sms_only.accepts_promotional_sms, sms_only.accepts_promotional_email), (True, False))
        self.assertEqual((sms_only.promo_sms_consent_source, sms_only.promo_email_consent_source), (CS.REGISTRATION, ""))
        self.assertIsNotNone(sms_only.promo_sms_consent_changed_at)
        self.assertIsNone(sms_only.promo_email_consent_changed_at)

    def test_signup_form_renders_unchecked_boxes_and_view_records_ticks(self):
        page = self.client.get(reverse("customers:account"))  # شکلِ صفحه‌ی ورود
        html = self.client.get("/").content.decode() if page.status_code != 200 else page.content.decode()
        self.assertNotIn("checked", "".join(
            part for part in html.split("<input") if "accepts_promotional" in part and "type=\"checkbox\"" in part
        ))
        response = self.client.post(reverse("customers:signup"), {
            "full_name": "ج", "phone": "09120009004", "password": "Str0ng-pass-91", "accepts_promotional_email": "on",
        })
        self.assertEqual(response.status_code, 200)
        c = Customer.objects.get(phone="09120009004")
        self.assertEqual((c.accepts_promotional_sms, c.accepts_promotional_email), (False, True))
        self.assertEqual(c.promo_email_consent_source, CS.REGISTRATION)


class AccountControlTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.customer = make_customer("09120009010")
        self.client.login(username="09120009010", password="x12345678")

    def post(self, **ticks):
        return self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "سارا", "email": "", "city": "", "birth_date": "", "prefs_submitted": "1", **ticks,
        })

    def test_channels_are_independent_and_withdrawal_is_recorded_with_source_and_time(self):
        self.post(accepts_promotional_sms="on")
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.accepts_promotional_sms, self.customer.accepts_promotional_email), (True, False))
        self.assertEqual(self.customer.promo_sms_consent_source, CS.ACCOUNT)
        granted_at = self.customer.promo_sms_consent_changed_at
        self.post(accepts_promotional_email="on")  # SMS تیک‌برداشته ⇒ پس‌گرفتن؛ ایمیل اعطا
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.accepts_promotional_sms, self.customer.accepts_promotional_email), (False, True))
        self.assertGreaterEqual(self.customer.promo_sms_consent_changed_at, granted_at)
        self.assertEqual(self.customer.promo_sms_consent_source, CS.ACCOUNT)

    def test_unchanged_submission_changes_nothing_and_missing_marker_keeps_consent(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, sms=True)
        self.customer.refresh_from_db()
        stamp = self.customer.promo_sms_consent_changed_at
        self.post(accepts_promotional_sms="on")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.promo_sms_consent_changed_at, stamp)
        self.client.post(reverse("customers:account-profile-update"), {"full_name": "سارا", "email": "", "city": "", "birth_date": ""})
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.accepts_promotional_sms)  # بدونِ prefs_submitted رضایت دست نمی‌خورد

    def test_changes_are_audited_in_the_current_store_without_personal_data(self):
        self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "سارا", "email": "", "city": "", "birth_date": "", "prefs_submitted": "1", "accepts_promotional_sms": "on",
        })
        entries = AuditLogEntry.objects.filter(action_code="customer.consent_changed")
        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertEqual(entry.store_id, self.store.pk)
        self.assertNotIn(self.customer.phone, str(entry.__dict__))
        self.assertNotIn(self.customer.email, str(entry.__dict__))


class CheckoutConsentTests(TestCase):
    """رضایت در تسویه‌حساب: فقط تیکِ صریح اعطا می‌کند؛ نزدنِ تیک رضایتِ قبلی را پس نمی‌گیرد."""

    def setUp(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor
        from apps.orders.models import PaymentGateway, ShippingMethod

        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-h2")
        cat = Category.objects.create(store=self.store, name="د", slug="cat-h2")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=cat, name="کالا", slug="p-h2", sku="H21", price=Decimal("200000"), stock=10,
        )
        ShippingMethod.objects.create(store=self.store, name="پست", slug="post-h2", cost=45_000)
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-h2")
        self.customer = make_customer("09123456780")
        self.client.login(username="09123456780", password="x12345678")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.payload = {
            "receiver_name": "علی", "phone": "09123456780", "province": "تهران", "city": "تهران",
            "postal_code": "1415873920", "full_address": "خیابان", "note": "",
        }

    def test_checkout_page_has_unchecked_consent_boxes(self):
        html = self.client.get(reverse("orders:checkout-step1")).content.decode()
        for name in ("accepts_promotional_sms", "accepts_promotional_email"):
            tag = html.split(f'name="{name}"')[1].split(">")[0]
            self.assertNotIn("checked", tag, name)

    def test_unticked_checkout_grants_nothing(self):
        self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.accepts_promotional_sms, self.customer.accepts_promotional_email), (False, False))

    def test_ticked_checkout_grants_only_ticked_channel_with_checkout_source(self):
        r = self.client.post(reverse("orders:checkout-pay"), dict(self.payload, accepts_promotional_sms="on"))
        self.assertIn("HX-Redirect", r.headers)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.accepts_promotional_sms, self.customer.accepts_promotional_email), (True, False))
        self.assertEqual(self.customer.promo_sms_consent_source, CS.CHECKOUT)

    def test_unticked_checkout_never_withdraws_existing_consent(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, sms=True, email=True)
        self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.accepts_promotional_sms, self.customer.accepts_promotional_email), (True, True))
        self.assertEqual(self.customer.promo_sms_consent_source, CS.ACCOUNT)


class DispatchAndDeliveryEnforcementTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.customer = make_customer("09120009020")

    def dispatch(self, key="coupon.issued", **kw):
        return dispatch_event(key, store=self.store, customer=self.customer, context=CTX, **kw)

    def test_unknown_consent_is_not_granted_for_either_channel(self):
        rows = self.dispatch()
        self.assertEqual({r.status for r in rows}, {S.SKIPPED})
        self.assertEqual({r.skip_reason for r in rows}, {"no_promotional_consent"})

    def test_channels_are_evaluated_independently(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, email=True)
        by = {r.channel: r for r in self.dispatch()}
        self.assertEqual((by["email"].status, by["sms"].status), (S.PENDING, S.SKIPPED))

    def test_withdrawal_after_queueing_blocks_delivery_without_calling_providers(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, sms=True, email=True)
        rows = self.dispatch()
        self.assertEqual({r.status for r in rows}, {S.PENDING})
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, email=False)  # فقط ایمیل پس گرفته شد
        with patch("apps.sms.services.sms_service.send_raw_sms") as sms_provider:
            sms_provider.return_value.status = "sent"
            sms_provider.return_value.provider = "x"
            sms_provider.return_value.provider_ref_id = "1"
            sms_provider.return_value.Status.SENT = "sent"
            result = deliver_pending()
        by = {r.channel: NotificationOutbox.objects.get(pk=r.pk) for r in rows}
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual((by["email"].status, by["email"].skip_reason, by["email"].attempts), (S.SKIPPED, "consent_withdrawn", 0))
        self.assertEqual(by["sms"].status, S.SENT)  # رضایتِ پیامک پابرجاست
        self.assertEqual(result["skipped"], 1)

    def test_manual_retry_of_failed_promotional_row_respects_later_withdrawal(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, email=True)
        (row,) = [r for r in self.dispatch() if r.channel == "email"]
        NotificationOutbox.objects.filter(pk=row.pk).update(status=S.FAILED, attempts=1)
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, email=False)
        row.refresh_from_db()
        retry_notification(row)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, "consent_withdrawn"))
        self.assertEqual(len(mail.outbox), 0)

    def test_transactional_and_security_messages_do_not_need_promotional_consent(self):
        ctx = {"order_number": "DM-1", "order_total": "1", "order_status": "x", "order_url": "", "customer_name": "س",
               "return_number": "R1", "reason": ""}
        rows = dispatch_event("return.approved", store=self.store, customer=self.customer, context=ctx)
        self.assertEqual([r.status for r in rows], [S.PENDING, S.PENDING])
        with patch("apps.sms.services.sms_service.send_raw_sms") as sms_provider:
            sms_provider.return_value.status = "sent"
            sms_provider.return_value.Status.SENT = "sent"
            sms_provider.return_value.provider = ""
            sms_provider.return_value.provider_ref_id = ""
            result = deliver_pending()
        self.assertEqual((result["sent"], result["skipped"]), (2, 0))
        security = dispatch_event(
            "account.sensitive_changed", store=self.store, customer=self.customer,
            context={"customer_name": "س", "changed_field": "ایمیل"},
        )
        self.assertTrue(all(r.status == S.PENDING and not r.is_promotional for r in security))

    def test_duplicate_dispatch_with_same_key_creates_no_extra_rows(self):
        consent_service.set_promotional_consent(self.customer, source=CS.ACCOUNT, sms=True, email=True)
        first = self.dispatch(dedupe_key="campaign-1:customer")
        again = self.dispatch(dedupe_key="campaign-1:customer")
        self.assertEqual((len(first), len(again)), (2, 0))
        self.assertEqual(NotificationOutbox.objects.filter(event_key="coupon.issued").count(), 2)

    def test_test_sends_are_not_gated_by_customer_consent(self):
        rows = dispatch_event("coupon.issued", store=self.store, customer=None, context=CTX, is_test=True,
                              test_recipient="qa@example.com", channels=["email"])
        deliver_pending()
        rows[0].refresh_from_db()
        self.assertEqual(rows[0].status, S.SENT)


class ConsentIsPerCustomerNotPerStoreTests(TestCase):
    def test_audit_trail_is_scoped_to_the_store_where_the_change_happened(self):
        a, b = Store.objects.get(slug="akhlaghi"), Store.objects.create(name="دوم", slug="second-h2", status=Store.Status.ACTIVE)
        c = make_customer("09120009030")
        consent_service.set_promotional_consent(c, source=CS.ACCOUNT, sms=True, store=a)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="customer.consent_changed", store=a).count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="customer.consent_changed", store=b).count(), 0)


class OperatorCommandTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.known = make_customer("09120009040")
        self.other = make_customer("09120009041")
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as fh:
            fh.write("phone\n09120009040\n+98912000-bad\n09999999999\n")
        self.addCleanup(os.unlink, self.path)

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("promotional_consent", *args, stdout=out)
        return out.getvalue()

    def test_import_is_dry_run_by_default_and_never_touches_unlisted_customers(self):
        out = self.run_cmd("import", "--file", self.path, "--channel", "sms", "--evidence", "form-123")
        self.assertIn("DRY-RUN", out)
        self.known.refresh_from_db()
        self.assertFalse(self.known.accepts_promotional_sms)

    def test_apply_grants_only_the_listed_channel_and_records_import_source_and_audit(self):
        out = self.run_cmd("import", "--file", self.path, "--channel", "sms", "--evidence", "form-123", "--store", self.store.slug, "--apply")
        self.assertIn("granted=1", out)
        self.known.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.known.accepts_promotional_sms, self.known.accepts_promotional_email, self.known.promo_sms_consent_source), (True, False, CS.IMPORT))
        self.assertFalse(self.other.accepts_promotional_sms)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="customer.consent_changed", store=self.store).count(), 1)

    def test_report_is_read_only_and_counts_by_source(self):
        before = Customer.objects.filter(accepts_promotional_sms=True).count()
        out = self.run_cmd("report")
        self.assertIn("sms", out)
        self.assertEqual(Customer.objects.filter(accepts_promotional_sms=True).count(), before)


class BackfillMigrationTests(TransactionTestCase):
    """0006 (schema) → 0007 (backfill): قدیمیِ True بی‌مدرک ⇒ False/legacy_unverified؛ False ⇒ انصرافِ صریح؛ idempotent؛ برگشت‌پذیرِ داده."""

    migrate_from = [("customers", "0006_promotional_consent_policy")]
    migrate_to = [("customers", "0007_backfill_promotional_consent")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        U, C = apps.get_model("auth", "User"), apps.get_model("customers", "Customer")
        def mk(phone, sms, email):
            return C.objects.create(user=U.objects.create(username=phone), full_name="x", phone=phone,
                                    accepts_promotional_sms=sms, accepts_promotional_email=email)
        self.rows = {"both_true": mk("09130000001", True, True), "sms_only": mk("09130000002", True, False),
                     "opted_out": mk("09130000003", False, False)}

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def fields(self, pk):
        c = Customer.objects.get(pk=pk)
        return (c.accepts_promotional_sms, c.promo_sms_consent_source, c.accepts_promotional_email, c.promo_email_consent_source)

    def test_forward_backfill_is_conservative_and_idempotent_and_reversible(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.assertEqual(self.fields(self.rows["both_true"].pk), (False, "legacy_unverified", False, "legacy_unverified"))
        self.assertEqual(self.fields(self.rows["sms_only"].pk), (False, "legacy_unverified", False, "legacy_opt_out"))
        self.assertEqual(self.fields(self.rows["opted_out"].pk), (False, "legacy_opt_out", False, "legacy_opt_out"))
        # هیچ ردیفی حذف نشد و هیچ مشتری رضایتِ فعال ندارد
        self.assertEqual(Customer.objects.count(), 3)
        self.assertEqual(Customer.objects.filter(accepts_promotional_sms=True).count(), 0)
        # اجرایِ دوباره‌ی تابعِ backfill تغییری نمی‌دهد (فقط ردیف‌هایِ بدونِ منبع)
        from importlib import import_module

        import_module("apps.customers.migrations.0007_backfill_promotional_consent").backfill(
            executor.loader.project_state(self.migrate_to).apps, None,
        )
        self.assertEqual(self.fields(self.rows["sms_only"].pk), (False, "legacy_unverified", False, "legacy_opt_out"))
        # رضایتی که پس از سیاستِ جدید ثبت شده، با برگشت دست نمی‌خورد
        Customer.objects.filter(pk=self.rows["opted_out"].pk).update(
            accepts_promotional_sms=True, promo_sms_consent_source="account",
        )
        MigrationExecutor(connection).migrate(self.migrate_from)
        self.assertEqual(self.fields(self.rows["both_true"].pk), (True, "", True, ""))
        self.assertEqual(self.fields(self.rows["opted_out"].pk)[:2], (True, "account"))
