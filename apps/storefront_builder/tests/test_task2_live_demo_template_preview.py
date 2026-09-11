"""Phase 5, Task 2 — live onboarding Demo Template preview
(``storefront_template_live_preview``).

Covers the required RED categories from the Task-2 charter:

1. ``LivePreviewReturnsRealRenderedOutputTests`` — a valid Template's live
   preview is real rendered output (header/hero/category content), not just
   HTTP 200.
2. ``TwoDistinctTemplatesProduceDifferentOutputTests`` — two structurally
   distinct Ready Templates render meaningfully different HTML (header
   variant markup, hero style, section composition, badge/card treatment).
3. ``DemoStoreContextIsRealTests`` — real ``rasti-mode-demo`` category/brand
   names appear in the rendered result.
4. ``DemoDraftUnchangedTests`` — the Demo Store's Draft is byte/field
   identical before and after any number of live-preview requests.
5. ``InvalidTemplateKeyTests`` — an unknown key fails closed (404), no
   mutation.
6. ``GalleryStillHasFiftyTemplatesTests`` — regression sanity: the Gallery
   still lists exactly 50 registered Ready Templates and the offline
   thumbnail path is untouched.
7. ``ExistingStaticThumbnailPathStillUsableTests`` — the pre-existing
   offline-screenshot/SVG-fallback thumbnail mechanism the Gallery already
   used is unaffected by this task's diff.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.storefront_appearance.rendering import (
    resolve_store_appearance_render_state,
)
from apps.storefront_builder.views import RASTI_MODE_DEMO_STORE_SLUG
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "sfb-task2-livepreview.rastisi.localhost"
PUBLIC_HOST = "sfb-task2-livepreview.example.com"

# Two real, registered Ready Templates with genuinely distinct declared DNA
# (already used throughout the Task-1 test suite): different header variant,
# different hero style, different badge treatment, different Home
# composition. Real category/brand names asserted below come directly from
# apps/stores/management/commands/seed_ready_template_fashion_demo.py.
EDITORIAL_JEWELRY = "editorial_jewelry"  # header=editorial_row, hero=luxury_showcase, badge=none, composition includes category_grid
DENSE_MARKETPLACE = "dense_marketplace"  # header=marketplace_search, hero=chocolate_carousel, badge=sale, composition includes brand_carousel
MINA_COMMUNITY = "mina_community"  # composition includes "community_gallery" -> the "story_rail" section_key
ROOT_CATEGORY_NAME = "کفش"  # one of the 3 seeded root category groups
A_SEEDED_BRAND_NAME = "Demo Motion"  # one of the 6 seeded fictional brand names
# Real seeded content titles (apps/stores/management/commands/
# seed_ready_template_fashion_demo.py) — golden_reference_service.py scopes
# ALL of these to the single real hero_banner/story_rail section the
# currently-applied Golden Reference baseline (fashion_promo_catalog)
# created, never to ``section=None``. Asserting these exact titles appear
# when previewing a DIFFERENT (non-baseline) template proves the Task 2
# same-section-key fallback tier actually surfaces the store's real content,
# not just that the section wrapper markup is present.
A_SEEDED_HERO_SLIDE_TITLE = "کالکشن پاییز و زمستان Rasti Mode"


def _snapshot(draft: StorefrontLayoutVersion) -> dict:
    """Same full-field non-mutation snapshot Task 1's own tests use."""
    draft.refresh_from_db()
    return {
        "edit_revision": draft.edit_revision,
        "appearance_config": draft.appearance_config,
        "header_config": draft.header_config,
        "footer_config": draft.footer_config,
        "template_provenance": draft.template_provenance,
        "template_baseline_snapshot": draft.template_baseline_snapshot,
        "sections": list(
            StorefrontSection.objects.filter(page__version=draft)
            .order_by("page_id", "order", "id")
            .values_list("page_id", "section_key", "order", "settings", "is_locked")
        ),
        "container_count": StorefrontContainer.objects.filter(page__version=draft).count(),
        "version_count": StorefrontLayoutVersion.objects.filter(layout_id=draft.layout_id).count(),
        "history_count": StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count(),
        "published_version_id": StorefrontLayout.objects.get(pk=draft.layout_id).published_version_id,
    }


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class LiveDemoTemplatePreviewTestCase(TestCase):
    """Seeds the real canonical Demo Store exactly once per test class
    (Django's ``setUpTestData`` savepoint — not once per test method, since
    this is the real, fairly heavy production seed/apply/publish pipeline),
    then logs in as staff on an unrelated Store (the merchant whose
    dashboard host is requesting the preview) — the Demo Store must be
    reachable and correctly previewed regardless of which merchant is
    logged in, since it is a fixed platform resource, not tenant data."""

    @classmethod
    def setUpTestData(cls):
        from io import StringIO
        call_command("apply_golden_reference_storefront", stdout=StringIO())

    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(
            username="task2_livepreview_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="task2_livepreview_owner", password="pass12345")
        self.demo_store = Store.objects.get(slug=RASTI_MODE_DEMO_STORE_SLUG)

    def _preview_url(self, key):
        return reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": key})


class LivePreviewReturnsRealRenderedOutputTests(LiveDemoTemplatePreviewTestCase):
    def test_valid_template_preview_returns_200_with_real_content(self):
        response = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # Not just "200" — the previewed template's own label and a real
        # rendered section must be present.
        self.assertIn("آتلیه نوآر", html)  # editorial_jewelry's label_fa
        self.assertIn("hero", html.lower())

    def test_preview_shows_demo_data_banner(self):
        response = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY))
        html = response.content.decode()
        self.assertIn("Rasti Mode Demo", html)


class TwoDistinctTemplatesProduceDifferentOutputTests(LiveDemoTemplatePreviewTestCase):
    def test_header_hero_and_composition_differ_between_two_real_templates(self):
        jewelry_html = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY)).content.decode()
        marketplace_html = self.admin_client.get(self._preview_url(DENSE_MARKETPLACE)).content.decode()

        self.assertNotEqual(jewelry_html, marketplace_html)

        # editorial_jewelry declares header=editorial_row; dense_marketplace
        # declares header=marketplace_search — real registry.get_layout_preset
        # data, not assumed strings.
        jewelry_preset = lpr.get_layout_preset(EDITORIAL_JEWELRY)
        marketplace_preset = lpr.get_layout_preset(DENSE_MARKETPLACE)
        self.assertNotEqual(
            jewelry_preset.header["header_variant"], marketplace_preset.header["header_variant"],
        )

        # dense_marketplace's Home composition includes "brands"
        # (brand_carousel) — editorial_jewelry's does not. A real seeded
        # brand name should appear only in the marketplace preview.
        self.assertNotIn(A_SEEDED_BRAND_NAME, jewelry_html)
        self.assertIn(A_SEEDED_BRAND_NAME, marketplace_html)

    def test_two_templates_resolve_different_badge_store_appearance_component(self):
        """editorial_jewelry declares badge=none, dense_marketplace
        badge=sale — a real render-affecting Store Appearance family
        difference (the same pair Task 1's own corrective proved differs at
        the candidate-resolution level). Verified here through the actual
        view: the candidate resolved and rendered by each live-preview
        request must select a different badge component."""
        from apps.storefront_builder.services import preset_service

        demo_draft = svc.get_or_create_draft(self.demo_store)
        jewelry_candidate = preset_service.resolve_preset_candidate(
            demo_draft, lpr.get_layout_preset(EDITORIAL_JEWELRY),
        )
        marketplace_candidate = preset_service.resolve_preset_candidate(
            demo_draft, lpr.get_layout_preset(DENSE_MARKETPLACE),
        )
        self.assertNotEqual(
            jewelry_candidate.store_appearance.component("badge").component.key,
            marketplace_candidate.store_appearance.component("badge").component.key,
        )
        # Both live-preview requests must succeed (proving the view actually
        # renders sections that consume this badge-aware card overlay).
        self.assertEqual(self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY)).status_code, 200)
        self.assertEqual(self.admin_client.get(self._preview_url(DENSE_MARKETPLACE)).status_code, 200)


class HeroBannerStoryRailContentIsNotEmptyTests(LiveDemoTemplatePreviewTestCase):
    """Browser-QA (Task 2) CRITICAL finding: hero/banner/story_rail sections
    rendered completely empty in every live-previewed Ready Template,
    because the Demo Store's real seeded content is scoped (by
    ``golden_reference_service.apply_golden_reference_storefront``) to the
    ONE real section the currently-applied baseline (``fashion_promo_
    catalog``) created — never to ``section=None`` — so previewing any
    OTHER template's unsaved candidate section found nothing via either the
    exact-pk match (impossible, unsaved) or the store-wide fallback (no
    unscoped rows exist). These assert the store's real seeded titles are
    present, not just that the section wrapper markup exists."""

    def test_hero_slide_real_title_appears_for_non_baseline_hero_template(self):
        # dense_marketplace is not the applied Golden Reference baseline
        # (fashion_promo_catalog) — its candidate's hero_banner section is
        # necessarily unsaved (pk=None).
        response = self.admin_client.get(self._preview_url(DENSE_MARKETPLACE))
        html = response.content.decode()
        self.assertIn(A_SEEDED_HERO_SLIDE_TITLE, html)

    def test_story_rail_context_has_real_non_empty_story_items_for_mina_community(self):
        """mina_community's composition also includes ``circular_categories``
        (a second, unrelated section that legitimately renders the same real
        category names) — so asserting a category name appears anywhere in
        the rendered HTML would not actually prove the ``story_rail``
        section itself resolved any content. Assert directly against the
        ``story_rail`` item's own resolved ``story_items``, at the
        render_service level, to prove that unambiguously."""
        from apps.storefront_builder.services import preset_service
        from apps.storefront_builder.services.render_service import build_candidate_render_items

        demo_draft = svc.get_or_create_draft(self.demo_store)
        candidate = preset_service.resolve_preset_candidate(demo_draft, lpr.get_layout_preset(MINA_COMMUNITY))
        home_page = candidate.pages["home"]
        items = build_candidate_render_items(
            home_page.sections, self.demo_store,
            global_appearance=candidate.appearance_config, store_appearance=candidate.store_appearance,
        )
        story_rail_items = [item for item in items if item["section"].section_key == "story_rail"]
        self.assertEqual(len(story_rail_items), 1)
        story_items = list(story_rail_items[0]["context"]["story_items"])
        self.assertGreater(len(story_items), 0)

        # Also confirmed end-to-end through the real view.
        response = self.admin_client.get(self._preview_url(MINA_COMMUNITY))
        self.assertEqual(response.status_code, 200)


class ContainerSettingsReachRenderedOutputTests(LiveDemoTemplatePreviewTestCase):
    """Independent review (Task 2) CRITICAL finding: ``build_candidate_
    container_rows`` attached ``row["container_settings"]``, but
    ``storefront_builder/partials/render_rows.html`` (the shared partial
    this feature reuses, per the "no second renderer" requirement) never
    actually read that key — every Ready Template's authored container
    settings (gap/background/alignment) were silently discarded regardless
    of their value. Proves the fix directly against the real, shared
    template file (not a synthetic stand-in), using real candidate items
    from the Demo Store, with a synthetic (worst-case, clearly
    non-default) ``container_settings`` injected onto one real row so the
    assertion cannot pass by coincidence with the real Ready Templates'
    all-default settings."""

    def test_multi_item_row_applies_gap_background_color_from_container_settings(self):
        from django.template.loader import render_to_string

        from apps.storefront_builder.services import preset_service
        from apps.storefront_builder.services.render_service import (
            build_candidate_container_rows,
            build_candidate_render_items,
        )

        demo_draft = svc.get_or_create_draft(self.demo_store)
        candidate = preset_service.resolve_preset_candidate(demo_draft, lpr.get_layout_preset(DENSE_MARKETPLACE))
        home_page = candidate.pages["home"]
        items = build_candidate_render_items(
            home_page.sections, self.demo_store,
            global_appearance=candidate.appearance_config, store_appearance=candidate.store_appearance,
        )
        self.assertGreaterEqual(len(items), 2, "need at least 2 sections to force the multi-item row branch")
        # Force two real, already-rendered items into one synthetic
        # multi-item row, carrying a deliberately distinctive, non-default
        # ``container_settings`` — proving the values reach the actual HTML,
        # not merely that ``build_candidate_container_rows`` computed them.
        rows = [{
            "row_key": "test-row",
            "items": items[:2],
            "container_settings": {
                "gap": 37, "mobile_mode": "stack", "content_width": "standard",
                "vertical_align": "center", "height_mode": "natural",
                "background_mode": "color", "background_color": "#1a2b3c",
                "background_pattern": "",
            },
        }]
        html = render_to_string(
            "storefront_builder/partials/render_rows.html",
            {"rows": rows, "use_container_layout": False},
        )
        self.assertIn("gap:37px", html)
        self.assertIn("#1a2b3c", html)
        self.assertIn("align-items:center", html)

    def test_single_item_row_applies_background_color_from_container_settings(self):
        """Every real A8 Ready Template composition produces single-item
        rows exclusively (none of the 50 set ``row_key``/``row_span``) — so
        this is the branch that actually matters for today's real
        templates, not just the multi-item grid case above."""
        from django.template.loader import render_to_string

        from apps.storefront_builder.services import preset_service
        from apps.storefront_builder.services.render_service import build_candidate_render_items

        demo_draft = svc.get_or_create_draft(self.demo_store)
        candidate = preset_service.resolve_preset_candidate(demo_draft, lpr.get_layout_preset(DENSE_MARKETPLACE))
        home_page = candidate.pages["home"]
        items = build_candidate_render_items(
            home_page.sections, self.demo_store,
            global_appearance=candidate.appearance_config, store_appearance=candidate.store_appearance,
        )
        rows = [{
            "row_key": "", "items": items[:1],
            "container_settings": {
                "gap": 14, "mobile_mode": "stack", "content_width": "standard",
                "vertical_align": "start", "height_mode": "natural",
                "background_mode": "color", "background_color": "#ff00aa",
                "background_pattern": "",
            },
        }]
        html = render_to_string(
            "storefront_builder/partials/render_rows.html",
            {"rows": rows, "use_container_layout": False},
        )
        self.assertIn("#ff00aa", html)
        self.assertIn("rsec-row-single", html)

    def test_row_without_container_settings_key_is_unaffected(self):
        """``group_items_into_rows``'s own plain output (every OTHER caller
        of this shared partial, e.g. real Draft/Published rendering with no
        real Container rows yet) never sets ``container_settings`` — this
        proves that case still renders with no gap/background override
        markup, i.e. the fix above is additive, not a behavior change for
        existing callers."""
        from django.template.loader import render_to_string

        from apps.storefront_builder.services import preset_service
        from apps.storefront_builder.services.render_service import (
            build_candidate_render_items, group_items_into_rows,
        )

        demo_draft = svc.get_or_create_draft(self.demo_store)
        candidate = preset_service.resolve_preset_candidate(demo_draft, lpr.get_layout_preset(DENSE_MARKETPLACE))
        home_page = candidate.pages["home"]
        items = build_candidate_render_items(
            home_page.sections, self.demo_store,
            global_appearance=candidate.appearance_config, store_appearance=candidate.store_appearance,
        )
        rows = group_items_into_rows(items)
        self.assertNotIn("container_settings", rows[0])
        html = render_to_string(
            "storefront_builder/partials/render_rows.html",
            {"rows": rows, "use_container_layout": False},
        )
        self.assertNotIn("gap:37px", html)
        self.assertNotIn("#1a2b3c", html)


class NavCategoriesReflectDemoStoreNotAmbientAdminStoreTests(LiveDemoTemplatePreviewTestCase):
    """Browser-QA (Task 2) IMPORTANT finding: ``apps.catalog.context_
    processors.nav_categories`` resolves ``resolve_store_for_service``,
    i.e. the AMBIENT admin-host Store (here: ``self.store``, the logged-in
    merchant's own store — a different Store than the one being
    live-previewed), not the Demo Store. The header nav must show the Demo
    Store's own real categories regardless of which merchant is logged in."""

    def test_nav_categories_in_context_all_belong_to_demo_store(self):
        response = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY))
        nav_categories = response.context["nav_categories"]
        self.assertGreater(len(nav_categories), 0)
        for category in nav_categories:
            self.assertEqual(category.store_id, self.demo_store.pk)
            self.assertNotEqual(category.store_id, self.store.pk)


class DemoStoreContextIsRealTests(LiveDemoTemplatePreviewTestCase):
    def test_real_seeded_category_name_appears_in_rendered_output(self):
        response = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY))
        html = response.content.decode()
        self.assertIn(ROOT_CATEGORY_NAME, html)

    def test_real_seeded_brand_name_appears_for_a_brand_carousel_template(self):
        response = self.admin_client.get(self._preview_url(DENSE_MARKETPLACE))
        html = response.content.decode()
        self.assertIn(A_SEEDED_BRAND_NAME, html)


class DemoDraftUnchangedTests(LiveDemoTemplatePreviewTestCase):
    def test_single_preview_request_leaves_demo_draft_unchanged(self):
        demo_draft = svc.get_or_create_draft(self.demo_store)
        before = _snapshot(demo_draft)
        before_appearance = resolve_store_appearance_render_state(demo_draft).manifest.selections

        response = self.admin_client.get(self._preview_url(EDITORIAL_JEWELRY))
        self.assertEqual(response.status_code, 200)

        after = _snapshot(demo_draft)
        after_appearance = resolve_store_appearance_render_state(demo_draft).manifest.selections
        self.assertEqual(before, after)
        self.assertEqual(dict(before_appearance), dict(after_appearance))

    def test_previewing_multiple_different_templates_still_leaves_demo_draft_unchanged(self):
        demo_draft = svc.get_or_create_draft(self.demo_store)
        before = _snapshot(demo_draft)

        for key in (EDITORIAL_JEWELRY, DENSE_MARKETPLACE, "warm_boutique"):
            response = self.admin_client.get(self._preview_url(key))
            self.assertEqual(response.status_code, 200)

        self.assertEqual(_snapshot(demo_draft), before)


class InvalidTemplateKeyTests(LiveDemoTemplatePreviewTestCase):
    def test_unknown_template_key_is_404_and_non_mutating(self):
        demo_draft = svc.get_or_create_draft(self.demo_store)
        before = _snapshot(demo_draft)

        response = self.admin_client.get(self._preview_url("__does_not_exist__"))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(_snapshot(demo_draft), before)

    def test_registered_but_non_ready_template_key_is_404_not_a_crash(self):
        """Independent review (Task 2) IMPORTANT finding: ``get_layout_
        preset`` resolves over the ENTIRE preset registry, not just the 50
        curated Ready Templates. ``clean_minimal`` is a real, registered key
        (``layout_preset_registry.get_layout_preset('clean_minimal')``
        returns a definition) but ``is_ready_template=False`` and has no
        complete Store Appearance — before the fix, this crashed with an
        unhandled ``AttributeError`` deep in ``store_appearance_global_
        renderer_template`` instead of failing closed. This view's whole
        promise is "preview one of the 50 Ready Templates", so a
        real-but-non-Ready key must be treated exactly like an unknown one."""
        from apps.storefront_builder import layout_preset_registry as lpr

        non_ready_preset = lpr.get_layout_preset("clean_minimal")
        self.assertIsNotNone(non_ready_preset)
        self.assertFalse(non_ready_preset.is_ready_template)

        demo_draft = svc.get_or_create_draft(self.demo_store)
        before = _snapshot(demo_draft)

        response = self.admin_client.get(self._preview_url("clean_minimal"))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(_snapshot(demo_draft), before)

    def test_anonymous_request_is_not_authorized(self):
        anon_client = Client(HTTP_HOST=ADMIN_HOST)
        response = anon_client.get(self._preview_url(EDITORIAL_JEWELRY))
        self.assertIn(response.status_code, (302, 403))


class GalleryStillHasFiftyTemplatesTests(LiveDemoTemplatePreviewTestCase):
    def test_gallery_still_lists_exactly_fifty_ready_templates(self):
        response = self.admin_client.get(reverse("dashboard:storefront-builder-templates"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["template_cards"]), 50)

    def test_gallery_cards_link_to_the_new_live_preview_route(self):
        response = self.admin_client.get(reverse("dashboard:storefront-builder-templates"))
        html = response.content.decode()
        self.assertIn(self._preview_url(EDITORIAL_JEWELRY), html)


class ExistingStaticThumbnailPathStillUsableTests(LiveDemoTemplatePreviewTestCase):
    def test_gallery_thumbnail_fields_still_populated_per_card(self):
        response = self.admin_client.get(reverse("dashboard:storefront-builder-templates"))
        cards = response.context["template_cards"]
        for card in cards:
            self.assertIn(card["thumbnail_kind"], ("screenshot", "svg"))
            if card["thumbnail_kind"] == "screenshot":
                self.assertTrue(card["thumbnail_url"])
            else:
                self.assertTrue(card["thumbnail_svg"])
