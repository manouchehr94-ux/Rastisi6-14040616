"""V5 six-site kit — the generic engine primitives added for Ready Templates 54-59.

Every primitive here is reusable by any Store (no template key anywhere): fonts, the global heading style, the wider content width,
the announcement strip's height, the floating widgets, the call-to-action strip, the product row «more» link, the carousel on
related products, the photo-first category tiles, the clean hero slider, the floating-card header, the centred-contact footer and the
two card styles. Each one is exercised through the real validation / mutation / render path."""

import json
import re
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.storefront_builder import appearance_registry, global_region_registry, section_registry, shell_geometry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service, r4_mutation_service, section_structure_service

from .test_media_views import HOST, MediaViewsTestCase

APP = Path(__file__).resolve().parents[1]
CORE_STATIC = APP.parent / "core" / "static"
HOME = StorefrontPage.PageType.HOME
PDP = StorefrontPage.PageType.PRODUCT_DETAIL


class FontsTests(SimpleTestCase):
    FONTS = {"Estedad": "Estedad", "Noto Sans Arabic": "NotoSansArabic", "Lalezar": "Lalezar"}

    def test_every_new_font_is_a_valid_choice_with_a_label_a_licence_and_font_files(self):
        from apps.storefront_builder.templatetags.storefront_builder_extras import rs_font_label

        css = (CORE_STATIC / "css" / "base.css").read_text(encoding="utf-8")
        for family, stem in self.FONTS.items():
            with self.subTest(family=family):
                self.assertIn(family, appearance_registry.FONT_CHOICES)
                self.assertNotEqual(rs_font_label(family), family)
                self.assertTrue(list((CORE_STATIC / "fonts").glob(f"{stem}-*")), "bundled woff2 files")
                self.assertTrue((CORE_STATIC / "fonts" / "licenses" / f"{stem}-OFL.txt").exists(), "OFL licence text ships with the font")
                self.assertRegex(css, r"@font-face\{font-family:'%s';" % re.escape(family))
        for family in self.FONTS:
            blocks = re.findall(r"@font-face\{font-family:'%s';[^}]*\}" % re.escape(family), css)
            self.assertEqual(len(blocks), 2, "one arabic and one latin subset per family")
            self.assertTrue(all("unicode-range" in block for block in blocks), "unused subsets are never fetched")

    def test_the_font_is_validated_by_the_one_appearance_validator(self):
        cleaned = layout_service.validate_appearance_config({"font": "Estedad"})
        self.assertEqual(cleaned["font"], "Estedad")
        with self.assertRaises(layout_service.AppearanceConfigValidationError):
            layout_service.validate_appearance_config({"font": "Comic Sans"})


class HeadingStyleTests(MediaViewsTestCase):
    def _post(self, patch):
        self.draft.refresh_from_db()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": self.draft.edit_revision,
                             "mutation": {"type": "appearance.update", "draft_id": self.draft.pk, "patch": patch}}),
            content_type="application/json",
        )

    def _history(self, command):
        self.draft.refresh_from_db()
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps({"base_revision": self.draft.edit_revision, "command": command}), content_type="application/json")

    def test_sparse_validation_default_is_never_stored_and_unknown_is_refused(self):
        self.assertNotIn("heading_style", layout_service.validate_appearance_config({}))
        self.assertNotIn("heading_style", layout_service.validate_appearance_config({"heading_style": "default"}))
        self.assertEqual(layout_service.validate_appearance_config({"heading_style": "centered_rule"})["heading_style"], "centered_rule")
        with self.assertRaises(layout_service.AppearanceConfigValidationError):
            layout_service.validate_appearance_config({"heading_style": "sparkly"})

    def test_through_the_one_mutation_path_with_undo_and_redo(self):
        start = self.draft.edit_revision
        response = self._post({"heading_style": "centered_rule"})
        self.assertEqual(response.status_code, 200, response.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, start + 1)
        self.assertEqual(self.draft.appearance_config.get("heading_style"), "centered_rule")
        self.assertEqual(self._history("undo").status_code, 200)
        self.draft.refresh_from_db()
        self.assertNotIn("heading_style", self.draft.appearance_config)
        self.assertEqual(self._history("redo").status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.appearance_config.get("heading_style"), "centered_rule")
        self.assertEqual(self._post({"heading_style": "sparkly"}).status_code, 400)
        self.assertEqual(self._post({"heading_style": "default"}).status_code, 200)
        self.draft.refresh_from_db()
        self.assertNotIn("heading_style", self.draft.appearance_config, "choosing the default again returns to the exact historical shape")

    def test_the_html_attribute_exists_only_for_a_non_default_style_and_css_covers_every_value(self):
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        for value in appearance_registry.SITE_HEADING_STYLE_CHOICES:
            if value != "default":
                self.assertIn(f'html[data-sfb-heading="{value}"]', css, value)
        base = (APP.parents[1] / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("{% if SHOP_HEADING_STYLE and SHOP_HEADING_STYLE != 'default' %}", base)

    def test_wider_content_width_is_a_registered_choice(self):
        self.assertIn(1800, appearance_registry.SITE_CONTENT_WIDTH_CHOICES)
        self.assertEqual(layout_service.validate_appearance_config({"content_width": 1800})["content_width"], 1800)


class AnnouncementAndFloatingTests(MediaViewsTestCase):
    def test_announcement_height_and_image_clamps(self):
        for key, high in (("announce_height", 120), ("announce_image_size", 64)):
            prop = shell_geometry.SHELL_GEOMETRY[("header", key)]
            self.assertEqual(prop.max_value, high)
        cleaned = shell_geometry.validate_geometry({"announce_height": 500, "announce_image_size": 9}, "header")
        self.assertEqual(cleaned, {"announce_height": 120, "announce_image_size": 16})

    def test_floating_widgets_are_sparse_validated_and_default_to_nothing(self):
        self.assertFalse({k for k in layout_service.validate_footer_config({}) if k.startswith("floating")})
        cleaned = layout_service.validate_footer_config({"floating_whatsapp": True, "floating_position": "start"})
        self.assertEqual((cleaned["floating_whatsapp"], cleaned["floating_position"]), (True, "start"))
        self.assertNotIn("floating_position", layout_service.validate_footer_config({"floating_position": "start"}), "no widget on: nothing stored")
        for bad in ({"floating_phone": "yes"}, {"floating_position": "middle"}):
            with self.subTest(bad=bad), self.assertRaises(layout_service.FooterConfigValidationError):
                layout_service.validate_footer_config(bad)

    def test_footer_update_mutation_and_render_use_the_stores_own_data_only(self):
        from apps.content.models import SocialLink

        r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=self.draft.edit_revision,
            mutation={"type": "footer.update", "patch": {"floating_whatsapp": True, "floating_back_to_top": True}},
        )
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.footer_config["floating_whatsapp"])
        html = self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()
        self.assertIn("sfb-floating-top", html, "back-to-top carries no data of its own")
        self.assertNotIn("sfb-floating-whatsapp", html, "no WhatsApp link configured: the widget is not invented")
        SocialLink.objects.create(store=self.store, platform=SocialLink.Platform.WHATSAPP, title="واتساپ", url="https://wa.me/989120000000",
                                  is_active=True, show_in_footer=True)
        cache.clear()
        html = self.client.get(reverse("dashboard:storefront-builder-preview")).content.decode()
        self.assertIn('href="https://wa.me/989120000000"', html)
        with self.assertRaises(r4_mutation_service.R4MutationError):
            r4_mutation_service.apply_mutation(
                store=self.store, actor=self.staff, base_revision=self.draft.edit_revision + 1 if False else self._rev(),
                mutation={"type": "footer.update", "patch": {"floating_position": "middle"}},
            )

    def _rev(self):
        self.draft.refresh_from_db()
        return self.draft.edit_revision


class SectionPrimitiveTests(SimpleTestCase):
    def test_decorative_strip_link_icon_and_size_are_validated(self):
        validate = section_registry._validate_decorative_strip_settings
        cleaned = validate({"optional_text": "x", "link_url": "https://example.com/a", "icon": "instagram", "text_size": 24})
        self.assertEqual((cleaned["link_url"], cleaned["icon"], cleaned["text_size"]), ("https://example.com/a", "instagram", 24))
        self.assertEqual(validate({"link_url": "#", "icon": ""}), {"link_url": "#"})
        self.assertEqual(validate({"link_url": "/products/", "text_size": 999})["text_size"], 48)
        for bad in ("javascript:alert(1)", "//evil.test", "data:text/html,x", "ftp://x"):
            with self.subTest(bad=bad), self.assertRaises(section_registry.DecorativeStripSettingsError):
                validate({"link_url": bad})
        self.assertNotIn("icon", validate({"icon": "<script>"}), "an unknown icon falls back to none")

    def test_decorative_strip_renders_one_anchor_only_with_a_link(self):
        from django.template.loader import render_to_string

        from apps.storefront_builder import decorative_strip

        plain = render_to_string("storefront_builder/sections/decorative_strip.html",
                                 {"strip": decorative_strip.build_view({"optional_text": "متن"})})
        self.assertNotIn("<a ", plain)
        linked = render_to_string("storefront_builder/sections/decorative_strip.html",
                                  {"strip": decorative_strip.build_view({"optional_text": "متن", "link_url": "https://example.com/", "icon": "instagram"})})
        self.assertEqual(linked.count("<a "), 1)
        self.assertIn('rel="noopener noreferrer"', linked)
        self.assertIn("decor-strip-icon", linked)

    def test_product_section_view_all_placement_is_sparse(self):
        validate = section_registry.get_definition("product_section").validate_settings
        base = {"data_source": "newest", "display_mode": "carousel", "item_limit": 6}
        self.assertNotIn("view_all_placement", validate(dict(base)))
        self.assertEqual(validate({**base, "view_all_placement": "bottom"})["view_all_placement"], "bottom")
        self.assertNotIn("view_all_placement", validate({**base, "view_all_placement": "elsewhere"}))

    def test_related_products_gained_a_small_schema_and_stays_passthrough_otherwise(self):
        definition = section_registry.get_definition("related_products")
        self.assertEqual({f.key for f in definition.settings_schema.fields if f.key in {"title", "display_mode", "carousel_navigation"}},
                         {"title", "display_mode", "carousel_navigation"})
        cleaned = definition.validate_settings({"card": {"card_style": "outline_plain"}, "display_mode": "grid", "carousel_navigation": "bogus", "title": "  مشابه  "})
        self.assertEqual(cleaned["title"], "مشابه")
        self.assertEqual(cleaned["card"]["card_style"], "outline_plain", "the shared card block is validated by its own capability, not dropped")
        self.assertNotIn("display_mode", cleaned)
        self.assertNotIn("carousel_navigation", cleaned)
        self.assertEqual(definition.validate_settings({"display_mode": "carousel", "carousel_navigation": "arrows"})["display_mode"], "carousel")

    def test_new_vocabulary_is_registered_once(self):
        self.assertIn("label_tiles", section_registry.CATEGORY_GRID_DISPLAY_MODES)
        self.assertIn("clean_slider", section_registry.HERO_STYLE_CHOICES)
        for style in ("lifestyle_cart", "outline_plain"):
            self.assertIn(style, section_registry.CARD_STYLE_CHOICES)
            self.assertEqual(section_registry.validate_card_settings({"card_style": style})["card_style"], style)
        for key in ("floating_card",):
            self.assertIn(key, {v.key for v in global_region_registry.GLOBAL_HEADER_REGION.variants})
        self.assertIn("centered_contact", {v.key for v in global_region_registry.GLOBAL_FOOTER_REGION.variants})

    def test_floating_card_header_geometry_is_variant_scoped(self):
        keys = {p.key for p in shell_geometry.properties_for("header", "floating_card")}
        self.assertTrue({"card_height", "card_radius", "band_height", "band_fill", "logo_height", "announce_bg"} <= keys)
        self.assertFalse({"card_height", "logo_height"} & {p.key for p in shell_geometry.properties_for("header", "legacy_default")})


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class RenderedPrimitivesTests(MediaViewsTestCase):
    def _add(self, key, page_type=HOME, **settings):
        section = section_structure_service.add_section(draft=self.draft, section_key=key, page_type=page_type)
        if settings:
            section.settings = {**(section.settings or {}), **settings}
            section.save(update_fields=["settings"])
        return section

    def _preview(self, page="home"):
        cache.clear()
        response = self.client.get(reverse("dashboard:storefront-builder-preview") + f"?page={page}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_label_tiles_render_the_label_bar_and_the_clean_slider_has_no_text_layer(self):
        from apps.catalog.models import Category

        Category.objects.create(store=self.store, name="سنگی", slug="stone-kit", is_active=True)
        self.draft.get_page(HOME).sections.all().delete()
        self._add("category_grid", display_mode="label_tiles", title="دسته‌ها")
        html = self._preview()
        self.assertIn("category-label-tiles-section", html)
        self.assertIn('class="category-label-bar">سنگی', html)

    def test_product_row_more_link_and_cta_card_style_render(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="v", slug="v-kit")
        category = Category.objects.create(store=self.store, name="c", slug="c-kit")
        Product.objects.create(store=self.store, vendor=vendor, category=category, name="کالا", slug="p-kit", sku="K1", price=Decimal("1000"),
                               stock=5, status=Product.Status.ACTIVE)
        self.draft.get_page(HOME).sections.all().delete()
        self._add("product_section", data_source="newest", display_mode="grid", item_limit=4, show_view_all=True,
                  view_all_placement="bottom", card={"card_style": "lifestyle_cart"})
        html = self._preview()
        self.assertIn("product-more-link", html)
        self.assertNotIn('class="btn btn-sm">مشاهده همه', html, "the heading button is replaced by the bottom link")
        self.assertIn("pcard-cta-btn", html)
        self.assertNotIn('class="addbar"', html, "a footer-CTA card style never also renders the hover add-bar")

    def test_related_products_carousel_uses_the_shared_row(self):
        self.assertEqual(
            (APP / "templates" / "storefront_builder" / "sections" / "related_products.html").read_text(encoding="utf-8").count("product_row.html"), 1)
        row = (APP / "templates" / "storefront_builder" / "partials" / "product_row.html").read_text(encoding="utf-8")
        self.assertIn("pcarousel-shell", row)
        section = (APP / "templates" / "storefront_builder" / "sections" / "product_section.html").read_text(encoding="utf-8")
        self.assertIn("product_row.html", section)
        self.assertNotIn("pcarousel-shell", section, "the row implementation lives in ONE partial")
