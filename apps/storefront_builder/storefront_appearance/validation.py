"""Server-side validation boundary for persisted and transient manifests."""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Mapping

from .compatibility import (
    CompatibilityEvaluation,
    evaluate_manifest_compatibility,
)
from .contracts import (
    InvalidStoreAppearanceContract,
    StoreAppearanceManifest,
    validate_manifest_families,
)
from .families import COMPONENT_FAMILIES, DEFAULT_STORE_APPEARANCE_MANIFEST
from .registry import COMPONENT_REGISTRY


_TOP_LEVEL_KEYS = frozenset({"schema_version", "selections", "settings"})
_SETTING_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_TEXT_MARKERS = (
    "<script",
    "</script",
    "<style",
    "</style",
    "javascript:",
    "expression(",
    "{%",
    "{{",
)
_FORBIDDEN_SETTING_KEY_MARKERS = (
    "html",
    "css",
    "javascript",
    "renderer",
    "template",
    "path",
    "raw_json",
)
_MAX_STRING_LENGTH = 500
_MAX_COLLECTION_ITEMS = 64
_MAX_DEPTH = 8
_MAX_NODES = 256

# Component-family settings are introduced only through reviewed typed schemas.
# A closed empty set is intentional at foundation time: component selection is
# already useful, while arbitrary per-family payloads remain impossible.
ALLOWED_SETTINGS_BY_FAMILY = {
    family_key: frozenset() for family_key in COMPONENT_FAMILIES
}
# P5-W2 — the ONLY reviewed typed per-family setting: the Theme family's
# bounded ``intensity`` enum. No free-form theme settings, no arbitrary
# numeric intensity, no merchant-provided raw CSS.
if "theme" in ALLOWED_SETTINGS_BY_FAMILY:
    ALLOWED_SETTINGS_BY_FAMILY["theme"] = frozenset({"intensity"})


@dataclasses.dataclass(frozen=True)
class ValidatedStoreAppearance:
    manifest: StoreAppearanceManifest
    compatibility: CompatibilityEvaluation


def _validate_bounded_json_like(value, *, depth: int = 0, counter=None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_NODES:
        raise InvalidStoreAppearanceContract("settings exceed the maximum node count")
    if depth > _MAX_DEPTH:
        raise InvalidStoreAppearanceContract("settings exceed the maximum nesting depth")

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidStoreAppearanceContract("settings contain a non-finite number")
        return
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise InvalidStoreAppearanceContract("settings contain an oversized string")
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_TEXT_MARKERS):
            raise InvalidStoreAppearanceContract("settings contain forbidden executable markup")
        return
    if isinstance(value, Mapping):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise InvalidStoreAppearanceContract("settings mapping is oversized")
        for key, item in value.items():
            if not isinstance(key, str) or not _SETTING_KEY_RE.fullmatch(key):
                raise InvalidStoreAppearanceContract("settings contain an unsafe key")
            lowered_key = key.lower()
            if any(marker in lowered_key for marker in _FORBIDDEN_SETTING_KEY_MARKERS):
                raise InvalidStoreAppearanceContract("settings contain a forbidden free-form field")
            _validate_bounded_json_like(item, depth=depth + 1, counter=counter)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise InvalidStoreAppearanceContract("settings list is oversized")
        for item in value:
            _validate_bounded_json_like(item, depth=depth + 1, counter=counter)
        return
    raise InvalidStoreAppearanceContract("settings must contain bounded JSON-like values")


def _validate_typed_settings(settings: Mapping) -> None:
    _validate_bounded_json_like(settings)
    for family_key, family_settings in settings.items():
        if family_key not in COMPONENT_FAMILIES:
            raise InvalidStoreAppearanceContract(
                f"settings contain unknown family: {family_key}"
            )
        if not isinstance(family_settings, Mapping):
            raise InvalidStoreAppearanceContract(
                f"settings for {family_key} must be a mapping"
            )
        unknown = set(family_settings) - ALLOWED_SETTINGS_BY_FAMILY[family_key]
        if unknown:
            raise InvalidStoreAppearanceContract(
                f"unknown settings for {family_key}: {sorted(unknown)}"
            )
        # P5-W2 — typed value validation for the Theme intensity enum. Only the
        # bounded {subtle, balanced, strong} vocabulary is accepted; anything
        # else (arbitrary string, number, etc.) is rejected.
        if family_key == "theme" and "intensity" in family_settings:
            from ..theme_catalog import THEME_INTENSITY_CHOICES

            if family_settings["intensity"] not in THEME_INTENSITY_CHOICES:
                raise InvalidStoreAppearanceContract(
                    f"invalid theme intensity: {family_settings['intensity']!r}"
                )


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(_plain(item) for item in value)
    return value


def manifest_to_primitive(manifest: StoreAppearanceManifest) -> dict:
    return {
        "schema_version": manifest.schema_version,
        "selections": _plain(manifest.selections),
        "settings": _plain(manifest.settings),
    }


def validate_store_appearance_manifest(
    raw,
    *,
    require_complete: bool = True,
    base_manifest: StoreAppearanceManifest | None = None,
) -> ValidatedStoreAppearance:
    if not isinstance(raw, Mapping):
        raise InvalidStoreAppearanceContract("Store Appearance manifest must be a mapping")
    unknown_top_level = set(raw) - _TOP_LEVEL_KEYS
    if unknown_top_level:
        raise InvalidStoreAppearanceContract(
            f"unknown top-level manifest fields: {sorted(unknown_top_level)}"
        )

    schema_version = raw.get("schema_version")
    selections = raw.get("selections", {})
    settings = raw.get("settings", {})
    if not isinstance(selections, Mapping):
        raise InvalidStoreAppearanceContract("manifest selections must be a mapping")
    if not isinstance(settings, Mapping):
        raise InvalidStoreAppearanceContract("manifest settings must be a mapping")

    if base_manifest is not None:
        base = manifest_to_primitive(base_manifest)
        merged_selections = base["selections"]
        merged_selections.update(dict(selections))
        merged_settings = base["settings"]
        for family_key, family_settings in settings.items():
            current = merged_settings.get(family_key, {})
            if isinstance(current, Mapping) and isinstance(family_settings, Mapping):
                current = dict(current)
                current.update(dict(family_settings))
                merged_settings[family_key] = current
            else:
                merged_settings[family_key] = family_settings
        selections = merged_selections
        settings = merged_settings
        require_complete = True

    _validate_typed_settings(settings)
    manifest = StoreAppearanceManifest(
        schema_version=schema_version,
        selections=selections,
        settings=settings,
    )
    validate_manifest_families(
        manifest, COMPONENT_FAMILIES, require_complete=require_complete
    )

    for family_key, component_key in manifest.selections.items():
        component = COMPONENT_REGISTRY.get(component_key)
        if component is None:
            raise InvalidStoreAppearanceContract(f"unknown component key: {component_key}")
        if component.family_key != family_key:
            raise InvalidStoreAppearanceContract(
                f"component {component_key} does not belong to family {family_key}"
            )

    compatibility = evaluate_manifest_compatibility(
        manifest, COMPONENT_REGISTRY, COMPONENT_FAMILIES
    )
    if compatibility.hard_errors:
        raise InvalidStoreAppearanceContract(
            f"incompatible Store Appearance manifest: {compatibility.hard_errors}"
        )
    return ValidatedStoreAppearance(manifest=manifest, compatibility=compatibility)


def normalize_persisted_manifest(raw) -> StoreAppearanceManifest:
    """Give pre-engine Drafts exact safe defaults; reject malformed new state."""

    if raw is None or raw == {}:
        return DEFAULT_STORE_APPEARANCE_MANIFEST
    if not isinstance(raw, Mapping):
        raise InvalidStoreAppearanceContract("persisted Store Appearance must be a mapping")
    selections = raw.get("selections")
    settings = raw.get("settings")
    if selections == {} and (settings is None or settings == {}):
        return DEFAULT_STORE_APPEARANCE_MANIFEST
    return validate_store_appearance_manifest(
        raw,
        require_complete=False,
        base_manifest=DEFAULT_STORE_APPEARANCE_MANIFEST,
    ).manifest
