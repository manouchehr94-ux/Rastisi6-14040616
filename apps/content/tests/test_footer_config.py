"""تست‌های جامع قابلیت «تنظیمات فوتر» — مدل، داشبورد، و رندر فروشگاه."""

from io import BytesIO

from PIL import Image

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.content.models import (
    FooterPaymentLogo,
    FooterSettings,
    FooterSettingsNotProvisionedError,
    FooterTrustBadge,
)
from apps.stores.models import Store, StoreMembership
from apps.stores.resolution import CompatibilityFallbackUnavailableError

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _grant_membership(store, user):
    from django.utils import timezone

    StoreMembership.objects.create(
        store=store, user=user, role=StoreMembership.Role.OWNER,
        status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
    )


def _make_image(name="test.png", size=(10, 10), fmt="PNG"):
    """ساخت تصویر ساختگی برای تست."""
    buf = BytesIO()
    Image.new("RGB", size).save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


# ---------------------------------------------------------------- FooterSettings Model


class FooterSettingsExplicitStoreTests(TestCase):
    def test_load_with_explicit_store_returns_that_stores_row(self):
        akhlaghi = _akhlaghi()
        fs = FooterSettings.load(store=akhlaghi)
        self.assertEqual(fs.store_id, akhlaghi.pk)

    def test_load_with_explicit_store_missing_row_raises_domain_error(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        with self.assertRaises(FooterSettingsNotProvisionedError):
            FooterSettings.load(store=store_b)

    def test_load_with_explicit_store_never_returns_another_stores_row(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        FooterSettings.provision_for(store_b)

        akhlaghi = _akhlaghi()
        fs_a = FooterSettings.load(store=akhlaghi)
        fs_b = FooterSettings.load(store=store_b)
        self.assertNotEqual(fs_a.pk, fs_b.pk)


class FooterSettingsCompatibilityModeTests(TestCase):
    def test_load_with_no_store_returns_akhlaghi_when_sole_active_store(self):
        akhlaghi = _akhlaghi()
        fs = FooterSettings.load()
        self.assertEqual(fs.store_id, akhlaghi.pk)

    def test_bootstrapped_via_the_data_migration(self):
        # The Akhlaghi row was created by the backfill migration, not
        # lazily by load() — every field keeps its model-level default.
        fs = FooterSettings.load()
        self.assertTrue(fs.is_enabled)
        self.assertTrue(fs.show_branding)
        self.assertTrue(fs.show_logo)
        self.assertTrue(fs.show_contact)
        self.assertTrue(fs.show_navigation)
        self.assertTrue(fs.show_social_links)
        self.assertFalse(fs.show_newsletter)
        self.assertFalse(fs.show_trust_badges)
        self.assertFalse(fs.show_payment_logos)
        self.assertEqual(fs.description, "")
        self.assertEqual(fs.copyright_text, "")

    def test_repeated_load_returns_same_row(self):
        fs1 = FooterSettings.load()
        fs2 = FooterSettings.load()
        self.assertEqual(fs1.pk, fs2.pk)

    def test_compatibility_mode_fails_closed_when_second_store_exists(self):
        Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        with self.assertRaises(CompatibilityFallbackUnavailableError):
            FooterSettings.load()

    def test_str(self):
        fs = FooterSettings.load()
        self.assertEqual(str(fs), "تنظیمات فوتر")


class FooterSettingsProvisionForTests(TestCase):
    def test_provision_for_creates_a_row_for_a_new_store(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        fs = FooterSettings.provision_for(store_b)
        self.assertEqual(fs.store_id, store_b.pk)

    def test_provision_for_is_idempotent(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        first = FooterSettings.provision_for(store_b)
        second = FooterSettings.provision_for(store_b)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(FooterSettings.objects.filter(store=store_b).count(), 1)

    def test_provision_for_never_overwrites_existing_values(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        fs = FooterSettings.provision_for(store_b)
        fs.copyright_text = "متن سفارشی"
        fs.save()

        reprovisioned = FooterSettings.provision_for(store_b)
        self.assertEqual(reprovisioned.copyright_text, "متن سفارشی")


class FooterSettingsOneToOneConstraintTests(TestCase):
    def test_duplicate_footersettings_for_same_store_rejected(self):
        akhlaghi = _akhlaghi()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FooterSettings.objects.create(store=akhlaghi)

    def test_second_store_may_have_its_own_row(self):
        store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        FooterSettings.objects.create(store=store_b)
        self.assertEqual(FooterSettings.objects.count(), 2)


# ---------------------------------------------------------------- FooterTrustBadge Model


class FooterTrustBadgeTests(TestCase):
    """تست‌های مدل FooterTrustBadge."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_creation(self):
        badge = FooterTrustBadge.objects.create(
            store=self.store,
            title="اینماد",
            image=_make_image("enamad.png"),
            destination_url="https://enamad.ir",
            display_order=1,
        )
        self.assertEqual(badge.title, "اینماد")
        self.assertTrue(badge.is_active)
        self.assertEqual(str(badge), "اینماد")

    def test_title_required(self):
        badge = FooterTrustBadge(store=self.store, title="", image=_make_image())
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_image_required(self):
        badge = FooterTrustBadge(store=self.store, title="test")
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_dangerous_url_rejected(self):
        badge = FooterTrustBadge(
            store=self.store, title="XSS", image=_make_image(),
            destination_url="javascript:alert(1)",
        )
        with self.assertRaises(ValidationError) as cm:
            badge.full_clean()
        self.assertIn("destination_url", cm.exception.message_dict)

    def test_protocol_relative_url_rejected(self):
        badge = FooterTrustBadge(
            store=self.store, title="Protocol", image=_make_image(),
            destination_url="//evil.com/phish",
        )
        with self.assertRaises(ValidationError) as cm:
            badge.full_clean()
        self.assertIn("destination_url", cm.exception.message_dict)

    def test_blank_url_allowed(self):
        badge = FooterTrustBadge(store=self.store, title="NoLink", image=_make_image(), destination_url="")
        badge.full_clean()  # should not raise

    def test_ordering(self):
        FooterTrustBadge.objects.create(store=self.store, title="B", image=_make_image("b.png"), display_order=2)
        FooterTrustBadge.objects.create(store=self.store, title="A", image=_make_image("a.png"), display_order=1)
        badges = list(FooterTrustBadge.objects.filter(store=self.store).values_list("title", flat=True))
        self.assertEqual(badges, ["A", "B"])

    def test_store_is_required(self):
        badge = FooterTrustBadge(title="NoStore", image=_make_image())
        with self.assertRaises(ValidationError):
            badge.full_clean()


# ---------------------------------------------------------------- FooterPaymentLogo Model


class FooterPaymentLogoTests(TestCase):
    """تست‌های مدل FooterPaymentLogo."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_creation(self):
        logo = FooterPaymentLogo.objects.create(
            store=self.store, title="زرین‌پال", image=_make_image("zp.png"), display_order=0,
        )
        self.assertEqual(logo.title, "زرین‌پال")
        self.assertTrue(logo.is_active)
        self.assertEqual(str(logo), "زرین‌پال")

    def test_title_required(self):
        logo = FooterPaymentLogo(store=self.store, title="", image=_make_image())
        with self.assertRaises(ValidationError):
            logo.full_clean()

    def test_image_required(self):
        logo = FooterPaymentLogo(store=self.store, title="test")
        with self.assertRaises(ValidationError):
            logo.full_clean()

    def test_ordering(self):
        FooterPaymentLogo.objects.create(store=self.store, title="Second", image=_make_image("s.png"), display_order=5)
        FooterPaymentLogo.objects.create(store=self.store, title="First", image=_make_image("f.png"), display_order=1)
        logos = list(FooterPaymentLogo.objects.filter(store=self.store).values_list("title", flat=True))
        self.assertEqual(logos, ["First", "Second"])


# ---------------------------------------------------------------- Dashboard Access


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class DashboardAccessTests(TestCase):
    """تست‌های دسترسی داشبورد فوتر."""

    def setUp(self):
        self.staff = User.objects.create_user(username="admin", password="pass123", is_staff=True)
        _grant_membership(_akhlaghi(), self.staff)
        self.user = User.objects.create_user(username="normal", password="pass123", is_staff=False)

    def test_anonymous_redirect(self):
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_non_staff_rejected(self):
        self.client.login(username="normal", password="pass123")
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_staff_allowed(self):
        self.client.login(username="admin", password="pass123")
        url = reverse("dashboard:footer-settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------- Dashboard CRUD


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class DashboardFooterCRUDTests(TestCase):
    """تست‌های CRUD داشبورد فوتر."""

    def setUp(self):
        self.store = _akhlaghi()
        self.staff = User.objects.create_user(username="admin", password="pass123", is_staff=True)
        _grant_membership(self.store, self.staff)
        self.client.login(username="admin", password="pass123")

    def test_settings_save(self):
        url = reverse("dashboard:footer-settings")
        resp = self.client.post(url, {
            "is_enabled": "on",
            "show_branding": "on",
            "show_contact": "on",
            "show_navigation": "on",
            "show_social_links": "on",
            "copyright_text": "My Copyright",
            "phone": "021-12345",
            "address": "Tehran",
        })
        self.assertEqual(resp.status_code, 302)
        fs = FooterSettings.load(store=self.store)
        self.assertEqual(fs.copyright_text, "My Copyright")
        self.assertEqual(fs.phone, "021-12345")
        self.assertEqual(fs.address, "Tehran")

    def test_badge_create(self):
        url = reverse("dashboard:footer-trust-badge-add")
        resp = self.client.post(url, {
            "title": "TestBadge",
            "image": _make_image("badge.png"),
            "display_order": "1",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterTrustBadge.objects.filter(store=self.store).count(), 1)
        created = FooterTrustBadge.objects.get(store=self.store)
        self.assertEqual(created.title, "TestBadge")
        self.assertEqual(created.store_id, self.store.pk)

    def test_badge_edit(self):
        badge = FooterTrustBadge.objects.create(store=self.store, title="Old", image=_make_image("old.png"))
        url = reverse("dashboard:footer-trust-badge-edit", args=[badge.pk])
        resp = self.client.post(url, {
            "title": "New",
            "display_order": "2",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        badge.refresh_from_db()
        self.assertEqual(badge.title, "New")

    def test_badge_delete(self):
        badge = FooterTrustBadge.objects.create(store=self.store, title="Del", image=_make_image("del.png"))
        url = reverse("dashboard:footer-trust-badge-delete", args=[badge.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterTrustBadge.objects.count(), 0)

    def test_badge_toggle(self):
        badge = FooterTrustBadge.objects.create(store=self.store, title="Toggle", image=_make_image("t.png"), is_active=True)
        url = reverse("dashboard:footer-trust-badge-toggle", args=[badge.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        badge.refresh_from_db()
        self.assertFalse(badge.is_active)

    def test_logo_create(self):
        url = reverse("dashboard:footer-payment-logo-add")
        resp = self.client.post(url, {
            "title": "ZarinPal",
            "image": _make_image("zp.png"),
            "display_order": "0",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterPaymentLogo.objects.filter(store=self.store).count(), 1)

    def test_logo_edit(self):
        logo = FooterPaymentLogo.objects.create(store=self.store, title="Old", image=_make_image("old.png"))
        url = reverse("dashboard:footer-payment-logo-edit", args=[logo.pk])
        resp = self.client.post(url, {
            "title": "Updated",
            "display_order": "3",
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        logo.refresh_from_db()
        self.assertEqual(logo.title, "Updated")

    def test_logo_delete(self):
        logo = FooterPaymentLogo.objects.create(store=self.store, title="Del", image=_make_image("del.png"))
        url = reverse("dashboard:footer-payment-logo-delete", args=[logo.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(FooterPaymentLogo.objects.count(), 0)

    def test_logo_toggle(self):
        logo = FooterPaymentLogo.objects.create(store=self.store, title="Toggle", image=_make_image("t.png"), is_active=True)
        url = reverse("dashboard:footer-payment-logo-toggle", args=[logo.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        logo.refresh_from_db()
        self.assertFalse(logo.is_active)


# ---------------------------------------------------------------- Dashboard Write Isolation (adversarial)


@override_settings(
    MEDIA_ROOT="/tmp/test_media_footer",
    ALLOWED_HOSTS=[f"store-a.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"],
)
class DashboardFooterCrossStoreIsolationTests(TestCase):
    """A Store A dashboard request must never mutate Store B's footer rows.

    Once a second Store exists, the compatibility fallback correctly fails
    closed (see apps.stores.resolution) — so "a Store A request" here means
    a request through a verified StoreDomain for Store A, exactly as it
    would work in production, not an unresolved/compat-mode request.

    ``HOST_A`` must be a real, resolvable Merchant Admin host — i.e.
    ``<admin_subdomain>.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}`` — not a
    hard-coded production suffix, since the local/test suffix
    (``rastisi.localhost`` in DEBUG) differs from the production one
    (``rastisi.ir``). A hard-coded ``.rastisi.ir`` host here would never
    match ``store_a.admin_subdomain`` under the locally configured suffix,
    causing every Dashboard request in this class to fall through to the
    public storefront resolver instead of the admin-portal one.
    """

    HOST_A = f"store-a.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"

    def setUp(self):
        from django.utils import timezone

        from apps.stores.models import StoreDomain

        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(
            store=self.store_a, hostname=self.HOST_A, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        self.store_a.admin_subdomain = self.HOST_A.split(".")[0]
        self.store_a.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="admin", password="pass123", is_staff=True)
        _grant_membership(self.store_a, self.staff)
        self.client.login(username="admin", password="pass123")

    def _post(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_HOST=self.HOST_A)

    def _get(self, url):
        return self.client.get(url, HTTP_HOST=self.HOST_A)

    def test_store_a_request_cannot_edit_store_b_badge(self):
        badge_b = FooterTrustBadge.objects.create(store=self.store_b, title="B-Badge", image=_make_image("b.png"))
        url = reverse("dashboard:footer-trust-badge-edit", args=[badge_b.pk])
        resp = self._post(url, {"title": "Hijacked", "display_order": "0", "is_active": "on"})
        self.assertEqual(resp.status_code, 404)
        badge_b.refresh_from_db()
        self.assertEqual(badge_b.title, "B-Badge")

    def test_store_a_request_cannot_delete_store_b_badge(self):
        badge_b = FooterTrustBadge.objects.create(store=self.store_b, title="B-Badge", image=_make_image("b.png"))
        url = reverse("dashboard:footer-trust-badge-delete", args=[badge_b.pk])
        resp = self._post(url)
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(FooterTrustBadge.objects.filter(pk=badge_b.pk).exists())

    def test_store_a_request_cannot_toggle_store_b_badge(self):
        badge_b = FooterTrustBadge.objects.create(
            store=self.store_b, title="B-Badge", image=_make_image("b.png"), is_active=True
        )
        url = reverse("dashboard:footer-trust-badge-toggle", args=[badge_b.pk])
        resp = self._post(url)
        self.assertEqual(resp.status_code, 404)
        badge_b.refresh_from_db()
        self.assertTrue(badge_b.is_active)

    def test_store_a_request_cannot_edit_store_b_payment_logo(self):
        logo_b = FooterPaymentLogo.objects.create(store=self.store_b, title="B-Logo", image=_make_image("b.png"))
        url = reverse("dashboard:footer-payment-logo-edit", args=[logo_b.pk])
        resp = self._post(url, {"title": "Hijacked", "display_order": "0", "is_active": "on"})
        self.assertEqual(resp.status_code, 404)
        logo_b.refresh_from_db()
        self.assertEqual(logo_b.title, "B-Logo")

    def test_store_a_request_cannot_delete_store_b_payment_logo(self):
        logo_b = FooterPaymentLogo.objects.create(store=self.store_b, title="B-Logo", image=_make_image("b.png"))
        url = reverse("dashboard:footer-payment-logo-delete", args=[logo_b.pk])
        resp = self._post(url)
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(FooterPaymentLogo.objects.filter(pk=logo_b.pk).exists())

    def test_store_a_request_cannot_toggle_store_b_payment_logo(self):
        logo_b = FooterPaymentLogo.objects.create(
            store=self.store_b, title="B-Logo", image=_make_image("b.png"), is_active=True
        )
        url = reverse("dashboard:footer-payment-logo-toggle", args=[logo_b.pk])
        resp = self._post(url)
        self.assertEqual(resp.status_code, 404)
        logo_b.refresh_from_db()
        self.assertTrue(logo_b.is_active)

    def test_badge_list_shows_only_current_store_rows(self):
        FooterTrustBadge.objects.create(store=self.store_a, title="A-Badge", image=_make_image("a.png"))
        FooterTrustBadge.objects.create(store=self.store_b, title="B-Badge", image=_make_image("b.png"))
        url = reverse("dashboard:footer-trust-badge-list")
        resp = self._get(url)
        titles = {b.title for b in resp.context["badges"]}
        self.assertEqual(titles, {"A-Badge"})

    def test_payment_logo_list_shows_only_current_store_rows(self):
        FooterPaymentLogo.objects.create(store=self.store_a, title="A-Logo", image=_make_image("a.png"))
        FooterPaymentLogo.objects.create(store=self.store_b, title="B-Logo", image=_make_image("b.png"))
        url = reverse("dashboard:footer-payment-logo-list")
        resp = self._get(url)
        titles = {l.title for l in resp.context["logos"]}
        self.assertEqual(titles, {"A-Logo"})

    def test_identical_titles_allowed_across_stores(self):
        FooterTrustBadge.objects.create(store=self.store_a, title="Same Title", image=_make_image("a.png"))
        FooterTrustBadge.objects.create(store=self.store_b, title="Same Title", image=_make_image("b.png"))
        self.assertEqual(FooterTrustBadge.objects.filter(title="Same Title").count(), 2)

    def test_identical_display_order_allowed_across_stores(self):
        FooterTrustBadge.objects.create(store=self.store_a, title="A", image=_make_image("a.png"), display_order=1)
        FooterTrustBadge.objects.create(store=self.store_b, title="B", image=_make_image("b.png"), display_order=1)
        self.assertEqual(FooterTrustBadge.objects.filter(display_order=1).count(), 2)


# ---------------------------------------------------------------- Storefront Rendering


@override_settings(MEDIA_ROOT="/tmp/test_media_footer")
class StorefrontFooterRenderTests(TestCase):
    """تست‌های رندر فوتر در فروشگاه."""

    def setUp(self):
        self.store = _akhlaghi()
        self.fs = FooterSettings.load(store=self.store)

    def _get_home(self):
        return self.client.get("/")

    def test_footer_enabled(self):
        self.fs.is_enabled = True
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "<footer")

    def test_footer_disabled(self):
        self.fs.is_enabled = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        # Footer tag exists but content is empty (guarded by is_enabled)
        self.assertNotIn("copy", content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else "")

    def test_branding_toggle_off(self):
        self.fs.show_branding = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        # The "about" class div shouldn't be in the footer
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="about"', footer_html)

    def test_contact_toggle_off(self):
        self.fs.show_contact = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("تماس با ما", footer_html)

    def test_contact_with_phone(self):
        self.fs.show_contact = True
        self.fs.phone = "021-9999"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "tel:021-9999")

    def test_contact_with_email(self):
        self.fs.show_contact = True
        self.fs.email = "info@test.ir"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "mailto:info@test.ir")

    def test_navigation_toggle_off(self):
        self.fs.show_navigation = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("NAV_FOOTER", footer_html)

    def test_social_toggle_off(self):
        self.fs.show_social_links = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="socials"', footer_html)

    def test_newsletter_toggle_on(self):
        self.fs.show_newsletter = True
        self.fs.newsletter_title = "خبرنامه تست"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "خبرنامه تست")
        self.assertContains(resp, "به‌زودی")

    def test_newsletter_toggle_off(self):
        self.fs.show_newsletter = False
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('class="news"', footer_html)

    def test_trust_badges_render(self):
        self.fs.show_trust_badges = True
        self.fs.save()
        FooterTrustBadge.objects.create(
            store=self.store, title="Enamad", image=_make_image("enamad.png"),
            destination_url="https://enamad.ir", is_active=True,
        )
        resp = self._get_home()
        self.assertContains(resp, "trust-badges")
        self.assertContains(resp, "https://enamad.ir")

    def test_payment_logos_render(self):
        self.fs.show_payment_logos = True
        self.fs.save()
        FooterPaymentLogo.objects.create(
            store=self.store, title="ZarinPal", image=_make_image("zp.png"), is_active=True,
        )
        resp = self._get_home()
        self.assertContains(resp, "payment-logos")

    def test_empty_trust_badges_not_shown(self):
        self.fs.show_trust_badges = True
        self.fs.save()
        # No badges exist
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("trust-badges", footer_html)

    def test_empty_payment_logos_not_shown(self):
        self.fs.show_payment_logos = True
        self.fs.save()
        # No logos exist
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn("payment-logos", footer_html)

    def test_no_href_hash_in_footer(self):
        """فوتر نباید لینک‌های بی‌مقصد (href="#") داشته باشد."""
        self.fs.show_contact = True
        self.fs.phone = "021-1234"
        self.fs.email = "a@b.com"
        self.fs.address = "Test Address"
        self.fs.save()
        resp = self._get_home()
        content = resp.content.decode()
        footer_html = content.split("<footer")[1].split("</footer>")[0] if "<footer" in content else ""
        self.assertNotIn('href="#"', footer_html)

    def test_copyright_custom_text(self):
        self.fs.copyright_text = "Custom (c) 2025"
        self.fs.save()
        resp = self._get_home()
        self.assertContains(resp, "Custom (c) 2025")

    def test_copyright_default_uses_shop_name(self):
        self.fs.copyright_text = ""
        self.fs.save()
        resp = self._get_home()
        # Default uses SHOP_NAME from settings
        self.assertContains(resp, "دیجی‌مارکت")


# ---------------------------------------------------------------- Storefront Isolation (adversarial)


class StorefrontFooterHostIsolationTests(TestCase):
    """Real resolver + middleware + context-processor coverage: Host A must
    render Store A's footer, Host B must render Store B's, and neither
    leaks into the other. No request.store mocking — full request/response
    cycle via the Django test client with distinct Host headers."""

    def setUp(self):
        from django.utils import timezone

        from apps.stores.models import StoreDomain

        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(
            store=self.store_a, hostname="store-a.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=self.store_b, hostname="store-b.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )

        from apps.core.models import ShopSettings

        # ShopSettings is also loaded by the (unmodified) core context
        # processor on every page render — Store B needs one provisioned
        # too, or rendering "/" for Store B would raise
        # ShopSettingsNotProvisionedError.
        ShopSettings.provision_for(self.store_b)

        self.fs_a = FooterSettings.load(store=self.store_a)
        self.fs_a.copyright_text = "Copyright A"
        self.fs_a.save()

        self.fs_b = FooterSettings.provision_for(self.store_b)
        self.fs_b.copyright_text = "Copyright B"
        self.fs_b.save()

    @override_settings(ALLOWED_HOSTS=["store-a.example.com", "store-b.example.com"])
    def test_host_a_renders_store_a_footer(self):
        resp = self.client.get("/", HTTP_HOST="store-a.example.com")
        self.assertContains(resp, "Copyright A")
        self.assertNotContains(resp, "Copyright B")

    @override_settings(ALLOWED_HOSTS=["store-a.example.com", "store-b.example.com"])
    def test_host_b_renders_store_b_footer(self):
        resp = self.client.get("/", HTTP_HOST="store-b.example.com")
        self.assertContains(resp, "Copyright B")
        self.assertNotContains(resp, "Copyright A")

    @override_settings(ALLOWED_HOSTS=["store-a.example.com", "store-b.example.com", "unknown.example.com"])
    def test_unknown_host_does_not_receive_either_stores_footer(self):
        from django.test import Client

        # Unresolved Store + 2 Stores existing → fail closed (no context
        # processor can silently pick one), so neither tenant's copyright
        # text is ever exposed to a request that couldn't be resolved to
        # anyone. As of Checkpoint 6 (ADR-83), the storefront turns an
        # unresolved Host into a clean 404 via resolve_store_for_storefront —
        # previously this raised a 500. Either way, no footer leaks; a 404 is
        # the correct, safer customer-facing result. Client(
        # raise_request_exception=False) is kept so any unexpected view-level
        # exception is surfaced as a response rather than re-raised.
        client = Client(raise_request_exception=False)
        resp = client.get("/", HTTP_HOST="unknown.example.com")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"Copyright A", resp.content)
        self.assertNotIn(b"Copyright B", resp.content)


# ---------------------------------------------------------------- Query Count Tests


class FooterQueryCountTests(TestCase):
    """تست شمارش query فوتر — با یک Store از پیش resolve‌شده (نه compatibility
    mode)، دقیقاً مطابق رفتار واقعی middleware برای یک درخواست معمولی."""

    def setUp(self):
        self.store = _akhlaghi()

    class _FakeRequest:
        def __init__(self, store):
            self.store = store

    def test_all_disabled_single_query(self):
        """All media sections disabled → only settings query."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.content.context_processors import footer_settings

        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = False
        fs.show_payment_logos = False
        fs.save()

        with CaptureQueriesContext(connection) as ctx:
            result = footer_settings(self._FakeRequest(self.store))
            # Force evaluation of lazy querysets
            list(result["FOOTER_TRUST_BADGES"])
            list(result["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(len(ctx), 1)  # Only settings load

    def test_badges_enabled_two_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.content.context_processors import footer_settings

        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = True
        fs.show_payment_logos = False
        fs.save()

        with CaptureQueriesContext(connection) as ctx:
            result = footer_settings(self._FakeRequest(self.store))
            list(result["FOOTER_TRUST_BADGES"])
            list(result["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(len(ctx), 2)

    def test_logos_enabled_two_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.content.context_processors import footer_settings

        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = False
        fs.show_payment_logos = True
        fs.save()

        with CaptureQueriesContext(connection) as ctx:
            result = footer_settings(self._FakeRequest(self.store))
            list(result["FOOTER_TRUST_BADGES"])
            list(result["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(len(ctx), 2)

    def test_both_enabled_three_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.content.context_processors import footer_settings

        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = True
        fs.show_payment_logos = True
        fs.save()

        with CaptureQueriesContext(connection) as ctx:
            result = footer_settings(self._FakeRequest(self.store))
            list(result["FOOTER_TRUST_BADGES"])
            list(result["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(len(ctx), 3)

    def test_badge_count_does_not_increase_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.content.context_processors import footer_settings

        fs = FooterSettings.load(store=self.store)
        fs.show_trust_badges = True
        fs.show_payment_logos = False
        fs.save()

        # Create 10 badges
        for i in range(10):
            FooterTrustBadge.objects.create(store=self.store, title=f"B{i}", image=_make_image(f"b{i}.png"), is_active=True)

        with CaptureQueriesContext(connection) as ctx:
            result = footer_settings(self._FakeRequest(self.store))
            list(result["FOOTER_TRUST_BADGES"])
            list(result["FOOTER_PAYMENT_LOGOS"])
        self.assertEqual(len(ctx), 2)  # Still just 2

    def test_compatibility_mode_costs_one_extra_query_when_store_unresolved(self):
        """Documents the real, accepted query-count cost of compatibility
        mode: resolving "no explicit Store" still requires one bounded
        query (apps.stores.resolution.resolve_compatibility_store) before
        the settings row itself can be fetched — 2 queries total instead of
        1, for the settings load alone."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        class _UnresolvedRequest:
            store = None

        with CaptureQueriesContext(connection) as ctx:
            FooterSettings.load(store=_UnresolvedRequest.store)
        self.assertEqual(len(ctx), 2)


# ---------------------------------------------------------------- Phone Validation Tests


class PhoneValidationTests(TestCase):
    """تست‌های اعتبارسنجی شماره تلفن."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_valid_iranian_number(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "021-91008877"
        fs.full_clean()

    def test_valid_international(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "+98 21 9100 8877"
        fs.full_clean()

    def test_spaces_and_parens(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "(021) 9100-8877"
        fs.full_clean()

    def test_whitespace_trimmed(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "  021-91008877  "
        fs.save()
        fs.refresh_from_db()
        self.assertEqual(fs.phone, "021-91008877")

    def test_alphabetic_rejected(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "call me maybe"
        with self.assertRaises(ValidationError):
            fs.full_clean()

    def test_html_rejected(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = '<script>alert(1)</script>'
        with self.assertRaises(ValidationError):
            fs.full_clean()

    def test_control_chars_rejected(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = "021\x00-9100"
        with self.assertRaises(ValidationError):
            fs.full_clean()

    def test_empty_allowed(self):
        fs = FooterSettings.load(store=self.store)
        fs.phone = ""
        fs.full_clean()  # Should not raise


# ---------------------------------------------------------------- Copyright Behavior Tests


class CopyrightBehaviorTests(TestCase):
    """تست‌های رفتار کپی‌رایت."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_configured_text_renders(self):
        fs = FooterSettings.load(store=self.store)
        fs.copyright_text = "تمامی حقوق محفوظ"
        fs.save()
        response = self.client.get("/")
        self.assertContains(response, "تمامی حقوق محفوظ")

    def test_empty_text_omits_section(self):
        fs = FooterSettings.load(store=self.store)
        fs.copyright_text = ""
        fs.save()
        response = self.client.get("/")
        # Should NOT have the old hardcoded copyright
        self.assertNotContains(response, "تمامی حقوق برای")

    def test_no_auto_generated_fallback(self):
        fs = FooterSettings.load(store=self.store)
        fs.copyright_text = ""
        fs.save()
        response = self.client.get("/")
        self.assertNotContains(response, "© ۱۴۰۵")

    def test_text_is_escaped(self):
        fs = FooterSettings.load(store=self.store)
        fs.copyright_text = '<img src=x onerror=alert(1)>'
        fs.save()
        response = self.client.get("/")
        self.assertNotContains(response, '<img src=x')
        self.assertContains(response, "&lt;img")


# ================================================================ IMAGE CONTENT SECURITY TESTS


class ImageContentSecurityTests(TestCase):
    """تست‌های امنیت محتوای تصویر — Pillow verification."""

    def setUp(self):
        self.store = _akhlaghi()

    def _valid_png(self, name="valid.png"):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, "PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def _valid_jpeg(self, name="valid.jpg"):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10), (0, 255, 0)).save(buf, "JPEG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")

    def _valid_webp(self, name="valid.webp"):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10), (0, 0, 255)).save(buf, "WEBP")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/webp")

    def test_valid_png_accepted(self):
        badge = FooterTrustBadge(store=self.store, title="PNG", image=self._valid_png())
        badge.full_clean()  # Should not raise

    def test_valid_jpeg_accepted(self):
        badge = FooterTrustBadge(store=self.store, title="JPEG", image=self._valid_jpeg())
        badge.full_clean()

    def test_valid_webp_accepted(self):
        badge = FooterTrustBadge(store=self.store, title="WebP", image=self._valid_webp())
        badge.full_clean()

    def test_plain_text_named_png_rejected(self):
        fake = SimpleUploadedFile("fake.png", b"This is plain text not an image", content_type="image/png")
        badge = FooterTrustBadge(store=self.store, title="Fake", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_html_named_jpg_rejected(self):
        html = b"<html><body><script>alert(1)</script></body></html>"
        fake = SimpleUploadedFile("badge.jpg", html, content_type="image/jpeg")
        badge = FooterTrustBadge(store=self.store, title="HTML", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_javascript_payload_named_png_rejected(self):
        js = b"var x = 1; function hack(){}"
        fake = SimpleUploadedFile("logo.png", js, content_type="image/png")
        logo = FooterPaymentLogo(store=self.store, title="JS", image=fake)
        with self.assertRaises(ValidationError):
            logo.full_clean()

    def test_corrupt_png_header_rejected(self):
        # PNG magic bytes followed by garbage
        corrupt = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        fake = SimpleUploadedFile("corrupt.png", corrupt, content_type="image/png")
        badge = FooterTrustBadge(store=self.store, title="Corrupt", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_truncated_jpeg_rejected(self):
        # JPEG SOI marker then nothing
        truncated = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        fake = SimpleUploadedFile("trunc.jpg", truncated, content_type="image/jpeg")
        badge = FooterTrustBadge(store=self.store, title="Trunc", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_svg_named_svg_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        fake = SimpleUploadedFile("badge.svg", svg, content_type="image/svg+xml")
        badge = FooterTrustBadge(store=self.store, title="SVG", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_svg_renamed_to_png_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        fake = SimpleUploadedFile("sneaky.png", svg, content_type="image/png")
        badge = FooterTrustBadge(store=self.store, title="SVG-PNG", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_oversized_valid_image_rejected(self):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        f = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
        f.size = 6 * 1024 * 1024  # 6 MiB > 5 MiB limit
        badge = FooterTrustBadge(store=self.store, title="Big", image=f)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_gif_rejected(self):
        """GIF is not in ALLOWED_IMAGE_FORMATS."""
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "GIF")
        f = SimpleUploadedFile("anim.gif", buf.getvalue(), content_type="image/gif")
        badge = FooterTrustBadge(store=self.store, title="GIF", image=f)
        with self.assertRaises(ValidationError):
            badge.full_clean()

    def test_invalid_create_produces_no_record(self):
        """Invalid image on create → no database row."""
        fake = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        badge = FooterTrustBadge(store=self.store, title="NoRecord", image=fake)
        with self.assertRaises(ValidationError):
            badge.full_clean()
        # Not saved
        self.assertFalse(FooterTrustBadge.objects.filter(title="NoRecord").exists())

    def test_invalid_replacement_preserves_old_value(self):
        """Invalid replacement image → old image field preserved."""
        badge = FooterTrustBadge.objects.create(
            store=self.store, title="Keep", image=self._valid_png("keep.png"), is_active=True
        )
        original_name = badge.image.name

        # Try to assign invalid image
        fake = SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")
        badge.image = fake
        with self.assertRaises(ValidationError):
            badge.full_clean()

        # Reload from DB - original should remain
        badge.refresh_from_db()
        self.assertEqual(badge.image.name, original_name)


class NewsletterTwoSwitchStatusTests(TestCase):
    """RS-03 — the dashboard states which of the two newsletter switches is the blocker."""

    HOST = "newsletterflag.rastisi.localhost"

    def setUp(self):
        from django.test import Client
        from django.utils import timezone as tz

        from apps.stores.models import StoreMembership

        self.store = Store.objects.get(slug="akhlaghi")
        self.store.admin_subdomain = self.HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        user = User.objects.create_user(username="09123500001", password="pass12345")
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=tz.now(),
        )
        self.client = Client(HTTP_HOST=self.HOST)
        self.client.login(username="09123500001", password="pass12345")

    def _page(self):
        with self.settings(ALLOWED_HOSTS=[self.HOST, "testserver"]):
            return self.client.get(reverse("dashboard:footer-settings")).content.decode()

    def test_off_on_but_studio_off_and_fully_on(self):
        from apps.storefront_builder.services import layout_service

        fs = FooterSettings.load(store=self.store)
        fs.show_newsletter = False
        fs.save()
        self.assertIn("وضعیت فعلی: <b>خاموش</b>", self._page())
        fs.show_newsletter = True
        fs.save()
        layout_service.get_or_create_draft(self.store, user=None)
        layout_service.publish(self.store)
        self.assertIn("خاموش است", self._page())  # studio footer switch off
        version = layout_service.get_or_create_layout(self.store).published_version
        cfg = dict(version.footer_config)
        cfg["show_newsletter"] = True
        version.footer_config = cfg
        version.save(update_fields=["footer_config"])
        self.assertIn("فرم خبرنامه در فوتر نمایش داده می‌شود", self._page())
