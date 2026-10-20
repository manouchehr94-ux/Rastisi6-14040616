from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase31AHiddenCellSemanticsTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
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

    def test_hidden_section_is_occupied_placeholder_not_empty_cell(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        first, second = list(container.cells.order_by("order", "id"))
        container_service.place_section(first, hidden)

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'data-hidden-section="{hidden.pk}"', html)
        self.assertIn("این محتوا مخفی است؛ خانه خالی نیست.", html)
        self.assertIn(f'data-cell-clear="{first.pk}"', html)
        self.assertIn(f'data-hidden-toggle="{hidden.pk}"', html)
        self.assertNotIn(f'data-empty-cell="{first.pk}"', html)
        self.assertIn(f'data-empty-cell="{second.pk}"', html)


    def test_active_cell_toolbar_removes_only_selected_block_and_keeps_cell_clear_distinct(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        cell = container.cells.get()
        container_service.place_section(cell, section)

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")

        self.assertIn(f'data-block-remove="{section.pk}"', html)
        self.assertIn('title="حذف فقط این بلاک"', html)
        self.assertIn("🗑", html)
        # Whole-cell clear remains a separate action for hidden/cell-context
        # controls; it is no longer overloaded by the selected Block toolbar.
        self.assertIn("var clearCellBtn = evt.target.closest('[data-cell-clear]');", html)
