"""Background ownership / primary-surface contract.

Owner QA: Design → Background → Custom colour on «پیشنهادهای شگفت‌انگیز» changed nothing the merchant could see. The wrapper
carried the right colour, but the widget's own white panel (``.special-wrap`` + a ``#f7f8fa`` list + a white gradient
``.special-panels``) covered ~94 % of the section, and a shared ``!important`` card rule in ``theme_palette.css`` kept it white.

The contract pinned here is generic engine behaviour (no section key, no Ready Template key):

* a component whose main surface IS the section marks itself ``data-sfb-section-surface``; under an explicit section fill it
  becomes transparent (picture fill: a translucent scrim) and, as ``ink``, takes the fill's accessible foreground;
* inner cards / list buttons / product-media tiles stay independent semantic surfaces (tokens, never fixed hex);
* an explicit fill is rendered by the SAME wrapper in Preview and Published, and the Studio gets it back as a script-free
  canonical fragment, so the edit is a partial refresh (a ``<script>`` in a fragment forces a full iframe reload).

Real-browser proof (computed styles, the 20-section audit, live colour input, mini/main parity) is in
``test_background_contract_browser.py`` (opt-in)."""

import re
from decimal import Decimal
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.core.color_utils import contrast_ratio
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.qa import background_contract as bgc
from apps.storefront_builder.services import layout_service as svc, section_structure_service as sss
from apps.storefront_builder.services.render_service import build_render_items

from .test_r4_mutation_api import R4MutationApiTestCase

APP = Path(__file__).resolve().parents[1]
BUILDER_CSS = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
HOME_CSS = (APP.parent / "catalog" / "static" / "css" / "home.css").read_text(encoding="utf-8")
THEME_CSS = (APP.parent / "core" / "static" / "css" / "theme_palette.css").read_text(encoding="utf-8")
TEMPLATES = APP / "templates" / "storefront_builder"
WRAPPER = "storefront_builder/partials/responsive_section_wrapper.html"
MARK = "data-sfb-section-surface"
BLUE, WHITE, DARK = "#0057FF", "#FFFFFF", "#101828"


def _read(*parts):
    return TEMPLATES.joinpath(*parts).read_text(encoding="utf-8")


def _contract_block():
    start = BUILDER_CSS.index("PRIMARY-SURFACE CONTRACT")
    return BUILDER_CSS[start:]


def _rules(css, selector):
    """The declarations of every flat top-level ``selector{...}`` rule (one rule per line start)."""
    return re.findall(r"(?m)^" + re.escape(selector) + r"\{([^{}]*)\}", css)


def _bg_values(declarations):
    return re.findall(r"(?<![-\w])background(?:-color|-image)?\s*:\s*([^;]+)", declarations)


class PrimarySurfaceContractSourceTests(SimpleTestCase):
    def test_contract_is_generic_and_names_no_template_or_section(self):
        block = _contract_block()
        selectors = re.findall(r"([^{}]+)\{", block)
        for selector in selectors:
            self.assertNotRegex(selector, r"template-\d|stationery|data-template|data-layout-preset|data-ready",
                                f"template-key selector in the contract: {selector.strip()}")
        # the whole fill vocabulary is covered by the generic selectors
        for mode in ("color", "pattern", "palette", "palette_pattern", "image"):
            self.assertIn(f'[data-bg-mode="{mode}"]', block)
        self.assertIn("[data-sfb-section-surface]", block)
        self.assertIn(':not([data-d~="surface"])', block)  # an explicit design «رنگ سطح» still wins over the fill

    def test_marked_surface_beats_the_palette_sheets_important_card_rule(self):
        # theme_palette.css paints shared homepage cards with !important; the contract must out-rank it
        self.assertRegex(THEME_CSS, r"\.special-wrap,[^{]*\{\s*background:var\(--theme-card-bg,var\(--theme-surface\)\)!important")
        block = _contract_block()
        explicit = re.search(r'\[data-bg-mode="color"\][^{]*\[data-sfb-section-surface\]\{([^}]*)\}', block).group(1)
        self.assertIn("background-color:transparent!important", explicit)
        self.assertIn("background-image:none!important", explicit)
        image = re.search(r'\[data-bg-mode="image"\][^{]*\[data-sfb-section-surface\]\{([^}]*)\}', block).group(1)
        self.assertIn("!important", image)
        self.assertIn("color-mix(", image)  # a translucent scrim, never an opaque panel over the picture
        self.assertRegex(block, r'\[data-sfb-section-surface="ink"\]\{color:var\(--ssf-fg\)!important\}')

    def test_every_primary_surface_is_marked_in_its_template(self):
        amazing = _read("sections", "amazing_offers.html")
        self.assertRegex(amazing, rf'<div class="special-wrap" {MARK}="ink"')
        hero = _read("partials", "hero_slider_body.html")
        self.assertEqual(len(re.findall(rf'class="hero-inner[^"]*"[^>]*{MARK}', hero)), 2)
        products = _read("sections", "product_section.html")
        for name in ("product-spotlight-slider", "product-spotlight-head", "product-spotlight-track"):
            self.assertRegex(products, rf'class="{name}"[^>]*{MARK}="ink"')
        self.assertRegex(products, rf"<section class=\"section product-section[^>]*{{% if [^%]*carousel[^%]*%}} {MARK}=\"ink\"")
        trust = _read("sections", "trust_features.html")
        self.assertEqual(len(re.findall(rf'<div class="feat"[^>]*{MARK}="ink"', trust)), 5)

    def test_amazing_offers_fragment_has_no_script_so_edits_stay_a_partial_refresh(self):
        amazing = re.sub(r"{% comment %}.*?{% endcomment %}", "", _read("sections", "amazing_offers.html"), flags=re.S)
        self.assertNotIn("<script", amazing)  # the Studio rejects a fragment with a <script> and reloads the whole iframe
        self.assertIn("x-init=\"start()\"", amazing)
        self.assertNotIn("Alpine.data('countdown')", amazing)

    def test_amazing_offers_has_no_fixed_surface_colours_left(self):
        """Every visible fill of the widget is a semantic token or transparent — in the Studio sheet AND in legacy home.css."""
        for sheet_name, css in (("storefront_builder.css", BUILDER_CSS), ("home.css", HOME_CSS)):
            for selector in (".special-wrap", ".special-panels", ".special-list", ".amazing-offers-section .special-list"):
                for declarations in _rules(css, selector):
                    for value in _bg_values(declarations):
                        self.assertNotRegex(
                            value.strip(),
                            r"^(#[0-9a-fA-F]{3,8}|rgba?\(|linear-gradient\()",
                            f"{sheet_name}: fixed surface {value!r} in {selector}")
        # the panel / list surfaces are tokens
        wrap = _rules(BUILDER_CSS, ".special-wrap")[0]
        self.assertIn("background:var(--brand-surface,#fff)", wrap)
        self.assertIn("border:1px solid var(--brand-border,#e0e3e8)", wrap)
        self.assertNotIn("linear-gradient", _rules(HOME_CSS, ".special-panels")[0])
        self.assertNotIn("#f7f8fa", "".join(_rules(HOME_CSS, ".amazing-offers-section .special-list")))

    def test_amazing_offers_inks_follow_the_fill_or_the_semantic_tokens(self):
        for selector, token in ((".special-kicker", "--ssf-accent"), (".special-count", "--ssf-accent"),
                                (".special-brand", "--ssf-muted"), (".special-price del", "--ssf-muted"),
                                (".special-price strong", "--ssf-price")):
            self.assertIn(token, _rules(BUILDER_CSS, selector)[0], selector)
        self.assertIn("color:inherit", _rules(BUILDER_CSS, ".special-copy h3")[0])
        # the product-media tile and the discount badge are the only intentional non-fill neutrals
        self.assertIn("background:var(--brand-surface,#fff)", _rules(BUILDER_CSS, ".special-image")[0])
        self.assertIn("background:#d53d3d", _rules(BUILDER_CSS, ".special-discount")[0])  # danger / sale accent

    def test_design_surface_alias_does_not_paint_the_primary_surface_over_the_fill(self):
        # «رنگ سطح» (data-d~=surface) re-paints the wrapper; bands/amazing offers keep their own explicit surface rule
        self.assertIn(':not(:has(.special-wrap))', BUILDER_CSS)
        self.assertIn(".rsec[data-d~=\"surface\"] .special-wrap{background:var(--d-surface);color:var(--d-surface-fg)}", BUILDER_CSS)


class BackgroundAuditClassifierTests(SimpleTestCase):
    """``qa.background_contract.classify`` — the verdict vocabulary of the 20-section audit."""

    def _m(self, **kw):
        base = {"blueSeen": True, "dominantShare": 10, "dominantIsMedia": False, "dominantIsCard": False, "ring": 100,
                "coverage": 60, "styleHasFill": True}
        return {**base, **kw}

    def test_verdicts(self):
        white = self._m()
        self.assertEqual(bgc.classify(white, self._m()), "PASS")
        self.assertEqual(bgc.classify(white, self._m(dominantShare=94)), "HIDDEN BY INNER SURFACE")
        self.assertEqual(bgc.classify(white, self._m(blueSeen=False)), "OVERRIDDEN BY CSS")
        self.assertEqual(bgc.classify(white, self._m(blueSeen=False, styleHasFill=False)), "NO CONSUMER")
        self.assertEqual(bgc.classify(white, self._m(ring=10, coverage=2)), "PARTIAL ONLY")
        self.assertEqual(bgc.classify(white, self._m(dominantShare=72, dominantIsCard=True)), "PASS (CARD / MEDIA TILES)")
        self.assertEqual(bgc.classify({"empty": True}, self._m()), "NO CONTENT")


def _background(mode="color", color="", **extra):
    return {"mode": mode, "color": color, "media_asset_id": None, "pattern_slug": "", "palette_role": "", **extra}


class AmazingOffersBackgroundRoundTripTests(R4MutationApiTestCase):
    """Colour → mutation → persisted settings → effective settings → canonical fragment == full Preview == Published."""

    def setUp(self):
        super().setUp()
        vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="bg-vendor")
        category = Category.objects.create(store=self.store, name="دسته", slug="bg-cat", is_active=True)
        for n in range(4):
            Product.objects.create(store=self.store, vendor=vendor, category=category, name=f"کالای تخفیف‌دار {n}",
                                   slug=f"bg-p-{n}", sku=f"BG-{n}", price=Decimal(200000 + n * 1000), discount_percent=20,
                                   stock=5, status=Product.Status.ACTIVE)
        self.offers = sss.add_section(draft=self.draft, section_key="amazing_offers", page_type="home")

    def _mutate(self, patch, *, fragment=True):
        self.draft.refresh_from_db()
        response = self._post_json({"base_revision": self.draft.edit_revision, "fragment": fragment, "mutation": {
            "type": "section.update_settings", "section_id": self.offers.pk, "patch": patch}})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _wrapper(self, html):
        start = html.rindex("<div", 0, html.index(f'data-section-id="{self.offers.pk}"'))
        return html[start:html.index(">", start) + 1]

    def test_custom_colour_round_trips_through_the_schema_and_reaches_the_wrapper_and_fragment(self):
        body = self._mutate({"background": _background(color=BLUE)})
        self.assertTrue(body["ok"])
        self.offers.refresh_from_db()
        self.assertEqual(self.offers.settings["background"]["color"].upper(), BLUE)
        self.assertEqual(self.offers.settings["background"]["mode"], "color")
        fragment = body["fragment"]
        self.assertEqual((fragment["kind"], fragment["id"]), ("section", self.offers.pk))
        html = fragment["html"]
        wrapper = self._wrapper(html)
        self.assertIn('data-bg-mode="color"', wrapper)
        self.assertRegex(wrapper, r"(?i)--sfb-section-bg-color:\s*#0057ff")
        self.assertRegex(wrapper, r"--sfb-section-fg:\s*#FFFFFF")  # accessible ink derived from the fill
        self.assertRegex(wrapper, r"(?i)background-color:\s*#0057ff")
        # the primary surface is marked and the fragment carries no <script> (partial refresh, no full iframe reload)
        self.assertRegex(html, rf'class="special-wrap" {MARK}="ink"')
        self.assertNotIn("<script", html)

    def test_fragment_is_exactly_the_section_of_the_full_preview(self):
        body = self._mutate({"background": _background(color=BLUE)})
        full = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home").content.decode()
        start = full.rindex('<div class="rsec', 0, full.index(f'data-section-id="{self.offers.pk}"'))
        end = full.find('<div class="rsec', start + 10)
        norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
        # the countdown deadline is "now + N hours": compare the markup with the timestamp neutralised
        mask = lambda s: re.sub(r"new Date\('[^']*'\)", "new Date('T')", norm(s))  # noqa: E731
        self.assertIn(mask(body["fragment"]["html"])[:1500], mask(full[start:end if end != -1 else len(full)]))

    def test_every_background_mode_reaches_the_wrapper_with_a_consumer(self):
        for patch, attrs in (
            (_background("palette", palette_role="tone-3"), ('data-bg-mode="palette"', 'data-palette-role="tone-3"')),
            (_background("palette_pattern", palette_role="tone-2", pattern_slug="commerce-doodle"),
             ('data-bg-mode="palette_pattern"',)),
            (_background("pattern", color="#102030", pattern_slug="commerce-doodle"), ('data-bg-mode="pattern"',)),
            (_background("color", color=DARK, bleed=True), ('data-bg-mode="color"', "data-bg-bleed")),
        ):
            html = self._mutate({"background": patch})["fragment"]["html"]
            wrapper = self._wrapper(html)
            for attr in attrs:
                self.assertIn(attr, wrapper, (patch, wrapper))
            self.assertIn(f'class="special-wrap" {MARK}="ink"', html)

    def test_foreground_token_has_aa_contrast_against_every_custom_fill(self):
        for fill in (WHITE, BLUE, DARK, "#F59E0B", "#7C3AED", "#EF4444", "#0F766E"):
            wrapper = self._wrapper(self._mutate({"background": _background(color=fill)})["fragment"]["html"])
            ink = re.search(r"--sfb-section-fg:\s*(#[0-9A-Fa-f]{6})", wrapper).group(1)
            self.assertGreaterEqual(contrast_ratio(ink, fill), 4.5, (fill, ink))

    def test_preview_and_published_render_the_same_fill_for_the_same_settings(self):
        self._mutate({"background": _background(color=BLUE, bleed=True)})
        layout = svc.get_or_create_layout(self.store)
        svc.publish(self.store)
        layout.refresh_from_db()
        published = layout.published_version
        draft_item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == self.offers.pk)
        pub_section = published.sections.get(section_key="amazing_offers")
        published_item = next(i for i in build_render_items(published, self.store) if i["section"].pk == pub_section.pk)
        preview = render_to_string(WRAPPER, {"item": draft_item, "is_preview": True})
        public = render_to_string(WRAPPER, {"item": published_item, "is_preview": False})

        def fill(html):
            tag = html[html.index("<div"):html.index(">", html.index("<div")) + 1]
            return {a: re.search(a + r'="([^"]*)"', tag).group(1) if re.search(a + r'="([^"]*)"', tag) else None
                    for a in ("data-bg-mode", "data-bg-bleed")} | {
                "vars": tuple(re.findall(r"(--sfb-section-(?:bg-color|fg):[^;\"]+)", tag)),
                "fill": re.search(r"background-color:[^;\"]+", tag).group(0)}

        self.assertEqual(fill(preview), fill(public))
        self.assertIn(f'{MARK}="ink"', public)


class EveryBackgroundSectionConsumesItsFillTests(R4MutationApiTestCase):
    """Server-side half of the Inspector honesty rule: whatever section exposes «پس‌زمینه این بخش», choosing a custom colour
    must reach the section wrapper as an inline fill + an accessible foreground token (nothing is a silent no-op).
    The painted result (inner surfaces) is proven for all of them by the opt-in browser audit."""

    def test_custom_colour_reaches_the_wrapper_of_every_section_that_offers_a_background(self):
        keys = [key for key, definition in section_registry.SECTION_REGISTRY.items()
                if definition.settings_schema and any(f.field_type == "background" for f in definition.settings_schema.fields)]
        self.assertGreaterEqual(len(keys), 20)
        checked = 0
        for key in keys:
            try:
                section = sss.add_section(draft=self.draft, section_key=key, page_type="home")
            except sss.SectionStructureError:
                continue  # not placeable on the home page (covered by its own page type in the browser audit)
            section.settings = {**section.settings, "background": _background(color=BLUE)}
            section.save()
            item = next(i for i in build_render_items(self.draft, self.store) if i["section"].pk == section.pk)
            html = render_to_string(WRAPPER, {"item": item, "is_preview": True})
            head = html[html.index("<div"):html.index(">", html.index("<div")) + 1]
            self.assertIn('data-bg-mode="color"', head, f"{key}: {head[:900]}")
            self.assertRegex(head, r"(?i)--sfb-section-bg-color:\s*#0057ff", key)
            self.assertRegex(head, r"--sfb-section-fg:\s*#FFFFFF", key)
            checked += 1
        self.assertGreaterEqual(checked, 18)
        self.assertEqual(StorefrontSection.objects.filter(page__version=self.draft).count() >= checked, True)
