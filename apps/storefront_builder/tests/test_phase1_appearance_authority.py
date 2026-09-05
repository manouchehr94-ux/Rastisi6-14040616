"""Phase 1 — Architecture & Authority: RED characterization tests.

Task 1 of the Storefront Appearance Convergence Phase-1 plan
(``docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md``).

These tests characterize the CURRENT baseline behavior and encode the
*desired* Phase-1 architecture invariants. They are intentionally written to
FAIL (RED) where the baseline reproduces a known Phase-1 authority gap, and to
PASS (GREEN) where the desired behavior is a backward-compatibility guarantee
that must be protected.

NO production code is modified by this task. Each test exercises real, public
routes and services (legacy Appearance/Header/Footer editors, the canonical
preset service, and the shared render resolver) rather than private internals.

Expected classification (per the plan):

* Group A — legacy Appearance preservation: EXPECTED RED
    (the legacy Appearance editor rebuilds ``appearance_config`` from known
    keys only and drops the reserved ``store_appearance`` manifest —
    ``views.storefront_appearance_editor``).
* Group B — legacy Header/Footer typed-manifest sync: characterization
    (the legacy editors write only ``header_config``/``footer_config``
    selectors; the typed manifest is derived at read time. Whether the
    *effective* manifest follows the legacy selector and leaves unrelated
    selections intact is what these tests pin down).
* Group C — Ready Template full-manifest fidelity: EXPECTED RED
    (``preset_service.apply_preset`` never persists ``preset.store_appearance``
    — the A02 gap. A conflicting pre-existing manifest survives Apply).
* Group D1 — historical/unmarked local variant precedence: EXPECTED GREEN
    (a non-default Store manifest variant currently wins over a saved local
    section variant; this legacy output must be protected).
* Group D2 — explicit-local variant precedence: EXPECTED RED
    (the ``appearance_overrides.variant_explicit`` marker is not yet honored;
    the local variant does not yet win over the inherited Store default).
"""

from __future__ import annotations

import copy

from django.core.cache import cache
from django.urls import reverse

from apps.storefront_builder.layout_preset_registry import get_layout_preset
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import (
    appearance_authority_service,
    layout_service,
    preset_service,
    render_service,
)
from apps.storefront_builder.storefront_appearance.contracts import (
    InvalidStoreAppearanceContract,
)
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    STORE_APPEARANCE_CONFIG_KEY,
    load_store_appearance_manifest,
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
)

from .test_views import StorefrontBuilderViewsTestCase


def _manifest_with(**selections):
    """A complete valid primitive manifest with the given selections overridden.

    Mirrors the helper used by ``test_r4_store_appearance_rendering`` /
    ``test_r4_store_appearance_persistence`` so the fixture is identical to the
    rest of the suite.
    """
    raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
    raw["selections"].update(selections)
    return raw


class Phase1AppearanceAuthorityBase(StorefrontBuilderViewsTestCase):
    """Shared Draft/manifest helpers for the Phase-1 characterization tests.

    Reuses ``StorefrontBuilderViewsTestCase`` for the store + OWNER membership +
    logged-in dashboard client with ``STOREFRONT_LAYOUT_MANAGE``.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)

    # -- manifest helpers -------------------------------------------------
    def _persist_manifest(self, **selections):
        raw = _manifest_with(**selections)
        persist_store_appearance_manifest(self.draft, raw)
        self.draft.refresh_from_db()
        return raw

    def _effective_selections(self):
        self.draft.refresh_from_db()
        state = render_service.resolve_store_appearance_render_state(self.draft)
        return dict(state.manifest.selections)

    # -- section helpers --------------------------------------------------
    def _reset_home_hero(self, *, hero_style="overlay", variant_explicit=None):
        self.home.sections.all().delete()
        settings = {"hero_style": hero_style}
        if variant_explicit is not None:
            settings["appearance_overrides"] = {"variant_explicit": variant_explicit}
        return StorefrontSection.objects.create(
            page=self.home,
            section_key="hero_banner",
            order=0,
            settings=settings,
        )

    def _home_render_items(self):
        # Fresh page instance so cached sections/settings are re-read.
        self.draft.refresh_from_db()
        page = self.draft.get_page(StorefrontPage.PageType.HOME)
        return render_service.build_page_render_items(page, self.store)


# =====================================================================
# TEST GROUP A — LEGACY APPEARANCE PRESERVATION
# =====================================================================
class LegacyAppearancePreservationTests(Phase1AppearanceAuthorityBase):
    """Desired invariant: a legacy Appearance edit changing one ordinary field
    must PRESERVE the persisted typed Store Appearance manifest.
    """

    def test_legacy_appearance_edit_preserves_typed_manifest(self):
        # Arrange: a valid non-default typed manifest (incl. non-default Hero
        # and Card) is persisted on the active Draft.
        self._persist_manifest(
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
        )
        self.draft.refresh_from_db()
        original_manifest = copy.deepcopy(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY)
        )
        self.assertIsNotNone(
            original_manifest,
            "precondition: the persisted manifest must exist before the edit",
        )
        self.assertEqual(original_manifest["selections"]["hero"], "hero.split.v1")
        self.assertEqual(original_manifest["selections"]["card"], "card.luxury_dark.v1")

        # Act: POST the legacy Appearance editor changing only `font`, using
        # the real route and a real (minimal) valid payload.
        response = self.client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {"font": "Tahoma"},
        )

        # Assert desired behavior.
        self.assertEqual(
            response.status_code,
            302,
            "legacy Appearance POST should redirect on success",
        )
        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.appearance_config.get("font"),
            "Tahoma",
            "the edited field must change",
        )
        self.assertEqual(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY),
            original_manifest,
            "the typed Store Appearance manifest must survive a legacy "
            "single-field Appearance edit (Phase-1 canonical-writer invariant)",
        )

    def test_legacy_appearance_edit_preserves_effective_hero_selection(self):
        """Effective-state view of the same invariant.

        Even if one accepts that the reserved key may be re-derived, the
        *effective* resolved Hero selection must not silently revert to the
        safe default after an unrelated Appearance edit.
        """
        self._persist_manifest(hero="hero.split.v1", card="card.luxury_dark.v1")

        self.client.post(
            reverse("dashboard:storefront-builder-appearance"),
            {"font": "Tahoma"},
        )

        selections = self._effective_selections()
        self.assertEqual(
            selections.get("hero"),
            "hero.split.v1",
            "effective Hero selection must survive an unrelated Appearance edit",
        )
        self.assertEqual(
            selections.get("card"),
            "card.luxury_dark.v1",
            "effective Card selection must survive an unrelated Appearance edit",
        )


# =====================================================================
# TEST GROUP B — LEGACY HEADER / FOOTER SYNC
# =====================================================================
class LegacyHeaderFooterSyncTests(Phase1AppearanceAuthorityBase):
    """Desired invariant: after a legacy Header/Footer selector edit, the
    effective typed manifest resolves to the newly chosen family value and
    unrelated manifest selections remain unchanged.
    """

    def test_legacy_header_edit_updates_effective_manifest_selection(self):
        # Arrange: a persisted manifest with selection A for header and a
        # distinct non-default hero selection that must remain intact.
        self._persist_manifest(
            header="header.legacy_default.v1",
            hero="hero.split.v1",
        )

        # Act: submit legacy Header selector B via the real Header route.
        # The real Header form requires `show_cart` to remain enabled
        # (validate_header_config rejects a header with no cart path), so we
        # send a faithful payload with the cart toggle on rather than a
        # stripped-down one.
        response = self.client.post(
            reverse("dashboard:storefront-builder-header"),
            {"header_variant": "dark_tech", "show_cart": "on"},
        )
        self.assertEqual(
            response.status_code,
            302,
            "legacy Header POST should redirect on success",
        )

        # Assert desired behavior.
        selections = self._effective_selections()
        self.assertEqual(
            selections.get("header"),
            "header.dark_tech.v1",
            "effective manifest header selection must follow the legacy edit",
        )
        self.assertEqual(
            selections.get("hero"),
            "hero.split.v1",
            "unrelated manifest selections must be preserved by a Header edit",
        )

    def test_legacy_footer_edit_updates_effective_manifest_selection(self):
        # Arrange.
        self._persist_manifest(
            footer="footer.legacy_default.v1",
            hero="hero.split.v1",
        )

        # Act: submit legacy Footer selector via the real Footer route.
        # The real Footer form requires at least one footer section to remain
        # enabled (validate_footer_config rejects a fully-empty footer), so we
        # send a faithful payload with a couple of standard sections on.
        response = self.client.post(
            reverse("dashboard:storefront-builder-footer"),
            {
                "footer_variant": "marketplace_dense",
                "show_about": "on",
                "show_copyright": "on",
            },
        )
        self.assertEqual(
            response.status_code,
            302,
            "legacy Footer POST should redirect on success",
        )

        # Assert desired behavior.
        selections = self._effective_selections()
        self.assertEqual(
            selections.get("footer"),
            "footer.marketplace_dense.v1",
            "effective manifest footer selection must follow the legacy edit",
        )
        self.assertEqual(
            selections.get("hero"),
            "hero.split.v1",
            "unrelated manifest selections must be preserved by a Footer edit",
        )


# =====================================================================
# TEST GROUP C — READY TEMPLATE FULL MANIFEST FIDELITY (A02)
# =====================================================================
class ReadyTemplateManifestFidelityTests(Phase1AppearanceAuthorityBase):
    """Desired invariant (Phase-1 core, A02): after applying a Ready Template,
    the effective manifest selections must equal the template's *complete*
    declared selections — not just header/footer/bottom_nav/motion — regardless
    of any conflicting selections present on the Draft beforehand.
    """

    PRESET_KEY = "dense_marketplace"

    def test_ready_template_apply_replaces_all_declared_manifest_selections(self):
        preset = get_layout_preset(self.PRESET_KEY)
        self.assertIsNotNone(preset, f"preset {self.PRESET_KEY!r} must exist")
        self.assertTrue(
            getattr(preset, "is_ready_template", False),
            f"{self.PRESET_KEY!r} must be a Ready Template",
        )
        declared = dict(preset.store_appearance["selections"])

        # Arrange: seed the Draft with a manifest that DELIBERATELY conflicts
        # with the recipe across multiple families (hero/card/product_view/
        # layout/badge), so a full-fidelity Apply must overwrite every one.
        self._persist_manifest(
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
            product_view="product_view.legacy_default.v1",
            layout="layout.legacy_default.v1",
            badge="badge.none.v1",
        )

        # Act: apply through the canonical preset service used by the product.
        preset_service.apply_preset(self.draft, preset)

        # Assert: complete declared selection mapping is now effective.
        effective = self._effective_selections()
        self.assertEqual(
            effective,
            declared,
            "declared Ready Template selections must equal effective manifest "
            "selections after Apply (A02: full declared manifest fidelity)",
        )

    def test_ready_template_apply_persists_declared_manifest_key(self):
        """Persistence-level view of A02: the reserved ``store_appearance`` key
        must hold the declared selections after Apply.
        """
        preset = get_layout_preset(self.PRESET_KEY)
        declared = dict(preset.store_appearance["selections"])

        self._persist_manifest(
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
        )
        preset_service.apply_preset(self.draft, preset)

        self.draft.refresh_from_db()
        persisted = load_store_appearance_manifest(self.draft)
        self.assertEqual(
            dict(persisted.selections),
            declared,
            "applying a Ready Template must persist its complete declared "
            "manifest selections (A02)",
        )


# =====================================================================
# TEST GROUP D — LOCAL VARIANT PRECEDENCE CHARACTERIZATION
# =====================================================================
class LocalVariantPrecedenceTests(Phase1AppearanceAuthorityBase):
    """D1 protects the current (legacy) output for historical rows.
    D2 encodes the desired explicit-local override behavior.
    """

    def test_historical_unmarked_variant_keeps_legacy_inherited_behavior(self):
        # Arrange: a saved local Hero variant with NO explicit-local marker,
        # and a conflicting non-default Store manifest Hero selection.
        self._reset_home_hero(hero_style="overlay", variant_explicit=None)
        self._persist_manifest(hero="hero.split.v1")

        # Act.
        items = self._home_render_items()

        # Assert CURRENT compatibility behavior: the Store/global manifest
        # variant wins for an unmarked historical row. This SHOULD PASS on the
        # baseline and must keep passing to protect existing stores.
        self.assertTrue(items, "home should render at least the hero item")
        active = items[0].get("active_variant")
        self.assertIsNotNone(active, "hero should resolve an active variant")
        self.assertEqual(
            active.key,
            "split",
            "historical unmarked section: inherited Store manifest variant "
            "must still win (backward-compatibility guarantee)",
        )

    def test_explicit_local_variant_wins_store_default(self):
        # Arrange: the same section, now carrying the explicit-local marker.
        self._reset_home_hero(hero_style="overlay", variant_explicit=True)
        self._persist_manifest(hero="hero.split.v1")

        # Act.
        items = self._home_render_items()

        # Assert DESIRED architecture behavior: an explicit local variant wins
        # over the inherited Store Global default.
        self.assertTrue(items, "home should render at least the hero item")
        active = items[0].get("active_variant")
        self.assertIsNotNone(active, "hero should resolve an active variant")
        self.assertEqual(
            active.key,
            "overlay",
            "explicit local Section variant (variant_explicit=True) must win "
            "over the inherited Store Global default (approved precedence)",
        )



# =====================================================================
# TASK 2 — APPEARANCE AUTHORITY SERVICE (unit-level, no route/render wiring)
# =====================================================================
class AppearanceAuthorityServiceTests(Phase1AppearanceAuthorityBase):
    """Directly exercise the canonical transformation primitives introduced in
    Task 2. These are unit-level tests of
    ``appearance_authority_service`` and must be GREEN after Task 2.

    They do NOT go through legacy routes, R4, preset_service, or the renderer:
    Task 2 only builds the transformation layer that later tasks will call.
    """

    # -- appearance patch preservation ------------------------------------
    def test_apply_appearance_patch_preserves_typed_manifest(self):
        self._persist_manifest(hero="hero.split.v1", card="card.luxury_dark.v1")
        self.draft.refresh_from_db()
        original_manifest = copy.deepcopy(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY)
        )
        self.assertIsNotNone(original_manifest)

        appearance_authority_service.apply_appearance_patch(
            version=self.draft, patch={"font": "Tahoma"}
        )

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY),
            original_manifest,
            "appearance patch must preserve the typed manifest key",
        )

    def test_apply_appearance_patch_preserves_unrelated_opaque_keys(self):
        # Seed an opaque/provenance-like key alongside a managed key.
        self._persist_manifest(hero="hero.split.v1")
        self.draft.refresh_from_db()
        config = dict(self.draft.appearance_config or {})
        config["layout_preset_key"] = "dense_marketplace"  # managed key
        config["__opaque_canonical_probe__"] = {"kept": True}  # unknown/opaque
        self.draft.appearance_config = config
        self.draft.save(update_fields=["appearance_config"])

        appearance_authority_service.apply_appearance_patch(
            version=self.draft, patch={"font": "Tahoma"}
        )

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        # Managed key that was not part of the patch is preserved.
        self.assertEqual(
            self.draft.appearance_config.get("layout_preset_key"),
            "dense_marketplace",
        )
        # Unknown/opaque canonical key is preserved untouched.
        self.assertEqual(
            self.draft.appearance_config.get("__opaque_canonical_probe__"),
            {"kept": True},
        )
        # And the typed manifest still survives.
        self.assertEqual(
            self.draft.appearance_config.get(STORE_APPEARANCE_CONFIG_KEY)[
                "selections"
            ]["hero"],
            "hero.split.v1",
        )

    def test_apply_appearance_patch_rejects_invalid_managed_field(self):
        self._persist_manifest(hero="hero.split.v1")
        with self.assertRaises(Exception):
            appearance_authority_service.apply_appearance_patch(
                version=self.draft, patch={"font": "NotARealFont123"}
            )
        # No partial persistence of the bad value.
        self.draft.refresh_from_db()
        self.assertNotEqual(self.draft.appearance_config.get("font"), "NotARealFont123")

    # -- header / footer / nav sync ---------------------------------------
    def test_apply_header_variant_syncs_mirror_and_manifest(self):
        self._persist_manifest(header="header.legacy_default.v1", hero="hero.split.v1")

        appearance_authority_service.apply_header_variant(
            version=self.draft, header_variant="dark_tech"
        )

        self.draft.refresh_from_db()
        # Legacy mirror updated.
        self.assertEqual(
            self.draft.header_config.get("header_variant"), "dark_tech"
        )
        # Typed manifest selection updated to match.
        selections = self._effective_selections()
        self.assertEqual(selections.get("header"), "header.dark_tech.v1")
        # Unrelated family preserved.
        self.assertEqual(selections.get("hero"), "hero.split.v1")

    def test_apply_footer_variant_syncs_mirror_and_manifest(self):
        self._persist_manifest(footer="footer.legacy_default.v1", hero="hero.split.v1")

        appearance_authority_service.apply_footer_variant(
            version=self.draft, footer_variant="marketplace_dense"
        )

        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.footer_config.get("footer_variant"), "marketplace_dense"
        )
        selections = self._effective_selections()
        self.assertEqual(selections.get("footer"), "footer.marketplace_dense.v1")
        self.assertEqual(selections.get("hero"), "hero.split.v1")

    def test_apply_footer_variant_mobile_nav_syncs_bottom_nav(self):
        self._persist_manifest(
            footer="footer.marketplace_dense.v1",
            bottom_nav="bottom_nav.hidden.v1",
            hero="hero.split.v1",
        )

        appearance_authority_service.apply_footer_variant(
            version=self.draft, mobile_nav_variant="five_item"
        )

        self.draft.refresh_from_db()
        self.assertEqual(
            self.draft.footer_config.get("mobile_nav_variant"), "five_item"
        )
        selections = self._effective_selections()
        self.assertEqual(selections.get("bottom_nav"), "bottom_nav.five_item.v1")
        # Footer selector and unrelated family untouched.
        self.assertEqual(selections.get("footer"), "footer.marketplace_dense.v1")
        self.assertEqual(selections.get("hero"), "hero.split.v1")

    def test_apply_header_variant_rejects_unknown_selector(self):
        self._persist_manifest(header="header.legacy_default.v1", hero="hero.split.v1")

        with self.assertRaises(Exception):
            appearance_authority_service.apply_header_variant(
                version=self.draft, header_variant="__definitely_not_a_variant__"
            )
        # Unrelated state not mutated.
        self.draft.refresh_from_db()
        self.assertEqual(self._effective_selections().get("hero"), "hero.split.v1")

    # -- full manifest application ----------------------------------------
    def test_apply_store_appearance_manifest_persists_validated_manifest(self):
        raw = _manifest_with(
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
            footer="footer.marketplace_dense.v1",
        )

        appearance_authority_service.apply_store_appearance_manifest(
            version=self.draft, manifest=raw
        )

        self.draft.refresh_from_db()
        persisted = load_store_appearance_manifest(self.draft)
        self.assertEqual(persisted.selections["hero"], "hero.split.v1")
        self.assertEqual(persisted.selections["card"], "card.luxury_dark.v1")
        self.assertEqual(persisted.selections["footer"], "footer.marketplace_dense.v1")
        # Compatibility mirror synchronized by the persistence primitive.
        self.assertEqual(
            self.draft.footer_config.get("footer_variant"), "marketplace_dense"
        )

    def test_apply_store_appearance_manifest_rejects_invalid_manifest(self):
        bad = _manifest_with(hero="hero.__nope__.v1")
        with self.assertRaises(InvalidStoreAppearanceContract):
            appearance_authority_service.apply_store_appearance_manifest(
                version=self.draft, manifest=bad
            )

    # -- ready template appearance primitive (NOT wired to preset_service) -
    def test_apply_ready_template_appearance_persists_declared_manifest(self):
        preset = get_layout_preset("dense_marketplace")
        declared = dict(preset.store_appearance["selections"])
        # Seed conflicting selections; the primitive must overwrite them all.
        self._persist_manifest(
            hero="hero.split.v1",
            card="card.luxury_dark.v1",
            layout="layout.legacy_default.v1",
        )

        appearance_authority_service.apply_ready_template_appearance(
            version=self.draft, preset=preset
        )

        self.draft.refresh_from_db()
        persisted = load_store_appearance_manifest(self.draft)
        self.assertEqual(dict(persisted.selections), declared)
        # Ordinary appearance overlay from the preset is also applied.
        self.assertEqual(
            self.draft.appearance_config.get("font"),
            preset.appearance["font"],
        )
