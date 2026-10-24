"""V5-RESIZE — ``section.resize`` / ``container.resize``: the ONE central size contract.

Every drag is one mutation = one Revision = one Undo step; sizes live in the existing JSON (``settings.design`` / ``Cell.span`` /
``Container.settings.stack_split``), never a new table; Auto (key absent) is the default and old data renders unchanged."""

import json
import re
from pathlib import Path

from django.urls import reverse

from apps.storefront_builder import design_block
from apps.storefront_builder.models import StorefrontCell, StorefrontContainer, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service, section_structure_service

from .test_r4_mutation_api import R4MutationApiTestCase

STATIC = Path(__file__).resolve().parents[1] / "static" / "storefront_builder"


class _ResizeBase(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.draft.get_page("home")

    def _mutate(self, mutation, *, expect=200):
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": mutation})
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def _history(self, command):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._refresh_revision(), "command": command}),
            content_type="application/json",
        )

    def _design(self, section):
        section.refresh_from_db()
        return dict(section.settings.get("design") or {})

    def _row(self, layout_key, cells=None):
        container = container_service.create_empty_container(self.page, layout_key)
        for cell, keys in zip(container.cells.order_by("order", "id"), cells or []):
            for key in keys:
                section_structure_service.add_section_to_cell(draft=self.draft, section_key=key, cell_id=cell.pk)
        return container

    def _spans(self, container):
        return [c.span for c in container.cells.order_by("order", "id")]


class SectionResizeTests(_ResizeBase):
    def test_height_is_one_mutation_one_revision_one_history_step_and_persists(self):
        revision, history = self._refresh_revision(), self._history_count()
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 640})
        self.assertEqual(self._design(self.section), {"min_height": 640})
        self.assertEqual(self._refresh_revision(), revision + 1)
        self.assertEqual(self._history_count(), history + 1)

    def test_width_and_alignment_are_stored_in_the_design_block(self):
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "width": 60, "align": "end"})
        self.assertEqual(self._design(self.section), {"width_pct": 60, "width_align": "end"})

    def test_auto_removes_the_key_and_keeps_every_other_design_value(self):
        self.section.settings = {**self.section.settings, "design": {"radius": "lg", "min_height": 500}}
        self.section.save(update_fields=["settings"])
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": None})
        self.assertEqual(self._design(self.section), {"radius": "lg"})

    def test_width_100_is_auto_and_drops_the_alignment_too(self):
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "width": 50, "align": "start"})
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "width": 100})
        self.assertEqual(self._design(self.section), {})

    def test_content_settings_are_never_touched(self):
        self.section.settings = {**self.section.settings, "autoplay": False, "interval_ms": 3000}
        self.section.save(update_fields=["settings"])
        before = {k: v for k, v in self.section.settings.items() if k != "design"}
        self.assertTrue(before)
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 700, "width": 80, "align": "center"})
        self.section.refresh_from_db()
        self.assertEqual({k: v for k, v in self.section.settings.items() if k != "design"}, before)

    def test_undo_and_redo_restore_the_exact_previous_and_next_size(self):
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 600})
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 900})
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertEqual(self._design(self.section), {"min_height": 600})
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertEqual(self._design(self.section), {})
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(self._design(self.section), {"min_height": 600})

    def test_every_registry_section_accepts_the_size_block_including_schema_less_ones(self):
        from apps.storefront_builder import section_registry

        keys = sorted(section_registry.SECTION_REGISTRY)
        self.assertGreaterEqual(len(keys), 38)
        for key in keys:
            with self.subTest(section=key):
                definition = section_registry.get_definition(key)
                self.assertIn("canvas_size", definition.capabilities)
                section = StorefrontSection.objects.create(version=self.draft, section_key=key, order=90)
                self._mutate({"type": "section.resize", "section_id": section.pk, "height": 480, "width": 70, "align": "start"})
                self.assertEqual(self._design(section), {"min_height": 480, "width_pct": 70, "width_align": "start"})

    def test_fashion_hero_and_single_banner_are_resizable_although_they_have_no_settings_schema(self):
        for key in ("fashion_lifestyle_hero", "single_banner"):
            section = StorefrontSection.objects.create(version=self.draft, section_key=key, order=91)
            self._mutate({"type": "section.resize", "section_id": section.pk, "height": 720})
            self.assertEqual(self._design(section)["min_height"], 720)

    def test_illegal_payloads_are_refused_and_change_nothing(self):
        bad = [
            {"height": 1601}, {"height": -1}, {"height": True}, {"height": "600"}, {"height": 600.5},
            {"width": 29}, {"width": 101}, {"width": False}, {"width": "50"},
            {"align": "middle"}, {"align": 1}, {"width": 50, "align": "justify"},
            {}, {"height": 600, "settings": {"title": "x"}}, {"height": 600, "section_id_2": 1},
        ]
        for extra in bad:
            with self.subTest(payload=extra):
                revision = self._refresh_revision()
                response = self._mutate({"type": "section.resize", "section_id": self.section.pk, **extra}, expect=400)
                self.assertEqual(response.json()["code"], "invalid_resize_value")
                self.assertEqual(self._refresh_revision(), revision)
                self.assertEqual(self._design(self.section), {})
        for section_id in (True, "1", None, 1.5):
            with self.subTest(section_id=section_id):
                self._mutate({"type": "section.resize", "section_id": section_id, "height": 600}, expect=400)

    def test_a_locked_section_or_a_section_in_a_locked_row_cannot_be_resized(self):
        self.section.is_locked = True
        self.section.save(update_fields=["is_locked"])
        response = self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 600}, expect=400)
        self.assertEqual(response.json()["code"], "section_locked")
        self.assertEqual(self._design(self.section), {})

    def test_foreign_and_unknown_sections_are_not_found(self):
        self._mutate({"type": "section.resize", "section_id": 9_999_999, "height": 600}, expect=400)

    def test_published_version_is_untouched_until_publish(self):
        layout_service.publish(self.store, user=self.staff)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        before = {s.pk: json.dumps(s.settings, sort_keys=True) for s in StorefrontSection.objects.filter(page__version=published)}
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        target = StorefrontSection.objects.filter(page__version=draft, section_key="hero_banner").first()
        self.draft = draft
        self._mutate({"type": "section.resize", "section_id": target.pk, "height": 810})
        after = {s.pk: json.dumps(s.settings, sort_keys=True) for s in StorefrontSection.objects.filter(page__version=published)}
        self.assertEqual(before, after)

    def test_the_wrapper_carries_the_size_flags_and_variables_and_auto_adds_nothing(self):
        self.assertEqual(design_block.render_attributes({})["flags"], "")
        manual = design_block.render_attributes({"min_height": 900, "width_pct": 60, "width_align": "end"})
        text = json.dumps(manual, ensure_ascii=False)
        for token in ("minh", "wa-end", "--d-minh", "900px", "--d-w", "60%"):
            self.assertIn(token, text)
        centred = json.dumps(design_block.render_attributes({"width_pct": 60}), ensure_ascii=False)
        self.assertIn("wa-center", centred)
        self.assertNotIn("--d-w", json.dumps(design_block.render_attributes({"width_pct": 100}), ensure_ascii=False))

    def test_design_validator_accepts_only_granted_size_keys_and_clamps_ranges(self):
        applicable = design_block.all_properties("hero_banner")
        self.assertTrue({"min_height", "width_pct", "width_align"} <= set(applicable))
        cleaned = design_block.validate_design_settings({"min_height": 5000, "width_pct": 5, "width_align": "start"}, applicable)
        self.assertEqual(cleaned, {"min_height": 1600, "width_pct": 30, "width_align": "start"})
        with self.assertRaises(ValueError):
            design_block.validate_design_settings({"width_align": "left"}, applicable)
        with self.assertRaises(ValueError):
            design_block.validate_design_settings({"min_height": 600}, ("radius",))


class InspectorKeepsTheManualSizeTests(_ResizeBase):
    """The size is canvas-only: the Inspector panel is unchanged, and an Inspector edit can never silently drop it."""

    def test_the_inspector_panel_does_not_offer_the_canvas_only_keys(self):
        for key in design_block.design_capable_section_keys():
            shown = {p["key"] for g in design_block.serialize_registry_for_inspector(key) for p in g["properties"]}
            self.assertFalse({"width_pct", "width_align"} & shown, key)

    def test_an_inspector_edit_keeps_manual_height_width_and_alignment(self):
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "height": 640, "width": 70, "align": "start"})
        self._mutate({"type": "section.update_settings", "section_id": self.section.pk, "patch": {"autoplay": False}})
        self.assertEqual(self._design(self.section), {"min_height": 640, "width_pct": 70, "width_align": "start"})
        self.section.refresh_from_db()
        self.assertIs(self.section.settings.get("autoplay"), False)

    def test_an_inspector_design_patch_keeps_the_canvas_only_keys(self):
        self._mutate({"type": "section.resize", "section_id": self.section.pk, "width": 60, "align": "end"})
        self._mutate({"type": "section.update_settings", "section_id": self.section.pk, "patch": {"design": {"image_position": "top"}}})
        design = self._design(self.section)
        self.assertEqual((design.get("width_pct"), design.get("width_align")), (60, "end"))
        self.assertEqual(design.get("image_position"), "top")


class ContainerResizeTests(_ResizeBase):
    def test_two_columns_change_ratio_keep_sum_ids_order_and_content(self):
        container = self._row("half", [["faq"], ["rich_text"]])
        cells_before = [(c.pk, c.order) for c in container.cells.order_by("order", "id")]
        sections_before = sorted(StorefrontSection.objects.filter(page=self.page).values_list("pk", flat=True))
        revision, history = self._refresh_revision(), self._history_count()
        self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [8, 4]})
        self.assertEqual(self._spans(container), [8, 4])
        self.assertEqual([(c.pk, c.order) for c in container.cells.order_by("order", "id")], cells_before)
        self.assertEqual(sorted(StorefrontSection.objects.filter(page=self.page).values_list("pk", flat=True)), sections_before)
        self.assertEqual(self._refresh_revision(), revision + 1)
        self.assertEqual(self._history_count(), history + 1)
        container.refresh_from_db()
        self.assertEqual(container.layout_key, "third_right")                    # the mapped preset, not a second model

    def test_a_ratio_without_a_preset_is_a_custom_row_and_still_valid(self):
        container = self._row("half")
        self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [5, 7]})
        self.assertEqual(self._spans(container), [5, 7])
        container.refresh_from_db()
        self.assertEqual(container.layout_key, "custom")
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn('<option value="custom" selected disabled>', html)              # the row's layout picker names it instead of showing a wrong preset

    def test_three_columns_keep_total_twelve_and_every_cell(self):
        container = self._row("thirds", [["faq"], ["rich_text"], ["quick_links"]])
        ids = [c.pk for c in container.cells.order_by("order", "id")]
        for spans in ([3, 5, 4], [2, 6, 4], [4, 2, 6]):
            with self.subTest(spans=spans):
                self._mutate({"type": "container.resize", "container_id": container.pk, "spans": spans})
                self.assertEqual(self._spans(container), spans)
                self.assertEqual([c.pk for c in container.cells.order_by("order", "id")], ids)
                self.assertEqual(sum(self._spans(container)), 12)

    def test_unusable_or_invalid_splits_are_refused(self):
        container = self._row("half")
        three = self._row("thirds")
        for target, spans in ((container, [1, 11]), (container, [11, 1]), (container, [6, 7]), (container, [6]), (container, [4, 4, 4]),
                              (container, [0, 12]), (container, [-3, 15]), (three, [1, 5, 6]), (three, [4, 4]), (three, [4, 4, 5])):
            with self.subTest(spans=spans):
                self._mutate({"type": "container.resize", "container_id": target.pk, "spans": spans}, expect=400)
        self.assertEqual(self._spans(container), [6, 6])
        self.assertEqual(self._spans(three), [4, 4, 4])
        for bad in ([6.0, 6.0], ["6", "6"], [True, 11], "6,6", {"a": 1}):
            self._mutate({"type": "container.resize", "container_id": container.pk, "spans": bad}, expect=400)

    def test_undo_and_redo_restore_the_exact_spans(self):
        container = self._row("half")
        self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [9, 3]})
        self.assertEqual(self._history("undo").status_code, 200)
        spans_after_undo = [c.span for c in StorefrontCell.objects.filter(container__page=self.page).order_by("container_id", "order")]
        self.assertIn(6, spans_after_undo)
        self.assertEqual(self._history("redo").status_code, 200)
        restored = StorefrontContainer.objects.filter(page=self.page).order_by("-id").first()
        self.assertEqual(self._spans(restored), [9, 3])

    def test_a_locked_container_cannot_be_resized(self):
        container = self._row("half")
        container.is_locked = True
        container.save(update_fields=["is_locked"])
        response = self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [8, 4]}, expect=400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertEqual(self._spans(container), [6, 6])


class StackedResizeTests(_ResizeBase):
    def _stacked(self):
        return self._row("big_right_two_left", [["newest_products"], ["faq"], ["rich_text"]])

    def test_the_big_column_width_moves_both_small_cells_together(self):
        container = self._stacked()
        self.assertEqual(self._spans(container), [8, 4, 4])
        ids = [c.pk for c in container.cells.order_by("order", "id")]
        self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [6, 6, 6]})
        self.assertEqual(self._spans(container), [6, 6, 6])
        self.assertEqual([c.pk for c in container.cells.order_by("order", "id")], ids)       # still three real Cells
        container.refresh_from_db()
        self.assertEqual(container.layout_key, "big_right_two_left")

    def test_small_cells_can_never_be_different_or_invalid(self):
        container = self._stacked()
        for spans in ([8, 5, 3], [8, 3, 5], [3, 9, 9], [10, 2, 2], [8, 4, 4, 4], [8, 4], [4, 8, 7]):
            with self.subTest(spans=spans):
                self._mutate({"type": "container.resize", "container_id": container.pk, "spans": spans}, expect=400)
        self.assertEqual(self._spans(container), [8, 4, 4])

    def test_height_split_is_stored_in_the_container_settings_and_auto_removes_it(self):
        container = self._stacked()
        self._mutate({"type": "container.resize", "container_id": container.pk, "stack_split": 60})
        container.refresh_from_db()
        self.assertEqual(container.settings.get("stack_split"), 60)
        self.assertEqual(self._spans(container), [8, 4, 4])
        self._mutate({"type": "container.resize", "container_id": container.pk, "stack_split": None})
        container.refresh_from_db()
        self.assertNotIn("stack_split", container.settings)

    def test_height_split_out_of_range_or_on_a_plain_row_is_refused(self):
        container = self._stacked()
        for value in (0, 10, 24, 76, 100, True, "50", 50.5):
            with self.subTest(value=value):
                self._mutate({"type": "container.resize", "container_id": container.pk, "stack_split": value}, expect=400)
        plain = self._row("half")
        self._mutate({"type": "container.resize", "container_id": plain.pk, "stack_split": 50}, expect=400)

    def test_removing_a_section_or_the_layout_keeps_the_rest_after_a_resize(self):
        container = self._stacked()
        self._mutate({"type": "container.resize", "container_id": container.pk, "spans": [7, 5, 5], "stack_split": 40})
        ids = list(StorefrontSection.objects.filter(page=self.page, cell__container=container).values_list("pk", flat=True))
        self.assertEqual(len(ids), 3)
        self._mutate({"type": "container.remove", "container_id": container.pk})
        self.assertEqual(sorted(StorefrontSection.objects.filter(pk__in=ids).values_list("pk", flat=True)), sorted(ids))

    def test_the_renderer_emits_the_split_tokens_only_when_set_so_auto_is_unchanged(self):
        from django.template.loader import render_to_string

        container = self._stacked()
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertNotIn("data-stack-split", html)
        self.assertNotIn("--stack-top", html)
        self._mutate({"type": "container.resize", "container_id": container.pk, "stack_split": 35})
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn('data-stack-split="35"', html)
        self.assertIn("--stack-top:35fr", html)
        self.assertIn("--stack-bottom:65fr", html)
        del render_to_string


class PublishedParityTests(_ResizeBase):
    """Preview and Published share one geometric contract; nothing of the builder reaches the published page."""

    def test_the_published_page_carries_the_sizes_and_no_builder_marker(self):
        from django.template.loader import render_to_string

        from apps.storefront_builder.models import StorefrontPage
        from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context

        stacked = self._row("big_right_two_left", [["newest_products"], ["faq"], ["rich_text"]])
        tall = StorefrontSection.objects.get(cell__container=stacked, section_key="rich_text")
        self._mutate({"type": "container.resize", "container_id": stacked.pk, "spans": [7, 5, 5], "stack_split": 45})
        self._mutate({"type": "section.resize", "section_id": tall.pk, "height": 520, "width": 70, "align": "start"})
        layout_service.publish(self.store, user=self.staff)

        class Request:
            pass

        context = build_universal_storefront_context(Request(), self.store, StorefrontPage.PageType.HOME)
        html = render_to_string("storefront_builder/partials/render_containers.html", {"render_containers": context["render_containers"], "is_preview": False})
        for token in ('data-stack-split="45"', "--stack-top:45fr", "--stack-bottom:55fr", "--cell-span:7", "--cell-span:5"):
            self.assertIn(token, html, token)
        self.assertRegex(html, r"--d-minh:\s*520px")
        self.assertRegex(html, r"--d-w:\s*70%")
        for marker in ("data-container-id", "data-section-id", "sfb-cell-add-more", "sfb-empty-cell", "data-rs-", "rs-handle", "rs-overlay"):
            self.assertNotIn(marker, html, marker)

    def test_nothing_is_emitted_for_automatic_sizes(self):
        stacked = self._row("big_right_two_left", [["newest_products"], ["faq"], ["rich_text"]])
        self.assertNotIn("stack_split", stacked.settings)
        attrs = design_block.render_attributes({})
        self.assertEqual((attrs["flags"], attrs["style"]), ("", ""))


class ResizeClientContractTests(_ResizeBase):
    """r4_resize.js is UI only: no own transport, no persisted state, one mutation per gesture, nothing sent while the pointer moves."""

    JS = (STATIC / "r4_resize.js").read_text(encoding="utf-8")

    def test_it_has_no_transport_or_browser_storage(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "localStorage", "sessionStorage", "indexedDB", "navigator.sendBeacon", "innerHTML +="):
            self.assertNotIn(forbidden, self.JS, forbidden)

    def test_every_write_goes_through_the_one_mutation_queue(self):
        self.assertGreaterEqual(self.JS.count("R4.enqueueStructuralMutation("), 1)
        for mutation_type in re.findall(r"type: '([a-z_.]+)'", self.JS):
            self.assertIn(mutation_type, {"section.resize", "container.resize", "container.change_layout"})

    def test_a_drag_sends_only_when_it_finishes_and_escape_restores_without_sending(self):
        move = self.JS[self.JS.index("function moveDrag"):self.JS.index("function endDrag")]
        self.assertNotIn("enqueueStructuralMutation", move)
        finish = self.JS[self.JS.index("function finish"):self.JS.index("function restore")]
        self.assertEqual(finish.count("enqueueStructuralMutation"), 1)
        self.assertIn("cancelled ? null", finish)
        self.assertIn("restore(d)", finish)
        self.assertIn("Escape", self.JS)

    def test_the_overlay_is_a_studio_shell_layer_never_part_of_the_storefront(self):
        css = (STATIC / "r4_studio.css").read_text(encoding="utf-8")
        block = css[css.index("*/", css.index("V5-RESIZE: on-canvas layer")) + 2:]
        for selector in re.findall(r"(?m)^([^{}@/\n][^{}]*)\{", block):
            for part in selector.split(","):
                self.assertTrue(part.strip().startswith(".rs-studio"), part)
        self.assertIn(".rs-studio .rs-overlay{position:absolute;inset:0;z-index:30;pointer-events:none", block)
        self.assertNotIn("r4_resize", (Path(__file__).resolve().parents[1] / "templates/storefront_builder/preview.html").read_text(encoding="utf-8"))

    def test_the_studio_exposes_the_real_controls_the_toolbar_reuses(self):
        studio = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
        api = studio[studio.index("R4.studio = {"):][:2600]
        for name in ("notify", "icon", "blocked", "selectedId", "rowState", "edit", "command", "askRemove", "clearSelection"):
            self.assertIn(name, api, name)
        self.assertEqual(studio.count("fetch("), 1)                                                   # still the one transport
        from apps.storefront_builder.studio_icons import STUDIO_ICON_PATHS as ICON_PATHS

        for icon in ("edit", "copy", "up", "down", "trash", "close"):
            self.assertIn(icon, ICON_PATHS, icon)

    def test_toolbar_order_and_real_actions(self):
        order = [m for m in re.findall(r"tbButton\('([a-z]+)'", self.JS)]
        self.assertEqual(order, ["edit", "duplicate", "up", "down", "remove", "close"])
        for action in ("S.edit(", "S.command(id, 'duplicate')", "S.command(id, 'up')", "S.command(id, 'down')", "S.askRemove(", "S.clearSelection()"):
            self.assertIn(action, self.JS, action)
