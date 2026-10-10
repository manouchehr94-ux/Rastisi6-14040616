"""WCAG 2.2 AA contract for every canonical Ready Template (and every registered palette).

The template list comes from the canonical registry (``layout_preset_registry.list_ready_templates``)
— never a hand-maintained list of keys — and each template's real palette is resolved through the
same functions the storefront renderer uses (``appearance_registry.resolve_colors`` /
``resolve_theme_roles`` / ``resolve_section_tones``). The pairs asserted are
``accessible_colors.accessible_pairs``: the exact foreground/background relationships the
rendered CSS depends on, so "what the renderer promises" and "what is tested" cannot drift apart.

Runtime counterpart (real DOM, computed styles, hover/focus states, all 50 templates rendered):
``python tools/contrast_audit/run_audit.py --suite storefront-templates``.
"""

from django.test import SimpleTestCase

from apps.core.color_utils import (
    AA_NORMAL_TEXT,
    DISABLED_TEXT_TARGET,
    contrast_ratio,
    mix_hex,
    ratio_between,
    relative_luminance,
)
from apps.storefront_builder import appearance_registry as ar
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.accessible_colors import TARGET, accessible_pairs, build_accessible_theme, failing_pairs


def _resolved(palette_slug, overrides=None, theme_overrides=None):
    cfg = {"palette_slug": palette_slug, "color_overrides": overrides or {}, "theme_overrides": theme_overrides or {}}
    colors, roles = ar.resolve_colors(cfg), ar.resolve_theme_roles(cfg)
    return cfg, colors, roles, ar.resolve_section_tones(cfg)


class ReadyTemplateContrastTests(SimpleTestCase):
    def test_every_ready_template_palette_satisfies_the_contrast_contract(self):
        templates = lpr.list_ready_templates()
        self.assertEqual(len(templates), 50, "the A8 catalog is exactly 50 Ready Templates")
        failures = []
        for template in templates:
            _cfg, colors, roles, tones = _resolved(template.default_palette_slug)
            theme = build_accessible_theme(colors, roles, tones)
            for name, fg, bg, ratio, need in failing_pairs(colors, roles, theme, tones):
                failures.append(f"{template.key} [{template.default_palette_slug}] {name}: {fg} on {bg} = {ratio:.2f}:1 (need {need})")
        self.assertFalse(failures, "\n".join(failures))

    def test_every_registered_palette_satisfies_the_contrast_contract(self):
        # merchants can pick ANY of the registered palettes (not only a template's default)
        self.assertGreaterEqual(len(ar.PALETTE_REGISTRY), 64)
        failures = []
        for slug in ar.PALETTE_REGISTRY:
            _cfg, colors, roles, tones = _resolved(slug)
            for name, fg, bg, ratio, need in failing_pairs(colors, roles, tones=tones):
                failures.append(f"{slug} {name}: {fg} on {bg} = {ratio:.2f}:1 (need {need})")
        self.assertFalse(failures, "\n".join(failures))

    def test_catalog_audits_both_light_and_dark_appearances(self):
        dark = light = 0
        for template in lpr.list_ready_templates():
            _cfg, colors, _roles, _tones = _resolved(template.default_palette_slug)
            if relative_luminance(colors["background"]) < 0.2:
                dark += 1
            else:
                light += 1
        self.assertGreater(dark, 0)
        self.assertGreater(light, 0)

    def test_identity_is_preserved_unsafe_colours_move_minimally_safe_ones_do_not_move(self):
        moved = unchanged = 0
        for template in lpr.list_ready_templates():
            _cfg, colors, roles, tones = _resolved(template.default_palette_slug)
            theme = build_accessible_theme(colors, roles, tones)
            surfaces = [colors["background"], colors["surface"], roles["card_bg"]]
            for key, raw in (("primary_text", colors["primary"]), ("accent_text", colors["accent"]),
                             ("muted_text", colors["muted"]), ("price_text", roles["price"]), ("text", colors["text"])):
                raw_ok = all(contrast_ratio(raw, s) >= TARGET for s in surfaces)
                if raw_ok:
                    self.assertEqual(theme[key].upper(), raw.upper(), f"{template.key} {key} was safe but changed")
                    unchanged += 1
                else:
                    moved += 1
                    self.assertNotEqual(theme[key].upper(), raw.upper())
                    # still recognisably the merchant's hue: only lightness moved (channel ordering is preserved)
                    order = lambda c: sorted(range(3), key=lambda i: int(c[1 + 2 * i:3 + 2 * i], 16))  # noqa: E731
                    self.assertEqual(order(theme[key]), order(raw), f"{template.key} {key} changed hue")
        self.assertGreater(moved, 0, "fixture sanity: some template palettes really do ship unsafe text colours")
        self.assertGreater(unchanged, 0)

    def test_raw_palette_resolution_is_not_rewritten(self):
        """The Builder/storage layer still sees the exact merchant colours."""
        for template in lpr.list_ready_templates():
            palette = ar.get_palette(template.default_palette_slug)
            self.assertEqual(ar.resolve_colors({"palette_slug": palette.slug}), dict(palette.colors))

    def test_disabled_controls_hold_3_to_1_on_every_template_palette(self):
        """tokens.css: --disabled-bg = text 8% on surface; --disabled-ink = text 75% on surface."""
        failures = []
        for template in lpr.list_ready_templates():
            _cfg, colors, roles, _tones = _resolved(template.default_palette_slug)
            theme = build_accessible_theme(colors, roles)
            text, surface = theme["text"], colors["surface"]
            bg, ink = mix_hex(text, surface, 0.08), mix_hex(text, surface, 0.75)
            for label, pair in (("ink on disabled bg", (ink, bg)), ("ink on surface", (ink, surface))):
                if contrast_ratio(*pair) < DISABLED_TEXT_TARGET:
                    failures.append(f"{template.key} {label}: {contrast_ratio(*pair):.2f}")
        self.assertFalse(failures, "\n".join(failures))

    def test_derived_variables_cover_the_whole_contract(self):
        _cfg, colors, roles, tones = _resolved(lpr.list_ready_templates()[0].default_palette_slug)
        names = {n for n, *_ in accessible_pairs(colors, roles, tones=tones)}
        for expected in ("primary_text on surface", "accent_text on card", "price_text on background", "muted_fg on muted_text",
                         "primary_hover_fg on primary_hover", "header_text on header_bg", "footer_text on footer_bg",
                         "gradient_fg on primary", "gradient_fg on gradient_end", "tone_1_fg on tone_1"):
            self.assertIn(expected, names)


class DynamicBrandColourTests(SimpleTestCase):
    """Arbitrary merchant colours — the case a template-key test can never cover."""

    BASE = {"secondary": "#7C3AED", "accent": "#FF4D77", "background": "#FFFFFF", "surface": "#FFFFFF",
            "text": "#241C3A", "muted": "#8B86A3", "border": "#ECE8F6"}
    ROLES = {"header_bg": "#FFFFFF", "header_text": "#241C3A", "nav_bg": "#FFFFFF", "nav_text": "#241C3A",
             "card_bg": "#FFFFFF", "footer_bg": "#241C3A", "footer_text": "#FFFFFF", "price": "#FF4D77"}

    def _theme(self, primary, **overrides):
        colors = {**self.BASE, "primary": primary, **overrides}
        roles = {**self.ROLES, **{k: v for k, v in overrides.items() if k in self.ROLES}}
        return colors, roles, build_accessible_theme(colors, roles)

    def test_dangerous_light_brand_backgrounds_get_dark_foregrounds(self):
        for primary in ("#FFFFFF", "#FFF200", "#FFE066", "#F5F5DC", "#E0FFFF", "#C8F7C5", "#FFB703"):
            _colors, _roles, theme = self._theme(primary)
            self.assertEqual(theme["primary_fg"], "#000000", primary)
            self.assertGreaterEqual(contrast_ratio(theme["primary_fg"], primary), AA_NORMAL_TEXT, primary)

    def test_dangerous_dark_brand_backgrounds_get_light_foregrounds(self):
        for primary in ("#000000", "#0A0A23", "#1E1B4B", "#7C2D12", "#064E3B", "#111827"):
            _colors, _roles, theme = self._theme(primary)
            self.assertEqual(theme["primary_fg"], "#FFFFFF", primary)
            self.assertGreaterEqual(contrast_ratio(theme["primary_fg"], primary), AA_NORMAL_TEXT, primary)

    def test_luminance_crossover_colours_still_reach_aa_with_black_or_white(self):
        # worst case for best-of(black, white) is the ~#767676 crossover (~4.58:1) — never below AA
        for primary in ("#767676", "#777777", "#757575", "#808080", "#8A8A8A", "#00A650", "#2E8B57", "#E67E22"):
            _colors, _roles, theme = self._theme(primary)
            self.assertGreaterEqual(contrast_ratio(theme["primary_fg"], primary), AA_NORMAL_TEXT, primary)

    def test_primary_as_text_is_adjusted_only_as_far_as_needed(self):
        _colors, _roles, theme = self._theme("#FFE066")
        self.assertGreaterEqual(contrast_ratio(theme["primary_text"], "#FFFFFF"), AA_NORMAL_TEXT)
        self.assertNotEqual(theme["primary_text"].upper(), "#000000")  # not collapsed to black: hue kept
        _colors, _roles, safe = self._theme("#1E3A8A")
        self.assertEqual(safe["primary_text"].upper(), "#1E3A8A")      # already safe -> untouched

    def test_text_on_dark_storefront_surfaces_lightens_instead_of_darkening(self):
        colors, roles, theme = self._theme(
            "#7C3AED", background="#0F0F23", surface="#1E1C35", card_bg="#1E1C35", text="#E2E8F0", muted="#94A3B8",
            header_bg="#1E1C35", header_text="#E2E8F0", nav_bg="#1E1C35", nav_text="#E2E8F0", footer_bg="#0F0F23", footer_text="#E2E8F0",
            price="#F43F5E")
        for key in ("primary_text", "accent_text", "price_text", "muted_text"):
            self.assertGreaterEqual(contrast_ratio(theme[key], "#1E1C35"), AA_NORMAL_TEXT, key)
            self.assertGreaterEqual(contrast_ratio(theme[key], "#0F0F23"), AA_NORMAL_TEXT, key)
        self.assertGreater(relative_luminance(theme["primary_text"]), relative_luminance("#7C3AED"))

    def test_region_text_is_forced_readable_even_if_the_merchant_pairs_it_badly(self):
        _colors, _roles, theme = self._theme("#6D28D9", header_bg="#1E3A8A", header_text="#2563EB", footer_bg="#FFFFFF", footer_text="#F1F5F9")
        self.assertGreaterEqual(contrast_ratio(theme["header_text"], "#1E3A8A"), AA_NORMAL_TEXT)
        self.assertGreaterEqual(contrast_ratio(theme["footer_text"], "#FFFFFF"), AA_NORMAL_TEXT)

    def test_hover_state_foreground_is_recomputed_for_the_hover_background(self):
        # a button that is fine at rest must not keep an inherited foreground when its background shifts
        for primary in ("#127948", "#7A51D8", "#617564", "#F59E0B", "#0F172A", "#16A34A"):
            _colors, _roles, theme = self._theme(primary)
            self.assertGreaterEqual(contrast_ratio(theme["primary_hover_fg"], theme["primary_hover"]), AA_NORMAL_TEXT, primary)

    def test_gradient_label_holds_on_both_stops_even_with_opposite_luminance(self):
        # near-black -> pale-yellow: no single black/white label serves both RAW stops, so the label follows the
        # primary stop and the end stop is the secondary colour nudged until the same label reads on it.
        colors, _roles, theme = self._theme("#0A0A23", secondary="#FFF200")
        self.assertEqual(theme["gradient_fg"], "#FFFFFF")
        self.assertGreaterEqual(contrast_ratio(theme["gradient_fg"], colors["primary"]), AA_NORMAL_TEXT)
        self.assertGreaterEqual(contrast_ratio(theme["gradient_fg"], theme["gradient_end"]), AA_NORMAL_TEXT)
        self.assertEqual(colors["secondary"], "#FFF200")  # the stored secondary is untouched

    def test_gradient_end_is_left_alone_when_the_label_already_reads_on_it(self):
        colors, _roles, theme = self._theme("#1E3A8A", secondary="#312E81")
        self.assertEqual(theme["gradient_end"].upper(), colors["secondary"].upper())

    def test_mixed_dark_page_and_light_surface_keep_every_general_usage_token_readable(self):
        # Reachable merchant config: black page, white card/surface, a mid-grey body text that passes on both,
        # saturated brand colours. Pure black fails on the page, pure white fails on the card, so the derived
        # usage tokens must land in the mid-luminance band that clears AA on BOTH (regression for ensure_contrast
        # requiring an end-point to pass before it searched).
        colors, roles, theme = self._theme(
            "#FF0000", secondary="#00A650", accent="#FFE066", background="#000000", surface="#FFFFFF",
            text="#767676", muted="#8A8A8A", card_bg="#FFFFFF", price="#6D28D9",
            header_bg="#000000", header_text="#FFFFFF", nav_bg="#000000", nav_text="#FFFFFF",
            footer_bg="#111111", footer_text="#FFFFFF")
        for key in ("text", "muted_text", "primary_text", "secondary_text", "accent_text", "price_text"):
            for surface in ("#000000", "#FFFFFF"):
                self.assertGreaterEqual(contrast_ratio(theme[key], surface), AA_NORMAL_TEXT, (key, theme[key], surface))
            self.assertNotIn(theme[key].upper(), ("#000000", "#FFFFFF"), key)
        self.assertEqual(failing_pairs(colors, roles, theme), [])
        self.assertEqual(colors["primary"], "#FF0000")  # stored brand colour untouched

    def test_translucent_surfaces_are_judged_after_compositing(self):
        # glass cards: a 70%-white card over a dark page is a light grey; white text on it must be judged on the composite
        self.assertLess(ratio_between("#FFFFFF", "rgba(255,255,255,0.7)", backdrop="#0F0F23"), AA_NORMAL_TEXT)
        self.assertGreaterEqual(ratio_between("#FFFFFF", "rgba(255,255,255,0.1)", backdrop="#0F0F23"), AA_NORMAL_TEXT)
