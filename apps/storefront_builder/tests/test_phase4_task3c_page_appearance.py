"""Phase 4, Task 3C — the Page Appearance tier.

Precedence: Template DNA -> Store Global -> Page -> Section/Component.
Before this task, no page-scoped appearance override existed at all — only
Store-global (``StorefrontLayoutVersion.appearance_config``) and
Section/Component-local overrides. This is a bounded, typed, sparse
override (exactly the 5 pre-existing "structural, non-identity" fields:
content_width/grid_density/card_shadow/card_hover/hero_style — see
``layout_service.PAGE_APPEARANCE_KEYS``), backed by a minimal forward
migration on ``StorefrontPage`` (no existing canonical JSON surface could
hold a per-page override cleanly), reusing the exact same rendering path
(``apps.core.context_processors._versioned_appearance`` ->
``templates/base.html``'s ``SHOP_CONTENT_WIDTH``/etc CSS custom properties)
both Preview and Public already share.

Core-identity tokens (colors/font/button_style/motion/type_scale/
palette_slug/template_slug) are deliberately NEVER part of this tier — see
``apps.core.context_processors._global_identity_version``'s own explicit
architecture decision that a customer must see the same brand identity on
every page.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder.models import StorefrontLayoutVersion, StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.appearance_authority_service import (
    PageAppearanceNotDraftError,
    apply_page_appearance_patch,
    effective_page_appearance_config,
)
from apps.stores.models import Store, StoreDomain

from .test_views import StorefrontBuilderViewsTestCase

HOST = "sfb-task3c.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


class ValidatePageAppearanceOverridesTests(TestCase):
    def test_only_the_five_allowed_keys_survive(self):
        cleaned = svc.validate_page_appearance_overrides({
            "content_width": 1100,
            "grid_density": 4,
            "card_shadow": "soft",
            "card_hover": "lift",
            "hero_style": "wide",
            "palette_slug": "theme-forest-cream",  # not allowed here — dropped
            "template_slug": "modern",  # not allowed here — dropped
        })
        self.assertEqual(
            cleaned,
            {
                "content_width": 1100, "grid_density": 4,
                "card_shadow": "soft", "card_hover": "lift", "hero_style": "wide",
            },
        )

    def test_empty_input_is_a_true_sparse_empty_dict(self):
        self.assertEqual(svc.validate_page_appearance_overrides({}), {})

    def test_absent_key_is_not_fabricated(self):
        cleaned = svc.validate_page_appearance_overrides({"content_width": 1100})
        self.assertEqual(cleaned, {"content_width": 1100})
        self.assertNotIn("grid_density", cleaned)
        self.assertNotIn("hero_style", cleaned)

    def test_invalid_choice_is_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_page_appearance_overrides({"hero_style": "not_a_real_style"})

    def test_invalid_content_width_type_is_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_page_appearance_overrides({"content_width": "not_a_number"})

    def test_non_dict_input_is_rejected(self):
        with self.assertRaises(svc.AppearanceConfigValidationError):
            svc.validate_page_appearance_overrides("not a dict")


class EffectivePageAppearanceConfigTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.CART)

    def test_no_override_falls_through_to_store_global(self):
        store_config = {"content_width": 1200, "hero_style": "wide"}
        resolved = effective_page_appearance_config(store_appearance_config=store_config, page=self.page)
        self.assertEqual(resolved, store_config)

    def test_page_override_wins_over_store_global(self):
        self.page.page_appearance_overrides = {"content_width": 1100}
        self.page.save(update_fields=["page_appearance_overrides"])
        store_config = {"content_width": 1200, "hero_style": "wide"}
        resolved = effective_page_appearance_config(store_appearance_config=store_config, page=self.page)
        self.assertEqual(resolved["content_width"], 1100)
        # Unrelated Store-global keys survive untouched.
        self.assertEqual(resolved["hero_style"], "wide")


class ApplyPageAppearancePatchTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page(StorefrontPage.PageType.CART)

    def test_patch_persists_validated_sparse_override(self):
        apply_page_appearance_patch(page=self.page, patch={"content_width": 1100})
        self.page.refresh_from_db()
        self.assertEqual(self.page.page_appearance_overrides, {"content_width": 1100})

    def test_patch_merges_sparsely_preserving_other_keys(self):
        apply_page_appearance_patch(page=self.page, patch={"content_width": 1100})
        apply_page_appearance_patch(page=self.page, patch={"hero_style": "tall"})
        self.page.refresh_from_db()
        self.assertEqual(
            self.page.page_appearance_overrides, {"content_width": 1100, "hero_style": "tall"},
        )

    def test_patch_rejects_invalid_value_without_partial_write(self):
        apply_page_appearance_patch(page=self.page, patch={"content_width": 1100})
        with self.assertRaises(svc.AppearanceConfigValidationError):
            apply_page_appearance_patch(page=self.page, patch={"hero_style": "bogus"})
        self.page.refresh_from_db()
        # The prior valid state survives untouched — no partial corruption.
        self.assertEqual(self.page.page_appearance_overrides, {"content_width": 1100})

    def test_patch_rejected_on_published_version(self):
        svc.publish(self.store)
        published_version = StorefrontLayoutVersion.objects.get(
            layout__store=self.store, status=StorefrontLayoutVersion.Status.PUBLISHED,
        )
        published_page = published_version.get_page(StorefrontPage.PageType.CART)
        with self.assertRaises(PageAppearanceNotDraftError):
            apply_page_appearance_patch(page=published_page, patch={"content_width": 1100})


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PageAppearanceEndToEndRenderingTests(TestCase):
    """Proves the full chain: canonical write -> Draft/Published lifecycle
    -> the SAME resolver Preview and Public both reach -> actual rendered
    CSS custom properties on templates/base.html's <html> tag."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        _verified_domain(self.store, HOST)
        self.draft = svc.get_or_create_draft(self.store)

    def _publish_with_store_global_and_page_override(self):
        self.draft.appearance_config = svc.validate_appearance_config(
            {**self.draft.effective_appearance_config(), "content_width": 1500},
        )
        self.draft.save(update_fields=["appearance_config"])

        cart_page = self.draft.get_page(StorefrontPage.PageType.CART)
        apply_page_appearance_patch(page=cart_page, patch={"content_width": 1100})

        svc.publish(self.store)

    def test_home_uses_store_global_content_width(self):
        self._publish_with_store_global_and_page_override()
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "--sfb-content-width:1500px")

    def test_cart_uses_its_own_page_override(self):
        self._publish_with_store_global_and_page_override()
        resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "--sfb-content-width:1100px")
        # Never the Store-global value on this page.
        self.assertNotContains(resp, "--sfb-content-width:1500px")

    def test_brand_identity_colors_are_identical_across_pages_regardless_of_page_override(self):
        """The one invariant this tier must never violate — a customer must
        see the same brand on every page, even though content_width now
        legitimately varies per page."""
        self._publish_with_store_global_and_page_override()
        home_resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        cart_resp = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST)

        def _extract_style_attr(html: str) -> str:
            start = html.index('style="--brand-primary:')
            end = html.index('"', start + len('style="'))
            return html[start:end]

        home_style = _extract_style_attr(home_resp.content.decode())
        cart_style = _extract_style_attr(cart_resp.content.decode())

        def _brand_primary(style: str) -> str:
            marker = "--brand-primary:"
            start = style.index(marker) + len(marker)
            end = style.index(";", start)
            return style[start:end]

        self.assertEqual(_brand_primary(home_style), _brand_primary(cart_style))

    def test_no_override_ever_set_is_unaffected(self):
        """Zero behavior change for every page that never uses this tier —
        the exact pre-Task-3C rendered value."""
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "--sfb-content-width:1200px")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver", "sfb-test.rastisi.localhost"])
class PageAppearancePreviewMatchesPublicTests(StorefrontBuilderViewsTestCase):
    """The canonical resolver must be reused identically by Preview
    (Draft) and Public (Published) — proven here on the SAME page_type."""

    def setUp(self):
        super().setUp()
        _verified_domain(self.store, HOST)

    def test_preview_reflects_the_page_override_before_publish(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        cart_page = draft.get_page(StorefrontPage.PageType.CART)
        apply_page_appearance_patch(page=cart_page, patch={"content_width": 1100})

        resp = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=cart")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "--sfb-content-width:1100px")

    def test_preview_and_public_agree_after_publish(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        cart_page = draft.get_page(StorefrontPage.PageType.CART)
        apply_page_appearance_patch(page=cart_page, patch={"content_width": 1100})
        svc.publish(self.store)

        preview_resp = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=cart")
        self.assertContains(preview_resp, "--sfb-content-width:1100px")

        public_client = Client(HTTP_HOST=HOST)
        public_resp = public_client.get(reverse("cart:detail"))
        self.assertContains(public_resp, "--sfb-content-width:1100px")
