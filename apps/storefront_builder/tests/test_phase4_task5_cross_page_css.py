"""Phase 4, Task 5 — cross-page CSS completeness.

Several section types were originally built Home-only: their CSS rules
lived only in ``apps/catalog/static/css/home.css``, which loads ONLY on
``catalog:home`` (see ``catalog/templates/catalog/home.html``). The five
other public envelopes (product detail, listing/search, collection, cart)
load ``apps/storefront_builder/static/css/storefront_builder.css`` instead
and never load ``home.css`` — so placing one of these Home-only-styled
sections on a non-Home page rendered its HTML correctly (shared Django
templates) but with no layout CSS at all.

Real-browser RED (before) / GREEN (after) computed-style proof for each
group lives in ``docs/qa_evidence/storefront_appearance_convergence/
phase4/task5_cross_page_css.md`` (Playwright against a live dev server is
the actual verification technique here, since computed CSS layout cannot
be proven by a Django test client). These tests are the permanent,
fast, CI-run regression guard: they assert the section renders on a
non-Home page AND that the CSS declarations the fix depends on are
present in ``storefront_builder.css`` — so a future edit that
accidentally deletes this block is caught immediately, without needing a
browser.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import HeroSlide
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service
from apps.stores.models import Store, StoreDomain

HOST = "sfb-task5.example.com"

_STOREFRONT_BUILDER_CSS = (
    Path(settings.BASE_DIR) / "apps" / "storefront_builder" / "static" / "css" / "storefront_builder.css"
)
_PRODUCT_CARD_CSS = Path(settings.BASE_DIR) / "apps" / "catalog" / "static" / "css" / "product_card.css"


def _akhlaghi() -> Store:
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class HeroSliderNonHomeCssCompletenessTests(TestCase):
    """Group A1 — hero_banner's default ``overlay`` style and image_slider
    share the exact same template (``partials/hero_slider_body.html``), so
    this is one root cause with one fix, verified for both section keys."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def _place_and_publish(self, section_key: str, page_type: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key=section_key, page_type=page_type,
        )
        HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید تست",
            destination_type="none", is_active=True, display_order=0,
        )
        svc.publish(self.store)
        return section

    def test_hero_banner_overlay_renders_on_cart(self):
        self._place_and_publish("hero_banner", StorefrontPage.PageType.CART)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section hero"', html)
        self.assertIn('class="hero-slide single"', html)

    def test_image_slider_renders_on_listing(self):
        self._place_and_publish("image_slider", StorefrontPage.PageType.LISTING)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section hero"', html)
        self.assertIn('class="hero-slide single"', html)

    def test_storefront_builder_css_carries_the_base_hero_layout_rules(self):
        # The exact declarations a broken/reverted mirror would be missing —
        # not a full copy of home.css, just the load-bearing subset that
        # gives the slider its absolute-positioned-overlay layout.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".hero-slide{position:absolute;inset:0;width:100%;height:100%}", css)
        self.assertIn(".hero-media{display:block;width:100%;height:100%}", css)
        self.assertIn(
            '.hero-inner{position:relative;overflow:hidden;border:1px solid #e2e5ea;'
            'border-radius:8px;background:#fff;aspect-ratio:1053/420;min-height:0;'
            'color:#fff;box-shadow:0 2px 10px rgba(15,23,42,.05)}',
            css,
        )

    def test_storefront_builder_css_carries_the_later_hero_cascade_overrides(self):
        # home.css layers two further, unconditioned passes ("V3 universal
        # dense-marketplace fidelity pass", "V4.2.2 readability calibration")
        # on top of the base hero rule above, plus their own mobile reset for
        # .hero-text — all equal-specificity plain-class rules, so which one
        # a browser actually renders depends on this file's own text order
        # matching home.css's, not just each declaration's mere presence.
        # Missing this layer was a real review-caught gap: hero_banner/
        # image_slider rendered structurally correct but with the wrong text
        # color/shadow, CTA shape, and tabs gradient above 680px.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".hero-inner{border-radius:6px;box-shadow:0 2px 8px rgba(15,23,42,.05)}", css)
        self.assertIn(
            '.hero-text{inset-inline-end:34px;bottom:48px;max-width:48%;'
            'padding:7px 10px;text-shadow:none;color:#24252a}',
            css,
        )
        self.assertIn(
            '.hero-cta{min-width:88px;height:30px;border-radius:18px;border:0;'
            'background:#fff;color:#222;font-weight:800;box-shadow:0 1px 4px rgba(0,0,0,.12)}',
            css,
        )
        self.assertIn(
            '.hero-tabs{padding-top:18px;'
            'background:linear-gradient(0deg,rgba(40,55,70,.72),transparent)}',
            css,
        )
        self.assertIn('.hero-cta{font-size:11.2px}', css)
        # The override block must appear AFTER the base block (cascade order
        # is what makes it win) — not merely present somewhere in the file.
        self.assertLess(
            css.index(".hero-slide{position:absolute;inset:0;width:100%;height:100%}"),
            css.index(".hero-inner{border-radius:6px;box-shadow:0 2px 8px rgba(15,23,42,.05)}"),
        )
        self.assertIn('.hero-inner[data-text-position="center"] .hero-text{', css)

    def test_storefront_builder_css_carries_the_pre_v3_responsive_hero_overrides(self):
        # A third, EARLIER "===== responsive =====" section in home.css
        # (before the V3/V4.2.2 comment headers, so a v3/v4.2.2-only sweep
        # doesn't find it) sets .hero-inner text-align/padding and
        # .hero-text h1/p margin-inline at the SAME two breakpoints already
        # mirrored above. A review-caught CRITICAL gap: missing this made
        # hero_banner/image_slider render un-centered at 681-1000px and
        # un-inset at <=680px, a real visible divergence from Home.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".hero-inner{aspect-ratio:16/7;text-align:center}", css)
        self.assertIn(".hero-text h1{margin-inline:auto}", css)
        self.assertIn(".hero-text p{margin-inline:auto}", css)
        self.assertIn(
            ".hero-inner{aspect-ratio:auto;min-height:300px;border-radius:5px;padding:28px 22px}",
            css,
        )

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class ProductSectionSpotlightAndCampaignBandNonHomeCssTests(TestCase):
    """Group A2 — product_section's "spotlight" (carousel + autoplay) and
    "campaign_band" display modes. Investigated and REFUTED the plan's
    hypothesis that this shares a CSS root with amazing_offers (disjoint
    class families, verified zero selector overlap) — fixed here as its
    own independent gap; amazing_offers is Group A3.

    ``render_service.hide_empty_public_sections`` deliberately hides
    ``product_section`` on Public when it resolves zero products (a
    pre-existing, unrelated rule) — so, unlike the hero fixture, this
    needs at least one real Product for the section to render at all."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Product, Vendor

        vendor = Vendor.objects.create(store=self.store, slug="task5-vendor", name="فروشنده تست")
        Product.objects.create(
            store=self.store, vendor=vendor, name="کالای تست", slug="task5-product",
            sku="T5-P", price="100000", status="active",
        )

    def _place_and_publish(self, page_type: str, settings_patch: dict):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="product_section", page_type=page_type,
        )
        section.settings = {**section.settings, **settings_patch}
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_spotlight_mode_renders_on_cart(self):
        self._place_and_publish(
            StorefrontPage.PageType.CART,
            {"display_mode": "carousel", "carousel_autoplay": True},
        )
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('product-section--spotlight', html)
        self.assertIn('class="product-spotlight-track"', html)

    def test_campaign_band_mode_renders_on_listing(self):
        self._place_and_publish(
            StorefrontPage.PageType.LISTING, {"display_mode": "campaign_band"},
        )
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('product-section--campaign-band', html)
        self.assertIn('class="product-campaign-band"', html)

    def test_storefront_builder_css_carries_the_spotlight_and_campaign_band_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        # The base rule AND the later overriding rule for the same selector
        # (home.css layers two `.product-section--spotlight` rules — border/
        # background only exist in the second one) — both required.
        self.assertIn(".product-section--spotlight{height:100%;display:flex;flex-direction:column}", css)
        self.assertIn(
            ".product-section--spotlight{height:100%;margin:0;border:1px solid #e1e4e8;"
            "border-top:2px solid var(--brand-accent,#f43f5e);border-radius:6px;"
            "background:#fff;overflow:hidden;display:flex;flex-direction:column}",
            css,
        )
        self.assertIn(
            ".product-spotlight-track{position:relative;display:grid;"
            "grid-template-columns:minmax(0,1fr);flex:1;min-height:0;background:#fff}",
            css,
        )
        self.assertIn(
            ".product-campaign-band{display:grid;"
            "grid-template-columns:minmax(168px,2.05fr) minmax(0,9.95fr);"
            "gap:12px;align-items:stretch;min-width:0}",
            css,
        )
        self.assertIn('.beauty-section-title{display:grid;grid-template-columns:1fr auto 1fr', css)

    def test_storefront_builder_css_carries_the_later_spotlight_cascade_overrides(self):
        # Same missing-cascade-layer issue as hero (see the hero test above)
        # — home.css's V3/V4.2.2 passes also touch product-spotlight-head's
        # font-size and .beauty-section-title's own mobile breakpoint.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".product-spotlight-slider{border-radius:6px;border-color:#e0e2e6}", css)
        self.assertIn(".product-spotlight-head h2{font-size:13.5px}", css)
        self.assertIn(".beauty-section-title{gap:10px;margin-bottom:14px}", css)
        self.assertLess(
            css.index(".product-spotlight-track{position:relative;display:grid;"
                       "grid-template-columns:minmax(0,1fr);flex:1;min-height:0;background:#fff}"),
            css.index(".product-spotlight-head h2{font-size:13.5px}"),
        )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class AmazingOffersNonHomeCssTests(TestCase):
    """Group A3 — amazing_offers. Confirmed (Group A2's evidence) zero
    selector overlap with product_section; an independent fix.

    home.css layers this selector family across four passes (base, "V3",
    a desktop-only "V4 Golden" list-left/image-right direction mirror, and
    "V4.2.2"), plus three separate margin-only overrides. The CSS mirror
    stores the MERGED FINAL value per property/breakpoint (verified
    against a real browser) rather than re-typing every historical layer
    — see the CSS file's own comment for why that is equivalent."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Product, Vendor

        vendor = Vendor.objects.create(store=self.store, slug="task5-a3-vendor", name="فروشنده تست")
        for i in range(2):
            Product.objects.create(
                store=self.store, vendor=vendor, name=f"کالای تست {i}", slug=f"task5-a3-product-{i}",
                sku=f"T5A3-P{i}", price="100000", status="active", discount_percent=20,
            )

    def _place_and_publish(self, page_type: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="amazing_offers", page_type=page_type,
        )
        section.settings = {**section.settings, "item_limit": 2}
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_renders_on_cart(self):
        # amazing_offers is in render_service.OPTIONAL_PRODUCT_DATA_SECTION_KEYS
        # (hidden on Public with zero resolved products) — the discounted
        # products in setUp are required, not incidental.
        self._place_and_publish(StorefrontPage.PageType.CART)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section amazing-offers-section"', html)
        self.assertIn('class="special-wrap"', html)

    def test_storefront_builder_css_carries_the_merged_final_special_offer_rules(self):
        # Broad, near-exhaustive coverage (not just 4 of ~24 selectors) —
        # a review-caught CRITICAL bug (.special-discount's font-size
        # carried the SUPERSEDED base layer's 10px instead of the later V3
        # pass's 9px, even though the sibling height/min-width properties
        # on that exact same selector/line were merged correctly) shipped
        # undetected specifically because this test didn't touch that
        # selector at all. Every multi-layer-merged selector is now
        # asserted with its FULL final declaration, not a substring, so a
        # similar one-property merge error cannot pass silently again.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".amazing-offers-section{margin:7px 0}", css)
        self.assertIn(
            ".special-wrap{display:grid;grid-template-columns:290px minmax(0,1fr);"
            "gap:0;background:#fff;border:1px solid #e0e3e8;border-radius:5px;"
            "overflow:hidden;box-shadow:0 1px 6px rgba(15,23,42,.05);min-height:250px}",
            css,
        )
        self.assertIn(
            ".special-list{order:1;background:#f7f8fa;border-inline-end:1px solid #e5e7eb;"
            "padding:8px;display:flex;flex-direction:column;gap:4px;min-width:0}",
            css,
        )
        self.assertIn(
            ".special-list-title{display:flex;flex-direction:column;gap:5px;"
            "padding:2px 3px 6px;border-bottom:1px solid #e2e5e9;font-weight:800;"
            "font-size:12px;color:#24272c}",
            css,
        )
        self.assertIn(
            ".special-list>button{display:grid;grid-template-columns:minmax(0,1fr) auto;"
            "align-items:center;gap:8px;width:100%;min-height:42px;padding:6px 8px;"
            "border:1px solid transparent;border-radius:3px;background:#fff;"
            "color:#4b4f56;text-align:right;cursor:pointer}",
            css,
        )
        self.assertIn(
            ".special-list-name{min-width:0;font-size:10.8px;line-height:1.6;"
            "white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
            css,
        )
        self.assertIn(".special-list-price{font-size:9.8px;color:#767b84;white-space:nowrap}", css)
        self.assertIn(
            ".special-main{grid-area:1/1;min-width:0;display:grid;"
            "grid-template-columns:minmax(0,1fr) minmax(230px,37%);align-items:center;"
            "padding:16px 22px;gap:16px}",
            css,
        )
        self.assertIn(
            ".special-copy{display:flex;flex-direction:column;align-items:flex-start;"
            "gap:6px;min-width:0}",
            css,
        )
        self.assertIn(".special-kicker{font-size:10.5px;color:#ef4444;font-weight:800}", css)
        # The exact selector the CRITICAL merge error landed on.
        self.assertIn(
            ".special-discount{display:inline-grid;place-items:center;min-width:39px;"
            "height:22px;border-radius:999px;background:#ef4444;color:#fff;"
            "font-size:9px;font-weight:900}",
            css,
        )
        self.assertIn(
            ".special-copy h3{font-size:18px;line-height:1.55;font-weight:800;"
            "color:#222;margin:0;max-width:520px}",
            css,
        )
        self.assertIn(".special-brand{font-size:10px;color:#777d86;margin:0}", css)
        self.assertIn(".special-price strong{font-size:18px;color:#169b62;font-weight:800}", css)
        self.assertIn(".special-price del{font-size:10px;color:#9aa0a6}", css)
        self.assertIn(
            ".special-buy{margin-top:4px;border:1px solid #34383f;background:#fff;"
            "color:#292d33;border-radius:2px;padding:6px 12px;font-size:10.5px;"
            "font-weight:700}",
            css,
        )
        self.assertIn(
            ".special-image{height:215px;display:grid;place-items:center;"
            "overflow:hidden;border-radius:4px;background:#fff}",
            css,
        )
        self.assertIn(
            ".amazing-offers-section .special-wrap{direction:ltr;"
            "grid-template-columns:270px minmax(0,1fr)}",
            css,
        )
        self.assertIn(
            ".amazing-offers-section .special-main{direction:ltr;"
            "grid-template-columns:minmax(0,1fr) minmax(210px,34%);padding:14px 20px;gap:14px}",
            css,
        )
        self.assertIn(".amazing-offers-section .special-image{direction:rtl;height:205px}", css)
        # The two older, unrelated "special offers" widget definitions
        # elsewhere in home.css (`.special-list>a`, no title/kicker/discount/
        # brand classes) must never get pulled in — this mirror is scoped to
        # the ONE widget amazing_offers.html actually emits.
        self.assertNotIn(".special-list>a{", css)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BannerNonHomeCssTests(TestCase):
    """Group B — single_banner (`.promo-dark`) and multi_banner
    (`.banner-section`/`.promo-grid`/`.promo-grid--{layout_variant}`/
    `.promo-card`/`.promo-media`/`.promo-overlay`). All 6 real
    `layout_variant` values (``section_registry.
    MULTI_BANNER_KNOWN_LAYOUT_VARIANTS``) are in scope — unlike
    hero_banner's variants (separate registered renderers), multi_banner
    is ONE template branching purely on this CSS class suffix."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def _place_and_publish(self, section_key: str, page_type: str, settings_patch: dict | None = None):
        from apps.content.models import PromotionalBanner

        section = section_structure_service.add_section(
            draft=self.draft, section_key=section_key, page_type=page_type,
        )
        if settings_patch:
            section.settings = {**section.settings, **settings_patch}
            section.save(update_fields=["settings"])
        PromotionalBanner.objects.create(
            store=self.store, section=section, title="بنر تست",
            destination_type="none", is_active=True, display_order=0,
        )
        svc.publish(self.store)
        return section

    def test_single_banner_renders_on_cart(self):
        self._place_and_publish("single_banner", StorefrontPage.PageType.CART)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('class="promo-dark"', resp.content.decode())

    def test_multi_banner_strip_variant_renders_on_listing(self):
        self._place_and_publish(
            "multi_banner", StorefrontPage.PageType.LISTING, {"layout_variant": "strip"},
        )
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("promo-grid--strip", html)
        self.assertIn('class="promo-card"', html)

    def test_storefront_builder_css_carries_the_promo_dark_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".promo-dark{position:relative;border-radius:22px;overflow:hidden;"
            "background:linear-gradient(100deg,#2a2440,#3b2f63);color:#fff;"
            "display:grid;grid-template-columns:1.3fr 1fr;align-items:center;"
            "padding:34px 40px;gap:20px}",
            css,
        )
        self.assertIn(
            ".promo-dark .mini{background:#fff;color:var(--ink);border-radius:16px;"
            "padding:12px;display:flex;gap:12px;align-items:center;max-width:300px;"
            "position:relative;z-index:2}",
            css,
        )
        self.assertIn(".promo-dark{grid-template-columns:1fr;text-align:center}", css)

    def test_storefront_builder_css_carries_the_merged_final_banner_grid_rules(self):
        # Broad coverage after the amazing_offers review lesson: assert the
        # FULL final declaration for every multi-layer-merged selector, not
        # a narrow substring, so a one-property merge error cannot pass
        # silently (e.g. .promo-card's border/min-height/box-shadow/
        # border-radius are each individually merged from 2-3 separate
        # passes; .promo-overlay/strong/em similarly).
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".banner-section{margin:7px 0}", css)
        self.assertIn(".promo-grid{gap:12px}", css)
        self.assertIn(
            ".promo-card{position:relative;display:block;overflow:hidden;"
            "border-radius:5px;background:#fff;border:1px solid #dfe3e8;"
            "min-height:260px;box-shadow:0 1px 5px rgba(15,23,42,.05)}",
            css,
        )
        self.assertIn(
            ".promo-overlay{position:absolute;inset:auto 0 0 0;z-index:2;"
            "display:flex;flex-direction:column;gap:4px;padding:32px 11px 8px;"
            "color:#111;background:linear-gradient(0deg,rgba(255,255,255,.96),"
            "rgba(255,255,255,.70) 58%,transparent)}",
            css,
        )
        self.assertIn(".promo-overlay strong{font-size:12.2px;font-weight:800;line-height:1.6}", css)
        # Judgment call 1 (documented in the CSS comment): .promo-overlay
        # small is display:none on Home today — mirrored byte-for-byte,
        # not "fixed", since matching Home's actual current rendering (not
        # a suspected pre-existing bug) is this task's job.
        self.assertIn(".promo-overlay small{display:none;font-size:10.6px;line-height:1.6;color:#555}", css)
        self.assertIn(
            ".promo-overlay em{display:inline-flex;align-self:flex-start;"
            "background:#fff;border:1px solid #222;border-radius:10px;"
            "padding:1px 7px;font-size:9.5px;font-style:normal}",
            css,
        )
        self.assertIn(
            ".promo-grid--strip .promo-card{min-height:48px!important;"
            "background:#fff;border:1px solid #e1e4e8;box-shadow:0 1px 4px rgba(15,23,42,.04)}",
            css,
        )
        self.assertIn(
            ".promo-grid--strip .promo-overlay{inset:0;display:flex;"
            "align-items:center;justify-content:center;padding:0 14px;"
            "background:#fff;text-align:center;color:#e4475d}",
            css,
        )
        # Judgment call 2 (documented in the CSS comment): atelier-duo's
        # card min-height is set at THREE overlapping max-width scopes;
        # below 680px the later-in-file @680 rule wins over @900, not the
        # "more specific-sounding" narrower breakpoint.
        self.assertIn(".promo-grid--atelier-duo .promo-card{min-height:410px;border-radius:0}", css)
        self.assertIn(".promo-grid--atelier-duo .promo-card{min-height:320px}", css)
        self.assertIn(".promo-grid--atelier-duo .promo-card{min-height:250px}", css)
        # Review-caught CRITICAL: the original ordering check searched for
        # the first "@media(max-width:900px)"/"@media(max-width:680px)"
        # ANYWHERE in this ~4900-line file — matching unrelated,
        # pre-existing blocks elsewhere, never Group B's own two blocks —
        # so it would still pass even if Group B's own 900px/680px blocks
        # were swapped, silently breaking the atelier-duo 3-tier cascade
        # this check exists to protect. Anchored directly to the two
        # Group-B-specific, uniquely-identifying declarations instead.
        idx_320 = css.index(".promo-grid--atelier-duo .promo-card{min-height:320px}")
        idx_250 = css.index(".promo-grid--atelier-duo .promo-card{min-height:250px}")
        self.assertLess(idx_320, idx_250)
        # No unrelated class from the same home.css "responsive" block
        # (`.orig` — a different, unrelated section) pulled in. `.tiles`
        # was the other neighbor in that same source block, but it is now
        # a legitimate Group C1 selector (see CategoryGridTilesNonHomeCssTests
        # below) — asserting its absence here would be a false positive,
        # not a real leak check, so that half of the original check moved
        # to Group C1's own test instead of staying here.
        self.assertNotIn(".orig{grid-template-columns", css)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CategoryGridTilesNonHomeCssTests(TestCase):
    """Group C1 — category_grid's plain "grid" and "carousel" display
    modes: the template's shared final branches (an explicit merchant
    ``category_ids`` selection, or — when that list is empty — an
    auto-picked top-level category set) both render the identical
    ``.tiles``/``.tiles-carousel``/``.tile``/``.wm``/``h4``/``.btn``
    markup (verified by reading ``category_grid.html`` directly), so an
    explicit selection is used here for a deterministic fixture rather
    than depending on auto-pick ordering. Unlike every other Task 5
    group so far, home.css defines this whole selector family in a
    single, unscattered generation (base rule plus one
    ``@media(max-width:1000px)`` collapse) — confirmed via an exhaustive
    whole-file grep before writing this fix, so no multi-pass cascade
    merge/ordering assertion is needed here."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Category

        self.cat_a = Category.objects.create(
            store=self.store, name="دسته الف", slug="task5-c1-cat-a", is_active=True,
        )
        self.cat_b = Category.objects.create(
            store=self.store, name="دسته ب", slug="task5-c1-cat-b", is_active=True,
        )

    def _place_and_publish(self, page_type: str, display_mode: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="category_grid", page_type=page_type,
        )
        section.settings = {
            **section.settings,
            "display_mode": display_mode,
            "category_ids": [self.cat_a.pk, self.cat_b.pk],
        }
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_grid_mode_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART, "grid")
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="tiles"', html)
        self.assertIn('class="tile t1"', html)
        self.assertIn('class="tile t2"', html)

    def test_carousel_mode_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING, "carousel")
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="tiles-carousel"', html)
        self.assertIn('class="tile t1"', html)

    def test_storefront_builder_css_carries_the_tiles_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}", css)
        self.assertIn(
            ".tile{position:relative;border-radius:20px;overflow:hidden;min-height:200px;"
            "padding:24px;color:#fff;display:flex;flex-direction:column;"
            "justify-content:flex-end;transition:.25s}",
            css,
        )
        self.assertIn(".tile:hover{transform:translateY(-3px)}", css)
        self.assertIn(".tile .wm{position:absolute;top:10px;left:14px;font-size:90px;opacity:.22}", css)
        self.assertIn(
            ".tile::after{content:'';position:absolute;inset:0;"
            "background:linear-gradient(transparent 30%,rgba(0,0,0,.45))}",
            css,
        )
        self.assertIn(".tile>*{position:relative;z-index:2}", css)
        self.assertIn(".tile h4{font-size:16px;font-weight:800;margin-bottom:10px}", css)
        self.assertIn(
            ".tile .btn{width:fit-content;padding:8px 16px;font-size:12px;"
            "background:rgba(255,255,255,.92);color:var(--ink)}",
            css,
        )
        self.assertIn(".t1{background:linear-gradient(135deg,#0ea5a3,#13c2c2)}", css)
        self.assertIn(".t2{background:linear-gradient(135deg,#334155,#475569)}", css)
        self.assertIn(".t3{background:linear-gradient(135deg,#e0567f,#f06595)}", css)
        self.assertIn(
            ".tiles-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;"
            "padding-bottom:6px;-webkit-overflow-scrolling:touch}",
            css,
        )
        self.assertIn(
            ".tiles-carousel .tile{flex:0 0 240px;scroll-snap-align:start;min-height:180px}", css,
        )
        self.assertIn("@media(max-width:1000px){\n  .tiles{grid-template-columns:1fr}\n}", css)
        self.assertIn("@media(max-width:680px){\n  .tiles-carousel .tile{flex-basis:200px}\n}", css)
        # This must be the BARE `.tiles-carousel` rule, on its own line —
        # not merely a substring match against the pre-existing
        # `collection_tiles` carousel mirror elsewhere in this file,
        # which deliberately uses the compound
        # `.collection-tiles-carousel.tiles-carousel` selector (its
        # declaration body happens to be textually identical, so a plain
        # substring check would pass even if this rule were deleted).
        self.assertIn(
            "\n.tiles-carousel{display:flex;gap:16px;overflow-x:auto;scroll-snap-type:x mandatory;"
            "padding-bottom:6px;-webkit-overflow-scrolling:touch}",
            css,
        )

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CategoryGridCircularNonHomeCssTests(TestCase):
    """Group C2 — category_grid's "circular" display mode
    (`.tiles-circular`/`.tile-circle`/`.tile-circle-img`/`.tile-circle-wm`/
    `.tile-circle-label`). home.css layers this family across 4 passes
    (base + 3 unconditioned overrides, one with its own @1000px block) —
    the most cascade-scattered category_grid mode. Real-browser
    ground-truth verification (a standalone harness loading home.css
    alone against this exact markup, not just reading the source)
    confirmed the base pass's and the "Universal dense storefront
    modules" pass's own @680px overrides for `.tile-circle`/
    `.tile-circle-img` are dead code — completely shadowed at every
    viewport by the later, unconditioned "V3" pass and its own @1000px
    block (which also matches everything ≤680px) — so only ONE
    responsive transition (at 1000px) is real for those two selectors,
    confirmed identical at both 900px and 390px. Deliberately NOT
    mirrored for that reason; see the CSS file's own comment."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Category

        self.cat_a = Category.objects.create(
            store=self.store, name="دسته الف", slug="task5-c2-cat-a", is_active=True,
        )
        self.cat_b = Category.objects.create(
            store=self.store, name="دسته ب", slug="task5-c2-cat-b", is_active=True,
        )

    def _place_and_publish(self, page_type: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="category_grid", page_type=page_type,
        )
        section.settings = {
            **section.settings,
            "display_mode": "circular",
            "category_ids": [self.cat_a.pk, self.cat_b.pk],
        }
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_circular_mode_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-circle-section"', html)
        self.assertIn('class="tiles-circular"', html)
        self.assertIn('class="tile-circle"', html)
        self.assertIn('class="tile-circle-img"', html)
        self.assertIn('class="tile-circle-label"', html)

    def test_circular_mode_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="tiles-circular"', html)
        self.assertIn('class="tile-circle"', html)

    def test_storefront_builder_css_carries_the_merged_final_circular_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-circle-section{margin:9px 0 7px}", css)
        self.assertIn(
            ".tiles-circular{display:flex;flex-wrap:nowrap;justify-content:space-around;"
            "gap:28px;overflow:visible;padding:2px 12px 5px}",
            css,
        )
        self.assertIn(
            ".tile-circle{display:flex;flex-direction:column;align-items:center;"
            "text-align:center;color:var(--ink);gap:5px;width:auto;min-width:0;"
            "flex:0 1 145px}",
            css,
        )
        self.assertIn(
            ".tile-circle:hover .tile-circle-img{transform:none;"
            "box-shadow:0 2px 8px rgba(15,23,42,.08)}",
            css,
        )
        self.assertIn(
            ".tile-circle-img{width:112px;height:112px;border-radius:50%;overflow:hidden;"
            "background:transparent;border:0;box-shadow:none;display:grid;"
            "place-items:center;transition:.2s}",
            css,
        )
        self.assertIn(
            ".tile-circle-img img{width:100%;height:100%;object-fit:contain;background:#fff;"
            "border-radius:50%;border:1px solid #e3e5e8;padding:4px}",
            css,
        )
        self.assertIn(".tile-circle-wm{font-size:38px}", css)
        self.assertIn(".tile-circle-label{font-size:11.8px;font-weight:600;color:#333}", css)
        self.assertIn(
            "@media(max-width:1000px){\n"
            "  .tiles-circular{overflow-x:auto;justify-content:flex-start;gap:14px}\n"
            "  .tile-circle{flex:0 0 110px}\n"
            "  .tile-circle-img{width:92px;height:92px}\n"
            "}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n  .tile-circle-label{font-size:11.5px}\n}",
            css,
        )
        # The base pass's and the "Universal dense storefront modules" pass's
        # own @680px `.tile-circle`/`.tile-circle-img` width/flex-basis
        # overrides are dead code on Home (proven via real-browser
        # ground-truth verification — see the CSS comment) and must never
        # be mirrored here, since doing so would NOT match Home's actual
        # rendering at any viewport.
        self.assertNotIn(".tile-circle{width:84px}", css)
        self.assertNotIn(".tile-circle{flex-basis:88px;width:88px}", css)
        self.assertNotIn(".tile-circle-img{width:76px;height:76px}", css)
        self.assertNotIn(".tile-circle-img{width:78px;height:78px}", css)

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        self.assertNotIn("tiles-circular", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SecHeadSharedBaselineNonHomeCssTests(TestCase):
    """Group C2.5 — cross-cutting `.sec-head` reconciliation, raised by
    Group C2's independent review (a false claim that `.sec-head` has no
    base CSS outside home.css at all masked a real divergence). Root
    cause: `apps/catalog/static/css/product_card.css`'s own `.sec-head`
    rule was a byte-for-byte copy of home.css's ORIGINAL, pre-refinement
    base pass (its own file header literally says "کپی دقیق از
    docs/spec/shop-frontend.html" — exact copy) — frozen at that point,
    never updated as home.css's own later refinement passes changed
    these values, and never given `.sec-head .more`/`.sec-head .more
    svg`/`.sec-head .btn` at all (not stale — entirely absent). `.sec-
    head` is the title-heading wrapper for the vast majority of section
    templates in the whole registry (16 of 43 files under
    storefront_builder/templates/.../sections use it), not any one
    family — so this is a shared base-contract fix in `product_card.css`
    itself (the file every page, Home included, actually loads it from),
    not a per-family shadow override in storefront_builder.css (which
    would create a second, competing definition).

    Home's rendering is provably unaffected: home.css's own later,
    equal-specificity rules already override every property this fix
    changes — verified via a real-browser harness using Home's actual
    `product_card.css`-then-`home.css` load order, confirming
    byte-identical computed styles before and after this fix.

    `.category-circle-section .sec-head{margin-bottom:6px}` (home.css:
    535) is mirrored separately, in storefront_builder.css's own Group
    C2 block — a genuinely family-specific override on top of this
    shared baseline, not folded in here."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Product, Vendor

        vendor = Vendor.objects.create(store=self.store, slug="task5-c25-vendor", name="فروشنده تست")
        Product.objects.create(
            store=self.store, vendor=vendor, name="کالای تست", slug="task5-c25-product",
            sku="T5C25-P", price="100000", status="active",
        )

    def test_newest_products_sec_head_renders_on_cart(self):
        # newest_products is representative family #1 (distinct from
        # circular/category_grid) — a title-only .sec-head with no
        # `.more`/`.btn`, always rendered (no {% if title %} gate).
        # Unlike best_sellers (which needs real OrderItem history via
        # best_seller_service and would resolve empty here),
        # newest_products only orders by -created_at, so 1 active
        # product is sufficient to keep it visible on Public (it is
        # also in OPTIONAL_PRODUCT_DATA_SECTION_KEYS).
        section_structure_service.add_section(
            draft=self.draft, section_key="newest_products", page_type=StorefrontPage.PageType.CART,
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="sec-head"', html)

    def test_product_card_css_carries_the_merged_final_sec_head_baseline(self):
        css = _PRODUCT_CARD_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".sec-head{display:flex;align-items:center;justify-content:space-between;"
            "gap:12px;margin-bottom:9px;flex-wrap:wrap}",
            css,
        )
        # `font-size` deliberately KEEPS its original fallback — see the
        # CSS file's own comment: `--sfb-heading-size` is a real,
        # already merchant-configurable, already-tested (test_appearance.
        # py) per-store heading-size token, the ONLY CSS consumer of
        # that variable anywhere, and NOT a stale copy like the other
        # properties on this same rule — home.css itself never uses
        # this variable at all for `.sec-head h2`. Only `font-weight`
        # and `gap` (plain hardcoded values on both sides, no
        # variable, no test coverage suggesting intentional divergence)
        # are corrected to home.css's current merged value.
        self.assertIn(
            ".sec-head h2{font-size:var(--sfb-heading-size, 19px);font-weight:800;"
            "display:flex;align-items:center;gap:6px}",
            css,
        )
        # `.bar`'s violet-gradient WAS itself once real per-store brand
        # theming (`--violet` resolves to `var(--brand-primary, ...)`
        # per apps/core/static/css/tokens.css) — but home.css's OWN
        # 3-pass history shows Home itself abandoned that gradient for
        # a fixed neutral color, so mirroring the CURRENT #111 value is
        # catching non-Home up to a decision Home already made, not
        # removing a still-live feature (unlike font-size above).
        self.assertIn(
            ".sec-head h2 .bar{width:3px;height:17px;border-radius:1px;background:#111}",
            css,
        )
        self.assertIn(
            ".sec-head .more{color:#333;font-weight:700;font-size:10.5px;"
            "display:flex;align-items:center;gap:5px}",
            css,
        )
        self.assertIn(".sec-head .more svg{width:16px;height:16px}", css)
        self.assertIn(
            ".sec-head .btn,.product-section .sec-head .btn{height:23px;min-height:23px;"
            "padding:0 9px;border-radius:999px;background:#fff;border:1px solid #e3e5e9;"
            "color:#ef4760;font-weight:700;box-shadow:none;font-size:10px}",
            css,
        )
        # No @680px override for `.sec-head h2` font-size: that would
        # only exist to force the same, explicitly out-of-scope
        # property back to a fixed value at small viewports.
        self.assertNotIn("@media(max-width:680px){\n  .sec-head h2{font-size:15px}\n}", css)
        # The stale, pre-fix values (a byte-for-byte copy of home.css's
        # ORIGINAL pre-refinement base pass) must never reappear.
        self.assertNotIn("margin-bottom:18px;flex-wrap:wrap}", css)
        self.assertNotIn(".sec-head h2{font-size:var(--sfb-heading-size, 19px);font-weight:900", css)
        self.assertNotIn(
            "width:5px;height:22px;border-radius:4px;"
            "background:linear-gradient(var(--violet),var(--violet-3))",
            css,
        )

    def test_storefront_builder_css_carries_the_circular_sec_head_override(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-circle-section .sec-head{margin-bottom:6px}", css)

    def test_home_page_is_unaffected_since_home_css_already_overrides_every_changed_property(self):
        home_css = Path(settings.BASE_DIR, "apps", "catalog", "static", "css", "home.css").read_text(
            encoding="utf-8",
        )
        # Home's OWN later cascade passes (not this fix) are what actually
        # govern its rendering — confirm they still exist untouched.
        self.assertIn(".sec-head{margin-bottom:9px}", home_css)
        self.assertIn(".sec-head h2{font-size:16px}", home_css)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
