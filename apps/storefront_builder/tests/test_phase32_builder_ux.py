from django.urls import reverse

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service, render_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase32BuilderUXTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()

    def _section(self, order=0, **kwargs):
        return StorefrontSection.objects.create(
            page=self.page, section_key="rich_text", order=order,
            settings={"body_html": f"section-{order}"}, **kwargs,
        )

    def test_legacy_stretch_is_normalized_to_natural_height_start(self):
        settings = container_service.effective_container_settings({"vertical_align": "stretch"})
        self.assertEqual(settings["vertical_align"], "start")
        self.assertEqual(container_service.effective_container_settings({})["vertical_align"], "start")

    def test_render_composition_distinguishes_hidden_placement_from_empty_container(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "half")
        first = container.cells.order_by("order", "id").first()
        container_service.place_section(first, hidden)
        compositions = render_service.build_container_render_items(self.page, [], include_empty=True)
        self.assertTrue(compositions[0]["has_placement"])
        self.assertFalse(compositions[0]["has_content"])

    def test_empty_container_preview_has_direct_delete_control(self):
        container = container_service.create_empty_container(self.page, "half")
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")
        self.assertIn(f'data-container-remove="{container.pk}"', html)
        self.assertIn("حذف این چیدمان خالی", html)

    def test_container_with_hidden_content_has_no_direct_empty_delete_control(self):
        hidden = self._section(is_active=False)
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), hidden)
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")
        self.assertNotIn(f'data-container-remove="{container.pk}"', html)


    def test_preview_exposes_direct_settings_and_selection_sync_contract(self):
        section = self._section()
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), section)
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        html = response.content.decode("utf-8")
        self.assertIn(f'data-open-settings="{section.pk}"', html)
        self.assertIn("sfb:openSectionSettings", html)
        self.assertIn("sfb:setSelection", html)
        self.assertIn("sfb-cell-selected", html)

    def test_rich_text_is_merchant_facing_and_explained_by_registry(self):
        rich = section_registry.get_definition("rich_text")
        image_text = section_registry.get_definition("image_text")
        self.assertEqual(rich.label_fa, "متن")
        self.assertIn("پاراگراف", rich.description_fa)
        self.assertIn("تصویر", image_text.description_fa)
