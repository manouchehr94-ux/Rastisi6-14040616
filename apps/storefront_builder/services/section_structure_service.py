"""R4 Task 8 — semantic Section structure mutations: add/remove/duplicate/move.

A server-side domain adapter, NOT an HTTP/R4 module: no request object, no
messages framework, no user-facing HTML. ``r4_mutation_service`` is the only
caller — it converts ``SectionStructureError.code`` into the stable
``R4MutationError`` codes the mutation boundary already returns.

Phase 4 (Task 3B) generalized every function here from Home-only to all six
``StorefrontPage.PageType`` values — ``add_section`` takes an explicit,
caller-validated ``page_type``; ``remove_section``/``duplicate_section``/
``move_section`` infer their page from the resolved ``section_id`` itself
(a section already uniquely belongs to exactly one page on exactly one
Draft, so no separate page_type input is needed or asked for — the same
principle the legacy editor's per-section views already use). None of these
ever call ``container_service.rebuild_page_from_legacy_rows``, which would
destroy empty Cells, multi-block Cells, and merchant-chosen layouts (see the
architecture ruling in the Task 8 plan) — that invariant is unchanged by the
page-type generalization.
"""

from __future__ import annotations

import copy

from .. import section_registry
from ..models import StorefrontCell, StorefrontContainer, StorefrontPage, StorefrontSection
from . import container_service, layout_service, row_service


class SectionStructureError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _scoped_section(draft, section_id) -> StorefrontSection:
    """The one strict scoping rule every mutation must use: a crafted
    ``section_id`` belonging to another Store, another page, or a
    non-active-Draft version is indistinguishable from "does not exist".

    Phase 4 (Task 3B): scoped by ``page__version=draft`` only — not by a
    specific ``page_type`` — because the section_id itself already uniquely
    identifies exactly one page on this exact Draft; requiring a second,
    redundant page_type match here would just be a copy of that same fact,
    never a real additional safety boundary."""
    try:
        return StorefrontSection.objects.select_for_update().get(
            pk=section_id,
            page__version=draft,
        )
    except StorefrontSection.DoesNotExist:
        raise SectionStructureError("section_not_found") from None


def _find_placement_cell(section: StorefrontSection):
    """Same-Cell resolution the rest of the codebase already uses: prefer
    the new multi-block FK, fall back to the legacy single-block OneToOne
    reverse pointer."""
    cell = section.cell
    if cell is None:
        cell = StorefrontCell.objects.filter(section=section).select_related("container").first()
    return cell


def _get_definition(section_key: str):
    try:
        return section_registry.get_definition(section_key)
    except section_registry.UnknownSectionTypeError:
        return None


def _next_page_order(page) -> int:
    """The page-level ``order`` field has no database uniqueness constraint
    on (page, order), yet it remains an active legacy/row-layout
    compatibility contract — a newly-created logical Section must never
    collide with a surviving one's order. ``len(sections)`` is unsafe once
    orders are sparse (e.g. after a prior remove left a gap); the only safe
    value is one past the current maximum. Sparse orders themselves are
    fine and never renumbered here — Container/Cell visual positioning
    stays authoritative regardless of this field's exact values."""
    last = page.sections.order_by("-order", "-id").only("order").first()
    return (last.order + 1) if last is not None else 0


def add_section(*, draft, section_key: str, page_type: str) -> StorefrontSection:
    if not isinstance(section_key, str) or not section_key:
        raise SectionStructureError("invalid_section_key")
    if page_type not in StorefrontPage.PageType.values:
        raise SectionStructureError("invalid_page_type")

    definition = _get_definition(section_key)
    if definition is None:
        raise SectionStructureError("invalid_section_key")

    page = draft.get_page(page_type)
    if not section_registry.is_section_allowed_on_page(section_key, page.page_type):
        raise SectionStructureError("section_not_allowed_on_page")
    if definition.hidden_from_library:
        raise SectionStructureError("section_hidden_from_library")

    if definition.max_instances is not None:
        existing_count = page.sections.filter(section_key=section_key).count()
        if existing_count >= definition.max_instances:
            raise SectionStructureError("max_instances_exceeded")

    container_service.ensure_page_containers(page)

    new_section = StorefrontSection.objects.create(
        page=page, section_key=section_key, order=_next_page_order(page),
        settings=definition.default_settings(),
    )
    container = container_service.create_empty_container(page, "single")
    cell = container.cells.order_by("order", "id").first()
    container_service.place_section(cell, new_section)
    return new_section


def remove_section(*, draft, section_id: int) -> None:
    section = _scoped_section(draft, section_id)

    if section.is_locked:
        raise SectionStructureError("section_locked")

    definition = _get_definition(section.section_key)
    if definition is not None and not definition.removable:
        raise SectionStructureError("section_not_removable")
    if definition is not None and definition.min_instances > 0:
        page = section.page
        remaining = page.sections.filter(section_key=section.section_key).exclude(pk=section.pk).count()
        if remaining < definition.min_instances:
            raise SectionStructureError("min_instances_violation")

    if row_service.is_row_member(section):
        raise SectionStructureError("row_member")

    page = section.page
    container_service.ensure_page_containers(page)
    section.refresh_from_db()

    cell = _find_placement_cell(section)
    if cell is not None and cell.container.is_locked:
        raise SectionStructureError("container_locked")

    container_service.remove_block(section)
    section.delete()


def duplicate_section(*, draft, section_id: int) -> StorefrontSection:
    section = _scoped_section(draft, section_id)

    definition = _get_definition(section.section_key)
    if definition is not None and not definition.duplicable:
        raise SectionStructureError("section_not_duplicable")
    if definition is not None and definition.max_instances is not None:
        existing_count = section.page.sections.filter(section_key=section.section_key).count()
        if existing_count >= definition.max_instances:
            raise SectionStructureError("max_instances_exceeded")

    page = section.page
    container_service.ensure_page_containers(page)
    section.refresh_from_db()

    cell = _find_placement_cell(section)
    if cell is not None and cell.container.is_locked:
        raise SectionStructureError("container_locked")

    new_section = StorefrontSection.objects.create(
        page=page, section_key=section.section_key, order=_next_page_order(page),
        is_active=section.is_active, settings=copy.deepcopy(section.settings or {}),
        # stable_id intentionally left to its default (uuid4) — a
        # duplicate is a NEW logical Section, not the same one cloned
        # across versions.
    )
    layout_service._clone_section_scoped_media(section, new_section)

    if cell is None:
        # Unreachable in practice — ensure_page_containers above guarantees
        # every page-level Section has a placement — but fail closed rather
        # than ever calling rebuild_page_from_legacy_rows.
        raise SectionStructureError("section_not_placed")

    # Compatibility case (Task 8 plan, Section 12): if this Cell is still
    # represented only by the legacy OneToOne pointer, adopt the SOURCE
    # into the new multi-block FK first — otherwise placing the duplicate
    # via the new FK would make the source disappear from
    # get_cell_blocks() (only the new FK's rows would be considered).
    if section.cell_id != cell.pk:
        container_service.add_block(cell, section, at_index=0)

    source_index = section.cell_order
    container_service.add_block(cell, new_section, at_index=source_index + 1)
    return new_section


def toggle_section_active(*, draft, section_id: int) -> StorefrontSection:
    """R4 Task 7 (Batch 1) — the exact same flag/effect as the legacy
    ``storefront_section_toggle`` view (``views.py``): flips ``is_active``
    only. Independent of ``is_locked``/duplicable/removable, exactly like
    the legacy view's own field-level independence."""
    section = _scoped_section(draft, section_id)
    section.is_active = not section.is_active
    section.save(update_fields=["is_active", "updated_at"])
    return section


def toggle_section_locked(*, draft, section_id: int) -> StorefrontSection:
    """R4 Task 7 (Batch 1) — the exact same flag as the legacy
    ``storefront_section_lock_toggle`` view (spec §37): only the flag is
    toggled here; the actual lock EFFECT (refusing move/remove) is enforced
    where it already is, in ``remove_section``/``move_section`` above."""
    section = _scoped_section(draft, section_id)
    section.is_locked = not section.is_locked
    section.save(update_fields=["is_locked", "updated_at"])
    return section


def _scoped_container(draft, container_id) -> StorefrontContainer:
    """Same strict scoping rule as ``_scoped_section`` above, for a
    Container id instead of a Section id."""
    try:
        return StorefrontContainer.objects.select_for_update().get(
            pk=container_id, page__version=draft,
        )
    except StorefrontContainer.DoesNotExist:
        raise SectionStructureError("container_not_found") from None


def change_container_layout(*, draft, container_id: int, layout_key: str) -> StorefrontContainer:
    """R4 Task 7 (Batch 1) — multi-column composition, wired to the EXACT
    SAME canonical service the legacy editor's own layout-preset UI already
    uses (``container_service.change_container_layout``): content-preserving
    grow/shrink, never a second implementation of the merge-on-shrink/
    locked-container rules that already live there."""
    container = _scoped_container(draft, container_id)
    try:
        return container_service.change_container_layout(container, layout_key)
    except container_service.ContainerLayoutError as exc:
        raise SectionStructureError("invalid_container_layout") from exc


def build_structure_projection(page) -> list[dict]:
    """The exact visual order Preview renders: Container.order -> Cell.order
    -> Block.cell_order. A purely-read projection — never mutates the page
    (no ``ensure_page_containers`` call here; callers that need placement
    initialized first must do that themselves before calling this)."""
    containers = list(
        page.containers.order_by("order", "id")
        .prefetch_related("cells__section", "cells__blocks")
    )
    items: list[dict] = []
    seen_ids: set[int] = set()
    for container in containers:
        cells = sorted(container.cells.all(), key=lambda c: (c.order, c.id))
        for cell in cells:
            for block in container_service.blocks_from_prefetched_cell(cell):
                items.append({"section": block, "container": container, "cell": cell})
                seen_ids.add(block.pk)
    # Compatibility fallback: a genuinely unplaced legacy Section (should
    # not exist after ensure_page_containers, but the projection stays
    # correct even if one slips through) is appended in page-level order.
    for section in page.sections.order_by("order", "id"):
        if section.pk not in seen_ids:
            items.append({"section": section, "container": None, "cell": None})
            seen_ids.add(section.pk)
    return items


def move_section(*, draft, section_id: int, direction: str) -> None:
    if direction not in ("up", "down"):
        raise SectionStructureError("invalid_direction")

    section = _scoped_section(draft, section_id)
    if section.is_locked:
        raise SectionStructureError("section_locked")

    page = section.page
    container_service.ensure_page_containers(page)
    section.refresh_from_db()

    projection = build_structure_projection(page)
    index = next((i for i, item in enumerate(projection) if item["section"].pk == section.pk), None)
    if index is None:
        raise SectionStructureError("section_not_found")

    adjacent_index = index - 1 if direction == "up" else index + 1
    if adjacent_index < 0 or adjacent_index >= len(projection):
        raise SectionStructureError("move_boundary")

    source_item = projection[index]
    target_item = projection[adjacent_index]
    target_section = target_item["section"]

    if target_section.is_locked:
        raise SectionStructureError("target_locked")

    source_cell = source_item["cell"]
    target_cell = target_item["cell"]
    source_container = source_item["container"]
    target_container = target_item["container"]
    if source_cell is None or target_cell is None:
        raise SectionStructureError("unsupported_placement")

    if source_container.is_locked:
        raise SectionStructureError("container_locked")
    if target_container.is_locked:
        raise SectionStructureError("target_container_locked")

    source_blocks = container_service.get_cell_blocks(source_cell)
    target_blocks = container_service.get_cell_blocks(target_cell)
    source_index_in_cell = next(i for i, b in enumerate(source_blocks) if b.pk == section.pk)
    target_index_in_cell = next(i for i, b in enumerate(target_blocks) if b.pk == target_section.pk)

    # Legacy row-layout compatibility (Task 8 plan, Section 16): simulate
    # the page-level ``order`` swap and validate it BEFORE any structural
    # write. A move that would break a legacy composite row is rejected
    # whole — no partial Container/Cell mutation.
    simulated = list(page.sections.order_by("order", "id"))
    sim_source = next(s for s in simulated if s.pk == section.pk)
    sim_target = next(s for s in simulated if s.pk == target_section.pk)
    sim_source.order, sim_target.order = sim_target.order, sim_source.order
    try:
        row_service.validate_page_row_layout(sorted(simulated, key=lambda s: (s.order, s.id)))
    except row_service.RowAssignmentError:
        raise SectionStructureError("row_layout_invalid") from None

    # Atomic visual position swap: move source into target's former Cell at
    # target's former index, then move target into source's former Cell at
    # source's former index. For a same-Cell adjacent pair this collapses
    # into the exact same result a single reorder would give (the second
    # call is a harmless no-op reorder); for different Cells this is the
    # only sequence that avoids a moment where the destination Cell has to
    # hold both Blocks under a "just append" semantics permanently.
    container_service.move_block(section, target_cell, at_index=target_index_in_cell)
    container_service.move_block(target_section, source_cell, at_index=source_index_in_cell)

    StorefrontSection.objects.filter(pk=section.pk).update(order=sim_source.order)
    StorefrontSection.objects.filter(pk=target_section.pk).update(order=sim_target.order)
