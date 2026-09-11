"""U7 — Ready Template / Version / Baseline / Reset Engine.

Audit finding: the APPLY mechanism (``preset_service.apply_preset`` on a
``LayoutPresetDefinition`` — page composition, appearance overlay,
header/footer overlay, atomic/validated, Draft-only, lock-protected) and
version/rollback history (``StorefrontLayoutVersion`` Draft/Publish/Restore
+ ``edit_history_service``'s bounded undo/redo stack) already existed and
are reused unchanged — a ``LayoutPresetDefinition`` already *is* the
versioned recipe the master contract calls a Ready Template.

What this phase adds, closing the real remaining gaps:

- ``LayoutPresetDefinition.version`` (was missing entirely).
- ``template_provenance`` on ``StorefrontLayoutVersion`` (was scaffolded in
  ``variant_contract.build_template_provenance``/``validate_template_provenance``
  since U1A but never actually written by any real Draft) — now written by
  every ``apply_preset`` call.
- ``preset_service.reset_storefront_to_baseline`` — reads the recorded
  provenance and re-applies exactly that key+version, refusing to silently
  substitute a changed current version (the master contract's explicit
  "Reset must restore the selected template VERSION baseline" rule).
- Real ``header_variant``/``footer_variant`` selections on 4 of the 5
  existing presets, so they compose global-region variants too, not just
  section content (the fifth, ``v5_golden_homepage``, is deliberately left
  untouched — see Known limitations in the ledger).
"""

from unittest import mock

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.global_region_registry import GLOBAL_FOOTER_REGION, GLOBAL_HEADER_REGION
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.variant_contract import build_template_provenance
from django.core.cache import cache
from django.test import TestCase

from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class PresetVersionFieldTests(TestCase):
    def test_all_registered_presets_have_a_nonempty_version(self):
        for preset in lpr.list_layout_presets():
            self.assertIsInstance(preset.version, str, preset.key)
            self.assertTrue(preset.version.strip(), preset.key)

    def test_default_version_is_one(self):
        # dense_catalog never set version= explicitly — must resolve to the
        # dataclass default, not silently None/empty.
        preset = lpr.get_layout_preset("dense_catalog")
        self.assertEqual(preset.version, "1")


class HeaderFooterVariantAssignmentTests(TestCase):
    """The 4 updated presets must reference real, currently-registered
    global variant keys — a typo here would silently fail-safe to the
    default variant at render time rather than error, so this is verified
    explicitly rather than trusted."""

    _UPDATED_PRESETS = ("clean_minimal", "editorial_story", "dense_catalog", "premium_boutique")

    def test_header_variant_is_a_real_registered_key(self):
        header_keys = {v.key for v in GLOBAL_HEADER_REGION.variants}
        for key in self._UPDATED_PRESETS:
            preset = lpr.get_layout_preset(key)
            self.assertIn(preset.header["header_variant"], header_keys, key)

    def test_footer_variant_is_a_real_registered_key(self):
        footer_keys = {v.key for v in GLOBAL_FOOTER_REGION.variants}
        for key in self._UPDATED_PRESETS:
            preset = lpr.get_layout_preset(key)
            self.assertIn(preset.footer["footer_variant"], footer_keys, key)

    def test_v5_golden_homepage_deliberately_left_untouched(self):
        preset = lpr.get_layout_preset("v5_golden_homepage")
        self.assertNotIn("header_variant", preset.header)
        self.assertNotIn("footer_variant", preset.footer)


class ApplyPresetProvenanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_apply_preset_records_provenance(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_catalog")
        preset_service.apply_preset(draft, preset)
        draft.refresh_from_db()
        self.assertEqual(
            draft.template_provenance,
            build_template_provenance(template_key="dense_catalog", template_version=preset.version),
        )

    def test_fresh_draft_has_no_provenance(self):
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.template_provenance, {})


class ResetToBaselineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_reset_without_provenance_raises(self):
        draft = svc.get_or_create_draft(self.store)
        with self.assertRaises(preset_service.NoTemplateBaselineError):
            preset_service.reset_storefront_to_baseline(draft)

    def test_reset_reapplies_recorded_preset(self):
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_catalog")
        preset_service.apply_preset(draft, preset)

        home_page = draft.get_page("home")
        home_page.sections.all().delete()
        self.assertEqual(home_page.sections.count(), 0)

        returned = preset_service.reset_storefront_to_baseline(draft)
        self.assertEqual(returned.key, "dense_catalog")
        draft.refresh_from_db()
        home_page = draft.get_page("home")
        self.assertEqual(
            list(home_page.sections.order_by("order").values_list("section_key", flat=True)),
            [entry.section_key for entry in preset.pages["home"]],
        )

    def test_reset_rejects_stale_recorded_version(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_catalog"))
        draft.refresh_from_db()
        draft.template_provenance["template"]["version"] = "some-old-version-that-is-not-current"
        draft.save(update_fields=["template_provenance"])
        with self.assertRaises(preset_service.TemplateBaselineVersionChangedError):
            preset_service.reset_storefront_to_baseline(draft)

    def test_reset_rejects_unknown_template_key(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_catalog"))
        draft.refresh_from_db()
        draft.template_provenance["template"]["key"] = "this-preset-key-does-not-exist"
        draft.save(update_fields=["template_provenance"])
        with self.assertRaises(preset_service.UnknownPresetError):
            preset_service.reset_storefront_to_baseline(draft)

    def test_reset_from_exact_matching_snapshot_survives_registry_disappearance(self):
        """Task-10 blocker corrective fix — CASE A of the root-cause
        contract. An EXACT matching snapshot (``snapshot["template_key"]``/
        ``["template_version"]`` still equal to the Draft's current
        ``template_provenance``) must keep restoring from the immutable
        ``template_baseline_snapshot`` even if the live
        ``layout_preset_registry`` can no longer resolve that key at all.
        The saved historical snapshot — not the live Registry — is reset's
        content source of truth for an exact match; only the (optional)
        metadata return value may come back ``None`` when the Registry
        entry is gone. This guards against an over-fix that hoists the
        Registry lookup ahead of the exact-snapshot branch and makes it
        depend on the Registry again."""
        draft = svc.get_or_create_draft(self.store)
        preset = lpr.get_layout_preset("dense_catalog")
        preset_service.apply_preset(draft, preset)

        home_page = draft.get_page("home")
        home_page.sections.all().delete()
        self.assertEqual(home_page.sections.count(), 0)

        with mock.patch.object(preset_service.layout_preset_registry, "get_layout_preset", return_value=None):
            returned = preset_service.reset_storefront_to_baseline(draft)

        self.assertIsNone(returned)
        draft.refresh_from_db()
        home_page = draft.get_page("home")
        self.assertEqual(
            list(home_page.sections.order_by("order").values_list("section_key", flat=True)),
            [entry.section_key for entry in preset.pages["home"]],
        )
