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



# ------------------------------------------------------------------------
# Phase 5 Task 4C — R4 device preview (Desktop / Tablet / Mobile). Ported
# from the legacy sfb-v3-device-switcher pattern; it only changes the
# presentation width/scale of the EXISTING #r4PreviewFrame iframe — never a
# second renderer / preview URL / iframe / srcdoc. UI-only state, never
# persisted to Store/Draft/database.
# ------------------------------------------------------------------------

from pathlib import Path

from django.conf import settings as dj_settings


class R4DevicePreviewMarkupTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.layout = svc.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])

    def _editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor"))

    def test_editor_has_a_device_switcher_with_three_accessible_modes(self):
        response = self._editor()
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-r4-device-switcher', content)
        # Three modes, each an accessible toggle with aria-pressed.
        for device in ("desktop", "tablet", "mobile"):
            self.assertIn(f'data-r4-device="{device}"', content)
        self.assertGreaterEqual(content.count("aria-pressed"), 3)
        # Desktop is the default selected state.
        desktop_idx = content.index('data-r4-device="desktop"')
        desktop_chunk = content[desktop_idx:desktop_idx + 120]
        self.assertIn('aria-pressed="true"', desktop_chunk)

    def test_device_switcher_does_not_introduce_a_second_preview_frame(self):
        response = self._editor()
        content = response.content.decode()
        # Still exactly one preview iframe, the canonical #r4PreviewFrame.
        self.assertEqual(content.count("<iframe"), 1)
        self.assertIn('id="r4PreviewFrame"', content)
        # No srcdoc / fake preview markup.
        self.assertNotIn("srcdoc", content)


class R4DevicePreviewJsContractTests(StorefrontBuilderViewsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js_source = Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")

    def test_device_switcher_resizes_the_existing_preview_frame_only(self):
        self.assertIn("data-r4-device-switcher", self.js_source)
        self.assertIn("data-r4-device", self.js_source)
        # It manipulates the SAME canonical preview frame reference.
        self.assertIn("previewFrame", self.js_source)

    def test_device_switcher_uses_aria_pressed_for_selected_state(self):
        self.assertIn("aria-pressed", self.js_source)

    def test_device_state_is_never_persisted(self):
        # UI-only preview state — never written to Store/Draft/localStorage,
        # and never through the mutation queue.
        self.assertNotIn("localStorage", self.js_source)
        # P5-W3 — the sanctioned POST fetches are now five: the three canonical
        # WRITE endpoints (mutate/history/publish) PLUS the two Design Lab
        # transient-candidate calls (callDesignLab + applyCandidate's payload
        # round-trip). The Design Lab endpoint (design-lab/) is READ-ONLY — it
        # computes transient candidates and WRITES NOTHING; the actual Design
        # Lab persistence still flows through the SAME mutate/ endpoint. Device
        # switching itself still adds no POST path. (Guard intent: no ROGUE
        # write path — see test_write_endpoints_are_only_the_sanctioned_r4_targets.)
        self.assertEqual(self.js_source.count("method: 'POST'"), 5)

    def test_device_switcher_adds_no_second_renderer_or_preview_url(self):
        # No new iframe creation, no srcdoc, no second preview src.
        self.assertNotIn("srcdoc", self.js_source)
        self.assertNotIn("createElement('iframe')", self.js_source)
        self.assertNotIn('createElement("iframe")', self.js_source)
