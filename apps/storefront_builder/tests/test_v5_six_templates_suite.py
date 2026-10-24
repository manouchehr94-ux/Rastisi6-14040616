"""V5 six reference templates (54-59) and the second batch of generic engine primitives.

Primitives (all generic, reusable by any Store, validated through the real section validators / resolvers / renderer):
product-row tabs (categories / subcategories / sorts), row glow, heading styles, the call-to-action strip, hero ratio / width, three
category display modes, blog editorial cards, image-text feature rows, multi-banner layouts + heading, several videos in a row, the
add-to-cart colour role and the three new product cards. Templates: each of the six is a registered, versioned Ready Template that can
be installed on a Store through the canonical path, published and rendered (Home and product page) without touching Store data."""

from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.storefront_builder import (
    appearance_registry, decorative_strip, layout_preset_registry as lpr, pdp_settings, section_registry as sr,
)
from apps.storefront_builder.qa import reference_capture as rc
from apps.storefront_builder.qa import reference_packs  # noqa: F401  (registers the demo packs)
from apps.storefront_builder.services import section_data_service
from apps.storefront_builder.services.category_selection import select_categories

from ._catalog_count import READY_TEMPLATE_COUNT

SIX = {
    "decor_sand_boutique": ("Dize", "sand-olive"),
    "rose_beauty_store": ("lilikacosmetics", "rose-cream"),
    "pink_beauty_gallery": ("lilium-gallery", "fuchsia-gallery"),
    "campaign_beauty_hub": ("AsalBanoo", "honey-orange"),
    "cocoa_gift_shop": ("khanehshokolati", "cocoa-gold"),
    "neon_digital_store": ("zhimunplus", "neon-navy"),
}
HOST = "six-suite.example.com"


class RegistrationTests(SimpleTestCase):
    def test_the_six_templates_are_registered_ready_templates_with_their_own_palette(self):
        for key, (_site, palette) in SIX.items():
            with self.subTest(key=key):
                preset = lpr.get_layout_preset(key)
                self.assertTrue(preset.is_ready_template)
                self.assertEqual(preset.default_palette_slug, palette)
                self.assertIsNotNone(appearance_registry.get_palette(palette))
                self.assertIn("home", preset.pages)
                self.assertIn("product_detail", preset.pages)

    def test_the_catalogue_count_is_the_single_constant(self):
        ready = [p for p in lpr.list_layout_presets() if p.is_ready_template]
        self.assertEqual(len(ready), READY_TEMPLATE_COUNT)

    def test_no_recipe_carries_third_party_copy_or_ids(self):
        for key in SIX:
            preset = lpr.get_layout_preset(key)
            blob = repr(preset.pages)
            for forbidden in ("L'OREAL", "LOREAL", "Stanley", "STANLEY", "SHEGLAM", "ChatGPT", "http"):
                self.assertNotIn(forbidden, blob, f"{key}: {forbidden}")


class PdpRecipeAndCssContractTests(SimpleTestCase):
    def _pdp_settings(self, key, section_key):
        entries = lpr.get_layout_preset(key).pages["product_detail"]
        return next(e for e in entries if e.section_key == section_key).settings

    def test_none_of_the_six_carries_the_mobile_floating_bar_and_two_carry_the_desktop_bar(self):
        for key in SIX:
            with self.subTest(key=key):
                self.assertIs(self._pdp_settings(key, "product_main")["show_mobile_sticky_bar"], False)
        with_desktop = {k for k in SIX if self._pdp_settings(k, "product_main").get("show_desktop_sticky_bar")}
        self.assertEqual(with_desktop, {"rose_beauty_store", "neon_digital_store"})

    def test_the_description_tabs_keep_a_tab_row_on_phones_where_the_references_do(self):
        tabbed = {k for k in SIX if self._pdp_settings(k, "product_description").get("mobile_layout") == "tabs"}
        self.assertEqual(tabbed, set(SIX) - {"decor_sand_boutique"})

    def test_the_honey_recipe_ships_an_empty_merchant_authored_faq_slot_only(self):
        entries = lpr.get_layout_preset("campaign_beauty_hub").pages["product_detail"]
        faq = [e for e in entries if e.section_key == "faq"]
        self.assertEqual(len(faq), 1)
        self.assertEqual(faq[0].settings["items"], [], "no invented question or answer")
        self.assertEqual(faq[0].semantic_slot_key, "product.faq")

    def test_the_khane_home_recipe_has_the_extra_banner_groups_and_the_banner_pool_covers_them(self):
        home = lpr.get_layout_preset("cocoa_gift_shop").pages["home"]
        variants = [e.settings.get("layout_variant") for e in home if e.section_key == "multi_banner"]
        self.assertEqual(variants, ["wide-single", "mosaic-5", "duo-round", "mosaic-5", "duo-round", "mini-4"])
        used = max(e.settings["offset"] + e.settings["item_limit"] for e in home if e.section_key == "multi_banner")
        self.assertEqual(used, 19)
        self.assertEqual(len(rc.PACKS["khanehshokolati"]["banners"]), used)

    def test_banner_variant_column_rules_out_rank_the_shared_grid_rule(self):
        css = (Path(sr.__file__).parent / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        for variant in ("duo-round", "trio-round", "people-4", "mosaic-5", "panel-4"):
            self.assertRegex(css, r"\.grid\.rsec-cols\.promo-grid--%s\{grid-template-columns" % variant, variant)
        # the shared product rule is (0,2,0); an unprefixed variant rule (0,1,0) would lose to it and render four equal columns
        self.assertNotRegex(css, r"(?m)^\.promo-grid--(duo-round|trio-round|people-4|mosaic-5|panel-4)\{grid-template-columns")


class FidelityRoundPrimitiveTests(SimpleTestCase):
    def test_testimonials_keep_a_valid_rating_and_style_only(self):
        item = {"name": "الف", "quote": "متن", "role": "نقش", "rating": 5}
        cleaned = sr._validate_testimonials_settings({"items": [item, {**item, "rating": 9}, {**item, "rating": "x"}], "style": "card_row"})
        self.assertEqual([i.get("rating") for i in cleaned["items"]], [5, None, None])
        self.assertEqual(cleaned["style"], "card_row")
        self.assertNotIn("style", sr._validate_testimonials_settings({"items": [], "style": "bogus"}))

    def test_faq_cards_style_is_written_only_when_chosen(self):
        base = {"items": [{"question": "س", "answer": "ج"}]}
        self.assertNotIn("style", sr._validate_faq_settings(base))
        self.assertEqual(sr._validate_faq_settings({**base, "style": "cards"})["style"], "cards")
        self.assertNotIn("style", sr._validate_faq_settings({**base, "style": "other"}))

    def test_image_text_media_library_picture_is_validated_and_sparse(self):
        self.assertNotIn("image_media_asset_id", sr._validate_image_text_settings({"title": "t"}))
        self.assertEqual(sr._validate_image_text_settings({"title": "t", "image_media_asset_id": "12"})["image_media_asset_id"], 12)
        for bad in ("x", 0, -3):
            with self.assertRaises(ValueError):
                sr._validate_image_text_settings({"title": "t", "image_media_asset_id": bad})

    def test_hero_split_open_is_a_registered_variant_with_its_own_renderer(self):
        self.assertIn("split_open", sr.HERO_STYLE_CHOICES)
        variants = {v.key: v for v in sr.get_definition("hero_banner").variants}
        self.assertEqual(variants["split_open"].renderer, "storefront_builder/sections/hero_banner_split_open.html")

    def test_footer_and_header_geometry_are_sparse_and_bounded(self):
        from apps.storefront_builder import shell_geometry

        self.assertEqual(shell_geometry.validate_geometry({"pad_y": 400, "text_size": 3}, "footer"), {"pad_y": 160, "text_size": 11})
        self.assertEqual(shell_geometry.validate_geometry({"mobile_search_icon": 1}, "header"), {"mobile_search_icon": 1})
        self.assertEqual(shell_geometry.validate_geometry({}, "footer"), {})
        self.assertEqual(shell_geometry.geometry_style({"pad_y": 56, "text_size": 15}, "footer"), "--gf-pad-y:56px;--gf-text:15px")

    def test_the_new_recipe_choices_are_set_where_the_references_need_them(self):
        main = lambda key: self._main(key)
        self.assertEqual(main("cocoa_gift_shop").get("info_panel"), "outlined_tone")
        self.assertNotIn("gallery_position", main("cocoa_gift_shop"), "the reference keeps the gallery at the start (right in RTL)")
        self.assertEqual(lpr.get_layout_preset("cocoa_gift_shop").footer["mobile_nav_variant"], "five_item")
        self.assertEqual(lpr.get_layout_preset("neon_digital_store").pages["home"][0].settings["hero_style"], "split_open")
        for key in ("campaign_beauty_hub", "neon_digital_store"):
            self.assertEqual(lpr.get_layout_preset(key).header["geometry"].get("mobile_search_icon"), 1, key)

    @staticmethod
    def _main(key):
        return next(e for e in lpr.get_layout_preset(key).pages["product_detail"] if e.section_key == "product_main").settings


class ProductSectionPrimitiveTests(SimpleTestCase):
    BASE = {"data_source": "newest", "item_limit": 8, "display_mode": "carousel"}

    def test_defaults_gain_no_new_keys(self):
        cleaned = sr._validate_product_section_settings(dict(self.BASE))
        for key in ("tabs_source", "tabs_count", "tabs_style", "row_backdrop", "heading_icon", "heading_style"):
            self.assertNotIn(key, cleaned)

    def test_tabs_glow_and_heading_styles_are_sparse_and_closed(self):
        cleaned = sr._validate_product_section_settings({
            **self.BASE, "tabs_source": "categories", "tabs_count": 99, "tabs_style": "pills", "row_backdrop": "glow",
            "heading_style": "icon_chip", "heading_icon": "fire",
        })
        self.assertEqual((cleaned["tabs_source"], cleaned["tabs_count"], cleaned["tabs_style"]), ("categories", 6, "pills"))
        self.assertEqual((cleaned["row_backdrop"], cleaned["heading_style"], cleaned["heading_icon"]), ("glow", "icon_chip", "fire"))
        junk = sr._validate_product_section_settings({**self.BASE, "tabs_source": "x", "row_backdrop": "x", "heading_style": "x",
                                                      "heading_icon": "nope"})
        for key in ("tabs_source", "row_backdrop", "heading_style", "heading_icon"):
            self.assertNotIn(key, junk)
        self.assertEqual(sr._validate_product_section_settings({**self.BASE, "heading_icon": "fire"})["heading_icon"], "fire")


class HeaderBlockTests(SimpleTestCase):
    def test_the_category_menu_block_is_a_registered_validated_block(self):
        from apps.storefront_builder.services import layout_service

        cleaned = layout_service.validate_header_config({"extra_blocks": [{"type": "category_menu"}, {"type": "spacer"}]})
        self.assertEqual([b["type"] for b in cleaned["extra_blocks"]], ["category_menu", "spacer"])
        with self.assertRaises(layout_service.HeaderConfigValidationError):
            layout_service.validate_header_config({"extra_blocks": [{"type": "freeform_html"}]})
        self.assertEqual(lpr.get_layout_preset("rose_beauty_store").header["extra_blocks"], [{"type": "category_menu"}])


class StrandedStoreFixture(TestCase):
    """A throw-away Store with real catalogue data (one shared helper for the data-backed tests below)."""

    @classmethod
    def setUpTestData(cls):
        cls.store, cls.owner, cls.products = rc.seed_store("lilikacosmetics", image_mode="none", preset_key=None, host=HOST)
        from apps.catalog.models import Category
        from apps.stores.models import Store

        cls.other = Store.objects.create(name="دیگر", slug="six-other", status=Store.Status.ACTIVE)
        Category.objects.create(store=cls.other, name="دسته بیگانه", slug="alien-cat", is_active=True)


class TabsResolverTests(StrandedStoreFixture):
    def test_category_and_subcategory_tabs_use_only_this_stores_real_categories(self):
        base = {"item_limit": 8, "tabs_count": 6}
        tabs = section_data_service.resolve_product_tabs(self.store, {**base, "tabs_source": "categories"})
        labels = [t["label"] for t in tabs]
        self.assertGreaterEqual(len(tabs), 2)
        self.assertNotIn("دسته بیگانه", labels)
        self.assertTrue(all(t["products"] and all(p.store_id == self.store.pk for p in t["products"]) for t in tabs))
        subs = section_data_service.resolve_product_tabs(self.store, {**base, "tabs_source": "subcategories"})
        self.assertTrue(set(t["label"] for t in subs) <= {"آرایش صورت", "آرایش لب", "ابزار آرایشی", "آرایش چشم"})

    def test_a_foreign_store_gets_no_tabs_and_one_usable_tab_falls_back_to_a_single_row(self):
        self.assertEqual(section_data_service.resolve_product_tabs(self.other, {"item_limit": 8, "tabs_source": "categories"}), [])
        self.assertEqual(section_data_service.resolve_product_tabs(self.store, {"item_limit": 8, "tabs_source": "categories", "tabs_count": 2})[:0], [])

    def test_the_subcategories_selection_mode_is_a_closed_registered_mode(self):
        from apps.storefront_builder.services.category_selection import CATEGORY_SOURCE_MODES

        self.assertIn("subcategories", CATEGORY_SOURCE_MODES)
        picked = select_categories(self.store, "subcategories")
        self.assertTrue(picked and all(c.parent_id for c in picked))
        self.assertEqual(select_categories(self.other, "subcategories"), [])


class SectionPrimitiveTests(SimpleTestCase):
    def test_new_category_display_modes_and_card_styles_and_layouts_are_registered(self):
        for mode in ("icon_rail", "ring_circles", "photo_cards"):
            self.assertIn(mode, sr.CATEGORY_GRID_DISPLAY_MODES)
        for style in ("gallery_pink", "campaign_round", "cocoa_gift"):
            self.assertIn(style, sr.CARD_STYLE_CHOICES)
        for layout in ("duo-round", "trio-round", "people-4", "mosaic-5", "panel-4"):
            self.assertIn(layout, sr.MULTI_BANNER_KNOWN_LAYOUT_VARIANTS)
            self.assertIn(layout, sr.MULTI_BANNER_LAYOUT_VARIANT_LABELS_FA)

    def test_hero_slider_options_are_sparse_and_closed(self):
        base = sr._validate_slider_settings({})
        for key in ("slider_ratio", "slider_ratio_mobile", "slider_width"):
            self.assertNotIn(key, base)
        cleaned = sr._validate_slider_settings({"slider_ratio": "2.5", "slider_ratio_mobile": "1.78", "slider_width": "full"})
        self.assertEqual((cleaned["slider_ratio"], cleaned["slider_ratio_mobile"], cleaned["slider_width"]), ("2.5", "1.78", "full"))
        bad = sr._validate_slider_settings({"slider_ratio": "9", "slider_ratio_mobile": "x", "slider_width": "wide"})
        for key in ("slider_ratio", "slider_ratio_mobile", "slider_width"):
            self.assertNotIn(key, bad)

    def test_call_to_action_strip_gradient_and_button(self):
        cleaned = sr._validate_decorative_strip_settings({
            "optional_text": "متن", "link_url": "/products/", "button_label": "مشاهده", "gradient_to": "token:tone-4",
            "background_color": "#0E0E0E",
        })
        view = decorative_strip.build_view(cleaned)
        self.assertEqual(view["button"], "مشاهده")
        self.assertTrue(view["gradient"])
        self.assertIn("--ds-bg2:", view["style"])
        plain = decorative_strip.build_view(sr._validate_decorative_strip_settings({"optional_text": "متن"}))
        self.assertEqual(plain["button"], "")
        self.assertFalse(plain["gradient"])

    def test_blog_image_text_multi_banner_and_video_validators(self):
        self.assertEqual(sr.validate_blog_posts_settings({"style": "editorial_cards"})["style"], "editorial_cards")
        self.assertNotIn("style", sr.validate_blog_posts_settings({"style": "nope"}))
        rows = sr._validate_image_text_settings({"feature_items": [
            {"icon": "award", "title": "الف", "text": "ب"}, {"icon": "bad", "title": "ج"}, {"title": ""}, "x"]})["feature_items"]
        self.assertEqual([r["icon"] for r in rows], ["award", ""])
        self.assertNotIn("feature_items", sr._validate_image_text_settings({"title": "t"}))
        banner = sr._validate_multi_banner_settings({"title": "عنوان", "heading_icon": "headset", "layout_variant": "people-4"})
        self.assertEqual((banner["title"], banner["heading_icon"]), ("عنوان", "headset"))
        self.assertNotIn("title", sr._validate_multi_banner_settings({"layout_variant": "people-4"}))
        video = sr._validate_video_section_settings({"title": "t", "videos": [
            {"url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "الف"}, {"url": ""}]})
        self.assertEqual(len(video["videos"]), 1)
        with self.assertRaises(sr.VideoSectionSettingsError):
            sr._validate_video_section_settings({"videos": [{"url": "https://example.com/not-a-video"}]})
        self.assertNotIn("videos", sr._validate_video_section_settings({"title": "t"}))

    def test_cta_tone_is_a_closed_palette_role_and_default_writes_no_attribute(self):
        view = pdp_settings.resolve_product_main_view({"cta_tone": "secondary"})
        self.assertIn(("cta-tone", "secondary"), view["attrs"])
        self.assertNotIn("cta-tone", [name for name, _v in pdp_settings.resolve_product_main_view({})["attrs"]])
        self.assertEqual(pdp_settings.clean_product_main_settings({"cta_tone": "neon"})["cta_tone"], "primary")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SixTemplatesRenderTests(TestCase):
    """Install each template on its own Store through the canonical path, publish, and render Home + product page."""

    def test_each_template_installs_publishes_and_renders_home_and_pdp(self):
        from apps.stores.models import Store, StoreDomain

        for index, (key, (site, _palette)) in enumerate(SIX.items()):
            with self.subTest(key=key):
                StoreDomain.objects.filter(hostname=HOST).delete()
                Store.objects.filter(slug=f"cap-{site.lower()}").delete()
                store, _owner, products = rc.seed_store(site, image_mode="none", preset_key=key, host=HOST)
                with rc.patched_best_sellers(products):
                    home = self.client.get("/", HTTP_HOST=HOST)
                    pdp = self.client.get(reverse("catalog:product-detail", args=[products[0].slug]), HTTP_HOST=HOST)
                self.assertEqual(home.status_code, 200, key)
                self.assertEqual(pdp.status_code, 200, key)
                html = home.content.decode()
                self.assertIn("data-sfb-template", html)
                self.assertNotIn("Traceback", html)
                # Store scoping: nothing of any other Store's data leaks into this page.
                self.assertTrue(all(p.store_id == store.pk for p in products))
                self.assertEqual(Decimal(products[0].price), Decimal(products[0].price))

    def test_installing_a_template_never_changes_catalogue_data(self):
        from apps.catalog.models import Category, Product
        from apps.stores.models import Store, StoreDomain

        StoreDomain.objects.filter(hostname=HOST).delete()
        Store.objects.filter(slug="cap-lilikacosmetics").delete()
        store, _owner, products = rc.seed_store("lilikacosmetics", image_mode="none", preset_key=None, host=HOST)
        before = (
            list(Product.objects.filter(store=store).order_by("pk").values_list("pk", "name", "price", "stock")),
            list(Category.objects.filter(store=store).order_by("pk").values_list("pk", "name", "parent_id")),
        )
        from apps.storefront_builder.services import layout_service, preset_service

        draft = layout_service.get_or_create_draft(store, user=_owner)
        layout_service.get_or_create_layout(store)
        for key in SIX:
            preset_service.apply_preset(draft, lpr.get_layout_preset(key))
        layout_service.publish(store)
        after = (
            list(Product.objects.filter(store=store).order_by("pk").values_list("pk", "name", "price", "stock")),
            list(Category.objects.filter(store=store).order_by("pk").values_list("pk", "name", "parent_id")),
        )
        self.assertEqual(before, after)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class CandidatePreviewContextTests(TestCase):
    """Two unsaved instances of one section key (the gallery live preview) must never share one cached context."""

    def test_two_unsaved_banner_rows_with_different_offsets_show_different_banners(self):
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import render_service
        from apps.stores.models import StoreDomain

        StoreDomain.objects.filter(hostname=HOST).delete()
        store, _owner, _products = rc.seed_store("AsalBanoo", image_mode="none", preset_key=None, host=HOST)
        first = StorefrontSection(section_key="multi_banner", settings={"item_limit": 2, "offset": 0, "layout_variant": "duo-round"})
        second = StorefrontSection(section_key="multi_banner", settings={"item_limit": 2, "offset": 2, "layout_variant": "duo-round"})
        items = render_service.build_candidate_render_items([first, second], store)
        a, b = ([x.pk for x in item["context"]["banners"]] for item in items)
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 2)
        self.assertFalse(set(a) & set(b), (a, b))

    def test_an_unsaved_linked_image_renders_nothing_instead_of_failing(self):
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import render_service
        from apps.stores.models import StoreDomain

        StoreDomain.objects.filter(hostname=HOST).delete()
        store, _owner, _products = rc.seed_store("AsalBanoo", image_mode="none", preset_key=None, host=HOST)
        items = render_service.build_candidate_render_items([StorefrontSection(section_key="linked_image", settings={})], store)
        self.assertEqual(list(items[0]["context"]["banners"]), [])


from .test_r4_mutation_api import R4MutationApiTestCase  # noqa: E402
from ._gallery_support import gallery_cards_by_key, studio_gallery_response  # noqa: E402


class GalleryAndInspectorTests(R4MutationApiTestCase):
    """The six templates are selectable in the Design Studio gallery and every Section they install is editable in the Inspector."""

    def test_the_six_templates_are_gallery_cards(self):
        response = studio_gallery_response(self.client)
        self.assertEqual(response.status_code, 200)
        cards = gallery_cards_by_key(response)
        for key in SIX:
            with self.subTest(key=key):
                self.assertIn(key, cards)
                self.assertTrue(cards[key]["preset"].label_fa)

    def test_every_installed_section_opens_in_the_inspector_and_accepts_a_real_edit(self):
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import preset_service

        for key in SIX:
            with self.subTest(key=key):
                preset_service.apply_preset(self.draft, lpr.get_layout_preset(key))
                sections = list(StorefrontSection.objects.filter(page__version=self.draft).order_by("page__page_type", "order"))
                self.assertGreater(len(sections), 3)
                for section in sections:
                    if not sr.get_definition(section.section_key).settings_schema:
                        continue  # cart / listing system sections have no Inspector form by design
                    response = self.client.get(reverse("dashboard:storefront-builder-r4-section-inspector", args=[section.pk]))
                    self.assertEqual(response.status_code, 200, (key, section.section_key))
                rows = [s for s in sections if s.section_key == "product_section"]
                if rows:
                    self.draft.refresh_from_db()
                    response = self._post_json({"base_revision": self.draft.edit_revision, "mutation": {
                        "type": "section.update_settings", "section_id": rows[0].pk, "patch": {"title": "عنوان ویرایش‌شده"}}})
                    self.assertEqual(response.status_code, 200, (key, response.content))
                    rows[0].refresh_from_db()
                    self.assertEqual(rows[0].settings["title"], "عنوان ویرایش‌شده")
