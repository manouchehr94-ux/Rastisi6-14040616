"""PR #18 finding #11 — the legacy dashboard Hero screens must only ever see and
change STORE-WIDE slides (``section IS NULL``). Section-scoped rows belong to a
Draft/Published layout version and are managed through the R4 media manager.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner
from apps.stores.models import Store, StoreDomain

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import _scoped_banners, _scoped_hero_slides

from .test_media_views import MediaViewsTestCase, _img


class LegacyHeroIsolationTests(MediaViewsTestCase):
    def setUp(self):
        super().setUp()
        self.wide = HeroSlide.objects.create(
            store=self.store, section=None, title="سراسری", desktop_image=_img("w.png"), is_active=True,
        )
        asset = MediaAsset.objects.create(store=self.store, image="x/scoped.png")
        self.draft_slide = HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="پیش‌نویس",
            desktop_asset=asset, is_active=True,
        )

    def published_slide(self):
        svc.publish(self.store, user=self.staff)
        row = HeroSlide.objects.filter(
            store=self.store, section__page__version__status="published",
        ).first()
        self.assertIsNotNone(row, "publish should clone the asset-backed slide")
        return row

    # --- list -------------------------------------------------------------
    def test_list_shows_only_store_wide_slides(self):
        resp = self.client.get(reverse("dashboard:hero-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([s.pk for s in resp.context["slides"]], [self.wide.pk])

    def test_list_hides_published_scoped_slides_too(self):
        pub = self.published_slide()
        resp = self.client.get(reverse("dashboard:hero-list"))
        self.assertNotIn(pub.pk, [s.pk for s in resp.context["slides"]])
        self.assertNotIn(self.draft_slide.pk, [s.pk for s in resp.context["slides"]])

    # --- direct-ID access: edit / toggle / delete -------------------------
    def _assert_untouched(self, row, title, active):
        row.refresh_from_db()
        self.assertEqual((row.title, row.is_active), (title, active))

    def test_direct_edit_of_draft_scoped_slide_is_404(self):
        url = reverse("dashboard:hero-edit", args=[self.draft_slide.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"title": "هک", "is_active": "on"}).status_code, 404)
        self._assert_untouched(self.draft_slide, "پیش‌نویس", True)

    def test_direct_toggle_and_delete_of_draft_scoped_slide_are_404(self):
        self.assertEqual(self.client.post(reverse("dashboard:hero-toggle", args=[self.draft_slide.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:hero-delete", args=[self.draft_slide.pk])).status_code, 404)
        self._assert_untouched(self.draft_slide, "پیش‌نویس", True)

    def test_direct_edit_toggle_delete_of_published_scoped_slide_are_404(self):
        pub = self.published_slide()
        title, active = pub.title, pub.is_active
        self.assertEqual(self.client.post(reverse("dashboard:hero-edit", args=[pub.pk]), {"title": "هک"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:hero-toggle", args=[pub.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:hero-delete", args=[pub.pk])).status_code, 404)
        self._assert_untouched(pub, title, active)

    # --- tenant isolation -------------------------------------------------
    def test_other_stores_store_wide_slide_is_404(self):
        other = Store.objects.create(name="فروشگاه دیگر", slug="other-legacy-hero")
        row = HeroSlide.objects.create(store=other, section=None, title="بیگانه", desktop_image=_img(), is_active=True)
        for name in ("hero-edit", "hero-toggle", "hero-delete"):
            self.assertEqual(self.client.post(reverse(f"dashboard:{name}", args=[row.pk])).status_code, 404, name)
        self.assertTrue(HeroSlide.objects.filter(pk=row.pk, title="بیگانه", is_active=True).exists())
        resp = self.client.get(reverse("dashboard:hero-list"))
        self.assertNotIn(row.pk, [s.pk for s in resp.context["slides"]])

    # --- normal legacy behaviour is preserved -----------------------------
    def test_store_wide_edit_toggle_delete_still_work(self):
        edit = reverse("dashboard:hero-edit", args=[self.wide.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        resp = self.client.post(edit, {"title": "تازه", "is_active": "on", "destination_type": "none", "display_order": "0"})
        self.assertEqual(resp.status_code, 302)
        self._assert_untouched(self.wide, "تازه", True)
        self.assertEqual(self.client.post(reverse("dashboard:hero-toggle", args=[self.wide.pk])).status_code, 302)
        self._assert_untouched(self.wide, "تازه", False)
        self.assertEqual(self.client.post(reverse("dashboard:hero-delete", args=[self.wide.pk])).status_code, 302)
        self.assertFalse(HeroSlide.objects.filter(pk=self.wide.pk).exists())

    def test_legacy_create_makes_a_store_wide_slide(self):
        resp = self.client.post(reverse("dashboard:hero-add"), {
            "title": "جدید", "is_active": "on", "destination_type": "none",
            "display_order": "5", "desktop_image": _img(),
        })
        self.assertEqual(resp.status_code, 302)
        created = HeroSlide.objects.get(title="جدید")
        self.assertIsNone(created.section_id)
        self.assertEqual(created.store_id, self.store.pk)

    def test_r4_default_fallback_is_unchanged(self):
        # A section with no active own slide still falls back to the store-wide row.
        self.draft_slide.delete()
        self.assertEqual([s.pk for s in _scoped_hero_slides(self.store, self.hero_section)], [self.wide.pk])


class LegacyBannerIsolationTests(MediaViewsTestCase):
    """Same store-wide-only contract for the legacy Banner screens."""

    def setUp(self):
        super().setUp()
        self.wide = PromotionalBanner.objects.create(
            store=self.store, section=None, title="بنر سراسری", desktop_image=_img("bw.png"), is_active=True,
        )
        asset = MediaAsset.objects.create(store=self.store, image="x/scoped-banner.png")
        self.draft_banner = PromotionalBanner.objects.create(
            store=self.store, section=self.banner_section, title="بنر پیش‌نویس",
            desktop_asset=asset, is_active=True,
        )

    def published_banner(self):
        svc.publish(self.store, user=self.staff)
        row = PromotionalBanner.objects.filter(
            store=self.store, section__page__version__status="published",
        ).first()
        self.assertIsNotNone(row, "publish should clone the asset-backed banner")
        return row

    def test_list_shows_only_store_wide_banners_even_after_publish(self):
        pub = self.published_banner()
        resp = self.client.get(reverse("dashboard:banner-list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([b.pk for b in resp.context["banners"]], [self.wide.pk])
        self.assertNotIn(pub.pk, [b.pk for b in resp.context["banners"]])

    def _assert_untouched(self, row, title, active):
        row.refresh_from_db()
        self.assertEqual((row.title, row.is_active), (title, active))

    def test_direct_id_access_to_draft_scoped_banner_is_404(self):
        edit = reverse("dashboard:banner-edit", args=[self.draft_banner.pk])
        self.assertEqual(self.client.get(edit).status_code, 404)
        self.assertEqual(self.client.post(edit, {"title": "هک", "is_active": "on"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:banner-toggle", args=[self.draft_banner.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:banner-delete", args=[self.draft_banner.pk])).status_code, 404)
        self._assert_untouched(self.draft_banner, "بنر پیش‌نویس", True)

    def test_direct_id_access_to_published_scoped_banner_is_404(self):
        pub = self.published_banner()
        title, active = pub.title, pub.is_active
        self.assertEqual(self.client.post(reverse("dashboard:banner-edit", args=[pub.pk]), {"title": "هک"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:banner-toggle", args=[pub.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("dashboard:banner-delete", args=[pub.pk])).status_code, 404)
        self._assert_untouched(pub, title, active)

    def test_other_stores_banner_is_404(self):
        other = Store.objects.create(name="فروشگاه دیگر", slug="other-legacy-banner")
        row = PromotionalBanner.objects.create(store=other, section=None, title="بیگانه", desktop_image=_img(), is_active=True)
        for name in ("banner-edit", "banner-toggle", "banner-delete"):
            self.assertEqual(self.client.post(reverse(f"dashboard:{name}", args=[row.pk])).status_code, 404, name)
        self.assertTrue(PromotionalBanner.objects.filter(pk=row.pk, is_active=True).exists())

    def test_store_wide_edit_toggle_delete_create_still_work(self):
        edit = reverse("dashboard:banner-edit", args=[self.wide.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        resp = self.client.post(edit, {"title": "تازه", "is_active": "on", "destination_type": "none", "display_order": "0"})
        self.assertEqual(resp.status_code, 302)
        self._assert_untouched(self.wide, "تازه", True)
        self.assertEqual(self.client.post(reverse("dashboard:banner-toggle", args=[self.wide.pk])).status_code, 302)
        self._assert_untouched(self.wide, "تازه", False)
        self.assertEqual(self.client.post(reverse("dashboard:banner-delete", args=[self.wide.pk])).status_code, 302)
        self.assertFalse(PromotionalBanner.objects.filter(pk=self.wide.pk).exists())
        resp = self.client.post(reverse("dashboard:banner-add"), {
            "title": "جدید", "is_active": "on", "destination_type": "none", "display_order": "3", "desktop_image": _img(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(PromotionalBanner.objects.get(title="جدید").section_id)

    def test_r4_banner_fallback_is_unchanged(self):
        self.draft_banner.delete()
        self.assertEqual([b.pk for b in _scoped_banners(self.store, self.banner_section)], [self.wide.pk])


@override_settings(ALLOWED_HOSTS=["legacy-home.example.com", "testserver"])
class LegacyPublicHomepageMediaTests(TestCase):
    """The legacy (non-visual-shell) public homepage must never render
    section-scoped — i.e. Draft/R4-managed — media."""

    HOST = "legacy-home.example.com"

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=self.HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.draft = svc.get_or_create_draft(self.store)
        self.hero_section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=900)
        self.banner_section = StorefrontSection.objects.create(version=self.draft, section_key="multi_banner", order=901)
        self.wide_slide = HeroSlide.objects.create(
            store=self.store, section=None, title="سراسری", desktop_image=_img("hw.png"), is_active=True)
        self.wide_banner = PromotionalBanner.objects.create(
            store=self.store, section=None, title="بنر سراسری", desktop_image=_img("bw.png"), is_active=True)
        HeroSlide.objects.create(
            store=self.store, section=self.hero_section, title="پیش‌نویس‌اسلاید", is_active=True,
            desktop_asset=MediaAsset.objects.create(store=self.store, image="x/d1.png"))
        PromotionalBanner.objects.create(
            store=self.store, section=self.banner_section, title="پیش‌نویس‌بنر", is_active=True,
            desktop_asset=MediaAsset.objects.create(store=self.store, image="x/d2.png"))

    def get_home(self):
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=self.HOST)
        self.assertEqual(resp.status_code, 200)
        return resp

    def test_draft_scoped_media_is_not_rendered_on_the_legacy_homepage(self):
        resp = self.get_home()
        self.assertIn("hero_slides", resp.context, "expected the legacy (non-visual-shell) homepage")
        self.assertEqual([s.pk for s in resp.context["hero_slides"]], [self.wide_slide.pk])
        self.assertEqual([b.pk for b in resp.context["promo_banners"]], [self.wide_banner.pk])
        html = resp.content.decode()
        self.assertNotIn("پیش‌نویس‌اسلاید", html)
        self.assertNotIn("پیش‌نویس‌بنر", html)

    def test_store_wide_media_still_renders_on_the_legacy_homepage(self):
        self.assertContains(self.get_home(), "سراسری")
