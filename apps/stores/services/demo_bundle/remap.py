"""Deterministic, collision-free renumbering of one source store's rows.

Two independent databases both start their auto-increment keys at 1, so their
rows collide. Studio settings, however, reference products, categories, menus,
media assets ... by *number*, so renumbering rows without rewriting every one
of those references silently breaks the design.

Strategy: every source ``k`` gets ONE uniform offset ``k * stride`` where
``stride`` is a power of ten above the largest key of any source. Then

* ``new_pk = old_pk + offset`` for every row;
* every foreign key / many-to-many value to a bundle row gets the same shift;
* inside Studio JSON, every value that *is* an id (see ``SCALAR_ID_KEYS``,
  ``LIST_ID_KEYS`` and the context rules below) gets the same shift;
* ``ProductVariant.combination_key`` (``"12-45"`` = sorted option-value ids)
  is rebuilt from the shifted ids.

Because the shift is uniform and model-independent the mapping never needs to
know whether the referenced row exists, so a dangling reference stays dangling
(exactly as in the source) instead of being re-pointed at another row.

Any id-looking key that this module does not understand makes the conversion
FAIL loudly (``UnmappedReference``) instead of being left stale; the operator
can declare it with ``extra_ref_keys`` / ``ignore_keys``.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from .files import model_for

#: Studio JSON keys that hold ONE id of another bundle row.
SCALAR_ID_KEYS = frozenset({
    "menu_id", "media_asset_id", "image_media_asset_id", "campaign_media_asset_id",
    "desktop_asset_id", "mobile_asset_id", "image_asset_id", "content_page_id",
})
#: Studio JSON keys that hold a LIST of ids.
LIST_ID_KEYS = frozenset({"product_ids", "category_ids", "brand_ids", "collection_ids"})

#: ``destination_id`` is an id only for these ``destination_type`` values.
DESTINATION_REFERENCE_TYPES = frozenset({"category", "product", "brand", "collection"})
#: ``source_id`` next to a legacy ``data_source`` is an id only for these values ...
LEGACY_SOURCE_REFERENCE_TYPES = frozenset({"category", "brand", "collection"})
#: ... and inside typed ``source.auto_parameters`` only for these ``auto_rule`` values.
TYPED_AUTO_RULES_WITH_ID = frozenset({"by_category", "by_brand", "by_collection"})
#: typed resource sources (``kind``) whose ``manual_ids`` are ids.
TYPED_SOURCE_KINDS = frozenset({"product", "brand", "category", "collection"})

_ID_LIKE = re.compile(r"(^|_)ids?$")

#: Models/fields whose JSON is Studio configuration and is therefore remapped.
JSON_FIELDS: dict[str, tuple[str, ...]] = {
    "storefront_builder.storefrontlayoutversion": (
        "header_config", "footer_config", "appearance_config", "template_provenance", "template_baseline_snapshot",
    ),
    "storefront_builder.storefrontpage": ("page_appearance_overrides",),
    "storefront_builder.storefrontsection": ("settings",),
    "storefront_builder.storefrontcontainer": ("settings",),
    "storefront_builder.storefrontcell": ("settings",),
}
COMBINATION_KEY = ("catalog.productvariant", "combination_key")


class RemapError(Exception):
    pass


class UnmappedReference(RemapError):
    """Id-looking JSON keys that are neither known nor explicitly ignored."""

    def __init__(self, paths: list[str]):
        super().__init__(
            "unmapped id-like key(s) in Studio JSON - declare each with --map-json-key KEY or --ignore-json-key KEY:\n  "
            + "\n  ".join(paths[:30])
        )
        self.paths = paths


@dataclass
class RemapOptions:
    extra_scalar_keys: frozenset[str] = frozenset()
    extra_list_keys: frozenset[str] = frozenset()
    ignore_keys: frozenset[str] = frozenset()


@dataclass
class RemapStats:
    offset: int = 0
    rows: int = 0
    fk_values: int = 0
    m2m_values: int = 0
    json_refs: dict[str, int] = field(default_factory=dict)
    combination_keys: int = 0
    warnings: list[str] = field(default_factory=list)


def plan_stride(max_pks: list[int]) -> int:
    """Smallest power of ten strictly above the largest key of any source (>= 10**6).

    10**6 keeps shifted ids visually distinct from small legitimate numbers
    (quantities, ratings) while staying far below the 2**31 limit of an integer key.
    """
    top = max([1000, *max_pks])
    stride = 1_000_000
    while stride <= top:
        stride *= 10
    return stride


#: target model of every id-bearing key (read side: used by the validator to resolve references)
_SCALAR_TARGET = {
    "menu_id": "content.Menu", "media_asset_id": "content.MediaAsset", "image_media_asset_id": "content.MediaAsset",
    "campaign_media_asset_id": "content.MediaAsset", "desktop_asset_id": "content.MediaAsset",
    "mobile_asset_id": "content.MediaAsset", "image_asset_id": "content.MediaAsset", "content_page_id": "content.ContentPage",
}
_LIST_TARGET = {
    "product_ids": "catalog.Product", "category_ids": "catalog.Category", "brand_ids": "catalog.Brand",
    "collection_ids": "catalog.MerchantCollection",
}
_TYPE_TARGET = {
    "product": "catalog.Product", "category": "catalog.Category", "brand": "catalog.Brand",
    "collection": "catalog.MerchantCollection",
    "by_category": "catalog.Category", "by_brand": "catalog.Brand", "by_collection": "catalog.MerchantCollection",
}


def json_refs(node, ancestors: tuple = ()):
    """Yield ``(json key, target model label, referenced pk)`` for every id in a Studio JSON blob.

    The read-only twin of the remapper: same keys, same context rules.
    """
    if isinstance(node, list):
        for item in node:
            yield from json_refs(item, ancestors)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        ids = value if isinstance(value, list) else [value]
        target = None
        if key in _SCALAR_TARGET:
            target = _SCALAR_TARGET[key]
        elif key in _LIST_TARGET:
            target = _LIST_TARGET[key]
        elif key == "destination_id" and node.get("destination_type") in DESTINATION_REFERENCE_TYPES:
            target = _TYPE_TARGET[node["destination_type"]]
        elif key == "source_id":
            if node.get("data_source") in LEGACY_SOURCE_REFERENCE_TYPES:
                target = _TYPE_TARGET[node["data_source"]]
            else:
                for anc in (node, *ancestors):
                    if isinstance(anc, dict) and anc.get("auto_rule") in TYPED_AUTO_RULES_WITH_ID:
                        target = _TYPE_TARGET[anc["auto_rule"]]
                        break
        elif key == "manual_ids" and node.get("kind") in TYPED_SOURCE_KINDS:
            target = _TYPE_TARGET[node["kind"]]
        if target is not None:
            for item in ids:
                if _is_id_int(item):
                    yield key, target, item
                elif isinstance(item, str) and item.isdigit() and int(item) > 0:
                    yield key, target, int(item)
        elif isinstance(value, (dict, list)):
            yield from json_refs(value, (node, *ancestors))


def _is_id_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _shift_scalar(value, offset: int):
    if _is_id_int(value):
        return value + offset
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return str(int(value) + offset)
    return value


def _shift_list(value, offset: int):
    if isinstance(value, list):
        return [_shift_scalar(v, offset) for v in value]
    return _shift_scalar(value, offset)


class _JsonRemapper:
    def __init__(self, offset: int, options: RemapOptions, stats: RemapStats):
        self.offset, self.options, self.stats = offset, options, stats
        self.unmapped: list[str] = []
        self.scalar_keys = SCALAR_ID_KEYS | options.extra_scalar_keys
        self.list_keys = LIST_ID_KEYS | options.extra_list_keys

    def _count(self, key: str, n: int = 1) -> None:
        self.stats.json_refs[key] = self.stats.json_refs.get(key, 0) + n

    def walk(self, node, path: str, ancestors: tuple):
        if isinstance(node, dict):
            return {k: self._value(k, v, node, f"{path}.{k}", ancestors) for k, v in node.items()}
        if isinstance(node, list):
            return [self.walk(v, f"{path}[]", ancestors) for v in node]
        return node

    def _value(self, key, value, parent: dict, path: str, ancestors: tuple):
        if key in self.options.ignore_keys:
            return value
        if key in self.scalar_keys:
            new = _shift_scalar(value, self.offset)
            if new != value:
                self._count(key)
            return new
        if key in self.list_keys:
            new = _shift_list(value, self.offset)
            if new != value:
                self._count(key, len(value) if isinstance(value, list) else 1)
            return new
        if key == "destination_id":
            if parent.get("destination_type") in DESTINATION_REFERENCE_TYPES:
                new = _shift_scalar(value, self.offset)
                if new != value:
                    self._count("destination_id")
                return new
            if _is_id_int(value):
                self.stats.warnings.append(f"{path}: destination_id={value} with non-reference destination_type left unchanged")
            return value
        if key == "source_id":
            chain = (parent, *ancestors)
            legacy = parent.get("data_source") in LEGACY_SOURCE_REFERENCE_TYPES
            typed = any(isinstance(a, dict) and a.get("auto_rule") in TYPED_AUTO_RULES_WITH_ID for a in chain)
            if legacy or typed:
                new = _shift_scalar(value, self.offset)
                if new != value:
                    self._count("source_id")
                return new
            if _is_id_int(value):
                self.stats.warnings.append(f"{path}: source_id={value} without a reference data_source/auto_rule left unchanged")
            return value
        if key == "manual_ids" and parent.get("kind") in TYPED_SOURCE_KINDS:
            new = _shift_list(value, self.offset)
            if new != value:
                self._count("manual_ids", len(value) if isinstance(value, list) else 1)
            return new
        if _ID_LIKE.search(key) and (
            _is_id_int(value) or (isinstance(value, list) and any(_is_id_int(v) for v in value))
        ):
            self.unmapped.append(f"{path} = {value!r}")
            return value
        if isinstance(value, (dict, list)):
            return self.walk(value, path, (parent, *ancestors))
        return value


def _model_fields(model):
    fks, m2ms = [], []
    for f in model._meta.concrete_fields:
        if f.is_relation and f.related_model._meta.label != "stores.Store":
            fks.append(f.name)
    for f in model._meta.many_to_many:
        m2ms.append(f.name)
    return fks, m2ms


def remap_records(records: list[dict], offset: int, options: RemapOptions | None = None) -> tuple[list[dict], RemapStats]:
    """Return ``(new_records, stats)``; the input is not modified."""
    options = options or RemapOptions()
    stats = RemapStats(offset=offset)
    out = copy.deepcopy(records)
    if offset == 0:
        stats.rows = len(out)
        _scan_only(out, options, stats)
        return out, stats

    jr = _JsonRemapper(offset, options, stats)
    cache: dict[str, tuple[list[str], list[str]]] = {}
    for rec in out:
        label = rec["model"]
        if label not in cache:
            cache[label] = _model_fields(model_for(label))
        fks, m2ms = cache[label]
        rec["pk"] = rec["pk"] + offset
        stats.rows += 1
        fields = rec["fields"]
        for name in fks:
            if fields.get(name) is not None:
                fields[name] = fields[name] + offset
                stats.fk_values += 1
        for name in m2ms:
            if fields.get(name):
                fields[name] = [v + offset for v in fields[name]]
                stats.m2m_values += len(fields[name])
        for name in JSON_FIELDS.get(label, ()):
            if name in fields:
                fields[name] = jr.walk(fields[name], f"{label}#{rec['pk'] - offset}.{name}", ())
        if label == COMBINATION_KEY[0] and fields.get(COMBINATION_KEY[1]):
            key = fields[COMBINATION_KEY[1]]
            parts = key.split("-")
            if all(p.isdigit() for p in parts):
                fields[COMBINATION_KEY[1]] = "-".join(str(int(p) + offset) for p in sorted(parts, key=int))
                stats.combination_keys += 1
            else:
                stats.warnings.append(f"{label}#{rec['pk'] - offset}: combination_key {key!r} is not an id list; kept")
    if jr.unmapped:
        raise UnmappedReference(jr.unmapped)
    _scan_metafields(out, stats)
    return out, stats


def _scan_only(records: list[dict], options: RemapOptions, stats: RemapStats) -> None:
    """Offset 0 keeps every number; still run the walker to detect unknown id keys early."""
    jr = _JsonRemapper(0, options, stats)
    for rec in records:
        for name in JSON_FIELDS.get(rec["model"], ()):
            if name in rec["fields"]:
                jr.walk(rec["fields"][name], f"{rec['model']}#{rec['pk']}.{name}", ())
    if jr.unmapped:
        raise UnmappedReference(jr.unmapped)
    _scan_metafields(records, stats)


def _scan_metafields(records: list[dict], stats: RemapStats) -> None:
    for rec in records:
        if rec["model"] == "catalog.productmetafield" and isinstance(rec["fields"].get("value_json"), (dict, list)):
            text = str(rec["fields"]["value_json"])
            if re.search(r"'[a-z_]*_ids?'\s*:", text):
                stats.warnings.append(
                    f"catalog.productmetafield#{rec['pk']}: value_json contains id-like keys; not remapped (free-form data)"
                )


def max_pk(records: list[dict]) -> int:
    return max((r["pk"] for r in records), default=0)


def assert_lossless(original: list[dict], remapped: list[dict], offset: int) -> list[str]:
    """Structural invariants of a remap. Returns a list of problems (empty = fine)."""
    problems: list[str] = []
    if len(original) != len(remapped):
        return [f"row count changed {len(original)} -> {len(remapped)}"]
    for a, b in zip(original, remapped):
        label = a["model"]
        if a["model"] != b["model"]:
            problems.append(f"model order changed at pk {a['pk']}")
            continue
        if b["pk"] != a["pk"] + offset:
            problems.append(f"{label}#{a['pk']}: pk {b['pk']} != {a['pk']}+{offset}")
        model = model_for(label)
        fks, m2ms = _model_fields(model)
        touched = set(fks) | set(m2ms) | set(JSON_FIELDS.get(label, ())) | (
            {COMBINATION_KEY[1]} if label == COMBINATION_KEY[0] else set()
        )
        if set(a["fields"]) != set(b["fields"]):
            problems.append(f"{label}#{a['pk']}: field set changed")
            continue
        for name, value in a["fields"].items():
            if name not in touched and b["fields"][name] != value:
                problems.append(f"{label}#{a['pk']}.{name}: value changed outside the id mapping")
    return problems
