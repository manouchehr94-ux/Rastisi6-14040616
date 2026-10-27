"""V5 composition lab — proof that complex layouts taken from the six reference sites (and a seventh, invented one) are BUILT AND EDITED
only through the generic R4 mutation path the Inspector uses (``container.add`` / ``container.resize`` / ``container.update_settings`` /
``section.update_settings`` / ``header.update`` / ``footer.update``): no recipe, no template key, no site CSS.

Every scenario is checked in Draft preview, after Publish on the public page, and through Undo / Redo; the phone behaviour is checked as the
sparse data attributes / design flags the central stylesheet acts on."""

import json
import re

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder import pdp_settings
from apps.storefront_builder.models import StorefrontContainer, StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import r4_mutation_service
from apps.stores.models import StoreDomain

from .test_media_views import HOST
from .test_v5_pdp_design_controls import _data_attrs, _pdp_tag, _PdpBase

HOME = StorefrontPage.PageType.HOME
LAB_HOST = "composition-lab.example.com"


@override_settings(ALLOWED_HOSTS=[HOST, LAB_HOST, "testserver"])
class _LabBase(_PdpBase):
    def setUp(self):
        super().setUp()
        StoreDomain.objects.create(
            store=self.store, hostname=LAB_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.public = Client(HTTP_HOST=LAB_HOST)

    # -- the Inspector's own entry point -------------------------------------------------------------------------------------
    def mutate(self, mutation):
        return r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=self._revision(), mutation=mutation,
        )

    def home_preview(self):
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + "?page=home")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def home_public(self):
        response = self.public.get("/", HTTP_HOST=LAB_HOST)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def build_container(self, layout, cells):
        self.mutate({"type": "container.add", "page_type": "home", "layout_key": layout, "cells": cells})
        return StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-id").first()

    def blocks(self, container, key=None):
        qs = StorefrontSection.objects.filter(cell__container=container).order_by("cell__order", "cell_order")
        return list(qs.filter(section_key=key) if key else qs)

    def patch(self, section, patch):
        self.mutate({"type": "section.update_settings", "section_id": section.pk, "patch": patch})

    def undo_redo_round_trip(self, probe):
        """``probe(html)`` is true while the last mutation is applied: Undo removes it, Redo brings it back."""
        self.assertTrue(probe(self.home_preview()))
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertFalse(probe(self.home_preview()), "Undo must remove the last edit")
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertTrue(probe(self.home_preview()), "Redo must bring the edit back")

    def publish_and_probe(self, probe):
        svc.publish(self.store)
        self.assertTrue(probe(self.home_public()), "the published page must carry the same composition")
        self.draft = svc.get_or_create_draft(self.store)          # editing continues on a fresh Draft


class AsymmetricTileCompositionTests(_LabBase):
    """Khanehshokolati's alternating text / photo tiles: four Cells of different widths, each holding a different kind of block."""

    def test_four_alternating_tiles_are_built_resized_and_styled_without_code(self):
        container = self.build_container("quarters", [["rich_text"], ["linked_image"], ["rich_text"], ["linked_image"]])
        self.assertEqual([s.section_key for s in self.blocks(container)], ["rich_text", "linked_image", "rich_text", "linked_image"])
        self.mutate({"type": "container.resize", "container_id": container.pk, "spans": [4, 2, 4, 2]})
        self.mutate({"type": "container.update_settings", "container_id": container.pk, "patch": {"gap": 18, "height_mode": "equal"}})
        for text_block in self.blocks(container, "rich_text"):
            self.patch(text_block, {"body_html": "<p>عنوان کاشی</p>", "design": {
                "min_height": 220, "valign": "center", "align": "center", "radius": 24},
                "background": {"mode": "color", "color": "#FBCB60"}})
        for photo in self.blocks(container, "linked_image"):
            self.patch(photo, {"design": {"image_ratio": "square", "radius": 24}})

        def probe(html):
            return ("--cell-span:4" in html and "--cell-span:2" in html and "--container-gap:18px" in html
                    and bool(re.search(r'data-d="[^"]*\bvalign\b', html)) and bool(re.search(r'data-d="[^"]*\bratio\b', html)))

        self.assertTrue(probe(self.home_preview()))
        self.publish_and_probe(probe)
        container = StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-id").first()
        # one more edit, then Undo / Redo of exactly that edit
        self.mutate({"type": "container.resize", "container_id": container.pk, "spans": [3, 3, 3, 3]})
        self.assertIn("--cell-span:3", self.home_preview())
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertIn("--cell-span:4", self.home_preview())
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertNotIn("--cell-span:4", self.home_preview())

    def test_a_stacked_side_composition_hosts_a_hero_and_two_panels(self):
        container = self.build_container("big_right_two_left", [["hero_banner"], ["multi_banner"], ["linked_image"]])
        hero = self.blocks(container, "hero_banner")[0]
        self.patch(hero, {"hero_style": "split_open", "image_side": "start", "split_ratio": "text_wide"})
        panels = self.blocks(container, "multi_banner")[0]
        self.patch(panels, {"layout_variant": "panel-4", "item_limit": 2})

        def probe(html):
            return 'data-layout="big_right_two_left"' in html
        self.assertTrue(probe(self.home_preview()))
        stored = self._stored(hero)
        self.assertEqual((stored["hero_style"], stored["image_side"], stored["split_ratio"]), ("split_open", "start", "text_wide"))
        self.publish_and_probe(probe)


class PhoneLayoutTests(_LabBase):
    """Independent phone behaviour: a four-card row becomes a one-card slider, stacked Cells reverse, a Container becomes a slider."""

    def test_a_multi_banner_row_becomes_a_one_card_slider_on_phones_only(self):
        container = self.build_container("half", [["multi_banner"], ["rich_text"]])
        banners = self.blocks(container, "multi_banner")[0]
        self.patch(banners, {"layout_variant": "people-4", "design": {"image_ratio": "portrait", "gap": 10}})
        self.patch(banners, {"design": {"image_ratio": "portrait", "gap": 10, "mobile_layout": "slider"}})
        self.assertEqual(self._stored(banners)["design"]["mobile_layout"], "slider")
        flags = lambda html: bool(re.search(r'data-d="[^"]*\bm-slider\b', html))
        self.undo_redo_round_trip(flags)
        self.publish_and_probe(flags)
        css = (self._css_path()).read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\(max-width:680px\)\{\s*\.rsec\[data-d~=\"m-stack\"\]")           # phone-only rules
        self.assertIn('.rsec[data-d~="m-slider"]', css)

    def test_out_of_vocabulary_phone_layout_is_refused_and_changes_nothing(self):
        container = self.build_container("half", [["multi_banner"], ["rich_text"]])
        banners = self.blocks(container, "multi_banner")[0]
        before = self._revision()
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.patch(banners, {"design": {"mobile_layout": "carousel3d"}})
        self.assertEqual(self._revision(), before)

    def test_container_phone_order_and_slider_modes(self):
        container = self.build_container("half", [["rich_text"], ["linked_image"]])
        self.mutate({"type": "container.update_settings", "container_id": container.pk, "patch": {"mobile_order": "reverse"}})
        self.assertIn('data-mobile-order="reverse"', self.home_preview())
        self.assertIn("--cell-i:2", self.home_preview(), "a reversed row numbers its cells so a phone slider can swipe in the opposite order")
        self.mutate({"type": "container.update_settings", "container_id": container.pk, "patch": {"mobile_mode": "slider"}})
        html = self.home_preview()
        self.assertIn('data-mobile-mode="slider"', html)
        self.publish_and_probe(lambda html: 'data-mobile-mode="slider"' in html)
        container = StorefrontContainer.objects.filter(page__version=self.draft, page__page_type="home").order_by("-id").first()
        self.mutate({"type": "container.update_settings", "container_id": container.pk, "patch": {"mobile_mode": "spin"}})
        self.assertIn('data-mobile-mode="stack"', self.home_preview(), "an unknown mode is never stored: the Container falls back to its default")

    @staticmethod
    def _css_path():
        from pathlib import Path
        return Path(__file__).resolve().parents[1] / "static" / "css" / "storefront_builder.css"


class HeroAndShellCompositionTests(_LabBase):
    def test_hero_picture_side_and_column_share_are_inspector_settings(self):
        container = self.build_container("half", [["hero_banner"], ["rich_text"]])
        hero = self.blocks(container, "hero_banner")[0]
        self.patch(hero, {"hero_style": "split", "image_side": "start", "split_ratio": "image_wide"})
        stored = self._stored(hero)
        self.assertEqual((stored["image_side"], stored["split_ratio"]), ("start", "image_wide"))
        before = self._revision()
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.patch(hero, {"image_side": "diagonal"})
        self.assertEqual(self._revision(), before)

    def test_footer_columns_can_be_reordered_resized_and_spaced_from_the_studio_path(self):
        self.mutate({"type": "footer.update", "patch": {"footer_variant": "marketplace_dense", "geometry": {
            "order_contact": 1, "order_about": 4, "column_count": 3, "column_gap": 40, "pad_y": 60, "text_size": 16}}})
        probe = lambda html: ("--gf-o-contact:1" in html and "--gf-cols:3" in html and "--gf-pad-y:60px" in html)
        self.assertTrue(probe(self.home_preview()))
        self.assertIn('data-gf-block="contact"', self.home_preview())
        self.undo_redo_round_trip(probe)
        self.publish_and_probe(probe)
        with self.assertRaises(r4_mutation_service.R4MutationError):
            self.mutate({"type": "footer.update", "patch": {"geometry": {"order_contact": "first"}}})


class ProductPageCompositionTests(_LabBase):
    def test_gallery_and_buy_panel_composition_including_block_order(self):
        self._update(self.main, {
            "gallery_position": "end", "gallery_split": "info_wide", "thumbs_position": "side", "gallery_frame": "flush",
            "info_panel": "outlined_tone", "info_order": [{"key": k} for k in ("price", "specs", "options", "actions")],
        })
        stored = self._stored(self.main)
        self.assertEqual([row["key"] for row in stored["info_order"]], ["price", "specs", "options", "actions"])
        attrs = _data_attrs(_pdp_tag(self._preview()))
        self.assertEqual((attrs["gallery-pos"], attrs["gallery-split"], attrs["thumbs"], attrs["info-order"]), ("end", "info_wide", "side", "custom"))
        html = self._preview()
        self.assertIn("--o-price:1", html)
        self.assertIn("--o-options:3", html)
        self.assertIn('data-blk="actions"', html)
        # Undo drops the whole edit; Redo restores it; the default order is never stored
        self.assertEqual(self._history("undo").status_code, 200)
        self.assertNotIn("info-order", _data_attrs(_pdp_tag(self._preview())))
        self.assertEqual(self._history("redo").status_code, 200)
        self.assertEqual(_data_attrs(_pdp_tag(self._preview()))["info-order"], "custom")
        self._update(self.main, {"info_order": [{"key": k} for k in pdp_settings.PRODUCT_INFO_BLOCK_KEYS]})
        self.assertNotIn("info_order", self._stored(self.main))

    def test_the_phone_quick_buy_bar_steps_aside_instead_of_covering_buy_controls(self):
        from pathlib import Path

        css = (Path(pdp_settings.__file__).resolve().parents[2] / "apps" / "catalog" / "static" / "css" / "product_detail.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media\(max-width:680px\)\{\s*\.pdp-satc\[data-away\]\{transform:translateY\(130%\);visibility:hidden")
        html = self._preview()
        self.assertIn("toggleAttribute('data-away', away)", html)
        self.assertIn(".pricebox, .opt-block, .qty, .pdp-actions", html)

    def test_info_order_ignores_unknown_and_duplicate_blocks_and_keeps_every_block(self):
        self.assertEqual(pdp_settings.effective_info_order(["trust", "bogus", "trust", "price"]),
                         ["trust", "price", "options", "specs", "gift", "actions", "notices", "contact"])
        self.assertEqual(pdp_settings.resolve_product_main_view({"info_order": ["bogus"]})["order_style"], "")
        self.assertEqual(len(pdp_settings.effective_info_order(None)), len(pdp_settings.PRODUCT_INFO_BLOCK_KEYS))
