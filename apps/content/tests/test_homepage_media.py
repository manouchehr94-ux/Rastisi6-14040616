"""تست‌های مدل‌ها و رندر اسلاید و بنر صفحه اصلی."""

from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import (
    HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES,
    DestinationType,
    HeroSlide,
    PromotionalBanner,
    validate_image_size,
)
from django.utils import timezone

from apps.content.services import resolve_destination_url
from apps.stores.models import Store, StoreMembership


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")

User = get_user_model()


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class HeroSlideModelTests(TestCase):
    def test_valid_creation(self):
        slide = HeroSlide.objects.create(store=_akhlaghi(), 
            title="تست", desktop_image=_img(), is_active=True, display_order=0
        )
        self.assertEqual(slide.title, "تست")

    def test_desktop_image_required(self):
        slide = HeroSlide(title="No img")
        with self.assertRaises(Exception):
            slide.full_clean()

    def test_mobile_image_optional(self):
        slide = HeroSlide(title="OK", desktop_image=_img())
        slide.full_clean()  # Should not raise

    def test_button_label_required_when_visible(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True, button_label="",
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://example.com",
        )
        with self.assertRaises(ValidationError) as ctx:
            slide.full_clean()
        self.assertIn("button_label", ctx.exception.message_dict)

    def test_destination_required_when_button_visible(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True,
            button_label="کلیک", destination_type=DestinationType.NONE,
        )
        with self.assertRaises(ValidationError):
            slide.full_clean()

    def test_hidden_button_no_destination_ok(self):
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=False,
            destination_type=DestinationType.NONE,
        )
        slide.full_clean()  # OK

    def test_ordering(self):
        HeroSlide.objects.create(store=_akhlaghi(), title="B", desktop_image=_img(), display_order=2)
        HeroSlide.objects.create(store=_akhlaghi(), title="A", desktop_image=_img(), display_order=1)
        slides = list(HeroSlide.objects.values_list("title", flat=True))
        self.assertEqual(slides, ["A", "B"])

    def test_destination_resolves(self):
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="V", slug="v")
        cat = Category.objects.create(store=store, name="C", slug="c")
        slide = HeroSlide(
            title="T", desktop_image=_img(), show_button=True,
            button_label="مشاهده", destination_type=DestinationType.CATEGORY,
            destination_category=cat,
        )
        url = resolve_destination_url(slide)
        self.assertIn("category=c", url)


class PromotionalBannerModelTests(TestCase):
    def test_valid_creation(self):
        banner = PromotionalBanner.objects.create(store=_akhlaghi(), 
            title="بنر", desktop_image=_img(), is_active=True,
        )
        self.assertTrue(banner.pk)

    def test_button_label_required_when_visible(self):
        banner = PromotionalBanner(
            title="B", desktop_image=_img(), show_button=True, button_label="",
            destination_type=DestinationType.EXTERNAL,
            destination_external_url="https://x.com",
        )
        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_inactive_not_in_active_queryset(self):
        PromotionalBanner.objects.create(store=_akhlaghi(), title="Active", desktop_image=_img(), is_active=True)
        PromotionalBanner.objects.create(store=_akhlaghi(), title="Inactive", desktop_image=_img(), is_active=False)
        active = PromotionalBanner.objects.filter(is_active=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().title, "Active")


class HomepageRenderingTests(TestCase):
    def setUp(self):
        self.slide = HeroSlide.objects.create(store=_akhlaghi(), 
            title="اسلاید فعال", desktop_image=_img("hero.png"),
            is_active=True, display_order=0,
        )
        self.inactive_slide = HeroSlide.objects.create(store=_akhlaghi(), 
            title="غیرفعال", desktop_image=_img("hero2.png"),
            is_active=False, display_order=1,
        )

    def test_active_slide_on_homepage(self):
        response = self.client.get("/")
        self.assertContains(response, "اسلاید فعال")

    def test_inactive_slide_hidden(self):
        response = self.client.get("/")
        self.assertNotContains(response, "غیرفعال")



class BannerRenderingTests(TestCase):
    def setUp(self):
        self.banner = PromotionalBanner.objects.create(store=_akhlaghi(), 
            title="بنر فعال", description="توضیح بنر",
            desktop_image=_img("banner.png"), is_active=True,
        )
        self.inactive = PromotionalBanner.objects.create(store=_akhlaghi(), 
            title="غیرفعال", desktop_image=_img("b2.png"), is_active=False,
        )

    def test_active_banner_on_homepage(self):
        response = self.client.get("/")
        self.assertContains(response, "بنر فعال")

    def test_inactive_banner_hidden(self):
        response = self.client.get("/")
        self.assertNotContains(response, "غیرفعال")

    def test_banner_description_rendered(self):
        response = self.client.get("/")
        self.assertContains(response, "توضیح بنر")


class DashboardHeroCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="pass!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff", password="pass!")

    def test_hero_list_accessible(self):
        response = self.client.get(reverse("dashboard:hero-list"))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:hero-list"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_create_hero(self):
        response = self.client.post(reverse("dashboard:hero-add"), {
            "title": "New Slide", "subtitle": "", "button_label": "",
            "destination_type": "none", "destination_external_url": "",
            "display_order": "0", "desktop_image": _img("new.png"),
        })
        self.assertRedirects(response, reverse("dashboard:hero-list"))
        self.assertTrue(HeroSlide.objects.filter(title="New Slide").exists())

    def test_toggle_hero(self):
        slide = HeroSlide.objects.create(store=_akhlaghi(), title="T", desktop_image=_img(), is_active=True)
        self.client.post(reverse("dashboard:hero-toggle", args=[slide.pk]))
        slide.refresh_from_db()
        self.assertFalse(slide.is_active)

    def test_delete_hero_post_only(self):
        slide = HeroSlide.objects.create(store=_akhlaghi(), title="T", desktop_image=_img())
        response = self.client.get(reverse("dashboard:hero-delete", args=[slide.pk]))
        self.assertEqual(response.status_code, 405)

    def test_no_deprecation_notice_when_builder_not_published(self):
        """چکپوینتِ بازبینیِ نهایی (بخشِ ۲۳): تا وقتی سازنده بصری برایِ
        این فروشگاه منتشر نشده، این صفحه هنوز مسیرِ واقعیِ ویرایشِ
        اسلایدر است — نباید هشدارِ «دیگر اثری ندارد» نشان دهد."""
        response = self.client.get(reverse("dashboard:hero-list"))
        self.assertNotContains(response, "دیگر روی صفحه‌ی عمومی اثری ندارد")

    def test_deprecation_notice_when_builder_published(self):
        from apps.storefront_builder.services import layout_service as sfb_svc

        store = _akhlaghi()
        sfb_svc.get_or_create_draft(store)
        sfb_svc.publish(store)

        response = self.client.get(reverse("dashboard:hero-list"))
        self.assertContains(response, "دیگر روی صفحه‌ی عمومی اثری ندارد")


class DashboardBannerCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="staff", password="pass!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff", password="pass!")

    def test_banner_list_accessible(self):
        response = self.client.get(reverse("dashboard:banner-list"))
        self.assertEqual(response.status_code, 200)

    def test_create_banner(self):
        response = self.client.post(reverse("dashboard:banner-add"), {
            "title": "New Banner", "description": "", "button_label": "",
            "destination_type": "none", "destination_external_url": "",
            "display_order": "0", "desktop_image": _img("bn.png"),
        })
        self.assertRedirects(response, reverse("dashboard:banner-list"))
        self.assertTrue(PromotionalBanner.objects.filter(title="New Banner").exists())

    def test_toggle_banner(self):
        b = PromotionalBanner.objects.create(store=_akhlaghi(), title="B", desktop_image=_img(), is_active=True)
        self.client.post(reverse("dashboard:banner-toggle", args=[b.pk]))
        b.refresh_from_db()
        self.assertFalse(b.is_active)

    def test_delete_banner_post_only(self):
        b = PromotionalBanner.objects.create(store=_akhlaghi(), title="B", desktop_image=_img())
        response = self.client.get(reverse("dashboard:banner-delete", args=[b.pk]))
        self.assertEqual(response.status_code, 405)


class EmptyStateTests(TestCase):
    def test_homepage_works_with_no_managed_content(self):
        """No active hero slides or banners → promotional sections omitted, page loads OK."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # No hardcoded hero campaign fallback should appear
        self.assertNotContains(response, "هر آنچه نیاز دارید، یک\u200cجا")
        # Banner section should not render hardcoded promo
        self.assertNotContains(response, "آخرین تخفیف\u200cها را از دست ندهید")

    def test_all_inactive_hero_omits_section(self):
        """All hero slides inactive → hero section absent."""
        HeroSlide.objects.create(store=_akhlaghi(), title="غیرفعال", desktop_image=_img(), is_active=False)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "غیرفعال")
        # No hardcoded hero campaign fallback
        self.assertNotContains(response, "هر آنچه نیاز دارید، یک\u200cجا")

    def test_all_inactive_banners_omits_section(self):
        """All banners inactive → banner section absent."""
        PromotionalBanner.objects.create(store=_akhlaghi(), title="بنر خاموش", desktop_image=_img(), is_active=False)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "بنر خاموش")
        self.assertNotContains(response, "آخرین تخفیف\u200cها را از دست ندهید")

    def test_other_homepage_sections_render_without_managed_content(self):
        """Category tiles and other sections remain even without hero/banners."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # Other section markers should still render
        self.assertContains(response, "محصولات پرفروش")




class ImageSizeValidatorTests(TestCase):
    """تست‌های اعتبارسنجی حجم تصویر — حداکثر ۵ مگابایت."""

    def test_at_limit_accepted(self):
        """File exactly at 5 MiB passes validation."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        f = SimpleUploadedFile("ok.png", buf.getvalue(), content_type="image/png")
        f.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES  # exactly at limit
        validate_image_size(f)  # Should not raise

    def test_over_limit_rejected(self):
        """File over 5 MiB is rejected."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        f = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
        f.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES + 1
        with self.assertRaises(ValidationError) as ctx:
            validate_image_size(f)
        self.assertIn("مگابایت", str(ctx.exception.message))

    def test_hero_desktop_oversized_rejected(self):
        """HeroSlide with oversized desktop image fails full_clean."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        f = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
        f.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES + 1024
        slide = HeroSlide(title="Big", desktop_image=f)
        with self.assertRaises(ValidationError):
            slide.full_clean()

    def test_hero_mobile_oversized_rejected(self):
        """HeroSlide with oversized mobile image fails full_clean."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        big = SimpleUploadedFile("big_m.png", buf.getvalue(), content_type="image/png")
        big.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES + 1024
        slide = HeroSlide(title="M", desktop_image=_img(), mobile_image=big)
        with self.assertRaises(ValidationError):
            slide.full_clean()

    def test_banner_desktop_oversized_rejected(self):
        """PromotionalBanner with oversized desktop image fails full_clean."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        f = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
        f.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES + 1
        banner = PromotionalBanner(title="Big", desktop_image=f)
        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_banner_mobile_oversized_rejected(self):
        """PromotionalBanner with oversized mobile image fails full_clean."""
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        big = SimpleUploadedFile("big_m.png", buf.getvalue(), content_type="image/png")
        big.size = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES + 1
        banner = PromotionalBanner(title="B", desktop_image=_img(), mobile_image=big)
        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_valid_size_hero_passes(self):
        """Normal-size image passes."""
        slide = HeroSlide(title="OK", desktop_image=_img())
        slide.full_clean()  # No exception


class TransactionSafeFileLifecycleTests(TransactionTestCase):
    """تست‌های چرخه‌ی زندگی فایل — حذف فقط پس از commit موفق.

    ``TransactionTestCase`` flushes (truncates) every table in its own
    teardown — including ``stores_store`` — which would otherwise
    permanently delete the Akhlaghi Store (and, via CASCADE, its
    ShopSettings/FooterSettings) for every later test in the same run,
    since every page render in this test class goes through the
    Store-aware ``shop_settings``/``footer_settings`` context processors.
    ``_fixture_teardown`` is overridden to reseed Akhlaghi (and its
    settings) after the base flush — deliberately not
    ``serialized_rollback = True``, which collides with flush's own
    ``post_migrate`` signal and raises a ``django_content_type`` duplicate-
    key error (see ``apps.stores.tests.test_resolution`` for the same
    lesson learned on the resolver's own migration-executor test).
    """

    def setUp(self):
        self.staff = User.objects.create_user(username="staff_lc", password="pass!", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="staff_lc", password="pass!")

    def _fixture_teardown(self):
        super()._fixture_teardown()
        from apps.content.models import FooterSettings
        from apps.core.models import ShopSettings
        from apps.stores.models import Store

        store, _ = Store.objects.get_or_create(
            slug="akhlaghi", defaults={"name": "Akhlaghi", "status": Store.Status.ACTIVE}
        )
        ShopSettings.provision_for(store)
        FooterSettings.provision_for(store)

    def test_hero_delete_retains_file_after_commit(self):
        """MED-001 (Retention-First, architect decision — supersedes the
        old, misleadingly-named ``test_hero_delete_removes_files_after_
        commit``, which passed only because it never actually asserted on
        storage state at all): deleting a hero row via the real endpoint
        deletes the row, but the physical file is intentionally RETAINED
        — this class is a ``TransactionTestCase``, so the view's own
        transaction really commits and ``transaction.on_commit`` fires
        naturally; no ``captureOnCommitCallbacks`` wrapper is needed or
        available here."""
        slide = HeroSlide.objects.create(store=_akhlaghi(), title="D", desktop_image=_img("del_hero.png"), is_active=True)
        desktop_name = slide.desktop_image.name
        storage = slide.desktop_image.storage
        self.assertTrue(storage.exists(desktop_name))

        response = self.client.post(reverse("dashboard:hero-delete", args=[slide.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HeroSlide.objects.filter(pk=slide.pk).exists())
        # Retention-First: the physical file remains after commit.
        self.assertTrue(storage.exists(desktop_name))

    def test_banner_delete_retains_file_after_commit(self):
        """MED-001 (Retention-First, architect decision — supersedes the
        old, misleadingly-named ``test_banner_delete_removes_files_after_
        commit``): same contract as the Hero test above, for
        ``PromotionalBanner``."""
        banner = PromotionalBanner.objects.create(store=_akhlaghi(), title="D", desktop_image=_img("del_b.png"), is_active=True)
        desktop_name = banner.desktop_image.name
        storage = banner.desktop_image.storage
        self.assertTrue(storage.exists(desktop_name))

        response = self.client.post(reverse("dashboard:banner-delete", args=[banner.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PromotionalBanner.objects.filter(pk=banner.pk).exists())
        # Retention-First: the physical file remains after commit.
        self.assertTrue(storage.exists(desktop_name))

    def test_failed_validation_preserves_existing_hero_image(self):
        """If validation fails on edit, existing desktop image is preserved."""
        slide = HeroSlide.objects.create(store=_akhlaghi(), 
            title="Keep", desktop_image=_img("keep.png"), is_active=True
        )
        original_name = slide.desktop_image.name

        # Submit invalid form (show_button=on but no destination)
        self.client.post(reverse("dashboard:hero-edit", args=[slide.pk]), {
            "title": "Keep",
            "subtitle": "",
            "button_label": "",
            "show_button": "on",  # Invalid: button visible without label/destination
            "destination_type": "none",
            "destination_external_url": "",
            "display_order": "0",
        })
        slide.refresh_from_db()
        # Original image should remain untouched
        self.assertEqual(slide.desktop_image.name, original_name)

    def test_failed_validation_preserves_existing_banner_image(self):
        """If validation fails on banner edit, existing desktop image is preserved."""
        banner = PromotionalBanner.objects.create(store=_akhlaghi(), 
            title="Keep", desktop_image=_img("keep_b.png"), is_active=True
        )
        original_name = banner.desktop_image.name

        # Submit invalid form
        self.client.post(reverse("dashboard:banner-edit", args=[banner.pk]), {
            "title": "Keep",
            "description": "",
            "button_label": "",
            "show_button": "on",
            "destination_type": "none",
            "destination_external_url": "",
            "display_order": "0",
        })
        banner.refresh_from_db()
        self.assertEqual(banner.desktop_image.name, original_name)
