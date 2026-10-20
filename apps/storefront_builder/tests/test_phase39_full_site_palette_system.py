from pathlib import Path

from django.conf import settings as django_settings

from apps.storefront_builder import appearance_registry

from .test_views import StorefrontBuilderViewsTestCase


class Phase39FullSitePaletteRegistryTests(StorefrontBuilderViewsTestCase):
    def test_at_least_twelve_dramatic_full_site_themes_exist(self):
        themes = [p for p in appearance_registry.list_palettes() if p.group_fa == "تم کامل"]
        self.assertGreaterEqual(len(themes), 12)
        for palette in themes:
            self.assertEqual(set(palette.theme_roles), set(appearance_registry.THEME_ROLE_KEYS))

    def test_black_gold_is_a_true_dark_theme_with_yellow_text(self):
        palette = appearance_registry.get_palette("theme-black-gold")
        self.assertEqual(palette.colors["background"], "#070707")
        self.assertEqual(palette.colors["surface"], "#151515")
        self.assertEqual(palette.colors["text"], "#FFE76A")
        self.assertEqual(palette.theme_roles["footer_bg"], "#030303")

    def test_manual_text_override_does_not_destroy_rest_of_theme(self):
        base = {
            "palette_slug": "theme-black-gold",
            "color_overrides": {},
            "theme_overrides": {},
        }
        before = appearance_registry.resolve_colors(base)
        after = appearance_registry.resolve_colors({
            **base,
            "color_overrides": {"text": "#FF0000"},
        })
        self.assertEqual(after["text"], "#FF0000")
        self.assertEqual(after["primary"], before["primary"])
        self.assertEqual(after["background"], before["background"])

    def test_region_override_can_change_only_footer(self):
        config = {
            "palette_slug": "theme-midnight-electric",
            "color_overrides": {},
            "theme_overrides": {"footer_bg": "#123456"},
        }
        roles = appearance_registry.resolve_theme_roles(config)
        self.assertEqual(roles["footer_bg"], "#123456")
        self.assertEqual(roles["header_bg"], "#070B18")


class Phase39GlobalThemeCssContractTests(StorefrontBuilderViewsTestCase):
    def test_theme_css_is_loaded_after_page_extra_css(self):
        root = Path(django_settings.BASE_DIR)
        base = (root / "templates/base.html").read_text(encoding="utf-8")
        extra = base.index("{% block extra_css %}{% endblock %}")
        theme = base.index("css/theme_palette.css")
        self.assertGreater(theme, extra)

    def test_theme_css_covers_all_major_storefront_surfaces(self):
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/core/static/css/theme_palette.css").read_text(encoding="utf-8")
        for needle in (
            ".header{",
            ".nav{",
            ".pcard,.card,.plp-filters",
            ".gallery .main",
            ".top,.stepper-bar",
            ".footer{",
            "--theme-card-bg",
        ):
            self.assertIn(needle, css)

    def test_theme_css_has_no_store_or_preset_specific_branch(self):
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/core/static/css/theme_palette.css").read_text(encoding="utf-8")
        self.assertNotIn("v5_golden_homepage", css)
        self.assertNotIn("golden-hero-row", css)
        self.assertNotIn("rastisi-fashion-test", css)

    def test_product_detail_rule_does_not_reset_thumbnail_background_image(self):
        """QA hotfix (post-Batch-2) — real browser QA found PDP gallery
        thumbnails (``product_main.html``'s ``.th`` buttons, each with its
        own inline ``background-image:url(...)``) rendering blank/white
        despite the underlying image/thumbnail files and URLs all being
        correct. Root cause: this Product Detail rule matches
        ``.gallery .thumbs .th`` and used the ``background`` *shorthand*
        with ``!important`` — the shorthand resets every background
        sub-property, including ``background-image``, to its initial value
        (``none``) even when only a color was written, and ``!important``
        makes that win over the thumbnail's own inline style. Using
        ``background-color`` instead only ever sets the theme's surface
        fallback color, never touching ``background-image``."""
        root = Path(django_settings.BASE_DIR)
        css = (root / "apps/core/static/css/theme_palette.css").read_text(encoding="utf-8")
        rule_start = css.index("/* Product detail */")
        rule_end = css.index("}", rule_start) + 1
        rule = css[rule_start:rule_end]

        self.assertIn(".gallery .thumbs .th", rule)
        self.assertIn("background-color:var(--theme-card-bg,var(--theme-surface))!important", rule)
        # The exact shorthand form that resets background-image — checked
        # as its own fragment (not a substring of "background-color:") so
        # a future edit can't silently reintroduce it.
        self.assertNotIn("background:var(--theme-card-bg,var(--theme-surface))!important", rule)

    def test_pdp_thumbnail_inline_background_image_is_untouched_by_the_palette_rule(self):
        """Companion rendering-level check: the PDP template still emits a
        real inline ``background-image`` on each gallery thumbnail — the
        CSS fix above is only meaningful because this inline style exists
        and needs to survive the cascade."""
        root = Path(django_settings.BASE_DIR)
        template = (
            root / "apps/storefront_builder/templates/storefront_builder/sections/product_main.html"
        ).read_text(encoding="utf-8")
        self.assertIn('class="th"', template)
        self.assertIn("background-image:url('{{ slide.thumb_url }}')", template)
