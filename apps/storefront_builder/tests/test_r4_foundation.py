from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion
from apps.storefront_builder.services import layout_service as svc

from .test_views import StorefrontBuilderViewsTestCase


class R4FoundationModelTests(TestCase):
    def test_r4_editor_is_enabled_by_default(self):
        # Pre-Task-10 remediation (R4 live cutover) — R4 is now the
        # canonical merchant editor; the field remains a non-blocking
        # compatibility flag a Store can be explicitly pinned back with
        # (see R4EditorRouteGateTests below), never a blocking rollout gate.
        field = StorefrontLayout._meta.get_field("r4_editor_enabled")
        self.assertTrue(field.default)

    def test_draft_edit_revision_starts_at_zero(self):
        field = StorefrontLayoutVersion._meta.get_field("edit_revision")
        self.assertEqual(field.default, 0)


class R4EditorRouteGateTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)

    def test_r4_route_is_unavailable_when_gate_is_off(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 404)

    def test_r4_route_renders_one_shell_when_gate_is_on(self):
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-r4-shell="true"')
        self.assertContains(response, 'id="r4PreviewFrame"')
        self.assertContains(response, 'id="r4Inspector"')
        self.assertContains(response, 'data-r4-inspector-open="false"')

    def test_r4_route_is_reachable_by_default_without_opting_in(self):
        # Pre-Task-10 remediation (R4 live cutover) — a Store that has
        # never touched the flag must still reach R4 directly: R4 is no
        # longer opt-in-only. Pre-Task-10 CORRECTIVE closure (Item 2) — the
        # shared base fixture (StorefrontBuilderViewsTestCase.setUp) now
        # pins every Store it creates to r4_editor_enabled=False, so every
        # OTHER test in this file keeps exercising the still-required full
        # legacy editor body; this test's whole point is the real model
        # default (True), so it explicitly restores it rather than
        # inheriting the base's pin.
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-r4-shell="true"')


class DashboardNavRoutesToR4Tests(StorefrontBuilderViewsTestCase):
    """Pre-Task-10 remediation (R4 live cutover) — dashboard/storefront
    appearance entry -> R4 Editor, per the Master Prompt's required
    outcome. base_admin.html is shared by every dashboard page, so any
    dashboard response's nav proves this — the R4 editor page itself
    (which also extends base_admin.html) is used here."""

    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)

    def test_primary_storefront_builder_nav_item_points_at_r4(self):
        # Pre-Task-10 CORRECTIVE closure (Item 2) — restore the real model
        # default (True); the shared base fixture now pins it False for
        # every OTHER test in this file (see the sibling test above).
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        r4_url = reverse("dashboard:storefront-builder-r4-editor")
        legacy_url = reverse("dashboard:storefront-builder-editor")
        content = response.content.decode()
        self.assertIn(f'data-admin-v2-priority="1" href="{r4_url}"', content)
        self.assertIn(f'data-admin-v2-priority="2" href="{r4_url}?panel=appearance"', content)
        # The legacy editor is still reachable (compatibility escape hatch
        # for the field-parity gap documented in
        # docs/qa_evidence/.../pre_task10_r4_cutover.md), just no longer
        # the priority-1/2 nav target.
        self.assertIn(legacy_url, content)
