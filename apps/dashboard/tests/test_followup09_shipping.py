"""FOLLOWUP-09 — one canonical place to edit shipping; the settings page is a read-only summary of the same model; no incomplete activation."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.orders.models import ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = f"shipping09.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ShippingSingleSourceTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09127930001", password="pass12345")
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127930001", password="pass12345")
        self.method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-09", method_type=ShippingMethod.MethodType.FLAT_RATE,
                                                    cost=50000, is_active=False)

    def summary_page(self):
        return self.client.get(reverse("dashboard:settings") + "?section=delivery-payment").content.decode()

    def test_settings_page_is_a_read_only_summary_linking_to_the_single_editor(self):
        html = self.summary_page()
        self.assertIn(reverse("dashboard:shipping-setup"), html)
        self.assertNotIn(reverse("dashboard:settings-shipping-toggle", args=[self.method.pk]), html)   # no second switch for shipping methods
        self.assertIn("پست", html)
        self.assertIn("غیرفعال", html)

    def test_both_pages_read_the_same_rows_and_follow_each_other(self):
        setup = self.client.get(reverse("dashboard:shipping-setup")).content.decode()
        self.assertIn("پست", setup)
        self.client.post(reverse("dashboard:shipping-method-simple-update", args=[self.method.pk]), {"is_active": "on", "cost": "50000"})
        self.method.refresh_from_db()
        self.assertTrue(self.method.is_active)
        html = self.summary_page()
        self.assertRegex(html, r"badge b-green[^>]*>\s*فعال")

    def test_the_legacy_toggle_endpoint_is_audited_and_never_activates_an_invalid_method(self):
        url = reverse("dashboard:settings-shipping-toggle", args=[self.method.pk])
        self.assertEqual(self.client.post(url).status_code, 204)
        self.method.refresh_from_db()
        self.assertTrue(self.method.is_active)
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="shipping_method.updated", object_id=str(self.method.pk)).exists())
        self.client.post(url)                                       # deactivate again
        # make the row invalid (pickup warehouse that does not belong to the store) and try to activate it
        from apps.stores.models import Store as S
        other = S.objects.create(name="B", slug="shipping09-b", status=S.Status.ACTIVE)
        from apps.catalog.models import Warehouse  # noqa
        wh = Warehouse.objects.create(store=other, name="انبار دیگر", code="W9", is_pickup_location=True)
        ShippingMethod.objects.filter(pk=self.method.pk).update(pickup_warehouse=wh, is_pickup=True)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 422)
        self.assertIn("HX-Refresh", resp)
        self.method.refresh_from_db()
        self.assertFalse(self.method.is_active)

    def test_other_stores_methods_are_404_through_both_endpoints(self):
        other_store = Store.objects.create(name="B", slug="shipping09-c", status=Store.Status.ACTIVE)
        foreign = ShippingMethod.objects.create(store=other_store, name="x", slug="x-09", method_type=ShippingMethod.MethodType.FLAT_RATE, cost=1)
        self.assertEqual(self.client.post(reverse("dashboard:settings-shipping-toggle", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:shipping-method-simple-update", args=[foreign.pk]), {"is_active": "on"}).status_code, 404)
        before = foreign.is_active
        foreign.refresh_from_db()
        self.assertEqual(foreign.is_active, before)

    def test_the_free_shipping_threshold_is_explained_on_both_pages(self):
        self.assertIn("آستانهٔ ارسال رایگانِ کلِ فروشگاه", self.summary_page())
        self.assertIn("آستانه‌ی ارسالِ رایگانِ همین روش", self.client.get(reverse("dashboard:shipping-setup")).content.decode())
