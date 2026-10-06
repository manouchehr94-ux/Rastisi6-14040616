"""Tests for the Checkpoint 4 Customer CRM foundation: Store-scoped
CustomerProfile, CustomerNote, CustomerTag — creation, permissions, and
adversarial tenant isolation."""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Vendor
from apps.core.models import AuditLogEntry
from apps.customers.models import Customer, CustomerNote, CustomerProfile, CustomerTag
from apps.dashboard.services import customer_crm_service
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"crm-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CustomerCrmTestCase(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST=HOST)
        self.store = _akhlaghi()
        self.store.admin_subdomain = "crm-test"
        self.store.save(update_fields=["admin_subdomain"])

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-crm")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-crm", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-crm")

        user = User.objects.create_user(username="09121190001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="سارا محمدی", phone="09121190001")
        self.order = Order.objects.create(
            code="DM-crm1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("400000"), payment_status=Order.PaymentStatus.PAID,
        )

        self.owner = User.objects.create_user(username="crm-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="crm-owner", password="pass12345")

    def _login_as(self, role, suffix):
        user = User.objects.create_user(username=f"crm-role-{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")


class ProfileServiceTests(CustomerCrmTestCase):
    def test_get_or_create_profile_is_idempotent(self):
        p1 = customer_crm_service.get_or_create_profile(self.store, self.customer)
        p2 = customer_crm_service.get_or_create_profile(self.store, self.customer)
        self.assertEqual(p1.pk, p2.pk)

    def test_refresh_stats_computes_from_store_scoped_orders(self):
        profile = customer_crm_service.get_or_create_profile(self.store, self.customer)
        customer_crm_service.refresh_customer_profile_stats(profile)
        profile.refresh_from_db()
        self.assertEqual(profile.order_count, 1)
        self.assertEqual(profile.total_spent, Decimal("400000"))
        self.assertIsNotNone(profile.stats_refreshed_at)

    def test_refresh_stats_ignores_other_stores_orders(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="crm-other-store")
        other_vendor = Vendor.objects.create(store=other_store, name="ف", slug="v-other-crm")
        other_shipping = ShippingMethod.objects.create(store=other_store, name="پست", slug="post-other-crm")
        other_gateway = PaymentGateway.objects.create(store=other_store, name="د", slug="gw-other-crm")
        Order.objects.create(
            code="DM-crm-other", store=other_store, customer=self.customer, vendor=other_vendor, address={},
            shipping_method=other_shipping, payment_gateway=other_gateway,
            grand_total=Decimal("9999999"), payment_status=Order.PaymentStatus.PAID,
        )
        profile = customer_crm_service.get_or_create_profile(self.store, self.customer)
        customer_crm_service.refresh_customer_profile_stats(profile)
        profile.refresh_from_db()
        self.assertEqual(profile.order_count, 1)
        self.assertEqual(profile.total_spent, Decimal("400000"))


class NoteViewTests(CustomerCrmTestCase):
    def test_owner_can_add_and_delete_note(self):
        response = self.client.post(
            reverse("dashboard:customer-note-add", args=[self.customer.pk]), {"body": "مشتری خوب است"},
        )
        self.assertEqual(response.status_code, 302)
        note = CustomerNote.objects.get(profile__customer=self.customer)
        self.assertEqual(note.body, "مشتری خوب است")
        self.assertTrue(
            AuditLogEntry.objects.filter(store=self.store, action_code="customer_note.created").exists()
        )

        response = self.client.post(
            reverse("dashboard:customer-note-delete", args=[self.customer.pk, note.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomerNote.objects.filter(pk=note.pk).exists())

    def test_content_editor_cannot_add_note(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "1")
        response = self.client.post(
            reverse("dashboard:customer-note-add", args=[self.customer.pk]), {"body": "x"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CustomerNote.objects.filter(profile__customer=self.customer).exists())

    def test_order_manager_can_add_note(self):
        self._login_as(StoreMembership.Role.ORDER_MANAGER, "2")
        response = self.client.post(
            reverse("dashboard:customer-note-add", args=[self.customer.pk]), {"body": "یادداشتِ مدیر سفارش"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomerNote.objects.filter(profile__customer=self.customer).exists())

    def test_cannot_delete_other_stores_note(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="crm-note-other-store")
        other_profile = CustomerProfile.objects.create(store=other_store, customer=self.customer)
        other_note = CustomerNote.objects.create(profile=other_profile, body="نباید قابل‌حذف باشد")
        response = self.client.post(
            reverse("dashboard:customer-note-delete", args=[self.customer.pk, other_note.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CustomerNote.objects.filter(pk=other_note.pk).exists())


class TagViewTests(CustomerCrmTestCase):
    def test_owner_can_create_tag_and_assign(self):
        response = self.client.post(
            reverse("dashboard:customer-tag-add"), {"name": "مشتریِ عمده", "code": "wholesale"},
        )
        self.assertEqual(response.status_code, 302)
        tag = CustomerTag.objects.get(store=self.store, code="wholesale")

        response = self.client.post(
            reverse("dashboard:customer-tag-toggle", args=[self.customer.pk]),
            {"tag_id": tag.pk, "action": "add"},
        )
        self.assertEqual(response.status_code, 302)
        profile = CustomerProfile.objects.get(store=self.store, customer=self.customer)
        self.assertIn(tag, profile.tags.all())

        response = self.client.post(
            reverse("dashboard:customer-tag-toggle", args=[self.customer.pk]),
            {"tag_id": tag.pk, "action": "remove"},
        )
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertNotIn(tag, profile.tags.all())

    def test_duplicate_tag_code_rejected(self):
        CustomerTag.objects.create(store=self.store, name="اول", code="dup-code")
        with self.assertRaises(customer_crm_service.CustomerCrmError):
            customer_crm_service.create_tag(self.store, name="دوم", code="dup-code")

    def test_archive_tag_keeps_existing_assignment_but_hides_from_active_list(self):
        tag = CustomerTag.objects.create(store=self.store, name="آرشیوی", code="archived-tag")
        profile = customer_crm_service.get_or_create_profile(self.store, self.customer)
        profile.tags.add(tag)
        customer_crm_service.archive_tag(self.store, tag.pk)
        tag.refresh_from_db()
        self.assertFalse(tag.is_active)
        self.assertIn(tag, profile.tags.all())

    def test_content_editor_cannot_manage_tags(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "3")
        response = self.client.post(reverse("dashboard:customer-tag-add"), {"name": "x", "code": "y"})
        self.assertEqual(response.status_code, 403)

    def test_cannot_assign_other_stores_tag(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="crm-tag-other-store")
        other_tag = CustomerTag.objects.create(store=other_store, name="خارجی", code="foreign-tag")
        with self.assertRaises(customer_crm_service.CustomerCrmError):
            customer_crm_service.bulk_add_tag(self.store, [self.customer.pk], other_tag.pk)

    def test_bulk_add_tag_ignores_customers_not_in_store(self):
        stranger_user = User.objects.create_user(username="09121190099", password="p")
        stranger = Customer.objects.create(user=stranger_user, full_name="غریبه", phone="09121190099")
        tag = CustomerTag.objects.create(store=self.store, name="ت", code="t1")
        count = customer_crm_service.bulk_add_tag(self.store, [self.customer.pk, stranger.pk], tag.pk)
        self.assertEqual(count, 1)
        self.assertFalse(CustomerProfile.objects.filter(store=self.store, customer=stranger).exists())


class StatusUpdateTests(CustomerCrmTestCase):
    def test_owner_can_set_internal_status(self):
        response = self.client.post(
            reverse("dashboard:customer-status-update", args=[self.customer.pk]),
            {"internal_status": CustomerProfile.InternalStatus.VIP},
        )
        self.assertEqual(response.status_code, 302)
        profile = CustomerProfile.objects.get(store=self.store, customer=self.customer)
        self.assertEqual(profile.internal_status, CustomerProfile.InternalStatus.VIP)

    def test_invalid_status_rejected(self):
        with self.assertRaises(customer_crm_service.CustomerCrmError):
            customer_crm_service.set_internal_status(self.store, [self.customer.pk], "not-a-real-status")


class CustomerDetailPageCrmTests(CustomerCrmTestCase):
    def test_detail_page_renders_crm_panel(self):
        response = self.client.get(reverse("dashboard:customer-detail", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "یادداشت‌های داخلی")


class CustomerBulkActionViewTests(CustomerCrmTestCase):
    def test_bulk_add_tag(self):
        tag = CustomerTag.objects.create(store=self.store, name="عمده", code="wholesale-bulk")
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "add-tag", "bulk_tag": tag.pk, "customer_ids": [self.customer.pk],
        })
        self.assertEqual(response.status_code, 302)
        profile = CustomerProfile.objects.get(store=self.store, customer=self.customer)
        self.assertIn(tag, profile.tags.all())

    def test_bulk_set_status(self):
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "set-status", "bulk_status": CustomerProfile.InternalStatus.WATCH,
            "customer_ids": [self.customer.pk],
        })
        self.assertEqual(response.status_code, 302)
        profile = CustomerProfile.objects.get(store=self.store, customer=self.customer)
        self.assertEqual(profile.internal_status, CustomerProfile.InternalStatus.WATCH)

    def test_bulk_export_selected(self):
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "export-selected", "customer_ids": [self.customer.pk],
        })
        # «خروج اطلاعات» is direct-download: the XLSX is the response, nothing is stored
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_no_selection_warns_without_crash(self):
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {"bulk_action": "set-status"})
        self.assertEqual(response.status_code, 302)

    def test_content_editor_cannot_bulk_add_tag(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "bulk1")
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "add-tag", "bulk_tag": "1", "customer_ids": [self.customer.pk],
        })
        self.assertEqual(response.status_code, 403)

    def test_foreign_customer_id_in_bulk_action_ignored(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="crm-bulk-other-store")
        other_vendor = Vendor.objects.create(store=other_store, name="ف", slug="v-bulk-other-crm")
        other_shipping = ShippingMethod.objects.create(store=other_store, name="پست", slug="post-bulk-other-crm")
        other_gateway = PaymentGateway.objects.create(store=other_store, name="د", slug="gw-bulk-other-crm")
        other_user = User.objects.create_user(username="09121190098", password="p")
        other_customer = Customer.objects.create(user=other_user, full_name="مشتریِ دیگر", phone="09121190098")
        Order.objects.create(
            code="DM-crm-bulk-other", store=other_store, customer=other_customer, vendor=other_vendor, address={},
            shipping_method=other_shipping, payment_gateway=other_gateway, grand_total=Decimal("1"),
        )
        tag = CustomerTag.objects.create(store=self.store, name="ب", code="bulk-foreign-tag")
        response = self.client.post(reverse("dashboard:customer-bulk-action"), {
            "bulk_action": "add-tag", "bulk_tag": tag.pk, "customer_ids": [other_customer.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomerProfile.objects.filter(store=self.store, customer=other_customer).exists())
