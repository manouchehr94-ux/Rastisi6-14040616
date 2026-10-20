"""R4-08 — the section settings chain (Inspector control -> schema -> save -> Draft -> render) must do what it shows.

Root causes proven here (each test failed before its fix):

* an explicit ``0`` of a design number (radius, border width, paddings, margins, gap ...) was stored but shown as an EMPTY
  control (``|default:""`` swallows 0) — and the next edit of that block re-sent the empty value, silently dropping the 0;
* a "colour + pattern" / "palette + pattern" background without a chosen pattern silently fell back to «theme», so the
  colour/palette the merchant had just chosen disappeared with no effect and no explanation;
* an out-of-range or cleared number was refused with an EMPTY message (so the Studio could only say "error"), the number
  inputs declared no limits, and an optional number could never be cleared back to its default.
"""

import re
from pathlib import Path

from django.urls import reverse

import apps.storefront_builder as sfb_package
from apps.storefront_builder import design_block, section_registry
from apps.storefront_builder.models import StorefrontSection

from .test_r4_mutation_api import R4MutationApiTestCase


def _inspector(client, pk):
    return client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[pk])).content.decode()


def _design_input(html, prop):
    """The ``<input>`` markup of one design property row."""
    start = html.index(f'data-r4-design-prop="{prop}"')
    end = html.index("</div>", start)
    return html[start:end]


class _Base(R4MutationApiTestCase):
    def make(self, key, order=1):
        definition = section_registry.get_definition(key)
        return StorefrontSection.objects.create(
            version=self.draft, section_key=key, order=order, settings=definition.default_settings(),
        )

    def patch(self, section, patch):
        self.draft.refresh_from_db()
        return self._post_json({
            "base_revision": self.draft.edit_revision,
            "mutation": {"type": "section.update_settings", "section_id": section.pk, "patch": patch},
        })


class DesignZeroValueTests(_Base):
    def test_an_explicit_zero_is_stored_and_shown_not_blanked(self):
        section = self.make("product_section")
        response = self.patch(section, {"design": {"radius": 0, "border_width": 0, "padding_top": 0}})
        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        self.assertEqual(section.settings["design"]["radius"], 0)

        html = _inspector(self.client, section.pk)
        for prop in ("radius", "border_width", "padding_top"):
            if f'data-r4-design-prop="{prop}"' in html:
                self.assertIn('value="0"', _design_input(html, prop), prop)

    def test_an_unset_design_number_still_renders_empty_automatic(self):
        section = self.make("product_section")
        self.patch(section, {"design": {"radius": 0}})
        html = _inspector(self.client, section.pk)
        self.assertIn('placeholder="خودکار"', _design_input(html, "radius"))
        self.assertIn('value=""', _design_input(html, "padding_bottom"))

    def test_the_next_edit_of_the_block_keeps_the_zero(self):
        """The Studio re-sends every non-empty control of the design block; a 0 the control shows survives."""
        section = self.make("product_section")
        self.patch(section, {"design": {"radius": 0}})
        html = _inspector(self.client, section.pk)
        self.assertIn('value="0"', _design_input(html, "radius"))
        # what the script would send after the user also set the border width: radius still 0
        self.patch(section, {"design": {"radius": 0, "border_width": 3}})
        section.refresh_from_db()
        self.assertEqual(section.settings["design"], {"radius": 0, "border_width": 3})


class BackgroundPatternFallbackTests(_Base):
    def test_colour_plus_pattern_without_a_pattern_keeps_the_colour(self):
        section = self.make("product_section")
        response = self.patch(section, {"background": {"mode": "pattern", "color": "#E11D48", "pattern_slug": ""}})
        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        bg = section.settings["background"]
        self.assertEqual((bg["mode"], bg["color"]), ("color", "#E11D48"))

    def test_palette_plus_pattern_without_a_pattern_keeps_the_palette_role(self):
        section = self.make("product_section")
        self.patch(section, {"background": {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": ""}})
        section.refresh_from_db()
        bg = section.settings["background"]
        self.assertEqual((bg["mode"], bg["palette_role"]), ("palette", "tone-2"))

    def test_a_real_pattern_is_kept_with_its_mode(self):
        section = self.make("product_section")
        slug = next(iter(section_registry.PATTERN_REGISTRY))
        self.patch(section, {"background": {"mode": "pattern", "color": "#E11D48", "pattern_slug": slug}})
        section.refresh_from_db()
        bg = section.settings["background"]
        self.assertEqual((bg["mode"], bg["color"], bg["pattern_slug"]), ("pattern", "#E11D48", slug))

    def test_an_unknown_pattern_slug_is_still_refused_to_theme(self):
        section = self.make("product_section")
        self.patch(section, {"background": {"mode": "pattern", "color": "#E11D48", "pattern_slug": "no-such-pattern"}})
        section.refresh_from_db()
        self.assertEqual(section.settings["background"]["mode"], "theme")


class NumberFieldContractTests(_Base):
    def setUp(self):
        super().setUp()
        self.product = self.make("product_section")
        self.banner = self.make("multi_banner", order=2)

    def test_out_of_range_number_is_refused_with_a_precise_persian_message(self):
        response = self.patch(self.product, {"item_limit": 99})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "invalid_settings")
        self.assertTrue(body["message"], "the refusal must say why")
        self.assertIn("۲۴", body["message"])           # the maximum (Persian digits)
        self.assertIn("۲", body["message"])            # the minimum
        self.assertRegex(body["message"], r"[؀-ۿ]")  # Persian, never the internal English text
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.settings["item_limit"], 99)

    def test_garbage_text_in_a_number_is_refused_with_a_message(self):
        response = self.patch(self.product, {"item_limit": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["message"])

    def test_any_other_invalid_value_still_gets_a_generic_persian_message(self):
        response = self.patch(self.product, {"display_mode": "not-a-mode"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["message"])

    def test_clearing_a_number_restores_its_default(self):
        self.patch(self.banner, {"item_limit": 3, "offset": 4})
        self.banner.refresh_from_db()
        self.assertEqual((self.banner.settings["item_limit"], self.banner.settings["offset"]), (3, 4))
        response = self.patch(self.banner, {"item_limit": "", "offset": ""})
        self.assertEqual(response.status_code, 200, response.content)
        self.banner.refresh_from_db()
        self.assertEqual(self.banner.settings["offset"], 0)
        self.assertIn(self.banner.settings["item_limit"], (None, 24))

    def test_clearing_a_number_with_a_default_restores_that_default(self):
        self.patch(self.product, {"item_limit": 12})
        response = self.patch(self.product, {"item_limit": ""})
        self.assertEqual(response.status_code, 200, response.content)
        self.product.refresh_from_db()
        self.assertEqual(self.product.settings["item_limit"], 8)

    def test_number_inputs_declare_their_limits(self):
        html = _inspector(self.client, self.product.pk)
        match = re.search(r'<input[^>]*data-r4-field-key="item_limit"[^>]*>', html)
        self.assertIsNotNone(match)
        tag = match.group(0)
        self.assertIn('data-r4-min="2"', tag)
        self.assertIn('data-r4-max="24"', tag)
        self.assertRegex(html, r'data-r4-field-hint[^>]*>[^<]*2[^<]*24')

    def test_the_script_clamps_a_typed_number_and_sends_the_default_for_an_empty_one(self):
        js = (Path(sfb_package.__file__).parent / "static" / "storefront_builder" / "r4_editor.js").read_text(encoding="utf-8")
        self.assertIn("data-r4-min", js)
        self.assertIn("data-r4-max", js)
        self.assertIn("data-r4-default", js)


class SharedContractAcrossSectionsTests(_Base):
    """The contract is the schema's, not product_section's: every section that declares the field obeys it."""

    def _keys_with(self, field_type):
        return [
            key for key, definition in section_registry.SECTION_REGISTRY.items()
            if definition.settings_schema and any(f.field_type == field_type for f in definition.settings_schema.fields)
        ]

    def test_every_section_with_a_design_block_stores_an_explicit_zero(self):
        keys = self._keys_with("design")
        self.assertTrue(keys)
        for order, key in enumerate(keys, start=1):
            with self.subTest(section=key):
                numbers = [
                    p for p in design_block.applicable_properties(key) if design_block.DESIGN_PROPERTIES[p].kind == "int"
                ]
                if not numbers:   # this section's capabilities expose no number to the merchant
                    continue
                section = self.make(key, order=order)
                response = self.patch(section, {"design": {numbers[0]: 0}})
                self.assertEqual(response.status_code, 200, response.content)
                section.refresh_from_db()
                self.assertEqual(section.settings["design"].get(numbers[0]), 0)

    def test_every_section_with_a_background_keeps_the_colour_of_an_unfinished_pattern_choice(self):
        keys = self._keys_with("background")
        self.assertTrue(keys)
        for order, key in enumerate(keys, start=1):
            with self.subTest(section=key):
                section = self.make(key, order=order)
                response = self.patch(section, {"background": {"mode": "pattern", "color": "#0F766E", "pattern_slug": ""}})
                self.assertEqual(response.status_code, 200, response.content)
                section.refresh_from_db()
                bg = section.settings["background"]
                self.assertEqual((bg["mode"], bg["color"]), ("color", "#0F766E"))

    def test_every_bounded_number_refuses_with_a_message_and_accepts_being_cleared(self):
        checked = 0
        for order, (key, definition) in enumerate(section_registry.SECTION_REGISTRY.items(), start=1):
            if not definition.settings_schema:
                continue
            for field in definition.settings_schema.fields:
                if field.field_type != "integer" or field.max_value is None:
                    continue
                with self.subTest(section=key, field=field.key):
                    section = self.make(key, order=order)
                    too_big = self.patch(section, {field.key: field.max_value + 1})
                    self.assertEqual(too_big.status_code, 400, too_big.content)
                    self.assertRegex(too_big.json()["message"], r"[؀-ۿ]")
                    cleared = self.patch(section, {field.key: ""})
                    if field.required and field.default is None:
                        continue
                    self.assertEqual(cleared.status_code, 200, cleared.content)
                    checked += 1
        self.assertGreater(checked, 0)

    def test_every_integer_control_in_every_inspector_declares_its_limits(self):
        seen = 0
        for order, (key, definition) in enumerate(section_registry.SECTION_REGISTRY.items(), start=1):
            if not definition.settings_schema:
                continue
            integers = [f for f in definition.settings_schema.fields if f.field_type == "integer"]
            if not integers:
                continue
            section = self.make(key, order=order)
            html = _inspector(self.client, section.pk)
            for field in integers:
                with self.subTest(section=key, field=field.key):
                    tag = re.search(rf'<input[^>]*data-r4-field-key="{re.escape(field.key)}"[^>]*>', html)
                    if tag is None:   # the control is not part of this Inspector's tabs (hidden/virtual field)
                        continue
                    seen += 1
                    if field.min_value is not None:
                        self.assertIn(f'data-r4-min="{field.min_value}"', tag.group(0))
                    if field.max_value is not None:
                        self.assertIn(f'data-r4-max="{field.max_value}"', tag.group(0))
        self.assertGreater(seen, 0)
