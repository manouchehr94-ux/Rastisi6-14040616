"""R4 Task 5 — the single optimistic mutation boundary for the R4 editor.

One transaction: lock the Store's ``StorefrontLayout``, resolve its
currently-active Draft (``layout.draft_version`` — never silently
switched/created here, see ``layout_service.get_or_create_draft`` for that),
compare ``base_revision``, dispatch exactly one allowlisted mutation type,
increment ``edit_revision`` once, and record history through the existing
``edit_history_service`` contract. R3 never calls this module.
"""

from __future__ import annotations

from django.db import transaction

from apps.storefront_builder import (
    appearance_registry,
    layout_preset_registry,
    resource_source,
    section_registry,
)
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import (
    appearance_authority_service,
    edit_history_service,
    layout_service,
    preset_service,
    section_structure_service,
)
from apps.storefront_builder.settings_schema import clean_section_schema_patch
from apps.storefront_builder.storefront_appearance.contracts import (
    InvalidStoreAppearanceContract,
)
from apps.storefront_builder.storefront_appearance.families import COMPONENT_FAMILIES
from apps.storefront_builder.storefront_appearance.persistence import (
    component_key_for_registry_reference,
    load_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.registry import get_component
from apps.storefront_builder.storefront_appearance.validation import (
    manifest_to_primitive,
    validate_store_appearance_manifest,
)


class R4MutationError(ValueError):
    pass


class R4StaleRevision(R4MutationError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("stale_revision")


_MUTATION_HISTORY_LABELS = {
    "section.update_settings": "ویرایش تنظیمات بخش",
    "section.add": "افزودن بخش",
    "section.remove": "حذف بخش",
    "section.duplicate": "تکرار بخش",
    "section.move": "جابه‌جایی بخش",
    "appearance.update": "ویرایش طراحی کلی",
    "header.update": "ویرایش هدر",
    "footer.update": "ویرایش فوتر",
    "appearance.component.update": "تغییر جزء طراحی فروشگاه",
    "appearance.manifest.apply": "اعمال طراحی فروشگاه",
    "appearance.template.apply": "اعمال قالب آماده",
}


def _history_label(mutation: dict) -> str:
    return _MUTATION_HISTORY_LABELS.get(mutation.get("type"), "ویرایش R4")


def _is_strict_int(value: object) -> bool:
    return type(value) is int


def _require_owned_resource(model, *, store, source_id: int) -> None:
    """Fail closed: a foreign-Store id and a nonexistent id both simply
    fail this single Store-scoped ``exists()`` check — never a second
    query against another Store to tell them apart."""
    if not model.objects.filter(store=store, pk=source_id).exists():
        raise R4MutationError("invalid_resource_ownership")


def _validate_resource_source_ownership(*, store, source: "resource_source.ResourceSource") -> None:
    """R4 Task 10 (Section 8) — a Store-scoped Picker search endpoint alone
    does not stop a client from POSTing an arbitrary foreign-Store id
    straight to this mutation endpoint. Every manual id / auto source_id a
    ``source`` patch actually references must belong to the current Store
    BEFORE the settings are persisted."""
    # Imported here, not at module scope: resource_source.py itself must
    # stay a pure, DB-free domain module (Task 9's hard rule) — the DB
    # lookups this ownership check needs live only in this service.
    from apps.catalog.models import Brand, Category, MerchantCollection
    from apps.catalog.services.collection_service import searchable_products

    if source.kind == "product":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_ids = set(
                searchable_products(store).filter(pk__in=source.manual_ids).values_list("pk", flat=True)
            )
            if owned_ids != set(source.manual_ids):
                raise R4MutationError("invalid_resource_ownership")
            return
        if source.auto_rule == "by_category":
            _require_owned_resource(Category, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_brand":
            _require_owned_resource(Brand, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_collection":
            _require_owned_resource(MerchantCollection, store=store, source_id=source.auto_parameters["source_id"])
        # newest/discounted/best_sellers/most_viewed reference no specific
        # resource id — nothing to own-check.
        return

    if source.kind == "brand":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_count = Brand.objects.filter(store=store, pk__in=source.manual_ids).count()
            if owned_count != len(set(source.manual_ids)):
                raise R4MutationError("invalid_resource_ownership")
        # auto_rule == "all_active" references no specific resource id.
        return

    # category/collection kinds are not exposed by the Task 10 UI and carry
    # no ownership rule yet — defensively a no-op rather than a false reject.


def _apply_section_update_settings(*, store, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    patch = mutation.get("patch")

    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    if not isinstance(patch, dict):
        raise R4MutationError("invalid_patch")

    # Scoped through the locked, active Draft — never by bare pk — so a
    # section belonging to another Store, or to a Published/non-active
    # version of THIS Store, is indistinguishable from "does not exist".
    try:
        section = StorefrontSection.objects.select_for_update().get(
            pk=section_id, page__version=draft,
        )
    except StorefrontSection.DoesNotExist:
        raise R4MutationError("section_not_found") from None

    try:
        definition = section_registry.get_definition(section.section_key)
    except ValueError:
        raise R4MutationError("unknown_section_type") from None

    if definition.settings_schema is None:
        raise R4MutationError("section_not_schema_enabled")

    # Narrowly scoped: covers both SettingsSchemaError (schema cleaning)
    # and a plain ValueError from the legacy validator bridge that
    # clean_section_schema_patch calls internally — one stable external
    # code either way, never the internal validator's own message text.
    try:
        cleaned = clean_section_schema_patch(definition, patch, section.settings or {})
    except ValueError as exc:
        raise R4MutationError("invalid_settings") from exc

    # R4 Task 10 — ownership is only ever validated when THIS mutation's
    # raw patch actually touches "source"; a stale/deleted legacy reference
    # left over from before Task 10 must never turn an unrelated field edit
    # into a failure (Section 10's explicit backward-compatibility rule).
    # Checked AFTER schema cleaning (the shape is already trustworthy) but
    # BEFORE section.settings is assigned/saved, so a rejection here rolls
    # back cleanly with no settings/revision/history change.
    if "source" in patch:
        try:
            projected_source = resource_source.resource_source_from_section_settings(
                section.section_key, cleaned,
            )
        except resource_source.ResourceSourceError:
            projected_source = None
        if projected_source is not None:
            _validate_resource_source_ownership(store=store, source=projected_source)

    section.settings = cleaned
    section.save(update_fields=["settings"])


def _apply_section_add(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_key = mutation.get("section_key")
    if not isinstance(section_key, str) or not section_key:
        raise R4MutationError("invalid_section_key")
    try:
        section_structure_service.add_section(draft=draft, section_key=section_key)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_remove(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    try:
        section_structure_service.remove_section(draft=draft, section_id=section_id)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_duplicate(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    try:
        section_structure_service.duplicate_section(draft=draft, section_id=section_id)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_move(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    direction = mutation.get("direction")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    if not isinstance(direction, str):
        raise R4MutationError("invalid_direction")
    try:
        section_structure_service.move_section(draft=draft, section_id=section_id, direction=direction)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


#: R4 Task 11 (Section 6) — Phase 1's narrow Global Design allowlist. Never
#: raw CSS/JSON, never an arbitrary color/template path — every other
#: appearance_config key (radius/button_radius/density/content_width/...)
#: only ever changes as a side effect of a Template switch (see
#: _TEMPLATE_OWNED_FIELDS below), exactly like R3's own editor (views.py).
_APPEARANCE_UPDATE_ALLOWED_PATCH_KEYS = frozenset({
    "template_slug", "palette_slug", "font", "type_scale", "motion", "button_style",
})

#: The fields a Template selection owns on transition — verified against
#: R3's own real POST-time semantics (views.py's ``_field()``), not
#: invented: exactly these 7 use "Template > posted > current" priority.
#: TemplateDefinition's other 5 "structural" fields (content_width/
#: grid_density/card_shadow/card_hover/hero_style — the Phase 8 P0-7
#: fields) are validated against a DIFFERENT, independent choice domain
#: (appearance_registry.SITE_CONTENT_WIDTH_CHOICES etc.) and are, by R3's
#: own real behavior, deliberately NOT auto-applied on a Template switch —
#: they only ever come from an explicit posted value or the current
#: stored one. swatch/name_fa/group_fa/description_fa/slug are
#: presentation-only / the key itself, also excluded.
_TEMPLATE_OWNED_FIELDS = ("font", "radius", "button_radius", "button_style", "density", "motion", "type_scale")


def _require_pinned_appearance_draft(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    """Pin A6 writes to the exact Draft the client previewed.

    Store ownership still comes exclusively from ``_lock_active_draft``. The
    explicit id prevents a stale browser tab from applying a candidate to a
    newly-created active Draft that happens to share the same revision.
    """
    draft_id = mutation.get("draft_id")
    if not _is_strict_int(draft_id):
        raise R4MutationError("invalid_draft_id")
    if draft_id != draft.pk:
        # Nonexistent, inactive, Published and foreign Draft ids are deliberately
        # indistinguishable to the caller.
        raise R4MutationError("draft_not_found")


_LEGACY_SELECTOR_FAMILIES = ("header", "footer", "bottom_nav", "motion")


def _component_key_from_live_reference(*, family: str, reference: str) -> str:
    component_key = component_key_for_registry_reference(reference, family_key=family)
    if component_key is None:
        # Every valid legacy selector should already be adapted into the central
        # registry. Fail closed rather than preserve a stale typed manifest.
        raise R4MutationError("invalid_store_appearance_manifest")
    return component_key


def _live_legacy_selection_updates(*, draft: StorefrontLayoutVersion) -> dict[str, str]:
    header = draft.effective_header_config()
    footer = draft.effective_footer_config()
    appearance = draft.effective_appearance_config()
    references = {
        "header": f"global_region:header:{header['header_variant']}",
        "footer": f"global_region:footer:{footer['footer_variant']}",
        "bottom_nav": f"global_region:mobile_bottom_nav:{footer['mobile_nav_variant']}",
        "motion": f"appearance_motion:{appearance['motion']}",
    }
    return {
        family: _component_key_from_live_reference(
            family=family, reference=references[family]
        )
        for family in _LEGACY_SELECTOR_FAMILIES
    }


def _persist_manifest_selection_updates(
    *,
    draft: StorefrontLayoutVersion,
    updates: dict[str, str],
    preserve_live_legacy_siblings: bool = False,
) -> None:
    try:
        current = load_store_appearance_manifest(draft)
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc
    current_primitive = manifest_to_primitive(current)
    primitive = manifest_to_primitive(current)
    live_legacy = _live_legacy_selection_updates(draft=draft)
    if preserve_live_legacy_siblings:
        primitive["selections"].update(
            {family: key for family, key in live_legacy.items() if family not in updates}
        )
    primitive["selections"].update(updates)

    # Do not turn a semantic no-op into explicit default JSON writes. A5's
    # fresh Draft stores a typed default manifest while legacy selector dicts
    # may remain sparse; effective selector equality is the relevant truth.
    if primitive == current_primitive and all(
        live_legacy[family] == primitive["selections"][family]
        for family in _LEGACY_SELECTOR_FAMILIES
    ):
        return

    try:
        appearance_authority_service.apply_store_appearance_manifest(
            version=draft, manifest=primitive
        )
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc


def _sync_manifest_from_live_selectors(*, draft: StorefrontLayoutVersion) -> None:
    _persist_manifest_selection_updates(
        draft=draft, updates=_live_legacy_selection_updates(draft=draft)
    )


def _apply_appearance_component_update(
    *, draft: StorefrontLayoutVersion, mutation: dict
) -> None:
    _require_pinned_appearance_draft(draft=draft, mutation=mutation)
    family = mutation.get("family")
    component_key = mutation.get("component_key")
    if not isinstance(family, str) or family not in COMPONENT_FAMILIES:
        raise R4MutationError("invalid_appearance_family")
    if not isinstance(component_key, str):
        raise R4MutationError("invalid_appearance_component")
    component = get_component(component_key)
    if component is None or component.family_key != family:
        raise R4MutationError("invalid_appearance_component")
    try:
        _persist_manifest_selection_updates(
            draft=draft,
            updates={family: component_key},
            preserve_live_legacy_siblings=True,
        )
    except R4MutationError as exc:
        if str(exc) == "invalid_store_appearance_manifest":
            raise R4MutationError("invalid_appearance_component") from exc
        raise


def _apply_appearance_manifest(
    *, draft: StorefrontLayoutVersion, mutation: dict
) -> None:
    _require_pinned_appearance_draft(draft=draft, mutation=mutation)
    candidate = mutation.get("manifest")
    if not isinstance(candidate, dict):
        raise R4MutationError("invalid_store_appearance_manifest")
    try:
        validated = validate_store_appearance_manifest(candidate).manifest
        primitive = manifest_to_primitive(validated)
        current = manifest_to_primitive(load_store_appearance_manifest(draft))
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc

    live_legacy = _live_legacy_selection_updates(draft=draft)
    if primitive == current and all(
        live_legacy[family] == primitive["selections"][family]
        for family in _LEGACY_SELECTOR_FAMILIES
    ):
        return

    try:
        appearance_authority_service.apply_store_appearance_manifest(
            version=draft, manifest=primitive
        )
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc


def _apply_appearance_template(
    *, draft: StorefrontLayoutVersion, mutation: dict
) -> None:
    _require_pinned_appearance_draft(draft=draft, mutation=mutation)
    template_key = mutation.get("template_key")
    template_version = mutation.get("template_version")
    if not isinstance(template_key, str) or not template_key:
        raise R4MutationError("unknown_appearance_template")
    if not isinstance(template_version, str) or not template_version:
        raise R4MutationError("template_version_mismatch")

    preset = layout_preset_registry.get_layout_preset(template_key)
    if preset is None or not preset.is_ready_template:
        raise R4MutationError("unknown_appearance_template")
    if preset.version != template_version:
        raise R4MutationError("template_version_mismatch")

    try:
        preset_service.apply_preset(draft, preset)
    except preset_service.InvalidPresetError as exc:
        raise R4MutationError("invalid_appearance_template") from exc

    # A6 predates A8's complete Ready-Template DNA. Synchronize the component
    # families that existing Ready Templates already own today.
    _sync_manifest_from_live_selectors(draft=draft)

    # ``apply_preset`` captured its baseline before the typed manifest sync.
    # Make the immutable baseline describe the exact final state of this one
    # atomic mutation, so Reset/Undo cannot reintroduce stale selectors.
    if draft.template_baseline_snapshot:
        snapshot = dict(draft.template_baseline_snapshot)
        snapshot["appearance"] = dict(draft.appearance_config or {})
        snapshot["header_config"] = dict(draft.header_config or {})
        snapshot["footer_config"] = dict(draft.footer_config or {})
        draft.template_baseline_snapshot = snapshot
        draft.save(update_fields=["template_baseline_snapshot"])


def _apply_appearance_update(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    patch = mutation.get("patch")
    if not isinstance(patch, dict):
        raise R4MutationError("invalid_patch")
    if set(patch) - _APPEARANCE_UPDATE_ALLOWED_PATCH_KEYS:
        raise R4MutationError("invalid_appearance_patch")

    current = draft.effective_appearance_config()
    candidate = dict(current)

    # A Template switch wins over an explicit field value in the SAME
    # patch — exact R3 precedence (views.py's `_field`: Template > posted
    # > current) — never the other way around.
    new_template_slug = patch.get("template_slug", current.get("template_slug"))
    template_changed = new_template_slug != current.get("template_slug")
    new_template = appearance_registry.get_template(new_template_slug) if template_changed else None
    candidate["template_slug"] = new_template_slug
    if new_template is not None:
        for field in _TEMPLATE_OWNED_FIELDS:
            candidate[field] = getattr(new_template, field)

    # Switching Palette starts fresh — old color/theme overrides made no
    # sense against the new palette (same rule R3's editor already applies).
    new_palette_slug = patch.get("palette_slug", current.get("palette_slug"))
    if new_palette_slug != current.get("palette_slug"):
        candidate["color_overrides"] = {}
        candidate["theme_overrides"] = {}
    candidate["palette_slug"] = new_palette_slug

    for field in ("font", "type_scale", "motion", "button_style"):
        if new_template is None and field in patch:
            candidate[field] = patch[field]

    try:
        cleaned = layout_service.validate_appearance_config(candidate)
    except layout_service.AppearanceConfigValidationError as exc:
        raise R4MutationError("invalid_appearance_config") from exc

    # Phase 1 (Task 4) — delegate the final appearance_config transformation to
    # the canonical authority service. This preserves the reserved
    # store_appearance manifest and any other opaque canonical keys that the
    # legacy managed validator would otherwise drop, while R4 keeps ownership of
    # transaction/lock/base-revision/history/response. Manifest synchronization
    # can be a semantic no-op (for example, boutique keeps the default motion),
    # but template-owned fields such as template_slug/font still changed and
    # must be visible to record_change(), which reloads the Draft from the DB.
    appearance_authority_service.apply_appearance_patch(version=draft, patch=cleaned)
    if "motion" in patch or new_template is not None:
        _sync_manifest_from_live_selectors(draft=draft)


def _apply_header_update(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    patch = mutation.get("patch")
    if not isinstance(patch, dict):
        raise R4MutationError("invalid_patch")
    if set(patch) - {"header_variant"}:
        raise R4MutationError("invalid_header_patch")

    candidate = dict(draft.effective_header_config())
    if "header_variant" in patch:
        candidate["header_variant"] = patch["header_variant"]

    try:
        cleaned = layout_service.validate_header_config(candidate)
    except layout_service.HeaderConfigValidationError as exc:
        raise R4MutationError("invalid_header_config") from exc

    # Persist the full validated header config first (toggles/announcement/
    # content preserved), then delegate the typed manifest header selection
    # synchronization to the canonical authority service.
    draft.header_config = cleaned
    draft.save(update_fields=["header_config"])
    try:
        appearance_authority_service.apply_header_variant(
            version=draft, header_variant=cleaned["header_variant"]
        )
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc


def _apply_footer_update(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    patch = mutation.get("patch")
    if not isinstance(patch, dict):
        raise R4MutationError("invalid_patch")
    if set(patch) - {"footer_variant"}:
        raise R4MutationError("invalid_footer_patch")

    candidate = dict(draft.effective_footer_config())
    if "footer_variant" in patch:
        candidate["footer_variant"] = patch["footer_variant"]

    try:
        cleaned = layout_service.validate_footer_config(candidate)
    except layout_service.FooterConfigValidationError as exc:
        raise R4MutationError("invalid_footer_config") from exc

    # Persist the full validated footer config first, then delegate the typed
    # manifest footer/bottom_nav selection synchronization to the authority
    # service. mobile_nav_variant is always present in the effective footer
    # config, so both families are kept in sync.
    draft.footer_config = cleaned
    draft.save(update_fields=["footer_config"])
    try:
        appearance_authority_service.apply_footer_variant(
            version=draft,
            footer_variant=cleaned["footer_variant"],
            mobile_nav_variant=cleaned["mobile_nav_variant"],
        )
    except InvalidStoreAppearanceContract as exc:
        raise R4MutationError("invalid_store_appearance_manifest") from exc


def _dispatch_mutation(*, store, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    """The one explicit, server-owned allowlist — no getattr-on-user-input,
    no globals(), no dynamic import, no eval. ``store`` is accepted (not
    used by every mutation type) to keep the dispatcher's signature stable
    for future allowlisted mutation types that need it."""
    mutation_type = mutation.get("type")
    if mutation_type == "section.update_settings":
        _apply_section_update_settings(store=store, draft=draft, mutation=mutation)
        return
    if mutation_type == "section.add":
        _apply_section_add(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.remove":
        _apply_section_remove(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.duplicate":
        _apply_section_duplicate(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.move":
        _apply_section_move(draft=draft, mutation=mutation)
        return
    if mutation_type == "appearance.update":
        _apply_appearance_update(draft=draft, mutation=mutation)
        return
    if mutation_type == "header.update":
        _apply_header_update(draft=draft, mutation=mutation)
        return
    if mutation_type == "footer.update":
        _apply_footer_update(draft=draft, mutation=mutation)
        return
    if mutation_type == "appearance.component.update":
        _apply_appearance_component_update(draft=draft, mutation=mutation)
        return
    if mutation_type == "appearance.manifest.apply":
        _apply_appearance_manifest(draft=draft, mutation=mutation)
        return
    if mutation_type == "appearance.template.apply":
        _apply_appearance_template(draft=draft, mutation=mutation)
        return
    raise R4MutationError("unknown_mutation_type")


def _lock_active_draft(*, store, base_revision: int) -> StorefrontLayoutVersion:
    """The ONE R4 concurrency boundary — select_for_update the Store's
    StorefrontLayout, resolve ONLY its already-active ``draft_version``
    (never silently create/switch one — see ``layout_service.
    get_or_create_draft`` for that), require DRAFT status, and compare
    ``base_revision``. Shared by normal mutations, Undo/Redo, and Publish;
    every caller runs inside its own ``@transaction.atomic``."""
    layout = StorefrontLayout.objects.select_for_update().get(store=store)

    if layout.draft_version_id is None:
        raise R4MutationError("no_active_draft")

    try:
        draft = StorefrontLayoutVersion.objects.select_for_update().get(
            pk=layout.draft_version_id,
            layout=layout,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
    except StorefrontLayoutVersion.DoesNotExist:
        raise R4MutationError("no_active_draft") from None

    if draft.edit_revision != base_revision:
        raise R4StaleRevision(draft.edit_revision)

    return draft


@transaction.atomic
def apply_mutation(*, store, actor, base_revision: int, mutation: dict) -> int:
    if not isinstance(mutation, dict):
        raise R4MutationError("invalid_mutation")

    draft = _lock_active_draft(store=store, base_revision=base_revision)

    before_state = edit_history_service.snapshot_draft(draft)

    _dispatch_mutation(store=store, draft=draft, mutation=mutation)

    changed = edit_history_service.record_change(
        draft=draft,
        actor=actor,
        action_label=_history_label(mutation),
        before_state=before_state,
    )
    if not changed:
        # Valid semantic no-op: no revision churn and no fake history entry.
        return draft.edit_revision

    draft.edit_revision += 1
    draft.save(update_fields=["edit_revision"])
    return draft.edit_revision


@transaction.atomic
def apply_history_command(*, store, actor, base_revision: int, command: str) -> dict:
    """R4 Task 11 — thin command wrapper around edit_history_service.undo/
    redo. Deliberately NEVER calls edit_history_service.record_change:
    routing Undo/Redo through the normal history path would make Undo
    itself a new undoable edit and corrupt history semantics (Section 13).
    A successful Undo/Redo still owns the ONE R4 revision-monotonicity
    guarantee: edit_revision always moves forward by exactly 1, even
    though the restored *content* may be older."""
    if command not in ("undo", "redo"):
        raise R4MutationError("unknown_history_command")

    draft = _lock_active_draft(store=store, base_revision=base_revision)

    entry = edit_history_service.undo(draft) if command == "undo" else edit_history_service.redo(draft)

    if entry is None:
        # Nothing to Undo/Redo — a controlled no-op: no Draft mutation, no
        # revision increment, no fake history entry.
        history = edit_history_service.history_state(draft)
        return {
            "changed": False,
            "new_revision": draft.edit_revision,
            "can_undo": history["can_undo"],
            "can_redo": history["can_redo"],
            "action_label": None,
        }

    draft.edit_revision += 1
    draft.save(update_fields=["edit_revision"])
    history = edit_history_service.history_state(draft)
    return {
        "changed": True,
        "new_revision": draft.edit_revision,
        "can_undo": history["can_undo"],
        "can_redo": history["can_redo"],
        "action_label": entry.action_label,
    }


@transaction.atomic
def publish_draft(*, store, actor, base_revision: int) -> StorefrontLayoutVersion:
    """R4 Task 11 — stale-aware Publish. Locks/compares through the SAME
    concurrency boundary as every other R4 write, then delegates the
    entire release lifecycle to the existing, already-atomic
    ``layout_service.publish`` — never a second, hand-rolled copy of it.
    Publish is deliberately NOT a normal edit mutation (Section 18): no
    history label, no edit_history_service.record_change call — the
    Draft being published already clears its own short-lived edit history
    as part of ``layout_service.publish`` itself."""
    _lock_active_draft(store=store, base_revision=base_revision)
    return layout_service.publish(store, user=actor)
