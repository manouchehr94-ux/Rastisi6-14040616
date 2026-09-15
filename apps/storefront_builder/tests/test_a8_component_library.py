import re
from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse

from apps.storefront_builder import global_region_registry
from apps.storefront_builder.storefront_appearance.registry import (
    COMPONENT_REGISTRY,
    component_counts_by_family,
    resolve_component_implementation,
)


A8_COMPONENT_KEYS = frozenset(
    {
        "header.editorial_row.v1",
        "header.marketplace_search.v1",
        "header.centered_brand.v1",
        "header.floating_compact.v1",
        "header.compact_drawer.v1",
        "header.promo_bar.v1",
        "header.community_shortcuts.v1",
        "header.overlay_transparent.v1",
        "header.editorial_masthead.v1",
        "header.compact_menu.v1",
        "header.category_tabs.v1",
        "header.playful_canopy.v1",
        "mega_menu.none.v1",
        "hero.none.v1",
        "hero.immersive.v1",
        "hero.editorial_split.v1",
        "hero.promo_bento.v1",
        "hero.typographic.v1",
        "hero.product_focus.v1",
        "hero.image_collage.v1",
        "hero.side_offer_slider.v1",
        "hero.media_feature.v1",
        "hero.quiet.v1",
        "hero.search_first.v1",
        "hero.campaign_mosaic.v1",
        "hero.social_gallery.v1",
        "layout.two_column.v1",
        "layout.three_column.v1",
        "layout.four_column.v1",
        "layout.dense_five.v1",
        "layout.horizontal_rail.v1",
        "layout.catalog_list.v1",
        "layout.bento_grid.v1",
        "layout.featured_split.v1",
        "layout.editorial_zigzag.v1",
        "product_view.standard_grid.v1",
        "product_view.carousel.v1",
        "product_view.dense_grid.v1",
        "product_view.editorial_grid.v1",
        "product_view.catalog_list.v1",
        "product_view.bento.v1",
        "product_view.featured_wall.v1",
        "card.standard.v1",
        "card.marketplace_price.v1",
        "card.editorial_minimal.v1",
        "card.retail_row.v1",
        "card.luxury_dark.v1",
        "card.soft_capsule.v1",
        "card.beauty_glass.v1",
        "card.paper_frame.v1",
        "card.price_first.v1",
        "card.portrait_round.v1",
        "card.catalog_index.v1",
        "card.shipping_label.v1",
        "card.shelf_editorial.v1",
        "card.technical_spec.v1",
        "card.tech_neon.v1",
        "card.bold_outline.v1",
        "badge.none.v1",
        "badge.sale.v1",
        "motion.none.v1",
        "motion.subtle.v1",
        "motion.dynamic.v1",
        "footer.minimal.v1",
        "footer.marketplace_columns.v1",
        "footer.editorial_wordmark.v1",
        "footer.brand_story.v1",
        "footer.bold_columns.v1",
        "footer.centered.v1",
        "footer.app_download.v1",
        "footer.playful_wave.v1",
        "bottom_nav.four_item.v1",
        "bottom_nav.five_item.v1",
        "bottom_nav.raised_cart.v1",
        "bottom_nav.floating_dock.v1",
        "bottom_nav.glass_dock.v1",
        "bottom_nav.minimal_icons.v1",
        "bottom_nav.wide_cart.v1",
        # P5-W2 — Ready Templates advertise only the Theme no-op.
        "theme.none.v1",
    }
)

A8_MOBILE_NAV_EXPECTATIONS = {
    "four_item": {"item_count": 4, "has_search": False},
    "five_item": {"item_count": 5, "has_search": True},
    "raised_cart": {"item_count": 5, "has_search": True},
    "floating_dock": {"item_count": 5, "has_search": True},
    "glass_dock": {"item_count": 5, "has_search": True},
    "minimal_icons": {"item_count": 4, "has_search": False},
    "wide_cart": {"item_count": 4, "has_search": False},
}


class A8ComponentLibraryTests(SimpleTestCase):
    def test_a8_expands_the_component_catalog_to_the_reviewed_exact_counts(self):
        self.assertEqual(
            component_counts_by_family(),
            {
                "header": 22,
                "mega_menu": 1,
                "hero": 19,
                "layout": 17,
                "product_view": 13,
                "card": 17,
                "badge": 2,
                "motion": 3,
                "footer": 16,
                "bottom_nav": 9,
                # P5-W2 — 8 occasion themes (none + 7 occasions) from the
                # single theme_catalog, adapted into the central registry.
                "theme": 8,
            },
        )
        self.assertEqual(len(COMPONENT_REGISTRY), 127)

    def test_mapping_vocabulary_is_registered_once_and_resolves_from_allowlist(self):
        self.assertTrue(
            A8_COMPONENT_KEYS.issubset(COMPONENT_REGISTRY),
            A8_COMPONENT_KEYS - COMPONENT_REGISTRY.keys(),
        )
        self.assertEqual(len(COMPONENT_REGISTRY), len(set(COMPONENT_REGISTRY)))

        for key in A8_COMPONENT_KEYS:
            with self.subTest(key=key):
                component = COMPONENT_REGISTRY[key]
                self.assertNotIn("/", component.registry_reference)
                self.assertIsNotNone(resolve_component_implementation(component))

    def test_new_semantic_keys_are_rtl_responsive_and_not_prototype_ids(self):
        prototype_identity = re.compile(r"(?:^|\.)(?:h\d+|x\d+|c-[a-z]+|g\d+|m(?:fab|dock|glass|icon|big|\d+))(?:\.|$)")
        for key in A8_COMPONENT_KEYS:
            with self.subTest(key=key):
                component = COMPONENT_REGISTRY.get(key)
                self.assertIsNotNone(component)
                self.assertFalse(prototype_identity.search(key))
                if component.family_key == "motion":
                    self.assertIn("reduced_motion", component.capabilities)
                else:
                    self.assertIn("rtl", component.capabilities)
                    self.assertTrue(
                        {"responsive", "mobile"}.intersection(component.capabilities)
                    )

    def test_every_a8_global_region_renderer_stays_in_trusted_partial_namespace(self):
        regions = {
            "header": global_region_registry.GLOBAL_HEADER_REGION,
            "footer": global_region_registry.GLOBAL_FOOTER_REGION,
            "bottom_nav": global_region_registry.GLOBAL_MOBILE_NAV_REGION,
        }
        for family_key, region in regions.items():
            keys = [key for key in A8_COMPONENT_KEYS if key.startswith(f"{family_key}.")]
            for key in keys:
                with self.subTest(key=key):
                    variant = resolve_component_implementation(COMPONENT_REGISTRY[key])
                    self.assertIn(variant, region.variants)
                    self.assertTrue(
                        variant.renderer.startswith("storefront_builder/partials/"),
                        variant.renderer,
                    )
                    self.assertIsNotNone(get_template(variant.renderer))

    def test_only_true_default_identities_are_virtual(self):
        virtual = {
            key
            for key, component in COMPONENT_REGISTRY.items()
            if component.registry_reference.startswith("virtual:")
        }
        self.assertEqual(
            virtual,
            {
                "mega_menu.none.v1",
                "card.legacy_default.v1",
                "badge.none.v1",
            },
        )

    def test_mobile_nav_identities_render_real_accessible_distinct_structures(self):
        required_urls = {
            reverse("catalog:home"),
            reverse("catalog:product-list"),
            reverse("cart:detail"),
            reverse("customers:account"),
        }
        rendered = {}
        for identity, expected in A8_MOBILE_NAV_EXPECTATIONS.items():
            with self.subTest(identity=identity):
                component = COMPONENT_REGISTRY[f"bottom_nav.{identity}.v1"]
                variant = resolve_component_implementation(component)
                html = render_to_string(
                    variant.renderer,
                    {"is_live_storefront": True, "page_type": "home", "cart_count": 7},
                )
                rendered[identity] = html
                self.assertIn(f'data-mobile-nav="{identity}"', html)
                self.assertIn(f"gmn--{identity}", html)
                self.assertEqual(html.count("data-mobile-nav-item"), expected["item_count"])
                self.assertEqual("data-mobile-nav-search" in html, expected["has_search"])
                self.assertIn('aria-label="ناوبری اصلی موبایل"', html)
                self.assertIn('aria-label="۷ کالا در سبد"', html)
                self.assertIn(">۷</span>", html)
                self.assertNotIn('href="#"', html)
                for url in required_urls:
                    self.assertIn(f'href="{url}"', html)

        self.assertNotEqual(rendered["four_item"], rendered["five_item"])
        self.assertNotIn("data-mobile-nav-search", rendered["four_item"])
        self.assertIn("data-mobile-nav-search", rendered["five_item"])

    def test_mobile_nav_css_is_mobile_only_rtl_safe_area_aware_and_identity_specific(self):
        css_path = Path(settings.BASE_DIR) / "apps/storefront_builder/static/css/storefront_builder.css"
        css = css_path.read_text(encoding="utf-8")

        self.assertIn(".gmn,.gmn-spacer{display:none}", css)
        self.assertIn("@media(max-width:680px)", css)
        self.assertIn("env(safe-area-inset-bottom", css)
        self.assertIn("direction:rtl", css)
        self.assertIn(".gmn-spacer", css)
        for identity in A8_MOBILE_NAV_EXPECTATIONS:
            with self.subTest(identity=identity):
                self.assertIn(f".gmn--{identity}", css)
