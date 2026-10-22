"""V5-LAYOUT-001 / V5-UI-005 — the two reference three-section patterns are built ONLY from existing engine capabilities.

* «سه ستون مساوی»      -> container_service preset ``thirds`` (4,4,4); one section per Cell.
* «بزرگ راست + دو کوچک چپ» -> preset with widths (8,4); the narrow Cell holds TWO blocks (repeated ``cell.add_section``).

Both use the three canonical mutation types through the one structural queue; nothing is published; a failing step stops the
chain and is reported (never a false success). Search placement (UI-005) is pinned here too."""

import re
from pathlib import Path

from django.urls import reverse

from apps.storefront_builder.services import container_service, section_structure_service as sss

from ._v5_shell_support import STUDIO_JS
from .test_template51_designability_wiring import _BandBase

APP = Path(__file__).resolve().parents[1]
PARTIAL = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "studio_structure.html").read_text(encoding="utf-8")


class PatternMarkupTests(_BandBase):
    def _html(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()

    def test_patterns_are_resolved_from_existing_registry_presets_only(self):
        from apps.storefront_builder.templatetags.storefront_builder_extras import rs_three_cell_patterns

        patterns = {p["key"]: p for p in rs_three_cell_patterns()}
        self.assertEqual(list(patterns), ["thirds_equal", "big_right_two_left"])
        for pattern in patterns.values():
            self.assertEqual(tuple(container_service.LAYOUT_PRESETS[pattern["engine"]]), tuple(pattern["widths"]))
        self.assertEqual(patterns["thirds_equal"]["cells"], "0,1,2")
        self.assertEqual(patterns["big_right_two_left"]["cells"], "0,1,1")     # both small sections go to the SAME (narrow) Cell

    def test_layout_tab_renders_both_cards_with_slot_labels_and_a_third_picker(self):
        html = self._html()
        tpl = html[html.index("data-rs-add-row-template"):]
        tpl = tpl[:tpl.index("</template>")]
        self.assertIn('value="thirds_equal" data-rs-engine-layout="thirds"', tpl)
        self.assertIn('data-rs-slot-cells="0,1,1"', tpl)
        self.assertIn("rs-stack", tpl)                                         # the stacked schematic
        self.assertIn("data-rs-add-row-third", tpl)
        self.assertRegex(tpl, r'data-rs-slot-field="2"[^>]*hidden')            # hidden for the two-column presets
        for expected in ("سه ستون مساوی", "بزرگ راست + دو کوچک چپ"):
            self.assertIn(expected, tpl)

    def test_exactly_one_search_field_first_in_the_sections_pane_before_the_suggestions(self):
        html = self._html()
        self.assertEqual(html.count('data-control="library-search"'), 1)
        pane = html[html.index('class="rs-add-section"'):]
        search = pane.index('data-control="library-search"')
        self.assertLess(search, pane.index("data-r4-showcase "))              # above «پیشنهادی» (suggestions)
        self.assertLess(search, pane.index('class="rs-library"'))              # and above the library cards
        self.assertLess(search, pane.index('id="r4StructureAddSelect"'))
        # the search is no longer inside the library block
        library = pane[pane.index('class="rs-library"'):pane.index('id="r4StructureAddSelect"')]
        self.assertNotIn("library-search", library)


class PatternMutationChainTests(_BandBase):
    """The exact sequence r4_studio.js sends, through the real R4 endpoint code path (no publish)."""

    def _mutate(self, mutation, expect=200):
        self.draft.refresh_from_db()
        response = self._post_json({"base_revision": self.draft.edit_revision, "mutation": mutation})
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def _new_container(self, first_key, layout):
        self._mutate({"type": "section.add", "section_key": first_key, "page_type": "home"})
        page = self.draft.get_page("home")
        first = page.sections.filter(section_key=first_key).latest("id")
        container = sss.find_placement_cell(first).container
        self._mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": layout})
        container.refresh_from_db()
        empties = [c for c in container.cells.order_by("order", "id") if not container_service.get_cell_blocks(c)]
        return container, empties

    def _keys_per_cell(self, container):
        return [[b.section_key for b in container_service.get_cell_blocks(c)] for c in container.cells.order_by("order", "id")]

    def test_three_equal_columns_one_section_per_cell(self):
        published_before = getattr(getattr(self.draft, "layout", None), "published_version_id", None)
        container, empties = self._new_container("rich_text", "thirds")
        self.assertEqual([c.span for c in container.cells.order_by("order", "id")], [4, 4, 4])
        self.assertEqual(len(empties), 2)
        self._mutate({"type": "cell.add_section", "section_key": "faq", "cell_id": empties[0].pk})
        self._mutate({"type": "cell.add_section", "section_key": "quick_links", "cell_id": empties[1].pk})
        self.assertEqual(self._keys_per_cell(container), [["rich_text"], ["faq"], ["quick_links"]])
        if hasattr(self.draft, "layout"):
            self.draft.layout.refresh_from_db()
            self.assertEqual(self.draft.layout.published_version_id, published_before)       # nothing published

    def test_big_cell_plus_narrow_cell_that_stacks_two_sections(self):
        container, empties = self._new_container("newest_products", "third_right")
        self.assertEqual([c.span for c in container.cells.order_by("order", "id")], [8, 4])
        self.assertEqual(len(empties), 1)
        narrow = empties[0]
        self._mutate({"type": "cell.add_section", "section_key": "best_sellers", "cell_id": narrow.pk})
        self._mutate({"type": "cell.add_section", "section_key": "faq", "cell_id": narrow.pk})   # same Cell: now holds a block -> add_block
        self.assertEqual(self._keys_per_cell(container), [["newest_products"], ["best_sellers", "faq"]])

    def test_a_refused_middle_step_is_visible_and_leaves_earlier_steps_committed(self):
        container, empties = self._new_container("rich_text", "thirds")
        self._mutate({"type": "cell.add_section", "section_key": "faq", "cell_id": empties[0].pk})
        # unknown section key: refused with a stable code; nothing written, revision untouched
        starting = self.draft.edit_revision
        self.draft.refresh_from_db()
        starting = self.draft.edit_revision
        response = self._post_json({"base_revision": starting, "mutation": {"type": "cell.add_section", "section_key": "no_such_section", "cell_id": empties[1].pk}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_section_key")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, starting)
        self.assertEqual(self._keys_per_cell(container), [["rich_text"], ["faq"], []])      # steps 1-3 stay; the empty Cell stays fillable


class PatternClientContractTests(_BandBase):
    """V5-LAYOUT-ATOMIC: the layout form sends ONE ``container.add``; the old section.add -> change_layout -> cell.add_section chain is gone."""

    def _submit_handler(self):
        start = STUDIO_JS.index("var layoutBuilding = false;")
        return STUDIO_JS[start:STUDIO_JS.index("// V5-LAYOUT-ATOMIC — a click on an empty Cell")]

    def test_the_form_sends_exactly_one_container_add_through_the_single_queue(self):
        body = self._submit_handler()
        self.assertEqual(set(re.findall(r"type: '([a-z_.]+)'", body)), {"container.add"})
        self.assertEqual(body.count("R4.enqueueStructuralMutation("), 1)
        for forbidden in ("fetch(", "publish", "XMLHttpRequest", "localStorage", "R4.addTwoColumnRow", "jobs.reduce("):
            self.assertFalse(forbidden in body, forbidden)

    def test_content_choice_is_optional_and_cells_are_sent_only_when_something_was_chosen(self):
        body = self._submit_handler()
        self.assertIn("if (anyContent) mutation.cells = cells;", body)
        self.assertNotIn("required", body)
        self.assertNotIn("notify('یک بخش", body)          # no «pick a section first» gate

    def test_double_submit_is_guarded_and_released_after_the_response(self):
        body = self._submit_handler()
        self.assertIn("if (layoutBuilding) return;", body)
        self.assertIn("layoutBuilding = true;", body)
        self.assertIn("then(function (result) {\n      layoutBuilding = false;", body)          # released after the response ...
        self.assertIn("}, function () {\n      layoutBuilding = false;", body)                 # ... and after a rejection
        self.assertIn("submit.disabled = true;", body)

    def test_success_is_announced_only_when_the_server_accepted_the_build(self):
        body = self._submit_handler()
        self.assertIn("if (result && result.ok) {", body)
        self.assertIn("notify('چیدمان به انتهای صفحه اضافه شد.", body)

    def test_selecting_a_card_never_builds_only_the_submit_does(self):
        # the only writer call lives inside the form's own submit listener
        before = STUDIO_JS[:STUDIO_JS.index("modalRoot.addEventListener('submit'")]
        self.assertNotIn("type: 'container.add'", before)

    def test_the_templates_no_longer_force_a_first_section(self):
        template = (Path(__file__).resolve().parents[1] / "templates/dashboard/storefront_builder/r4/partials/studio_structure.html").read_text(encoding="utf-8")
        form = template[template.index("<template data-rs-add-row-template>"):]
        self.assertNotIn("required", form[:form.index("</template>")])
        self.assertIn("ساختن چیدمان", form)
