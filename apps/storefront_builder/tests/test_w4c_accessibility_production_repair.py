"""P5-W4C — Accessibility Closure Round, Phase B — production repair contracts.

Repair round 2's bounded browser smoke recorded two genuine, pre-existing
production accessibility gaps (not harness bugs, documented in
``docs/qa_evidence/storefront_design_engine/phase5/w4_certification/implementation/23_repair_round2_smoke_evidence.md``):

- Finding A (Listing): ``product_listing.html``'s filter/search/sort
  controls carry no accessible name mechanism.
- Finding B (PDP): ``product_main.html``'s ``.opt-block .swatch`` divs are
  not keyboard-focusable.

These tests are the strict-TDD RED contracts for the Accessibility
Closure Round's authorized Phase B repair -- ONLY these two template
files, no renderer/registry/service/model/cart-logic/Theme-architecture
change. No existing test module owns rendering/accessibility assertions
for either template (confirmed by source inspection: no test file greps
either template's filename for an accessibility contract), so this is a
new, dedicated module per the round's own instruction.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates" / "storefront_builder" / "sections"


class W4CListingAccessibleNameRepairTests(SimpleTestCase):
    """Finding A -- every filter/search/sort control in BOTH layout
    branches (``sidebar_dense`` and standard) must carry an explicit
    accessible name (``aria-label``), not rely on a preceding ``<h3>``,
    a plain ``<span>``, or placeholder text alone."""

    LABELS = {
        "q": "جستجوی محصولات",
        "category": "دسته‌بندی",
        "brand": "برند",
        "min_price": "حداقل قیمت",
        "max_price": "حداکثر قیمت",
        "sort": "مرتب‌سازی",
    }

    # Matches the opening ``{% if ... %}``, a bare ``{% else %}``, or
    # ``{% endif %}`` -- depth-tracked below so an inline conditional on an
    # attribute value (e.g. ``{% if sort_key == key %}selected{% endif %}``,
    # of which this file has several) is never mistaken for the TOP-LEVEL
    # ``{% if settings.layout_variant == "sidebar_dense" %}``'s own closing
    # tag. Django templates have no ``{% elif %}``, so if/else/endif alone
    # is a complete depth model.
    _TAG_RE = re.compile(r"\{%-?\s*(if\b[^%]*|else|endif)\s*-?%\}")

    @classmethod
    def _split_top_level_if_else(cls, source, if_marker):
        start = source.index(if_marker)
        depth = 1
        else_idx = None
        endif_idx = None
        for match in cls._TAG_RE.finditer(source, start + len(if_marker)):
            tag = match.group(1)
            if tag.startswith("if"):
                depth += 1
            elif tag == "endif":
                depth -= 1
                if depth == 0:
                    endif_idx = match.start()
                    break
            elif tag == "else" and depth == 1 and else_idx is None:
                else_idx = match.start()
        assert else_idx is not None and endif_idx is not None, "unbalanced if/else/endif"
        return start, else_idx, endif_idx

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = (TEMPLATES_ROOT / "product_listing.html").read_text(encoding="utf-8")
        start, else_idx, endif_idx = cls._split_top_level_if_else(
            cls.source, '{% if settings.layout_variant == "sidebar_dense" %}'
        )
        cls.sidebar_dense_branch = cls.source[start:else_idx]
        cls.standard_branch = cls.source[else_idx:endif_idx]

    def _tag(self, branch, name_attr):
        match = re.search(
            r'<(?:input|select)\b[^>]*\bname="%s"[^>]*>' % re.escape(name_attr),
            branch,
        )
        self.assertIsNotNone(match, f'no <input|select name="{name_attr}"> tag found')
        return match.group(0)

    def _assert_accessible_name_in_both_branches(self, name_attr):
        label = self.LABELS[name_attr]
        for layout, branch in (
            ("sidebar_dense", self.sidebar_dense_branch),
            ("standard", self.standard_branch),
        ):
            with self.subTest(layout=layout, control=name_attr):
                tag = self._tag(branch, name_attr)
                self.assertIn(
                    f'aria-label="{label}"',
                    tag,
                    f'{layout} layout: name="{name_attr}" control is missing '
                    f'aria-label="{label}"; found tag: {tag!r}',
                )

    def test_1_q_search_input_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("q")

    def test_2_category_select_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("category")

    def test_3_brand_select_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("brand")

    def test_4_min_price_input_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("min_price")

    def test_5_max_price_input_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("max_price")

    def test_6_sort_select_has_aria_label_both_branches(self):
        self._assert_accessible_name_in_both_branches("sort")

    def test_7_discounted_checkbox_already_has_a_label_wrapper_untouched(self):
        """Regression guard -- the two checkboxes were never flagged as
        broken (already wrapped in ``<label class="plp-check">``); this
        repair must not touch them."""
        for branch in (self.sidebar_dense_branch, self.standard_branch):
            self.assertIn('<label class="plp-check">', branch)
            self.assertIn('name="discounted"', branch)
            self.assertIn('name="in_stock"', branch)


class W4CPdpSwatchKeyboardRepairTests(SimpleTestCase):
    """Finding B -- the ``.opt-block .swatch`` control must become
    keyboard-operable in BOTH the multi_axis and legacy variant-rendering
    paths, reusing the SAME existing Alpine selection function for mouse
    click and keyboard Enter/Space -- never a second state owner."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = (TEMPLATES_ROOT / "product_main.html").read_text(encoding="utf-8")

    def _extract_swatch_div(self, click_action):
        pattern = r'<div class="swatch"[^>]*@click="%s"[^>]*></div>' % re.escape(click_action)
        match = re.search(pattern, self.source)
        self.assertIsNotNone(
            match, f'no swatch <div> found with @click="{click_action}"; source may already differ from expected shape'
        )
        return match.group(0)

    # ---- multi_axis path (selectAxisValue) --------------------------------

    def test_10_multi_axis_swatch_has_role_button(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn('role="button"', tag)

    def test_11_multi_axis_swatch_has_tabindex_zero(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn('tabindex="0"', tag)

    def test_12_multi_axis_swatch_has_dynamic_aria_label(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn(':aria-label="v.label"', tag)

    def test_13_multi_axis_swatch_has_aria_pressed_matching_active_state(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn(':aria-pressed="selected[axis.id] === v.id"', tag)

    def test_14_multi_axis_swatch_enter_invokes_same_selection_function(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn('@keydown.enter.prevent="selectAxisValue(axis.id, v.id)"', tag)

    def test_15_multi_axis_swatch_space_invokes_same_selection_function(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn('@keydown.space.prevent="selectAxisValue(axis.id, v.id)"', tag)

    def test_16_multi_axis_swatch_click_still_present_unchanged(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn('@click="selectAxisValue(axis.id, v.id)"', tag)

    def test_17_multi_axis_swatch_title_and_visual_state_preserved(self):
        tag = self._extract_swatch_div("selectAxisValue(axis.id, v.id)")
        self.assertIn(':title="v.label"', tag)
        self.assertIn(":style=\"'background:' + v.color_hex\"", tag)
        self.assertIn(
            ":class=\"{ active: selected[axis.id] === v.id, unavailable: !isValueAvailable(axis.id, v.id) }\"",
            tag,
        )

    # ---- legacy path (selectLegacy) ---------------------------------------

    def test_20_legacy_swatch_has_role_button(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn('role="button"', tag)

    def test_21_legacy_swatch_has_tabindex_zero(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn('tabindex="0"', tag)

    def test_22_legacy_swatch_has_dynamic_aria_label(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn(':aria-label="v.label"', tag)

    def test_23_legacy_swatch_has_aria_pressed_matching_active_state(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn(':aria-pressed="selectedVariantId === v.id"', tag)

    def test_24_legacy_swatch_enter_invokes_same_selection_function(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn('@keydown.enter.prevent="selectLegacy(v.id)"', tag)

    def test_25_legacy_swatch_space_invokes_same_selection_function(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn('@keydown.space.prevent="selectLegacy(v.id)"', tag)

    def test_26_legacy_swatch_click_still_present_unchanged(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn('@click="selectLegacy(v.id)"', tag)

    def test_27_legacy_swatch_title_and_visual_state_preserved(self):
        tag = self._extract_swatch_div("selectLegacy(v.id)")
        self.assertIn(':title="v.label"', tag)
        self.assertIn(":style=\"'background:' + v.color_hex\"", tag)
        self.assertIn(
            ':class="{ active: selectedVariantId === v.id, unavailable: !v.is_purchasable }"',
            tag,
        )

    # ---- regression guard: the sibling size <button> path is untouched ---

    def test_30_multi_axis_size_button_path_unchanged(self):
        self.assertIn(
            '<button type="button" class="size" :class="{ active: selected[axis.id] === v.id, '
            'unavailable: !isValueAvailable(axis.id, v.id) }"\n'
            '                          @click="selectAxisValue(axis.id, v.id)" x-text="v.label"></button>',
            self.source,
        )

    def test_31_legacy_size_button_path_unchanged(self):
        self.assertIn(
            '<button type="button" class="size" :class="{ active: selectedVariantId === v.id, '
            'unavailable: !v.is_purchasable }"\n'
            '                          @click="selectLegacy(v.id)" x-text="v.label"></button>',
            self.source,
        )

    def test_32_no_second_alpine_component_introduced(self):
        """Key invariant -- mouse click and keyboard Enter/Space must
        invoke the SAME existing selection function; no duplicate Alpine
        state owner. There is still exactly one ``x-data="variantSelector(``
        root in the file."""
        self.assertEqual(self.source.count('x-data="variantSelector('), 1)
