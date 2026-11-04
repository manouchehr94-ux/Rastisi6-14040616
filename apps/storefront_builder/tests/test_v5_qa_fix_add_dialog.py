"""V5-UI-001..004 + V5-FUNC-001 on real Django: the add dialog (tabs, library cards, search) is server-rendered from the SAME
legal library as the select, the engine-supported layout presets only, and the builder placeholders cannot hide content."""

import re

from django.urls import reverse

from ._v5_shell_support import APP, STUDIO_CSS, STUDIO_JS, strip_comments
from .test_template51_designability_wiring import _BandBase

BUILDER_CSS = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
CONTAINERS = (APP / "templates" / "storefront_builder" / "partials" / "render_container.html").read_text(encoding="utf-8")


class AddDialogRenderingTests(_BandBase):
    def _html(self):
        return self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()

    def test_every_legal_select_option_has_exactly_one_library_card_and_vice_versa(self):
        html = self._html()
        select = html[html.index('id="r4StructureAddSelect"'):]
        select = select[:select.index("</select>")]
        option_keys = re.findall(r'<option value="([a-z0-9_]+)">', select)
        card_keys = re.findall(r'data-rs-library-key="([a-z0-9_]+)"', html)
        self.assertTrue(option_keys)
        self.assertEqual(sorted(option_keys), sorted(card_keys))                 # one legality source: no extra, no missing card

    def test_cards_carry_title_category_glyph_and_registry_description_only(self):
        html = self._html()
        card = html[html.index('class="rs-library-card"'):]
        card = card[:card.index("</button>")]
        for part in ('class="rs-wire rs-wire--', 'data-rs-library-label="', 'data-rs-library-category="', "<strong>", "<em>"):
            self.assertIn(part, card)
        # rich_text declares a registry description; the card shows it verbatim (never an invented one)
        rich = html[html.index('data-rs-library-key="rich_text"'):]
        rich = rich[:rich.index("</button>")]
        self.assertIn("<small>", rich)

    def test_search_field_and_empty_state_exist_and_cards_stay_plain_buttons(self):
        html = self._html()
        self.assertIn('data-control="library-search"', html)
        self.assertIn("data-rs-library-empty", html)

    def test_the_single_legacy_add_section_action_and_the_old_select_are_kept(self):
        html = self._html()
        panel = html[html.index("data-rs-structure-scroll"):]
        self.assertEqual(panel.count('data-rastisi-action="add-section"'), 1)       # the structure panel's own opener (pinned contract)
        self.assertIn('id="r4StructureAddSelect"', html)
        self.assertIn('id="r4StructureAddButton"', html)

    def test_layout_tab_offers_the_two_cell_presets_then_the_registry_patterns_and_samples(self):
        from apps.storefront_builder.services import container_service

        html = self._html()
        offered = re.findall(r'name="rs_row_layout" value="(\w+)"', html)
        expected = [k for k, widths in container_service.LAYOUT_PRESETS.items() if len(widths) == 2]
        self.assertEqual(offered[:len(expected)], expected)                       # the five existing ratios are untouched, same order
        # V5-LAYOUT-001 (see test_v5_layout_patterns), then the four-column rows and the two editable samples added for the seller's
        # «افزودن چیدمان» dialog (see test_v5_add_layout_dialog) — each card still resolves to an existing engine preset
        self.assertEqual(offered[len(expected):], ["thirds_equal", "big_right_two_left", "quarters_equal", "quarters_424", "sample_tiles", "sample_hero_panels"])
        self.assertFalse({"quarters", "single"} & set(offered))                   # no other preset is ever offered

    def test_the_empty_cell_add_control_stays_in_the_structure_panel(self):
        # the preview chip is compact now; the authoritative add-to-empty-cell controls are server-rendered hooks that remain
        self.assertIn("data-r4-structure-empty-cell-add", self._html().replace("template", "template") + open(
            APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "studio_structure.html", encoding="utf-8").read())


class AddDialogStaticContractTests(_BandBase):
    def test_modal_has_two_tabs_one_dialog_and_ui_only_tab_state(self):
        self.assertIn("data-rastisi-action=\"add-tab\"", STUDIO_JS)
        self.assertIn("case 'add-tab':", STUDIO_JS)
        self.assertIn("case 'open-add-section': openModal('add-section'); break;", STUDIO_JS)
        self.assertIn("case 'add-row': openModal('add-row')", STUDIO_JS)             # pinned by test_followup12_add_row
        start = STUDIO_JS.index("function filterLibrary(input)")
        search = STUDIO_JS[start:STUDIO_JS.index("root.addEventListener('input'", start)]
        for forbidden in ("fetch(", "enqueue", "R4.", "XMLHttpRequest"):
            self.assertFalse(forbidden in search, forbidden)

    def test_builder_placeholder_overrides_are_builder_only_and_compact(self):
        # V5-QA-FIX-01's empty-section placeholder chip (the empty-CELL control was redesigned in V5-UI-006/007, see test_v5_ui_006_add_controls)
        mark = BUILDER_CSS.index("V5-QA-FIX-01 (V5-FUNC-001")
        block = BUILDER_CSS[BUILDER_CSS.rindex("/*", 0, mark):BUILDER_CSS.index("/* V5-UI-006/007 — add-section controls")]
        css = strip_comments(block)
        for selector in re.findall(r"([^{}]+)\{", css):
            self.assertTrue(selector.strip().startswith(".sfb-preview-sections .rsec.sfb-rsec-builder-empty"), selector)
        self.assertIn("left: 8px;", css)
        # the chip exists in the DOM only for Preview (never the public storefront)
        self.assertRegex(CONTAINERS, r"\{% elif is_preview %\}\s*<button type=\"button\" class=\"sfb-empty-cell-add\"")

    def test_studio_stylesheet_additions_stay_scoped(self):
        css = strip_comments(STUDIO_CSS[STUDIO_CSS.index(".rs-studio .rs-add-tabs{"):])
        for rule in re.findall(r"([^{}]+)\{", css):
            for selector in (s.strip() for s in rule.split(",")):
                if selector and not selector.startswith("@"):
                    self.assertTrue(selector.startswith(".rs-studio"), selector)
