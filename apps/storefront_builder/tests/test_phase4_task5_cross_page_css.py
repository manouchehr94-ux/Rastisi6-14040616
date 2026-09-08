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
        css = _STOREFRONT_BUILDER_CSS.read_text(encoding="utf-8")
        self.assertIn(".amazing-offers-section{margin:7px 0}", css)
        self.assertIn(
            ".special-wrap{display:grid;grid-template-columns:290px minmax(0,1fr);"
            "gap:0;background:#fff;border:1px solid #e0e3e8;border-radius:5px;"
            "overflow:hidden;box-shadow:0 1px 6px rgba(15,23,42,.05);min-height:250px}",
            css,
        )
        self.assertIn(
            ".amazing-offers-section .special-wrap{direction:ltr;"
            "grid-template-columns:270px minmax(0,1fr)}",
            css,
        )
        self.assertIn(".special-copy h3{font-size:18px;line-height:1.55", css)
        # The two older, unrelated "special offers" widget definitions
        # elsewhere in home.css (`.special-list>a`, no title/kicker/discount/
        # brand classes) must never get pulled in — this mirror is scoped to
        # the ONE widget amazing_offers.html actually emits.
        self.assertNotIn(".special-list>a{", css)
