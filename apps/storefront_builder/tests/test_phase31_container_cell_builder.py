from django.urls import reverse

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


class Phase31ContainerCellBuilderTests(StorefrontBuilderViewsTestCase):
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

    def _layout_url(self, container):
        return reverse("dashboard:storefront-builder-container-layout", args=[container.pk])


    def test_preview_renders_empty_cells_before_content_exists(self):
        container_service.create_empty_container(self.page, "half")

        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-layout="half"')
        self.assertContains(response, 'class="rcontainer-cell', count=2)
        self.assertContains(response, "افزودن محتوا", count=2)
        self.assertContains(response, "data-empty-cell=", count=2)


    def test_ensure_page_containers_appends_unplaced_content_after_order_zero(self):
        container_service.create_empty_container(self.page, "single", order=0)
        section = self._section()

        container_service.ensure_page_containers(self.page)

        containers = list(self.page.containers.order_by("order", "id"))
        self.assertEqual([item.order for item in containers], [0, 1])
        self.assertEqual(containers[1].cells.get().section_id, section.pk)


    def test_published_context_uses_container_layout_as_source_of_truth(self):
        from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context

        section = self._section()
        container = container_service.create_empty_container(self.page, "half")
        container_service.place_section(container.cells.order_by("order", "id").first(), section)
        published = layout_service.publish(self.store)

        class Request:
            pass

        context = build_universal_storefront_context(
            Request(), self.store, StorefrontPage.PageType.HOME
        )
        self.assertTrue(context["use_container_layout"])
        self.assertEqual(context["storefront_version"].pk, published.pk)
        self.assertEqual(len(context["render_containers"]), 1)
        composition = context["render_containers"][0]
        self.assertEqual(composition["container"].layout_key, "half")
        self.assertEqual([entry["cell"].span for entry in composition["cells"]], [6, 6])
        self.assertIsNotNone(composition["cells"][0]["item"])
        self.assertIsNone(composition["cells"][1]["item"])
