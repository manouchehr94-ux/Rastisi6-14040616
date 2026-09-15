"""Read-only Store Appearance resolution for the shared R4 render pipeline.

The persisted manifest contains only stable component identities.  This module
turns those identities into trusted, platform-owned registry implementations
once per ``StorefrontLayoutVersion`` render.  It is deliberately not a second
renderer: Preview and Public continue to use ``services.render_service`` and
thread this typed state through the existing global-region/section helpers.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

from .. import global_region_registry
from ..global_region_registry import GlobalVariantDefinition
from ..variant_contract import VariantDefinition
from .adapters import resolve_component_implementation
from .contracts import (
    ComponentDefinition,
    ComponentFamilyDefinition,
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
)
from .families import COMPONENT_FAMILIES
from .persistence import load_store_appearance_manifest
from .registry import COMPONENT_REGISTRY


_GLOBAL_REGION_BY_FAMILY = {
    "header": global_region_registry.GLOBAL_HEADER_REGION,
    "footer": global_region_registry.GLOBAL_FOOTER_REGION,
    "bottom_nav": global_region_registry.GLOBAL_MOBILE_NAV_REGION,
}


@dataclasses.dataclass(frozen=True)
class ResolvedAppearanceComponent:
    """One selected family resolved to its trusted existing implementation."""

    family: ComponentFamilyDefinition
    component: ComponentDefinition
    implementation: object


@dataclasses.dataclass(frozen=True)
class ResolvedStoreAppearance:
    """Typed, immutable appearance state for exactly one layout version."""

    version_id: int
    manifest: StoreAppearanceManifest
    components: Mapping[str, ResolvedAppearanceComponent]

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))

    def component(self, family_key: str) -> ResolvedAppearanceComponent:
        try:
            return self.components[family_key]
        except KeyError as exc:
            raise InvalidStoreAppearanceContract(
                f"unknown resolved appearance family: {family_key}"
            ) from exc


def resolve_store_appearance_manifest_state(
    manifest: StoreAppearanceManifest, *, version_id: int,
) -> ResolvedStoreAppearance:
    """Phase 5, Task 1 corrective — the pure manifest-to-render-state core,
    extracted out of ``resolve_store_appearance_render_state`` (behavior for
    that function is unchanged; this is a pure extract, not a rewrite) so
    BOTH the persisted-version path below AND a transient candidate-preview
    path (``preset_service.resolve_preset_candidate``) resolve a
    ``StoreAppearanceManifest`` into ``ResolvedStoreAppearance`` through
    exactly one implementation. Takes an already-typed, already-validated
    manifest directly — no I/O, no persistence lookup, no assumption that the
    manifest is actually saved anywhere at ``version_id``. Registry
    implementations are resolved only from platform-owned symbolic
    references; no merchant-supplied renderer path is ever evaluated here."""

    resolved: dict[str, ResolvedAppearanceComponent] = {}
    for family_key, family in COMPONENT_FAMILIES.items():
        component_key = manifest.selections[family_key]
        component = COMPONENT_REGISTRY.get(component_key)
        if component is None:
            # Normalized/validated manifests make this unreachable, but
            # retaining the explicit contract keeps a corrupted
            # registry/state boundary loud.
            raise InvalidStoreAppearanceContract(
                f"unknown component key at render time: {component_key}"
            )
        resolved[family_key] = ResolvedAppearanceComponent(
            family=family,
            component=component,
            implementation=resolve_component_implementation(component),
        )
    return ResolvedStoreAppearance(
        version_id=version_id,
        manifest=manifest,
        components=resolved,
    )


def resolve_store_appearance_render_state(version) -> ResolvedStoreAppearance:
    """Resolve stable manifest identities for one concrete Draft/Published version.

    ``load_store_appearance_manifest`` already provides the critical read-time
    distinction required by A7: valid pre-engine selectors are adapted to
    stable component identities, unknown legacy selectors fall back safely,
    while malformed *new* persisted manifest state raises instead of being
    silently hidden. Registry implementations are then resolved only from
    platform-owned symbolic references; no merchant-supplied renderer path is
    ever evaluated here.
    """

    if version.pk is None:
        raise ValueError("Store Appearance rendering requires a saved layout version")

    manifest = load_store_appearance_manifest(version)
    return resolve_store_appearance_manifest_state(manifest, version_id=version.pk)


def global_renderer_template(
    state: ResolvedStoreAppearance,
    family_key: str,
    legacy_config: Mapping[str, object] | None = None,
) -> str:
    """Return a trusted Django template path for a global-region family.

    During the A7 transition, a family's Store Appearance safe default means
    "preserve the pre-engine selector already stored on this same Version".
    This keeps the existing Header/Footer editors and older Ready Templates
    visually stable while the new engine is introduced.  A non-default
    Manifest selection is explicit and therefore authoritative.  In both
    cases the renderer path comes only from the Python registry.
    """

    resolved = state.component(family_key)
    if resolved.family.renderer_role != "global_region":
        raise InvalidStoreAppearanceContract(
            f"{family_key} is not a global-region appearance family"
        )

    implementation = resolved.implementation
    if not isinstance(implementation, GlobalVariantDefinition):
        raise InvalidStoreAppearanceContract(
            f"{family_key} does not resolve to a renderable global-region variant"
        )

    if resolved.component.key == resolved.family.safe_default_component_key:
        region = _GLOBAL_REGION_BY_FAMILY.get(family_key)
        if region is None:
            raise InvalidStoreAppearanceContract(
                f"{family_key} has no trusted global-region adapter"
            )
        return global_region_registry.resolve_global_renderer_template(
            region, dict(legacy_config or {})
        )

    return implementation.renderer


def card_settings_for(state: ResolvedStoreAppearance) -> dict[str, str]:
    """Return the selected card's bounded in-memory settings overlay."""

    resolved = state.component("card")
    if resolved.component.key == resolved.family.safe_default_component_key:
        return {}
    if not resolved.component.registry_reference.startswith("card_style:"):
        raise InvalidStoreAppearanceContract(
            f"{resolved.component.key} does not resolve to a card style"
        )
    return {"card_style": str(resolved.implementation)}


def badge_settings_for(state: ResolvedStoreAppearance) -> dict[str, str]:
    """Return the selected badge's bounded in-memory settings overlay."""

    resolved = state.component("badge")
    if resolved.component.key == resolved.family.safe_default_component_key:
        return {}
    if not resolved.component.registry_reference.startswith("badge_treatment:"):
        raise InvalidStoreAppearanceContract(
            f"{resolved.component.key} does not resolve to a badge treatment"
        )
    return {"badge_treatment": str(resolved.implementation)}


@dataclasses.dataclass(frozen=True)
class ThemeOverlayState:
    """P5-W2 — the ONE resolved occasion Theme, resolved once through the
    canonical ``resolve_store_appearance_manifest_state`` and consumed
    identically by the storefront shell (global chrome) and page sections.

    Consumers read THIS; they never re-read the manifest and never
    independently look up the theme. ``css_variables`` are platform-owned,
    bounded, and derived only from the ``theme_catalog`` entry plus the
    validated intensity — never from any merchant-provided raw value.
    """

    occasion_key: str
    component_key: str
    tone: str
    intensity: str
    label_fa: str
    css_variables: Mapping[str, str]
    is_active: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "css_variables", MappingProxyType(dict(self.css_variables))
        )


def theme_overlay_state(state: ResolvedStoreAppearance) -> ThemeOverlayState:
    """Resolve the single active occasion Theme from the already-resolved
    appearance state. ``theme.none.v1`` is a true no-op (``is_active=False``,
    no decoration). Intensity comes from ``manifest.settings["theme"]``.
    """

    from ..theme_catalog import (
        DEFAULT_THEME_INTENSITY,
        accent_soft_mix_for,
        get_theme_occasion_by_component_key,
        motif_opacity_for,
    )

    resolved = state.component("theme")
    if resolved.family.renderer_role != "appearance_token":
        raise InvalidStoreAppearanceContract("theme is not an appearance-token family")

    occasion = resolved.implementation
    # ``resolve_component_implementation`` returns the ThemeOccasion catalog
    # entry for a theme component. Guard defensively.
    component_key = resolved.component.key
    if getattr(occasion, "component_key", None) != component_key:
        occasion = get_theme_occasion_by_component_key(component_key)

    # Intensity is a bounded, validated per-family setting.
    theme_settings = state.manifest.settings.get("theme", {})
    intensity = theme_settings.get("intensity", DEFAULT_THEME_INTENSITY)

    if occasion.is_noop:
        return ThemeOverlayState(
            occasion_key="none",
            component_key=component_key,
            tone=occasion.tone,
            intensity=intensity,
            label_fa=occasion.label_fa,
            css_variables={},
            is_active=False,
        )

    css_variables = {
        "--occasion-accent": occasion.accent,
        "--occasion-accent-soft": occasion.accent_soft,
        "--occasion-motif-opacity": motif_opacity_for(intensity),
        "--occasion-accent-mix": accent_soft_mix_for(intensity),
    }
    return ThemeOverlayState(
        occasion_key=occasion.occasion_key,
        component_key=component_key,
        tone=occasion.tone,
        intensity=intensity,
        label_fa=occasion.label_fa,
        css_variables=css_variables,
        is_active=True,
    )


def section_variant_for(
    state: ResolvedStoreAppearance,
    section_key: str,
) -> VariantDefinition | None:
    """Return the selected registered Variant for ``section_key`` when explicit.

    The foundation ``*.legacy_default.v1`` selections intentionally mean
    "preserve the existing section-local runtime behavior".  This is what lets
    A7 attach the new manifest to old Ready Templates without visually
    rewriting their already-persisted ``hero_style``/``display_mode`` values.
    A non-default component selection, however, is an explicit Design Engine
    choice and overrides that one registered variant at render time only.
    """

    matches: list[VariantDefinition] = []
    for resolved in state.components.values():
        if resolved.family.renderer_role != "section_variant":
            continue
        if resolved.component.key == resolved.family.safe_default_component_key:
            continue
        prefix = f"section_variant:{section_key}:"
        if not resolved.component.registry_reference.startswith(prefix):
            continue
        if not isinstance(resolved.implementation, VariantDefinition):
            raise InvalidStoreAppearanceContract(
                f"{resolved.component.key} does not resolve to a section variant"
            )
        matches.append(resolved.implementation)

    if len(matches) > 1:
        raise InvalidStoreAppearanceContract(
            f"multiple Store Appearance variants target section {section_key}"
        )
    return matches[0] if matches else None
