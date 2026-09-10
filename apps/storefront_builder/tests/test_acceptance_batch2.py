"""Acceptance Batch 2 (post-U11) — «Ready Template Lifecycle / History /
Baseline / Granular Reset».

Real QA against a live database found ``preset_service.apply_preset``
mutating the active Draft row in-place with no recoverable pre-switch
checkpoint (Draft id, Published id, and version count all unchanged
before/after an explicit Ready Template switch). This file covers the
three issues that batch defines:

* Issue 1 — a pre-apply/pre-reset recovery checkpoint, built entirely on
  the existing ``StorefrontLayoutVersion`` history/``restore_version``
  lifecycle (``layout_service.checkpoint_draft_before_replacement``).
* Issue 2 — an immutable, normalized baseline snapshot
  (``StorefrontLayoutVersion.template_baseline_snapshot``) recorded at
  apply time, so a later reset is immune to the live
  ``layout_preset_registry`` definition changing underneath it.
* Issue 3 — granular reset (field/component/section/page/header/footer/
  storefront) sourced from that snapshot, identified by a stable
  ``StorefrontSection.template_slot_key`` rather than ordinal position.
"""

import dataclasses
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-batch2.rastisi.localhost"
PUBLIC_HOST = "sfb-batch2.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _baseline_section(draft, section_key=None):
    """Return a deterministic baseline-origin section from ``draft``.

    Ready Templates are allowed to contain the same reusable section type more
    than once (dense commerce pages legitimately have several product rails).
    Granular-reset identity is therefore ``template_slot_key`` — exactly the
    invariant this acceptance batch is meant to exercise — not uniqueness of a
    ``section_key``.
    """
    sections = draft.home_page().sections.exclude(template_slot_key="").order_by("order", "pk")
    if section_key is not None:
        sections = sections.filter(section_key=section_key)
    section = sections.first()
    if section is None:
        raise AssertionError(f"No baseline-origin section found for {section_key!r}")
    return section


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="sfb-batch2-store-b", defaults=dict(name="فروشگاه دوم Batch 2", status=Store.Status.ACTIVE),
    )
    return store


class PreApplyCheckpointTests(TestCase):
    """Issue 1 — Tests A-H."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.staff = User.objects.create_user(username="batch2_checkpoint_owner", password="pass12345", is_staff=True)

    def _apply_dense_marketplace(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        return draft

    def test_a_applying_a_different_template_creates_a_recoverable_pre_switch_checkpoint(self):
        draft1 = self._apply_dense_marketplace()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before + 1)
        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")
        self.assertEqual(checkpoint.pk, draft1.pk)
        self.assertEqual(checkpoint.template_provenance["template"]["key"], "dense_marketplace")

    def test_b_active_draft_becomes_a_distinct_version_where_appropriate(self):
        draft1 = self._apply_dense_marketplace()
        new_draft = preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        self.assertNotEqual(new_draft.pk, draft1.pk)
        layout = svc.get_or_create_layout(self.store)
        self.assertEqual(layout.draft_version_id, new_draft.pk)

        # "where appropriate" — an already-empty Draft has nothing worth a
        # checkpoint for, so the SAME row is reused (no version-history spam).
        other_store = _second_store()
        fresh_draft = svc.get_or_create_draft(other_store)
        fresh_draft.sections.all().delete()
        result_draft = preset_service.apply_preset_with_checkpoint(
            other_store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        self.assertEqual(result_draft.pk, fresh_draft.pk)

    def test_c_published_version_id_and_content_remain_untouched(self):
        self._apply_dense_marketplace()
        svc.publish(self.store)
        layout = svc.get_or_create_layout(self.store)
        published_before_id = layout.published_version_id
        fingerprint_before = layout.published_version.content_fingerprint

        preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, published_before_id)
        layout.published_version.refresh_from_db()
        self.assertEqual(layout.published_version.content_fingerprint, fingerprint_before)

    def test_d_pre_switch_state_is_recoverable_via_existing_restore_version(self):
        draft1 = self._apply_dense_marketplace()
        home_before = list(draft1.home_page().sections.order_by("order").values_list("section_key", flat=True))

        preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        layout = svc.get_or_create_layout(self.store)
        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")

        restored = svc.restore_version(self.store, checkpoint.pk, user=self.staff)
        home_after = list(restored.home_page().sections.order_by("order").values_list("section_key", flat=True))
        self.assertEqual(home_after, home_before)

    def test_e_restore_creates_a_draft_and_never_auto_publishes(self):
        draft1 = self._apply_dense_marketplace()
        svc.publish(self.store)
        # publish() archives draft1 too (as the previous published version's
        # predecessor path) — re-create a fresh draft with real content atop it.
        draft2 = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft2, lpr.get_layout_preset("dense_marketplace"))
        layout = svc.get_or_create_layout(self.store)
        published_before = layout.published_version_id

        preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        layout.refresh_from_db()
        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")
        restored = svc.restore_version(self.store, checkpoint.pk, user=self.staff)

        self.assertEqual(restored.status, StorefrontLayoutVersion.Status.DRAFT)
        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, published_before)
        self.assertEqual(layout.draft_version_id, restored.pk)

    def test_f_one_store_cannot_restore_another_stores_history(self):
        self._apply_dense_marketplace()
        preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )
        layout = svc.get_or_create_layout(self.store)
        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")

        other_store = _second_store()
        with self.assertRaises(svc.CrossStoreVersionError):
            svc.restore_version(other_store, checkpoint.pk, user=self.staff)

    def test_g_failed_template_apply_leaves_no_half_created_history_state(self):
        draft1 = self._apply_dense_marketplace()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        draft_pk_before = layout.draft_version_id

        section = draft1.home_page().sections.first()
        section.is_locked = True
        section.save(update_fields=["is_locked"])

        with self.assertRaises(preset_service.LockedSectionsPresentError):
            preset_service.apply_preset_with_checkpoint(
                self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
            )

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)
        self.assertEqual(layout.draft_version_id, draft_pk_before)
        draft1.refresh_from_db()
        self.assertEqual(draft1.status, StorefrontLayoutVersion.Status.DRAFT)

    def test_h_apply_and_history_transition_are_atomic(self):
        draft1 = self._apply_dense_marketplace()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        sections_before = StorefrontSection.objects.filter(page__version=draft1).count()

        with mock.patch(
            "apps.storefront_builder.services.preset_service.container_service.rebuild_page_from_legacy_rows",
            side_effect=RuntimeError("simulated mid-operation failure"),
        ):
            with self.assertRaises(RuntimeError):
                preset_service.apply_preset_with_checkpoint(
                    self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
                )

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)
        self.assertEqual(layout.draft_version_id, draft1.pk)
        draft1.refresh_from_db()
        self.assertEqual(draft1.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertEqual(StorefrontSection.objects.filter(page__version=draft1).count(), sections_before)


class ZeroSectionMeaningfulStateCheckpointTests(TestCase):
    """Post-demo hardening pass, Issue 5: ``checkpoint_draft_before_replacement``'s
    old "does this Draft have any sections?" shortcut was too weak — a
    zero-section Draft can still hold meaningful merchant changes
    (appearance/header/footer/palette/template baseline state) that a
    template switch must not silently destroy without a recoverable
    checkpoint. Each test here isolates exactly one global scope, with
    every *other* scope left at its pristine default, to prove the new
    meaningful-state policy checks each axis independently."""

    def setUp(self):
        cache.clear()
        self.store = _second_store()
        self.staff = User.objects.create_user(username="batch2_zero_section_owner", password="pass12345", is_staff=True)

    def _fresh_pristine_draft(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        draft.sections.all().delete()
        draft.refresh_from_db()
        return draft

    def _checkpoint(self):
        return svc.checkpoint_draft_before_replacement(self.store, reason_label="تست چک‌پوینت", user=self.staff)

    def test_empty_pristine_draft_gets_no_unnecessary_checkpoint(self):
        draft = self._fresh_pristine_draft()
        result = self._checkpoint()
        self.assertEqual(result.pk, draft.pk)
        self.assertEqual(result.status, StorefrontLayoutVersion.Status.DRAFT)

    def test_zero_sections_with_modified_appearance_config_is_checkpointed(self):
        draft = self._fresh_pristine_draft()
        draft.appearance_config = {"density": "compact"}
        draft.save(update_fields=["appearance_config"])
        result = self._checkpoint()
        self.assertNotEqual(result.pk, draft.pk)
        draft.refresh_from_db()
        self.assertEqual(draft.status, StorefrontLayoutVersion.Status.ARCHIVED)

    def test_zero_sections_with_modified_palette_is_checkpointed(self):
        """Palette lives inside ``appearance_config['palette_slug']`` — a
        palette-only change must still be recognized as meaningful."""
        draft = self._fresh_pristine_draft()
        draft.appearance_config = {"palette_slug": "warm-earth"}
        draft.save(update_fields=["appearance_config"])
        result = self._checkpoint()
        self.assertNotEqual(result.pk, draft.pk)

    def test_zero_sections_with_modified_header_config_is_checkpointed(self):
        draft = self._fresh_pristine_draft()
        draft.header_config = {"variant": "centered"}
        draft.save(update_fields=["header_config"])
        result = self._checkpoint()
        self.assertNotEqual(result.pk, draft.pk)

    def test_zero_sections_with_modified_footer_config_is_checkpointed(self):
        draft = self._fresh_pristine_draft()
        draft.footer_config = {"variant": "expanded"}
        draft.save(update_fields=["footer_config"])
        result = self._checkpoint()
        self.assertNotEqual(result.pk, draft.pk)

    def test_zero_sections_with_template_provenance_is_checkpointed(self):
        """Template provenance/baseline state (e.g. a Ready Template was
        applied and then every section was manually removed) is itself
        meaningful state — a later replacement must not discard it silently."""
        draft = self._fresh_pristine_draft()
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        draft.sections.all().delete()
        result = self._checkpoint()
        self.assertNotEqual(result.pk, draft.pk)
        draft.refresh_from_db()
        self.assertEqual(draft.status, StorefrontLayoutVersion.Status.ARCHIVED)

    def test_checkpoint_clones_full_content_including_the_modified_global_scope(self):
        draft = self._fresh_pristine_draft()
        draft.header_config = {"variant": "centered"}
        draft.save(update_fields=["header_config"])
        new_draft = self._checkpoint()
        draft.refresh_from_db()
        self.assertEqual(draft.header_config, {"variant": "centered"})
        self.assertEqual(new_draft.header_config, {"variant": "centered"})


class SameTemplateNoOpTests(TestCase):
    """Post-demo hardening pass, Issue 6: applying the exact same,
    unmodified Ready Template to a Draft that is already exactly at that
    Template's baseline must not create redundant version-history noise
    (another archived version / another Draft row) — there is no
    meaningful change to checkpoint."""

    def setUp(self):
        cache.clear()
        self.store = _second_store()
        self.staff = User.objects.create_user(username="batch2_noop_owner", password="pass12345", is_staff=True)

    def test_reapplying_the_same_unmodified_template_creates_no_new_version_or_draft(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        draft_id_before = layout.draft_version_id

        result = preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("dense_marketplace"), user=self.staff,
        )

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before)
        self.assertEqual(layout.draft_version_id, draft_id_before)
        self.assertEqual(result.pk, draft_id_before)

    def test_applying_a_genuinely_different_template_still_checkpoints(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        draft_id_before = layout.draft_version_id

        result = preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("warm_boutique"), user=self.staff,
        )

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before + 1)
        self.assertNotEqual(layout.draft_version_id, draft_id_before)
        self.assertNotEqual(result.pk, draft_id_before)

    def test_reapplying_same_template_after_a_manual_edit_still_checkpoints(self):
        """A merchant's manual edit since the last apply is real, recoverable
        content — re-applying the same Template to revert it must still be
        checkpointed, exactly like any other meaningful replacement."""
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        section = draft.home_page().sections.first()
        section.settings = {**section.settings, "_manual_qa_marker": True}
        section.save(update_fields=["settings"])
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        draft_id_before = layout.draft_version_id

        result = preset_service.apply_preset_with_checkpoint(
            self.store, lpr.get_layout_preset("dense_marketplace"), user=self.staff,
        )

        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before + 1)
        self.assertNotEqual(layout.draft_version_id, draft_id_before)
        self.assertNotEqual(result.pk, draft_id_before)


class ImmutableBaselineSnapshotTests(TestCase):
    """Issue 2 — Tests A-H."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_a_applied_ready_template_stores_an_exact_baseline_snapshot(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        snapshot = draft.template_baseline_snapshot
        self.assertEqual(snapshot["template_key"], "dense_marketplace")
        self.assertEqual(snapshot["template_version"], preset.version)
        self.assertIn("home", snapshot["pages"])

    def test_b_mutating_the_registry_definition_does_not_change_the_reset_result(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        original_density = draft.effective_appearance_config()["density"]
        self.assertNotEqual(original_density, "relaxed")

        # Simulate "a developer accidentally changed the recipe contents but
        # forgot to increment version" — the exact motivating risk.
        mutated = dataclasses.replace(preset, appearance={**preset.appearance, "density": "relaxed"})
        original_entry = lpr.LAYOUT_PRESET_REGISTRY["dense_marketplace"]
        lpr.LAYOUT_PRESET_REGISTRY["dense_marketplace"] = mutated
        try:
            draft.home_page().sections.all().delete()
            preset_service.reset_storefront_to_baseline(draft)
            draft.refresh_from_db()
            self.assertEqual(draft.effective_appearance_config()["density"], original_density)
            self.assertGreater(draft.home_page().sections.count(), 0)
        finally:
            lpr.LAYOUT_PRESET_REGISTRY["dense_marketplace"] = original_entry

    def test_c_palette_baseline_is_included(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        snapshot = draft.template_baseline_snapshot
        self.assertEqual(snapshot["default_palette_slug"], preset.default_palette_slug)
        self.assertEqual(snapshot["appearance"]["palette_slug"], preset.default_palette_slug)

    def test_d_header_and_footer_baseline_are_included(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        snapshot = draft.template_baseline_snapshot
        self.assertEqual(snapshot["header_config"]["header_variant"], preset.header["header_variant"])
        self.assertEqual(snapshot["footer_config"]["footer_variant"], preset.footer["footer_variant"])

    def test_e_page_and_section_baseline_are_included(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        home_entries = draft.template_baseline_snapshot["pages"]["home"]
        actual_keys = [e["section_key"] for e in home_entries]
        expected_keys = [entry.section_key for entry in preset.pages["home"]]
        self.assertEqual(actual_keys, expected_keys)
        self.assertTrue(all(e["slot_key"] for e in home_entries))

    def test_f_snapshot_contains_no_renderer_template_paths(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        serialized = json.dumps(draft.template_baseline_snapshot, ensure_ascii=False)
        self.assertNotIn(".html", serialized)
        self.assertNotIn("template_name", serialized)
        self.assertNotIn("storefront_builder/sections/", serialized)

    def test_g_snapshot_is_store_and_version_scoped(self):
        draft1 = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft1, lpr.get_layout_preset("dense_marketplace"))
        other_store = _second_store()
        draft2 = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(draft2, lpr.get_layout_preset("warm_boutique"))
        draft1.refresh_from_db()
        draft2.refresh_from_db()
        self.assertEqual(draft1.template_baseline_snapshot["template_key"], "dense_marketplace")
        self.assertEqual(draft2.template_baseline_snapshot["template_key"], "warm_boutique")
        self.assertNotEqual(draft1.template_baseline_snapshot, draft2.template_baseline_snapshot)

    def test_h_legacy_no_snapshot_version_falls_back_safely(self):
        """Post-demo hardening pass, Issue 4: a version-matched compatibility
        reset on a pre-Batch-2 Draft (no immutable snapshot) still visibly
        resets the storefront using the current registry — but must NEVER
        persist that reconstruction into ``template_baseline_snapshot`` as
        though it were the exact historical baseline (version equality is
        not proof the live Registry's content is unchanged since it was
        applied). The Draft stays a genuine no-snapshot Draft afterward, and
        granular (section/page/header/footer) reset — which requires a real
        exact snapshot — correctly stays unavailable for it."""
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        # Simulate a pre-Batch-2 version: provenance present, snapshot missing.
        draft.template_baseline_snapshot = {}
        draft.save(update_fields=["template_baseline_snapshot"])
        draft.home_page().sections.all().delete()

        result = preset_service.reset_storefront_to_baseline(draft)
        self.assertEqual(result.key, "dense_marketplace")
        draft.refresh_from_db()
        self.assertGreater(draft.home_page().sections.count(), 0)
        # Never fabricated/"healed" into an exact historical snapshot — the
        # current registry's content is not proof of the exact baseline
        # that was originally applied, so it must not be persisted as one.
        self.assertFalse(draft.template_baseline_snapshot)
        # Granular reset correctly stays disabled — no exact snapshot exists.
        section = draft.home_page().sections.first()
        section.template_slot_key = "home:0"
        section.save(update_fields=["template_slot_key"])
        with self.assertRaises(preset_service.NoTemplateBaselineError):
            preset_service.reset_section_to_baseline(draft, section)

    def test_h2_legacy_version_mismatch_still_raises_never_fabricates(self):
        from apps.storefront_builder.variant_contract import build_template_provenance

        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_marketplace"))
        draft.refresh_from_db()
        draft.template_baseline_snapshot = {}
        draft.template_provenance = build_template_provenance(template_key="dense_marketplace", template_version="999")
        draft.save(update_fields=["template_baseline_snapshot", "template_provenance"])
        with self.assertRaises(preset_service.TemplateBaselineVersionChangedError):
            preset_service.reset_storefront_to_baseline(draft)


class GranularResetTests(TestCase):
    """Issue 3 — field/component/section/page/header/footer semantics."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, self.preset)
        self.draft.refresh_from_db()

    def test_reset_field_restores_only_that_key(self):
        section = _baseline_section(self.draft, "product_section")
        baseline_title = section.settings["title"]
        section.settings = {**section.settings, "title": "عنوان دستی مرچنت", "item_limit": 99}
        section.save(update_fields=["settings"])

        preset_service.reset_section_setting_to_baseline(self.draft, section, "title")
        section.refresh_from_db()
        self.assertEqual(section.settings["title"], baseline_title)
        self.assertEqual(section.settings["item_limit"], 99)

    def test_reset_component_restores_a_nested_settings_dict(self):
        section = _baseline_section(self.draft, "product_section")
        baseline_card = dict(section.settings["card"])
        section.settings = {**section.settings, "card": {**section.settings["card"], "card_style": "minimal"}}
        section.save(update_fields=["settings"])

        preset_service.reset_section_setting_to_baseline(self.draft, section, "card")
        section.refresh_from_db()
        self.assertEqual(section.settings["card"], baseline_card)

    def test_reset_field_unknown_key_raises(self):
        section = _baseline_section(self.draft, "product_section")
        with self.assertRaises(preset_service.BaselineFieldNotFoundError):
            preset_service.reset_section_setting_to_baseline(self.draft, section, "not_a_real_field")

    def test_reset_appearance_field_restores_only_that_key(self):
        self.draft.appearance_config = {**self.draft.effective_appearance_config(), "density": "relaxed", "font": "Georgia"}
        self.draft.save(update_fields=["appearance_config"])
        preset_service.reset_appearance_setting_to_baseline(self.draft, "density")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.effective_appearance_config()["density"], self.preset.appearance["density"])
        self.assertEqual(self.draft.effective_appearance_config()["font"], "Georgia")

    def test_reset_appearance_field_unknown_key_raises(self):
        with self.assertRaises(preset_service.BaselineFieldNotFoundError):
            preset_service.reset_appearance_setting_to_baseline(self.draft, "not_a_real_appearance_field")

    def test_reset_section_survives_reorder_insert_and_unrelated_delete(self):
        home = self.draft.home_page()
        target = _baseline_section(self.draft)
        baseline_settings = dict(target.settings)
        baseline_row_key, baseline_row_span = target.row_key, target.row_span

        other = home.sections.exclude(pk=target.pk).first()
        target.order, other.order = other.order, target.order
        target.save(update_fields=["order"])
        other.save(update_fields=["order"])

        StorefrontSection.objects.create(page=home, section_key="rich_text", order=999, settings={"content": "دستی"})
        home.sections.filter(section_key="trust_features").delete()

        target.refresh_from_db()
        mutated_settings = dict(target.settings)
        mutated_settings["merchant_marker"] = "changed"
        target.settings = mutated_settings
        target.save(update_fields=["settings"])

        preset_service.reset_section_to_baseline(self.draft, target)
        target.refresh_from_db()
        self.assertEqual(target.settings, baseline_settings)
        self.assertEqual(target.row_key, baseline_row_key)
        self.assertEqual(target.row_span, baseline_row_span)

    def test_reset_section_restores_a_manually_modified_row_span_and_row_key(self):
        """Post-demo hardening pass, Issue 7: explicit coverage for the
        exact scenario the mission's own known-limitations note called
        out — a merchant manually changes a baseline section's row_key/
        row_span (e.g. a drag-and-drop resize/regroup), and a single-
        section reset must restore both back to the Template baseline."""
        home = self.draft.home_page()
        target = _baseline_section(self.draft)
        baseline_row_key, baseline_row_span = target.row_key, target.row_span

        target.row_key = f"{baseline_row_key}-merchant-custom"
        target.row_span = baseline_row_span + 4
        target.save(update_fields=["row_key", "row_span"])

        preset_service.reset_section_to_baseline(self.draft, target)
        target.refresh_from_db()
        self.assertEqual(target.row_key, baseline_row_key)
        self.assertEqual(target.row_span, baseline_row_span)

    def test_reset_section_does_not_mutate_another_baseline_section(self):
        home = self.draft.home_page()
        target = _baseline_section(self.draft)
        sibling = home.sections.exclude(pk=target.pk).first()
        sibling_settings_before = dict(sibling.settings)
        sibling_row_key_before, sibling_row_span_before = sibling.row_key, sibling.row_span

        mutated = dict(target.settings)
        mutated["merchant_marker"] = "changed"
        target.settings = mutated
        target.save(update_fields=["settings"])

        preset_service.reset_section_to_baseline(self.draft, target)
        sibling.refresh_from_db()
        self.assertEqual(sibling.settings, sibling_settings_before)
        self.assertEqual(sibling.row_key, sibling_row_key_before)
        self.assertEqual(sibling.row_span, sibling_row_span_before)

    def test_reset_section_never_touches_the_published_version(self):
        svc.publish(self.store)
        layout = svc.get_or_create_layout(self.store)
        published_before_id = layout.published_version_id
        published_fingerprint_before = layout.published_version.compute_fingerprint()

        # publish() clears layout.draft_version — get_or_create_draft makes a
        # brand new (empty) one, so it needs the Template re-applied to have
        # any baseline-origin section to reset in the first place.
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, self.preset)
        draft.refresh_from_db()
        target = _baseline_section(draft)
        mutated = dict(target.settings)
        mutated["merchant_marker"] = "changed"
        target.settings = mutated
        target.save(update_fields=["settings"])

        preset_service.reset_section_to_baseline(draft, target)

        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, published_before_id)
        layout.published_version.refresh_from_db()
        self.assertEqual(layout.published_version.compute_fingerprint(), published_fingerprint_before)

    def test_cannot_reset_a_merchant_created_section(self):
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="rich_text", order=999, settings={},
        )
        with self.assertRaises(preset_service.NotABaselineSectionError):
            preset_service.reset_section_to_baseline(self.draft, custom)
        with self.assertRaises(preset_service.NotABaselineSectionError):
            preset_service.reset_section_setting_to_baseline(self.draft, custom, "content")

    def test_reset_section_stale_slot_raises_not_a_silent_noop(self):
        section = _baseline_section(self.draft, "product_section")
        section.template_slot_key = "dense_marketplace:v1:home:9999"
        section.save(update_fields=["template_slot_key"])
        with self.assertRaises(preset_service.BaselineSlotNotFoundError):
            preset_service.reset_section_to_baseline(self.draft, section)

    def test_merchant_created_section_survives_reset_of_a_different_section(self):
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="rich_text", order=999, settings={"content": "دستی"},
        )
        target = _baseline_section(self.draft)
        preset_service.reset_section_to_baseline(self.draft, target)
        self.assertTrue(StorefrontSection.objects.filter(pk=custom.pk).exists())

    def test_reset_page_restores_baseline_composition(self):
        home = self.draft.home_page()
        home.sections.filter(section_key="trust_features").delete()
        StorefrontSection.objects.create(page=home, section_key="rich_text", order=999, settings={})

        preset_service.reset_page_to_baseline(self.draft, "home")

        keys = list(home.sections.order_by("order").values_list("section_key", flat=True))
        expected = [entry.section_key for entry in self.preset.pages["home"]]
        self.assertEqual(keys, expected)

    def test_reset_page_intentionally_removes_that_pages_merchant_content(self):
        """Explicit, documented exception: whole-PAGE reset (unlike section/
        field reset) MAY remove a merchant-added section on that same page
        — it is a full, confirmed baseline restore of the page."""
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="rich_text", order=999, settings={},
        )
        preset_service.reset_page_to_baseline(self.draft, "home")
        self.assertFalse(StorefrontSection.objects.filter(pk=custom.pk).exists())

    def test_reset_page_never_touches_other_pages_or_header_footer(self):
        listing = self.draft.get_page("listing")
        listing_custom = StorefrontSection.objects.create(page=listing, section_key="rich_text", order=999, settings={})
        original_header = dict(self.draft.header_config)
        original_footer = dict(self.draft.footer_config)

        self.draft.home_page().sections.filter(section_key="trust_features").delete()
        preset_service.reset_page_to_baseline(self.draft, "home")

        self.assertTrue(StorefrontSection.objects.filter(pk=listing_custom.pk).exists())
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config, original_header)
        self.assertEqual(self.draft.footer_config, original_footer)

    def test_reset_page_type_not_covered_by_baseline_raises(self):
        snapshot = dict(self.draft.template_baseline_snapshot)
        snapshot["pages"] = {k: v for k, v in snapshot["pages"].items() if k != "cart"}
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot"])
        with self.assertRaises(preset_service.UnknownBaselinePageError):
            preset_service.reset_page_to_baseline(self.draft, "cart")

    def test_reset_header_restores_baseline_and_never_touches_footer(self):
        original_footer = dict(self.draft.footer_config)
        self.draft.header_config = {**self.draft.effective_header_config(), "sticky": not self.preset.header["sticky"]}
        self.draft.save(update_fields=["header_config"])

        preset_service.reset_header_to_baseline(self.draft)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["header_variant"], self.preset.header["header_variant"])
        self.assertEqual(self.draft.footer_config, original_footer)

    def test_reset_footer_restores_baseline_and_never_touches_header(self):
        original_header = dict(self.draft.header_config)
        self.draft.footer_config = {**self.draft.effective_footer_config(), "show_newsletter": not self.preset.footer.get("show_newsletter", True)}
        self.draft.save(update_fields=["footer_config"])

        preset_service.reset_footer_to_baseline(self.draft)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["footer_variant"], self.preset.footer["footer_variant"])
        self.assertEqual(self.draft.header_config, original_header)

    def test_reset_header_without_header_baseline_raises(self):
        snapshot = dict(self.draft.template_baseline_snapshot)
        snapshot["header_config"] = None
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot"])
        with self.assertRaises(preset_service.NoHeaderBaselineError):
            preset_service.reset_header_to_baseline(self.draft)

    def test_reset_header_footer_without_any_baseline_raises_no_template_baseline(self):
        other_draft = svc.get_or_create_draft(_second_store())
        with self.assertRaises(preset_service.NoTemplateBaselineError):
            preset_service.reset_header_to_baseline(other_draft)
        with self.assertRaises(preset_service.NoTemplateBaselineError):
            preset_service.reset_footer_to_baseline(other_draft)


class ResetCheckpointIntegrationTests(TestCase):
    """Issue 3's «VERSIONING INTERACTION WITH RESET» — page/storefront reset
    integrate with the same checkpoint mechanism as Issue 1."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.staff = User.objects.create_user(username="batch2_reset_checkpoint_owner", password="pass12345", is_staff=True)
        self.draft = svc.get_or_create_draft(self.store)
        self.preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, self.preset)
        self.draft.refresh_from_db()

    def test_reset_storefront_with_checkpoint_creates_a_checkpoint(self):
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()
        self.draft.home_page().sections.filter(section_key="trust_features").delete()

        new_draft = preset_service.reset_storefront_with_checkpoint(self.store, user=self.staff)
        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before + 1)
        self.assertNotEqual(new_draft.pk, self.draft.pk)
        keys = list(new_draft.home_page().sections.order_by("order").values_list("section_key", flat=True))
        expected = [entry.section_key for entry in self.preset.pages["home"]]
        self.assertEqual(keys, expected)

    def test_reset_storefront_with_checkpoint_no_baseline_raises(self):
        other_store = _second_store()
        svc.get_or_create_draft(other_store)
        with self.assertRaises(preset_service.NoTemplateBaselineError):
            preset_service.reset_storefront_with_checkpoint(other_store, user=self.staff)

    def test_reset_page_with_checkpoint_creates_a_checkpoint(self):
        layout = svc.get_or_create_layout(self.store)
        versions_before = layout.versions.count()

        new_draft = preset_service.reset_page_with_checkpoint(self.store, "home", user=self.staff)
        layout.refresh_from_db()
        self.assertEqual(layout.versions.count(), versions_before + 1)
        self.assertNotEqual(new_draft.pk, self.draft.pk)

    def test_published_version_untouched_by_reset_with_checkpoint(self):
        svc.publish(self.store)
        draft2 = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft2, self.preset)
        layout = svc.get_or_create_layout(self.store)
        published_before = layout.published_version_id

        preset_service.reset_storefront_with_checkpoint(self.store, user=self.staff)
        layout.refresh_from_db()
        self.assertEqual(layout.published_version_id, published_before)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class MerchantResetUITests(TestCase):
    """UI / merchant-experience requirements: Persian labels, explicit
    confirmation for destructive scopes, no JSON/registry keys/renderer
    paths/internal IDs exposed, controls absent without a baseline."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="batch2_ui_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="batch2_ui_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, self.preset)
        self.draft.refresh_from_db()
        # Pre-Task-10 CORRECTIVE closure (Item 2, second legacy retirement
        # pass) — the granular reset UI this class exercises now renders
        # only inside editor.html's still-required FULL legacy body (a
        # Store explicitly pinned back with r4_editor_enabled=False); on
        # the live R4 default it is retired along with the rest of the
        # duplicate merchant-editing surface.
        layout = svc.get_or_create_layout(self.store)
        layout.r4_editor_enabled = False
        layout.save(update_fields=["r4_editor_enabled"])

    def test_section_reset_control_shown_only_for_baseline_origin_sections(self):
        target = _baseline_section(self.draft, "product_section")
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="product_section", order=999, settings={
                "data_source": "newest", "item_limit": 8, "display_mode": "grid",
            },
        )
        resp_target = self.admin_client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[target.pk]),
        )
        self.assertContains(resp_target, "بازنشانی این بخش به قالب")

        resp_custom = self.admin_client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[custom.pk]),
        )
        self.assertNotContains(resp_custom, "بازنشانی این بخش به قالب")

    def test_reset_section_view_works_end_to_end_with_confirm_dialog(self):
        target = _baseline_section(self.draft)
        resp = self.admin_client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[target.pk]),
        )
        self.assertContains(resp, "confirm(")
        self.assertContains(
            resp, f"action=\"{reverse('dashboard:storefront-builder-section-reset', args=[target.pk])}\"",
        )

        post_resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-section-reset", args=[target.pk]),
        )
        self.assertEqual(post_resp.status_code, 302)

    def test_field_reset_control_shown_for_baseline_sections_with_a_title(self):
        """Post-demo hardening pass, Issue 7: the RESET FIELD control (only
        illustrated on ``product_section`` before this pass) is now wired
        consistently on the "title" field of every baseline-origin section
        type that has one — proven end-to-end here on two more types."""
        for section_key in ("category_grid", "brand_carousel"):
            target = self.draft.home_page().sections.get(section_key=section_key)
            resp = self.admin_client.get(
                reverse("dashboard:storefront-builder-section-settings", args=[target.pk]),
            )
            self.assertContains(
                resp, f"action=\"{reverse('dashboard:storefront-builder-section-field-reset', args=[target.pk])}\"",
                msg_prefix=section_key,
            )
            self.assertContains(resp, 'value="title"', msg_prefix=section_key)

            post_resp = self.admin_client.post(
                reverse("dashboard:storefront-builder-section-field-reset", args=[target.pk]),
                {"field": "title"},
            )
            self.assertEqual(post_resp.status_code, 302, section_key)

    def test_field_reset_control_absent_for_a_merchant_created_section(self):
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="category_grid", order=999, settings={"title": "دسته‌های من"},
        )
        resp = self.admin_client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[custom.pk]),
        )
        self.assertNotContains(
            resp, reverse("dashboard:storefront-builder-section-field-reset", args=[custom.pk]),
        )

    def test_appearance_field_reset_control_shown_and_works_end_to_end(self):
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-appearance"))
        self.assertContains(
            resp, f"action=\"{reverse('dashboard:storefront-builder-appearance-field-reset')}\"",
        )
        self.assertContains(resp, 'value="density"')

        post_resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-appearance-field-reset"), {"field": "density"},
        )
        self.assertEqual(post_resp.status_code, 302)

    def test_reset_section_view_rejects_merchant_created_section_with_persian_message(self):
        custom = StorefrontSection.objects.create(
            page=self.draft.home_page(), section_key="rich_text", order=999, settings={},
        )
        resp = self.admin_client.post(
            reverse("dashboard:storefront-builder-section-reset", args=[custom.pk]), follow=True,
        )
        self.assertContains(resp, "هرگز از یک Ready Template baseline نیامده")

    def test_header_reset_button_shown_when_baseline_exists_and_absent_without_one(self):
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-header"))
        self.assertContains(resp, "بازنشانی هدر به قالب")

        self.draft.template_baseline_snapshot = {}
        self.draft.save(update_fields=["template_baseline_snapshot"])
        resp2 = self.admin_client.get(reverse("dashboard:storefront-builder-header"))
        self.assertNotContains(resp2, "بازنشانی هدر به قالب")

    def test_footer_reset_button_shown_when_baseline_exists(self):
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertContains(resp, "بازنشانی فوتر به قالب")

    def test_reset_header_view_end_to_end(self):
        resp = self.admin_client.post(reverse("dashboard:storefront-builder-header-reset"))
        self.assertEqual(resp.status_code, 302)

    def test_reset_footer_view_end_to_end(self):
        resp = self.admin_client.post(reverse("dashboard:storefront-builder-footer-reset"))
        self.assertEqual(resp.status_code, 302)

    def test_page_and_storefront_reset_controls_in_editor_with_confirm(self):
        resp = self.admin_client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertContains(resp, "بازنشانی این صفحه به قالب")
        self.assertContains(resp, "بازنشانی کل ظاهر فروشگاه به قالب")
        self.assertContains(resp, "confirm(")

    def test_reset_page_view_end_to_end(self):
        resp = self.admin_client.post(reverse("dashboard:storefront-builder-page-reset"), {"page": "home"})
        self.assertEqual(resp.status_code, 302)

    def test_reset_storefront_view_end_to_end(self):
        resp = self.admin_client.post(reverse("dashboard:storefront-builder-reset-to-baseline"))
        self.assertEqual(resp.status_code, 302)

    def test_no_reset_controls_when_store_has_no_baseline_at_all(self):
        other_store = _second_store()
        other_store.admin_subdomain = "sfb-batch2-store-b"
        other_store.save(update_fields=["admin_subdomain"])
        StoreMembership.objects.create(
            store=other_store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        other_admin_client = Client(HTTP_HOST="sfb-batch2-store-b.rastisi.localhost")
        with override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "sfb-batch2-store-b.rastisi.localhost", "testserver"]):
            other_admin_client.login(username="batch2_ui_owner", password="pass12345")
            resp = other_admin_client.get(reverse("dashboard:storefront-builder-editor"))
            self.assertNotContains(resp, "بازنشانی این صفحه به قالب")
            self.assertNotContains(resp, "بازنشانی کل ظاهر فروشگاه به قالب")

    def test_no_internal_ids_json_or_registry_keys_exposed_in_editor_or_history(self):
        editor_resp = self.admin_client.get(reverse("dashboard:storefront-builder-editor"))
        content = editor_resp.content.decode()
        self.assertNotIn("template_slot_key", content)
        self.assertNotIn("template_baseline_snapshot", content)

        history_resp = self.admin_client.get(reverse("dashboard:storefront-builder-history"))
        history_content = history_resp.content.decode()
        self.assertNotIn("template_slot_key", history_content)
        self.assertNotIn("template_baseline_snapshot", history_content)
