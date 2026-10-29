"""تست‌های صفحه‌ی سادهٔ راه‌اندازیِ ارسال — apps.dashboard.views.shipping_setup /
shipping_method_simple_update."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.services.checklist_service import build_setup_checklist
from apps.orders.models import ShippingMethod
from apps.orders.services.shipping_service import DEFAULT_SHIPPING_METHODS, ensure_default_shipping_methods
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"ship-setup-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ShippingSetupTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09127700001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09127700001", password="pass12345")


class EnsureDefaultShippingMethodsTests(TestCase):
    def test_creates_all_common_methods(self):
        store = Store.objects.create(name="فروشگاه تست ارسال", slug="ship-seed-store", status=Store.Status.ACTIVE)
        methods = ensure_default_shipping_methods(store)
        self.assertEqual(len(methods), len(DEFAULT_SHIPPING_METHODS))
        slugs = set(ShippingMethod.objects.filter(store=store).values_list("slug", flat=True))
        self.assertEqual(slugs, {entry["slug"] for entry in DEFAULT_SHIPPING_METHODS})

    def test_all_seeded_methods_start_inactive(self):
        store = Store.objects.create(name="فروشگاه تست ارسال ۲", slug="ship-seed-store-2", status=Store.Status.ACTIVE)
        ensure_default_shipping_methods(store)
        self.assertFalse(ShippingMethod.objects.filter(store=store, is_active=True).exists())

    def test_pickup_method_is_flagged_correctly(self):
        store = Store.objects.create(name="فروشگاه تست ارسال ۳", slug="ship-seed-store-3", status=Store.Status.ACTIVE)
        ensure_default_shipping_methods(store)
        pickup = ShippingMethod.objects.get(store=store, slug="pickup")
        self.assertTrue(pickup.is_pickup)
        self.assertEqual(pickup.cost, 0)

    def test_running_twice_does_not_duplicate(self):
        store = Store.objects.create(name="فروشگاه تست ارسال ۴", slug="ship-seed-store-4", status=Store.Status.ACTIVE)
        ensure_default_shipping_methods(store)
        first_count = ShippingMethod.objects.filter(store=store).count()
        ensure_default_shipping_methods(store)
        second_count = ShippingMethod.objects.filter(store=store).count()
        self.assertEqual(first_count, second_count)
        self.assertEqual(first_count, len(DEFAULT_SHIPPING_METHODS))

    def test_does_not_overwrite_merchant_edits(self):
        store = Store.objects.create(name="فروشگاه تست ارسال ۵", slug="ship-seed-store-5", status=Store.Status.ACTIVE)
        ensure_default_shipping_methods(store)
        method = ShippingMethod.objects.get(store=store, slug="tipax")
        method.is_active = True
        method.cost = Decimal("45000")
        method.save(update_fields=["is_active", "cost"])

        ensure_default_shipping_methods(store)

        method.refresh_from_db()
        self.assertTrue(method.is_active)
        self.assertEqual(method.cost, Decimal("45000"))


class ShippingSetupPageTests(ShippingSetupTestCase):
    def test_common_methods_appear(self):
        response = self.client.get(reverse("dashboard:shipping-setup"))
        self.assertEqual(response.status_code, 200)
        for entry in DEFAULT_SHIPPING_METHODS:
            self.assertContains(response, entry["name"])

    def test_visiting_page_is_idempotent_seed_trigger(self):
        self.client.get(reverse("dashboard:shipping-setup"))
        first_count = ShippingMethod.objects.filter(store=self.store).count()
        self.client.get(reverse("dashboard:shipping-setup"))
        second_count = ShippingMethod.objects.filter(store=self.store).count()
        self.assertEqual(first_count, second_count)

    def test_advanced_settings_link_present(self):
        response = self.client.get(reverse("dashboard:shipping-setup"))
        self.assertContains(response, reverse("dashboard:shipping-method-list"))


class ShippingMethodSimpleUpdateTests(ShippingSetupTestCase):
    def setUp(self):
        super().setUp()
        ensure_default_shipping_methods(self.store)
        self.post_method = ShippingMethod.objects.get(store=self.store, slug="post")
        self.tipax_method = ShippingMethod.objects.get(store=self.store, slug="tipax")
        self.pickup_method = ShippingMethod.objects.get(store=self.store, slug="pickup")

    def test_activate_method(self):
        response = self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.post_method.pk]),
            {"is_active": "on", "cost": "0"}, follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.post_method.refresh_from_db()
        self.assertTrue(self.post_method.is_active)

    def test_deactivate_method(self):
        self.post_method.is_active = True
        self.post_method.save(update_fields=["is_active"])
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.post_method.pk]),
            {"cost": "0"},
        )
        self.post_method.refresh_from_db()
        self.assertFalse(self.post_method.is_active)

    def test_cod_forces_cost_to_zero_even_if_submitted(self):
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.post_method.pk]),
            {"is_active": "on", "cod_eligible": "on", "cost": "99999"},
        )
        self.post_method.refresh_from_db()
        self.assertTrue(self.post_method.cod_eligible)
        self.assertEqual(self.post_method.cost, Decimal("0"))

    def test_fixed_cost_saves_correctly(self):
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.tipax_method.pk]),
            {"is_active": "on", "cost": "35000"},
        )
        self.tipax_method.refresh_from_db()
        self.assertTrue(self.tipax_method.is_active)
        self.assertFalse(self.tipax_method.cod_eligible)
        self.assertEqual(self.tipax_method.cost, Decimal("35000"))

    def test_negative_cost_rejected(self):
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.tipax_method.pk]),
            {"is_active": "on", "cost": "-100"},
        )
        self.tipax_method.refresh_from_db()
        self.assertEqual(self.tipax_method.cost, Decimal("0"))

    def test_pickup_defaults_to_zero_cost_regardless_of_input(self):
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.pickup_method.pk]),
            {"is_active": "on", "cost": "12345"},
        )
        self.pickup_method.refresh_from_db()
        self.assertTrue(self.pickup_method.is_active)
        self.assertEqual(self.pickup_method.cost, Decimal("0"))

    def test_free_shipping_threshold_saves_correctly(self):
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.tipax_method.pk]),
            {"is_active": "on", "cost": "20000", "free_over": "300000"},
        )
        self.tipax_method.refresh_from_db()
        self.assertEqual(self.tipax_method.free_over, Decimal("300000"))

    def test_free_shipping_threshold_left_empty_disables_it(self):
        self.tipax_method.free_over = Decimal("500000")
        self.tipax_method.save(update_fields=["free_over"])
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[self.tipax_method.pk]),
            {"is_active": "on", "cost": "20000", "free_over": ""},
        )
        self.tipax_method.refresh_from_db()
        self.assertIsNone(self.tipax_method.free_over)

    def test_cannot_update_other_store_method(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="ship-setup-other", status=Store.Status.ACTIVE)
        other_method = ensure_default_shipping_methods(other_store)[0]
        response = self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[other_method.pk]),
            {"is_active": "on"},
        )
        self.assertEqual(response.status_code, 404)
        other_method.refresh_from_db()
        self.assertFalse(other_method.is_active)


class ShippingChecklistCompletionTests(ShippingSetupTestCase):
    def test_checklist_incomplete_with_no_active_methods(self):
        ensure_default_shipping_methods(self.store)
        from django.test import RequestFactory
        result = build_setup_checklist(self.store, RequestFactory().get("/"))
        step = next(s for s in result["steps"] if s["key"] == "shipping")
        self.assertFalse(step["is_complete"])

    def test_checklist_complete_with_one_active_method(self):
        ensure_default_shipping_methods(self.store)
        pickup = ShippingMethod.objects.get(store=self.store, slug="pickup")
        self.client.post(
            reverse("dashboard:shipping-method-simple-update", args=[pickup.pk]), {"is_active": "on"},
        )
        from django.test import RequestFactory
        result = build_setup_checklist(self.store, RequestFactory().get("/"))
        step = next(s for s in result["steps"] if s["key"] == "shipping")
        self.assertTrue(step["is_complete"])


class ShippingAccordionTests(ShippingSetupTestCase):
    """Accordion rows: closed by default, active first without touching the real order, switch = the real is_active flag."""

    def setUp(self):
        super().setUp()
        ensure_default_shipping_methods(self.store)
        self.page_url = reverse("dashboard:shipping-setup")

    def methods(self):
        return list(ShippingMethod.objects.filter(store=self.store).order_by("display_order", "name"))

    def test_rows_are_closed_by_default_with_accessible_switches_and_round_trip_links(self):
        html = self.client.get(self.page_url).content.decode()
        self.assertNotIn("au-acc is-open", html)
        self.assertEqual(html.count('role="switch"'), len(self.methods()))
        self.assertIn("section=delivery-payment", html)

    def test_active_methods_come_first_but_stored_order_is_untouched(self):
        before = [(m.pk, m.display_order) for m in self.methods()]
        last = self.methods()[-1]
        ShippingMethod.objects.filter(pk=last.pk).update(is_active=True)
        response = self.client.get(self.page_url)
        shown = [m.pk for m in response.context["methods"]]
        self.assertEqual(shown[0], last.pk)
        self.assertEqual([(m.pk, m.display_order) for m in self.methods()], before)

    def test_toggle_flips_only_the_active_flag_and_keeps_cost_cod_and_threshold(self):
        method = next(m for m in self.methods() if not m.is_pickup)
        ShippingMethod.objects.filter(pk=method.pk).update(cost=Decimal("45000"), free_over=Decimal("900000"), cod_eligible=False, is_active=False)
        self.client.post(reverse("dashboard:shipping-method-toggle", args=[method.pk]))
        method.refresh_from_db()
        self.assertTrue(method.is_active)
        self.assertEqual((method.cost, method.free_over, method.cod_eligible), (Decimal("45000"), Decimal("900000"), False))
        self.client.post(reverse("dashboard:shipping-method-toggle", args=[method.pk]))
        method.refresh_from_db()
        self.assertFalse(method.is_active)

    def test_pickup_row_keeps_zero_cost_and_no_cost_field(self):
        pickup = ShippingMethod.objects.get(store=self.store, slug="pickup")
        html = self.client.get(self.page_url).content.decode()
        self.assertNotIn(f'id="ship-cost-{pickup.pk}"', html)
        self.client.post(reverse("dashboard:shipping-method-simple-update", args=[pickup.pk]), {"is_active": "on", "cost": "9999"})
        pickup.refresh_from_db()
        self.assertEqual(pickup.cost, 0)

    def test_saving_a_row_keeps_it_open_and_shows_the_message(self):
        method = next(m for m in self.methods() if not m.is_pickup)
        self.client.post(reverse("dashboard:shipping-method-simple-update", args=[method.pk]), {"is_active": "on", "cost": "-5"})
        html = self.client.get(self.page_url).content.decode()
        self.assertIn(f'id="ship-{method.pk}"', html)
        self.assertRegex(html, rf'class="au-acc is-open"[^>]*id="ship-{method.pk}"')

    def test_toggle_is_store_scoped(self):
        other = Store.objects.create(name="دیگر", slug="ship-acc-other", status=Store.Status.ACTIVE)
        foreign = ensure_default_shipping_methods(other)[0]
        self.assertEqual(self.client.post(reverse("dashboard:shipping-method-toggle", args=[foreign.pk])).status_code, 404)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_active)
