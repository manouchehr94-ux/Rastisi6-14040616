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

Before this repair, several call sites decided "may I physically delete
this file?" purely from their own local, narrow knowledge (e.g. "did *this*
field's value change?") and called ``storage.delete()`` directly —
bypassing the one canonical row-level safety check entirely. This module
proves (RED, before the fix; GREEN, after) that the physical byte survives
every one of those bypass scenarios, and that genuinely-orphaned bytes are
still actually removed.

These tests use the real configured ``MediaAsset.image`` storage (local
FileSystemStorage under ``MEDIA_ROOT`` in this test environment) and assert
directly on ``storage.exists(name)`` — i.e. real byte-level survival, not
merely "the database row still exists".

NOT EXECUTED in this sandbox — no Django runtime is available here (see
the MED-001 final report). Written and statically reviewed
(``python3 -m py_compile``) only.
"""

from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.content.services import (
    cleanup_reusable_media_file,
    delete_media_asset_if_unreferenced,
    is_physical_media_path_safe_to_delete,
)
from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


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
    still needs."""

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
            delete_media_asset_if_unreferenced(asset)

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
    Pruning the unreferenced alias's metadata row may be allowed, but the
    physical bytes (still needed by the referenced alias) must remain."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_physical_bytes_survive_pruning_the_unreferenced_alias(self):
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
        # transaction.on_commit cleanup to actually run within this test's
        # own wrapping transaction, so the assertion below proves the
        # callback's OWN safety re-check holds, not merely that it never
        # fired.
        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset_a)

        # The unreferenced alias's metadata row MAY be removed...
        self.assertTrue(deleted)
        self.assertFalse(MediaAsset.objects.filter(pk=asset_a.pk).exists())
        # ...but the physical bytes MUST remain (asset_b still needs them),
        # and asset_b's own consumer must still resolve.
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


class Red6GenuinelyUnreferencedFileIsActuallyDeletedTests(TestCase):
    """RED 6 — safety must not become permanent leaking: truly-orphaned
    reusable media bytes (no Placement/background/history/baseline/legacy-
    field/other-alias reference of any kind) ARE physically removed."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_truly_orphaned_asset_is_physically_deleted(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("truly-orphaned.png"))
        name = asset.image.name
        storage = _storage_of(asset.image)
        self.assertTrue(storage.exists(name))
        self.assertFalse(asset.is_referenced())

        with self.captureOnCommitCallbacks(execute=True):
            deleted = delete_media_asset_if_unreferenced(asset)
        self.assertTrue(deleted)
        self.assertFalse(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_legacy_fallback_cleanup_actually_deletes_a_truly_orphaned_legacy_file(self):
        slide = HeroSlide.objects.create(store=self.store, title="بدون asset", desktop_image=_img("legacy-orphan.png"))
        name = slide.desktop_image.name
        storage = _storage_of(slide.desktop_image)
        slide.delete()

        with self.captureOnCommitCallbacks(execute=True):
            cleanup_reusable_media_file(name, storage)
        self.assertFalse(storage.exists(name))


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
    not delete bytes the other Store's asset still needs. This is a
    conservative physical-byte protection, not a tenant-data exposure —
    ``is_physical_media_path_safe_to_delete`` only returns a boolean, never
    the other Store's row/identity."""

    def setUp(self):
        cache.clear()
        self.store_a = _akhlaghi()
        self.store_b = _other_store()

    def test_cleanup_from_store_a_does_not_delete_bytes_store_b_still_references(self):
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

        # The initiating Store's own unreferenced metadata row may be
        # pruned...
        self.assertTrue(deleted)
        self.assertFalse(MediaAsset.objects.filter(pk=asset_a.pk).exists())
        # ...but the physically-shared bytes must survive, because store_b
        # still canonically needs them.
        self.assertTrue(storage.exists(shared_name))
        asset_b.refresh_from_db()
        self.assertTrue(asset_b.is_referenced())

    def test_the_boolean_gate_itself_does_not_leak_other_store_identity(self):
        """The physical-path safety gate is a pure boolean decision — it
        must not require/return any information about the OTHER store's
        asset row to make a safe (conservative) call."""
        asset_a = MediaAsset.objects.create(store=self.store_a, image=_img("cross-store-bool.png"))
        shared_name = asset_a.image.name

        asset_b = MediaAsset.objects.create(store=self.store_b, image=shared_name)
        HeroSlide.objects.create(store=self.store_b, desktop_image=_img(), desktop_asset=asset_b)

        result = is_physical_media_path_safe_to_delete(shared_name, exclude_asset_pk=asset_a.pk)
        self.assertIsInstance(result, bool)
        self.assertFalse(result)
