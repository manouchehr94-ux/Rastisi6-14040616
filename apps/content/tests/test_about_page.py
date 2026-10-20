"""RS-06 — the «درباره ما» page on the existing content system: one-click Draft creation (never auto-published), idempotent,
store-scoped, and the price-inquiry CTA resolves to it (200) only when it is published."""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, PriceMode, Product, Vendor
from apps.content import about_page
from apps.content.models import ContentPage
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "aboutpg.rastisi.localhost"


class ServiceTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_ensure_creates_a_footer_linked_draft_and_is_idempotent(self):
        page, created, published = about_page.ensure_about_page(self.store)
        self.assertTrue(created)
        self.assertFalse(published)
        self.assertEqual((page.slug, page.status, page.store_id), ("about-us", ContentPage.Status.DRAFT, self.store.pk))
        self.assertTrue(page.show_in_footer)
        self.assertIn("متنِ نمایشی", page.body)
        page.body = "<p>متن واقعی مالک</p>"
        page.save()
        again, created2, _ = about_page.ensure_about_page(self.store)
        self.assertEqual((again.pk, created2, again.body), (page.pk, False, "<p>متن واقعی مالک</p>"))
        self.assertEqual(ContentPage.objects.filter(store=self.store, slug="about-us").count(), 1)

    def test_publish_is_explicit_and_state_follows(self):
        self.assertEqual(about_page.about_page_state(self.store)["state"], "missing")
        about_page.ensure_about_page(self.store)
        self.assertEqual(about_page.about_page_state(self.store)["state"], "draft")
        about_page.ensure_about_page(self.store, publish=True)
        self.assertEqual(about_page.about_page_state(self.store)["state"], "published")

    def test_other_stores_page_is_never_this_stores_page(self):
        other = Store.objects.create(name="B", slug="about-other", status=Store.Status.ACTIVE)
        about_page.ensure_about_page(other, publish=True)
        self.assertEqual(about_page.about_page_state(self.store)["state"], "missing")

    def test_command_defaults_to_a_dry_run(self):
        out = StringIO()
        call_command("ensure_about_page", "--store", "akhlaghi", stdout=out)
        self.assertFalse(ContentPage.objects.filter(store=self.store, slug="about-us").exists())
        call_command("ensure_about_page", "--store", "akhlaghi", "--create", stdout=out)
        self.assertEqual(about_page.about_page_state(self.store)["state"], "draft")
        call_command("ensure_about_page", "--store", "akhlaghi", "--publish", stdout=out)
        self.assertEqual(about_page.about_page_state(self.store)["state"], "published")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class DashboardTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123400001", password="pass12345")
        self.m = StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123400001", password="pass12345")

    def test_empty_pages_list_offers_the_one_click_draft_and_it_never_publishes(self):
        r = self.client.get(reverse("dashboard:page-list"))
        self.assertContains(r, "هنوز ساخته نشده است")
        self.assertContains(r, reverse("dashboard:page-create-about"))
        r2 = self.client.post(reverse("dashboard:page-create-about"))
        page = ContentPage.objects.get(store=self.store, slug="about-us")
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(r2["Location"], reverse("dashboard:page-edit", args=[page.pk]))
        self.assertEqual(page.status, ContentPage.Status.DRAFT)
        self.assertContains(self.client.get(reverse("dashboard:page-list")), "هنوز منتشر نشده است")
        self.client.post(reverse("dashboard:page-publish", args=[page.pk]))
        self.assertNotContains(self.client.get(reverse("dashboard:page-list")), reverse("dashboard:page-create-about"))

    def test_get_is_not_allowed_and_csrf_is_enforced(self):
        self.assertEqual(self.client.get(reverse("dashboard:page-create-about")).status_code, 405)
        c = Client(HTTP_HOST=HOST, enforce_csrf_checks=True)
        c.login(username="09123400001", password="pass12345")
        self.assertEqual(c.post(reverse("dashboard:page-create-about")).status_code, 403)
        self.assertFalse(ContentPage.objects.filter(slug="about-us").exists())

    def test_a_role_without_content_permission_cannot_create_it(self):
        analyst = User.objects.create_user(username="09123400002", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="09123400002", password="pass12345")
        self.assertEqual(self.client.post(reverse("dashboard:page-create-about")).status_code, 403)
        self.assertFalse(ContentPage.objects.filter(slug="about-us").exists())


class InquiryCtaTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        v = Vendor.objects.create(store=self.store, name="V", slug="v-ab")
        c = Category.objects.create(store=self.store, name="C", slug="c-ab")
        self.p = Product.objects.create(
            store=self.store, vendor=v, category=c, name="استعلامی", slug="inq-ab", sku="AB1", price=Decimal("1000"),
            stock=3, price_mode_override=PriceMode.INQUIRY,
        )

    def cta(self, html):
        return 'class="btn btn-primary pdp-inquiry-cta" href="/pages/about-us/"' in html

    def test_cta_is_absent_with_an_honest_note_until_the_page_is_published(self):
        html = self.client.get(reverse("catalog:product-detail", args=[self.p.slug])).content.decode()
        self.assertFalse(self.cta(html))
        self.assertIn("راه ارتباطی برای استعلام هنوز", html)
        about_page.ensure_about_page(self.store)  # Draft only
        html = self.client.get(reverse("catalog:product-detail", args=[self.p.slug])).content.decode()
        self.assertFalse(self.cta(html))
        self.assertEqual(self.client.get("/pages/about-us/").status_code, 404)

    def test_published_page_makes_the_cta_a_real_200_and_it_appears_in_the_footer(self):
        about_page.ensure_about_page(self.store, publish=True)
        html = self.client.get(reverse("catalog:product-detail", args=[self.p.slug])).content.decode()
        self.assertTrue(self.cta(html), html[html.find("pdp-inquiry"):][:300])
        self.assertEqual(self.client.get("/pages/about-us/").status_code, 200)
        self.assertIn('href="/pages/about-us/"', self.client.get(reverse("catalog:product-list")).content.decode())

    def test_buying_an_inquiry_product_stays_blocked(self):
        about_page.ensure_about_page(self.store, publish=True)
        r = self.client.post(reverse("cart:add", args=[self.p.slug]), {"quantity": 1})
        self.assertNotEqual(r.status_code, 500)
        from apps.cart.models import CartItem
        self.assertFalse(CartItem.objects.filter(product=self.p).exists())


class FooterShowsFlaggedPagesAlongsideMenusTests(TestCase):
    """Root cause found in browser QA: when a footer menu is configured the flagged «دسترسی سریع»/«خدمات» pages (About, Contact)
    were silently dropped. They are now appended to the same column, so a published About page is findable from the footer."""

    TEMPLATES = (
        "storefront_builder/partials/global_footer/_shared/nav_column.html",
        "storefront_builder/partials/page_shell_footer.html",
    )

    def _ctx(self, store):
        about_page.ensure_about_page(store, publish=True)
        pages = list(ContentPage.objects.filter(store=store, slug="about-us"))
        menu = {"title": "منو", "items": [{"title": "لینک", "url": "https://example.com/x", "children": [], "open_in_new_tab": False}]}
        return {
            "NAV_FOOTER_1": menu, "NAV_FOOTER_2": menu,
            "footer_pages_quick_access": pages, "footer_pages_customer_service": pages,
            "footer_config": {"show_quick_links": True, "responsive": {}},
        }

    def test_about_link_is_in_the_footer_even_with_footer_menus(self):
        from django.template.loader import render_to_string

        store = Store.objects.get(slug="akhlaghi")
        ctx = self._ctx(store)
        for name in self.TEMPLATES:
            html = render_to_string(name, ctx)
            self.assertIn('href="/pages/about-us/"', html, name)
            self.assertIn("https://example.com/x", html, name)  # the merchant's menu itself is untouched

    def test_without_menus_behaviour_is_unchanged(self):
        from django.template.loader import render_to_string

        store = Store.objects.get(slug="akhlaghi")
        ctx = self._ctx(store)
        ctx["NAV_FOOTER_1"] = ctx["NAV_FOOTER_2"] = None
        html = render_to_string(self.TEMPLATES[0], ctx)
        self.assertEqual(html.count('href="/pages/about-us/"'), 2)  # one per column group, as before


class MobileDrawerReachesFlaggedPagesTests(TestCase):
    def test_drawer_lists_the_flagged_pages_without_a_menu(self):
        from django.template.loader import render_to_string

        store = Store.objects.get(slug="akhlaghi")
        page, _, _ = about_page.ensure_about_page(store, publish=True)
        html = render_to_string("partials/mobile_nav_drawer.html", {"NAV_HEADER": None, "NAV_MOBILE": None, "footer_pages_quick_access": [page]})
        self.assertIn('href="/pages/about-us/"', html)
        self.assertNotIn("mobile-nav-drawer__pages", render_to_string("partials/mobile_nav_drawer.html", {"NAV_HEADER": None, "NAV_MOBILE": None}))
