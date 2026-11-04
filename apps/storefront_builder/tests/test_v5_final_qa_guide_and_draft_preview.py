"""V5 final QA fix — (1) the image guide reads the picture's REAL placement (Container preset, Cell, dragged dividers, the Section's own size / fit),
(2) «پیش‌نمایش» opens the customer view of the saved DRAFT, never the published store.

Both ride the existing infrastructure: ``upload_frames`` / ``upload_placement`` (read-only), the ``image_guide`` tag, and the public context assembly
fed from the Draft (``storefront_context_service.build_draft_preview_context``). No model, no migration, no write path."""

import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import PromotionalBanner
from apps.storefront_builder import upload_frames, upload_placement
from apps.storefront_builder.models import StorefrontLayout, StorefrontSection
from apps.storefront_builder.services import container_service, layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

from . import test_v5_linked_image_announcement as linked_tests
from .test_media_views import MediaViewsTestCase

User = get_user_model()
APP = Path(__file__).resolve().parents[1]
ADMIN_HOST = "sfb-final-qa.rastisi.localhost"
PUBLIC_HOST = "sfb-final-qa-public.example.com"


def _pic(width=300, height=200, name="p.png"):
    buf = BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class _PlacementBase(linked_tests._LinkedBase):
    """A Draft page with one «big + two small» Container, one linked-image Section per Cell."""

    def _stack(self, layout="big_right_two_left", settings=None):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, layout, settings=settings)
        cells = list(container.cells.order_by("order", "id"))
        sections = []
        for number, cell in enumerate(cells):
            section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=950 + number)
            container_service.place_section(cell, section)
            sections.append(section)
        return container, cells, sections

    def _frame(self, section, slot="banner_desktop"):
        section.refresh_from_db()
        frames = upload_frames.resolve_frames(slot, store=self.store, target=section)
        self.assertEqual(len(frames), 1, frames)
        return frames[0]

    def _expected_cell(self, span, gap=14, viewport=upload_placement.REF_DESKTOP_VW):
        page = self.draft.get_page("home")
        inner = upload_placement.inner_width(upload_placement.content_width(self.draft, page), viewport)
        return upload_placement.cell_width(span, inner, gap)


class PlacementGeometryTests(_PlacementBase):
    def test_each_cell_of_a_stacked_layout_gets_its_own_real_width_from_the_layout(self):
        container, cells, (big, top, bottom) = self._stack()
        frames = [self._frame(s) for s in (big, top, bottom)]
        self.assertEqual([f["slot_name"] for f in frames], ["خانهٔ بزرگ", "خانهٔ کوچک بالا", "خانهٔ کوچک پایین"])
        self.assertEqual(frames[0]["w_px"], int(self._expected_cell(8) + 0.5))
        self.assertEqual(frames[1]["w_px"], int(self._expected_cell(4) + 0.5))
        self.assertEqual(frames[2]["w_px"], frames[1]["w_px"])
        self.assertGreater(frames[0]["w_px"], frames[1]["w_px"])
        # numbers come from the layout, not from the generic banner table (1200×900, 4:3)
        for f in frames:
            self.assertNotEqual(f["rec"], [1200, 900])
            self.assertEqual(f["rec"][0], min(2400, -(-f["w_px"] * 2 // 10) * 10))
            self.assertEqual(f["min"][0], f["w_px"])

    def test_dragging_the_column_boundary_changes_the_suggested_size_of_every_cell(self):
        container, cells, (big, top, bottom) = self._stack()
        before = [self._frame(s)["w_px"] for s in (big, top)]
        container_service.resize_container(container, spans=[9, 3, 3])
        after = [self._frame(s)["w_px"] for s in (big, top)]
        self.assertGreater(after[0], before[0])
        self.assertLess(after[1], before[1])
        self.assertEqual(after[0], int(self._expected_cell(9) + 0.5))
        self.assertEqual(after[1], int(self._expected_cell(3) + 0.5))

    def test_a_50_50_row_becomes_70_30_and_each_cell_follows(self):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "half")
        cells = list(container.cells.order_by("order", "id"))
        sections = []
        for number, cell in enumerate(cells):
            section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=960 + number)
            container_service.place_section(cell, section)
            sections.append(section)
        half = [self._frame(s)["w_px"] for s in sections]
        self.assertEqual(half[0], half[1])
        container_service.change_container_layout(container, "third_right")      # 8 / 4
        wide = [self._frame(s)["w_px"] for s in sections]
        self.assertEqual(wide[0], int(self._expected_cell(8) + 0.5))
        self.assertEqual(wide[1], int(self._expected_cell(4) + 0.5))
        self.assertGreater(wide[0], half[0])

    def test_a_section_without_a_manual_height_keeps_its_own_ratio_so_only_the_width_is_promised(self):
        container, cells, (big, top, bottom) = self._stack()
        container_service.place_section(cells[0], big)
        single = self._frame(top)
        # the top small Cell is an auto row — as tall as its own picture
        self.assertTrue(single["free"])
        self.assertIsNone(single["h_px"])
        self.assertIn("بریده نمی‌شود", single["crop_note"])
        self.assertEqual(single["rec"][1], 0)

    def _single(self, order=940):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "single")
        section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=order)
        container_service.place_section(container.cells.get(), section)
        return section

    def test_a_manual_height_makes_the_frame_exact_and_contain_cover_are_stated(self):
        section = self._single()
        section.settings = {"design": {"min_height": 500, "image_fit": "cover", "image_position": "top"}}
        section.save(update_fields=["settings"])
        f = self._frame(section)
        self.assertFalse(f["free"])
        self.assertFalse(f["approx"])
        self.assertEqual(f["h_px"], 500)
        self.assertAlmostEqual(f["ratio"], f["w_px"] / 500, places=1)
        self.assertEqual(f["fit"], "cover")
        self.assertIn("پر کردن قاب", f["crop_note"])
        self.assertIn("بالا", f["crop_note"])
        section.settings = {"design": {"min_height": 500, "image_fit": "contain"}}
        section.save(update_fields=["settings"])
        self.assertIn("نمایش کامل", self._frame(section)["crop_note"])

    def test_the_phone_is_measured_separately_and_a_manual_height_never_exceeds_80vw(self):
        section = self._single(941)
        section.settings = {"design": {"min_height": 700}}
        section.save(update_fields=["settings"])
        desktop, phone = self._frame(section), self._frame(section, "banner_mobile")
        self.assertEqual(desktop["h_px"], 700)
        self.assertEqual(phone["h_px"], int(0.8 * upload_placement.REF_MOBILE_VW + 0.5))
        inner = upload_placement.inner_width(upload_placement.content_width(self.draft, self.draft.get_page("home")), 390)
        self.assertEqual(phone["w_px"], int(inner + 0.5))                         # the Cells stack: full width of the phone column
        self.assertLess(phone["w_px"], desktop["w_px"])

    def test_in_the_stacked_layout_a_manual_height_is_not_claimed_because_the_stylesheet_ignores_it(self):
        container, cells, (big, top, bottom) = self._stack()
        before = self._frame(big)
        big.settings = {"design": {"min_height": 900}}
        big.save(update_fields=["settings"])
        after = self._frame(big)
        self.assertNotEqual(after["h_px"], 900)
        self.assertEqual(after["h_px"], before["h_px"])
        self.assertIn("اثری ندارد", after["crop_note"])
        # the claim is pinned to the real rule: the stacked Cell's section resets min-height (more specific than the manual-height rule)
        css = (APP / "static" / "css" / "storefront_builder.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'\.rcontainer\[data-layout="big_right_two_left"\] > \.rcontainer-cell > \.rsec \{ flex: 1 1 auto; min-height: 0; \}')

    def test_section_width_percent_shrinks_the_frame(self):
        container, cells, (big, top, bottom) = self._stack()
        full = self._frame(big)["w_px"]
        big.settings = {"design": {"width_pct": 50}}
        big.save(update_fields=["settings"])
        self.assertAlmostEqual(self._frame(big)["w_px"], full / 2, delta=1)

    def test_neighbours_real_pictures_decide_the_big_cells_height(self):
        container, cells, (big, top, bottom) = self._stack()
        for section in (top, bottom):
            self.assertEqual(self._add(section, desktop_image=_pic(400, 200)).status_code, 302)    # 2:1 → half as tall as wide
        f = self._frame(big)
        small_w = self._expected_cell(4)
        self.assertEqual(f["kind"], "siblings")
        self.assertFalse(f["approx"])
        self.assertAlmostEqual(f["h_px"], 2 * (small_w / 2) + 14, delta=2)
        self.assertIn("محاسبه شد", f["crop_note"])

    def test_an_unknown_neighbour_is_reported_as_an_assumption_never_as_an_exact_size(self):
        container, cells, (big, top, bottom) = self._stack()
        f = self._frame(big)
        self.assertEqual(f["kind"], "assumed")
        self.assertTrue(f["approx"])
        self.assertIn("تقریبی", f["size_text"])
        self.assertIn("فرض", f["crop_note"])

    def test_dragging_the_height_divider_of_the_two_small_cells_changes_their_suggested_height(self):
        container, cells, (big, top, bottom) = self._stack()
        container_service.resize_container(container, stack_split=30, set_split=True)
        small_top, small_bottom = self._frame(top), self._frame(bottom)
        container_service.resize_container(container, stack_split=70, set_split=True)
        top_70 = self._frame(top)
        self.assertTrue(small_top["approx"] and small_bottom["approx"])
        self.assertGreater(small_bottom["h_px"], small_top["h_px"])
        self.assertGreater(top_70["h_px"], small_top["h_px"])

    def test_several_sections_in_one_cell_each_keep_their_own_height(self):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "single")
        cell = container.cells.get()
        sections = []
        for number in range(2):
            section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=970 + number)
            container_service.add_block(cell, section)
            sections.append(section)
        f = self._frame(sections[1])
        self.assertIn("بخش 2 از 2", f["slot_name"])
        self.assertTrue(f["free"])
        self.assertEqual(f["kind"], "shared")

    def test_phone_stacked_mode_versus_same_mode(self):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "half", settings={"mobile_mode": "same"})
        cells = list(container.cells.order_by("order", "id"))
        section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=980)
        container_service.place_section(cells[0], section)
        same = self._frame(section, "banner_mobile")["w_px"]
        container.settings = {"mobile_mode": "stack"}
        container.save(update_fields=["settings"])
        stacked = self._frame(section, "banner_mobile")["w_px"]
        self.assertLess(same, stacked)                                             # side by side on the phone: about half the column


class GuideRenderingTests(_PlacementBase):
    def _guide(self, section, kind="banners"):
        response = self.client.get(reverse("dashboard:storefront-builder-section-media-add", args=[section.pk, kind]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_media_form_shows_the_real_placement_instead_of_the_generic_banner_numbers(self):
        container, cells, (big, top, bottom) = self._stack()
        html = self._guide(big)
        self.assertIn("راهنمای تصویر: تصویر خانهٔ بزرگ — دسکتاپ", html)          # the placement names the picture, not the generic «بنر تبلیغاتی»
        for text in ("جایگاه واقعی", "خانهٔ بزرگ", "بزرگ راست + دو کوچک چپ", "اندازهٔ نمایش", "وضعیت برش"):
            self.assertIn(text, html, text)
        # the data the browser script validates a chosen file against is the placement's, not 1200×900
        spec = re.search(r'data-image-guide="banner_desktop"[^>]*data-spec="([^"]*)"', html).group(1).replace("&quot;", '"')
        self.assertNotIn('"rec": [1200, 900]', spec)
        self.assertIn('"placement": true', spec)
        mobile = self._guide(big)
        self.assertEqual(mobile.count('data-image-guide="banner_mobile"'), 1)
        self.assertIn("موبایل", mobile)

    def test_reopening_the_guide_after_a_drag_shows_the_new_numbers_and_changes_nothing(self):
        container, cells, (big, top, bottom) = self._stack()
        first = self._guide(big)
        revision = self.draft.edit_revision
        history = self.draft.edit_history_entries.count()
        container_service.resize_container(container, spans=[9, 3, 3])
        second = self._guide(big)
        self.assertNotEqual(first, second)
        self.draft.refresh_from_db()
        # reading the guide is read-only: nothing was written by the two GETs
        self.assertEqual(self.draft.edit_history_entries.count(), history)
        self.assertEqual(self.draft.edit_revision, revision)

    def test_a_slot_without_a_placement_keeps_the_established_safe_guide(self):
        # the multi-banner section of the base fixture is a direct (legacy) section: no Cell → the generic guide, unchanged
        response = self.client.get(reverse("dashboard:storefront-builder-section-media-add", args=[self.banner_section.pk, "banners"]))
        html = response.content.decode()
        self.assertNotIn("جایگاه واقعی", html)
        self.assertIn("ابعادِ پیشنهادی", html)
        self.assertIn("۱۲۰۰×۹۰۰", html)

    def test_hero_and_banner_sections_in_a_cell_also_report_their_real_width(self):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "half")
        cells = list(container.cells.order_by("order", "id"))
        hero = StorefrontSection.objects.create(version=self.draft, page=page, section_key="hero_banner", order=990)
        container_service.place_section(cells[0], hero)
        frames = upload_frames.resolve_frames("hero_desktop", store=self.store, target=hero)
        self.assertTrue(all(f.get("placement") for f in frames))
        self.assertEqual(frames[0]["w_px"], int(self._expected_cell(6) + 0.5))
        self.assertGreater(frames[0]["h_px"], 0)

    def test_the_guide_script_understands_a_free_height_and_a_width_only_minimum(self):
        js = (Path(upload_frames.__file__).resolve().parents[1] / "core" / "static" / "core" / "image_guide.js").read_text(encoding="utf-8")
        self.assertIn("f.free", js)
        self.assertIn("function dim(a)", js)
        self.assertNotIn("fetch(", js)


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class DraftPreviewTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.owner = User.objects.create_user(username="final_qa_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.admin = Client(HTTP_HOST=ADMIN_HOST)
        self.admin.login(username="final_qa_owner", password="pass12345")
        self.public = Client(HTTP_HOST=PUBLIC_HOST)
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        self.draft = svc.get_or_create_draft(self.store)          # a fresh Draft cloned from the published one
        self.url = reverse("dashboard:storefront-builder-draft-preview")

    def _set_announcement(self, text):
        config = dict(self.draft.header_config or {})
        config.update({"announcement_enabled": True, "announcement_text": text})
        self.draft.header_config = config
        self.draft.save(update_fields=["header_config"])

    def test_the_draft_is_visible_in_the_preview_and_the_published_store_is_unchanged(self):
        self._set_announcement("متن فقط در پیش‌نویس ۴۲۴۲")
        preview = self.admin.get(self.url, {"page": "home"})
        public = self.public.get("/")
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "متن فقط در پیش‌نویس ۴۲۴۲")
        self.assertEqual(public.status_code, 200)
        self.assertNotContains(public, "متن فقط در پیش‌نویس ۴۲۴۲")

    def test_it_is_the_customer_view_without_any_builder_tooling(self):
        html = self.admin.get(self.url, {"page": "home"}).content.decode()
        for forbidden in ("sfb-rsec-toolbar", "sfb-builder-container", "sfb-cell-add-more", "sfb-empty-cell-add", "data-sfb-builder-mode",
                          "data-admin-edit", "sfb-announcement-edit-button", "rs-overlay", "sfb-rsec-builder-empty", "data-section-id=",
                          "data-container-id="):
            self.assertNotIn(forbidden, html, forbidden)
        self.assertIn("data-sfb-draft-chip", html)                  # the only addition: a small «not published» status chip
        self.assertIn('name="robots" content="noindex', html)

    def test_a_linked_image_added_to_the_draft_shows_only_in_the_preview(self):
        page = self.draft.get_page("home")
        container = container_service.create_empty_container(page, "single")
        section = StorefrontSection.objects.create(version=self.draft, page=page, section_key="linked_image", order=995)
        container_service.place_section(container.cells.get(), section)
        PromotionalBanner.objects.create(store=self.store, section=section, title="عکس فقط پیش‌نویس", desktop_image=_pic(),
                                         destination_type="external", destination_external_url="https://example.com/draft-only", is_active=True)
        preview = self.admin.get(self.url, {"page": "home"}).content.decode()
        public = self.public.get("/").content.decode()
        self.assertIn("https://example.com/draft-only", preview)
        self.assertIn("عکس فقط پیش‌نویس", preview)
        self.assertNotIn("https://example.com/draft-only", public)

    def test_every_page_type_renders_and_a_second_request_still_shows_the_latest_draft(self):
        for page_type in ("home", "listing", "product_detail", "collection", "search", "cart"):
            self.assertEqual(self.admin.get(self.url, {"page": page_type}).status_code, 200, page_type)
        self._set_announcement("نخستین")
        self.assertContains(self.admin.get(self.url), "نخستین")
        self._set_announcement("دومین")
        response = self.admin.get(self.url)
        self.assertContains(response, "دومین")
        self.assertNotContains(response, "نخستین")
        self.assertIn("no-store", response["Cache-Control"])                         # a refresh never serves an older copy

    def test_it_is_read_only_and_never_publishes(self):
        published = StorefrontLayout.objects.get(store=self.store).published_version_id
        self.assertIsNotNone(published)
        revision, history = self.draft.edit_revision, self.draft.edit_history_entries.count()
        response = self.admin.get(self.url, {"page": "home"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.admin.post(self.url).status_code, 405)
        self.draft.refresh_from_db()
        self.assertEqual(StorefrontLayout.objects.get(store=self.store).published_version_id, published)
        self.assertEqual((self.draft.edit_revision, self.draft.edit_history_entries.count()), (revision, history))

    def test_only_a_manager_of_this_store_can_open_it_and_other_stores_never_leak(self):
        anonymous = Client(HTTP_HOST=ADMIN_HOST).get(self.url)
        self.assertIn(anonymous.status_code, (302, 401, 403))
        self.assertNotIn("data-sfb-draft-chip", anonymous.content.decode() if anonymous.status_code == 200 else "")
        outsider = User.objects.create_user(username="final_qa_outsider", password="pass12345", is_staff=True)
        client = Client(HTTP_HOST=ADMIN_HOST)
        client.login(username="final_qa_outsider", password="pass12345")
        denied = client.get(self.url)
        self.assertNotEqual(denied.status_code, 200)
        self.assertEqual(self.public.get(self.url).status_code in (200, 404, 302, 403), True)
        public_body = self.public.get(self.url)
        self.assertNotContains(public_body, "data-sfb-draft-chip", status_code=public_body.status_code)

    def test_a_store_with_no_draft_says_so_instead_of_pretending(self):
        layout = StorefrontLayout.objects.get(store=self.store)
        layout.draft_version = None
        layout.save(update_fields=["draft_version"])
        html = self.admin.get(self.url).content.decode()
        self.assertIn("بدون تغییر", html)
        self.assertIn("پیش‌نویسی با تغییر منتشرنشده وجود ندارد", html)


class StudioPreviewButtonTests(TestCase):
    """The Studio wires «پیش‌نمایش» to the saved Draft and keeps the published store as its own, clearly named control."""

    JS = (APP / "static" / "storefront_builder" / "r4_studio.js").read_text(encoding="utf-8")
    HTML = (APP / "templates" / "dashboard" / "storefront_builder" / "r4" / "editor.html").read_text(encoding="utf-8")
    SCRIPT = (APP / "static" / "storefront_builder" / "draft_preview.js").read_text(encoding="utf-8")

    def test_two_separate_controls_with_honest_labels(self):
        self.assertRegex(self.HTML, r'data-rastisi-action="public-preview"[^>]*aria-label="پیش‌نمایش تغییرات')
        self.assertRegex(self.HTML, r'data-rastisi-action="view-published"[^>]*aria-label="مشاهدهٔ فروشگاه منتشرشده"')
        self.assertNotIn("نمای عمومی", self.HTML)

    def test_preview_opens_the_draft_after_the_save_is_confirmed_and_never_the_public_url(self):
        case = re.search(r"case 'public-preview':(.*?)case 'view-published':", self.JS, re.S).group(1)
        self.assertIn("openDraftPreview()", case)
        self.assertNotIn("public_url", case)
        body = re.search(r"function openDraftPreview\(\) \{(.*?)\n  \}\n", self.JS, re.S).group(1)
        for needle in ("R4.flushPending", "ui.saveState", "R4.pendingWrites", "DATA.draft_preview_url", "ذخیرهٔ تغییرات تأیید نشد"):
            self.assertIn(needle, body, needle)
        self.assertNotIn("public_url", body)
        self.assertNotIn("fetch(", body)                                              # UI-only: no new write path

    def test_the_link_guard_never_falls_back_to_the_published_store(self):
        self.assertNotIn("fetch(", self.SCRIPT)
        self.assertNotIn("localStorage", self.SCRIPT)
        self.assertIn("evt.preventDefault()", self.SCRIPT)
        self.assertIn("پیش‌نمایش پیش‌نویس", self.SCRIPT)
