"""Admin Experience Upgrade — Part 2/3: the new-store tax default and the single tax editor.

* New stores start WITHOUT tax and with the suggested 10.00 % pre-filled; both values come from Django settings (one source), for
  ``provision_for`` and for any other way a ``ShopSettings`` row is created.
* Enabling 10 % from the tax page makes cart, order snapshot and grand total consistent; disabling it later never rewrites orders.
* Existing stores / rows stay exactly as they were (also across the migration that changes the field defaults).
* The rate has ONE editor (``/admin-portal/tax/settings/``); the finance section only summarises it."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.services.pricing import cart_totals
from apps.core.models import AuditLogEntry, ShopSettings
from apps.orders.models import Order
from apps.orders.services.tax_service import calculate_order_taxes
from apps.orders.tests.test_order_service_shipping_tax import ShippingTaxOrderIntegrationTestCase
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "tax-upgrade.rastisi.localhost"


def _new_store(slug):
    return Store.objects.create(name=f"فروشگاه {slug}", slug=slug, status=Store.Status.ACTIVE)


class NewStoreTaxDefaultsTests(TestCase):
    def test_a_new_store_starts_without_tax_and_with_the_suggested_rate(self):
        shop = ShopSettings.provision_for(_new_store("tax-new-1"))
        self.assertFalse(shop.tax_enabled)
        self.assertEqual(shop.tax_percent, Decimal("10.00"))
        self.assertIsNone(shop.tax_setup_confirmed_at)              # still «not decided» for the setup checklist
        self.assertEqual(ShopSettings.load(store=shop.store).pk, shop.pk)          # load() returns the same row

    def test_tax_amount_is_zero_while_disabled(self):
        store = _new_store("tax-new-2")
        ShopSettings.provision_for(store)
        result = calculate_order_taxes(
            store, items=[{"unit_price": Decimal("1000000"), "quantity": 2, "discount_allocation": Decimal("0")}],
            shipping_amount=Decimal("50000"),
        )
        self.assertEqual((result["total_tax"], result["line_tax_total"], result["shipping_tax"]), (0, 0, 0))

    @override_settings(SHOP_NEW_STORE_TAX_ENABLED=True, SHOP_NEW_STORE_TAX_PERCENT="12.50")
    def test_the_defaults_are_configurable_and_apply_to_every_creation_path(self):
        provisioned = ShopSettings.provision_for(_new_store("tax-new-3"))
        direct = ShopSettings.objects.create(store=_new_store("tax-new-4"))            # not via provision_for
        for shop in (provisioned, direct):
            shop.refresh_from_db()
            self.assertEqual((shop.tax_enabled, shop.tax_percent), (True, Decimal("12.50")))

    def test_a_broken_setting_falls_back_to_the_safe_suggestion(self):
        for bad in ("abc", "-3", "150", ""):
            with override_settings(SHOP_NEW_STORE_TAX_PERCENT=bad):
                shop = ShopSettings.objects.create(store=_new_store(f"tax-bad-{abs(hash(bad)) % 9999}"))
                self.assertEqual(shop.tax_percent, Decimal("10.00"), bad)

    def test_provision_for_never_overwrites_a_merchant_choice(self):
        store = _new_store("tax-new-5")
        shop = ShopSettings.provision_for(store)
        ShopSettings.objects.filter(pk=shop.pk).update(tax_enabled=True, tax_percent=Decimal("7.00"))
        again = ShopSettings.provision_for(store)
        self.assertEqual((again.tax_enabled, again.tax_percent), (True, Decimal("7.00")))

    def test_the_existing_legacy_store_keeps_its_old_values(self):
        legacy = ShopSettings.load(store=Store.objects.get(slug="akhlaghi"))
        self.assertEqual((legacy.tax_enabled, legacy.tax_percent), (True, Decimal("9.00")))


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class EnableTaxEndToEndTests(ShippingTaxOrderIntegrationTestCase):
    """The shop starts like a brand-new one (tax off, 10 %); the merchant enables it on the tax page."""

    def setUp(self):
        super().setUp()
        ShopSettings.objects.filter(store=self.store).update(
            tax_enabled=False, tax_percent=Decimal("10.00"), tax_setup_confirmed_at=None,
            prices_include_tax=False, shipping_taxable=False,
        )
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09129990001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin = Client(HTTP_HOST=HOST)
        self.admin.force_login(owner)

    def _totals(self):
        return cart_totals(self.cart, store=self.store, shipping_method=self.shipping)

    def test_off_then_on_at_ten_percent_is_consistent_everywhere(self):
        totals = self._totals()
        self.assertEqual(totals["tax"], 0)
        grand_without_tax = totals["grand_total"]

        page = self.admin.get(reverse("dashboard:tax-settings"))
        self.assertContains(page, "مالیات ندارم")
        self.assertEqual(page.context["settings"].tax_enabled, False)
        self.assertContains(page, 'name="tax_percent"')
        self.assertContains(page, "10.00")                                     # the suggestion is already filled in

        self.admin.post(reverse("dashboard:tax-settings"), {"tax_enabled": "on", "tax_percent": "10"})
        shop = ShopSettings.load(store=self.store)
        self.assertEqual((shop.tax_enabled, shop.tax_percent), (True, Decimal("10.00")))
        self.assertIsNotNone(shop.tax_setup_confirmed_at)

        totals = self._totals()
        self.assertEqual(totals["tax"], Decimal("100000"))                     # 10 % of 1,000,000
        self.assertEqual(totals["grand_total"], grand_without_tax + Decimal("100000"))
        order = self._create()
        self.assertEqual(order.tax, Decimal("100000"))
        self.assertEqual(order.grand_total, grand_without_tax + Decimal("100000"))
        item = order.items.get()
        self.assertEqual((item.tax_rate_percent, item.total_tax), (Decimal("10.00"), Decimal("100000")))

    def test_disabling_later_never_rewrites_a_past_order(self):
        self.admin.post(reverse("dashboard:tax-settings"), {"tax_enabled": "on", "tax_percent": "10"})
        past = self._create()
        self.admin.post(reverse("dashboard:tax-settings"), {"tax_enabled": "off", "tax_percent": "10"})
        self.assertEqual(self._totals()["tax"], 0)                             # new carts: no tax
        past = Order.objects.get(pk=past.pk)
        self.assertEqual(past.tax, Decimal("100000"))                          # the order keeps what it was charged
        self.assertEqual(past.items.get().tax_rate_percent, Decimal("10.00"))

    def test_rate_is_validated_audited_and_digits_are_normalised(self):
        url = reverse("dashboard:tax-settings")
        bad = self.admin.post(url, {"tax_enabled": "on", "tax_percent": "abc"})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "نرخ مالیات باید یک عدد باشد")
        self.assertEqual(ShopSettings.load(store=self.store).tax_percent, Decimal("10.00"))
        self.assertFalse(ShopSettings.load(store=self.store).tax_enabled)      # nothing at all was saved on the invalid post
        self.admin.post(url, {"tax_enabled": "on", "tax_percent": "۱۲٫۵"})
        self.assertEqual(ShopSettings.load(store=self.store).tax_percent, Decimal("12.50"))
        entry = AuditLogEntry.objects.filter(action_code="tax_settings.updated", store=self.store).latest("pk")
        self.assertIn("12.50", entry.after_summary)

    def test_a_post_without_a_rate_leaves_the_rate_untouched(self):
        self.admin.post(reverse("dashboard:tax-settings"), {"tax_enabled": "on"})
        self.assertEqual(ShopSettings.load(store=self.store).tax_percent, Decimal("10.00"))

    def test_the_rate_has_one_editor_the_finance_section_only_summarises(self):
        self.admin.post(reverse("dashboard:tax-settings"), {"tax_enabled": "on", "tax_percent": "10"})
        self.admin.post(reverse("dashboard:settings-finance"), {"tax_percent": "3", "free_shipping_threshold": "900000"})
        shop = ShopSettings.load(store=self.store)
        self.assertEqual((shop.tax_percent, shop.free_shipping_threshold), (Decimal("10.00"), Decimal("900000")))
        page = self.admin.get(reverse("dashboard:settings") + "?section=finance")
        self.assertContains(page, "مدیریت مالیات")
        self.assertContains(page, reverse("dashboard:tax-settings"))
        self.assertNotContains(page, 'name="tax_percent"')


class LegacyRowsAcrossTheMigrationTests(TransactionTestCase):
    """The migration only changes the field DEFAULTS; a row written before it must come out identical."""

    def test_legacy_values_survive_the_defaults_migration(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0021_price_inquiry")])
        old_apps = executor.loader.project_state([("core", "0021_price_inquiry")]).apps
        OldShop, OldStore = old_apps.get_model("core", "ShopSettings"), old_apps.get_model("stores", "Store")
        store = OldStore.objects.create(name="قدیمی", slug="legacy-tax-row", status="active")
        OldShop.objects.create(store=store, tax_enabled=True, tax_percent=Decimal("9"), name="قدیمی")
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            row = ShopSettings.objects.get(store__slug="legacy-tax-row")
            self.assertEqual((row.tax_enabled, row.tax_percent), (True, Decimal("9.00")))
        finally:
            Store.objects.filter(slug="legacy-tax-row").delete()


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ShippingSingleReferenceTests(ShippingTaxOrderIntegrationTestCase):
    """Settings → «ارسال و درگاه» is a readable summary + the «مدیریت ارسال» button; the editor is /shipping/setup/ only."""

    def setUp(self):
        super().setUp()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        owner = User.objects.create_user(username="09129990002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin = Client(HTTP_HOST=HOST)
        self.admin.force_login(owner)

    def test_summary_page_has_the_button_and_no_second_editor(self):
        page = self.admin.get(reverse("dashboard:settings") + "?section=delivery-payment")
        self.assertContains(page, "مدیریت ارسال")
        self.assertContains(page, reverse("dashboard:shipping-setup"))
        self.assertContains(page, self.shipping.name)                          # readable summary of the real methods
        for editor_hint in ('name="cost"', 'name="cod_eligible"', 'name="free_over"', "settings-shipping-toggle", "shipping-method-simple-update"):
            self.assertNotContains(page, editor_hint)

    def test_primary_editor_is_intact_and_old_routes_stay_compatible(self):
        editor = self.admin.get(reverse("dashboard:shipping-setup"))
        self.assertEqual(editor.status_code, 200)
        self.assertContains(editor, 'name="cost"')
        # the legacy toggle route still answers (and keeps its permission + tenant rules) although nothing links to it any more
        self.assertEqual(self.admin.get(reverse("dashboard:settings-shipping-toggle", args=[self.shipping.pk])).status_code, 405)
        self.assertEqual(self.admin.get("/admin-panel/settings/?section=delivery-payment").status_code, 302)   # old admin-panel prefix
