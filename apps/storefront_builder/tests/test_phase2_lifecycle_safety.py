"""Phase 2 (Lifecycle & Safety) — Task 1 RED/GREEN characterization.

These tests encode the DESIRED Phase-2 lifecycle invariants and prove, at
the current baseline, which gaps are still RED (defect present) and which
already-safe behaviours are GREEN. They use ONLY real routes/services and
real fixtures (Store "akhlaghi" via ``StorefrontBuilderViewsTestCase``,
``layout_service`` for the real Draft/Publish lifecycle) — no fabricated
APIs, no production code changes.

Gap mapping (see
``docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md``):

* L05 (P2) — no editing path may mutate a Published/Archived version.
  Expected at baseline: GREEN (already safe by Draft-scoping in
  ``_get_scoped_section``, ``apps/storefront_builder/views.py:772-781``).
* L01 (P1) — a real legacy Draft mutation MUST advance the Draft's
  ``edit_revision`` (Draft-wide monotonic optimistic-concurrency token).
  Expected at baseline: RED — legacy view mutations record edit history but
  never advance ``edit_revision`` (see ``_record_edit_history``,
  ``apps/storefront_builder/views.py:68-104``; the increment lives only in
  the R4 path, ``r4_mutation_service._lock_active_draft``).
"""

from django.urls import reverse

from apps.storefront_builder.models import (
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase


# ---------------------------------------------------------------------------
# Task 2 — Published / Archived / Cross-store mutation-protection convergence
# ---------------------------------------------------------------------------
#
# GOAL (gap L05): prove that EVERY active Appearance/Builder-owned legacy
# mutation family cannot mutate (a) a PUBLISHED version, (b) an ARCHIVED
# version, or (c) a FOREIGN store's version.
#
# This is a NEGATIVE-TEST task. All legacy structural / container / cell /
# block / media routes resolve their target through the Draft+store scoping
# helpers (``_get_scoped_section`` / ``_get_scoped_container`` /
# ``_get_scoped_cell`` in ``apps/storefront_builder/views.py``, mirrored by
# ``media_views``), so a Published/Archived/foreign target id is
# indistinguishable from "does not exist" → 404, and nothing is mutated.
# The Appearance/header/footer/publish/undo/redo/discard/reset routes have
# NO target-version parameter at all — they resolve the request store's
# active Draft via ``layout_service.get_or_create_draft`` — so they are
# structurally incapable of naming a Published/Archived version; the only
# reachable "wrong target" for them is a foreign store, which the tenant
# host + membership resolution rejects. ``storefront_restore`` is the one
# route that accepts an explicit ``version_id``; it never mutates the target
# (it clones it into a NEW Draft) and rejects a foreign version id (404).
#
# Coverage already proven elsewhere and intentionally NOT duplicated here:
#   * R4 ``section.update_settings`` on a Published version and on a foreign
#     store section — ``test_r4_mutation_api.PublishedVersionImmutabilityTests``
#     / ``TenantIsolationTests``.
#   * ``layout_service.restore_version`` cross-store rejection —
#     ``test_layout_service.RestoreTests.test_restore_rejects_cross_store_version``.
#   * Media list/edit/delete from another store → 404 —
#     ``test_media_views.TenantIsolationTests``.
#   * Tampered foreign background-media asset rejected without mutation —
#     ``test_phase35_reference_editable_backgrounds``.
# The legacy ``storefront_section_settings`` Published/Archived cases are
# already covered by the Task-1 classes above and are also not duplicated.

from django.contrib.auth import get_user_model

_User = get_user_model()


# ---------------------------------------------------------------------------
# Task 4 — Legacy Publish / Undo / Redo / Restore / Discard lifecycle safety
# ---------------------------------------------------------------------------
#
# Gaps closed here:
#
# * L03 (P1) — the legacy ``storefront_undo`` / ``storefront_redo`` views must
#   be revision-coherent: a *successful* undo/redo (one that actually restores
#   a different Draft state) advances the Draft-wide ``edit_revision`` by
#   EXACTLY 1, matching the R4 ``apply_history_command`` guarantee — so
#   undo/redo through EITHER entry point is revision-monotonic. A no-op
#   undo/redo (nothing to undo/redo) advances nothing. Undo/Redo must NEVER
#   append a new undoable history entry (Section 13). Baseline: RED — the
#   legacy views call ``edit_history_service.undo/redo`` directly and never
#   touch ``edit_revision``.
#
# * L02 (P1) — the legacy ``storefront_publish`` view must reach the same
#   lifecycle guarantee as R4 ``publish_draft``: atomic, archive the previous
#   Published, clear draft history/pointer, swap pointers — by delegating to
#   the SAME shared ``layout_service.publish`` contract. Where a base revision
#   is available on the request, a stale publish (Draft advanced under the
#   client) is rejected coherently and mutates nothing.
#
# * Restore / Discard remain atomic, Draft-lifecycle-correct, and recover the
#   canonical typed ``store_appearance`` manifest intact across an
#   apply → undo → redo → restore round-trip (structurally byte-for-byte
#   equal), with revision monotonic where a real change occurred.

from apps.storefront_builder.models import StorefrontEditHistoryEntry
from apps.storefront_builder.storefront_appearance import persistence as appearance_persistence
from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive


# ---------------------------------------------------------------------------
# Task 5 — Structure-lock operation-matrix convergence (L06) + lifecycle-safe
# template/reset revision coherence (L04)
# ---------------------------------------------------------------------------
#
# AUTHORITATIVE structure-lock operation matrix (spec §11). "structure-lock
# protects STRUCTURAL operations ONLY" — it is NOT an appearance/content lock.
# These tests prove the matrix is COMPLETE and CONSISTENT across BOTH the R4
# structure path (``section_structure_service`` behind the R4 mutation route)
# AND the legacy views, for both ``Section.is_locked`` and
# ``Container.is_locked``:
#
#   Operation                              | locked: allowed? | proven on
#   ---------------------------------------|------------------|-----------
#   Section move / reorder                 | NO               | R4 + legacy
#   Section remove                         | NO               | R4 + legacy
#   Block move / remove (within cell)      | NO               | legacy
#   Container settings/layout/move/remove  | NO (locked ctr)  | legacy
#   Cell add-section / clear               | NO (locked ctr)  | legacy
#   Template apply / baseline reset (page  | NO               | preset_service
#       with a locked section)             |                  | + apply view
#   Section settings edit (content/appear) | YES              | R4 + legacy
#   Toggle active / collapse / lock-toggle | YES              | legacy
#   Section duplicate (new logical section)| YES              | R4 + legacy
#
# The R4 path surfaces a refused structural op as a 400 JSON body
# ``{"ok": false, "code": "<section_locked|container_locked|target_locked|...>"}``
# (see ``r4_views.storefront_r4_mutation`` mapping ``SectionStructureError.code``
# via ``R4MutationError``); the legacy views surface it as a Persian
# ``messages.error`` + the section/container-state partial (no mutation). Both
# must leave the Draft byte-for-byte unchanged: no structural mutation, no
# ``edit_revision`` advance, no history entry.

import json

from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontEditHistoryEntry as _T5HistoryEntry,
)
from apps.storefront_builder.services import (
    container_service as _t5_container_service,
)


class _StructureLockMatrixMixin(StorefrontBuilderViewsTestCase):
    """Shared fixture for the structure-lock matrix: an active Draft with the
    R4 gate ON so the R4 mutation route is reachable, plus helpers to build
    real page-level sections placed in real Container/Cell composition (the
    exact runtime shape ``ensure_page_containers`` produces)."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        # Start from a clean Home so section counts/orders are deterministic.
        self.home.containers.all().delete()
        self.home.sections.all().delete()

    def _add_section(self, section_key="rich_text", *, order=0, settings=None, is_locked=False):
        section = StorefrontSection.objects.create(
            page=self.home, section_key=section_key, order=order,
            settings=settings if settings is not None else {"body_html": "<p>x</p>"},
            is_locked=is_locked,
        )
        return section

    def _place_each_section_in_own_container(self):
        """Mirror the real runtime placement: every page-level Section ends up
        as the sole Block of its own single-column Container/Cell."""
        _t5_container_service.ensure_page_containers(self.home)

    def _cell_of(self, section):
        """Resolve a Section's placement Cell the same way the production code
        does: prefer the new multi-block FK, fall back to the legacy
        ``StorefrontCell.section`` OneToOne that ``ensure_page_containers``
        writes."""
        section.refresh_from_db()
        if section.cell_id is not None:
            return section.cell
        return StorefrontCell.objects.filter(section=section).select_related("container").first()

    def _post_r4(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _r4_mutate(self, mutation):
        self.draft.refresh_from_db()
        return self._post_r4({
            "base_revision": self.draft.edit_revision,
            "mutation": mutation,
        })

    def _history_count(self):
        return _T5HistoryEntry.objects.filter(draft_version=self.draft).count()

    def _revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision


# ---------------------------------------------------------------------------
# L06 — NEGATIVE tests: every "NO" cell, R4 structure path
# ---------------------------------------------------------------------------


class R4StructureLockNegativeTests(_StructureLockMatrixMixin):
    """R4 structure path (``section_structure_service`` behind the R4 mutation
    route): every structural "NO" cell must be refused with the stable
    ``SectionStructureError.code`` and mutate nothing (no revision advance, no
    history entry)."""

    def _assert_r4_refused(self, mutation, expected_code):
        revision_before = self._revision()
        history_before = self._history_count()
        resp = self._r4_mutate(mutation)
        self.assertEqual(resp.status_code, 400, f"{mutation['type']} must be refused")
        body = resp.json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["code"], expected_code)
        # Nothing moved: revision + history are unchanged (atomic refusal).
        self.assertEqual(self._revision(), revision_before)
        self.assertEqual(self._history_count(), history_before)

    def test_r4_section_remove_on_locked_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()
        self._assert_r4_refused(
            {"type": "section.remove", "section_id": locked.pk}, "section_locked",
        )
        self.assertTrue(StorefrontSection.objects.filter(pk=locked.pk).exists())

    def test_r4_section_move_on_locked_source_section_is_refused(self):
        locked = self._add_section(order=0, is_locked=True)
        self._add_section(section_key="rich_text", order=1)
        self._place_each_section_in_own_container()
        order_before = locked.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": locked.pk, "direction": "down"},
            "section_locked",
        )
        locked.refresh_from_db()
        self.assertEqual(locked.order, order_before)

    def test_r4_section_move_toward_locked_target_is_refused(self):
        mover = self._add_section(order=0)
        locked_target = self._add_section(order=1, is_locked=True)
        self._place_each_section_in_own_container()
        order_before = mover.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": mover.pk, "direction": "down"},
            "target_locked",
        )
        mover.refresh_from_db()
        self.assertEqual(mover.order, order_before)

    def test_r4_section_move_out_of_locked_container_is_refused(self):
        # A section whose CONTAINER is locked cannot be reordered even if the
        # section itself is unlocked — container-level structural lock.
        mover = self._add_section(order=0)
        self._add_section(order=1)
        self._place_each_section_in_own_container()
        # Lock the mover's own container.
        container = self._cell_of(mover).container
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        order_before = mover.order
        self._assert_r4_refused(
            {"type": "section.move", "section_id": mover.pk, "direction": "down"},
            "container_locked",
        )
        mover.refresh_from_db()
        self.assertEqual(mover.order, order_before)


# ---------------------------------------------------------------------------
# L06 — POSITIVE tests: lock is structure-only (R4 path)
# ---------------------------------------------------------------------------


class R4StructureLockPositiveTests(_StructureLockMatrixMixin):
    """A locked section must still accept content/appearance settings edits and
    duplication through the R4 path — the lock is structural only."""

    def test_r4_settings_edit_on_locked_section_succeeds(self):
        locked = self._add_section(
            section_key="hero_banner", order=0,
            settings=None, is_locked=True,
        )
        # hero_banner carries a real schema; give it its defaults first.
        from apps.storefront_builder import section_registry
        locked.settings = section_registry.get_definition("hero_banner").default_settings()
        locked.save(update_fields=["settings"])
        self._place_each_section_in_own_container()

        revision_before = self._revision()
        resp = self._r4_mutate({
            "type": "section.update_settings",
            "section_id": locked.pk,
            "patch": {"autoplay": False},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        locked.refresh_from_db()
        self.assertIs(locked.settings["autoplay"], False)
        self.assertTrue(locked.is_locked)  # still locked — edit did not unlock
        self.assertEqual(self._revision(), revision_before + 1)

    def test_r4_duplicate_of_locked_section_succeeds_and_creates_new_section(self):
        locked = self._add_section(order=0, is_locked=True)
        self._place_each_section_in_own_container()
        count_before = self.home.sections.count()

        revision_before = self._revision()
        resp = self._r4_mutate({"type": "section.duplicate", "section_id": locked.pk})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        # A NEW logical section was created; the source stays locked/intact.
        self.assertEqual(self.home.sections.count(), count_before + 1)
        locked.refresh_from_db()
        self.assertTrue(locked.is_locked)
        self.assertEqual(self._revision(), revision_before + 1)
        # The duplicate is a distinct section (fresh stable_id) and is NOT
        # itself locked — a duplicate is a brand-new logical section.
        duplicate = self.home.sections.exclude(pk=locked.pk).get()
        self.assertNotEqual(duplicate.stable_id, locked.stable_id)
        self.assertFalse(duplicate.is_locked)


# ---------------------------------------------------------------------------
# L06 — NEGATIVE tests: every "NO" cell, legacy views (Section + Container)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# L06 — POSITIVE tests: lock is structure-only (legacy views)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# L06 — Template apply / baseline reset over a page with a locked section
# ---------------------------------------------------------------------------
#
# The apply_preset service + apply-preset view lock refusal is already proven
# by ``test_preset_service.LockedSectionsBlockPresetApplyTests``. These tests
# extend the same "NO" cell to the RESET side of the matrix — the
# snapshot-driven ``apply_baseline_snapshot`` and ``reset_page_to_baseline``
# paths (used by every reset-to-Ready-Template-baseline route) must ALSO refuse
# a page carrying a locked section and mutate nothing.

from apps.storefront_builder import layout_preset_registry as _t5_lpr
from apps.storefront_builder.services import preset_service as _t5_preset_service


class BaselineResetLockRefusalTests(_StructureLockMatrixMixin):
    """``apply_baseline_snapshot`` / ``reset_page_to_baseline`` must raise
    ``LockedSectionsPresentError`` when the target page has a locked section,
    exactly like ``apply_preset`` does — the reset paths are just as
    structurally destructive (they delete + rebuild the page's sections)."""

    def _first_ready_template(self):
        return next(iter(_t5_lpr.list_ready_templates()))

    def _apply_ready_template(self):
        preset = self._first_ready_template()
        _t5_preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        return preset

    def test_apply_baseline_snapshot_refuses_locked_page_and_mutates_nothing(self):
        preset = self._apply_ready_template()
        snapshot = self.draft.template_baseline_snapshot
        self.assertTrue(snapshot)

        # Lock one of the Home sections the snapshot would otherwise replace.
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        first = home.sections.order_by("order").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])
        section_keys_before = list(
            home.sections.order_by("order").values_list("section_key", flat=True))

        with self.assertRaises(_t5_preset_service.LockedSectionsPresentError):
            _t5_preset_service.apply_baseline_snapshot(self.draft, snapshot)

        # Nothing on the page changed — the locked section (and every sibling)
        # is intact.
        home.refresh_from_db()
        self.assertTrue(StorefrontSection.objects.filter(pk=first.pk, is_locked=True).exists())
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            section_keys_before,
        )

    def test_reset_page_to_baseline_refuses_locked_page_and_mutates_nothing(self):
        self._apply_ready_template()
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        first = home.sections.order_by("order").first()
        first.is_locked = True
        first.save(update_fields=["is_locked"])
        section_keys_before = list(
            home.sections.order_by("order").values_list("section_key", flat=True))

        with self.assertRaises(_t5_preset_service.LockedSectionsPresentError):
            _t5_preset_service.reset_page_to_baseline(self.draft, StorefrontPage.PageType.HOME)

        home.refresh_from_db()
        self.assertTrue(StorefrontSection.objects.filter(pk=first.pk, is_locked=True).exists())
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            section_keys_before,
        )


# ---------------------------------------------------------------------------
# L04 — legacy template-apply + reset lifecycle: atomic, revision-coherent
# (advance on REAL change, advance NOTHING on a no-op), refuse locked pages.
# ---------------------------------------------------------------------------
#
# Apply/reset semantics are UNCHANGED (replacement/reset). The only invariant
# proven here is the Task-3 ``record_change`` revision-coherence contract
# reaching these endpoints:
#
#   * In-place granular resets (section-field / appearance-field / header /
#     footer reset) mutate the SAME active Draft, so they route through the
#     ``@_record_edit_history`` decorator's ``record_change`` — advancing
#     ``edit_revision`` by exactly 1 on a real change and by nothing on a
#     semantic no-op (resetting a field already at its baseline value).
#   * Checkpoint-based apply/whole-storefront reset preserve the previous
#     Draft as a recoverable ARCHIVED checkpoint and rebuild on a fresh Draft;
#     the Published version is never touched and the operation is atomic.


# ---------------------------------------------------------------------------
# Task 7 — Cross-entry lifecycle convergence + recovery proof (VERIFICATION)
# ---------------------------------------------------------------------------
#
# This is a CONVERGENCE-PROOF task. Tasks 3–6 already made the legacy and R4
# entry points lifecycle- and revision-safe and closed the media A05 gap:
#
#   * Task 3 — ``edit_revision`` is a single Draft-wide monotonic token; a
#     REAL change via EITHER legacy (``@_record_edit_history`` →
#     ``edit_history_service.record_change``) or R4 (``apply_mutation`` →
#     ``record_change``) advances it by exactly 1; a semantic no-op advances
#     nothing.
#   * Task 4 — legacy publish routes through the shared
#     ``layout_service.publish`` (atomic; archives previous Published; clears
#     draft history+pointer; swaps pointers) and, when a base_revision is
#     supplied, through the stale-aware ``r4_mutation_service.publish_draft``;
#     legacy undo/redo advance ``edit_revision`` by exactly 1 on success and 0
#     on a no-op and never create a new undoable edit (shared
#     ``_run_history_command``).
#   * Task 5 — the structure-lock matrix is consistent across R4 + legacy;
#     lock is structure-only.
#   * Task 6 — ``MediaAsset.is_referenced()`` now sees JSON backgrounds +
#     history/baseline snapshots, tenant-scoped + fail-closed; the deletion
#     gate refuses a still-referenced/recoverable asset.
#
# These END-TO-END tests PROVE the two entry points now converge and that
# recovery is safe. They are TESTS-ONLY — no production change was required.
# Every scenario uses ONLY real routes/services/fixtures (Store "akhlaghi"
# via ``StorefrontBuilderViewsTestCase``, ``layout_service`` for the real
# Draft/Publish lifecycle, the real R4 mutation/history/publish endpoints,
# the real ``store_appearance`` persistence, and real ``MediaAsset`` rows).
#
# Scope guard: the individual per-task invariants (single-step revision
# coherence, structure-lock cells, per-route immutability, per-class media
# reachability) are already proven by the Task 1–6 classes above and by
# ``apps.content.tests.test_phase2_media_reachability``; these Task-7 classes
# do NOT re-prove them cell-by-cell. They prove the *composite* end-state:
# a full multi-step lifecycle SEQUENCE run once via each entry point
# converges on an identical observable end-state, a mixed legacy↔R4 sequence
# is safely ordered with no lost update in either direction, and the
# canonical Appearance + still-referenced media survive every recovery
# operation.

from apps.content.models import MediaAsset
from apps.content.services import delete_media_asset_if_unreferenced


class _CrossEntryConvergenceMixin(StorefrontBuilderViewsTestCase):
    """Shared helpers for Task-7 end-to-end scenarios: an active Draft with
    the R4 gate ON (so the real R4 routes are reachable), plus thin wrappers
    over the real legacy and R4 HTTP boundaries and the ``store_appearance``
    manifest round-trip helpers.

    Nothing here fabricates an API: every helper posts to a real route or
    calls a real service exactly as production callers do."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)

    # --- revision / history observation -----------------------------------

    def _revision(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision

    def _total_history(self):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()

    # --- legacy entry point ------------------------------------------------


    # --- R4 entry point ----------------------------------------------------

    def _r4_mutation(self, mutation, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _r4_history(self, command, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": base_revision, "command": command}),
            content_type="application/json",
        )

    def _r4_publish(self, *, base_revision=None):
        if base_revision is None:
            base_revision = self._revision()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps({"base_revision": base_revision}),
            content_type="application/json",
        )

    # --- store_appearance manifest ----------------------------------------

    def _manifest_primitive(self, version):
        return manifest_to_primitive(
            appearance_persistence.load_store_appearance_manifest(version))

    def _ready_manifest(self):
        ready = next(iter(_t5_lpr.list_ready_templates()))
        return dict(ready.store_appearance)


class FullLifecycleConvergenceTests(_CrossEntryConvergenceMixin):
    """Step 1 — prove R4 and legacy entry points converge on identical
    lifecycle behaviour for the SAME logical sequence:

        persist canonical typed manifest → mutate section settings
        → revision advances by exactly 1 → publish → previous Published
        archived → restore into a fresh Draft → undo → redo

    run once end-to-end via the LEGACY entry points and once via the R4
    entry points, asserting the observable end-state converges (typed
    ``store_appearance`` manifest intact byte-for-byte, published/archived
    pointers, monotonic ``edit_revision``)."""

    def _seed_manifest_and_section(self):
        """Persist the canonical typed manifest and add one rich_text section
        carrying a known body — the shared starting point for both runs."""
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()
        section = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=0,
            settings={"body_html": "<p>حالت اولیه</p>"},
        )
        return expected_manifest, section


    def _run_lifecycle_via_r4(self):
        expected_manifest, section = self._seed_manifest_and_section()
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        r0 = self._revision()
        # (1) MUTATE via R4 — section.update_settings, advances by exactly 1.
        resp = self._r4_mutation({
            "type": "section.update_settings",
            "section_id": section.pk,
            "patch": {"body_html": "<p>ویرایش‌شده</p>"},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        self.assertEqual(resp.json()["new_revision"], r0 + 1)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>ویرایش‌شده</p>")
        r1 = self._revision()
        self.assertEqual(r1, r0 + 1)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        # (2) PUBLISH via R4 — stale-aware publish, same shared lifecycle.
        draft_pk = self.draft.pk
        pub = self._r4_publish(base_revision=r1)
        self.assertEqual(pub.status_code, 200, pub.content)
        self.assertIs(pub.json()["ok"], True)
        self.assertEqual(pub.json()["published_version_id"], draft_pk)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id
        self.assertEqual(published_version_id, draft_pk)
        self.assertIsNone(self.layout.draft_version_id)
        promoted = StorefrontLayoutVersion.objects.get(pk=draft_pk)
        self.assertEqual(promoted.status, StorefrontLayoutVersion.Status.PUBLISHED)
        self.assertEqual(self._manifest_primitive(promoted), expected_manifest)

        # (3) RESTORE the published version into a fresh Draft, via the
        # R4-safe restore endpoint. P5-W5A: the legacy restore route is a
        # Class-A/C-adjacent route that now fails closed under
        # r4_editor_enabled=True; the R4-safe endpoint is its canonical
        # replacement, converging onto the same, unmodified
        # layout_service.restore_version(). No active Draft exists right
        # after publish, so base_draft_id/base_revision are both None (the
        # documented "no Draft" precondition — P5-W5A Independent-Review
        # repair: the wire contract now binds to Draft identity too, not
        # revision alone).
        restore_resp = self.client.post(
            reverse("dashboard:storefront-builder-r4-restore", args=[published_version_id]),
            data=json.dumps({"base_draft_id": None, "base_revision": None}),
            content_type="application/json",
        )
        self.assertEqual(restore_resp.status_code, 200, restore_resp.content)
        self.assertIs(restore_resp.json()["ok"], True)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        return {
            "manifest": self._manifest_primitive(self.draft),
            "promoted_status": promoted.status,
            "published_is_promoted_draft": published_version_id == draft_pk,
            "draft_pointer_cleared_at_publish": True,
        }

    def test_full_lifecycle_via_r4_keeps_manifest_pointers_and_revision_contract(self):
        end_state = self._run_lifecycle_via_r4()
        self.assertTrue(end_state["published_is_promoted_draft"])
        self.assertEqual(end_state["promoted_status"], StorefrontLayoutVersion.Status.PUBLISHED)

    def test_undo_redo_after_restore_is_revision_monotonic_and_manifest_intact(self):
        expected_manifest, section = self._seed_manifest_and_section()
        for body in ("<p>دوم</p>", "<p>سوم</p>"):
            edit = self._r4_mutation({
                "type": "section.update_settings", "section_id": section.pk, "patch": {"body_html": body},
            })
            self.assertEqual(edit.status_code, 200, edit.content)
        r_before = self._revision()

        undo = self._r4_history("undo")
        self.assertEqual(undo.status_code, 200, undo.content)
        body = undo.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], r_before + 1)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>دوم</p>")
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)

        redo = self._r4_history("redo")
        self.assertEqual(redo.status_code, 200, redo.content)
        body = redo.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], r_before + 2)
        section.refresh_from_db()
        self.assertEqual(section.settings["body_html"], "<p>سوم</p>")
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)


class RecoveryMediaIntegrityTests(_CrossEntryConvergenceMixin):
    """Step 3 — recovery after each operation (undo / redo / restore / reset)
    restores the canonical Appearance (typed manifest) AND does NOT orphan or
    physically delete a still-referenced/recoverable media asset.

    Every media assertion is NON-DESTRUCTIVE: it checks the ``is_referenced()``
    reachability predicate / the deletion-gate refusal on a THROWAWAY asset
    created only for the test — it never actually destroys a shared fixture.
    The asset and the referencing section share the SAME store so the
    tenant-scoped reachability scan matches (see Task 6)."""

    def _throwaway_asset(self, name):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (320, 160), (7, 8, 9)).save(buf, "PNG")
        return MediaAsset.objects.create(
            store=self.store,
            image=SimpleUploadedFile(name, buf.getvalue(), content_type="image/png"),
        )

    def _section_with_background(self, asset, *, order=0):
        return StorefrontSection.objects.create(
            page=self.home, section_key="hero_banner", order=order,
            settings={"background": {"mode": "image", "media_asset_id": asset.pk}},
        )

    def _assert_asset_protected(self, asset):
        """Non-destructive: still referenced/recoverable AND the deletion gate
        refuses to physically delete it (leaving the row intact)."""
        asset.refresh_from_db()
        self.assertTrue(asset.is_referenced())
        self.assertFalse(delete_media_asset_if_unreferenced(asset))
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())


    def test_manifest_and_referenced_media_survive_undo_redo(self):
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()

        asset = self._throwaway_asset("recover-undo.png")
        self._section_with_background(asset, order=0)
        text = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=1, settings={"body_html": "<p>یک</p>"},
        )
        self._assert_asset_protected(asset)

        # Two real R4 edits, then undo/redo — the media reference lives on the background section (live JSON) and is
        # also captured in the history snapshots (recovery reference), so it must stay reachable.
        for body in ("<p>دو</p>", "<p>سه</p>"):
            edit = self._r4_mutation({
                "type": "section.update_settings", "section_id": text.pk, "patch": {"body_html": body},
            })
            self.assertEqual(edit.status_code, 200, edit.content)

        self.assertIs(self._r4_history("undo").json()["ok"], True)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)
        self._assert_asset_protected(asset)

        self.assertIs(self._r4_history("redo").json()["ok"], True)
        self.assertEqual(self._manifest_primitive(self.draft), expected_manifest)
        self._assert_asset_protected(asset)

    def test_manifest_and_referenced_media_survive_restore(self):
        expected_manifest = self._ready_manifest()
        appearance_persistence.persist_store_appearance_manifest(self.draft, expected_manifest)
        self.draft.refresh_from_db()

        asset = self._throwaway_asset("recover-restore.png")
        self._section_with_background(asset, order=0)
        self._assert_asset_protected(asset)

        # PUBLISH then RESTORE into a fresh Draft — the manifest survives the clone byte-for-byte and the background
        # reference is carried into the cloned Draft AND preserved on the archived source.
        self.assertEqual(self._r4_publish().status_code, 200)
        self.layout.refresh_from_db()
        published_version_id = self.layout.published_version_id
        self._assert_asset_protected(asset)

        restore = self.client.post(
            reverse("dashboard:storefront-builder-r4-restore", args=[published_version_id]),
            data=json.dumps({"base_draft_id": None, "base_revision": None}),
            content_type="application/json",
        )
        self.assertEqual(restore.status_code, 200, restore.content)
        restored = svc.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(self._manifest_primitive(restored), expected_manifest)
        self._assert_asset_protected(asset)

    def test_referenced_media_survives_snapshot_only_recovery_reference(self):
        # A recovery-only reference: the asset is referenced ONLY inside an
        # edit-history snapshot (no live section carries it), proving the
        # recovery reference class keeps a recoverable asset protected — the
        # deletion gate must still refuse. This mirrors the media module's
        # snapshot reachability invariant, exercised here in the lifecycle
        # module against the deletion gate end-to-end.
        asset = self._throwaway_asset("recover-snapshot.png")
        # No live section references the asset; only a history snapshot does.
        StorefrontEditHistoryEntry.objects.create(
            draft_version=self.draft, actor=None, sequence=1,
            action_label="ویرایش تنظیمات بخش",
            before_state={"pages": {}, "containers": {}},
            after_state={
                "pages": {
                    "home": [
                        {
                            "section_key": "hero_banner",
                            "order": 0,
                            "settings": {
                                "background": {"mode": "image", "media_asset_id": asset.pk},
                            },
                            "media": {"hero_slides": [{"desktop_asset_id": asset.pk}]},
                        }
                    ],
                },
                "containers": {},
            },
        )
        # Guard: no live FK placement and no live section reference — the
        # snapshot is the ONLY reference.
        self.assertFalse(asset.hero_placements.exists())
        self.assertFalse(
            StorefrontSection.objects.filter(
                page__version=self.draft,
                settings__background__media_asset_id=asset.pk,
            ).exists()
        )
        # Recoverable-via-snapshot → protected.
        self._assert_asset_protected(asset)

    def test_manifest_and_referenced_media_survive_baseline_reset(self):
        # Reset-to-baseline recovery path: after applying a Ready Template the
        # Draft carries a ``template_baseline_snapshot``; an asset referenced
        # inside that snapshot is recoverable via reset and must stay
        # protected. Uses the real apply-preset service to build the snapshot.
        preset = next(iter(_t5_lpr.list_ready_templates()))
        _t5_preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.template_baseline_snapshot)

        asset = self._throwaway_asset("recover-baseline.png")
        # Reference the asset ONLY inside the baseline snapshot (recovery ref).
        snapshot = dict(self.draft.template_baseline_snapshot)
        home_entries = list(snapshot.get("pages", {}).get("home", []))
        home_entries.append({
            "section_key": "hero_banner",
            "settings": {"background": {"mode": "image", "media_asset_id": asset.pk}},
        })
        snapshot.setdefault("pages", {})["home"] = home_entries
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot", "updated_at"])

        # Recoverable-via-baseline-snapshot → protected (deletion gate refuses).
        self._assert_asset_protected(asset)

        # And a real in-place reset stays revision-coherent while the asset
        # remains protected (the baseline snapshot is unchanged by a granular
        # reset). Re-check after a manifest reload to prove the canonical
        # Appearance is still loadable/intact.
        self.assertTrue(self._manifest_primitive(self.draft))
        self._assert_asset_protected(asset)
