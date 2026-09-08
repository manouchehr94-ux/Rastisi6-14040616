"""R4 Task 9 — ResourceSource: one shared, typed contract for how a Section
selects the Product/Brand/Category/Collection resources it displays.

Pure domain module: no database access, no Django Model import. Deliberately
does NOT import ``settings_schema.py`` or ``section_registry.py`` — those
import THIS module (never the other way around), so there is no circular
import between the schema/registry layers and this contract.

Two independent things live here:

- ``ResourceSource`` itself — a typed, JSON-serializable value with its own
  invariants, entirely independent of any specific Section type.
- Pure compatibility adapters that translate the CURRENT legacy persisted
  shapes (``product_section``'s ``data_source``/``source_id``/``product_ids``,
  ``brand_carousel``'s ``brand_ids``) to/from ``ResourceSource`` — no
  persisted key is ever renamed by Task 9; ``ResourceSource`` is a Phase 1
  in-memory/Inspector-facing contract layered ON TOP of the existing storage
  shape, not a replacement for it.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Mapping


class ResourceSourceError(ValueError):
    """Invalid ResourceSource construction, (de)serialization, or
    section-compatibility — a stable, safe-to-surface message."""


ALLOWED_KINDS = ("product", "category", "brand", "collection")
ALLOWED_MODES = ("auto", "manual")

#: Reuse of the CURRENT system's manual-ID caps — never invented/enlarged
#: here (see section_registry.py: _MAX_MANUAL_PRODUCT_IDS=60,
#: _MAX_BRAND_CAROUSEL_IDS=24, category/collection multi-select caps=12).
_MANUAL_ID_CAPS = {
    "product": 60,
    "brand": 24,
    "category": 12,
    "collection": 12,
}

#: The TYPED contract's own semantic auto-rule names — never the legacy
#: persisted words ("category"/"brand"/"collection") the compatibility
#: adapters translate to/from.
_PRODUCT_AUTO_RULES_NO_PARAMS = frozenset({"newest", "discounted", "best_sellers", "most_viewed"})
_PRODUCT_AUTO_RULES_WITH_SOURCE_ID = frozenset({"by_category", "by_brand", "by_collection"})
_PRODUCT_AUTO_RULES = _PRODUCT_AUTO_RULES_NO_PARAMS | _PRODUCT_AUTO_RULES_WITH_SOURCE_ID

#: Brand's current system can resolve exactly one automatic behaviour.
_BRAND_AUTO_RULES = frozenset({"all_active"})
#: Category/Collection are not exposed by the R4 Task 9/10 UI yet, but their
#: existing universal-selection behaviour also supports "empty IDs means
#: every active/current Store resource" — the contract lists them as valid
#: kinds and allows the same single rule, never inventing anything beyond it.
_CATEGORY_AUTO_RULES = frozenset({"all_active"})
_COLLECTION_AUTO_RULES = frozenset({"all_active"})

_AUTO_RULES_BY_KIND = {
    "product": _PRODUCT_AUTO_RULES,
    "brand": _BRAND_AUTO_RULES,
    "category": _CATEGORY_AUTO_RULES,
    "collection": _COLLECTION_AUTO_RULES,
}


def manual_id_limit(kind: str) -> int:
    """The existing, already-authoritative manual-ID cap for ``kind`` — a
    tiny public accessor so Task 10's Picker never re-invents/duplicates
    ``_MANUAL_ID_CAPS`` (never enlarges it either)."""
    if kind not in ALLOWED_KINDS:
        raise ResourceSourceError(f"unsupported kind {kind!r} (allowed: {list(ALLOWED_KINDS)!r})")
    return _MANUAL_ID_CAPS[kind]


def _is_strict_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _clean_manual_ids(raw_ids, *, kind: str) -> tuple[int, ...]:
    cap = _MANUAL_ID_CAPS[kind]
    cleaned: list[int] = []
    seen: set[int] = set()
    for value in raw_ids:
        if not _is_strict_positive_int(value):
            raise ResourceSourceError(f"manual id must be a strict positive integer (got {value!r})")
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if len(cleaned) > cap:
        raise ResourceSourceError(f"manual_ids exceeds the maximum of {cap} for kind {kind!r}")
    return tuple(cleaned)


def _clean_auto_parameters(raw_parameters: Mapping, *, kind: str, auto_rule: str) -> dict:
    # Runtime container type is already validated by the caller
    # (ResourceSource.__post_init__) before this is called — this only
    # does the per-rule semantic cleaning (allowed keys / required values).
    if kind == "product" and auto_rule in _PRODUCT_AUTO_RULES_WITH_SOURCE_ID:
        unknown = set(raw_parameters) - {"source_id"}
        if unknown:
            raise ResourceSourceError(f"unknown auto_parameters key(s): {sorted(unknown)!r}")
        if "source_id" not in raw_parameters:
            raise ResourceSourceError(f"auto_rule {auto_rule!r} requires a source_id parameter")
        source_id = raw_parameters["source_id"]
        if not _is_strict_positive_int(source_id):
            raise ResourceSourceError("source_id must be a strict positive integer")
        return {"source_id": source_id}
    # Every other allowed auto_rule (product's ID-free rules, and every
    # brand/category/collection rule) takes no parameters at all.
    if raw_parameters:
        raise ResourceSourceError(f"auto_rule {auto_rule!r} does not accept any parameters")
    return {}


@dataclasses.dataclass(frozen=True)
class ResourceSource:
    kind: str
    mode: str
    auto_rule: str | None = None
    auto_parameters: Mapping[str, object] = dataclasses.field(default_factory=dict)
    manual_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_KINDS:
            raise ResourceSourceError(f"unsupported kind {self.kind!r} (allowed: {list(ALLOWED_KINDS)!r})")
        if self.mode not in ALLOWED_MODES:
            raise ResourceSourceError(f"unsupported mode {self.mode!r} (allowed: {list(ALLOWED_MODES)!r})")

        # Runtime container type must be validated BEFORE any coercion — a
        # falsey-but-wrong-type value (0, "", [], {}) must never silently
        # become the valid empty structure for the other field. A string is
        # deliberately excluded even though it is iterable (``tuple("73")``
        # would silently become ('7', '3')), and a Mapping is never accepted
        # as a stand-in for manual_ids.
        if not isinstance(self.auto_parameters, Mapping):
            raise ResourceSourceError(
                f"auto_parameters must be a mapping (got {type(self.auto_parameters).__name__})"
            )
        if not isinstance(self.manual_ids, (list, tuple)):
            raise ResourceSourceError(
                f"manual_ids must be a list or tuple (got {type(self.manual_ids).__name__})"
            )

        # Defensive copies — never retain a caller-owned mutable structure;
        # a list/dict the caller mutates afterward must never mutate this
        # (frozen, but auto_parameters/manual_ids would otherwise alias it).
        manual_ids = tuple(self.manual_ids)
        auto_parameters = dict(self.auto_parameters)

        if self.mode == "manual":
            if self.auto_rule is not None:
                raise ResourceSourceError("mode='manual' must not set auto_rule")
            if auto_parameters:
                raise ResourceSourceError("mode='manual' must not set auto_parameters")
            manual_ids = _clean_manual_ids(manual_ids, kind=self.kind)
            if not manual_ids:
                raise ResourceSourceError("mode='manual' requires at least one selected id")
        else:  # mode == "auto"
            if manual_ids:
                raise ResourceSourceError("mode='auto' must not set manual_ids")
            allowed_rules = _AUTO_RULES_BY_KIND[self.kind]
            if self.auto_rule not in allowed_rules:
                raise ResourceSourceError(
                    f"auto_rule {self.auto_rule!r} is not valid for kind {self.kind!r} "
                    f"(allowed: {sorted(allowed_rules)!r})"
                )
            auto_parameters = _clean_auto_parameters(auto_parameters, kind=self.kind, auto_rule=self.auto_rule)
            manual_ids = ()

        object.__setattr__(self, "manual_ids", manual_ids)
        # A frozen dataclass still lets a mutable dict be mutated THROUGH
        # the attribute (``source.auto_parameters["x"] = ...``) — wrap it in
        # a genuinely read-only view so the value contract holds all the
        # way through. serialize_resource_source() still produces a plain
        # JSON-safe dict via ``dict(source.auto_parameters)``.
        object.__setattr__(self, "auto_parameters", MappingProxyType(auto_parameters))


# --------------------------------------------------------------- serialization

_SERIALIZED_KEYS = frozenset({"kind", "mode", "auto_rule", "auto_parameters", "manual_ids"})


def serialize_resource_source(source: ResourceSource) -> dict:
    """Deterministic, JSON-safe shape. ``manual_ids`` serializes as a JSON
    array; round-tripping through ``deserialize_resource_source`` preserves
    semantics and ordered IDs."""
    return {
        "kind": source.kind,
        "mode": source.mode,
        "auto_rule": source.auto_rule,
        "auto_parameters": dict(source.auto_parameters),
        "manual_ids": list(source.manual_ids),
    }


def deserialize_resource_source(raw: object) -> ResourceSource:
    if not isinstance(raw, Mapping):
        raise ResourceSourceError("resource_source must be an object")
    unknown = set(raw) - _SERIALIZED_KEYS
    if unknown:
        raise ResourceSourceError(f"unknown resource_source key(s): {sorted(unknown)!r}")

    kind = raw.get("kind")
    if not isinstance(kind, str):
        raise ResourceSourceError("kind must be a string")
    mode = raw.get("mode")
    if not isinstance(mode, str):
        raise ResourceSourceError("mode must be a string")
    auto_rule = raw.get("auto_rule")
    if auto_rule is not None and not isinstance(auto_rule, str):
        raise ResourceSourceError("auto_rule must be a string or null")

    # A MISSING key legitimately defaults to the empty structure; a
    # PRESENT-but-wrong-type value (including a falsey one — 0, "", [], {},
    # explicit null) must be rejected outright, never silently coerced —
    # falsiness must never change a value's runtime type contract.
    if "auto_parameters" in raw:
        auto_parameters = raw["auto_parameters"]
        if not isinstance(auto_parameters, Mapping):
            raise ResourceSourceError(
                f"auto_parameters must be an object (got {type(auto_parameters).__name__})"
            )
    else:
        auto_parameters = {}

    if "manual_ids" in raw:
        manual_ids_raw = raw["manual_ids"]
        if not isinstance(manual_ids_raw, (list, tuple)):
            raise ResourceSourceError(
                f"manual_ids must be an array (got {type(manual_ids_raw).__name__})"
            )
    else:
        manual_ids_raw = []

    return ResourceSource(
        kind=kind, mode=mode, auto_rule=auto_rule,
        auto_parameters=auto_parameters, manual_ids=tuple(manual_ids_raw),
    )


# -------------------------------------------------- Product compatibility

#: Legacy `data_source` -> typed auto_rule for the three single-reference
#: sources; every other value maps to itself (already the typed name for
#: product's four ID-free auto rules).
_PRODUCT_LEGACY_SINGLE_REFERENCE_TO_AUTO_RULE = {
    "category": "by_category",
    "brand": "by_brand",
    "collection": "by_collection",
}
_PRODUCT_AUTO_RULE_TO_LEGACY_SINGLE_REFERENCE = {
    value: key for key, value in _PRODUCT_LEGACY_SINGLE_REFERENCE_TO_AUTO_RULE.items()
}


def product_resource_source_from_settings(settings: Mapping) -> ResourceSource:
    settings = settings or {}
    data_source = settings.get("data_source")
    if data_source == "manual":
        return ResourceSource(
            kind="product", mode="manual", manual_ids=tuple(settings.get("product_ids") or ()),
        )
    if data_source in _PRODUCT_LEGACY_SINGLE_REFERENCE_TO_AUTO_RULE:
        return ResourceSource(
            kind="product", mode="auto",
            auto_rule=_PRODUCT_LEGACY_SINGLE_REFERENCE_TO_AUTO_RULE[data_source],
            auto_parameters={"source_id": settings.get("source_id")},
        )
    if data_source in _PRODUCT_AUTO_RULES_NO_PARAMS:
        return ResourceSource(kind="product", mode="auto", auto_rule=data_source)
    raise ResourceSourceError(f"unsupported legacy product data_source {data_source!r}")


def product_resource_source_to_legacy_patch(source: ResourceSource) -> dict:
    if source.kind != "product":
        raise ResourceSourceError(f"expected kind='product', got {source.kind!r}")
    if source.mode == "manual":
        return {"data_source": "manual", "source_id": None, "product_ids": list(source.manual_ids)}
    if source.auto_rule in _PRODUCT_AUTO_RULE_TO_LEGACY_SINGLE_REFERENCE:
        return {
            "data_source": _PRODUCT_AUTO_RULE_TO_LEGACY_SINGLE_REFERENCE[source.auto_rule],
            "source_id": source.auto_parameters["source_id"],
            "product_ids": [],
        }
    if source.auto_rule in _PRODUCT_AUTO_RULES_NO_PARAMS:
        return {"data_source": source.auto_rule, "source_id": None, "product_ids": []}
    raise ResourceSourceError(f"unsupported product auto_rule {source.auto_rule!r}")


# ---------------------------------------------------- Brand compatibility

def brand_resource_source_from_settings(settings: Mapping) -> ResourceSource:
    settings = settings or {}
    brand_ids = settings.get("brand_ids") or []
    if brand_ids:
        return ResourceSource(kind="brand", mode="manual", manual_ids=tuple(brand_ids))
    return ResourceSource(kind="brand", mode="auto", auto_rule="all_active")


def brand_resource_source_to_legacy_patch(source: ResourceSource) -> dict:
    if source.kind != "brand":
        raise ResourceSourceError(f"expected kind='brand', got {source.kind!r}")
    if source.mode == "manual":
        return {"brand_ids": list(source.manual_ids)}
    if source.auto_rule == "all_active":
        return {"brand_ids": []}
    raise ResourceSourceError(f"unsupported brand auto_rule {source.auto_rule!r}")


# -------------------------------------------------- Category compatibility

def category_resource_source_from_settings(settings: Mapping) -> ResourceSource:
    settings = settings or {}
    category_ids = settings.get("category_ids") or []
    if category_ids:
        return ResourceSource(kind="category", mode="manual", manual_ids=tuple(category_ids))
    return ResourceSource(kind="category", mode="auto", auto_rule="all_active")


def category_resource_source_to_legacy_patch(source: ResourceSource) -> dict:
    if source.kind != "category":
        raise ResourceSourceError(f"expected kind='category', got {source.kind!r}")
    if source.mode == "manual":
        return {"category_ids": list(source.manual_ids)}
    if source.auto_rule == "all_active":
        return {"category_ids": []}
    raise ResourceSourceError(f"unsupported category auto_rule {source.auto_rule!r}")


# ----------------------------------------------- Collection compatibility

def collection_resource_source_from_settings(settings: Mapping) -> ResourceSource:
    settings = settings or {}
    collection_ids = settings.get("collection_ids") or []
    if collection_ids:
        return ResourceSource(kind="collection", mode="manual", manual_ids=tuple(collection_ids))
    return ResourceSource(kind="collection", mode="auto", auto_rule="all_active")


def collection_resource_source_to_legacy_patch(source: ResourceSource) -> dict:
    if source.kind != "collection":
        raise ResourceSourceError(f"expected kind='collection', got {source.kind!r}")
    if source.mode == "manual":
        return {"collection_ids": list(source.manual_ids)}
    if source.auto_rule == "all_active":
        return {"collection_ids": []}
    raise ResourceSourceError(f"unsupported collection auto_rule {source.auto_rule!r}")


# --------------------------------------------- generic Section adapter router
#
# A fixed allowlist, no dynamic import/getattr, no database — reusable by
# Task 10's Resource Picker without duplicating this routing.

_SECTION_ADAPTERS: dict[str, dict] = {
    "product_section": {
        "kind": "product",
        "from_settings": product_resource_source_from_settings,
        "to_legacy_patch": product_resource_source_to_legacy_patch,
    },
    "brand_carousel": {
        "kind": "brand",
        "from_settings": brand_resource_source_from_settings,
        "to_legacy_patch": brand_resource_source_to_legacy_patch,
    },
    "collection_tiles": {
        "kind": "collection",
        "from_settings": collection_resource_source_from_settings,
        "to_legacy_patch": collection_resource_source_to_legacy_patch,
    },
    "category_grid": {
        "kind": "category",
        "from_settings": category_resource_source_from_settings,
        "to_legacy_patch": category_resource_source_to_legacy_patch,
    },
}


def resource_source_from_section_settings(section_key: str, settings: Mapping) -> ResourceSource:
    entry = _SECTION_ADAPTERS.get(section_key)
    if entry is None:
        raise ResourceSourceError(f"unsupported section_key {section_key!r}")
    return entry["from_settings"](settings)


def resource_source_to_legacy_patch(section_key: str, source: ResourceSource) -> dict:
    entry = _SECTION_ADAPTERS.get(section_key)
    if entry is None:
        raise ResourceSourceError(f"unsupported section_key {section_key!r}")
    if source.kind != entry["kind"]:
        raise ResourceSourceError(
            f"resource_source kind {source.kind!r} is not compatible with section {section_key!r} "
            f"(expected {entry['kind']!r})"
        )
    return entry["to_legacy_patch"](source)
