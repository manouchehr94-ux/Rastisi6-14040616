"""FOLLOWUP-12 — "add a section" and "build a two-column row" are discoverable at the TOP of the Studio structure panel.

The guided dialog is only a UI over the three EXISTING canonical mutations (section.add -> container.change_layout ->
cell.add_section): no new mutation type, no second sender, nothing is published. The real-browser end-to-end run (create,
reload, undo, 1440/390) is recorded in the follow-up evidence; here the markup, the JS contract and the mutation chain are pinned."""

import re
from pathlib import Path

from django.urls import reverse

from apps.storefront_builder.services import container_service, section_structure_service as sss

from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static" / "storefront_builder"
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")


class AddRowMarkupTests(_BandBase):
    def _structure(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        start = html.index("data-rs-structure-scroll")
        return html, html[start:]

    def test_both_actions_sit_above_the_section_list(self):
        _, panel = self._structure()
        add = panel.index("data-rs-add-section-top")
        row = panel.index("data-rs-add-row-top")
        first_tree_row = panel.index("data-r4-structure-row")
        self.assertLess(add, first_tree_row)
        self.assertLess(row, first_tree_row)
        self.assertIn("افزودن بخش", panel[add - 120:add + 200])
        self.assertIn("ردیف دو‌ستونه", panel[row - 120:row + 200])

    def test_the_dialog_offers_only_registry_two_cell_presets(self):
        _, panel = self._structure()
        tpl = panel[panel.index("data-rs-add-row-template"):]
        tpl = tpl[:tpl.index("</template>")]
        offered = re.findall(r'name="rs_row_layout" value="(\w+)"', tpl)
        expected = [k for k, widths in container_service.LAYOUT_PRESETS.items() if len(widths) == 2]
        # V5-LAYOUT-001: after the registry two-cell presets, exactly the two reference three-section patterns (each mapped, server-side,
        # onto an EXISTING engine preset by its widths — see test_v5_layout_patterns)
        self.assertEqual(offered, expected + ["thirds_equal", "big_right_two_left"])
        self.assertNotIn("thirds", offered)
        self.assertEqual(len(re.findall(r'<optgroup label=', tpl)) % 3, 0)   # the section picker appears once per slot (first/second/third)
        self.assertIn("data-rs-add-row-first", tpl)
        self.assertIn("data-rs-add-row-second", tpl)

    def test_dialog_says_nothing_is_published(self):
        _, panel = self._structure()
        self.assertIn("فقط در پیش‌نویس", panel)

    def test_there_is_exactly_one_add_section_action_and_the_layout_details_remain(self):
        _, panel = self._structure()
        # the engine-parity browser contract pins ONE add-section action in the panel; it now lives at the top
        self.assertEqual(panel.count('data-rastisi-action="add-section"'), 1)
        self.assertNotIn('class="full add-block"', panel)
        self.assertIn("ردیف‌ها و ستون‌بندی", panel)


class AddRowJsContractTests(_BandBase):
    def test_the_chain_uses_only_existing_mutation_types(self):
        body = EDITOR_JS[EDITOR_JS.index("R4.addTwoColumnRow"):]
        body = body[:body.index("// ---- Inspector")]
        types = set(re.findall(r"type: '([a-z_.]+)'", body))
        self.assertEqual(types, {"section.add", "container.change_layout", "cell.add_section"})
        self.assertNotIn("fetch(", body)
        self.assertNotIn("publish", body.lower())

    def test_studio_dialog_calls_the_chain_and_never_publishes(self):
        self.assertIn("R4.addTwoColumnRow(", STUDIO_JS)
        self.assertIn("case 'add-row': openModal('add-row')", STUDIO_JS)
        submit = STUDIO_JS[STUDIO_JS.index("data-rs-add-row-form]"):][:1400]
        self.assertNotIn("publish", submit.lower().replace("منتشر", ""))


class AddRowMutationChainTests(_BandBase):
    """The exact sequence the dialog sends, through the real R4 endpoint code path."""

    def _mutate(self, mutation):
        self.draft.refresh_from_db()
        response = self._post_json({"base_revision": self.draft.edit_revision, "mutation": mutation})
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_rich_text_beside_image_text_with_separate_cells_and_no_publish(self):
        published_before = self.draft.layout.published_version_id if hasattr(self.draft, "layout") else None
        self._mutate({"type": "section.add", "section_key": "rich_text", "page_type": "home"})
        page = self.draft.get_page("home")
        first = page.sections.filter(section_key="rich_text").latest("id")
        container = sss.find_placement_cell(first).container
        self._mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": "third_left"})
        container.refresh_from_db()
        empty = [c for c in container.cells.order_by("order", "id") if not container_service.get_cell_blocks(c)]
        self.assertEqual(len(empty), 1)
        self._mutate({"type": "cell.add_section", "section_key": "image_text", "cell_id": empty[0].pk})
        cells = list(container.cells.order_by("order", "id"))
        self.assertEqual([c.span for c in cells], [4, 8])
        keys = [[b.section_key for b in container_service.get_cell_blocks(c)] for c in cells]
        self.assertEqual(keys, [["rich_text"], ["image_text"]])
        if hasattr(self.draft, "layout"):
            self.draft.layout.refresh_from_db()
            self.assertEqual(self.draft.layout.published_version_id, published_before)
