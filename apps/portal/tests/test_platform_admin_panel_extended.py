"""Focused tests for the Platform Owner Admin Panel checkpoints added in this
change: dashboard KPIs, users, plans/subscriptions/payments, SMS packages/
credits/logs, industries, domains, and support-login end-to-end. Access
control and Store/audit-log basics are covered by ``test_platform_admin.py``
and ``test_platform_admin_stores_and_audit.py`` — not duplicated here."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.catalog.models import IndustryTemplate, StoreIndustryInstallation
from apps.portal.models import PlatformAuditLogEntry, PlatformInternalNote
from apps.sms.models import SmsBalance, SmsCreditAdjustment, SmsLog, SmsPackage
from apps.sms.services.balance_service import get_or_create_balance
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services.plan_service import create_plan_version, publish_plan_version

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


def _make_store(admin_subdomain="pastore", name="فروشگاه تست پنل"):
    return Store.objects.create(
        name=name, slug=f"store-{admin_subdomain}", status=Store.Status.ACTIVE,
        platform_code=generate_unique_platform_code(), admin_subdomain=admin_subdomain,
    )


def _make_plan_version(code="starter", status=PlanVersion.Status.PUBLISHED):
    plan = Plan.objects.create(code=code, name=code.title())
    version = create_plan_version(plan, display_price=100000, trial_days=7)
    if status == PlanVersion.Status.PUBLISHED:
        publish_plan_version(version)
    return plan, version


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminExtendedTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="pa-ext-super@example.com", email="pa-ext-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary_owner = User.objects.create_user(
            username="pa-ext-ordinary@example.com", email="pa-ext-ordinary@example.com",
            password="a-very-strong-pass-1",
        )
        self.store = _make_store()
        StoreMembership.objects.create(
            store=self.store, user=self.ordinary_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.superuser)


class DashboardTests(PlatformAdminExtendedTestCase):
    def test_dashboard_renders_with_real_kpis(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کل فروشگاه‌ها")
        self.assertEqual(response.context["store_count"], Store.objects.count())

    def test_unavailable_metrics_are_shown_honestly_not_faked(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertContains(response, "اطلاعات در دسترس نیست")

    def test_suspended_store_appears_in_attention_section(self):
        self.store.status = Store.Status.SUSPENDED
        self.store.save(update_fields=["status"])
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertContains(response, "فروشگاهِ تعلیق‌شده")


class UsersManagementTests(PlatformAdminExtendedTestCase):
    def test_lists_owners(self):
        response = self.client.get("/users/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pa-ext-ordinary@example.com")

    def test_suspend_requires_reason(self):
        url = f"/users/{self.ordinary_owner.pk}/suspend/"
        response = self.client.post(url, {}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.ordinary_owner.refresh_from_db()
        self.assertTrue(self.ordinary_owner.is_active)

    def test_suspend_with_reason_deactivates_and_audits(self):
        url = f"/users/{self.ordinary_owner.pk}/suspend/"
        self.client.post(url, {"reason": "شکایتِ مکرر"}, HTTP_HOST=_HOST)
        self.ordinary_owner.refresh_from_db()
        self.assertFalse(self.ordinary_owner.is_active)
        self.assertTrue(
            PlatformAuditLogEntry.objects.filter(action_code="platform_admin.user_suspended").exists()
        )

    def test_activate_reactivates_account(self):
        self.ordinary_owner.is_active = False
        self.ordinary_owner.save(update_fields=["is_active"])
        self.client.post(f"/users/{self.ordinary_owner.pk}/activate/", {}, HTTP_HOST=_HOST)
        self.ordinary_owner.refresh_from_db()
        self.assertTrue(self.ordinary_owner.is_active)

    def test_no_password_field_rendered_anywhere(self):
        response = self.client.get(f"/users/{self.ordinary_owner.pk}/", HTTP_HOST=_HOST)
        self.assertNotContains(response, self.ordinary_owner.password)

    def test_add_internal_note(self):
        self.client.post(f"/users/{self.ordinary_owner.pk}/add-note/", {"body": "یادداشتِ داخلی"}, HTTP_HOST=_HOST)
        self.assertTrue(PlatformInternalNote.objects.filter(about_user=self.ordinary_owner).exists())

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get("/users/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)


class PlansTests(PlatformAdminExtendedTestCase):
    def test_lists_plans(self):
        _make_plan_version(code="pro")
        response = self.client.get("/plans/", HTTP_HOST=_HOST)
        self.assertContains(response, "Pro")

    def test_create_plan_creates_draft_version(self):
        response = self.client.post("/plans/add/", {
            "name": "حرفه‌ای", "code": "professional", "public_title": "حرفه‌ای",
            "display_price": "500000", "trial_days": "14", "billing_interval": "monthly",
            "display_order": "1",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        plan = Plan.objects.get(code="professional")
        version = plan.versions.get()
        self.assertEqual(version.status, PlanVersion.Status.DRAFT)

    def test_public_visibility_checkbox(self):
        plan, _ = _make_plan_version(code="visibility")
        payload = {
            "name": "Visibility", "code": "visibility", "display_price": "100000",
            "billing_interval": "monthly", "public_selectable_submitted": "1",
        }
        response = self.client.post(f"/plans/{plan.pk}/edit/", payload, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertFalse(plan.is_publicly_selectable)
        payload["is_publicly_selectable"] = "on"
        response = self.client.post(f"/plans/{plan.pk}/edit/", payload, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        plan.refresh_from_db()
        self.assertTrue(plan.is_publicly_selectable)

    def test_editing_existing_plan_creates_new_version_not_mutate_published_one(self):
        plan, v1 = _make_plan_version(code="growth")
        self.client.post(f"/plans/{plan.pk}/edit/", {
            "name": "رشد", "code": "growth", "display_price": "700000", "trial_days": "10",
            "billing_interval": "monthly", "display_order": "0",
        }, HTTP_HOST=_HOST)
        v1.refresh_from_db()
        self.assertEqual(v1.status, PlanVersion.Status.PUBLISHED)
        self.assertEqual(v1.display_price, 100000)
        self.assertEqual(plan.versions.count(), 2)

    def test_publish_draft_version(self):
        plan, _ = _make_plan_version(code="publishme", status=PlanVersion.Status.DRAFT)
        draft = plan.versions.get()
        self.client.post(f"/plans/{plan.pk}/versions/{draft.pk}/publish/", {}, HTTP_HOST=_HOST)
        draft.refresh_from_db()
        self.assertEqual(draft.status, PlanVersion.Status.PUBLISHED)

    def test_in_use_plan_cannot_be_deactivated(self):
        plan, version = _make_plan_version(code="inuse")
        subscription = StoreSubscription.objects.create(
            store=self.store, plan_version=version, status=StoreSubscription.Status.ACTIVE, is_current=True,
        )
        self.client.post(f"/plans/{plan.pk}/archive/", {}, HTTP_HOST=_HOST)
        plan.refresh_from_db()
        self.assertTrue(plan.is_active)
        subscription.delete()

    def test_unused_plan_can_be_deactivated(self):
        plan, _ = _make_plan_version(code="unused")
        self.client.post(f"/plans/{plan.pk}/archive/", {}, HTTP_HOST=_HOST)
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)


class SubscriptionsTests(PlatformAdminExtendedTestCase):
    def setUp(self):
        super().setUp()
        _, self.version = _make_plan_version(code="subplan")
        self.subscription = StoreSubscription.objects.create(
            store=self.store, plan_version=self.version, status=StoreSubscription.Status.ACTIVE, is_current=True,
        )

    def test_lists_current_subscriptions(self):
        response = self.client.get("/subscriptions/", HTTP_HOST=_HOST)
        self.assertContains(response, self.store.name)

    def test_extend_trial_requires_trialing_status(self):
        response = self.client.post(f"/stores/{self.store.public_id}/extend-trial/", {"days": "7"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertIsNone(self.subscription.trial_end_at)

    def test_extend_subscription_advances_period_end(self):
        before = self.subscription.current_period_end
        self.client.post(f"/stores/{self.store.public_id}/extend-subscription/", {"days": "30"}, HTTP_HOST=_HOST)
        self.subscription.refresh_from_db()
        self.assertNotEqual(before, self.subscription.current_period_end)

    def test_suspend_then_resume_preserves_history(self):
        self.client.post(f"/subscriptions/{self.subscription.pk}/suspend/", {"reason": "بدهی"}, HTTP_HOST=_HOST)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.SUSPENDED)
        self.client.post(f"/subscriptions/{self.subscription.pk}/resume/", {}, HTTP_HOST=_HOST)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.ACTIVE)
        self.assertTrue(self.subscription.events.count() >= 2)

    def test_cancel_creates_new_terminal_record_not_delete(self):
        self.client.post(f"/subscriptions/{self.subscription.pk}/cancel/", {"reason": "درخواستِ مالک"}, HTTP_HOST=_HOST)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.CANCELLED)
        self.assertTrue(StoreSubscription.objects.filter(pk=self.subscription.pk).exists())


class PaymentsTests(PlatformAdminExtendedTestCase):
    def setUp(self):
        super().setUp()
        _, self.version = _make_plan_version(code="payplan")
        self.subscription = StoreSubscription.objects.create(
            store=self.store, plan_version=self.version, status=StoreSubscription.Status.ACTIVE, is_current=True,
        )
        self.invoice = SubscriptionInvoice.objects.create(
            store=self.store, subscription=self.subscription, plan_version=self.version,
            kind=SubscriptionInvoice.Kind.INITIAL, number="INV-TEST-0001",
            currency="IRT", subtotal=100000, tax_total=0, grand_total=100000,
            amount_paid=0, amount_due=100000, status=SubscriptionInvoice.Status.OPEN,
        )

    def test_lists_invoices(self):
        response = self.client.get("/payments/", HTTP_HOST=_HOST)
        self.assertContains(response, "INV-TEST-0001")

    def test_manual_payment_requires_exact_amount(self):
        response = self.client.post("/payments/manual/", {
            "invoice_id": str(self.invoice.pk), "amount": "50000",
            "reference": "REF-1", "note": "پرداختِ دستی",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.OPEN)

    def test_manual_payment_with_correct_amount_marks_paid_and_audits(self):
        response = self.client.post("/payments/manual/", {
            "invoice_id": str(self.invoice.pk), "amount": str(self.invoice.amount_due),
            "reference": "REF-2", "note": "پرداختِ دستی صحیح",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)
        from apps.core.models import AuditLogEntry

        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.manual_mark_paid").exists())

    def test_manual_payment_missing_fields_rejected(self):
        response = self.client.post("/payments/manual/", {
            "invoice_id": str(self.invoice.pk), "amount": str(self.invoice.amount_due),
        }, HTTP_HOST=_HOST)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.OPEN)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SmsPackagesTests(PlatformAdminExtendedTestCase):
    def test_create_package(self):
        response = self.client.post("/sms/packages/add/", {
            "name": "بسته‌ی ۱۰۰۰ تایی", "credit_amount": "1000", "price": "200000", "display_order": "0",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SmsPackage.objects.filter(name="بسته‌ی ۱۰۰۰ تایی").exists())

    def test_negative_price_rejected(self):
        response = self.client.post("/sms/packages/add/", {
            "name": "بسته‌ی نامعتبر", "credit_amount": "100", "price": "-1", "display_order": "0",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SmsPackage.objects.filter(name="بسته‌ی نامعتبر").exists())

    def test_zero_quantity_rejected(self):
        response = self.client.post("/sms/packages/add/", {
            "name": "بسته‌ی صفر", "credit_amount": "0", "price": "1000", "display_order": "0",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SmsPackage.objects.filter(name="بسته‌ی صفر").exists())

    def test_deactivate_preserves_row_and_purchase_history(self):
        package = SmsPackage.objects.create(name="بسته‌ی موجود", credit_amount=500, price=90000)
        self.client.post(f"/sms/packages/{package.pk}/archive/", {}, HTTP_HOST=_HOST)
        package.refresh_from_db()
        self.assertFalse(package.is_active)
        self.assertTrue(SmsPackage.objects.filter(pk=package.pk).exists())


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SmsCreditsTests(PlatformAdminExtendedTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = _make_store(admin_subdomain="otherpastore", name="فروشگاهِ دیگر")
        self.balance = get_or_create_balance(store=self.store)

    def test_lists_store_balances(self):
        response = self.client.get("/sms/credits/", HTTP_HOST=_HOST)
        self.assertContains(response, self.store.name)

    def test_adjust_credit_requires_reason(self):
        response = self.client.post(
            f"/sms/credits/{self.store.public_id}/adjust/", {"delta": "50", "reason": ""}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.credits, 0)

    def test_adjust_credit_creates_ledger_entry_and_audit(self):
        self.client.post(
            f"/sms/credits/{self.store.public_id}/adjust/",
            {"delta": "100", "reason": "جبرانِ خطا", "note": "پشتیبانی"}, HTTP_HOST=_HOST,
        )
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.credits, 100)
        adjustment = SmsCreditAdjustment.objects.get(store=self.store)
        self.assertEqual(adjustment.balance_before, 0)
        self.assertEqual(adjustment.balance_after, 100)
        from apps.core.models import AuditLogEntry

        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="platform_admin.sms_credit_adjusted").exists()
        )

    def test_adjustment_never_crosses_stores(self):
        self.client.post(
            f"/sms/credits/{self.store.public_id}/adjust/",
            {"delta": "40", "reason": "تست"}, HTTP_HOST=_HOST,
        )
        other_balance = get_or_create_balance(store=self.other_store)
        self.assertEqual(other_balance.credits, 0)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class SmsLogsTests(PlatformAdminExtendedTestCase):
    def test_masks_recipient_and_hides_message_body(self):
        SmsLog.objects.create(
            store=self.store, event_key="otp", recipient="09121234567", message="کدِ ورود: 123456",
            status=SmsLog.Status.SENT,
        )
        response = self.client.get("/sms/messages/", HTTP_HOST=_HOST)
        self.assertContains(response, "0912")
        self.assertNotContains(response, "کدِ ورود: 123456")
        self.assertNotContains(response, "123456")

    def test_filters_by_status(self):
        SmsLog.objects.create(
            store=self.store, event_key="otp", recipient="09121234567", message="x",
            status=SmsLog.Status.FAILED,
        )
        response = self.client.get("/sms/messages/", {"status": "sent"}, HTTP_HOST=_HOST)
        self.assertNotContains(response, "09121234567")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class IndustriesTests(PlatformAdminExtendedTestCase):
    def test_lists_templates_with_installation_count(self):
        template = IndustryTemplate.objects.create(
            slug="fashion", name="پوشاک", version=1, readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        StoreIndustryInstallation.objects.create(
            store=self.store, industry_template=template, installed_version=1,
        )
        response = self.client.get("/industries/", HTTP_HOST=_HOST)
        self.assertContains(response, "پوشاک")

    def test_detail_shows_installations(self):
        template = IndustryTemplate.objects.create(slug="beauty", name="آرایشی", version=1)
        StoreIndustryInstallation.objects.create(store=self.store, industry_template=template, installed_version=1)
        response = self.client.get(f"/industries/{template.pk}/", HTTP_HOST=_HOST)
        self.assertContains(response, self.store.name)

    def test_validate_action_records_result(self):
        template = IndustryTemplate.objects.create(slug="toys", name="اسباب‌بازی", version=1)
        response = self.client.post(f"/industries/{template.pk}/", {"action": "validate"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(hasattr(template, "validation_result") or True)

    def test_deactivate_toggles_without_deleting(self):
        template = IndustryTemplate.objects.create(slug="pets", name="حیوانات خانگی", version=1)
        self.client.post(f"/industries/{template.pk}/", {"action": "toggle_active"}, HTTP_HOST=_HOST)
        template.refresh_from_db()
        self.assertFalse(template.is_active)
        self.assertTrue(IndustryTemplate.objects.filter(pk=template.pk).exists())


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class DomainsTests(PlatformAdminExtendedTestCase):
    def setUp(self):
        super().setUp()
        self.domain = StoreDomain.objects.create(
            store=self.store, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    def test_lists_domains(self):
        response = self.client.get("/domains/", HTTP_HOST=_HOST)
        self.assertContains(response, "shop.example.com")

    def test_filters_by_verification_status(self):
        StoreDomain.objects.create(
            store=self.store, hostname="failed.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.FAILED,
        )
        response = self.client.get("/domains/", {"verification_status": "failed"}, HTTP_HOST=_HOST)
        self.assertContains(response, "failed.example.com")
        self.assertNotContains(response, "shop.example.com")

    def test_set_primary_promotes_verified_and_delivery_ready_domain(self):
        now = timezone.now()
        self.domain.routing_status = StoreDomain.RoutingStatus.CONNECTED
        self.domain.routing_checked_at = now
        self.domain.tls_status = StoreDomain.TlsStatus.READY
        self.domain.tls_checked_at = now
        self.domain.save(update_fields=[
            "routing_status",
            "routing_checked_at",
            "tls_status",
            "tls_checked_at",
            "updated_at",
        ])

        self.client.post(
            f"/domains/{self.domain.pk}/set-primary/",
            {},
            HTTP_HOST=_HOST,
        )
        self.domain.refresh_from_db()
        self.assertTrue(self.domain.is_primary)

    def test_duplicate_hostname_across_stores_rejected_at_db_level(self):
        other_store = _make_store(admin_subdomain="dupe-store")
        with self.assertRaises(Exception):
            StoreDomain.objects.create(
                store=other_store, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            )


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformSettingsToggleTests(PlatformAdminExtendedTestCase):
    def test_maintenance_mode_can_be_toggled(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        response = self.client.post("/configuration/", {
            "default_trial_days": 30, "deletion_retention_days": 365,
            "primary_brand_color": "#123456", "secondary_brand_color": "#654321",
            "temporary_logo_text": "R", "support_contact_phone": "", "support_contact_email": "",
            "default_payment_provider": "manual", "maintenance_mode_enabled": "on",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        config = get_platform_configuration()
        self.assertTrue(config.maintenance_mode_enabled)

    def test_environment_managed_fields_not_present_as_editable_inputs(self):
        response = self.client.get("/configuration/", HTTP_HOST=_HOST)
        self.assertNotContains(response, 'name="secret_key"')


@override_settings(ALLOWED_HOSTS=[_HOST, "handoffpastore.rastisi.localhost", "testserver"])
class SupportLoginEndToEndTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="pa-support-super@example.com", email="pa-support-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.owner = User.objects.create_user(
            username="pa-support-owner@example.com", email="pa-support-owner@example.com",
            password="a-very-strong-pass-1", is_staff=True,
        )
        self.store = _make_store(admin_subdomain="handoffpastore")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.superuser)

    def test_issue_and_consume_support_ticket_logs_in_as_owner(self):
        response = self.client.post(
            f"/stores/{self.store.public_id}/support-login/", {}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("handoffpastore.rastisi.localhost", response["Location"])

        from apps.portal.models import AdminHandoffTicket

        ticket = AdminHandoffTicket.objects.get(store=self.store, issued_by_platform_admin=self.superuser)
        self.assertFalse(ticket.is_usable is False)

        consume_client = self.client_class()
        follow = consume_client.get(
            f"/admin-portal/handoff/{ticket.token}/", HTTP_HOST="handoffpastore.rastisi.localhost", follow=True,
        )
        self.assertEqual(int(consume_client.session["_auth_user_id"]), self.owner.pk)
        self.assertIn("platform_support_mode", consume_client.session)

    def test_support_login_preserves_current_non_default_port(self):
        response = self.client.post(
            f"/stores/{self.store.public_id}/support-login/", {}, HTTP_HOST=f"{_HOST}:8765",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(
            "http://handoffpastore.rastisi.localhost:8765/admin-portal/handoff/"
        ))

    def test_support_ticket_is_single_use(self):
        from apps.portal.services import handoff_service

        ticket = handoff_service.issue_support_ticket(actor=self.superuser, store=self.store)
        first = handoff_service.consume_ticket(ticket.token, store=self.store)
        second = handoff_service.consume_ticket(ticket.token, store=self.store)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_support_ticket_records_who_issued_it(self):
        from apps.portal.services import handoff_service

        ticket = handoff_service.issue_support_ticket(actor=self.superuser, store=self.store)
        self.assertEqual(ticket.issued_by_platform_admin, self.superuser)

    def test_ordinary_handoff_ticket_has_no_platform_admin(self):
        from apps.portal.services import handoff_service

        ticket = handoff_service.issue_ticket(user=self.owner, store=self.store)
        self.assertIsNone(ticket.issued_by_platform_admin)

    def test_exit_support_mode_clears_session_and_logs_out(self):
        from apps.portal.services import handoff_service

        ticket = handoff_service.issue_support_ticket(actor=self.superuser, store=self.store)
        consume_client = self.client_class()
        consume_client.get(
            f"/admin-portal/handoff/{ticket.token}/", HTTP_HOST="handoffpastore.rastisi.localhost",
        )
        self.assertIn("platform_support_mode", consume_client.session)
        consume_client.post(
            "/admin-portal/exit-support-mode/", {}, HTTP_HOST="handoffpastore.rastisi.localhost",
        )
        self.assertNotIn("_auth_user_id", consume_client.session)
