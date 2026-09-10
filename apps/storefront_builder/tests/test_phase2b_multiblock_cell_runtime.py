"""Phase 2B — multi-block Cell runtime foundation regression tests.

Covers ``container_service.get_cell_blocks``/``add_block``/``remove_block``/
``move_block``/``reorder_block``/``reorder_blocks_in_cell`` (the new
multi-block-capable service operations, built on top of Phase 2A's additive
``StorefrontSection.cell``/``cell_order`` fields), plus the runtime-wide
consequences of a Cell being able to hold more than one ordered Block:
rendering (0/1/N Blocks, no duplicate rendering when the legacy OneToOne and
the new FK reference the same Section), cloning, edit-history snapshot/
restore (undo/redo), and ``content_fingerprint`` drift-detection.

Everything here is additive coverage on top of the already-passing Phase 2A
suite (``test_phase2a_cell_section_fk_foundation.py``) and the pre-existing
Container/Cell suites (``test_phase30_container_cell_foundation.py``,
``test_phase31_container_cell_builder.py``, ``test_phase31a_hidden_cell_semantics.py``,
``test_phase35a_publish_container_invariant.py``, extended separately in this
same batch) — none of those files' existing assertions are weakened; this
file only adds new scenarios that did not exist before Phase 2B.

Same sandbox constraint as every other test file in this app touched this
session: this environment has no Django installation and no network access
to install one (confirmed via direct ``pip``/``uv`` attempts against PyPI,
both blocked by the sandbox's ``INTEGRATIONS_ONLY`` network policy — 403
Forbidden through the proxy). Every test below was written and read carefully
against the real service/model source in this same session, and every
modified/new Python file was AST-syntax-checked, but none of this is a
substitute for actually running ``python manage.py test
apps.storefront_builder`` in a real Django environment — that verification
must happen after this push, exactly as it did for Phase 2A.
"""

from django.core.cache import cache
from django.test import TestCase

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import (
    container_service,
    edit_history_service,
    layout_service as svc,
    render_service,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class Phase2BTestCase(TestCase):
    """Shared setup — a clean HOME page with no legacy content, mirroring
    the exact ``setUp`` convention every other Container/Cell test file in
    this app already uses (see e.g. ``test_phase30_container_cell_foundation.py``)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self, order=0, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=order,
            settings={"body_html": f"section-{order}"},
            **kwargs,
        )


# ----------------------------------------------------------------------
# get_cell_blocks — the authoritative read path
# ----------------------------------------------------------------------

class GetCellBlocksTests(Phase2BTestCase):
    def test_empty_cell_returns_empty_list(self):
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        self.assertEqual(container_service.get_cell_blocks(cell), [])

    def test_legacy_single_block_cell_returns_that_one_section(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([b.pk for b in blocks], [section.pk])

    def test_new_fk_multi_block_cell_returns_all_in_cell_order(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        container_service.add_block(cell, button)

        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([b.pk for b in blocks], [heading.pk, text.pk, button.pk])

    def test_section_placed_via_both_relationships_is_returned_exactly_once(self):
        """The normal post-Phase-2A-backfill steady state: legacy
        ``cell.section`` and the new ``section.cell`` both point at the same
        Cell/Section. ``get_cell_blocks`` must never return it twice."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)
        # Simulate the Phase 2A migration backfill directly (bypassing the
        # service layer, exactly like the real migration's RunPython step
        # does) so both relationships legitimately agree.
        StorefrontSection.objects.filter(pk=section.pk).update(cell_id=cell.pk, cell_order=0)

        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([b.pk for b in blocks], [section.pk])
        self.assertEqual(len(blocks), 1)


# ----------------------------------------------------------------------
# add_block
# ----------------------------------------------------------------------

class AddBlockTests(Phase2BTestCase):
    def test_add_first_block_to_empty_cell(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        container_service.add_block(cell, section)

        section.refresh_from_db()
        self.assertEqual(section.cell_id, cell.pk)
        self.assertEqual(section.cell_order, 0)

    def test_add_second_block_appends_after_first(self):
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, first)

        container_service.add_block(cell, second)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.cell_order, 0)
        self.assertEqual(second.cell_order, 1)
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [first.pk, second.pk],
        )

    def test_add_third_block_at_explicit_index_shifts_siblings(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        button = self._section(2)

        container_service.add_block(cell, button, at_index=1)

        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [heading.pk, button.pk, text.pk],
        )

    def test_add_block_to_already_occupied_cell_does_not_error(self):
        """Unlike ``place_section``, adding to an occupied Cell is the whole
        point of this operation, not an error."""
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, first)

        container_service.add_block(cell, second)  # must not raise

        self.assertEqual(len(container_service.get_cell_blocks(cell)), 2)

    def test_add_block_adopts_cells_own_legacy_content_at_position_zero(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        result = container_service.add_block(cell, section)

        self.assertEqual(result.pk, section.pk)
        section.refresh_from_db()
        self.assertEqual(section.cell_id, cell.pk)
        self.assertEqual(section.cell_order, 0)
        # No duplicate — still exactly one Block in this Cell.
        self.assertEqual(len(container_service.get_cell_blocks(cell)), 1)

    def test_add_block_rejects_cross_page_section(self):
        other_page = self.draft.get_page(StorefrontPage.PageType.SEARCH)
        foreign_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0, settings={},
        )
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.add_block(cell, foreign_section)

    def test_add_block_rejects_locked_container(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        cell = container.cells.get()

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.add_block(cell, section)

    def test_add_block_clears_stale_legacy_pointer_when_moving_from_another_cell(self):
        """If a Section's legacy ``placement_cell`` still points at a
        *different* Cell than the one it's being newly added to via the new
        FK, that stale legacy pointer must be cleared — otherwise the
        vacated Cell's ``get_cell_blocks`` could resurrect it."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.place_section(cell_a, section)  # legacy pointer -> cell_a

        container_service.add_block(cell_b, section)  # new FK -> cell_b

        cell_a.refresh_from_db()
        self.assertIsNone(cell_a.section_id, "stale legacy pointer at the vacated Cell must be cleared")
        self.assertEqual(container_service.get_cell_blocks(cell_a), [])
        self.assertEqual([b.pk for b in container_service.get_cell_blocks(cell_b)], [section.pk])


# ----------------------------------------------------------------------
# remove_block
# ----------------------------------------------------------------------

class RemoveBlockTests(Phase2BTestCase):
    def test_remove_one_block_leaves_cell_and_container_and_other_blocks_intact(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)
        container_sid = container.stable_id
        cell_sid = cell.stable_id

        container_service.remove_block(text)

        self.assertTrue(self.page.containers.filter(stable_id=container_sid).exists())
        self.assertTrue(container.cells.filter(stable_id=cell_sid).exists())
        self.assertTrue(StorefrontSection.objects.filter(pk=text.pk).exists(), "remove_block must never delete the Section")
        text.refresh_from_db()
        self.assertIsNone(text.cell_id)
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [heading.pk, button.pk],
        )

    def test_remove_block_compacts_remaining_cell_order_with_no_gaps(self):
        first = self._section(0)
        second = self._section(1)
        third = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (first, second, third):
            container_service.add_block(cell, section)

        container_service.remove_block(first)

        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(second.cell_order, 0)
        self.assertEqual(third.cell_order, 1)

    def test_remove_block_on_legacy_only_placement_clears_legacy_pointer_too(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        container_service.remove_block(section)

        cell.refresh_from_db()
        self.assertIsNone(cell.section_id)
        self.assertEqual(container_service.get_cell_blocks(cell), [])

    def test_remove_block_on_unplaced_section_is_a_safe_noop(self):
        section = self._section()
        container_service.remove_block(section)  # must not raise
        section.refresh_from_db()
        self.assertIsNone(section.cell_id)


# ----------------------------------------------------------------------
# move_block — Cell A -> Cell B
# ----------------------------------------------------------------------

class MoveBlockTests(Phase2BTestCase):
    def test_move_block_between_cells_preserves_identity(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, section)
        stable_id = section.stable_id
        pk = section.pk

        container_service.move_block(section, cell_b)

        section.refresh_from_db()
        self.assertEqual(section.pk, pk)
        self.assertEqual(section.stable_id, stable_id)
        self.assertEqual(section.cell_id, cell_b.pk)
        self.assertEqual(container_service.get_cell_blocks(cell_a), [])
        self.assertEqual([b.pk for b in container_service.get_cell_blocks(cell_b)], [section.pk])

    def test_move_block_compacts_source_cell_siblings(self):
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, first)
        container_service.add_block(cell_a, second)

        container_service.move_block(first, cell_b)

        second.refresh_from_db()
        self.assertEqual(second.cell_order, 0)

    def test_move_block_into_a_cell_that_already_has_blocks_appends(self):
        moving = self._section(0)
        existing = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, moving)
        container_service.add_block(cell_b, existing)

        container_service.move_block(moving, cell_b)

        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell_b)],
            [existing.pk, moving.pk],
        )

    def test_move_block_rejects_cross_page_target(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, section)

        other_page = self.draft.get_page(StorefrontPage.PageType.SEARCH)
        other_container = container_service.create_empty_container(other_page, "single")
        foreign_cell = other_container.cells.get()

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.move_block(section, foreign_cell)

    def test_move_block_rejects_locked_source_container(self):
        """R4 Task 8 (Batch 2, lifecycle-lock parity) — before this fix,
        ``move_block`` only checked the TARGET Cell's Container lock; a
        Block could be moved OUT of a locked source Container by simply
        targeting an unlocked one. The source side must be checked too."""
        section = self._section()
        source_container = container_service.create_empty_container(self.page, "single")
        source_cell = source_container.cells.get()
        container_service.add_block(source_cell, section)
        source_container.is_locked = True
        source_container.save(update_fields=["is_locked"])

        target_container = container_service.create_empty_container(self.page, "single")
        target_cell = target_container.cells.get()

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.move_block(section, target_cell)
        section.refresh_from_db()
        self.assertEqual(section.cell_id, source_cell.pk)

    def test_move_block_within_same_cell_is_a_reorder(self):
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, first)
        container_service.add_block(cell, second)

        container_service.move_block(first, cell, at_index=1)

        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [second.pk, first.pk],
        )


# ----------------------------------------------------------------------
# reorder_block / reorder_blocks_in_cell
# ----------------------------------------------------------------------

class ReorderBlocksTests(Phase2BTestCase):
    def test_reorder_blocks_in_cell_applies_exact_new_order(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        container_service.reorder_blocks_in_cell(cell, [heading.pk, button.pk, text.pk])

        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [heading.pk, button.pk, text.pk],
        )

    def test_reorder_blocks_in_cell_rejects_partial_list(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.reorder_blocks_in_cell(cell, [heading.pk])

    def test_reorder_blocks_in_cell_rejects_foreign_section_id(self):
        heading = self._section(0)
        text = self._section(1)
        other_page = self.draft.get_page(StorefrontPage.PageType.SEARCH)
        foreign = StorefrontSection.objects.create(page=other_page, section_key="rich_text", order=0, settings={})
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.reorder_blocks_in_cell(cell, [heading.pk, foreign.pk])

    def test_reorder_blocks_in_cell_rejects_duplicate_ids(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.reorder_blocks_in_cell(cell, [heading.pk, heading.pk])

    def test_reorder_block_single_item_moves_to_requested_position(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        container_service.reorder_block(button, at_index=0)

        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [button.pk, heading.pk, text.pk],
        )


# ----------------------------------------------------------------------
# Rendering — 0 / 1 / N Blocks per Cell, no duplicate rendering
# ----------------------------------------------------------------------

class MultiBlockRenderingTests(Phase2BTestCase):
    def _render_cell_entry(self):
        items = render_service.build_page_render_items(self.page, self.store)
        rendered = render_service.build_container_render_items(self.page, items, include_empty=True)
        return rendered[0]["cells"][0]

    def test_zero_blocks_renders_no_items(self):
        container_service.create_empty_container(self.page, "single")

        cell_entry = self._render_cell_entry()

        self.assertEqual(cell_entry["items"], [])
        self.assertIsNone(cell_entry["item"])

    def test_one_block_renders_exactly_one_item_matching_pre_phase2b_contract(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        cell_entry = self._render_cell_entry()

        self.assertEqual(len(cell_entry["items"]), 1)
        self.assertEqual(cell_entry["items"][0]["section"].pk, section.pk)
        # The pre-Phase-2B singular "item" contract every existing consumer
        # depends on must still resolve to the same (now: first) item.
        self.assertIs(cell_entry["item"], cell_entry["items"][0])

    def test_three_blocks_render_all_in_cell_order(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        cell_entry = self._render_cell_entry()

        self.assertEqual(
            [item["section"].pk for item in cell_entry["items"]],
            [heading.pk, text.pk, button.pk],
        )

    def test_no_duplicate_rendering_when_legacy_and_new_relationship_reference_same_section(self):
        """The exact scenario the owner's spec calls out by name: after the
        Phase 2A backfill, ``cell.section == Section A`` and
        ``Section A.cell == cell`` simultaneously — Section A must render
        exactly once, never twice."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)
        StorefrontSection.objects.filter(pk=section.pk).update(cell_id=cell.pk, cell_order=0)

        cell_entry = self._render_cell_entry()

        self.assertEqual(len(cell_entry["items"]), 1)
        self.assertEqual(cell_entry["items"][0]["section"].pk, section.pk)

    def test_inactive_block_is_excluded_from_items_but_counted_in_blocks(self):
        visible = self._section(0)
        hidden = self._section(1, is_active=False)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, visible)
        container_service.add_block(cell, hidden)

        cell_entry = self._render_cell_entry()

        self.assertEqual([item["section"].pk for item in cell_entry["items"]], [visible.pk])
        self.assertEqual({b.pk for b in cell_entry["blocks"]}, {visible.pk, hidden.pk})


# ----------------------------------------------------------------------
# Clone (Draft creation from Published, Restore)
# ----------------------------------------------------------------------

class CloneMultiBlockCellTests(Phase2BTestCase):
    def test_clone_preserves_multi_block_composition_and_order(self):
        from apps.storefront_builder.models import StorefrontLayoutVersion
        from apps.storefront_builder.services import layout_service

        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        target = StorefrontLayoutVersion.objects.create(
            layout=self.draft.layout,
            version_number=self.draft.version_number + 5000,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
        layout_service._clone_version_content(self.draft, target)

        target_page = target.get_page(StorefrontPage.PageType.HOME)
        target_container = target_page.containers.get(stable_id=container.stable_id)
        target_cell = target_container.cells.get(stable_id=cell.stable_id)
        cloned_blocks = container_service.get_cell_blocks(target_cell)
        self.assertEqual(len(cloned_blocks), 3)
        self.assertEqual(
            [b.stable_id for b in cloned_blocks],
            [heading.stable_id, text.stable_id, button.stable_id],
        )
        # Cloned identity: new PKs, same stable_ids — the existing, unchanged
        # clone-identity contract this codebase already guarantees for the
        # legacy single-block path.
        self.assertNotEqual({b.pk for b in cloned_blocks}, {heading.pk, text.pk, button.pk})

    def test_clone_preserves_empty_cell_alongside_a_multi_block_cell(self):
        from apps.storefront_builder.models import StorefrontLayoutVersion
        from apps.storefront_builder.services import layout_service

        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, first)
        container_service.add_block(cell_a, second)
        # cell_b intentionally stays empty.

        target = StorefrontLayoutVersion.objects.create(
            layout=self.draft.layout,
            version_number=self.draft.version_number + 5001,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
        layout_service._clone_version_content(self.draft, target)

        target_page = target.get_page(StorefrontPage.PageType.HOME)
        target_container = target_page.containers.get(stable_id=container.stable_id)
        cloned_cell_a = target_container.cells.get(stable_id=cell_a.stable_id)
        cloned_cell_b = target_container.cells.get(stable_id=cell_b.stable_id)
        self.assertEqual(len(container_service.get_cell_blocks(cloned_cell_a)), 2)
        self.assertEqual(container_service.get_cell_blocks(cloned_cell_b), [])


# ----------------------------------------------------------------------
# Edit-history snapshot / restore (Undo / Redo)
# ----------------------------------------------------------------------

class MultiBlockHistoryTests(Phase2BTestCase):
    def test_snapshot_captures_multi_block_composition(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        snapshot = edit_history_service.snapshot_draft(self.draft)

        home_containers = snapshot["containers"]["home"]
        cell_data = home_containers[0]["cells"][0]
        self.assertEqual(
            [b["section_stable_id"] for b in cell_data["blocks"]],
            [str(heading.stable_id), str(text.stable_id)],
        )

    def test_undo_restores_previous_two_block_composition_after_a_third_is_added(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        before_state = edit_history_service.snapshot_draft(self.draft)
        button = self._section(2)
        container_service.add_block(cell, button)
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="افزودن بلاک", before_state=before_state,
        )
        self.assertEqual(len(container_service.get_cell_blocks(cell)), 3)

        edit_history_service.undo(self.draft)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        restored_blocks = container_service.get_cell_blocks(restored_cell)
        self.assertEqual([b.stable_id for b in restored_blocks], [heading.stable_id, text.stable_id])

    def test_redo_reapplies_the_undone_third_block(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        before_state = edit_history_service.snapshot_draft(self.draft)
        button = self._section(2)
        button_stable_id = button.stable_id
        container_service.add_block(cell, button)
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="افزودن بلاک", before_state=before_state,
        )

        edit_history_service.undo(self.draft)
        edit_history_service.redo(self.draft)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        restored_blocks = container_service.get_cell_blocks(restored_cell)
        self.assertEqual(
            [b.stable_id for b in restored_blocks],
            [heading.stable_id, text.stable_id, button_stable_id],
        )

    def test_undo_restores_previous_block_order_after_a_reorder(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)
        before_state = edit_history_service.snapshot_draft(self.draft)

        container_service.reorder_blocks_in_cell(cell, [heading.pk, button.pk, text.pk])
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="تغییر ترتیب", before_state=before_state,
        )
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cell)],
            [heading.pk, button.pk, text.pk],
        )

        edit_history_service.undo(self.draft)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        restored_order = [b.stable_id for b in container_service.get_cell_blocks(restored_cell)]
        self.assertEqual(restored_order, [heading.stable_id, text.stable_id, button.stable_id])

    def test_old_history_entry_without_blocks_key_restores_unchanged(self):
        """Backward compatibility: a history entry recorded before Phase 2B
        never has a "blocks" key inside its per-cell snapshot at all — restoring
        it must not crash and must not invent any multi-block FK placement."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        old_style_state = edit_history_service.snapshot_draft(self.draft)
        # Simulate a pre-Phase-2B snapshot by stripping the new key from
        # every cell entry, exactly as a real old history row would be.
        for containers in old_style_state["containers"].values():
            for container_data in containers:
                for cell_data in container_data["cells"]:
                    cell_data.pop("blocks", None)

        edit_history_service.restore_draft_state(self.draft, old_style_state)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        self.assertEqual(restored_cell.section_id, section.pk)
        self.assertIsNone(
            StorefrontSection.objects.get(pk=section.pk).cell_id,
            "restoring an old-style snapshot must never invent a new-FK placement that was never recorded",
        )


# ----------------------------------------------------------------------
# content_fingerprint drift-detection
# ----------------------------------------------------------------------

class MultiBlockFingerprintTests(Phase2BTestCase):
    def test_fingerprint_changes_when_a_block_is_added(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, section)
        before = self.draft.compute_fingerprint()

        second = self._section(1)
        container_service.add_block(cell, second)

        after = self.draft.compute_fingerprint()
        self.assertNotEqual(before, after)

    def test_fingerprint_differs_between_two_block_orderings(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        heading_then_text = self.draft.compute_fingerprint()

        container_service.reorder_blocks_in_cell(cell, [text.pk, heading.pk])

        text_then_heading = self.draft.compute_fingerprint()
        self.assertNotEqual(heading_then_text, text_then_heading)

    def test_fingerprint_differs_between_one_block_and_two_blocks(self):
        heading = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        one_block = self.draft.compute_fingerprint()

        button = self._section(1)
        container_service.add_block(cell, button)

        two_blocks = self.draft.compute_fingerprint()
        self.assertNotEqual(one_block, two_blocks)

    def test_fingerprint_stable_for_unchanged_multi_block_composition(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        fp1 = self.draft.compute_fingerprint()
        fp2 = self.draft.compute_fingerprint()
        self.assertEqual(fp1, fp2)



# ----------------------------------------------------------------------
# Real-environment fix follow-up — collision-safe reordering
# ----------------------------------------------------------------------
#
# A real Django+SQLite run of the original Phase 2B implementation
# reproduced ``IntegrityError: UNIQUE constraint failed:
# storefront_builder_storefrontsection.cell_id,
# storefront_builder_storefrontsection.cell_order`` for every one of these
# scenarios — a naive single ``bulk_update`` writing final ``cell_order``
# values directly (e.g. swapping two rows) can transiently collide with
# another row's still-old value mid-statement, on both SQLite and
# PostgreSQL, since neither guarantees a multi-row UPDATE applies "as if
# simultaneously". ``container_service._persist_cell_order`` (a temporary
# out-of-range scratch pass, then the real final pass, both inside the
# caller's ``transaction.atomic()``) is the single, reused fix — this class
# proves the exact scenarios that previously failed now succeed and leave
# every row's final ``cell_order`` normalized to exactly 0..N-1.


class CollisionSafeReorderTests(Phase2BTestCase):
    def _cell_order_values(self, cell):
        return list(
            container_service.StorefrontSection.objects.filter(cell_id=cell.pk)
            .order_by("cell_order")
            .values_list("cell_order", flat=True)
        )

    def test_swap_two_blocks_via_reorder_blocks_in_cell(self):
        a = self._section(0)
        b = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, a)
        container_service.add_block(cell, b)

        container_service.reorder_blocks_in_cell(cell, [b.pk, a.pk])  # must not raise IntegrityError

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [b.pk, a.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1])

    def test_reorder_three_blocks_full_reverse_via_reorder_blocks_in_cell(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        container_service.reorder_blocks_in_cell(cell, [button.pk, text.pk, heading.pk])

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [button.pk, text.pk, heading.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1, 2])

    def test_reorder_block_moves_first_to_last(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        container_service.reorder_block(heading, at_index=2)

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [text.pk, button.pk, heading.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1, 2])

    def test_reorder_block_moves_last_to_first(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        container_service.reorder_block(button, at_index=0)

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [button.pk, heading.pk, text.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1, 2])

    def test_repeated_reorder_stays_collision_free_and_normalized(self):
        heading = self._section(0)
        text = self._section(1)
        button = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (heading, text, button):
            container_service.add_block(cell, section)

        # Several reorders in a row on the same Cell — each one must
        # independently be collision-safe; none of them may raise.
        container_service.reorder_blocks_in_cell(cell, [text.pk, button.pk, heading.pk])
        container_service.reorder_blocks_in_cell(cell, [heading.pk, text.pk, button.pk])
        container_service.reorder_block(button, at_index=0)
        container_service.move_block(heading, cell, at_index=2)

        self.assertEqual(self._cell_order_values(cell), [0, 1, 2])
        self.assertEqual(len(container_service.get_cell_blocks(cell)), 3)

    def test_move_within_same_cell_swap_positions_is_collision_safe(self):
        first = self._section(0)
        second = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, first)
        container_service.add_block(cell, second)

        container_service.move_block(first, cell, at_index=1)  # same-cell reorder path

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [second.pk, first.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1])

    def test_add_block_insert_shift_is_collision_safe(self):
        """``add_block``'s insert-at-index path shifts every following
        sibling's ``cell_order`` up by one — also routed through the
        collision-safe helper now, proven here with 3 existing Blocks."""
        a = self._section(0)
        b = self._section(1)
        c = self._section(2)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        for section in (a, b, c):
            container_service.add_block(cell, section)
        d = self._section(3)

        container_service.add_block(cell, d, at_index=0)

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [d.pk, a.pk, b.pk, c.pk],
        )
        self.assertEqual(self._cell_order_values(cell), [0, 1, 2, 3])

    def test_fingerprint_changes_after_a_reorder_that_previously_would_have_raised(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        before = self.draft.compute_fingerprint()

        container_service.reorder_blocks_in_cell(cell, [text.pk, heading.pk])

        after = self.draft.compute_fingerprint()
        self.assertNotEqual(before, after)

    def test_undo_restores_order_after_a_swap_reorder(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        before_state = edit_history_service.snapshot_draft(self.draft)

        container_service.reorder_blocks_in_cell(cell, [text.pk, heading.pk])
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="جابه‌جایی", before_state=before_state,
        )
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)], [text.pk, heading.pk],
        )

        edit_history_service.undo(self.draft)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        self.assertEqual(
            [b.stable_id for b in container_service.get_cell_blocks(restored_cell)],
            [heading.stable_id, text.stable_id],
        )

    def test_redo_restores_reordered_state(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)
        before_state = edit_history_service.snapshot_draft(self.draft)
        container_service.reorder_blocks_in_cell(cell, [text.pk, heading.pk])
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="جابه‌جایی", before_state=before_state,
        )

        edit_history_service.undo(self.draft)
        edit_history_service.redo(self.draft)

        restored_cell = self.page.containers.get(stable_id=container.stable_id).cells.get(stable_id=cell.stable_id)
        self.assertEqual(
            [b.stable_id for b in container_service.get_cell_blocks(restored_cell)],
            [text.stable_id, heading.stable_id],
        )


# ----------------------------------------------------------------------
# Real-environment fix follow-up — legacy write / new read synchronization
# ----------------------------------------------------------------------
#
# ``place_section`` is the exact write path the current Builder UI uses
# (``views.storefront_cell_add_section``); ``storefront_cell_clear`` (the
# view) deletes the Section outright rather than merely detaching it. These
# tests prove the ACTUAL supported legacy workflows leave ``get_cell_blocks``
# — the new authoritative read path — never disagreeing with what the
# legacy write just established, and never resurrecting a Section the
# legacy write believes has been replaced/removed.


class LegacyWriteNewReadSynchronizationTests(Phase2BTestCase):
    def test_scenario_a_replacing_content_via_place_section_does_not_resurrect_old_block(self):
        """Start: cell.section = X, X.cell = cell (normal mirrored state).
        Supported current workflow for "replace this Cell's content": clear
        the old content, then place the new one — exactly what the real
        Builder UI's two endpoints (``storefront_cell_clear`` then
        ``storefront_cell_add_section``) do in sequence. Final state must be
        get_cell_blocks(cell) == [Y], with X no longer an active Block of
        this Cell."""
        x = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, x)
        self.assertEqual(container_service.get_cell_blocks(cell), [x])

        # Actual supported legacy workflow: the real cell-clear service path
        # (mirrors views.storefront_cell_clear exactly: delete the Section,
        # relying on StorefrontCell.section's SET_NULL) ...
        x.delete()
        cell.refresh_from_db()
        self.assertIsNone(cell.section_id)
        # ... then place_section the new content.
        y = self._section(1)
        container_service.place_section(cell, y)

        self.assertEqual(container_service.get_cell_blocks(cell), [y])
        self.assertFalse(StorefrontSection.objects.filter(pk=x.pk).exists())

    def test_scenario_a_direct_place_section_replacement_never_leaves_two_sources_of_truth(self):
        """A second, even more direct variant of Scenario A: placing Y
        directly into a Cell that currently (via the new FK) holds X as one
        of several Blocks must detach X from this Cell so it cannot be
        resurrected — proving ``place_section``'s synchronization, not just
        the clear+place sequence above."""
        x = self._section(0)
        y = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, x)  # X becomes a new-FK Block of this Cell

        container_service.place_section(cell, y)

        self.assertEqual(container_service.get_cell_blocks(cell), [y])
        x.refresh_from_db()
        self.assertIsNone(x.cell_id, "X must no longer be attached to this Cell through the new FK")
        # X still exists (place_section never deletes) but is unattached.
        self.assertTrue(StorefrontSection.objects.filter(pk=x.pk).exists())

    def test_scenario_b_current_cell_clear_leaves_cell_empty_through_new_read_path(self):
        """Start: cell.section = X, X.cell = cell. Run the actual current
        Cell-clear behaviour (delete the Section — the real
        views.storefront_cell_clear path, ``StorefrontCell.section``'s
        SET_NULL does the rest). Expected: get_cell_blocks(cell) == [],
        Container and Cell remain alive."""
        x = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, x)
        container_sid = container.stable_id
        cell_sid = cell.stable_id

        x.delete()  # the real cell-clear view's exact mechanism

        cell.refresh_from_db()
        self.assertEqual(container_service.get_cell_blocks(cell), [])
        self.assertTrue(self.page.containers.filter(stable_id=container_sid).exists())
        self.assertTrue(container.cells.filter(stable_id=cell_sid).exists())

    def test_scenario_c_legacy_placement_into_empty_cell_is_immediately_visible(self):
        """Use the exact current write operation the Builder UI uses
        (``place_section``, called by ``storefront_cell_add_section``) on a
        genuinely empty Cell. Immediately afterward,
        get_cell_blocks(cell) must reliably return the newly placed
        Section — using the SAME ``cell`` Python instance the caller
        already had, not a freshly re-fetched one, since that is exactly
        how the real view code is structured."""
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        y = self._section(0)

        container_service.place_section(cell, y)

        self.assertEqual(container_service.get_cell_blocks(cell), [y])

    def test_scenario_d_mirrored_section_renders_exactly_once(self):
        """When cell.section = X and X.cell = cell (the normal state
        place_section now establishes), X must render exactly once — this
        preserves the already-passing no-duplicate-render guarantee under
        the corrected place_section."""
        x = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, x)

        blocks = container_service.get_cell_blocks(cell)

        self.assertEqual(blocks, [x])
        self.assertEqual(len(blocks), 1)

    def test_place_section_moves_section_from_a_different_cell_and_compacts_its_siblings(self):
        """If a Section is currently one of several new-FK Blocks in Cell A,
        and the legacy ``place_section`` places it into Cell B, Cell A's
        remaining Blocks must be compacted (0..N-1) exactly like
        ``remove_block``/``move_block`` already guarantee."""
        moving = self._section(0)
        sibling = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, moving)
        container_service.add_block(cell_a, sibling)

        container_service.place_section(cell_b, moving)

        sibling.refresh_from_db()
        self.assertEqual(sibling.cell_order, 0)
        self.assertEqual(container_service.get_cell_blocks(cell_a), [sibling])
        self.assertEqual(container_service.get_cell_blocks(cell_b), [moving])
