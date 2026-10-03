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

# Pre-existing (not introduced by this repair, not part of this round's
# authorized scope) 4-axis near-collisions that share the same rendered
# hero_style -- discovered as a side effect of building the stricter
# check below. Recorded here, not silently ignored, and explicitly
# excluded from the "no NEW collision" assertions until a future,
# separately-authorized round addresses them.
_PRE_EXISTING_OUT_OF_SCOPE_4AXIS_COLLISIONS = frozenset({
    frozenset({"cedar_home", "city_classic"}),
    frozenset({"handmade_luxe", "mist_quiet"}),
    frozenset({"tower_department", "harbor_imports"}),
})


def _above_fold_signature(preset):
    selections = preset.store_appearance["selections"]
    return tuple(selections[axis] for axis in _ABOVE_FOLD_AXES)


def _rendered_hero_style(preset):
    """The REAL hero_style the hero_banner section actually renders with
    (read off the built preset's own pages["home"], not re-derived from a
    private mapping) -- this is what the browser actually shows, and is
    exactly the axis that let parnian_editorial's first repair attempt
    (hero=editorial_split) silently collide with artisan_grain's
    hero=typographic: both resolve to the same hero_style even though
    the two hero *keys* differ syntactically."""
    for entry in preset.pages.get("home", ()):
        if entry.section_key == "hero_banner":
            return entry.settings["hero_style"]
    return None


def _rendered_above_fold_signature(preset):
    """Header + REAL rendered hero_style (not the raw hero key) + layout
    + product_view -- deliberately excludes bottom_nav, which is a
    Mobile-only element invisible in the Desktop above-the-fold view.
    This is the stricter signature that actually caught the
    artisan_grain regression the raw-hero-key check missed."""
    selections = preset.store_appearance["selections"]
    return (
        selections["header"],
        _rendered_hero_style(preset),
        selections["layout"],
        selections["product_view"],
    )


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

    def test_no_new_rendered_hero_style_collision_among_all_fifty(self):
        # Code-review finding: a raw-hero-KEY-only check is insufficient --
        # different hero keys (e.g. "editorial_split" and "typographic")
        # can resolve to the identical rendered hero_style. This checks the
        # REAL rendered hero_style off each preset's own built pages, which
        # is what a browser actually shows.
        signatures = {}
        collisions = []
        for preset in lpr.list_ready_templates():
            sig = _rendered_above_fold_signature(preset)
            if sig in signatures:
                collisions.append(frozenset({signatures[sig], preset.key}))
            else:
                signatures[sig] = preset.key
        new_collisions = [
            pair for pair in collisions
            if pair not in _PRE_EXISTING_OUT_OF_SCOPE_4AXIS_COLLISIONS
        ]
        self.assertEqual(
            new_collisions, [],
            "repair must not introduce any NEW rendered-hero-style collision "
            f"(pre-existing, out-of-scope ones are allowed): {new_collisions}",
        )
        for target_key, anchor_key in _REPAIR_PAIRS:
            with self.subTest(pair=(target_key, anchor_key)):
                self.assertNotEqual(
                    _rendered_hero_style(lpr.get_layout_preset(target_key)),
                    _rendered_hero_style(lpr.get_layout_preset(anchor_key)),
                    f"{target_key} must render a genuinely different hero_style "
                    f"than {anchor_key}, not just a different hero key",
                )


class AppearanceHeroStyleIsIntentionallyRecomputedTests(SimpleTestCase):
    """The page-level appearance.hero_style (tall/split/wide) is derived
    from the hero family independently of the hero_banner's own
    hero_style. Swapping hero families changes this too -- pinned here
    explicitly so it's a verified, intentional part of the repair rather
    than an unverified side effect (code-review finding)."""

    def test_green_workshop_appearance_hero_style_unchanged_group(self):
        # editorial_split and product_focus are both in the "split" group.
        preset = lpr.get_layout_preset("green_workshop")
        self.assertEqual(preset.appearance["hero_style"], "split")

    def test_laleh_play_appearance_hero_style_moves_tall_to_wide(self):
        # image_collage ("tall") -> typographic ("wide").
        preset = lpr.get_layout_preset("laleh_play")
        self.assertEqual(preset.appearance["hero_style"], "wide")

    def test_parnian_editorial_appearance_hero_style_moves_tall_to_beauty_split_group(self):
        # immersive ("tall") -> product_focus ("split").
        preset = lpr.get_layout_preset("parnian_editorial")
        self.assertEqual(preset.appearance["hero_style"], "split")
