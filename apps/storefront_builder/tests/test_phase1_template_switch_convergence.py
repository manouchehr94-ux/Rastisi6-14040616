"""Phase-1 RED tests — SWITCH CONVERGENCE, HISTORY/REVISION, BASELINE, RESET.

Architecture Convergence / Phase 1 — Safe Ready Template Switching /
Merchant Preservation.

Corrective pass (Architect review of b1107507). These tests now:

  * Blocker 1: use the EXISTING canonical ``r4_mutation_service.switch_template``
    entry point (no guessed future function names).
  * Blocker 2/general rule: resolve the ACTIVE Draft after every whole-Draft
    operation (``layout.refresh_from_db(); layout.draft_version``); logical
    identity via stable_id.
  * Blocker 4: call ``preset_service.reset_section_to_baseline(draft, section)``
    with the SECTION OBJECT (no stable_id/pk fallback, no TypeError fallback).
  * Blocker 8: deterministic pair A=``aftab_price`` / B=``almas_luxury``.
  * Blocker 11: HTTP convergence tests assert real success (200 + ok==True /
    valid redirect) AND active-Draft/provenance/merchant-content invariants —
    no false green from a 4xx that merely left content untouched.
  * Blocker 12: Undo/Redo through the canonical R4 command boundary
    ``apply_history_command(store, actor, base_revision, command)`` asserting
    ``changed`` and single revision increment.

The current ``switch_template`` archives + clones a new Draft, so the SAME-Draft
/ single-history-entry / single-revision contracts are expected RED, exposing
real Phase-1 gaps rather than "function missing".
"""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.services import r4_mutation_service
from apps.storefront_builder.variant_contract import validate_template_provenance
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-p1-test.rastisi.localhost"

TEMPLATE_A_KEY = "aftab_price"
TEMPLATE_B_KEY = "almas_luxury"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


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
        self.template_a = lpr.get_layout_preset(TEMPLATE_A_KEY)
        self.template_b = lpr.get_layout_preset(TEMPLATE_B_KEY)
        self.assertIsNotNone(self.template_a, f"{TEMPLATE_A_KEY} must exist")
        self.assertIsNotNone(self.template_b, f"{TEMPLATE_B_KEY} must exist")
        self.assertTrue(self.template_a.is_ready_template)
        self.assertTrue(self.template_b.is_ready_template)
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(self.draft, self.template_a)
        self.draft.refresh_from_db()
        self.original_draft_pk = self.draft.pk

    def _active_draft(self):
        self.layout.refresh_from_db()
        return self.layout.draft_version

    def _switch_to_b(self, *, base_revision=None):
        r4_mutation_service.switch_template(
            store=self.store,
            actor=self.staff,
            base_revision=self.draft.edit_revision if base_revision is None else base_revision,
            template_key=self.template_b.key,
            template_version=self.template_b.version,
        )
        return self._active_draft()

    def _history_count(self, draft):
        return StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count()

    def _login(self):
        client = Client(HTTP_HOST=HOST)
        client.login(username="p1c_owner", password="pass12345")
        return client


# --------------------------------------------------------------------------
# SAME DRAFT / HISTORY / CONCURRENCY (43-49)
# --------------------------------------------------------------------------
class SameDraftHistoryRevisionTests(Phase1ConvergenceBase):
    def test_switch_keeps_same_draft_pk(self):
        self._switch_to_b()
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id, self.original_draft_pk,
            "RED: normal switch must keep the SAME active Draft pk "
            "(current clone/checkpoint switch violates this).",
        )

    def test_switch_adds_exactly_one_history_entry_on_same_draft(self):
        before = self._history_count(self.draft)
        self._switch_to_b()
        # Must be measured on the SAME (still-active) Draft.
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id, self.original_draft_pk,
            "RED: switch must remain on the same Draft to own its history entry.",
        )
        self.assertEqual(
            self._history_count(self.draft), before + 1,
            "RED: a normal switch must record exactly one canonical history entry "
            "on the active Draft.",
        )

    def test_switch_increments_edit_revision_exactly_once(self):
        start = self.draft.edit_revision
        self._switch_to_b()
        self.layout.refresh_from_db()
        active = self.layout.draft_version
        self.assertEqual(
            (self.layout.draft_version_id, active.edit_revision),
            (self.original_draft_pk, start + 1),
            "RED: a normal switch must stay on the same Draft and increment "
            "edit_revision exactly once.",
        )

    def test_undo_via_canonical_command_restores_pre_switch_state(self):
        # Blocker 12: canonical R4 Undo boundary.
        pre_keys = list(
            self.draft.get_page("home").sections.order_by("order").values_list(
                "section_key", flat=True
            )
        )
        pre_provenance = dict(self.draft.template_provenance or {})
        self._switch_to_b()
        active = self._active_draft()
        result = r4_mutation_service.apply_history_command(
            store=self.store, actor=self.staff,
            base_revision=active.edit_revision, command="undo",
        )
        self.assertTrue(
            result.get("changed"),
            "RED: Undo of a switch must report changed=True.",
        )
        restored = self._active_draft()
        self.assertEqual(
            list(restored.get_page("home").sections.order_by("order").values_list(
                "section_key", flat=True)),
            pre_keys,
            "RED: Undo must restore the complete pre-switch composition.",
        )
        self.assertEqual(
            dict(restored.template_provenance or {}), pre_provenance,
            "RED: Undo must restore the pre-switch provenance.",
        )

    def test_redo_via_canonical_command_restores_switched_state(self):
        self._switch_to_b()
        active = self._active_draft()
        switched_provenance = dict(active.template_provenance or {})
        r4_mutation_service.apply_history_command(
            store=self.store, actor=self.staff,
            base_revision=active.edit_revision, command="undo",
        )
        after_undo = self._active_draft()
        rev_before_redo = after_undo.edit_revision
        result = r4_mutation_service.apply_history_command(
            store=self.store, actor=self.staff,
            base_revision=after_undo.edit_revision, command="redo",
        )
        self.assertTrue(result.get("changed"), "RED: Redo must report changed=True.")
        self.assertEqual(
            result.get("new_revision"), rev_before_redo + 1,
            "RED: Redo must increment edit_revision exactly once.",
        )
        redone = self._active_draft()
        self.assertEqual(
            dict(redone.template_provenance or {}), switched_provenance,
            "RED: Redo must restore the switched (Template B) state.",
        )

    def test_stale_base_revision_causes_zero_mutation(self):
        self.draft.edit_revision = 7
        self.draft.save(update_fields=["edit_revision"])
        before_sections = list(
            self.draft.get_page("home").sections.values_list("stable_id", flat=True)
        )
        raised = False
        try:
            r4_mutation_service.switch_template(
                store=self.store, actor=self.staff, base_revision=3,
                template_key=self.template_b.key, template_version=self.template_b.version,
            )
        except getattr(r4_mutation_service, "R4StaleRevision", Exception):
            raised = True
        self.assertTrue(
            raised,
            "RED: a stale base_revision must raise R4StaleRevision before any mutation.",
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, 7, "revision must be unchanged")
        self.assertEqual(
            list(self.draft.get_page("home").sections.values_list("stable_id", flat=True)),
            before_sections,
            "RED: a stale switch must mutate nothing.",
        )

    def test_store_a_cannot_mutate_store_b(self):
        other = Store.objects.create(name="Other Co", slug="other-co-phase1")
        other_draft = svc.get_or_create_draft(other, user=self.staff)
        preset_service.apply_preset(other_draft, self.template_a)
        other_draft.refresh_from_db()
        other_sids = set(other_draft.sections.values_list("stable_id", flat=True))
        self._switch_to_b()
        # Store B's active draft content must be untouched.
        other_layout = svc.get_or_create_layout(other)
        other_layout.refresh_from_db()
        other_active = other_layout.draft_version
        self.assertEqual(
            set(other_active.sections.values_list("stable_id", flat=True)),
            other_sids,
            "RED: switching Store A's template must never mutate Store B content.",
        )


# --------------------------------------------------------------------------
# BASELINE / PROVENANCE COHERENCE (12-15)
# --------------------------------------------------------------------------
class BaselineProvenanceTests(Phase1ConvergenceBase):
    def test_new_baseline_snapshot_entries_carry_semantic_slot_key(self):
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
        self.draft.refresh_from_db()
        self.assertNotIn(
            "semantic_slot_key",
            self.draft.template_baseline_snapshot["pages"]["home"][0],
            "legacy snapshot intentionally has no semantic_slot_key (must read safely)",
        )

    def test_successful_switch_leaves_provenance_b_and_baseline_b(self):
        switched = self._switch_to_b()
        prov = validate_template_provenance(switched.template_provenance)
        self.assertEqual(
            prov["template"]["key"], self.template_b.key,
            "RED: after switch, provenance must be Template B.",
        )
        snap = switched.template_baseline_snapshot or {}
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
        sid = manual.stable_id
        switched = self._switch_to_b()
        self.assertIsNotNone(
            StorefrontSection.objects.filter(page__version=switched, stable_id=sid).first(),
            "RED: preserved unmatched manual content must survive the switch.",
        )
        snap = switched.template_baseline_snapshot or {}
        home_entries = (snap.get("pages") or {}).get("home") or []
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
        switched = self._switch_to_b()
        home = switched.get_page("home")
        section = home.sections.exclude(template_slot_key="").order_by("order").first()
        if section is None:
            self.skipTest("no B-owned mapped slot present to reset")
        section.settings = {**(section.settings or {}), "__edited__": "yes"}
        section.save(update_fields=["settings"])
        # Blocker 4: pass the SECTION OBJECT, no stable_id/pk/TypeError fallback.
        preset_service.reset_section_to_baseline(switched, section)
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
        sid = manual.stable_id
        switched = self._switch_to_b()
        active_manual = StorefrontSection.objects.filter(
            page__version=switched, stable_id=sid
        ).first()
        self.assertIsNotNone(active_manual, "RED: preserved manual section must exist post-switch.")
        self.assertEqual(active_manual.template_slot_key, "")
        with self.assertRaises(
            getattr(preset_service, "NotABaselineSectionError", Exception),
            msg="RED: granular reset of unmatched preserved legacy content must "
                "fail safe (NotABaselineSectionError), never delete/reattach.",
        ):
            preset_service.reset_section_to_baseline(switched, active_manual)

    def test_whole_page_reset_intentionally_restores_b_baseline(self):
        switched = self._switch_to_b()
        preset_service.reset_page_to_baseline(switched, "home")
        keys = list(
            switched.get_page("home").sections.order_by("order").values_list(
                "section_key", flat=True)
        )
        expected = [e.section_key for e in self.template_b.pages.get("home", ())]
        self.assertEqual(
            keys, expected,
            "RED: whole-page reset after a B switch must intentionally restore "
            "B's baseline composition.",
        )

    def test_whole_store_reset_intentionally_restores_b_baseline(self):
        switched = self._switch_to_b()
        returned = preset_service.reset_storefront_to_baseline(switched)
        self.assertEqual(
            getattr(returned, "key", None), self.template_b.key,
            "RED: whole-store reset after a B switch must restore B baseline "
            "(provenance/baseline coherent -> no version-changed error).",
        )


# --------------------------------------------------------------------------
# MERCHANT-FACING CONVERGENCE (54-58)
# --------------------------------------------------------------------------
class MerchantFacingConvergenceTests(Phase1ConvergenceBase):
    def test_r4_switch_template_is_preservation_first(self):
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=97,
            settings={"content": "keep-through-r4"},
        )
        sid = merchant.stable_id
        switched = self._switch_to_b()
        self.assertIsNotNone(
            StorefrontSection.objects.filter(page__version=switched, stable_id=sid).first(),
            "RED: R4 switch-template must be preservation-first (merchant section "
            "survives on the active Draft).",
        )

    def test_r4_ready_template_apply_is_preservation_first_after_convergence(self):
        # Blocker 11: require real success (200 + ok==True) AND invariants.
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=98,
            settings={"content": "keep-through-apply"},
        )
        sid = merchant.stable_id
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
        self.assertEqual(
            resp.status_code, 200,
            f"RED: R4 Ready Template apply must succeed (200). got {resp.status_code}",
        )
        self.assertIs(
            resp.json().get("ok"), True,
            "RED: R4 Ready Template apply must return ok==True.",
        )
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id, self.original_draft_pk,
            "RED: converged R4 apply must stay on the same active Draft.",
        )
        active = self.layout.draft_version
        prov = validate_template_provenance(active.template_provenance)
        self.assertEqual(prov["template"]["key"], self.template_b.key,
                         "RED: provenance must be Template B after apply.")
        self.assertIsNotNone(
            StorefrontSection.objects.filter(page__version=active, stable_id=sid).first(),
            "RED: converged R4 apply must be preservation-first (merchant section "
            "survives on the active Draft).",
        )

    def test_dashboard_ready_template_apply_is_preservation_first_after_convergence(self):
        merchant = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=99,
            settings={"content": "keep-through-dashboard"},
        )
        sid = merchant.stable_id
        client = self._login()
        resp = client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            data={"preset_key": self.template_b.key, "confirm_preset_apply": "1"},
        )
        # A redirect is the success shape for this form view; assert it, then
        # assert the real invariants (Blocker 11).
        self.assertIn(
            resp.status_code, (302, 303),
            f"RED: dashboard apply must redirect on success. got {resp.status_code}",
        )
        self.layout.refresh_from_db()
        self.assertEqual(
            self.layout.draft_version_id, self.original_draft_pk,
            "RED: converged dashboard Ready Template apply must stay on the same "
            "active Draft.",
        )
        active = self.layout.draft_version
        prov = validate_template_provenance(active.template_provenance)
        self.assertEqual(
            prov["template"]["key"], self.template_b.key,
            "RED: dashboard apply must set provenance to Template B.",
        )
        self.assertIsNotNone(
            StorefrontSection.objects.filter(page__version=active, stable_id=sid).first(),
            "RED: converged dashboard Ready Template apply must be preservation-first.",
        )

    def test_dashboard_ready_template_change_records_single_history_and_revision(self):
        before_hist = self._history_count(self.draft)
        start_rev = self.draft.edit_revision
        client = self._login()
        client.post(
            reverse("dashboard:storefront-builder-apply-preset"),
            data={"preset_key": self.template_b.key, "confirm_preset_apply": "1"},
        )
        self.layout.refresh_from_db()
        active_id = self.layout.draft_version_id
        hist_after = StorefrontEditHistoryEntry.objects.filter(
            draft_version_id=active_id
        ).count()
        active = StorefrontLayoutVersion.objects.get(pk=active_id)
        self.assertEqual(
            (active_id, hist_after, active.edit_revision),
            (self.original_draft_pk, before_hist + 1, start_rev + 1),
            "RED: a dashboard Ready Template change must stay on the same Draft "
            "and record EXACTLY one history entry / one revision increment "
            "(no double-record via @_record_edit_history + apply_mutation).",
        )

    def test_non_ready_structural_preset_remains_separate_confirmed_destructive(self):
        non_ready = next(
            (p for p in lpr.list_layout_presets()
             if not p.is_ready_template and "home" in p.pages),
            None,
        )
        if non_ready is None:
            self.skipTest("no non-Ready structural preset with a home composition")
        roles = [getattr(e, "semantic_slot_key", None) for e in non_ready.pages.get("home", ())]
        self.assertTrue(
            all(r is None for r in roles),
            "RED: non-Ready structural presets remain a separate "
            "confirmed-destructive concept (no mandatory semantic roles).",
        )


# --------------------------------------------------------------------------
# NO PARALLEL ARCHITECTURE (59-62)
# --------------------------------------------------------------------------
class NoParallelArchitectureTests(TestCase):
    def test_no_new_migration_is_required_by_the_semantic_contract(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        changed = False
        try:
            call_command(
                "makemigrations", "storefront_builder", "--check", "--dry-run",
                stdout=out, stderr=out, verbosity=1,
            )
        except SystemExit as exc:
            changed = (getattr(exc, "code", 0) not in (0, None))
        self.assertFalse(
            changed,
            "RED/GREEN guard: the semantic contract must require NO new "
            f"migration. makemigrations --check reported changes:\n{out.getvalue()}",
        )

    def test_only_one_ready_template_registry_exists(self):
        self.assertTrue(hasattr(lpr, "LAYOUT_PRESET_REGISTRY"))
        self.assertTrue(hasattr(lpr, "LAYOUT_PRESET_VERSION_REGISTRY"))
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
        field_names = {f.name for f in StorefrontLayoutVersion._meta.get_fields()}
        baseline_like = {
            n for n in field_names
            if "baseline" in n.lower() and n != "template_baseline_snapshot"
        }
        self.assertEqual(
            baseline_like, set(),
            f"RED: no second baseline field may exist; found {baseline_like}",
        )
