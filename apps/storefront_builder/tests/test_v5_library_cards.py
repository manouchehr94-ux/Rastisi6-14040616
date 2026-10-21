"""V5 block library: the add-section dialog gains card tiles, but the ONLY writer stays the existing R4 section.add path
(r4_editor.js, #r4StructureAddButton). Static contract — no Django, no database, no browser."""

import re
import unittest

from ._v5_shell_support import APP, EDITOR_JS, STUDIO_CSS, STUDIO_JS, strip_comments

PARTIAL = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "studio_structure.html").read_text(encoding="utf-8")


def _library_markup() -> str:
    start = PARTIAL.index('<div class="rs-library"')
    return PARTIAL[start:PARTIAL.index('<label class="field" for="r4StructureAddSelect">', start)]


class V5LibraryCardTests(unittest.TestCase):
    def test_cards_are_generated_from_the_same_legal_library_as_the_select(self):
        markup = _library_markup()
        self.assertIn("{% for group in structure_library %}", markup)
        self.assertIn("{% for entry in group.items %}", markup)
        self.assertIn('data-rs-library-key="{{ entry.key }}"', markup)
        # the legacy select + button are still there (R4 hooks and existing tests rely on them)
        self.assertIn('id="r4StructureAddSelect"', PARTIAL)
        self.assertIn('id="r4StructureAddButton"', PARTIAL)

    def test_cards_live_inside_the_add_section_scope_the_r4_listener_reads(self):
        add_scope = PARTIAL.index('data-r4-add-section')
        self.assertLess(add_scope, PARTIAL.index('<div class="rs-library"'))
        self.assertLess(PARTIAL.index('<div class="rs-library"'), PARTIAL.index('id="r4StructureAddButton"'))

    def test_card_markup_carries_no_write_hooks_of_its_own(self):
        markup = _library_markup()
        for forbidden in ("data-r4-showcase-choice", "data-section-key", "<form", "href=", "onclick", "hx-"):
            self.assertFalse(forbidden in markup, forbidden)
        self.assertEqual(set(re.findall(r'data-rastisi-action="([a-z-]+)"', markup)), {"library-add"})

    def test_studio_handler_only_forwards_to_the_existing_controls(self):
        start = STUDIO_JS.index("case 'library-add':")
        handler = STUDIO_JS[start:STUDIO_JS.index("break;\n      }", start)]
        self.assertIn("querySelector('#r4StructureAddSelect')", handler)
        self.assertIn("querySelector('#r4StructureAddButton')", handler)
        self.assertIn("libButton.click()", handler)
        for forbidden in ("enqueue", "fetch", "section.add", "R4.", "XMLHttpRequest"):
            self.assertFalse(forbidden in handler, forbidden)

    def test_the_one_section_add_writer_is_unchanged(self):
        # r4_editor.js still builds section.add from the select value of #r4StructureAddButton's own scope
        self.assertIn("var addScope = addBtn.closest('[data-r4-add-section]') || structurePanel;", EDITOR_JS)
        self.assertIn("section_key: sectionKey,", EDITOR_JS)
        self.assertEqual(STUDIO_JS.count("section.add"), 0)

    def test_library_and_layout_card_css_is_scoped_and_not_hiding_anything(self):
        css = strip_comments(STUDIO_CSS[STUDIO_CSS.index(".rs-studio .rs-library{"):])
        for rule in re.findall(r"([^{}]+)\{", css):
            for selector in (s.strip() for s in rule.split(",")):
                if selector and not selector.startswith("@"):
                    self.assertTrue(selector.startswith(".rs-studio"), selector)


if __name__ == "__main__":
    unittest.main()
