"""Contract tests for the dark_digital v2 luxury/mobile-navigation rebuild."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import global_region_registry as g
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service, preset_service
from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()
HOST = "dark-v2-public.example.com"
ADMIN_HOST = "dark-v2-admin.rastisi.localhost"
ROOT = Path(__file__).resolve().parents[3]


def _store():
    return Store.objects.get(slug="akhlaghi")


class DarkDigitalV2RecipeTests(TestCase):
    def test_recipe_identity_and_shell(self):
        preset = lpr.get_layout_preset("dark_digital")
        self.assertEqual(preset.version, "2")
        self.assertEqual(preset.default_palette_slug, "theme-black-gold")
        self.assertEqual(preset.appearance["content_width"], 1320)
        self.assertEqual(preset.header["header_variant"], "luxury_search")
        self.assertEqual(preset.footer["footer_variant"], "dark_tech")
        self.assertEqual(preset.footer["mobile_nav_variant"], "luxury_floating_cart")

    def test_home_recipe_is_distinct_and_uses_registered_generic_variants(self):
        home = lpr.get_layout_preset("dark_digital").pages["home"]
        self.assertEqual([e.section_key for e in home], [
            "hero_banner", "category_grid", "product_section", "trust_features", "product_section",
        ])
        self.assertEqual(home[0].settings["hero_style"], "luxury_showcase")
        self.assertEqual(home[1].settings["display_mode"], "luxury_shortcuts")
        self.assertTrue(all(e.settings["card"]["card_style"] == "luxury_dark" for e in (home[2], home[4])))
        self.assertIn("luxury_showcase", section_registry.HERO_STYLE_CHOICES)
        self.assertIn("luxury_shortcuts", section_registry.CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("luxury_dark", section_registry.CARD_STYLE_CHOICES)
        for entry in (home[2], home[4]):
            self.assertEqual(entry.settings["responsive"]["desktop_columns"], 4)
            self.assertEqual(entry.settings["responsive"]["tablet_columns"], 3)
            self.assertEqual(entry.settings["responsive"]["mobile_columns"], 2)

    def test_previous_completed_template_versions_stay_frozen(self):
        self.assertEqual(lpr.get_layout_preset("fashion_promo_catalog").version, "7")
        for key in ("warm_boutique", "premium_leather", "dense_marketplace", "editorial_jewelry"):
            self.assertEqual(lpr.get_layout_preset(key).version, "2", key)

    def test_no_template_identity_branch_was_added_to_generic_runtime(self):
        for rel in (
            "apps/storefront_builder/services/render_service.py",
            "apps/storefront_builder/services/storefront_context_service.py",
            "apps/storefront_builder/global_region_registry.py",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('template_key == "dark_digital"', source)
            self.assertNotIn("store.slug ==", source)


class MobileBottomNavRegistryTests(TestCase):
    def test_mobile_region_defaults_to_hidden_for_legacy_stores(self):
        self.assertEqual(g.GLOBAL_MOBILE_NAV_REGION.default_variant, "hidden")
        self.assertEqual(g.resolve_active_global_variant(g.GLOBAL_MOBILE_NAV_REGION, {}).key, "hidden")

    def test_luxury_variant_is_registered_and_trusted(self):
        variant = g.get_global_variant(g.GLOBAL_MOBILE_NAV_REGION, "luxury_floating_cart")
        self.assertIsNotNone(variant)
        self.assertEqual(variant.renderer, "storefront_builder/partials/global_mobile_nav/luxury_floating_cart.html")

    def test_footer_validation_accepts_valid_and_rejects_unknown_mobile_variant(self):
        cleaned = layout_service.validate_footer_config({"show_copyright": True, "mobile_nav_variant": "luxury_floating_cart"})
        self.assertEqual(cleaned["mobile_nav_variant"], "luxury_floating_cart")
        with self.assertRaises(layout_service.FooterConfigValidationError):
            layout_service.validate_footer_config({"show_copyright": True, "mobile_nav_variant": "../../x"})

    def test_applying_preset_persists_mobile_nav_in_footer_config(self):
        store = _store()
        draft = layout_service.get_or_create_draft(store)
        preset_service.apply_preset_by_key(draft, "dark_digital")
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config["mobile_nav_variant"], "luxury_floating_cart")

    def test_mobile_nav_css_is_mobile_only_and_safe_area_aware(self):
        css = (ROOT / "apps/storefront_builder/static/css/storefront_builder.css").read_text(encoding="utf-8")
        self.assertIn(".gmn,.gmn-spacer{display:none}", css)
        self.assertIn("@media(max-width:680px)", css)
        self.assertIn("env(safe-area-inset-bottom", css)

    def test_mobile_cart_count_has_stable_htmx_oob_target(self):
        nav = (ROOT / "apps/storefront_builder/templates/storefront_builder/partials/global_mobile_nav/luxury_floating_cart.html").read_text(encoding="utf-8")
        oob = (ROOT / "apps/cart/templates/cart/partials/header_counts_oob.html").read_text(encoding="utf-8")
        self.assertIn('id="mobile-cart-count"', nav)
        self.assertIn('id="mobile-cart-count"', oob)
        self.assertIn('hx-swap-oob="outerHTML:#mobile-cart-count"', oob)

    def test_final_polish_product_trust_icons_use_shared_currentcolor_svg(self):
        product_main = (ROOT / "apps/storefront_builder/templates/storefront_builder/sections/product_main.html").read_text(encoding="utf-8")
        icon_partial = (ROOT / "apps/storefront_builder/templates/storefront_builder/partials/global_header/_shared/icon.html").read_text(encoding="utf-8")
        for raw_emoji in ("🛡", "🚚", "↩"):
            self.assertNotIn(raw_emoji, product_main)
        for icon_name in ("shield-check", "truck", "return-policy"):
            self.assertIn(f'with name="{icon_name}"', product_main)
            self.assertIn(f'data-rastisi-icon="{icon_name}"', icon_partial)
        self.assertIn('stroke="currentColor"', icon_partial)

    def test_final_polish_pdp_category_state_does_not_claim_aria_current_page(self):
        nav = (ROOT / "apps/storefront_builder/templates/storefront_builder/partials/global_mobile_nav/luxury_floating_cart.html").read_text(encoding="utf-8")
        self.assertIn("page_type == 'listing' or page_type == 'collection' or page_type == 'product_detail'", nav)
        self.assertIn("{% if page_type == 'listing' %} aria-current=\"page\"{% endif %}", nav)
        self.assertNotIn("page_type == 'product_detail' %} aria-current=\"page\"", nav)

    def test_switching_to_another_ready_template_does_not_leak_mobile_nav(self):
        store = _store()
        draft = layout_service.get_or_create_draft(store)
        preset_service.apply_preset_by_key(draft, "dark_digital")
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config["mobile_nav_variant"], "luxury_floating_cart")

        preset_service.apply_preset_by_key(draft, "warm_boutique")
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config["mobile_nav_variant"], "hidden")

class MobileBottomNavRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _store()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.update_or_create(
            hostname=HOST,
            defaults={
                "store": self.store,
                "is_primary": False,
                "verification_status": StoreDomain.VerificationStatus.VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        draft = layout_service.get_or_create_draft(self.store)
        preset_service.apply_preset_by_key(draft, "dark_digital")
        layout_service.publish(self.store)

    @override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
    def test_public_home_renders_functional_mobile_nav_and_real_routes(self):
        resp = Client(HTTP_HOST=HOST).get(reverse("catalog:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-mobile-nav="luxury_floating_cart"')
        self.assertContains(resp, reverse("cart:detail"))
        self.assertContains(resp, reverse("customers:account"))
        self.assertContains(resp, reverse("catalog:product-list"))

    @override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
    def test_context_resolves_mobile_nav_renderer_from_published_footer_config(self):
        request = RequestFactory().get("/")
        ctx = build_universal_storefront_context(request, self.store, StorefrontPage.PageType.HOME)
        self.assertEqual(ctx["mobile_bottom_nav_template"], "storefront_builder/partials/global_mobile_nav/luxury_floating_cart.html")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_builder_preview_has_nav_but_never_live_cart_count_badge(self):
        user = User.objects.create_user(username="dark_v2_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        c = Client(HTTP_HOST=ADMIN_HOST)
        self.assertTrue(c.login(username="dark_v2_owner", password="pass12345"))
        resp = c.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-mobile-nav="luxury_floating_cart"')
        self.assertNotContains(resp, 'class="gmn-count"')


class MobileBottomNavEditorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _store()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.user = User.objects.create_user(username="dark_v2_editor", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="dark_v2_editor", password="pass12345")
        # P5-W5A — both tests below deliberately exercise the LEGACY
        # full-page footer form (see the second test's own comment); per
        # the binding single-active-write-surface policy this legacy POST
        # is now fail-closed for a Store on the R4 default and remains
        # available only for a Store explicitly pinned back — exactly the
        # rollback scenario these tests are actually testing.
        layout = layout_service.get_or_create_layout(self.store)
        layout.r4_editor_enabled = False
        layout.save(update_fields=["r4_editor_enabled"])

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_footer_editor_round_trips_mobile_navigation_variant(self):
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on", "footer_variant": "dark_tech", "mobile_nav_variant": "luxury_floating_cart",
        })
        self.assertEqual(resp.status_code, 302)
        draft = layout_service.get_or_create_draft(self.store)
        self.assertEqual(draft.footer_config["mobile_nav_variant"], "luxury_floating_cart")
        # The V3 Builder mounts footer controls through the HTMX inspector partial.
        # Exercise the same surface merchants use instead of the legacy full-page footer form.
        get_resp = self.client.get(
            reverse("dashboard:storefront-builder-footer"),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(get_resp, 'id="mobile_nav_variant_select"')
        self.assertContains(get_resp, 'value="luxury_floating_cart" selected')

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_legacy_footer_post_preserves_mobile_navigation_variant(self):
        first = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on",
            "footer_variant": "dark_tech",
            "mobile_nav_variant": "luxury_floating_cart",
        })
        self.assertEqual(first.status_code, 302)

        # Simulate the legacy full-page Footer Settings form, which has no
        # mobile_nav_variant control. Saving it must not erase the Builder choice.
        second = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on",
            "footer_variant": "dark_tech",
        })
        self.assertEqual(second.status_code, 302)
        draft = layout_service.get_or_create_draft(self.store)
        self.assertEqual(draft.footer_config["mobile_nav_variant"], "luxury_floating_cart")
