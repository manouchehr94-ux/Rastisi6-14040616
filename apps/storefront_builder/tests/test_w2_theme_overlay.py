"""P5-W2 — Reversible Theme Overlay (occasion/seasonal appearance layer).

Strict TDD RED suite. Every test here encodes a required W2 behavioral
contract and is expected to FAIL for a genuine missing-feature reason against
the certified base ``b7d8ac281389870877553f5a308af3e77dcdd7f0`` (the ``theme``
family, the ``theme_catalog`` data authority, the intensity setting, the
canonical rendering accessor, and the ``apply_theme``/``clear_theme``
mutations do not exist yet).

Architecture law honored by these tests:
* ONE canonical Store-Appearance family (``theme``), renderer_role
  ``appearance_token`` (NOT a new role, NOT ``theme_overlay``).
* ONE data authority: ``apps.storefront_builder.theme_catalog``.
* Canonical registration path: theme_catalog -> adapters ->
  COMPONENT_REGISTRY -> rendering.
* Theme owns ONLY ``selections["theme"]`` and ``settings["theme"]``; it never
  touches non-theme state and never restores from ``template_baseline_snapshot``.
"""

from __future__ import annotations

import copy

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.storefront_builder.services import layout_service
from apps.storefront_builder.models import StorefrontPage
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


# ---------------------------------------------------------------------------
# Contract / Registry (25.1–25.6)
# ---------------------------------------------------------------------------
class ThemeFamilyContractTests(SimpleTestCase):
    def test_theme_family_exists(self):
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )

        self.assertIn("theme", COMPONENT_FAMILIES)

    def test_theme_family_renderer_role_is_appearance_token(self):
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )

        self.assertEqual(
            COMPONENT_FAMILIES["theme"].renderer_role, "appearance_token"
        )

    def test_theme_family_safe_default_is_none(self):
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )

        self.assertEqual(
            COMPONENT_FAMILIES["theme"].safe_default_component_key,
            "theme.none.v1",
        )

    def test_theme_family_is_optional(self):
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )

        self.assertTrue(COMPONENT_FAMILIES["theme"].optional)

    def test_renderer_roles_are_not_expanded_for_theme(self):
        # Architecture rule: do NOT add a new renderer role. Theme reuses the
        # existing ``appearance_token`` role.
        from apps.storefront_builder.storefront_appearance.contracts import (
            _RENDERER_ROLES,
        )

        self.assertEqual(
            _RENDERER_ROLES,
            frozenset(
                {
                    "global_region",
                    "section_variant",
                    "composition",
                    "appearance_token",
                }
            ),
        )

    def test_theme_component_definitions_come_from_catalog_through_adapters(self):
        from apps.storefront_builder import theme_catalog
        from apps.storefront_builder.storefront_appearance.registry import (
            COMPONENT_REGISTRY,
        )

        for entry in theme_catalog.list_theme_occasions():
            with self.subTest(occasion=entry.occasion_key):
                self.assertIn(entry.component_key, COMPONENT_REGISTRY)
                component = COMPONENT_REGISTRY[entry.component_key]
                self.assertEqual(component.family_key, "theme")
                self.assertEqual(
                    component.registry_reference,
                    f"theme_overlay:{entry.occasion_key}",
                )

    def test_all_expected_occasion_component_keys_registered(self):
        from apps.storefront_builder.storefront_appearance.registry import (
            COMPONENT_REGISTRY,
        )

        expected = {
            "theme.none.v1",
            "theme.nowruz.v1",
            "theme.yalda.v1",
            "theme.valentine.v1",
            "theme.ramadan.v1",
            "theme.eid_fitr.v1",
            "theme.eid_qorban.v1",
            "theme.muharram.v1",
        }
        self.assertTrue(expected.issubset(set(COMPONENT_REGISTRY)))

    def test_unknown_theme_symbolic_reference_fails_closed(self):
        from apps.storefront_builder.storefront_appearance.adapters import (
            resolve_registry_reference,
        )
        from apps.storefront_builder.storefront_appearance.contracts import (
            InvalidStoreAppearanceContract,
        )

        with self.assertRaises(InvalidStoreAppearanceContract):
            resolve_registry_reference("theme_overlay:not_a_real_occasion")


# ---------------------------------------------------------------------------
# Catalog single-owner + tone (8, 9, 25.30, 25.31)
# ---------------------------------------------------------------------------
class ThemeCatalogAuthorityTests(SimpleTestCase):
    def test_catalog_is_single_owner_of_occasion_metadata(self):
        from apps.storefront_builder import theme_catalog

        entry = theme_catalog.get_theme_occasion("yalda")
        self.assertEqual(entry.component_key, "theme.yalda.v1")
        self.assertTrue(entry.label_fa)
        self.assertIn(entry.tone, {"festive", "neutral", "mourning"})
        self.assertTrue(entry.accent)

    def test_muharram_tone_is_mourning(self):
        from apps.storefront_builder import theme_catalog

        self.assertEqual(theme_catalog.get_theme_occasion("muharram").tone, "mourning")

    def test_mourning_theme_does_not_enable_celebratory_flags(self):
        from apps.storefront_builder import theme_catalog

        muharram = theme_catalog.get_theme_occasion("muharram")
        # A mourning theme must never carry celebratory motif/pressure flags.
        self.assertFalse(muharram.festive_motifs)
        self.assertFalse(muharram.countdown_pressure)
        self.assertFalse(muharram.sale_badge)

    def test_none_occasion_is_a_true_noop(self):
        from apps.storefront_builder import theme_catalog

        none_entry = theme_catalog.get_theme_occasion("none")
        self.assertEqual(none_entry.component_key, "theme.none.v1")
        self.assertEqual(none_entry.tone, "neutral")
        self.assertTrue(none_entry.is_noop)

    def test_adapter_does_not_duplicate_occasion_data(self):
        # The adapter must read the catalog, not hold its own occasion table.
        import apps.storefront_builder.storefront_appearance.adapters as adapters

        source = adapters.__file__
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        # No hard-coded occasion accent hexes or Persian occasion labels in the
        # adapter; occasion identity lives only in theme_catalog.
        self.assertNotIn("nowruz", text.lower().replace("theme_overlay", ""))


# ---------------------------------------------------------------------------
# Validation (25.7–25.10)
# ---------------------------------------------------------------------------
class ThemeIntensityValidationTests(SimpleTestCase):
    def _manifest_with_theme(self, *, component="theme.yalda.v1", intensity="balanced"):
        from apps.storefront_builder.storefront_appearance.families import (
            DEFAULT_STORE_APPEARANCE_MANIFEST,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            manifest_to_primitive,
        )

        raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
        raw["selections"]["theme"] = component
        raw["settings"]["theme"] = {"intensity": intensity}
        return raw

    def test_intensity_allowlisted_for_theme_family(self):
        from apps.storefront_builder.storefront_appearance.validation import (
            ALLOWED_SETTINGS_BY_FAMILY,
        )

        self.assertEqual(ALLOWED_SETTINGS_BY_FAMILY["theme"], frozenset({"intensity"}))

    def test_subtle_valid(self):
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        validate_store_appearance_manifest(self._manifest_with_theme(intensity="subtle"))

    def test_balanced_valid(self):
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        validate_store_appearance_manifest(self._manifest_with_theme(intensity="balanced"))

    def test_strong_valid(self):
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        validate_store_appearance_manifest(self._manifest_with_theme(intensity="strong"))

    def test_unknown_intensity_rejected(self):
        from apps.storefront_builder.storefront_appearance.contracts import (
            InvalidStoreAppearanceContract,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        with self.assertRaises(InvalidStoreAppearanceContract):
            validate_store_appearance_manifest(
                self._manifest_with_theme(intensity="aggressive")
            )


# ---------------------------------------------------------------------------
# Default / backward compatibility (25.11, 25.12)
# ---------------------------------------------------------------------------
class ThemeDefaultCompatibilityTests(SimpleTestCase):
    def test_default_manifest_selects_theme_none(self):
        from apps.storefront_builder.storefront_appearance.families import (
            DEFAULT_STORE_APPEARANCE_MANIFEST,
        )

        self.assertEqual(
            DEFAULT_STORE_APPEARANCE_MANIFEST.selections["theme"], "theme.none.v1"
        )

    def test_pre_theme_persisted_manifest_normalizes_to_theme_none(self):
        # An old persisted manifest created before the theme family existed:
        # every family EXCEPT theme is present. Normalization must fill the
        # missing family with the safe default and never raise.
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
            DEFAULT_STORE_APPEARANCE_MANIFEST,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            manifest_to_primitive,
            normalize_persisted_manifest,
        )

        primitive = copy.deepcopy(
            manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST)
        )
        primitive["selections"].pop("theme", None)  # pre-W2 shape
        self.assertNotIn("theme", primitive["selections"])

        normalized = normalize_persisted_manifest(primitive)
        self.assertEqual(normalized.selections["theme"], "theme.none.v1")
        # Sanity: normalization produced a complete manifest.
        self.assertEqual(set(normalized.selections), set(COMPONENT_FAMILIES))


# ---------------------------------------------------------------------------
# All-50 Ready Template compatibility (25.13–25.15)
# ---------------------------------------------------------------------------
class ThemeReadyTemplateCompatibilityTests(SimpleTestCase):
    def test_all_ready_template_manifests_valid_and_default_to_theme_none(self):
        from apps.storefront_builder import layout_preset_registry as lpr
        from apps.storefront_builder.storefront_appearance.families import (
            COMPONENT_FAMILIES,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            validate_store_appearance_manifest,
        )

        presets = lpr.list_ready_templates()
        self.assertEqual(len(presets), 50)
        required = set(COMPONENT_FAMILIES)
        for preset in presets:
            with self.subTest(preset=preset.key):
                manifest = dict(preset.store_appearance)
                validated = validate_store_appearance_manifest(
                    manifest, require_complete=True
                ).manifest
                self.assertEqual(set(validated.selections), required)
                self.assertEqual(
                    validated.selections["theme"],
                    "theme.none.v1",
                    "Ready Templates must not auto-assign an occasion theme",
                )


class ThemeReadyTemplateApplyTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_all_50_candidate_previews_resolve(self):
        from apps.storefront_builder import layout_preset_registry as lpr
        from apps.storefront_builder.services import preset_service

        for preset in lpr.list_ready_templates():
            with self.subTest(preset=preset.key):
                candidate = preset_service.resolve_preset_candidate(self.draft, preset)
                self.assertIsNotNone(candidate)

    def test_all_50_apply_succeed_with_theme_none(self):
        from apps.storefront_builder import layout_preset_registry as lpr
        from apps.storefront_builder.services import preset_service
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )

        for preset in lpr.list_ready_templates():
            with self.subTest(preset=preset.key):
                draft = layout_service.get_or_create_draft(self.store, user=self.staff)
                preset_service.apply_preset(draft, preset)
                draft.refresh_from_db()
                manifest = load_store_appearance_manifest(draft)
                self.assertEqual(manifest.selections["theme"], "theme.none.v1")


# ---------------------------------------------------------------------------
# Atomic mutation + reversibility (25.16–25.20)
# ---------------------------------------------------------------------------
class ThemeAtomicMutationTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def _snapshot_non_theme(self, version):
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            manifest_to_primitive,
        )

        version.refresh_from_db()
        primitive = manifest_to_primitive(load_store_appearance_manifest(version))
        selections = {k: v for k, v in primitive["selections"].items() if k != "theme"}
        settings = {k: v for k, v in primitive["settings"].items() if k != "theme"}
        return selections, settings

    def test_apply_theme_changes_only_theme_owned_state(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            manifest_to_primitive,
        )

        before_sel, before_set = self._snapshot_non_theme(self.draft)

        appearance_authority_service.apply_theme(
            version=self.draft,
            component_key="theme.yalda.v1",
            intensity="strong",
        )

        after_sel, after_set = self._snapshot_non_theme(self.draft)
        self.assertEqual(after_sel, before_sel)
        self.assertEqual(after_set, before_set)

        self.draft.refresh_from_db()
        primitive = manifest_to_primitive(load_store_appearance_manifest(self.draft))
        self.assertEqual(primitive["selections"]["theme"], "theme.yalda.v1")
        self.assertEqual(primitive["settings"]["theme"], {"intensity": "strong"})

    def test_clear_theme_resets_theme_to_none_only(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )
        from apps.storefront_builder.storefront_appearance.validation import (
            manifest_to_primitive,
        )

        appearance_authority_service.apply_theme(
            version=self.draft,
            component_key="theme.yalda.v1",
            intensity="strong",
        )
        before_sel, before_set = self._snapshot_non_theme(self.draft)

        appearance_authority_service.clear_theme(version=self.draft)

        after_sel, after_set = self._snapshot_non_theme(self.draft)
        self.assertEqual(after_sel, before_sel)
        self.assertEqual(after_set, before_set)

        self.draft.refresh_from_db()
        primitive = manifest_to_primitive(load_store_appearance_manifest(self.draft))
        self.assertEqual(primitive["selections"]["theme"], "theme.none.v1")
        self.assertNotIn("theme", primitive["settings"])

    def test_reversibility_scenario_restores_pre_theme_state_exactly(self):
        """State A (template) -> State B (merchant customizes non-theme) ->
        State C (enable Yalda strong) -> State D (clear theme). D's non-theme
        state must equal B exactly, NOT State A."""
        from apps.storefront_builder import layout_preset_registry as lpr
        from apps.storefront_builder.services import (
            appearance_authority_service,
            preset_service,
        )

        # State A — apply a Ready Template.
        preset = next(iter(lpr.list_ready_templates()))
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()

        # State B — merchant customizes non-theme appearance (a header change).
        appearance_authority_service.apply_header_variant(
            version=self.draft, header_variant="premium_three_column"
        )
        self.draft.refresh_from_db()
        state_b_sel, state_b_set = self._snapshot_non_theme(self.draft)

        # State C — enable Yalda strong.
        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.yalda.v1", intensity="strong"
        )

        # State D — clear theme.
        appearance_authority_service.clear_theme(version=self.draft)
        state_d_sel, state_d_set = self._snapshot_non_theme(self.draft)

        self.assertEqual(state_d_sel, state_b_sel)
        self.assertEqual(state_d_set, state_b_set)


# ---------------------------------------------------------------------------
# Mutation governance: stale-write, tenant isolation, history (25.21–25.24)
# ---------------------------------------------------------------------------
class ThemeMutationGovernanceTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.layout = self.draft.layout

    def _theme_apply_mutation(self, *, intensity="balanced", component="theme.yalda.v1"):
        return {
            "type": "theme.apply",
            "draft_id": self.draft.pk,
            "component_key": component,
            "intensity": intensity,
        }

    def test_valid_revision_applies_and_advances(self):
        from apps.storefront_builder.services import r4_mutation_service

        base = self.draft.edit_revision
        new_rev = r4_mutation_service.apply_mutation(
            store=self.store,
            actor=self.staff,
            base_revision=base,
            mutation=self._theme_apply_mutation(),
        )
        self.assertGreater(new_rev, base)

    def test_stale_revision_rejected(self):
        from apps.storefront_builder.services import r4_mutation_service

        base = self.draft.edit_revision
        # Advance once so base is now stale.
        r4_mutation_service.apply_mutation(
            store=self.store,
            actor=self.staff,
            base_revision=base,
            mutation=self._theme_apply_mutation(intensity="subtle"),
        )
        with self.assertRaises(r4_mutation_service.R4StaleRevision):
            r4_mutation_service.apply_mutation(
                store=self.store,
                actor=self.staff,
                base_revision=base,  # stale
                mutation=self._theme_apply_mutation(intensity="strong"),
            )

    def test_tenant_isolation_store_a_cannot_mutate_store_b_theme(self):
        from apps.storefront_builder.services import r4_mutation_service
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )

        other = Store.objects.create(name="other-store", slug="other-store")
        other_draft = layout_service.get_or_create_draft(other, user=self.staff)

        # A crafted mutation naming Store B's draft id, applied against Store A,
        # must be rejected — it must never mutate Store B's theme state.
        mutation = {
            "type": "theme.apply",
            "draft_id": other_draft.pk,
            "component_key": "theme.yalda.v1",
            "intensity": "strong",
        }
        with self.assertRaises(r4_mutation_service.R4MutationError):
            r4_mutation_service.apply_mutation(
                store=self.store,
                actor=self.staff,
                base_revision=self.draft.edit_revision,
                mutation=mutation,
            )
        other_draft.refresh_from_db()
        self.assertEqual(
            load_store_appearance_manifest(other_draft).selections["theme"],
            "theme.none.v1",
        )

    def test_theme_mutation_participates_in_undo_redo(self):
        from apps.storefront_builder.services import r4_mutation_service
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )

        base = self.draft.edit_revision
        rev_after_apply = r4_mutation_service.apply_mutation(
            store=self.store,
            actor=self.staff,
            base_revision=base,
            mutation=self._theme_apply_mutation(component="theme.yalda.v1"),
        )
        self.draft.refresh_from_db()
        self.assertEqual(
            load_store_appearance_manifest(self.draft).selections["theme"],
            "theme.yalda.v1",
        )

        undo = r4_mutation_service.apply_history_command(
            store=self.store,
            actor=self.staff,
            base_revision=rev_after_apply,
            command="undo",
        )
        self.assertTrue(undo["changed"])
        self.draft.refresh_from_db()
        self.assertEqual(
            load_store_appearance_manifest(self.draft).selections["theme"],
            "theme.none.v1",
        )


# ---------------------------------------------------------------------------
# Rendering (25.25–25.29)
# ---------------------------------------------------------------------------
class ThemeRenderingTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def test_theme_reaches_canonical_resolved_appearance(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.services.render_service import (
            resolve_store_appearance_render_state,
        )
        from apps.storefront_builder.storefront_appearance.rendering import (
            theme_overlay_state,
        )

        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.yalda.v1", intensity="strong"
        )
        self.draft.refresh_from_db()
        state = resolve_store_appearance_render_state(self.draft)
        overlay = theme_overlay_state(state)
        self.assertEqual(overlay.occasion_key, "yalda")
        self.assertEqual(overlay.intensity, "strong")
        self.assertEqual(overlay.tone, "festive")
        self.assertTrue(overlay.is_active)

    def test_theme_none_has_no_decoration(self):
        from apps.storefront_builder.services.render_service import (
            resolve_store_appearance_render_state,
        )
        from apps.storefront_builder.storefront_appearance.rendering import (
            theme_overlay_state,
        )

        state = resolve_store_appearance_render_state(self.draft)
        overlay = theme_overlay_state(state)
        self.assertEqual(overlay.occasion_key, "none")
        self.assertFalse(overlay.is_active)

    def test_theme_overlay_exposes_platform_owned_css_variables(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.services.render_service import (
            resolve_store_appearance_render_state,
        )
        from apps.storefront_builder.storefront_appearance.rendering import (
            theme_overlay_state,
        )

        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.ramadan.v1", intensity="balanced"
        )
        self.draft.refresh_from_db()
        state = resolve_store_appearance_render_state(self.draft)
        overlay = theme_overlay_state(state)
        css_vars = overlay.css_variables
        self.assertIn("--occasion-accent", css_vars)
        self.assertIn("--occasion-accent-soft", css_vars)
        self.assertIn("--occasion-motif-opacity", css_vars)

    def test_preview_public_parity_after_publish(self):
        """The SAME resolved Theme drives editor preview and published public
        storefront. After publishing a Yalda draft, the published version's
        resolved theme equals the draft's resolved theme."""
        from apps.storefront_builder.services import (
            appearance_authority_service,
            r4_mutation_service,
        )
        from apps.storefront_builder.services.render_service import (
            resolve_store_appearance_render_state,
        )
        from apps.storefront_builder.storefront_appearance.rendering import (
            theme_overlay_state,
        )

        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.yalda.v1", intensity="strong"
        )
        self.draft.refresh_from_db()
        preview_overlay = theme_overlay_state(
            resolve_store_appearance_render_state(self.draft)
        )

        published = r4_mutation_service.publish_draft(
            store=self.store,
            actor=self.staff,
            base_revision=self.draft.edit_revision,
        )
        public_overlay = theme_overlay_state(
            resolve_store_appearance_render_state(published)
        )

        self.assertEqual(preview_overlay.occasion_key, public_overlay.occasion_key)
        self.assertEqual(preview_overlay.intensity, public_overlay.intensity)
        self.assertEqual(preview_overlay.tone, public_overlay.tone)
        self.assertEqual(preview_overlay.css_variables, public_overlay.css_variables)


class ThemeShellChromeAndSectionTests(StorefrontBuilderViewsTestCase):
    """Theme must reach global chrome AND at least one page section through the
    single resolved appearance. The base shell (<html>, header, footer/bottom
    nav) reads the SHOP_OCCASION_* projection produced by the shared
    ``shop_settings`` context processor from the SAME resolved version, and the
    responsive section wrapper carries the same occasion marker."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def _shop_context(self, version):
        from django.test import RequestFactory
        from apps.core.context_processors import shop_settings

        request = RequestFactory().get("/", HTTP_HOST="testserver")
        request.store = self.store
        request.storefront_appearance_version = version
        return shop_settings(request)

    def test_context_processor_projects_theme_onto_global_chrome(self):
        from apps.storefront_builder.services import appearance_authority_service

        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.yalda.v1", intensity="strong"
        )
        self.draft.refresh_from_db()
        ctx = self._shop_context(self.draft)
        self.assertEqual(ctx["SHOP_OCCASION_THEME"], "yalda")
        self.assertEqual(ctx["SHOP_OCCASION_TONE"], "festive")
        self.assertEqual(ctx["SHOP_OCCASION_INTENSITY"], "strong")
        self.assertTrue(ctx["SHOP_OCCASION_ACCENT"])

    def test_theme_none_projection_is_inert(self):
        ctx = self._shop_context(self.draft)
        self.assertEqual(ctx["SHOP_OCCASION_THEME"], "none")

    def test_base_shell_html_consumes_occasion_projection(self):
        # base.html's <html> tag consumes SHOP_OCCASION_* platform values.
        # Render the exact conditional the shell uses against the real
        # context-processor projection (avoids rendering the entire page shell,
        # which needs unrelated nav/menu context).
        from django.template import Context, Template
        from apps.storefront_builder.services import appearance_authority_service

        appearance_authority_service.apply_theme(
            version=self.draft, component_key="theme.yalda.v1", intensity="strong"
        )
        self.draft.refresh_from_db()
        ctx = self._shop_context(self.draft)
        shell_fragment = (
            "{% if SHOP_OCCASION_THEME and SHOP_OCCASION_THEME != 'none' %}"
            'data-occasion-theme="{{ SHOP_OCCASION_THEME }}" '
            'data-occasion-tone="{{ SHOP_OCCASION_TONE }}" '
            'data-occasion-intensity="{{ SHOP_OCCASION_INTENSITY }}" '
            "--occasion-accent:{{ SHOP_OCCASION_ACCENT }}"
            "{% endif %}"
        )
        html = Template(shell_fragment).render(Context(ctx))
        self.assertIn('data-occasion-theme="yalda"', html)
        self.assertIn('data-occasion-intensity="strong"', html)
        self.assertIn("--occasion-accent", html)

        # And base.html's source truly wires these variables (contract check).
        import os
        from django.conf import settings as dj_settings

        with open(
            os.path.join(dj_settings.BASE_DIR, "templates/base.html"),
            "r",
            encoding="utf-8",
        ) as handle:
            base_src = handle.read()
        self.assertIn("data-occasion-theme", base_src)
        self.assertIn("--occasion-accent", base_src)

    def test_section_wrapper_template_consumes_occasion_marker(self):
        # A real page section wrapper must consume the SAME resolved occasion
        # so section decoration is driven by ONE resolved theme (never a second
        # per-section theme lookup). Contract check on the shared wrapper the
        # public renderer already uses for every section.
        import os
        from django.conf import settings as dj_settings

        wrapper = None
        for base in [
            "apps/storefront_builder/templates/storefront_builder/partials/responsive_section_wrapper.html",
        ]:
            path = os.path.join(dj_settings.BASE_DIR, base)
            if os.path.exists(path):
                wrapper = path
                break
        self.assertIsNotNone(wrapper)
        with open(wrapper, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("SHOP_OCCASION_THEME", text)



# ---------------------------------------------------------------------------
# R4 merchant controls — end-to-end through the real mutate route + editor UI
# ---------------------------------------------------------------------------
class ThemeR4EndpointTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)

    def _mutate(self, mutation):
        import json
        from django.urls import reverse

        self.draft.refresh_from_db()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps(
                {"base_revision": self.draft.edit_revision, "mutation": mutation}
            ),
            content_type="application/json",
        )

    def test_theme_apply_and_clear_through_real_route(self):
        from apps.storefront_builder.storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )

        resp = self._mutate(
            {
                "type": "theme.apply",
                "draft_id": self.draft.pk,
                "component_key": "theme.yalda.v1",
                "intensity": "strong",
            }
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        self.assertEqual(manifest.selections["theme"], "theme.yalda.v1")
        self.assertEqual(manifest.settings["theme"], {"intensity": "strong"})

        resp = self._mutate({"type": "theme.clear", "draft_id": self.draft.pk})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        self.assertEqual(manifest.selections["theme"], "theme.none.v1")
        self.assertNotIn("theme", manifest.settings)

    def test_theme_apply_invalid_intensity_rejected_through_route(self):
        resp = self._mutate(
            {
                "type": "theme.apply",
                "draft_id": self.draft.pk,
                "component_key": "theme.yalda.v1",
                "intensity": "aggressive",
            }
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIs(resp.json()["ok"], False)

    def test_r4_editor_renders_theme_controls(self):
        from django.urls import reverse

        resp = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("data-r4-theme-panel", body)
        self.assertIn("data-r4-theme-apply", body)
        self.assertIn("data-r4-theme-clear", body)
        self.assertIn("تم مناسبتی", body)
