"""R4-09 + R4-10 — the Design Studio settings UX.

R4-09  ONE shared colour picker in front of every R4 colour control (palette roles with real swatches, suggested colours,
       free spectrum, HEX field, automatic vs custom kept apart, cancel never writes). It is progressive enhancement of the
       existing native controls: the storage contract (``""`` | ``token:<role>`` | ``#RRGGBB``) and the mutation path
       are untouched, so there is no second engine here — only the pieces that can be pinned without a browser:
       the palette swatch data, the markup contract the picker relies on and the picker's "never writes by itself" rule.
       The behaviour in a real browser (pick, type, cancel, F5, Draft preview, Published unchanged) is in the QA evidence.

R4-10  The Design tab is split into five sub-sections by GENERIC metadata (``workspace_layout``): the ``design`` field is
       shown as slices built from the section's own applicable properties, so a control appears only where the section
       supports it, nothing is lost or duplicated, and the stored settings / schema do not change.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

import apps.storefront_builder as sfb_package
from apps.storefront_builder import design_block, section_registry, semantic_colors, workspace_layout
from apps.storefront_builder.models import StorefrontSection

from .test_r408_section_settings_contract import _Base, _design_input, _inspector

APP = Path(sfb_package.__file__).parent
STATIC = APP / "static" / "storefront_builder"
EDITOR_JS = (STATIC / "r4_editor.js").read_text(encoding="utf-8")
STUDIO_JS = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
STUDIO_CSS = (STATIC / "r4_studio.css").read_text(encoding="utf-8")
_PICKER = STATIC / "r4_color_picker.js"
PICKER_JS = _PICKER.read_text(encoding="utf-8") if _PICKER.exists() else ""   # a missing file fails the tests, not the import

SUBS = ["background", "colors", "cards", "layout", "images"]
OWNER_PROPS = {
    "colors": {"text_color", "heading_color", "accent_color", "price_color", "button_fill", "button_text", "button_border"},
    "cards": {"surface_color", "border_color", "border_width", "radius", "shadow", "shadow_color", "shadow_blur"},
    "layout": {"padding_top", "padding_bottom", "margin_top", "margin_bottom", "min_height", "align", "gap",
               "columns_desktop", "columns_tablet", "columns_mobile", "item_width", "valign", "mobile_layout"},
    "images": {"image_ratio", "image_fit", "image_position", "image_zoom", "hide_desktop", "hide_tablet", "hide_mobile"},
}


def _slice_props(card):
    return [p["key"] for g in card.design_groups for p in g["properties"]]


def _tabs(key):
    definition = section_registry.SECTION_REGISTRY[key]
    return {t.key: t for t in workspace_layout.build_workspace_tabs(
        definition.settings_schema.fields, design_groups=design_block.serialize_registry_for_inspector(key),
    )}


# ------------------------------------------------------------------------------------------------ R4-10 engine
class DesignSubsectionEngineTests(SimpleTestCase):
    def test_every_section_type_keeps_three_primary_tabs_and_slices_every_applicable_property_exactly_once(self):
        checked = 0
        for key, definition in section_registry.SECTION_REGISTRY.items():
            if definition.settings_schema is None:
                continue
            tabs = _tabs(key)
            self.assertEqual(list(tabs), ["content", "design", "advanced"], key)
            slices = [c for c in tabs["design"].cards if c.design_groups is not None]
            sliced = [p for c in slices for p in _slice_props(c)]
            has_design_field = any(f.field_type == "design" for f in definition.settings_schema.fields)
            if has_design_field:
                self.assertEqual(sorted(sliced), sorted(design_block.applicable_properties(key)), f"{key}: lost/duplicated")
                self.assertEqual(len(sliced), len(set(sliced)), key)
            else:
                self.assertEqual(slices, [], key)
            # every non-design field is in exactly ONE card of exactly one tab
            placed = [f.key for t in tabs.values() for c in t.cards for f in c.fields if f.field_type != "design"]
            expected = [f.key for f in definition.settings_schema.fields if f.field_type != "design"]
            self.assertEqual(sorted(placed), sorted(expected), key)
            checked += 1
        self.assertGreater(checked, 20)

    def test_subsections_are_the_owner_five_in_order_and_only_where_the_section_supports_them(self):
        for key, definition in section_registry.SECTION_REGISTRY.items():
            if definition.settings_schema is None:
                continue
            design = _tabs(key)["design"]
            keys = [s.key for s in design.subsections]
            self.assertEqual(keys, [k for k in SUBS if k in keys], f"{key}: wrong order / unknown sub-section")
            for sub in design.subsections:
                self.assertTrue(sub.cards, f"{key}/{sub.key}: an empty sub-section must not exist")
                for card in sub.cards:
                    self.assertTrue(card.fields or card.has_media_manager or card.is_manage, f"{key}/{card.key}")
            # background only when the schema has the background field
            self.assertEqual(
                "background" in keys, any(f.field_type == "background" for f in definition.settings_schema.fields), key,
            )
            # a design sub-section only offers properties the section's capabilities grant
            applicable = set(design_block.applicable_properties(key))
            for sub in design.subsections:
                for card in sub.cards:
                    if card.design_groups is not None:
                        self.assertTrue(set(_slice_props(card)) <= applicable, key)
                        self.assertTrue(set(_slice_props(card)) <= OWNER_PROPS[sub.key], f"{key}/{sub.key}")

    def test_the_owner_assignment_of_properties(self):
        design = _tabs("product_section")["design"]
        by_sub = {s.key: {p for c in s.cards if c.design_groups is not None for p in _slice_props(c)} for s in design.subsections}
        self.assertEqual([s.key for s in design.subsections], SUBS)
        for sub, expected in OWNER_PROPS.items():
            self.assertEqual(by_sub[sub], expected & set(design_block.applicable_properties("product_section")), sub)
        # product_section really supports (nearly) all of them, so the sets are the whole owner list
        self.assertGreaterEqual(len(by_sub["colors"]), 6)

    def test_unlisted_properties_follow_their_design_group(self):
        self.assertEqual(workspace_layout.design_property_subsection("future_x", "image"), "images")
        self.assertEqual(workspace_layout.design_property_subsection("future_y", "shadow"), "cards")
        self.assertEqual(workspace_layout.design_property_subsection("future_z", "actions"), "colors")
        self.assertEqual(workspace_layout.design_property_subsection("future_w", "unknown-group"), "layout")
        self.assertEqual(workspace_layout.design_property_subsection("surface_color", "colors"), "cards")

    def test_every_registered_design_property_has_a_subsection(self):
        for prop in design_block.DESIGN_PROPERTIES.values():
            sub = workspace_layout.design_property_subsection(prop.key, prop.group)
            self.assertIn(sub, SUBS)
            self.assertIn(prop.key, OWNER_PROPS[sub], f"{prop.key} is not in the owner list of {sub}")

    def test_without_design_groups_the_field_stays_one_card(self):
        definition = section_registry.SECTION_REGISTRY["product_section"]
        design = {t.key: t for t in workspace_layout.build_workspace_tabs(definition.settings_schema.fields)}["design"]
        self.assertIn("style", [c.key for c in design.cards])
        self.assertEqual([c.design_groups for c in design.cards if c.key == "style"], [None])


# ------------------------------------------------------------------------------------------------ R4-10 markup
class DesignSubsectionMarkupTests(_Base):
    def _html(self, key, order=1):
        return _inspector(self.client, self.make(key, order).pk)

    def test_product_section_shows_a_five_tab_bar_with_accessible_wiring(self):
        html = self._html("product_section")
        nav = html[html.index("data-r4-subnav"):]
        self.assertEqual(re.findall(r'data-r4-sub="([a-z]+)"', nav), SUBS)
        self.assertIn('<nav class="r4-ws-subnav" role="tablist"', html)
        for sub in SUBS:
            self.assertIn(f'id="r4Sub-{sub}"', html)
            self.assertIn(f'aria-controls="r4SubPanel-{sub}"', html)
            self.assertIn(f'id="r4SubPanel-{sub}"', html)
            self.assertIn(f'aria-labelledby="r4Sub-{sub}"', html)
            self.assertIn('role="tabpanel"', html)
        # roving tabindex: only the active tab is tabbable
        self.assertEqual(len(re.findall(r'data-r4-sub="[a-z]+" aria-controls="[^"]+" aria-selected="true" tabindex="0"', html)), 1)
        self.assertEqual(len(re.findall(r'aria-selected="false" tabindex="-1"', html)), 4)

    def test_dom_ids_are_unique_even_though_the_design_field_is_sliced(self):
        html = self._html("product_section")
        ids = re.findall(r'\bid="([^"]+)"', html)
        duplicated = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(duplicated, set())

    def test_each_design_property_control_exists_exactly_once_and_in_its_owner_subsection(self):
        html = self._html("product_section")
        keys = re.findall(r'data-r4-design-prop="([a-z_]+)"', html)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(design_block.applicable_properties("product_section")))
        for sub, props in OWNER_PROPS.items():
            start = html.index(f'data-r4-sub-panel="{sub}"')
            nxt = [html.find(f'data-r4-sub-panel="{o}"', start + 10) for o in SUBS if SUBS.index(o) > SUBS.index(sub)]
            end = min([n for n in nxt if n != -1] or [html.index("<footer", start)])
            inside = set(re.findall(r'data-r4-design-prop="([a-z_]+)"', html[start:end]))
            self.assertEqual(inside, props & set(keys), sub)

    def test_sections_show_only_what_they_support(self):
        # hero: background + layout-ish cards only; a section with just a background gets no sub bar at all
        hero = self._html("hero_banner")
        hero_subs = re.findall(r'data-r4-sub="([a-z]+)"', hero)
        self.assertIn("background", hero_subs)
        self.assertNotIn("colors", hero_subs)
        newsletter = self._html("newsletter", order=2)
        self.assertNotIn("data-r4-subnav", newsletter)
        self.assertIn('data-r4-ws-card="background"', newsletter)

    def test_a_section_without_a_design_block_never_renders_a_design_property(self):
        html = self._html("faq", order=3)
        self.assertNotIn("data-r4-design-prop", html)

    def test_r408_zero_and_auto_survive_the_split(self):
        section = self.make("product_section")
        self.patch(section, {"design": {"radius": 0, "border_width": 0, "padding_top": 0}})
        html = _inspector(self.client, section.pk)
        for prop in ("radius", "border_width", "padding_top"):
            self.assertIn('value="0"', _design_input(html, prop), prop)
        self.assertIn('placeholder="خودکار"', _design_input(html, "padding_bottom"))
        self.assertIn('value=""', _design_input(html, "padding_bottom"))

    def test_r408_number_limits_still_declared(self):
        html = self._html("product_section")
        tag = re.search(r'<input[^>]*data-r4-field-key="item_limit"[^>]*>', html).group(0)
        self.assertIn('data-r4-min="2"', tag)
        self.assertIn('data-r4-max="24"', tag)

    def test_a_patch_of_the_whole_design_block_is_still_accepted_unchanged(self):
        """The Studio sends the WHOLE block (all slices read) — same contract and result as before the split."""
        section = self.make("product_section")
        patch = {"design": {"radius": 12, "text_color": "token:primary", "surface_color": "#E11D48",
                            "image_ratio": "square", "padding_top": 10}}
        response = self.patch(section, patch)
        self.assertEqual(response.status_code, 200, response.content)
        section.refresh_from_db()
        self.assertEqual(section.settings["design"], patch["design"])

    def test_the_stored_settings_schema_is_unchanged(self):
        definition = section_registry.SECTION_REGISTRY["product_section"]
        design_fields = [f for f in definition.settings_schema.fields if f.field_type == "design"]
        self.assertEqual([f.key for f in design_fields], ["design"])


class DesignSubsectionScriptAndStyleTests(SimpleTestCase):
    def test_the_design_patch_gathers_every_slice(self):
        self.assertIn(".r4-design-block[data-r4-field-key=", EDITOR_JS)
        self.assertIn("slices", EDITOR_JS[EDITOR_JS.index("R4-10: the Design tab shows this ONE field"):][:900])

    def test_switching_sub_sections_is_pure_display_state(self):
        block = EDITOR_JS[EDITOR_JS.index("function activateSub("):EDITOR_JS.index("function syncSubsections()")]
        self.assertNotIn("enqueueMutation", block)
        self.assertNotIn("fetch(", block)
        self.assertIn("panel.hidden", block)          # panels are hidden, never removed: no control (value) is lost

    def test_keyboard_navigation_follows_rtl(self):
        block = EDITOR_JS[EDITOR_JS.index("R4-10 — keyboard on the Design sub-section bar"):][:1400]
        for needle in ("ArrowLeft", "ArrowRight", "Home", "End", "rtl"):
            self.assertIn(needle, block)

    def test_the_bar_hides_when_fewer_than_two_sub_sections_have_content_and_follows_search(self):
        self.assertIn("visibleKeys.length < 2", EDITOR_JS)
        self.assertIn("R4.setSubsectionSearch", EDITOR_JS)
        self.assertIn("R4.setSubsectionSearch", STUDIO_JS)

    def test_dormant_design_slices_hide_their_card(self):
        block = EDITOR_JS[EDITOR_JS.index("function syncWorkspaceCards()"):][:1800]
        self.assertIn("data-r4-design-group", block)
        self.assertIn("anyGroup", block)

    def test_the_bar_is_sticky_scrolls_sideways_and_is_larger_on_phones(self):
        rule = re.search(r"\.rs-studio \.r4-ws-subnav\{([^}]*)\}", STUDIO_CSS).group(1)
        for needle in ("position:sticky", "overflow-x:auto", "flex-wrap:nowrap"):
            self.assertIn(needle, rule)
        phone = STUDIO_CSS[STUDIO_CSS.index("R4-10 — Design tab sub-sections"):]
        self.assertRegex(phone, r"@media \(max-width:850px\)\{[^@]*\.r4-ws-subtab\{min-height:42px")
        self.assertIn("aria-selected=\"true\"", STUDIO_CSS[STUDIO_CSS.index("R4-10 — Design tab sub-sections"):])


# ------------------------------------------------------------------------------------------------ R4-09
class ColorPaletteDataTests(SimpleTestCase):
    def test_every_palette_role_resolves_to_a_hex_for_the_swatches(self):
        mapping = semantic_colors.token_hex_map({})
        self.assertEqual(set(mapping), {f"token:{k}" for k in semantic_colors.SEMANTIC_COLOR_TOKENS})
        for token, value in mapping.items():
            self.assertRegex(value, r"^#[0-9A-F]{6}$", token)

    def test_swatches_follow_the_draft_palette(self):
        before = semantic_colors.token_hex_map({})
        after = semantic_colors.token_hex_map({"color_overrides": {"primary": "#112233"}})
        self.assertNotEqual(before["token:primary"], after["token:primary"])
        self.assertEqual(after["token:primary"], "#112233")
        # display data only: the stored value of a role is still the role, never the hex
        self.assertEqual(semantic_colors.clean_semantic_color("token:primary"), "token:primary")

    def test_none_config_is_safe(self):
        self.assertEqual(set(semantic_colors.token_hex_map(None)), set(semantic_colors.token_hex_map({})))


class ColorPickerContractTests(_Base):
    def test_palette_options_carry_their_swatch_colour_and_the_native_controls_stay_as_fallback(self):
        html = _inspector(self.client, self.make("product_section").pk)
        self.assertIn("data-r4-color-token", html)
        self.assertIn("data-r4-color-custom", html)
        options = re.findall(r'<option value="(token:[a-z0-9-]+)" data-hex="([^"]*)"', html)
        self.assertTrue(options)
        for token, hex_value in options:
            self.assertRegex(hex_value, r"^#[0-9A-F]{6}$", token)

    def test_automatic_and_custom_stay_distinct_in_the_native_source_of_truth(self):
        section = self.make("product_section")
        self.patch(section, {"design": {"text_color": "#E11D48"}})
        html = _inspector(self.client, section.pk)
        row = html[html.index('data-r4-design-prop="text_color"'):][:2600]
        self.assertIn('<option value="custom" selected>', row)
        self.assertIn('value="#e11d48"', row)
        # an untouched colour is "automatic" (empty), never a silently saved grey
        auto = html[html.index('data-r4-design-prop="heading_color"'):][:2600]
        self.assertIn('<option value="" selected>', auto)
        self.assertIn("hidden", auto[auto.index('data-r4-color-custom'):][:300])

    def test_the_editor_page_loads_the_picker_script(self):
        page = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn("storefront_builder/r4_color_picker.js", page)
        self.assertIn("r4_editor.js", page)


class ColorPickerSourceTests(SimpleTestCase):
    def test_the_picker_never_writes_by_itself(self):
        for forbidden in ("fetch(", "XMLHttpRequest", "enqueueMutation", "enqueueStructuralMutation", "localStorage"):
            self.assertNotIn(forbidden, PICKER_JS, forbidden)
        # it only changes the native control and dispatches the same bubbling `change` the control always dispatched
        self.assertIn("new Event(type, { bubbles: true })", PICKER_JS)

    def test_cancel_paths_exist_and_apply_nothing(self):
        close_block = PICKER_JS[PICKER_JS.index("function closePicker("):PICKER_JS.index("function openPicker(")]
        self.assertNotIn("apply", close_block.replace("applyAndClose", ""))
        for needle in ("Escape", "onOutside", "'انصراف'", "closePicker(true)"):
            self.assertIn(needle, PICKER_JS)

    def test_free_colour_is_a_draft_until_applied_and_invalid_hex_is_refused(self):
        self.assertIn("apply.disabled = !(dirty && valid)", PICKER_JS)
        self.assertIn("HEX6.test(draftHex)", PICKER_JS)
        self.assertIn("aria-invalid", PICKER_JS)
        self.assertIn("'role', 'alert'", PICKER_JS)

    def test_one_click_choices_apply_through_a_single_change(self):
        self.assertIn("applyAndClose(function () { adapter.applyAuto(); })", PICKER_JS)
        self.assertIn("adapter.applyToken(t.value)", PICKER_JS)
        self.assertIn("adapter.applyCustom(pair[0])", PICKER_JS)

    def test_accessibility_hooks(self):
        for needle in ("aria-haspopup", "aria-expanded", "'role', 'dialog'", "aria-label", "aria-pressed", "aria-live",
                       "ArrowDown", "Tab", "tabIndex"):
            self.assertIn(needle, PICKER_JS, needle)

    def test_it_enhances_every_r4_colour_control_not_just_the_background(self):
        self.assertIn("[data-r4-color-control]:not([data-r4-cp])", PICKER_JS)       # design block, colour fields, overlay, geometry
        self.assertIn('.rs-studio input[type="color"]:not([data-r4-cp])', PICKER_JS)   # background colour, global palette, container
        self.assertIn("MutationObserver", PICKER_JS)                                  # Inspector / Global Design re-render their markup

    def test_every_raw_colour_input_of_the_studio_lives_under_the_studio_root(self):
        editor = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "editor.html").read_text(encoding="utf-8")
        self.assertIn("rs-studio", editor)
        for name in ("studio_global_design.html", "studio_structure.html"):
            source = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / name).read_text(encoding="utf-8")
            self.assertIn('type="color"', source)      # still the native element: the source of truth the picker fronts

    def test_one_shared_semantic_colour_partial_serves_every_colour_property(self):
        partial = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "color_control.html").read_text(encoding="utf-8")
        self.assertIn('data-hex="{{ color_hex|dictget:token }}"', partial)
        settings_field = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "partials" / "settings_field.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(settings_field.count("color_control.html"), 3)   # colour field, design properties, overlay


@unittest.skipUnless(shutil.which("node"), "node is not available")
class ColorPickerHexParsingTests(SimpleTestCase):
    def _norm(self, values):
        script = (
            "const vm=require('vm'),fs=require('fs');"
            "const stub=()=>({style:{setProperty(){}},setAttribute(){},appendChild(){},removeChild(){},classList:{add(){}}});"
            "const ctx={document:{readyState:'complete',querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){},createElement:stub,"
            "head:stub(),body:stub(),documentElement:{contains:()=>true,setAttribute(){}}},getComputedStyle:()=>({getPropertyValue:()=>'1'}),"
            "MutationObserver:function(){this.observe=()=>{}},requestAnimationFrame:setTimeout,setTimeout,Event:function(){}};"
            "ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);"
            "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(v=>ctx.RastiSiColorPicker.normHex(v))));"
        )
        result = subprocess.run(["node", "-e", script, str(STATIC / "r4_color_picker.js"), json.dumps(values)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_hex_normalisation_accepts_what_a_merchant_types_and_refuses_the_rest(self):
        cases = {
            "#e11d48": "#E11D48", "e11d48": "#E11D48", "  #E11D48 ": "#E11D48", "#abc": "#AABBCC", "ABC": "#AABBCC",
            "۱۲۳۴۵۶": "#123456", "#۱۲۳abc": "#123ABC",
            "": "", "#12345": "", "#1234567": "", "#gggggg": "", "rgb(1,2,3)": "", "#12 345": "", "red": "",
        }
        self.assertEqual(self._norm(list(cases)), list(cases.values()))
