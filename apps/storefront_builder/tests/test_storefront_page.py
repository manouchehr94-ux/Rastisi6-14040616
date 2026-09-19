"""Phase 1A — Universal Page Architecture. Required tests per the owner's
Part-by-part test plan:

A. StorefrontPage model
B. Migration/backfill
C. New version creation
D. Published -> Draft clone
E. Multi-page sections
F. stable_id uniqueness
G. Duplicate section
H. Publish
I. Restore
J. Discard
K. Tenant isolation

Written and read carefully this session; NOT executed (no Django runtime
available in this sandbox — see docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1A_REPORT.md).
"""

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase

from apps.storefront_builder.models import (
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(
        name="فروشگاه صفحات دوم", slug="sfb-page-test-other", admin_subdomain="sfb-page-test-other",
    )


ALL_PAGE_TYPES = {"home", "product_detail", "listing", "collection", "search", "cart"}


class StorefrontPageModelTests(TestCase):
    """A. StorefrontPage model."""

    def setUp(self):
        cache.clear()
        self.layout = StorefrontLayout.provision_for(_akhlaghi())

    def test_exactly_six_page_types_supported(self):
        self.assertEqual(set(StorefrontPage.PageType.values), ALL_PAGE_TYPES)

    def test_creating_a_version_creates_exactly_six_pages(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        self.assertEqual(version.pages.count(), 6)
        self.assertEqual(set(version.pages.values_list("page_type", flat=True)), ALL_PAGE_TYPES)

    def test_unique_page_type_per_version(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        with self.assertRaises(IntegrityError):
            StorefrontPage.objects.create(version=version, page_type=StorefrontPage.PageType.HOME)

    def test_ensure_version_pages_is_idempotent(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        self.assertEqual(version.pages.count(), 6)
        StorefrontPage.ensure_version_pages(version)  # must not raise, must not duplicate
        self.assertEqual(version.pages.count(), 6)

    def test_ensure_version_pages_fills_in_only_missing_types(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        version.pages.filter(page_type=StorefrontPage.PageType.CART).delete()
        self.assertEqual(version.pages.count(), 5)
        StorefrontPage.ensure_version_pages(version)
        self.assertEqual(version.pages.count(), 6)
        self.assertTrue(version.pages.filter(page_type=StorefrontPage.PageType.CART).exists())

    def test_page_tenant_ownership_resolves_through_version_layout_store(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        home = version.home_page()
        self.assertEqual(home.version.layout.store_id, _akhlaghi().pk)


class MultiPageSectionOwnershipTests(TestCase):
    """E. Multi-page sections — create sections on two different page
    types, clone the version, assert each section stays on the correct
    corresponding page."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_sections_on_two_different_pages_clone_onto_the_matching_pages(self):
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        listing = d1.pages.get(page_type=StorefrontPage.PageType.LISTING)

        home.sections.all().delete()
        home_section = StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        listing_section = StorefrontSection.objects.create(page=listing, section_key="rich_text", order=0)

        svc.publish(self.store)
        d2 = svc.get_or_create_draft(self.store)

        cloned_home = d2.home_page()
        cloned_listing = d2.pages.get(page_type=StorefrontPage.PageType.LISTING)

        self.assertTrue(cloned_home.sections.filter(stable_id=home_section.stable_id, section_key="hero_banner").exists())
        self.assertTrue(cloned_listing.sections.filter(stable_id=listing_section.stable_id, section_key="rich_text").exists())
        # cross-check: the home section must NOT have leaked onto listing,
        # nor vice versa.
        self.assertFalse(cloned_home.sections.filter(section_key="rich_text").exists())
        self.assertFalse(cloned_listing.sections.filter(section_key="hero_banner").exists())


class StableIdPageScopedUniquenessTests(TestCase):
    """F. stable_id uniqueness — allowed on corresponding pages across
    different versions; rejected twice within the same page."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_same_stable_id_allowed_on_corresponding_pages_across_versions(self):
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        home.sections.all().delete()
        section = StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        stable_id = section.stable_id

        svc.publish(self.store)
        d2 = svc.get_or_create_draft(self.store)
        cloned_home = d2.home_page()

        self.assertTrue(cloned_home.sections.filter(stable_id=stable_id).exists())
        self.assertTrue(home.sections.filter(stable_id=stable_id).exists())

    def test_duplicate_stable_id_rejected_within_the_same_page(self):
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        home.sections.all().delete()
        a = StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        with self.assertRaises(IntegrityError):
            StorefrontSection.objects.create(page=home, section_key="rich_text", order=1, stable_id=a.stable_id)

    def test_duplicate_stable_id_allowed_across_two_different_pages_of_the_same_version(self):
        """Distinct from version-scoping: two DIFFERENT pages of the SAME
        version can legitimately share a stable_id without violating the
        (page, stable_id) constraint, since they are different page rows."""
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        listing = d1.pages.get(page_type=StorefrontPage.PageType.LISTING)
        home.sections.all().delete()
        a = StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        # must NOT raise.
        StorefrontSection.objects.create(page=listing, section_key="rich_text", order=0, stable_id=a.stable_id)


class SectionDuplicateStaysOnSamePageTests(TestCase):
    """G. Duplicate section — receives new stable_id and remains on same page."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.urls import reverse
        from django.utils import timezone

        from apps.stores.models import StoreMembership

        User = get_user_model()
        host = "sfb-page-dup-test.rastisi.localhost"
        self.store.admin_subdomain = host.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="page_dup_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=host)
        self.client.login(username="page_dup_owner", password="pass12345")
        self.reverse = reverse
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.home_page().sections.all().delete()

    def test_duplicate_gets_new_stable_id_and_stays_on_same_page(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        home = self.draft.home_page()
        section = StorefrontSection.objects.create(page=home, section_key="rich_text", order=0)

        self.client.post(self.reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))

        duplicate = home.sections.filter(section_key="rich_text").exclude(pk=section.pk).get()
        self.assertNotEqual(duplicate.stable_id, section.stable_id)
        self.assertEqual(duplicate.page_id, home.pk)


class PublishActivatesCompletePageSetTests(TestCase):
    """H. Publish — exposes the complete page set atomically."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_publish_makes_all_pages_and_their_sections_live_together(self):
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        listing = d1.pages.get(page_type=StorefrontPage.PageType.LISTING)
        home.sections.all().delete()
        StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        StorefrontSection.objects.create(page=listing, section_key="rich_text", order=0)

        published = svc.publish(self.store)

        self.assertEqual(published.pages.count(), 6)
        published_home = published.pages.get(page_type=StorefrontPage.PageType.HOME)
        published_listing = published.pages.get(page_type=StorefrontPage.PageType.LISTING)
        self.assertTrue(published_home.sections.filter(section_key="hero_banner").exists())
        self.assertTrue(published_listing.sections.filter(section_key="rich_text").exists())

    def test_publish_is_a_single_pointer_swap_not_a_per_page_operation(self):
        """There must be no independent per-page publish pointer — only
        StorefrontLayout.published_version, exactly as before Phase 1A."""
        layout_fields = {f.name for f in StorefrontLayout._meta.get_fields()}
        self.assertIn("published_version", layout_fields)
        self.assertNotIn("published_home", layout_fields)
        self.assertNotIn("published_product", layout_fields)
        self.assertNotIn("published_cart", layout_fields)


class RestoreRecreatesCompletePageSetTests(TestCase):
    """I. Restore — recreates all six pages and their compositions."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_restoring_an_archived_version_recreates_all_pages(self):
        d1 = svc.get_or_create_draft(self.store)
        home = d1.home_page()
        home.sections.all().delete()
        StorefrontSection.objects.create(page=home, section_key="hero_banner", order=0)
        v1 = svc.publish(self.store)

        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

        restored = svc.restore_version(self.store, v1.pk)
        self.assertEqual(restored.pages.count(), 6)
        self.assertTrue(restored.home_page().sections.filter(section_key="hero_banner").exists())


class DiscardDoesNotDamagePublishedPagesTests(TestCase):
    """J. Discard — removes Draft pages/sections/placements without
    damaging Published version/pages/assets."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_discard_removes_only_draft_pages_keeps_published_intact(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.home_page().sections.all().delete()
        StorefrontSection.objects.create(page=d1.home_page(), section_key="hero_banner", order=0)
        published = svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        d2_pk = d2.pk

        svc.discard_draft(self.store)

        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=d2_pk).exists())
        published.refresh_from_db()
        self.assertEqual(published.pages.count(), 6)
        self.assertTrue(published.home_page().sections.filter(section_key="hero_banner").exists())


class PageTenantIsolationTests(TestCase):
    """K. Tenant isolation — Store A cannot access/edit Store B page or section."""

    def setUp(self):
        cache.clear()
        self.store_a = _akhlaghi()
        self.store_b = _other_store()

    def test_page_of_store_b_not_reachable_via_store_a_layout(self):
        draft_a = svc.get_or_create_draft(self.store_a)
        draft_b = svc.get_or_create_draft(self.store_b)

        self.assertFalse(draft_a.pages.filter(pk__in=draft_b.pages.values_list("pk", flat=True)).exists())

    def test_get_scoped_section_rejects_a_section_belonging_to_another_store(self):
        from django.test import Client
        from django.urls import reverse

        from apps.storefront_builder.views import _get_scoped_section

        draft_b = svc.get_or_create_draft(self.store_b)
        home_b = draft_b.home_page()
        home_b.sections.all().delete()
        foreign_section = StorefrontSection.objects.create(page=home_b, section_key="rich_text", order=0)

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.stores.models import StoreMembership

        User = get_user_model()
        host = "sfb-page-isolation-test.rastisi.localhost"
        self.store_a.admin_subdomain = host.split(".")[0]
        self.store_a.save(update_fields=["admin_subdomain"])
        staff = User.objects.create_user(username="page_isolation_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_a, user=staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=host)
        client.login(username="page_isolation_owner", password="pass12345")

        resp = client.post(reverse("dashboard:storefront-builder-section-toggle", args=[foreign_section.pk]))
        self.assertEqual(resp.status_code, 404)
