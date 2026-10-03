"""Phase 2C — runtime transition + content-preserving layout changes.

Covers:

1. Merge-on-shrink: ``container_service.change_container_layout`` reducing
   the number of Cells must NEVER silently destroy content (the approved
   V3 prototype's ``applyLayout()`` requirement) — every removed Cell's
   Blocks (visible, hidden, and inactive alike) are moved into the last
   surviving Cell, preserving relative order, with the collision-safe
   ``_persist_cell_placement``/``_persist_cell_order`` primitives proven in
   Phase 2B (never a second, unsafe reorder implementation).
2. Expansion: growing the Cell count never redistributes existing content —
   new Cells are always created empty.
3. Same-Cell-count ratio changes: content never moves between Cells merely
   because spans changed.
4. Undo/redo of a layout change (including a merge) as ONE logical history
   step.
5. Clone/Publish/Restore preserve merged Block membership and order.
6. ``content_fingerprint`` reacts to composition changes caused by a merge.
7. ``clear_cell`` (the new multi-block "clear this whole Cell" primitive,
   distinct from ``remove_block``'s "remove exactly one Block").
8. Explicit runtime-source-of-truth proofs: the new FK composition model
   works correctly even for Cells whose only prior content lived through
   the legacy OneToOne, the legacy fallback still works for genuinely
   untouched old-style rows, and no legacy write path can leave a stale/
   contradictory pointer that resurrects removed content.

Everything here is additive on top of the already-passing Phase 2A/2B
suites; none of those files' existing assertions are weakened. The two
pre-existing tests that asserted the now-superseded Phase 2B "refuse to
shrink when trailing content exists" behaviour were updated in place (not
deleted) in ``test_phase31_container_cell_builder.py`` and
``test_phase31a_hidden_cell_semantics.py``, each with an explicit docstring
explaining why the approved V3 prototype requirement supersedes that
behaviour.

Same sandbox constraint as every other test file touched this session:
this environment has no Django installation and no network access to
install one. Every test below was written and read carefully against the
real service/model source in this session, and every modified/new Python
file was AST-syntax-checked, but this is not a substitute for a real
``python manage.py test apps.storefront_builder`` run — that verification
must happen after this push, exactly as it did for Phases 2A and 2B.
"""

from django.core.cache import cache
from django.test import TestCase

from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import (
    container_service,
    edit_history_service,
    layout_service as svc,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class Phase2CTestCase(TestCase):
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
# Merge-on-shrink
# ----------------------------------------------------------------------

class MergeOnShrinkTests(Phase2CTestCase):
    def test_2_cells_to_1_preserves_multi_block_cells_in_relative_order(self):
        """Container example from the spec: Cell 1 (Brands-equivalent,
        single Block), Cell 2 (Heading, Text, Button — 3 Blocks). Shrinking
        50/50 -> 100% must merge Cell 2's Blocks after Cell 1's, in order."""
        brands = self._section(0)
        heading = self._section(1)
        text = self._section(2)
        button = self._section(3)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, brands)
        container_service.add_block(cell_2, heading)
        container_service.add_block(cell_2, text)
        container_service.add_block(cell_2, button)

        container_service.change_container_layout(container, "single")

        container.refresh_from_db()
        remaining = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(remaining), 1)
        survivor = remaining[0]
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(survivor)],
            [brands.pk, heading.pk, text.pk, button.pk],
        )
        self.assertEqual(
            [b.cell_order for b in container_service.get_cell_blocks(survivor)],
            [0, 1, 2, 3],
        )

    def test_4_cells_to_2_merges_removed_cells_into_last_surviving_cell(self):
        """Exact example from the spec: A(A1,A2) B(B1,B2) C(C1) D(D1,D2),
        shrink 4->2. Expected: Cell A unchanged; Cell B gets B1,B2,C1,D1,D2
        appended in that order."""
        a1, a2 = self._section(0), self._section(1)
        b1, b2 = self._section(2), self._section(3)
        c1 = self._section(4)
        d1, d2 = self._section(5), self._section(6)
        container = container_service.create_empty_container(self.page, "quarters")
        cell_a, cell_b, cell_c, cell_d = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, a1)
        container_service.add_block(cell_a, a2)
        container_service.add_block(cell_b, b1)
        container_service.add_block(cell_b, b2)
        container_service.add_block(cell_c, c1)
        container_service.add_block(cell_d, d1)
        container_service.add_block(cell_d, d2)

        container_service.change_container_layout(container, "half")

        container.refresh_from_db()
        remaining = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(remaining), 2)
        survivor_a, survivor_b = remaining
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(survivor_a)],
            [a1.pk, a2.pk],
        )
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(survivor_b)],
            [b1.pk, b2.pk, c1.pk, d1.pk, d2.pk],
        )
        self.assertEqual(
            [b.cell_order for b in container_service.get_cell_blocks(survivor_b)],
            [0, 1, 2, 3, 4],
        )

    def test_4_cells_to_1_merges_every_cell_in_original_order(self):
        a1 = self._section(0)
        b1, b2 = self._section(1), self._section(2)
        c1 = self._section(3)
        d1 = self._section(4)
        container = container_service.create_empty_container(self.page, "quarters")
        cell_a, cell_b, cell_c, cell_d = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, a1)
        container_service.add_block(cell_b, b1)
        container_service.add_block(cell_b, b2)
        container_service.add_block(cell_c, c1)
        container_service.add_block(cell_d, d1)

        container_service.change_container_layout(container, "single")

        container.refresh_from_db()
        remaining = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(remaining), 1)
        blocks = container_service.get_cell_blocks(remaining[0])
        self.assertEqual([b.pk for b in blocks], [a1.pk, b1.pk, b2.pk, c1.pk, d1.pk])
        self.assertEqual([b.cell_order for b in blocks], [0, 1, 2, 3, 4])

    def test_final_orders_normalized_after_merge(self):
        first = self._section(0)
        second = self._section(1)
        third = self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, first)
        container_service.add_block(cell_b, second)
        container_service.add_block(cell_b, third)

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        orders = list(
            StorefrontSection.objects.filter(cell_id=survivor.pk)
            .order_by("cell_order")
            .values_list("cell_order", flat=True)
        )
        self.assertEqual(orders, [0, 1, 2])

    def test_hidden_content_survives_merge(self):
        visible = self._section(0)
        hidden = self._section(1, is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, visible)
        container_service.add_block(cell_b, hidden)

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        blocks = container_service.get_cell_blocks(survivor)
        self.assertEqual([b.pk for b in blocks], [visible.pk, hidden.pk])
        hidden.refresh_from_db()
        self.assertFalse(hidden.is_active, "merge must never change is_active")
        self.assertTrue(StorefrontSection.objects.filter(pk=hidden.pk).exists())

    def test_inactive_content_survives_merge_per_existing_persistence_semantics(self):
        """'Inactive' here means the same ``is_active=False`` semantics
        already established by Phase 31A — this is not a new state, just
        proof the merge treats it identically to 'hidden' (both survive)."""
        active = self._section(0)
        inactive = self._section(1, is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, inactive)
        container_service.add_block(cell_b, active)

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        blocks = container_service.get_cell_blocks(survivor)
        self.assertEqual({b.pk for b in blocks}, {active.pk, inactive.pk})

    def test_empty_removed_cells_shrink_safely_with_no_merge_needed(self):
        occupied = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, occupied)
        # cell_b intentionally stays empty.

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(survivor)],
            [occupied.pk],
        )

    def test_merge_adopts_legacy_only_content_into_new_fk(self):
        """A Cell whose content was placed only through the legacy
        ``place_section`` OneToOne path (never touched by any Phase 2B
        multi-block operation) must still be correctly picked up and
        merged — proving the merge uses ``get_cell_blocks`` (the
        authoritative read path), not a raw new-FK-only query."""
        legacy_only = self._section(0)
        new_fk = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.place_section(cell_a, legacy_only)  # legacy path
        container_service.add_block(cell_b, new_fk)  # new FK path

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(survivor)],
            [legacy_only.pk, new_fk.pk],
        )
        legacy_only.refresh_from_db()
        self.assertEqual(legacy_only.cell_id, survivor.pk, "merge must adopt legacy-only content into the new FK")


# ----------------------------------------------------------------------
# Expansion
# ----------------------------------------------------------------------

class ExpansionPreservesContentTests(Phase2CTestCase):
    def test_1_to_2_expansion_keeps_content_in_first_cell_second_is_empty(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        container_service.change_container_layout(container, "half")

        container.refresh_from_db()
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(cells), 2)
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells[0])],
            [heading.pk, text.pk],
        )
        self.assertEqual(container_service.get_cell_blocks(cells[1]), [])

    def test_1_to_4_expansion_keeps_content_in_first_cell_rest_are_empty(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, section)

        container_service.change_container_layout(container, "quarters")

        container.refresh_from_db()
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual(len(cells), 4)
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells[0])],
            [section.pk],
        )
        for cell in cells[1:]:
            self.assertEqual(container_service.get_cell_blocks(cell), [])


# ----------------------------------------------------------------------
# Same Cell-count ratio changes
# ----------------------------------------------------------------------

class RatioChangeSameCellCountTests(Phase2CTestCase):
    def test_50_50_to_33_67_does_not_move_content_between_cells(self):
        left_content = self._section(0)
        right_content = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_left, cell_right = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_left, left_content)
        container_service.add_block(cell_right, right_content)
        left_sid, right_sid = cell_left.stable_id, cell_right.stable_id

        container_service.change_container_layout(container, "quarter_left")

        container.refresh_from_db()
        cells_by_sid = {c.stable_id: c for c in container.cells.all()}
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells_by_sid[left_sid])],
            [left_content.pk],
        )
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells_by_sid[right_sid])],
            [right_content.pk],
        )
        self.assertEqual(cells_by_sid[left_sid].span, 3)
        self.assertEqual(cells_by_sid[right_sid].span, 9)

    def test_25_75_to_67_33_does_not_swap_content(self):
        left_content = self._section(0)
        right_content = self._section(1)
        container = container_service.create_empty_container(self.page, "quarter_left")
        cell_left, cell_right = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_left, left_content)
        container_service.add_block(cell_right, right_content)
        left_sid, right_sid = cell_left.stable_id, cell_right.stable_id

        container_service.change_container_layout(container, "third_right")

        container.refresh_from_db()
        cells_by_sid = {c.stable_id: c for c in container.cells.all()}
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells_by_sid[left_sid])],
            [left_content.pk],
        )
        self.assertEqual(
            [b.pk for b in container_service.get_cell_blocks(cells_by_sid[right_sid])],
            [right_content.pk],
        )


# ----------------------------------------------------------------------
# Undo / Redo of a merge-on-shrink layout change
# ----------------------------------------------------------------------

class MergeUndoRedoTests(Phase2CTestCase):
    def test_shrink_is_one_history_step_and_undo_restores_removed_cell_and_blocks(self):
        a = self._section(0)
        b = self._section(1)
        c = self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.add_block(cell_2, c)
        container_sid = container.stable_id
        cell_1_sid, cell_2_sid = cell_1.stable_id, cell_2.stable_id
        before_state = edit_history_service.snapshot_draft(self.draft)

        container_service.change_container_layout(container, "single")
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="تغییر شکل چیدمان", before_state=before_state,
        )
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

        edit_history_service.undo(self.draft)

        restored_container = self.page.containers.get(stable_id=container_sid)
        restored_cells = list(restored_container.cells.order_by("order", "id"))
        self.assertEqual(len(restored_cells), 2)
        restored_by_sid = {c.stable_id: c for c in restored_cells}
        self.assertIn(cell_1_sid, restored_by_sid)
        self.assertIn(cell_2_sid, restored_by_sid)
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(restored_by_sid[cell_1_sid])],
            [a.pk],
        )
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(restored_by_sid[cell_2_sid])],
            [b.pk, c.pk],
        )

    def test_redo_reapplies_the_merge_with_exact_block_order(self):
        a = self._section(0)
        b = self._section(1)
        c = self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.add_block(cell_2, c)
        container_sid = container.stable_id
        before_state = edit_history_service.snapshot_draft(self.draft)
        container_service.change_container_layout(container, "single")
        edit_history_service.record_change(
            draft=self.draft, actor=None, action_label="تغییر شکل چیدمان", before_state=before_state,
        )

        edit_history_service.undo(self.draft)
        edit_history_service.redo(self.draft)

        restored_container = self.page.containers.get(stable_id=container_sid)
        restored_cells = list(restored_container.cells.order_by("order", "id"))
        self.assertEqual(len(restored_cells), 1)
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(restored_cells[0])],
            [a.pk, b.pk, c.pk],
        )


# ----------------------------------------------------------------------
# Clone / Publish / Restore preserve merged Blocks
# ----------------------------------------------------------------------

class MergePersistenceLifecycleTests(Phase2CTestCase):
    def test_clone_preserves_merged_composition(self):
        a = self._section(0)
        b = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.change_container_layout(container, "single")
        survivor = container.cells.get()

        target = StorefrontLayoutVersion.objects.create(
            layout=self.draft.layout,
            version_number=self.draft.version_number + 7000,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
        svc._clone_version_content(self.draft, target)

        target_page = target.get_page(StorefrontPage.PageType.HOME)
        target_container = target_page.containers.get(stable_id=container.stable_id)
        target_cell = target_container.cells.get(stable_id=survivor.stable_id)
        cloned = container_service.get_cell_blocks(target_cell)
        self.assertEqual([x.stable_id for x in cloned], [a.stable_id, b.stable_id])

    def test_publish_preserves_merged_blocks_with_no_orphan_or_duplicate(self):
        a = self._section(0)
        b = self._section(1)
        c = self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.add_block(cell_2, c)

        container_service.change_container_layout(container, "single")
        published = svc.publish(self.store)

        published_page = published.get_page(StorefrontPage.PageType.HOME)
        published_container = published_page.containers.get()
        published_cell = published_container.cells.get()
        blocks = container_service.get_cell_blocks(published_cell)
        self.assertEqual({x.stable_id for x in blocks}, {a.stable_id, b.stable_id, c.stable_id})
        self.assertEqual(len(blocks), 3, "no duplicate Block")
        # No orphan: every one of the three original Sections is still
        # attached to exactly the one surviving Cell.
        for section in (a, b, c):
            section.refresh_from_db()
            self.assertEqual(section.cell_id, published_cell.pk)

    def test_restore_preserves_merged_blocks(self):
        a = self._section(0)
        b = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.change_container_layout(container, "single")
        published = svc.publish(self.store)
        published_version_id = published.pk

        # get_or_create_draft after a publish creates a fresh draft cloned
        # from the just-published version; restore_version instead always
        # creates its OWN new draft from the requested source version,
        # replacing any current draft (per its own docstring) — no need to
        # separately create/discard an intermediate draft first.
        restored_draft = svc.restore_version(self.store, published_version_id)

        restored_page = restored_draft.get_page(StorefrontPage.PageType.HOME)
        restored_container = restored_page.containers.get()
        restored_cell = restored_container.cells.get()
        blocks = container_service.get_cell_blocks(restored_cell)
        self.assertEqual({x.stable_id for x in blocks}, {a.stable_id, b.stable_id})


# ----------------------------------------------------------------------
# Fingerprint
# ----------------------------------------------------------------------

class MergeFingerprintTests(Phase2CTestCase):
    def test_fingerprint_changes_after_merge(self):
        a = self._section(0)
        b = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        before = self.draft.compute_fingerprint()

        container_service.change_container_layout(container, "single")

        after = self.draft.compute_fingerprint()
        self.assertNotEqual(before, after)

    def test_fingerprint_deterministic_for_same_final_composition(self):
        a = self._section(0)
        b = self._section(1)
        container = container_service.create_empty_container(self.page, "half")
        cell_1, cell_2 = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_1, a)
        container_service.add_block(cell_2, b)
        container_service.change_container_layout(container, "single")

        fp1 = self.draft.compute_fingerprint()
        fp2 = self.draft.compute_fingerprint()
        self.assertEqual(fp1, fp2)


# ----------------------------------------------------------------------
# clear_cell vs remove_block — distinct service-level operations
# ----------------------------------------------------------------------

class ClearCellTests(Phase2CTestCase):
    def test_clear_cell_detaches_every_block_but_never_deletes_sections(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        detached = container_service.clear_cell(cell)

        self.assertEqual({x.pk for x in detached}, {heading.pk, text.pk})
        self.assertEqual(container_service.get_cell_blocks(cell), [])
        for section in (heading, text):
            self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
            section.refresh_from_db()
            self.assertIsNone(section.cell_id)

    def test_clear_cell_on_legacy_only_content_also_detaches(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        detached = container_service.clear_cell(cell)

        self.assertEqual(detached, [section])
        cell.refresh_from_db()
        self.assertIsNone(cell.section_id)
        self.assertEqual(container_service.get_cell_blocks(cell), [])

    def test_clear_cell_rejects_when_any_block_is_locked(self):
        unlocked = self._section(0)
        locked = self._section(1, is_locked=True)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, unlocked)
        container_service.add_block(cell, locked)

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.clear_cell(cell)

        # All-or-nothing: nothing was detached.
        self.assertEqual(len(container_service.get_cell_blocks(cell)), 2)

    def test_clear_cell_is_distinct_from_remove_block_which_only_removes_one(self):
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        container_service.remove_block(heading)

        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [text.pk],
            "remove_block must only remove the one Block passed to it",
        )


# ----------------------------------------------------------------------
# Runtime source-of-truth: new FK is primary, legacy is fallback/mirror only
# ----------------------------------------------------------------------

class RuntimeSourceOfTruthTests(Phase2CTestCase):
    def test_new_fk_composition_works_when_legacy_pointer_is_absent(self):
        """A Cell whose Blocks were placed entirely through ``add_block``
        (never ``place_section``) has no legacy OneToOne pointer at all —
        the new FK alone must be sufficient."""
        heading = self._section(0)
        text = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, heading)
        container_service.add_block(cell, text)

        self.assertIsNone(cell.section_id, "no legacy pointer was ever written")
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(cell)],
            [heading.pk, text.pk],
        )

    def test_legacy_fallback_still_handles_a_true_old_style_row(self):
        """A Cell populated by directly assigning the legacy OneToOne
        (bypassing every Phase 2B/2C service function) — the exact shape a
        genuinely pre-Phase-2A row has — must still resolve correctly
        through ``get_cell_blocks``."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        cell.section = section
        cell.save(update_fields=["section", "updated_at"])
        self.assertIsNone(StorefrontSection.objects.get(pk=section.pk).cell_id)

        self.assertEqual(container_service.get_cell_blocks(cell), [section])

    def test_new_multi_block_state_is_never_overridden_by_stale_legacy_pointer(self):
        """If a Cell's legacy pointer still (incorrectly, from external/
        direct manipulation) references a Section that is NOT one of the
        Cell's current new-FK Blocks, the new-FK Blocks must still win —
        the legacy branch is only ever consulted when the new FK is
        completely empty for that Cell."""
        real_block = self._section(0)
        stale_legacy_target = self._section(1)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, real_block)
        # Directly force a stale legacy pointer via raw model access —
        # simulating external/inconsistent data, not a supported write path.
        from apps.storefront_builder.models import StorefrontCell as RawCell
        RawCell.objects.filter(pk=cell.pk).update(section_id=stale_legacy_target.pk)
        cell.refresh_from_db()

        blocks = container_service.get_cell_blocks(cell)

        self.assertEqual([x.pk for x in blocks], [real_block.pk])

    def test_legacy_write_path_leaves_new_composition_synchronized(self):
        """``place_section`` (the real Builder UI's write path) must leave
        ``get_cell_blocks`` immediately consistent — already proven in
        Phase 2B, re-confirmed here as part of Phase 2C's source-of-truth
        audit since this is exactly the guarantee the new FK being
        'primary' depends on."""
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        container_service.place_section(cell, section)

        section.refresh_from_db()
        self.assertEqual(section.cell_id, cell.pk)
        self.assertEqual(section.cell_order, 0)
        self.assertEqual(container_service.get_cell_blocks(cell), [section])



# ----------------------------------------------------------------------
# Live-Builder closure fix — real VIEW-level regression tests
# ----------------------------------------------------------------------
#
# The Phase 2C report identified that live Builder code (``views.py``)
# still read the legacy ``StorefrontCell.section`` OneToOne directly in
# three places (the ``storefront_cell_add_section`` occupied-check, the
# ``storefront_cell_clear`` delete path, and the ``storefront_section_settings``
# ``placement_cell`` Inspector context), and that a few Builder-chrome
# templates (``container_settings_form.html``, ``container_state.html``)
# determined occupied/empty solely from ``cell.section_id``/``cell.section``.
# None of that is correct once a real multi-block Cell exists (e.g. after a
# Phase 2C merge-on-shrink) — this class proves the fix using the ACTUAL
# HTTP endpoints a merchant's browser calls, not just the service layer
# directly (which the rest of this file already covers).

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE  # noqa: F401 (documents the permission this suite relies on)
from apps.stores.models import StoreMembership

User = get_user_model()
_HOST = "sfb-2c-test.rastisi.localhost"


class LiveBuilderMultiBlockClosureTests(TestCase):
    """Real HTTP-level regression coverage — deliberately NOT reusing
    ``test_views.StorefrontBuilderViewsTestCase`` (that class's ``setUp``
    mutates the shared ``akhlaghi`` Store's ``admin_subdomain``, which this
    file's other test classes in this same module also rely on staying at
    its default value across the whole file's test run order) — a small,
    self-contained, equivalent setup avoids any cross-test-class ordering
    risk while still exercising the exact same real view/permission/host
    stack every other Builder view test in this app already uses."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = _HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="sfb_2c_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=_HOST)
        self.client.login(username="sfb_2c_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self, order=0, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=order,
            settings={"body_html": f"section-{order}"}, **kwargs,
        )

    def _build_multiblock_cell_via_real_workflow(self):
        """Container 50/50 -> merge to 100% using the REAL service-level
        layout-change workflow (the supported way a real multi-block Cell
        with more than one Block currently comes to exist, since no UI yet
        exposes a direct "add second Block" action) — Cell A holds A;
        Cell B holds B, C. After merging to a single Cell, the survivor
        holds A, B, C in that order, entirely through the new FK."""
        a = self._section(0)
        b = self._section(1)
        c = self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        cell_a, cell_b = list(container.cells.order_by("order", "id"))
        container_service.add_block(cell_a, a)
        container_service.add_block(cell_b, b)
        container_service.add_block(cell_b, c)

        container_service.change_container_layout(container, "single")

        survivor = container.cells.get()
        self.assertIsNone(survivor.section_id, "the surviving Cell's content lives entirely through the new FK")
        self.assertEqual(
            [x.pk for x in container_service.get_cell_blocks(survivor)],
            [a.pk, b.pk, c.pk],
        )
        return container, survivor, (a, b, c)

    # -- VIEW: multi-block Cell clear ---------------------------------

    def test_view_multiblock_cell_clear_removes_all_content(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk])
        )

        self.assertEqual(response.status_code, 200)
        survivor.refresh_from_db()
        self.assertEqual(container_service.get_cell_blocks(survivor), [])
        for section in (a, b, c):
            self.assertFalse(
                StorefrontSection.objects.filter(pk=section.pk).exists(),
                "the endpoint's established contract is to DELETE cleared content, for every Block",
            )

    def test_view_cell_and_container_survive_multiblock_clear(self):
        container, survivor, _ = self._build_multiblock_cell_via_real_workflow()
        container_sid, cell_sid = container.stable_id, survivor.stable_id

        self.client.post(reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk]))

        self.assertTrue(self.page.containers.filter(stable_id=container_sid).exists())
        self.assertTrue(
            self.page.containers.get(stable_id=container_sid).cells.filter(stable_id=cell_sid).exists()
        )

    def test_view_no_orphan_section_remains_after_multiblock_clear(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()

        self.client.post(reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk]))

        # The cleared Sections were deleted (established contract), and no
        # OTHER Section on the page was left dangling/unplaced by this
        # operation — the publish invariant only cares about Sections that
        # still exist.
        remaining_section_ids = set(self.page.sections.values_list("pk", flat=True))
        self.assertEqual(remaining_section_ids & {a.pk, b.pk, c.pk}, set())
        # Publish must not raise/orphan anything as a result of the clear.
        svc.publish(self.store, user=self.staff)

    def test_view_multiblock_clear_is_one_history_operation(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        self._build_multiblock_cell_via_real_workflow()
        survivor = self.page.containers.get().cells.get()
        self.draft.edit_history_entries.all().delete()

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    def test_view_undo_restores_all_blocks_in_exact_order_after_multiblock_clear(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        cell_sid = survivor.stable_id
        self.draft.edit_history_entries.all().delete()

        self.client.post(reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk]))
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

        undo_response = self.client.post(reverse("dashboard:storefront-builder-undo"))

        self.assertTrue(undo_response.json()["ok"])
        restored_cell = self.page.containers.get().cells.get(stable_id=cell_sid)
        restored_blocks = container_service.get_cell_blocks(restored_cell)
        self.assertEqual([x.stable_id for x in restored_blocks], [a.stable_id, b.stable_id, c.stable_id])

    def test_view_redo_clears_again_after_undo_of_multiblock_clear(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        cell_sid = survivor.stable_id
        self.draft.edit_history_entries.all().delete()
        self.client.post(reverse("dashboard:storefront-builder-cell-clear", args=[survivor.pk]))
        self.client.post(reverse("dashboard:storefront-builder-undo"))

        redo_response = self.client.post(reverse("dashboard:storefront-builder-redo"))

        self.assertTrue(redo_response.json()["ok"])
        restored_cell = self.page.containers.get().cells.get(stable_id=cell_sid)
        self.assertEqual(container_service.get_cell_blocks(restored_cell), [])

    # -- LOCKED BLOCK SAFETY -------------------------------------------

    def test_view_multiblock_clear_is_atomic_when_one_block_is_locked(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        a = self._section(0)
        locked_b = self._section(1, is_locked=True)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.add_block(cell, a)
        container_service.add_block(cell, locked_b)

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk])
        )

        self.assertEqual(response.status_code, 200)
        # All-or-nothing: neither Section was removed because ONE was locked.
        cell.refresh_from_db()
        remaining = container_service.get_cell_blocks(cell)
        self.assertEqual({x.pk for x in remaining}, {a.pk, locked_b.pk})
        self.assertTrue(StorefrontSection.objects.filter(pk=a.pk).exists())
        self.assertTrue(StorefrontSection.objects.filter(pk=locked_b.pk).exists())

    # -- VIEW: new-FK occupancy used by the add-to-cell action ---------

    def test_view_cell_with_new_fk_blocks_and_null_legacy_pointer_accepts_another_block(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """V3 exposes the Phase-2B multi-block engine through the real live
        add-to-cell endpoint: new-FK-only occupancy is preserved, then the new
        Block is appended rather than replacing any existing content."""
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        self.assertIsNone(survivor.section_id)

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"page": "home", "cell_id": survivor.pk, "section_key": "rich_text"},
        )

        self.assertEqual(response.status_code, 200)
        blocks = container_service.get_cell_blocks(survivor)
        self.assertEqual([x.pk for x in blocks[:3]], [a.pk, b.pk, c.pk])
        self.assertEqual(len(blocks), 4)
        self.assertEqual(blocks[-1].section_key, "rich_text")
        self.assertEqual([x.cell_order for x in blocks], [0, 1, 2, 3])

    def test_view_add_to_genuinely_empty_cell_still_succeeds(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """Regression guard alongside the fix above: an ACTUALLY empty
        Cell (no legacy pointer, no new-FK Blocks) must still accept the
        real add-to-cell action exactly as before."""
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"page": "home", "cell_id": cell.pk, "section_key": "rich_text"},
        )

        self.assertEqual(response.status_code, 200)
        cell.refresh_from_db()
        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].section_key, "rich_text")

    # -- V3 LIVE BLOCK ACTIONS -----------------------------------------

    def test_view_block_remove_deletes_only_selected_block_and_preserves_siblings_and_cell(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        cell_sid = survivor.stable_id

        response = self.client.post(
            reverse("dashboard:storefront-builder-block-remove", args=[b.pk])
        )

        self.assertEqual(response.status_code, 200)
        survivor = container.cells.get(stable_id=cell_sid)
        self.assertEqual([x.pk for x in container_service.get_cell_blocks(survivor)], [a.pk, c.pk])
        self.assertEqual([x.cell_order for x in container_service.get_cell_blocks(survivor)], [0, 1])
        self.assertFalse(StorefrontSection.objects.filter(pk=b.pk).exists())
        self.assertTrue(StorefrontSection.objects.filter(pk=a.pk).exists())
        self.assertTrue(StorefrontSection.objects.filter(pk=c.pk).exists())

    def test_view_block_move_between_cells_preserves_identity_and_orders(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        a, b, c = self._section(0), self._section(1), self._section(2)
        container = container_service.create_empty_container(self.page, "half")
        first, second = list(container.cells.order_by("order", "id"))
        container_service.add_block(first, a)
        container_service.add_block(first, b)
        container_service.add_block(second, c)

        response = self.client.post(
            reverse("dashboard:storefront-builder-block-move", args=[b.pk]),
            {"target_cell_id": second.pk, "at_index": 0},
        )

        self.assertEqual(response.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.cell_id, second.pk)
        self.assertEqual([x.pk for x in container_service.get_cell_blocks(first)], [a.pk])
        self.assertEqual([x.pk for x in container_service.get_cell_blocks(second)], [b.pk, c.pk])
        self.assertEqual([x.cell_order for x in container_service.get_cell_blocks(second)], [0, 1])

    def test_view_block_move_direction_reorders_inside_same_cell(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()

        response = self.client.post(
            reverse("dashboard:storefront-builder-block-move", args=[c.pk]),
            {"target_cell_id": survivor.pk, "direction": "up"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([x.pk for x in container_service.get_cell_blocks(survivor)], [a.pk, c.pk, b.pk])
        self.assertEqual([x.cell_order for x in container_service.get_cell_blocks(survivor)], [0, 1, 2])

    def test_view_duplicate_placed_block_stays_in_same_cell_after_source(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        old_ids = {a.pk, b.pk, c.pk}

        response = self.client.post(
            reverse("dashboard:storefront-builder-section-duplicate", args=[b.pk])
        )

        self.assertEqual(response.status_code, 200)
        blocks = container_service.get_cell_blocks(survivor)
        self.assertEqual(len(blocks), 4)
        duplicate = next(x for x in blocks if x.pk not in old_ids)
        self.assertEqual([x.pk for x in blocks], [a.pk, b.pk, duplicate.pk, c.pk])
        self.assertEqual(duplicate.cell_id, survivor.pk)
        self.assertNotEqual(duplicate.stable_id, b.stable_id)

    # -- VIEW/CONTEXT: new-FK-only Section resolves its Cell -----------

    def test_view_new_fk_only_section_settings_context_resolves_its_cell(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """A Section placed ONLY through the new FK (e.g. one of several
        Blocks merged into a Cell) has no legacy ``placement_cell`` reverse
        relation at all — the real Inspector view
        (``storefront_section_settings``) must still correctly report
        which Cell/Container it belongs to, so the rendered Inspector
        exposes V3 Cell context actions rather than incorrectly falling back
        to the no-placement whole-Section branch."""
        container, survivor, (a, b, c) = self._build_multiblock_cell_via_real_workflow()
        self.assertIsNone(StorefrontCell.objects.filter(section_id=b.pk).first(), "b has no legacy reverse relation")

        response = self.client.get(
            reverse("dashboard:storefront-builder-section-settings", args=[b.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("خالی کردن ستون", html)
        self.assertIn("حذف فقط همین بلاک", html)
        self.assertIn(f"cellCommand({survivor.pk}, 'clear', {b.pk})", html)
        self.assertIn(f"blockCommand({b.pk}, 'remove')", html)

    # -- LEGACY: single-block clear still behaves exactly as before ----

    def test_legacy_single_block_clear_still_behaves_exactly_as_before(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)
        container_sid, cell_sid = container.stable_id, cell.stable_id
        self.draft.edit_history_entries.all().delete()

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[cell.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        restored_cell = self.page.containers.get(stable_id=container_sid).cells.get(stable_id=cell_sid)
        self.assertIsNone(restored_cell.section_id)
        self.assertEqual(self.draft.edit_history_entries.count(), 1)

    # -- TENANT/PERMISSION scoping remains intact -----------------------

    def test_cell_clear_endpoint_rejects_cross_store_cell(self):
        other_store = Store.objects.create(name="فروشگاه دیگر ۲c", slug="phase2c-cross-store-check")
        other_draft = svc.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_page.containers.all().delete()
        other_page.sections.all().delete()
        other_container = container_service.create_empty_container(other_page, "single")
        other_cell = other_container.cells.get()
        other_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0, settings={},
        )
        container_service.place_section(other_cell, other_section)

        response = self.client.post(
            reverse("dashboard:storefront-builder-cell-clear", args=[other_cell.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(StorefrontSection.objects.filter(pk=other_section.pk).exists())

    def test_cell_add_section_endpoint_requires_login(self):
        anonymous_client = Client(HTTP_HOST=_HOST)
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        response = anonymous_client.post(
            reverse("dashboard:storefront-builder-cell-add-section"),
            {"page": "home", "cell_id": cell.pk, "section_key": "rich_text"},
        )

        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(container_service.get_cell_blocks(cell), [])
