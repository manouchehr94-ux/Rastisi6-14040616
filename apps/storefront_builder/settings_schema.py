"""U— R4 Task 3: the declarative Settings Schema core.

A closed, JSON-safe field-type contract for section settings. This is a
Strangler boundary alongside the legacy ``SectionDefinition.validate_settings``
handwritten validators, not a replacement for them: ``clean_schema_patch``
only cleans the subset of keys a schema explicitly declares, and callers are
expected to run the result through the existing legacy validator afterwards
(see the architecture spec, Part V). No field type here allows arbitrary
merchant-controlled HTML/CSS/JS/template execution — ``rich_text`` is a
semantic field type whose actual sanitization remains the existing
sanitizer's job, not this module's.
"""

from __future__ import annotations

import dataclasses
import json

from . import appearance_registry, resource_source

ALLOWED_FIELD_TYPES = frozenset({
    "text",
    "textarea",
    "rich_text",
    "integer",
    "boolean",
    "choice",
    "color",
    "media",
    "variant",
    "resource_source",
    "appearance_override",
})

ALLOWED_GROUPS = frozenset({
    "basic",
    "advanced",
})

_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_digits(value: object) -> str:
    """Persian/Arabic-Indic → ASCII digit normalization, used by every
    server-side integer cleaning path. Server correctness must never depend
    on the browser having normalized digits first."""
    return str(value).translate(_DIGIT_TRANSLATION)


class SettingsSchemaError(ValueError):
    """Raised for schema-construction and patch-cleaning contract failures.

    Subclasses ``ValueError`` so existing ``assertRaises(ValueError, ...)``
    call sites (legacy validators, tests) remain compatible.
    """


@dataclasses.dataclass(frozen=True)
class SettingsField:
    key: str
    label: str
    field_type: str
    group: str
    default: object = None
    required: bool = False
    choices: tuple[tuple[str, str], ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    max_length: int | None = None
    widget_hint: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise SettingsSchemaError("Settings field key must not be empty")
        if self.field_type not in ALLOWED_FIELD_TYPES:
            raise SettingsSchemaError(
                f"Unsupported settings field_type {self.field_type!r} for key {self.key!r}"
            )
        if self.group not in ALLOWED_GROUPS:
            raise SettingsSchemaError(
                f"Unsupported settings group {self.group!r} for key {self.key!r}"
            )

        normalized_choices = []
        for pair in self.choices or ():
            pair = tuple(pair)
            if len(pair) != 2:
                raise SettingsSchemaError(
                    f"Malformed choice pair for {self.key!r}: {pair!r} (must be a 2-item pair)"
                )
            value, label = pair
            if not isinstance(value, str) or not isinstance(label, str):
                raise SettingsSchemaError(
                    f"Choice value/label for {self.key!r} must be strings (got {pair!r})"
                )
            normalized_choices.append(pair)
        object.__setattr__(self, "choices", tuple(normalized_choices))

        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise SettingsSchemaError(
                f"min_value {self.min_value} must be <= max_value {self.max_value} for {self.key!r}"
            )

        if self.max_length is not None and self.max_length < 0:
            raise SettingsSchemaError(f"max_length must not be negative for {self.key!r}")

        try:
            json.dumps(self.default)
        except TypeError as exc:
            raise SettingsSchemaError(
                f"default for {self.key!r} is not JSON-safe: {self.default!r}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class SettingsSchema:
    fields: tuple[SettingsField, ...]
    preserve_unmanaged: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields or ()))
        seen_keys: set[str] = set()
        for field in self.fields:
            if not isinstance(field, SettingsField):
                raise SettingsSchemaError(
                    f"SettingsSchema.fields must contain SettingsField instances (got {field!r})"
                )
            if field.key in seen_keys:
                raise SettingsSchemaError(f"Duplicate settings field key {field.key!r}")
            seen_keys.add(field.key)

    def get_field(self, key: str) -> SettingsField | None:
        for field in self.fields:
            if field.key == key:
                return field
        return None


_BOOLEAN_STRING_VALUES = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "on": True,
    "off": False,
}


def _clean_boolean_value(field: SettingsField, raw_value: object) -> bool:
    """Explicit boolean parsing — never Python truthiness. ``bool("false")``
    is ``True`` in Python, which is exactly the kind of surprise this must
    not reproduce for merchant-facing settings."""
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in _BOOLEAN_STRING_VALUES:
            return _BOOLEAN_STRING_VALUES[normalized]
    elif isinstance(raw_value, int):
        if raw_value == 1:
            return True
        if raw_value == 0:
            return False
    raise SettingsSchemaError(
        f"Invalid boolean value for {field.key!r}: {raw_value!r}"
    )


def _clean_field_value(field: SettingsField, raw_value: object) -> object:
    if field.field_type == "integer":
        try:
            cleaned = int(normalize_digits(raw_value))
        except (TypeError, ValueError) as exc:
            raise SettingsSchemaError(
                f"Invalid integer value for {field.key!r}: {raw_value!r}"
            ) from exc
        if field.min_value is not None and cleaned < field.min_value:
            raise SettingsSchemaError(
                f"{field.key!r} must be >= {field.min_value} (got {cleaned})"
            )
        if field.max_value is not None and cleaned > field.max_value:
            raise SettingsSchemaError(
                f"{field.key!r} must be <= {field.max_value} (got {cleaned})"
            )
        return cleaned

    if field.field_type == "boolean":
        return _clean_boolean_value(field, raw_value)

    if field.field_type == "choice":
        allowed_values = {value for value, _label in field.choices}
        if raw_value not in allowed_values:
            raise SettingsSchemaError(
                f"{field.key!r} must be one of {sorted(allowed_values)!r} (got {raw_value!r})"
            )
        return raw_value

    if field.field_type in ("text", "textarea", "rich_text"):
        cleaned = raw_value if isinstance(raw_value, str) else str(raw_value)
        if field.max_length is not None and len(cleaned) > field.max_length:
            raise SettingsSchemaError(
                f"{field.key!r} exceeds max_length {field.max_length} (got {len(cleaned)})"
            )
        return cleaned

    if field.field_type == "appearance_override":
        return validate_appearance_overrides(raw_value)

    if field.field_type == "resource_source":
        # R4 Task 9 — the generic typed shape only (kind/mode/auto_rule/
        # auto_parameters/manual_ids); THIS module has no notion of which
        # section owns the field, so it cannot check kind-compatibility or
        # translate to legacy persisted keys — that section-specific step
        # is section_registry.py's `_with_resource_source` wrapper, which
        # runs on this cleaned, JSON-safe serialized form.
        try:
            typed = resource_source.deserialize_resource_source(raw_value)
        except resource_source.ResourceSourceError as exc:
            raise SettingsSchemaError(str(exc)) from exc
        return resource_source.serialize_resource_source(typed)

    # color / media / variant: opaque, schema-declared but not type-coerced
    # yet — passed through unchanged for the legacy validator to
    # authoritatively check.
    return raw_value


#: R4 Task 7 — the only top-level appearance_overrides block Phase 1 supports.
_APPEARANCE_TYPOGRAPHY_KEYS = frozenset({"enabled", "font", "type_scale"})


def validate_appearance_overrides(raw: object) -> dict:
    """Typed server-side contract for the sparse ``appearance_overrides``
    section-settings block (Task 7 first slice: ``typography`` only).

    No free-form CSS/JSON is ever accepted — ``font``/``type_scale`` are
    checked against the existing curated ``appearance_registry`` allowlists,
    never a second/duplicated allowlist. Never mutates ``raw``.

    ``None``/``{}`` -> ``{}``. When ``typography.enabled`` is ``False``,
    the cleaned result is sparse (``{"typography": {"enabled": False}}``) —
    any stale ``font``/``type_scale`` in the input is dropped, never
    resolved/applied.
    """
    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, dict):
        raise SettingsSchemaError("appearance_overrides must be an object")

    unknown_top_keys = set(raw) - {"typography"}
    if unknown_top_keys:
        raise SettingsSchemaError(
            f"Unknown appearance_overrides key(s): {sorted(unknown_top_keys)!r}"
        )

    if "typography" not in raw:
        return {}

    typography_raw = raw["typography"]
    if not isinstance(typography_raw, dict):
        raise SettingsSchemaError("appearance_overrides.typography must be an object")

    unknown_typography_keys = set(typography_raw) - _APPEARANCE_TYPOGRAPHY_KEYS
    if unknown_typography_keys:
        raise SettingsSchemaError(
            f"Unknown typography key(s): {sorted(unknown_typography_keys)!r}"
        )

    if "enabled" not in typography_raw:
        raise SettingsSchemaError("appearance_overrides.typography.enabled is required")
    enabled = typography_raw["enabled"]
    if not isinstance(enabled, bool):
        raise SettingsSchemaError("appearance_overrides.typography.enabled must be a boolean")

    if not enabled:
        return {"typography": {"enabled": False}}

    cleaned_typography = {"enabled": True}
    if "font" in typography_raw:
        font = typography_raw["font"]
        if font not in appearance_registry.FONT_CHOICES:
            raise SettingsSchemaError(
                f"appearance_overrides.typography.font must be one of "
                f"{list(appearance_registry.FONT_CHOICES)!r} (got {font!r})"
            )
        cleaned_typography["font"] = font
    if "type_scale" in typography_raw:
        type_scale = typography_raw["type_scale"]
        if type_scale not in appearance_registry.TYPE_SCALE_CHOICES:
            raise SettingsSchemaError(
                f"appearance_overrides.typography.type_scale must be one of "
                f"{list(appearance_registry.TYPE_SCALE_CHOICES)!r} (got {type_scale!r})"
            )
        cleaned_typography["type_scale"] = type_scale

    return {"typography": cleaned_typography}


def clean_schema_patch(schema: SettingsSchema, raw_patch: dict, current_settings: dict) -> dict:
    """Clean only the schema-declared keys present in ``raw_patch`` and
    merge them into (a copy of) ``current_settings``. Never mutates either
    input. Unknown keys in ``raw_patch`` are always rejected — regardless
    of ``preserve_unmanaged``, which only governs whether *existing*
    undeclared keys already in ``current_settings`` survive the merge."""
    declared_keys = {field.key for field in schema.fields}
    unknown_keys = set(raw_patch) - declared_keys
    if unknown_keys:
        raise SettingsSchemaError(
            f"Unknown settings key(s): {sorted(unknown_keys)!r}"
        )

    cleaned_patch = {}
    for field in schema.fields:
        if field.key in raw_patch:
            cleaned_patch[field.key] = _clean_field_value(field, raw_patch[field.key])

    if schema.preserve_unmanaged:
        merged = dict(current_settings)
        merged.update(cleaned_patch)
        return merged

    declared_current = {
        key: current_settings[key] for key in declared_keys if key in current_settings
    }
    declared_current.update(cleaned_patch)
    return declared_current


def serialize_schema(schema: SettingsSchema) -> dict:
    """Deterministic, JSON-safe metadata for the Inspector layer. Declared
    field order is preserved; no Python callables or runtime objects are
    included."""
    return {
        "preserve_unmanaged": schema.preserve_unmanaged,
        "fields": [
            {
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "group": field.group,
                "default": field.default,
                "required": field.required,
                "choices": [list(pair) for pair in field.choices],
                "min_value": field.min_value,
                "max_value": field.max_value,
                "max_length": field.max_length,
                "widget_hint": field.widget_hint,
            }
            for field in schema.fields
        ],
    }


def clean_section_schema_patch(definition, raw_patch: dict, current_settings: dict) -> dict:
    """R4-only Strangler bridge: schema-clean the patch first, merge it into
    ``current_settings``, then run the result through the section's own
    existing ``validate_settings`` — which stays the sole authority (see
    the architecture spec, Part V). Never called from R3, which keeps
    posting straight to ``definition.validate_settings`` unchanged."""
    if definition.settings_schema is None:
        raise SettingsSchemaError("Section is not schema-enabled")

    merged = clean_schema_patch(definition.settings_schema, raw_patch, current_settings)
    validated = definition.validate_settings(merged)
    # Phase 1 (Task 6) — stamp the internal explicit-local-variant marker only
    # when this patch genuinely targets the section's registered variant key.
    # Applied AFTER validation (the marker is intentionally outside the
    # client-writable ``appearance_overrides`` contract), so a client can never
    # set it directly and a non-variant patch never sets it. Any caller that
    # routes section-settings edits through this bridge (the R4 mutation
    # service today) inherits the behavior without owning the rule.
    return mark_explicit_variant_override(
        settings=validated,
        variant_setting_key=getattr(definition, "variant_setting_key", None),
        patch=raw_patch,
    )


#: Phase 1 (Task 6) — the internal explicit-local-variant marker key. It lives
#: inside the existing ``appearance_overrides`` block but is deliberately NOT a
#: member of the client-writable ``appearance_overrides`` contract
#: (``validate_appearance_overrides`` still rejects it as an unknown key). The
#: trusted server-side settings paths stamp it AFTER validation, so a client
#: can never manufacture explicit-local intent by supplying it directly.
VARIANT_EXPLICIT_OVERRIDE_KEY = "variant_explicit"


def mark_explicit_variant_override(
    *,
    settings: dict,
    variant_setting_key: str | None,
    patch: dict,
) -> dict:
    """Return ``settings`` with the internal explicit-local-variant marker set
    IFF ``patch`` genuinely targets the section's registered
    ``variant_setting_key``.

    Phase 1 (Task 6): a title/source/typography/content-only patch (one that
    does not include the variant key) is returned unchanged, so a historical
    section keeps its current inherited/global behavior until the merchant
    actually changes its local variant. Never mutates the inputs. Must be
    called on ALREADY-VALIDATED settings (it does not re-run schema validation,
    and the marker is intentionally outside the client-writable contract).
    """
    if not variant_setting_key or variant_setting_key not in patch:
        return settings

    from copy import deepcopy

    updated = deepcopy(settings)
    overrides = dict(updated.get("appearance_overrides") or {})
    overrides[VARIANT_EXPLICIT_OVERRIDE_KEY] = True
    updated["appearance_overrides"] = overrides
    return updated
