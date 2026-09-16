"""P5-W4A — CMS content pages converge onto the canonical universal
storefront shell (``storefront_shell.html`` +
``build_universal_storefront_context(..., shell_only=True)``), while the
page's own domain body/SEO ownership (title, summary, body,
``effective_seo_title``/``effective_seo_description``) and its existing
tenant/publication scoping (already correct — ``page_detail`` already
resolves ``store`` via ``resolve_store_for_storefront`` and filters
``PUBLISHED``-only) stay exactly as they are. Reuses the same real
two-Store/verified-``StoreDomain``/distinct-``HTTP_HOST`` fixture pattern as
``apps.customers.tests.test_wishlist_store_isolation``/
``test_wishlist_shell_convergence`` — no ``request.store`` mocking."""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import ContentPage, FooterSettings
from apps.core.models import ShopSettings
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

HOST_A = "cms-a.example.com"
HOST_B = "cms-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


def _publish_with_header_variant(store, header_variant):
    draft = svc.get_or_create_draft(store)
    draft.header_config = {**(draft.header_config or {}), "header_variant": header_variant}
    draft.save(update_fields=["header_config"])
    svc.publish(store)


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class CmsPageShellConvergenceTwoStoreTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="cmssc-store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.page_a = ContentPage.objects.create(
            store=self.store_a, title="درباره ما", slug="about-cmssc", body="متن درباره ما",
            summary="خلاصه", seo_title="About SEO Title", seo_description="About SEO Description",
            status=ContentPage.Status.PUBLISHED, published_at=timezone.now(),
        )
        self.draft_page_a = ContentPage.objects.create(
            store=self.store_a, title="پیش‌نویس", slug="draft-cmssc", body="پیش‌نویس",
            status=ContentPage.Status.DRAFT,
        )

        _publish_with_header_variant(self.store_a, "editorial_row")
        _publish_with_header_variant(self.store_b, "community_shortcuts")

    def _get(self, host, slug):
        return self.client.get(reverse("content:page-detail", args=[slug]), HTTP_HOST=host)

    # A — canonical Header/Footer present.
    def test_canonical_shell_templates_present_on_published_page(self):
        resp = self._get(HOST_A, "about-cmssc")
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_shell.html", template_names)
        self.assertIn("storefront_builder/partials/global_header/editorial_row.html", template_names)

    # P5-W4A review repair (IMPORTANT 4 follow-up) — the strengthened
    # Browser QA discovered that converging onto storefront_shell.html
    # renders the global Header/Footer/Bottom-Nav partials but, unlike
    # catalog/cart's own storefront_shell.html templates (which each link
    # it themselves via their own ``extra_css`` block), page_detail.html
    # never linked the stylesheet that actually styles those partials
    # (``storefront_builder.css``) — so the chrome rendered, unstyled, with
    # no CSS-driven visibility rules (e.g. the Bottom Nav's mobile-only
    # ``@media(max-width:680px)`` rule) ever applying.
    def test_canonical_shell_stylesheet_linked(self):
        resp = self._get(HOST_A, "about-cmssc")
        self.assertContains(resp, "css/storefront_builder.css")

    # B — body/summary/title remain exact CMS content.
    def test_body_and_title_preserved(self):
        resp = self._get(HOST_A, "about-cmssc")
        self.assertContains(resp, "درباره ما")
        self.assertContains(resp, "متن درباره ما")
        self.assertContains(resp, "خلاصه")

    # C/D — SEO ownership preserved.
    def test_seo_title_and_description_preserved(self):
        resp = self._get(HOST_A, "about-cmssc")
        self.assertContains(resp, "About SEO Title")
        self.assertContains(resp, "About SEO Description")

    # No noindex added — CMS pages stay indexable, unlike Wishlist/account.
    def test_no_noindex_added(self):
        resp = self._get(HOST_A, "about-cmssc")
        self.assertNotContains(resp, 'name="robots" content="noindex')

    # E — DRAFT page remains inaccessible.
    def test_draft_page_returns_404(self):
        resp = self._get(HOST_A, "draft-cmssc")
        self.assertEqual(resp.status_code, 404)

    # F — Store A's page cannot resolve on Store B's host.
    def test_store_a_page_404s_on_store_b_host(self):
        resp = self._get(HOST_B, "about-cmssc")
        self.assertEqual(resp.status_code, 404)

    # G — shell isolation between Stores.
    def test_shell_isolation_between_stores(self):
        page_b = ContentPage.objects.create(
            store=self.store_b, title="About B", slug="about-b-cmssc", body="Body B",
            status=ContentPage.Status.PUBLISHED, published_at=timezone.now(),
        )
        template_names_a = [t.name for t in self._get(HOST_A, "about-cmssc").templates if t.name]
        self.assertIn("storefront_builder/partials/global_header/editorial_row.html", template_names_a)
        self.assertNotIn("storefront_builder/partials/global_header/community_shortcuts.html", template_names_a)

        template_names_b = [t.name for t in self._get(HOST_B, "about-b-cmssc").templates if t.name]
        self.assertIn("storefront_builder/partials/global_header/community_shortcuts.html", template_names_b)
        self.assertNotIn("storefront_builder/partials/global_header/editorial_row.html", template_names_b)


class CmsPageShellConvergenceFallbackTests(TestCase):
    """H — a Store with a published ContentPage but NO published universal
    storefront layout: the page still 200s with its domain body;
    storefront_shell.html falls through to base.html via block.super."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.page = ContentPage.objects.create(
            store=self.store, title="بدون انتشار", slug="no-publish-cmssc",
            body="بدنه بدون Storefront منتشرشده",
            status=ContentPage.Status.PUBLISHED, published_at=timezone.now(),
        )
        # Deliberately no get_or_create_draft/publish call.

    def test_page_renders_without_published_layout(self):
        resp = self.client.get(reverse("content:page-detail", args=["no-publish-cmssc"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "بدون انتشار")
        self.assertContains(resp, "بدنه بدون Storefront منتشرشده")
