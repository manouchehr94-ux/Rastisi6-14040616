"""One owner per rectangle: «پس‌زمینه این بخش» vs «رنگ سطح (پنل/کارت)» — and ONE capability registry behind it.

Owner report: on an ordinary six-card ``product_section`` the Background colour changed nothing visible when the section
also carried ``design.surface_color``: the design-block CSS re-painted the SAME rectangle the Background owns.

Engine rules pinned here (generic; no section / template key):

* Background paints the section CANVAS (wrapper, bleed layer, campaign band fill); «رنگ سطح» paints INTERNAL surfaces
  only — the elements the markup marks ``data-sfb-card-surface`` / ``data-sfb-section-surface``;
* a section type offers «رنگ سطح» iff it REGISTERS the ``internal_surface`` capability on its ``SectionDefinition`` — the
  existing capability registry is the single source of truth (Design properties, Inspector, validator, renderer);
* settings stored while a capability was granted stay editable after it is withdrawn: dormant, preserved, inert;
* a card on a custom surface re-inks (text / muted / price / accent) with the surface's accessible foreground."""

import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from apps.core.color_utils import contrast_ratio
from apps.storefront_builder import design_block, section_registry
from apps.storefront_builder.services import section_structure_service as sss
from apps.storefront_builder.settings_schema import clean_section_schema_patch

from .test_r4_mutation_api import R4MutationApiTestCase

APP = Path(__file__).resolve().parents[1]
REPO_APPS = APP.parent
BUILDER_CSS = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
THEME_CSS = (REPO_APPS / "core" / "static" / "css" / "theme_palette.css").read_text(encoding="utf-8")
_BUILDER_RULES = re.sub(r"/\*.*?\*/", "", BUILDER_CSS, flags=re.S)  # rules only: comments never carry selectors
SURFACE_HINT = "رنگ کارت‌ها یا پنل‌های داخلی این بخش"
BACKGROUND_HINT = "رنگ یا تصویر پشت کل این بخش"
MARKER = re.compile(r"data-sfb-card-surface|data-sfb-section-surface")


def _template_source(name, seen=None):
    """A template's source plus the sources of the partials it statically ``{% include %}``s."""
    seen = seen if seen is not None else set()
    candidates = [APP / "templates" / name, REPO_APPS / "catalog" / "templates" / name]
    path = next((c for c in candidates if c.exists()), None)
    if path is None or name in seen:
        return ""
    seen.add(name)
    source = path.read_text(encoding="utf-8")
    for included in re.findall(r"""{%\s*include\s+["']([^"']+)["']""", source):
        source += _template_source(included, seen)
    return source


def _design_capable():
    return [section_registry.get_definition(key) for key in design_block.design_capable_section_keys()]


def _surface_rules():
    return re.findall(r'([^{}]*\[data-d~="surface"\][^{}]*)\{([^{}]*)\}', _BUILDER_RULES)


class CapabilityRegistryIsTheSourceOfTruthTests(SimpleTestCase):
    def test_design_properties_are_derived_from_registered_capabilities_only(self):
        self.assertFalse(hasattr(design_block, "DESIGN_APPLICABLE"), "the per-section table must not exist any more")
        self.assertFalse(hasattr(design_block, "PROPERTY_DISPLAY_MODES"))
        for definition in _design_capable():
            self.assertEqual(
                design_block.applicable_properties(definition.key),
                design_block.properties_for_capabilities(definition.capabilities), definition.key)
            self.assertTrue(definition.supports_capability("internal_surface") == ("surface_color" in design_block.applicable_properties(definition.key)))

    def test_every_design_capability_name_is_known_and_meaningful(self):
        for definition in _design_capable():
            for name in definition.capabilities:
                if name.startswith("design_"):
                    self.assertIn(name, design_block.DESIGN_CAPABILITIES, f"{definition.key}: {name}")
        for name, (props, _modes) in design_block.DESIGN_CAPABILITIES.items():
            self.assertTrue(props and set(props) <= set(design_block.DESIGN_PROPERTIES), name)

    def test_internal_surface_capability_matches_the_markup_exactly(self):
        """A section registers ``internal_surface`` iff its markup (with its partials) marks an internal surface."""
        offering = set()
        image_caps = {"design_image_fit", "design_image_position", "design_image_ratio", "design_image_zoom"}
        for definition in _design_capable():
            if {c for c in definition.capabilities if c.startswith("design_")} <= image_caps:
                continue  # R4-11: a section that only offers the image controls (hero / banner / slider) takes no part in surface colour
            marked = bool(MARKER.search(_template_source(definition.template_name.replace("storefront_builder/", "storefront_builder/", 1))))
            registered = definition.supports_capability("internal_surface")
            self.assertEqual(registered, marked, f"{definition.key}: capability {registered} vs markup {marked}")
            if registered:
                offering.add(definition.key)
        self.assertGreaterEqual(len(offering), 5)  # the registry, not a list in this test, says which

    def test_surface_control_is_offered_exactly_by_the_capability(self):
        for definition in _design_capable():
            groups = design_block.serialize_registry_for_inspector(definition.key)
            shown = {p["key"] for g in groups for p in g["properties"]}
            self.assertEqual("surface_color" in shown, definition.supports_capability("internal_surface"), definition.key)
            if "surface_color" in shown:
                prop = next(p for g in groups for p in g["properties"] if p["key"] == "surface_color")
                self.assertTrue(prop["hint"] and not prop["box"])

    def test_item_width_is_a_carousel_only_property_for_the_section_that_registers_it_that_way(self):
        modes = {d.key: design_block.display_modes_for_capabilities(d.capabilities).get("item_width") for d in _design_capable()
                 if "item_width" in design_block.applicable_properties(d.key)}
        self.assertEqual(modes["product_section"], ("carousel",))
        self.assertIsNone(modes["brand_carousel"])  # a capability that grants it unrestricted wins

    def test_unknown_design_capability_is_rejected_at_registry_finalisation(self):
        base = dict(section_registry._BASE_SECTION_REGISTRY)
        import dataclasses

        bad = dataclasses.replace(base["faq"], capabilities=frozenset({"design_nonsense"}))
        with self.assertRaises(ValueError):
            section_registry._finalize_registry({"faq": bad})

    def test_the_property_table_per_section_matches_what_shipped_before_the_registry_move(self):
        expected = {
            "surface_panel": 14, "product_section": 28, "category_grid": 26, "brand_carousel": 23,
            "blog_posts": 28, "amazing_offers": 24, "decorative_strip": 4,
            # R4-11: sections that show merchant images now offer the image controls (fit / position / ratio, R4-13 zoom) and nothing else
            "best_sellers": 4, "newest_products": 4, "discounted_products": 4, "collection_tiles": 3,
            "hero_banner": 1, "image_slider": 1, "multi_banner": 1, "image_text": 2,
            # V5 «عکس لینک‌دار»: border / radius / shadow / spacing + the image fit and focal point (no background, no copy)
            "linked_image": 12,
        }
        actual = {d.key: len(design_block.applicable_properties(d.key)) for d in _design_capable()}
        self.assertEqual(actual, expected)


class SurfaceColourNeverPaintsTheCanvasTests(SimpleTestCase):
    def test_no_surface_rule_targets_the_wrapper_bleed_or_band_except_the_surface_mode_declaration(self):
        rules = _surface_rules()
        self.assertTrue(rules)
        for selector, declarations in rules:
            if "--d-surface" not in declarations:
                continue
            for part in (p.strip() for p in selector.split(",")):
                if '[data-d~="surface"]' not in part:
                    continue
                tail = part.split('[data-d~="surface"]', 1)[1].strip()
                if tail == '[data-bg-mode="surface"]':
                    continue  # the Background's own «surface» mode: the canvas IS the surface panel (one meaning)
                self.assertTrue(tail, f"surface colour paints the section wrapper: {part}")
                self.assertNotIn("rsec-bleed", tail)
                self.assertNotIn("product-campaign-band", tail)
        self.assertNotIn(":not(:has(.special-wrap))", BUILDER_CSS)

    def test_internal_surface_rule_targets_semantic_markers_not_class_lists(self):
        selector, rule = next((s, d) for s, d in _surface_rules() if "--d-surface" in d and "data-sfb-card-surface" in s)
        self.assertIn("[data-sfb-card-surface]", selector)
        self.assertIn("[data-sfb-section-surface]", selector)
        for legacy_class in (".pcard", ".brand-tile", ".blog-card", ".blog-panel", ".surface-panel"):
            self.assertNotIn(legacy_class, selector)
        self.assertNotRegex(selector, r"template-\d|stationery|data-template")
        self.assertIn("background:var(--d-surface)!important", rule)  # the palette sheet forces card fills with !important
        self.assertIn("color:var(--d-surface-fg)!important", rule)

    def test_card_inks_follow_the_surfaces_accessible_foreground(self):
        rule = next(d for s, d in _surface_rules() if "--d-surface" in d and "data-sfb-card-surface" in s)
        for token in ("--ssf-fg", "--ssf-muted"):
            self.assertIn(f"{token}:", rule)
        for leaking in ("--theme-text", "--brand-text", "--theme-muted"):  # global tokens are never overridden (chips inside cards keep theirs)
            self.assertNotIn(f"{leaking}:", rule)
        accent = next(d for s, d in _surface_rules() if '[data-d~="surface-brand"]' in s)
        for token in ("--ssf-price", "--ssf-accent", "--ssf-muted"):
            self.assertIn(f"{token}:", accent)
        # the card is its own ink context (no leak from an enclosing marked surface) and the palette sheet consumes the tokens
        reset = next(d for s, d in re.findall(r"([^{}]*)\{([^{}]*)\}", _BUILDER_RULES) if s.strip() == "[data-sfb-card-surface]")
        for token in ("--ssf-fg", "--ssf-muted", "--ssf-price", "--ssf-accent"):
            self.assertIn(f"{token}:", reset)
        for consumer in ("var(--ssf-muted,var(--theme-muted))", "var(--ssf-fg,var(--theme-text))", "var(--ssf-price,var(--theme-price-text"):
            self.assertIn(consumer, THEME_CSS)

    def test_campaign_band_fill_belongs_to_the_background_only(self):
        self.assertNotRegex(BUILDER_CSS, r"\.product-campaign-band\{background:var\(--d-surface\)")
        # the copy panel has its own independent colour contract
        self.assertIn("background-color:var(--cp-bg,", BUILDER_CSS)

    def test_the_legacy_row_painter_respects_an_explicit_background(self):
        """theme_palette.css used to repaint a product section in a legacy row with an !important card fill, hiding any Background."""
        self.assertIn(".rsec-row-item>.rsec:not([data-bg-mode])>.product-section:not(.product-section--spotlight)", THEME_CSS)
        self.assertNotIn(".rsec-row-item>.rsec>.product-section:not(.product-section--spotlight)", THEME_CSS)


class SurfaceInkModeTests(SimpleTestCase):
    def test_brand_inks_stay_on_surfaces_the_theme_already_ensures_and_re_ink_elsewhere(self):
        keeps = design_block.surface_keeps_brand_inks
        self.assertTrue(keeps("#FFFFFF"))
        self.assertTrue(keeps("#F4F5F9"))
        self.assertTrue(keeps("token:surface"))
        self.assertTrue(keeps("token:background"))
        self.assertTrue(keeps(""))
        self.assertFalse(keeps("#101828"))
        self.assertFalse(keeps("#0057FF"))
        self.assertFalse(keeps("token:tone-3"))
        self.assertFalse(keeps("token:primary"))

    def test_render_attributes_flag_the_ink_mode_and_the_foreground_is_wcag_aa(self):
        light = design_block.render_attributes({"surface_color": "#FFFFFF"})
        dark = design_block.render_attributes({"surface_color": "#101828"})
        self.assertIn("surface-brand", light["flags"].split())
        self.assertNotIn("surface-brand", dark["flags"].split())
        for hex_surface in ("#FFFFFF", "#101828", "#0057FF", "#F59E0B", "#7C3AED", "#14532D", "#FDE68A"):
            fg = re.search(r"--d-surface-fg:(#[0-9A-Fa-f]{6})", design_block.render_attributes({"surface_color": hex_surface})["style"]).group(1)
            self.assertGreaterEqual(contrast_ratio(fg, hex_surface), 4.5, (hex_surface, fg))


class LegacyDesignSettingsStayEditableTests(SimpleTestCase):
    """A capability withdrawn by an engine change must not strand earlier merchant settings (generic, registry-driven)."""

    def _legacy_cases(self):
        """(definition, a design property the section does NOT grant, a valid value for it)."""
        cases = []
        for definition in _design_capable():
            granted = set(design_block.applicable_properties(definition.key))
            for prop in design_block.DESIGN_PROPERTIES.values():
                if prop.key in granted:
                    continue
                value = ("#FFFFFF" if prop.kind == "color" else max(prop.min_value, 3) if prop.kind == "int"
                         else next(c for c, _ in prop.choices if c))
                cases.append((definition, prop.key, value))
        return cases

    def test_every_withdrawn_property_of_every_section_keeps_unrelated_edits_working_and_is_preserved(self):
        cases = self._legacy_cases()
        self.assertGreater(len(cases), 20)
        for definition, key, value in cases:
            current = definition.default_settings()
            current["design"] = {key: value}
            out = clean_section_schema_patch(definition, {"title": "عنوان تازه"}, current) if "title" in {
                f.key for f in definition.settings_schema.fields} else clean_section_schema_patch(
                definition, {"design": {}}, current)
            self.assertEqual(out["design"].get(key), value, f"{definition.key}.{key}: dormant value lost")

    def test_dormant_values_survive_a_design_block_edit_with_the_hidden_control_omitted_and_a_background_edit(self):
        definition = section_registry.get_definition("category_grid")
        current = definition.default_settings()
        current["design"] = {"surface_color": "#FFFFFF", "radius": 6, "text_color": "#112233"}
        edited = clean_section_schema_patch(definition, {"design": {"radius": 9, "text_color": "#112233"}}, current)
        self.assertEqual(edited["design"], {"radius": 9, "text_color": "#112233", "surface_color": "#FFFFFF"})
        bg = {"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}
        edited = clean_section_schema_patch(definition, {"background": bg}, current)
        self.assertEqual(edited["design"], {"surface_color": "#FFFFFF", "radius": 6, "text_color": "#112233"})
        self.assertEqual(edited["background"]["color"].upper(), "#0057FF")

    def test_newly_submitted_or_changed_unsupported_properties_are_still_rejected(self):
        definition = section_registry.get_definition("category_grid")
        current = definition.default_settings()
        with self.assertRaises(ValueError):
            clean_section_schema_patch(definition, {"design": {"surface_color": "#000000"}}, current)
        current["design"] = {"surface_color": "#FFFFFF"}
        with self.assertRaises(ValueError):
            clean_section_schema_patch(definition, {"design": {"surface_color": "#000000"}}, current)  # changed value
        with self.assertRaises(ValueError):
            clean_section_schema_patch(definition, {"design": {"nope": 1}}, current)  # never a design property
        # an idempotent re-send of the stored value is accepted
        self.assertEqual(clean_section_schema_patch(definition, {"design": {"surface_color": "#FFFFFF"}}, current)["design"],
                         {"surface_color": "#FFFFFF"})

    def test_dormant_keys_render_inert(self):
        applicable = design_block.applicable_properties("category_grid")
        attrs = design_block.render_attributes({"surface_color": "#FFFFFF", "radius": 6}, applicable)
        self.assertNotIn("surface", attrs["flags"].split())
        self.assertNotIn("--d-surface", attrs["style"])
        self.assertIn("--d-radius:6px", attrs["style"])


class InspectorExplainsTheDifferenceTests(R4MutationApiTestCase):
    def setUp(self):
        super().setUp()
        self.section.delete()
        self.products = sss.add_section(draft=self.draft, section_key="product_section", page_type="home")
        self.grid = sss.add_section(draft=self.draft, section_key="category_grid", page_type="home")

    def _inspector(self, section):
        return self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))

    def _post(self, section, patch, expect=200):
        self.draft.refresh_from_db()
        response = self._post_json({"base_revision": self.draft.edit_revision, "fragment": True, "mutation": {
            "type": "section.update_settings", "section_id": section.pk, "patch": patch}})
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_background_and_surface_controls_carry_distinct_persian_explanations(self):
        response = self._inspector(self.products)
        self.assertContains(response, BACKGROUND_HINT)
        self.assertContains(response, SURFACE_HINT)
        self.assertContains(response, 'data-r4-design-prop="surface_color"')

    def test_a_section_without_the_capability_does_not_offer_the_surface_control(self):
        response = self._inspector(self.grid)
        self.assertNotContains(response, 'data-r4-design-prop="surface_color"')
        self.assertContains(response, BACKGROUND_HINT)

    def test_surface_colour_and_background_are_stored_independently(self):
        self.assertTrue(self._post(self.products, {"design": {"surface_color": "#FFFFFF"}})["ok"])
        body = self._post(self.products, {"background": {"mode": "color", "color": "#0057FF", "media_asset_id": None,
                                                         "pattern_slug": "", "palette_role": ""}})
        self.products.refresh_from_db()
        self.assertEqual(self.products.settings["background"]["color"].upper(), "#0057FF")
        self.assertEqual(self.products.settings["design"]["surface_color"].upper(), "#FFFFFF")
        html = body["fragment"]["html"]
        wrapper = html[html.index("<div"):html.index(">", html.index("<div")) + 1]
        self.assertRegex(wrapper, r"(?i)background-color:\s*#0057ff")
        self.assertRegex(wrapper, r'data-d="[^"]*surface')

    def test_legacy_category_grid_with_a_stored_surface_colour_stays_editable_through_the_real_mutation_pipeline(self):
        self.grid.settings = {**self.grid.settings, "design": {"surface_color": "#FFFFFF", "radius": 8}}
        self.grid.save()
        for patch in ({"title": "دسته‌ها"},
                      {"background": {"mode": "color", "color": "#0057FF", "media_asset_id": None, "pattern_slug": "", "palette_role": ""}},
                      {"design": {"radius": 12}}):
            self.assertTrue(self._post(self.grid, patch)["ok"], patch)
        self.grid.refresh_from_db()
        self.assertEqual(self.grid.settings["design"]["surface_color"], "#FFFFFF")  # dormant value preserved
        self.assertEqual(self.grid.settings["design"]["radius"], 12)
        self.assertEqual(self.grid.settings["background"]["color"].upper(), "#0057FF")
        self._post(self.grid, {"design": {"surface_color": "#000000"}}, expect=400)  # a NEW unsupported value is refused
        self.assertNotContains(self._inspector(self.grid), 'data-r4-design-prop="surface_color"')
        # inert in the rendered wrapper
        html = self._post(self.grid, {"title": "دسته‌ها 2"})["fragment"]["html"]
        wrapper = html[html.index("<div"):html.index(">", html.index("<div")) + 1]
        self.assertNotRegex(wrapper, r'data-d="[^"]*surface')
