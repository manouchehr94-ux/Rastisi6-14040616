"""Account page UI contract: independent tabs (never pdp-tabs / product_detail.css), only the selected panel visible, store-themed."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.customers.models import Customer

User = get_user_model()
PANELS = ("profile", "orders", "addresses", "coupons", "security")


class AccountTabsStructureTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="09127775566", password="x-Pass#12345")
        Customer.objects.create(user=user, full_name="تب‌ها", phone="09127775566")
        self.client.force_login(user)
        self.html = self.client.get(reverse("customers:account")).content.decode()

    def test_does_not_use_the_product_page_tab_component_or_its_stylesheet(self):
        self.assertNotIn("pdp-tabs", self.html)
        self.assertNotIn("product_detail.css", self.html)
        self.assertNotIn('class="tabpane', self.html)

    def test_five_accessible_tabs_and_panels_with_only_profile_visible_on_first_paint(self):
        for key in PANELS:
            self.assertIn(f'id="acct-tab-{key}"', self.html)
            self.assertIn(f'aria-controls="acct-panel-{key}"', self.html)
            self.assertIn(f'aria-labelledby="acct-tab-{key}"', self.html)
        self.assertIn('role="tablist"', self.html)
        self.assertEqual(self.html.count('role="tabpanel"'), 5)
        for key in PANELS[1:]:                                                # server-rendered hidden → no flash of stacked panels
            self.assertRegex(self.html, rf'id="acct-panel-{key}"[^>]*\bhidden\b')
        self.assertNotRegex(self.html, r'id="acct-panel-profile"[^>]*\shidden\s')

    def test_wishlist_stays_a_real_link_and_htmx_targets_still_exist(self):
        self.assertIn(reverse("customers:wishlist"), self.html)
        for target in ("account-profile", "account-addresses", "account-security"):
            self.assertIn(f'id="{target}"', self.html)

    def test_profile_and_address_htmx_saves_still_work_and_stay_in_their_panels(self):
        res = self.client.post(reverse("customers:account-profile-update"), {"full_name": "نام تازه", "email": "", "city": "تهران"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "نام تازه")
        bad = self.client.post(reverse("customers:account-profile-update"), {"full_name": "", "email": "bad"})
        self.assertContains(bad, "coup-err")
        added = self.client.post(reverse("customers:address-add"), {"receiver_name": "م", "phone": "09121110000", "province": "تهران", "city": "تهران", "full_address": "خیابان"})
        self.assertContains(added, "addr-card")
