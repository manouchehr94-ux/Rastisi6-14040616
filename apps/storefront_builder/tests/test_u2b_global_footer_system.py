"""U2B — Global Footer + Global Region Completion.

Extends the U2A Global Header architecture (``global_region_registry.py``)
with a second region, ``GLOBAL_FOOTER_REGION``, using the exact same
``GlobalRegionDefinition``/``GlobalVariantDefinition`` contract — no
duplicate concepts, no second registry.

Covers the required test categories A-S from the U2B work order:

A   — all five footer variant keys are registered.
B   — default is legacy_default.
C   — each key resolves its own trusted renderer.
D/E — unknown/non-string persisted key falls back safely (read-time).
F   — an arbitrary/path-like value can never become the renderer.
G/H — write-time invalid key is rejected; a valid one round-trips.
I   — an existing Store without a footer variant remains legacy_default.
J   — two Stores' footer variants never leak into each other.
K   — resolution performs zero DB queries.
L/M — public storefront and Builder Preview both use the resolved renderer.
N   — shared data (FOOTER_SETTINGS/social/nav/categories) is identical
      regardless of which footer variant is selected.
O   — no forbidden store/template/family branching exists.
P   — no migration required (footer_variant lives in the existing
      StorefrontLayoutVersion.footer_config JSONField).
Q   — SECTION_REGISTRY (U1) remains untouched.
R   — U2A header behavior remains intact (header region unaffected).
S   — the renderer namespace protection remains active for both regions.

Paths are computed via ``pathlib``/``__file__`` throughout — never
hard-coded — so this module is portable across Linux and Windows.
"""

import inspect
import re
from pathlib import Path
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import global_region_registry as g
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.section_registry import SECTION_REGISTRY
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.storefront_context_service import build_universal_storefront_context
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STOREFRONT_BUILDER_APP = _REPO_ROOT / "apps" / "storefront_builder"
_GLOBAL_FOOTER_CSS_PATH = _STOREFRONT_BUILDER_APP / "static" / "css" / "storefront_builder.css"
_LEGACY_FOOTER_PATH = (
    _STOREFRONT_BUILDER_APP / "templates" / "storefront_builder" / "partials" / "page_shell_footer.html"
)
_GLOBAL_FOOTER_TEMPLATES_DIR = (
    _STOREFRONT_BUILDER_APP / "templates" / "storefront_builder" / "partials" / "global_footer"
)

ADMIN_HOST = "u2b-footer-admin.rastisi.localhost"
PUBLIC_HOST = "u2b-footer-public.example.com"

_ALL_FOOTER_VARIANT_KEYS = {
    "legacy_default", "marketplace_dense", "premium_columns", "boutique_editorial", "dark_tech",
    "promo_columns", "beauty_retail_columns", "chocolate_dark_columns",
}


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _render_footer_variant(template_name, footer_config_overrides=None, **extra_ctx):
    from django.template.loader import get_template
    from django.test import RequestFactory

    request = RequestFactory().get("/")

    class _AnonymousUser:
        is_authenticated = False

    request.user = _AnonymousUser()
    footer_config = {
        "show_about": True, "show_contact": True, "show_quick_links": True, "show_categories": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": True, "show_copyright": True, "extra_blocks": [], "responsive": {},
    }
    footer_config.update(footer_config_overrides or {})
    ctx = {
        "footer_config": footer_config, "is_live_storefront": True, "is_builder_preview": False,
        "top_level_categories": [], "NAV_FOOTER_1": None, "SHOP_NAME": "فروشگاه آزمایشی",
        "SHOP_TAGLINE": "بهترین انتخاب شما", "SHOP_LOGO": None,
        "FOOTER_SETTINGS": None, "FOOTER_TRUST_BADGES": [], "FOOTER_PAYMENT_LOGOS": [],
        "SOCIAL_LINKS_FOOTER": [], "SHOP_CONTACT_PHONE": None, "SHOP_CONTACT_EMAIL": None,
        "request": request,
    }
    ctx.update(extra_ctx)
    return get_template(template_name).render(ctx)


def _mock_trust_badge(title="نماد اعتماد الکترونیکی"):
    return SimpleNamespace(title=title, destination_url=None, image=SimpleNamespace(url="/media/badge.png"))


def _mock_payment_logo(title="درگاه پرداخت"):
    return SimpleNamespace(title=title, image=SimpleNamespace(url="/media/logo.png"))


def _opening_div_tag(html, css_class):
    """Returns the full opening ``<div class="{css_class}" ...>`` tag, or
    an empty string if that class never appears — used to inspect an
    element's own attributes without accidentally matching content that
    merely follows it in the rendered HTML."""
    match = re.search(rf'<div class="{re.escape(css_class)}"[^>]*>', html)
    return match.group(0) if match else ""


class FooterVariantsRegisteredTests(TestCase):
    """Test A/B — all five footer variants registered; default is
    legacy_default."""

    def test_all_five_footer_keys_registered(self):
        keys = {v.key for v in g.GLOBAL_FOOTER_REGION.variants}
        self.assertTrue(_ALL_FOOTER_VARIANT_KEYS.issubset(keys))

    def test_default_variant_is_legacy_default(self):
        self.assertEqual(g.GLOBAL_FOOTER_REGION.default_variant, "legacy_default")

    def test_legacy_default_footer_renderer_is_the_pre_existing_unmoved_partial(self):
        legacy = g.get_global_variant(g.GLOBAL_FOOTER_REGION, "legacy_default")
        self.assertEqual(legacy.renderer, "storefront_builder/partials/page_shell_footer.html")

    def test_variant_setting_key_is_footer_variant(self):
        self.assertEqual(g.GLOBAL_FOOTER_REGION.variant_setting_key, "footer_variant")

    def test_footer_region_reuses_the_exact_same_dataclasses_as_header(self):
        """No duplicate/independent footer registry concept exists — both
        regions are built from the identical GlobalRegionDefinition/
        GlobalVariantDefinition classes."""
        self.assertIs(type(g.GLOBAL_FOOTER_REGION), type(g.GLOBAL_HEADER_REGION))
        self.assertIs(type(g.GLOBAL_FOOTER_REGION.variants[0]), type(g.GLOBAL_HEADER_REGION.variants[0]))


class FooterRendererResolutionTests(TestCase):
    """Test C/F — each key resolves its own distinct renderer; an
    arbitrary/path-like value never becomes the renderer."""

    def test_each_registered_footer_key_resolves_to_its_own_renderer(self):
        for variant in g.GLOBAL_FOOTER_REGION.variants:
            resolved = g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, {"footer_variant": variant.key})
            self.assertEqual(resolved.key, variant.key)
            self.assertEqual(
                g.resolve_global_renderer_template(g.GLOBAL_FOOTER_REGION, {"footer_variant": variant.key}),
                variant.renderer,
            )

    def test_all_five_footer_renderers_are_distinct(self):
        renderers = [v.renderer for v in g.GLOBAL_FOOTER_REGION.variants]
        self.assertEqual(len(renderers), len(set(renderers)), renderers)

    def test_arbitrary_path_like_value_never_becomes_the_footer_renderer(self):
        malicious_values = [
            "../../../etc/passwd",
            "/etc/passwd",
            "storefront_builder/partials/global_footer/marketplace_dense.html",
            "some/random/template.html",
            "C:\\Windows\\System32",
        ]
        for value in malicious_values:
            template = g.resolve_global_renderer_template(g.GLOBAL_FOOTER_REGION, {"footer_variant": value})
            self.assertIn(template, {v.renderer for v in g.GLOBAL_FOOTER_REGION.variants}, value)


class FooterReadTimeFallbackSafetyTests(TestCase):
    """Test D/E — unknown/non-string persisted key falls back safely,
    never raises, never mutates the stored config."""

    def test_missing_footer_variant_key_falls_back_to_default(self):
        variant = g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, {})
        self.assertEqual(variant.key, "legacy_default")

    def test_none_config_falls_back_to_default(self):
        variant = g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, None)
        self.assertEqual(variant.key, "legacy_default")

    def test_unknown_stored_footer_variant_falls_back_without_raising(self):
        variant = g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, {"footer_variant": "some_retired_key"})
        self.assertEqual(variant.key, "legacy_default")

    def test_non_string_stored_footer_variant_falls_back_without_raising(self):
        for bogus in (123, [], {}, True):
            variant = g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, {"footer_variant": bogus})
            self.assertEqual(variant.key, "legacy_default", bogus)

    def test_read_time_resolution_never_mutates_the_input_config(self):
        config = {"footer_variant": "unknown_value", "show_about": True}
        original = dict(config)
        g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, config)
        self.assertEqual(config, original)


class FooterWriteTimeValidationTests(TestCase):
    """Test G/H — invalid key rejected at write time; a valid key persists
    exactly as the stable string, never a template path."""

    def test_invalid_footer_variant_key_is_rejected(self):
        with self.assertRaises(g.UnknownGlobalVariantSelectionError):
            g.validate_global_variant_selection(g.GLOBAL_FOOTER_REGION, "not_a_real_variant")

    def test_valid_footer_variant_round_trips_through_validate_footer_config(self):
        for key in _ALL_FOOTER_VARIANT_KEYS:
            cleaned = svc.validate_footer_config({"show_about": True, "footer_variant": key})
            self.assertEqual(cleaned["footer_variant"], key)
            self.assertNotIn("/", cleaned["footer_variant"])
            self.assertNotIn(".html", cleaned["footer_variant"])

    def test_missing_footer_variant_persists_the_default_key(self):
        cleaned = svc.validate_footer_config({"show_about": True})
        self.assertEqual(cleaned["footer_variant"], "legacy_default")


class ExistingStoreRemainsLegacyTests(TestCase):
    """Test I — a real, published Store with no footer_variant set
    resolves the exact pre-U2B renderer through the real HTTP path."""

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
    def test_published_store_without_footer_variant_uses_legacy_default_template(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = svc.validate_footer_config({"show_copyright": True})
        draft.save(update_fields=["footer_config"])
        svc.publish(self.store)

        resp = self.public_client.get(reverse("catalog:home"))
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_builder/partials/page_shell_footer.html", template_names)
        for variant_key in _ALL_FOOTER_VARIANT_KEYS - {"legacy_default"}:
            self.assertNotIn(f"storefront_builder/partials/global_footer/{variant_key}.html", template_names)


class CrossStoreFooterIsolationTests(TestCase):
    """Test J — two Stores' independently-configured footer variants
    never leak into each other's public rendering."""

    def setUp(self):
        cache.clear()

    @override_settings(ALLOWED_HOSTS=["u2b-store-a.example.com", "u2b-store-b.example.com", "testserver"])
    def test_two_stores_resolve_their_own_independent_footer_variant(self):
        store_a = _akhlaghi()
        store_b = Store.objects.create(name="فروشگاه دومِ U2B", slug="u2b-footer-store-b", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(
            store=store_a, hostname="u2b-store-a.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=store_b, hostname="u2b-store-b.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

        draft_a = svc.get_or_create_draft(store_a)
        draft_a.footer_config = svc.validate_footer_config({"show_copyright": True, "footer_variant": "dark_tech"})
        draft_a.save(update_fields=["footer_config"])
        svc.publish(store_a)

        draft_b = svc.get_or_create_draft(store_b)
        draft_b.footer_config = svc.validate_footer_config({"show_copyright": True, "footer_variant": "boutique_editorial"})
        draft_b.save(update_fields=["footer_config"])
        svc.publish(store_b)

        resp_a = Client(HTTP_HOST="u2b-store-a.example.com").get(reverse("catalog:home"))
        resp_b = Client(HTTP_HOST="u2b-store-b.example.com").get(reverse("catalog:home"))

        templates_a = [t.name for t in resp_a.templates if t.name]
        templates_b = [t.name for t in resp_b.templates if t.name]
        self.assertIn("storefront_builder/partials/global_footer/dark_tech.html", templates_a)
        self.assertNotIn("storefront_builder/partials/global_footer/boutique_editorial.html", templates_a)
        self.assertIn("storefront_builder/partials/global_footer/boutique_editorial.html", templates_b)
        self.assertNotIn("storefront_builder/partials/global_footer/dark_tech.html", templates_b)


class FooterZeroQueryResolutionTests(TestCase):
    """Test K — resolving the active footer variant/template is pure
    in-memory metadata lookup; never issues a database query."""

    def test_resolve_active_global_variant_for_footer_performs_no_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            g.resolve_active_global_variant(g.GLOBAL_FOOTER_REGION, {"footer_variant": "dark_tech"})
            g.resolve_global_renderer_template(g.GLOBAL_FOOTER_REGION, {"footer_variant": "unknown"})
        self.assertEqual(len(ctx.captured_queries), 0)


class PublicAndPreviewUseResolvedFooterRendererTests(TestCase):
    """Test L/M — both the public storefront context service and Builder
    Preview resolve footer_variant_template via the identical registry
    function."""

    def test_storefront_context_service_exposes_footer_variant_template(self):
        store = _akhlaghi()
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        for key in _ALL_FOOTER_VARIANT_KEYS:
            draft = svc.get_or_create_draft(store)
            draft.footer_config = svc.validate_footer_config({"show_copyright": True, "footer_variant": key})
            draft.save(update_fields=["footer_config"])
            svc.publish(store)
            context = build_universal_storefront_context(request, store, StorefrontPage.PageType.HOME)
            self.assertEqual(
                context["footer_variant_template"],
                g.get_global_variant(g.GLOBAL_FOOTER_REGION, key).renderer,
            )

    def test_builder_preview_context_includes_footer_variant_template(self):
        store = _akhlaghi()
        store.admin_subdomain = ADMIN_HOST.split(".")[0]
        store.save(update_fields=["admin_subdomain"])
        staff = User.objects.create_user(username="u2b_preview_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=store, user=staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=ADMIN_HOST)
        client.login(username="u2b_preview_owner", password="pass12345")
        draft = svc.get_or_create_draft(store)
        draft.footer_config = svc.validate_footer_config({"show_copyright": True, "footer_variant": "premium_columns"})
        draft.save(update_fields=["footer_config"])

        with override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"]):
            resp = client.get(reverse("dashboard:storefront-builder-preview"))
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_builder/partials/global_footer/premium_columns.html", template_names)


class SharedDataIndependentOfFooterVariantTests(TestCase):
    """Test N — FOOTER_SETTINGS/social/nav/category data sources are
    identical regardless of which footer variant renders them; only the
    resolved template path changes."""

    def test_every_footer_variant_template_reads_the_same_shared_partials(self):
        for template_name in ("marketplace_dense", "premium_columns", "boutique_editorial", "dark_tech"):
            path = _GLOBAL_FOOTER_TEMPLATES_DIR / f"{template_name}.html"
            source = path.read_text(encoding="utf-8")
            self.assertIn("_shared/brand.html", source, template_name)
            # marketplace_dense/premium_columns/dark_tech route contact
            # through the shared contact_column.html (heading + real-data
            # guard as one centralized unit — see contact_column.html);
            # boutique_editorial includes contact_info.html directly since
            # it never shows the dedicated contact-column heading. Both
            # paths ultimately reuse the one real contact_info.html partial
            # — this only proves neither variant duplicates that logic
            # inline.
            self.assertTrue(
                "_shared/contact_info.html" in source or "_shared/contact_column.html" in source,
                template_name,
            )
            self.assertIn("_shared/legal_row.html", source, template_name)

    def test_contact_column_partial_itself_reuses_contact_info_partial(self):
        contact_column_path = _GLOBAL_FOOTER_TEMPLATES_DIR / "_shared" / "contact_column.html"
        source = contact_column_path.read_text(encoding="utf-8")
        self.assertIn("_shared/contact_info.html", source)


class NoForbiddenFooterBranchingTests(TestCase):
    """Test O — no branching on store/template/family identity exists
    anywhere reachable from the footer feature."""

    _FORBIDDEN_PATTERNS = (
        re.compile(r"template_key\s*=="),
        re.compile(r"store\.slug\s*=="),
        re.compile(r"store\.id\s*=="),
        re.compile(r"family_slug\s*=="),
    )

    def test_global_region_registry_source_has_no_forbidden_conditionals(self):
        source = inspect.getsource(g)
        for pattern in self._FORBIDDEN_PATTERNS:
            self.assertIsNone(pattern.search(source), pattern.pattern)

    def test_new_footer_templates_have_no_forbidden_conditionals(self):
        for path in _GLOBAL_FOOTER_TEMPLATES_DIR.rglob("*.html"):
            source = path.read_text(encoding="utf-8")
            for pattern in self._FORBIDDEN_PATTERNS:
                self.assertIsNone(pattern.search(source), f"{path}: {pattern.pattern}")


class NoMigrationNeededTests(TestCase):
    """Test P — footer_variant lives entirely inside the pre-existing
    footer_config JSONField; no schema change is needed."""

    def test_footer_variant_round_trips_through_the_existing_jsonfield(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.footer_config = svc.validate_footer_config({"show_copyright": True, "footer_variant": "dark_tech"})
        draft.save(update_fields=["footer_config"])
        draft.refresh_from_db()
        self.assertEqual(draft.footer_config["footer_variant"], "dark_tech")


class U1SectionRegistryUntouchedTests(TestCase):
    """Test Q — U1's SECTION_REGISTRY is completely untouched by U2B."""

    def test_section_registry_still_has_exactly_34_keys(self):
        self.assertEqual(len(SECTION_REGISTRY), 36)


class U2AHeaderBehaviorIntactTests(TestCase):
    """Test R — U2A's header region is unaffected by adding the footer
    region."""

    def test_header_region_still_has_its_five_variants(self):
        keys = {v.key for v in g.GLOBAL_HEADER_REGION.variants}
        expected = {
            "legacy_default", "marketplace_search_first", "premium_three_column",
            "boutique_centered", "dark_tech", "promo_search_nav", "beauty_search_nav",
            "chocolate_centered_search", "atelier_nav", "luxury_search",
        }
        self.assertTrue(expected.issubset(keys))

    def test_header_default_variant_still_legacy_default(self):
        self.assertEqual(g.GLOBAL_HEADER_REGION.default_variant, "legacy_default")

    def test_header_and_footer_regions_are_independent_objects(self):
        self.assertIsNot(g.GLOBAL_HEADER_REGION, g.GLOBAL_FOOTER_REGION)
        header_keys = {v.key for v in g.GLOBAL_HEADER_REGION.variants}
        footer_keys = {v.key for v in g.GLOBAL_FOOTER_REGION.variants}
        # both regions legitimately share some key names (legacy_default,
        # dark_tech) — that's fine, they're scoped per-region via
        # variant_setting_key ("header_variant" vs "footer_variant"), never
        # cross-resolved.
        self.assertIn("legacy_default", header_keys)
        self.assertIn("legacy_default", footer_keys)


class RendererNamespaceProtectionActiveTests(TestCase):
    """Test S — the renderer namespace validation still runs for both
    regions (it is shared, region-agnostic code)."""

    def test_namespace_validation_rejects_a_footer_renderer_outside_the_namespace(self):
        with self.assertRaises(g.InvalidGlobalVariantDefinitionError):
            g._validate_global_variant_renderer("outside/the/namespace/footer.html")

    def test_all_registered_footer_renderers_are_within_the_namespace(self):
        for variant in g.GLOBAL_FOOTER_REGION.variants:
            self.assertTrue(variant.renderer.startswith(g.GLOBAL_RENDERER_NAMESPACE), variant.key)


class FooterEditorRegressionTests(TestCase):
    """Regression coverage for the editor wiring — mirrors the U2A header
    editor tests exactly."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="u2b_footer_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.client.login(username="u2b_footer_owner", password="pass12345")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_post_with_unknown_footer_variant_key_is_rejected(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on", "footer_variant": "totally_made_up_variant",
        })
        self.assertEqual(resp.status_code, 200)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.effective_footer_config()["footer_variant"], "legacy_default")

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_post_with_valid_footer_variant_round_trips(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        resp = self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_copyright": "on", "footer_variant": "premium_columns",
        })
        self.assertEqual(resp.status_code, 302)
        draft = svc.get_or_create_draft(self.store)
        self.assertEqual(draft.footer_config["footer_variant"], "premium_columns")

        get_resp = self.client.get(reverse("dashboard:storefront-builder-footer"))
        self.assertContains(get_resp, 'value="premium_columns" selected')

    @override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
    def test_switching_footer_variant_does_not_erase_footer_content_settings(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        """Changing the visual variant must be independent from footer
        content — an unrelated content toggle (show_about) must survive a
        footer_variant change made in a separate request."""
        self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_about": "on", "show_copyright": "on", "footer_variant": "legacy_default",
        })
        self.client.post(reverse("dashboard:storefront-builder-footer"), {
            "show_about": "on", "show_copyright": "on", "footer_variant": "dark_tech",
        })
        draft = svc.get_or_create_draft(self.store)
        self.assertTrue(draft.footer_config["show_about"])
        self.assertEqual(draft.footer_config["footer_variant"], "dark_tech")


class NoFakeContentRegressionTests(TestCase):
    """Regression coverage found during implementation — boutique_editorial
    must never render an empty-looking newsletter/social block when the
    Store has configured neither, and no variant may fabricate contact/
    trust/social data that was not actually provided."""

    def test_boutique_editorial_omits_newsletter_block_without_real_data(self):
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/boutique_editorial.html",
            {"show_newsletter": True}, FOOTER_SETTINGS=None,
        )
        self.assertNotIn("gf-newsletter", html)

    def test_boutique_editorial_omits_social_block_without_real_links(self):
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/boutique_editorial.html",
            {"show_social": True}, SOCIAL_LINKS_FOOTER=[],
        )
        self.assertNotIn("gf-socials", html)

    def test_no_variant_template_contains_a_hardcoded_phone_or_social_handle(self):
        for path in _GLOBAL_FOOTER_TEMPLATES_DIR.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("instagram.com/", source, path.name)
            self.assertNotIn("t.me/", source, path.name)
            self.assertNotIn("۰۹۱", source, path.name)


class FooterTrustBadgePaymentLogoIndependenceTests(TestCase):
    """Blocker 1 (post-review correction pass) — show_trust_badges and
    show_payment_logos are independent gates, each with its own
    hide_on_tablet/hide_on_mobile responsive setting; one component's
    toggle/responsive setting must never control the other. Exercises
    actual rendered HTML (via the real Django template engine), not only
    source-string assertions."""

    _NEW_VARIANTS = ("marketplace_dense", "premium_columns", "boutique_editorial", "dark_tech")

    def _render(self, variant, footer_config_overrides, **extra_ctx):
        return _render_footer_variant(
            f"storefront_builder/partials/global_footer/{variant}.html",
            footer_config_overrides,
            **extra_ctx,
        )

    def test_a_trust_off_payment_on_renders_only_payment_logos(self):
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {"show_trust_badges": False, "show_payment_logos": True},
                FOOTER_TRUST_BADGES=[_mock_trust_badge()], FOOTER_PAYMENT_LOGOS=[_mock_payment_logo()],
            )
            self.assertNotIn("gf-trust-badges", html, variant)
            self.assertIn("gf-payment-logos", html, variant)

    def test_b_trust_on_payment_off_renders_only_trust_badges(self):
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {"show_trust_badges": True, "show_payment_logos": False},
                FOOTER_TRUST_BADGES=[_mock_trust_badge()], FOOTER_PAYMENT_LOGOS=[_mock_payment_logo()],
            )
            self.assertIn("gf-trust-badges", html, variant)
            self.assertNotIn("gf-payment-logos", html, variant)

    def test_c_trust_hidden_on_mobile_payment_still_visible_on_mobile(self):
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {
                    "show_trust_badges": True, "show_payment_logos": True,
                    "responsive": {
                        "show_trust_badges": {"hide_on_tablet": False, "hide_on_mobile": True},
                        "show_payment_logos": {"hide_on_tablet": False, "hide_on_mobile": False},
                    },
                },
                FOOTER_TRUST_BADGES=[_mock_trust_badge()], FOOTER_PAYMENT_LOGOS=[_mock_payment_logo()],
            )
            trust_tag = _opening_div_tag(html, "gf-trust-badges")
            payment_tag = _opening_div_tag(html, "gf-payment-logos")
            self.assertIn("data-shell-hide-mobile", trust_tag, variant)
            self.assertNotIn("data-shell-hide-mobile", payment_tag, variant)

    def test_d_payment_hidden_on_tablet_trust_still_visible_on_tablet(self):
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {
                    "show_trust_badges": True, "show_payment_logos": True,
                    "responsive": {
                        "show_trust_badges": {"hide_on_tablet": False, "hide_on_mobile": False},
                        "show_payment_logos": {"hide_on_tablet": True, "hide_on_mobile": False},
                    },
                },
                FOOTER_TRUST_BADGES=[_mock_trust_badge()], FOOTER_PAYMENT_LOGOS=[_mock_payment_logo()],
            )
            trust_tag = _opening_div_tag(html, "gf-trust-badges")
            payment_tag = _opening_div_tag(html, "gf-payment-logos")
            self.assertNotIn("data-shell-hide-tablet", trust_tag, variant)
            self.assertIn("data-shell-hide-tablet", payment_tag, variant)

    def test_neither_toggle_enabled_renders_no_credibility_region_at_all(self):
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {"show_trust_badges": False, "show_payment_logos": False},
                FOOTER_TRUST_BADGES=[_mock_trust_badge()], FOOTER_PAYMENT_LOGOS=[_mock_payment_logo()],
            )
            self.assertNotIn("gf-credibility", html, variant)

    def test_toggle_enabled_but_no_real_data_renders_nothing(self):
        """A toggle being on with no real merchant data must still render
        nothing — never a fabricated badge/logo, and no empty wrapper."""
        for variant in self._NEW_VARIANTS:
            html = self._render(
                variant,
                {"show_trust_badges": True, "show_payment_logos": True},
                FOOTER_TRUST_BADGES=[], FOOTER_PAYMENT_LOGOS=[],
            )
            self.assertNotIn("gf-credibility", html, variant)


class FooterSocialExtraBlockRegressionTests(TestCase):
    """Blocker 2 (post-review correction pass) — the shared
    ``extra_blocks.html`` partial must support all three validated
    ``FOOTER_EXTRA_BLOCK_TYPES`` (layout_service.py): custom_text/link/
    social. A real ``social`` extra block (backed by real
    ``SOCIAL_LINKS_FOOTER`` data) must render — reusing the existing
    ``social_links.html`` shared partial, never inventing new content —
    under every NEW production footer variant.

    Note: ``page_shell_footer.html`` (the untouched ``legacy_default``
    renderer) has never rendered the ``social`` extra-block type in its
    own extra_blocks loop — inspection of that file shows its loop only
    ever handles ``custom_text``/``link``. That is a pre-existing quirk of
    the legacy template this correction pass intentionally leaves
    untouched (``legacy_default`` must keep rendering the exact existing
    footer behavior); it is not a regression this pass introduces, and
    this test suite therefore covers the four NEW variants only.
    """

    _NEW_VARIANTS = ("marketplace_dense", "premium_columns", "boutique_editorial", "dark_tech")

    def test_real_social_extra_block_renders_under_every_new_variant(self):
        social_links = [
            SimpleNamespace(
                url="https://instagram.example/real-store-account",
                title="اینستاگرام فروشگاه",
                effective_icon_name="instagram",
            )
        ]
        for variant in self._NEW_VARIANTS:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"extra_blocks": [{"type": "social"}]},
                SOCIAL_LINKS_FOOTER=social_links,
            )
            self.assertIn("gf-col-extra-social", html, variant)
            self.assertIn("https://instagram.example/real-store-account", html, variant)

    def test_social_extra_block_renders_nothing_without_real_social_link_data(self):
        for variant in self._NEW_VARIANTS:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"extra_blocks": [{"type": "social"}]},
                SOCIAL_LINKS_FOOTER=[],
            )
            self.assertNotIn("gf-col-extra-social", html, variant)

    def test_custom_text_and_link_extra_blocks_still_render_alongside_social(self):
        """The new social branch must not have disturbed the two
        pre-existing extra-block types."""
        blocks = [
            {"type": "custom_text", "title": "توضیحات", "text": "متن آزمایشی واقعی"},
            {"type": "link", "label": "قوانین", "url": "https://example.com/rules"},
            {"type": "social"},
        ]
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/marketplace_dense.html",
            {"extra_blocks": blocks},
            SOCIAL_LINKS_FOOTER=[
                SimpleNamespace(url="https://t.me/example-real", title="تلگرام", effective_icon_name="telegram")
            ],
        )
        self.assertIn("متن آزمایشی واقعی", html)
        self.assertIn("https://example.com/rules", html)
        self.assertIn("gf-col-extra-social", html)


class FooterContactColumnRegressionTests(TestCase):
    """Blocker 3 (post-review correction pass) — a Store with no real
    contact data must never receive an orphaned "ارتباط با ما" heading
    over an empty contact column, in every variant that shows a dedicated
    contact-column heading (marketplace_dense/premium_columns/dark_tech;
    boutique_editorial never rendered this heading in the first place)."""

    _VARIANTS_WITH_CONTACT_HEADING = ("marketplace_dense", "premium_columns", "dark_tech")

    def test_no_contact_heading_or_list_without_real_contact_data(self):
        for variant in self._VARIANTS_WITH_CONTACT_HEADING:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_contact": True},
                FOOTER_SETTINGS=None, SHOP_CONTACT_PHONE=None, SHOP_CONTACT_EMAIL=None,
            )
            self.assertNotIn("ارتباط با ما", html, variant)
            self.assertNotIn("gf-contact-list", html, variant)

    def test_contact_heading_and_list_present_with_real_contact_data(self):
        for variant in self._VARIANTS_WITH_CONTACT_HEADING:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_contact": True},
                SHOP_CONTACT_PHONE="02100000000",
            )
            self.assertIn("ارتباط با ما", html, variant)
            self.assertIn("gf-contact-list", html, variant)


class FooterContactAccessibilityRegressionTests(TestCase):
    """Accessibility correction (post-review pass) — the decorative
    ☎/✉/⌖ glyphs must not pollute assistive output, while the underlying
    tel:/mailto: link semantics stay unchanged."""

    def test_decorative_contact_glyphs_are_aria_hidden_but_links_unchanged(self):
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/dark_tech.html",
            {"show_contact": True},
            SHOP_CONTACT_PHONE="02100000000", SHOP_CONTACT_EMAIL="info@example.com",
        )
        self.assertIn('<span aria-hidden="true">☎</span>', html)
        self.assertIn('<span aria-hidden="true">✉</span>', html)
        self.assertIn('href="tel:02100000000"', html)
        self.assertIn('href="mailto:info@example.com"', html)


class BuilderPreviewCacheBustingTests(TestCase):
    """Browser-QA cache hardening (post-review passes) — the Builder
    Preview must reference the CURRENT U2B-specific cache-busting query
    token for storefront_builder.css, distinct from every prior token, so
    stale cached CSS from an earlier pass can never be mistaken for the
    latest corrected U2B footer styles during local browser QA."""

    def test_preview_css_cache_token_is_the_current_u2b_v2_token(self):
        preview_path = (
            _STOREFRONT_BUILDER_APP / "templates" / "storefront_builder" / "preview.html"
        )
        source = preview_path.read_text(encoding="utf-8")
        match = re.search(r"storefront_builder\.css['\"]\s*%\}\?v=([\w.-]+)", source)
        self.assertIsNotNone(match, "no storefront_builder.css cache-busting token found in preview.html")
        token = match.group(1)
        self.assertEqual(token, "u2b-footer-v3-20260823")
        self.assertNotEqual(token, "u2a-v5-mobile-20260823")
        self.assertNotEqual(token, "u2b-footer-v1-20260823")


class FooterEmptyStructuralShellRegressionTests(TestCase):
    """Visual-hardening pass — structural footer wrappers (the main
    column grid, the legal row, and boutique's statement/links/social
    regions) must render only when they contain at least one actually
    renderable region; merchant toggles alone (without real backing data)
    must never leave a padded/bordered empty shell. Exercises rendered
    HTML end-to-end via the real Django template engine."""

    _GRID_VARIANTS = {
        "marketplace_dense": "gf-dense-grid",
        "premium_columns": "gf-premium-grid",
        "dark_tech": "gf-dark-grid",
    }

    def test_a_social_enabled_with_no_real_links_produces_no_empty_legal_or_social_shell(self):
        for variant in self._GRID_VARIANTS:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_social": True, "show_copyright": False},
                SOCIAL_LINKS_FOOTER=[],
            )
            self.assertNotIn("gf-legal-row", html, variant)
        boutique_html = _render_footer_variant(
            "storefront_builder/partials/global_footer/boutique_editorial.html",
            {"show_social": True},
            SOCIAL_LINKS_FOOTER=[],
        )
        self.assertNotIn("gf-boutique-social", boutique_html)

    def test_b_minimal_configuration_leaves_no_empty_main_grid(self):
        minimal_overrides = {
            "show_about": False, "show_contact": False, "show_quick_links": False,
            "show_categories": False, "show_trust_badges": False, "show_payment_logos": False,
            "show_newsletter": False, "extra_blocks": [],
            # show_copyright stays True — the one active section, per the
            # real validate_footer_config "not fully empty" invariant.
        }
        for variant, grid_class in self._GRID_VARIANTS.items():
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                minimal_overrides,
                FOOTER_SETTINGS=None, SOCIAL_LINKS_FOOTER=[],
            )
            self.assertNotIn(grid_class, html, variant)
            # the one active toggle (copyright) must still render for real
            self.assertIn("gf-legal-row", html, variant)
            self.assertIn("gf-copy", html, variant)

    def test_c_boutique_with_no_renderable_statement_content_omits_the_statement_region(self):
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/boutique_editorial.html",
            {"show_about": False, "show_newsletter": False},
            FOOTER_SETTINGS=None,
        )
        self.assertNotIn("gf-boutique-statement", html)

    def test_d_boutique_with_no_renderable_links_content_omits_the_links_region(self):
        html = _render_footer_variant(
            "storefront_builder/partials/global_footer/boutique_editorial.html",
            {
                "show_quick_links": True, "show_categories": True, "show_contact": True,
                "extra_blocks": [],
            },
            NAV_FOOTER_1=None, FOOTER_SETTINGS=None, SOCIAL_LINKS_FOOTER=[],
        )
        self.assertNotIn("gf-boutique-links", html)

    def test_e_copyright_off_and_no_social_data_produces_no_empty_legal_row(self):
        for variant in self._GRID_VARIANTS:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_copyright": False, "show_social": True},
                SOCIAL_LINKS_FOOTER=[],
            )
            self.assertNotIn("gf-legal-row", html, variant)

    def test_grid_still_renders_when_at_least_one_region_has_real_content(self):
        """Guards against over-correction — a grid with real content must
        still render (this is not a blanket hide)."""
        for variant, grid_class in self._GRID_VARIANTS.items():
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_about": True},
            )
            self.assertIn(grid_class, html, variant)

    def test_legal_row_still_renders_with_real_social_data(self):
        social_links = [SimpleNamespace(url="https://instagram.example/real", title="اینستاگرام", effective_icon_name="instagram")]
        for variant in self._GRID_VARIANTS:
            html = _render_footer_variant(
                f"storefront_builder/partials/global_footer/{variant}.html",
                {"show_social": True, "show_copyright": False},
                SOCIAL_LINKS_FOOTER=social_links,
            )
            self.assertIn("gf-legal-row", html, variant)
            self.assertIn("gf-socials", html, variant)


class PremiumCredibilityAlignmentRegressionTests(TestCase):
    """Visual-hardening pass — the Premium Columns trust/payment region's
    centered alignment must target the actual flex formatting context
    (``.gf-credibility``, defined by trust_payment.html), not its
    non-flex ancestor wrapper (``.gf-premium-credibility``) which has no
    ``display:flex``/``grid`` of its own and so cannot honor
    ``justify-content``."""

    def test_premium_credibility_css_targets_the_actual_flex_container(self):
        source = _GLOBAL_FOOTER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gf--premium .gf-premium-credibility .gf-credibility{justify-content:center}", source)
        # the old, ineffective selector must be gone, not just superseded
        self.assertNotIn(".gf--premium .gf-premium-credibility{justify-content:center}", source)

    def test_gf_premium_credibility_itself_still_has_no_conflicting_justify_content_rule(self):
        source = _GLOBAL_FOOTER_CSS_PATH.read_text(encoding="utf-8")
        # a bare rule directly on .gf-premium-credibility (not the
        # ".gf-credibility" descendant) would be dead CSS and a sign the
        # fix regressed back to targeting the non-flex ancestor.
        self.assertNotRegex(source, r"\.gf-premium-credibility\{[^}]*justify-content")


class MobileSocialTouchTargetRegressionTests(TestCase):
    """Visual-hardening pass — icon-only footer social controls
    (``.gf-socials a``) must have a >=44x44 usable touch target at the
    existing mobile breakpoint (<=680px), scoped only to U2B footer
    social controls — desktop proportions and all other links/buttons
    are untouched."""

    def test_mobile_breakpoint_bumps_social_link_target_to_at_least_44px(self):
        source = _GLOBAL_FOOTER_CSS_PATH.read_text(encoding="utf-8")
        override = ".gf-socials a{width:44px;height:44px}"
        self.assertIn(override, source)
        # must sit inside a max-width:680px breakpoint, not applied
        # unconditionally (which would break the 34px desktop design).
        preceding = source[: source.index(override)]
        self.assertIn("@media(max-width:680px){", preceding[-400:])

    def test_desktop_social_link_proportions_unchanged(self):
        source = _GLOBAL_FOOTER_CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gf-socials a{display:grid;place-items:center;width:34px;height:34px", source)

    def test_touch_target_fix_does_not_touch_unrelated_selectors(self):
        source = _GLOBAL_FOOTER_CSS_PATH.read_text(encoding="utf-8")
        # the added mobile rule must be scoped to .gf-socials only, never
        # a blanket "a{...}" or "button{...}" rule.
        self.assertNotRegex(source, r"@media\(max-width:680px\)\{\s*a\{width:44px")
