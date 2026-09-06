"""Phase 2 (Lifecycle & Safety) — Task 1 media reachability characterization
(L07 / A05, the P0 gap).

``MediaAsset.is_referenced()`` (``apps/content/models.py:418-431``) is the
single truth used by ``content.services.delete_media_asset_if_unreferenced``
(``apps/content/services.py:211-243``) to decide whether a physical media file
may be deleted. Today it only ORs the five direct FK placement relations
(Hero/Banner desktop+mobile/Story). It is BLIND to two additional live
reference classes documented in the media-reference taxonomy (inventory §5):

  #2 JSON reference — ``StorefrontSection.settings["background"]["media_asset_id"]``
     (written by ``views._extract_background_raw``; rendered by
     ``content.services.resolve_background_media_url``).
  #4 Recovery reference — an asset id captured inside an edit-history
     snapshot (``StorefrontEditHistoryEntry.before_state``/``after_state``)
     or a ``template_baseline_snapshot`` on a version.

Because ``is_referenced()`` cannot see either, an asset referenced ONLY by
one of these is currently reported as unreferenced → deletable while still
shown / still recoverable. That is the A05 defect (L07, P0).

These tests are DELIBERATELY NON-DESTRUCTIVE: they assert on the
``is_referenced()`` reachability predicate rather than actually invoking a
delete that could destroy live fixtures. The desired-invariant assertions are
expected to FAIL at baseline (intended RED). A single throwaway-asset test
documents the *current unsafe consequence* (the deletion gate would delete a
JSON-only-referenced asset) using an asset created solely for that purpose.
"""

from io import BytesIO

from django.core.cache import cache
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.content.models import MediaAsset
from apps.content.services import delete_media_asset_if_unreferenced
from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="phase2-reach.png"):
    buf = BytesIO()
    Image.new("RGB", (640, 320), (12, 24, 36)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class JsonOnlyBackgroundReferenceReachabilityTests(TestCase):
    """L07 case A — asset referenced ONLY via a section's JSON
    ``settings.background.media_asset_id`` (no Hero/Banner/Story FK
    placement)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def _section_with_background_asset(self, version):
        home = version.get_page(StorefrontPage.PageType.HOME)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        StorefrontSection.objects.create(
            page=home,
            section_key="hero_banner",
            order=0,
            settings={
                "background": {
                    "mode": "image",
                    "media_asset_id": asset.pk,
                },
            },
        )
        return asset

    def test_json_only_referenced_asset_on_draft_is_reachable(self):
        """DESIRED (currently RED): an asset referenced only through a Draft
        section's background JSON is considered referenced."""
        draft = svc.get_or_create_draft(self.store, user=None)
        asset = self._section_with_background_asset(draft)

        # Guard: prove there is genuinely NO FK placement, so the JSON is the
        # only live reference — this is what makes the assertion meaningful.
        self.assertFalse(asset.hero_placements.exists())
        self.assertFalse(asset.banner_desktop_placements.exists())
        self.assertFalse(asset.story_placements.exists())

        # DESIRED invariant — FAILS at baseline (L07 RED).
        self.assertTrue(asset.is_referenced())

    def test_json_only_referenced_asset_on_published_is_reachable(self):
        """DESIRED (currently RED): same, but the JSON reference lives on a
        PUBLISHED version (still shown to visitors)."""
        draft = svc.get_or_create_draft(self.store, user=None)
        asset = self._section_with_background_asset(draft)
        svc.publish(self.store)

        asset.refresh_from_db()
        # DESIRED invariant — FAILS at baseline (L07 RED).
        self.assertTrue(asset.is_referenced())


class SnapshotOnlyReferenceReachabilityTests(TestCase):
    """L07 case B — asset referenced ONLY by a recovery snapshot (edit
    history entry / template_baseline_snapshot), with no live FK placement
    and no live JSON on any current section."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def _bare_draft(self):
        draft = svc.get_or_create_draft(self.store, user=None)
        # Remove any bootstrapped sections so there is no live JSON/FK
        # reference anywhere — the ONLY reference will be inside a snapshot.
        StorefrontSection.objects.filter(page__version=draft).delete()
        return draft

    def test_edit_history_snapshot_only_referenced_asset_is_reachable(self):
        """DESIRED (currently RED): an asset id captured inside an edit
        history entry's ``after_state`` (recoverable via Undo/Redo /
        restore) is considered referenced."""
        draft = self._bare_draft()
        asset = MediaAsset.objects.create(store=self.store, image=_img())

        # A realistic snapshot shape (mirrors edit_history_service.snapshot_draft):
        # a section carrying the asset in its background JSON, plus the asset
        # id captured as a serialized media placement field.
        snapshot = {
            "header_config": {},
            "footer_config": {},
            "appearance_config": {},
            "pages": {
                "home": [
                    {
                        "section_key": "hero_banner",
                        "order": 0,
                        "settings": {
                            "background": {
                                "mode": "image",
                                "media_asset_id": asset.pk,
                            },
                        },
                        "media": {
                            "hero_slides": [{"desktop_asset_id": asset.pk}],
                        },
                    }
                ],
            },
            "containers": {},
        }
        StorefrontEditHistoryEntry.objects.create(
            draft_version=draft,
            actor=None,
            sequence=1,
            action_label="ویرایش تنظیمات بخش",
            before_state={"pages": {}, "containers": {}},
            after_state=snapshot,
        )

        # Guard: no live FK placement and no live section references it.
        self.assertFalse(asset.hero_placements.exists())
        self.assertFalse(
            StorefrontSection.objects.filter(page__version=draft).exists()
        )

        # DESIRED invariant — FAILS at baseline (L07 RED).
        self.assertTrue(asset.is_referenced())

    def test_template_baseline_snapshot_only_referenced_asset_is_reachable(self):
        """DESIRED (currently RED): an asset id captured inside a version's
        ``template_baseline_snapshot`` (recoverable via reset-to-baseline) is
        considered referenced."""
        draft = self._bare_draft()
        asset = MediaAsset.objects.create(store=self.store, image=_img())

        draft.template_baseline_snapshot = {
            "pages": {
                "home": [
                    {
                        "section_key": "hero_banner",
                        "settings": {
                            "background": {
                                "mode": "image",
                                "media_asset_id": asset.pk,
                            },
                        },
                    }
                ],
            },
        }
        draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        self.assertFalse(asset.hero_placements.exists())
        self.assertFalse(
            StorefrontSection.objects.filter(page__version=draft).exists()
        )

        # DESIRED invariant — FAILS at baseline (L07 RED).
        self.assertTrue(asset.is_referenced())


class UnsafeDeletionConsequenceTests(TestCase):
    """L07 — documents the concrete unsafe CONSEQUENCE of the reachability
    gap through the real deletion gate, using a THROWAWAY asset created only
    for this test (never a shared/live fixture asset).

    At baseline the gate ``delete_media_asset_if_unreferenced`` returns True
    (deletes) for a JSON-only-referenced asset — the defect. After L07 is
    closed (Task 6) it must return False. This is the desired-invariant
    assertion and is expected to FAIL at baseline (RED).
    """

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_gate_must_not_delete_json_only_referenced_asset(self):
        draft = svc.get_or_create_draft(self.store, user=None)
        home = draft.get_page(StorefrontPage.PageType.HOME)
        # Throwaway asset, referenced ONLY by this section's background JSON.
        asset = MediaAsset.objects.create(store=self.store, image=_img("throwaway.png"))
        StorefrontSection.objects.create(
            page=home,
            section_key="hero_banner",
            order=1,
            settings={
                "background": {"mode": "image", "media_asset_id": asset.pk},
            },
        )
        asset_pk = asset.pk

        deleted = delete_media_asset_if_unreferenced(asset)

        # DESIRED invariant — FAILS at baseline (L07 RED): the gate must
        # refuse to delete a still-referenced (JSON-only) asset.
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset_pk).exists())


class GenuinelyUnreferencedAssetTests(TestCase):
    """Preservation guard — an asset with ZERO references of ANY class must
    still be reported unreferenced (GREEN today; must stay GREEN after the
    Task-6 fix so the fix does not over-reach into 'everything is
    referenced')."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_asset_with_no_references_is_not_reachable(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("orphan.png"))
        self.assertFalse(asset.is_referenced())



class CrossStoreIsolationReachabilityTests(TestCase):
    """L07 — the extended reachability check MUST stay tenant-scoped: an
    asset owned by store A must NOT be reported referenced merely because
    store B's section JSON / recovery snapshot happens to carry the same
    integer id. This proves the fix does not full-table-scan across stores
    and cannot be tricked into preserving/deleting the wrong tenant's asset.
    """

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.other = Store.objects.create(
            name="فروشگاه دیگر (ایزوله‌سازی رسانه)",
            slug="phase2-reach-other-store",
            admin_subdomain="phase2-reach-other-store",
        )

    def test_other_store_json_background_does_not_reference_this_asset(self):
        """An asset in store A, with NO reference in store A, is unreferenced
        even though store B has a section background JSON carrying the same
        id value."""
        asset = MediaAsset.objects.create(store=self.store, image=_img("iso-a.png"))

        # Store B: a draft section whose background JSON reuses asset.pk.
        other_draft = svc.get_or_create_draft(self.other, user=None)
        other_home = other_draft.get_page(StorefrontPage.PageType.HOME)
        StorefrontSection.objects.create(
            page=other_home,
            section_key="hero_banner",
            order=0,
            settings={
                "background": {"mode": "image", "media_asset_id": asset.pk},
            },
        )

        # Cross-tenant JSON must NOT make store A's asset referenced.
        self.assertFalse(asset.is_referenced())

    def test_other_store_recovery_snapshot_does_not_reference_this_asset(self):
        """Same isolation for recovery snapshots — store B's edit-history and
        baseline snapshot referencing the id must not reach store A's asset."""
        asset = MediaAsset.objects.create(store=self.store, image=_img("iso-b.png"))

        other_draft = svc.get_or_create_draft(self.other, user=None)
        StorefrontEditHistoryEntry.objects.create(
            draft_version=other_draft,
            actor=None,
            sequence=1,
            action_label="ویرایش تنظیمات بخش",
            before_state={"pages": {}, "containers": {}},
            after_state={
                "pages": {
                    "home": [
                        {
                            "section_key": "hero_banner",
                            "media": {"hero_slides": [{"desktop_asset_id": asset.pk}]},
                        }
                    ],
                },
            },
        )
        other_draft.template_baseline_snapshot = {
            "pages": {
                "home": [
                    {
                        "section_key": "hero_banner",
                        "settings": {
                            "background": {"mode": "image", "media_asset_id": asset.pk},
                        },
                    }
                ],
            },
        }
        other_draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        self.assertFalse(asset.is_referenced())

    def test_same_store_snapshot_still_references_after_isolation_setup(self):
        """Control: within the OWN store the snapshot reference IS seen — so
        the isolation above is genuine tenant scoping, not a check that never
        matches snapshots."""
        asset = MediaAsset.objects.create(store=self.store, image=_img("iso-c.png"))
        own_draft = svc.get_or_create_draft(self.store, user=None)
        StorefrontSection.objects.filter(page__version=own_draft).delete()
        own_draft.template_baseline_snapshot = {
            "pages": {
                "home": [
                    {
                        "section_key": "hero_banner",
                        "settings": {
                            "background": {"mode": "image", "media_asset_id": asset.pk},
                        },
                    }
                ],
            },
        }
        own_draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        self.assertTrue(asset.is_referenced())


class UnrelatedIntegerDoesNotOverReachTests(TestCase):
    """L07 — the id-key matcher must not match an unrelated integer that
    merely equals the asset id under a NON-media key (e.g. ``order`` or a
    destination id). This guards against the fix over-reaching into "every
    asset is referenced"."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_matching_integer_under_unrelated_key_does_not_reference(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("unrelated.png"))
        draft = svc.get_or_create_draft(self.store, user=None)
        StorefrontSection.objects.filter(page__version=draft).delete()
        home = draft.get_page(StorefrontPage.PageType.HOME)
        # The asset id appears ONLY under unrelated keys (order / a
        # destination product id) — never under a media-id key.
        StorefrontSection.objects.create(
            page=home,
            section_key="hero_banner",
            order=asset.pk,
            settings={
                "order": asset.pk,
                "destination": {"destination_product_id": asset.pk},
                "background": {"mode": "theme", "media_asset_id": None},
            },
        )
        self.assertFalse(asset.is_referenced())
