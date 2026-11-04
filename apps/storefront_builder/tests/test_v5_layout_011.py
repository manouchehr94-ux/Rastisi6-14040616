"""V5-LAYOUT-011 — (1) the stacked «big + two small» preset is THREE real Cells; (2) ``container.remove`` never deletes content."""

import json

from django.urls import reverse

from apps.storefront_builder.models import StorefrontCell, StorefrontContainer, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service

from .test_r4_mutation_api import R4MutationApiTestCase

STACK = "big_right_two_left"


class _Base(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.page = self.draft.get_page("home")
        container_service.ensure_page_containers(self.page)

    def _mutate(self, mutation, expect=200):
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": mutation})
        self.assertEqual(response.status_code, expect, response.content)
        return response

    def _add(self, layout, cells=None, expect=200):
        mutation = {"type": "container.add", "page_type": "home", "layout_key": layout}
        if cells is not None:
            mutation["cells"] = cells
        return self._mutate(mutation, expect)

    def _history(self, command):
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self._refresh_revision(), "command": command}),
            content_type="application/json",
        )

    def _containers(self, version=None):
        return list(StorefrontContainer.objects.filter(page__version=version or self.draft, page__page_type="home").order_by("order", "id"))

    def _last(self):
        return self._containers()[-1]

    def _cells(self, container):
        return list(container.cells.order_by("order", "id"))

    def _keys(self, container):
        return [[b.section_key for b in container_service.get_cell_blocks(c)] for c in self._cells(container)]

    def _add_to(self, cell, key):
        return self._mutate({"type": "cell.add_section", "section_key": key, "cell_id": cell.pk})


class StackedLayoutTests(_Base):
    def test_one_request_makes_exactly_one_container_with_three_real_cells(self):
        containers, revision, history = len(self._containers()), self._refresh_revision(), self._history_count()
        self._add(STACK)
        self.assertEqual(len(self._containers()), containers + 1)                  # ONE logical container, not two
        self.assertEqual(self._refresh_revision(), revision + 1)
        self.assertEqual(self._history_count(), history + 1)
        container = self._last()
        self.assertEqual(container.layout_key, STACK)                              # distinguishable from a plain 8/4 row by structure
        self.assertEqual([c.span for c in self._cells(container)], [8, 4, 4])
        self.assertEqual(self._keys(container), [[], [], []])
        container_service.validate_page_containers(self.page)
        self.assertEqual(container_service.layout_key_for_spans((8, 4, 4)), STACK)
        self.assertEqual(container_service.layout_key_for_spans((8, 4)), "third_right")        # the plain row is unchanged

    def test_each_slot_fills_independently_and_the_order_never_moves(self):
        self._add(STACK)
        container = self._last()
        big, top, bottom = self._cells(container)
        self._add_to(bottom, "rich_text")                                           # bottom first, top still empty
        self.assertEqual(self._keys(container), [[], [], ["rich_text"]])
        bottom_block = container_service.get_cell_blocks(bottom)[0]
        self._add_to(top, "faq")
        self.assertEqual(self._keys(container), [[], ["faq"], ["rich_text"]])      # top never replaced bottom, order intact
        self._add_to(big, "newest_products")
        self.assertEqual(self._keys(container), [["newest_products"], ["faq"], ["rich_text"]])
        bottom_block.refresh_from_db()
        self.assertEqual(bottom_block.cell_id, bottom.pk)                           # same id, same cell
        self.assertEqual([c.pk for c in self._cells(container)], [big.pk, top.pk, bottom.pk])

    def test_undo_redo_publish_and_preview_keep_the_three_slots(self):
        self._add(STACK, [["newest_products"], ["faq"], ["rich_text"]])
        container = self._last()
        before = [(c.span, [b.pk for b in container_service.get_cell_blocks(c)]) for c in self._cells(container)]
        undo = self._history("undo")
        self.assertEqual(undo.status_code, 200, undo.content)
        self.assertFalse(StorefrontContainer.objects.filter(pk=container.pk).exists() and self._last().layout_key == STACK)
        redo = self._history("redo")
        self.assertEqual(redo.status_code, 200, redo.content)
        restored = self._last()
        self.assertEqual(restored.layout_key, STACK)
        self.assertEqual([(c.span, [b.pk for b in container_service.get_cell_blocks(c)]) for c in self._cells(restored)], before)   # ids preserved
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertIn('data-layout="%s"' % STACK, html)
        layout_service.publish(self.store, user=self.staff)
        self.layout.refresh_from_db()
        published = [c for c in self._containers(self.layout.published_version) if c.layout_key == STACK]
        self.assertEqual(len(published), 1)
        self.assertEqual([c.span for c in self._cells(published[0])], [8, 4, 4])
        self.assertEqual(self._keys(published[0]), [["newest_products"], ["faq"], ["rich_text"]])

    def test_plain_presets_keep_their_behaviour(self):
        for layout, spans in (("half", [6, 6]), ("thirds", [4, 4, 4]), ("third_right", [8, 4]), ("quarters", [3, 3, 3, 3])):
            with self.subTest(layout=layout):
                self._add(layout)
                self.assertEqual([c.span for c in self._cells(self._last())], spans)

    def test_changing_layout_between_plain_and_stacked_never_loses_content(self):
        self._add("third_right", [["newest_products"], ["faq", "rich_text"]])
        container = self._last()
        self._mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": STACK})
        container.refresh_from_db()
        self.assertEqual(container.layout_key, STACK)
        self.assertEqual([c.span for c in self._cells(container)], [8, 4, 4])
        self.assertEqual(self._keys(container), [["newest_products"], ["faq", "rich_text"], []])    # grow adds an EMPTY third cell
        container_service.validate_container(container)
        self._mutate({"type": "container.change_layout", "container_id": container.pk, "layout_key": "third_right"})
        self.assertEqual(self._keys(container), [["newest_products"], ["faq", "rich_text"]])        # shrink merges, nothing dropped

    def test_stacked_preset_cannot_be_forged_with_wrong_cells(self):
        self._add(STACK)
        container = self._last()
        cell = self._cells(container)[2]
        cell.span = 6
        cell.save(update_fields=["span"])
        with self.assertRaises(container_service.ContainerLayoutError):
            container_service.validate_container(container)

    def test_a_raw_draft_with_unplaced_sections_wraps_them_in_their_own_rows_this_is_not_a_second_request(self):
        """Evidence for «does one click make two containers?»: the only extra rows come from ``ensure_page_containers`` adopting legacy,
        not-yet-placed Sections (this test class's setUp pre-adopts them, hence the explicit fresh draft here)."""
        page = self.draft.get_page("listing")
        StorefrontContainer.objects.filter(page=page).delete()
        StorefrontSection.objects.create(page=page, version=self.draft, section_key="faq", order=0)
        StorefrontSection.objects.create(page=page, version=self.draft, section_key="rich_text", order=1)
        before = StorefrontContainer.objects.filter(page=page).count()
        unplaced = StorefrontSection.objects.filter(page=page).count()
        self.assertEqual(before, 0)
        self.assertGreaterEqual(unplaced, 2)
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {
            "type": "container.add", "page_type": "listing", "layout_key": STACK}})
        self.assertEqual(response.status_code, 200, response.content)
        after = StorefrontContainer.objects.filter(page=page).count()
        self.assertEqual(after - before, 1 + unplaced)                              # 1 new layout + one adopted row per legacy section
        self.assertEqual(StorefrontContainer.objects.filter(page=page, layout_key=STACK).count(), 1)


class RemoveContainerTests(_Base):
    def test_an_empty_container_is_removed_and_undo_restores_it(self):
        self._add("thirds")
        container = self._last()
        before_ids = [c.pk for c in self._containers()]
        revision, history = self._refresh_revision(), self._history_count()
        response = self._mutate({"type": "container.remove", "container_id": container.pk})
        self.assertEqual(response.json()["mutation_type"], "container.remove")
        self.assertEqual(self._refresh_revision(), revision + 1)
        self.assertEqual(self._history_count(), history + 1)
        self.assertEqual([c.pk for c in self._containers()], before_ids[:-1])      # only this one disappeared
        undo = self._history("undo")
        self.assertEqual(undo.status_code, 200, undo.content)
        self.assertEqual(len(self._containers()), len(before_ids))
        self.assertEqual(self._last().layout_key, "thirds")
        self.assertEqual([c.span for c in self._cells(self._last())], [4, 4, 4])

    def test_a_container_with_content_dissolves_into_independent_rows_without_losing_anything(self):
        self._add("thirds", [["newest_products"], ["faq", "rich_text"], []])
        target = self._last()
        self._add("half")                                                             # a later container that must only shift
        later = self._last()
        blocks = [b for c in self._cells(target) for b in container_service.get_cell_blocks(c)]
        ids = [b.pk for b in blocks]
        # a block with its own settings + a hidden one: both must survive untouched
        hidden = blocks[1]
        self._mutate({"type": "section.toggle_active", "section_id": hidden.pk})
        self._mutate({"type": "section.update_settings", "section_id": blocks[2].pk, "patch": {"body_html": "<p>باید بماند</p>"}})
        sections_before = StorefrontSection.objects.filter(page=self.page).count()
        position = list(c.pk for c in self._containers()).index(target.pk)
        self._mutate({"type": "container.remove", "container_id": target.pk})
        self.assertFalse(StorefrontContainer.objects.filter(pk=target.pk).exists())
        self.assertEqual(StorefrontSection.objects.filter(page=self.page).count(), sections_before)       # NO section deleted
        containers = self._containers()
        rows = containers[position:position + 3]
        self.assertEqual([c.layout_key for c in rows], ["single"] * 3)
        self.assertEqual([[b.pk for b in container_service.get_cell_blocks(self._cells(c)[0])] for c in rows], [[i] for i in ids])   # reading order, same ids
        self.assertEqual(containers[position + 3].pk, later.pk)                       # the later container only shifted
        hidden.refresh_from_db()
        self.assertFalse(hidden.is_active)
        blocks[2].refresh_from_db()
        self.assertIn("باید بماند", blocks[2].settings["body_html"])
        container_service.validate_page_containers(self.page)
        undo = self._history("undo")
        self.assertEqual(undo.status_code, 200, undo.content)
        restored = [c for c in self._containers() if c.layout_key == "thirds"]
        self.assertEqual(len(restored), 1)
        self.assertEqual(sorted(b.pk for c in self._cells(restored[0]) for b in container_service.get_cell_blocks(c)), sorted(ids))

    def test_locked_content_or_locked_container_is_refused_without_any_change(self):
        self._add("half", [["faq"], ["rich_text"]])
        container = self._last()
        block = container_service.get_cell_blocks(self._cells(container)[0])[0]
        self._mutate({"type": "section.toggle_locked", "section_id": block.pk})
        revision, snapshot = self._refresh_revision(), [(c.pk, c.layout_key) for c in self._containers()]
        response = self._post_json({"base_revision": revision, "mutation": {"type": "container.remove", "container_id": container.pk}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_has_locked_section")
        self.assertTrue(response.json()["message"])
        self.assertEqual(self._refresh_revision(), revision)
        self.assertEqual([(c.pk, c.layout_key) for c in self._containers()], snapshot)
        # unlocked content, locked container
        self._mutate({"type": "section.toggle_locked", "section_id": block.pk})
        StorefrontContainer.objects.filter(pk=container.pk).update(is_locked=True)
        response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {"type": "container.remove", "container_id": container.pk}})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "container_locked")
        self.assertTrue(StorefrontContainer.objects.filter(pk=container.pk).exists())

    def test_scoping_validation_and_the_published_page_are_untouched(self):
        self._add("half", [["faq"], []])
        container = self._last()
        published_before = self.layout.published_version_id
        for bad in ("1", None, True, 99999999):
            with self.subTest(container_id=bad):
                response = self._post_json({"base_revision": self._refresh_revision(), "mutation": {"type": "container.remove", "container_id": bad}})
                self.assertEqual(response.status_code, 400, response.content)
        layout_service.publish(self.store, user=self.staff)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        published_containers = [(c.layout_key, len(self._cells(c))) for c in self._containers(published)]
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)          # a fresh Draft cloned from the published one
        draft_container = [c for c in self._containers() if c.layout_key == "half"][-1]
        self._mutate({"type": "container.remove", "container_id": draft_container.pk})
        self.assertEqual([(c.layout_key, len(self._cells(c))) for c in self._containers(published)], published_containers)   # published untouched
        self.assertNotIn(draft_container.pk, [c.pk for c in self._containers()])
        self.assertNotEqual(published.pk, published_before)

    def test_extra_payload_fields_cannot_turn_it_into_a_content_delete(self):
        self._add("half", [["faq"], ["rich_text"]])
        container = self._last()
        ids = [b.pk for c in self._cells(container) for b in container_service.get_cell_blocks(c)]
        self._mutate({"type": "container.remove", "container_id": container.pk, "delete_content": True, "content": "delete"})
        self.assertEqual(StorefrontSection.objects.filter(pk__in=ids).count(), 2)  # the flag is ignored: content is ALWAYS kept


class UiContractTests(_Base):
    APP = __import__("pathlib").Path(__file__).resolve().parents[1]

    def _editor(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()

    def test_the_rows_panel_lists_every_real_container_including_empty_ones_each_with_a_remove_control(self):
        self._add("thirds")                                                         # fully empty
        self._add("half", [["faq"], []])
        html = self._editor()
        panel = html[html.index('class="rs-more rs-rows"'):]
        panel = panel[:panel.index("rs-empty-cells") if "rs-empty-cells" in panel else len(panel)]
        rows = panel.count("data-r4-structure-container-row")
        self.assertEqual(rows, len(self._containers()))                              # every container, not only those with Sections
        self.assertEqual(panel.count('data-rastisi-action="remove-container"'), rows)
        self.assertIn('data-container-empty="true"', panel)
        self.assertIn("خالی (بدون بخش)", panel)
        for key in container_service.STACKED_LAYOUT_PRESETS:
            self.assertIn('value="%s"' % key, panel)                                # the layout picker offers the stacked preset too

    def test_a_locked_container_has_a_disabled_remove_control(self):
        self._add("half")
        StorefrontContainer.objects.filter(pk=self._last().pk).update(is_locked=True)
        panel = self._editor()
        row = panel[panel.rindex('data-r4-structure-container-row'):]
        row = row[:row.index("rs-container-settings")]
        self.assertRegex(row, r'data-rastisi-action="remove-container"[^>]*disabled')

    def test_the_canvas_control_exists_only_inside_a_fully_empty_layout_never_over_a_section(self):
        self._add("thirds")
        empty = self._last()
        self._add("half", [["faq"], []])
        html = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        self.assertEqual(html.count("sfb-empty-cell-remove"), 1)
        self.assertIn('data-container-remove="%d"' % empty.pk, html)
        import re
        self.assertTrue(re.search(r'class="sfb-empty-cell-add"[^>]*>.*?</button>\s*<button type="button" class="sfb-empty-cell-remove"', html, re.S))

    def test_the_studio_remove_flow_confirms_then_sends_exactly_one_container_remove(self):
        js = (self.APP / "static/storefront_builder/r4_studio.js").read_text(encoding="utf-8")
        self.assertIn("case 'remove-container': {", js)
        confirm = js[js.index("case 'confirm-remove-container': {"):][:900]
        self.assertEqual(confirm.count("R4.enqueueStructuralMutation("), 1)
        self.assertIn("type: 'container.remove', container_id: rmTarget", confirm)
        for forbidden in ("fetch(", "section.remove", "delete_content", "publish"):
            self.assertFalse(forbidden in confirm, forbidden)
        modal = js[js.index("case 'remove-container': {\n        // V5-LAYOUT-011"):][:900]
        self.assertIn("هیچ بخشی حذف نمی‌شود", modal)                                  # content is explicitly said to be kept

    def test_stacked_css_is_central_layout_key_driven_with_a_mobile_reset(self):
        css = (self.APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn('.rcontainer[data-layout="big_right_two_left"] { grid-template-rows: auto 1fr; }', css)
        self.assertIn("grid-row: 1 / span 2;", css)
        mobile = css[css.index('@media (max-width: 1000px) {\n  .rcontainer[data-layout="big_right_two_left"]'):][:700]
        self.assertIn("grid-row: auto;", mobile)
        self.assertIn('[data-mobile-mode="stack"]', mobile)
        self.assertNotIn("height:", css[css.index('.rcontainer[data-layout="big_right_two_left"] { grid-template-rows'):][:900].replace("min-height", ""))   # no fixed heights

    def test_published_output_carries_no_remove_controls(self):
        from django.template.loader import render_to_string

        from apps.storefront_builder.models import StorefrontPage
        from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context

        self._add("thirds")
        layout_service.publish(self.store, user=self.staff)

        class Request:
            pass

        context = build_universal_storefront_context(Request(), self.store, StorefrontPage.PageType.HOME)
        html = render_to_string("storefront_builder/partials/render_containers.html", {"render_containers": context["render_containers"], "is_preview": False})
        for marker in ("sfb-empty-cell-remove", "data-container-remove", "حذف چیدمان"):
            self.assertNotIn(marker, html, marker)


class LayoutHeightContractTests(_Base):
    """V5-RESIZE — the ONE surface / media-fill primitive: the visible frame grows, content is never stretched, clipped or given a height."""

    APP = __import__("pathlib").Path(__file__).resolve().parents[1]
    FRAMES = (".hero-inner", ".fashion-hero-inner", ".hero-split-inner", ".hero-atelier-inner", ".hero-luxury-stage", ".promo-dark")

    def _css(self):
        return (self.APP / "static/css/storefront_builder.css").read_text(encoding="utf-8")

    def _block(self):
        import re

        css = self._css()
        start = css.index("V5-RESIZE — the central SURFACE / MEDIA FILL primitive")
        end = css.index("@media (max-width: 1000px) {\n  .rcontainer[data-layout=\"big_right_two_left\"][data-mobile-mode=\"stack\"]", start)
        return re.sub(r"/\*.*?\*/", "", css[css.rindex("/*", 0, start):end], flags=re.S)

    def test_only_stacked_cells_and_manual_height_sections_are_fill_contexts_legacy_modes_are_untouched(self):
        import re

        block = self._block()
        for selector in [rule.strip() for rule in re.findall(r"([^{}]+)\{", block) if "@media" not in rule]:       # whole prelude (commas live inside :is())
            self.assertTrue(
                'data-layout="big_right_two_left"' in selector or 'data-d~="minh"' in selector or 'data-d~="w' in selector,
                "a rule outside the stacked layout / manual-size contexts: %r" % selector,
            )
        css = self._css()
        for legacy in ('.rcontainer[data-height-mode="natural"] > .rcontainer-cell {\n  align-self: start;\n}',
                       '.rcontainer[data-height-mode="equal"] > .rcontainer-cell {\n  align-self: stretch;\n  height: auto;'):
            self.assertIn(legacy, css)                                              # the existing contract is byte-for-byte untouched

    def test_surfaces_fill_but_contents_are_never_stretched_clipped_or_given_fixed_heights(self):
        import re

        block = self._block()
        for forbidden in ("overflow", "object-fit", "transform", "height: 100%", "pcard", "pcarousel", " img", "!important"):
            self.assertNotIn(forbidden, block, forbidden)
        for declaration in re.findall(r"(?<![-\w])(height|min-height|max-height)\s*:\s*([^;]+);", block):
            # only: the flex «may shrink» reset, the bounded automatic growth of a media frame, lifting that cap for a manual height, and the phone bound
            self.assertIn(declaration, (("min-height", "0"), ("max-height", "125cqw"), ("max-height", "none"),
                                         ("min-height", "min(var(--d-minh), 80vw)")), declaration)
        self.assertIn("> .section {\n  flex: 1 1 auto;", block)
        self.assertIn("flex: 1 1 auto;", block)

    def test_the_single_frame_list_names_every_hero_and_banner_family(self):
        block = self._block()
        for frame in self.FRAMES:
            self.assertIn(frame, block)

    def _class_names(self, name, depth=0):
        import re

        root = self.APP / "templates"
        text = (root / name).read_text(encoding="utf-8")
        names = {c for group in re.findall(r'class="([^"]+)"', text) for c in group.split()}
        if depth < 3:
            for include in re.findall(r"{% include ['\"]([^'\"]+)['\"]", text):
                if (root / include).exists():
                    names |= self._class_names(include, depth + 1)
        return names

    def test_every_hero_or_banner_section_template_names_its_frame_in_the_central_list(self):
        import re

        families = sorted(
            p.name for p in (self.APP / "templates/storefront_builder/sections").glob("*.html")
            if re.fullmatch(r"(hero_banner.*|image_slider|single_banner|fashion_lifestyle_hero)\.html", p.name)
        )
        self.assertGreaterEqual(len(families), 9)
        for name in families:
            names = self._class_names("storefront_builder/sections/" + name)
            self.assertTrue(
                [f for f in self.FRAMES if f.lstrip(".") in names],
                "%s names no frame of the central fill primitive (a new family would silently fall outside the contract)" % name,
            )

    def test_manual_width_rules_exist_and_never_exceed_the_cell(self):
        block = self._block()
        self.assertIn('.rsec[data-d~="w"] { width: var(--d-w); max-width: 100%; }', block)
        for anchor in ("wa-start", "wa-end", "wa-center"):
            self.assertIn('data-d~="%s"' % anchor, block)

    def test_height_split_rows_never_go_below_their_content(self):
        block = self._block()
        self.assertIn("minmax(min-content, var(--stack-top)) minmax(min-content, var(--stack-bottom))", block)

    def test_mobile_stack_resets_the_grid_and_adds_no_height(self):
        css = self._css()
        mobile = css[css.index('@media (max-width: 1000px) {\n  .rcontainer[data-layout="big_right_two_left"]'):][:800]
        self.assertIn("grid-template-rows: none;", mobile)
        self.assertNotIn("height", mobile.replace("grid-template-rows", ""))
