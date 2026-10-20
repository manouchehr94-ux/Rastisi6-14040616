from pathlib import Path

from django.urls import reverse


from .test_views import StorefrontBuilderViewsTestCase


class Phase274InteractionStabilityTests(StorefrontBuilderViewsTestCase):
    def _draft(self):
        from apps.storefront_builder.services import layout_service
        return layout_service.get_or_create_draft(self.store, user=self.staff)


    def test_preview_exposes_row_and_lock_state_for_builder_sync(self):
        response = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-section-row-key")
        self.assertContains(response, "data-section-row-span")
        self.assertContains(response, "data-section-locked")

    def test_inline_toolbar_uses_registry_capabilities(self):
        render_service = (
            Path(__file__).resolve().parents[1] / "services" / "render_service.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            Path(__file__).resolve().parents[1]
            / "templates" / "storefront_builder" / "partials" / "responsive_section_wrapper.html"
        ).read_text(encoding="utf-8")
        self.assertIn('"definition": definition', render_service)
        self.assertIn("not item.definition.duplicable", wrapper)
        self.assertIn("not item.definition.removable", wrapper)

    def test_browser_runner_guards_dialog_drag_and_repeated_key_order(self):
        runner = (
            Path(__file__).resolve().parents[3]
            / "tools" / "storefront_builder_qa" / "run.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn("async function previewSectionIdOrder()", runner)
        self.assertIn("await waitSectionIdOrderChanged(before)", runner)
        self.assertIn("clickAcceptingDialog(toolbar.locator('[data-cmd=\"remove\"]'))", runner)
        self.assertIn("overlay.dataset.dropIndex !== ''", runner)
        self.assertIn("inline-toolbar-capability-contract", runner)
        self.assertIn("async function revealInlineToolbar(section)", runner)
        self.assertIn("await section.hover()", runner)
        self.assertIn("await toolbar.waitFor({ state: 'visible'", runner)
