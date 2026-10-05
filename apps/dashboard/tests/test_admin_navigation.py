"""Merchant-admin two-level navigation (sidebar sections + section tabs).

Covers the information architecture in ``apps.dashboard.navigation`` and its
rendering in ``base_admin.html``:

* the IA map itself (nine sections, the agreed tabs, no duplicate hrefs);
* routing coverage — every named dashboard route belongs to a section, so no
  screen is orphaned by the redesign;
* round-trip — each tab's own URL resolves back to that tab;
* permissions — roles only ever see sections/tabs they can open, and no
  rendered link leads to a 403;
* active state on representative list/detail/query-string pages;
* the command palette index and the removal of the nested accordion.
"""

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone

from apps.dashboard import navigation
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import StoreMembership

User = get_user_model()

SECTION_ORDER = ["dashboard", "orders", "products", "finance", "customers",
                 "marketing", "store", "reports", "settings"]

EXPECTED_TABS = {
    "orders": ["همه سفارش‌ها", "مرجوعی‌ها"],
    "products": ["همه کالاها", "دسته‌بندی‌ها", "برندها", "ویژگی‌ها", "موجودی", "انبارها",
                 "رزرو موجودی", "انتقال انبار"],
    "finance": ["فاکتورها", "پرداخت‌ها", "تطبیق پرداخت‌ها"],
    "customers": ["مشتریان", "سگمنت‌ها"],
    "marketing": ["کمپین‌ها", "مناسبت‌ها و هدیه‌ها", "کدهای تخفیف", "اعلان‌ها و پیام‌ها"],
    "store": ["ظاهر و طراحی", "سازنده فروشگاه", "قالب‌های آماده", "کالکشن‌ها", "محتوا",
              "صفحه اصلی", "منوها", "فوتر", "شبکه‌های اجتماعی"],
    "reports": ["گزارش‌های حرفه‌ای", "گزارش رخدادها"],
    "settings": ["تنظیمات عمومی", "ارسال", "مالیات", "تنظیمات مالی", "پیامک", "اعضای تیم",
                 "اشتراک", "صورتحساب اشتراک", "مصرف و سقف‌ها", "واردات داده", "صادرات داده"],
}


def _all_flags(value=True):
    flags = set()
    for section in navigation.SECTIONS:
        for tab in section.tabs:
            flags.update(tab.perms)
    for extra in navigation.PALETTE_EXTRAS:
        flags.update(extra.perms)
    return {flag: value for flag in flags}


def _dashboard_url_names():
    from apps.dashboard import urls as dashboard_urls

    def walk(patterns):
        for pattern in patterns:
            if hasattr(pattern, "url_patterns"):
                yield from walk(pattern.url_patterns)
            elif pattern.name:
                yield pattern.name

    return sorted(set(walk(dashboard_urls.urlpatterns)))


class NavigationMapTests(SimpleTestCase):
    def test_nine_sections_in_the_agreed_order(self):
        self.assertEqual([s.key for s in navigation.SECTIONS], SECTION_ORDER)
        self.assertEqual(
            [s.label for s in navigation.SECTIONS],
            ["داشبورد", "سفارش‌ها", "کالاها", "فاکتورها و مالی", "مشتریان",
             "بازاریابی", "فروشگاه", "گزارش‌ها", "تنظیمات"],
        )

    def test_section_tabs_match_the_agreed_information_architecture(self):
        for section in navigation.SECTIONS:
            if section.key == "dashboard":
                continue
            self.assertEqual([t.label for t in section.tabs], EXPECTED_TABS[section.key], section.key)

    def test_no_two_tabs_share_the_same_destination(self):
        seen = {}
        for section in navigation.SECTIONS:
            for tab in section.tabs:
                key = (tab.url_name, tab.query)
                self.assertNotIn(key, seen, f"{tab.key} duplicates {seen.get(key)}")
                seen[key] = tab.key

    def test_every_tab_points_at_a_real_dashboard_route(self):
        names = set(_dashboard_url_names())
        for section in navigation.SECTIONS:
            for tab in section.tabs:
                self.assertIn(tab.url_name, names, tab.key)
                self.assertTrue(reverse(f"dashboard:{tab.url_name}"))

    def test_every_dashboard_route_belongs_to_a_section(self):
        orphans = [
            name for name in _dashboard_url_names()
            if name not in navigation.NON_NAVIGATIONAL_URL_NAMES
            and navigation.resolve_active(name, {}, "")[0] is None
        ]
        self.assertEqual(orphans, [], "dashboard routes not covered by the navigation map")

    def test_each_tab_url_resolves_back_to_its_own_tab(self):
        for section in navigation.SECTIONS:
            for tab in section.tabs:
                get = {}
                if tab.query:
                    key, _, value = tab.query.lstrip("?").partition("=")
                    get = {key.split("&")[0]: value.split("&")[0]}
                self.assertEqual(
                    navigation.resolve_active(tab.url_name, get, ""), (section.key, tab.key),
                    f"{section.key}/{tab.key}",
                )

    def test_representative_detail_and_edit_routes_light_up_their_list_tab(self):
        cases = {
            "order-detail": ("orders", "orders"),
            "order-refund": ("orders", "orders"),
            "return-detail": ("orders", "returns"),
            "product-edit": ("products", "products"),
            "product-variants": ("products", "products"),
            "warehouse-detail": ("products", "warehouses"),
            "transfer-add": ("products", "transfers"),
            "invoice-detail": ("finance", "invoices"),
            "payment-reconciliation-resolve": ("finance", "payment-reconciliations"),
            "customer-detail": ("customers", "customers"),
            "customer-tag-list": ("customers", "customers"),
            "segment-detail": ("customers", "segments"),
            "coupon-edit": ("marketing", "coupons"),
            "notification-history": ("marketing", "notifications"),
            "storefront-builder-header": ("store", "builder"),
            "storefront-builder-template-live-preview": ("store", "templates"),
            "collection-products": ("store", "collections"),
            "banner-list": ("store", "homepage"),
            "menu-item-list": ("store", "menus"),
            "footer-trust-badge-list": ("store", "footer"),
            "report-body": ("reports", "reports"),
            "audit-log-table": ("reports", "audit-log"),
            "shipping-zone-list": ("settings", "shipping"),
            "tax-rate-list": ("settings", "tax"),
            "settings-industry-preview": ("settings", "settings-general"),
            "gift-wrap-products": ("settings", "settings-finance"),
            "sms-log-list": ("settings", "sms"),
            "sms-outbox-list": ("settings", "sms"),
            "staff-add": ("settings", "staff"),
            "subscription-plans": ("settings", "subscription"),
            "billing-invoice-detail": ("settings", "billing"),
            "usage-overview": ("settings", "usage"),
            "import-detail": ("settings", "imports"),
            "export-create": ("settings", "exports"),
        }
        for url_name, expected in cases.items():
            self.assertEqual(navigation.resolve_active(url_name, {}, ""), expected, url_name)

    def test_query_string_disambiguates_shared_urls(self):
        resolve = navigation.resolve_active
        self.assertEqual(resolve("campaign-list", {"kind": "occasions"}, ""), ("marketing", "occasions"))
        self.assertEqual(resolve("campaign-list", {"kind": "campaigns"}, ""), ("marketing", "campaigns"))
        self.assertEqual(resolve("campaign-edit", {}, "occasions"), ("marketing", "occasions"))
        self.assertEqual(resolve("campaign-detail", {}, "campaigns"), ("marketing", "campaigns"))
        self.assertEqual(resolve("settings", {}, ""), ("settings", "settings-general"))
        self.assertEqual(resolve("settings", {"section": "payment-config"}, ""), ("settings", "settings-general"))
        self.assertEqual(resolve("settings", {"section": "finance"}, ""), ("settings", "settings-finance"))
        self.assertEqual(resolve("settings", {"section": "sms"}, ""), ("settings", "sms"))
        self.assertEqual(
            resolve("storefront-builder-r4-editor", {"panel": "appearance"}, ""), ("store", "appearance"))
        self.assertEqual(resolve("storefront-builder-r4-editor", {}, ""), ("store", "builder"))
        self.assertEqual(resolve("storefront-builder-r4-editor", {"panel": "header"}, ""), ("store", "builder"))

    def test_legacy_active_page_is_only_a_fallback(self):
        self.assertEqual(navigation.resolve_active("some-unknown-name", {}, "brands"), ("products", "brands"))
        self.assertEqual(navigation.resolve_active("some-unknown-name", {}, ""), (None, None))


class NavigationPermissionFilteringTests(SimpleTestCase):
    def test_without_any_permission_only_the_dashboard_remains(self):
        nav = navigation.build_navigation(flags={}, url_name="dashboard")
        self.assertEqual([s.key for s in nav.sections], ["dashboard"])
        self.assertFalse(nav.show_tabs)

    def test_a_section_disappears_when_all_of_its_tabs_are_hidden(self):
        nav = navigation.build_navigation(flags={"can_view_orders": True}, url_name="order-list")
        self.assertEqual([s.key for s in nav.sections], ["dashboard", "orders", "finance"])
        orders = nav.sections[1]
        self.assertEqual([t.label for t in orders.tabs], ["همه سفارش‌ها"])  # no returns permission
        self.assertFalse(nav.show_tabs, "a single-tab section must not render a tab bar")

    def test_section_link_points_at_its_first_permitted_tab(self):
        nav = navigation.build_navigation(flags={"can_manage_brands": True}, url_name="brand-list")
        products = next(s for s in nav.sections if s.key == "products")
        self.assertEqual(products.href, reverse("dashboard:brand-list"))
        self.assertEqual([t.key for t in products.tabs], ["brands"])

    def test_all_permissions_show_every_tab(self):
        nav = navigation.build_navigation(flags=_all_flags(), url_name="dashboard")
        self.assertEqual([s.key for s in nav.sections], SECTION_ORDER)
        for section in nav.sections:
            if section.key != "dashboard":
                self.assertEqual([t.label for t in section.tabs], EXPECTED_TABS[section.key])

    def test_badges_are_hidden_when_zero(self):
        nav = navigation.build_navigation(
            flags=_all_flags(), url_name="order-list",
            counts={"nav_pending_order_count": 0, "nav_product_count": 0},
        )
        self.assertTrue(all(s.badge == 0 for s in nav.sections))
        nav = navigation.build_navigation(
            flags=_all_flags(), url_name="order-list",
            counts={"nav_pending_order_count": 3, "nav_product_count": 7},
        )
        self.assertEqual(next(s for s in nav.sections if s.key == "orders").badge, 3)
        products = next(s for s in nav.sections if s.key == "products")
        self.assertEqual(next(t for t in products.tabs if t.key == "products").badge, 7)

    def test_palette_only_lists_permitted_destinations(self):
        self.assertEqual([i.title for i in navigation.build_palette({})], ["نمای کلی"])
        items = navigation.build_palette({"can_view_products": True})
        self.assertIn("همه کالاها", [i.title for i in items])
        self.assertNotIn("دسته‌بندی‌ها", [i.title for i in items])

    def test_palette_paths_use_the_new_section_labels(self):
        items = {i.title: i.path for i in navigation.build_palette(_all_flags())}
        self.assertEqual(items["همه کالاها"], "کالاها ← همه کالاها")
        self.assertEqual(items["همه سفارش‌ها"], "سفارش‌ها ← همه سفارش‌ها")
        self.assertEqual(items["کدهای تخفیف"], "بازاریابی ← کدهای تخفیف")
        self.assertEqual(items["پیامک"], "تنظیمات ← پیامک")
        self.assertEqual(items["نمای کلی"], "داشبورد")
        for path in items.values():
            for old in ("فروش ←", "مدیریت ←", "ارسال و مالیات ←"):
                self.assertNotIn(old, path)


class NavigationRenderingTests(PermissionEnforcementTestCase):
    def _soup(self, url_name, *args, query=""):
        response = self.client.get(reverse(f"dashboard:{url_name}", args=args) + query)
        self.assertEqual(response.status_code, 200, url_name)
        return BeautifulSoup(response.content.decode(), "html.parser"), response

    def _active(self, soup):
        section = soup.select_one(".sidebar a.nav-item.active")
        tab = soup.select_one(".admin-section-tab.active")
        return (section["data-section"] if section else None, tab["data-tab"] if tab else None)

    def test_owner_sidebar_is_flat_with_nine_links_and_no_nested_items(self):
        self._login(self.owner)
        soup, _ = self._soup("dashboard")
        links = soup.select(".sidebar nav.nav a.nav-item")
        self.assertEqual([a["data-section"] for a in links], SECTION_ORDER)
        self.assertEqual(soup.select(".sidebar .nav-group, .sidebar button[aria-expanded]"), [])
        self.assertEqual(len(soup.select(".sidebar nav.nav a")), 9)
        self.assertEqual(soup.select(".admin-section-tabs"), [], "dashboard has a single screen: no tab bar")

    def test_navigation_partials_do_not_leak_template_comments(self):
        self._login(self.owner)
        html = self.client.get(reverse("dashboard:product-list")).content.decode()
        for leaked in ("{#", "#}", "Level-1", "Level-2", "apps.dashboard.navigation", "{% comment"):
            self.assertNotIn(leaked, html)

    def test_active_section_and_tab_on_representative_pages(self):
        self._login(self.owner)
        cases = [
            (("dashboard",), "", ("dashboard", None)),
            (("order-list",), "", ("orders", "orders")),
            (("order-detail", self.order.code), "", ("orders", "orders")),
            (("product-list",), "", ("products", "products")),
            (("product-edit", self.product.pk), "", ("products", "products")),
            (("category-list",), "", ("products", "categories")),
            (("invoice-list",), "", ("finance", "invoices")),
            (("payment-list",), "", ("finance", "payments")),
            (("customer-list",), "", ("customers", "customers")),
            (("campaign-list",), "?kind=occasions", ("marketing", "occasions")),
            (("coupon-list",), "", ("marketing", "coupons")),
            (("page-list",), "", ("store", "content")),
            (("report-list",), "", ("reports", "reports")),
            (("settings",), "", ("settings", "settings-general")),
            (("settings",), "?section=finance", ("settings", "settings-finance")),
            (("shipping-setup",), "", ("settings", "shipping")),
            (("staff-list",), "", ("settings", "staff")),
        ]
        for args, query, expected in cases:
            with self.subTest(page=args[0], query=query):
                soup, _ = self._soup(*args, query=query)
                section, tab = self._active(soup)
                self.assertEqual((section, tab), expected)

    def test_tab_bar_marks_the_active_tab_and_links_all_siblings(self):
        self._login(self.owner)
        soup, _ = self._soup("category-list")
        nav = soup.select_one("nav.admin-section-tabs")
        self.assertIsNotNone(nav)
        self.assertEqual(nav["aria-label"], "بخش‌های کالاها")
        labels = [a.get_text(" ", strip=True).split(" ")[0] for a in nav.select("a.admin-section-tab")]
        self.assertEqual(labels[:3], ["همه", "دسته‌بندی‌ها", "برندها"])
        active = nav.select("a.admin-section-tab.active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["aria-current"], "page")
        self.assertEqual(active[0]["href"], reverse("dashboard:category-list"))
        # The active sidebar section is announced too.
        self.assertEqual(soup.select_one(".sidebar a.nav-item.active")["aria-current"], "true")

    def test_command_palette_index_uses_the_new_paths(self):
        self._login(self.owner)
        soup, _ = self._soup("dashboard")
        items = {a["data-title"]: a["data-path"] for a in soup.select("#adminV2CommandIndex a[data-search-item]")}
        self.assertEqual(items["همه کالاها"], "کالاها ← همه کالاها")
        self.assertEqual(items["پرداخت‌ها"], "فاکتورها و مالی ← پرداخت‌ها")
        self.assertEqual(items["قالب‌های آماده"], "فروشگاه ← قالب‌های آماده")
        self.assertEqual(items["گزارش رخدادها"], "گزارش‌ها ← گزارش رخدادها")
        self.assertIn("Ctrl K", soup.get_text())

    def test_each_role_only_sees_sections_and_tabs_it_can_open(self):
        """Every sidebar link and tab rendered for a role must lead somewhere that role
        is actually allowed to open — never a 403."""
        for user in (self.owner, self.administrator, self.catalog_manager, self.order_manager,
                     self.content_editor, self.analyst):
            self._login(user)
            soup, _ = self._soup("dashboard")
            hrefs = {a["href"] for a in soup.select(".sidebar nav.nav a.nav-item")}
            checked = set()
            for href in sorted(hrefs):
                response = self.client.get(href)
                self.assertNotEqual(response.status_code, 403, f"{user.username}: sidebar link {href}")
                if response.status_code != 200:
                    continue
                page = BeautifulSoup(response.content.decode(), "html.parser")
                for tab in page.select("a.admin-section-tab"):
                    if tab["href"] in checked:
                        continue
                    checked.add(tab["href"])
                    tab_response = self.client.get(tab["href"])
                    self.assertNotEqual(
                        tab_response.status_code, 403, f"{user.username}: tab {tab['href']}")

    def test_roles_do_not_see_tabs_they_lack_permission_for(self):
        self._login(self.content_editor)
        soup, _ = self._soup("page-list")
        tabs = {a["data-tab"] for a in soup.select("a.admin-section-tab")}
        self.assertIn("content", tabs)
        sections = {a["data-section"] for a in soup.select(".sidebar nav.nav a.nav-item")}
        self.assertNotIn("orders", sections)
        self.assertNotIn("products", sections)
        self.assertNotIn("settings", sections)

        # An order manager keeps the warehouse/reservation screens of their workflow in the
        # «کالاها» section, but not the catalog tabs they have no permission for.
        self._login(self.order_manager)
        response = self.client.get(reverse("dashboard:order-list"))
        page = BeautifulSoup(response.content.decode(), "html.parser")
        self.assertIn("orders", {a["data-section"] for a in page.select(".sidebar nav.nav a.nav-item")})
        products_href = page.select_one('.sidebar a[data-section="products"]')
        if products_href is not None:
            products_page = BeautifulSoup(self.client.get(products_href["href"]).content.decode(), "html.parser")
            product_tabs = {a["data-tab"] for a in products_page.select("a.admin-section-tab")}
            self.assertNotIn("products", product_tabs)
            self.assertNotIn("categories", product_tabs)

    def test_every_tab_destination_is_reachable_for_the_owner(self):
        self._login(self.owner)
        soup, _ = self._soup("dashboard")
        visited = 0
        for section in soup.select(".sidebar nav.nav a.nav-item"):
            page = BeautifulSoup(self.client.get(section["href"]).content.decode(), "html.parser")
            hrefs = [a["href"] for a in page.select("a.admin-section-tab")] or [section["href"]]
            for href in hrefs:
                response = self.client.get(href)
                self.assertIn(response.status_code, (200, 302), href)
                visited += 1
        self.assertEqual(visited, sum(len(section.tabs) for section in navigation.SECTIONS))

    def test_embedded_mode_hides_chrome_via_css(self):
        css = open("apps/dashboard/static/css/admin_v2.css", encoding="utf-8").read()
        self.assertIn("body.admin-v2-embedded .admin-section-tabs", css)
