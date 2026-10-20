from django.test import TestCase

from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import container_service, edit_history_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase30ContainerCellFoundationTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def _section(self, order, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=order,
            settings={"body_html": f"section-{order}"},
            **kwargs,
        )

    def test_legacy_half_row_mirrors_to_one_container_with_two_cells(self):
        first = self._section(0, row_key="pair", row_span=6)
        second = self._section(1, row_key="pair", row_span=6)

        container_service.rebuild_page_from_legacy_rows(self.page)

        self.assertEqual(self.page.containers.count(), 1)
        container = self.page.containers.get()
        self.assertEqual(container.layout_key, "half")
        cells = list(container.cells.order_by("order"))
        self.assertEqual([cell.span for cell in cells], [6, 6])
        self.assertEqual([cell.section_id for cell in cells], [first.pk, second.pk])
        container_service.validate_page_containers(self.page)

    def test_empty_layout_exists_before_content(self):
        container = container_service.create_empty_container(self.page, "quarter_left")

        cells = list(container.cells.order_by("order"))
        self.assertEqual([cell.span for cell in cells], [3, 9])
        self.assertEqual([cell.section_id for cell in cells], [None, None])
        container_service.validate_container(container, cells)

    def test_section_can_be_placed_into_empty_cell(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        cell = container.cells.order_by("order").first()

        container_service.place_section(cell, section)

        cell.refresh_from_db()
        self.assertEqual(cell.section_id, section.pk)
        self.assertEqual(section.placement_cell.pk, cell.pk)

    def test_section_from_another_page_cannot_be_placed(self):
        other_page = self.draft.get_page(StorefrontPage.PageType.SEARCH)
        section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0, settings={}
        )
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()

        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.place_section(cell, section)

        cell.refresh_from_db()
        self.assertIsNone(cell.section_id)

    def test_snapshot_restore_preserves_empty_cells_and_placement(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        cells = list(container.cells.order_by("order"))
        container_service.place_section(cells[0], section)
        container_sid = container.stable_id
        cell_sids = [cell.stable_id for cell in cells]
        section_sid = section.stable_id

        state = edit_history_service.snapshot_draft(self.draft)
        self.page.containers.all().delete()
        self.page.sections.all().delete()

        edit_history_service.restore_draft_state(self.draft, state)

        restored_container = self.page.containers.get(stable_id=container_sid)
        restored_cells = list(restored_container.cells.order_by("order"))
        self.assertEqual([cell.stable_id for cell in restored_cells], cell_sids)
        self.assertEqual(restored_cells[0].section.stable_id, section_sid)
        self.assertIsNone(restored_cells[1].section_id)

    def test_clone_preserves_container_cell_identity_and_empty_slot(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        first_cell, second_cell = list(container.cells.order_by("order"))
        container_service.place_section(first_cell, section)

        target = StorefrontLayoutVersion.objects.create(
            layout=self.draft.layout,
            version_number=self.draft.version_number + 1000,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
        layout_service._clone_version_content(self.draft, target)
        target_page = target.get_page(StorefrontPage.PageType.HOME)

        cloned_container = target_page.containers.get(stable_id=container.stable_id)
        cloned_cells = list(cloned_container.cells.order_by("order"))
        self.assertEqual([cell.stable_id for cell in cloned_cells], [first_cell.stable_id, second_cell.stable_id])
        self.assertEqual(cloned_cells[0].section.stable_id, section.stable_id)
        self.assertIsNone(cloned_cells[1].section_id)

    def test_fingerprint_includes_container_layout(self):
        section = self._section(0)
        container = container_service.create_empty_container(self.page, "half")
        first_cell, _ = list(container.cells.order_by("order"))
        container_service.place_section(first_cell, section)
        before = self.draft.compute_fingerprint()

        container.settings = {**container.settings, "gap": 26}
        container.save(update_fields=["settings", "updated_at"])
        after = self.draft.compute_fingerprint()

        self.assertNotEqual(before, after)


class Phase30ContainerCellModelContractTests(TestCase):
    def test_models_expose_expected_relations(self):
        self.assertEqual(StorefrontContainer._meta.get_field("page").remote_field.related_name, "containers")
        self.assertEqual(StorefrontCell._meta.get_field("container").remote_field.related_name, "cells")
        self.assertEqual(StorefrontCell._meta.get_field("section").remote_field.related_name, "placement_cell")
        self.assertTrue(StorefrontCell._meta.get_field("section").null)
