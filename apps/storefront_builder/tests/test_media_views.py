from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-media-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class MediaViewsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="media_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="media_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.filter(section_key__in=["hero_banner", "multi_banner", "story_rail"]).delete()
        self.hero_section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=900)
        self.banner_section = StorefrontSection.objects.create(version=self.draft, section_key="multi_banner", order=901)
        self.story_section = StorefrontSection.objects.create(version=self.draft, section_key="story_rail", order=902)


class HeroSlideCrudTests(MediaViewsTestCase):
    def test_media_list_page_renders(self):
        """رگرسیونِ باگِ واقعی: ``{% load storefront_builder_extras %}``
        بعد از اولین استفاده از فیلترِ ``section_label`` (در
        ``{% block title %}``) آمده بود — یعنی خودِ صفحه‌ی «مدیریت
        اسلایدها» با TemplateSyntaxError کرش می‌کرد. هیچ تستِ قبلی این
        مسیرِ GET را صدا نمی‌زد (فقط POSTِ افزودن/ویرایش/حذف تست شده
        بودند)، پس این کرش فقط با یک بازدیدِ واقعیِ مرورگر پیدا شد."""
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "hero-slides"])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "اسلایدر اصلی")

    def test_add_slide(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "اسلاید تست", "subtitle": "زیر", "show_button": "on", "button_label": "برو",
             "destination_type": "external", "destination_external_url": "https://example.com",
             "desktop_image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        slide = HeroSlide.objects.get(section=self.hero_section)
        self.assertEqual(slide.title, "اسلاید تست")
        self.assertEqual(slide.store_id, self.store.pk)

    def test_add_form_shows_search_and_cart_destination_options(self):
        """چکپوینتِ سازگاریِ Phase 3: این فرمِ جداگانه (نه بلوکِ JSONِ
        section_destination_fields.html) هم باید همان دو مقصدِ جدید را
        نشان دهد — قراردادِ مقصد باید یکسان باشد، هرچه UI آن دو باشد."""
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"])
        )
        self.assertContains(resp, '<option value="search">')
        self.assertContains(resp, '<option value="cart">')

    def test_add_slide_with_search_destination(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "اسلایدِ جستجو", "destination_type": "search", "desktop_image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        slide = HeroSlide.objects.get(section=self.hero_section)
        self.assertEqual(slide.destination_type, "search")

    def test_add_slide_without_image_rejected(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "بدون تصویر", "destination_type": "none"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(HeroSlide.objects.filter(section=self.hero_section).exists())

    def test_edit_slide(self):
        slide = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="قدیم", desktop_image=_img())
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.hero_section.pk, "hero-slides", slide.pk]),
            {"title": "جدید", "destination_type": "none", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        slide.refresh_from_db()
        self.assertEqual(slide.title, "جدید")

    def test_delete_slide(self):
        slide = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="حذف‌شو", desktop_image=_img())
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-delete", args=[self.hero_section.pk, "hero-slides", slide.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(HeroSlide.objects.filter(pk=slide.pk).exists())

    def test_toggle_slide(self):
        slide = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="ت", desktop_image=_img(), is_active=True)
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-toggle", args=[self.hero_section.pk, "hero-slides", slide.pk]),
        )
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)

    def test_reorder_slides(self):
        s1 = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="1", desktop_image=_img(), display_order=0)
        s2 = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="2", desktop_image=_img(), display_order=1)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-reorder", args=[self.hero_section.pk, "hero-slides"]),
            {"item_ids": [str(s2.pk), str(s1.pk)]},
        )
        self.assertEqual(resp.status_code, 200)
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s2.display_order, 0)
        self.assertEqual(s1.display_order, 1)

    def test_move_up(self):
        s1 = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="1", desktop_image=_img(), display_order=0)
        s2 = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="2", desktop_image=_img(), display_order=1)
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-move", args=[self.hero_section.pk, "hero-slides", s2.pk]),
            {"direction": "up"},
        )
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s2.display_order, 0)
        self.assertEqual(s1.display_order, 1)

    def test_wrong_kind_for_section_type_is_404(self):
        """اسلاید نمی‌تواند به یک section از نوعِ product_section وصل شود —
        allowlistِ ``section_keys`` در ``_media_config`` باید رد کند."""
        other_section = StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=902)
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[other_section.pk, "hero-slides"]),
        )
        self.assertEqual(resp.status_code, 404)

    def test_unknown_kind_is_404(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "not-a-real-kind"]),
        )
        self.assertEqual(resp.status_code, 404)


class BannerCrudTests(MediaViewsTestCase):
    def test_media_list_page_renders(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.banner_section.pk, "banners"])
        )
        self.assertEqual(resp.status_code, 200)

    def test_add_banner(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.banner_section.pk, "banners"]),
            {"title": "بنر تست", "description": "توضیح", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        banner = PromotionalBanner.objects.get(section=self.banner_section)
        self.assertEqual(banner.title, "بنر تست")

    def test_add_banner_with_cart_destination(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.banner_section.pk, "banners"]),
            {"title": "بنرِ سبد خرید", "destination_type": "cart", "desktop_image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        banner = PromotionalBanner.objects.get(section=self.banner_section)
        self.assertEqual(banner.destination_type, "cart")

    def test_external_link_with_dangerous_scheme_rejected(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.banner_section.pk, "banners"]),
            {"title": "بنر", "destination_type": "external", "destination_external_url": "javascript:alert(1)",
             "desktop_image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PromotionalBanner.objects.filter(section=self.banner_section).exists())


class StoryRailItemCrudTests(MediaViewsTestCase):
    """Phase 4 (Task 6) — ``StoryRailItem`` has one ``image`` field, not the
    desktop/mobile pair ``HeroSlide``/``PromotionalBanner`` have.
    ``storefront_section_media_form`` used to hardcode that pair (reading
    ``obj.desktop_image``/``obj.mobile_image`` unconditionally), which meant
    editing (not creating — ``obj.pk`` being falsy on create short-circuited
    the crash) any existing story item raised ``AttributeError`` — a live,
    reachable 500 for any merchant clicking "ویرایش" on a story rail item.
    Fixed by making the form's file-field handling config-driven
    (``_MEDIA_KINDS[kind]["file_fields"]``)."""

    def test_media_list_page_renders(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.story_section.pk, "story-items"])
        )
        self.assertEqual(resp.status_code, 200)

    def test_add_form_shows_single_image_field_not_desktop_mobile(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.story_section.pk, "story-items"])
        )
        self.assertNotContains(resp, "تصویر دسکتاپ")
        self.assertNotContains(resp, "تصویر موبایل")
        self.assertContains(resp, 'name="image"')

    def test_add_form_renders_title_input_exactly_once(self):
        """Phase 4 (Task 6, Group F correction) — ``story-items``' kind-
        specific text field IS ``title`` (unlike ``hero-slides``'
        ``subtitle``/``banners``' ``description``), so the form's generic
        title block and its kind-specific text-field block used to both
        render a ``name="title"`` input. A browser posts duplicate keys as
        a list; Django's ``QueryDict.get`` returns the LAST one, so the
        merchant's typed title was silently discarded on every save."""
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.story_section.pk, "story-items"])
        )
        self.assertEqual(resp.content.decode().count('name="title"'), 1)

    def test_add_story_item_title_is_actually_saved(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.story_section.pk, "story-items"]),
            {"title": "عنوان تایپ‌شده", "destination_type": "none", "image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        item = StoryRailItem.objects.get(section=self.story_section)
        self.assertEqual(item.title, "عنوان تایپ‌شده")

    def test_add_story_item(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.story_section.pk, "story-items"]),
            {"title": "استوری تست", "destination_type": "none", "image": _img(), "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        item = StoryRailItem.objects.get(section=self.story_section)
        self.assertEqual(item.title, "استوری تست")
        self.assertEqual(item.store_id, self.store.pk)
        self.assertIsNotNone(item.image_asset_id)

    def test_add_story_item_without_image_rejected(self):
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.story_section.pk, "story-items"]),
            {"title": "بدون تصویر", "destination_type": "none"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(StoryRailItem.objects.filter(section=self.story_section).exists())

    def test_edit_story_item_title_only_does_not_crash(self):
        """The real defect: an edit that touches no file field used to raise
        ``AttributeError`` unconditionally on ``obj.desktop_image``."""
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="قدیم", image=_img())
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.story_section.pk, "story-items", item.pk]),
            {"title": "جدید", "destination_type": "none", "is_active": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.title, "جدید")

    def test_edit_story_item_replaces_image_and_creates_new_asset(self):
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="قدیم", image=_img("first.png"))
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.story_section.pk, "story-items", item.pk]),
            {"title": "قدیم", "destination_type": "none", "is_active": "on", "image": _img("second.png")},
        )
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertIn("second", item.image.name)
        self.assertEqual(MediaAsset.objects.get(pk=item.image_asset_id).image, item.image.name)

    def test_media_list_shows_story_item_thumbnail(self):
        """Phase 4 (Task 6, Group F correction) — the list partial used to
        read ``item.desktop_image_url`` unconditionally, which does not
        exist on ``StoryRailItem`` (its own resolved property is
        ``image_url``); Django's template lookup swallows the
        ``AttributeError``, so every story item rendered with no thumbnail
        at all. Fixed via a per-kind ``thumb_field`` config entry."""
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="ت", image=_img())
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.story_section.pk, "story-items"])
        )
        self.assertContains(resp, f'<img src="{item.image_url}"')

    def test_delete_story_item(self):
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="حذف‌شو", image=_img())
        resp = self.client.post(
            reverse("dashboard:storefront-builder-section-media-delete", args=[self.story_section.pk, "story-items", item.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(StoryRailItem.objects.filter(pk=item.pk).exists())

    def test_toggle_story_item(self):
        item = StoryRailItem.objects.create(store=self.store, section=self.story_section, title="ت", image=_img(), is_active=True)
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-toggle", args=[self.story_section.pk, "story-items", item.pk]),
        )
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_wrong_kind_for_section_type_is_404(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "story-items"]),
        )
        self.assertEqual(resp.status_code, 404)


class MediaCrossStoreIsolationTests(MediaViewsTestCase):
    def setUp(self):
        super().setUp()
        self.other_store = Store.objects.create(
            name="فروشگاه دیگر رسانه", slug="sfb-media-other", admin_subdomain="sfb-media-other", status=Store.Status.ACTIVE,
        )
        self.other_staff = User.objects.create_user(username="media_other_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.other_store, user=self.other_staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.other_client = Client(HTTP_HOST="sfb-media-other.rastisi.localhost")
        self.other_client.login(username="media_other_owner", password="pass12345")

    def test_other_store_cannot_see_section_media_list(self):
        resp = self.other_client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "hero-slides"]),
        )
        self.assertEqual(resp.status_code, 404)

    def test_other_store_cannot_edit_slide(self):
        slide = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="محرمانه", desktop_image=_img())
        resp = self.other_client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.hero_section.pk, "hero-slides", slide.pk]),
            {"title": "دستکاری‌شده", "destination_type": "none"},
        )
        self.assertEqual(resp.status_code, 404)
        slide.refresh_from_db()
        self.assertEqual(slide.title, "محرمانه")

    def test_other_store_cannot_delete_slide(self):
        slide = HeroSlide.objects.create(store=self.store, section=self.hero_section, title="محرمانه", desktop_image=_img())
        resp = self.other_client.post(
            reverse("dashboard:storefront-builder-section-media-delete", args=[self.hero_section.pk, "hero-slides", slide.pk]),
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(HeroSlide.objects.filter(pk=slide.pk).exists())

    def test_anonymous_denied(self):
        self.client.logout()
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-media-list", args=[self.hero_section.pk, "hero-slides"]),
        )
        self.assertEqual(resp.status_code, 302)
