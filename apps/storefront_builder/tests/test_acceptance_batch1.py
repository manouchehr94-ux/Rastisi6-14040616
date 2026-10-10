"""Acceptance Batch 1 (post-U11) — «Ready Template Integrity + Public
Presentation».

Real Windows/browser QA against the completed U3-U11 Universal Storefront
Engine surfaced four small acceptance gaps. Issue 1 (a Ready Template's
default palette not becoming the new baseline on apply) is fixed and
tested in ``test_preset_service.py`` (``PaletteSeparationTests``) — this
file covers the remaining three:

* Issue 2 — a real CSS specificity bug in the shared U2A/U2B header/footer
  stylesheet made nav/header links inherit the wrong semantic color role
  for any palette defining independent header/nav roles (confirmed via
  real QA against the ``theme-forest-cream`` full-site-theme).
* Issue 3 — the merchant-facing Ready Template Gallery must show only the
  8 official U10 recipes, not the 5 historical/internal presets kept for
  Advanced-mode use, via a registry-level ``is_ready_template`` flag.
* Issue 4 — an optional, data-driven commerce section (best sellers,
  discounted products, amazing offers, a generic product_section, related
  products) that resolves to zero products must not render its shell,
  heading, or merchant-facing empty-state on the public/live storefront —
  while the same section keeps that explanatory empty-state in the
  Builder/editor so a merchant understands why a section looks empty
  while composing a page.
"""

from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-batch1.rastisi.localhost"
PUBLIC_HOST = "sfb-batch1.example.com"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CSS_PATH = _REPO_ROOT / "apps" / "storefront_builder" / "static" / "css" / "storefront_builder.css"

HISTORICAL_KEYS = ("clean_minimal", "editorial_story", "dense_catalog", "premium_boutique", "v5_golden_homepage")
READY_TEMPLATE_KEYS = (
    "dense_marketplace", "premium_leather", "warm_boutique", "fashion_promo_catalog",
    "playful_lifestyle", "utility_catalog", "editorial_jewelry", "dark_digital",
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="sfb-batch1-store-b", defaults=dict(name="فروشگاه دوم Batch 1", status=Store.Status.ACTIVE),
    )
    return store


class HeaderNavContrastSpecificityTests(TestCase):
    """Issue 2 — ``.gh a,.gh button{color:inherit}`` (specificity 0,1,1, a
    class + element-type selector) out-ranked the single-class semantic
    color tokens (``.gh-nl``/``.gh-btn``/``.gh-account-link``, each
    0,1,0), so real nav/header links inherited the ancestor ``<header>``'s
    ``--theme-header-text`` (paired with ``header_bg``) while actually
    sitting on ``--gh-surface`` (paired with ``--gh-ink``/``colors.text``)
    — two different semantic pairings that only coincide for a palette
    with no independent header/nav role overrides. Confirmed via real QA
    against ``theme-forest-cream`` (cream ``header_text`` on a near-white
    ``surface`` — nearly invisible). The defect is palette-architecture-
    level, not Template-specific, so it is fixed centrally. Official Ready
    Templates may therefore safely opt into reusable full-site palette roles;
    the acceptance invariant below is the actual foreground/background
    contrast they resolve to, not the historical absence of ``theme_roles``."""

    def test_the_broken_specificity_selector_is_gone(self):
        """The old selector is still named, on purpose, inside the fix's own
        explanatory comment above it — so strip CSS comments before
        asserting it is gone as an actual *rule*."""
        import re

        css = re.sub(r"/\*.*?\*/", "", _CSS_PATH.read_text(encoding="utf-8"), flags=re.DOTALL)
        self.assertNotIn(".gh a,.gh button{color:inherit}", css)

    def test_the_zero_specificity_where_fallback_is_present(self):
        css = _CSS_PATH.read_text(encoding="utf-8")
        self.assertIn(".gh :where(a,button){color:inherit}", css)

    def test_component_color_tokens_are_unchanged_by_the_fix(self):
        css = _CSS_PATH.read_text(encoding="utf-8")
        for selector in (".gh-nl{", ".gh-btn{", ".gh-account-link{"):
            self.assertIn(selector, css)

    def test_official_ready_template_region_roles_are_contrast_safe(self):
        """Ready Templates may now intentionally use full-site palette roles.

        The original regression was caused by a CSS specificity bug that made
        header/nav controls inherit a *different* semantic text color from the
        surface they actually sat on.  The central ``:where(a,button)`` fix
        above removes that coupling, so forbidding ``theme_roles`` entirely is
        both stale and weaker than checking the real invariant.  Every official
        Ready Template must resolve accessible header/nav/footer foreground ↔
        background pairs regardless of whether those roles are derived from the
        eight base colors or explicitly curated by its reusable palette.
        """
        from apps.core.color_utils import contrast_ratio
        from apps.storefront_builder import appearance_registry

        for key in READY_TEMPLATE_KEYS:
            preset = lpr.get_layout_preset(key)
            palette = appearance_registry.get_palette(preset.default_palette_slug)
            self.assertIsNotNone(palette, key)
            roles = appearance_registry.resolve_theme_roles({
                **preset.appearance,
                "palette_slug": preset.default_palette_slug,
            })
            self.assertEqual(set(roles), set(appearance_registry.THEME_ROLE_KEYS), key)
            for foreground, background in (
                ("header_text", "header_bg"),
                ("nav_text", "nav_bg"),
                ("footer_text", "footer_bg"),
            ):
                self.assertGreaterEqual(
                    contrast_ratio(roles[foreground], roles[background]),
                    4.5,
                    f"{key}: {foreground} on {background}",
                )


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class ReadyTemplateGallerySeparationTests(TestCase):
    """Issue 3 — Tests A-F."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="batch1_gallery_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="batch1_gallery_owner", password="pass12345")
        self.url = reverse("dashboard:storefront-builder-templates")

    def test_a_gallery_keeps_the_original_eight_in_the_fifty_template_catalog(self):
        """Checked via ``response.context`` (the exact set of preset keys
        rendered as cards), not by scanning the page for a historical
        preset's Persian label text — a couple of the 8 official
        templates' own descriptions happen to share words with historical
        labels (e.g. ``editorial_jewelry``'s description contains
        "روایت‌محور", also ``editorial_story``'s label), which would make a
        naive text-absence check false-fail without indicating any real
        separation bug."""
        self.assertEqual(len(lpr.list_ready_templates()), 53)
        self.assertTrue(set(READY_TEMPLATE_KEYS).issubset({p.key for p in lpr.list_ready_templates()}))
        response = self.admin_client.get(self.url)
        cards = response.context["template_cards"]
        self.assertEqual(len(cards), 53)
        self.assertTrue(set(READY_TEMPLATE_KEYS).issubset({c["preset"].key for c in cards}))
        for key in READY_TEMPLATE_KEYS:
            self.assertContains(response, lpr.get_layout_preset(key).label_fa)

    def test_b_historical_presets_remain_registered_and_directly_applicable(self):
        self.assertEqual(len(lpr.list_layout_presets()), 58)
        for key in HISTORICAL_KEYS:
            preset = lpr.get_layout_preset(key)
            self.assertIsNotNone(preset, key)
            self.assertFalse(preset.is_ready_template, key)
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dense_catalog"))
        draft.refresh_from_db()
        self.assertEqual(draft.template_provenance.get("template", {}).get("key"), "dense_catalog")

    def test_c_selected_ready_template_is_marked_current_not_as_an_apply_action(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dark_digital"))
        response = self.admin_client.get(self.url)
        cards = {c["preset"].key: c for c in response.context["template_cards"]}
        self.assertTrue(cards["dark_digital"]["is_current"])
        for key in READY_TEMPLATE_KEYS:
            if key != "dark_digital":
                self.assertFalse(cards[key]["is_current"], key)
        self.assertContains(response, "قالبِ فعلی")
        self.assertContains(response, "در حال استفاده")
        # the current card must never carry the "apply" form/action for its
        # own preset — no hidden preset_key input for dark_digital at all.
        self.assertNotContains(response, 'name="preset_key" value="dark_digital"')

    def test_d_a_different_ready_template_remains_applicable_from_the_gallery(self):
        draft = svc.get_or_create_draft(self.store)
        preset_service.apply_preset(draft, lpr.get_layout_preset("dark_digital"))
        response = self.admin_client.get(self.url)
        self.assertContains(response, 'name="preset_key" value="warm_boutique"')

    def test_e_no_cross_store_current_template_leakage(self):
        other_store = _second_store()
        other_draft = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(other_draft, lpr.get_layout_preset("dark_digital"))

        response = self.admin_client.get(self.url)
        cards = {c["preset"].key: c for c in response.context["template_cards"]}
        self.assertFalse(cards["dark_digital"]["is_current"])
        self.assertNotContains(response, "قالبِ فعلی")

    def test_f_ready_template_keys_are_not_reference_store_or_family_names(self):
        for key in READY_TEMPLATE_KEYS:
            self.assertNotIn(" ", key)
            self.assertEqual(key, key.lower())


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class EmptyDataDrivenSectionsHiddenOnPublicTests(TestCase):
    """Issue 4 — Tests A-E."""

    EMPTY_STATE_TEXT = "فعلاً کالایی برای نمایش وجود ندارد."

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(username="batch1_empty_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="batch1_empty_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)
        self.draft = svc.get_or_create_draft(self.store)
        # dense_marketplace's home page includes a "best_sellers"-sourced
        # product_section ("پرفروش‌ترین‌ها") plus discounted_products and
        # amazing_offers — all genuinely empty for a fresh store with no
        # products yet.
        preset_service.apply_preset(
            self.draft, lpr.get_layout_preset_version("dense_marketplace", "2")
        )

    def _make_discounted_product(self):
        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده Batch1", slug="v-batch1")
        category = Category.objects.create(store=self.store, name="دسته Batch1", slug="c-batch1")
        return Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای تخفیف‌دار Batch1",
            slug="batch1-discounted-product", sku="SKU-BATCH1-DISC", price=Decimal("100000"),
            discount_percent=20, status=Product.Status.ACTIVE,
        )

    def test_a_empty_data_driven_sections_are_hidden_on_public_home(self):
        svc.publish(self.store)
        response = self.public_client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.EMPTY_STATE_TEXT)
        self.assertNotContains(response, "پرفروش‌ترین‌ها")

    def test_b_same_empty_sections_still_show_explanatory_empty_state_in_builder(self):
        response = self.admin_client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.EMPTY_STATE_TEXT)
        self.assertContains(response, "پرفروش‌ترین‌ها")

    def test_c_non_empty_discounted_products_section_renders_normally_on_public_home(self):
        self._make_discounted_product()
        svc.publish(self.store)
        response = self.public_client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کالای تخفیف‌دار Batch1")
        self.assertNotContains(response, self.EMPTY_STATE_TEXT)

    def test_d_no_blank_wrapper_remains_for_a_hidden_section(self):
        svc.publish(self.store)
        response = self.public_client.get(reverse("catalog:home"))
        content = response.content.decode()
        best_sellers_section = next(
            s for s in self.draft.get_page("home").sections.all() if s.settings.get("data_source") == "best_sellers"
        )
        self.assertNotIn(f'data-section-key="{best_sellers_section.section_key}"', content)

    def test_e_tenant_and_store_scoping_are_intact(self):
        """A second store's non-empty discounted product must never leak
        into this store's public rendering, and vice versa (the section
        must still be correctly hidden for THIS store)."""
        other_store = _second_store()
        StoreDomain.objects.create(
            store=other_store, hostname="sfb-batch1-store-b.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        other_draft = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(
            other_draft, lpr.get_layout_preset_version("dense_marketplace", "2")
        )
        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=other_store, name="فروشنده استور دوم", slug="v-batch1-b")
        category = Category.objects.create(store=other_store, name="دسته استور دوم", slug="c-batch1-b")
        Product.objects.create(
            store=other_store, vendor=vendor, category=category, name="کالای فروشگاهِ دوم",
            slug="store-b-discounted-product", sku="SKU-BATCH1-B-DISC", price=Decimal("50000"),
            discount_percent=15, status=Product.Status.ACTIVE,
        )
        svc.publish(other_store)
        svc.publish(self.store)

        own_response = self.public_client.get(reverse("catalog:home"))
        self.assertNotContains(own_response, "کالای فروشگاهِ دوم")
        self.assertNotContains(own_response, self.EMPTY_STATE_TEXT)
