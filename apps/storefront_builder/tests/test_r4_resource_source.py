"""R4 Task 9 — the shared, typed ResourceSource contract for Product/Brand.

Pure-contract tests first (no DB), then the compatibility adapters, then
(after section_registry.py registers the Product/Brand schemas) the schema
bridge / wrapper-preservation / R3-compatibility proofs.
"""

from django.test import SimpleTestCase, TestCase

from apps.storefront_builder import resource_source as rs
from apps.storefront_builder import section_registry
from apps.storefront_builder.settings_schema import clean_section_schema_patch


class ResourceSourceConstructionTests(SimpleTestCase):
    def test_invalid_kind_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="widget", mode="auto", auto_rule="all_active")

    def test_invalid_mode_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="sometimes", auto_rule="all_active")

    def test_bool_manual_id_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=(True,))

    def test_zero_manual_id_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=(0,))

    def test_negative_manual_id_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=(-5,))

    def test_manual_ids_deduplicated_preserving_first_seen_order(self):
        source = rs.ResourceSource(kind="product", mode="manual", manual_ids=(7, 3, 7, 9, 3))
        self.assertEqual(source.manual_ids, (7, 3, 9))

    def test_input_list_mutation_after_construction_does_not_mutate_source(self):
        ids = [7, 3]
        source = rs.ResourceSource(kind="product", mode="manual", manual_ids=tuple(ids))
        ids.append(999)
        self.assertEqual(source.manual_ids, (7, 3))

    def test_input_dict_mutation_after_construction_does_not_mutate_source(self):
        params = {"source_id": 5}
        source = rs.ResourceSource(kind="product", mode="auto", auto_rule="by_category", auto_parameters=params)
        params["source_id"] = 999
        params["extra"] = "x"
        self.assertEqual(dict(source.auto_parameters), {"source_id": 5})

    def test_per_kind_manual_cap_enforced(self):
        rs.ResourceSource(kind="product", mode="manual", manual_ids=tuple(range(1, 61)))
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=tuple(range(1, 62)))
        rs.ResourceSource(kind="brand", mode="manual", manual_ids=tuple(range(1, 25)))
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="manual", manual_ids=tuple(range(1, 26)))
        rs.ResourceSource(kind="category", mode="manual", manual_ids=tuple(range(1, 13)))
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="category", mode="manual", manual_ids=tuple(range(1, 14)))
        rs.ResourceSource(kind="collection", mode="manual", manual_ids=tuple(range(1, 13)))
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="collection", mode="manual", manual_ids=tuple(range(1, 14)))


# ---------------------------------------------------------------------------
# Corrective review pass — a falsey-but-wrong-type serialized value must
# never silently become the valid empty structure for the other field, and
# a non-Mapping/non-sequence value passed directly to the constructor must
# raise ResourceSourceError rather than an uncontrolled Python TypeError.
# ---------------------------------------------------------------------------


class DeserializerStrictTypeTests(SimpleTestCase):
    def _valid_auto_payload(self, **overrides):
        payload = {
            "kind": "product", "mode": "auto", "auto_rule": "newest",
            "auto_parameters": {}, "manual_ids": [],
        }
        payload.update(overrides)
        return payload

    def test_auto_parameters_list_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(auto_parameters=[]))

    def test_auto_parameters_empty_string_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(auto_parameters=""))

    def test_auto_parameters_zero_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(auto_parameters=0))

    def test_auto_parameters_null_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(auto_parameters=None))

    def test_manual_ids_empty_string_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(manual_ids=""))

    def test_manual_ids_empty_dict_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(manual_ids={}))

    def test_manual_ids_zero_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(manual_ids=0))

    def test_manual_ids_null_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(self._valid_auto_payload(manual_ids=None))

    def test_missing_auto_parameters_key_still_uses_default(self):
        payload = self._valid_auto_payload()
        del payload["auto_parameters"]
        source = rs.deserialize_resource_source(payload)
        self.assertEqual(dict(source.auto_parameters), {})

    def test_missing_manual_ids_key_still_uses_default(self):
        payload = self._valid_auto_payload()
        del payload["manual_ids"]
        source = rs.deserialize_resource_source(payload)
        self.assertEqual(source.manual_ids, ())


class ConstructorRuntimeTypeTests(SimpleTestCase):
    def test_auto_parameters_list_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="newest", auto_parameters=[])

    def test_auto_parameters_empty_string_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="newest", auto_parameters="")

    def test_auto_parameters_list_of_pairs_rejected(self):
        # A list-of-pairs is NOT accepted as an accidental Mapping substitute,
        # even though dict(list_of_pairs) would otherwise happily coerce it.
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(
                kind="product", mode="auto", auto_rule="by_category",
                auto_parameters=[("source_id", 5)],
            )

    def test_manual_ids_scalar_int_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=7)

    def test_manual_ids_string_rejected(self):
        # tuple("73") would silently become ('7', '3') without an upfront
        # container-type check — must be rejected outright instead.
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids="73")

    def test_manual_ids_mapping_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids={1: "x", 2: "y"})


class InternalImmutabilityTests(SimpleTestCase):
    def test_auto_parameters_mapping_is_not_writable(self):
        source = rs.ResourceSource(
            kind="product", mode="auto", auto_rule="by_category", auto_parameters={"source_id": 5},
        )
        with self.assertRaises(TypeError):
            source.auto_parameters["source_id"] = 999

    def test_caller_dict_aliasing_after_construction_still_impossible(self):
        params = {"source_id": 5}
        source = rs.ResourceSource(
            kind="product", mode="auto", auto_rule="by_category", auto_parameters=params,
        )
        params["source_id"] = 999
        self.assertEqual(dict(source.auto_parameters), {"source_id": 5})


class ProductAutoRuleTests(SimpleTestCase):
    def test_exact_allowlist(self):
        for rule in ("newest", "discounted", "best_sellers", "most_viewed"):
            rs.ResourceSource(kind="product", mode="auto", auto_rule=rule)
        for rule in ("by_category", "by_brand", "by_collection"):
            rs.ResourceSource(kind="product", mode="auto", auto_rule=rule, auto_parameters={"source_id": 1})
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="trending")
        # The legacy persisted words for single-reference sources must NOT
        # be accepted as typed auto_rule names directly.
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="category", auto_parameters={"source_id": 1})

    def test_by_category_requires_positive_source_id(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="by_category")
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="by_category", auto_parameters={"source_id": 0})
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="by_category", auto_parameters={"source_id": True})
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(
                kind="product", mode="auto", auto_rule="by_category",
                auto_parameters={"source_id": 1, "extra": 2},
            )

    def test_by_brand_and_by_collection_require_positive_source_id(self):
        rs.ResourceSource(kind="product", mode="auto", auto_rule="by_brand", auto_parameters={"source_id": 4})
        rs.ResourceSource(kind="product", mode="auto", auto_rule="by_collection", auto_parameters={"source_id": 9})
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="by_brand", auto_parameters={"source_id": -1})

    def test_no_parameter_rules_reject_any_parameters(self):
        for rule in ("newest", "discounted", "best_sellers", "most_viewed"):
            with self.assertRaises(rs.ResourceSourceError):
                rs.ResourceSource(kind="product", mode="auto", auto_rule=rule, auto_parameters={"source_id": 1})


class BrandAutoRuleTests(SimpleTestCase):
    def test_only_all_active_allowed(self):
        rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="auto", auto_rule="newest")
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="auto", auto_rule="by_category", auto_parameters={"source_id": 1})

    def test_all_active_rejects_parameters(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active", auto_parameters={"source_id": 1})

    def test_category_and_collection_support_all_active(self):
        rs.ResourceSource(kind="category", mode="auto", auto_rule="all_active")
        rs.ResourceSource(kind="collection", mode="auto", auto_rule="all_active")


class ModeInvariantTests(SimpleTestCase):
    def test_manual_mode_requires_at_least_one_id(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=())

    def test_manual_mode_rejects_auto_rule(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=(1,), auto_rule="newest")

    def test_manual_mode_rejects_auto_parameters(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="manual", manual_ids=(1,), auto_parameters={"source_id": 1})

    def test_auto_mode_rejects_manual_ids(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="product", mode="auto", auto_rule="newest", manual_ids=(1,))

    def test_auto_mode_requires_valid_rule_for_kind(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.ResourceSource(kind="brand", mode="auto", auto_rule=None)


class SerializationTests(SimpleTestCase):
    def test_round_trip_manual(self):
        source = rs.ResourceSource(kind="product", mode="manual", manual_ids=(9, 4, 1))
        payload = rs.serialize_resource_source(source)
        self.assertEqual(payload, {
            "kind": "product", "mode": "manual", "auto_rule": None,
            "auto_parameters": {}, "manual_ids": [9, 4, 1],
        })
        self.assertEqual(rs.deserialize_resource_source(payload), source)

    def test_round_trip_auto_with_parameters(self):
        source = rs.ResourceSource(
            kind="product", mode="auto", auto_rule="by_category", auto_parameters={"source_id": 17},
        )
        payload = rs.serialize_resource_source(source)
        self.assertEqual(payload["auto_parameters"], {"source_id": 17})
        self.assertEqual(rs.deserialize_resource_source(payload), source)

    def test_round_trip_auto_no_parameters(self):
        source = rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
        payload = rs.serialize_resource_source(source)
        self.assertEqual(payload, {
            "kind": "brand", "mode": "auto", "auto_rule": "all_active",
            "auto_parameters": {}, "manual_ids": [],
        })
        self.assertEqual(rs.deserialize_resource_source(payload), source)

    def test_serialized_unknown_top_level_key_rejected(self):
        payload = rs.serialize_resource_source(rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active"))
        payload["unexpected"] = 1
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(payload)

    def test_deserialize_rejects_non_object(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source("not-an-object")
        with self.assertRaises(rs.ResourceSourceError):
            rs.deserialize_resource_source(None)


class ProductLegacyCompatibilityTests(SimpleTestCase):
    def test_all_eight_data_sources_round_trip(self):
        cases = [
            ({"data_source": "newest", "source_id": None, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="newest")),
            ({"data_source": "discounted", "source_id": None, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="discounted")),
            ({"data_source": "best_sellers", "source_id": None, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="best_sellers")),
            ({"data_source": "most_viewed", "source_id": None, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="most_viewed")),
            ({"data_source": "category", "source_id": 17, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="by_category", auto_parameters={"source_id": 17})),
            ({"data_source": "brand", "source_id": 4, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="by_brand", auto_parameters={"source_id": 4})),
            ({"data_source": "collection", "source_id": 9, "product_ids": []},
             rs.ResourceSource(kind="product", mode="auto", auto_rule="by_collection", auto_parameters={"source_id": 9})),
            ({"data_source": "manual", "source_id": None, "product_ids": [7, 3, 9]},
             rs.ResourceSource(kind="product", mode="manual", manual_ids=(7, 3, 9))),
        ]
        for legacy_settings, expected_typed in cases:
            with self.subTest(legacy_settings=legacy_settings):
                typed = rs.product_resource_source_from_settings(legacy_settings)
                self.assertEqual(typed, expected_typed)
                round_tripped = rs.product_resource_source_to_legacy_patch(typed)
                self.assertEqual(round_tripped, legacy_settings)
                self.assertNotIn("source", round_tripped)


class BrandLegacyCompatibilityTests(SimpleTestCase):
    def test_empty_ids_means_auto_all_active(self):
        typed = rs.brand_resource_source_from_settings({"brand_ids": []})
        self.assertEqual(typed, rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active"))
        patch = rs.brand_resource_source_to_legacy_patch(typed)
        self.assertEqual(patch, {"brand_ids": []})
        self.assertNotIn("source", patch)

    def test_manual_ids_preserve_order(self):
        typed = rs.brand_resource_source_from_settings({"brand_ids": [7, 3, 9]})
        self.assertEqual(typed, rs.ResourceSource(kind="brand", mode="manual", manual_ids=(7, 3, 9)))
        patch = rs.brand_resource_source_to_legacy_patch(typed)
        self.assertEqual(patch, {"brand_ids": [7, 3, 9]})
        self.assertNotIn("source", patch)

    def test_dedup_without_reorder(self):
        source = rs.ResourceSource(kind="brand", mode="manual", manual_ids=(7, 3, 7, 9))
        self.assertEqual(source.manual_ids, (7, 3, 9))


class CollectionLegacyCompatibilityTests(SimpleTestCase):
    def test_empty_ids_means_auto_all_active(self):
        typed = rs.collection_resource_source_from_settings({"collection_ids": []})
        self.assertEqual(typed, rs.ResourceSource(kind="collection", mode="auto", auto_rule="all_active"))
        patch = rs.collection_resource_source_to_legacy_patch(typed)
        self.assertEqual(patch, {"collection_ids": []})
        self.assertNotIn("source", patch)

    def test_missing_key_means_auto_all_active(self):
        typed = rs.collection_resource_source_from_settings({})
        self.assertEqual(typed, rs.ResourceSource(kind="collection", mode="auto", auto_rule="all_active"))

    def test_manual_ids_preserve_order(self):
        typed = rs.collection_resource_source_from_settings({"collection_ids": [7, 3]})
        self.assertEqual(typed, rs.ResourceSource(kind="collection", mode="manual", manual_ids=(7, 3)))
        patch = rs.collection_resource_source_to_legacy_patch(typed)
        self.assertEqual(patch, {"collection_ids": [7, 3]})
        self.assertNotIn("source", patch)

    def test_dedup_without_reorder(self):
        source = rs.ResourceSource(kind="collection", mode="manual", manual_ids=(7, 3, 7, 9))
        self.assertEqual(source.manual_ids, (7, 3, 9))

    def test_wrong_kind_to_legacy_patch_rejected(self):
        brand_source = rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
        with self.assertRaises(rs.ResourceSourceError):
            rs.collection_resource_source_to_legacy_patch(brand_source)

    def test_max_twelve_manual_ids_cap(self):
        # Cap is 12 (same as the existing typed validator); the 13th trips it.
        ok = rs.collection_resource_source_from_settings({"collection_ids": list(range(1, 13))})
        self.assertEqual(len(ok.manual_ids), 12)
        with self.assertRaises(rs.ResourceSourceError):
            rs.collection_resource_source_from_settings({"collection_ids": list(range(1, 14))})

    def test_nonpositive_manual_id_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.collection_resource_source_from_settings({"collection_ids": [0]})
        with self.assertRaises(rs.ResourceSourceError):
            rs.collection_resource_source_from_settings({"collection_ids": [-3]})


class CollectionTilesRouterTests(SimpleTestCase):
    def test_collection_tiles_router_roundtrip_manual(self):
        source = rs.resource_source_from_section_settings("collection_tiles", {"collection_ids": [7, 3]})
        self.assertEqual(source.kind, "collection")
        self.assertEqual(source.manual_ids, (7, 3))
        patch = rs.resource_source_to_legacy_patch("collection_tiles", source)
        self.assertEqual(patch, {"collection_ids": [7, 3]})
        self.assertNotIn("source", patch)

    def test_collection_tiles_router_auto_all_active(self):
        source = rs.resource_source_from_section_settings("collection_tiles", {"collection_ids": []})
        self.assertEqual(source, rs.ResourceSource(kind="collection", mode="auto", auto_rule="all_active"))
        patch = rs.resource_source_to_legacy_patch("collection_tiles", source)
        self.assertEqual(patch, {"collection_ids": []})

    def test_collection_tiles_incompatible_kind_rejected(self):
        brand_source = rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
        with self.assertRaises(rs.ResourceSourceError):
            rs.resource_source_to_legacy_patch("collection_tiles", brand_source)


class GenericSectionAdapterTests(SimpleTestCase):
    def test_product_section_router(self):
        typed = rs.resource_source_from_section_settings(
            "product_section", {"data_source": "newest", "source_id": None, "product_ids": []},
        )
        self.assertEqual(typed.kind, "product")
        patch = rs.resource_source_to_legacy_patch("product_section", typed)
        self.assertEqual(patch, {"data_source": "newest", "source_id": None, "product_ids": []})

    def test_brand_carousel_router(self):
        typed = rs.resource_source_from_section_settings("brand_carousel", {"brand_ids": [1, 2]})
        self.assertEqual(typed.kind, "brand")
        patch = rs.resource_source_to_legacy_patch("brand_carousel", typed)
        self.assertEqual(patch, {"brand_ids": [1, 2]})

    def test_unknown_section_key_rejected(self):
        with self.assertRaises(rs.ResourceSourceError):
            rs.resource_source_from_section_settings("hero_banner", {})
        with self.assertRaises(rs.ResourceSourceError):
            rs.resource_source_to_legacy_patch(
                "hero_banner", rs.ResourceSource(kind="product", mode="auto", auto_rule="newest"),
            )

    def test_incompatible_kind_rejected(self):
        brand_source = rs.ResourceSource(kind="brand", mode="auto", auto_rule="all_active")
        with self.assertRaises(rs.ResourceSourceError):
            rs.resource_source_to_legacy_patch("product_section", brand_source)


# ---------------------------------------------------------------------------
# Schema-bridge / wrapper-preservation / R3-compatibility proofs — these only
# go GREEN once section_registry.py registers PRODUCT_SECTION_SCHEMA and
# BRAND_CAROUSEL_SCHEMA (with the "source" field) and wires _with_resource_source.
# ---------------------------------------------------------------------------


class SchemaBridgeTests(TestCase):
    def test_product_definition_has_settings_schema_with_one_source_field(self):
        definition = section_registry.get_definition("product_section")
        self.assertIsNotNone(definition.settings_schema)
        source_fields = [f for f in definition.settings_schema.fields if f.field_type == "resource_source"]
        self.assertEqual(len(source_fields), 1)
        self.assertEqual(source_fields[0].key, "source")

    def test_brand_definition_has_settings_schema_with_exactly_one_source_field(self):
        definition = section_registry.get_definition("brand_carousel")
        self.assertIsNotNone(definition.settings_schema)
        source_fields = [f for f in definition.settings_schema.fields if f.field_type == "resource_source"]
        self.assertEqual(len(source_fields), 1)
        self.assertEqual(source_fields[0].key, "source")

    def test_product_source_patch_cleans_to_legacy_keys_only(self):
        definition = section_registry.get_definition("product_section")
        current = definition.default_settings()
        patch = {
            "source": {
                "kind": "product", "mode": "auto", "auto_rule": "by_category",
                "auto_parameters": {"source_id": 17}, "manual_ids": [],
            },
        }
        cleaned = clean_section_schema_patch(definition, patch, current)
        self.assertEqual(cleaned["data_source"], "category")
        self.assertEqual(cleaned["source_id"], 17)
        self.assertEqual(cleaned["product_ids"], [])
        self.assertNotIn("source", cleaned)

    def test_brand_source_patch_cleans_to_legacy_keys_only(self):
        definition = section_registry.get_definition("brand_carousel")
        current = definition.default_settings()
        patch = {
            "source": {
                "kind": "brand", "mode": "manual", "auto_rule": None,
                "auto_parameters": {}, "manual_ids": [7, 3],
            },
        }
        cleaned = clean_section_schema_patch(definition, patch, current)
        self.assertEqual(cleaned["brand_ids"], [7, 3])
        self.assertNotIn("source", cleaned)


    def test_collection_definition_has_settings_schema_with_exactly_one_source_field(self):
        definition = section_registry.get_definition("collection_tiles")
        self.assertIsNotNone(definition.settings_schema)
        source_fields = [f for f in definition.settings_schema.fields if f.field_type == "resource_source"]
        self.assertEqual(len(source_fields), 1)
        self.assertEqual(source_fields[0].key, "source")

    def test_collection_source_patch_cleans_to_legacy_keys_only(self):
        definition = section_registry.get_definition("collection_tiles")
        current = definition.default_settings()
        patch = {
            "source": {
                "kind": "collection", "mode": "manual", "auto_rule": None,
                "auto_parameters": {}, "manual_ids": [7, 3],
            },
        }
        cleaned = clean_section_schema_patch(definition, patch, current)
        self.assertEqual(cleaned["collection_ids"], [7, 3])
        self.assertNotIn("source", cleaned)


class WrapperPreservationTests(TestCase):
    def test_product_source_patch_preserves_other_wrapper_blocks(self):
        definition = section_registry.get_definition("product_section")
        current = definition.default_settings()
        for block_key in ("responsive", "destination", "card", "motion", "background", "spacing"):
            self.assertIn(block_key, current)

        patch = {"source": {
            "kind": "product", "mode": "manual", "auto_rule": None,
            "auto_parameters": {}, "manual_ids": [7, 3],
        }}
        cleaned = clean_section_schema_patch(definition, patch, current)

        for block_key in ("responsive", "destination", "card", "motion", "background", "spacing"):
            self.assertEqual(cleaned[block_key], current[block_key])
        self.assertEqual(cleaned["data_source"], "manual")
        self.assertEqual(cleaned["product_ids"], [7, 3])

    def test_brand_source_patch_preserves_other_wrapper_blocks(self):
        definition = section_registry.get_definition("brand_carousel")
        current = definition.default_settings()
        for block_key in ("responsive", "destination", "motion", "background", "spacing"):
            self.assertIn(block_key, current)

        patch = {"source": {
            "kind": "brand", "mode": "auto", "auto_rule": "all_active",
            "auto_parameters": {}, "manual_ids": [],
        }}
        cleaned = clean_section_schema_patch(definition, patch, current)
        for block_key in ("responsive", "destination", "motion", "background", "spacing"):
            self.assertEqual(cleaned[block_key], current[block_key])
        self.assertEqual(cleaned["brand_ids"], [])


    def test_collection_source_patch_preserves_tile_style_variant_marker(self):
        # tile_style is collection_tiles' variant marker — a source-only patch
        # must carry the dormant/stored variant forward untouched.
        definition = section_registry.get_definition("collection_tiles")
        current = {**definition.default_settings(), "tile_style": "carousel", "title": "کالکشن‌ها"}
        patch = {"source": {
            "kind": "collection", "mode": "auto", "auto_rule": "all_active",
            "auto_parameters": {}, "manual_ids": [],
        }}
        cleaned = clean_section_schema_patch(definition, patch, current)
        self.assertEqual(cleaned["tile_style"], "carousel")
        self.assertEqual(cleaned["title"], "کالکشن‌ها")
        self.assertEqual(cleaned["collection_ids"], [])
        self.assertNotIn("source", cleaned)


class WrapperWithoutSourceKeyPreservesLegacyBehaviorTests(TestCase):
    def test_product_validate_without_source_key_behaves_as_before(self):
        definition = section_registry.get_definition("product_section")
        raw = {"data_source": "best_sellers", "item_limit": 12, "display_mode": "grid", "show_view_all": False}
        result = definition.validate_settings(raw)
        self.assertEqual(result["data_source"], "best_sellers")
        self.assertNotIn("source", result)

    def test_brand_validate_without_source_key_behaves_as_before(self):
        definition = section_registry.get_definition("brand_carousel")
        raw = {"brand_ids": [5, 6], "display_mode": "carousel"}
        result = definition.validate_settings(raw)
        self.assertEqual(result["brand_ids"], [5, 6])
        self.assertNotIn("source", result)

    def test_collection_validate_without_source_key_behaves_as_before(self):
        definition = section_registry.get_definition("collection_tiles")
        raw = {"collection_ids": [5, 6], "tile_style": "carousel", "title": "x"}
        result = definition.validate_settings(raw)
        self.assertEqual(result["collection_ids"], [5, 6])
        self.assertEqual(result["tile_style"], "carousel")
        self.assertNotIn("source", result)


class DefaultSettingsShapeTests(TestCase):
    def test_product_default_settings_has_no_source_key(self):
        definition = section_registry.get_definition("product_section")
        self.assertNotIn("source", definition.default_settings())

    def test_brand_default_settings_has_no_source_key(self):
        definition = section_registry.get_definition("brand_carousel")
        self.assertNotIn("source", definition.default_settings())

    def test_collection_default_settings_has_no_source_key(self):
        definition = section_registry.get_definition("collection_tiles")
        self.assertNotIn("source", definition.default_settings())


class R3CompatibilityTests(SimpleTestCase):
    def test_legacy_product_validator_unaffected_by_schema(self):
        result = section_registry._validate_product_section_settings({
            "data_source": "manual", "product_ids": [7, 3], "item_limit": 8,
            "display_mode": "carousel", "show_view_all": True,
        })
        self.assertEqual(result["data_source"], "manual")
        self.assertEqual(result["product_ids"], [7, 3])
        self.assertNotIn("source", result)

    def test_legacy_brand_validator_unaffected_by_schema(self):
        result = section_registry._validate_brand_carousel_settings(
            {"brand_ids": [7, 3, 9], "display_mode": "grid"},
        )
        self.assertEqual(result["brand_ids"], [7, 3, 9])
        self.assertNotIn("source", result)

    def test_legacy_collection_validator_unaffected_by_schema(self):
        result = section_registry._validate_collection_tiles_settings(
            {"collection_ids": [7, 3, 9], "tile_style": "grid"},
        )
        self.assertEqual(result["collection_ids"], [7, 3, 9])
        self.assertNotIn("source", result)
