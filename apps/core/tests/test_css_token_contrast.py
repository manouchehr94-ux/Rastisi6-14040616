"""Deterministic semantic contrast contract for the first-party stylesheets.

These tests do not grep for particular hex codes. They resolve each style system's
own design tokens (custom properties, ``var()`` chains, ``color-mix``) and assert the
*relationships* the UI relies on: this text colour on that surface, this label on that
filled control, in every state the component can be in. Change a token and the pair
that breaks fails here; change a hex without breaking a pair and nothing fails.

The browser-level counterpart (computed styles, hover/focus/active transitions) lives in
``tools/contrast_audit`` — see its README.
"""

import re

from django.test import SimpleTestCase

from apps.core.color_utils import AA_NON_TEXT, AA_NORMAL_TEXT, DISABLED_TEXT_TARGET, contrast_ratio
from apps.core.tests.css_tokens import custom_properties, iter_rules, ratio, read_css, resolve

AA = AA_NORMAL_TEXT


class TokenPairTestCase(SimpleTestCase):
    def assertPairs(self, props, pairs, scope=""):
        failures = []
        for fg, bg, need in pairs:
            fg_hex, bg_hex = resolve(fg, props), resolve(bg, props)
            ratio = contrast_ratio(fg_hex, bg_hex)
            if ratio + 1e-9 < need:
                failures.append(f"{fg} ({fg_hex}) on {bg} ({bg_hex}) = {ratio:.2f}:1, need {need}")
        self.assertFalse(failures, f"{scope} contrast failures:\n  " + "\n  ".join(failures))


# --------------------------------------------------------------------------- dashboard / Merchant Admin


class DashboardAdminTokenTests(TokenPairTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = read_css("apps/dashboard/static/css/admin.css")
        cls.light = custom_properties(cls.css, ":root")
        cls.dark = {**cls.light, **custom_properties(cls.css, 'body[data-theme="dark"]')}

    def _status_pairs(self):
        pairs = []
        for hue in ("green", "amber", "red", "blue", "cyan", "purple"):
            ink, soft = f"var(--{hue}-ink)", f"var(--{hue}-soft)"
            pairs += [(ink, soft, AA), (ink, "var(--card)", AA), (ink, "var(--bg)", AA)]
        return pairs

    def test_status_badge_text_light(self):
        self.assertPairs(self.light, self._status_pairs(), "admin light status")

    def test_status_badge_text_dark(self):
        self.assertPairs(self.dark, self._status_pairs(), "admin dark status")

    def test_muted_and_body_text_on_every_surface(self):
        for name, props in (("light", self.light), ("dark", self.dark)):
            self.assertPairs(props, [
                ("var(--text)", "var(--card)", AA), ("var(--text)", "var(--bg)", AA),
                ("var(--muted)", "var(--card)", AA), ("var(--muted)", "var(--bg)", AA),
                ("var(--muted)", "var(--border)", AA),  # .b-gray badge, .trend.flat
                ("var(--muted)", "var(--primary-soft)", AA),
                ("var(--primary-text)", "var(--primary-soft)", AA), ("var(--primary-text)", "var(--card)", AA),
            ], f"admin {name} text")

    def test_filled_primary_button_label_on_both_gradient_stops(self):
        # .btn-primary = linear-gradient(135deg, --primary, --primary-2), label #fff (default AND hover)
        self.assertPairs(self.light, [("#ffffff", "var(--primary)", AA), ("#ffffff", "var(--primary-2)", AA)], "btn-primary")

    def test_disabled_controls_stay_readable(self):
        for props in (self.light, self.dark):
            self.assertPairs(props, [
                ("var(--disabled-ink)", "var(--disabled-bg)", DISABLED_TEXT_TARGET),
                ("var(--disabled-ink)", "var(--card)", DISABLED_TEXT_TARGET),
            ], "admin disabled")

    def test_danger_button_label(self):
        self.assertPairs(self.light, [("var(--red-ink)", "var(--red-soft)", AA)], "btn-danger")

    def test_avatar_gradient_keeps_white_initials_readable(self):
        rule = next(d for s, d in iter_rules(self.css) if s == ".avatar")
        stops = re.findall(r"#[0-9a-fA-F]{6}", rule["background"])
        self.assertGreaterEqual(len(stops), 2)
        for stop in stops:
            self.assertGreaterEqual(contrast_ratio("#ffffff", stop), AA, stop)


class AdminV2AndWizardTokenTests(TokenPairTestCase):
    def test_admin_v2_muted_on_surfaces(self):
        props = custom_properties(read_css("apps/dashboard/static/css/admin_v2.css"), "body.admin-v2-body")
        self.assertPairs(props, [
            ("var(--admin-v2-muted)", "var(--admin-v2-surface)", AA), ("var(--admin-v2-muted)", "var(--admin-v2-canvas)", AA),
            ("var(--admin-v2-text)", "var(--admin-v2-surface)", AA),
        ], "admin_v2")

    def test_logo_gradient_end_stop_keeps_white_glyph_readable(self):
        css = read_css("apps/dashboard/static/css/admin_v2.css")
        props = custom_properties(css, "body.admin-v2-body")
        rule = next(d for s, d in iter_rules(css) if s == "body.admin-v2-body .brand .logo")
        stops = [resolve(p.strip(), props) for p in re.findall(r"var\(--admin-v2-accent\)|#[0-9a-fA-F]{6}", rule["background"])]
        for stop in stops:
            self.assertGreaterEqual(contrast_ratio("#ffffff", stop), AA, stop)

    def test_campaign_wizard_scope(self):
        css = read_css("apps/dashboard/static/css/campaign_wizard.css")
        props = custom_properties(css, ".cw")
        self.assertPairs(props, [
            ("var(--muted)", "#ffffff", AA), ("var(--muted)", "var(--bg)", AA), ("var(--muted)", "#ececf4", AA),
            ("var(--muted)", "#f7f5ff", AA), ("var(--muted)", "#f7f8fc", AA), ("var(--muted)", "#f3f3f9", AA),
            ("var(--violet)", "var(--violet-pale)", AA), ("var(--violet)", "#ffffff", AA), ("#ffffff", "var(--violet)", AA),
            ("var(--violet-dark)", "#ffffff", AA), ("var(--green-ink)", "var(--green-pale)", AA),
            ("var(--ink)", "#ffffff", AA),
        ], "campaign wizard")
        # preview hero: white headline + small caption on BOTH stops of the gradient
        hero = next(d for s, d in iter_rules(css) if s == ".cw .cw-preview-hero")
        for stop in re.findall(r"#[0-9a-fA-F]{6}", hero["background"]):
            self.assertGreaterEqual(contrast_ratio("#e4dfff", stop), AA, stop)

    def test_product_entry_scope(self):
        css = read_css("apps/dashboard/static/css/product_entry_prototype.css")
        props = custom_properties(css, ".pe-prototype")
        self.assertPairs(props, [
            ("var(--muted)", "#ffffff", AA), ("var(--muted)", "var(--bg)", AA), ("var(--muted)", "#f3f4f6", AA),
            ("var(--primary)", "var(--soft)", AA), ("var(--primary)", "#ffffff", AA), ("#ffffff", "var(--primary)", AA),
            ("#ffffff", "var(--success)", AA), ("var(--text)", "var(--bg)", AA),
            ("#334155", "#cbd5e1", AA),  # inactive step number
            ("#5d6577", "#e8eaf0", DISABLED_TEXT_TARGET),  # disabled button
        ], "product entry")


# --------------------------------------------------------------------------- platform (public site, portal, onboarding, auth)


class PlatformDarkTokenTests(TokenPairTestCase):
    """platform-tokens.css — the dark owner-portal theme (``--p-*``)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = read_css("apps/portal/static/portal/css/platform-tokens.css")
        cls.props = custom_properties(cls.css, ":root")

    def test_text_and_status_tokens_on_dark_surfaces(self):
        pairs = []
        for surface in ("--p-bg", "--p-card", "--p-primary-soft"):
            pairs += [(f"var({fg})", f"var({surface})", AA) for fg in ("--p-ink", "--p-muted", "--p-primary", "--p-accent")]
        pairs += [("#f28b82", "#2b1616", AA), ("#f2c38b", "#2b2416", AA), ("var(--p-accent)", "var(--p-accent-soft)", AA)]
        self.assertPairs(self.props, pairs, "platform dark")

    def test_primary_button_default_and_hover_stops(self):
        """Regression: the hover gradient ended on #0a7a58 under the unchanged #08130f label (3.55:1)."""
        rules = {s: d for s, d in iter_rules(self.css)}
        for selector in (".p-btn-primary", ".p-btn-primary:hover"):
            decl = rules[selector]["background"]
            label = rules[".p-btn-primary"]["color"]
            for stop in re.findall(r"var\(--[\w-]+\)|#[0-9a-fA-F]{6}", decl):
                self.assertGreaterEqual(contrast_ratio(resolve(label, self.props), resolve(stop, self.props)), AA, f"{selector} {stop}")


class PublicSiteTokenTests(TokenPairTestCase):
    """public-site-v2.css + public-home-v3.css — the light RastiSi brand (``--rs-*``), used by the public
    site, auth pages and the onboarding journey."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        v2 = read_css("apps/portal/static/portal/css/public-site-v2.css")
        v3 = read_css("apps/portal/static/portal/css/public-home-v3.css")
        cls.v2 = v2
        cls.props = {**custom_properties(v2, ":root"), **custom_properties(v3, ":root")}

    def test_text_roles_on_every_surface(self):
        pairs = []
        for surface in ("--rs-paper", "--rs-surface", "--rs-soft", "--rs-sand"):
            pairs += [(f"var({fg})", f"var({surface})", AA) for fg in ("--rs-ink", "--rs-muted", "--rs-brand")]
        for surface in ("--rs-paper", "--rs-soft", "--rs-surface"):
            pairs += [(f"var({fg})", f"var({surface})", AA) for fg in ("--rs-danger", "--rs-success", "--rs-warning", "--rs-warm")]
        self.assertPairs(self.props, pairs, "public site")

    def test_filled_controls(self):
        self.assertPairs(self.props, [
            ("var(--rs-surface)", "var(--rs-brand)", AA),            # .rs-btn-primary / .ob-btn-primary
            ("var(--rs-surface)", "var(--rs-brand-strong)", AA),     # ...:hover
            ("var(--rs-ink)", "var(--rs-accent)", AA),               # .rs-btn-accent
            ("var(--rs-paper)", "var(--rs-brand-strong)", AA),       # .rs-dark sections
        ], "public site controls")

    def test_disabled_and_locked_states_are_still_readable(self):
        self.assertPairs(self.props, [
            ("var(--rs-disabled-ink)", "var(--rs-disabled-bg)", DISABLED_TEXT_TARGET),
            ("var(--rs-disabled-ink)", "var(--rs-paper)", DISABLED_TEXT_TARGET),
            ("var(--rs-muted)", "var(--rs-disabled-bg)", DISABLED_TEXT_TARGET),  # locked onboarding step dot
        ], "disabled")

    def test_two_tone_focus_ring_is_visible_on_any_surface(self):
        # ink outline + white halo: one of the two always contrasts with the surroundings.
        self.assertPairs(self.props, [("var(--rs-focus-ink)", "var(--rs-focus-halo)", AA_NON_TEXT)], "focus ring")
        for surface in ("--rs-paper", "--rs-brand-strong", "--rs-brand"):
            ring_vs_surface = max(
                contrast_ratio(resolve("var(--rs-focus-ink)", self.props), resolve(f"var({surface})", self.props)),
                contrast_ratio(resolve("var(--rs-focus-halo)", self.props), resolve(f"var({surface})", self.props)),
            )
            self.assertGreaterEqual(ring_vs_surface, AA_NON_TEXT, surface)

    def test_builder_demo_chrome(self):
        # dark workbench of the homepage demo: muted label on both chrome shades; each demo palette
        # as a tag colour (darkened 15% toward black) on the sample window
        self.assertPairs(self.props, [
            ("var(--rh-on-chrome)", "var(--rh-chrome)", AA), ("var(--rh-on-chrome-muted)", "var(--rh-chrome)", AA),
            ("var(--rh-on-chrome-muted)", "var(--rh-chrome-2)", AA),
        ], "demo chrome")
        for palette in ("--rh-p-forest", "--rh-p-indigo", "--rh-p-copper", "--rh-p-graphite"):
            tagged = f"color-mix(in srgb, var({palette}) 85%, var(--rs-ink))"
            self.assertPairs(self.props, [(tagged, "var(--rs-soft)", AA), (tagged, "var(--rs-surface)", AA)], palette)

    def test_decorative_numerals_meet_large_text_threshold(self):
        rule = next(d for s, d in iter_rules(self.v2) if s == ".rs-page-count")
        self.assertGreaterEqual(contrast_ratio(resolve(rule["color"], self.props), resolve("var(--rs-paper)", self.props)), 3.0)


class PlatformAdminPanelTokenTests(TokenPairTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.props = custom_properties(read_css("apps/portal/static/portal/css/platform-admin-panel.css"), ":root")

    def test_status_ink_on_tint(self):
        pairs = []
        for hue, tint in (("green", "greenbg"), ("orange", "orangebg"), ("red", "redbg"), ("blue", "bluebg")):
            pairs += [(f"var(--pa-{hue}-ink)", f"var(--pa-{tint})", AA), (f"var(--pa-{hue}-ink)", "var(--pa-card)", AA)]
        self.assertPairs(self.props, pairs, "platform admin status")

    def test_text_and_primary_buttons(self):
        self.assertPairs(self.props, [
            ("var(--pa-ink)", "var(--pa-card)", AA), ("var(--pa-muted)", "var(--pa-card)", AA), ("var(--pa-muted)", "var(--pa-bg)", AA),
            ("#ffffff", "var(--pa-purple)", AA), ("#ffffff", "var(--pa-purple2)", AA),  # .pa-primary gradient stops
            ("var(--pa-purple)", "var(--pa-soft)", AA),                                   # .pa-soft, avatar
            ("var(--pa-disabled-ink)", "var(--pa-disabled-bg)", DISABLED_TEXT_TARGET),
        ], "platform admin")


# --------------------------------------------------------------------------- Storefront Builder chrome


class BuilderStudioTokenTests(TokenPairTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = read_css("apps/storefront_builder/static/storefront_builder/r4_studio.css")
        cls.props = custom_properties(cls.css, ".rs-studio")

    def test_studio_text_roles(self):
        self.assertPairs(self.props, [
            ("var(--ink)", "var(--surface)", AA), ("var(--ink)", "var(--bg)", AA),
            ("var(--muted)", "var(--surface)", AA), ("var(--muted)", "var(--bg)", AA),
            ("var(--primary)", "var(--surface)", AA), ("var(--primary)", "var(--primary-soft)", AA),
            ("var(--danger)", "var(--surface)", AA), ("#ffffff", "var(--primary)", AA),
            # muted-ink = the sage secondary text on every studio surface it appears on
            ("var(--muted-ink)", "#ffffff", AA), ("var(--muted-ink)", "#fcfdfb", AA), ("var(--muted-ink)", "#edf1eb", AA),
            ("var(--muted-ink)", "#e6ebe1", AA), ("var(--muted-ink)", "#d6ddd0", AA),
        ], "studio")

    def test_studio_disabled_publish_button_is_readable(self):
        self.assertPairs(self.props, [("var(--disabled-ink)", "var(--disabled-bg)", DISABLED_TEXT_TARGET),
                                      ("var(--disabled-ink)", "var(--surface)", DISABLED_TEXT_TARGET)], "studio disabled")


# --------------------------------------------------------------------------- Storefront static tokens


class StorefrontStaticTokenTests(TokenPairTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.props = custom_properties(read_css("apps/core/static/css/tokens.css"), ":root")

    def test_platform_success_green_works_as_fill_and_as_text(self):
        # one token is used both as a fill (white label: "جدید" pill, step number) and as a text colour on white / tinted surfaces
        self.assertPairs(self.props, [("#ffffff", "var(--green)", AA), ("var(--green)", "#ffffff", AA),
                                      ("var(--green)", "var(--green-soft)", AA), ("var(--amber-text)", "#ffffff", AA)], "success green")

    def test_default_theme_fallbacks_of_the_usage_tokens(self):
        """With no store palette injected (error pages, tests) the `-text` fallbacks must still read on the default surfaces."""
        for token in ("--violet-text", "--pink-text", "--secondary-text"):
            for surface in ("#ffffff", "#f7f5fc"):
                fallback = re.search(r"var\([^,]+,\s*(#[0-9a-fA-F]{6})\s*\)", self.props[token]).group(1)
                self.assertGreaterEqual(contrast_ratio(fallback, surface), AA, f"{token} {fallback} on {surface}")


# --------------------------------------------------------------------------- known failures found by the browser audit


class KnownRegressionTests(SimpleTestCase):
    def test_admin_link_reset_cannot_outrank_component_colours(self):
        """`.admin-body a{color:inherit}` (0,1,1) beat `.btn-primary`/`.tab.active` (<=0,2,0), so every
        `<a class="btn btn-primary">` rendered dark text on indigo (2.3:1). The reset must stay zero-specificity."""
        css = read_css("apps/dashboard/static/css/admin.css")
        self.assertIn(":where(.admin-body a:not(.btn))", css)
        self.assertNotRegex(css, r"\.admin-body a\s*\{\s*color:\s*inherit")

    def test_no_state_fades_text_with_element_opacity(self):
        """Element `opacity` on a disabled/locked control also halves its text contrast (1.4–1.7:1 measured).
        Disabled-style rules in the first-party stylesheets must use explicit colours."""
        files = [
            "apps/dashboard/static/css/admin.css", "apps/dashboard/static/css/product_entry_prototype.css",
            "apps/portal/static/portal/css/public-site-v2.css", "apps/portal/static/portal/css/onboarding.css",
            "apps/portal/static/portal/css/platform-admin-panel.css", "apps/portal/static/portal/css/platform-tokens.css",
            "apps/storefront_builder/static/storefront_builder/r4_studio.css",
            "apps/storefront_builder/static/css/storefront_builder.css",
            "apps/catalog/static/css/home.css", "apps/catalog/static/css/product_detail.css",
            "apps/catalog/static/css/product_list.css", "apps/catalog/static/css/product_card.css",
        ]
        offenders = []
        for path in files:
            for selector, decls in iter_rules(read_css(path)):
                if not re.search(r":disabled|\[disabled\]|\.disabled|is-locked|\[aria-disabled", selector):
                    continue
                opacity = decls.get("opacity")
                if opacity is not None and float(opacity) < 0.9:
                    offenders.append(f"{path}: {selector} {{opacity:{opacity}}}")
        self.assertFalse(offenders, "\n".join(offenders))

    def test_out_of_stock_fades_only_the_picture_not_the_badges_over_it(self):
        css = read_css("apps/catalog/static/css/product_card.css")
        for selector, decls in iter_rules(css):
            if "out-of-stock" in selector and "opacity" in decls:
                self.assertRegex(selector, r"img|picture|video", selector)

    def test_hero_copy_sits_on_a_contained_scrim(self):
        """Hero copy over a merchant-uploaded image: deterministic worst case. Dark copy on a 88% white panel and
        white copy on a 66% dark panel must hold >= 4.5:1 over a pure-black AND a pure-white pixel."""
        from apps.core.color_utils import ratio_between

        for fg, panel in (("#24252a", "rgba(255,255,255,.88)"), ("#34363d", "rgba(255,255,255,.88)"), ("#ffffff", "rgba(18,20,26,.66)")):
            for pixel in ("#000000", "#ffffff"):
                self.assertGreaterEqual(ratio_between(fg, panel, backdrop=pixel), AA, f"{fg} on {panel} over {pixel}")
        css = read_css("apps/core/static/css/theme_palette.css")
        rule = next(d for s, d in iter_rules(css) if s == ".hero-text")
        self.assertIn("rgba(255,255,255,.88)", rule["background"])

    def test_hero_tab_strip_scrim_and_image_section_head_scrim(self):
        from apps.core.color_utils import ratio_between

        for pixel in ("#000000", "#ffffff"):
            self.assertGreaterEqual(ratio_between("#ffffff", "rgba(18,20,26,.78)", backdrop=pixel), AA)
            self.assertGreaterEqual(ratio_between("#ffffff", "rgba(14,16,22,.66)", backdrop=pixel), AA)


# --------------------------------------------------------------------------- surface ownership (live template switching)


class CategoryComponentSurfaceOwnershipTests(SimpleTestCase):
    """A Template switch replaces the palette but keeps the merchant's sections, so any section presentation can meet
    any palette. Every component therefore has to name the surface its text sits on:

    * text directly on the PAGE (or on a merchant/palette BAND) uses ``--sfb-section-fg`` when a band defines it and the
      accessible page-text token otherwise — never a fixed dark or white literal;
    * a component that paints its OWN fixed tile uses a fixed colour that is verified on that tile.
    """

    FILES = ("apps/catalog/static/css/home.css", "apps/storefront_builder/static/css/storefront_builder.css")
    #: text sits directly on the page / band
    PAGE_OWNED = (".category-image-tile", ".category-fashion-tile", ".category-beauty-tile", ".category-chocolate-story-item",
                  ".tile-circle", ".tile-circle-label")
    #: own fixed surface: (selector, surface colour)
    TILE_OWNED = ((".category-mosaic-tile", "#ffffff"), (".category-mosaic-chevron", "#ffffff"),
                  (".category-chocolate-label", "#7B4518"))
    #: (page background, accessible page text, band background or None, band foreground or None)
    SCENARIOS = (
        ("dark page", "#070707", "#FFE76A", None, None),
        ("light page", "#FFFDF9", "#201B17", None, None),
        ("dark page, light band", "#070707", "#FFE76A", "#FFFFFF", "#000000"),
        ("light page, dark band", "#FFFDF9", "#201B17", "#1A1A2E", "#FFFFFF"),
        ("saturated page", "#FF4D77", "#000000", None, None),
    )

    @staticmethod
    def final_colour(css, selector):
        """The ``color`` of the LAST rule that sets one on exactly ``selector`` (later rules win at equal specificity)."""
        found = None
        for sel, decls in iter_rules(css):
            if selector in [s.strip() for s in sel.split(",")] and "color" in decls:
                found = decls["color"]
        return found

    def test_page_owned_text_follows_the_surface_it_sits_on(self):
        failures = []
        for path in self.FILES:
            css = read_css(path)
            for selector in self.PAGE_OWNED:
                value = self.final_colour(css, selector)
                if value is None:
                    continue  # inherits from a component that is itself checked
                for name, page, text, band, band_fg in self.SCENARIOS:
                    props = {"--brand-text": text, "--ink": text}
                    surface = page
                    if band:
                        props["--sfb-section-fg"] = band_fg
                        surface = band
                    got = ratio(value, surface, props)
                    if got + 1e-9 < AA:
                        failures.append(f"{path}: {selector} {{color:{value}}} on {name} ({surface}) = {got:.2f}:1")
        self.assertFalse(failures, "\n".join(failures))

    def test_own_surface_components_use_a_colour_verified_on_their_own_tile(self):
        failures = []
        for path in self.FILES:
            css = read_css(path)
            for selector, surface in self.TILE_OWNED:
                value = self.final_colour(css, selector)
                if value is None:
                    continue
                for name, _page, text, _band, _fg in self.SCENARIOS:
                    # palette tokens change per scenario; a tile with its own surface must not depend on them
                    got = ratio(value, surface, {"--brand-text": text, "--muted": text, "--ink": text, "--brand-muted": text})
                    if got + 1e-9 < AA:
                        failures.append(f"{path}: {selector} {{color:{value}}} on its own {surface} under {name} = {got:.2f}:1")
        self.assertFalse(failures, "\n".join(failures))

    def test_the_two_stylesheets_agree_on_category_text_colours(self):
        """home.css (public) and storefront_builder.css (Builder preview) both ship these rules; they must not diverge."""
        home, builder = (read_css(p) for p in self.FILES)
        for selector in self.PAGE_OWNED + tuple(s for s, _ in self.TILE_OWNED):
            a, b = self.final_colour(home, selector), self.final_colour(builder, selector)
            if a is not None and b is not None:
                self.assertEqual(a, b, selector)

    def test_filled_admin_shortcut_keeps_its_own_foreground_inside_every_header(self):
        css = read_css("apps/storefront_builder/static/css/storefront_builder.css")
        rule = next(d for s, d in iter_rules(css) if ".gh a.store-admin-shortcut" in s)
        self.assertEqual(rule["color"], "var(--brand-primary-fg,#fff)")
