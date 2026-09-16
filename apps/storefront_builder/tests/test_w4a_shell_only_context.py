"""P5-W4A — the explicit ``shell_only`` contract on
``storefront_context_service.build_universal_storefront_context``.

Domain-owned public pages (Wishlist, CMS) don't correspond to any of the six
real ``StorefrontPage.PageType`` values. ``shell_only=True`` is an EXPLICIT
opt-in (never inferred from an unrecognized ``page_type`` string) that
projects the Store's published Header/Footer/Bottom-Nav/appearance chrome —
the exact same projection every real page type gets — without resolving or
touching any ``StorefrontPage`` row. See
``docs/superpowers/specs/2026-09-16-phase5-w4a-public-shell-convergence-design.md``
§11 for the full architectural rationale (including why the original design
draft's implicit "unknown page_type => shell-only" rule was rejected by
Architect review)."""

from unittest import mock

from django.test import RequestFactory, TestCase

from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import page_resolution_service
from apps.storefront_builder.services.storefront_context_service import (
    build_universal_storefront_context,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ShellOnlyContextTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.get("/")

    def test_shell_only_published_store_returns_canonical_shell(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self.store.refresh_from_db()

        request = self._request()
        shell_ctx = build_universal_storefront_context(
            request, self.store, "wishlist", shell_only=True,
        )

        self.assertIs(shell_ctx["uses_universal_shell"], True)
        self.assertIsNotNone(shell_ctx["storefront_version"])
        self.assertIsNone(shell_ctx["storefront_page"])
        self.assertEqual(shell_ctx["page_type"], "wishlist")
        self.assertIsNotNone(shell_ctx["header_variant_template"])
        self.assertIsNotNone(shell_ctx["footer_variant_template"])
        self.assertIsNotNone(shell_ctx["store_appearance"])
        self.assertEqual(shell_ctx["render_items"], [])
        self.assertEqual(shell_ctx["rows"], [])
        self.assertEqual(shell_ctx["render_containers"], [])
        self.assertIs(shell_ctx["use_container_layout"], False)

        # Same projection path as a real page type on the SAME Store/version —
        # proves shell_only shares (not forks) the canonical header/footer
        # resolution, not merely "produces a similarly-shaped value."
        home_request = self._request()
        home_ctx = build_universal_storefront_context(
            home_request, self.store, StorefrontPage.PageType.HOME,
        )
        self.assertEqual(shell_ctx["header_variant_template"], home_ctx["header_variant_template"])
        self.assertEqual(shell_ctx["footer_variant_template"], home_ctx["footer_variant_template"])
        self.assertEqual(shell_ctx["mobile_bottom_nav_template"], home_ctx["mobile_bottom_nav_template"])
        self.assertEqual(
            list(shell_ctx["top_level_categories"]), list(home_ctx["top_level_categories"])
        )

    def test_shell_only_unpublished_store_returns_legacy_fallback(self):
        # No get_or_create_draft/publish call -> genuinely unpublished.
        request = self._request()
        shell_ctx = build_universal_storefront_context(
            request, self.store, "wishlist", shell_only=True,
        )
        self.assertIs(shell_ctx["uses_universal_shell"], False)
        self.assertIsNone(shell_ctx["storefront_version"])
        self.assertIsNone(shell_ctx["storefront_page"])
        self.assertEqual(shell_ctx["page_type"], "wishlist")
        self.assertIsNone(shell_ctx["mobile_bottom_nav_template"])
        self.assertNotIn("header_variant_template", shell_ctx)
        self.assertNotIn("footer_variant_template", shell_ctx)
        self.assertEqual(shell_ctx["render_items"], [])

    def test_invalid_normal_page_type_preserves_todays_fail_safe(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self.store.refresh_from_db()

        request = self._request()
        # shell_only NOT passed -> defaults False. A typo'd "real" page_type
        # must NOT silently become a valid shell-only page.
        ctx = build_universal_storefront_context(request, self.store, "prodcut_detail")

        self.assertIs(ctx["uses_universal_shell"], False)
        self.assertIsNone(ctx["storefront_version"])
        self.assertIsNone(ctx["storefront_page"])
        self.assertIsNone(ctx["mobile_bottom_nav_template"])
        self.assertNotIn("header_variant_template", ctx)
        self.assertEqual(ctx["render_items"], [])

    def test_shell_only_never_resolves_a_storefront_page(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self.store.refresh_from_db()

        request = self._request()
        with mock.patch.object(
            page_resolution_service, "resolve_published_page",
            wraps=page_resolution_service.resolve_published_page,
        ) as spy:
            shell_ctx = build_universal_storefront_context(
                request, self.store, "wishlist", shell_only=True,
            )
        spy.assert_not_called()
        self.assertIsNone(shell_ctx["storefront_page"])
        self.assertEqual(shell_ctx["render_items"], [])
        self.assertEqual(shell_ctx["rows"], [])
        self.assertEqual(shell_ctx["render_containers"], [])

    def test_shell_only_published_sets_request_appearance_version_not_page(self):
        svc.get_or_create_draft(self.store)
        version = svc.publish(self.store)
        self.store.refresh_from_db()

        request = self._request()
        build_universal_storefront_context(request, self.store, "wishlist", shell_only=True)

        self.assertEqual(request.storefront_appearance_version.pk, version.pk)
        self.assertIsNone(request.storefront_appearance_page)

    def test_normal_page_type_request_side_effects_unchanged(self):
        svc.get_or_create_draft(self.store)
        version = svc.publish(self.store)
        self.store.refresh_from_db()

        request = self._request()
        build_universal_storefront_context(request, self.store, StorefrontPage.PageType.HOME)

        self.assertEqual(request.storefront_appearance_version.pk, version.pk)
        self.assertIsNotNone(request.storefront_appearance_page)
        self.assertEqual(
            request.storefront_appearance_page.page_type, StorefrontPage.PageType.HOME
        )
