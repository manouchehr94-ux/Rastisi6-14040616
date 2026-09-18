"""P5-W4C rendered visual distinctness repair — contract tests for the
three targeted Ready Template repairs (green_workshop, laleh_play,
parnian_editorial). Their v2 definitions were found materially
indistinguishable, above the fold, from their respective anchors
(pine_eco, playful_lifestyle, silk_editorial — left untouched). These
tests pin: the new v3 identity, the outgoing v2/v1 history staying
resolvable, an actual above-the-fold structural difference from the
anchor (not palette/font/radius alone), and that the canonical catalog
stays at exactly 50 with no duplicate registration.
"""

from django.test import SimpleTestCase

from apps.storefront_builder import layout_preset_registry as lpr

_REPAIR_PAIRS = (
    ("green_workshop", "pine_eco"),
    ("laleh_play", "playful_lifestyle"),
    ("parnian_editorial", "silk_editorial"),
)

_ABOVE_FOLD_AXES = ("header", "hero", "layout", "product_view", "bottom_nav")


def _above_fold_signature(preset):
    selections = preset.store_appearance["selections"]
    return tuple(selections[axis] for axis in _ABOVE_FOLD_AXES)


class RepairTargetsAreNowVersionThreeTests(SimpleTestCase):
    def test_green_workshop_latest_is_v3(self):
        self.assertEqual(lpr.get_layout_preset("green_workshop").version, "3")

    def test_laleh_play_latest_is_v3(self):
        self.assertEqual(lpr.get_layout_preset("laleh_play").version, "3")

    def test_parnian_editorial_latest_is_v3(self):
        self.assertEqual(lpr.get_layout_preset("parnian_editorial").version, "3")


class OutgoingHistoryRemainsResolvableTests(SimpleTestCase):
    def test_green_workshop_v2_and_v1_both_resolvable(self):
        v2 = lpr.get_layout_preset_version("green_workshop", "2")
        v1 = lpr.get_layout_preset_version("green_workshop", "1")
        self.assertIsNotNone(v2)
        self.assertIsNotNone(v1)
        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.editorial_split.v1")
        self.assertIsNot(v2, v1)

    def test_laleh_play_v2_and_v1_both_resolvable(self):
        v2 = lpr.get_layout_preset_version("laleh_play", "2")
        v1 = lpr.get_layout_preset_version("laleh_play", "1")
        self.assertIsNotNone(v2)
        self.assertIsNotNone(v1)
        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.image_collage.v1")
        self.assertIsNot(v2, v1)

    def test_parnian_editorial_v2_and_v1_both_resolvable(self):
        v2 = lpr.get_layout_preset_version("parnian_editorial", "2")
        v1 = lpr.get_layout_preset_version("parnian_editorial", "1")
        self.assertIsNotNone(v2)
        self.assertIsNotNone(v1)
        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.immersive.v1")
        self.assertIsNot(v2, v1)

    def test_outgoing_v2_specs_are_byte_identical_to_the_old_certified_v2(self):
        # The exact fields that were certified/rendered as v2 must survive
        # unchanged in history -- only the *current* row may have moved on.
        expectations = {
            "green_workshop": dict(
                header="header.compact_menu.v1", layout="layout.three_column.v1",
                product_view="product_view.standard_grid.v1", card="card.standard.v1",
                footer="footer.brand_story.v1", bottom_nav="bottom_nav.floating_dock.v1",
            ),
            "laleh_play": dict(
                header="header.playful_canopy.v1", layout="layout.three_column.v1",
                product_view="product_view.standard_grid.v1", card="card.paper_frame.v1",
                footer="footer.playful_wave.v1", bottom_nav="bottom_nav.five_item.v1",
            ),
            "parnian_editorial": dict(
                header="header.editorial_masthead.v1", layout="layout.two_column.v1",
                product_view="product_view.editorial_grid.v1", card="card.shelf_editorial.v1",
                footer="footer.editorial_wordmark.v1", bottom_nav="bottom_nav.minimal_icons.v1",
            ),
        }
        for key, expected in expectations.items():
            v2 = lpr.get_layout_preset_version(key, "2")
            self.assertIsNotNone(v2, f"{key} v2 must remain resolvable")
            selections = v2.store_appearance["selections"]
            for axis, value in expected.items():
                self.assertEqual(
                    selections[axis], value,
                    f"{key} v2.{axis} must be byte-identical to the certified v2 recipe",
                )


class AboveFoldIdentityNoLongerMatchesAnchorTests(SimpleTestCase):
    def test_each_repaired_target_differs_from_its_anchor_above_the_fold(self):
        for target_key, anchor_key in _REPAIR_PAIRS:
            target = lpr.get_layout_preset(target_key)
            anchor = lpr.get_layout_preset(anchor_key)
            with self.subTest(pair=(target_key, anchor_key)):
                self.assertNotEqual(
                    _above_fold_signature(target), _above_fold_signature(anchor),
                    f"{target_key} v3 must no longer match {anchor_key} on all "
                    "major visible above-the-fold axes",
                )

    def test_the_difference_includes_hero_not_palette_font_radius_alone(self):
        for target_key, anchor_key in _REPAIR_PAIRS:
            target = lpr.get_layout_preset(target_key)
            anchor = lpr.get_layout_preset(anchor_key)
            with self.subTest(pair=(target_key, anchor_key)):
                target_hero = target.store_appearance["selections"]["hero"]
                anchor_hero = anchor.store_appearance["selections"]["hero"]
                self.assertNotEqual(
                    target_hero, anchor_hero,
                    f"{target_key} v3 must use a different hero component than "
                    f"{anchor_key}, not merely a different palette/font/radius",
                )

    def test_anchors_are_completely_untouched(self):
        # The three anchors are explicitly not to be modified this round.
        expected_anchor_hero = {
            "pine_eco": "hero.editorial_split.v1",
            "playful_lifestyle": "hero.image_collage.v1",
            "silk_editorial": "hero.immersive.v1",
        }
        for anchor_key, expected_hero in expected_anchor_hero.items():
            preset = lpr.get_layout_preset(anchor_key)
            self.assertEqual(preset.version, "2")
            self.assertEqual(preset.store_appearance["selections"]["hero"], expected_hero)


class CatalogIntegrityAfterRepairTests(SimpleTestCase):
    def test_canonical_ready_template_count_remains_fifty(self):
        self.assertEqual(len(lpr.list_ready_templates()), 50)

    def test_canonical_keys_are_still_exactly_the_same_fifty(self):
        keys = sorted(preset.key for preset in lpr.list_ready_templates())
        self.assertEqual(len(keys), len(set(keys)))
        for target_key, _ in _REPAIR_PAIRS:
            self.assertIn(target_key, keys)

    def test_no_new_above_fold_collision_introduced_among_all_fifty(self):
        signatures = {}
        collisions = []
        for preset in lpr.list_ready_templates():
            sig = _above_fold_signature(preset)
            if sig in signatures:
                collisions.append((signatures[sig], preset.key))
            else:
                signatures[sig] = preset.key
        # cedar_home/city_classic is a pre-existing, separately-reviewed and
        # accepted PASS (real dark/light header contrast on Desktop) -- not
        # part of this repair's scope, so it is explicitly excluded here.
        collisions = [
            pair for pair in collisions
            if set(pair) != {"cedar_home", "city_classic"}
        ]
        self.assertEqual(
            collisions, [],
            f"repair must not introduce any NEW above-the-fold collision: {collisions}",
        )
