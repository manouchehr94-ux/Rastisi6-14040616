"""V5-LAYOUT-ATOMIC — ``container.add``: one request, one Revision, one history step, all-or-nothing.

Reuses only existing primitives (``create_empty_container`` + ``add_section_to_cell``) through the ONE R4 mutation boundary."""

import json

from django.urls import reverse

from apps.storefront_builder.models import StorefrontCell, StorefrontContainer, StorefrontEditHistoryEntry, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service, r4_mutation_service

from .test_r4_mutation_api import R4MutationApiTestCase


class ContainerAddTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.draft.get_page("home")
        container_service.ensure_page_containers(self.page)          # the fixture's unplaced hero is wrapped once, up front (as add_section does)

    # ---- helpers
    def _counts(self):
        return (
            StorefrontContainer.objects.filter(page__version=self.draft).count(),
            StorefrontCell.objects.filter(container__page__version=self.draft).count(),
            StorefrontSection.objects.filter(page__version=self.draft).count(),
        )

    def _add(self, layout_key, cells=None, *, base=None, expect=200):
        payload = {"type": "container.add", "page_type": "home", "layout_key": layout_key}
        if cells is not None:
            payload["cells"] = cells
        response = self._post_json({"base_revision": self._refresh_revision() if base is None else base, "mutation": payload})
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def _history(self, command):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._refresh_revision(), "command": command}),
            content_type="application/json",
        )

    def _last_container(self):
        return StorefrontContainer.objects.filter(page__version=self.draft).order_by("-order", "-id").first()

    def _keys(self, container):
        return [[b.section_key for b in container_service.get_cell_blocks(c)] for c in container.cells.order_by("order", "id")]

    # ---- 1/3: empty layouts, one request / one revision / one history step
    def test_empty_layouts_in_one_request_one_revision_one_history_entry(self):
        for layout, spans in (("half", [6, 6]), ("thirds", [4, 4, 4]), ("third_right", [8, 4]), ("quarters", [3, 3, 3, 3])):
            with self.subTest(layout=layout):
                before_counts, before_rev, before_hist = self._counts(), self._refresh_revision(), self._history_count()
                response = self._add(layout)
                self.assertEqual(response.json()["mutation_type"], "container.add")
                self.assertEqual(self._refresh_revision(), before_rev + 1)
                self.assertEqual(self._history_count(), before_hist + 1)
                container = self._last_container()
                self.assertEqual(container.layout_key, layout)
                self.assertEqual([c.span for c in container.cells.order_by("order", "id")], spans)
                self.assertEqual(self._keys(container), [[] for _ in spans])               # fully empty Cells, no forced content
                self.assertEqual(self._counts(), (before_counts[0] + 1, before_counts[1] + len(spans), before_counts[2]))

    # ---- 4: pre-filled layout is one atomic mutation
    def test_prefilled_three_columns_are_independent_sections_in_one_request(self):
        before_rev, before_hist = self._refresh_revision(), self._history_count()
        self._add("thirds", [["rich_text"], ["faq"], ["quick_links"]])
        self.assertEqual(self._refresh_revision(), before_rev + 1)
        self.assertEqual(self._history_count(), before_hist + 1)
        container = self._last_container()
        self.assertEqual(self._keys(container), [["rich_text"], ["faq"], ["quick_links"]])
        ids = [b.pk for c in container.cells.order_by("order", "id") for b in container_service.get_cell_blocks(c)]
        self.assertEqual(len(set(ids)), 3)

    # ---- 5: one big + two small stacked: three independent Blocks
    def test_big_plus_two_small_stacked_are_three_independent_blocks(self):
        self._add("third_right", [["newest_products"], ["faq", "rich_text"]])
        container = self._last_container()
        big, narrow = list(container.cells.order_by("order", "id"))
        self.assertEqual([c.span for c in (big, narrow)], [8, 4])
        big_blocks, narrow_blocks = container_service.get_cell_blocks(big), container_service.get_cell_blocks(narrow)
        self.assertEqual([b.section_key for b in big_blocks], ["newest_products"])
        self.assertEqual([b.section_key for b in narrow_blocks], ["faq", "rich_text"])
        top_small, bottom_small = narrow_blocks
        self.assertNotEqual(top_small.pk, bottom_small.pk)
        self.assertEqual([b.cell_order for b in narrow_blocks], [0, 1])
        # independent settings: editing the bottom block changes neither neighbour
        before = {b.pk: dict(b.settings) for b in (big_blocks[0], top_small)}
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {
            "type": "section.update_settings", "section_id": bottom_small.pk, "patch": {"body_html": "<p>فقط پایین</p>"}}})
        self.assertEqual(response.status_code, 200, response.content)
        bottom_small.refresh_from_db()
        self.assertIn("فقط پایین", bottom_small.settings["body_html"])
        for block in (big_blocks[0], top_small):
            block.refresh_from_db()
            self.assertEqual(block.settings, before[block.pk])

    def test_removing_one_block_keeps_the_others_and_the_layout(self):
        self._add("third_right", [["newest_products"], ["faq", "rich_text"]])
        container = self._last_container()
        narrow = list(container.cells.order_by("order", "id"))[1]
        top_small, bottom_small = container_service.get_cell_blocks(narrow)
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {"type": "section.remove", "section_id": top_small.pk}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._keys(container), [["newest_products"], ["rich_text"]])
        self.assertEqual([b.cell_order for b in container_service.get_cell_blocks(narrow)], [0])          # compacted, no gap
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())
        # removing the last block leaves a fillable EMPTY Cell
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {"type": "section.remove", "section_id": bottom_small.pk}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._keys(container), [["newest_products"], []])

    # ---- 4: rollback
    def test_a_refused_second_or_third_block_rolls_everything_back(self):
        cases = {
            "unknown key as 2nd": [["faq"], ["no_such_section"]],
            "unknown key as 3rd": [["faq"], ["rich_text"], ["no_such_section"]],
            "single-instance repeated": [["faq"], ["rich_text"], ["faq", "no_such_section"]],
        }
        for name, cells in cases.items():
            with self.subTest(case=name):
                counts, revision, history = self._counts(), self._refresh_revision(), self._history_count()
                layout = "thirds" if len(cells) == 3 else "half"
                response = self._add(layout, cells, expect=400)
                body = response.json()
                self.assertFalse(body["ok"])
                self.assertTrue(body["message"])                                          # a Persian reason, never silent
                self.assertEqual(self._counts(), counts)                                  # no container, no cells, no sections
                self.assertEqual(self._refresh_revision(), revision)
                self.assertEqual(self._history_count(), history)

    def test_a_section_limited_to_one_instance_cannot_be_used_twice_and_nothing_is_kept(self):
        from apps.storefront_builder import section_registry

        limited = next((d.key for d in section_registry.SECTION_REGISTRY.values() if d.max_instances == 1 and not d.hidden_from_library
                        and section_registry.is_section_allowed_on_page(d.key, "home")), None)
        if limited is None:
            self.skipTest("no single-instance section in the registry")
        StorefrontSection.objects.filter(page=self.page, section_key=limited).delete()
        counts, revision = self._counts(), self._refresh_revision()
        self._add("half", [[limited], [limited]], expect=400)
        self.assertEqual((self._counts(), self._refresh_revision()), (counts, revision))

    def test_shape_and_legality_validation_is_unchanged_in_strictness(self):
        counts, revision = self._counts(), self._refresh_revision()
        for layout, cells in (("nope", None), ("single", None), ("half", [["faq"], ["faq"], ["faq"]]), ("half", "x"),
                              ("half", [["faq", "faq", "faq", "faq", "faq"]]), ("half", [[1]]), ("half", [["" ]])):
            with self.subTest(layout=layout, cells=cells):
                self._add(layout, cells, expect=400)
        response = self._post_json({"base_revision": revision, "mutation": {"type": "container.add", "page_type": "nope", "layout_key": "half"}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self._counts(), self._refresh_revision()), (counts, revision))

    # ---- 8: duplicate / replayed request
    def test_a_replayed_request_with_the_same_base_revision_is_a_conflict_not_a_second_layout(self):
        base = self._refresh_revision()
        self._add("half", base=base)
        counts = self._counts()
        response = self._add("half", base=base, expect=409)
        self.assertEqual(response.json()["code"], "stale_revision")
        self.assertEqual(self._counts(), counts)

    # ---- 2: one Undo / one Redo for the whole build
    def test_one_undo_removes_the_whole_build_and_one_redo_restores_it(self):
        counts = self._counts()
        self._add("third_right", [["newest_products"], ["faq", "rich_text"]])
        built = self._counts()
        self.assertEqual(built, (counts[0] + 1, counts[1] + 2, counts[2] + 3))
        undo = self._history("undo")
        self.assertEqual(undo.status_code, 200, undo.content)
        self.assertEqual(self._counts(), counts)
        redo = self._history("redo")
        self.assertEqual(redo.status_code, 200, redo.content)
        self.assertEqual(self._counts(), built)
        container = self._last_container()
        self.assertEqual(self._keys(container), [["newest_products"], ["faq", "rich_text"]])

    # ---- 7: draft independent of published; empty cells publish
    def test_draft_only_until_publish_and_empty_cells_publish_safely(self):
        published_before = self.layout.published_version_id
        self._add("thirds")
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.published_version_id, published_before)               # nothing published by building
        container = self._last_container()
        layout_service.publish(self.store, user=self.staff)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        self.assertIsNotNone(published)
        pub_container = StorefrontContainer.objects.filter(page__version=published, layout_key="thirds").first()
        self.assertIsNotNone(pub_container)
        self.assertEqual([c.span for c in pub_container.cells.order_by("order", "id")], [4, 4, 4])
        self.assertEqual(container.layout_key, "thirds")

    def test_the_new_layout_renders_in_the_shared_preview_with_empty_cell_controls(self):
        self._add("half", [["faq"], []])
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn("sfb-empty-cell-add", html)                                           # empty Cell stays fillable from the canvas
        self.assertIn("data-empty-cell=", html)


class CellAddClientContractTests(R4MutationApiTestCase):
    """The canvas «add to this Cell» flow: a message from the preview frame opens a dialog that only ever targets that Cell."""

    @classmethod
    def _js(cls):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / "static/storefront_builder/r4_studio.js").read_text(encoding="utf-8")

    def test_only_the_preview_frame_on_our_origin_can_open_the_dialog(self):
        js = self._js()
        body = js[js.index("window.addEventListener('message'"):][:700]
        self.assertIn("evt.source !== frame.contentWindow", body)
        self.assertIn("evt.origin !== window.location.origin", body)
        self.assertIn("'sfb:addToCell'", body)
        self.assertIn("openCellAdd(evt.data.cellId)", body)

    def test_the_canvas_chip_is_caught_on_the_preview_window_in_the_capture_phase_and_only_reads_the_cell_id(self):
        js = self._js()
        bind = js[js.index("function bindCanvasCellChips("):js.index("window.addEventListener('message'")]
        self.assertIn("closest('[data-empty-cell], [data-cell-add]')", bind)
        self.assertIn("}, true);", bind)                                     # capture phase: before preview.html's own interceptor
        self.assertIn("openCellAdd(", bind)
        self.assertIn("document.addEventListener('load'", bind)                 # R4 swaps a twin iframe after every refresh: bind each frame on load
        for forbidden in ("fetch(", "R4.", "enqueue", "postMessage", "localStorage"):
            self.assertFalse(forbidden in bind, forbidden)
        opener = js[js.index("function openCellAdd("):js.index("function bindCanvasCellChips(")]
        self.assertIn("if (!cellId || ui.lab.active || ui.modal) return;", opener)
        self.assertIn("openModal('add-cell', { cellId: cellId })", opener)

    def test_the_cell_dialog_writes_only_cell_add_section_for_that_cell(self):
        js = self._js()
        handler = js[js.index("case 'cell-add': {"):][:900]
        self.assertIn("R4.addSection(cellKey, ui.modal.cellId)", handler)
        for forbidden in ("section.add'", "fetch(", "publish", "container."):
            self.assertFalse(forbidden in handler, forbidden)

    def test_the_cell_dialog_removes_every_page_end_control(self):
        js = self._js()
        render = js[js.index("if (m.type === 'add-cell' && slot) {"):][:1100]
        for removed in ("[data-r4-showcase]", "#r4StructureAddButton", "#r4StructureAddSelect"):
            self.assertIn(removed, render)
        self.assertIn("'cell-add'", render)

    def test_a_cell_add_is_the_existing_mutation_and_is_idempotent_per_request(self):
        page = self.draft.get_page("home")
        container_service.ensure_page_containers(page)
        container = container_service.create_empty_container(page, "half")
        cell = container.cells.order_by("order", "id").first()
        revision = self._refresh_revision()
        first = self._post_json({"base_revision": revision, "mutation": {"type": "cell.add_section", "section_key": "faq", "cell_id": cell.pk}})
        self.assertEqual(first.status_code, 200, first.content)
        # a replay of the same base_revision (double click / retry after network delay) is a stale 409: nothing is duplicated
        replay = self._post_json({"base_revision": revision, "mutation": {"type": "cell.add_section", "section_key": "faq", "cell_id": cell.pk}})
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(StorefrontSection.objects.filter(page__version=self.draft, section_key="faq").count(), 1)
