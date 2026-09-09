"""Phase 4 — Task 6, Group F: write/effective-state reconciliation for the
four global Store-Appearance TEMPORARY-ADAPTER families (`hero`,
`product_view`, `card`, `badge`).

Per the plan (Ruling J): reconciliation only, NO new merchant-facing selector
UI. `hero`/`product_view` already got their write-path reconciliation in
Phase 1 Task 6 (the generic `variant_explicit` marker, keyed off each
section's own registered `variant_setting_key` — see
`docs/qa_evidence/storefront_appearance_convergence/phase1/task6_explicit_local_variant.md`).
These tests certify that mechanism end-to-end for the two families
specifically (not just generically), through the real R4 mutation HTTP
endpoint.

`card`/`badge` never had (and, per investigation, never need) a comparable
local-override marker: neither family has ANY merchant-facing local write
path (no SettingsSchema field, no legacy form field for `card_style`/
`badge_treatment` on any section) — the only place a local `card.card_style`
value ever originates is a Ready Template's own authored `settings.card`,
and every registered Ready Template (verified below across the full live
registry) either matches its own declared `card` family selection or leaves
its shared non-Home boilerplate sections at the inert `"standard"` value
specifically so the Store Appearance manifest is free to be the single
overlay authority for them (mirrors `apply_header_variant`: one canonical
write authority, no independent second writer). These tests certify that the
manifest is the sole effective-state authority for `card`/`badge`, applied
consistently to every `CARD_AWARE_SECTION_KEYS` section, and that reverting
to the safe default leaves each section's own locally-authored value
untouched.
"""

from __future__ import annotations

import copy
import json

from django.core.cache import cache
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.section_registry import CARD_AWARE_SECTION_KEYS, get_definition
from apps.storefront_builder.services import layout_service, preset_service, render_service
from apps.storefront_builder.storefront_appearance.families import (
    DEFAULT_STORE_APPEARANCE_MANIFEST,
)
from apps.storefront_builder.storefront_appearance.persistence import (
    persist_store_appearance_manifest,
)
from apps.storefront_builder.storefront_appearance.validation import manifest_to_primitive

from .test_views import StorefrontBuilderViewsTestCase


def _manifest_with(**selections):
    raw = copy.deepcopy(manifest_to_primitive(DEFAULT_STORE_APPEARANCE_MANIFEST))
    raw["selections"].update(selections)
    return raw


class GroupFReconciliationBase(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        self.home = self.draft.get_page(StorefrontPage.PageType.HOME)
        self.home.sections.all().delete()

    def _post_r4(self, mutation, *, base_revision=None):
        self.draft.refresh_from_db()
        if base_revision is None:
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _component_update(self, family, component_key):
        return self._post_r4({
            "type": "appearance.component.update",
            "draft_id": self.draft.pk,
            "family": family,
            "component_key": component_key,
        })

    def _settings_update(self, section, patch):
        return self._post_r4({
            "type": "section.update_settings",
            "section_id": section.pk,
            "patch": patch,
        })

    def _render_items(self, page=None):
        self.draft.refresh_from_db()
        page = page or self.draft.get_page(StorefrontPage.PageType.HOME)
        return render_service.build_page_render_items(page, self.store)

    def _item_for(self, items, section_key):
        for item in items:
            if item["section"].section_key == section_key:
                return item
        raise AssertionError(f"no render item for {section_key!r}")

    def _default_settings(self, section_key, **overrides):
        settings = get_definition(section_key).default_settings()
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(settings.get(key), dict):
                settings[key] = {**settings[key], **value}
            else:
                settings[key] = value
        return settings


class HeroFamilyReconciliationTests(GroupFReconciliationBase):
    """`hero` family — Store Appearance manifest overlays an unmarked
    section's own `hero_style`; an explicit local edit (via the real R4
    `section.update_settings` write path) wins over a later, conflicting
    manifest selection — exactly the `apply_header_variant`-style contract,
    proven specifically for `hero`."""

    def setUp(self):
        super().setUp()
        self.hero = StorefrontSection.objects.create(
            page=self.home, section_key="hero_banner", order=0,
            settings=self._default_settings("hero_banner", hero_style="overlay"),
        )

    def test_manifest_hero_selection_overlays_unmarked_section(self):
        resp = self._component_update("hero", "hero.split.v1")
        self.assertEqual(resp.status_code, 200)

        item = self._item_for(self._render_items(), "hero_banner")
        self.assertEqual(item["active_variant"].key, "split")

    def test_explicit_local_hero_style_wins_over_later_manifest_selection(self):
        r1 = self._settings_update(self.hero, {"hero_style": "atelier_triptych"})
        self.assertEqual(r1.status_code, 200)
        self.hero.refresh_from_db()
        self.assertTrue(
            self.hero.settings.get("appearance_overrides", {}).get("variant_explicit")
        )

        r2 = self._component_update("hero", "hero.split.v1")
        self.assertEqual(r2.status_code, 200)

        item = self._item_for(self._render_items(), "hero_banner")
        self.assertEqual(item["active_variant"].key, "atelier_triptych")


class ProductViewFamilyReconciliationTests(GroupFReconciliationBase):
    """`product_view` family — the same contract, proven for
    `product_section`'s own `display_mode` axis."""

    def setUp(self):
        super().setUp()
        self.product_section = StorefrontSection.objects.create(
            page=self.home, section_key="product_section", order=0,
            settings=self._default_settings(
                "product_section", display_mode="carousel", data_source="newest",
            ),
        )

    def test_manifest_product_view_selection_overlays_unmarked_section(self):
        resp = self._component_update("product_view", "product_view.dense_grid.v1")
        self.assertEqual(resp.status_code, 200)

        item = self._item_for(self._render_items(), "product_section")
        # ``dense_grid`` resolves to ``catalog_product_wall:group_columns``,
        # a different section than ``product_section`` — the family targets
        # exactly one section per component, so an unrelated section keeps
        # its own registered variant when the selected component targets a
        # different section entirely (no cross-section leakage).
        self.assertEqual(item["active_variant"].key, "carousel")

        resp2 = self._component_update("product_view", "product_view.editorial_grid.v1")
        self.assertEqual(resp2.status_code, 200)
        item2 = self._item_for(self._render_items(), "product_section")
        self.assertEqual(item2["active_variant"].key, "grid")

    def test_explicit_local_display_mode_wins_over_later_manifest_selection(self):
        r1 = self._settings_update(self.product_section, {"display_mode": "campaign_band"})
        self.assertEqual(r1.status_code, 200)
        self.product_section.refresh_from_db()
        self.assertTrue(
            self.product_section.settings.get("appearance_overrides", {})
            .get("variant_explicit")
        )

        r2 = self._component_update("product_view", "product_view.editorial_grid.v1")
        self.assertEqual(r2.status_code, 200)

        item = self._item_for(self._render_items(), "product_section")
        self.assertEqual(item["active_variant"].key, "campaign_band")


class CardFamilyReconciliationTests(GroupFReconciliationBase):
    """`card` family — no local write path exists anywhere for
    `card.card_style` (no SettingsSchema field, no legacy form field on any
    section), so the Store Appearance manifest is the sole write authority;
    a non-default selection must overlay EVERY `CARD_AWARE_SECTION_KEYS`
    section consistently, and the safe default must leave each section's own
    (Ready-Template-authored or otherwise persisted) value untouched."""

    def setUp(self):
        super().setUp()
        self.product_section = StorefrontSection.objects.create(
            page=self.home, section_key="product_section", order=0,
            settings=self._default_settings(
                "product_section", display_mode="grid", data_source="newest",
                card={"card_style": "standard"},
            ),
        )
        self.wall = StorefrontSection.objects.create(
            page=self.home, section_key="catalog_product_wall", order=1,
            settings=self._default_settings(
                "catalog_product_wall", card={"card_style": "minimal"},
            ),
        )

    def _card_style(self, item):
        return item["context"]["settings"].get("card", {}).get("card_style")

    def test_manifest_card_selection_overlays_every_card_aware_section(self):
        resp = self._component_update("card", "card.luxury_dark.v1")
        self.assertEqual(resp.status_code, 200)

        items = self._render_items()
        self.assertEqual(self._card_style(self._item_for(items, "product_section")), "luxury_dark")
        self.assertEqual(self._card_style(self._item_for(items, "catalog_product_wall")), "luxury_dark")

    def test_default_card_selection_leaves_local_card_style_untouched(self):
        # The family starts at its safe default (``card.legacy_default.v1``);
        # each section's own locally-authored value must render unchanged.
        items = self._render_items()
        self.assertEqual(self._card_style(self._item_for(items, "product_section")), "standard")
        self.assertEqual(self._card_style(self._item_for(items, "catalog_product_wall")), "minimal")

    def test_reverting_to_default_restores_each_sections_own_local_value(self):
        self._component_update("card", "card.luxury_dark.v1")
        resp = self._component_update("card", "card.legacy_default.v1")
        self.assertEqual(resp.status_code, 200)

        items = self._render_items()
        self.assertEqual(self._card_style(self._item_for(items, "product_section")), "standard")
        self.assertEqual(self._card_style(self._item_for(items, "catalog_product_wall")), "minimal")


class BadgeFamilyReconciliationTests(GroupFReconciliationBase):
    """`badge` family — mirrors the `card` family contract exactly for
    `badge_treatment` (also no local write path anywhere)."""

    def setUp(self):
        super().setUp()
        self.product_section = StorefrontSection.objects.create(
            page=self.home, section_key="product_section", order=0,
            settings=self._default_settings(
                "product_section", display_mode="grid", data_source="newest",
            ),
        )

    def _badge_treatment(self, item):
        return item["context"]["settings"].get("card", {}).get("badge_treatment")

    def test_manifest_badge_selection_overlays_card_aware_section(self):
        resp = self._component_update("badge", "badge.sale.v1")
        self.assertEqual(resp.status_code, 200)

        item = self._item_for(self._render_items(), "product_section")
        self.assertEqual(self._badge_treatment(item), "sale")

    def test_default_badge_selection_applies_no_overlay(self):
        item = self._item_for(self._render_items(), "product_section")
        self.assertIsNone(self._badge_treatment(item))


class ReadyTemplateCardFamilyConsistencyTests(GroupFReconciliationBase):
    """Every registered Ready Template (the live production registry, not a
    hand-picked sample) declares a `card` family selection in its typed
    `store_appearance` DNA; its shared non-Home, context-aware boilerplate
    sections (`product_listing`/`collection_products`/`related_products` —
    the same composition across every recipe, from `_u10_standard_non_home_pages`)
    must render with that declared family's `card_style` — proving the
    manifest overlay (not any per-template hand-authored local value) is
    what actually drives their presentation, exactly the single-writer
    contract Group F requires."""

    def test_every_ready_template_overlays_shared_non_home_sections_with_its_declared_card(self):
        checked_any = False
        for preset in layout_preset_registry.list_ready_templates():
            selection = preset.store_appearance["selections"]["card"]
            if selection == "card.legacy_default.v1":
                continue  # nothing to overlay; not a card-family exercise
            declared_card_style = selection.split(".")[1]

            preset_service.apply_preset(self.draft, preset)
            for page_type, section_key in (
                ("listing", "product_listing"),
                ("collection", "collection_products"),
                ("product_detail", "related_products"),
            ):
                page = self.draft.get_page(page_type)
                if not StorefrontSection.objects.filter(
                    page=page, section_key=section_key, is_active=True,
                ).exists():
                    continue
                items = self._render_items(page=page)
                item = self._item_for(items, section_key)
                self.assertEqual(
                    item["context"]["settings"].get("card", {}).get("card_style"),
                    declared_card_style,
                    f"preset {preset.key!r} / page {page_type!r} / section {section_key!r}: "
                    "the Store Appearance manifest's declared card family must be the "
                    "effective card_style for this shared, non-curated boilerplate section",
                )
                checked_any = True
        self.assertTrue(checked_any, "no Ready Template exercised a non-default card family")
