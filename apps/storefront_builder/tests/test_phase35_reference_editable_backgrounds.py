from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_views import StorefrontBuilderViewsTestCase


def _img(name="bg.png"):
    buf = BytesIO()
    Image.new("RGB", (10, 10), (120, 80, 40)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class Phase35ReferencePresetContractTests(TestCase):
    def test_reference_preset_keeps_the_approved_dense_homepage_sequence(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        self.assertEqual(
            [entry.section_key for entry in preset.pages["home"]],
            [
                "product_section", "hero_banner",
                "category_grid",
                "trust_features",
                "multi_banner",
                "product_section",
                "amazing_offers",
                "product_section",
                "multi_banner", "multi_banner",
                "product_section",
                "multi_banner", "multi_banner",
                "product_section", "product_section",
                "product_section",
                "product_section", "product_section",
                "multi_banner",
                "product_section",
                "multi_banner",
                "product_section",
            ],
        )

    def test_reference_preset_is_merchant_facing_and_keeps_colored_rails(self):
        preset = layout_preset_registry.get_layout_preset("v5_golden_homepage")
        self.assertEqual(preset.label_fa, "فروشگاه رنگی و کاتالوگی — مرجع")
        rails = [
            e for e in preset.pages["home"]
            if e.section_key == "product_section"
            and (e.settings or {}).get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertEqual(len(rails), 5)
        self.assertEqual(
            {e.settings["background"]["palette_role"] for e in rails},
            {"tone-1", "tone-2", "tone-3", "tone-4", "tone-5"},
        )
        self.assertEqual(preset.default_palette_slug, "catalog-colorful")


class Phase35ReferencePresetUndoSafetyTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.page = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.page.containers.all().delete()
        self.page.sections.all().delete()
        self.draft.edit_history_entries.all().delete()

    def test_reference_preset_apply_is_one_undo_step_and_restores_previous_draft(self):
        """Acceptance Batch 2 (post-U11) correction: applying a Ready
        Template over a Draft with real existing content (``original``
        below) now preserves that content as a recoverable version-history
        checkpoint (Issue 1) instead of a local Undo/Redo entry — the same
        Draft-identity-boundary rule ``publish()`` already applies to
        Undo/Redo (see ``test_u1a_preset_edit_history_characterization.py``
        for the full rationale). The previous Draft state is still fully
        recoverable, just via History → Restore instead of Undo."""
        original = StorefrontSection.objects.create(
            page=self.page,
            section_key="rich_text",
            order=0,
            settings={"body_html": "<p>قبل از مرجع</p>"},
        )
        original_stable_id = original.stable_id
        container = container_service.create_empty_container(self.page, "single")
        container_service.place_section(container.cells.get(), original)

        # ARCH-02: non-ready structural presets are no longer applicable through the dashboard endpoint; this
        # characterizes the (unchanged) checkpointing service directly.
        from apps.storefront_builder import layout_preset_registry as _lpr
        from apps.storefront_builder.services import preset_service as _preset_service

        _preset_service.apply_preset_with_checkpoint(
            self.store, _lpr.get_layout_preset("v5_golden_homepage"), user=self.staff,
        )

        layout = layout_service.get_or_create_layout(self.store)
        new_draft = layout.draft_version
        self.assertNotEqual(new_draft.pk, self.draft.pk)
        self.assertEqual(new_draft.appearance_config.get("layout_preset_key"), "v5_golden_homepage")
        self.assertGreater(new_draft.get_page(StorefrontPage.PageType.HOME).sections.count(), 1)

        # No Undo entry against either row — the checkpoint is the recovery
        # mechanism for this action.
        self.assertEqual(new_draft.edit_history_entries.count(), 0)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, StorefrontLayoutVersion.Status.ARCHIVED)
        self.assertEqual(self.draft.edit_history_entries.count(), 0)

        checkpoint = layout.versions.filter(status=StorefrontLayoutVersion.Status.ARCHIVED).latest("version_number")
        self.assertEqual(checkpoint.pk, self.draft.pk)
        restored = layout_service.restore_version(self.store, checkpoint.pk, user=self.staff)
        restored_section = restored.get_page(StorefrontPage.PageType.HOME).sections.get(stable_id=original_stable_id)
        self.assertEqual(restored_section.settings["body_html"], "<p>قبل از مرجع</p>")

        self.draft.refresh_from_db()
        restored_page = self.draft.get_page(StorefrontPage.PageType.HOME)
        restored = list(restored_page.sections.order_by("order", "id"))
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].section_key, "rich_text")
        self.assertEqual(restored[0].stable_id, original_stable_id)
        restored_container = restored_page.containers.get()
        restored_cell = restored_container.cells.get()
        self.assertEqual(restored_cell.section.stable_id, original_stable_id)
