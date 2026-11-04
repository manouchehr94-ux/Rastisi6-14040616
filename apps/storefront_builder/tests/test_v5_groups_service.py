"""V5 Groups — the nested, free layout tree built ONLY through the R4 mutation path (the one the Studio sends).

Container -> Cells -> (Blocks | one nested Container) -> Cells -> ...  Every operation keeps content, is one Revision / one Undo step, and
leaves a valid tree (integer spans of the 12-unit grid summing to 12 at every level, bounded depth and size)."""

from apps.storefront_builder.models import StorefrontCell, StorefrontContainer, StorefrontSection
from apps.storefront_builder.services import container_service, r4_mutation_service

from .test_v5_composition_lab import _LabBase


class _GroupBase(_LabBase):
    def row(self, *keys):
        """A fresh page row with one empty Cell per key... or one single empty Cell when no key is given (the «ردیف ساده»)."""
        self.mutate({"type": "row.add", "page_type": "home"})
        container = StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-order", "-id").first()
        return container

    def cells(self, container):
        return list(StorefrontCell.objects.filter(container=container).order_by("order", "id"))

    def spans(self, container):
        return [cell.span for cell in self.cells(container)]

    def tree_ok(self):
        page = self.draft.get_page("home")
        container_service.validate_page_containers(page)

    def nested(self, cell):
        return StorefrontContainer.all_objects.filter(parent_cell=cell).first()

    def put(self, cell, key):
        self.mutate({"type": "cell.add_section", "cell_id": cell.pk, "section_key": key})
        return StorefrontSection.objects.filter(cell=cell, section_key=key).order_by("-id").first()


class SplitTests(_GroupBase):
    def test_a_simple_row_is_one_empty_cell_and_becomes_a_group_when_split(self):
        row = self.row()
        self.assertEqual(self.spans(row), [12])
        self.assertEqual(row.layout_key, "single")
        cell = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": cell.pk, "axis": "horizontal", "count": 3})
        row.refresh_from_db()
        self.assertEqual(self.spans(row), [4, 4, 4])
        self.assertTrue(row.settings.get("group"))
        self.assertNotIn("axis", row.settings)
        self.assertEqual(row.layout_key, "thirds")
        self.tree_ok()

    def test_vertical_split_marks_the_axis_and_two_parts_are_even(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "vertical", "count": 2})
        row.refresh_from_db()
        self.assertEqual((self.spans(row), row.settings.get("axis")), ([6, 6], "vertical"))
        self.assertEqual(row.layout_key, "custom")

    def test_splitting_a_cell_of_a_multi_cell_row_nests_a_group_and_keeps_the_content(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 3})
        left = self.cells(row)[0]
        block = self.put(left, "rich_text")
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 3})
        group = self.nested(left)
        self.assertIsNotNone(group)
        self.assertEqual((self.spans(group), group.settings.get("axis")), ([4, 4, 4], "vertical"))
        block.refresh_from_db()
        self.assertEqual(block.cell_id, self.cells(group)[0].pk)                      # the same Section, now in the first new cell
        self.assertEqual(StorefrontSection.objects.filter(pk=block.pk).count(), 1)
        self.tree_ok()

    def test_a_free_tree_of_at_least_eight_cells_is_valid_and_each_step_is_one_revision(self):
        row = self.row()
        revision = self._revision()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 3})           # 3
        self.assertEqual(self._revision(), revision + 1)
        first = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": first.pk, "axis": "vertical", "count": 3})                           # +3 nested
        group = self.nested(first)
        middle = self.cells(group)[1]
        self.mutate({"type": "cell.split", "cell_id": middle.pk, "axis": "horizontal", "count": 2})                        # +2 nested deeper
        deep = self.nested(middle)
        self.mutate({"type": "cell.split", "cell_id": self.cells(deep)[1].pk, "axis": "vertical", "count": 3})             # +3
        total = StorefrontCell.objects.filter(container__page=row.page).count()
        leaves = StorefrontCell.objects.filter(container__page=row.page).exclude(child_containers__isnull=False).count()
        self.assertGreaterEqual(leaves, 8)
        self.assertGreaterEqual(total, 8)
        self.tree_ok()
        self.assertEqual(container_service.container_depth(self.nested(self.cells(deep)[1])), 3)

    def test_splitting_a_group_host_relays_the_group_instead_of_adding_a_level(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        left = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        group = self.nested(left)
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "horizontal", "count": 3})
        self.assertEqual(StorefrontContainer.all_objects.filter(parent_cell=left).count(), 1)
        group.refresh_from_db()
        self.assertEqual((self.spans(group), group.settings.get("axis")), ([4, 4, 4], None))

    def test_refusals_change_nothing(self):
        row = self.row()
        cell = self.cells(row)[0]
        for bad in ({"axis": "diagonal", "count": 2}, {"axis": "horizontal", "count": 4}, {"axis": "horizontal", "count": 1}, {"axis": "horizontal", "count": "2"}):
            before = self._revision()
            with self.assertRaises(r4_mutation_service.R4MutationError):
                self.mutate({"type": "cell.split", "cell_id": cell.pk, **bad})
            self.assertEqual(self._revision(), before)

    def test_locked_block_or_row_refuses_a_split(self):
        row = self.row()
        block = self.put(self.cells(row)[0], "rich_text")
        self.mutate({"type": "section.toggle_locked", "section_id": block.pk})
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})

    def test_depth_is_bounded(self):
        row = self.row()
        cell = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": cell.pk, "axis": "horizontal", "count": 2})
        cell = self.cells(row)[0]
        depth = 0
        with self.assertRaises(r4_mutation_service.R4MutationError) as caught:
            for _ in range(20):
                self.mutate({"type": "cell.split", "cell_id": cell.pk, "axis": "vertical", "count": 2})
                group = self.nested(cell)
                cell = self.cells(group)[0]
                depth += 1
        self.assertEqual(str(caught.exception), "group_depth_limit")
        self.assertEqual(depth, container_service.MAX_GROUP_DEPTH)


class GroupCellTests(_GroupBase):
    def three(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 3})
        return row

    def test_add_cell_rescales_the_others_and_is_capped(self):
        row = self.three()
        self.mutate({"type": "container.add_cell", "container_id": row.pk})
        spans = self.spans(row)
        self.assertEqual((len(spans), sum(spans)), (4, 12))
        self.assertGreaterEqual(min(spans), container_service.GROUP_MIN_SPAN)
        self.mutate({"type": "container.add_cell", "container_id": row.pk})
        self.mutate({"type": "container.add_cell", "container_id": row.pk})
        self.assertEqual(self.spans(row), [2] * 6)
        with self.assertRaises(r4_mutation_service.R4MutationError) as caught:
            self.mutate({"type": "container.add_cell", "container_id": row.pk})
        self.assertEqual(str(caught.exception), "cell_limit")
        self.tree_ok()

    def test_remove_cell_deletes_its_content_and_the_others_absorb_the_width(self):
        row = self.three()
        cells = self.cells(row)
        block = self.put(cells[1], "rich_text")
        self.mutate({"type": "cell.remove", "cell_id": cells[1].pk})
        self.assertFalse(StorefrontSection.objects.filter(pk=block.pk).exists())
        spans = self.spans(row)
        self.assertEqual((len(spans), sum(spans)), (2, 12))

    def test_a_group_left_with_one_cell_dissolves_and_keeps_the_survivor_content(self):
        row = self.three()
        left = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        group = self.nested(left)
        top, bottom = self.cells(group)
        kept = self.put(bottom, "faq")
        self.mutate({"type": "cell.remove", "cell_id": top.pk})
        self.assertIsNone(self.nested(left))                         # the wrapper disappeared
        kept.refresh_from_db()
        self.assertEqual(kept.cell_id, left.pk)                      # its content moved up into the parent cell
        self.tree_ok()

    def test_move_cell_swaps_order_and_spans_travel(self):
        row = self.three()
        self.mutate({"type": "container.resize", "container_id": row.pk, "spans": [6, 3, 3]})
        first = self.cells(row)[0]
        self.mutate({"type": "cell.move", "cell_id": first.pk, "direction": "down"})
        self.assertEqual(self.spans(row), [3, 6, 3])
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.mutate({"type": "cell.move", "cell_id": self.cells(row)[2].pk, "direction": "down"})

    def test_duplicate_cell_copies_content_as_new_sections(self):
        row = self.three()
        cells = self.cells(row)
        original = self.put(cells[0], "rich_text")
        self.mutate({"type": "cell.duplicate", "cell_id": cells[0].pk})
        new_cells = self.cells(row)
        self.assertEqual(len(new_cells), 4)
        copy = StorefrontSection.objects.filter(cell=new_cells[1]).first()
        self.assertIsNotNone(copy)
        self.assertNotEqual(copy.pk, original.pk)
        self.assertEqual(sum(self.spans(row)), 12)

    def test_duplicate_row_deep_copies_the_nested_tree(self):
        row = self.three()
        left = self.cells(row)[0]
        self.put(left, "rich_text")
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        before = StorefrontSection.objects.filter(page=row.page, section_key="rich_text").count()
        self.mutate({"type": "container.duplicate", "container_id": row.pk})
        self.assertEqual(StorefrontSection.objects.filter(page=row.page, section_key="rich_text").count(), before + 1)
        self.assertEqual(StorefrontContainer.all_objects.filter(page=row.page, parent_cell__isnull=False).count(), 2)
        self.tree_ok()

    def test_remove_group_deletes_everything_inside(self):
        row = self.three()
        block = self.put(self.cells(row)[2], "rich_text")
        self.mutate({"type": "container.remove_group", "container_id": row.pk})
        self.assertFalse(StorefrontContainer.all_objects.filter(pk=row.pk).exists())
        self.assertFalse(StorefrontSection.objects.filter(pk=block.pk).exists())

    def test_blocks_cannot_be_placed_straight_into_a_cell_that_hosts_a_group(self):
        row = self.three()
        left = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.mutate({"type": "cell.add_section", "cell_id": left.pk, "section_key": "rich_text"})

    def test_set_layout_grows_and_merges_blocks_when_shrinking(self):
        row = self.three()
        cells = self.cells(row)
        a, b = self.put(cells[1], "rich_text"), self.put(cells[2], "faq")
        self.mutate({"type": "container.set_layout", "container_id": row.pk, "axis": "horizontal", "count": 2})
        self.assertEqual(self.spans(row), [6, 6])
        last = self.cells(row)[1]
        a.refresh_from_db(), b.refresh_from_db()
        self.assertEqual((a.cell_id, b.cell_id), (last.pk, last.pk))
        self.mutate({"type": "container.set_layout", "container_id": row.pk, "axis": "vertical", "count": 3})
        row.refresh_from_db()
        self.assertEqual((self.spans(row), row.settings.get("axis")), ([4, 4, 4], "vertical"))


class UndoRedoAndPublishTests(_GroupBase):
    def test_undo_and_redo_restore_the_whole_nested_tree(self):
        row = self.row()
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        left = self.cells(row)[0]
        block = self.put(left, "rich_text")
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 3})
        count = lambda: StorefrontContainer.all_objects.filter(page__version=self.draft, parent_cell__isnull=False).count()
        self.assertEqual(count(), 1)
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertEqual(count(), 0)
        self.assertEqual(StorefrontSection.objects.filter(stable_id=block.stable_id).count(), 1)
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(count(), 1)
        nested = StorefrontContainer.all_objects.get(page__version=self.draft, parent_cell__isnull=False)
        self.assertEqual(sorted(c.span for c in nested.cells.all()), [4, 4, 4])
        moved = StorefrontSection.objects.get(stable_id=block.stable_id)
        self.assertEqual(moved.cell.container_id, nested.pk)

    def test_publish_and_the_next_draft_keep_the_tree_and_the_fingerprint_changes(self):
        from apps.storefront_builder.services import layout_service

        row = self.row()
        before = self.draft.semantic_hash() if hasattr(self.draft, "semantic_hash") else None
        self.mutate({"type": "cell.split", "cell_id": self.cells(row)[0].pk, "axis": "horizontal", "count": 2})
        left = self.cells(row)[0]
        self.mutate({"type": "cell.split", "cell_id": left.pk, "axis": "vertical", "count": 2})
        if before is not None:
            self.draft.refresh_from_db()
            self.assertNotEqual(before, self.draft.semantic_hash())
        layout_service.publish(self.store)
        published = layout_service.get_or_create_layout(self.store).published_version
        nested = StorefrontContainer.all_objects.filter(page__version=published, parent_cell__isnull=False)
        self.assertEqual(nested.count(), 1)
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.assertEqual(StorefrontContainer.all_objects.filter(page__version=draft, parent_cell__isnull=False).count(), 1)
        self.assertEqual(StorefrontContainer.objects.filter(page__version=draft, parent_cell__isnull=False).count(), 0)      # default manager = rows only
