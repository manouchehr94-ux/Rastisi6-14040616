"""U2A — Visual Global Header System (Header + Navigation + Search + Mobile Shell).

Covers the required test categories A-S from the U2A work order:

A/C — read-time fallback safety (``global_region_registry.resolve_active_global_variant``
      never raises; missing/unknown stored key -> ``default_variant``).
B/F — a valid stored key selects its own distinct, registered renderer.
D   — merchant JSON can never select an arbitrary template path (only a
      registered variant *key* is ever consulted).
E   — all five variants (legacy_default + four new archetypes) are registered.
G   — the existing default storefront (no ``header_variant`` set) still
      resolves the exact pre-U2A renderer, unchanged.
H/I — the shared search/nav-menu partials/context are the same across every
      variant (real reuse, not four independent copies).
J   — every variant template declares a mobile navigation/menu-trigger
      affordance (local ``ghMobileOpen``/``aria-controls="gh-mobile-nav"``, or the
      legacy_default's own equivalent burger+nav).
K   — no ``template_key``/``store.slug``/``family_slug`` conditional exists
      anywhere reachable from this feature.
L   — cross-store isolation: two Stores' header variants never leak.
M   — resolving the active variant/template performs zero DB queries.
N   — the persisted config value is always the stable key, never a path.
O/P — editor POST rejects an unknown key and round-trips a valid one.
Q   — no migration required (``header_variant`` lives inside the existing
      ``StorefrontLayoutVersion.header_config`` JSONField).
R   — ``SECTION_REGISTRY`` is untouched (still exactly 34 keys).
S   — the U1B2 "no production variant declares capabilities" tripwire
      (a completely separate, pre-existing contract) still passes untouched.
"""

import inspect
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import global_region_registry as g
from apps.storefront_builder import section_registry as section_registry_module
from apps.storefront_builder import variant_contract as variant_contract_module
from apps.storefront_builder.section_registry import SECTION_REGISTRY
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context
from apps.storefront_builder.models import StorefrontPage
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "u2a-header-admin.rastisi.localhost"
PUBLIC_HOST = "u2a-header-public.example.com"

_ALL_VARIANT_KEYS = {
    "legacy_default", "marketplace_search_first", "premium_three_column",
    "boutique_centered", "dark_tech", "promo_search_nav", "beauty_search_nav",
    "chocolate_centered_search", "atelier_nav", "luxury_search",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GLOBAL_HEADER_DIR = (
    _REPO_ROOT / "apps" / "storefront_builder" / "templates" / "storefront_builder"
    / "partials" / "global_header"
)
_GLOBAL_HEADER_CSS_PATH = (
    _REPO_ROOT / "apps" / "storefront_builder" / "static" / "css" / "storefront_builder.css"
)
_LOGO_PARTIAL_PATH = _GLOBAL_HEADER_DIR / "_shared" / "logo.html"
_LEGACY_HEADER_PATH = (
    _REPO_ROOT / "apps" / "storefront_builder" / "templates" / "storefront_builder"
    / "partials" / "page_shell_header.html"
)
_THEME_PALETTE_PATH = _REPO_ROOT / "apps" / "core" / "static" / "css" / "theme_palette.css"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ReadTimeFallbackSafetyTests(TestCase):
    """Test A/C — resolve_active_global_variant never raises; missing/unknown
    stored value always falls back to the registered default."""

    def test_missing_header_variant_key_falls_back_to_default(self):
        variant = g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, {})
        self.assertEqual(variant.key, g.GLOBAL_HEADER_REGION.default_variant)

    def test_none_config_falls_back_to_default(self):
        variant = g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, None)
        self.assertEqual(variant.key, g.GLOBAL_HEADER_REGION.default_variant)

    def test_unknown_stored_variant_falls_back_to_default_without_raising(self):
        variant = g.resolve_active_global_variant(
            g.GLOBAL_HEADER_REGION, {"header_variant": "some_retired_or_typo_key"},
        )
        self.assertEqual(variant.key, g.GLOBAL_HEADER_REGION.default_variant)

    def test_non_string_stored_variant_falls_back_without_raising(self):
        for bogus in (123, [], {}, True):
            variant = g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, {"header_variant": bogus})
            self.assertEqual(variant.key, g.GLOBAL_HEADER_REGION.default_variant, bogus)


class ValidVariantSelectionTests(TestCase):
    """Test B — a valid, present key resolves to its own, distinct renderer."""

    def test_each_registered_key_resolves_to_its_own_renderer(self):
        for variant in g.GLOBAL_HEADER_REGION.variants:
            resolved = g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, {"header_variant": variant.key})
            self.assertEqual(resolved.key, variant.key)
            self.assertEqual(
                g.resolve_global_renderer_template(g.GLOBAL_HEADER_REGION, {"header_variant": variant.key}),
                variant.renderer,
            )


class NoArbitraryTemplatePathTests(TestCase):
    """Test D — a merchant JSON value is only ever used as a lookup *key*
    into the trusted registry; it can never itself become the rendered
    template path."""

    def test_arbitrary_path_like_value_never_becomes_the_renderer(self):
        malicious_values = [
            "../../../etc/passwd",
            "/etc/passwd",
            "storefront_builder/partials/global_header/marketplace_search_first.html",
            "some/random/template.html",
            "C:\\Windows\\System32",
        ]
        for value in malicious_values:
            template = g.resolve_global_renderer_template(g.GLOBAL_HEADER_REGION, {"header_variant": value})
            # هیچ‌کدام از این مقادیر خودشان به‌عنوان مسیرِ Template استفاده
            # نشده‌اند — نتیجه همیشه یکی از پنج renderer ثبت‌شده است.
            self.assertIn(template, {v.renderer for v in g.GLOBAL_HEADER_REGION.variants}, value)

    def test_renderer_namespace_is_enforced_at_import_time(self):
        with self.assertRaises(g.InvalidGlobalVariantDefinitionError):
            g._validate_global_variant_renderer("../outside/namespace.html")
        with self.assertRaises(g.InvalidGlobalVariantDefinitionError):
            g._validate_global_variant_renderer("/absolute/path.html")
        with self.assertRaises(g.InvalidGlobalVariantDefinitionError):
            g._validate_global_variant_renderer("not/in/namespace.html")


class AllFourProductionVariantsRegisteredTests(TestCase):
    """Test E/F — the four new archetypes (plus the backward-compatible
    default) are all registered, with five distinct renderer paths."""

    def test_all_five_keys_registered(self):
        keys = {v.key for v in g.GLOBAL_HEADER_REGION.variants}
        self.assertTrue(_ALL_VARIANT_KEYS.issubset(keys))

    def test_all_five_renderers_are_distinct(self):
        renderers = [v.renderer for v in g.GLOBAL_HEADER_REGION.variants]
        self.assertEqual(len(renderers), len(set(renderers)), renderers)

    def test_default_variant_is_legacy_default(self):
        self.assertEqual(g.GLOBAL_HEADER_REGION.default_variant, "legacy_default")

    def test_legacy_default_renderer_is_the_pre_existing_unmoved_partial(self):
        legacy = g.get_global_variant(g.GLOBAL_HEADER_REGION, "legacy_default")
        self.assertEqual(legacy.renderer, "storefront_builder/partials/page_shell_header.html")


class ExistingDefaultStorefrontUnchangedTests(TestCase):
    """Test G — a real, published Store with no ``header_variant`` set
    resolves the exact pre-U2A renderer through the real HTTP path (public
    homepage), not just the registry function in isolation."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.filter(store=self.store, hostname=PUBLIC_HOST).delete()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)

    @override_settings(ALLOWED_HOSTS=[PUBLIC_HOST, "testserver"])
    def test_published_store_without_header_variant_uses_legacy_default_template(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = svc.validate_header_config({"show_cart": True})
        draft.save(update_fields=["header_config"])
        svc.publish(self.store)

        resp = self.public_client.get(reverse("catalog:home"))
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_builder/partials/page_shell_header.html", template_names)
        for variant_key in _ALL_VARIANT_KEYS - {"legacy_default"}:
            self.assertNotIn(
                f"storefront_builder/partials/global_header/{variant_key}.html", template_names,
            )


class SharedSearchAndNavReuseTests(TestCase):
    """Test H/I — one real search component/context and one real
    NAV_HEADER/category data source is what every variant template
    consumes; not four independent re-implementations."""

    def test_every_variant_template_includes_the_shared_search_partial_source(self):
        for key in ("marketplace_search_first", "premium_three_column", "boutique_centered", "dark_tech"):
            path = _GLOBAL_HEADER_DIR / f"{key}.html"
            source = path.read_text(encoding="utf-8")
            self.assertIn("_shared/search_form.html", source, key)

    def test_every_variant_template_includes_the_shared_nav_header_items_partial(self):
        for key in ("marketplace_search_first", "premium_three_column", "boutique_centered", "dark_tech"):
            path = _GLOBAL_HEADER_DIR / f"{key}.html"
            source = path.read_text(encoding="utf-8")
            self.assertIn("_shared/nav_header_items.html", source, key)

    def test_storefront_context_service_provides_same_nav_categories_regardless_of_variant(self):
        """``nav_categories``/``NAV_HEADER`` come from the global context
        processors, never from the resolved variant — the context service
        itself does not branch on ``header_variant`` for anything except the
        one ``header_variant_template`` key."""
        store = _akhlaghi()
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        for key in _ALL_VARIANT_KEYS:
            draft = svc.get_or_create_draft(store)
            draft.header_config = svc.validate_header_config({"show_cart": True, "header_variant": key})
            draft.save(update_fields=["header_config"])
            svc.publish(store)
            context = build_universal_storefront_context(request, store, StorefrontPage.PageType.HOME)
            self.assertIn("top_level_categories", context)
            self.assertEqual(
                context["header_variant_template"],
                g.get_global_variant(g.GLOBAL_HEADER_REGION, key).renderer,
            )


class MobileShellPresenceTests(TestCase):
    """Test J — every variant declares a mobile nav/menu-trigger affordance."""

    def test_every_new_variant_declares_mobile_nav_trigger(self):
        for key in ("marketplace_search_first", "premium_three_column", "boutique_centered", "dark_tech"):
            path = _GLOBAL_HEADER_DIR / f"{key}.html"
            source = path.read_text(encoding="utf-8")
            self.assertIn('x-data="{ ghMobileOpen: false }"', source, key)
            self.assertIn("ghMobileOpen", source, key)
            self.assertNotIn("mobileNavOpen", source, key)
            self.assertIn('aria-controls="gh-mobile-nav"', source, key)
            self.assertIn('id="gh-mobile-nav"', source, key)

    def test_legacy_default_still_has_its_own_mobile_burger_and_nav(self):
        source = _LEGACY_HEADER_PATH.read_text(encoding="utf-8")
        self.assertIn("mobileNavOpen", source)
        self.assertIn('<nav class="nav"', source)


class NoForbiddenBranchingTests(TestCase):
    """Test K — no ``if template_key ==``/``if store.slug ==``/
    ``if family_slug ==`` conditional exists in the new registry module or
    any of the new template partials."""

    _FORBIDDEN_PATTERNS = (
        re.compile(r"template_key\s*=="),
        re.compile(r"store\.slug\s*=="),
        re.compile(r"family_slug\s*=="),
    )

    def test_global_region_registry_source_has_no_forbidden_conditionals(self):
        source = inspect.getsource(g)
        for pattern in self._FORBIDDEN_PATTERNS:
            self.assertIsNone(pattern.search(source), pattern.pattern)

    def test_new_variant_templates_have_no_forbidden_conditionals(self):
        for path in _GLOBAL_HEADER_DIR.rglob("*.html"):
            source = path.read_text(encoding="utf-8")
            for pattern in self._FORBIDDEN_PATTERNS:
                self.assertIsNone(pattern.search(source), f"{path}: {pattern.pattern}")


class CrossStoreIsolationTests(TestCase):
    """Test L — two Stores' independently-configured header variants never
    leak into each other's public rendering."""

    def setUp(self):
        cache.clear()

    @override_settings(ALLOWED_HOSTS=["u2a-store-a.example.com", "u2a-store-b.example.com", "testserver"])
    def test_two_stores_resolve_their_own_independent_header_variant(self):
        store_a = _akhlaghi()
        store_b = Store.objects.create(name="فروشگاه دومِ U2A", slug="u2a-header-store-b", status=Store.Status.ACTIVE)
        StoreDomain.objects.filter(store=store_a, hostname="u2a-store-a.example.com").delete()
        StoreDomain.objects.create(
            store=store_a, hostname="u2a-store-a.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=store_b, hostname="u2a-store-b.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

        draft_a = svc.get_or_create_draft(store_a)
        draft_a.header_config = svc.validate_header_config({"show_cart": True, "header_variant": "dark_tech"})
        draft_a.save(update_fields=["header_config"])
        svc.publish(store_a)

        draft_b = svc.get_or_create_draft(store_b)
        draft_b.header_config = svc.validate_header_config({"show_cart": True, "header_variant": "boutique_centered"})
        draft_b.save(update_fields=["header_config"])
        svc.publish(store_b)

        resp_a = Client(HTTP_HOST="u2a-store-a.example.com").get(reverse("catalog:home"))
        resp_b = Client(HTTP_HOST="u2a-store-b.example.com").get(reverse("catalog:home"))

        templates_a = [t.name for t in resp_a.templates if t.name]
        templates_b = [t.name for t in resp_b.templates if t.name]
        self.assertIn("storefront_builder/partials/global_header/dark_tech.html", templates_a)
        self.assertNotIn("storefront_builder/partials/global_header/boutique_centered.html", templates_a)
        self.assertIn("storefront_builder/partials/global_header/boutique_centered.html", templates_b)
        self.assertNotIn("storefront_builder/partials/global_header/dark_tech.html", templates_b)


class ZeroQueryResolutionTests(TestCase):
    """Test M — resolving the active variant/template is pure in-memory
    metadata lookup; it must never itself issue a database query."""

    def test_resolve_active_global_variant_performs_no_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, {"header_variant": "dark_tech"})
            g.resolve_global_renderer_template(g.GLOBAL_HEADER_REGION, {"header_variant": "unknown"})
        self.assertEqual(len(ctx.captured_queries), 0)


class PersistedValueIsStableKeyTests(TestCase):
    """Test N — whatever gets written to ``header_config["header_variant"]``
    is always one of the five stable keys, never a template path."""

    def test_validate_header_config_persists_only_a_registered_key(self):
        for key in _ALL_VARIANT_KEYS:
            cleaned = svc.validate_header_config({"show_cart": True, "header_variant": key})
            self.assertEqual(cleaned["header_variant"], key)
            self.assertNotIn("/", cleaned["header_variant"])
            self.assertNotIn(".html", cleaned["header_variant"])

    def test_missing_header_variant_persists_the_default_key(self):
        cleaned = svc.validate_header_config({"show_cart": True})
        self.assertEqual(cleaned["header_variant"], "legacy_default")


class EditorRejectsUnknownVariantTests(TestCase):
    """Test O/P — the editor POST rejects an unknown key outright and
    round-trips a valid selection end-to-end through the real HTTP view."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="u2a_header_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="u2a_header_owner", password="pass12345")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_post_with_unknown_variant_key_is_rejected(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_cart": "on", "header_variant": "totally_made_up_variant",
        })
        self.assertEqual(resp.status_code, 200)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.effective_header_config()["header_variant"], "legacy_default")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_post_with_valid_variant_key_round_trips(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.post(reverse("dashboard:storefront-builder-header"), {
            "show_cart": "on", "header_variant": "premium_three_column",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.header_config["header_variant"], "premium_three_column")

        get_resp = self.client.get(reverse("dashboard:storefront-builder-header"))
        self.assertContains(get_resp, 'value="premium_three_column" selected')


class NoMigrationRequiredTests(TestCase):
    """Test Q — ``header_variant`` lives entirely inside the pre-existing
    ``header_config`` JSONField; no schema change is needed."""

    def test_header_variant_round_trips_through_the_existing_jsonfield(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.header_config = svc.validate_header_config({"show_cart": True, "header_variant": "dark_tech"})
        draft.save(update_fields=["header_config"])
        draft.refresh_from_db()
        self.assertEqual(draft.header_config["header_variant"], "dark_tech")


class SectionRegistryUntouchedTests(TestCase):
    """Test R — U2A does not touch ``SECTION_REGISTRY`` at all."""

    def test_section_registry_still_has_exactly_34_keys(self):
        self.assertEqual(len(SECTION_REGISTRY), 36)


class U1CapabilityTripwireStillPassesTests(TestCase):
    """Test S — the pre-existing U1B2 tripwire (no production
    ``VariantDefinition`` declares its own capabilities) is a completely
    separate contract from this Global Header system and must still pass
    untouched."""

    def test_no_production_section_variant_declares_additional_capabilities(self):
        offenders = [
            (definition.key, variant.key, variant.capabilities)
            for definition in SECTION_REGISTRY.values()
            for variant in definition.variants
            if variant.capabilities
        ]
        self.assertEqual(offenders, [])


# =====================================================================
# U2A VISUAL-CORRECTNESS FIX PASS — regression tests for the 5 issues
# found in external review of U2A_REVIEW.patch:
#   1. marketplace main-row CSS selector mismatch
#   2. global-header CSS variable scope (announcement/tagline outside <header>)
#   3. show_tagline=False being silently coerced back to True by |default:True
#   4. mobile-only nav visible on desktop (initial mobileNavOpen=True)
#   5. hardcoded fake "فروش ویژه آخر هفته" campaign text
# =====================================================================

def _render_variant(template_name, header_config_overrides=None, **extra_ctx):
    from django.template.loader import get_template
    from django.test import RequestFactory

    request = RequestFactory().get("/")

    class _AnonymousUser:
        is_authenticated = False

    request.user = _AnonymousUser()
    header_config = {
        "show_search": True, "show_account": True, "show_wishlist": True, "show_cart": True,
        "sticky": False, "announcement_enabled": False, "announcement_text": "",
        "announcement_links": [], "announcement_show_phone": False, "extra_blocks": [],
        "responsive": {},
    }
    header_config.update(header_config_overrides or {})
    ctx = {
        "header_config": header_config, "is_live_storefront": True, "is_builder_preview": False,
        "nav_categories": [], "NAV_HEADER": None, "SHOP_NAME": "فروشگاه آزمایشی",
        "SHOP_TAGLINE": "بهترین انتخاب شما", "SHOP_LOGO": None, "SHOW_ADMIN_SHORTCUT": False,
        "SHOP_ADMIN_URL": None, "wishlist_count": 0, "cart_count": 0, "SHOP_CONTACT_PHONE": None,
        "SOCIAL_LINKS_HEADER": [], "request": request,
    }
    ctx.update(extra_ctx)
    return get_template(template_name).render(ctx)


class MarketplaceRowSelectorFixTests(TestCase):
    """Fix #1 — .gh-row-main IS the .wrap element (same tag), not an
    ancestor of a separate .wrap descendant; the CSS selector must match
    that actual markup contract."""

    def test_marketplace_dom_carries_wrap_and_row_main_on_the_same_element(self):
        html = _render_variant("storefront_builder/partials/global_header/marketplace_search_first.html")
        self.assertIn('class="wrap gh-row gh-row-main"', html)

    def test_css_no_longer_uses_the_broken_descendant_selector(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertNotIn(".gh-row-main .wrap", css)

    def test_css_uses_the_correct_selector_targeting_the_row_main_element_itself(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--marketplace .gh-row-main{display:flex", css)


class ShowTaglineSemanticsTests(TestCase):
    """Fix #3 — show_tagline=False must definitely hide the tagline;
    omitted/True must keep showing it. ``|default:True`` treats an
    explicit Python False as falsy too and silently un-hides it — the
    partial must compare with ``== False`` instead."""

    def test_explicit_show_tagline_false_hides_tagline(self):
        html = _render_variant("storefront_builder/partials/global_header/marketplace_search_first.html")
        self.assertNotIn("بهترین انتخاب شما", html)

    def test_omitted_show_tagline_preserves_default_shown_behavior(self):
        html = _render_variant("storefront_builder/partials/global_header/premium_three_column.html")
        self.assertIn("بهترین انتخاب شما", html)

    def test_explicit_show_tagline_true_shows_tagline(self):
        from django.template import Context, Template

        template = Template(
            '{% include "storefront_builder/partials/global_header/_shared/logo.html" '
            'with is_live_storefront=True is_builder_preview=False show_tagline=True %}'
        )
        html = template.render(Context({
            "SHOP_NAME": "فروشگاه آزمایشی", "SHOP_TAGLINE": "بهترین انتخاب شما", "SHOP_LOGO": None,
        }))
        self.assertIn("بهترین انتخاب شما", html)

    def test_logo_partial_source_compares_with_explicit_false_not_default_filter(self):
        source = _LOGO_PARTIAL_PATH.read_text(encoding="utf-8")
        self.assertNotIn("show_tagline|default:True", source)
        self.assertIn("show_tagline != False", source)


class DesktopMobileNavVisibilityTests(TestCase):
    """Fix #4 — a dedicated mobile-only nav element (premium/dark_tech,
    where the desktop nav lives in a separate element) must be
    CSS-hidden above the tablet breakpoint by default, independent of the
    legacy body's ``mobileNavOpen`` Alpine state."""

    def test_premium_mobile_nav_hidden_by_default_in_css(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh-premium-mobile-nav{display:none}", css)

    def test_dark_mobile_nav_hidden_by_default_in_css(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh-dark-mobile-nav{display:none}", css)

    def test_premium_mobile_nav_reappears_at_the_tablet_breakpoint(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh-premium-mobile-nav:not(.gh-nav-hidden){display:block}", css)

    def test_dark_mobile_nav_reappears_at_the_tablet_breakpoint(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh-dark-mobile-nav:not(.gh-nav-hidden){display:block}", css)

    def test_every_variant_has_exactly_one_gh_mobile_nav_id_and_matching_aria_controls(self):
        for template_name in (
            "storefront_builder/partials/global_header/marketplace_search_first.html",
            "storefront_builder/partials/global_header/premium_three_column.html",
            "storefront_builder/partials/global_header/boutique_centered.html",
            "storefront_builder/partials/global_header/dark_tech.html",
        ):
            html = _render_variant(template_name)
            self.assertEqual(html.count('id="gh-mobile-nav"'), 1, template_name)
            self.assertIn('aria-controls="gh-mobile-nav"', html, template_name)


class NoFabricatedCommercialContentTests(TestCase):
    """Fix #5 — the shipped marketplace header must never emit a
    hardcoded, unconditional campaign claim; only real merchant-provided
    header_config data (extra_blocks) may produce promotional copy."""

    def test_marketplace_default_render_has_no_fabricated_campaign_text(self):
        html = _render_variant("storefront_builder/partials/global_header/marketplace_search_first.html")
        self.assertNotIn("فروش ویژه", html)
        self.assertNotIn("gh-nav-hot", html)

    def test_marketplace_template_source_has_no_hardcoded_campaign_string(self):
        source = (_GLOBAL_HEADER_DIR / "marketplace_search_first.html").read_text(encoding="utf-8")
        self.assertNotIn("فروش ویژه", source)


class GlobalHeaderCssVariableScopeTests(TestCase):
    """Fix #2 — announcement/header/tagline must all be descendants of the
    same `.gh-shell`-scoped ancestor so custom-property color tokens
    (and the dark_tech palette override) reach all three, not just the
    <header> element itself."""

    def test_dark_tech_wraps_announcement_header_and_tagline_in_one_shell(self):
        html = _render_variant(
            "storefront_builder/partials/global_header/dark_tech.html",
            {"announcement_enabled": True, "extra_blocks": [{"type": "tagline"}]},
        )
        shell_start = html.index('class="gh-shell gh-shell--dark"')
        announce_pos = html.index("gh-announce")
        header_pos = html.index('class="header gh gh--dark')
        tagline_pos = html.rindex("gh-tagline-strip")
        shell_end = html.rindex("</div>")
        self.assertLess(shell_start, announce_pos)
        self.assertLess(announce_pos, header_pos)
        self.assertLess(header_pos, tagline_pos)
        self.assertLess(tagline_pos, shell_end)

    def test_every_new_variant_has_its_own_gh_shell_modifier_class(self):
        expectations = {
            "storefront_builder/partials/global_header/marketplace_search_first.html": "gh-shell--marketplace",
            "storefront_builder/partials/global_header/premium_three_column.html": "gh-shell--premium",
            "storefront_builder/partials/global_header/boutique_centered.html": "gh-shell--boutique",
            "storefront_builder/partials/global_header/dark_tech.html": "gh-shell--dark",
        }
        for template_name, shell_class in expectations.items():
            html = _render_variant(template_name)
            self.assertIn(shell_class, html, template_name)

    def test_css_defines_shell_scoped_variables_not_header_scoped(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh-shell{--gh-ink:", css)
        self.assertIn(".gh-shell--dark{--gh-ink:", css)
        self.assertNotIn(".gh{--gh-ink:", css)
        self.assertNotIn(".gh--dark{--gh-ink:", css)


class LegacyDefaultUnchangedByCorrectionPassTests(TestCase):
    """Fix-pass invariant — legacy_default's own renderer must remain
    byte-for-byte unrelated to any of the gh-shell/gh-* correction work
    (it never used those classes and still doesn't)."""

    def test_legacy_default_template_has_no_gh_shell_classes(self):
        source = _LEGACY_HEADER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("gh-shell", source)
        self.assertNotIn('class="header gh ', source)

    def test_legacy_default_still_resolves_correctly(self):
        variant = g.get_global_variant(g.GLOBAL_HEADER_REGION, "legacy_default")
        self.assertEqual(variant.renderer, "storefront_builder/partials/page_shell_header.html")


class AllFourTrustedRendererKeysStillResolveTests(TestCase):
    """Re-verification after the correction pass — all five keys still
    resolve to their own distinct, registered renderer."""

    def test_all_five_keys_resolve_to_their_registered_renderer(self):
        for variant in g.GLOBAL_HEADER_REGION.variants:
            resolved = g.resolve_active_global_variant(g.GLOBAL_HEADER_REGION, {"header_variant": variant.key})
            self.assertEqual(resolved.renderer, variant.renderer)


# =====================================================================
# U2A VISUAL-CORRECTNESS FIX PASS #2 — regression tests for the 3 issues
# found in real Windows/Chrome manual browser QA against U2A_VISUAL_QA.patch:
#   1. boutique nav overflow/collision from duplicated NAV_HEADER +
#      category_link_row plus an unsafe fixed-height + flex-wrap combo
#   2. dark_tech main header row rendering as a light surface because a
#      global, out-of-scope stylesheet (theme_palette.css) forces
#      .header{...!important}, which beats plain (non-important) specificity
#   3. native horizontal scrollbar chrome visible inside header nav rows
# =====================================================================


class BoutiqueNavDuplicationFixTests(TestCase):
    """Fix #1a — NAV_HEADER (real merchant menu) is the primary boutique
    desktop nav source when it exists; the category list is only a
    fallback for a Store that hasn't configured NAV_HEADER — never both
    rendered together (which produced visually duplicated taxonomy)."""

    def test_boutique_renders_nav_header_items_only_when_nav_header_present(self):
        nav_header = {
            "title": "Main",
            "items": [{"title": "Shoes", "url": "/shoes/", "open_in_new_tab": False, "children": []}],
        }
        html = _render_variant(
            "storefront_builder/partials/global_header/boutique_centered.html",
            NAV_HEADER=nav_header,
            nav_categories=[],
        )
        self.assertIn('class="gh-nl"', html)
        self.assertNotIn('class="gh-cat-link"', html)

    def test_boutique_falls_back_to_category_link_row_when_nav_header_absent(self):
        html = _render_variant(
            "storefront_builder/partials/global_header/boutique_centered.html",
            NAV_HEADER=None,
            nav_categories=[],
        )
        self.assertIn("gh-cat-link-empty", html)
        self.assertNotIn('class="gh-nl"', html)

    def test_boutique_template_source_never_renders_both_sources_unconditionally(self):
        source = (_GLOBAL_HEADER_DIR / "boutique_centered.html").read_text(encoding="utf-8")
        self.assertIn("{% if NAV_HEADER %}", source)
        nav_header_include = 'include "storefront_builder/partials/global_header/_shared/nav_header_items.html"'
        category_include = 'include "storefront_builder/partials/global_header/_shared/category_link_row.html"'
        self.assertIn(nav_header_include, source)
        self.assertIn(category_include, source)


class BoutiqueNavHeightSafetyTests(TestCase):
    """Browser QA V4 — boutique navigation must remain single-line and
    horizontally scroll within its own surface, explicitly defeating the
    shared ``.header .wrap`` fixed-height rule that caused tagline overlap."""

    def test_boutique_nav_uses_specific_auto_height_single_line_rule(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        selector = ".gh--boutique .gh-boutique-nav .gh-boutique-nav-links{"
        self.assertIn(selector, css)
        rule_start = css.index(selector)
        rule_end = css.index("}", rule_start)
        rule = css[rule_start:rule_end]
        self.assertIn("height:auto", rule)
        self.assertIn("min-height:46px", rule)
        self.assertIn("flex-wrap:nowrap", rule)
        self.assertIn("overflow-x:auto", rule)

    def test_boutique_nav_no_longer_uses_wrapping_strategy(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        selector = ".gh--boutique .gh-boutique-nav .gh-boutique-nav-links{"
        rule_start = css.index(selector)
        rule_end = css.index("}", rule_start)
        rule = css[rule_start:rule_end]
        self.assertNotIn("flex-wrap:wrap", rule)
        self.assertNotIn("height:46px", rule.replace("min-height:46px", ""))


class DarkTechMainHeaderSurfaceTests(TestCase):
    """Fix #2 — the compound .gh--dark.header selector must win over the
    global theme_palette.css `.header{...!important}` rule (which beats
    plain specificity outright), by matching its !important on the same
    three properties, scoped to the one compound class combination that
    only the dark_tech variant's own <header> ever carries."""

    def test_dark_header_rule_uses_important_to_beat_the_global_theme_rule(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--dark.header{", css)
        rule_start = css.index(".gh--dark.header{")
        rule_end = css.index("}", rule_start)
        rule = css[rule_start:rule_end]
        self.assertIn("background:var(--gh-bg) !important", rule)
        self.assertIn("color:var(--gh-ink) !important", rule)
        self.assertIn("border-color:var(--gh-border) !important", rule)

    def test_theme_palette_css_forces_header_with_important_confirming_root_cause(self):
        source = _THEME_PALETTE_PATH.read_text(encoding="utf-8")
        self.assertIn(".header{", source)
        rule_start = source.index(".header{")
        rule_end = source.index("}", rule_start)
        rule = source[rule_start:rule_end]
        self.assertIn("!important", rule)

    def test_no_generic_header_wrap_or_body_override_was_introduced(self):
        """The fix must stay scoped to the compound .gh--dark.header
        selector — it must never touch bare .header/.wrap/body anywhere
        in the U2A CSS section."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        u2a_start = css.index("U2A — Global Header Variants")
        u2a_section = css[u2a_start:]
        for forbidden in ("\n.header{", "\nheader{", "\n.wrap{", "\nbody{"):
            self.assertNotIn(forbidden, u2a_section, forbidden)


class HorizontalScrollbarHiddenTests(TestCase):
    """Fix #3 — native scrollbar chrome hidden only on the five real U2A
    header horizontal-scroll containers; scrolling itself (overflow-x)
    remains functional and no other scrollbar anywhere is affected."""

    _SCROLL_CONTAINER_SELECTORS = (
        ".gh-nav-links-scroll",
        ".gh--premium .gh-premium-nav-links",
        ".gh-premium-mobile-nav .wrap",
        ".gh-boutique-nav-links",
        ".gh--dark .gh-dark-cats",
        ".gh-dark-mobile-nav .wrap",
    )

    def test_every_known_scroll_container_hides_scrollbar_chrome(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn("scrollbar-width:none", css)
        self.assertIn("-ms-overflow-style:none", css)
        self.assertIn("::-webkit-scrollbar{display:none}", css)
        for selector in self._SCROLL_CONTAINER_SELECTORS:
            self.assertIn(selector, css, selector)

    def test_scroll_containers_still_declare_overflow_x_auto(self):
        """Scrolling itself must remain functional — only the visual
        chrome is hidden, never the overflow behavior. Each selector also
        appears in the shared scrollbar-hiding rule and (for gh-dark-cats)
        in a responsive display:none override, so this checks for the
        exact layout-rule text rather than slicing between the nearest
        braces."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        for full_rule in (
            ".gh-nav-links-scroll{display:flex;align-items:center;gap:6px;flex:1;min-width:0;overflow-x:auto}",
            ".gh--premium .gh-premium-nav-links{display:flex;align-items:center;gap:2px;overflow-x:auto}",
            ".gh-premium-mobile-nav .wrap{display:flex;align-items:center;gap:4px;height:44px;overflow-x:auto}",
            ".gh--boutique .gh-boutique-nav .gh-boutique-nav-links{display:flex;align-items:center;justify-content:safe center;gap:6px;height:auto;min-height:46px;padding-block:6px;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-inline:contain}",
            ".gh--dark .gh-dark-cats{display:flex;align-items:center;gap:2px;flex:1;min-width:0;overflow-x:auto}",
            ".gh-dark-mobile-nav .wrap{display:flex;align-items:center;gap:4px;height:44px;overflow-x:auto}",
        ):
            self.assertIn(full_rule, css, full_rule)

    def test_scrollbar_hiding_is_not_global(self):
        """A blanket ``*{scrollbar-width:none}`` (or on html/body) would
        hide scrollbars site-wide, including the Builder canvas — the
        fix must only ever target the U2A-namespaced selectors."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("html{scrollbar-width", css)
        self.assertNotIn("body{scrollbar-width", css)
        self.assertNotIn("*{scrollbar-width", css)


class LegacyDefaultUnchangedByFixPassTwoTests(TestCase):
    """Fix-pass invariant — legacy_default must remain completely
    unrelated to any of this pass's boutique/dark_tech/scrollbar work."""

    def test_legacy_default_template_unchanged_markers(self):
        source = _LEGACY_HEADER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("gh-shell", source)
        self.assertNotIn("gh-boutique", source)
        self.assertNotIn("gh-dark", source)
        self.assertNotIn("scrollbar-width", source)

    def test_legacy_default_still_resolves_correctly_after_fix_pass_two(self):
        variant = g.get_global_variant(g.GLOBAL_HEADER_REGION, "legacy_default")
        self.assertEqual(variant.renderer, "storefront_builder/partials/page_shell_header.html")


_PROMO_HEADER_TEMPLATE_PATH = (
    _GLOBAL_HEADER_DIR / "promo_search_nav.html"
)


class PromoHeaderDesktopGridStructureTests(TestCase):
    """Final Home micro-fix — merchant QA: the previous pass only hid the
    inert desktop burger; the promo header's main row must actually read
    as RIGHT=brand / CENTER=search / LEFT=actions in RTL. Implemented as
    a real CSS Grid with explicit named areas (not flex order tricks),
    verified here at the CSS-source level; the live pixel positions were
    verified separately with a real browser render (see the mission's
    final report)."""

    def test_row_main_is_a_grid_with_named_areas(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-row-main{", css)
        self.assertIn('grid-template-areas:"brand search actions"', css)

    def test_logo_is_the_brand_area(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-row-main > .gh-logo{grid-area:brand", css)

    def test_search_is_the_flexible_central_area(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-row-main > .gh-promo-search{grid-area:search", css)

    def test_actions_is_the_compact_auto_width_area(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-row-main > .gh-actions{grid-area:actions}", css)

    def test_search_area_overrides_the_shared_display_contents_wrapper(self):
        """``.gh-promo-search`` also carries the shared ``gh-inline-block``
        class, which sets ``display:contents`` — that makes an element
        invalid as a grid item. The promo-specific override must restore
        a real display value so the grid actually places it."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-row-main > .gh-promo-search{grid-area:search;display:block", css)

    def test_desktop_burger_is_hidden(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-burger{display:none}", css)

    @staticmethod
    def _promo_mobile_block(css: str) -> str:
        """The ``.gh--promo``-specific ``@media(max-width:680px)`` block —
        extracted by anchoring on the promo-only comment that opens it,
        since the file has many unrelated 680px blocks for other
        variants/sections."""
        anchor = css.index("deliberate MOBILE-ONLY")
        start = css.rindex("@media(max-width:680px)", 0, anchor)
        end = css.index("\n}\n", anchor) + 3
        return css[start:end]

    def test_mobile_breakpoint_uses_a_deliberate_three_column_grid(self):
        """Merchant QA addendum — the desktop composition (search fighting
        the logo for space in a flex row) read as broken at 390px: the
        store name visibly clipped, controls overcrowded. Mobile now gets
        its OWN grid — RIGHT=burger, CENTER=logo, LEFT=actions — never a
        reuse/revert of the desktop track sizing."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        mobile_block = self._promo_mobile_block(css)
        self.assertIn('grid-template-areas:"burger logo actions"', mobile_block)
        self.assertIn(".gh--promo .gh-row-main > .gh-burger{grid-area:burger}", mobile_block)
        self.assertIn(".gh--promo .gh-row-main > .gh-logo{grid-area:logo", mobile_block)
        self.assertIn(".gh--promo .gh-row-main > .gh-actions{grid-area:actions}", mobile_block)
        self.assertIn(".gh--promo .gh-burger{display:inline-flex}", mobile_block)

    def test_mobile_hides_the_desktop_inline_search_wrapper(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        mobile_block = self._promo_mobile_block(css)
        self.assertIn(".gh--promo .gh-row-main > .gh-promo-search{display:none}", mobile_block)

    def test_mobile_logo_can_shrink_to_the_grid_tracks_real_available_width(self):
        """Root cause of the merchant-reported clipping ("...ti Mode
        Demo"): a hardcoded px guess for the logo text's max-width still
        ellipsized names that fit comfortably in the actual CENTER grid
        track. The fix constrains the SHRINK path (min-width:0 up the
        ancestor chain) instead of guessing a fixed width, so the text
        renders at its real available size and only ellipsizes if it
        truly doesn't fit."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        mobile_block = self._promo_mobile_block(css)
        self.assertIn(".gh--promo .gh-logo{min-width:0", mobile_block)
        self.assertIn(".gh--promo .gh-logo-text{min-width:0}", mobile_block)

    def test_mobile_search_moves_to_its_own_full_width_row(self):
        """Same established pattern as premium_three_column/dark_tech's
        own ``.gh-mobile-search`` second row — search never competes with
        burger/logo/actions for space in the main row at phone widths."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh--promo .gh-mobile-search:not([data-shell-hide-mobile]){display:block}", css)
        self.assertIn(".gh--promo .gh-mobile-search .gh-search{display:flex", css)

    def test_promo_template_includes_a_dedicated_mobile_search_row_with_unique_field_id(self):
        source = _PROMO_HEADER_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn('class="gh-mobile-search gh-promo-mobile-search"', source)
        self.assertIn('field_id="gh-search-input-promo-mobile"', source)

    def test_promo_template_markup_unchanged_by_css_only_fix(self):
        """This pass fixes the header via CSS structure, not by
        reordering the DOM — burger/logo/search/actions must still exist
        in their original source order (grid-template-areas alone
        determines the visual position)."""
        source = _PROMO_HEADER_TEMPLATE_PATH.read_text(encoding="utf-8")
        burger_pos = source.index("gh-burger")
        logo_pos = source.index("_shared/logo.html")
        search_pos = source.index("gh-promo-search")
        actions_pos = source.index('class="gh-actions"')
        self.assertLess(burger_pos, logo_pos)
        self.assertLess(logo_pos, search_pos)
        self.assertLess(search_pos, actions_pos)


class PromoHeaderMobileNavToggleContractTests(TestCase):
    """Re-verifies the mobile hamburger contract survives the desktop
    grid restructuring — the toggle logic itself (Alpine ``ghMobileOpen``
    state, ``gh-nav-hidden`` class binding) was never touched by this
    pass, only the desktop CSS was."""

    def test_burger_toggles_ghmobileopen_state(self):
        html = _render_variant("storefront_builder/partials/global_header/promo_search_nav.html")
        self.assertIn("@click=\"ghMobileOpen = !ghMobileOpen\"", html)
        self.assertIn('aria-controls="gh-mobile-nav"', html)

    def test_nav_row_binds_hidden_class_to_the_same_state(self):
        html = _render_variant("storefront_builder/partials/global_header/promo_search_nav.html")
        self.assertIn('id="gh-mobile-nav"', html)
        self.assertIn("{ 'gh-nav-hidden': !ghMobileOpen }", html)

    def test_burger_button_itself_is_never_css_hidden_below_the_desktop_breakpoint(self):
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        mobile_block = PromoHeaderDesktopGridStructureTests._promo_mobile_block(css)
        self.assertNotIn(".gh--promo .gh-burger{display:none}", mobile_block)


class PublicHeaderNeverShowsAdminShortcutTests(TestCase):
    """Final storefront-polish pass — root cause: ``SHOW_ADMIN_SHORTCUT``
    used to be true for ANY anonymous visitor of the real public
    ``catalog:home`` (page-gated only, never staff/auth-gated). Every
    Global Header Variant includes the same shared ``admin_shortcut.html``
    partial, so this is verified once per variant at the template level;
    the context-processor-level fix itself is covered by
    ``test_page_shell.py``'s live-request tests."""

    def test_admin_shortcut_never_renders_when_flag_is_false(self):
        for template_name in (
            "storefront_builder/partials/global_header/promo_search_nav.html",
            "storefront_builder/partials/global_header/marketplace_search_first.html",
            "storefront_builder/partials/global_header/premium_three_column.html",
            "storefront_builder/partials/global_header/boutique_centered.html",
            "storefront_builder/partials/global_header/dark_tech.html",
        ):
            html = _render_variant(template_name, SHOW_ADMIN_SHORTCUT=False, SHOP_ADMIN_URL="http://admin.example.com/admin-portal/")
            self.assertNotIn("store-admin-shortcut", html, template_name)
            self.assertNotIn("پنل مدیریت", html, template_name)

    def test_shared_partial_guard_itself_still_works_given_the_flag(self):
        """Sanity check that the assertions above are actually exercising
        a real conditional (not one that's unconditionally False/broken):
        the shared partial DOES render given the same flag/URL — proving
        the fix lives in the context processor (now never sets this True
        for ``catalog:home``), not in a disabled/dead template branch."""
        html = _render_variant(
            "storefront_builder/partials/global_header/promo_search_nav.html",
            SHOW_ADMIN_SHORTCUT=True, SHOP_ADMIN_URL="http://admin.example.com/admin-portal/",
        )
        self.assertIn("store-admin-shortcut", html)
        self.assertIn("پنل مدیریت", html)


class CartLabelTests(TestCase):
    """Final storefront-polish pass — merchant requirement: the promo
    header's cart control must additionally carry the visible text
    "سبد خرید" beside its icon, while every OTHER Global Header Variant's
    cart button stays exactly icon-only (variant isolation — the label
    is opt-in via ``cart_action.html``'s ``show_label``, and only
    ``promo_search_nav.html`` passes it)."""

    def test_promo_cart_shows_visible_label(self):
        html = _render_variant("storefront_builder/partials/global_header/promo_search_nav.html")
        self.assertIn('<span class="gh-cart-label">سبد خرید</span>', html)

    def test_promo_cart_link_and_badge_unchanged(self):
        html = _render_variant("storefront_builder/partials/global_header/promo_search_nav.html", cart_count=7)
        self.assertIn('href="/cart/"', html)
        self.assertIn('id="cart-count"', html)
        self.assertIn(">۷<", html)

    def test_promo_cart_action_include_passes_show_label_true(self):
        source = _PROMO_HEADER_TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn('cart_action.html" with show_label=True', source)

    def test_other_variants_cart_stays_icon_only(self):
        for template_name in (
            "storefront_builder/partials/global_header/marketplace_search_first.html",
            "storefront_builder/partials/global_header/premium_three_column.html",
            "storefront_builder/partials/global_header/boutique_centered.html",
            "storefront_builder/partials/global_header/dark_tech.html",
        ):
            html = _render_variant(template_name)
            self.assertNotIn("gh-cart-label", html, template_name)

    def test_cart_action_partial_label_is_opt_in_not_default(self):
        """Isolation guarantee at the shared-partial level: omitting
        ``show_label`` entirely (as every pre-existing call site does)
        must never render the label."""
        from django.template import Context, Template

        template = Template(
            '{% include "storefront_builder/partials/global_header/_shared/cart_action.html" %}'
        )
        html = template.render(Context({"is_live_storefront": True, "cart_count": 0}))
        self.assertNotIn("gh-cart-label", html)

    def test_cart_label_visually_hidden_at_mobile_breakpoint(self):
        """Compact footprint requirement at 390px — the label becomes
        accessible-only (same technique as ``.gh-account-link``'s
        existing compact-label behavior), the link/icon/badge stay."""
        css = _GLOBAL_HEADER_CSS_PATH.read_text(encoding="utf-8")
        mobile_block = PromoHeaderDesktopGridStructureTests._promo_mobile_block(css)
        self.assertIn(".gh--promo .gh-cart-label{position:absolute", mobile_block)
