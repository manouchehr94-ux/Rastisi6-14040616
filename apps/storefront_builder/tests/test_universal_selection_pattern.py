from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.storefront_builder.section_registry import (
    _validate_brand_carousel_settings,
    _validate_category_grid_settings,
    _validate_collection_tiles_settings,
    _validate_product_section_settings,
    default_brand_carousel_settings,
    default_category_grid_settings,
    default_collection_tiles_settings,
)


BASE = Path(settings.BASE_DIR)


class UniversalSelectionPatternTests(SimpleTestCase):
    def _read(self, rel):
        return (BASE / rel).read_text(encoding="utf-8")

    def test_ordered_ids_are_preserved_by_existing_validators(self):
        self.assertEqual(
            _validate_brand_carousel_settings({"brand_ids": [7, 3, 9], "display_mode": "grid"})["brand_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_category_grid_settings({"category_ids": [7, 3, 9], "display_mode": "grid", "item_limit": 12})["category_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_collection_tiles_settings({"collection_ids": [7, 3, 9], "tile_style": "grid"})["collection_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            _validate_product_section_settings({
                "data_source": "manual", "product_ids": [7, 3, 9], "item_limit": 8,
                "display_mode": "carousel", "show_view_all": True,
            })["product_ids"],
            [7, 3, 9],
        )

    def test_existing_validators_dedupe_without_reordering_and_keep_caps(self):
        self.assertEqual(
            _validate_brand_carousel_settings({"brand_ids": [7, 3, 7, 9], "display_mode": "grid"})["brand_ids"],
            [7, 3, 9],
        )
        self.assertEqual(
            len(_validate_brand_carousel_settings({"brand_ids": list(range(1, 40)), "display_mode": "grid"})["brand_ids"]),
            24,
        )
        self.assertEqual(
            len(_validate_category_grid_settings({"category_ids": list(range(1, 30)), "display_mode": "grid", "item_limit": 12})["category_ids"]),
            12,
        )
        self.assertEqual(
            len(_validate_collection_tiles_settings({"collection_ids": list(range(1, 30)), "tile_style": "grid"})["collection_ids"]),
            12,
        )

    def test_empty_non_product_ids_keep_automatic_compatibility(self):
        self.assertEqual(default_brand_carousel_settings()["brand_ids"], [])
        self.assertEqual(default_category_grid_settings()["category_ids"], [])
        self.assertEqual(default_collection_tiles_settings()["collection_ids"], [])
        self.assertEqual(_validate_brand_carousel_settings({"display_mode": "grid"})["brand_ids"], [])
        self.assertEqual(_validate_category_grid_settings({"display_mode": "grid", "item_limit": 12})["category_ids"], [])
        self.assertEqual(_validate_collection_tiles_settings({"tile_style": "grid"})["collection_ids"], [])
