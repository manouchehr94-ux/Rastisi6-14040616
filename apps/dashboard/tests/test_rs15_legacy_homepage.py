"""ARCH-02 (supersedes RS-15) — the dashboard hero/banner screens manage the store's SHARED default media
(``section IS NULL``): the template-independent pool every Design Studio section without its own media renders.

They stay fully editable after the Design Studio has published (the pool genuinely drives the storefront), they say
so honestly (no "no effect on the storefront" claim), other stores' ids stay 404, anonymous users are refused, and
an edit is visible to the renderer's fallback straight away."""

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, PromotionalBanner
from apps.stores.models import Store, StoreMembership
from apps.storefront_builder.services import layout_service as svc

User = get_user_model()
HOST = "rs15.rastisi.localhost"


def _img(name="x.png"):
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class LegacyHomepageReadOnlyTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123800001", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123800001", password="pass12345")
        self.slide = HeroSlide.objects.create(store=self.store, section=None, title="قدیمی", desktop_image=_img(), is_active=True)
        self.banner = PromotionalBanner.objects.create(store=self.store, section=None, title="بنر قدیمی", desktop_image=_img(), is_active=True)

    def publish_studio(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_before_studio_the_shared_media_screens_work(self):
        self.assertEqual(self.client.post(reverse("dashboard:hero-toggle", args=[self.slide.pk])).status_code, 302)
        self.slide.refresh_from_db()
        self.assertFalse(self.slide.is_active)
        html = self.client.get(reverse("dashboard:hero-list")).content.decode()
        self.assertIn("اسلاید جدید", html)

    def test_after_studio_the_shared_media_lists_stay_editable_and_say_what_they_do(self):
        self.publish_studio()
        for name, title, add_label in (("hero-list", "قدیمی", "اسلاید جدید"), ("banner-list", "بنر قدیمی", "بنر جدید")):
            html = self.client.get(reverse(f"dashboard:{name}")).content.decode()
            self.assertIn(title, html)
            self.assertIn(add_label, html)                       # still editable
            self.assertIn("/toggle/", html)
            self.assertIn("/delete/", html)
            self.assertIn("رسانه‌های مشترک فروشگاه", html)
            self.assertIn("بلافاصله", html)                      # honest: no Draft for the shared pool
            self.assertNotIn("فقط‌خواندنی", html)
            self.assertNotIn("اثری ندارد", html)                 # the old, false "no effect" claim is gone
            self.assertIn(reverse("dashboard:storefront-builder-r4-editor"), html)

    def test_after_studio_shared_media_edits_apply_and_reach_the_renderer_fallback(self):
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services import render_service

        self.publish_studio()
        resp = self.client.post(reverse("dashboard:hero-toggle", args=[self.slide.pk]))
        self.assertEqual(resp.status_code, 302)
        self.slide.refresh_from_db()
        self.assertFalse(self.slide.is_active)
        self.assertEqual(list(render_service._scoped_hero_slides(self.store, StorefrontSection(section_key="hero_banner"))), [])
        self.client.post(reverse("dashboard:hero-toggle", args=[self.slide.pk]))
        self.assertEqual(
            [s.pk for s in render_service._scoped_hero_slides(self.store, StorefrontSection(section_key="hero_banner"))],
            [self.slide.pk],
        )
        self.assertEqual(self.client.post(reverse("dashboard:banner-delete", args=[self.banner.pk])).status_code, 302)
        self.assertFalse(PromotionalBanner.objects.filter(pk=self.banner.pk).exists())

    def test_foreign_store_ids_stay_404_after_studio(self):
        self.publish_studio()
        other = Store.objects.create(name="دیگر", slug="rs15-other")
        foreign = HeroSlide.objects.create(store=other, section=None, title="بیگانه", desktop_image=_img(), is_active=True)
        self.assertEqual(self.client.post(reverse("dashboard:hero-toggle", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:hero-delete", args=[foreign.pk])).status_code, 404)
        foreign.refresh_from_db()
        self.assertTrue(foreign.is_active)

    def test_anonymous_cannot_reach_the_screens(self):
        self.publish_studio()
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("dashboard:hero-list")).status_code, 200)
        self.assertNotEqual(self.client.post(reverse("dashboard:hero-delete", args=[self.slide.pk])).status_code, 200)
        self.assertTrue(HeroSlide.objects.filter(pk=self.slide.pk).exists())
