"""V5 — «عکس لینک‌دار» (a section: ONE own picture + optional link) and the header «نوار اطلاعیه» (text + small picture + optional link).

Both ride the single R4 engine: the picture of a linked image is the section-scoped PromotionalBanner row of the canonical media CRUD (store-scoped
MediaAsset), its link that row's DestinationMixin; the announcement strip is the header's own sparse ``header_config`` written only by ``header.update``.
No second engine, no new table, no migration."""

import json
import re
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse
from PIL import Image

from decimal import Decimal

from apps.catalog.models import Category, MerchantCollection, Product, Vendor
from apps.content import media_reachability
from apps.content.models import MediaAsset, PromotionalBanner
from apps.storefront_builder import design_block, global_region_registry, section_registry, shell_geometry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service, r4_mutation_service
from apps.stores.models import Store

from .test_media_views import MediaViewsTestCase, _img

STATIC = Path(__file__).resolve().parents[1] / "static" / "storefront_builder"


def _png(name="small.png", size=(40, 40)):
    buf = BytesIO()
    Image.new("RGB", size, (200, 10, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class _LinkedBase(MediaViewsTestCase):
    def _section(self, order=910):
        return StorefrontSection.objects.create(version=self.draft, section_key="linked_image", order=order)

    def _add(self, section, **extra):
        data = {"title": "توصیف تصویر", "destination_type": "none", "desktop_image": _img(), "is_active": "on", **extra}
        return self.client.post(reverse("dashboard:storefront-builder-section-media-add", args=[section.pk, "banners"]), data)

    def _preview(self, page="home"):
        return self.client.get(reverse("dashboard:storefront-builder-preview") + f"?page={page}").content.decode()

    def _section_html(self, html, section):
        """The rendered linked-image body of ONE section (its ``<section class="section linked-image">`` element)."""
        start = html.index(f'data-section-id="{section.pk}"')
        body = re.search(r'<section class="section linked-image.*?</section>', html[start:], re.S)
        return body.group(0) if body else ""


class LinkedImageRegistryTests(_LinkedBase):
    def test_it_is_a_library_section_with_the_shared_contracts_and_no_frame_or_copy(self):
        definition = section_registry.get_definition("linked_image")
        self.assertEqual(definition.label_fa, "عکس لینک‌دار")
        self.assertFalse(definition.hidden_from_library)
        self.assertEqual(definition.category_fa, "تصاویر و تبلیغات")
        self.assertTrue(definition.duplicable)
        for capability in ("design_image_fit", "design_image_position", "design_frame", "canvas_size", "layout_width"):
            self.assertIn(capability, definition.capabilities)
        self.assertNotIn("background", definition.capabilities)                       # no promotional frame / panel
        self.assertEqual([f.key for f in definition.settings_schema.fields], ["design"])   # no title / text / button field at all
        groups = {key for group in section_registry.list_library_groups("home") for key in (d.key for d in group[1])}
        self.assertIn("linked_image", groups)

    def test_the_old_announcement_bar_section_is_untouched_and_still_hidden(self):
        definition = section_registry.get_definition("announcement_bar")
        self.assertTrue(definition.hidden_from_library)
        self.assertEqual(definition.max_instances, 1)


class LinkedImageMediaTests(_LinkedBase):
    def test_one_own_picture_per_section_through_the_canonical_media_crud(self):
        section = self._section()
        self.assertEqual(self._add(section, destination_type="cart").status_code, 302)
        banner = PromotionalBanner.objects.get(section=section)
        self.assertEqual((banner.store_id, banner.title, banner.destination_type), (self.store.pk, "توصیف تصویر", "cart"))
        self.assertIsNotNone(banner.desktop_asset_id)                                   # a store-scoped MediaAsset, not raw JSON bytes
        self.assertEqual(MediaAsset.objects.get(pk=banner.desktop_asset_id).store_id, self.store.pk)
        # a second picture is refused (UI hides «افزودن»; the server refuses a tampered request) and nothing is written
        refused = self._add(section)
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(PromotionalBanner.objects.filter(section=section).count(), 1)

    def test_the_form_asks_only_for_alt_picture_and_link_and_the_manager_names_the_limit(self):
        section = self._section()
        form = self.client.get(reverse("dashboard:storefront-builder-section-media-add", args=[section.pk, "banners"]), HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1").content.decode()
        self.assertIn("متن جایگزین تصویر (Alt)", form)
        for forbidden in ('name="show_button"', 'name="button_label"', 'name="description"'):
            self.assertNotIn(forbidden, form)
        self._add(section)
        manager = self.client.get(reverse("dashboard:storefront-builder-section-media-list", args=[section.pk, "banners"]),
                                  HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1").content.decode()
        self.assertIn("فقط یک تصویر دارد", manager)
        self.assertNotIn("+ افزودن", manager)                                                   # no add button once the one picture exists

    def test_store_wide_default_banners_are_never_shown_or_adopted(self):
        PromotionalBanner.objects.create(store=self.store, title="بنر سراسری فروشگاه", description="x", section=None, is_active=True,
                                         desktop_image=_img("wide.png"))
        section = self._section()
        manager = self.client.get(reverse("dashboard:storefront-builder-section-media-list", args=[section.pk, "banners"]),
                                  HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1").content.decode()
        self.assertNotIn("data-r4-media-defaults", manager)
        self.assertNotIn("بنر سراسری فروشگاه", manager)
        adopt = self.client.post(reverse("dashboard:storefront-builder-section-media-adopt-defaults", args=[section.pk, "banners"]))
        self.assertEqual(adopt.status_code, 404)
        self.assertEqual(PromotionalBanner.objects.filter(section=section).count(), 0)

    def test_a_dangerous_link_is_refused_and_nothing_is_saved(self):
        section = self._section()
        self._add(section, destination_type="external", destination_external_url="javascript:alert(1)")
        self.assertEqual(PromotionalBanner.objects.filter(section=section).count(), 0)

    def test_another_stores_media_endpoints_cannot_touch_this_section(self):
        other = Store.objects.create(name="فروشگاه دیگر", slug="linked-other", admin_subdomain="linked-other", status=Store.Status.ACTIVE)
        foreign_layout = layout_service.get_or_create_draft(other)
        foreign = StorefrontSection.objects.create(version=foreign_layout, section_key="linked_image", order=1)
        refused = self.client.post(reverse("dashboard:storefront-builder-section-media-add", args=[foreign.pk, "banners"]),
                                   {"title": "x", "destination_type": "none", "desktop_image": _img(), "is_active": "on"})
        self.assertIn(refused.status_code, (403, 404))
        self.assertEqual(PromotionalBanner.objects.filter(section=foreign).count(), 0)


class LinkedImageRenderTests(_LinkedBase):
    def test_published_linked_picture_is_one_anchor_around_the_image_with_safe_new_tab_attributes(self):
        section = self._section()
        self._add(section, destination_type="external", destination_external_url="https://www.instagram.com/rastisi_shop/", open_in_new_tab="on")
        banner = PromotionalBanner.objects.get(section=section)
        html = render_to_string("storefront_builder/sections/linked_image.html", {"banners": [banner], "is_builder_preview": False})
        self.assertRegex(html, r'<a class="linked-image-frame" href="https://www\.instagram\.com/rastisi_shop/" target="_blank" rel="noopener noreferrer"')
        self.assertRegex(html, r'(?s)<a class="linked-image-frame"[^>]*>\s*<picture>.*?<img class="linked-image-img"[^>]*alt="توصیف تصویر"')
        self.assertNotIn("promo-dark", html)
        self.assertIn('loading="lazy"', html)
        self.assertEqual(len(re.findall(r"<a\b", html)), 1)                                   # never nested / duplicated links
        for copy in ("<h3", "<button", "btn ", "data-admin", "placeholder"):
            self.assertNotIn(copy, html)

    def test_builder_preview_keeps_the_picture_selectable_a_link_without_href(self):
        section = self._section()
        self._add(section, destination_type="external", destination_external_url="https://www.instagram.com/rastisi_shop/", open_in_new_tab="on")
        html = self._section_html(self._preview(), section)
        # the Studio never selects through an <a href> (a click on a link is the storefront's own) — so the preview frame has no href
        self.assertIn('data-linked-href="https://www.instagram.com/rastisi_shop/"', html)
        self.assertNotRegex(html, r"<a\b[^>]*\shref=")
        self.assertNotIn("data-admin-edit", html)
        self.assertIn('loading="eager"', html)                                                  # no collapsed first layout in a refreshed preview

    def test_every_internal_destination_resolves_to_this_stores_own_page(self):
        vendor = Vendor.objects.create(store=self.store, name="فروشنده لینک", slug="v-linked")
        category = Category.objects.create(store=self.store, name="دستهٔ لینک", slug="c-linked", is_active=True)
        collection = MerchantCollection.objects.create(store=self.store, name="مجموعهٔ لینک", slug="col-linked")
        product = Product.objects.create(store=self.store, vendor=vendor, category=category, name="کالای لینک", slug="p-linked", sku="SKU-LINKED",
                                         price=Decimal("10000"), stock=5, status=Product.Status.ACTIVE)
        cases = (("category", {"destination_category": category.pk}, "c-linked"), ("collection", {"destination_collection": collection.pk}, "col-linked"),
                 ("product", {"destination_product": product.pk}, "p-linked"))
        for order, (kind, extra, needle) in enumerate(cases, start=920):
            section = self._section(order=order)
            self.assertEqual(self._add(section, destination_type=kind, **extra).status_code, 302, kind)
            banner = PromotionalBanner.objects.get(section=section)
            html = render_to_string("storefront_builder/sections/linked_image.html", {"banners": [banner], "is_builder_preview": False})
            href = re.search(r'<a class="linked-image-frame" href="([^"]+)"', html).group(1)
            self.assertTrue(href.startswith("/"), (kind, href))                                  # this store's own page, never an absolute foreign URL
            self.assertIn(needle, href, kind)
            self.assertNotIn("target=", html)                                                    # internal links open in the same tab
        none = self._section(order=930)
        self._add(none)                                                                            # «بدون لینک»
        banner = PromotionalBanner.objects.get(section=none)
        self.assertNotIn("<a ", render_to_string("storefront_builder/sections/linked_image.html", {"banners": [banner], "is_builder_preview": False}))

    def test_without_a_link_it_is_a_plain_block_with_nothing_clickable(self):
        section = self._section()
        self._add(section)
        html = self._section_html(self._preview(), section)
        self.assertIn('<div class="linked-image-frame"', html)
        self.assertNotIn("<a ", html)
        banner = PromotionalBanner.objects.get(section=section)
        published = render_to_string("storefront_builder/sections/linked_image.html", {"banners": [banner], "is_builder_preview": False})
        self.assertNotIn("<a ", published)

    def test_no_picture_means_a_builder_placeholder_and_nothing_at_all_in_published(self):
        PromotionalBanner.objects.create(store=self.store, title="بنر سراسری فروشگاه", section=None, is_active=True, desktop_image=_img("wide.png"))
        section = self._section()
        html = self._section_html(self._preview(), section)
        self.assertIn("تصویری انتخاب نشده است", html)
        self.assertNotIn("بنر سراسری فروشگاه", html)                                         # never a random / default store banner
        context = {"banners": [], "is_builder_preview": False}
        self.assertEqual(render_to_string("storefront_builder/sections/linked_image.html", context).strip(), "")

    def test_three_cells_each_keep_their_own_picture_and_link(self):
        sections = [self._section(order=920 + i) for i in range(3)]
        self._add(sections[0], title="یک", destination_type="cart")
        self._add(sections[1], title="دو", destination_type="external", destination_external_url="https://example.com/a")
        self._add(sections[2], title="سه")
        html = self._preview()
        parts = [self._section_html(html, s) for s in sections]
        self.assertIn('alt="یک"', parts[0])
        self.assertIn('alt="دو"', parts[1])
        self.assertIn('alt="سه"', parts[2])
        self.assertIn("https://example.com/a", parts[1])
        self.assertNotIn("https://example.com/a", parts[0] + parts[2])
        self.assertIn("/cart/", parts[0])
        sources = [PromotionalBanner.objects.get(section=s).desktop_image_url for s in sections]
        self.assertEqual(len(set(sources)), 3)
        # changing ONE picture's link changes only that row
        PromotionalBanner.objects.filter(section=sections[0]).update(destination_type="external", destination_external_url="https://example.com/z")
        html = self._preview()
        self.assertIn("https://example.com/z", self._section_html(html, sections[0]))
        self.assertNotIn("https://example.com/z", self._section_html(html, sections[1]) + self._section_html(html, sections[2]))

    def test_the_css_keeps_the_natural_ratio_by_default_and_never_hides_part_of_the_picture(self):
        css = (Path(__file__).resolve().parents[1] / "static/css/storefront_builder.css").read_text(encoding="utf-8")
        marker = css.index("V5 «عکس لینک‌دار»")
        start = css.rindex("/*", 0, marker)
        block = css[start:css.index(".linked-image-placeholder strong", start)]
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        self.assertIn("height: auto;", block)
        self.assertIn("object-fit: var(--img-fit, contain);", block)                         # explicit «پر کردن قاب» (cover) is the only cropping
        self.assertNotIn("overflow", block)
        self.assertIn("border-radius: inherit;", block)                                       # the design block's corner radius reaches the picture itself
        self.assertIn(".linked-image-frame", css[css.index(".fashion-hero-inner, .hero-split-inner") - 60:][:300] if ".fashion-hero-inner, .hero-split-inner" in css else css)

    def test_the_visual_resize_contract_applies(self):
        section = self._section()
        self._add(section)
        base = self.draft.edit_revision
        from apps.storefront_builder.services import layout_service as svc

        draft = svc.get_or_create_draft(self.store, user=self.staff)
        revision = r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=draft.edit_revision,
            mutation={"type": "section.resize", "section_id": section.pk, "height": 420, "width": 70, "align": "start"},
        )
        section.refresh_from_db()
        self.assertEqual(section.settings["design"], {"min_height": 420, "width_pct": 70, "width_align": "start"})
        self.assertGreater(revision, base)
        wrapper = re.search(r'<div class="rsec[^>]*data-section-id="%d".*?style="([^"]*)"' % section.pk, self._preview(), re.S).group(1)
        self.assertIn("--d-minh:420px", wrapper.replace(" ", ""))


class AnnouncementConfigTests(_LinkedBase):
    def _header(self, **patch):
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        return r4_mutation_service.apply_mutation(
            store=self.store, actor=self.staff, base_revision=draft.edit_revision,
            mutation={"type": "header.update", "patch": patch},
        )

    def _stored(self):
        return layout_service.get_or_create_draft(self.store, user=self.staff).header_config

    def test_an_untouched_header_stores_and_renders_exactly_what_it_did_before(self):
        cleaned = layout_service.validate_header_config({})
        for key in ("announcement_image_asset_id", "announcement_image_alt", "announcement_image_side", "announcement_link_url",
                    "announcement_link_new_tab", "announcement_align", "announcement_pages"):
            self.assertNotIn(key, cleaned)
        self._header(announcement_enabled=True, announcement_text="ارسال رایگان")
        html = self._preview()
        self.assertIn("<span>ارسال رایگان</span>", html)
        self.assertNotIn("data-ann-x", html)
        self.assertNotIn("ann-main", html)

    def test_validation_refuses_dangerous_or_malformed_values_and_stays_sparse(self):
        bad = [{"announcement_link_url": "javascript:alert(1)"}, {"announcement_link_url": "data:text/html,x"}, {"announcement_link_url": "//evil.example"},
               {"announcement_image_asset_id": "x"}, {"announcement_image_asset_id": True}, {"announcement_image_asset_id": -3},
               {"announcement_align": "left"}, {"announcement_pages": "nowhere"}, {"announcement_image_side": "top"}]
        for patch in bad:
            with self.subTest(patch=patch):
                with self.assertRaises(layout_service.HeaderConfigValidationError):
                    layout_service.validate_header_config(patch)
        ok = layout_service.validate_header_config({"announcement_link_url": "/products/", "announcement_link_new_tab": True, "announcement_image_side": "start",
                                                    "announcement_pages": "all", "announcement_align": ""})
        self.assertEqual((ok["announcement_link_url"], ok["announcement_link_new_tab"]), ("/products/", True))
        for key in ("announcement_image_side", "announcement_pages", "announcement_align"):
            self.assertNotIn(key, ok)

    def test_header_update_accepts_the_new_keys_once_one_revision_and_undoes_in_one_step(self):
        asset = MediaAsset.objects.create(store=self.store, image=_png())
        before = layout_service.get_or_create_draft(self.store, user=self.staff).edit_revision
        revision = self._header(announcement_enabled=True, announcement_text="جشنواره", announcement_image_asset_id=str(asset.pk),
                                announcement_image_alt="نشان", announcement_link_url="https://example.com/sale", announcement_link_new_tab=True,
                                announcement_align="center", announcement_pages="home", geometry={"announce_bg": "token:accent", "announce_image_size": "30"})
        self.assertEqual(revision, before + 1)
        stored = self._stored()
        self.assertEqual((stored["announcement_image_asset_id"], stored["announcement_pages"], stored["announcement_align"]), (asset.pk, "home", "center"))
        self.assertEqual(stored["geometry"]["announce_image_size"], 30)
        response = self.client.post(reverse("dashboard:storefront-builder-r4-history"),
                                    data=json.dumps({"base_revision": revision, "command": "undo"}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("announcement_image_asset_id", self._stored())
        redo = self.client.post(reverse("dashboard:storefront-builder-r4-history"),
                                data=json.dumps({"base_revision": response.json()["new_revision"], "command": "redo"}), content_type="application/json")
        self.assertEqual(redo.status_code, 200, redo.content)
        self.assertEqual(self._stored()["announcement_image_asset_id"], asset.pk)

    def test_the_picture_must_belong_to_this_store(self):
        other = Store.objects.create(name="فروشگاه دیگر", slug="ann-other", admin_subdomain="ann-other", status=Store.Status.ACTIVE)
        foreign = MediaAsset.objects.create(store=other, image=_png("foreign.png"))
        for asset_id in (foreign.pk, 999999):
            with self.subTest(asset=asset_id):
                with self.assertRaises(r4_mutation_service.R4MutationError) as ctx:
                    self._header(announcement_image_asset_id=asset_id)
                self.assertEqual(str(ctx.exception), "invalid_announcement_image")
        self.assertNotIn("announcement_image_asset_id", self._stored())

    def test_a_refused_header_value_says_why_and_changes_nothing(self):
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        response = self.client.post(reverse("dashboard:storefront-builder-r4-mutation"), content_type="application/json",
                                    data=json.dumps({"base_revision": draft.edit_revision, "mutation": {"type": "header.update", "patch": {"announcement_link_url": "javascript:alert(1)"}}}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_header_config")
        self.assertIn("هیچ تغییری ذخیره نشد", response.json()["message"])

    def test_the_asset_is_reachable_so_it_is_never_deleted_while_the_header_uses_it(self):
        asset = MediaAsset.objects.create(store=self.store, image=_png())
        self.assertFalse(media_reachability.is_reachable_via_json_or_snapshots(asset))
        self._header(announcement_image_asset_id=asset.pk)
        self.assertTrue(media_reachability.is_reachable_via_json_or_snapshots(asset))

    def test_geometry_colours_and_size_are_offered_for_every_header_variant(self):
        for variant in global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION):
            keys = {p.key for p in shell_geometry.properties_for("header", variant.key)}
            self.assertTrue({"announce_bg", "announce_fg", "announce_image_size"} <= keys, variant.key)


class AnnouncementRenderTests(AnnouncementConfigTests):
    def _setup_full(self, **extra):
        asset = MediaAsset.objects.create(store=self.store, image=_png("icon.png", (60, 30)))
        patch = {"announcement_enabled": True, "announcement_text": "ارسال رایگان", "announcement_image_asset_id": asset.pk,
                 "announcement_image_alt": "ارسال", "announcement_link_url": "/products/", "announcement_show_phone": False}
        patch.update(extra)
        self._header(**patch)
        return asset

    def test_every_header_variant_renders_exactly_one_extended_strip_above_the_header_without_nested_links(self):
        asset = self._setup_full()
        for variant in global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION):
            with self.subTest(variant=variant.key):
                self._header(header_variant=variant.key)
                html = self._preview()
                self.assertEqual(html.count("data-ann-x"), 1, variant.key)
                strip = html[html.index("data-ann-x"):]
                strip = strip[:strip.index("<header")] if "<header" in strip else strip[:2500]
                self.assertIn('class="ann-main ann-main--link" href="/products/"', strip)
                self.assertIn(asset.image.url, strip)
                self.assertIn('alt="ارسال"', strip)
                main = re.search(r'<a class="ann-main ann-main--link".*?</a>', strip, re.S).group(0)
                self.assertEqual(main.count("<a "), 1)                                        # never an anchor inside the anchor
                self.assertEqual(html.count('class="ann-text"'), 1)

    def test_colours_alignment_and_picture_side_reach_the_strip(self):
        self._setup_full(announcement_align="end", announcement_image_side="end", geometry={"announce_bg": "#102030", "announce_fg": "#fafafa"})
        html = self._preview()
        self.assertRegex(html, r'data-ann-x data-ann-align="end" style="background:#102030;color:#FAFAFA"')
        strip = html[html.index("data-ann-x"):][:1200]
        self.assertLess(strip.index('class="ann-text"'), strip.index('class="ann-img"'))      # picture on the end side of the text

    def test_page_scope_home_only_hides_it_elsewhere_and_all_shows_it_everywhere(self):
        self._setup_full(announcement_pages="home")
        self.assertIn("data-ann-x", self._preview("home"))
        self.assertNotIn("data-ann-x", self._preview("listing"))
        self._header(announcement_pages="all")
        self.assertIn("data-ann-x", self._preview("listing"))

    def test_switching_it_off_removes_the_strip_and_a_foreign_picture_shows_nothing(self):
        self._setup_full()
        self._header(announcement_enabled=False)
        self.assertNotIn("data-ann-x", self._preview())
        self.assertNotIn("announce", re.findall(r'class="(announce[^"]*)"', self._preview())[:1])
        other = Store.objects.create(name="فروشگاه دیگر", slug="ann-other2", admin_subdomain="ann-other2", status=Store.Status.ACTIVE)
        foreign = MediaAsset.objects.create(store=other, image=_png("foreign.png"))
        draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        draft.header_config = {**draft.header_config, "announcement_enabled": True, "announcement_image_asset_id": foreign.pk}   # tampered storage
        draft.save(update_fields=["header_config"])
        html = self._preview()
        self.assertNotIn(foreign.image.url, html)                                              # fail-closed at render time

    def test_published_is_unchanged_until_publish(self):
        self._setup_full()
        published = layout_service.get_or_create_layout(self.store).published_version
        before = (published.header_config if published else None)
        self._header(announcement_text="متن تازه")
        layout = layout_service.get_or_create_layout(self.store)
        layout.refresh_from_db()
        after = (layout.published_version.header_config if layout.published_version else None)
        self.assertEqual(before, after)


class AnnouncementUploadAndStudioTests(AnnouncementConfigTests):
    URL = "dashboard:storefront-builder-r4-announcement-image"

    def test_upload_creates_one_store_scoped_asset_only_for_a_real_image(self):
        ok = self.client.post(reverse(self.URL), {"image": _png()})
        self.assertEqual(ok.status_code, 200, ok.content)
        asset = MediaAsset.objects.get(pk=ok.json()["asset_id"])
        self.assertEqual(asset.store_id, self.store.pk)
        count = MediaAsset.objects.count()
        for bad in (SimpleUploadedFile("x.html", b"<script>alert(1)</script>", content_type="image/png"),
                    SimpleUploadedFile("x.png", b"not an image", content_type="image/png")):
            response = self.client.post(reverse(self.URL), {"image": bad})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(reverse(self.URL), {}).status_code, 400)
        self.assertEqual(MediaAsset.objects.count(), count)                                    # a failed upload leaves nothing behind

    def test_upload_requires_a_signed_in_store_manager_and_post(self):
        self.assertEqual(self.client.get(reverse(self.URL)).status_code, 405)
        self.client.logout()
        self.assertNotEqual(self.client.post(reverse(self.URL), {"image": _png()}).status_code, 200)

    def test_the_studio_panel_has_the_announcement_block_and_the_library_card_is_not_a_section(self):
        html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        for marker in ("data-r4-announce-block", 'data-r4-global-field="announcement_image_asset_id"', 'data-r4-global-field="announcement_link_url"',
                       'data-r4-global-field="announcement_pages"', 'data-r4-global-field="announcement_align"', 'data-r4-geometry-prop="announce_bg"'):
            self.assertIn(marker, html, marker)
        self.assertEqual(html.count('data-r4-geometry-prop="announce_bg"'), 1)               # not duplicated among the variant's geometry
        # the text control keeps the strip short (a phone strip stays ≤ ~88px): the Studio field stops at 200 characters
        self.assertRegex(html, r'<input[^>]*id="r4GlobalAnnouncementText"[^>]*maxlength="200"')
        card = re.search(r'<button[^>]*data-rastisi-action="open-announcement".*?</button>', html, re.S).group(0)
        self.assertIn("نوار اطلاعیه", card)
        self.assertNotIn("data-rs-library-key", card)                                          # it adds NO section

    def test_the_client_script_is_ui_only_one_upload_transport_and_nothing_stored(self):
        js = re.sub(r"/\*.*?\*/", "", (STATIC / "r4_announcement.js").read_text(encoding="utf-8"), flags=re.S)   # code, not the header comment
        self.assertEqual(js.count("fetch("), 1)
        self.assertIn("data-r4-announce-upload-url", js)
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "header.update", "enqueueMutation"):
            self.assertNotIn(forbidden, js, forbidden)                                        # the mutation is sent by the existing field handler
        studio = (STATIC / "r4_studio.js").read_text(encoding="utf-8")
        self.assertIn("case 'open-announcement'", studio)
        self.assertEqual(studio.count("fetch("), 1)
