"""HTTP-level tests proving ``permission_required`` is actually wired onto
the merchant-admin views listed in the Phase 1B request: products,
categories, variants, orders (view vs. status-change), customers, reports,
settings (general/payment/sms), and content management.

A member with the wrong role for an action gets an actual 403 (rendered via
``dashboard/403.html``), never a silent 200 — this is what distinguishes
these tests from ``test_membership_authorization.py`` (which covers "is this
user a member of this Store at all") and ``test_authorization.py`` (which
covers the permission registry in isolation, without HTTP).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services.variant_service import create_variant, set_product_type
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _user_with_role(store, username, role):
    user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
    StoreMembership.objects.create(
        store=store, user=user, role=role,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )
    return user


class PermissionEnforcementTestCase(TestCase):
    """Shared fixture: one Store, one of each resource, one user per role."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-perm")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="cat-perm")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="prod-perm",
            sku="SKU-PERM1", price=Decimal("100000"), stock=5,
        )
        set_product_type(self.product, Product.ProductType.VARIABLE)
        self.variant = create_variant(self.product, attribute="رنگ", value="قرمز")

        customer_user = User.objects.create_user(username="perm-customer-login", password="pass12345")
        self.customer = Customer.objects.create(user=customer_user, full_name="مشتری تست", phone="09121170001")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-perm", cost=Decimal("30000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-perm")
        self.order = Order.objects.create(
            code="DM-PERM1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
        )

        self.owner = _user_with_role(self.store, "perm-owner", StoreMembership.Role.OWNER)
        self.administrator = _user_with_role(self.store, "perm-admin", StoreMembership.Role.ADMINISTRATOR)
        self.catalog_manager = _user_with_role(self.store, "perm-catalog", StoreMembership.Role.CATALOG_MANAGER)
        self.order_manager = _user_with_role(self.store, "perm-order", StoreMembership.Role.ORDER_MANAGER)
        self.content_editor = _user_with_role(self.store, "perm-content", StoreMembership.Role.CONTENT_EDITOR)
        self.analyst = _user_with_role(self.store, "perm-analyst", StoreMembership.Role.ANALYST)

    def _login(self, user):
        self.client.logout()
        self.client.force_login(user)


class ProductPermissionTests(PermissionEnforcementTestCase):
    def test_catalog_manager_can_view_products(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 200)

    def test_catalog_manager_can_create_product_form(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:product-add"), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_catalog_manager_can_delete_product(self):
        self._login(self.catalog_manager)
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertNotEqual(response.status_code, 403)

    def test_order_manager_cannot_view_products(self):
        self._login(self.order_manager)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(response.status_code, 403)

    def test_content_editor_cannot_delete_product(self):
        self._login(self.content_editor)
        response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_analyst_can_view_but_not_delete_product(self):
        self._login(self.analyst)
        view_response = self.client.get(reverse("dashboard:product-list"))
        self.assertEqual(view_response.status_code, 200)
        delete_response = self.client.post(reverse("dashboard:product-delete", args=[self.product.pk]))
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_owner_can_do_everything(self):
        self._login(self.owner)
        self.assertEqual(self.client.get(reverse("dashboard:product-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:product-add"), follow=True).status_code, 200)


class CategoryPermissionTests(PermissionEnforcementTestCase):
    def test_catalog_manager_can_manage_categories(self):
        self._login(self.catalog_manager)
        self.assertEqual(self.client.get(reverse("dashboard:category-list")).status_code, 200)

    def test_analyst_cannot_manage_categories(self):
        self._login(self.analyst)
        self.assertEqual(self.client.get(reverse("dashboard:category-list")).status_code, 403)

    def test_content_editor_cannot_manage_categories(self):
        self._login(self.content_editor)
        self.assertEqual(self.client.get(reverse("dashboard:category-list")).status_code, 403)


class VariantPermissionTests(PermissionEnforcementTestCase):
    def test_catalog_manager_can_view_variants(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

    def test_order_manager_cannot_view_variants(self):
        self._login(self.order_manager)
        response = self.client.get(reverse("dashboard:product-variants", args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)


class OrderPermissionTests(PermissionEnforcementTestCase):
    def test_order_manager_can_view_orders(self):
        self._login(self.order_manager)
        self.assertEqual(self.client.get(reverse("dashboard:order-list")).status_code, 200)

    def test_catalog_manager_cannot_view_orders(self):
        self._login(self.catalog_manager)
        self.assertEqual(self.client.get(reverse("dashboard:order-list")).status_code, 403)

    def test_analyst_can_view_order_detail_but_not_change_status(self):
        self._login(self.analyst)
        detail_url = reverse("dashboard:order-detail", args=[self.order.code])
        self.assertEqual(self.client.get(detail_url).status_code, 200)

        response = self.client.post(detail_url, {"status": Order.Status.PROCESSING, "tracking_code": ""})
        self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, Order.Status.PROCESSING)

    def test_order_manager_can_change_order_status(self):
        self._login(self.order_manager)
        detail_url = reverse("dashboard:order-detail", args=[self.order.code])
        response = self.client.post(detail_url, {"status": Order.Status.PROCESSING, "tracking_code": ""})
        self.assertRedirects(response, detail_url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PROCESSING)


class CustomerPermissionTests(PermissionEnforcementTestCase):
    def test_order_manager_can_view_customers(self):
        self._login(self.order_manager)
        self.assertEqual(self.client.get(reverse("dashboard:customer-list")).status_code, 200)

    def test_content_editor_cannot_view_customers(self):
        self._login(self.content_editor)
        self.assertEqual(self.client.get(reverse("dashboard:customer-list")).status_code, 403)

    def test_analyst_can_view_customers(self):
        self._login(self.analyst)
        self.assertEqual(self.client.get(reverse("dashboard:customer-list")).status_code, 200)


class ReportsPermissionTests(PermissionEnforcementTestCase):
    def test_analyst_can_view_reports(self):
        self._login(self.analyst)
        self.assertEqual(self.client.get(reverse("dashboard:report-list")).status_code, 200)

    def test_content_editor_cannot_view_reports(self):
        self._login(self.content_editor)
        self.assertEqual(self.client.get(reverse("dashboard:report-list")).status_code, 403)


class SettingsPermissionTests(PermissionEnforcementTestCase):
    def test_administrator_can_view_settings(self):
        self._login(self.administrator)
        self.assertEqual(self.client.get(reverse("dashboard:settings")).status_code, 200)

    def test_catalog_manager_cannot_view_settings(self):
        self._login(self.catalog_manager)
        self.assertEqual(self.client.get(reverse("dashboard:settings")).status_code, 403)

    def test_order_manager_cannot_toggle_payment_gateway(self):
        self._login(self.order_manager)
        response = self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertEqual(response.status_code, 403)

    def test_administrator_can_toggle_payment_gateway(self):
        self._login(self.administrator)
        response = self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertNotEqual(response.status_code, 403)

    def test_catalog_manager_cannot_manage_sms_settings(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:sms-log-list"))
        self.assertEqual(response.status_code, 403)


class ContentPermissionTests(PermissionEnforcementTestCase):
    def test_content_editor_can_manage_pages(self):
        self._login(self.content_editor)
        self.assertEqual(self.client.get(reverse("dashboard:page-list")).status_code, 200)

    def test_catalog_manager_cannot_manage_pages(self):
        self._login(self.catalog_manager)
        self.assertEqual(self.client.get(reverse("dashboard:page-list")).status_code, 403)

    def test_content_editor_can_manage_menus(self):
        self._login(self.content_editor)
        self.assertEqual(self.client.get(reverse("dashboard:menu-list")).status_code, 200)


class MediaPermissionTests(PermissionEnforcementTestCase):
    def test_catalog_manager_can_view_product_media(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

    def test_order_manager_cannot_view_product_media(self):
        self._login(self.order_manager)
        response = self.client.get(reverse("dashboard:product-images", args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)


class PermissionAwareNavigationTests(PermissionEnforcementTestCase):
    """The sidebar (apps.dashboard.context_processors.merchant_permissions)
    must only render links the current role actually has permission for —
    the previous version rendered every nav item unconditionally."""

    def test_owner_sees_every_nav_section(self):
        self._login(self.owner)
        response = self.client.get(reverse("dashboard:dashboard"))
        for section in ("orders", "products", "finance", "customers", "marketing", "store", "reports", "settings"):
            self.assertContains(response, f'data-section="{section}"')

    def test_content_editor_does_not_see_product_or_order_nav(self):
        self._login(self.content_editor)
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(response, 'data-section="products"')
        self.assertNotContains(response, 'data-section="orders"')
        self.assertNotContains(response, 'data-section="settings"')
        self.assertContains(response, 'data-section="store"')

    def test_analyst_does_not_see_settings_nav(self):
        self._login(self.analyst)
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, 'data-section="products"')
        # The analyst keeps read-only settings screens (shipping, tax, usage…) but never the
        # general-settings, team or SMS tabs they cannot open.
        shipping = self.client.get(reverse("dashboard:shipping-setup"))
        self.assertEqual(shipping.status_code, 200)
        for tab in ("settings-general", "settings-finance", "sms", "staff"):
            self.assertNotContains(shipping, f'data-tab="{tab}"')
        self.assertContains(shipping, 'data-tab="shipping"')
        self.assertEqual(self.client.get(reverse("dashboard:settings")).status_code, 403)

    def test_catalog_manager_does_not_see_customers_or_content_nav(self):
        self._login(self.catalog_manager)
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(response, 'data-section="customers"')
        self.assertNotContains(response, 'data-section="store"')
        # …but the catalog area they own still exposes its categories tab.
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, 'data-tab="categories"')


class SuperuserAndNoMembershipPermissionTests(PermissionEnforcementTestCase):
    """Superuser behavior per the intended architecture: Platform Superuser
    (``/admin/``) is a separate concern from merchant-admin permissions —
    superuser status grants nothing here without an explicit membership."""

    def test_superuser_without_membership_denied_at_staff_required_layer(self):
        superuser = User.objects.create_superuser(
            username="perm-super", email="perm-super@example.com", password="pass12345",
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_staff_without_membership_denied_before_reaching_permission_check(self):
        staff = User.objects.create_user(username="perm-nostaff-member", password="pass12345", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertRedirects(response, reverse("catalog:home"))

    def test_inactive_membership_denied(self):
        user = User.objects.create_user(username="perm-invited", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.INVITED,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertRedirects(response, reverse("catalog:home"))
