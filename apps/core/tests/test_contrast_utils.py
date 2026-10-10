"""WCAG 2.x contrast utility — the single implementation shared by the storefront
theme pipeline, the semantic-token tests and the runtime browser audit
(``tools/contrast_audit``). These tests pin known reference values from the WCAG
definition, not implementation details."""

from django.test import SimpleTestCase

from apps.core import color_utils as cu


class ParseCssColorTests(SimpleTestCase):
    def test_hex_forms(self):
        self.assertEqual(cu.parse_css_color("#fff"), (255.0, 255.0, 255.0, 1.0))
        self.assertEqual(cu.parse_css_color("#0F172A"), (15.0, 23.0, 42.0, 1.0))
        r, g, b, a = cu.parse_css_color("#00000080")
        self.assertEqual((r, g, b), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(a, 128 / 255)
        self.assertAlmostEqual(cu.parse_css_color("#f008")[3], 0x88 / 255)

    def test_rgb_forms(self):
        self.assertEqual(cu.parse_css_color("rgb(10, 20, 30)"), (10.0, 20.0, 30.0, 1.0))
        self.assertEqual(cu.parse_css_color("rgba(10,20,30,.5)"), (10.0, 20.0, 30.0, 0.5))
        self.assertEqual(cu.parse_css_color("rgb(10 20 30 / 25%)"), (10.0, 20.0, 30.0, 0.25))
        self.assertEqual(cu.parse_css_color("rgb(100% 0% 0%)"), (255.0, 0.0, 0.0, 1.0))

    def test_color_function_srgb(self):
        self.assertEqual(cu.parse_css_color("color(srgb 1 0 0 / 0.5)"), (255.0, 0.0, 0.0, 0.5))

    def test_keywords_and_tuples(self):
        self.assertEqual(cu.parse_css_color("transparent")[3], 0.0)
        self.assertEqual(cu.parse_css_color("WHITE"), (255.0, 255.0, 255.0, 1.0))
        self.assertEqual(cu.parse_css_color((1, 2, 3)), (1.0, 2.0, 3.0, 1.0))

    def test_unresolvable_values_are_rejected_not_guessed(self):
        # var()/color-mix()/currentColor must be resolved by the browser first.
        for value in ("var(--x)", "color-mix(in srgb, red, blue)", "currentColor", "#12", "rgb(1,2)"):
            with self.assertRaises(ValueError, msg=value):
                cu.parse_css_color(value)


class RatioTests(SimpleTestCase):
    def test_black_white_is_21(self):
        self.assertAlmostEqual(cu.contrast_ratio("#000000", "#FFFFFF"), 21.0, places=6)
        self.assertAlmostEqual(cu.contrast_ratio("#FFFFFF", "#000000"), 21.0, places=6)

    def test_identical_is_1(self):
        self.assertAlmostEqual(cu.contrast_ratio("#6D28D9", "#6D28D9"), 1.0, places=6)

    def test_known_threshold_pairs(self):
        # #767676 on white is the canonical "just passes 4.5:1" grey; #777 just fails.
        self.assertGreaterEqual(cu.contrast_ratio("#767676", "#FFFFFF"), cu.AA_NORMAL_TEXT)
        self.assertLess(cu.contrast_ratio("#777777", "#FFFFFF"), cu.AA_NORMAL_TEXT)
        self.assertAlmostEqual(cu.contrast_ratio("#767676", "#FFFFFF"), 4.54, places=2)

    def test_relative_luminance_endpoints_and_greys(self):
        self.assertAlmostEqual(cu.relative_luminance("#000000"), 0.0)
        self.assertAlmostEqual(cu.relative_luminance("#FFFFFF"), 1.0)
        self.assertAlmostEqual(cu.relative_luminance("#808080"), 0.2159, places=3)

    def test_sRGB_linearisation_uses_gamma_not_naive_average(self):
        # Pure green is far brighter than pure blue to the eye (0.7152 vs 0.0722).
        self.assertGreater(cu.relative_luminance("#00FF00"), 9 * cu.relative_luminance("#0000FF"))

    def test_large_text_threshold_selection(self):
        self.assertEqual(cu.required_ratio(16, 400), 4.5)
        self.assertEqual(cu.required_ratio(24, 400), 3.0)
        self.assertEqual(cu.required_ratio(18.66, 700), 3.0)
        self.assertEqual(cu.required_ratio(18.66, 400), 4.5)
        self.assertEqual(cu.required_ratio(14, 700), 4.5)


class AlphaCompositingTests(SimpleTestCase):
    def test_half_black_over_white_is_mid_grey(self):
        r, g, b, a = cu.composite("rgba(0,0,0,0.5)", "#FFFFFF")
        self.assertEqual(a, 1.0)
        self.assertAlmostEqual(r, 127.5)
        self.assertAlmostEqual(g, 127.5)

    def test_translucent_text_ratio_is_measured_after_compositing(self):
        # 50% black text on white is a #808080-ish grey: far below black's 21:1.
        self.assertAlmostEqual(cu.ratio_between("rgba(0,0,0,0.5)", "#FFFFFF"), 3.98, places=2)
        self.assertLess(cu.ratio_between("rgba(0,0,0,0.5)", "#FFFFFF"), cu.AA_NORMAL_TEXT)

    def test_translucent_background_is_flattened_over_backdrop(self):
        # white text on 20%-black over white: a light grey panel -> ~1.6:1
        self.assertLess(cu.ratio_between("#FFFFFF", "rgba(0,0,0,0.2)"), 2.0)
        # same panel over a black backdrop is effectively black -> white text is 21:1
        self.assertGreater(cu.ratio_between("#FFFFFF", "rgba(0,0,0,0.2)", backdrop="#000000"), 15)

    def test_composite_of_transparent_is_transparent(self):
        self.assertEqual(cu.composite("transparent", "transparent")[3], 0.0)

    def test_flatten_returns_opaque_rgb(self):
        self.assertEqual(len(cu.flatten("rgba(255,0,0,0.5)", "#FFFFFF")), 3)


class DerivationTests(SimpleTestCase):
    def test_best_foreground_picks_higher_contrast_of_black_white(self):
        self.assertEqual(cu.best_foreground("#000000"), "#FFFFFF")
        self.assertEqual(cu.best_foreground("#FFFFFF"), "#000000")
        self.assertEqual(cu.best_foreground("#FFB703"), "#000000")  # saturated yellow
        self.assertEqual(cu.best_foreground("#1E3A8A"), "#FFFFFF")  # deep blue

    def test_foreground_for_is_always_AA_on_any_background(self):
        # Whatever a merchant picks, best-of(black, white) reaches 4.5:1
        # (worst case at the luminance crossover ~0.179 is ~4.58:1).
        for step in range(0, 256, 5):
            for tint in ((1, 1, 1), (1, 0.4, 0.1), (0.2, 1, 0.3), (0.3, 0.2, 1), (1, 1, 0.2)):
                bg = cu._rgb_to_hex(step * tint[0], step * tint[1], step * tint[2])
                fg = cu.foreground_for(bg)
                self.assertGreaterEqual(cu.contrast_ratio(fg, bg), cu.AA_NORMAL_TEXT, bg)

    def test_ensure_contrast_leaves_passing_colour_untouched(self):
        self.assertEqual(cu.ensure_contrast("#1E293B", "#FFFFFF"), "#1E293B")

    def test_ensure_contrast_makes_minimal_hue_preserving_change(self):
        fixed = cu.ensure_contrast("#D3A13B", "#FFFFFF")  # gold accent on white (2.35:1)
        self.assertNotEqual(fixed, "#D3A13B")
        self.assertGreaterEqual(cu.contrast_ratio(fixed, "#FFFFFF"), cu.AA_NORMAL_TEXT)
        # not collapsed to black: still a recognisably warm/gold colour (R > B)
        r, _g, b, _a = cu.parse_css_color(fixed)
        self.assertGreater(r, b + 20)

    def test_ensure_contrast_light_text_on_dark_goes_lighter(self):
        fixed = cu.ensure_contrast("#6D28D9", "#0F0F23")
        self.assertGreaterEqual(cu.contrast_ratio(fixed, "#0F0F23"), cu.AA_NORMAL_TEXT)
        self.assertGreater(cu.relative_luminance(fixed), cu.relative_luminance("#6D28D9"))

    def test_ensure_contrast_satisfies_every_backdrop_at_once(self):
        backdrops = ["#FFFFFF", "#F7F5FC", "#ECE8F6"]
        fixed = cu.ensure_contrast("#FFB020", backdrops)
        for backdrop in backdrops:
            self.assertGreaterEqual(cu.contrast_ratio(fixed, backdrop), cu.AA_NORMAL_TEXT)

    # --- multi-backdrop: the passing set may lie strictly BETWEEN black and white -----------------------------------

    def test_ensure_contrast_black_and_white_backdrops_finds_the_middle_band(self):
        # Pure black fails on the black backdrop (1:1) and pure white fails on the white one, but a mid-luminance red
        # (~#EE0000) clears 4.5:1 on BOTH. The old search required an end-point to pass first and collapsed to 1:1.
        for target in (cu.AA_NORMAL_TEXT, 4.55):
            fixed = cu.ensure_contrast("#FF0000", ["#000000", "#FFFFFF"], target)
            self.assertNotIn(fixed, ("#000000", "#FFFFFF"), target)
            self.assertGreaterEqual(cu.contrast_ratio(fixed, "#000000"), target, (target, fixed))
            self.assertGreaterEqual(cu.contrast_ratio(fixed, "#FFFFFF"), target, (target, fixed))
            r, g, b = (int(fixed[i:i + 2], 16) for i in (1, 3, 5))
            self.assertGreater(r, 200, fixed)        # still unmistakably red
            self.assertEqual((g, b), (0, 0), fixed)  # hue preserved: only the red channel moved

    def test_ensure_contrast_mixed_dark_and_light_surfaces_for_several_hues(self):
        surfaces = ["#000000", "#FFFFFF"]
        for start in ("#FF0000", "#6D28D9", "#00A650", "#FFE066", "#FF4D77", "#2563EB"):
            for target in (cu.AA_NORMAL_TEXT, 4.55):
                fixed = cu.ensure_contrast(start, surfaces, target)
                for surface in surfaces:
                    self.assertGreaterEqual(cu.contrast_ratio(fixed, surface), target, (start, target, fixed, surface))
                self.assertEqual(fixed, fixed.upper())
                self.assertRegex(fixed, r"^#[0-9A-F]{6}$")

    def test_ensure_contrast_near_black_and_near_white_surfaces(self):
        # a single colour can clear AA on both only when (L_light + 0.05) / (L_dark + 0.05) >= AA**2 (20.25:1), i.e. a
        # near-black page against a near-white card; such pairs have a (narrow) passing luminance band.
        for backdrops in (["#000000", "#FFFFFF"], ["#000000", "#FDFDFD"], ["#030303", "#FFFFFF"]):
            for start in ("#FF0000", "#7C3AED", "#D3A13B", "#00A650"):
                fixed = cu.ensure_contrast(start, backdrops, cu.AA_NORMAL_TEXT)
                for backdrop in backdrops:
                    self.assertGreaterEqual(cu.contrast_ratio(fixed, backdrop), 4.5, (start, backdrops, fixed))

    def test_ensure_contrast_infeasible_realistic_surfaces_return_the_maximin_colour(self):
        # navy page + near-white card cannot BOTH reach 4.55 with any single colour (best possible is ~4.34:1).
        # The result must still be the best compromise, not black/white with ~1:1 on one surface.
        backdrops = ["#0F0F23", "#FFFFFF"]
        fixed = cu.ensure_contrast("#FF0000", backdrops, 4.55)
        worst = min(cu.contrast_ratio(fixed, b) for b in backdrops)
        self.assertGreater(worst, 4.3, fixed)

    def test_ensure_contrast_multi_backdrop_is_deterministic_and_unchanged_when_already_passing(self):
        self.assertEqual(cu.ensure_contrast("#767676", ["#000000", "#FFFFFF"], 4.5), "#767676")
        first = cu.ensure_contrast("#FF0000", ["#000000", "#FFFFFF"], 4.55)
        self.assertEqual(first, cu.ensure_contrast("#FF0000", ["#000000", "#FFFFFF"], 4.55))

    def test_ensure_contrast_impossible_target_returns_best_worst_case_not_an_endpoint(self):
        # 7:1 on both black and white is mathematically impossible (best possible worst-case is ~4.58:1 at the
        # luminance crossover). The result must be that maximin colour, never an end-point with 1:1 on one backdrop.
        backdrops = ["#000000", "#FFFFFF"]
        fixed = cu.ensure_contrast("#FF0000", backdrops, 7.0)
        worst = min(cu.contrast_ratio(fixed, b) for b in backdrops)
        self.assertGreater(worst, 4.5, fixed)
        self.assertNotIn(fixed, ("#000000", "#FFFFFF"))
        for endpoint in ("#000000", "#FFFFFF"):
            self.assertGreater(worst, min(cu.contrast_ratio(endpoint, b) for b in backdrops))
        # and it is the best achievable on the hue-preserving path: no neighbouring red does better
        for step in (-1, 1):
            neighbour = "#%02X0000" % (int(fixed[1:3], 16) + step)
            self.assertLessEqual(min(cu.contrast_ratio(neighbour, b) for b in backdrops), worst + 1e-9)

    def test_ensure_contrast_is_cheap_enough_for_the_request_path(self):
        import time
        started = time.perf_counter()
        for _ in range(200):
            cu.ensure_contrast("#FF0000", ["#000000", "#FFFFFF", "#7F7F7F"], 7.0)
        self.assertLess(time.perf_counter() - started, 2.0)  # ~1-3 ms each in practice

    def test_ensure_contrast_large_text_target_is_gentler(self):
        normal = cu.ensure_contrast("#E9A23B", "#FFFFFF", 4.5)
        large = cu.ensure_contrast("#E9A23B", "#FFFFFF", 3.0)
        self.assertGreater(cu.relative_luminance(large), cu.relative_luminance(normal))
        self.assertGreaterEqual(cu.contrast_ratio(large, "#FFFFFF"), 3.0)

    def test_state_pair_keeps_foreground_readable_in_the_new_state(self):
        # 'mint' primary: darkened hover with the ORIGINAL black foreground is 4.08:1 (a real
        # shipped failure); state_pair re-derives the foreground for the hover background.
        for base in ("#127948", "#7A51D8", "#617564", "#F59E0B", "#0F172A", "#FFFFFF"):
            bg, fg = cu.state_pair(base)
            self.assertGreaterEqual(cu.contrast_ratio(fg, bg), cu.AA_NORMAL_TEXT, base)
