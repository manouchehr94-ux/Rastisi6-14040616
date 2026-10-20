"""FOLLOWUP-02 / 03 — one Design Studio with two clearly-named entries, a legacy hero/banner list whose status labels cannot be
read as "live on the site", and a Studio public/back-to-store link that follows the real dev port instead of a hard-coded 8000."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import HeroSlide, PromotionalBanner
from apps.dashboard import navigation
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain, StoreMembership

from .test_rs15_legacy_homepage import HOST, _img

User = get_user_model()


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class _Base(TestCase):
    """Same fixture as the RS-15 tests (a store, its owner, one legacy slide and banner), without re-running them."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.owner = User.objects.create_user(username="09123800002", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09123800002", password="pass12345")
        self.slide = HeroSlide.objects.create(store=self.store, section=None, title="قدیمی", desktop_image=_img(), is_active=True)
        self.banner = PromotionalBanner.objects.create(store=self.store, section=None, title="بنر قدیمی", desktop_image=_img(), is_active=True)

    def publish_studio(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)


class NavigationMapTests(_Base):
    def test_both_entries_lead_to_the_same_studio_route_with_distinct_labels(self):
        store = next(s for s in navigation.SECTIONS if s.key == "store")
        tabs = {t.key: t for t in store.tabs}
        self.assertEqual(tabs["appearance"].url_name, tabs["builder"].url_name)   # ONE engine, never a second route
        self.assertEqual(tabs["appearance"].label, "ظاهر و طراحی")
        self.assertEqual(tabs["builder"].label, "ساختار صفحه‌ها")                   # the Studio's own «ساختار صفحه»
        self.assertEqual(tabs["homepage"].label, "رسانه‌های مشترک فروشگاه")         # the shared-media pool, not a second editor
        self.assertNotIn("قدیمی", tabs["homepage"].label)
        self.assertEqual(len({t.label for t in store.tabs}), len(store.tabs))

    def test_old_vocabulary_is_still_searchable(self):
        store = next(s for s in navigation.SECTIONS if s.key == "store")
        builder = next(t for t in store.tabs if t.key == "builder")
        self.assertIn("سازنده فروشگاه", builder.keywords)


class SharedMediaLabelTests(_Base):
    def test_studio_stores_show_the_shared_media_status_as_live(self):
        self.publish_studio()
        for name in ("hero-list", "banner-list"):
            html = self.client.get(reverse(f"dashboard:{name}")).content.decode()
            self.assertIn('class="badge b-green">فعال<', html)
            self.assertNotIn("در داده قدیمی", html)
            self.assertNotIn("بدون تأثیر در نسخه منتشرشده", html)
            self.assertIn(reverse("dashboard:storefront-builder-r4-editor"), html)
        self.slide.refresh_from_db()
        self.assertTrue(self.slide.is_active)                                      # nothing was changed or deleted

    def test_non_studio_stores_keep_the_live_green_badge(self):
        html = self.client.get(reverse("dashboard:hero-list")).content.decode()
        self.assertIn('class="badge b-green">فعال<', html)
        self.assertNotIn("در داده قدیمی", html)


class StudioPublicUrlPortTests(_Base):
    def setUp(self):
        super().setUp()
        StoreDomain.objects.create(
            store=self.store, hostname="rs15shop.rastisi.localhost", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

    @override_settings(DEBUG=True)
    def test_studio_public_url_uses_the_port_of_the_current_request(self):
        self.client.defaults["HTTP_HOST"] = f"{HOST}:8003"
        with override_settings(ALLOWED_HOSTS=[f"{HOST}", "testserver"]):
            html = self.client.get(reverse("dashboard:storefront-builder-r4-editor")).content.decode()
        self.assertIn('data-rs-public-url="http://rs15shop.rastisi.localhost:8003/"', html)
        self.assertNotIn(":8000", html)
