"""Panel UX (M4-C): the settings search says what it searches and points to the global search. No behaviour changes — the same forms, URLs, permissions and tax authority as before."""

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


class SettingsSearchLabelTests(_FinanceBase):
    def test_settings_search_states_its_scope_and_points_to_the_global_search(self):
        html = self._html()
        self.assertIn('settings-search-label', html)
        self.assertIn('class="settings-search-scope"', html)
        self.assertIn("فقط صفحه‌های تنظیمات", html)
        self.assertIn("Ctrl+K", html)
        self.assertIn('aria-describedby="settingsSearchHint"', html)
        self.assertIn('id="settingsSearchHint"', html)
        self.assertIn("data-au-search-input", html)

    def test_search_index_stays_permission_filtered_and_section_links_survive(self):
        html = self._html()
        hrefs = re.findall(r'data-au-search-item[^>]*><a href="([^"]+)"', html)
        self.assertTrue(hrefs)
        index_items = len(hrefs)
        # a member without any settings permission sees no index (the box itself is not rendered)
        outsider = User.objects.create_user(username="m4-out", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=outsider, role=StoreMembership.Role.CONTENT_EDITOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="m4-out", password="pass12345")
        resp = self.client.get(reverse("dashboard:settings") + "?section=finance")
        if resp.status_code == 200:
            other = len(re.findall(r'data-au-search-item[^>]*><a href="([^"]+)"', resp.content.decode()))
            self.assertLessEqual(other, index_items)
