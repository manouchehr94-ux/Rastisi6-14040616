"""Canonical, preservation-aware transformation of Storefront Appearance state.

Phase 1 — Task 2 of the Storefront Appearance Convergence plan
(``docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md``).

This module owns exactly one responsibility: **preservation-aware
transformation of the typed/legacy Appearance state on a Draft
``StorefrontLayoutVersion``**. Legacy views, the R4 mutation service and the
preset service will (in later tasks) delegate their *state transformation* to
these primitives instead of independently reconstructing overlapping state.

It deliberately does NOT own:

* HTTP authorization / route behavior;
* active-Draft locking, ``edit_revision`` / stale-write detection;
* edit-history snapshots;
* rendering / effective resolution;
* business-domain logic; media lifetime;
* Template composition replacement.

Those responsibilities remain in their current layers. In particular, the
Draft-only guard, compatibility-mirror synchronization and the single ``save``
are provided by ``storefront_appearance.persistence.persist_store_appearance_manifest``
and are reused here rather than duplicated.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ..models import APPEARANCE_CONFIG_DEFAULTS
from ..storefront_appearance.contracts import (
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
)
from ..storefront_appearance.persistence import (
    component_key_for_registry_reference,
    load_store_appearance_manifest,
    persist_store_appearance_manifest,
)
from ..storefront_appearance.validation import manifest_to_primitive
from . import layout_service


# The set of appearance keys owned by the legacy Appearance form/validator.
# Anything outside this set (e.g. the reserved ``store_appearance`` typed
# manifest, or future canonical/provenance state) is OPAQUE to this
# transformation and must survive a managed-field patch untouched.
#
# Pre-Task-10 remediation — bug fix: this set previously omitted
# ``layout_service.PAGE_APPEARANCE_KEYS`` (content_width/grid_density/
# card_shadow/card_hover/hero_style), the 5 Phase 8 P0-7 structural fields.
# ``validate_appearance_config`` has always cleaned/returned them when
# posted (they are deliberately sparse-by-design, not part of
# ``APPEARANCE_CONFIG_DEFAULTS``), and the legacy ``storefront_appearance_
# editor`` view has always read and posted them — but this merge loop only
# ever copied keys already in ``APPEARANCE_CONFIG_DEFAULTS`` back onto the
# saved config, so a Store-global (non-Template, non-Page-override) edit of
# any of these 5 fields was silently discarded by both the legacy editor and
# every caller of ``apply_appearance_patch``, R4 included. Reproduced
# directly against this function before the fix (a bare ``content_width``
# patch left the saved config completely untouched); fixed by including the
# same 5-key set ``layout_service.validate_page_appearance_overrides``
# already uses as its own canonical allowlist — no new field, no schema
# change, single source of truth.
_MANAGED_APPEARANCE_KEYS = frozenset(APPEARANCE_CONFIG_DEFAULTS) | layout_service.PAGE_APPEARANCE_KEYS

# Legacy-selector registry-reference prefixes, reused from the persistence
# adapter's own conventions. We do not maintain a second component-key map.
_HEADER_REFERENCE_PREFIX = "global_region:header:"
_FOOTER_REFERENCE_PREFIX = "global_region:footer:"
_BOTTOM_NAV_REFERENCE_PREFIX = "global_region:mobile_bottom_nav:"


def _merge_appearance_config(
    current: Mapping[str, Any] | None,
    patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a new appearance_config where the validated managed projection of
    ``patch`` is merged over ``current`` while preserving every non-managed
    (opaque/canonical) key.

    ``layout_service.validate_appearance_config`` intentionally rebuilds only
    the managed keys (starting from ``APPEARANCE_CONFIG_DEFAULTS``), so calling
    it directly would drop opaque state such as ``store_appearance``. We
    therefore: (1) build the managed input from current+patch, (2) validate it
    (so an invalid managed field still fails), and (3) copy the validated
    managed keys back onto a deep copy of ``current`` — leaving opaque keys
    exactly as they were.
    """
    current_config = deepcopy(dict(current or {}))

    # Managed input: current managed values overlaid with the incoming patch.
    managed_input = {
        key: value
        for key, value in current_config.items()
        if key in _MANAGED_APPEARANCE_KEYS
    }
    managed_input.update(dict(patch))

    validated_managed = layout_service.validate_appearance_config(managed_input)

    # Merge validated managed values back over the opaque-preserving copy.
    merged = current_config
    for key in _MANAGED_APPEARANCE_KEYS:
        if key in validated_managed:
            merged[key] = validated_managed[key]
    return merged


def apply_appearance_patch(
    *,
    version,
    patch: Mapping[str, Any],
):
    """Merge validated legacy/global appearance fields onto ``version`` without
    dropping opaque canonical keys (e.g. the typed ``store_appearance``
    manifest).

    Saves only ``appearance_config``. Draft/lifecycle/authorization concerns
    remain with the caller.
    """
    version.appearance_config = _merge_appearance_config(
        version.appearance_config, patch
    )
    version.save(update_fields=["appearance_config", "updated_at"])
    return version


def apply_store_appearance_manifest(
    *,
    version,
    manifest: StoreAppearanceManifest | Mapping[str, Any],
):
    """Validate and persist the complete typed manifest and its compatibility
    mirrors, delegating to the single canonical persistence primitive.
    """
    persist_store_appearance_manifest(version, manifest)
    return version


def _manifest_with_family(version, *, family_key: str, component_key: str):
    """Build a complete primitive manifest equal to the version's current
    effective manifest with a single ``family_key`` selection replaced.
    """
    current = load_store_appearance_manifest(version)
    primitive = manifest_to_primitive(current)
    primitive["selections"][family_key] = component_key
    return primitive


def _typed_key_for_selector(
    *, family_key: str, prefix: str, selector: str
) -> str:
    """Translate a legacy selector value into its typed component key using the
    existing inverse adapter (no duplicate maps).
    """
    reference = f"{prefix}{selector}"
    component_key = component_key_for_registry_reference(
        reference, family_key=family_key
    )
    if component_key is None:
        raise InvalidStoreAppearanceContract(
            f"unknown {family_key} selector: {selector!r}"
        )
    return component_key


def apply_header_variant(
    *,
    version,
    header_variant: str,
):
    """Update the Header selection so the legacy ``header_config`` mirror and the
    typed manifest ``header`` family agree, preserving all other families.
    """
    component_key = _typed_key_for_selector(
        family_key="header",
        prefix=_HEADER_REFERENCE_PREFIX,
        selector=header_variant,
    )
    manifest = _manifest_with_family(
        version, family_key="header", component_key=component_key
    )
    # persist_store_appearance_manifest re-derives and writes the legacy
    # header_config.header_variant mirror from the typed manifest, so both stay
    # in sync in a single validated, atomic save.
    persist_store_appearance_manifest(version, manifest)
    return version


def apply_footer_variant(
    *,
    version,
    footer_variant: str | None = None,
    mobile_nav_variant: str | None = None,
):
    """Update the Footer and/or Mobile Bottom Navigation selection so the legacy
    ``footer_config`` mirrors and the typed manifest ``footer`` / ``bottom_nav``
    families agree, preserving all other families.

    At least one of ``footer_variant`` / ``mobile_nav_variant`` should be
    provided; a call with neither is a no-op preserving current state.
    """
    if footer_variant is None and mobile_nav_variant is None:
        return version

    current = load_store_appearance_manifest(version)
    primitive = manifest_to_primitive(current)

    if footer_variant is not None:
        primitive["selections"]["footer"] = _typed_key_for_selector(
            family_key="footer",
            prefix=_FOOTER_REFERENCE_PREFIX,
            selector=footer_variant,
        )
    if mobile_nav_variant is not None:
        primitive["selections"]["bottom_nav"] = _typed_key_for_selector(
            family_key="bottom_nav",
            prefix=_BOTTOM_NAV_REFERENCE_PREFIX,
            selector=mobile_nav_variant,
        )

    persist_store_appearance_manifest(version, primitive)
    return version


def apply_ready_template_appearance(
    *,
    version,
    preset,
):
    """Apply a Ready Template's ordinary appearance overlay, header/footer config
    and its COMPLETE declared typed manifest to ``version``.

    This is the canonical authority primitive for recipe appearance
    application. Task 2 only builds and unit-tests it; wiring it into
    ``preset_service.apply_preset`` is Task 5. It does NOT replace page
    composition, provenance, or baseline snapshots — those remain in
    ``preset_service``.

    The typed manifest is persisted LAST so that its compatibility mirrors are
    the authoritative selector synchronization step and cannot be overwritten
    by a stale legacy overlay written earlier in this function.
    """
    # 1) Ordinary appearance overlay (font/radius/motion/... ), preservation-aware.
    if preset.appearance:
        apply_appearance_patch(version=version, patch=dict(preset.appearance))

    # 2) Preset header/footer config overlays — merge so unrelated config
    #    (toggles/content) survives; the selector fields will be re-derived
    #    authoritatively from the typed manifest in step 3.
    save_fields: list[str] = []
    if preset.header:
        header = dict(version.header_config or {})
        header.update(dict(preset.header))
        version.header_config = header
        save_fields.append("header_config")
    if preset.footer:
        footer = dict(version.footer_config or {})
        footer.update(dict(preset.footer))
        version.footer_config = footer
        save_fields.append("footer_config")
    if save_fields:
        version.save(update_fields=[*save_fields, "updated_at"])

    # 3) Complete declared typed manifest LAST — authoritative selector sync.
    if preset.store_appearance:
        persist_store_appearance_manifest(version, preset.store_appearance)

    return version


class PageAppearanceNotDraftError(ValueError):
    """Phase 4 (Task 3C) — a Page Appearance patch was attempted against a
    page whose version is not the active Draft. Tenant-safety/lifecycle
    boundary, not a validation error — never silently applied to a
    Published (immutable, historical) or Archived version."""


def apply_page_appearance_patch(*, page, patch: Mapping[str, Any]):
    """Phase 4 (Task 3C) — the ONE canonical write primitive for the Page
    Appearance tier. Draft-only (mirrors every other mutation boundary in
    this domain — Published/Archived versions are immutable history);
    sparse-merge (only the keys present in ``patch`` change; every other
    key already stored on ``page.page_appearance_overrides`` survives
    untouched — the same principle ``_merge_appearance_config`` applies for
    Store Global, simpler here since this JSON field only ever holds the
    bounded ``PAGE_APPEARANCE_KEYS`` set, so there is no opaque-key
    preservation concern)."""
    if page.version.status != page.version.__class__.Status.DRAFT:
        raise PageAppearanceNotDraftError(
            "بازنویسیِ ظاهرِ صفحه فقط رویِ Draftِ فعال مجاز است"
        )
    validated_patch = layout_service.validate_page_appearance_overrides(dict(patch))
    merged = dict(page.page_appearance_overrides or {})
    merged.update(validated_patch)
    page.page_appearance_overrides = merged
    page.save(update_fields=["page_appearance_overrides", "updated_at"])
    return page


def effective_page_appearance_config(*, store_appearance_config: Mapping[str, Any], page) -> dict:
    """Phase 4 (Task 3C) — the canonical resolver: Store Global's already-
    fully-defaulted appearance config, with this Page's sparse override (if
    any) applied on top for exactly the bounded ``PAGE_APPEARANCE_KEYS``
    set. This is the ONE function Preview and Public both must call — never
    a second, independently-derived resolution of the same precedence."""
    resolved = dict(store_appearance_config)
    resolved.update(dict(page.page_appearance_overrides or {}))
    return resolved
