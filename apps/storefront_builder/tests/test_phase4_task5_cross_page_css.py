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
        # A bare (non-`:has()`/non-`[data-...]`-scoped) `.sec-head h2` rule
        # with a literal numeric `font-size` would mean the deliberately-
        # excluded `--sfb-heading-size` variable got dropped or shadowed;
        # scoped companions (e.g. `:has(.pcard.style-beauty_retail)
        # .sec-head h2{font-size:15px}`) legitimately use literal values
        # and must not trip this guard, hence the line-start anchor.
        self.assertNotRegex(css, r"(?m)^\.sec-head h2\{font-size:\d")
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

    def test_product_card_css_carries_the_compact_density_btn_override(self):
        # Raised by this fix's own independent review: the base `.btn`
        # rule added above only matched home.css's DEFAULT-density
        # merged value — home.css also has a real, higher-specificity
        # `html[data-sfb-density="compact"]` override (home.css:699-700)
        # for this exact selector that was missing here entirely.
        css = _PRODUCT_CARD_CSS.read_text(encoding="utf-8")
        self.assertIn(
            'html[data-sfb-density="compact"] .sec-head .btn,\n'
            'html[data-sfb-density="compact"] .product-section .sec-head .btn'
            "{font-size:9.4px;min-height:24px;height:24px}",
            css,
        )

    def test_product_card_css_carries_the_patterned_rail_sec_head_baseline(self):
        # Raised by this fix's own independent review: `.rsec[data-
        # pattern]>.section>.sec-head*` (the small white-capsule heading
        # on patterned-background rails) had no rule anywhere in this
        # file before, despite `data-pattern` being emitted by the one
        # shared `responsive_section_wrapper.html` on every page type —
        # a real, previously-undiscovered non-Home gap in the exact
        # same `.sec-head` family this fix otherwise reconciles.
        css = _PRODUCT_CARD_CSS.read_text(encoding="utf-8")
        self.assertIn(".rsec[data-pattern]>.section>.sec-head{margin-bottom:7px;align-items:center}", css)
        self.assertIn(
            ".rsec[data-pattern]>.section>.sec-head h2{width:max-content;max-width:75%;"
            "padding:4px 10px;border-radius:999px;background:#fff;color:#ef4760;"
            "font-size:11.4px;line-height:1.4;font-weight:800;"
            "box-shadow:0 1px 3px rgba(0,0,0,.05)}",
            css,
        )
        self.assertIn(".rsec[data-pattern]>.section>.sec-head h2 .bar{display:none;background:#ff5a72}", css)
        self.assertIn(
            ".rsec[data-pattern]>.section>.sec-head .btn{height:21px;min-height:21px;"
            "padding-inline:8px;font-size:9.4px;background:rgba(255,255,255,.96);"
            "color:#ef4760;border-color:#fff}",
            css,
        )
        # The plain @680px override (11px) only wins at default density —
        # home.css's compact-density override (11.4px) is MORE specific
        # and wins regardless of viewport, so it must be its own rule,
        # not folded into the @680px block.
        self.assertIn(".rsec[data-pattern]>.section>.sec-head h2{font-size:11px}", css)
        self.assertIn(
            'html[data-sfb-density="compact"] .rsec[data-pattern]>.section>.sec-head h2{font-size:11.4px}',
            css,
        )

    def test_product_card_css_carries_the_missing_card_style_sec_head_companions(self):
        # Raised by this fix's own independent review: the evidence doc
        # claimed every card-style/pattern `.sec-head` overlay other than
        # fashion_sale/luxury_dark was "already shared" — false for
        # beauty_retail, chocolate_retail, and minimal, whose home.css
        # `.sec-head` companions had never been mirrored here at all.
        css = _PRODUCT_CARD_CSS.read_text(encoding="utf-8")
        self.assertIn(
            '.rsec[data-bg-mode="palette"]:has(.pcard.style-beauty_retail) .sec-head h2{color:#fff}',
            css,
        )
        self.assertIn(
            '.rsec[data-bg-mode="palette"]:has(.pcard.style-beauty_retail) .sec-head .btn'
            "{background:#fff;border-color:#fff;color:var(--violet)}",
            css,
        )
        self.assertIn(".product-section:has(.pcard.style-beauty_retail) .sec-head{margin-bottom:10px}", css)
        self.assertIn(".product-section:has(.pcard.style-beauty_retail) .sec-head h2{font-size:15px}", css)
        self.assertIn(
            ".product-section:has(.pcard.style-beauty_retail) .sec-head h2 .bar"
            "{background:var(--violet);height:17px;width:3px}",
            css,
        )
        self.assertIn(".product-section:has(.pcard.style-chocolate_retail) .sec-head{margin-bottom:14px}", css)
        self.assertIn(
            ".product-section:has(.pcard.style-chocolate_retail) .sec-head h2{font-size:16px;color:#33271d}",
            css,
        )
        self.assertIn(
            ".product-section:has(.pcard.style-chocolate_retail) .sec-head h2 .bar{background:#7B4518}",
            css,
        )
        self.assertIn(
            ".product-section:has(.pcard.style-minimal) .sec-head"
            "{justify-content:center;text-align:center;margin-bottom:18px}",
            css,
        )
        self.assertIn(
            ".product-section:has(.pcard.style-minimal) .sec-head h2{font-size:16px;font-weight:850}",
            css,
        )
        self.assertIn(".product-section:has(.pcard.style-minimal) .sec-head h2 .bar{display:none}", css)

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


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CategoryGridImageStripNonHomeCssTests(TestCase):
    """Group C3 — category_grid's "image_strip" display mode
    (`.category-image-strip-section`/`.category-image-strip`/`.category-
    image-tile`/`.category-image-media`/`.category-image-fallback`/
    `.category-image-label`). home.css layers this family across TWO
    passes: "V4.1 reference polish" (base + its own @1000px/@680px
    blocks) and a later, unlabeled "Phase 3.7" pass (unconditioned +
    its own separate @680px block). Real-browser ground-truth
    verification (a standalone harness loading home.css alone against
    this exact markup) confirmed the V4.1 pass's own @1000px/@680px
    overrides for `.category-image-media`'s `height` and `.category-
    image-label`'s `@680px` `font-size` are dead code — completely
    shadowed at every viewport by the later, unconditioned "Phase 3.7"
    pass — so those responsive transitions never actually occur, while
    `.category-image-tile`'s own `flex-basis` responsive values
    (untouched by "Phase 3.7") remain genuinely live. Deliberately NOT
    mirrored for that reason; see the CSS file's own comment."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Category

        self.cat_a = Category.objects.create(
            store=self.store, name="دسته الف", slug="task5-c3-cat-a", is_active=True,
        )
        self.cat_b = Category.objects.create(
            store=self.store, name="دسته ب", slug="task5-c3-cat-b", is_active=True,
        )

    def _place_and_publish(self, page_type: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="category_grid", page_type=page_type,
        )
        section.settings = {
            **section.settings,
            "display_mode": "image_strip",
            "category_ids": [self.cat_a.pk, self.cat_b.pk],
        }
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_image_strip_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-image-strip-section"', html)
        self.assertIn('class="category-image-strip"', html)
        self.assertIn('class="category-image-tile"', html)
        self.assertIn('class="category-image-media"', html)
        self.assertIn('class="category-image-label"', html)
        # An initial assumption that `.rcontainer` never renders on this
        # public route was wrong (caught by this very test failing) —
        # it genuinely wraps every section here, confirming the
        # `.rcontainer:has(.category-image-strip-section)` mirror below
        # is real and necessary, not inert.
        self.assertIn('class="rcontainer"', html)

    def test_image_strip_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="category-image-strip"', html)
        self.assertIn('class="category-image-tile"', html)

    def test_storefront_builder_css_carries_the_merged_final_image_strip_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-image-strip-section{margin:8px 0 7px}", css)
        self.assertIn(".category-image-strip-section .sec-head{margin-bottom:4px}", css)
        self.assertIn(
            ".category-image-strip{display:grid;"
            "grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:14px;"
            "align-items:start;padding:2px 6px 4px}",
            css,
        )
        self.assertIn(
            ".category-image-tile{min-width:0;display:flex;flex-direction:column;"
            "align-items:center;gap:4px;color:#25282d;text-align:center}",
            css,
        )
        self.assertIn(
            ".category-image-media{width:100%;height:106px;display:grid;"
            "place-items:center;overflow:hidden;background:transparent}",
            css,
        )
        self.assertIn(
            ".category-image-media img{display:block;width:100%;height:100%;"
            "object-fit:contain;border:0;border-radius:0;padding:0;box-shadow:none}",
            css,
        )
        self.assertIn(".category-image-fallback{font-size:42px;line-height:1}", css)
        self.assertIn(
            ".category-image-label{font-size:10.5px;font-weight:700;line-height:1.45;"
            "white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}",
            css,
        )
        self.assertIn(
            ".category-image-tile:hover .category-image-media{transform:translateY(-1px)}",
            css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n"
            "  .category-image-strip{display:flex;overflow-x:auto;"
            "scroll-snap-type:x proximity}\n"
            "  .category-image-tile{flex:0 0 126px;scroll-snap-align:start}\n"
            "}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .category-image-tile{flex-basis:96px}\n"
            "  .category-image-strip{gap:12px}\n"
            "}",
            css,
        )
        # The V4.1 pass's own @1000px/@680px `.category-image-media`
        # height overrides, @680px `.category-image-label` font-size
        # override, and @1000px `.category-image-strip` padding-inline
        # override are all dead code on Home (proven via real-browser
        # ground-truth verification — padding stays `2px 6px 4px` at
        # every viewport) and must never be mirrored, since doing so
        # would NOT match Home's actual rendering at any viewport.
        self.assertNotIn(".category-image-media{height:98px}", css)
        self.assertNotIn(".category-image-media{height:78px}", css)
        self.assertNotIn(".category-image-label{font-size:8.5px}", css)
        self.assertNotIn("padding-inline:3px", css)
        # `.rcontainer` genuinely renders on every public non-Home page
        # (confirmed by the markup test above — an initial assumption
        # that it didn't was wrong) — its own base rule (`margin:0`)
        # already exists elsewhere in this file; this narrow `:has()`
        # exception is the one genuinely family-specific piece that
        # needed adding, matching home.css's own real rendering.
        self.assertIn(".rcontainer:has(.category-image-strip-section){margin-bottom:5px}", css)

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        self.assertNotIn("category-image-strip", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CategoryGridRemainingModesNonHomeCssTests(TestCase):
    """Task 5, remaining Group C — the last 6 of `category_grid`'s 11
    `display_mode`s (`fashion_flat`, `fashion_mosaic`, `beauty_icons`,
    `chocolate_story`, `chocolate_badges`, `atelier_mosaic`) were
    Home-only. Exhaustive whole-file grep of home.css for every one of
    these selector families confirmed each is a single, unscattered
    generation (unlike `circular`'s 4-pass cascade or `image_strip`'s
    2-pass one) — no cascade merge needed, values mirrored verbatim.
    `.beauty-section-title` (beauty_icons) is the SAME shared heading
    already mirrored from Group A2 (`product_section` campaign_band);
    `.chocolate-section-title` (chocolate_story/chocolate_badges) is
    shared by those two modes and written once. Ground-truth verified
    via a standalone real-browser harness (home.css alone vs
    storefront_builder.css alone, byte-identical at 1440/900/390 for
    every explicitly-set property)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)
        from apps.catalog.models import Category

        self.cat_a = Category.objects.create(
            store=self.store, name="دسته الف", slug="task5-cgrem-cat-a", is_active=True,
        )
        self.cat_b = Category.objects.create(
            store=self.store, name="دسته ب", slug="task5-cgrem-cat-b", is_active=True,
        )

    def _place_and_publish(self, page_type: str, display_mode: str):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="category_grid", page_type=page_type,
        )
        section.settings = {
            **section.settings,
            "display_mode": display_mode,
            "category_ids": [self.cat_a.pk, self.cat_b.pk],
            # An explicit title is required: `beauty_section_title`/
            # `chocolate-section-title`/`atelier-section-title` (like
            # `.sec-head` itself, per Group C2.5's finding) only render
            # inside `{% if category_grid_settings.title %}` — the
            # default empty title would silently skip that markup.
            "title": "دسته‌بندی",
        }
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        return section

    def test_fashion_flat_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART, "fashion_flat")
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-fashion-rail-section"', html)
        self.assertIn('class="sec-head"', html)
        self.assertIn('class="category-fashion-rail"', html)
        self.assertIn('class="category-fashion-tile"', html)
        self.assertIn('class="category-fashion-media"', html)
        self.assertIn('class="category-fashion-label"', html)

    def test_fashion_mosaic_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING, "fashion_mosaic")
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-fashion-mosaic-section"', html)
        self.assertIn('class="sec-head"', html)
        self.assertIn('class="category-fashion-mosaic"', html)
        self.assertIn('class="category-mosaic-tile"', html)
        self.assertIn('class="category-mosaic-heading"', html)
        self.assertIn('class="category-mosaic-media"', html)

    def test_beauty_icons_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART, "beauty_icons")
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-beauty-strip-section"', html)
        self.assertIn('class="beauty-section-title"', html)
        self.assertIn('class="category-beauty-strip"', html)
        self.assertIn('class="category-beauty-tile"', html)
        self.assertIn('class="category-beauty-media"', html)
        self.assertIn('class="category-beauty-label"', html)

    def test_chocolate_story_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING, "chocolate_story")
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-chocolate-story-section"', html)
        self.assertIn('class="chocolate-section-title"', html)
        self.assertIn('class="category-chocolate-story-rail"', html)
        self.assertIn('class="category-chocolate-story-item"', html)
        self.assertIn('class="category-chocolate-story-media"', html)
        self.assertIn('class="category-chocolate-story-label"', html)

    def test_chocolate_badges_renders_on_cart(self):
        self._place_and_publish(StorefrontPage.PageType.CART, "chocolate_badges")
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-chocolate-section"', html)
        self.assertIn('class="chocolate-section-title"', html)
        self.assertIn('class="category-chocolate-grid"', html)
        self.assertIn('class="category-chocolate-tile"', html)
        self.assertIn('class="category-chocolate-media"', html)
        self.assertIn('class="category-chocolate-label"', html)

    def test_atelier_mosaic_renders_on_listing(self):
        self._place_and_publish(StorefrontPage.PageType.LISTING, "atelier_mosaic")
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section category-atelier-section"', html)
        self.assertIn('class="atelier-section-title"', html)
        self.assertIn('class="category-atelier-mosaic"', html)
        self.assertIn('class="category-atelier-tile"', html)
        self.assertIn('class="category-atelier-media"', html)
        self.assertIn('class="category-atelier-shade"', html)
        self.assertIn('class="category-atelier-label"', html)

    def test_storefront_builder_css_carries_fashion_flat_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-fashion-rail-section{margin:2px 0}", css)
        self.assertIn(
            ".category-fashion-rail{display:flex;overflow-x:auto;gap:18px;"
            "padding-inline:2px 2px;scroll-snap-type:x proximity;scrollbar-width:none}",
            css,
        )
        self.assertIn(
            ".category-fashion-tile{display:flex;flex-direction:column;align-items:center;"
            "gap:6px;color:#25282d;text-align:center;flex:0 0 64px;scroll-snap-align:start}",
            css,
        )
        self.assertIn(
            ".category-fashion-media{width:60px;height:60px;aspect-ratio:1/1;"
            "border-radius:50%;overflow:hidden;background:#f4f2f5;display:grid;"
            "place-items:center;border:none}",
            css,
        )
        self.assertIn(
            ".category-fashion-label{font-size:10.5px;font-weight:700;line-height:1.35;"
            "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:72px}",
            css,
        )
        self.assertIn(
            "@media(max-width:860px){\n"
            "  .category-fashion-tile{flex-basis:56px}\n"
            "  .category-fashion-media{width:52px;height:52px}\n"
            "}",
            css,
        )

    def test_storefront_builder_css_carries_fashion_mosaic_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-fashion-mosaic-section{margin:10px 0}", css)
        self.assertIn(
            ".category-fashion-mosaic{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}",
            css,
        )
        self.assertIn(
            ".category-mosaic-tile{display:flex;flex-direction:column;gap:8px;"
            "color:#25282d;background:#fff;border-radius:10px;overflow:hidden}",
            css,
        )
        self.assertIn(
            ".category-mosaic-heading{display:flex;align-items:center;gap:4px;"
            "font-size:12.5px;font-weight:800;padding-inline:2px}",
            css,
        )
        self.assertIn(
            ".category-mosaic-media{aspect-ratio:1/1;border-radius:8px;overflow:hidden;"
            "background:#f6f4f5}",
            css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n"
            "  .category-fashion-mosaic{grid-template-columns:repeat(3,1fr)}\n"
            "}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .category-fashion-mosaic{grid-template-columns:repeat(2,1fr);gap:10px}\n"
            "  .category-mosaic-heading{font-size:12.5px}\n"
            "}",
            css,
        )

    def test_storefront_builder_css_carries_beauty_icons_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-beauty-strip-section{margin:24px 0 30px}", css)
        self.assertIn(
            ".category-beauty-strip{display:grid;grid-template-columns:"
            "repeat(6,minmax(0,1fr));gap:28px;align-items:start}",
            css,
        )
        self.assertIn(
            ".category-beauty-tile{display:flex;flex-direction:column;align-items:center;"
            "gap:7px;text-align:center;color:var(--ink);min-width:0}",
            css,
        )
        self.assertIn(
            ".category-beauty-media{width:96px;height:96px;border-radius:14px;padding:7px;"
            "overflow:hidden;display:grid;place-items:center;background:linear-gradient"
            "(145deg,var(--violet),color-mix(in srgb,var(--violet) 70%,#ef41ba));"
            "box-shadow:0 4px 10px color-mix(in srgb,var(--violet) 18%,transparent)}",
            css,
        )
        self.assertIn(
            ".category-beauty-label{font-size:12px;font-weight:750;line-height:1.45;"
            "max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
            css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n"
            "  .category-beauty-strip{grid-template-columns:repeat(6,94px);"
            "overflow-x:auto;scrollbar-width:none;justify-content:flex-start;gap:16px;"
            "padding-bottom:4px}\n"
            "  .category-beauty-strip::-webkit-scrollbar{display:none}\n"
            "  .category-beauty-media{width:80px;height:80px}\n"
            "}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .category-beauty-strip-section{margin:16px 0 20px}\n"
            "  .category-beauty-strip{grid-template-columns:repeat(6,78px);gap:12px}\n"
            "  .category-beauty-media{width:66px;height:66px;border-radius:11px;padding:5px}\n"
            "  .category-beauty-media img{padding:8px}\n"
            "  .category-beauty-label{font-size:10px}\n"
            "}",
            css,
        )

    def test_storefront_builder_css_carries_chocolate_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-chocolate-story-section{margin:12px 0 10px}", css)
        self.assertIn(
            ".category-chocolate-story-rail{display:flex;align-items:flex-start;"
            "justify-content:center;gap:14px;overflow-x:auto;padding:2px 6px 8px;"
            "scrollbar-width:none}",
            css,
        )
        self.assertIn(
            ".category-chocolate-story-media{width:82px;height:82px;border-radius:50%;"
            "padding:3px;background:#fff;border:2px solid #C85C72;box-shadow:0 3px 10px "
            "rgba(74,48,25,.08);display:grid;place-items:center;overflow:hidden}",
            css,
        )
        self.assertIn(".category-chocolate-section{margin:16px 0 24px}", css)
        self.assertIn(".chocolate-section-title{text-align:center;margin-bottom:14px}", css)
        self.assertIn(
            ".chocolate-section-title h2{font-size:15px;font-weight:800;color:#3c2b1d;margin:0}",
            css,
        )
        self.assertIn(
            ".category-chocolate-grid{display:grid;grid-template-columns:"
            "repeat(6,minmax(0,1fr));gap:18px 16px}",
            css,
        )
        self.assertIn(
            ".category-chocolate-media{width:124px;height:98px;display:grid;"
            "place-items:center;position:relative;border-radius:48% 52% 45% 55%/58% 45% "
            "55% 42%;background:#E7D1B7;overflow:hidden;box-shadow:0 3px 10px rgba(93,54,22,.07)}",
            css,
        )
        self.assertIn(
            ".category-chocolate-label{min-width:98px;max-width:100%;padding:5px 13px;"
            "border-radius:999px;background:#7B4518;color:#fff;font-size:10.5px;"
            "font-weight:700;line-height:1.25;white-space:nowrap;overflow:hidden;"
            "text-overflow:ellipsis}",
            css,
        )
        self.assertIn(
            "@media(max-width:900px){\n"
            "  .category-chocolate-grid{grid-template-columns:repeat(4,minmax(0,1fr))}\n"
            "  .category-chocolate-media{width:104px;height:82px}\n"
            "}",
            css,
        )
        self.assertIn(".category-chocolate-story-item{flex-basis:78px}", css)
        self.assertIn(".category-chocolate-media{width:82px;height:68px}", css)

    def test_storefront_builder_css_carries_atelier_mosaic_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".category-atelier-section{margin:16px 0 24px}", css)
        self.assertIn(".atelier-section-title{text-align:center;margin:0 0 15px}", css)
        self.assertIn(
            ".atelier-section-title h2{margin:0;font-size:18px;font-weight:900;color:var(--ink)}",
            css,
        )
        self.assertIn(
            ".category-atelier-mosaic{display:grid;grid-template-columns:"
            "repeat(4,minmax(0,1fr));gap:16px}",
            css,
        )
        self.assertIn(
            ".category-atelier-tile{position:relative;display:block;min-width:0;"
            "aspect-ratio:.83/1;overflow:hidden;background:var(--palette-tone-4,#EEE4D6);"
            "color:#fff;text-decoration:none}",
            css,
        )
        self.assertIn(
            ".category-atelier-shade{position:absolute;inset:0;background:linear-gradient"
            "(180deg,rgba(20,16,12,.02) 45%,rgba(20,16,12,.64) 100%);pointer-events:none}",
            css,
        )
        self.assertIn(
            ".category-atelier-label{position:absolute;z-index:2;inset-inline:16px;"
            "bottom:15px;color:#fff;font-size:clamp(16px,1.8vw,27px);line-height:1.25;"
            "font-weight:950;text-shadow:0 1px 8px rgba(0,0,0,.22)}",
            css,
        )
        self.assertIn(
            "@media(max-width:900px){\n"
            "  .category-atelier-mosaic{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}\n"
            "}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .category-atelier-mosaic{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}\n"
            "  .category-atelier-label{inset-inline:10px;bottom:10px;font-size:16px}\n"
            "}",
            css,
        )

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        for marker in (
            "category-fashion", "category-mosaic", "category-beauty",
            "category-chocolate", "category-atelier",
        ):
            self.assertNotIn(marker, home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class GroupDNonHomeCssTests(TestCase):
    """Task 5, Group D — `promo_cards` + `image_text` + `blog_posts` were
    Home-only. `promo_cards` needs no new CSS at all: its markup
    (`.tiles`/`.tile`/`.wm`/`h4`/`.btn`) is byte-identical to
    `category_grid`'s `grid`/`carousel` modes, already mirrored from
    Group C1 — confirmed by direct template comparison, not assumed.
    `image_text` (`.cream`) is a single, unscattered home.css
    generation. `blog_posts` (`.blog-grid`/`.blog-card`) has two
    unconditioned passes; merged-final values independently
    re-derived via a real-browser ground-truth harness (byte-identical
    to a direct read of both passes in file order)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def test_promo_cards_renders_on_cart_reusing_group_c1_tiles_css(self):
        from apps.catalog.models import Category

        Category.objects.create(store=self.store, name="دسته الف", slug="task5-d-cat-a", is_active=True)
        section_structure_service.add_section(
            draft=self.draft, section_key="promo_cards", page_type=StorefrontPage.PageType.CART,
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section"><div class="tiles"', html)
        self.assertIn('class="tile t1"', html)
        self.assertIn('class="wm"', html)
        # Guard the "no new CSS needed" claim directly (raised by this
        # batch's own independent review): if the Group C1 `.tiles`
        # block ever regresses, promo_cards would silently lose its
        # layout too, since it reuses that exact selector family.
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}", css)
        self.assertIn(".tile .wm{position:absolute;top:10px;left:14px;font-size:90px;opacity:.22}", css)
        self.assertIn(".tile h4{font-size:16px;font-weight:800;margin-bottom:10px}", css)
        self.assertIn(
            ".tile .btn{width:fit-content;padding:8px 16px;font-size:12px;"
            "background:rgba(255,255,255,.92);color:var(--ink)}",
            css,
        )

    def test_image_text_renders_on_listing(self):
        section = section_structure_service.add_section(
            draft=self.draft, section_key="image_text", page_type=StorefrontPage.PageType.LISTING,
        )
        section.settings = {
            **section.settings,
            "title": "متن نمونه", "body_html": "<p>بدنه</p>", "image_url": "https://example.com/x.png",
        }
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="cream"', html)
        self.assertIn('class="rack"', html)

    def test_blog_posts_renders_on_cart(self):
        from apps.blog.models import BlogPost

        BlogPost.objects.create(
            title="مطلب تست", slug="task5-d-post", body="متن", category_label="اخبار",
            published_at=timezone.now(),
        )
        section_structure_service.add_section(
            draft=self.draft, section_key="blog_posts", page_type=StorefrontPage.PageType.CART,
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="grid blog-grid"', html)
        self.assertIn('class="blog-card"', html)
        self.assertIn('class="th"', html)
        self.assertIn('class="bd"', html)
        self.assertIn('class="meta"', html)
        self.assertIn('class="read"', html)

    def test_storefront_builder_css_carries_image_text_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".cream{position:relative;border-radius:22px;overflow:hidden;background:"
            "linear-gradient(100deg,#f3e9d8,#efe2cb);display:grid;"
            "grid-template-columns:1fr 1fr;align-items:center;padding:36px 40px;gap:20px}",
            css,
        )
        self.assertIn(
            ".cream h3{font-size:22px;font-weight:900;color:#5b4326;margin-bottom:10px}", css,
        )
        self.assertIn(
            ".cream .rack{font-size:74px;letter-spacing:6px;text-align:center;"
            "filter:drop-shadow(0 8px 16px rgba(120,90,40,.2))}",
            css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n"
            "  .cream{grid-template-columns:1fr;text-align:center}\n"
            "  .cream .rack{margin-inline:auto}\n"
            "}",
            css,
        )

    def test_storefront_builder_css_carries_the_merged_final_blog_posts_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".blog-grid{grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}", css)
        self.assertIn(
            ".blog-card{background:#fff;border:1px solid var(--line);border-radius:7px;"
            "overflow:hidden;transition:.2s;box-shadow:0 1px 5px rgba(15,23,42,.04)}",
            css,
        )
        self.assertIn(
            ".blog-card:hover{transform:none;box-shadow:0 3px 10px rgba(15,23,42,.08)}", css,
        )
        self.assertIn(
            ".blog-card .th{height:150px;display:grid;place-items:center;font-size:38px}", css,
        )
        self.assertIn(".blog-card .bd{padding:10px 11px}", css)
        self.assertIn(
            ".blog-card .meta{font-size:8.5px;color:var(--muted);display:flex;gap:10px;"
            "margin-bottom:4px}",
            css,
        )
        self.assertIn(
            ".blog-card h4{font-size:10.5px;font-weight:700;line-height:1.65;margin-bottom:5px}",
            css,
        )
        self.assertIn(
            ".blog-card .read{color:#444;font-size:9px;font-weight:700;display:flex;"
            "align-items:center;gap:4px}",
            css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n  .blog-grid{grid-template-columns:repeat(3,1fr)}\n}", css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .blog-grid{grid-template-columns:repeat(2,1fr);gap:8px}\n"
            "  .blog-card .th{height:105px}\n"
            "}",
            css,
        )
        # Stale base-only values (superseded by the later, unconditioned
        # pass) must never reappear on their own.
        self.assertNotIn("grid-template-columns:repeat(auto-fill,minmax(200px,1fr))", css)
        self.assertNotIn(".blog-card{border-radius:var(--radius)}", css)

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class GroupENonHomeCssTests(TestCase):
    """Task 5, Group E — `faq` + `testimonials` + `trust_features` +
    `video_section` were Home-only. `faq`/`testimonials`/`video_section`
    (home.css's "checkpoint 12" block) are a single, unscattered
    generation. `trust_features` (`.features`/`.feat`) is the most
    cascade-scattered family in this task — 5 unconditioned passes plus
    density scoping, genuinely live on Home's own hardcoded template
    (30 occurrences) — merged-final values independently re-derived via
    a real-browser ground-truth harness, which confirmed the same
    "later unconditioned rule shadows an earlier breakpoint override"
    pattern as Group C2/C3, PLUS a genuine (non-coincidental)
    compact-density divergence for `.features` itself, mirrored per
    the Group C2.5 precedent."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def _place(self, section_key: str, page_type: str, settings_patch: dict):
        section = section_structure_service.add_section(
            draft=self.draft, section_key=section_key, page_type=page_type,
        )
        section.settings = {**section.settings, **settings_patch}
        section.save(update_fields=["settings"])
        return section

    def test_faq_renders_on_cart(self):
        self._place(
            "faq", StorefrontPage.PageType.CART,
            {"title": "سوالات", "items": [{"question": "س", "answer": "ج"}]},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="sec-head"', html)
        self.assertIn('class="faq-list"', html)
        self.assertIn('class="faq-item"', html)

    def test_testimonials_renders_on_listing(self):
        self._place(
            "testimonials", StorefrontPage.PageType.LISTING,
            {"title": "نظرات", "items": [{"quote": "ق", "name": "ن", "role": "ر"}]},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="testimonial-list"', html)
        self.assertIn('class="testimonial-card"', html)
        self.assertIn('class="quote"', html)
        self.assertIn('class="who"', html)

    def test_trust_features_renders_on_cart_with_default_items(self):
        self._place("trust_features", StorefrontPage.PageType.CART, {})
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="features"', html)
        self.assertIn('class="feat"', html)
        self.assertIn('class="ic"', html)

    def test_video_section_renders_on_listing(self):
        self._place(
            "video_section", StorefrontPage.PageType.LISTING,
            {"title": "ویدیو", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="sec-head"', html)
        self.assertIn('class="video-embed-wrap"', html)
        self.assertIn("<iframe", html)

    def test_storefront_builder_css_carries_faq_testimonials_video_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".faq-list{display:flex;flex-direction:column;gap:10px;max-width:760px;margin:0 auto}",
            css,
        )
        self.assertIn(
            ".faq-item{border:1px solid var(--line);border-radius:12px;padding:14px 18px;"
            "background:var(--card)}",
            css,
        )
        self.assertIn(".faq-item summary{cursor:pointer;font-weight:700;font-size:13.5px;list-style:none}", css)
        self.assertIn(".faq-item p{margin-top:10px;color:var(--muted);font-size:13px;line-height:1.9}", css)
        self.assertIn(
            ".testimonial-list{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}", css,
        )
        self.assertIn(
            ".testimonial-card{border:1px solid var(--line);border-radius:14px;padding:20px;"
            "background:var(--card)}",
            css,
        )
        self.assertIn(".testimonial-card .quote{font-size:13.5px;line-height:1.9;margin-bottom:12px}", css)
        self.assertIn(
            "@media(max-width:1000px){.testimonial-list{grid-template-columns:repeat(2,1fr)}}", css,
        )
        self.assertIn("@media(max-width:680px){.testimonial-list{grid-template-columns:1fr}}", css)
        self.assertIn(
            ".video-embed-wrap{position:relative;max-width:860px;margin:0 auto;aspect-ratio:16/9;"
            "border-radius:16px;overflow:hidden;background:#000;display:flex;align-items:center;"
            "justify-content:center}",
            css,
        )
        self.assertIn(".video-embed-wrap iframe{position:absolute;inset:0;width:100%;height:100%;border:0}", css)

    def test_storefront_builder_css_carries_the_merged_final_trust_features_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".features{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:9px;"
            "margin:7px 0 8px}",
            css,
        )
        self.assertIn(
            ".feat{background:#fff;border:1px solid var(--line);border-radius:5px;padding:6px 9px;"
            "display:flex;align-items:center;gap:8px;min-height:54px;"
            "box-shadow:0 1px 5px rgba(15,23,42,.04)}",
            css,
        )
        self.assertIn(
            ".feat .ic{width:31px;height:31px;border-radius:4px;background:#fff;color:#f43f5e;"
            "border:0;display:grid;place-items:center;flex-shrink:0;font-size:15px}",
            css,
        )
        self.assertIn(".feat .ic svg{width:21px;height:21px}", css)
        self.assertIn(".feat b{font-size:11px;font-weight:600;line-height:1.45;display:block}", css)
        self.assertIn(".feat small{color:var(--muted);font-size:9.5px;line-height:1.5}", css)
        self.assertIn(
            'html[data-sfb-density="compact"] .features{gap:10px;margin:18px 0}', css,
        )
        self.assertIn(
            'html[data-sfb-density="relaxed"] .features{gap:22px;margin:54px 0}', css,
        )
        self.assertIn(
            "@media(max-width:1000px){\n  .features{grid-template-columns:repeat(3,1fr)}\n}", css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .features{display:flex;overflow-x:auto}\n"
            "  .feat{flex:0 0 180px}\n"
            "  .feat b{font-size:10.8px}\n"
            "  .feat small{font-size:9.4px}\n"
            "}",
            css,
        )
        self.assertIn('html[data-sfb-density="compact"] .feat b{font-size:11px}', css)
        self.assertIn('html[data-sfb-density="compact"] .feat small{font-size:9.5px}', css)
        # The dead pass-1 breakpoint overrides (shadowed by later
        # unconditioned rules — the element is display:flex at ≤680px,
        # not grid, so its own @1000px/@680px grid-template-columns
        # never actually apply, and a still-later pass's min-height
        # always wins over the @680px block's 56px) must never reappear.
        self.assertNotIn(".features{grid-template-columns:repeat(2,1fr)}", css)
        self.assertNotIn(".features{grid-template-columns:1fr}", css)
        self.assertNotIn(".feat{flex:0 0 180px;min-height:56px}", css)
        # Round-2 correction (raised by this batch's own independent
        # review): the @680px block's own `.features` `gap:8px` is ALSO
        # dead code — shadowed by the same later, unconditioned V3 pass
        # that gives the base rule its `gap:9px` (which wins at every
        # viewport, ≤680px included) — must never reappear.
        self.assertNotIn(".features{display:flex;overflow-x:auto;gap:8px}", css)

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css_group_e(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class BrandCarouselBeautyTabsNonHomeCssTests(TestCase):
    """Task 5, plus: `brand_carousel`'s `beauty_tabs` display mode
    cosmetic gap (the Task-0 plan's disposition table, row 12). Base
    `brand_carousel` CSS is already Phase-3 CERTIFY-ONLY/mirrored;
    `beauty_tabs`'s own `.brand-beauty-tabs`/`.brand-beauty-tabs
    .brand-beauty-tab`/`.brand-beauty-tabs .brand-tile-name` were never
    mirrored — a single, unscattered home.css generation.

    Round-2 correction (raised by this batch's own independent review):
    `.brand-section--beauty-tabs{margin:...}` and `.beauty-brand-
    title{margin-bottom:16px}` are dead code on Home — a per-selector
    grep cannot see that the title div carries a SECOND class,
    `beauty-section-title` (already mirrored, Group A2), whose
    textually-later home.css rule wins, and that the section itself
    also carries the generic `.section` class, whose own textually-
    later home.css rule (`margin:14px 0`, a pre-existing, cross-cutting
    gap affecting every mirrored section in this task, not just this
    one) wins over `.brand-section--beauty-tabs`'s own margin. Both
    dead rules were removed rather than mirrored."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def test_beauty_tabs_renders_on_cart(self):
        from apps.catalog.models import Brand

        Brand.objects.create(store=self.store, name="برند تست", slug="task5-beautytabs-brand", is_active=True)
        section = section_structure_service.add_section(
            draft=self.draft, section_key="brand_carousel", page_type=StorefrontPage.PageType.CART,
        )
        section.settings = {**section.settings, "display_mode": "beauty_tabs"}
        section.save(update_fields=["settings"])
        svc.publish(self.store)
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('class="section brand-section--beauty-tabs"', html)
        self.assertIn('class="beauty-section-title beauty-brand-title"', html)
        self.assertIn('class="brand-beauty-tabs"', html)
        self.assertIn('class="brand-tile brand-beauty-tab"', html)

    def test_storefront_builder_css_carries_the_beauty_tabs_rules(self):
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        # `.brand-section--beauty-tabs`/`.beauty-brand-title` margins are
        # dead code on Home (shadowed by the generic `.section` rule and
        # by the already-mirrored `.beauty-section-title`, respectively)
        # and must never be mirrored — doing so would give this element
        # an active margin Home never actually renders.
        self.assertNotIn(".brand-section--beauty-tabs{margin", css)
        self.assertNotIn(".beauty-brand-title{margin-bottom:16px}", css)
        self.assertIn(
            ".brand-beauty-tabs{display:flex;overflow-x:auto;scroll-snap-type:x proximity;"
            "scrollbar-width:none;border:1px solid var(--line);border-radius:9px;"
            "background:#fff;padding:0}",
            css,
        )
        self.assertIn(
            ".brand-beauty-tabs .brand-beauty-tab{flex:1 0 150px;min-width:150px;min-height:64px;"
            "border:0;border-inline-end:1px solid var(--line);border-radius:0;background:#fff;"
            "padding:9px 13px;box-shadow:none;scroll-snap-align:start}",
            css,
        )
        self.assertIn(".brand-beauty-tabs .brand-beauty-tab:last-child{border-inline-end:0}", css)
        self.assertIn(
            ".brand-beauty-tabs .brand-beauty-tab:hover{background:#fff9fc;color:var(--violet)}", css,
        )
        self.assertIn(
            ".brand-beauty-tabs .brand-tile-name{color:var(--violet);font-size:10.5px;"
            "font-weight:700;text-align:center}",
            css,
        )
        self.assertIn(
            "@media(max-width:680px){\n"
            "  .brand-beauty-tabs .brand-beauty-tab{flex-basis:128px;min-width:128px;"
            "min-height:56px}\n"
            "}",
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
