"""P5-W4B — 50-Template Curation contract tests.

Approved design head 75decc08d9569b45744930044cc29a4dce65bb43:
docs/superpowers/specs/2026-09-16-phase5-w4b-50-template-curation-design.md
docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/w4b_curation_inventory.md §15/§16

21 curated keys bump version "1" -> "2" with exactly one new section
appended to their Home composition (inserted immediately before
``newsletter`` for the 7 keys whose composition already ends there). The
outgoing version-1 definition is preserved byte-for-byte in
``_HISTORICAL_SPECS`` and resolvable via ``get_layout_preset_version``.
"""

import dataclasses
import hashlib

from django.test import SimpleTestCase, TestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry
from apps.storefront_builder.a8_ready_templates import A8_READY_TEMPLATES
from apps.storefront_builder.tests.test_a8_ready_template_catalog import (
    FORBIDDEN_DATA_KEYS,
    _walk,
)

# Captured once, before any production edit, at git HEAD
# fac7e3653ad07d5df5c9e4210137171134d7f90f (apps/ still byte-identical to
# the certified 707dd631e851bdd13173bf3950489142f3e526b1 base). See
# docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/00_certified_w4a_fingerprints.md.
# NEVER regenerate these after curation is applied.
CERTIFIED_W4A_FINGERPRINT = {
    ('premium_leather_noir', '1'): 'e85be9baa87fa763de5bd42afe93d99b97e39e0272904d62de980cf5d35436bb',
    ('artisan_grain', '1'): '925876abfe18d9c98ca0f27c141e97db2e863314a80b28c58c7a9baeec85adf3',
    ('coastal_product', '1'): '57c28aa59c54bad100ff8135e70c869becf3afcdcc479688955307e1549cdb5f',
    ('handmade_luxe', '1'): '20c0a51ccbd43fc5463e8d35aa9dc11138e0016de3838875dec494f197388049',
    ('watchmaker_round', '1'): 'e5289689e89d7e9499e58d6c3092a966940f7565d0da61299e76ded05b2e58a3',
    ('horizon_story', '1'): 'e1d735561d53de0020a5a1edf9d84da57c59914d01ba4f05abcd3d358269bf7b',
    ('silk_editorial', '1'): '191ae7f1792d38a44b1e2015ee009acd30e5f79a43834dca986cbba6f65753bb',
    ('city_classic', '1'): '3b0e5ffd5fb4b81a28e3c5d0103ef999bdfa3094a32e71fcc9f14d81e7729949',
    ('kamand_artisan', '1'): 'e51f203924bcf7e712e649e22755a9a6513f7b4bd7c0db383072685fb2de60a7',
    ('parnian_editorial', '1'): '01239db408071a37fc4839f0ebec82c1f4c1d62ed8ea8aa646a0c106431b562b',
    ('niloufar_glass', '1'): '1c7673d5add223a809486f9886704acf0b8e4f94d05a29ea83c1f796056c219a',
    ('beauty_dew', '1'): '8569ba1aa10d45e27bfd14a2d22ecd86edebc78f37b2b162e16988a10c7a97bc',
    ('laleh_play', '1'): '4772d1e19c5bcb31258050a7d71f2486130f887ba9f94e6fce2f6cbb5cce0aaa',
    ('almas_luxury', '1'): '8262096804f5b281c907343723d66f8716efe43c5e175bc3bca28614cc333cf8',
    ('green_workshop', '1'): '99576f38fe583ac46dcc5253a08d86f0bd002f4b917b01a021a9163175dddedb',
    ('pine_eco', '1'): '41c6ab3c83b50b4e0169b8f02906239ee885a49dae3f56fd551f7eb04db78b15',
    ('mirror_beauty', '1'): '6e29eec91232a00e040ae0fe2646ec85c6744220bfa6035411ea74784c5b2488',
    ('cedar_home', '1'): '4585f014a7d40ce50abe6070a917eaf773fb22341da244f3fd2aeaf66d9be5ef',
    ('simorgh_market', '1'): '1a5a9c4f026ae0c8f12769d6870dde90cadc7e0eba53c4191e3591ec7bf9cd20',
    ('rayan_tech', '1'): '1614c1659f58ae11c634b815952b6258553475b00d8d03e6724a4e680fb4b2e0',
    ('harbor_imports', '1'): 'c9e65804bf919bf0ecee57cef6f4f4d126c6bba20659752f18c5022c7dbd417f',
}

# Exact approved final Home section_key sequence per curated key
# (inventory §15, "New Home section_key sequence" column).
EXPECTED_NEW_HOME_SEQUENCE = {
    "premium_leather_noir": ("hero_banner", "category_grid", "product_section", "image_text", "brand_carousel"),
    "artisan_grain": ("hero_banner", "category_grid", "product_section", "image_text", "collection_tiles"),
    "coastal_product": ("hero_banner", "category_grid", "product_section", "image_text", "collection_tiles"),
    "handmade_luxe": ("hero_banner", "category_grid", "product_section", "image_text", "brand_carousel"),
    "watchmaker_round": ("hero_banner", "category_grid", "product_section", "image_text", "brand_carousel"),
    "horizon_story": ("hero_banner", "category_grid", "product_section", "image_text", "story_rail"),
    "silk_editorial": ("hero_banner", "category_grid", "product_section", "image_text", "collection_tiles"),
    "city_classic": ("hero_banner", "category_grid", "product_section", "image_text", "collection_tiles"),
    "kamand_artisan": ("hero_banner", "category_grid", "product_section", "image_text", "story_rail"),
    "parnian_editorial": ("hero_banner", "category_grid", "product_section", "image_text", "story_rail"),
    "niloufar_glass": ("hero_banner", "category_grid", "product_section", "collection_tiles", "newsletter"),
    "beauty_dew": ("hero_banner", "category_grid", "product_section", "story_rail", "newsletter"),
    "laleh_play": ("hero_banner", "category_grid", "product_section", "brand_carousel", "newsletter"),
    "almas_luxury": ("hero_banner", "category_grid", "product_section", "story_rail", "newsletter"),
    "green_workshop": ("hero_banner", "category_grid", "product_section", "image_text", "brand_carousel", "newsletter"),
    "pine_eco": ("hero_banner", "category_grid", "product_section", "image_text", "collection_tiles", "newsletter"),
    "mirror_beauty": ("hero_banner", "category_grid", "product_section", "image_text", "story_rail", "newsletter"),
    "cedar_home": ("hero_banner", "category_grid", "product_section", "trust_features", "collection_tiles"),
    "simorgh_market": ("hero_banner", "category_grid", "product_section", "trust_features", "brand_carousel"),
    "rayan_tech": ("hero_banner", "category_grid", "product_section", "trust_features", "story_rail"),
    "harbor_imports": ("hero_banner", "category_grid", "product_section", "product_section", "trust_features", "brand_carousel"),
}

# Exact certified pre-W4B (version "1") Home section_key sequence per
# curated key — the byte-for-byte skeleton the frozen historical row must
# still reproduce.
CERTIFIED_OLD_HOME_SEQUENCE = {
    "premium_leather_noir": ("hero_banner", "category_grid", "product_section", "image_text"),
    "artisan_grain": ("hero_banner", "category_grid", "product_section", "image_text"),
    "coastal_product": ("hero_banner", "category_grid", "product_section", "image_text"),
    "handmade_luxe": ("hero_banner", "category_grid", "product_section", "image_text"),
    "watchmaker_round": ("hero_banner", "category_grid", "product_section", "image_text"),
    "horizon_story": ("hero_banner", "category_grid", "product_section", "image_text"),
    "silk_editorial": ("hero_banner", "category_grid", "product_section", "image_text"),
    "city_classic": ("hero_banner", "category_grid", "product_section", "image_text"),
    "kamand_artisan": ("hero_banner", "category_grid", "product_section", "image_text"),
    "parnian_editorial": ("hero_banner", "category_grid", "product_section", "image_text"),
    "niloufar_glass": ("hero_banner", "category_grid", "product_section", "newsletter"),
    "beauty_dew": ("hero_banner", "category_grid", "product_section", "newsletter"),
    "laleh_play": ("hero_banner", "category_grid", "product_section", "newsletter"),
    "almas_luxury": ("hero_banner", "category_grid", "product_section", "newsletter"),
    "green_workshop": ("hero_banner", "category_grid", "product_section", "image_text", "newsletter"),
    "pine_eco": ("hero_banner", "category_grid", "product_section", "image_text", "newsletter"),
    "mirror_beauty": ("hero_banner", "category_grid", "product_section", "image_text", "newsletter"),
    "cedar_home": ("hero_banner", "category_grid", "product_section", "trust_features"),
    "simorgh_market": ("hero_banner", "category_grid", "product_section", "trust_features"),
    "rayan_tech": ("hero_banner", "category_grid", "product_section", "trust_features"),
    "harbor_imports": ("hero_banner", "category_grid", "product_section", "product_section", "trust_features"),
}

CURATED_KEYS = tuple(EXPECTED_NEW_HOME_SEQUENCE)
assert len(CURATED_KEYS) == 21

NEWSLETTER_TERMINAL_CURATED_KEYS = (
    "niloufar_glass", "beauty_dew", "laleh_play", "almas_luxury",
    "green_workshop", "pine_eco", "mirror_beauty",
)
assert len(NEWSLETTER_TERMINAL_CURATED_KEYS) == 7

# section_key each curated key is approved to gain (inventory §15/design §8).
EXPECTED_ADDED_SECTION = {
    "premium_leather_noir": "brand_carousel", "artisan_grain": "collection_tiles",
    "coastal_product": "collection_tiles", "handmade_luxe": "brand_carousel",
    "watchmaker_round": "brand_carousel", "horizon_story": "story_rail",
    "silk_editorial": "collection_tiles", "city_classic": "collection_tiles",
    "kamand_artisan": "story_rail", "parnian_editorial": "story_rail",
    "niloufar_glass": "collection_tiles", "beauty_dew": "story_rail",
    "laleh_play": "brand_carousel", "almas_luxury": "story_rail",
    "green_workshop": "brand_carousel", "pine_eco": "collection_tiles",
    "mirror_beauty": "story_rail", "cedar_home": "collection_tiles",
    "simorgh_market": "brand_carousel", "rayan_tech": "story_rail",
    "harbor_imports": "brand_carousel",
}

REJECTED_MECHANISMS = frozenset({"blog_posts", "promo_cards", "image_slider", "trust_features"})


def _deep_freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((k, _deep_freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_deep_freeze(v) for v in value))
    return value


def fingerprint(preset) -> str:
    frozen = _deep_freeze(dataclasses.asdict(preset))
    return hashlib.sha256(repr(frozen).encode()).hexdigest()


class ExactFiftyLatestCatalogTests(SimpleTestCase):
    def test_a8_ready_templates_is_exactly_fifty(self):
        self.assertEqual(len(A8_READY_TEMPLATES), 50)

    def test_list_ready_templates_is_exactly_fifty(self):
        self.assertEqual(len(lpr.list_ready_templates()), 50)


# P5-W4C rendered-visual-distinctness repair (source HEAD
# 6074424b99cd922a28fe3187fef10a53931e535b) intentionally bumped exactly
# these 3 of the 21 W4B-curated keys from "2" to "3" to fix a real
# above-the-fold rendered-hero collision against their pair anchor. See
# apps/storefront_builder/tests/test_a8_visual_distinctness_repair.py.
_W4C_VISUAL_REPAIR_VERSION_THREE_KEYS = frozenset({
    "green_workshop", "laleh_play", "parnian_editorial",
})


class ExplicitVersionMapTests(SimpleTestCase):
    def test_all_21_curated_keys_are_now_version_two(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                latest = lpr.get_layout_preset(key)
                self.assertIsNotNone(latest, key)
                expected_version = (
                    "3" if key in _W4C_VISUAL_REPAIR_VERSION_THREE_KEYS else "2"
                )
                self.assertEqual(latest.version, expected_version, key)

    def test_no_other_ready_template_received_an_unintended_version_bump(self):
        expected_non_curated_versions = {
            preset.key: preset.version
            for preset in A8_READY_TEMPLATES
            if preset.key not in CURATED_KEYS
        }
        for key, version in expected_non_curated_versions.items():
            with self.subTest(key=key):
                self.assertNotEqual(version, "0", key)  # sanity: versions are real
        # tower_department (C10's untouched side) must stay at "1".
        self.assertEqual(lpr.get_layout_preset("tower_department").version, "1")


class HistoricalPreservationTests(SimpleTestCase):
    def test_historical_v1_resolves_and_is_not_the_latest_object(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                latest = lpr.get_layout_preset(key)
                historical = lpr.get_layout_preset_version(key, "1")
                self.assertIsNotNone(historical, key)
                self.assertEqual(historical.version, "1", key)
                self.assertIsNot(latest, historical, key)

    def test_historical_v1_home_skeleton_matches_certified_pre_w4b_source(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                historical = lpr.get_layout_preset_version(key, "1")
                actual = tuple(entry.section_key for entry in historical.pages["home"])
                self.assertEqual(actual, CERTIFIED_OLD_HOME_SEQUENCE[key], key)

    def test_full_historical_fingerprint_matches_certified_w4a_capture(self):
        """Proves byte-for-byte preservation of the WHOLE LayoutPresetDefinition
        (not just the Home section-key sequence) against the fingerprint
        captured before any production edit — see
        docs/qa_evidence/.../w4b_template_curation/implementation/00_certified_w4a_fingerprints.md."""
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                historical = lpr.get_layout_preset_version(key, "1")
                self.assertEqual(
                    fingerprint(historical),
                    CERTIFIED_W4A_FINGERPRINT[(key, "1")],
                    key,
                )


class HistoricalForbiddenPayloadScanTests(SimpleTestCase):
    """Regression contract for the _HISTORICAL_SPECS preservation mechanism
    itself — not a suspicion that the old recipes are unsafe. Reuses the
    exact same walk/prototype-ID checks
    test_a8_ready_template_catalog.py::test_recipes_contain_no_tenant_executable_or_prototype_payload
    already performs, applied to the 21 newly-preserved historical (v1)
    definitions, which list_ready_templates() never reaches."""

    def test_historical_v1_definitions_contain_no_forbidden_payload(self):
        import json
        import re

        prototype_id = re.compile(
            r"(?:^|[.\s])(h\d+|x\d+|c-[a-z]+|g\d+|m(?:fab|dock|glass|icon|big|\d+))(?:$|[.\s])"
        )
        for key in CURATED_KEYS:
            historical = lpr.get_layout_preset_version(key, "1")
            with self.subTest(preset=key):
                primitive = dataclasses.asdict(historical)
                for mapping in _walk(primitive):
                    self.assertFalse(FORBIDDEN_DATA_KEYS.intersection(mapping), mapping)
                serialized = json.dumps(primitive, ensure_ascii=False).lower()
                self.assertNotIn("<script", serialized)
                self.assertNotIn("javascript:", serialized)
                self.assertNotIn("{%", serialized)
                self.assertNotIn("{{", serialized)
                self.assertIsNone(prototype_id.search(serialized), key)


class ExactCompositionMatrixTests(SimpleTestCase):
    def test_latest_v2_home_sequence_matches_approved_matrix_exactly(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                latest = lpr.get_layout_preset(key)
                actual = tuple(entry.section_key for entry in latest.pages["home"])
                self.assertEqual(actual, EXPECTED_NEW_HOME_SEQUENCE[key], key)

    def test_added_section_is_exactly_the_approved_one_and_appears_once(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                old_sequence = CERTIFIED_OLD_HOME_SEQUENCE[key]
                new_sequence = EXPECTED_NEW_HOME_SEQUENCE[key]
                added = [s for s in new_sequence if s not in old_sequence]
                self.assertEqual(added, [EXPECTED_ADDED_SECTION[key]], key)
                # non-redundant: the added section did not already exist in
                # this exact key's own pre-curation composition.
                self.assertNotIn(EXPECTED_ADDED_SECTION[key], old_sequence, key)

    def test_added_section_keys_are_registered_and_home_allowed(self):
        for key in CURATED_KEYS:
            section_key = EXPECTED_ADDED_SECTION[key]
            with self.subTest(key=key, section_key=section_key):
                self.assertTrue(section_registry.is_valid_section_key(section_key), section_key)
                self.assertTrue(
                    section_registry.is_section_allowed_on_page(section_key, "home"), section_key,
                )


class NewsletterTerminalContractTests(SimpleTestCase):
    def test_newsletter_stays_the_final_home_section_for_all_seven(self):
        for key in NEWSLETTER_TERMINAL_CURATED_KEYS:
            with self.subTest(key=key):
                preset = lpr.get_layout_preset(key)
                self.assertEqual(preset.pages["home"][-1].section_key, "newsletter", key)

    def test_added_section_is_immediately_before_newsletter(self):
        for key in NEWSLETTER_TERMINAL_CURATED_KEYS:
            with self.subTest(key=key):
                preset = lpr.get_layout_preset(key)
                sequence = [entry.section_key for entry in preset.pages["home"]]
                self.assertEqual(sequence[-2], EXPECTED_ADDED_SECTION[key], key)
                self.assertEqual(sequence[-1], "newsletter", key)


class CompositionTokenAllowlistTests(SimpleTestCase):
    def test_only_collection_tiles_is_a_genuinely_new_static_section_token(self):
        from apps.storefront_builder.a8_ready_templates import _STATIC_SECTIONS

        self.assertEqual(_STATIC_SECTIONS.get("collection_tiles"), "collection_tiles")
        # story_rail/brand_carousel must keep reusing the pre-existing tokens,
        # not gain a redundant new alias.
        self.assertEqual(_STATIC_SECTIONS.get("community_gallery"), "story_rail")
        self.assertEqual(_STATIC_SECTIONS.get("brands"), "brand_carousel")

    def test_no_speculative_token_added_for_a_rejected_mechanism(self):
        from apps.storefront_builder.a8_ready_templates import _STATIC_SECTIONS

        for rejected in ("blog_posts", "promo_cards", "image_slider"):
            self.assertNotIn(rejected, _STATIC_SECTIONS)


class RejectedMechanismsAbsentFromNewCurationTests(SimpleTestCase):
    def test_no_curated_key_gained_a_rejected_mechanism(self):
        for key in CURATED_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(EXPECTED_ADDED_SECTION[key], REJECTED_MECHANISMS, key)

    def test_pre_existing_trust_features_baseline_usage_is_untouched(self):
        """cedar_home/simorgh_market/rayan_tech/harbor_imports already had
        trust_features before W4B (tower_department's own cluster-mate
        pattern) — W4B must not have removed it, only appended after it."""
        for key in ("cedar_home", "simorgh_market", "rayan_tech", "harbor_imports"):
            with self.subTest(key=key):
                sequence = EXPECTED_NEW_HOME_SEQUENCE[key]
                self.assertIn("trust_features", sequence, key)


class DiversityContractTests(SimpleTestCase):
    def test_fifty_pairwise_unique_recipe_signatures(self):
        from apps.storefront_builder.storefront_appearance.inventory import recipe_signature

        presets = lpr.list_ready_templates()
        signatures = [recipe_signature(preset) for preset in presets]
        self.assertEqual(len(signatures), 50)
        self.assertEqual(len(set(signatures)), 50)


class AllFiftyCanonicalApplyRegressionTests(TestCase):
    """All-50 canonical apply/resolution regression — through the existing
    apply_preset authority only (no W4B-specific apply engine)."""

    def test_every_latest_ready_template_applies_through_the_canonical_path(self):
        from apps.stores.models import Store
        from apps.storefront_builder.services import layout_service as svc
        from apps.storefront_builder.services import preset_service

        store = Store.objects.get(slug="akhlaghi")
        presets = lpr.list_ready_templates()
        self.assertEqual(len(presets), 50)
        for preset in presets:
            with self.subTest(key=preset.key, version=preset.version):
                draft = svc.get_or_create_draft(store)
                preset_service.apply_preset(draft, preset)
                draft.refresh_from_db()
                self.assertGreater(draft.get_page("home").sections.count(), 0)
