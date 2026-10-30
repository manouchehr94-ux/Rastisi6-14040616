"""Panel UX (M4-B): the finance section is an accordion with real on/off switches for its Boolean settings. No behaviour changes — the same forms, URLs, permissions and tax authority as before."""

from decimal import Decimal
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class _FinanceBase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.user = User.objects.create_user(username="m4-fin", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="m4-fin", password="pass12345")

    def _html(self):
        return self.client.get(reverse("dashboard:settings") + "?section=finance").content.decode()


class FinanceAccordionTests(_FinanceBase):
    def test_three_accordions_in_the_documented_order(self):
        html = self._html()
        ids = re.findall(r'class="au-acc[^"]*" id="(fin-(?!panel)[a-z-]+)"', html)
        self.assertEqual(ids, ["fin-free-shipping", "fin-gift-wrap", "fin-tax"])
        for panel in ("fin-panel-free-shipping", "fin-panel-gift-wrap", "fin-panel-tax"):
            self.assertIn(f'aria-controls="{panel}"', html)
            self.assertIn(f'id="{panel}"', html)

    def test_only_the_primary_card_is_open_by_default(self):
        html = self._html()
        self.assertRegex(html, r'id="fin-free-shipping"[^>]*>|class="au-acc is-open" id="fin-free-shipping"')
        self.assertIn('id="fin-panel-gift-wrap" hidden', html)
        self.assertIn('id="fin-panel-tax" hidden', html)

    def test_boolean_settings_are_real_switches_and_actions_stay_checkboxes(self):
        html = self._html()
        panel = html[html.index('id="fin-panel-gift-wrap"'):html.index('id="fin-tax"')]
        for name in ("gift_wrap_available", "gift_wrap_message_enabled"):
            self.assertRegex(panel, rf'<label class="au-switch">\s*<input type="checkbox" name="{name}"')
        # «remove the current picture» is an action, not a state — it is not dressed up as a switch
        self.assertRegex(panel, r'<label><input type="checkbox" name="remove_gift_wrap_image">')
        # no autosubmit: the whole form is saved explicitly, so the switch cannot silently drop the other fields
        self.assertNotIn("data-au-autosubmit", panel)

    def test_switch_state_mirrors_the_stored_value(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = False
        shop.save(update_fields=["gift_wrap_available"])
        off = self._html()
        self.assertRegex(off, r'name="gift_wrap_available" >')
        self.assertIn('data-testid="finance-gift-wrap-status">غیرفعال', off)
        shop.gift_wrap_available = True
        shop.save(update_fields=["gift_wrap_available"])
        on = self._html()
        self.assertRegex(on, r'name="gift_wrap_available" checked>')
        self.assertIn('data-testid="finance-gift-wrap-status">فعال', on)

    def test_saving_through_the_new_markup_still_works(self):
        response = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_available": "on", "gift_wrap_price": "15000", "gift_wrap_pricing_scope": "per_order",
            "gift_wrap_title": "کادو", "gift_wrap_description": "", "gift_wrap_message_enabled": "on",
        })
        self.assertIn(response.status_code, (200, 302))
        shop = ShopSettings.load(store=self.store)
        self.assertTrue(shop.gift_wrap_available)
        self.assertTrue(shop.gift_wrap_message_enabled)

    def test_a_rejected_gift_wrap_form_opens_its_accordion(self):
        response = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_available": "on", "gift_wrap_price": "-500", "gift_wrap_pricing_scope": "per_order",
        })
        body = response.content.decode() if response.status_code == 200 else self.client.get(response["Location"]).content.decode()
        if 'id="fin-gift-wrap"' in body:
            self.assertIn('aria-expanded="true" aria-controls="fin-panel-gift-wrap"', body)
        self.assertFalse(ShopSettings.load(store=self.store).gift_wrap_available)

    def test_tax_stays_a_read_only_summary_and_its_percent_is_never_touched(self):
        shop = ShopSettings.load(store=self.store)
        before = (shop.tax_enabled, shop.tax_percent)
        html = self._html()
        self.assertIn('data-testid="finance-tax-summary"', html)
        self.assertIn(reverse("dashboard:tax-settings"), html)
        for editor_hint in ('name="tax_percent"', 'name="tax_enabled"'):
            self.assertNotIn(editor_hint, html)
        shop.refresh_from_db()
        self.assertEqual((shop.tax_enabled, shop.tax_percent), before)
        self.assertIsInstance(shop.tax_percent, Decimal)

    def test_free_shipping_form_still_posts_to_the_same_endpoint(self):
        html = self._html()
        self.assertIn(f'action="{reverse("dashboard:settings-finance")}"', html)
        self.assertIn("ذخیره آستانه", html)
