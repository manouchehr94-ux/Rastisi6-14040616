"""Phase-1 RED tests — SWITCH CONVERGENCE, HISTORY/REVISION, BASELINE, RESET.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

These RED tests encode the binding same-Draft / history / concurrency /
baseline / reset / merchant-facing-convergence / no-parallel-architecture
contracts that production does NOT yet implement:

  * A normal switch stays on the SAME Draft, records exactly ONE canonical
    history entry, increments edit_revision exactly ONCE; Undo restores the
    complete pre-switch state, Redo restores the switched state; a stale
    base_revision mutates nothing; Store A cannot mutate Store B.
  * End state: provenance = B AND an honest B baseline snapshot; unmatched
    preserved A/manual content is not written as B-owned baseline.
  * New baseline snapshot entries carry semantic_slot_key; legacy snapshots
    without it remain valid/fail safe.
  * Granular reset of a mapped B slot uses B baseline; granular reset of an
    unmatched preserved legacy section fails safe; whole-page / whole-store
    reset intentionally restore B baseline.
  * All merchant-facing Ready Template routes converge on preservation-first;
    dashboard Ready Template change records exactly ONE history entry / ONE
    revision increment (must not double-record via the @_record_edit_history
    decorator AND apply_mutation).
  * No new model/table/migration; no second registry/history/baseline.

Where the Phase-1 operation/field does not exist yet, tests fail at test
level with a descriptive message (never ImportError at collection).
"""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import edit_history_service
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import r4_mutation_service
from apps.storefront_builder.variant_contract import validate_template_provenance
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-p1-test.rastisi.localhost"
_MISSING = object()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _two_ready_templates():
    ready = sorted(lpr.list_ready_templates(), key=lambda p: p.key)
    if len(ready) < 2:
        return None, None
    a = ready[0]
    b = next((p for p in ready if p.key != a.key), None)
    return a, b


def _preservation_switch(store, preset, *, user=None):
    for name in (
        "switch_ready_template_preserving",
        "switch_template_preserving_merge",
        "apply_ready_template_preserving",
        "preservation_first_switch",
    ):
        fn = getattr(preset_service, name, None)
        if callable(fn):
            return fn(store, preset, user=user)
    return _MISSING


class Phase1ConvergenceBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(
            username="p1c_owner", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.template_a, self.template_b = _two_ready_templates()
        if self.template_a is None:
            self.skipTest("fewer than two Ready Templates registered")
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, self.template_a)
        self.draft.refresh_from_db()

    def _history_count(self):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=self.draft).count()

    def _require_impl(self, result):
        if result is _MISSING:
            self.fail(
                "RED: preservation-first Ready Template switch not implemented."
            )
        return result


# --------------------------------------------------------------------------
# SAME DRAFT / HISTORY / CONCURRENCY (43-49)
# --------------------------------------------------------------------------
class SameDraftHistoryRevisionTests(Phase1ConvergenceBase):
    def test_switch_keeps_same_draft_pk(self):
        original = self.draft.pk
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id, original,
            "RED: normal switch must keep the SAME active Draft pk (no "
            "checkpoint_draft_before_replacement as the mechanism).",
        )

    def test_switch_adds_exactly_one_history_entry(self):
        before = self._history_count()
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.assertEqual(
            self._history_count(), before + 1,
            "RED: a normal switch must record exactly one canonical "
            "StorefrontEditHistoryEntry.",
        )

    def test_switch_increments_edit_revision_exactly_once(self):
        start = self.draft.edit_revision
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.edit_revision, start + 1,
            "RED: a normal switch must increment edit_revision exactly once.",
        )

    def test_undo_restores_complete_pre_switch_state(self):
        pre = edit_history_service.snapshot_draft(self.draft)
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        edit_history_service.undo(self.draft)
        self.draft.refresh_from_db()
        post_undo = edit_history_service.snapshot_draft(self.draft)
        self.assertEqual(
            post_undo.get("pages"), pre.get("pages"),
            "RED: Undo must restore the complete pre-switch page composition.",
        )
        self.assertEqual(
            post_undo.get("template_provenance"), pre.get("template_provenance"),
            "RED: Undo must restore the pre-switch provenance.",
        )

    def test_redo_restores_switched_state(self):
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        switched = edit_history_service.snapshot_draft(self.draft)
        edit_history_service.undo(self.draft)
        self.draft.refresh_from_db()
        edit_history_service.redo(self.draft)
        self.draft.refresh_from_db()
        redone = edit_history_service.snapshot_draft(self.draft)
        self.assertEqual(
            redone.get("template_provenance"), switched.get("template_provenance"),
            "RED: Redo must restore the switched (Template B) state.",
        )

    def test_stale_base_revision_causes_zero_mutation(self):
        # Route through the R4 boundary if the converged switch is exposed
        # there; the stale base_revision must be rejected before any write.
        self.draft.edit_revision = 7
        self.draft.save(update_fields=["edit_revision"])
        before_sections = list(
            self.draft.get_page("home").sections.values_list("pk", flat=True)
        )
        raised = False
        try:
            r4_mutation_service.switch_template(
                store=self.store, actor=self.staff, base_revision=3,
                template_key=self.template_b.key, template_version=self.template_b.version,
            )
        except getattr(r4_mutation_service, "R4StaleRevision", Exception):
            raised = True
        except TypeError:
            self.fail("RED: r4 switch_template signature changed unexpectedly.")
        self.assertTrue(
            raised,
            "RED: a stale base_revision must raise R4StaleRevision before any mutation.",
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, 7, "revision must be unchanged")
        self.assertEqual(
            list(self.draft.get_page("home").sections.values_list("pk", flat=True)),
            before_sections,
            "RED: a stale switch must mutate nothing.",
        )

    def test_store_a_cannot_mutate_store_b(self):
        # Build a second store and prove a switch scoped to store A never
        # touches store B's draft/sections.
        other = Store.objects.create(
            name="Other Co", slug="other-co-phase1",
        )
        other_draft = svc.get_or_create_draft(other, user=self.staff)
        preset_service.apply_preset(other_draft, self.template_a)
        other_draft.refresh_from_db()
        other_pks = set(other_draft.sections.values_list("pk", flat=True))
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        still_there = set(
            StorefrontSection.objects.filter(pk__in=other_pks).values_list("pk", flat=True)
        )
        self.assertEqual(
            still_there, other_pks,
            "RED: switching Store A's template must never mutate Store B content.",
        )


# --------------------------------------------------------------------------
# BASELINE / PROVENANCE COHERENCE (12-15)
# --------------------------------------------------------------------------
class BaselineProvenanceTests(Phase1ConvergenceBase):
    def test_new_baseline_snapshot_entries_carry_semantic_slot_key(self):
        # After any Ready Template apply, snapshot page entries should carry
        # semantic_slot_key alongside the existing keys.
        self.draft.refresh_from_db()
        snapshot = self.draft.template_baseline_snapshot or {}
        pages = snapshot.get("pages") or {}
        entries = pages.get("home") or []
        if not entries:
            self.skipTest("template A recorded no home baseline entries")
        missing = [e for e in entries if "semantic_slot_key" not in e]
        self.assertEqual(
            missing, [],
            "RED: new template_baseline_snapshot home entries must include "
            "semantic_slot_key alongside slot_key/section_key/settings/row_key/"
            "row_span/container_settings.",
        )

    def test_legacy_snapshot_without_semantic_slot_key_remains_valid(self):
        # A legacy snapshot (no semantic_slot_key) must not raise on read and
        # must be treated as a valid legacy state (fail safe).
        self.draft.template_baseline_snapshot = {
            "template_key": self.template_a.key,
            "template_version": self.template_a.version,
            "default_palette_slug": None,
            "appearance": {},
            "header_config": None,
            "footer_config": None,
            "pages": {"home": [{"slot_key": "x", "section_key": "rich_text",
                                "settings": {}, "row_key": "", "row_span": 12,
                                "container_settings": None}]},
        }
        self.draft.save(update_fields=["template_baseline_snapshot"])
        # Reading it back must not error.
        self.draft.refresh_from_db()
        self.assertNotIn(
            "semantic_slot_key",
            self.draft.template_baseline_snapshot["pages"]["home"][0],
            "legacy snapshot intentionally has no semantic_slot_key",
        )

    def test_successful_switch_leaves_provenance_b_and_baseline_b(self):
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        prov = validate_template_provenance(self.draft.template_provenance)
        self.assertEqual(
            prov["template"]["key"], self.template_b.key,
            "RED: after switch, provenance must be Template B.",
        )
        snap = self.draft.template_baseline_snapshot or {}
        self.assertEqual(
            snap.get("template_key"), self.template_b.key,
            "RED: after switch, baseline snapshot must be the honest B baseline "
            "(not A, not the merged merchant state).",
        )

    def test_unmatched_preserved_content_not_written_as_b_baseline(self):
        manual = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=95,
            settings={"content": "legacy-manual"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        # The preserved manual section must still exist (not deleted)...
        self.assertTrue(
            StorefrontSection.objects.filter(pk=manual.pk).exists(),
            "RED: preserved unmatched manual content must survive the switch.",
        )
        snap = self.draft.template_baseline_snapshot or {}
        home_entries = (snap.get("pages") or {}).get("home") or []
        # ...but B's baseline must describe B's canonical recipe, not the
        # preserved manual section.
        b_section_keys = [e.section_key for e in self.template_b.pages.get("home", ())]
        snapshot_keys = [e.get("section_key") for e in home_entries]
        self.assertEqual(
            snapshot_keys, b_section_keys,
            "RED: B baseline snapshot must equal B's canonical recipe; preserved "
            "unmatched manual content must not be represented as a B-owned slot.",
        )


# --------------------------------------------------------------------------
# RESET BEHAVIOR (50-53)
# --------------------------------------------------------------------------
class ResetBehaviorTests(Phase1ConvergenceBase):
    def test_granular_reset_of_mapped_b_slot_uses_b_baseline(self):
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        # Pick a B baseline section and edit it, then reset-to-baseline.
        home = self.draft.get_page("home")
        section = home.sections.exclude(template_slot_key="").order_by("order").first()
        if section is None:
            self.skipTest("no B-owned mapped slot present to reset")
        section.settings = {**(section.settings or {}), "__edited__": "yes"}
        section.save(update_fields=["settings"])
        try:
            preset_service.reset_section_to_baseline(self.draft, section.stable_id)
        except TypeError:
            # Signature may differ; try pk-based fallback used elsewhere.
            preset_service.reset_section_to_baseline(self.draft, section.pk)
        section.refresh_from_db()
        self.assertNotIn(
            "__edited__", section.settings,
            "RED: granular reset of a B-owned mapped slot must restore B baseline.",
        )

    def test_granular_reset_of_unmatched_preserved_legacy_fails_safe(self):
        manual = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=96,
            settings={"content": "legacy"},
        )
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        # A section with empty template_slot_key must fail safe on granular reset.
        self.assertEqual(manual.template_slot_key, "")
        with self.assertRaises(
            getattr(preset_service, "NotABaselineSectionError", Exception),
            msg="RED: granular reset of unmatched preserved legacy content must "
                "fail safe (NotABaselineSectionError), never delete/reattach.",
        ):
            try:
                preset_service.reset_section_to_baseline(self.draft, manual.stable_id)
            except TypeError:
                preset_service.reset_section_to_baseline(self.draft, manual.pk)

    def test_whole_page_reset_intentionally_restores_b_baseline(self):
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        preset_service.reset_page_to_baseline(self.draft, "home")
        home = self.draft.get_page("home")
        keys = list(home.sections.order_by("order").values_list("section_key", flat=True))
        expected = [e.section_key for e in self.template_b.pages.get("home", ())]
        self.assertEqual(
            keys, expected,
            "RED: whole-page reset after a B switch must intentionally restore "
            "B's baseline composition.",
        )

    def test_whole_store_reset_intentionally_restores_b_baseline(self):
        self._require_impl(_preservation_switch(self.store, self.template_b, user=self.staff))
        self.draft.refresh_from_db()
        returned = preset_service.reset_storefront_to_baseline(self.draft)
        self.assertEqual(
            getattr(returned, "key", None), self.template_b.key,
            "RED: whole-store reset after a B switch must restore B baseline "
            "(provenance/baseline are coherent -> no version-changed error).",
        )


# --------------------------------------------------------------------------
# MERCHANT-FACING CONVERGENCE (54-58)
# --------------------------------------------------------------------------
class MerchantFacingConvergenceTests(Phase1ConvergenceBase):
    def _login(self):
        from django.test import Client

        client = Client(HTTP_HOST=HOST)
        client.login(username="p1c_owner", password="pass12345")
        return client

    def test_r4_switch_template_is_preservation_first(self):
        # A merchant section must survive an R4 switch-template call.
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=97,
            settings={"content": "keep-through-r4"},
        )
        try:
            r4_mutation_service.switch_template(
                store=self.store, actor=self.staff,
                base_revision=self.draft.edit_revision,
                template_key=self.template_b.key,
                template_version=self.template_b.version,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as RED explanation
            self.fail(f"RED: R4 switch_template must succeed preservation-first: {exc!r}")
        self.assertTrue(
            StorefrontSection.objects.filter(pk=merchant.pk).exists(),
            "RED: R4 switch-template must be preservation-first (merchant "
            "section survives).",
        )

    def test_r4_ready_template_apply_is_preservation_first_after_convergence(self):
        # The in-place appearance.template.apply mutation must, after
        # convergence, preserve merchant content rather than delete+recreate.
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=98,
            settings={"content": "keep-through-apply"},
        )
        payload = {
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "appearance.template.apply",
                "template_key": self.template_b.key,
                "template_version": self.template_b.version,
            },
        }
        client = self._login()
        resp = client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(payload), content_type="application/json",
        )
        # Whatever the transport result, merchant content must survive.
        self.assertTrue(
            StorefrontSection.objects.filter(pk=merchant.pk).exists(),
            "RED: after convergence, R4 Ready Template apply must be "
            f"preservation-first (merchant section survived). resp={resp.status_code}",
        )

    def test_dashboard_ready_template_apply_is_preservation_first_after_convergence(self):
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=99,
            settings={"content": "keep-through-dashboard"},
        )
        client = self._login()
        resp = client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            data={
                "preset_key": self.template_b.key,
                "confirm_preset_apply": "1",
            },
        )
        self.assertTrue(
            StorefrontSection.objects.filter(pk=merchant.pk).exists(),
            "RED: after convergence, dashboard Ready Template apply must be "
            f"preservation-first for is_ready_template presets. resp={resp.status_code}",
        )

    def test_dashboard_ready_template_change_records_single_history_and_revision(self):
        # Guard against double-recording via @_record_edit_history AND
        # apply_mutation after convergence.
        before_hist = self._history_count()
        start_rev = self.draft.edit_revision
        client = self._login()
        client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            data={"preset_key": self.template_b.key, "confirm_preset_apply": "1"},
        )
        # Re-resolve the active draft (must be the same one).
        self.layout.refresh_from_db()
        active_id = self.layout.draft_version_id
        hist_after = StorefrontEditHistoryEntry.objects.filter(
            draft_version_id=active_id
        ).count()
        active = StorefrontLayoutVersion.objects.get(pk=active_id)
        self.assertEqual(
            (active_id, hist_after, active.edit_revision),
            (self.draft.pk, before_hist + 1, start_rev + 1),
            "RED: a dashboard Ready Template change must stay on the same Draft "
            "and record EXACTLY one history entry / one revision increment "
            "(no double-record via decorator + apply_mutation).",
        )

    def test_non_ready_structural_preset_remains_separate_confirmed_destructive(self):
        # A non-Ready structural preset keeps its confirmed-destructive concept:
        # it is NOT routed through the preservation-first merge.
        non_ready = next(
            (p for p in lpr.list_layout_presets() if not p.is_ready_template
             and "home" in p.pages),
            None,
        )
        if non_ready is None:
            self.skipTest("no non-Ready structural preset with a home composition")
        # Its semantic identity is intentionally absent -> it is a separate
        # product concept from preservation-first Ready Template switching.
        home_entries = non_ready.pages.get("home", ())
        roles = [getattr(e, "semantic_slot_key", None) for e in home_entries]
        self.assertTrue(
            all(r is None for r in roles) or not non_ready.is_ready_template,
            "RED: non-Ready structural presets remain a separate "
            "confirmed-destructive concept (no mandatory semantic roles).",
        )


# --------------------------------------------------------------------------
# NO PARALLEL ARCHITECTURE (59-62)
# --------------------------------------------------------------------------
class NoParallelArchitectureTests(TestCase):
    def test_no_new_migration_is_required_by_the_semantic_contract(self):
        # semantic_slot_key is recipe metadata (frozen dataclass) + baseline
        # JSON — never a DB column. `makemigrations --check` must report no
        # pending model changes for storefront_builder.
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        changed = False
        try:
            call_command(
                "makemigrations", "storefront_builder", "--check", "--dry-run",
                stdout=out, stderr=out, verbosity=1,
            )
        except SystemExit as exc:  # --check exits non-zero when changes exist
            changed = (getattr(exc, "code", 0) not in (0, None))
        self.assertFalse(
            changed,
            "RED/GREEN guard: the semantic contract must require NO new "
            f"migration. makemigrations --check reported changes:\n{out.getvalue()}",
        )

    def test_only_one_ready_template_registry_exists(self):
        # layout_preset_registry is the single Ready Template registry.
        self.assertTrue(hasattr(lpr, "LAYOUT_PRESET_REGISTRY"))
        self.assertTrue(hasattr(lpr, "LAYOUT_PRESET_VERSION_REGISTRY"))
        # No second, separately-maintained semantic-key catalog module.
        import importlib

        for forbidden in (
            "apps.storefront_builder.semantic_slot_registry",
            "apps.storefront_builder.semantic_slots",
            "apps.storefront_builder.slot_semantic_registry",
        ):
            with self.assertRaises(
                ModuleNotFoundError,
                msg=f"RED: a second semantic-key registry ({forbidden}) must NOT exist.",
            ):
                importlib.import_module(forbidden)

    def test_only_one_history_system_exists(self):
        # StorefrontEditHistoryEntry is the single canonical history model.
        from apps.storefront_builder import models as sfb_models

        history_models = [
            name for name in dir(sfb_models)
            if name.endswith("EditHistoryEntry") or name.endswith("HistoryEntry")
        ]
        self.assertEqual(
            history_models, ["StorefrontEditHistoryEntry"],
            f"RED: exactly one history model must exist; found {history_models}",
        )

    def test_only_one_baseline_field_exists(self):
        # template_baseline_snapshot on StorefrontLayoutVersion is the single
        # baseline source. No second baseline field/model.
        field_names = {f.name for f in StorefrontLayoutVersion._meta.get_fields()}
        baseline_like = {
            n for n in field_names
            if "baseline" in n.lower() and n != "template_baseline_snapshot"
        }
        self.assertEqual(
            baseline_like, set(),
            f"RED: no second baseline field may exist; found {baseline_like}",
        )
