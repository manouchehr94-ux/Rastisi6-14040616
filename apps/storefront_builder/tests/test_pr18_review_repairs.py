"""PR #18 post-review repairs (findings #1–#6).

#1 removing a mobile image from an ASSET-BACKED slide (UI control + server + publish)
#2 ``destination_type`` is validated and escaped (no reflected JS)
#3 non-numeric / out-of-range destination ids never 500
#4 inline R4 requests never queue stale flash messages
#5 default-image adoption tells the merchant what happened (created / skipped / failed)
#6 ``media_default_state`` no longer swallows real errors
"""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.messages import get_messages
from django.template.loader import render_to_string
from django.urls import reverse

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder import media_views
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import media_defaults_service as mds
from apps.storefront_builder.templatetags.storefront_builder_extras import media_default_state

from .test_media_default_images import INLINE, _DefaultsBase
from .test_media_views import _img

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "storefront_builder"
PICKER_CALL = re.compile(r"x-data=\"(destinationPicker\((?:.|\n)*?\))\"")
PAYLOAD = "none');window.__pwned=1;//"


class _Base(_DefaultsBase):
    def asset(self, name):
        return MediaAsset.objects.create(store=self.store, image=f"media-assets/{name}.png")

    def asset_only_hero(self, title="اسلاید", mobile=True, **kw):
        """A slide that exists only as MediaAssets (what a Published clone / an adopted default is)."""
        return HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title=title, is_active=True,
            desktop_asset=self.asset(f"d-{title}"), mobile_asset=self.asset(f"m-{title}") if mobile else None, **kw,
        )

    def edit_url(self, item, section=None, kind="hero-slides"):
        return self.url("edit", (section or self.hero_section).pk, kind, item.pk)

    def add_url(self, section=None, kind="hero-slides"):
        return self.url("add", (section or self.hero_section).pk, kind)

    def post_edit(self, item, data, inline=True, **kw):
        base = {"title": item.title or "t", "is_active": "on", "destination_type": "none"}
        base.update(data)
        return self.client.post(self.edit_url(item, **kw), base, **(INLINE if inline else {}))

    def node(self, call):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        js = (STATIC_DIR / "destination_picker.js").read_text(encoding="utf-8")
        script = (f"var window={{}};\n{js}\nvar destinationPicker=window.destinationPicker;\n"
                  f"var r={call};console.log(JSON.stringify({{r:r,pwned:typeof window.__pwned}}));")
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def picker_call(self, markup):
        match = PICKER_CALL.search(markup)
        self.assertIsNotNone(match, "destinationPicker x-data not rendered")
        return html.unescape(match.group(1))  # what the browser hands to Alpine


# --------------------------------------------------------------------------- #1
class RemoveAssetBackedMobileImageTests(_Base):
    def test_control_is_rendered_for_an_asset_only_mobile_image(self):
        slide = self.asset_only_hero()
        for inline in (True, False):
            page = (self.client.get(self.edit_url(slide), **INLINE) if inline else self.client.get(self.edit_url(slide))).content.decode()
            self.assertIn('name="remove_mobile"', page, f"inline={inline}")
            self.assertEqual(page.count("sfb-media-current"), 2)  # desktop + mobile previews

    def test_control_is_absent_when_there_is_no_mobile_image_and_on_add(self):
        slide = self.asset_only_hero(mobile=False)
        self.assertNotIn('name="remove_mobile"', self.client.get(self.edit_url(slide), **INLINE).content.decode())
        self.assertNotIn('name="remove_mobile"', self.client.get(self.add_url(), **INLINE).content.decode())

    def test_control_is_still_rendered_for_a_legacy_file_row(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="قدیمی", desktop_image=_img("d.png"),
            mobile_image=_img("m.png"), is_active=True,
        )
        self.assertIn('name="remove_mobile"', self.client.get(self.edit_url(slide), **INLINE).content.decode())

    def test_story_item_keeps_its_note_and_has_no_remove_control(self):
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="س", image_asset=self.asset("s"), is_active=True)
        page = self.client.get(self.edit_url(item, self.story_section, "story-items"), **INLINE).content.decode()
        self.assertNotIn("remove_", page)
        self.assertIn("تصویر فعلی حفظ می‌شود", page)

    def test_removal_clears_only_the_mobile_fk_and_retains_every_asset_row(self):
        slide = self.asset_only_hero()
        desktop_id, mobile_id = slide.desktop_asset_id, slide.mobile_asset_id
        assets_before = MediaAsset.objects.count()
        resp = self.post_edit(slide, {"remove_mobile": "on"})
        self.assertEqual(resp.status_code, 200)
        slide.refresh_from_db()
        self.assertIsNone(slide.mobile_asset_id)
        self.assertEqual(slide.desktop_asset_id, desktop_id)
        self.assertEqual(slide.mobile_image_url, "")
        self.assertTrue(slide.desktop_image_url)
        self.assertEqual(MediaAsset.objects.count(), assets_before)  # retention-first: nothing deleted
        self.assertTrue(MediaAsset.objects.filter(pk=mobile_id).exists())
        self.assertEqual(resp.headers["HX-Trigger"], "r4:media-changed")  # a real, publishable change
        self.assertEqual(resp.headers["HX-Trigger-After-Swap"], "r4:media-modal-saved")

    def test_no_checkbox_keeps_the_mobile_image_and_does_not_dirty_the_draft(self):
        slide = self.asset_only_hero()
        mobile_id = slide.mobile_asset_id
        resp = self.post_edit(slide, {})
        slide.refresh_from_db()
        self.assertEqual(slide.mobile_asset_id, mobile_id)
        self.assertNotIn("HX-Trigger", resp.headers)

    def test_removal_with_no_mobile_image_is_a_no_op(self):
        slide = self.asset_only_hero(mobile=False)
        resp = self.post_edit(slide, {"remove_mobile": "on"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Trigger", resp.headers)
        slide.refresh_from_db()
        self.assertIsNone(slide.mobile_asset_id)

    def test_a_new_upload_wins_over_the_removal_checkbox(self):
        slide = self.asset_only_hero()
        old = slide.mobile_asset_id
        self.client.post(self.edit_url(slide), {
            "title": slide.title, "is_active": "on", "destination_type": "none",
            "remove_mobile": "on", "mobile_image": _img("new.png"),
        }, **INLINE)
        slide.refresh_from_db()
        self.assertIsNotNone(slide.mobile_asset_id)
        self.assertNotEqual(slide.mobile_asset_id, old)

    def test_row_with_a_legacy_file_and_an_asset_is_cleared_on_both_sides(self):
        slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="هر دو", desktop_image=_img("d.png"),
            mobile_image=_img("m.png"), is_active=True,
        )
        self.post_edit(slide, {"title": "هر دو", "mobile_image": _img("m2.png")})  # gives it a mobile asset
        slide.refresh_from_db()
        self.assertTrue(slide.mobile_asset_id)
        self.post_edit(slide, {"title": "هر دو", "remove_mobile": "on"})
        slide.refresh_from_db()
        self.assertFalse(slide.mobile_image)
        self.assertIsNone(slide.mobile_asset_id)
        self.assertEqual(slide.mobile_image_url, "")

    def test_banner_kind_behaves_the_same(self):
        banner = PromotionalBanner.objects.create(
            store=self.store, section=self.banner_section, title="بنر", is_active=True,
            desktop_asset=self.asset("bd"), mobile_asset=self.asset("bm"),
        )
        url = self.edit_url(banner, self.banner_section, "banners")
        self.assertIn('name="remove_mobile"', self.client.get(url, **INLINE).content.decode())
        resp = self.client.post(url, {"title": "بنر", "is_active": "on", "destination_type": "none", "remove_mobile": "on"}, **INLINE)
        self.assertEqual(resp.status_code, 200)
        banner.refresh_from_db()
        self.assertIsNone(banner.mobile_asset_id)
        self.assertTrue(banner.desktop_asset_id)

    def test_removal_changes_the_draft_fingerprint(self):
        slide = self.asset_only_hero()
        before = self.draft.compute_fingerprint()
        self.post_edit(slide, {"remove_mobile": "on"})
        self.assertNotEqual(self.draft.compute_fingerprint(), before)

    def test_publish_clones_the_removal_and_keeps_the_untouched_slide_intact(self):
        edited = self.asset_only_hero("ویرایش‌شده")
        untouched = self.asset_only_hero("دست‌نخورده")
        keep_mobile = untouched.mobile_asset_id
        self.post_edit(edited, {"remove_mobile": "on"})
        published = svc.publish(self.store)
        section = StorefrontSection.objects.get(page__version=published, stable_id=self.hero_section.stable_id)
        rows = {r.title: r for r in HeroSlide.objects.filter(section=section)}
        self.assertEqual(set(rows), {"ویرایش‌شده", "دست‌نخورده"})
        self.assertIsNone(rows["ویرایش‌شده"].mobile_asset_id)
        self.assertEqual(rows["ویرایش‌شده"].desktop_asset_id, edited.desktop_asset_id)
        self.assertEqual(rows["دست‌نخورده"].mobile_asset_id, keep_mobile)
        # ...and the NEXT draft (cloned from the published version) agrees
        draft = svc.get_or_create_draft(self.store)
        next_section = StorefrontSection.objects.get(page__version=draft, stable_id=self.hero_section.stable_id)
        next_rows = {r.title: r for r in HeroSlide.objects.filter(section=next_section)}
        self.assertIsNone(next_rows["ویرایش‌شده"].mobile_asset_id)
        self.assertEqual(next_rows["دست‌نخورده"].mobile_asset_id, keep_mobile)


# --------------------------------------------------------------------------- #2
class DestinationTypeSafetyTests(_Base):
    def test_tampered_type_is_rejected_and_never_reflected_into_the_page(self):
        resp = self.client.post(self.add_url(), {"title": "x", "destination_type": PAYLOAD}, **INLINE)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(HeroSlide.objects.filter(section=self.hero_section).exists())
        page = resp.content.decode()
        self.assertNotIn("__pwned", page)
        self.assertEqual(resp.context["error_tab"], "destination")
        state = self.node(self.picker_call(page))
        self.assertEqual(state["pwned"], "undefined")
        self.assertEqual(state["r"]["type"], "none")  # re-rendered in a SAFE state

    def test_tampered_type_on_edit_leaves_the_row_untouched(self):
        slide = self.asset_only_hero(destination_type="search")
        resp = self.post_edit(slide, {"destination_type": PAYLOAD, "title": "تغییر"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", resp.headers)
        slide.refresh_from_db()
        self.assertEqual((slide.title, slide.destination_type), ("اسلاید", "search"))

    def test_empty_type_is_rejected_too(self):
        slide = self.asset_only_hero()
        resp = self.post_edit(slide, {"destination_type": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", resp.headers)

    def test_every_real_type_is_still_accepted(self):
        slide = self.asset_only_hero()
        for dtype in ("none", "search", "cart"):
            with self.subTest(dtype=dtype):
                resp = self.post_edit(slide, {"destination_type": dtype})
                self.assertIn("HX-Trigger-After-Swap", resp.headers)
                slide.refresh_from_db()
                self.assertEqual(slide.destination_type, dtype)

    def test_template_escapes_a_corrupt_stored_type_in_both_form_layouts(self):
        """Defence in depth: even if an invalid value reached the DB, it stays an inert string."""
        config = media_views.media_config_for_kind("hero-slides")
        for inline in (True, False):
            with self.subTest(inline=inline):
                item = HeroSlide(store=self.store, section=self.hero_section, destination_type=PAYLOAD)
                markup = render_to_string(
                    "dashboard/storefront_builder/partials/section_media_form_body.html",
                    {"section": self.hero_section, "item": item, "kind": "hero-slides", "config": config,
                     "categories": [], "brands": [], "collections": [], "inline_media": inline,
                     "form_errors": [], "error_tabs": [], "error_tab": "content", "reselect_fields": []},
                )
                state = self.node(self.picker_call(markup))
                self.assertEqual(state["pwned"], "undefined")
                self.assertEqual(state["r"]["type"], PAYLOAD)  # a harmless string, not code

    def test_section_destination_block_escapes_the_same_sink(self):
        section = SimpleNamespace(pk=1, settings={"destination": {"destination_type": PAYLOAD, "destination_id": None}})
        markup = render_to_string(
            "dashboard/storefront_builder/partials/section_destination_fields.html",
            {"section": section, "destination_product_name": "", "categories": [], "brands": [], "collections": []},
        )
        state = self.node(self.picker_call(markup))
        self.assertEqual(state["pwned"], "undefined")
        self.assertEqual(state["r"]["type"], PAYLOAD)


# --------------------------------------------------------------------------- #3
class NonNumericDestinationIdTests(_Base):
    BAD = ["abc", "1.5", "²", "-1", "0", "9" * 30, "1e3", "٫"]

    def test_bad_ids_never_500_and_never_persist(self):
        fields = {"category": "destination_category", "brand": "destination_brand",
                  "collection": "destination_collection", "product": "destination_product"}
        for dtype, field in fields.items():
            for bad in self.BAD:
                with self.subTest(dtype=dtype, bad=bad):
                    resp = self.client.post(
                        self.add_url(), {"title": "x", "desktop_image": _img(), "destination_type": dtype, field: bad}, **INLINE,
                    )
                    self.assertEqual(resp.status_code, 200)
                    self.assertEqual(resp.context["error_tab"], "destination")
                    self.assertTrue(resp.context["form_errors"])
                    self.assertNotIn("HX-Trigger-After-Swap", resp.headers)
        self.assertFalse(HeroSlide.objects.filter(section=self.hero_section).exists())

    def test_edit_with_a_bad_id_leaves_the_stored_destination_alone(self):
        self._make_targets_once()
        slide = self.asset_only_hero(destination_type="category", destination_category=self.cat)
        resp = self.post_edit(slide, {"destination_type": "brand", "destination_brand": "abc"})
        self.assertEqual(resp.status_code, 200)
        slide.refresh_from_db()
        self.assertEqual((slide.destination_type, slide.destination_category_id, slide.destination_brand_id),
                         ("category", self.cat.pk, None))

    def test_a_valid_id_still_works(self):
        self._make_targets_once()
        slide = self.asset_only_hero()
        resp = self.post_edit(slide, {"destination_type": "brand", "destination_brand": str(self.brand.pk)})
        self.assertIn("HX-Trigger-After-Swap", resp.headers)
        slide.refresh_from_db()
        self.assertEqual((slide.destination_type, slide.destination_brand_id), ("brand", self.brand.pk))

    def _make_targets_once(self):
        from apps.catalog.models import Brand, Category
        self.cat = Category.objects.create(store=self.store, name="دسته", slug="pr18-cat", is_active=True)
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="pr18-brand", is_active=True)


# --------------------------------------------------------------------------- #4
class InlineFlashMessageTests(_Base):
    def _legacy_page_text(self):
        return self.client.get(self.url("list", self.hero_section.pk, "hero-slides")).content.decode()

    def test_positive_control_legacy_saves_still_flash(self):
        slide = self.asset_only_hero()
        self.post_edit(slide, {}, inline=False)
        self.assertIn("ذخیره شد", self._legacy_page_text())

    def test_inline_add_edit_delete_queue_nothing(self):
        slide = self.asset_only_hero()
        added = self.client.post(self.add_url(), {"title": "جدید", "desktop_image": _img(), "is_active": "on",
                                                  "destination_type": "none"}, **INLINE)
        edited = self.post_edit(slide, {"title": "ویرایش"})
        deleted = self.client.post(self.url("delete", self.hero_section.pk, "hero-slides", slide.pk), **INLINE)
        for name, resp in (("add", added), ("edit", edited), ("delete", deleted)):
            self.assertEqual(list(get_messages(resp.wsgi_request)), [], name)
        page = self._legacy_page_text()
        self.assertNotIn("ذخیره شد", page)
        self.assertNotIn("حذف شد", page)

    def test_inline_adopt_queues_nothing(self):
        self.make_defaults()
        resp = self.adopt()
        self.assertEqual(list(get_messages(resp.wsgi_request)), [])
        self.assertNotIn("قابل‌ویرایش شد", self._legacy_page_text().split("data-r4-media-notice")[0])

    def test_legacy_delete_still_flashes(self):
        slide = self.asset_only_hero()
        self.client.post(self.url("delete", self.hero_section.pk, "hero-slides", slide.pk))
        self.assertIn("حذف شد", self._legacy_page_text())


# --------------------------------------------------------------------------- #5
class AdoptFeedbackTests(_Base):
    def notice(self, resp):
        match = re.search(r"data-r4-media-notice[^>]*>(.*?)</div>", resp.content.decode(), re.S)
        return html.unescape(match.group(1)).strip() if match else None

    def test_created_is_reported_inside_the_list(self):
        self.make_defaults()
        resp = self.adopt()
        self.assertEqual(self.notice(resp), "3 تصویر پیش‌فرض قابل‌ویرایش شد.")
        self.assertIn("HX-Trigger", resp.headers)

    def test_created_and_skipped_are_both_reported(self):
        self.make_defaults()
        HeroSlide.objects.create(store=self.store, section=None, title="بدون تصویر", display_order=9, is_active=True)
        resp = self.adopt()
        self.assertEqual(self.notice(resp), "3 تصویر پیش‌فرض قابل‌ویرایش شد. 1 مورد بدون فایل تصویر کپی نشد.")

    def test_all_skipped_says_nothing_was_copied_and_does_not_dirty_the_draft(self):
        HeroSlide.objects.create(store=self.store, section=None, title="الف", display_order=0, is_active=True)
        HeroSlide.objects.create(store=self.store, section=None, title="ب", display_order=1, is_active=True)
        resp = self.adopt()
        self.assertEqual(self.notice(resp), "هیچ موردی کپی نشد: 2 تصویر پیش‌فرض فایل تصویری ندارد.")
        self.assertNotIn("HX-Trigger", resp.headers)
        self.assertFalse(self.own())

    def test_nothing_to_adopt_is_explained(self):
        resp = self.adopt()
        self.assertIn("موردی برای تبدیل نبود", self.notice(resp))
        self.assertNotIn("HX-Trigger", resp.headers)

    def test_a_section_that_already_has_active_items_is_explained(self):
        self.make_defaults()
        self.asset_only_hero()
        self.assertIn("موردی برای تبدیل نبود", self.notice(self.adopt()))

    def test_plain_list_has_no_notice(self):
        self.make_defaults()
        self.assertNotIn("data-r4-media-notice", self.list_html())

    def test_legacy_adopt_reports_through_a_flash_and_a_redirect(self):
        resp = self.adopt(inline=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("موردی برای تبدیل نبود", self.client.get(resp.headers["Location"]).content.decode())
        self.make_defaults()
        resp = self.adopt(inline=False)
        self.assertIn("3 تصویر پیش‌فرض قابل‌ویرایش شد.", self.client.get(resp.headers["Location"]).content.decode())

    def test_studio_js_toasts_when_the_adopt_request_itself_fails(self):
        js = (STATIC_DIR / "r4_studio.js").read_text(encoding="utf-8")
        block = js.split("function adoptRequestFailed", 1)[1].split("// Fired by media_views", 1)[0]
        self.assertIn("data-r4-media-adopt", block)
        self.assertIn("notify('تبدیل تصاویر پیش‌فرض انجام نشد؛ دوباره تلاش کنید.')", block)
        for event in ("htmx:responseError", "htmx:sendError", "htmx:timeout"):
            self.assertIn(f"'{event}'", block)


# --------------------------------------------------------------------------- #6
class MediaDefaultStateTagTests(_Base):
    def test_unusable_config_is_inert(self):
        for config in (None, {}, {"label": "x"}, "not-a-dict"):
            with self.subTest(config=config):
                self.assertFalse(media_default_state(self.hero_section, config).in_effect)

    def test_normal_path_is_unchanged(self):
        self.make_defaults()
        state = media_default_state(self.hero_section, media_views.media_config_for_kind("hero-slides"))
        self.assertTrue(state.in_effect)
        self.assertEqual(len(state.items), 3)

    def test_real_errors_propagate_instead_of_looking_like_no_defaults(self):
        config = media_views.media_config_for_kind("hero-slides")
        with mock.patch.object(mds, "default_media_state", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                media_default_state(self.hero_section, config)

    def test_a_failure_surfaces_as_a_logged_500_not_a_silent_empty_list(self):
        self.make_defaults()
        self.client.raise_request_exception = False
        with mock.patch.object(mds, "default_media_state", side_effect=RuntimeError("boom")):
            with self.assertLogs("django.request", level="ERROR"):
                resp = self.client.get(self.url("list", self.hero_section.pk, "hero-slides"), **INLINE)
        self.assertEqual(resp.status_code, 500)
