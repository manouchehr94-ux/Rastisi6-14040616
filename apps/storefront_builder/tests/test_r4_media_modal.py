"""R4 heavy-editor modal refactor — media add/edit form + media list layout.

The Design Studio Inspector is ~300px wide; a media item's create/edit form now
opens in a large dialog (``media-editor`` in r4_studio.js) that mounts the SAME
server-rendered form (``section_media_form_body.html``) as four presentation-only
tabs. These tests pin: the modal-mode markup contract, the one-form/one-Save
contract, the retarget/close response headers, validation UX, the preserved
D-002/D-003/D-004 repairs *through the modal path*, the wrapping media-list
markup, and the small JS contracts.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from django.contrib.messages import get_messages
from django.urls import reverse

from apps.catalog.models import Brand, Category, MerchantCollection, Product
from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from apps.storefront_builder import media_views

from .test_ds_defect_repair import _DestinationFixtureMixin
from .test_media_views import MediaViewsTestCase, _img

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "storefront_builder"
INLINE = {"HTTP_HX_REQUEST": "true", "HTTP_HX_R4_INLINE": "1"}
TABS = ("content", "media", "destination", "status")
PICKER_CALL = re.compile(r"x-data=\"(destinationPicker\((?:.|\n)*?\))\"")


class _ModalBase(_DestinationFixtureMixin, MediaViewsTestCase):
    def setUp(self):
        super().setUp()
        self._make_targets()

    def add_url(self, section=None, kind="hero-slides"):
        return reverse("dashboard:storefront-builder-section-media-add", args=[(section or self.hero_section).pk, kind])

    def edit_url(self, item, section=None, kind="hero-slides"):
        return reverse("dashboard:storefront-builder-section-media-edit", args=[(section or self.hero_section).pk, kind, item.pk])

    def get_inline(self, url):
        return self.client.get(url, **INLINE)

    def post_inline(self, url, data):
        return self.client.post(url, data, **INLINE)

    def make_slide(self, **kwargs):
        defaults = dict(store=self.store, section=self.hero_section, title="اسلاید", desktop_image=_img(), is_active=True)
        defaults.update(kwargs)
        return HeroSlide.objects.create(**defaults)


class ModalRenderingTests(_ModalBase):
    def test_add_form_renders_modal_markup(self):
        html = self.get_inline(self.add_url()).content.decode()
        self.assertIn('id="r4MediaForm"', html)
        self.assertIn('role="tablist"', html)
        for tab in TABS:
            self.assertIn(f'id="r4MediaTab-{tab}"', html)
            self.assertIn(f'id="r4MediaPanel-{tab}"', html)
            self.assertIn(f'data-r4-media-panel="{tab}"', html)
        self.assertEqual(html.count("<form"), 1)
        self.assertIn("novalidate", html)  # server-side validation stays authoritative
        self.assertIn('hx-target="#r4MediaModalSlot"', html)
        self.assertIn(self.add_url(), html)
        # Save/Cancel live in the dialog footer (tied to the form via form=), not per tab.
        self.assertNotIn('type="submit"', html)
        self.assertNotIn("← بازگشت", html)
        self.assertNotIn("<details", html)

    def test_no_template_comment_leaks_into_markup(self):
        """A multi-line ``{# #}`` is not a Django comment: it once rendered its
        text on the page and swallowed the destination controls."""
        for url in (self.add_url(), self.add_url(kind="banners", section=self.banner_section)):
            html = self.get_inline(url).content.decode()
            self.assertNotIn("{#", html)
            self.assertNotIn("Media form field group", html)
            self.assertNotIn("{%", html)
        legacy = self.client.get(self.add_url()).content.decode()
        self.assertNotIn("Media form field group", legacy)
        self.assertNotIn("{#", legacy)

    def test_every_destination_control_is_in_the_destination_panel(self):
        html = self.get_inline(self.add_url()).content.decode()
        panel = html.split('data-r4-media-panel="destination"', 1)[1].split('data-r4-media-panel="status"', 1)[0]
        for name in ("destination_type", "destination_category", "destination_brand", "destination_collection",
                     "destination_product", "destination_external_url", "open_in_new_tab"):
            self.assertIn(f'name="{name}"', panel)
        for value in ("none", "category", "brand", "collection", "product", "search", "cart", "external"):
            self.assertIn(f'<option value="{value}">', panel)

    def test_field_groups_land_in_the_intended_tabs(self):
        html = self.get_inline(self.add_url()).content.decode()

        def panel(name, nxt):
            return html.split(f'data-r4-media-panel="{name}"', 1)[1].split(f'data-r4-media-panel="{nxt}"', 1)[0]
        content, media, status = panel("content", "media"), panel("media", "destination"), html.split('data-r4-media-panel="status"', 1)[1]
        for name in ("title", "subtitle", "show_button", "button_label"):
            self.assertIn(f'name="{name}"', content)
        self.assertIn('name="desktop_image"', media)
        self.assertIn('name="mobile_image"', media)
        self.assertIn('name="is_active"', status)

    def test_edit_form_populates_existing_values_and_image_preview(self):
        slide = self.make_slide(
            title="عنوان موجود", subtitle="زیر موجود", show_button=True, button_label="بخر",
            destination_type="brand", destination_brand=self.brand,
        )
        # show_button needs a destination (model.clean): brand set above.
        html = self.get_inline(self.edit_url(slide)).content.decode()
        self.assertIn('value="عنوان موجود"', html)
        self.assertIn('value="زیر موجود"', html)
        self.assertIn('value="بخر"', html)
        self.assertRegex(html, r'<input type="checkbox" name="show_button"[^>]*checked')
        self.assertIn(f'<option value="{self.brand.pk}" selected>', html)
        self.assertIn(self.edit_url(slide), html)
        self.assertIn(f'src="{slide.desktop_image_url}"', html)  # current image preview
        self.assertRegex(html, r'<input type="checkbox" name="is_active"[^>]*checked')

    def test_edit_form_renders_inactive_item_unchecked(self):
        slide = self.make_slide(is_active=False)
        html = self.get_inline(self.edit_url(slide)).content.decode()
        self.assertNotIn("checked", re.search(r'<input type="checkbox" name="is_active"[^>]*>', html).group(0))

    def test_banner_and_story_items_share_the_same_modal_form(self):
        banner = PromotionalBanner.objects.create(store=self.store, section=self.banner_section, title="بنر", desktop_image=_img())
        story = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="استوری", image=_img())
        b_html = self.get_inline(self.edit_url(banner, self.banner_section, "banners")).content.decode()
        s_html = self.get_inline(self.edit_url(story, self.story_section, "story-items")).content.decode()
        for html in (b_html, s_html):
            self.assertIn('id="r4MediaForm"', html)
            self.assertEqual(html.count('role="tab"'), 4)
        self.assertIn('name="description"', b_html)
        self.assertIn('name="mobile_image"', b_html)
        self.assertIn('name="image"', s_html)
        self.assertIn(f'src="{story.image_url}"', s_html)

    def test_legacy_full_page_keeps_linear_layout(self):
        html = self.client.get(self.add_url()).content.decode()
        self.assertNotIn('id="r4MediaForm"', html)
        self.assertNotIn('role="tablist"', html)
        self.assertIn("<details", html)
        self.assertIn('type="submit"', html)
        self.assertIn("← بازگشت", html)
        self.assertIn('name="destination_type"', html)


class ModalFormContractTests(_ModalBase):
    def test_one_submission_carries_values_from_every_tab(self):
        slide = self.make_slide(title="قدیم", subtitle="قدیم", show_button=False)
        resp = self.post_inline(self.edit_url(slide), {
            # محتوا
            "title": "عنوان جدید", "subtitle": "زیرعنوان جدید", "show_button": "on", "button_label": "برو",
            # تصاویر
            "desktop_image": _img("new.png"),
            # لینک و مقصد
            "destination_type": "brand", "destination_brand": str(self.brand.pk), "open_in_new_tab": "on",
            # وضعیت (unchecked → key omitted)
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        slide.refresh_from_db()
        self.assertEqual((slide.title, slide.subtitle, slide.button_label), ("عنوان جدید", "زیرعنوان جدید", "برو"))
        self.assertTrue(slide.show_button)
        self.assertEqual((slide.destination_type, slide.destination_brand_id), ("brand", self.brand.pk))
        self.assertTrue(slide.open_in_new_tab)
        self.assertFalse(slide.is_active)
        self.assertIn("new", slide.desktop_image.name)
        self.assertIsNotNone(slide.desktop_asset_id)

    def test_add_through_the_modal_persists_everything_at_once(self):
        resp = self.post_inline(self.add_url(), {
            "title": "جدید", "subtitle": "ز", "desktop_image": _img(), "is_active": "on",
            "destination_type": "category", "destination_category": str(self.cat.pk),
            **{k: v for k, v in self._stale_siblings().items() if k != "destination_category"},
        })
        self.assertEqual(resp.status_code, 200, resp.content)
        slide = HeroSlide.objects.get(section=self.hero_section)
        self.assertEqual((slide.title, slide.destination_type, slide.destination_category_id), ("جدید", "category", self.cat.pk))
        self.assertIsNone(slide.destination_brand_id)
        self.assertTrue(slide.is_active)

    def test_success_response_retargets_the_manager_and_closes_the_dialog(self):
        slide = self.make_slide()
        resp = self.post_inline(self.edit_url(slide), {"title": "تغییر", "is_active": "on", "destination_type": "none"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["HX-Retarget"], "[data-r4-media-manager]")
        self.assertEqual(resp.headers["HX-Reswap"], "innerHTML")
        self.assertEqual(resp.headers["HX-Trigger-After-Swap"], "r4:media-modal-saved")
        self.assertEqual(resp.headers["HX-Trigger"], "r4:media-changed")
        body = resp.content.decode()
        self.assertIn("data-r4-media-open", body)  # refreshed manager body, not the form
        self.assertIn("تغییر", body)
        self.assertNotIn('id="r4MediaForm"', body)

    def test_unchanged_edit_still_closes_dialog_but_does_not_dirty_the_draft(self):
        slide = self.make_slide(title="ثابت")
        resp = self.post_inline(self.edit_url(slide), {"title": "ثابت", "is_active": "on", "destination_type": "none"})
        self.assertEqual(resp.headers["HX-Trigger-After-Swap"], "r4:media-modal-saved")
        self.assertNotIn("HX-Trigger", resp.headers)

    def test_legacy_post_still_redirects_without_modal_headers(self):
        slide = self.make_slide()
        resp = self.client.post(self.edit_url(slide), {"title": "لگسی", "is_active": "on", "destination_type": "none"})
        self.assertEqual(resp.status_code, 302)
        for header in ("HX-Retarget", "HX-Reswap", "HX-Trigger-After-Swap"):
            self.assertNotIn(header, resp.headers)


class ModalRepairRegressionTests(_ModalBase):
    """D-002 / D-003 / D-004 must hold through the modal (inline) path."""

    def test_d002_active_true_to_false_persists_after_one_modal_save(self):
        slide = self.make_slide(is_active=True)
        self.post_inline(self.edit_url(slide), {"title": "اسلاید", "destination_type": "none"})  # checkbox omitted
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)
        html = self.get_inline(self.edit_url(slide)).content.decode()
        self.assertNotIn("checked", re.search(r'<input type="checkbox" name="is_active"[^>]*>', html).group(0))

    def test_d002_false_to_true_persists(self):
        slide = self.make_slide(is_active=False)
        self.post_inline(self.edit_url(slide), {"title": "اسلاید", "is_active": "on", "destination_type": "none"})
        slide.refresh_from_db()
        self.assertTrue(slide.is_active)

    def test_d002_list_toggle_still_works(self):
        slide = self.make_slide(is_active=True)
        url = reverse("dashboard:storefront-builder-section-media-toggle", args=[self.hero_section.pk, "hero-slides", slide.pk])
        self.client.post(url, **INLINE)
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)
        self.client.post(url, **INLINE)
        slide.refresh_from_db()
        self.assertTrue(slide.is_active)

    def test_d003_named_transitions_persist_on_first_modal_save(self):
        cases = [("category", "brand"), ("brand", "collection"), ("collection", "external")]
        seed = {
            "category": {"destination_category": self.cat}, "brand": {"destination_brand": self.brand},
            "collection": {"destination_collection": self.coll},
        }
        expected = {
            "brand": ("brand", None, self.brand.pk, None, None, ""),
            "collection": ("collection", None, None, self.coll.pk, None, ""),
            "external": ("external", None, None, None, None, "https://example.com/z"),
        }
        for src, dst in cases:
            with self.subTest(src=src, dst=dst):
                slide = self.make_slide(destination_type=src, **seed[src])
                post = {"destination_type": dst, **self._stale_siblings()}
                if dst == "external":
                    post["destination_external_url"] = "https://example.com/z"
                resp = self.post_inline(self.edit_url(slide), {"title": "اسلاید", "is_active": "on", **post})
                self.assertEqual(resp.status_code, 200)
                self.assertIn("HX-Trigger-After-Swap", resp.headers, "first Save must succeed, not re-render the form")
                self.assertEqual(self._values(slide), expected[dst])
                slide.delete()

    def test_d003_every_type_to_every_type_through_the_modal(self):
        types = ["none", "category", "brand", "collection", "product", "search", "cart", "external"]
        expect = {
            "none": ("none", None, None, None, None, ""), "search": ("search", None, None, None, None, ""),
            "cart": ("cart", None, None, None, None, ""),
            "category": ("category", self.cat.pk, None, None, None, ""),
            "brand": ("brand", None, self.brand.pk, None, None, ""),
            "collection": ("collection", None, None, self.coll.pk, None, ""),
            "product": ("product", None, None, None, self.product.pk, ""),
            "external": ("external", None, None, None, None, "https://example.com/z"),
        }
        slide = self.make_slide()
        for dst in types:
            with self.subTest(dst=dst):
                post = {"destination_type": dst, **self._stale_siblings()}
                if dst == "external":
                    post["destination_external_url"] = "https://example.com/z"
                resp = self.post_inline(self.edit_url(slide), {"title": "اسلاید", "is_active": "on", **post})
                self.assertIn("HX-Trigger-After-Swap", resp.headers, dst)
                self.assertEqual(self._values(slide), expect[dst])

    # ---- D-004 -----------------------------------------------------------
    def _node(self, call):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        js = (STATIC_DIR / "destination_picker.js").read_text(encoding="utf-8")
        script = f"var window={{}};\n{js}\nvar destinationPicker=window.destinationPicker;\nconsole.log(JSON.stringify({call}));"
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_d004_null_destination_ids_render_valid_js_in_the_modal(self):
        for dtype in ("product", "category", "brand", "collection"):
            with self.subTest(dtype=dtype):
                slide = self.make_slide()
                HeroSlide.objects.filter(pk=slide.pk).update(destination_type=dtype)  # orphaned: FK is NULL
                html = self.get_inline(self.edit_url(slide)).content.decode()
                call = PICKER_CALL.search(html).group(1).replace("&#x27;", "'").replace("&quot;", '"')
                self.assertNotIn("None", call)
                state = self._node(call)
                self.assertEqual(state["type"], dtype)
                self.assertIsNone(state["productId"])
                if dtype == "product":  # usable Product Search
                    self.assertIn('name="q_dest_product"', html)
                    self.assertIn('hx-vals=\'{"mode": "destination"}\'', html)
                slide.delete()


class ModalValidationTests(_ModalBase):
    def _errors_context(self, resp):
        return resp.context["form_errors"], resp.context["error_tab"], resp.context["error_tabs"]

    def test_missing_image_keeps_dialog_open_preserves_values_and_opens_media_tab(self):
        resp = self.post_inline(self.add_url(), {
            "title": "فقط عنوان", "subtitle": "ز", "button_label": "دکمه", "is_active": "on",
            "destination_type": "brand", "destination_brand": str(self.brand.pk),
        })
        self.assertEqual(resp.status_code, 200)
        for header in ("HX-Retarget", "HX-Trigger-After-Swap", "HX-Trigger"):
            self.assertNotIn(header, resp.headers)  # re-render lands in the dialog's own target
        html = resp.content.decode()
        self.assertIn('id="r4MediaForm"', html)
        self.assertIn("mediaFormTabs('media')", html)
        self.assertIn("data-r4-media-errors", html)
        self.assertNotRegex(html, r"data-r4-media-errors\s+hidden")
        self.assertIn("تصویر الزامی است", html)
        self.assertIn('id="r4MediaTab-media"', html)
        self.assertRegex(html, r'id="r4MediaTab-media"[^>]*>تصاویر[^<]*<span class="r4-media-tab-flag"')
        # values from every tab survive the round trip
        self.assertIn('value="فقط عنوان"', html)
        self.assertIn('value="دکمه"', html)
        self.assertIn(f'<option value="{self.brand.pk}" selected>', html)
        self.assertIn(self.add_url(), html)  # still the ADD url, never an edit url with pk=None
        self.assertFalse(HeroSlide.objects.filter(section=self.hero_section).exists())

    def test_errors_are_shown_in_form_not_queued_as_django_messages(self):
        resp = self.post_inline(self.add_url(), {"title": "بدون تصویر", "is_active": "on"})
        self.assertEqual(list(get_messages(resp.wsgi_request)), [])

    def test_destination_error_opens_destination_tab_and_keeps_other_tabs(self):
        slide = self.make_slide(title="قدیم")
        resp = self.post_inline(self.edit_url(slide), {
            "title": "عنوان تازه", "is_active": "on", "destination_type": "external", "destination_external_url": "",
        })
        self.assertEqual(resp.status_code, 200)
        messages_, tab, tabs = self._errors_context(resp)
        self.assertEqual(tab, "destination")
        self.assertIn("destination", tabs)
        html = resp.content.decode()
        self.assertIn("mediaFormTabs('destination')", html)
        self.assertIn('value="عنوان تازه"', html)  # inactive-tab value not discarded
        slide.refresh_from_db()
        self.assertEqual((slide.title, slide.destination_type), ("قدیم", "none"))

    def test_invalid_external_scheme_is_rejected_server_side(self):
        slide = self.make_slide()
        resp = self.post_inline(self.edit_url(slide), {
            "title": "اسلاید", "is_active": "on", "destination_type": "external",
            "destination_external_url": "javascript:alert(1)",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("HX-Trigger-After-Swap", resp.headers)
        slide.refresh_from_db()
        self.assertEqual(slide.destination_type, "none")

    def test_error_tab_mapping(self):
        f = media_views._media_form_tab_for_field
        for name in ("title", "subtitle", "description", "button_label", "show_button"):
            self.assertEqual(f(name), "content", name)
        for name in ("desktop_image", "mobile_image", "image", "desktop_asset", "remove_mobile"):
            self.assertEqual(f(name), "media", name)
        for name in ("destination_type", "destination_category", "destination_external_url", "open_in_new_tab", "__all__"):
            self.assertEqual(f(name), "destination", name)
        self.assertEqual(f("is_active"), "status")

    def test_form_errors_helper_first_tab_follows_field_order(self):
        from django.core.exceptions import ValidationError
        exc = ValidationError({"is_active": "a", "desktop_image": "b"})
        messages_, tabs, first = media_views._media_form_errors(exc)
        self.assertEqual((messages_, tabs, first), (["a", "b"], ["status", "media"], "status"))
        self.assertEqual(media_views._media_form_errors(Exception("boom")), (["boom"], ["content"], "content"))


class ReselectFileNoticeTests(_ModalBase):
    """A browser cannot re-populate <input type=file> after a server-side
    validation error, so the merchant must be told to pick the image again —
    and the form must not claim a "current image" that was never saved."""

    NOTE = "sfb-media-reselect"
    SUMMARY = media_views._RESELECT_FILE_SUMMARY
    BAD_DESTINATION = {"destination_type": "external", "destination_external_url": ""}

    def _group(self, html, field):
        """The <div class="form-group"> that wraps the given file input."""
        before = html.split(f'name="{field}" id="id_{field}"', 1)[0]
        start = before.rindex('<div class="form-group">')
        after = html.split(f'name="{field}" id="id_{field}"', 1)[1]
        return before[start:] + after.split("</div>", 1)[0]

    def test_add_flow_new_file_is_flagged_and_no_phantom_current_image(self):
        resp = self.post_inline(self.add_url(), {"title": "t", "is_active": "on", "desktop_image": _img(), **self.BAD_DESTINATION})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        group = self._group(html, "desktop_image")
        self.assertIn(self.NOTE, group)
        self.assertIn("دوباره انتخاب کنید", group)
        self.assertNotIn("تصویر فعلی حفظ می‌شود", group)  # nothing was saved
        self.assertNotIn("sfb-media-current", html)
        self.assertIn("(الزامی)", group)  # still an ADD: the image is required
        self.assertNotIn(self.NOTE, self._group(html, "mobile_image"))
        self.assertIn(self.SUMMARY, resp.context["form_errors"])
        self.assertIn(self.SUMMARY, html)
        self.assertEqual(resp.context["reselect_fields"], ["desktop_image"])
        self.assertFalse(HeroSlide.objects.filter(section=self.hero_section).exists())

    def test_edit_flow_shows_the_persisted_image_not_the_lost_upload(self):
        slide = self.make_slide(title="قدیم")
        stored = slide.desktop_image.name
        resp = self.post_inline(self.edit_url(slide), {
            "title": "قدیم", "is_active": "on", "desktop_image": _img("lost.png"), **self.BAD_DESTINATION,
        })
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        group = self._group(html, "desktop_image")
        self.assertIn(self.NOTE, group)
        self.assertIn(f'src="{slide.desktop_image_url}"', group)  # the stored image, not "lost.png"
        self.assertNotIn("lost", group)
        slide.refresh_from_db()
        self.assertEqual(slide.desktop_image.name, stored)  # DB untouched

    def test_only_the_field_whose_file_was_lost_is_flagged(self):
        resp = self.post_inline(self.add_url(), {
            "title": "t", "is_active": "on", "mobile_image": _img("m.png"), **self.BAD_DESTINATION,
        })
        html = resp.content.decode()
        self.assertNotIn(self.NOTE, self._group(html, "desktop_image"))
        self.assertIn(self.NOTE, self._group(html, "mobile_image"))
        self.assertEqual(resp.context["reselect_fields"], ["mobile_image"])

    def test_failure_without_a_selected_file_shows_no_reselect_notice(self):
        slide = self.make_slide()
        resp = self.post_inline(self.edit_url(slide), {"title": "x", "is_active": "on", **self.BAD_DESTINATION})
        html = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(f'class="{self.NOTE}"', html)
        self.assertNotIn(self.SUMMARY, html)
        self.assertEqual(resp.context["reselect_fields"], [])

    def test_get_never_shows_the_notice(self):
        slide = self.make_slide()
        for url in (self.add_url(), self.edit_url(slide)):
            self.assertNotIn(f'class="{self.NOTE}"', self.get_inline(url).content.decode())

    def test_story_item_single_image_field_is_flagged(self):
        resp = self.post_inline(
            self.add_url(self.story_section, "story-items"),
            {"title": "t", "is_active": "on", "image": _img(), **self.BAD_DESTINATION},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.NOTE, self._group(resp.content.decode(), "image"))

    def test_legacy_full_page_also_flags_the_lost_file(self):
        resp = self.client.post(self.add_url(), {"title": "t", "is_active": "on", "desktop_image": _img(), **self.BAD_DESTINATION})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.NOTE, self._group(resp.content.decode(), "desktop_image"))


class MediaListLayoutTests(_ModalBase):
    def setUp(self):
        super().setUp()
        self.slide = self.make_slide(title="عنوان خیلی خیلی خیلی طولانی برای بررسی سرریز افقی در ستون باریک")

    def list_html(self, inline=True):
        url = reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "hero-slides"])
        return (self.get_inline(url) if inline else self.client.get(url)).content.decode()

    def test_rows_wrap_and_every_action_is_present(self):
        html = self.list_html()
        row = re.search(r'<div class="panel sfb-media-row"[^>]*>', html).group(0)
        self.assertIn("flex-wrap:wrap", row)
        self.assertNotRegex(row, r"gap:14px")
        actions = html.split('class="sfb-media-actions"', 1)[1]
        self.assertIn("data-r4-media-open", actions)
        self.assertIn("ویرایش", actions)
        self.assertIn("غیرفعال‌سازی", actions)
        self.assertIn("حذف", actions)
        self.assertIn("/toggle/", actions)
        self.assertIn("/delete/", actions)
        # reorder controls + drag handle + thumbnail are still there
        self.assertIn("جابه‌جایی به بالا", html)
        self.assertIn("جابه‌جایی به پایین", html)
        self.assertIn("sfb-media-handle", html)
        self.assertIn(f'<img src="{self.slide.desktop_image_url}"', html)
        self.assertIn('class="sfb-media-title"', html)
        self.assertIn('title="عنوان خیلی', html)  # full title available as a tooltip when ellipsized

    def test_inline_edit_and_add_open_the_dialog_not_the_inspector(self):
        manager = self.get_inline(reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "hero-slides"])).content.decode()
        self.assertIn(f'data-r4-media-open="{self.add_url()}"', manager)
        self.assertIn('data-r4-media-title="افزودن اسلاید"', manager)
        self.assertIn(f'data-r4-media-open="{self.edit_url(self.slide)}"', manager)
        self.assertIn('data-r4-media-title="ویرایش اسلاید"', manager)
        # the old inline-into-the-manager loading is gone
        self.assertNotIn('hx-target="closest [data-r4-media-manager]"', manager)

    def test_legacy_list_keeps_plain_edit_link(self):
        html = self.list_html(inline=False)
        self.assertIn(f'<a href="{self.edit_url(self.slide)}" class="btn btn-sm">ویرایش</a>', html)
        self.assertNotIn("data-r4-media-open", html)

    def test_toggle_and_delete_keep_working_inline(self):
        toggle = reverse("dashboard:storefront-builder-section-media-toggle", args=[self.hero_section.pk, "hero-slides", self.slide.pk])
        resp = self.client.post(toggle, **INLINE)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("sfb-media-actions", resp.content.decode())
        delete = reverse("dashboard:storefront-builder-section-media-delete", args=[self.hero_section.pk, "hero-slides", self.slide.pk])
        self.assertEqual(self.client.post(delete, **INLINE).status_code, 200)
        self.assertFalse(HeroSlide.objects.filter(pk=self.slide.pk).exists())


class StudioAssetContractTests(_ModalBase):
    """Static contracts of the presentation layer (no browser needed)."""

    def setUp(self):
        super().setUp()
        self.js = (STATIC_DIR / "r4_studio.js").read_text(encoding="utf-8")
        self.css = (STATIC_DIR / "r4_studio.css").read_text(encoding="utf-8")

    def test_media_editor_is_a_studio_modal_with_dialog_semantics(self):
        self.assertIn("case 'media-editor':", self.js)
        self.assertIn("data-r4-media-open", self.js)
        self.assertIn('role="dialog" aria-modal="true" aria-labelledby="rsDialogTitle"', self.js)  # shared shell
        self.assertIn('form="r4MediaForm"', self.js)  # one Save, tied to the one form
        self.assertEqual(self.js.count('id="r4MediaSave"'), 1)

    def test_live_form_is_never_rebuilt_by_other_studio_rerenders(self):
        self.assertIn("m.type === 'media-editor' && modalRoot.querySelector('.modal.media-modal')) return;", self.js)

    def test_dirty_form_close_is_gated_and_reuses_the_escape_path(self):
        self.assertIn("function closeModal(restore, force)", self.js)
        self.assertIn("ui.media.dirty && !force", self.js)
        self.assertIn("toggleMediaDiscardPrompt(true)", self.js)
        self.assertIn("case 'media-discard': closeModal(true, true)", self.js)

    def test_in_flight_save_flag_is_cleared_by_the_swap_not_a_detached_afterRequest(self):
        after_swap = self.js.split("modalRoot.addEventListener('htmx:afterSwap'", 1)[1].split("modalRoot.addEventListener('htmx:beforeRequest'", 1)[0]
        self.assertIn("ui.media.saving = false", after_swap)
        self.assertIn("modalRoot.addEventListener('htmx:timeout', mediaRequestFailed)", self.js)

    def test_failed_save_rerender_cannot_be_settled_over_by_htmx(self):
        """htmx copies server class/style onto new elements whose id matches an
        old one. The re-rendered form reuses every r4MediaPanel-* id, so without
        clearing the slot first it wiped Alpine's display:none and showed ALL tab
        panels at once (found in a real browser; invisible to Django tests)."""
        guard = self.js.split("modalRoot.addEventListener('htmx:beforeSwap'", 1)[1].split("modalRoot.addEventListener('htmx:afterSwap'", 1)[0]
        self.assertIn("d.shouldSwap", guard)  # a 4xx/5xx must never clear the merchant's form
        self.assertIn("d.target.id === 'r4MediaModalSlot'", guard)
        self.assertIn("d.target.innerHTML = ''", guard)

    def test_focus_trap_ignores_hidden_controls(self):
        self.assertIn("getClientRects().length > 0", self.js)

    def test_help_text_and_undo_shortcuts_untouched(self):
        self.assertIn("Ctrl / ⌘ + Shift + Z: بازگردانی", self.js)  # D-001

    def test_css_defines_modal_tabs_and_wrapping_rows(self):
        for needle in (".modal.media-modal", ".r4-media-tabs", ".sfb-media-row", "flex-wrap:wrap",
                       ".sfb-media-actions", "grid-template-columns:repeat(3,minmax(0,1fr))"):
            self.assertIn(needle, self.css)
        self.assertRegex(self.css, r"\.media-modal\{[^}]*height:min\(600px,90dvh\)")
        self.assertIn("@media (max-width:720px)", self.css)

    def test_studio_page_loads_the_shared_picker_script(self):
        template = (STATIC_DIR.parent.parent / "templates/dashboard/storefront_builder/r4/editor.html").read_text(encoding="utf-8")
        self.assertIn("destination_picker.js", template)

    def _run_tabs(self, body):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        js = (STATIC_DIR / "destination_picker.js").read_text(encoding="utf-8")
        script = (
            "var window={getComputedStyle:function(){return {direction:'rtl'}}};"
            "var document={getElementById:function(id){return {focus:function(){window.focused=id}}}};"
            f"{js}\nvar make=function(t){{var o=window.mediaFormTabs(t);o.$el={{}};o.$nextTick=function(f){{f()}};return o}};\n{body}"
        )
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_media_form_tabs_state_machine(self):
        result = self._run_tabs("""
          var a=make('destination'), b=make('bogus'), c=make(undefined);
          var r=make('content'); r.onKey({key:'ArrowLeft',preventDefault:function(){}}); var rtlNext=r.tab;   // RTL: Left = forward
          r.onKey({key:'ArrowRight',preventDefault:function(){}}); var rtlBack=r.tab;
          r.onKey({key:'ArrowRight',preventDefault:function(){}}); var wrapped=r.tab;                       // wraps to last
          r.onKey({key:'Home',preventDefault:function(){}}); var home=r.tab;
          r.onKey({key:'End',preventDefault:function(){}}); var end=r.tab;
          var prevented=false; r.onKey({key:'x',preventDefault:function(){prevented=true}});
          console.log(JSON.stringify({a:a.tab,b:b.tab,c:c.tab,rtlNext,rtlBack,wrapped,home,end,prevented,focused:window.focused}));
        """)
        self.assertEqual(result, {"a": "destination", "b": "content", "c": "content", "rtlNext": "media", "rtlBack": "content",
                                  "wrapped": "status", "home": "content", "end": "status", "prevented": False,
                                  "focused": "r4MediaTab-status"})
