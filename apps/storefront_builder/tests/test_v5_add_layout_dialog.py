"""V5 «افزودن بخش ← چیدمان» — the dialog now offers what the engine supports: four equal columns, an asymmetric four-column row
(4/2/4/2) and two ready-made, fully editable samples («متن · تصویر · متن · تصویر», «هیرو + پنل‌های کناری»).

All of it rides on the ONE ``container.add`` mutation (per-Cell ``spans`` are applied by the same validated resize code the drag handles
use): one request, one Revision, one Undo step, no new renderer and no new persistence."""

import re

from django.urls import reverse

from apps.storefront_builder.models import StorefrontContainer
from apps.storefront_builder.services import container_service, r4_mutation_service
from apps.storefront_builder.templatetags import storefront_builder_extras as tags

from ._v5_shell_support import STUDIO_JS
from .test_template51_designability_wiring import _BandBase
from .test_v5_composition_lab import _LabBase


class FourCellContainerAddTests(_LabBase):
    def revision(self):
        return self._revision()

    def last_container(self):
        return StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-id").first()

    def spans(self, container):
        return [cell.span for cell in container.cells.order_by("order")]

    def test_four_equal_cells_in_one_container_add(self):
        before = self.revision()
        self.mutate({"type": "container.add", "page_type": "home", "layout_key": "quarters"})
        container = self.last_container()
        self.assertEqual(self.spans(container), [3, 3, 3, 3])
        self.assertEqual(self.revision(), before + 1)                                  # ONE revision for the whole build

    def test_asymmetric_widths_and_per_cell_sections_in_one_container_add(self):
        before = self.revision()
        self.mutate({"type": "container.add", "page_type": "home", "layout_key": "quarters", "spans": [4, 2, 4, 2],
                     "cells": [["rich_text"], ["linked_image"], [], ["linked_image"]]})
        container = self.last_container()
        self.assertEqual(self.spans(container), [4, 2, 4, 2])
        self.assertEqual(container.layout_key, "custom")                                 # the same label a dragged row gets
        self.assertEqual(self.revision(), before + 1)
        keys = [[s.section_key for s in cell.blocks.all()] for cell in container.cells.order_by("order")]
        self.assertEqual(keys, [["rich_text"], ["linked_image"], [], ["linked_image"]])      # a cell may stay empty
        # exactly one Undo step takes the whole row away, and Redo brings it back with the same widths
        self.assertIn("--cell-span:4", self.home_preview())
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertNotIn("--cell-span:4", self.home_preview())
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertIn("--cell-span:4", self.home_preview())

    def test_invalid_widths_are_refused_and_nothing_is_built(self):
        for spans in ([4, 4, 4, 4], [6, 6], [1, 5, 3, 3], [4, 2, 4], "4,2,4,2", [4, 2, 4, "2"]):
            before = self.revision()
            count = StorefrontContainer.objects.filter(page__version=self.draft).count()
            with self.assertRaises(r4_mutation_service.R4MutationError, msg=str(spans)):
                self.mutate({"type": "container.add", "page_type": "home", "layout_key": "quarters", "spans": spans, "cells": [["rich_text"]]})
            self.assertEqual(self.revision(), before)
            self.assertEqual(StorefrontContainer.objects.filter(page__version=self.draft).count(), count)

    def test_stacked_layout_only_accepts_its_own_split(self):
        self.mutate({"type": "container.add", "page_type": "home", "layout_key": "big_right_two_left", "spans": [8, 4, 4]})
        self.assertEqual(self.spans(self.last_container()), [8, 4, 4])
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.mutate({"type": "container.add", "page_type": "home", "layout_key": "big_right_two_left", "spans": [6, 3, 3]})


class DialogMarkupTests(_BandBase):
    def _template(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        tpl = html[html.index("data-rs-add-row-template"):]
        return tpl[:tpl.index("</template>")]

    def test_cards_resolve_to_existing_engine_presets_only(self):
        four = {p["key"]: p for p in tags.rs_four_cell_patterns()}
        self.assertEqual(list(four), ["quarters_equal", "quarters_424"])
        self.assertEqual(tuple(container_service.LAYOUT_PRESETS[four["quarters_equal"]["engine"]]), (3, 3, 3, 3))
        self.assertEqual(four["quarters_424"]["spans"], "4,2,4,2")
        self.assertEqual(sum(four["quarters_424"]["widths"]), container_service.GRID_UNITS)
        samples = {p["key"]: p for p in tags.rs_sample_layouts()}
        self.assertEqual(list(samples), ["sample_tiles", "sample_hero_panels"])
        self.assertEqual(samples["sample_tiles"]["sections"], "rich_text,linked_image,rich_text,linked_image")
        self.assertEqual(samples["sample_hero_panels"]["engine"], "big_right_two_left")
        self.assertIn(samples["sample_tiles"]["engine"], container_service.LAYOUT_PRESETS)

    def test_dialog_shows_groups_four_cells_samples_and_a_fourth_picker_in_persian(self):
        tpl = self._template()
        for text in ("دو ستونه", "سه ستونه", "چهار ستونه", "نمونه‌های آماده (قابل‌ویرایش)", "چهار ستون مساوی",
                     "چهار ستون نامتقارن ۴/۲/۴/۲", "متن · تصویر · متن · تصویر", "هیرو + پنل‌های کناری", "ساختن چیدمان"):
            self.assertIn(text, tpl)
        self.assertIn('value="quarters_424" data-rs-engine-layout="quarters"', tpl)
        self.assertIn('data-rs-slot-spans="4,2,4,2"', tpl)
        self.assertIn('data-rs-sample-sections="rich_text,linked_image,rich_text,linked_image"', tpl)
        self.assertIn("data-rs-add-row-fourth", tpl)
        self.assertRegex(tpl, r'data-rs-slot-field="3"[^>]*hidden')
        self.assertIn("ردیف‌ها و ستون‌بندی", tpl)                                       # where the next controls live

    def test_the_form_still_sends_exactly_one_container_add_with_optional_spans(self):
        start = STUDIO_JS.index("var layoutBuilding = false;")
        body = STUDIO_JS[start:STUDIO_JS.index("// V5-LAYOUT-ATOMIC — a click on an empty Cell")]
        self.assertEqual(set(re.findall(r"type: '([a-z_.]+)'", body)), {"container.add"})
        self.assertEqual(body.count("R4.enqueueStructuralMutation("), 1)
        self.assertIn("mutation.spans = spansAttr.split(',').map(Number);", body)
        self.assertIn("data-rs-add-row-fourth", body)
