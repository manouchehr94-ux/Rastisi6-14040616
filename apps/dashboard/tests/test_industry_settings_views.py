from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import IndustryTemplate, IndustryTemplateCategory, StoreIndustryInstallation
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = f"isv-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class IndustrySettingsTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.template = IndustryTemplate.objects.create(
            slug="isv-clothing", name="پوشاک", version=1,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        IndustryTemplateCategory.objects.create(
            industry_template=self.template, code="clothing", name="پوشاک",
        )
        self.staff = User.objects.create_user(username="09121188001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121188001", password="pass12345")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class IndustrySettingsZeroTemplatesTests(TestCase):
    """سناریوی دقیقِ گزارشِ باگ: هیچ ``IndustryTemplate``ای در سامانه نیست —
    صفحه‌ی تنظیماتِ صنف باید یک پیامِ تشخیصیِ روشن نشان دهد، نه اینکه وانمود
    کند راه‌اندازی تمام شده است."""

    def setUp(self):
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="09121188009", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="09121188009", password="pass12345")

    def test_zero_templates_shows_diagnostic_not_success(self):
        self.assertEqual(IndustryTemplate.objects.count(), 0)
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هیچ الگوی صنفِ فعالی در سامانه ثبت نشده است")
        self.assertContains(response, "seed_industry_templates")
        self.assertNotContains(response, "نصب‌شده")


class IndustrySettingsPageTests(IndustrySettingsTestCase):
    def test_renders_available_templates(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پوشاک")

    def test_inactive_template_not_listed(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertNotContains(response, "پوشاک")
        self.assertContains(response, "هیچ الگوی صنفِ فعالی در سامانه ثبت نشده است")
        self.assertContains(response, "seed_industry_templates")

    def test_only_latest_version_shown(self):
        v2 = IndustryTemplate.objects.create(
            slug="isv-clothing", name="پوشاک نسخه‌ی دو", version=2,
            readiness=IndustryTemplate.Readiness.PRODUCTION_READY,
        )
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertContains(response, "پوشاک نسخه‌ی دو")
        # only the newer version's card/install action is rendered once —
        # asserted against the install form's action URL (which is unique
        # per template pk) rather than the button's wording, since the
        # button label itself ("نصب") is UI copy, not the actual contract
        # under test.
        install_url = reverse("dashboard:settings-industry-install", args=[v2.pk])
        self.assertContains(response, f'action="{install_url}"', count=1)
        # and the older version's own install action must not also appear.
        old_install_url = reverse("dashboard:settings-industry-install", args=[self.template.pk])
        self.assertNotContains(response, f'action="{old_install_url}"')


class IndustryInstallViewTests(IndustrySettingsTestCase):
    def test_install_creates_categories(self):
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_second_install_shows_error_not_crash(self):
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StoreIndustryInstallation.objects.filter(store=self.store).count(), 1)

    def test_installed_state_shown_after_install(self):
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        response = self.client.get(reverse("dashboard:settings") + "?section=industry")
        self.assertContains(response, "وضعیت نصب")
        self.assertContains(response, "نصب‌شده")
        self.assertContains(response, "تاریخ نصب")

    def test_other_store_unaffected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="isv-other", status=Store.Status.ACTIVE)
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertFalse(StoreIndustryInstallation.objects.filter(store=other_store).exists())


class IndustrySettingsPermissionTests(IndustrySettingsTestCase):
    def test_catalog_manager_cannot_install(self):
        user = User.objects.create_user(username="09121188002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.CATALOG_MANAGER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username=user.username, password="pass12345")
        response = self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_install(self):
        response = self.client.post(
            reverse("dashboard:settings-industry-install", args=[self.template.pk]), follow=True,
        )
        self.assertTrue(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

class IndustrySettingsCustomNameTests(IndustrySettingsTestCase):
    """«سایر (صنف آزاد)» in the merchant-admin settings path: the real industry name is required and validated server-side (FV2)."""

    def setUp(self):
        super().setUp()
        from apps.portal.tests._industry import ensure_other_template

        self.other = ensure_other_template()
        self.url = reverse("dashboard:settings-industry-install", args=[self.other.pk])

    def test_the_other_card_renders_a_required_name_input_and_ordinary_cards_do_not(self):
        html = self.client.get(reverse("dashboard:settings") + "?section=industry").content.decode()
        self.assertEqual(html.count('name="custom_industry_name"'), 1)
        self.assertIn("data-testid=\"custom-industry-name\"", html)

    def test_other_without_a_valid_name_is_refused_and_installs_nothing(self):
        for bad in ("", "  ", "ا", "<b>x</b>", "ا" * 81):
            with self.subTest(name=bad):
                response = self.client.post(self.url, {"custom_industry_name": bad})
                self.assertEqual(response.status_code, 302)
                self.assertFalse(StoreIndustryInstallation.objects.filter(store=self.store).exists())

    def test_other_with_a_name_installs_and_the_settings_page_shows_it(self):
        self.client.post(self.url, {"custom_industry_name": "  گالری   سفال "})
        installation = StoreIndustryInstallation.objects.get(store=self.store)
        self.assertEqual(installation.custom_industry_name, "گالری سفال")
        html = self.client.get(reverse("dashboard:settings") + "?section=industry").content.decode()
        self.assertIn("گالری سفال", html)

    def test_an_ordinary_template_ignores_the_name(self):
        self.client.post(reverse("dashboard:settings-industry-install", args=[self.template.pk]), {"custom_industry_name": "جعلی"})
        self.assertEqual(StoreIndustryInstallation.objects.get(store=self.store).custom_industry_name, "")
