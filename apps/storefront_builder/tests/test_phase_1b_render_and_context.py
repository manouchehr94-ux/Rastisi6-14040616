"""Phase 1B — Parts A/B/F: build_page_render_items / build_render_items
compatibility wrapper, and build_universal_storefront_context.

Covers required scenarios 8 (header/footer/appearance context comes from
the same version on all six page types), 12 (empty non-home StorefrontPage
still preserves existing commerce page functionality — asserted at the
service level here; route-level assertions are in
test_phase_1b_routes.py), and regression coverage for the existing
build_render_items(version, store) signature (scenario 14 — existing Home
rendering must not regress).

Written and read carefully this session; NOT EXECUTED (no Django runtime
available in this sandbox).
"""

from django.core.cache import cache
from django.test import TestCase

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_page_render_items, build_render_items
from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class _FakeRequest:
    """Minimal request stand-in — build_universal_storefront_context only
    ever sets one attribute on it (storefront_appearance_version)."""


class BuildRenderItemsBackwardCompatibilityTests(TestCase):
    """14 — existing Home rendering must not regress: build_render_items(version, store)
    keeps working exactly as before Phase 1B (both existing production
    callers, and the entire pre-existing test_render_service.py suite,
    depend on this)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_build_render_items_still_returns_home_pages_sections(self):
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)

        items = build_render_items(draft, self.store)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["section"].section_key, "hero_banner")

    def test_build_render_items_is_now_a_thin_wrapper_around_build_page_render_items(self):
        draft = svc.get_or_create_draft(self.store)
        home = draft.home_page()
        home.sections.all().delete()
        StorefrontSection.objects.create(page=home, section_key="rich_text", order=0)

        via_version = build_render_items(draft, self.store)
        via_page = build_page_render_items(home, self.store)
        self.assertEqual(
            [i["section"].pk for i in via_version],
            [i["section"].pk for i in via_page],
        )


class BuildPageRenderItemsForNonHomePagesTests(TestCase):
    """12 — a genuinely empty non-home StorefrontPage (no rows at all)
    renders zero items, no crash, no fabricated content — the underlying
    safety property `build_page_render_items` must always have.

    Phase 5 update: as of the default-composition feature, a freshly
    bootstrapped store's five non-home pages are no longer empty by
    default (see `bootstrap_service.apply_default_non_home_sections`) —
    that is Phase 5's own explicit, documented default content, not
    "fabricated" in the sense this checkpoint originally guarded against
    (silently synthesizing content for a page a merchant deliberately
    emptied). These tests now cover both: the still-true "empty in, empty
    out" mechanism, and the new "first draft is never empty" contract."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_explicitly_emptied_non_home_page_returns_empty_list(self):
        draft = svc.get_or_create_draft(self.store)
        for page_type in (
            StorefrontPage.PageType.PRODUCT_DETAIL, StorefrontPage.PageType.LISTING,
            StorefrontPage.PageType.COLLECTION, StorefrontPage.PageType.SEARCH,
            StorefrontPage.PageType.CART,
        ):
            draft.pages.get(page_type=page_type).sections.all().delete()
        published = svc.publish(self.store)
        for page_type in (
            StorefrontPage.PageType.PRODUCT_DETAIL, StorefrontPage.PageType.LISTING,
            StorefrontPage.PageType.COLLECTION, StorefrontPage.PageType.SEARCH,
            StorefrontPage.PageType.CART,
        ):
            page = published.pages.get(page_type=page_type)
            items = build_page_render_items(page, self.store)
            self.assertEqual(items, [])

    def test_first_draft_non_home_pages_are_not_empty_by_default(self):
        """Phase 5: برخلافِ صفحه‌ی اصلی، این پنج صفحه دیگر با یک بومِ
        خالی شروع نمی‌کنند."""
        draft = svc.get_or_create_draft(self.store)
        published = svc.publish(self.store)
        for page_type in (
            StorefrontPage.PageType.PRODUCT_DETAIL, StorefrontPage.PageType.LISTING,
            StorefrontPage.PageType.COLLECTION, StorefrontPage.PageType.SEARCH,
            StorefrontPage.PageType.CART,
        ):
            page = published.pages.get(page_type=page_type)
            items = build_page_render_items(page, self.store)
            self.assertGreater(len(items), 0, page_type)

    def test_non_home_page_with_a_section_renders_it_correctly(self):
        draft = svc.get_or_create_draft(self.store)
        listing_page = draft.pages.get(page_type=StorefrontPage.PageType.LISTING)
        listing_page.sections.all().delete()
        StorefrontSection.objects.create(page=listing_page, section_key="trust_features", order=0)
        published = svc.publish(self.store)
        published_listing = published.pages.get(page_type=StorefrontPage.PageType.LISTING)

        items = build_page_render_items(published_listing, self.store)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["section"].section_key, "trust_features")


class BuildUniversalStorefrontContextTests(TestCase):
    """8 — header/footer/appearance context comes from the same version on
    all six page types. Also covers the unresolved (never-published)
    shape contract."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_a_store_that_never_published_gets_the_engine_native_default_context(self):
        """There is no "unresolved" shape any more: the first public request provisions the deterministic engine default."""
        request = _FakeRequest()
        context = build_universal_storefront_context(request, self.store, StorefrontPage.PageType.HOME)
        self.assertNotIn("uses_universal_shell", context)
        version = context["storefront_version"]
        self.assertIsNotNone(version)
        self.assertEqual(version.status, "published")
        self.assertIsNotNone(context["storefront_page"])
        self.assertEqual(context["page_type"], StorefrontPage.PageType.HOME)
        self.assertIsNotNone(context["layout_header_config"])
        self.assertIsNotNone(context["layout_footer_config"])
        self.assertTrue(context["render_items"])
        self.assertEqual(request.storefront_appearance_version.pk, version.pk)

    def test_all_six_page_types_share_the_same_header_footer_appearance_source(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "announcement_text": "SHARED-MARKER"}
        draft.save(update_fields=["header_config"])
        published = svc.publish(self.store)

        page_types = [
            StorefrontPage.PageType.HOME, StorefrontPage.PageType.PRODUCT_DETAIL,
            StorefrontPage.PageType.LISTING, StorefrontPage.PageType.COLLECTION,
            StorefrontPage.PageType.SEARCH, StorefrontPage.PageType.CART,
        ]
        for page_type in page_types:
            request = _FakeRequest()
            context = build_universal_storefront_context(request, self.store, page_type)
            self.assertEqual(context["storefront_version"].pk, published.pk)
            self.assertEqual(context["layout_header_config"]["announcement_text"], "SHARED-MARKER")
            self.assertEqual(request.storefront_appearance_version.pk, published.pk)

    def test_context_sets_storefront_appearance_version_for_non_home_pages_too(self):
        """This is the concrete mechanism that makes global color/font/family
        tokens (via apps.core.context_processors) consistent across all six
        routes once a store has published — before Phase 1B, only home()
        ever set this attribute."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        request = _FakeRequest()
        build_universal_storefront_context(request, self.store, StorefrontPage.PageType.CART)
        self.assertTrue(hasattr(request, "storefront_appearance_version"))
