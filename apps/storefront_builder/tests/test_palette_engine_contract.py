"""The global palette engine's colour-resolution contract (``appearance_registry`` module docstring), proven without a browser.

Precedence, lowest → highest: engine defaults · Ready Template baseline · selected palette · merchant global overrides ·
explicit section/component settings. These tests pin each layer, the deterministic hand-offs between them, per-property reset,
Store isolation, Draft/Published isolation and the accessible status-text tokens for EVERY registered palette.
"""

import copy
import json

from django.test import SimpleTestCase

from apps.storefront_builder import appearance_registry as ar
from apps.storefront_builder import global_region_registry as grr
from apps.storefront_builder.accessible_colors import accessible_pairs, build_accessible_theme, failing_pairs
from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import layout_service as svc, preset_service
from apps.storefront_builder.services import r4_mutation_service
from apps.stores.models import Store

from .test_r4_mutation_api import R4MutationApiTestCase

DARK = "theme-midnight-electric"      # full-site theme with explicit region roles
LIGHT = "uupm-trust-blue"
COLORFUL = "marketplace-spectrum"


def _cfg(slug=DARK, colors=None, roles=None):
    return {"palette_slug": slug, "color_overrides": dict(colors or {}), "theme_overrides": dict(roles or {})}


class ResolutionContractTests(SimpleTestCase):
    def test_the_registry_holds_the_library_and_every_palette_resolves_all_roles(self):
        palettes = ar.list_palettes()
        self.assertGreaterEqual(len(palettes), 64)
        for palette in palettes:
            with self.subTest(palette=palette.slug):
                cfg = _cfg(palette.slug)
                colors, roles, tones = ar.resolve_colors(cfg), ar.resolve_theme_roles(cfg), ar.resolve_section_tones(cfg)
                self.assertEqual(set(colors), {"primary", "secondary", "accent", "background", "surface", "text", "muted", "border"})
                self.assertEqual(set(roles), set(ar.THEME_ROLE_KEYS))
                self.assertEqual(len(tones), 5)

    def test_layer_3_palette_beats_engine_defaults_and_layer_4_override_beats_palette(self):
        self.assertEqual(ar.resolve_colors({"palette_slug": None})["surface"], ar.DEFAULT_COLORS["surface"])
        self.assertEqual(ar.resolve_colors(_cfg(DARK))["surface"], ar.get_palette(DARK).colors["surface"])
        self.assertEqual(ar.resolve_colors(_cfg(DARK, {"surface": "#123456"}))["surface"], "#123456")
        self.assertEqual(ar.resolve_colors(_cfg(DARK, {"surface": "#123456"}))["text"], ar.get_palette(DARK).colors["text"])

    def test_a_base_colour_override_reaches_the_roles_that_follow_it_and_not_the_ones_the_palette_made_different(self):
        palette = ar.get_palette(DARK)
        before = ar.resolve_theme_roles(_cfg(DARK))
        after = ar.resolve_theme_roles(_cfg(DARK, {"surface": "#FF0000"}))
        # card_bg IS the palette's surface in this theme → it follows the merchant's surface
        self.assertEqual(palette.theme_roles["card_bg"], palette.colors["surface"])
        self.assertEqual(after["card_bg"], "#FF0000")
        # header_bg was deliberately defined by the palette as something else → unchanged until the merchant sets it
        self.assertNotEqual(palette.theme_roles["header_bg"], palette.colors["surface"])
        self.assertEqual(after["header_bg"], before["header_bg"])
        self.assertEqual(after["footer_bg"], before["footer_bg"])

    def test_layer_4_region_override_beats_everything_below_it(self):
        roles = ar.resolve_theme_roles(_cfg(DARK, {"surface": "#FF0000"}, {"card_bg": "#00FF00", "header_bg": "#0000FF"}))
        self.assertEqual(roles["card_bg"], "#00FF00")
        self.assertEqual(roles["header_bg"], "#0000FF")

    def test_derived_roles_follow_final_colours_for_palettes_without_explicit_roles(self):
        plain = next(p for p in ar.list_palettes() if not p.theme_roles)
        roles = ar.resolve_theme_roles(_cfg(plain.slug, {"text": "#101010", "surface": "#FAFAFA", "accent": "#CC2200"}))
        self.assertEqual(roles["header_text"], "#101010")
        self.assertEqual(roles["header_bg"], "#FAFAFA")
        self.assertEqual(roles["footer_bg"], "#101010")
        self.assertEqual(roles["price"], "#CC2200")

    def test_curated_tones_survive_overrides_that_do_not_touch_primary_secondary_accent(self):
        curated = next(p for p in ar.list_palettes() if p.section_tones)
        self.assertEqual(ar.resolve_section_tones(_cfg(curated.slug, {"surface": "#FFFFFF", "text": "#000000"})),
                         curated.section_tones)
        self.assertNotEqual(ar.resolve_section_tones(_cfg(curated.slug, {"primary": "#123456"})), curated.section_tones)

    def test_provenance_marks_inherited_versus_overridden_and_gives_the_reset_value(self):
        prov = ar.resolve_color_provenance({
            **_cfg(DARK, {"surface": "#FF0000", "text": ar.get_palette(DARK).colors["text"]}, {"price": "#00FF00"}),
            "color_overrides_customized": True,  # what a real merchant edit stores
        })
        surface = prov["colors"]["surface"]
        self.assertEqual((surface["source"], surface["value"], surface["default"]),
                         ("override", "#FF0000", ar.get_palette(DARK).colors["surface"]))
        # a STORED override is an explicit merchant value even when it now equals the palette's (it stays resettable)
        self.assertEqual(prov["colors"]["text"]["source"], "override")
        self.assertEqual(prov["colors"]["primary"]["source"], "palette")
        self.assertEqual(prov["roles"]["price"]["source"], "override")
        self.assertEqual(prov["roles"]["price"]["default"], ar.get_palette(DARK).theme_roles["price"])
        self.assertEqual(prov["roles"]["card_bg"]["source"], "derived")  # follows the overridden surface
        self.assertEqual(prov["roles"]["header_bg"]["source"], "palette")
        self.assertEqual(ar.resolve_color_provenance({"palette_slug": None})["colors"]["primary"]["source"], "default")
        # legacy Store-colour mirror (never customised, not from a template) is labelled as such, not as the merchant's
        legacy = ar.resolve_color_provenance({**_cfg(DARK, {"surface": "#FF0000"}), "color_overrides_customized": False})
        self.assertEqual((legacy["colors"]["surface"]["source"], legacy["colors"]["surface"]["stored"]), ("carry_over", True))

    def test_a_custom_palette_never_mutates_the_shared_registry(self):
        snapshot = copy.deepcopy({slug: (p.colors, p.theme_roles, p.section_tones) for slug, p in ar.PALETTE_REGISTRY.items()})
        for cfg in (_cfg(DARK, {"surface": "#FF0000", "primary": "#00FF00"}, {"card_bg": "#0000FF"}), _cfg(LIGHT, {"text": "#111111"})):
            ar.resolve_colors(cfg), ar.resolve_theme_roles(cfg), ar.resolve_section_tones(cfg), ar.resolve_color_provenance(cfg)
        self.assertEqual(snapshot, {slug: (p.colors, p.theme_roles, p.section_tones) for slug, p in ar.PALETTE_REGISTRY.items()})


class AccessibleTokensForEveryPaletteTests(SimpleTestCase):
    def test_every_palette_meets_the_contrast_contract_including_status_text(self):
        for palette in ar.list_palettes():
            with self.subTest(palette=palette.slug):
                cfg = _cfg(palette.slug)
                colors, roles, tones = ar.resolve_colors(cfg), ar.resolve_theme_roles(cfg), ar.resolve_section_tones(cfg)
                theme = build_accessible_theme(colors, roles, tones=tones)
                for key in ("success_text", "warning_text", "danger_text"):
                    self.assertIn(key, theme)
                failures = failing_pairs(colors, roles, theme, tones)
                status = [f for f in failures if any(k in f[0] for k in ("success_text", "warning_text", "danger_text"))]
                self.assertEqual(status, [], status)
        names = {name for name, *_ in accessible_pairs(ar.resolve_colors(_cfg(DARK)), ar.resolve_theme_roles(_cfg(DARK)))}
        self.assertTrue(any(n.startswith("success_text on") for n in names))

    def test_status_text_with_a_custom_global_override_still_meets_contrast(self):
        cfg = _cfg(DARK, {"surface": "#FFFFFF", "background": "#FFFFFF"})
        colors, roles = ar.resolve_colors(cfg), ar.resolve_theme_roles(cfg)
        self.assertEqual(failing_pairs(colors, roles), [])


class NavRoleApplicabilityTests(SimpleTestCase):
    """Applicability comes from the capabilities registered on the variant definitions themselves (no parallel allowlist)."""

    NAV_ROLES = tuple(grr.ROLE_REQUIRES_CAPABILITY)

    def test_the_studio_offers_a_region_role_only_where_a_selected_variant_declares_the_capability(self):
        roles = ar.THEME_ROLE_KEYS
        plain_footer = {"footer_variant": "stationery_dark"}
        for variant in grr.list_global_variants(grr.GLOBAL_HEADER_REGION):
            offered = grr.applicable_theme_roles({"header_variant": variant.key}, plain_footer, roles)
            self.assertTrue(set(roles) - set(self.NAV_ROLES) <= set(offered), variant.key)
            self.assertEqual(set(self.NAV_ROLES) <= set(offered), grr.NAV_SURFACE in variant.capabilities, variant.key)
        # a footer that draws a navigation strip makes the roles applicable even for a header that does not
        self.assertIn("nav_bg", grr.applicable_theme_roles({"header_variant": "stationery_search"},
                                                           {"footer_variant": "kawaii_minimal"}, roles))
        self.assertNotIn("nav_bg", grr.applicable_theme_roles({"header_variant": "stationery_search"}, plain_footer, roles))

    def test_the_capability_flows_into_the_one_component_registry(self):
        from apps.storefront_builder.storefront_appearance.registry import get_component

        self.assertIn(grr.NAV_SURFACE, get_component("header.kawaii_center.v1").capabilities)
        self.assertNotIn(grr.NAV_SURFACE, get_component("header.stationery_search.v1").capabilities)
        self.assertIn(grr.NAV_SURFACE, get_component("footer.kawaii_minimal.v1").capabilities)

    def test_no_renderer_path_allowlist_exists(self):
        self.assertFalse(hasattr(grr, "NAV_ROLE_RENDERERS"))


class PaletteMutationPersistenceTests(R4MutationApiTestCase):
    """Palette and colour edits go through the one R4 mutation authority and the Draft/Publish lifecycle."""

    def _update(self, patch):
        revision = self.draft.edit_revision
        response = self._post_json({"base_revision": revision, "mutation": {"type": "appearance.update", "patch": patch}})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.draft.refresh_from_db()
        return self.draft.appearance_config

    def test_palette_selection_and_custom_colours_persist_in_the_draft_only(self):
        published = svc.publish(self.store, user=self.staff)
        self.draft = svc.get_or_create_draft(self.store, user=self.staff)
        published_before = json.dumps(published.appearance_config, sort_keys=True)
        fingerprint = published.content_fingerprint

        config = self._update({"palette_slug": DARK})
        self.assertEqual(config["palette_slug"], DARK)
        config = self._update({"color_overrides": {"surface": "#FF0000", "primary": "#00AA55"}})
        self.assertEqual(config["color_overrides"], {"surface": "#FF0000", "primary": "#00AA55"})
        self.assertTrue(config["color_overrides_customized"])
        config = self._update({"theme_overrides": {"price": "#123456"}})
        self.assertEqual(config["theme_overrides"], {"price": "#123456"})
        self.assertEqual(config["color_overrides"], {"surface": "#FF0000", "primary": "#00AA55"}, "partial patches merge")

        self.draft.refresh_from_db()
        reloaded = StorefrontLayoutVersion.objects.get(pk=self.draft.pk).appearance_config
        self.assertEqual(reloaded["palette_slug"], DARK)
        published.refresh_from_db()
        self.assertEqual(json.dumps(published.appearance_config, sort_keys=True), published_before,
                         "Draft edits never reach Published before an explicit publish")
        self.assertEqual(published.content_fingerprint, published.compute_fingerprint())
        self.assertEqual(published.content_fingerprint, fingerprint)

    def test_null_resets_exactly_one_property_to_the_palette_value(self):
        self._update({"palette_slug": DARK})
        self._update({"color_overrides": {"surface": "#FF0000", "primary": "#00AA55"}, "theme_overrides": {"price": "#123456"}})
        config = self._update({"color_overrides": {"surface": None}})
        self.assertEqual(config["color_overrides"], {"primary": "#00AA55"})
        self.assertEqual(config["theme_overrides"], {"price": "#123456"})
        self.assertTrue(config["color_overrides_customized"])
        config = self._update({"color_overrides": {"primary": None}, "theme_overrides": {"price": None}})
        self.assertEqual((config["color_overrides"], config["theme_overrides"]), ({}, {}))
        self.assertFalse(config["color_overrides_customized"])
        self.assertEqual(ar.resolve_colors(config)["surface"], ar.get_palette(DARK).colors["surface"])

    def test_posting_the_palette_value_is_also_not_an_override(self):
        self._update({"palette_slug": DARK})
        config = self._update({"color_overrides": {"surface": ar.get_palette(DARK).colors["surface"]}})
        self.assertEqual(config["color_overrides"], {})

    def _section_with_local_overrides(self):
        return StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=5,
            settings={"title": "محلی", "background": {"mode": "color", "color": "#0057FF"},
                      "design": {"surface_color": "#FFE600"}},
        )

    def test_switching_palette_keeps_explicit_global_and_region_overrides_and_section_settings(self):
        self._update({"palette_slug": DARK})
        self._update({"color_overrides": {"surface": "#FF0000", "primary": "#00AA55"}, "theme_overrides": {"card_bg": "#00FF00"}})
        section = self._section_with_local_overrides()
        before = json.dumps(StorefrontSection.objects.get(pk=section.pk).settings, sort_keys=True)

        config = self._update({"palette_slug": LIGHT})

        self.assertEqual(config["palette_slug"], LIGHT)
        self.assertEqual(config["color_overrides"], {"surface": "#FF0000", "primary": "#00AA55"})
        self.assertEqual(config["theme_overrides"], {"card_bg": "#00FF00"})
        self.assertTrue(config["color_overrides_customized"])
        self.assertEqual(json.dumps(StorefrontSection.objects.get(pk=section.pk).settings, sort_keys=True), before)
        # inherited colours DID change (they follow the new palette); explicit ones did not
        resolved = ar.resolve_colors(config)
        self.assertEqual(resolved["text"], ar.get_palette(LIGHT).colors["text"])
        self.assertEqual(resolved["surface"], "#FF0000")
        provenance = ar.resolve_color_provenance(config)
        self.assertEqual(provenance["colors"]["text"]["source"], "palette")
        self.assertEqual(provenance["colors"]["surface"]["source"], "override")
        self.assertEqual(provenance["colors"]["surface"]["default"], ar.get_palette(LIGHT).colors["surface"])

    def test_one_preserved_override_can_still_be_reset_to_the_new_palette(self):
        self._update({"palette_slug": DARK})
        self._update({"color_overrides": {"surface": "#FF0000", "primary": "#00AA55"}})
        self._update({"palette_slug": LIGHT})
        config = self._update({"color_overrides": {"surface": None}})
        self.assertEqual(config["color_overrides"], {"primary": "#00AA55"})
        self.assertEqual(ar.resolve_colors(config)["surface"], ar.get_palette(LIGHT).colors["surface"])

    def test_a_palette_switch_drops_only_colours_that_were_never_a_merchant_choice(self):
        """Bootstrap / template carry-over (``color_overrides_customized`` False) must not defeat the palette just chosen."""
        self.draft.appearance_config = {
            **self.draft.effective_appearance_config(), "palette_slug": DARK,
            "color_overrides": {"surface": "#ABCDEF"}, "color_overrides_customized": False,
        }
        self.draft.save(update_fields=["appearance_config"])
        config = self._update({"palette_slug": LIGHT})
        self.assertEqual(config["color_overrides"], {})

    def test_clearing_every_global_override_is_an_explicit_action_and_leaves_sections_alone(self):
        self._update({"palette_slug": DARK})
        self._update({"color_overrides": {"surface": "#FF0000"}, "theme_overrides": {"price": "#123456"}})
        section = self._section_with_local_overrides()
        before = json.dumps(StorefrontSection.objects.get(pk=section.pk).settings, sort_keys=True)
        revision = self.draft.edit_revision
        history = self._history_count()

        config = self._update({"clear_global_color_overrides": True})

        self.assertEqual((config["color_overrides"], config["theme_overrides"], config["color_overrides_customized"]),
                         ({}, {}, False))
        self.assertEqual(config["palette_slug"], DARK, "the palette selection is not touched")
        self.assertEqual(json.dumps(StorefrontSection.objects.get(pk=section.pk).settings, sort_keys=True), before)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, revision + 1)
        self.assertEqual(self._history_count(), history + 1, "it is one undoable, recorded step")
        # only a literal True clears; nothing else (e.g. a palette switch) is allowed to
        self._update({"color_overrides": {"surface": "#FF0000"}})
        self.assertEqual(self._update({"clear_global_color_overrides": False})["color_overrides"], {"surface": "#FF0000"})
        self.assertEqual(self._update({"palette_slug": LIGHT})["color_overrides"], {"surface": "#FF0000"})

    def test_invalid_colours_are_rejected_and_change_nothing(self):
        self._update({"palette_slug": DARK})
        revision = self.draft.edit_revision
        for bad in ("red", "#12", "#GGGGGG", "url(x)"):
            response = self._post_json({"base_revision": revision, "mutation": {
                "type": "appearance.update", "patch": {"color_overrides": {"surface": bad}}}})
            self.assertEqual(response.status_code, 400, bad)
            self.draft.refresh_from_db()
            self.assertEqual(self.draft.edit_revision, revision)
            self.assertEqual(self.draft.appearance_config["color_overrides"], {})

    def test_another_stores_draft_is_never_changed_by_this_stores_palette_edits(self):
        other = Store.objects.create(name="فروشگاه دیگر", slug="sfb-palette-other", admin_subdomain="sfb-palette-other",
                                     status=Store.Status.ACTIVE)
        other_draft = svc.get_or_create_draft(other)
        other_before = json.dumps(other_draft.appearance_config, sort_keys=True)
        self._update({"palette_slug": DARK})
        self._update({"color_overrides": {"surface": "#FF0000"}})
        other_draft.refresh_from_db()
        self.assertEqual(json.dumps(other_draft.appearance_config, sort_keys=True), other_before)
        self.assertNotEqual(other_draft.appearance_config.get("palette_slug"), DARK)

    def test_template_apply_installs_a_palette_that_a_later_selection_replaces(self):
        from apps.storefront_builder import layout_preset_registry as lpr

        preset = lpr.get_layout_preset("stationery_spectrum")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["palette_slug"], preset.default_palette_slug)
        config = self._update({"palette_slug": DARK})
        self.assertEqual(config["palette_slug"], DARK)
        self.assertEqual(self.draft.template_provenance["template"]["key"], "stationery_spectrum")


class MixedOriginOverrideTests(R4MutationApiTestCase):
    """A Ready Template installs SEVERAL initial colour overrides; the merchant changes only some of them. Each stored override must
    keep its own origin (template-initialised vs merchant-customised) across a palette switch, in the Studio's per-colour source and
    on reset — with the template baseline snapshot untouched. (``color_overrides_customized`` is one boolean; the per-property truth
    comes from comparing each stored value with the baseline snapshot the template recorded.)"""

    TEMPLATE_COLORS = {"primary": "#111111", "accent": "#222222", "border": "#333333"}
    TEMPLATE_ROLES = {"header_bg": "#444444", "footer_bg": "#555555", "price": "#666666"}

    def setUp(self):
        super().setUp()
        import dataclasses

        from apps.storefront_builder import layout_preset_registry as lpr

        base = lpr.get_layout_preset("stationery_spectrum")
        self.preset = dataclasses.replace(
            base, default_palette_slug=DARK,
            appearance={**base.appearance, "color_overrides": dict(self.TEMPLATE_COLORS),
                        "theme_overrides": dict(self.TEMPLATE_ROLES)},
        )
        preset_service.apply_preset(self.draft, self.preset)
        self.draft.refresh_from_db()
        self.baseline = json.loads(json.dumps(self.draft.template_baseline_snapshot))

    def _update(self, patch):
        response = self._post_json({"base_revision": self.draft.edit_revision,
                                    "mutation": {"type": "appearance.update", "patch": patch}})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.draft.refresh_from_db()
        return self.draft.appearance_config

    def _sources(self):
        provenance = ar.resolve_color_provenance(self.draft.effective_appearance_config(), self.draft.template_baseline_snapshot)
        return ({k: v["source"] for k, v in provenance["colors"].items()},
                {k: v["source"] for k, v in provenance["roles"].items()})

    def test_the_template_installed_several_initial_overrides_and_recorded_them_in_the_baseline(self):
        config = self.draft.appearance_config
        self.assertEqual(config["color_overrides"], self.TEMPLATE_COLORS)
        self.assertEqual(config["theme_overrides"], self.TEMPLATE_ROLES)
        self.assertEqual(self.baseline["appearance"]["color_overrides"], self.TEMPLATE_COLORS)
        self.assertEqual(self.baseline["appearance"]["theme_overrides"], self.TEMPLATE_ROLES)
        colors, roles = self._sources()
        self.assertEqual({k: colors[k] for k in self.TEMPLATE_COLORS}, {k: "template" for k in self.TEMPLATE_COLORS})
        self.assertEqual({k: roles[k] for k in self.TEMPLATE_ROLES}, {k: "template" for k in self.TEMPLATE_ROLES})

    def test_editing_one_colour_marks_only_that_colour_as_the_merchants(self):
        self._update({"color_overrides": {"accent": "#AA0000"}, "theme_overrides": {"header_bg": "#BB0000"}})
        colors, roles = self._sources()
        self.assertEqual((colors["accent"], colors["primary"], colors["border"]), ("override", "template", "template"))
        self.assertEqual((roles["header_bg"], roles["footer_bg"], roles["price"]), ("override", "template", "template"))

    def test_a_palette_switch_keeps_only_the_individually_customised_colours(self):
        self._update({"color_overrides": {"accent": "#AA0000"}, "theme_overrides": {"header_bg": "#BB0000"}})
        config = self._update({"palette_slug": LIGHT})
        self.assertEqual(config["palette_slug"], LIGHT)
        self.assertEqual(config["color_overrides"], {"accent": "#AA0000"},
                         "unmodified template colours follow the new palette; the customised one survives")
        self.assertEqual(config["theme_overrides"], {"header_bg": "#BB0000"}, "same rule for region colours")
        resolved = ar.resolve_colors(config)
        self.assertEqual(resolved["primary"], ar.get_palette(LIGHT).colors["primary"])
        self.assertEqual(resolved["border"], ar.get_palette(LIGHT).colors["border"])
        self.assertEqual(resolved["accent"], "#AA0000")
        colors, roles = self._sources()
        self.assertEqual((colors["accent"], colors["primary"], colors["border"]), ("override", "palette", "palette"))
        self.assertEqual((roles["header_bg"], roles["footer_bg"]), ("override", "palette"))
        self.assertTrue(config["color_overrides_customized"])

    def test_untouched_template_colours_all_follow_a_palette_switch(self):
        config = self._update({"palette_slug": LIGHT})
        self.assertEqual((config["color_overrides"], config["theme_overrides"]), ({}, {}))

    def test_resetting_one_colour_affects_no_other_colour(self):
        self._update({"color_overrides": {"accent": "#AA0000", "primary": "#0A0A0A"}, "theme_overrides": {"header_bg": "#BB0000"}})
        config = self._update({"color_overrides": {"accent": None}})
        self.assertEqual(config["color_overrides"], {"primary": "#0A0A0A", "border": self.TEMPLATE_COLORS["border"]})
        self.assertEqual(config["theme_overrides"], {**self.TEMPLATE_ROLES, "header_bg": "#BB0000"})
        config = self._update({"theme_overrides": {"header_bg": None}})
        self.assertEqual(config["theme_overrides"], {"footer_bg": "#555555", "price": "#666666"})
        self.assertEqual(config["color_overrides"], {"primary": "#0A0A0A", "border": self.TEMPLATE_COLORS["border"]})

    def test_the_template_baseline_snapshot_is_never_touched_by_any_of_it(self):
        self._update({"color_overrides": {"accent": "#AA0000"}, "theme_overrides": {"header_bg": "#BB0000"}})
        self._update({"palette_slug": LIGHT})
        self._update({"color_overrides": {"accent": None}})
        self._update({"clear_global_color_overrides": True})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.template_baseline_snapshot, self.baseline)

    def test_template_baseline_reset_still_restores_the_installed_overrides(self):
        self._update({"color_overrides": {"accent": "#AA0000"}})
        self._update({"palette_slug": LIGHT})
        response = self._post_json({"base_revision": self.draft.edit_revision, "mutation": {
            "type": "appearance.reset_setting_to_baseline", "key": "color_overrides"}})
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config["color_overrides"], self.TEMPLATE_COLORS)
