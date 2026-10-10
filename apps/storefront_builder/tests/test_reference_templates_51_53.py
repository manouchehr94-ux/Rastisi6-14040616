"""Reference-fidelity Ready Templates 51-53.

Focused contracts for the three templates added on top of the token-built
A8 catalog: registry identity, complete resolvable Store Appearance DNA, the
narrowly-scoped variants they rely on, and the real merchant lifecycle
(gallery card -> select/apply on a Draft -> switch -> publish -> public Home).
"""

from __future__ import annotations

import dataclasses

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import get_template
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import appearance_registry, global_region_registry
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry
from apps.storefront_builder.a8_ready_templates import A8_READY_TEMPLATES
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import ready_template_card_service, store_template_service
from apps.storefront_builder.services import template_preview_service
from apps.storefront_builder.storefront_appearance.families import COMPONENT_FAMILIES
from apps.storefront_builder.storefront_appearance.registry import get_component
from apps.stores.models import Store, StoreDomain

User = get_user_model()

REFERENCE_TEMPLATES = {
    # 51 / 52 / 53 — key -> (label, header, footer, palette)
    "stationery_spectrum": ("تحریر رنگی", "stationery_search", "stationery_dark", "spectrum-stationery"),
    "magenta_beauty_retail": ("زیبایی ارغوانی", "beauty_search_nav", "beauty_retail_columns", "orchid-retail"),
    "pastel_kawaii_stationery": ("کاغذ پاستلی", "kawaii_center", "kawaii_minimal", "pastel-lilac"),
}
HOST = "sfb-ref-51-53.example.com"


def _home_section_keys(preset):
    return [entry.section_key for entry in preset.pages["home"]]


class ReferenceTemplateRegistryTests(SimpleTestCase):
    def test_three_new_official_templates_extend_the_fifty_key_catalog(self):
        latest = {preset.key: preset for preset in lpr.list_ready_templates()}
        self.assertEqual(len(A8_READY_TEMPLATES), 50)
        self.assertEqual(len(latest), 53)
        a8_keys = {preset.key for preset in A8_READY_TEMPLATES}
        for key, (label, *_rest) in REFERENCE_TEMPLATES.items():
            with self.subTest(key=key):
                self.assertNotIn(key, a8_keys)
                preset = latest[key]
                self.assertTrue(preset.is_ready_template)
                self.assertEqual(preset.version, "1")
                self.assertEqual(preset.label_fa, label)
                self.assertIs(lpr.get_layout_preset_version(key, "1"), preset)

    def test_recipes_carry_the_reference_identity(self):
        for key, (_label, header, footer, palette) in REFERENCE_TEMPLATES.items():
            with self.subTest(key=key):
                preset = lpr.get_layout_preset(key)
                self.assertEqual(preset.header["header_variant"], header)
                self.assertEqual(preset.footer["footer_variant"], footer)
                self.assertEqual(preset.default_palette_slug, palette)
                self.assertIsNotNone(appearance_registry.get_palette(palette))
                self.assertEqual(
                    preset.store_appearance["selections"]["header"], f"header.{header}.v1",
                )
                self.assertEqual(
                    preset.store_appearance["selections"]["footer"], f"footer.{footer}.v1",
                )
                # Section-local card / product-view / hero variants must stay in
                # force: a non-default manifest selection would override them
                # on every section at render time.
                for family in ("card", "product_view", "hero"):
                    self.assertEqual(
                        preset.store_appearance["selections"][family], f"{family}.legacy_default.v1",
                    )

    def test_every_recipe_has_complete_resolvable_dna(self):
        for key in REFERENCE_TEMPLATES:
            with self.subTest(key=key):
                selections = lpr.get_layout_preset(key).store_appearance["selections"]
                self.assertEqual(set(selections), set(COMPONENT_FAMILIES))
                for family_key, component_key in selections.items():
                    component = get_component(component_key)
                    self.assertIsNotNone(component, component_key)
                    self.assertEqual(component.family_key, family_key)

    def test_every_home_row_has_a_unique_explicit_semantic_role(self):
        for key in REFERENCE_TEMPLATES:
            with self.subTest(key=key):
                roles = [entry.semantic_slot_key for entry in lpr.get_layout_preset(key).pages["home"]]
                self.assertTrue(all(roles))
                self.assertEqual(len(roles), len(set(roles)))

    def test_new_templates_are_structurally_distinct_from_the_whole_catalog(self):
        def signature(preset):
            return (
                preset.header["header_variant"], preset.footer["footer_variant"],
                tuple(_home_section_keys(preset)),
                tuple(sorted((preset.store_appearance["selections"]).items())),
            )

        signatures = {}
        for preset in lpr.list_ready_templates():
            signatures.setdefault(signature(preset), []).append(preset.key)
        for key in REFERENCE_TEMPLATES:
            self.assertEqual(signatures[signature(lpr.get_layout_preset(key))], [key])

    def test_recipe_composition_matches_the_reference_section_maps(self):
        spectrum = lpr.get_layout_preset("stationery_spectrum")
        keys = _home_section_keys(spectrum)
        self.assertEqual(keys[0], "multi_banner")
        self.assertEqual(keys.count("hero_banner"), 1)
        self.assertIn("amazing_offers", keys)
        # five coloured bands in palette tone order 1..5
        roles = [
            entry.settings["background"]["palette_role"]
            for entry in spectrum.pages["home"]
            if entry.section_key == "product_section"
            and entry.settings.get("background", {}).get("mode") == "palette_pattern"
        ]
        self.assertEqual(roles, ["tone-1", "tone-2", "tone-3", "tone-4", "tone-5"])
        # paired white rails share a 6/6 row
        pair_rows = {}
        for entry in spectrum.pages["home"]:
            if entry.row_key:
                pair_rows.setdefault(entry.row_key, []).append(entry.row_span)
        self.assertIn([6, 6], pair_rows.values())

        # the strip banner uses the picture-first variant; the four tiles use the near-square variant
        banners = [e.settings["layout_variant"] for e in spectrum.pages["home"] if e.section_key == "multi_banner"]
        self.assertEqual(banners, ["strip-art", "tile-4"])
        self.assertEqual(
            next(e for e in spectrum.pages["home"] if e.section_key == "category_grid").settings["display_mode"],
            "grey_circles",
        )

        beauty = lpr.get_layout_preset("magenta_beauty_retail")
        # no product row is invented where the reference leaves the recently-viewed area empty
        self.assertEqual(
            _home_section_keys(beauty),
            [
                "hero_banner", "category_grid", "product_section", "category_grid", "product_section",
                "brand_carousel", "catalog_product_wall", "multi_banner", "catalog_product_wall",
                "newsletter", "trust_features",
            ],
        )
        modes = [e.settings["display_mode"] for e in beauty.pages["home"] if e.section_key == "category_grid"]
        self.assertEqual(modes, ["icon_tiles", "gradient_tiles"])

        pastel = lpr.get_layout_preset("pastel_kawaii_stationery")
        grids = [e for e in pastel.pages["home"] if e.section_key == "product_section"]
        self.assertGreaterEqual(len(grids), 8)
        self.assertTrue(all(e.settings["display_mode"] == "catalog_grid" for e in grids))
        self.assertTrue(all(e.settings["card"]["card_style"] == "pastel_flat" for e in grids))
        # the reference has no quick-view trigger on cards
        for key in REFERENCE_TEMPLATES:
            for entry in lpr.get_layout_preset(key).pages["home"]:
                card = (entry.settings or {}).get("card")
                if card and card.get("card_style") in {"pastel_flat", "center_stepper", "beauty_retail"}:
                    self.assertIs(card.get("show_quick_view"), False, (key, entry.section_key))
        self.assertEqual(pastel.pages["home"][0].settings["hero_style"], "poster_wide")
        self.assertEqual(
            [e.settings.get("block_style") for e in pastel.pages["home"] if e.section_key == "image_text"],
            ["plain", "plain"],
        )
        self.assertIn("testimonials", _home_section_keys(pastel))

    def test_no_marketing_copy_is_invented_for_placeholder_blocks(self):
        """Placeholder text is a neutral structural label, never a marketing message or a person name."""
        pastel = lpr.get_layout_preset("pastel_kawaii_stationery")
        for entry in pastel.pages["home"]:
            if entry.section_key == "image_text":
                self.assertEqual(entry.settings["title"], "عنوان بخش")
                self.assertIn("ویرایشگر", entry.settings["body_html"])
            if entry.section_key == "testimonials":
                self.assertEqual({i["name"] for i in entry.settings["items"]}, {"مشتری"})
                self.assertEqual({i["quote"] for i in entry.settings["items"]}, {"نظر مشتری"})


class ReferenceVariantContractTests(SimpleTestCase):
    def test_new_global_variants_resolve_to_real_renderers(self):
        for region, key in (
            (global_region_registry.GLOBAL_HEADER_REGION, "stationery_search"),
            (global_region_registry.GLOBAL_HEADER_REGION, "kawaii_center"),
            (global_region_registry.GLOBAL_FOOTER_REGION, "stationery_dark"),
            (global_region_registry.GLOBAL_FOOTER_REGION, "kawaii_minimal"),
        ):
            with self.subTest(region=region.key, variant=key):
                variant = global_region_registry.get_global_variant(region, key)
                self.assertIsNotNone(variant)
                self.assertTrue(variant.renderer.startswith(global_region_registry.GLOBAL_RENDERER_NAMESPACE))
                get_template(variant.renderer)

    def test_new_card_styles_and_display_modes_are_registered(self):
        self.assertIn("center_stepper", section_registry.CARD_STYLE_CHOICES)
        self.assertIn("pastel_flat", section_registry.CARD_STYLE_CHOICES)
        self.assertIn("catalog_grid", section_registry.PRODUCT_SECTION_DISPLAY_MODES)
        for mode in ("pastel_tiles", "grey_circles", "icon_tiles", "gradient_tiles"):
            self.assertIn(mode, section_registry.CATEGORY_GRID_DISPLAY_MODES)
        for layout in ("tile-4", "strip-art"):
            self.assertIn(layout, section_registry.MULTI_BANNER_KNOWN_LAYOUT_VARIANTS)
        self.assertIn("poster_wide", section_registry.HERO_STYLE_CHOICES)
        product = section_registry.get_definition("product_section")
        self.assertIn("catalog_grid", {variant.key for variant in product.variants})
        category = section_registry.get_definition("category_grid")
        self.assertTrue({"pastel_tiles", "grey_circles", "icon_tiles", "gradient_tiles"} <= {variant.key for variant in category.variants})

    def test_orchid_palette_carries_the_brand_price_role(self):
        palette = appearance_registry.get_palette("orchid-retail")
        self.assertEqual(palette.theme_roles["price"], palette.colors["primary"])
        self.assertEqual(len(palette.section_tones), 5)

    def test_every_reference_recipe_section_validates_with_its_variant_settings(self):
        for key in REFERENCE_TEMPLATES:
            preset = lpr.get_layout_preset(key)
            for page_type, entries in preset.pages.items():
                for entry in entries:
                    with self.subTest(key=key, page=page_type, section=entry.section_key):
                        definition = section_registry.get_definition(entry.section_key)
                        cleaned = (
                            definition.default_settings() if entry.settings is None
                            else definition.validate_settings(entry.settings)
                        )
                        if entry.section_key == "product_section" and entry.settings:
                            self.assertEqual(
                                cleaned["display_mode"], entry.settings["display_mode"],
                            )

    def test_recipes_contain_no_script_or_template_payload(self):
        for key in REFERENCE_TEMPLATES:
            serialized = str(dataclasses.asdict(lpr.get_layout_preset(key))).lower()
            for needle in ("<script", "javascript:", "{%", "{{"):
                self.assertNotIn(needle, serialized, key)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ReferenceTemplateLifecycleTests(TestCase):
    """Gallery card -> first apply -> preservation-first switch -> publish ->
    public Home, for each of the three templates, through the real services."""

    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.actor = User.objects.create_user(username="ref_51_53_owner", password="pass12345", is_staff=True)

    def test_gallery_cards_exist_for_the_three_templates_with_a_thumbnail(self):
        draft = svc.get_or_create_draft(self.store)
        cards = ready_template_card_service.build_ready_template_cards(
            draft, current_template_key=None, current_template_version=None,
        )
        by_key = {card["preset"].key: card for card in cards}
        self.assertEqual(len(cards), 53)
        for key in REFERENCE_TEMPLATES:
            with self.subTest(key=key):
                card = by_key[key]
                self.assertTrue(card["thumbnail_svg"] or card["thumbnail_url"])
                self.assertTrue(card["header_variant_label"])
                self.assertTrue(card["footer_variant_label"])
                self.assertTrue(card["palette_swatch"])
                svg = template_preview_service.resolve_gallery_thumbnail(card["preset"])
                self.assertIn("<svg", svg)

    def test_each_template_applies_switches_publishes_and_renders_publicly(self):
        client = Client(HTTP_HOST=HOST)
        markers = {
            "stationery_spectrum": ("gh--stationery", "gf--stationery"),
            "magenta_beauty_retail": ("gh--beauty", "gf--beauty"),
            "pastel_kawaii_stationery": ("gh--kawaii", "gf--kawaii"),
        }
        first = True
        for key in REFERENCE_TEMPLATES:
            with self.subTest(key=key):
                result = store_template_service.select_ready_template(
                    store=self.store, actor=self.actor, template_key=key,
                )
                self.assertEqual(result.action, "initial" if first else "switched")
                first = False
                applied = store_template_service.get_applied_template(self.store)
                self.assertEqual((applied.key, applied.version), (key, "1"))
                self.assertTrue(applied.is_current_version)
                svc.publish(self.store, user=self.actor)
                cache.clear()
                response = client.get(reverse("catalog:home"))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                for marker in markers[key]:
                    self.assertIn(marker, html)


class ReferencePrimitiveRenderTests(SimpleTestCase):
    """The generic primitives added for 51-53 render through their registered section templates."""

    @staticmethod
    def _render(template, **context):
        from django.template.loader import render_to_string

        return render_to_string(f"storefront_builder/sections/{template}.html", context)

    @staticmethod
    def _category(n):
        from types import SimpleNamespace

        return SimpleNamespace(pk=n, slug=f"c{n}", name=f"دسته {n}", icon="🏷️", image=None, representative_media=None)

    def test_category_icon_and_gradient_tiles(self):
        cats = [self._category(1), self._category(2)]
        html = self._render("category_grid", top_categories=cats, category_grid_settings={"display_mode": "icon_tiles", "title": "T"})
        self.assertIn("category-icontile-row", html)
        self.assertEqual(html.count('class="category-icontile"'), 2)
        html = self._render("category_grid", top_categories=cats, category_grid_settings={"display_mode": "gradient_tiles", "title": ""})
        self.assertIn("category-gradient-grid", html)
        self.assertIn("category-gradient-title", html)
        for mode, marker in (("grey_circles", "category-grey-circles"), ("pastel_tiles", "category-pastel-grid")):
            html = self._render("category_grid", top_categories=cats, category_grid_settings={"display_mode": mode, "title": "T"})
            self.assertIn(marker, html)

    def test_catalog_grid_pager_bar_only_when_view_all_is_enabled(self):
        base = {"display_mode": "catalog_grid", "title": "T", "card": {}}
        with_bar = self._render("product_section", settings={**base, "show_view_all": True}, products=[])
        self.assertIn("catalog-grid-bar-row", with_bar)
        self.assertIn("catalog-grid-more", with_bar)
        self.assertNotIn("catalog-grid-bar-row", self._render("product_section", settings={**base, "show_view_all": False}, products=[]))

    def test_plain_image_text_block_has_a_geometry_placeholder_but_cream_is_unchanged(self):
        plain = self._render("image_text", settings={"title": "a", "body_html": "<p>b</p>", "image_url": "", "image_position": "left", "block_style": "plain"})
        self.assertIn("imgtext-plain", plain)
        self.assertIn("imgtext-placeholder", plain)
        cream = self._render("image_text", settings={"title": "a", "body_html": "<p>b</p>", "image_url": "", "image_position": "right"})
        self.assertNotIn("imgtext-plain", cream)
        self.assertNotIn("imgtext-placeholder", cream)

    def test_testimonials_avatar_grid_is_opt_in(self):
        items = [{"name": "n", "quote": "q", "role": ""}]
        self.assertIn("testimonials--avatar-grid", self._render("testimonials", settings={"title": "t", "items": items, "style": "avatar_grid"}))
        self.assertNotIn("testimonials--avatar-grid", self._render("testimonials", settings={"title": "t", "items": items}))

    def test_optional_settings_are_written_only_when_non_default(self):
        image_text = section_registry.get_definition("image_text")
        self.assertNotIn("block_style", image_text.validate_settings({"title": "a"}))
        self.assertEqual(image_text.validate_settings({"title": "a", "block_style": "plain"})["block_style"], "plain")
        self.assertNotIn("block_style", image_text.validate_settings({"title": "a", "block_style": "weird"}))
        testimonials = section_registry.get_definition("testimonials")
        self.assertNotIn("style", testimonials.validate_settings({"items": []}))
        self.assertEqual(testimonials.validate_settings({"items": [], "style": "avatar_grid"})["style"], "avatar_grid")
        self.assertNotIn("show_quick_view", section_registry.validate_card_settings({}))
        self.assertIs(section_registry.validate_card_settings({"show_quick_view": False})["show_quick_view"], False)
        self.assertNotIn("show_quick_view", section_registry.validate_card_settings({"show_quick_view": True}))


class BlogPanelPrimitiveTests(SimpleTestCase):
    def test_blog_panel_style_is_written_only_when_selected(self):
        from apps.storefront_builder import section_registry as sr

        self.assertNotIn("style", sr.validate_blog_posts_settings({"title": "x", "item_limit": 5}))
        self.assertNotIn("style", sr.validate_blog_posts_settings({"style": "grid"}))
        self.assertEqual(sr.validate_blog_posts_settings({"style": "panel_carousel"})["style"], "panel_carousel")

    def test_spectrum_recipe_uses_the_generic_panel_presentations(self):
        spectrum = lpr.get_layout_preset("stationery_spectrum")
        blog = [e for e in spectrum.pages["home"] if e.section_key == "blog_posts"][0]
        self.assertEqual(blog.settings["style"], "panel_carousel")
        brands = [e for e in spectrum.pages["home"] if e.section_key == "brand_carousel"][0]
        self.assertEqual(brands.settings["background"], {"mode": "color", "color": "#FFFFFF"})
