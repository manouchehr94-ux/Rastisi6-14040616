"""Tests for the Golden Reference Storefront G1 setup command
(``apply_golden_reference_storefront``).

The Golden Reference Storefront is the customized ``rasti-mode-demo`` store —
a visually complete premium multi-brand fashion/lifestyle storefront produced
entirely through existing production contracts (the demo seed for the real
catalog/content, then the ``fashion_promo_catalog`` Ready Template baseline
customized via the normal preset/appearance/publish services).

Contracts asserted here (see
``docs/superpowers/plans/2026-09-04-golden-reference-storefront-g1-plan.md``):

- The command runs the idempotent demo seed, then applies + publishes the
  Golden composition. A published V2 layout exists afterward (so the public
  route uses the universal shell, not the legacy fallback).
- Provenance stays honest: the applied baseline is still
  ``fashion_promo_catalog`` — the Golden customization is NOT a 51st Ready
  Template and never mutates the A8 registry.
- The Golden shell selections are applied: header ``marketplace_search_first``,
  footer ``premium_columns``, mobile bottom nav ``five_item``, palette
  ``theme-forest-cream``.
- The Home composition is the approved 12-section commercial rhythm.
- Re-running converges (idempotent): no duplicate stores/products, exactly one
  published layout, identical section order.
- Tenant isolation: only ``rasti-mode-demo`` is ever touched.

MEDIA_ROOT is overridden so uploaded media never lands under the real
project ``media/``.
"""

import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalog.models import Product
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import layout_service
from apps.stores.models import Store
from apps.storefront_builder.tests._catalog_count import READY_TEMPLATE_COUNT

STORE_SLUG = "rasti-mode-demo"
OTHER_REAL_SLUG = "rastisi-fashion-test"

GOLDEN_HOME_SECTIONS = [
    # The announcement is rendered by the global header
    # (header_config.announcement_enabled), not as a page section — avoiding a
    # duplicate announcement strip observed in visual QA.
    "hero_banner",
    "category_grid",
    "multi_banner",
    "product_section",   # newest
    "brand_carousel",
    "multi_banner",
    "product_section",   # most viewed / popular
    "story_rail",
    "product_section",   # discounted / special offer
    "collection_tiles",
    "trust_features",
    "newsletter",
]


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ApplyGoldenReferenceStorefrontCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def _run(self, *extra_args):
        call_command("apply_golden_reference_storefront", *extra_args, stdout=StringIO())

    def _store(self) -> Store:
        return Store.objects.get(slug=STORE_SLUG)

    # ---------------------------------------------------- Orchestration boundary
    # The Golden service is the ONE architecturally-correct Apply+Publish
    # mechanism (real registered baseline -> Golden customization -> publish). The
    # seed command must be used only for demo Catalog/content setup — the Golden
    # command must NOT ask the seed to Apply+Publish the Ready Template first
    # (a redundant orchestration step).

    def test_seed_is_invoked_for_content_only_not_to_apply_publish_the_template(self):
        import apps.stores.management.commands.apply_golden_reference_storefront as cmd

        original_call_command = cmd.call_command
        seen_seed_calls = []

        def _spy(name, *args, **kwargs):
            if name == "seed_ready_template_fashion_demo":
                seen_seed_calls.append(list(args))
            return original_call_command(name, *args, **kwargs)

        with mock.patch.object(cmd, "call_command", side_effect=_spy):
            self._run()

        self.assertEqual(len(seen_seed_calls), 1, "seed should be invoked exactly once")
        seed_args = seen_seed_calls[0]
        self.assertNotIn(
            "--ready-template",
            seed_args,
            "Golden command must not delegate Apply+Publish to the seed; the Golden "
            "service owns baseline Apply -> customize -> Publish.",
        )
        # And the end state must still be fully correct without that delegation.
        published = layout_service.get_or_create_layout(self._store()).published_version
        self.assertIsNotNone(published)
        self.assertEqual(
            published.template_provenance.get("template", {}).get("key"),
            "fashion_promo_catalog",
        )

    # ------------------------------------------------------------------ Publish

    def test_provisions_a_published_universal_layout(self):
        self._run()
        layout = layout_service.get_or_create_layout(self._store())
        self.assertIsNotNone(layout.published_version_id)

    def test_provenance_is_still_the_fashion_promo_catalog_baseline(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        self.assertEqual(
            published.template_provenance.get("template", {}).get("key"),
            "fashion_promo_catalog",
        )

    # ------------------- Baseline-truth invariants (Phase-1 reconstruction) ----
    # These prove the Golden setup follows the correct model:
    #   template_baseline_snapshot = pure authored registered template truth,
    #   live Draft/Published = authored baseline + Golden merchant customizations.

    def _authored_baseline(self):
        """The ACTUAL authored registered fashion_promo_catalog baseline —
        read straight from the registry, independent of anything Golden does."""
        preset = lpr.get_layout_preset("fashion_promo_catalog")
        home_keys = [entry.section_key for entry in preset.pages["home"]]
        return preset, home_keys

    def test_A_provenance_points_at_the_real_registered_template_key_and_version(self):
        preset, _ = self._authored_baseline()
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        template = published.template_provenance.get("template", {})
        self.assertEqual(template.get("key"), "fashion_promo_catalog")
        self.assertEqual(template.get("version"), preset.version)

    def test_B_baseline_snapshot_is_the_authored_template_not_the_golden_home(self):
        preset, authored_home_keys = self._authored_baseline()
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        snapshot = published.template_baseline_snapshot
        self.assertTrue(snapshot, "expected a recorded template_baseline_snapshot")
        self.assertEqual(snapshot.get("template_key"), "fashion_promo_catalog")
        self.assertEqual(snapshot.get("template_version"), preset.version)
        # The snapshot must describe the AUTHORED baseline Home, NOT the Golden
        # customized 12-section Home.
        snapshot_home_keys = [entry["section_key"] for entry in snapshot["pages"]["home"]]
        self.assertEqual(snapshot_home_keys, authored_home_keys)
        self.assertNotEqual(snapshot_home_keys, GOLDEN_HOME_SECTIONS)
        # The snapshot palette is the authored template palette, not the Golden
        # identity palette.
        self.assertEqual(snapshot.get("default_palette_slug"), preset.default_palette_slug)
        self.assertNotEqual(snapshot.get("default_palette_slug"), "theme-forest-cream")

    def test_C_live_draft_intentionally_differs_from_the_authored_baseline(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        snapshot = published.template_baseline_snapshot
        # Live composition is the Golden Home; authored baseline is different.
        live_home_keys = list(
            published.home_page().sections.order_by("order").values_list("section_key", flat=True)
        )
        snapshot_home_keys = [entry["section_key"] for entry in snapshot["pages"]["home"]]
        self.assertEqual(live_home_keys, GOLDEN_HOME_SECTIONS)
        self.assertNotEqual(live_home_keys, snapshot_home_keys)
        # Live shell/palette are the Golden merchant selections; the authored
        # baseline recorded the template's own (different) shell/palette.
        self.assertEqual(published.effective_appearance_config().get("palette_slug"), "theme-forest-cream")
        self.assertNotEqual(
            published.effective_header_config().get("header_variant"),
            snapshot["header_config"].get("header_variant"),
        )

    def test_D_official_a8_catalog_remains_exactly_fifty(self):
        before = {p.key for p in lpr.list_ready_templates()}
        self._run()
        after = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(before, after)
        self.assertEqual(len(after), READY_TEMPLATE_COUNT)  # real registry: 50 A8 templates + 3 later ones (verified from list_ready_templates())

    # ------------------------------------------------------------------ Shell

    def test_golden_shell_variants_are_applied(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        header = published.effective_header_config()
        footer = published.effective_footer_config()
        appearance = published.effective_appearance_config()
        self.assertEqual(header.get("header_variant"), "marketplace_search_first")
        self.assertEqual(footer.get("footer_variant"), "premium_columns")
        self.assertEqual(footer.get("mobile_nav_variant"), "five_item")
        self.assertEqual(appearance.get("palette_slug"), "theme-forest-cream")

    def test_cart_shortcut_remains_enabled_in_header(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        self.assertTrue(published.effective_header_config().get("show_cart", True))

    # ------------------------------------------------------------------ Home

    def test_home_composition_matches_the_golden_commercial_rhythm(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            GOLDEN_HOME_SECTIONS,
        )

    def test_three_product_sections_use_distinct_data_sources(self):
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        product_sections = [
            s for s in home.sections.order_by("order") if s.section_key == "product_section"
        ]
        sources = [s.settings.get("data_source") for s in product_sections]
        self.assertEqual(sources, ["newest", "most_viewed", "discounted"])

    def test_no_catalog_ids_are_hardcoded_into_product_section_settings(self):
        """Product data must resolve at render time from Catalog via
        ``data_source`` — never by baking product IDs into Builder JSON."""
        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        for section in home.sections.filter(section_key="product_section"):
            self.assertEqual(section.settings.get("product_ids", []), [])

    def test_all_three_product_sections_resolve_non_empty_so_they_render(self):
        """Every product_section (newest, most_viewed, discounted) must resolve
        real products and survive the empty-public-section filter — otherwise
        the Home would silently drop a merchandising section."""
        from apps.storefront_builder.services import render_service

        self._run()
        published = layout_service.get_or_create_layout(self._store()).published_version
        home = published.home_page()
        sa = render_service.resolve_store_appearance_render_state(published)
        items = render_service.build_page_render_items(home, self._store(), store_appearance=sa)
        for it in items:
            if it["section"].section_key == "product_section":
                self.assertGreater(
                    len(it["context"].get("products", [])),
                    0,
                    it["section"].settings.get("data_source"),
                )
        visible_keys = [it["section"].section_key for it in render_service.hide_empty_public_sections(items)]
        self.assertEqual(visible_keys.count("product_section"), 3)

    def test_demo_products_have_deterministic_view_signals(self):
        self._run()
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store, views_count=0).count(), 0)

    # ------------------------------------------------------------------ Idempotence

    def test_second_run_converges_without_duplicates(self):
        self._run()
        self._run()
        self.assertEqual(Store.objects.filter(slug=STORE_SLUG).count(), 1)
        store = self._store()
        self.assertEqual(Product.objects.filter(store=store).count(), 50)
        layout = layout_service.get_or_create_layout(store)
        self.assertIsNotNone(layout.published_version_id)
        home = layout.published_version.home_page()
        self.assertEqual(
            list(home.sections.order_by("order").values_list("section_key", flat=True)),
            GOLDEN_HOME_SECTIONS,
        )

    # ------------------------------------------------------------------ Invariants

    def test_a8_ready_template_registry_is_unchanged(self):
        before = {p.key for p in lpr.list_ready_templates()}
        self._run()
        after = {p.key for p in lpr.list_ready_templates()}
        self.assertEqual(before, after)
        self.assertEqual(len(after), READY_TEMPLATE_COUNT)  # real registry: 50 A8 templates + 3 later ones (verified from list_ready_templates())

    def test_never_touches_another_store(self):
        other = Store.objects.create(
            name="فروشگاه لباس تستی راستی سی", slug=OTHER_REAL_SLUG, status=Store.Status.ACTIVE
        )
        self._run()
        other.refresh_from_db()
        self.assertEqual(other.name, "فروشگاه لباس تستی راستی سی")
        from apps.storefront_builder.models import StorefrontLayout

        self.assertFalse(StorefrontLayout.objects.filter(store=other).exists())
