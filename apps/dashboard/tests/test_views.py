from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class DashboardViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121121001", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121001", password="pass12345")

    def test_dashboard_renders_with_active_nav(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "داشبورد")
        self.assertContains(response, 'data-page="dashboard"')
        self.assertContains(response, "روند فروش")

    def test_dashboard_shows_catalog_health_tiles_linking_to_filtered_product_lists(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "سلامتِ کاتالوگ")
        product_list_url = reverse("dashboard:product-list")
        self.assertContains(response, f'href="{product_list_url}?status=active"')
        self.assertContains(response, f'href="{product_list_url}?status=draft"')
        self.assertContains(response, f'href="{product_list_url}?status=out"')
        self.assertContains(response, f'href="{product_list_url}?health=no_images"')
        self.assertContains(response, f'href="{product_list_url}?health=no_seo"')
        self.assertContains(response, f'href="{product_list_url}?health=missing_variants"')

    def test_dashboard_shows_all_nine_sidebar_sections(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        for label in [
            "داشبورد", "سفارش‌ها", "کالاها", "فاکتورها و مالی", "مشتریان",
            "بازاریابی", "فروشگاه", "گزارش‌ها", "تنظیمات",
        ]:
            self.assertContains(response, label)

    def test_dashboard_shows_store_status(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "فعال")
        self.assertContains(response, 'data-store-status="active"')


class CollapsibleSidebarTests(TestCase):
    """چک‌های ساختاریِ سایدبارِ تخت (دو سطحی) — نُه حوزه‌ی کاری بدون آکاردئون،
    مخفی‌شدنِ بج‌های صفر، و درِ کشویی موبایل."""

    def setUp(self):
        self.staff = User.objects.create_user(username="09121121003", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121003", password="pass12345")

    def test_sidebar_is_flat_with_nine_sections_and_no_accordion(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        for section_key in ["dashboard", "orders", "products", "finance", "customers",
                            "marketing", "store", "reports", "settings"]:
            self.assertContains(response, f'data-section="{section_key}"')
        for legacy in ("nav-group-head", "nav-group-body", "sidebarNav", 'data-group='):
            self.assertNotContains(response, legacy)
        self.assertEqual(response.content.decode().count('data-section="'), 9)

    def test_zero_badges_are_not_rendered(self):
        # فروشگاهِ akhlaghi در fixture پایه هیچ محصول/سفارشِ در انتظاری ندارد.
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertNotContains(response, 'badge-nav">0</span>')

    def test_nonzero_product_badge_is_rendered(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        store = Store.objects.get(slug="akhlaghi")
        category = Category.objects.create(store=store, name="پوشاک", slug="clothing-sidebar-test")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="vendor-sidebar-test")
        Product.objects.create(
            store=store, vendor=vendor, category=category, name="تیشرت", slug="tshirt-sidebar-test",
            sku="SKU-SB1", price=Decimal("100000"),
        )
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertContains(response, '<span class="badge-nav">1</span>')  # on the «همه کالاها» tab

    def test_nav_badges_shown_on_non_dashboard_pages_too(self):
        # قبلاً nav_product_count/nav_pending_order_count فقط در ویوِ خودِ
        # داشبورد محاسبه می‌شدند؛ اکنون context processor روی هر صفحه‌ای
        # که request.store دارد آن‌ها را فراهم می‌کند.
        response = self.client.get(reverse("dashboard:product-list"))
        self.assertIn("nav_product_count", response.context)

    def test_mobile_backdrop_present(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "sidebar-backdrop")

    def test_sidebar_footer_has_back_to_rastisi_and_user_card(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertContains(response, "sidebar-foot")
        self.assertContains(response, "بازگشت به راستیسی")
        self.assertContains(response, "card-mini")


class SalesChartPartialViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121121002", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121121002", password="pass12345")

    def test_week_range_returns_svg(self):
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "week"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")

    def test_invalid_range_falls_back_without_error(self):
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "nonsense"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<svg")

    def test_anonymous_cannot_fetch_chart(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:sales-chart"), {"range": "week"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)