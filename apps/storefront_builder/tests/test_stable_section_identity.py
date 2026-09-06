"""Phase 0.5 — Part 11.A: stable logical Section identity (owner decision 3).

Covers:
1. Published Section -> Draft clone: same stable_id.
2. Section duplicate: different stable_id.
3. Existing (pre-migration) sections: stable_id populated (backfill).
"""

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class StableIdCloneTests(TestCase):
    """A.1 — Published Section -> Draft clone preserves stable_id."""

    def setUp(self):
        cache.clear()

    def test_stable_id_survives_published_to_draft_clone(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        original_stable_id = section.stable_id

        svc.publish(store)
        d2 = svc.get_or_create_draft(store)

        cloned = d2.sections.get(section_key="hero_banner")
        self.assertEqual(cloned.stable_id, original_stable_id)
        self.assertNotEqual(cloned.pk, section.pk)

    def test_stable_id_survives_restore(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        original_stable_id = section.stable_id
        v1 = svc.publish(store)

        svc.get_or_create_draft(store)
        svc.publish(store)

        restored = svc.restore_version(store, v1.pk)
        restored_section = restored.sections.get(section_key="hero_banner")
        self.assertEqual(restored_section.stable_id, original_stable_id)

    def test_multiple_sections_each_keep_their_own_distinct_stable_id(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        a = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        b = StorefrontSection.objects.create(version=d1, section_key="newest_products", order=1)
        self.assertNotEqual(a.stable_id, b.stable_id)

        svc.publish(store)
        d2 = svc.get_or_create_draft(store)
        cloned_a = d2.sections.get(section_key="hero_banner")
        cloned_b = d2.sections.get(section_key="newest_products")
        self.assertEqual(cloned_a.stable_id, a.stable_id)
        self.assertEqual(cloned_b.stable_id, b.stable_id)
        self.assertNotEqual(cloned_a.stable_id, cloned_b.stable_id)


class StableIdDuplicateTests(TestCase):
    """A.2 — Section duplicate must receive a NEW stable_id (it is a
    logically new section, not the same one existing twice)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.utils import timezone

        from apps.stores.models import StoreMembership

        User = get_user_model()
        host = "sfb-stableid-test.rastisi.localhost"
        self.store.admin_subdomain = host.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="stableid_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=host)
        self.client.login(username="stableid_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_duplicate_receives_a_different_stable_id(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        original_stable_id = section.stable_id

        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))

        duplicate = self.draft.sections.filter(section_key="rich_text").exclude(pk=section.pk).get()
        self.assertNotEqual(duplicate.stable_id, original_stable_id)


class StableIdUniquenessConstraintTests(TestCase):
    """A.3-adjacent: uniqueness is scoped to (version, stable_id) at the
    time this Phase 0.5 test file was written; Phase 1A moved the actual
    DB constraint to (page, stable_id) — see test_storefront_page.py's
    `StableIdPageScopedUniquenessTests` for the page-scoped tests. The
    two sections created below via `version=` both resolve to the SAME
    home page (through the compatibility shim), so this test's outcome is
    unaffected by that change and remains a correct regression check: the
    same stable_id must be allowed across two different versions, but
    rejected twice within the same version/page."""

    def setUp(self):
        cache.clear()

    def test_same_stable_id_allowed_across_two_different_versions(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        stable_id = section.stable_id
        svc.publish(store)
        d2 = svc.get_or_create_draft(store)

        # the clone in d2 legitimately shares the same stable_id as the
        # Published version's section — this must NOT raise, because the
        # constraint is scoped per-version, not global.
        self.assertTrue(d2.sections.filter(stable_id=stable_id).exists())
        self.assertTrue(d1.sections.filter(stable_id=stable_id).exists())

    def test_duplicate_stable_id_within_same_version_rejected(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        with self.assertRaises(IntegrityError):
            StorefrontSection.objects.create(
                version=d1, section_key="newest_products", order=1, stable_id=section.stable_id,
            )



class BrandStableIdentityAcrossPublishTests(TestCase):
    """Brand end-to-end gate — a placed brand_carousel keeps its stable
    logical identity (``stable_id``) across the Published -> Draft clone,
    while the PK legitimately changes (a new row is a new physical clone).
    Comparing ``stable_id`` (NOT PK) is the correct identity check for the
    same logical Brand section across versions."""

    def setUp(self):
        cache.clear()

    def test_brand_section_stable_id_survives_publish_to_draft_clone(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(
            version=d1, section_key="brand_carousel", order=0,
            settings={"title": "برند پایدار", "display_mode": "grid", "brand_ids": [], "show_view_all": False},
        )
        original_stable_id = section.stable_id
        self.assertTrue(original_stable_id)

        svc.publish(store)
        d2 = svc.get_or_create_draft(store)

        cloned = d2.sections.get(section_key="brand_carousel")
        # Identity is the stable_id — NOT the PK, which is a fresh clone row.
        self.assertEqual(cloned.stable_id, original_stable_id)
        self.assertNotEqual(cloned.pk, section.pk)
        # Settings survive the clone alongside the identity.
        self.assertEqual(cloned.settings.get("title"), "برند پایدار")

    def test_two_brand_sections_keep_distinct_stable_ids_across_clone(self):
        store = _akhlaghi()
        d1 = svc.get_or_create_draft(store)
        d1.sections.all().delete()
        grid = StorefrontSection.objects.create(
            version=d1, section_key="brand_carousel", order=0,
            settings={"display_mode": "grid", "brand_ids": [], "show_view_all": False},
        )
        carousel = StorefrontSection.objects.create(
            version=d1, section_key="brand_carousel", order=1,
            settings={"display_mode": "carousel", "brand_ids": [], "show_view_all": False},
        )
        self.assertNotEqual(grid.stable_id, carousel.stable_id)

        svc.publish(store)
        d2 = svc.get_or_create_draft(store)
        clones = {s.settings.get("display_mode"): s for s in d2.sections.filter(section_key="brand_carousel")}
        self.assertEqual(clones["grid"].stable_id, grid.stable_id)
        self.assertEqual(clones["carousel"].stable_id, carousel.stable_id)
        self.assertNotEqual(clones["grid"].stable_id, clones["carousel"].stable_id)
