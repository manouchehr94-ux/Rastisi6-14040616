"""Contract tests for the dark_digital v2 luxury/mobile-navigation rebuild."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import global_region_registry as g
from apps.storefront_builder import layout_preset_registry as lpr
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
        self.assertEqual(
            draft.footer_config["mobile_nav_variant"],
            lpr.get_layout_preset("dark_digital").footer["mobile_nav_variant"],
        )

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
        # FOLLOWUP-10: the fixed strip only keeps the (service-gated) shipping line; the authenticity / return icons are still
        # provided by the shared partial for merchant-verified trust items.
        self.assertIn('with name="truck"', product_main)
        for icon_name in ("shield-check", "truck", "return-policy"):
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
        self.assertEqual(
            draft.footer_config["mobile_nav_variant"],
            lpr.get_layout_preset("dark_digital").footer["mobile_nav_variant"],
        )
        self.assertNotEqual(draft.footer_config["mobile_nav_variant"], "hidden")

        preset_service.apply_preset_by_key(draft, "warm_boutique")
        draft.refresh_from_db()
        # the next template ships its OWN navigation choice; nothing is inherited from the previous template
        self.assertEqual(
            draft.footer_config["mobile_nav_variant"],
            lpr.get_layout_preset("warm_boutique").footer.get("mobile_nav_variant", "hidden"),
        )

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
        self.nav_variant = lpr.get_layout_preset("dark_digital").footer["mobile_nav_variant"]
        layout_service.publish(self.store)

    @override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
    def test_public_home_renders_functional_mobile_nav_and_real_routes(self):
        resp = Client(HTTP_HOST=HOST).get(reverse("catalog:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'data-mobile-nav="{self.nav_variant}"')
        self.assertContains(resp, reverse("cart:detail"))
        self.assertContains(resp, reverse("customers:account"))
        self.assertContains(resp, reverse("catalog:product-list"))

    @override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
    def test_context_resolves_mobile_nav_renderer_from_published_footer_config(self):
        request = RequestFactory().get("/")
        ctx = build_universal_storefront_context(request, self.store, StorefrontPage.PageType.HOME)
        self.assertEqual(ctx["mobile_bottom_nav_template"], f"storefront_builder/partials/global_mobile_nav/{self.nav_variant}.html")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_builder_preview_has_nav_but_never_live_cart_count_badge(self):
        user = User.objects.create_user(username="dark_v2_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        c = Client(HTTP_HOST=ADMIN_HOST)
        self.assertTrue(c.login(username="dark_v2_owner", password="pass12345"))
        resp = c.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'data-mobile-nav="{self.nav_variant}"')
        self.assertNotContains(resp, 'class="gmn-count"')
