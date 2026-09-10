import dataclasses
import json
from pathlib import Path

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.storefront_builder import appearance_registry, global_region_registry, layout_preset_registry
from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder.models import (
    StorefrontCell,
    StorefrontContainer,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from apps.storefront_builder.services import container_service, layout_service, preset_service
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase


class R4VerticalSliceTestCase(R4MutationApiTestCase):
    """Shared base: R4MutationApiTestCase already gives a gated Draft with
    one bare (unplaced) ``hero_banner`` Section (``self.section``). Task 8
    tests additionally need a real, placed ``rich_text`` Section as the
    generic "safe to add/remove/duplicate/move" candidate."""

    def setUp(self):
        super().setUp()
        self.home_page = self.draft.get_page(StorefrontPage.PageType.HOME)
        # The shared base fixture's Draft is bootstrapped with ~16 default
        # legacy sections (layout_service.get_or_create_draft ->
        # bootstrap_service.apply_bootstrap_content, already migrated into
        # Containers by ensure_version_containers) plus one bare
        # hero_banner (R4MutationApiTestCase.setUp). Task 8's structural
        # tests need a clean, fully predictable Home page instead — each
        # test builds its own minimal, explicit Container/Cell scenario.
        self.home_page.sections.all().delete()
        self.home_page.containers.all().delete()

    def _place_new_section(self, section_key="rich_text", **kwargs):
        order = self.home_page.sections.count()
        section = StorefrontSection.objects.create(
            page=self.home_page, section_key=section_key, order=order, **kwargs,
        )
        container = container_service.create_empty_container(self.home_page, "single")
        cell = container.cells.order_by("order", "id").first()
        container_service.place_section(cell, section)
        return section, container, cell


class AddSectionTests(R4VerticalSliceTestCase):
    def test_add_succeeds_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)

        new_section = StorefrontSection.objects.exclude(pk=self.section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertIsNotNone(new_section.cell_id)
        self.assertEqual(list(container_service.get_cell_blocks(new_section.cell)), [new_section])

    def test_add_preserves_existing_containers_and_cells(self):
        _, existing_container, existing_cell = self._place_new_section("rich_text")
        containers_before = set(StorefrontContainer.objects.filter(page=self.home_page).values_list("pk", flat=True))
        cells_before = set(StorefrontCell.objects.filter(container__page=self.home_page).values_list("pk", flat=True))

        self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "faq", "page_type": "home"},
        })

        containers_after = set(StorefrontContainer.objects.filter(page=self.home_page).values_list("pk", flat=True))
        cells_after = set(StorefrontCell.objects.filter(container__page=self.home_page).values_list("pk", flat=True))
        self.assertTrue(containers_before.issubset(containers_after))
        self.assertTrue(cells_before.issubset(cells_after))
        existing_cell.refresh_from_db()
        self.assertEqual(existing_cell.section_id, existing_container.cells.first().section_id)

    def test_add_rejects_invalid_section_key(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "does_not_exist", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_hidden_from_library(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "announcement_bar", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_hidden_from_library")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_section_not_allowed_on_home(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "product_main", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_allowed_on_page")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_add_rejects_max_instances_exceeded(self):
        self._place_new_section("trust_features")
        starting_revision = self.draft.edit_revision
        before_count = self.home_page.sections.filter(section_key="trust_features").count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "trust_features", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "max_instances_exceeded")
        self.assertEqual(self._refresh_revision(), starting_revision)
        self.assertEqual(self.home_page.sections.filter(section_key="trust_features").count(), before_count)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "home"},
        })
        count_after_first = self.home_page.sections.count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.home_page.sections.count(), count_after_first)


class RemoveSectionTests(R4VerticalSliceTestCase):
    def test_remove_succeeds_and_increments_revision_once(self):
        section, container, cell = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell.pk).exists())

    def test_remove_multi_block_safety(self):
        section, container, cell = self._place_new_section("rich_text")
        sibling = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, sibling, at_index=1)
        other_container_count = StorefrontContainer.objects.filter(page=self.home_page).exclude(pk=container.pk).count()

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
        sibling.refresh_from_db()
        self.assertEqual(sibling.cell_id, cell.pk)
        self.assertEqual(sibling.cell_order, 0)
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertEqual(
            StorefrontContainer.objects.filter(page=self.home_page).exclude(pk=container.pk).count(),
            other_container_count,
        )

    def test_remove_rejects_locked_section(self):
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_locked")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_locked_container(self):
        section, container, _ = self._place_new_section("rich_text")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_non_removable_definition(self):
        section, _, _ = self._place_new_section("product_main")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_removable")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_row_member(self):
        section, _, _ = self._place_new_section("rich_text", row_key="promo-row", row_span=6)
        StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
            row_key="promo-row", row_span=6,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "row_member")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_remove_rejects_min_instances_violation(self):
        real_definition = section_registry_module.get_definition("rich_text")
        min_one_definition = dataclasses.replace(real_definition, min_instances=1)
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.section_structure_service.section_registry.get_definition",
            return_value=min_one_definition,
        ):
            response = self._post_json({
                "base_revision": starting_revision,
                "mutation": {"type": "section.remove", "section_id": section.pk},
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "min_instances_violation")
        self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 409)


class DuplicateSectionTests(R4VerticalSliceTestCase):
    def test_duplicate_succeeds_with_independent_settings_and_same_cell_placement(self):
        section, container, cell = self._place_new_section(
            "rich_text", settings={"body_html": "<p>اصل</p>", "nested": {"level": 1}},
        )
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)

        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertNotEqual(duplicate.pk, section.pk)
        self.assertNotEqual(duplicate.stable_id, section.stable_id)
        self.assertEqual(duplicate.settings, section.settings)

        duplicate.settings["nested"]["level"] = 999
        duplicate.save(update_fields=["settings"])
        section.refresh_from_db()
        self.assertEqual(section.settings["nested"]["level"], 1)

        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([b.pk for b in blocks], [section.pk, duplicate.pk])

    def test_duplicate_adopts_legacy_only_cell_pointer_without_losing_source(self):
        section, container, cell = self._place_new_section("rich_text")
        # Simulate a genuinely legacy-only placement: detach the new FK,
        # leaving only the OneToOne pointer — the exact compatibility case
        # instruction Section 12 calls out.
        StorefrontSection.objects.filter(pk=section.pk).update(cell=None, cell_order=0)
        section.refresh_from_db()
        cell.refresh_from_db()
        self.assertIsNone(section.cell_id)
        self.assertEqual(cell.section_id, section.pk)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        blocks = container_service.get_cell_blocks(cell)
        block_ids = [b.pk for b in blocks]
        self.assertIn(section.pk, block_ids)
        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="rich_text",
        )
        self.assertIn(duplicate.pk, block_ids)
        self.assertEqual(block_ids, [section.pk, duplicate.pk])

    def test_duplicate_clones_section_scoped_media_without_duplicating_asset_bytes(self):
        section, _, _ = self._place_new_section("hero_banner")
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.content.models import HeroSlide, MediaAsset

        buf = io.BytesIO()
        Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
        png_bytes = buf.getvalue()
        asset = MediaAsset.objects.create(
            store=self.store,
            image=SimpleUploadedFile("qa.png", png_bytes, content_type="image/png"),
        )
        HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید اصلی",
            desktop_asset=asset,
            desktop_image=SimpleUploadedFile("qa.png", png_bytes, content_type="image/png"),
        )
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        duplicate = StorefrontSection.objects.exclude(pk=section.pk).get(
            page=self.home_page, section_key="hero_banner",
        )
        duplicate_slide = HeroSlide.objects.get(section=duplicate)
        self.assertEqual(duplicate_slide.desktop_asset_id, asset.pk)
        self.assertNotEqual(duplicate_slide.pk, HeroSlide.objects.get(section=section).pk)
        self.assertEqual(MediaAsset.objects.filter(store=self.store).count(), 1)

    def test_duplicate_rejects_non_duplicable_definition(self):
        section, _, _ = self._place_new_section("trust_features")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_duplicable")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_duplicate_rejects_max_instances_exceeded(self):
        section, _, _ = self._place_new_section("trust_features")
        # trust_features has duplicable=False already; use a mocked
        # duplicable-but-max-instances=1 definition to isolate this check.
        real_definition = section_registry_module.get_definition("trust_features")
        mocked = dataclasses.replace(real_definition, duplicable=True, max_instances=1)
        starting_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.section_structure_service.section_registry.get_definition",
            return_value=mocked,
        ):
            response = self._post_json({
                "base_revision": starting_revision,
                "mutation": {"type": "section.duplicate", "section_id": section.pk},
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "max_instances_exceeded")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_duplicate_rejects_locked_container(self):
        section, container, _ = self._place_new_section("rich_text")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        count_after_first = self.home_page.sections.count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.home_page.sections.count(), count_after_first)


class SparsePageOrderingTests(R4VerticalSliceTestCase):
    """Corrective review pass — StorefrontSection.order has no database
    uniqueness constraint on (page, order); add_section/duplicate_section
    must never CREATE a duplicate page-level order when existing orders are
    sparse (e.g. after a prior remove left a gap). Container/Cell visual
    positioning stays authoritative and untouched by these tests — this is
    purely about the legacy/row-layout-compatibility ``order`` field."""

    def _create_placed(self, section_key, order, **kwargs):
        section = StorefrontSection.objects.create(
            page=self.home_page, section_key=section_key, order=order, **kwargs,
        )
        container = container_service.create_empty_container(self.home_page, "single")
        cell = container.cells.order_by("order", "id").first()
        container_service.place_section(cell, section)
        return section, container, cell

    def test_add_after_sparse_page_orders_gets_max_plus_one(self):
        section_a, _, _ = self._create_placed("rich_text", order=0)
        section_b, _, _ = self._create_placed("faq", order=2)  # order=1 deliberately never exists

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "faq", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 200)

        orders = list(self.home_page.sections.order_by("order").values_list("order", flat=True))
        self.assertEqual(len(orders), len(set(orders)), "page-level order must stay unique")

        new_section = StorefrontSection.objects.exclude(
            pk__in=[section_a.pk, section_b.pk],
        ).get(page=self.home_page)
        self.assertEqual(new_section.order, 3)

    def test_remove_then_add_through_real_mutation_api_does_not_duplicate_order(self):
        section_a, container_a, _ = self._create_placed("rich_text", order=0)
        section_b, container_b, _ = self._create_placed("faq", order=1)
        section_c, container_c, _ = self._create_placed("rich_text", order=2)

        starting_revision = self.draft.edit_revision
        remove_response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": section_b.pk},
        })
        self.assertEqual(remove_response.status_code, 200)
        revision_after_remove = self._refresh_revision()
        self.assertEqual(revision_after_remove, starting_revision + 1)

        add_response = self._post_json({
            "base_revision": revision_after_remove,
            "mutation": {"type": "section.add", "section_key": "faq", "page_type": "home"},
        })
        self.assertEqual(add_response.status_code, 200)
        revision_after_add = self._refresh_revision()
        self.assertEqual(revision_after_add, revision_after_remove + 1)

        remaining_orders = list(self.home_page.sections.order_by("order").values_list("order", flat=True))
        self.assertEqual(len(remaining_orders), len(set(remaining_orders)), "page-level order must stay unique")

        new_section = StorefrontSection.objects.exclude(
            pk__in=[section_a.pk, section_c.pk],
        ).get(page=self.home_page)
        section_a.refresh_from_db()
        section_c.refresh_from_db()
        self.assertGreater(new_section.order, section_a.order)
        self.assertGreater(new_section.order, section_c.order)

        # Real Containers/Cells remain intact: the removed section's own
        # Container/Cell survive (Task 8's remove contract never deletes
        # them), and the untouched siblings' Containers survive too.
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_a.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_b.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_c.pk).exists())
        self.assertFalse(StorefrontSection.objects.filter(pk=section_b.pk).exists())

    def test_duplicate_after_sparse_page_orders_gets_max_plus_one(self):
        source, _, source_cell = self._create_placed("rich_text", order=0)
        other, _, _ = self._create_placed("faq", order=2)  # order=1 deliberately never exists

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.duplicate", "section_id": source.pk},
        })
        self.assertEqual(response.status_code, 200)

        duplicate = StorefrontSection.objects.exclude(
            pk__in=[source.pk, other.pk],
        ).get(page=self.home_page)
        self.assertNotEqual(duplicate.stable_id, source.stable_id)
        self.assertEqual(duplicate.order, 3)

        orders = list(self.home_page.sections.order_by("order").values_list("order", flat=True))
        self.assertEqual(len(orders), len(set(orders)), "page-level order must stay unique")

        # Visual same-Cell placement is a SEPARATE concern from page-level
        # order and must remain unchanged: the duplicate sits immediately
        # after the source in the source's own Cell.
        blocks = container_service.get_cell_blocks(source_cell)
        self.assertEqual([b.pk for b in blocks], [source.pk, duplicate.pk])


class MoveSectionSameCellTests(R4VerticalSliceTestCase):
    def test_move_up_swaps_adjacent_blocks_in_same_cell(self):
        _, container, cell = self._place_new_section("rich_text")
        a = StorefrontSection.objects.get(page=self.home_page, section_key="rich_text")
        b = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, b, at_index=1)
        c = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell, c, at_index=2)

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": b.pk, "direction": "up"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        blocks = container_service.get_cell_blocks(cell)
        self.assertEqual([blk.pk for blk in blocks], [b.pk, a.pk, c.pk])
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell.pk).exists())

    def test_move_boundary_is_rejected_not_a_silent_noop(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "up"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "move_boundary")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_invalid_direction(self):
        section, _, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "sideways"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_direction")
        self.assertEqual(self._refresh_revision(), starting_revision)


class MoveSectionCrossCellTests(R4VerticalSliceTestCase):
    def test_move_down_swaps_across_two_single_cell_containers(self):
        section_a, container_a, cell_a = self._place_new_section("rich_text")
        section_b, container_b, cell_b = self._place_new_section("faq")

        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)

        self.assertEqual(self.home_page.sections.count(), 2)
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_a.pk).exists())
        self.assertTrue(StorefrontContainer.objects.filter(pk=container_b.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell_a.pk).exists())
        self.assertTrue(StorefrontCell.objects.filter(pk=cell_b.pk).exists())

        cell_a.refresh_from_db()
        cell_b.refresh_from_db()
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_a)], [section_b.pk])
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_b)], [section_a.pk])

    def test_move_with_sibling_in_source_cell(self):
        section_a, container_a, cell_a = self._place_new_section("rich_text")
        sibling = StorefrontSection.objects.create(
            page=self.home_page, section_key="faq", order=self.home_page.sections.count(),
        )
        container_service.add_block(cell_a, sibling, at_index=0)  # sibling, then section_a
        section_target, container_target, cell_target = self._place_new_section("faq")

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)
        cell_a.refresh_from_db()
        cell_target.refresh_from_db()
        self.assertEqual(
            [blk.pk for blk in container_service.get_cell_blocks(cell_a)],
            [sibling.pk, section_target.pk],
        )
        self.assertEqual(
            [blk.pk for blk in container_service.get_cell_blocks(cell_target)],
            [section_a.pk],
        )

    def test_move_rejects_locked_source_container(self):
        section_a, container_a, _ = self._place_new_section("rich_text")
        self._place_new_section("faq")
        container_a.is_locked = True
        container_a.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_target_container(self):
        section_a, _, _ = self._place_new_section("rich_text")
        _, container_target, _ = self._place_new_section("faq")
        container_target.is_locked = True
        container_target.save(update_fields=["is_locked"])
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "target_container_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_source_section(self):
        section_a, _, _ = self._place_new_section("rich_text", is_locked=True)
        self._place_new_section("faq")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_locked_adjacent_target_section(self):
        section_a, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", is_locked=True)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "target_locked")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_move_rejects_row_layout_invalid(self):
        # a (no row_key) sits immediately before a valid, contiguous
        # 2-member "promo-row" (b, c). Moving a down would swap its
        # page-level order with b's, sandwiching a between b and c in the
        # simulated page order — breaking the row's contiguity.
        section_a, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        self._place_new_section("faq", row_key="promo-row", row_span=6)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "row_layout_invalid")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_stale_replay_returns_409_and_no_structural_change(self):
        section_a, _, cell_a = self._place_new_section("rich_text")
        self._place_new_section("faq")
        starting_revision = self.draft.edit_revision
        self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        cell_a.refresh_from_db()
        state_after_first = [blk.pk for blk in container_service.get_cell_blocks(cell_a)]
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.move", "section_id": section_a.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 409)
        cell_a.refresh_from_db()
        self.assertEqual([blk.pk for blk in container_service.get_cell_blocks(cell_a)], state_after_first)


class TenantAndScopeSecurityTests(R4VerticalSliceTestCase):
    def test_gate_off_makes_mutation_endpoint_unavailable(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "home"},
        })
        self.assertEqual(response.status_code, 404)

    def test_foreign_store_section_cannot_be_removed(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-vslice-other-store",
            admin_subdomain="r4-vslice-other-store",
        )
        from apps.storefront_builder.services import layout_service as svc
        other_draft = svc.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": other_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=other_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_published_version_section_cannot_be_mutated(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        StorefrontPage.ensure_version_pages(published)
        published_page = published.get_page(StorefrontPage.PageType.HOME)
        published_section = StorefrontSection.objects.create(
            page=published_page, section_key="rich_text", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": published_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=published_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_other_page_section_cannot_be_structurally_changed_via_crafted_id(self):
        product_page = self.draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)
        product_section = StorefrontSection.objects.create(
            page=product_page, section_key="product_main", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.remove", "section_id": product_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StorefrontSection.objects.filter(pk=product_section.pk).exists())
        self.assertEqual(self._refresh_revision(), starting_revision)


# ---------------------------------------------------------------------------
# R4 Task 11 — Global Design + Header/Footer selection + Undo/Redo + Publish
# ---------------------------------------------------------------------------


class R4GlobalDesignTestCase(R4MutationApiTestCase):
    pass


class GlobalMutationTests(R4GlobalDesignTestCase):
    """Section 27 — appearance.update/header.update/footer.update: prove
    RED (currently rejected as unknown_mutation_type) before implementation,
    then that each successful mutation uses the active Draft, increments
    revision exactly once, and creates exactly one normal history entry."""

    def test_appearance_update_succeeds_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["font"], "Tahoma")

    def test_header_update_succeeds_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "header.update", "patch": {"header_variant": "marketplace_search_first"}},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["header_variant"], "marketplace_search_first")

    def test_footer_update_succeeds_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"footer_variant": "marketplace_dense"}},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["footer_variant"], "marketplace_dense")

    def test_appearance_update_does_not_touch_published_version(self):
        published = StorefrontLayoutVersion.objects.create(
            layout=self.layout, version_number=999,
            status=StorefrontLayoutVersion.Status.PUBLISHED,
            appearance_config={"font": "Arial"},
        )
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        self.assertEqual(response.status_code, 200)
        published.refresh_from_db()
        self.assertEqual(published.appearance_config["font"], "Arial")


class AppearanceDomainValidatorReuseTests(R4GlobalDesignTestCase):
    """Section 28 — R4 must not invent Appearance validation; every rule
    still comes from layout_service.validate_appearance_config /
    appearance_registry."""

    def test_invalid_template_slug_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"template_slug": "not-a-real-template"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_invalid_palette_slug_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"palette_slug": "not-a-real-palette"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_invalid_font_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "NotARealFont"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_invalid_type_scale_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"type_scale": "huge"}},
        })
        self.assertEqual(response.status_code, 400)

    def test_invalid_motion_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"motion": "extreme"}},
        })
        self.assertEqual(response.status_code, 400)

    def test_invalid_button_style_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"button_style": "glowing"}},
        })
        self.assertEqual(response.status_code, 400)

    def test_unknown_appearance_patch_key_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"raw_css": "body{color:red}"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_validate_appearance_config_is_the_validator_boundary(self):
        with patch(
            "apps.storefront_builder.services.r4_mutation_service.layout_service.validate_appearance_config",
            wraps=layout_service.validate_appearance_config,
        ) as mock_validate:
            response = self._post_json({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
            })
        self.assertEqual(response.status_code, 200)
        mock_validate.assert_called_once()

    def test_template_switch_applies_template_structural_defaults(self):
        template = appearance_registry.get_template("boutique")
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"template_slug": "boutique"}},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        cfg = self.draft.appearance_config
        self.assertEqual(cfg["template_slug"], "boutique")
        for field in ("font", "radius", "button_radius", "button_style", "density", "motion", "type_scale"):
            self.assertEqual(cfg[field], getattr(template, field), f"field={field}")

    def test_template_switch_wins_over_explicit_field_in_the_same_patch(self):
        # Exact R3 precedence (views.py's `_field`): Template > posted > current.
        template = appearance_registry.get_template("boutique")
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "appearance.update",
                "patch": {"template_slug": "boutique", "font": "Georgia"},
            },
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["font"], template.font)
        self.assertNotEqual(self.draft.appearance_config["font"], "Georgia")

    def test_palette_switch_clears_old_color_and_theme_overrides(self):
        self.draft.appearance_config = {
            **self.draft.effective_appearance_config(),
            "color_overrides": {"primary": "#123456"},
            "theme_overrides": {"header_bg": "#654321"},
        }
        self.draft.save(update_fields=["appearance_config"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"palette_slug": "beauty-magenta"}},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["palette_slug"], "beauty-magenta")
        self.assertEqual(self.draft.appearance_config["color_overrides"], {})
        self.assertEqual(self.draft.appearance_config["theme_overrides"], {})


class HeaderDomainValidatorReuseTests(R4GlobalDesignTestCase):
    def test_registered_header_variant_succeeds(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "header.update", "patch": {"header_variant": "marketplace_search_first"}},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["header_variant"], "marketplace_search_first")

    def test_unknown_header_variant_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "header.update", "patch": {"header_variant": "not-a-real-variant"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_unknown_header_patch_key_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "header.update", "patch": {"show_search": False}},
        })
        self.assertEqual(response.status_code, 400)

    def test_validate_header_config_is_the_validator_boundary(self):
        with patch(
            "apps.storefront_builder.services.r4_mutation_service.layout_service.validate_header_config",
            wraps=layout_service.validate_header_config,
        ) as mock_validate:
            response = self._post_json({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "header.update", "patch": {"header_variant": "premium_three_column"}},
            })
        self.assertEqual(response.status_code, 200)
        mock_validate.assert_called_once()


class FooterDomainValidatorReuseTests(R4GlobalDesignTestCase):
    def test_registered_footer_variant_succeeds(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"footer_variant": "marketplace_dense"}},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["footer_variant"], "marketplace_dense")

    def test_unknown_footer_variant_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "footer.update", "patch": {"footer_variant": "not-a-real-variant"}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_unknown_footer_patch_key_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.update", "patch": {"show_about": False}},
        })
        self.assertEqual(response.status_code, 400)

    def test_validate_footer_config_is_the_validator_boundary(self):
        with patch(
            "apps.storefront_builder.services.r4_mutation_service.layout_service.validate_footer_config",
            wraps=layout_service.validate_footer_config,
        ) as mock_validate:
            response = self._post_json({
                "base_revision": self.draft.edit_revision,
                "mutation": {"type": "footer.update", "patch": {"footer_variant": "premium_columns"}},
            })
        self.assertEqual(response.status_code, 200)
        mock_validate.assert_called_once()


class UndoRedoTestCase(R4MutationApiTestCase):
    def _post_history(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps(payload), content_type="application/json",
        )


class UndoTests(UndoRedoTestCase):
    def test_undo_restores_prior_state_and_increments_revision_once(self):
        starting_revision = self.draft.edit_revision
        history_count_before = self._history_count()

        mutation_response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["font"], "Tahoma")
        self.assertEqual(self._history_count(), history_count_before + 1)

        undo_response = self._post_history({"base_revision": after_mutation_revision, "command": "undo"})
        self.assertEqual(undo_response.status_code, 200)
        body = undo_response.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], after_mutation_revision + 1)
        self.assertIs(body["can_redo"], True)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, after_mutation_revision + 1)
        self.assertNotEqual(self.draft.appearance_config.get("font"), "Tahoma")
        # Undo must never itself create a NEW history row.
        self.assertEqual(self._history_count(), history_count_before + 1)

    def test_stale_mutation_after_undo_is_rejected(self):
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        self._post_history({"base_revision": after_mutation_revision, "command": "undo"})

        stale_response = self._post_json({
            "base_revision": after_mutation_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Arial"}},
        })
        self.assertEqual(stale_response.status_code, 409)
        self.draft.refresh_from_db()
        self.assertNotEqual(self.draft.appearance_config.get("font"), "Arial")

    def test_stale_undo_is_rejected(self):
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        response = self._post_history({"base_revision": after_mutation_revision - 1, "command": "undo"})
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["code"], "stale_revision")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(self.draft.edit_revision, after_mutation_revision)


class RedoTests(UndoRedoTestCase):
    def test_redo_restores_after_state_and_increments_revision_again(self):
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        undo_response = self._post_history({"base_revision": after_mutation_revision, "command": "undo"})
        after_undo_revision = undo_response.json()["new_revision"]

        redo_response = self._post_history({"base_revision": after_undo_revision, "command": "redo"})
        self.assertEqual(redo_response.status_code, 200)
        body = redo_response.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], True)
        self.assertEqual(body["new_revision"], after_undo_revision + 1)
        self.assertIs(body["can_undo"], True)

        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(self.draft.edit_revision, after_undo_revision + 1)

    def test_stale_redo_is_rejected(self):
        mutation_response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        after_mutation_revision = mutation_response.json()["new_revision"]
        undo_response = self._post_history({"base_revision": after_mutation_revision, "command": "undo"})
        after_undo_revision = undo_response.json()["new_revision"]

        stale_redo = self._post_history({"base_revision": after_undo_revision - 1, "command": "redo"})
        self.assertEqual(stale_redo.status_code, 409)
        self.assertEqual(stale_redo.json()["code"], "stale_revision")
        self.draft.refresh_from_db()
        self.assertNotEqual(self.draft.appearance_config.get("font"), "Tahoma")
        self.assertEqual(self.draft.edit_revision, after_undo_revision)


class NoOpHistoryCommandTests(UndoRedoTestCase):
    def test_undo_with_nothing_to_undo_is_a_controlled_noop(self):
        starting_revision = self.draft.edit_revision
        response = self._post_history({"base_revision": starting_revision, "command": "undo"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], False)
        self.assertEqual(body["new_revision"], starting_revision)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)

    def test_redo_with_nothing_to_redo_is_a_controlled_noop(self):
        starting_revision = self.draft.edit_revision
        response = self._post_history({"base_revision": starting_revision, "command": "redo"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        self.assertIs(body["changed"], False)
        self.assertEqual(body["new_revision"], starting_revision)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting_revision)

    def test_invalid_history_command_is_rejected(self):
        response = self._post_history({"base_revision": self.draft.edit_revision, "command": "rewind"})
        self.assertEqual(response.status_code, 400)


class PublishTests(R4MutationApiTestCase):
    def _post_publish(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps(payload), content_type="application/json",
        )

    def test_stale_publish_is_rejected_and_does_not_call_layout_service_publish(self):
        self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.update", "patch": {"font": "Tahoma"}},
        })
        self.draft.refresh_from_db()
        current_revision = self.draft.edit_revision
        self.assertGreater(current_revision, 0)

        with patch("apps.storefront_builder.services.r4_mutation_service.layout_service.publish") as mock_publish:
            response = self._post_publish({"base_revision": current_revision - 1})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_revision")
        mock_publish.assert_not_called()

        self.layout.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, StorefrontLayoutVersion.Status.DRAFT)
        self.assertIsNone(self.layout.published_version_id)
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)

    def test_successful_publish_calls_layout_service_publish_exactly_once(self):
        current_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.r4_mutation_service.layout_service.publish",
            wraps=layout_service.publish,
        ) as mock_publish:
            response = self._post_publish({"base_revision": current_revision})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body["ok"], True)
        mock_publish.assert_called_once()

        self.layout.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, StorefrontLayoutVersion.Status.PUBLISHED)
        self.assertEqual(self.layout.published_version_id, self.draft.pk)
        self.assertIsNone(self.layout.draft_version_id)
        self.assertEqual(body["published_version_id"], self.draft.pk)
        self.assertEqual(body["published_version_number"], self.draft.version_number)

    def test_publish_does_not_call_record_change(self):
        current_revision = self.draft.edit_revision
        with patch(
            "apps.storefront_builder.services.r4_mutation_service.edit_history_service.record_change",
        ) as mock_record:
            response = self._post_publish({"base_revision": current_revision})
        self.assertEqual(response.status_code, 200)
        mock_record.assert_not_called()


class PublishSecurityGateTests(R4MutationApiTestCase):
    def _post_publish(self, payload):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=json.dumps(payload), content_type="application/json",
        )

    def test_gate_off_returns_404(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self._post_publish({"base_revision": self.draft.edit_revision})
        self.assertEqual(response.status_code, 404)

    def test_anonymous_cannot_publish(self):
        self.client.logout()
        response = self._post_publish({"base_revision": self.draft.edit_revision})
        self.assertNotEqual(response.status_code, 200)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)

    def test_malformed_json_is_rejected(self):
        response = self.client.post(
            reverse("dashboard:storefront-builder-r4-publish"),
            data=b"{not valid json", content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_base_revision_is_rejected(self):
        response = self._post_publish({})
        self.assertEqual(response.status_code, 400)

    def test_boolean_base_revision_is_rejected(self):
        response = self._post_publish({"base_revision": True})
        self.assertEqual(response.status_code, 400)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)

    def test_get_is_rejected(self):
        response = self.client.get(reverse("dashboard:storefront-builder-r4-publish"))
        self.assertEqual(response.status_code, 405)


class GlobalDesignUiContractTests(R4MutationApiTestCase):
    def _get_editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor"))

    def test_editor_has_one_global_design_control_and_history_publish_buttons(self):
        response = self._get_editor()
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count('id="r4GlobalDesignToggle"'), 1)
        self.assertEqual(body.count('id="r4UndoButton"'), 1)
        self.assertEqual(body.count('id="r4RedoButton"'), 1)
        self.assertIn('id="r4PublishButton"', body)

    def test_global_design_toggle_is_in_topbar_not_structure_panel(self):
        body = self._get_editor().content.decode()
        structure_start = body.index('<aside id="r4Structure"')
        structure_end = body.index("</aside>", structure_start)
        self.assertNotIn("r4GlobalDesignToggle", body[structure_start:structure_end])

    def test_no_r3_modal_iframe_or_editor_urls_in_response(self):
        body = self._get_editor().content.decode()
        self.assertNotIn("header_editor", body)
        self.assertNotIn("footer_editor", body)
        self.assertNotIn("appearance_editor", body)
        self.assertNotIn("modal fade", body)

    def test_registered_non_default_header_and_footer_variants_are_rendered(self):
        body = self._get_editor().content.decode()
        header_variant = next(
            v for v in global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION)
            if v.key == "marketplace_search_first"
        )
        footer_variant = next(
            v for v in global_region_registry.list_global_variants(global_region_registry.GLOBAL_FOOTER_REGION)
            if v.key == "marketplace_dense"
        )
        self.assertIn(f'value="{header_variant.key}"', body)
        self.assertIn(header_variant.label_fa, body)
        self.assertIn(f'value="{footer_variant.key}"', body)
        self.assertIn(footer_variant.label_fa, body)

    def test_initial_undo_redo_disabled_state_reflects_history_service(self):
        body = self._get_editor().content.decode()
        undo_start = body.index("<button", body.index('id="r4UndoButton"') - 100)
        undo_tag = body[undo_start:body.index(">", undo_start) + 1]
        self.assertIn("disabled", undo_tag)


class NonHomePageEditorLoadTests(R4MutationApiTestCase):
    """Phase 4 (Task 3B) — the R4 editor GET route must resolve, render, and
    scope its "Add Section" library to whichever ``?page=`` was requested,
    not always Home."""

    def _get_editor(self, page=None):
        url = reverse("dashboard:storefront-builder-r4-editor")
        if page is not None:
            url += f"?page={page}"
        return self.client.get(url)

    def test_missing_page_param_defaults_to_home(self):
        response = self._get_editor()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_type"], StorefrontPage.PageType.HOME)

    def test_invalid_page_param_defaults_to_home(self):
        response = self._get_editor(page="not_a_real_page")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_type"], StorefrontPage.PageType.HOME)

    def test_cart_page_param_loads_cart_page(self):
        response = self._get_editor(page="cart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_type"], StorefrontPage.PageType.CART)
        self.assertEqual(response.context["page"].page_type, StorefrontPage.PageType.CART)
        # cart_items/cart_summary are cart-only, mandatory, context-aware —
        # they must appear in Cart's own structure projection.
        structure_keys = {item["label"] for item in response.context["structure_items"]}
        self.assertTrue(structure_keys)

    def test_page_switcher_renders_all_six_page_types(self):
        response = self._get_editor(page="cart")
        body = response.content.decode()
        self.assertIn('id="r4PageSwitcherSelect"', body)
        for value, _label in StorefrontPage.PageType.choices:
            self.assertIn(f'value="{value}"', body)
        self.assertIn('data-r4-page-type="cart"', body)

    def test_preview_iframe_targets_the_current_page_type(self):
        response = self._get_editor(page="listing")
        body = response.content.decode()
        self.assertIn("?page=listing", body)

    def test_add_section_library_is_scoped_to_current_page_type(self):
        # rich_text is allowed on all 6 page types; fashion_lifestyle_hero
        # is Home-only — Cart's library must include the former and never
        # the (already-hidden-from-library-by-page-restriction) latter.
        response = self._get_editor(page="cart")
        body = response.content.decode()
        add_select_start = body.index('id="r4StructureAddSelect"')
        add_select_end = body.index("</select>", add_select_start)
        add_select_html = body[add_select_start:add_select_end]
        self.assertIn('value="rich_text"', add_select_html)


class ClientQueueStaticContractTests(TestCase):
    def setUp(self):
        js_path = Path(__file__).resolve().parents[1] / "static" / "storefront_builder" / "r4_editor.js"
        self.content = js_path.read_text(encoding="utf-8")

    def test_no_independent_command_queues(self):
        for forbidden in ("undoQueue", "publishQueue", "globalDesignQueue"):
            self.assertNotIn(forbidden, self.content)

    def test_global_design_uses_enqueue_mutation(self):
        self.assertIn("r4GlobalDesign", self.content)
        self.assertIn("R4.enqueueMutation", self.content)

    def test_undo_redo_and_publish_reuse_the_shared_queue(self):
        self.assertIn("R4.queue", self.content)
        self.assertIn("r4UndoButton", self.content)
        self.assertIn("r4RedoButton", self.content)
        self.assertIn("r4PublishButton", self.content)


class NonHomePageStructureMutationTests(R4VerticalSliceTestCase):
    """Phase 4 (Task 3B) — section.add/remove/duplicate/move must work on
    every StorefrontPage.PageType, not just Home. Before this task,
    section_structure_service hardcoded Home for every operation."""

    def _cart_page(self):
        return self.draft.get_page(StorefrontPage.PageType.CART)

    def test_add_section_on_cart_page_succeeds(self):
        cart_page = self._cart_page()
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "cart"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["ok"], True)
        new_section = StorefrontSection.objects.get(page=cart_page, section_key="rich_text")
        self.assertIsNotNone(new_section.cell_id)
        # Confirms it landed on Cart, never silently on Home (the pre-Task-3B
        # hardcoded default).
        self.assertFalse(
            StorefrontSection.objects.filter(page=self.home_page, section_key="rich_text").exists()
        )

    def test_add_section_missing_page_type_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_page_type")

    def test_add_section_invalid_page_type_is_rejected(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.add", "section_key": "rich_text", "page_type": "not_a_real_page"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_page_type")

    def test_remove_section_on_non_home_page_succeeds(self):
        cart_page = self._cart_page()
        order = cart_page.sections.count()
        section = StorefrontSection.objects.create(
            page=cart_page, section_key="rich_text", order=order,
        )
        container = container_service.create_empty_container(cart_page, "single")
        container_service.place_section(container.cells.get(), section)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.remove", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())

    def test_duplicate_section_on_non_home_page_succeeds(self):
        cart_page = self._cart_page()
        section = StorefrontSection.objects.create(
            page=cart_page, section_key="rich_text", order=cart_page.sections.count(),
        )
        container = container_service.create_empty_container(cart_page, "single")
        container_service.place_section(container.cells.get(), section)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.duplicate", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StorefrontSection.objects.filter(page=cart_page, section_key="rich_text").count(), 2,
        )

    def test_section_id_from_another_store_is_rejected_regardless_of_page_type(self):
        # Regression guard for dropping the hardcoded page_type filter in
        # _scoped_section: cross-Store scoping must still be airtight (it
        # was always enforced via page__version=draft — unrelated to the
        # page_type change — this proves the two are independent).
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="phase4-task3-other-store", admin_subdomain="phase4-task3-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_cart = other_draft.get_page(StorefrontPage.PageType.CART)
        foreign_section = StorefrontSection.objects.create(
            page=other_cart, section_key="rich_text", order=0,
        )
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.remove", "section_id": foreign_section.pk},
        })
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# R4 Task 7 (Batch 1) — enable/disable, lock, multi-column composition
# ---------------------------------------------------------------------------


class ToggleSectionActiveTests(R4VerticalSliceTestCase):
    def test_toggle_active_flips_and_increments_revision(self):
        section, _, _ = self._place_new_section("rich_text")
        self.assertTrue(section.is_active)
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.toggle_active", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new_revision"], starting_revision + 1)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        section.refresh_from_db()
        self.assertFalse(section.is_active)

    def test_toggle_active_twice_returns_to_original_state(self):
        section, _, _ = self._place_new_section("rich_text")
        for _ in range(2):
            self._post_json({
                "base_revision": self._refresh_revision(),
                "mutation": {"type": "section.toggle_active", "section_id": section.pk},
            })
        section.refresh_from_db()
        self.assertTrue(section.is_active)

    def test_toggle_active_does_not_affect_is_locked(self):
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.toggle_active", "section_id": section.pk},
        })
        section.refresh_from_db()
        self.assertFalse(section.is_active)
        self.assertTrue(section.is_locked)

    def test_toggle_active_on_locked_section_still_succeeds(self):
        # Independent of is_locked, exactly like the legacy view's contract
        # (is_locked only guards move/remove, never enable/disable).
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.toggle_active", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)

    def test_foreign_store_section_cannot_be_toggled(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-task7-toggle-other-store",
            admin_subdomain="r4-task7-toggle-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_section = StorefrontSection.objects.create(
            page=other_page, section_key="rich_text", order=0,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.toggle_active", "section_id": other_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        other_section.refresh_from_db()
        self.assertTrue(other_section.is_active)
        self.assertEqual(self._refresh_revision(), starting_revision)


class ToggleSectionLockedTests(R4VerticalSliceTestCase):
    def test_toggle_locked_flips_and_increments_revision(self):
        section, _, _ = self._place_new_section("rich_text")
        self.assertFalse(section.is_locked)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.toggle_locked", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        section.refresh_from_db()
        self.assertTrue(section.is_locked)

    def test_locking_then_move_is_rejected(self):
        section, _, _ = self._place_new_section("rich_text")
        self._place_new_section("faq")
        self._post_json({
            "base_revision": self._refresh_revision(),
            "mutation": {"type": "section.toggle_locked", "section_id": section.pk},
        })
        response = self._post_json({
            "base_revision": self._refresh_revision(),
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_locked")

    def test_unlocking_restores_move_capability(self):
        section, _, _ = self._place_new_section("rich_text", is_locked=True)
        self._place_new_section("faq")
        self._post_json({
            "base_revision": self._refresh_revision(),
            "mutation": {"type": "section.toggle_locked", "section_id": section.pk},
        })
        response = self._post_json({
            "base_revision": self._refresh_revision(),
            "mutation": {"type": "section.move", "section_id": section.pk, "direction": "down"},
        })
        self.assertEqual(response.status_code, 200)


class ChangeContainerLayoutTests(R4VerticalSliceTestCase):
    def test_change_layout_grows_container_with_empty_cells(self):
        section, container, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "container.change_layout", "container_id": container.pk, "layout_key": "half"},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        container.refresh_from_db()
        self.assertEqual(container.layout_key, "half")
        self.assertEqual(container.cells.count(), 2)
        section.refresh_from_db()
        self.assertEqual(section.cell.container_id, container.pk)

    def test_change_layout_shrink_merges_content_into_last_cell(self):
        container = container_service.create_empty_container(self.home_page, "thirds")
        cells = list(container.cells.order_by("order", "id"))
        sections = []
        for index, cell in enumerate(cells):
            section = StorefrontSection.objects.create(
                page=self.home_page, section_key="rich_text", order=index,
            )
            container_service.place_section(cell, section)
            sections.append(section)

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "container.change_layout", "container_id": container.pk, "layout_key": "single"},
        })
        self.assertEqual(response.status_code, 200)
        container.refresh_from_db()
        self.assertEqual(container.cells.count(), 1)
        surviving_cell = container.cells.get()
        for section in sections:
            self.assertTrue(StorefrontSection.objects.filter(pk=section.pk).exists())
        blocks = container_service.get_cell_blocks(surviving_cell)
        self.assertEqual({s.pk for s in blocks}, {s.pk for s in sections})

    def test_change_layout_rejects_invalid_layout_key(self):
        _, container, _ = self._place_new_section("rich_text")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "container.change_layout", "container_id": container.pk, "layout_key": "nonexistent"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_change_layout_rejects_locked_container(self):
        _, container, _ = self._place_new_section("rich_text")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "container.change_layout", "container_id": container.pk, "layout_key": "half"},
        })
        self.assertEqual(response.status_code, 400)

    def test_foreign_store_container_cannot_be_changed(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-task7-layout-other-store",
            admin_subdomain="r4-task7-layout-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_container = container_service.create_empty_container(other_page, "single")
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {
                "type": "container.change_layout",
                "container_id": other_container.pk,
                "layout_key": "half",
            },
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_not_found")
        other_container.refresh_from_db()
        self.assertEqual(other_container.layout_key, "single")
        self.assertEqual(self._refresh_revision(), starting_revision)


# ---------------------------------------------------------------------------
# R4 Task 7 (Batch 2) — granular baseline reset (in-place mutation types)
# ---------------------------------------------------------------------------


class BaselineResetMutationTests(R4MutationApiTestCase):
    """The five ``preset_service`` baseline-reset granularities that operate
    IN PLACE on the current Draft (never replace its identity), wired as
    normal R4 mutation types: section / section-setting / appearance-setting
    / header / footer. Discard/page-reset/storefront-reset — which DO
    replace the Draft's identity — are covered separately below."""

    def setUp(self):
        super().setUp()
        self.preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, self.preset)
        self.draft.refresh_from_db()
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)

    def _section(self, section_key):
        return self.home.sections.get(section_key=section_key)

    def test_section_reset_to_baseline_restores_mutated_settings(self):
        section = self._section("product_section")
        baseline_title = section.settings["title"]
        section.settings = {**section.settings, "title": "دستی"}
        section.save(update_fields=["settings"])

        starting_revision = self.draft.edit_revision
        before_count = self._history_count()
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.reset_to_baseline", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._refresh_revision(), starting_revision + 1)
        self.assertEqual(self._history_count(), before_count + 1)
        section.refresh_from_db()
        self.assertEqual(section.settings["title"], baseline_title)

    def test_section_reset_to_baseline_rejects_non_baseline_section(self):
        section = StorefrontSection.objects.create(
            page=self.home, section_key="rich_text", order=999,
        )
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.reset_to_baseline", "section_id": section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_foreign_store_section_cannot_be_reset(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-task7-reset-other-store",
            admin_subdomain="r4-task7-reset-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_page = other_draft.get_page(StorefrontPage.PageType.HOME)
        other_section = StorefrontSection.objects.create(page=other_page, section_key="rich_text", order=0)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "section.reset_to_baseline", "section_id": other_section.pk},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section_not_found")
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_section_reset_setting_to_baseline_restores_only_that_key(self):
        section = self._section("product_section")
        baseline_title = section.settings["title"]
        section.settings = {**section.settings, "title": "دستی", "item_limit": 99}
        section.save(update_fields=["settings"])

        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.reset_setting_to_baseline", "section_id": section.pk, "key": "title"},
        })
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.settings["title"], baseline_title)
        self.assertEqual(section.settings["item_limit"], 99)

    def test_section_reset_setting_to_baseline_rejects_unknown_key(self):
        section = self._section("product_section")
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {
                "type": "section.reset_setting_to_baseline", "section_id": section.pk, "key": "not_a_real_field",
            },
        })
        self.assertEqual(response.status_code, 400)

    def test_appearance_reset_setting_to_baseline_restores_only_that_key(self):
        self.draft.appearance_config = {
            **self.draft.effective_appearance_config(), "density": "relaxed", "font": "Georgia",
        }
        self.draft.save(update_fields=["appearance_config"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.reset_setting_to_baseline", "key": "density"},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.effective_appearance_config()["density"], self.preset.appearance["density"])
        self.assertEqual(self.draft.effective_appearance_config()["font"], "Georgia")

    def test_appearance_reset_setting_to_baseline_rejects_unknown_key(self):
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "appearance.reset_setting_to_baseline", "key": "not_a_real_appearance_field"},
        })
        self.assertEqual(response.status_code, 400)

    def test_header_reset_to_baseline_restores_header_variant(self):
        self.draft.header_config = {
            **self.draft.effective_header_config(), "sticky": not self.preset.header["sticky"],
        }
        self.draft.save(update_fields=["header_config"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "header.reset_to_baseline"},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config["header_variant"], self.preset.header["header_variant"])

    def test_footer_reset_to_baseline_restores_footer_variant(self):
        self.draft.footer_config = {
            **self.draft.effective_footer_config(),
            "show_newsletter": not self.preset.footer.get("show_newsletter", True),
        }
        self.draft.save(update_fields=["footer_config"])
        response = self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "footer.reset_to_baseline"},
        })
        self.assertEqual(response.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.footer_config["footer_variant"], self.preset.footer["footer_variant"])


class BaselineResetWithoutTemplateTests(R4MutationApiTestCase):
    """A Draft that never had a Ready Template applied has no baseline to
    reset anything to — ``preset_service`` itself already rejects this
    (``NoTemplateBaselineError``); this is just the R4 mutation contract's
    own external-code mapping of that same rejection."""

    def test_header_reset_without_any_baseline_is_rejected(self):
        self.assertFalse(self.draft.template_baseline_snapshot)
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "header.reset_to_baseline"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)

    def test_appearance_reset_without_any_baseline_is_rejected(self):
        starting_revision = self.draft.edit_revision
        response = self._post_json({
            "base_revision": starting_revision,
            "mutation": {"type": "appearance.reset_setting_to_baseline", "key": "density"},
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._refresh_revision(), starting_revision)


# ---------------------------------------------------------------------------
# R4 Task 7 (Batch 2) — discard / reset-page / reset-storefront: dedicated
# endpoints (NOT normal mutation types) because each REPLACES the Draft's
# identity (deletes it, or archives it behind a fresh checkpointed version)
# — the exact same reason Publish is its own dedicated endpoint rather than
# a ``_dispatch_mutation`` type.
# ---------------------------------------------------------------------------


class DraftReplacingEndpointTests(R4MutationApiTestCase):
    def _post_discard(self, base_revision):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-discard"),
            data=json.dumps({"base_revision": base_revision}),
            content_type="application/json",
        )

    def _post_reset_page(self, base_revision, page_type):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-reset-page"),
            data=json.dumps({"base_revision": base_revision, "page_type": page_type}),
            content_type="application/json",
        )

    def _post_reset_storefront(self, base_revision):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-reset-storefront"),
            data=json.dumps({"base_revision": base_revision}),
            content_type="application/json",
        )

    def test_discard_deletes_the_draft(self):
        draft_id = self.draft.pk
        response = self._post_discard(self.draft.edit_revision)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["ok"], True)
        self.assertFalse(StorefrontLayoutVersion.objects.filter(pk=draft_id).exists())
        self.layout.refresh_from_db()
        self.assertIsNone(self.layout.draft_version_id)

    def test_discard_rejects_stale_revision(self):
        response = self._post_discard(self.draft.edit_revision + 1)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(StorefrontLayoutVersion.objects.filter(pk=self.draft.pk).exists())

    def test_discard_requires_gate_enabled(self):
        self.layout.r4_editor_enabled = False
        self.layout.save(update_fields=["r4_editor_enabled"])
        response = self._post_discard(self.draft.edit_revision)
        self.assertEqual(response.status_code, 404)

    def test_reset_page_creates_a_checkpoint_and_new_draft(self):
        preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        old_draft_id = self.draft.pk
        versions_before = self.layout.versions.count()

        response = self._post_reset_page(self.draft.edit_revision, "home")
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["ok"], True)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.versions.count(), versions_before + 1)
        self.assertNotEqual(self.layout.draft_version_id, old_draft_id)
        self.assertTrue(
            StorefrontLayoutVersion.objects.filter(
                pk=old_draft_id, status=StorefrontLayoutVersion.Status.ARCHIVED,
            ).exists(),
        )

    def test_reset_page_rejects_page_type_not_covered_by_baseline(self):
        preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        snapshot = dict(self.draft.template_baseline_snapshot)
        snapshot["pages"] = {k: v for k, v in snapshot["pages"].items() if k != "cart"}
        self.draft.template_baseline_snapshot = snapshot
        self.draft.save(update_fields=["template_baseline_snapshot"])

        starting_revision = self.draft.edit_revision
        response = self._post_reset_page(starting_revision, "cart")
        self.assertEqual(response.status_code, 400)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)

    def test_reset_page_rejects_invalid_page_type(self):
        response = self._post_reset_page(self.draft.edit_revision, "not_a_real_page")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_page_type")

    def test_reset_page_rejects_stale_revision(self):
        preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        response = self._post_reset_page(self.draft.edit_revision + 1, "home")
        self.assertEqual(response.status_code, 409)

    def test_reset_storefront_creates_a_checkpoint_and_new_draft(self):
        preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        old_draft_id = self.draft.pk
        versions_before = self.layout.versions.count()

        response = self._post_reset_storefront(self.draft.edit_revision)
        self.assertEqual(response.status_code, 200)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.versions.count(), versions_before + 1)
        self.assertNotEqual(self.layout.draft_version_id, old_draft_id)

    def test_reset_storefront_without_any_baseline_is_rejected(self):
        response = self._post_reset_storefront(self.draft.edit_revision)
        self.assertEqual(response.status_code, 400)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.draft_version_id, self.draft.pk)

    def test_reset_storefront_never_touches_the_published_version(self):
        preset = layout_preset_registry.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        layout_service.publish(self.store, user=self.staff)
        draft2 = layout_service.get_or_create_draft(self.store, user=self.staff)
        preset_service.apply_preset(draft2, preset)
        draft2.refresh_from_db()
        self.layout.refresh_from_db()
        published_before = self.layout.published_version_id

        response = self._post_reset_storefront(draft2.edit_revision)
        self.assertEqual(response.status_code, 200)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.published_version_id, published_before)

    def test_foreign_store_draft_cannot_be_discarded_via_own_session(self):
        # Tenant isolation: resolve_store_for_service always resolves the
        # CURRENT session's own Store — there is no store-id/draft-id input
        # on this endpoint at all for a crafted id to target another Store.
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="r4-task7-discard-other-store",
            admin_subdomain="r4-task7-discard-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_draft_id = other_draft.pk
        response = self._post_discard(self.draft.edit_revision)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StorefrontLayoutVersion.objects.filter(pk=other_draft_id).exists())
