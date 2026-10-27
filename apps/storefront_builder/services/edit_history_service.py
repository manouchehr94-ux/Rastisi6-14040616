"""Short-lived server-side Undo/Redo history for Storefront Builder drafts.

Release history remains ``StorefrontLayoutVersion``.  This module is a separate,
bounded interaction stack for the *current mutable draft* so editor Undo/Redo
never mutates a Published version or pollutes merchant-visible version history.
"""

from __future__ import annotations

from uuid import UUID

from django.db import models, transaction

from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

from ..models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayoutVersion,
    StorefrontSection,
)

_MAX_HISTORY_ENTRIES = 30

_SECTION_FIELDS = (
    "section_key",
    "order",
    "is_active",
    "settings",
    "collapsed_in_editor",
    "stable_id",
    "template_slot_key",
    "row_key",
    "row_span",
    "is_locked",
)

_SCOPED_MEDIA = (
    ("hero_slides", HeroSlide),
    ("banners", PromotionalBanner),
    ("story_items", StoryRailItem),
)

_SKIP_MEDIA_FIELDS = {
    "id", "store", "section", "created_at", "updated_at",
}


def _json_value(value):
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "name") and not isinstance(value, str):
        # FieldFile / ImageFieldFile
        return value.name or ""
    return value


def _serialize_media(instance) -> dict:
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in _SKIP_MEDIA_FIELDS or field.primary_key:
            continue
        value = getattr(instance, field.attname)
        data[field.attname] = _json_value(value)
    return data


def _serialize_section(section: StorefrontSection, media: dict | None = None) -> dict:
    # stable_id remains the logical editor identity.  The database id is also
    # captured as a restore hint because existing section mutation routes are
    # PK-based; preserving it across Undo/Redo prevents stale command endpoints.
    data = {"id": section.pk}
    for field_name in _SECTION_FIELDS:
        value = getattr(section, field_name)
        data[field_name] = _json_value(value)
    section_media = {}
    for related_name, _model in _SCOPED_MEDIA:
        # ``media`` is the bulk lookup built once per snapshot (``{relation: {section_id: [rows]}}``); without it
        # (a direct call) the relation is queried for this section only. Rows are always ordered by id.
        if media is not None:
            rows = media[related_name].get(section.pk, ())
        else:
            rows = sorted(getattr(section, related_name).all(), key=lambda row: row.pk)
        section_media[related_name] = [_serialize_media(row) for row in rows]
    data["media"] = section_media
    return data


def _serialize_cell(cell: StorefrontCell, blocks=None, section_stable_id=None, children=None) -> dict:
    if blocks is None:
        blocks = list(cell.blocks.all())
    if section_stable_id is None and cell.section_id:
        section_stable_id = cell.section.stable_id
    data = {
        "stable_id": str(cell.stable_id),
        "order": cell.order,
        "span": cell.span,
        "settings": dict(cell.settings or {}),
        # Legacy single-block OneToOne — kept exactly as before (Phase 2A/2B
        # never remove it); every history entry recorded before Phase 2B
        # only ever has this key, so ``restore_draft_state`` must go on
        # restoring it as before regardless of whether ``blocks`` (below) is
        # present.
        "section_stable_id": (str(section_stable_id) if cell.section_id else None),
        # Phase 2B: the new multi-block FK's Blocks, in ``cell_order``. A
        # Cell with exactly one Block here (today's common case) still
        # produces a one-item list — restore doesn't special-case "single"
        # vs. "multi" separately, one code path handles both sizes.
        "blocks": [
            {"section_stable_id": str(block.stable_id), "cell_order": block.cell_order}
            for block in sorted(blocks, key=lambda block: (block.cell_order, block.pk))
        ],
    }
    # V5 Groups: the Containers nested in this Cell — the key exists only when there are any, so every snapshot of a page without Groups
    # is exactly what it was before (old and new history entries stay interchangeable).
    if children:
        data["children"] = children
    return data


def _serialize_container(container: StorefrontContainer, cells=None, blocks_by_cell=None, sections_by_id=None, nested_by_cell=None) -> dict:
    if cells is None:
        cells = list(container.cells.all())
    out = []
    for cell in sorted(cells, key=lambda cell: (cell.order, cell.pk)):
        children = [
            _serialize_container(child, (nested_by_cell or {}).get("cells", {}).get(child.pk, []), blocks_by_cell, sections_by_id, nested_by_cell)
            for child in (nested_by_cell or {}).get("by_cell", {}).get(cell.pk, [])
        ] if nested_by_cell else None
        if blocks_by_cell is None:
            out.append(_serialize_cell(cell, children=children))
            continue
        linked = sections_by_id.get(cell.section_id) if cell.section_id else None
        out.append(_serialize_cell(
            cell, blocks=blocks_by_cell.get(cell.pk, []),
            section_stable_id=linked.stable_id if linked is not None else None, children=children,
        ))
    return {
        "stable_id": str(container.stable_id),
        "order": container.order,
        "layout_key": container.layout_key,
        "settings": dict(container.settings or {}),
        "is_locked": container.is_locked,
        "cells": out,
    }


def snapshot_draft(draft: StorefrontLayoutVersion) -> dict:
    """Return a JSON-serialisable complete editable state of ``draft``.

    Every table the serialisers read is loaded ONCE for the whole draft (a snapshot is taken twice per mutation, so a
    query-per-page / per-section / per-cell pattern dominated the latency of every Studio edit) and grouped in Python."""
    page_list = list(draft.pages.order_by("page_type"))
    page_ids = [page.pk for page in page_list]
    sections = list(StorefrontSection.objects.filter(page_id__in=page_ids).order_by("order", "id"))
    sections_by_id = {section.pk: section for section in sections}
    sections_by_page: dict = {}
    blocks_by_cell: dict = {}
    for section in sections:
        sections_by_page.setdefault(section.page_id, []).append(section)
        if section.cell_id:
            blocks_by_cell.setdefault(section.cell_id, []).append(section)
    media = {}
    for related_name, model in _SCOPED_MEDIA:
        grouped: dict = {}
        for row in model.objects.filter(section_id__in=sections_by_id).order_by("id"):
            grouped.setdefault(row.section_id, []).append(row)
        media[related_name] = grouped
    containers = list(StorefrontContainer.all_objects.filter(page_id__in=page_ids).order_by("order", "id"))
    cells_by_container: dict = {}
    for cell in StorefrontCell.objects.filter(container__in=containers):
        cells_by_container.setdefault(cell.container_id, []).append(cell)
    containers_by_page: dict = {}
    nested_by_cell: dict = {}
    for container in containers:
        if container.parent_cell_id is None:
            containers_by_page.setdefault(container.page_id, []).append(container)
        else:
            nested_by_cell.setdefault(container.parent_cell_id, []).append(container)
    nested_context = {"by_cell": nested_by_cell, "cells": cells_by_container} if nested_by_cell else None

    pages = {}
    containers_out = {}
    for page in page_list:
        pages[page.page_type] = [_serialize_section(section, media) for section in sections_by_page.get(page.pk, [])]
        containers_out[page.page_type] = [
            _serialize_container(container, cells_by_container.get(container.pk, []), blocks_by_cell, sections_by_id, nested_context)
            for container in containers_by_page.get(page.pk, [])
        ]
    return {
        "header_config": dict(draft.header_config or {}),
        "footer_config": dict(draft.footer_config or {}),
        "appearance_config": dict(draft.appearance_config or {}),
        "template_provenance": dict(draft.template_provenance or {}),
        "template_baseline_snapshot": dict(draft.template_baseline_snapshot or {}),
        "pages": pages,
        "containers": containers_out,
    }


def _restore_media(section: StorefrontSection, media_state: dict) -> None:
    store_id = section.page.version.layout.store_id
    for related_name, model in _SCOPED_MEDIA:
        for row_data in media_state.get(related_name, []):
            kwargs = dict(row_data)
            kwargs["store_id"] = store_id
            kwargs["section"] = section
            model.objects.create(**kwargs)


def _restore_container(container_data: dict, page, parent_cell, section_map: dict, blocks_to_assign: list) -> None:
    """Recreate one snapshot Container (and, recursively, the Groups nested in its Cells)."""
    container = StorefrontContainer.objects.create(
        page=page,
        parent_cell=parent_cell,
        stable_id=container_data["stable_id"],
        order=container_data.get("order", 0),
        layout_key=container_data.get("layout_key", "single"),
        settings=dict(container_data.get("settings") or {}),
        is_locked=container_data.get("is_locked", False),
    )
    StorefrontCell.objects.bulk_create([
        StorefrontCell(
            container=container,
            stable_id=cell_data["stable_id"],
            order=cell_data.get("order", 0),
            span=cell_data.get("span", 12),
            settings=dict(cell_data.get("settings") or {}),
            section=section_map.get(cell_data.get("section_stable_id")),
        )
        for cell_data in container_data.get("cells", [])
    ])
    # Phase 2B: re-fetch the just-created Cells by stable_id (the same pattern ``layout_service._clone_version_content`` and
    # ``container_service.clone_page_containers`` already use) before wiring up the multi-block FK — ``bulk_create`` does not reliably
    # populate PKs on every backend, and the target Cell objects above were never individually saved.
    cells_by_stable_id = {str(cell.stable_id): cell for cell in container.cells.all()}
    for cell_data in container_data.get("cells", []):
        target_cell = cells_by_stable_id.get(cell_data["stable_id"])
        if target_cell is None:
            continue
        # Old history entries recorded before Phase 2B never have a "blocks" key at all — ``.get(..., [])`` makes restoring them behave
        # exactly as before.
        for block_data in cell_data.get("blocks", []):
            block_section = section_map.get(block_data.get("section_stable_id"))
            if block_section is None:
                continue
            blocks_to_assign.append((block_section, target_cell.pk, block_data.get("cell_order", 0)))
        for child_data in cell_data.get("children", []):
            _restore_container(child_data, page, target_cell, section_map, blocks_to_assign)


@transaction.atomic
def restore_draft_state(draft: StorefrontLayoutVersion, state: dict) -> None:
    """Replace only the mutable Draft's editable content with a trusted snapshot."""
    locked_draft = StorefrontLayoutVersion.objects.select_for_update().get(pk=draft.pk)
    locked_draft.header_config = dict(state.get("header_config") or {})
    locked_draft.footer_config = dict(state.get("footer_config") or {})
    locked_draft.appearance_config = dict(state.get("appearance_config") or {})
    update_fields = ["header_config", "footer_config", "appearance_config"]
    # History rows created before A6 legitimately lack these metadata keys.
    # Preserve their current values for those old snapshots instead of
    # clearing template identity merely because the old schema could not save it.
    if "template_provenance" in state:
        locked_draft.template_provenance = dict(state.get("template_provenance") or {})
        update_fields.append("template_provenance")
    if "template_baseline_snapshot" in state:
        locked_draft.template_baseline_snapshot = dict(
            state.get("template_baseline_snapshot") or {}
        )
        update_fields.append("template_baseline_snapshot")
    locked_draft.save(update_fields=[*update_fields, "updated_at"])

    # Layout and content are restored independently.  Containers are deleted
    # first; their Cells use SET_NULL towards Sections, so this never deletes
    # merchant content accidentally.
    for page in locked_draft.pages.all():
        page.containers.all().delete()

    # Section deletion cascades only section-scoped Placement rows. MediaAsset
    # files remain untouched because the Placement FKs point to them with PROTECT.
    locked_draft.sections.all().delete()

    page_by_type = {page.page_type: page for page in locked_draft.pages.all()}
    section_by_page_and_stable_id = {}
    for page_type, sections_state in (state.get("pages") or {}).items():
        page = page_by_type.get(page_type)
        if page is None:
            continue
        page_map = {}
        for section_state in sections_state:
            section_kwargs = {
                "page": page,
                "section_key": section_state["section_key"],
                "order": section_state.get("order", 0),
                "is_active": section_state.get("is_active", True),
                "settings": dict(section_state.get("settings") or {}),
                "collapsed_in_editor": section_state.get("collapsed_in_editor", False),
                "stable_id": section_state["stable_id"],
                "template_slot_key": section_state.get("template_slot_key", ""),
                "row_key": section_state.get("row_key", ""),
                "row_span": section_state.get("row_span", 12),
                "is_locked": section_state.get("is_locked", False),
            }
            # New snapshots preserve the original DB row id. Old history
            # entries created before this change do not contain id and
            # intentionally fall back to the previous auto-PK restore path.
            if section_state.get("id") is not None:
                section_kwargs["id"] = section_state["id"]
            section = StorefrontSection.objects.create(**section_kwargs)
            page_map[str(section.stable_id)] = section
            _restore_media(section, section_state.get("media") or {})
        section_by_page_and_stable_id[page_type] = page_map

    # Phase 3.0 snapshots include empty Cells as first-class layout state.
    # Old history entries do not have the ``containers`` key; for those,
    # rebuild from their preserved legacy row_key/row_span values.
    container_state = state.get("containers")
    if isinstance(container_state, dict):
        blocks_to_assign = []  # (stable_id-keyed lookups deferred until every Cell exists)
        for page_type, containers in container_state.items():
            page = page_by_type.get(page_type)
            if page is None:
                continue
            section_map = section_by_page_and_stable_id.get(page_type, {})
            for container_data in containers:
                _restore_container(container_data, page, None, section_map, blocks_to_assign)
        if blocks_to_assign:
            updated_sections = []
            for section, cell_pk, cell_order in blocks_to_assign:
                section.cell_id = cell_pk
                section.cell_order = cell_order
                updated_sections.append(section)
            StorefrontSection.objects.bulk_update(updated_sections, ["cell", "cell_order"])
    else:
        from . import container_service
        container_service.ensure_version_containers(locked_draft)


def _history_qs(draft):
    return StorefrontEditHistoryEntry.objects.filter(draft_version=draft)


def history_state(draft: StorefrontLayoutVersion) -> dict:
    qs = _history_qs(draft)
    undo_entry = qs.filter(is_undone=False).order_by("-sequence").first()
    redo_entry = qs.filter(is_undone=True).order_by("sequence").first()
    return {
        "can_undo": undo_entry is not None,
        "can_redo": redo_entry is not None,
        "undo_label": undo_entry.action_label if undo_entry else "",
        "redo_label": redo_entry.action_label if redo_entry else "",
    }


@transaction.atomic
def record_change(*, draft: StorefrontLayoutVersion, actor, action_label: str, before_state: dict) -> bool:
    """Append one successful mutation; invalid/no-op submissions add nothing.

    L01 convergence (Phase 2 Task 3): ``edit_revision`` is the single
    Draft-wide monotonic optimistic-concurrency token for ALL
    Appearance/Builder-owned mutations. This is the one place a real
    change is detected (before/after snapshot compare), so it is the one
    place the token advances — atomically, exactly once, and *iff* a
    history entry is appended. Advancing here (rather than only in the R4
    path) makes BOTH the legacy ``@_record_edit_history`` decorator and the
    R4 ``apply_mutation`` path revision-coherent through a single boundary:
    a legacy edit now makes a concurrent R4 client's ``base_revision``
    stale, and history + revision can never drift apart. A semantic no-op
    (``before_state == after_state``) advances nothing and records nothing.

    R4 ``apply_mutation`` therefore MUST NOT re-increment after calling this
    (that would advance by 2). R4 ``apply_history_command`` (Undo/Redo)
    deliberately never calls ``record_change`` and owns its own single
    increment — that path is unaffected by the advance added here.
    """
    locked_draft = StorefrontLayoutVersion.objects.select_for_update().get(pk=draft.pk)
    after_state = snapshot_draft(locked_draft)
    if before_state == after_state:
        return False

    qs = _history_qs(locked_draft)
    # A new edit after Undo starts a new branch; conventional Redo is discarded.
    qs.filter(is_undone=True).delete()
    last_sequence = qs.aggregate(max_sequence=models.Max("sequence"))["max_sequence"] or 0
    StorefrontEditHistoryEntry.objects.create(
        draft_version=locked_draft,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        sequence=last_sequence + 1,
        action_label=action_label[:120],
        before_state=before_state,
        after_state=after_state,
    )

    ids_to_keep = list(
        qs.order_by("-sequence").values_list("pk", flat=True)[:_MAX_HISTORY_ENTRIES]
    )
    if ids_to_keep:
        qs.exclude(pk__in=ids_to_keep).delete()

    # Advance the Draft-wide revision token in the same atomic block as the
    # history append, so revision monotonicity and history stay coherent for
    # every caller. Mutate the caller's instance too so it observes the new
    # value without a manual refresh.
    locked_draft.edit_revision = models.F("edit_revision") + 1
    locked_draft.save(update_fields=["edit_revision"])
    locked_draft.refresh_from_db(fields=["edit_revision"])
    draft.edit_revision = locked_draft.edit_revision
    return True


@transaction.atomic
def undo(draft: StorefrontLayoutVersion):
    entry = (
        _history_qs(draft)
        .select_for_update()
        .filter(is_undone=False)
        .order_by("-sequence")
        .first()
    )
    if entry is None:
        return None
    restore_draft_state(draft, entry.before_state)
    entry.is_undone = True
    entry.save(update_fields=["is_undone", "updated_at"])
    return entry


@transaction.atomic
def redo(draft: StorefrontLayoutVersion):
    entry = (
        _history_qs(draft)
        .select_for_update()
        .filter(is_undone=True)
        .order_by("sequence")
        .first()
    )
    if entry is None:
        return None
    restore_draft_state(draft, entry.after_state)
    entry.is_undone = False
    entry.save(update_fields=["is_undone", "updated_at"])
    return entry
