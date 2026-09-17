"""Task 4 contracts for the exact A8 Ready Template catalog."""

import dataclasses
import json
import re

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.a8_ready_templates import A8_READY_TEMPLATES
from apps.storefront_builder.storefront_appearance.families import COMPONENT_FAMILIES
from apps.storefront_builder.storefront_appearance.registry import get_component


EXPECTED_LATEST_VERSIONS = {
    "editorial_jewelry": "3",
    "dense_marketplace": "3",
    "warm_boutique": "3",
    "premium_leather": "3",
    "dark_digital": "3",
    "cedar_home": "2",
    "street_drop": "1",
    "premium_leather_noir": "2",
    "search_market": "1",
    "playful_lifestyle": "2",
    "utility_catalog": "2",
    "artisan_grain": "2",
    "pixel_play": "1",
    "simorgh_market": "2",
    "coastal_product": "2",
    "literary_catalog": "1",
    "gallery_minimal": "1",
    "handmade_luxe": "2",
    "niloufar_glass": "2",
    "tool_finder": "1",
    "green_workshop": "2",
    "tower_department": "1",
    "beauty_dew": "2",
    "fashion_promo_catalog": "8",
    "horizon_story": "2",
    "mina_community": "1",
    "silk_editorial": "2",
    "tuska_bento": "1",
    "rayan_tech": "2",
    "laleh_play": "2",
    "city_classic": "2",
    "collection_index": "1",
    "kamand_artisan": "2",
    "almas_luxury": "2",
    "roosta_zigzag": "1",
    "mother_utility": "1",
    "aftab_price": "1",
    "mist_quiet": "1",
    "night_catalog": "1",
    "watchmaker_round": "2",
    "kite_playful": "1",
    "pine_eco": "2",
    "mirror_beauty": "2",
    "charcoal_grill": "1",
    "calligraphy_paper": "1",
    "harbor_imports": "2",
    "parnian_editorial": "2",
    "racer_tech": "1",
    "ferdowsi_department": "1",
    "anniversary_mosaic": "1",
}

HISTORICAL_IDENTITIES = {
    "dense_marketplace": "2",
    "premium_leather": "2",
    "warm_boutique": "2",
    "fashion_promo_catalog": "7",
    "playful_lifestyle": "1",
    "utility_catalog": "1",
    "editorial_jewelry": "2",
    "dark_digital": "2",
}

FORBIDDEN_DATA_KEYS = {
    "store_id",
    "store_slug",
    "resource_id",
    "product_id",
    "product_ids",
    "category_id",
    "category_ids",
    "collection_id",
    "collection_ids",
    "brand_id",
    "brand_ids",
    "source_id",
    "manual_product_ids",
    "renderer",
    "renderer_path",
    "template",
    "template_path",
    "html",
    "css",
    "javascript",
    "script",
}


def _walk(value):
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (tuple, list, set, frozenset)):
        for item in value:
            yield from _walk(item)


class A8ReadyTemplateCatalogTests(SimpleTestCase):
    def test_show_all_is_exactly_the_literal_fifty_key_catalog(self):
        presets = lpr.list_ready_templates()

        self.assertEqual(len(A8_READY_TEMPLATES), 50)
        self.assertEqual(
            {preset.key: preset.version for preset in A8_READY_TEMPLATES},
            EXPECTED_LATEST_VERSIONS,
        )
        self.assertEqual(len(presets), 50)
        self.assertEqual(len({preset.key for preset in presets}), 50)
        self.assertEqual(
            {preset.key: preset.version for preset in presets},
            EXPECTED_LATEST_VERSIONS,
        )

    def test_every_latest_recipe_has_complete_resolvable_versioned_dna(self):
        expected_families = set(COMPONENT_FAMILIES)

        for preset in lpr.list_ready_templates():
            with self.subTest(preset=preset.key):
                self.assertIs(lpr.get_layout_preset_version(preset.key, preset.version), preset)
                self.assertIsNotNone(preset.store_appearance)
                self.assertEqual(preset.store_appearance["schema_version"], 1)
                self.assertEqual(
                    set(preset.store_appearance["selections"]), expected_families
                )
                for family_key, component_key in preset.store_appearance["selections"].items():
                    component = get_component(component_key)
                    self.assertIsNotNone(component, component_key)
                    self.assertEqual(component.family_key, family_key)

    def test_historical_eight_remain_exact_and_manifest_transition_is_removed(self):
        self.assertFalse(hasattr(lpr, "_LEGACY_READY_TEMPLATE_IDENTITIES"))

        for key, old_version in HISTORICAL_IDENTITIES.items():
            with self.subTest(key=key):
                historical = lpr.get_layout_preset_version(key, old_version)
                latest = lpr.get_layout_preset(key)
                self.assertIsNotNone(historical)
                self.assertIsNotNone(historical.store_appearance)
                self.assertEqual(historical.store_appearance["schema_version"], 1)
                self.assertGreater(int(latest.version), int(old_version))

        manifestless = lpr.LayoutPresetDefinition(
            key="__a8_manifestless_official__",
            label_fa="قالب بدون مانیفست",
            description_fa="باید رد شود",
            is_ready_template=True,
        )
        with self.assertRaises(lpr.InvalidLayoutPresetError):
            lpr.register_layout_preset(manifestless)

    def test_recipes_contain_no_tenant_executable_or_prototype_payload(self):
        prototype_id = re.compile(
            r"(?:^|[.\s])(h\d+|x\d+|c-[a-z]+|g\d+|m(?:fab|dock|glass|icon|big|\d+))(?:$|[.\s])"
        )

        for preset in lpr.list_ready_templates():
            with self.subTest(preset=preset.key):
                primitive = dataclasses.asdict(preset)
                for mapping in _walk(primitive):
                    self.assertFalse(FORBIDDEN_DATA_KEYS.intersection(mapping), mapping)
                serialized = json.dumps(primitive, ensure_ascii=False).lower()
                self.assertNotIn("<script", serialized)
                self.assertNotIn("javascript:", serialized)
                self.assertNotIn("{%", serialized)
                self.assertNotIn("{{", serialized)
                self.assertIsNone(prototype_id.search(serialized), preset.key)
