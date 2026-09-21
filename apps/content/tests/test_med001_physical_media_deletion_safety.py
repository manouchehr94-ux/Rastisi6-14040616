"""MED-001 (P0) — Shared media PHYSICAL-FILE deletion bypass.

A single physical storage path for reusable Storefront media (Hero/Banner/
Story) can be pointed at by MULTIPLE independent references at once:

* multiple ``MediaAsset`` rows aliasing the exact same ``image.name`` (even
  across different Stores — ``_sync_asset_references`` creates a fresh
  ``MediaAsset`` row that points at an *already-saved* file name, without
  copying bytes);
* legacy ``HeroSlide``/``PromotionalBanner``/``StoryRailItem`` ImageFields
  that still hold the same filename directly (pre-Phase-0.5 rows, or rows
  touched only through the legacy Dashboard hero/banner screens);
* a Draft/Published/Archived Placement row, a section background JSON
  reference, an edit-history recovery snapshot, or a template baseline
  snapshot — all already covered by ``MediaAsset.is_referenced()`` /
  ``apps.content.media_reachability`` at the *row* level.

BINDING POLICY UPDATE (MED-001, architect decision — Retention-First):
the MED-001 concurrency investigation proved that a check-then-
``storage.delete()`` design — even one re-checking safety inside the
``transaction.on_commit`` callback, immediately before the physical
delete — still has a real, provable attach-vs-delete TOCTOU race against
concurrent reference creation (a new ``MediaAsset`` alias, an Undo/Redo
revival, a Draft/Restore clone, a background-JSON write). The binding P0
fix is RETENTION-FIRST: online/runtime code must never automatically
destroy either the physical bytes OR an unreferenced ``MediaAsset``
metadata row for this reusable-media family. A small storage/metadata leak
is an accepted cost of eliminating the race outright (there is no delete
to race against). Durable, serialized garbage collection is deferred to a
separate, later-architected task — not designed or implemented here.

These tests use the real configured ``MediaAsset.image`` storage (local
FileSystemStorage under ``MEDIA_ROOT`` in this test environment) and assert
directly on ``storage.exists(name)`` — i.e. real byte-level survival, not
merely "the database row still exists". Several tests below also exercise
the REAL HTTP endpoints (``self.client.post`` + ``reverse``) that used to
own the raw-delete bypass, not just the service functions directly — this
closes the production-wiring coverage gap identified in the MED-001
concurrency investigation.

NOT EXECUTED in this sandbox — no Django runtime is available here (see
the MED-001 final report). Written and statically reviewed
(``python3 -m py_compile``) only.
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.content.services import cleanup_reusable_media_file, delete_media_asset_if_unreferenced
from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(
        name="فروشگاه دیگرِ MED-001", slug="med001-other-store", admin_subdomain="med001-other-store",
    )


def _img(name="med001.png"):
    buf = BytesIO()
    Image.new("RGB", (640, 320), (5, 15, 25)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _storage_of(asset_or_field):
    """Real storage object for a saved ``ImageFieldFile``."""
    return asset_or_field.storage


class Red1DraftReplacementMustNotDeletePublishedBytesTests(TransactionTestCase):
    """RED 1 — replacing a Draft's image must never physically delete bytes
    a Published placement (sharing the same ``MediaAsset``/physical path)
    still needs. Under MED-001 Retention-First, this holds unconditionally
    — even the OLD asset (no longer referenced by the Draft) is retained,
    not merely "retained because Published still needs it"."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_replacing_draft_image_preserves_published_bytes_and_url(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.all().delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img("shared-draft-published.png"))
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="ثابت", desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        published_slide.refresh_from_db()

        draft2 = svc.get_or_create_draft(self.store)
        draft_section = draft2.sections.get(section_key="hero_banner")
        draft_slide = HeroSlide.objects.get(section=draft_section)
        self.assertEqual(draft_slide.desktop_asset_id, asset.pk)

        old_physical_name = asset.image.name
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(old_physical_name))

        # Replace the Draft's image with a brand-new asset (simulating the
        # storefront_section_media_form upgrade flow) and run the SAME
        # cleanup decision the repaired write path uses for the old asset.
        new_asset = MediaAsset.objects.create(store=self.store, image=_img("draft-replacement.png"))
        draft_slide.desktop_asset = new_asset
        draft_slide.save(update_fields=["desktop_asset"])

        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset)

        # Retention-First: never destroyed, regardless of Published still
        # needing it.
        self.assertFalse(deleted)
        # OLD physical filename must still exist — Published still needs it.
        self.assertTrue(storage.exists(old_physical_name))
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        published_slide.refresh_from_db()
        self.assertEqual(published_slide.desktop_asset_id, asset.pk)
        self.assertTrue(published_slide.desktop_image_url)


class Red2HistoryOnlyReferenceTests(TestCase):
    """RED 2 — an asset unreferenced by any live Placement FK, but whose id
    is captured in ``StorefrontEditHistoryEntry.before_state``/
    ``after_state``, must survive cleanup attempts."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_history_only_asset_is_not_deleted(self):
        draft = svc.get_or_create_draft(self.store, user=None)
        StorefrontSection.objects.filter(page__version=draft).delete()
        asset = MediaAsset.objects.create(store=self.store, image=_img("history-only.png"))

        StorefrontEditHistoryEntry.objects.create(
            draft_version=draft, actor=None, sequence=1, action_label="ویرایش",
            before_state={"pages": {}, "containers": {}},
            after_state={
                "pages": {
                    "home": [
                        {"section_key": "hero_banner", "media": {"hero_slides": [{"desktop_asset_id": asset.pk}]}},
                    ],
                },
            },
        )

        self.assertFalse(asset.hero_placements.exists())
        self.assertTrue(asset.is_referenced())

        deleted = delete_media_asset_if_unreferenced(asset)
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(asset.image.name))


class Red3TemplateBaselineOnlyReferenceTests(TestCase):
    """RED 3 — an asset whose only canonical reachability is a version's
    ``template_baseline_snapshot`` must survive cleanup."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_baseline_only_asset_is_not_deleted(self):
        draft = svc.get_or_create_draft(self.store, user=None)
        StorefrontSection.objects.filter(page__version=draft).delete()
        asset = MediaAsset.objects.create(store=self.store, image=_img("baseline-only.png"))
        draft.template_baseline_snapshot = {
            "pages": {
                "home": [
                    {"section_key": "hero_banner", "settings": {"background": {"mode": "image", "media_asset_id": asset.pk}}},
                ],
            },
        }
        draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        self.assertFalse(asset.hero_placements.exists())
        self.assertTrue(asset.is_referenced())

        deleted = delete_media_asset_if_unreferenced(asset)
        self.assertFalse(deleted)
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(asset.image.name))


class Red4SamePhysicalPathMultipleAliasesTests(TestCase):
    """RED 4 — two ``MediaAsset`` rows alias the SAME physical filename.
    Under MED-001 Retention-First, the unreferenced alias's metadata row is
    ALSO retained (not merely the physical bytes) — deleting the metadata
    row while another alias still legitimately needs the bytes would still
    leave the retained row concept intact, but retention now applies
    uniformly regardless of alias reachability."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_physical_bytes_and_unreferenced_alias_row_both_survive(self):
        asset_a = MediaAsset.objects.create(store=self.store, image=_img("aliased.png"))
        shared_name = asset_a.image.name
        storage = _storage_of(asset_a.image)

        # asset_b is a second MediaAsset ROW aliasing the exact same
        # physical path (no re-upload — mirrors _sync_asset_references's
        # own "point at an already-saved name" pattern).
        asset_b = MediaAsset.objects.create(store=self.store, image=shared_name)

        # Only asset_b stays canonically referenced (e.g. a live Hero
        # placement); asset_a has zero references.
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=asset_b)

        self.assertFalse(asset_a.is_referenced())
        self.assertTrue(asset_b.is_referenced())

        # captureOnCommitCallbacks(execute=True) forces the scheduled
        # transaction.on_commit callback to actually run within this
        # test's own wrapping transaction, proving it is a genuine no-op,
        # not merely that it never fired.
        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset_a)

        # Retention-First: the unreferenced alias's metadata row is NOT
        # removed either.
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset_a.pk).exists())
        # The physical bytes remain (asset_b still needs them), and
        # asset_b's own consumer must still resolve.
        self.assertTrue(storage.exists(shared_name))
        asset_b.refresh_from_db()
        self.assertTrue(asset_b.is_referenced())
        self.assertEqual(asset_b.image.name, shared_name)


class Red5LegacyFieldPlusMediaAssetSamePathTests(TestCase):
    """RED 5 — a legacy HeroSlide/PromotionalBanner ImageField and a
    MediaAsset point at the SAME physical filename. Deleting/replacing the
    legacy Dashboard record may remove its own row, but must not destroy
    the shared bytes the MediaAsset (still canonically reachable) needs."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_deleting_legacy_hero_row_does_not_destroy_bytes_shared_with_a_mediaasset(self):
        # A legacy (pre-Phase-0.5, no asset FK) HeroSlide directly owning a
        # physical file.
        legacy_slide = HeroSlide.objects.create(
            store=self.store, title="قدیمی", desktop_image=_img("legacy-shared.png"),
        )
        shared_name = legacy_slide.desktop_image.name
        storage = _storage_of(legacy_slide.desktop_image)

        # A MediaAsset that happens to alias the exact same physical path,
        # and is canonically reachable (a different, live Hero placement).
        shared_asset = MediaAsset.objects.create(store=self.store, image=shared_name)
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=shared_asset)
        self.assertTrue(shared_asset.is_referenced())

        # Legacy route deletes its own row and attempts physical cleanup —
        # through the canonical gate, not a direct storage.delete.
        legacy_slide.delete()
        with self.captureOnCommitCallbacks(execute=True):
            cleanup_reusable_media_file(shared_name, storage)

        self.assertTrue(storage.exists(shared_name))
        shared_asset.refresh_from_db()
        self.assertEqual(shared_asset.image.name, shared_name)


class Retention6TrulyUnreferencedMediaIsIntentionallyRetainedTests(TestCase):
    """RETENTION 6A/6B (MED-001, architect decision — supersedes the old
    "RED 6: genuinely unreferenced bytes are actually deleted"): this is
    NOT a leak accidentally caused by a bug — it is the deliberate,
    binding P0 policy. Even truly-orphaned reusable media (no Placement/
    background/history/baseline/legacy-field/other-alias reference of any
    kind) is intentionally RETAINED, both as a ``MediaAsset`` metadata row
    and as physical bytes, because online/runtime code must never
    automatically destroy either — durable, serialized garbage collection
    for genuinely-orphaned media is deferred to a separate,
    later-architected task."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_retention_6a_truly_unreferenced_mediaasset_remains_in_db_and_bytes_remain(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("truly-orphaned.png"))
        name = asset.image.name
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(name))
        self.assertFalse(asset.is_referenced())

        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset)

        # Deliberate retention, not a leak: no destructive action at all.
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(storage.exists(name))

    def test_retention_6b_truly_orphaned_legacy_filename_remains_physically_present(self):
        slide = HeroSlide.objects.create(store=self.store, title="بدون asset", desktop_image=_img("legacy-orphan.png"))
        name = slide.desktop_image.name
        storage = _storage_of(slide.desktop_image)
        slide.delete()

        with self.captureOnCommitCallbacks(execute=True):
            cleanup_reusable_media_file(name, storage)

        # Deliberate retention: the legacy filename cleanup path is a
        # no-op for this reusable-media family.
        self.assertTrue(storage.exists(name))


class Red7TransactionRollbackTests(TransactionTestCase):
    """RED 7 — physical bytes must never be deleted before a successful DB
    commit; a forced rollback after scheduling cleanup must leave the file
    intact."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_rollback_after_scheduling_cleanup_never_deletes_the_file(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("rollback-safety.png"))
        name = asset.image.name
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(name))

        class _ForcedRollback(Exception):
            pass

        try:
            with transaction.atomic():
                delete_media_asset_if_unreferenced(asset)
                raise _ForcedRollback()
        except _ForcedRollback:
            pass

        # on_commit callback must never have fired: row still exists AND
        # physical file still exists.
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(storage.exists(name))


class Red8CrossStoreExactPathAliasSafetyTests(TestCase):
    """RED 8 — two MediaAsset rows in DIFFERENT Stores deliberately share
    the exact same physical filename; cleanup initiated from one Store must
    not delete bytes (or, under MED-001 Retention-First, the initiating
    Store's own metadata row either) that the other Store's asset still
    needs. This is a conservative physical-byte protection, not a
    tenant-data exposure — the retention decision never inspects or
    returns the other Store's row/identity, only performs no destructive
    action at all."""

    def setUp(self):
        cache.clear()
        self.store_a = _akhlaghi()
        self.store_b = _other_store()

    def test_cleanup_from_store_a_does_not_delete_bytes_or_row_store_b_still_references(self):
        asset_a = MediaAsset.objects.create(store=self.store_a, image=_img("cross-store-shared.png"))
        shared_name = asset_a.image.name
        storage = _storage_of(asset_a.image)

        # Store B deliberately aliases the exact same physical filename and
        # keeps it canonically referenced within its own tenant scope.
        asset_b = MediaAsset.objects.create(store=self.store_b, image=shared_name)
        HeroSlide.objects.create(store=self.store_b, desktop_image=_img(), desktop_asset=asset_b)
        self.assertTrue(asset_b.is_referenced())

        # asset_a itself has zero references within store_a.
        self.assertFalse(asset_a.is_referenced())

        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset_a)

        # Retention-First: the initiating Store's own unreferenced
        # metadata row is NOT pruned either.
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset_a.pk).exists())
        # The physically-shared bytes survive, because store_b still
        # canonically needs them.
        self.assertTrue(storage.exists(shared_name))
        asset_b.refresh_from_db()
        self.assertTrue(asset_b.is_referenced())


# =========================================================================
# MANDATORY REAL ENDPOINT TESTS (MED-001 concurrency-investigation gap)
#
# Every test below drives the ACTUAL production HTTP view that used to own
# a raw storage.delete() bypass — not the service functions directly — so
# these prove the production wiring itself, not merely the service layer
# in isolation. Several also deliberately construct a shared-filename/
# MediaAsset-alias scenario that would have FAILED under the pre-MED-001
# unconditional storage.delete() behavior.
# =========================================================================


def _hero_owner(store, *, username):
    user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
    StoreMembership.objects.create(
        store=store, user=user, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )
    return user


class EndpointStorefrontBuilderReplacementRetentionTests(TransactionTestCase):
    """Endpoint test #1 — real ``storefront_section_media_form`` replacement
    (Draft), where a Published placement shares the exact same old
    ``MediaAsset``/physical file. This is the actual former bypass path
    (``_sync_asset_references`` + the old-asset cleanup call in
    ``storefront_section_media_form``), driven end-to-end over HTTP, not
    called as a service function directly."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.owner = _hero_owner(self.store, username="med001-ep-sfb-replace-owner")

    def test_real_draft_replacement_endpoint_preserves_published_bytes_and_old_row(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.all().delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img("ep-shared-published.png"))
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="ثابت", desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        published_slide.refresh_from_db()

        draft2 = svc.get_or_create_draft(self.store)
        draft_section = draft2.sections.get(section_key="hero_banner")
        draft_slide = HeroSlide.objects.get(section=draft_section)
        old_physical_name = asset.image.name
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(old_physical_name))

        client = Client()
        client.login(username="med001-ep-sfb-replace-owner", password="pass12345")

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse(
                    "dashboard:storefront-builder-section-media-edit",
                    args=[draft_section.pk, "hero-slides", draft_slide.pk],
                ),
                {"title": "ثابت", "destination_type": "none", "desktop_image": _img("ep-new-draft.png"), "is_active": "on"},
            )

        self.assertIn(response.status_code, (200, 302))

        draft_slide.refresh_from_db()
        # Draft now uses a NEW reference/file.
        self.assertNotEqual(draft_slide.desktop_asset_id, asset.pk)
        self.assertTrue(draft_slide.desktop_image_url)

        # Published is untouched and still resolves the OLD asset.
        published_slide.refresh_from_db()
        self.assertEqual(published_slide.desktop_asset_id, asset.pk)
        self.assertTrue(published_slide.desktop_image_url)

        # Old physical file AND old MediaAsset row both remain
        # (Retention-First) — this is the exact scenario that would have
        # destroyed shared bytes under the pre-MED-001 unconditional
        # storage.delete() behavior.
        self.assertTrue(storage.exists(old_physical_name))
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())


class EndpointStorefrontBuilderLegacyDeleteFallbackRetentionTests(TransactionTestCase):
    """Endpoint test #2 — real ``storefront_section_media_delete`` for a
    legacy (no-asset-FK) placement, driven over HTTP."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.owner = _hero_owner(self.store, username="med001-ep-sfb-delete-owner")

    def test_real_legacy_placement_delete_endpoint_preserves_physical_file(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.all().delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=0)
        # A legacy (no asset FK) placement — pre-Phase-0.5 shape.
        legacy_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="بدون asset", desktop_image=_img("ep-legacy-delete.png"),
        )
        physical_name = legacy_slide.desktop_image.name
        storage = _storage_of(legacy_slide.desktop_image)
        self.assertTrue(storage.exists(physical_name))

        client = Client()
        client.login(username="med001-ep-sfb-delete-owner", password="pass12345")

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse(
                    "dashboard:storefront-builder-section-media-delete",
                    args=[section.pk, "hero-slides", legacy_slide.pk],
                ),
            )

        self.assertIn(response.status_code, (200, 302))
        self.assertFalse(HeroSlide.objects.filter(pk=legacy_slide.pk).exists())
        # Retention-First: the physical file remains even though the
        # placement row itself is gone.
        self.assertTrue(storage.exists(physical_name))


class EndpointDashboardHeroRetentionTests(TransactionTestCase):
    """Endpoint tests #3/#4 — real legacy Dashboard ``hero_form``/
    ``hero_delete``, driven over HTTP. At least one scenario here uses a
    filename shared with a live ``MediaAsset`` alias so it would have
    FAILED under the pre-MED-001 unconditional storage.delete() behavior."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.owner = _hero_owner(self.store, username="med001-ep-hero-owner")
        self.client.login(username="med001-ep-hero-owner", password="pass12345")

    def test_real_hero_replacement_endpoint_preserves_shared_old_file(self):
        slide = HeroSlide.objects.create(
            store=self.store, title="تعویض", desktop_image=_img("ep-hero-old.png"), is_active=True,
        )
        old_name = slide.desktop_image.name
        storage = _storage_of(slide.desktop_image)

        # A live MediaAsset alias deliberately shares the exact same
        # physical filename — this is the scenario that would have been
        # destroyed by the pre-MED-001 unconditional storage.delete().
        shared_asset = MediaAsset.objects.create(store=self.store, image=old_name)
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=shared_asset)
        self.assertTrue(shared_asset.is_referenced())
        self.assertTrue(storage.exists(old_name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("dashboard:hero-edit", args=[slide.pk]),
                {
                    "title": "تعویض", "subtitle": "", "button_label": "", "show_button": "",
                    "destination_type": "none", "destination_external_url": "", "display_order": "0",
                    "desktop_image": _img("ep-hero-new.png"),
                },
            )

        self.assertEqual(response.status_code, 302)
        slide.refresh_from_db()
        # Hero row now has the NEW legacy image value.
        self.assertNotEqual(slide.desktop_image.name, old_name)
        # Old physical file remains — still aliased by shared_asset.
        self.assertTrue(storage.exists(old_name))
        shared_asset.refresh_from_db()
        self.assertEqual(shared_asset.image.name, old_name)
        self.assertTrue(shared_asset.is_referenced())

    def test_real_hero_delete_endpoint_preserves_physical_file(self):
        slide = HeroSlide.objects.create(
            store=self.store, title="حذف", desktop_image=_img("ep-hero-delete.png"), is_active=True,
        )
        name = slide.desktop_image.name
        storage = _storage_of(slide.desktop_image)
        self.assertTrue(storage.exists(name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:hero-delete", args=[slide.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(HeroSlide.objects.filter(pk=slide.pk).exists())
        # Retention-First: physical file remains.
        self.assertTrue(storage.exists(name))


class EndpointDashboardBannerRetentionTests(TransactionTestCase):
    """Endpoint tests #5/#6 — real legacy Dashboard ``banner_form``/
    ``banner_delete``, driven over HTTP — same shape as the Hero endpoint
    tests above."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE},
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.owner = _hero_owner(self.store, username="med001-ep-banner-owner")
        self.client.login(username="med001-ep-banner-owner", password="pass12345")

    def test_real_banner_replacement_endpoint_preserves_old_file(self):
        banner = PromotionalBanner.objects.create(
            store=self.store, title="تعویض بنر", desktop_image=_img("ep-banner-old.png"), is_active=True,
        )
        old_name = banner.desktop_image.name
        storage = _storage_of(banner.desktop_image)
        self.assertTrue(storage.exists(old_name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("dashboard:banner-edit", args=[banner.pk]),
                {
                    "title": "تعویض بنر", "description": "", "button_label": "", "show_button": "",
                    "destination_type": "none", "destination_external_url": "", "display_order": "0",
                    "desktop_image": _img("ep-banner-new.png"),
                },
            )

        self.assertEqual(response.status_code, 302)
        banner.refresh_from_db()
        self.assertNotEqual(banner.desktop_image.name, old_name)
        self.assertTrue(storage.exists(old_name))

    def test_real_banner_delete_endpoint_preserves_physical_file(self):
        banner = PromotionalBanner.objects.create(
            store=self.store, title="حذف بنر", desktop_image=_img("ep-banner-delete.png"), is_active=True,
        )
        name = banner.desktop_image.name
        storage = _storage_of(banner.desktop_image)
        self.assertTrue(storage.exists(name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("dashboard:banner-delete", args=[banner.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PromotionalBanner.objects.filter(pk=banner.pk).exists())
        self.assertTrue(storage.exists(name))
