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
        self.assertIn('.hero-inner[data-text-position="center"] .hero-text{', css)

    def test_home_page_is_unaffected_since_it_never_loads_storefront_builder_css(self):
        home_html = Path(settings.BASE_DIR, "apps", "catalog", "templates", "catalog", "home.html").read_text(
            encoding="utf-8",
        )
        self.assertNotIn("storefront_builder.css", home_html)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
