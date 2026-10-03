# Exact source diff, 0898c31b..6074424b

Full diff across both repair commits (`316b7332` initial repair,
`6074424b` code-review correction), covering `a8_ready_templates.py`
(the only production file touched) and the two test files
(`test_a8_ready_template_catalog.py`'s `EXPECTED_LATEST_VERSIONS` pin,
`test_a8_visual_distinctness_repair.py`'s new contract tests).

```diff
diff --git a/apps/storefront_builder/a8_ready_templates.py b/apps/storefront_builder/a8_ready_templates.py
index 304080fc..87f06843 100644
--- a/apps/storefront_builder/a8_ready_templates.py
+++ b/apps/storefront_builder/a8_ready_templates.py
@@ -248,7 +248,14 @@ _SPECS = (
     _RecipeSpec("handmade_luxe", "2", "چرم دست", "editorial_row", "editorial_split", "three_column", "editorial_grid", "luxury_dark", "none", "subtle", "brand_story", "floating_dock", "theme-terracotta-cream", "Vazirmatn", "relaxed", 1100, 10, ("hero", "indexed_categories", "product_grid", "brand_story", "brands")),
     _RecipeSpec("niloufar_glass", "2", "نیلوفر", "floating_compact", "image_collage", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "centered", "raised_cart", "rose", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "collection_tiles", "newsletter")),
     _RecipeSpec("tool_finder", "1", "آچار", "marketplace_search", "none", "four_column", "standard_grid", "technical_spec", "none", "none", "marketplace_columns", "four_item", "navy", "Arial", "compact", 1320, 4, ("tile_categories", "product_grid", "trust_features")),
-    _RecipeSpec("green_workshop", "2", "سبزه", "compact_menu", "editorial_split", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "brands", "newsletter")),
+    # P5-W4C rendered visual distinctness repair -- v2 was materially
+    # indistinguishable from pine_eco above the fold (identical header,
+    # hero, layout, product_view, bottom_nav). v3 keeps green_workshop's
+    # own header/layout/card/footer/bottom_nav/palette/density unchanged
+    # and switches only the hero family (editorial_split -> product_focus)
+    # -- a genuinely different rendered hero component, not a palette/
+    # font/radius change. pine_eco itself is untouched.
+    _RecipeSpec("green_workshop", "3", "سبزه", "compact_menu", "product_focus", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "brands", "newsletter")),
     _RecipeSpec("tower_department", "1", "برج", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "marketplace_price", "sale", "dynamic", "marketplace_columns", "five_item", "theme-crimson-charcoal", "Vazirmatn", "compact", 1500, 8, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features")),
     _RecipeSpec("beauty_dew", "2", "شبنم", "floating_compact", "product_focus", "horizontal_rail", "carousel", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_rail", "community_gallery", "newsletter")),
     _RecipeSpec("fashion_promo_catalog", "8", "تندر", "promo_bar", "promo_bento", "dense_five", "dense_grid", "price_first", "sale", "dynamic", "marketplace_columns", "raised_cart", "magenta-pop", "Vazirmatn", "compact", 1500, 8, ("hero", "chip_categories", "sale_products", "product_grid")),
@@ -257,7 +264,14 @@ _SPECS = (
     _RecipeSpec("silk_editorial", "2", "ابریشم", "editorial_masthead", "immersive", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "atelier-ivory", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "brand_story", "collection_tiles")),
     _RecipeSpec("tuska_bento", "1", "توسکا", "compact_menu", "promo_bento", "bento_grid", "bento", "luxury_dark", "sale", "dynamic", "minimal", "four_item", "plum", "Vazirmatn", "normal", 1200, 12, ("hero", "tile_categories", "bento_products", "testimonials")),
     _RecipeSpec("rayan_tech", "2", "رایان", "marketplace_search", "product_focus", "four_column", "standard_grid", "technical_spec", "none", "subtle", "app_download", "four_item", "theme-midnight-electric", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "service_strip", "community_gallery")),
-    _RecipeSpec("laleh_play", "2", "لاله‌زار", "playful_canopy", "image_collage", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "brands", "newsletter")),
+    # P5-W4C rendered visual distinctness repair -- v2 was materially
+    # indistinguishable from playful_lifestyle above the fold (identical
+    # arch-cutout hero composition/photos/copy, identical header). v3
+    # keeps laleh_play's own header/layout/card/footer/bottom_nav/palette
+    # unchanged and switches only the hero family (image_collage ->
+    # typographic) -- a genuinely different rendered hero, still a bold
+    # playful headline treatment. playful_lifestyle itself is untouched.
+    _RecipeSpec("laleh_play", "3", "لاله‌زار", "playful_canopy", "typographic", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "brands", "newsletter")),
     _RecipeSpec("city_classic", "2", "شهر", "centered_brand", "editorial_split", "four_column", "standard_grid", "standard", "none", "subtle", "brand_story", "four_item", "uupm-professional-navy", "Vazirmatn", "normal", 1200, 8, ("hero", "circular_categories", "product_grid", "brand_story", "collection_tiles")),
     _RecipeSpec("collection_index", "1", "کلکسیون", "compact_drawer", "none", "catalog_list", "catalog_list", "catalog_index", "none", "none", "minimal", "minimal_icons", "catalog-colorful", "Arial", "compact", 1100, 0, ("indexed_categories", "product_list", "editorial_note")),
     _RecipeSpec("kamand_artisan", "2", "کمند", "overlay_transparent", "editorial_split", "three_column", "editorial_grid", "editorial_minimal", "none", "subtle", "brand_story", "floating_dock", "terracotta", "Vazirmatn", "relaxed", 1100, 6, ("hero", "indexed_categories", "product_grid", "brand_story", "community_gallery")),
@@ -274,7 +288,21 @@ _SPECS = (
     _RecipeSpec("charcoal_grill", "1", "زغال", "promo_bar", "product_focus", "four_column", "standard_grid", "bold_outline", "sale", "dynamic", "bold_columns", "wide_cart", "theme-graphite-orange", "Vazirmatn", "compact", 1200, 0, ("hero", "chip_categories", "product_grid", "sale_products")),
     _RecipeSpec("calligraphy_paper", "1", "خط", "compact_drawer", "immersive", "catalog_list", "catalog_list", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "mono", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_list", "brand_story")),
     _RecipeSpec("harbor_imports", "2", "بندر", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "shipping_label", "sale", "subtle", "marketplace_columns", "four_item", "navy", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features", "brands")),
-    _RecipeSpec("parnian_editorial", "2", "پرنیان", "editorial_masthead", "immersive", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "community_gallery")),
+    # P5-W4C rendered visual distinctness repair -- v2 was materially
+    # indistinguishable from silk_editorial above the fold (identical
+    # immersive hero panel/photo/headline/CTA, identical header). v3
+    # keeps parnian_editorial's own header/layout/card/footer/bottom_nav/
+    # palette unchanged and switches only the hero family (immersive ->
+    # product_focus) -- a genuinely different rendered hero, still an
+    # editorial/refined treatment. silk_editorial itself is untouched.
+    # NOTE: an earlier attempt used "editorial_split" here, but that
+    # resolves to the same rendered hero_style ("split") as
+    # artisan_grain's "typographic" hero while sharing the same header
+    # (editorial_masthead), layout (two_column) and product_view
+    # (editorial_grid) -- a code-review finding that would have silently
+    # recreated this exact defect against a different, unchecked sibling.
+    # product_focus avoids this (verified against all 50).
+    _RecipeSpec("parnian_editorial", "3", "پرنیان", "editorial_masthead", "product_focus", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "community_gallery")),
     _RecipeSpec("racer_tech", "1", "تک‌سوار", "promo_bar", "media_feature", "horizontal_rail", "carousel", "technical_spec", "sale", "dynamic", "marketplace_columns", "wide_cart", "uupm-gaming-neon", "Vazirmatn", "compact", 1320, 6, ("ticker", "hero", "chip_categories", "product_rail", "sale_products")),
     _RecipeSpec("ferdowsi_department", "1", "فردوسی", "centered_brand", "campaign_mosaic", "featured_split", "featured_wall", "marketplace_price", "sale", "subtle", "marketplace_columns", "five_item", "uupm-burgundy-gold", "Vazirmatn", "normal", 1320, 8, ("hero", "tile_categories", "featured_products", "product_grid", "brands", "trust_features")),
     _RecipeSpec("anniversary_mosaic", "1", "پنجاه", "editorial_row", "promo_bento", "bento_grid", "bento", "catalog_index", "sale", "dynamic", "editorial_wordmark", "floating_dock", "uupm-creative-pink", "Vazirmatn", "normal", 1320, 12, ("ticker", "hero", "circular_categories", "bento_products", "testimonials", "newsletter")),
@@ -323,6 +351,15 @@ _HISTORICAL_SPECS = (
     _RecipeSpec("mirror_beauty", "1", "آینه", "floating_compact", "product_focus", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "brand_story", "newsletter")),
     _RecipeSpec("harbor_imports", "1", "بندر", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "shipping_label", "sale", "subtle", "marketplace_columns", "four_item", "navy", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features")),
     _RecipeSpec("parnian_editorial", "1", "پرنیان", "editorial_masthead", "immersive", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story")),
+    # P5-W4C rendered visual distinctness repair -- exact, byte-for-byte
+    # outgoing version-2 rows for the three keys just moved to version 3
+    # above, preserved verbatim through the same register_layout_preset
+    # authority so v2 stays resolvable forever via
+    # get_layout_preset_version(key, "2") -- mirroring the existing v1
+    # preservation pattern already used throughout this tuple.
+    _RecipeSpec("green_workshop", "2", "سبزه", "compact_menu", "editorial_split", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "brands", "newsletter")),
+    _RecipeSpec("laleh_play", "2", "لاله‌زار", "playful_canopy", "image_collage", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "brands", "newsletter")),
+    _RecipeSpec("parnian_editorial", "2", "پرنیان", "editorial_masthead", "immersive", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "community_gallery")),
 )
 
 for _historical_spec in _HISTORICAL_SPECS:
diff --git a/apps/storefront_builder/tests/test_a8_ready_template_catalog.py b/apps/storefront_builder/tests/test_a8_ready_template_catalog.py
index 2abbdb0f..966d8962 100644
--- a/apps/storefront_builder/tests/test_a8_ready_template_catalog.py
+++ b/apps/storefront_builder/tests/test_a8_ready_template_catalog.py
@@ -33,7 +33,7 @@ EXPECTED_LATEST_VERSIONS = {
     "handmade_luxe": "2",
     "niloufar_glass": "2",
     "tool_finder": "1",
-    "green_workshop": "2",
+    "green_workshop": "3",
     "tower_department": "1",
     "beauty_dew": "2",
     "fashion_promo_catalog": "8",
@@ -42,7 +42,7 @@ EXPECTED_LATEST_VERSIONS = {
     "silk_editorial": "2",
     "tuska_bento": "1",
     "rayan_tech": "2",
-    "laleh_play": "2",
+    "laleh_play": "3",
     "city_classic": "2",
     "collection_index": "1",
     "kamand_artisan": "2",
@@ -59,7 +59,7 @@ EXPECTED_LATEST_VERSIONS = {
     "charcoal_grill": "1",
     "calligraphy_paper": "1",
     "harbor_imports": "2",
-    "parnian_editorial": "2",
+    "parnian_editorial": "3",
     "racer_tech": "1",
     "ferdowsi_department": "1",
     "anniversary_mosaic": "1",
diff --git a/apps/storefront_builder/tests/test_a8_visual_distinctness_repair.py b/apps/storefront_builder/tests/test_a8_visual_distinctness_repair.py
new file mode 100644
index 00000000..7cb649bb
--- /dev/null
+++ b/apps/storefront_builder/tests/test_a8_visual_distinctness_repair.py
@@ -0,0 +1,260 @@
+"""P5-W4C rendered visual distinctness repair — contract tests for the
+three targeted Ready Template repairs (green_workshop, laleh_play,
+parnian_editorial). Their v2 definitions were found materially
+indistinguishable, above the fold, from their respective anchors
+(pine_eco, playful_lifestyle, silk_editorial — left untouched). These
+tests pin: the new v3 identity, the outgoing v2/v1 history staying
+resolvable, an actual above-the-fold structural difference from the
+anchor (not palette/font/radius alone), and that the canonical catalog
+stays at exactly 50 with no duplicate registration.
+"""
+
+from django.test import SimpleTestCase
+
+from apps.storefront_builder import layout_preset_registry as lpr
+
+_REPAIR_PAIRS = (
+    ("green_workshop", "pine_eco"),
+    ("laleh_play", "playful_lifestyle"),
+    ("parnian_editorial", "silk_editorial"),
+)
+
+_ABOVE_FOLD_AXES = ("header", "hero", "layout", "product_view", "bottom_nav")
+
+# Pre-existing (not introduced by this repair, not part of this round's
+# authorized scope) 4-axis near-collisions that share the same rendered
+# hero_style -- discovered as a side effect of building the stricter
+# check below. Recorded here, not silently ignored, and explicitly
+# excluded from the "no NEW collision" assertions until a future,
+# separately-authorized round addresses them.
+_PRE_EXISTING_OUT_OF_SCOPE_4AXIS_COLLISIONS = frozenset({
+    frozenset({"cedar_home", "city_classic"}),
+    frozenset({"handmade_luxe", "mist_quiet"}),
+    frozenset({"tower_department", "harbor_imports"}),
+})
+
+
+def _above_fold_signature(preset):
+    selections = preset.store_appearance["selections"]
+    return tuple(selections[axis] for axis in _ABOVE_FOLD_AXES)
+
+
+def _rendered_hero_style(preset):
+    """The REAL hero_style the hero_banner section actually renders with
+    (read off the built preset's own pages["home"], not re-derived from a
+    private mapping) -- this is what the browser actually shows, and is
+    exactly the axis that let parnian_editorial's first repair attempt
+    (hero=editorial_split) silently collide with artisan_grain's
+    hero=typographic: both resolve to the same hero_style even though
+    the two hero *keys* differ syntactically."""
+    for entry in preset.pages.get("home", ()):
+        if entry.section_key == "hero_banner":
+            return entry.settings["hero_style"]
+    return None
+
+
+def _rendered_above_fold_signature(preset):
+    """Header + REAL rendered hero_style (not the raw hero key) + layout
+    + product_view -- deliberately excludes bottom_nav, which is a
+    Mobile-only element invisible in the Desktop above-the-fold view.
+    This is the stricter signature that actually caught the
+    artisan_grain regression the raw-hero-key check missed."""
+    selections = preset.store_appearance["selections"]
+    return (
+        selections["header"],
+        _rendered_hero_style(preset),
+        selections["layout"],
+        selections["product_view"],
+    )
+
+
+class RepairTargetsAreNowVersionThreeTests(SimpleTestCase):
+    def test_green_workshop_latest_is_v3(self):
+        self.assertEqual(lpr.get_layout_preset("green_workshop").version, "3")
+
+    def test_laleh_play_latest_is_v3(self):
+        self.assertEqual(lpr.get_layout_preset("laleh_play").version, "3")
+
+    def test_parnian_editorial_latest_is_v3(self):
+        self.assertEqual(lpr.get_layout_preset("parnian_editorial").version, "3")
+
+
+class OutgoingHistoryRemainsResolvableTests(SimpleTestCase):
+    def test_green_workshop_v2_and_v1_both_resolvable(self):
+        v2 = lpr.get_layout_preset_version("green_workshop", "2")
+        v1 = lpr.get_layout_preset_version("green_workshop", "1")
+        self.assertIsNotNone(v2)
+        self.assertIsNotNone(v1)
+        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.editorial_split.v1")
+        self.assertIsNot(v2, v1)
+
+    def test_laleh_play_v2_and_v1_both_resolvable(self):
+        v2 = lpr.get_layout_preset_version("laleh_play", "2")
+        v1 = lpr.get_layout_preset_version("laleh_play", "1")
+        self.assertIsNotNone(v2)
+        self.assertIsNotNone(v1)
+        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.image_collage.v1")
+        self.assertIsNot(v2, v1)
+
+    def test_parnian_editorial_v2_and_v1_both_resolvable(self):
+        v2 = lpr.get_layout_preset_version("parnian_editorial", "2")
+        v1 = lpr.get_layout_preset_version("parnian_editorial", "1")
+        self.assertIsNotNone(v2)
+        self.assertIsNotNone(v1)
+        self.assertEqual(v2.store_appearance["selections"]["hero"], "hero.immersive.v1")
+        self.assertIsNot(v2, v1)
+
+    def test_outgoing_v2_specs_are_byte_identical_to_the_old_certified_v2(self):
+        # The exact fields that were certified/rendered as v2 must survive
+        # unchanged in history -- only the *current* row may have moved on.
+        expectations = {
+            "green_workshop": dict(
+                header="header.compact_menu.v1", layout="layout.three_column.v1",
+                product_view="product_view.standard_grid.v1", card="card.standard.v1",
+                footer="footer.brand_story.v1", bottom_nav="bottom_nav.floating_dock.v1",
+            ),
+            "laleh_play": dict(
+                header="header.playful_canopy.v1", layout="layout.three_column.v1",
+                product_view="product_view.standard_grid.v1", card="card.paper_frame.v1",
+                footer="footer.playful_wave.v1", bottom_nav="bottom_nav.five_item.v1",
+            ),
+            "parnian_editorial": dict(
+                header="header.editorial_masthead.v1", layout="layout.two_column.v1",
+                product_view="product_view.editorial_grid.v1", card="card.shelf_editorial.v1",
+                footer="footer.editorial_wordmark.v1", bottom_nav="bottom_nav.minimal_icons.v1",
+            ),
+        }
+        for key, expected in expectations.items():
+            v2 = lpr.get_layout_preset_version(key, "2")
+            self.assertIsNotNone(v2, f"{key} v2 must remain resolvable")
+            selections = v2.store_appearance["selections"]
+            for axis, value in expected.items():
+                self.assertEqual(
+                    selections[axis], value,
+                    f"{key} v2.{axis} must be byte-identical to the certified v2 recipe",
+                )
+
+
+class AboveFoldIdentityNoLongerMatchesAnchorTests(SimpleTestCase):
+    def test_each_repaired_target_differs_from_its_anchor_above_the_fold(self):
+        for target_key, anchor_key in _REPAIR_PAIRS:
+            target = lpr.get_layout_preset(target_key)
+            anchor = lpr.get_layout_preset(anchor_key)
+            with self.subTest(pair=(target_key, anchor_key)):
+                self.assertNotEqual(
+                    _above_fold_signature(target), _above_fold_signature(anchor),
+                    f"{target_key} v3 must no longer match {anchor_key} on all "
+                    "major visible above-the-fold axes",
+                )
+
+    def test_the_difference_includes_hero_not_palette_font_radius_alone(self):
+        for target_key, anchor_key in _REPAIR_PAIRS:
+            target = lpr.get_layout_preset(target_key)
+            anchor = lpr.get_layout_preset(anchor_key)
+            with self.subTest(pair=(target_key, anchor_key)):
+                target_hero = target.store_appearance["selections"]["hero"]
+                anchor_hero = anchor.store_appearance["selections"]["hero"]
+                self.assertNotEqual(
+                    target_hero, anchor_hero,
+                    f"{target_key} v3 must use a different hero component than "
+                    f"{anchor_key}, not merely a different palette/font/radius",
+                )
+
+    def test_anchors_are_completely_untouched(self):
+        # The three anchors are explicitly not to be modified this round.
+        expected_anchor_hero = {
+            "pine_eco": "hero.editorial_split.v1",
+            "playful_lifestyle": "hero.image_collage.v1",
+            "silk_editorial": "hero.immersive.v1",
+        }
+        for anchor_key, expected_hero in expected_anchor_hero.items():
+            preset = lpr.get_layout_preset(anchor_key)
+            self.assertEqual(preset.version, "2")
+            self.assertEqual(preset.store_appearance["selections"]["hero"], expected_hero)
+
+
+class CatalogIntegrityAfterRepairTests(SimpleTestCase):
+    def test_canonical_ready_template_count_remains_fifty(self):
+        self.assertEqual(len(lpr.list_ready_templates()), 50)
+
+    def test_canonical_keys_are_still_exactly_the_same_fifty(self):
+        keys = sorted(preset.key for preset in lpr.list_ready_templates())
+        self.assertEqual(len(keys), len(set(keys)))
+        for target_key, _ in _REPAIR_PAIRS:
+            self.assertIn(target_key, keys)
+
+    def test_no_new_above_fold_collision_introduced_among_all_fifty(self):
+        signatures = {}
+        collisions = []
+        for preset in lpr.list_ready_templates():
+            sig = _above_fold_signature(preset)
+            if sig in signatures:
+                collisions.append((signatures[sig], preset.key))
+            else:
+                signatures[sig] = preset.key
+        # cedar_home/city_classic is a pre-existing, separately-reviewed and
+        # accepted PASS (real dark/light header contrast on Desktop) -- not
+        # part of this repair's scope, so it is explicitly excluded here.
+        collisions = [
+            pair for pair in collisions
+            if set(pair) != {"cedar_home", "city_classic"}
+        ]
+        self.assertEqual(
+            collisions, [],
+            f"repair must not introduce any NEW above-the-fold collision: {collisions}",
+        )
+
+    def test_no_new_rendered_hero_style_collision_among_all_fifty(self):
+        # Code-review finding: a raw-hero-KEY-only check is insufficient --
+        # different hero keys (e.g. "editorial_split" and "typographic")
+        # can resolve to the identical rendered hero_style. This checks the
+        # REAL rendered hero_style off each preset's own built pages, which
+        # is what a browser actually shows.
+        signatures = {}
+        collisions = []
+        for preset in lpr.list_ready_templates():
+            sig = _rendered_above_fold_signature(preset)
+            if sig in signatures:
+                collisions.append(frozenset({signatures[sig], preset.key}))
+            else:
+                signatures[sig] = preset.key
+        new_collisions = [
+            pair for pair in collisions
+            if pair not in _PRE_EXISTING_OUT_OF_SCOPE_4AXIS_COLLISIONS
+        ]
+        self.assertEqual(
+            new_collisions, [],
+            "repair must not introduce any NEW rendered-hero-style collision "
+            f"(pre-existing, out-of-scope ones are allowed): {new_collisions}",
+        )
+        for target_key, anchor_key in _REPAIR_PAIRS:
+            with self.subTest(pair=(target_key, anchor_key)):
+                self.assertNotEqual(
+                    _rendered_hero_style(lpr.get_layout_preset(target_key)),
+                    _rendered_hero_style(lpr.get_layout_preset(anchor_key)),
+                    f"{target_key} must render a genuinely different hero_style "
+                    f"than {anchor_key}, not just a different hero key",
+                )
+
+
+class AppearanceHeroStyleIsIntentionallyRecomputedTests(SimpleTestCase):
+    """The page-level appearance.hero_style (tall/split/wide) is derived
+    from the hero family independently of the hero_banner's own
+    hero_style. Swapping hero families changes this too -- pinned here
+    explicitly so it's a verified, intentional part of the repair rather
+    than an unverified side effect (code-review finding)."""
+
+    def test_green_workshop_appearance_hero_style_unchanged_group(self):
+        # editorial_split and product_focus are both in the "split" group.
+        preset = lpr.get_layout_preset("green_workshop")
+        self.assertEqual(preset.appearance["hero_style"], "split")
+
+    def test_laleh_play_appearance_hero_style_moves_tall_to_wide(self):
+        # image_collage ("tall") -> typographic ("wide").
+        preset = lpr.get_layout_preset("laleh_play")
+        self.assertEqual(preset.appearance["hero_style"], "wide")
+
+    def test_parnian_editorial_appearance_hero_style_moves_tall_to_beauty_split_group(self):
+        # immersive ("tall") -> product_focus ("split").
+        preset = lpr.get_layout_preset("parnian_editorial")
+        self.assertEqual(preset.appearance["hero_style"], "split")
```
