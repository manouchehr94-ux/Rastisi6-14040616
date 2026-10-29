from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.stores.models import Store, StoreMembership
from apps.stores.services import integration_service

User = get_user_model()


def _grant_akhlaghi_membership(user):
    StoreMembership.objects.create(
        store=Store.objects.get(slug="akhlaghi"), user=user,
        role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        accepted_at=timezone.now(),
    )


class IntegrationSettingsSectionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="09121197001", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121197001", password="pass12345")

    def test_section_lists_all_providers(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=integrations")
        self.assertContains(response, "اینماد")
        self.assertContains(response, "ترب")
        self.assertContains(response, "گوگل آنالیتیکس")

    def test_connect_activates_integration(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]),
            {"enamad_id": "123456", "enamad_auth_code": "abcDEF123"},
        )
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        store = Store.objects.get(slug="akhlaghi")
        rows = integration_service.connections_context(store=store)
        enamad_row = next(row for row in rows if row["provider"].code == "enamad")
        self.assertTrue(enamad_row["is_connected"])

    def test_enamad_meta_field_is_visible_to_merchant_admin(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=integrations")
        self.assertContains(response, "متاتگ احراز فنی اینماد")

    def test_enamad_can_connect_with_verification_meta_before_badge_is_issued(self):
        meta = '<meta name="enamad-verification" content="merchant-token-123">'
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]),
            {"verification_meta_tag": meta, "enamad_code": ""},
        )
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        store = Store.objects.get(slug="akhlaghi")
        row = next(
            row for row in integration_service.connections_context(store=store)
            if row["provider"].code == "enamad"
        )
        self.assertTrue(row["is_connected"])
        self.assertEqual(row["credentials"]["verification_meta_tag"], meta)

    def test_enamad_can_save_badge_identifiers_independently_of_meta(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]),
            {"enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"},
        )
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        store = Store.objects.get(slug="akhlaghi")
        row = next(
            row for row in integration_service.connections_context(store=store)
            if row["provider"].code == "enamad"
        )
        self.assertTrue(row["is_connected"])
        self.assertEqual(row["credentials"]["enamad_id"], "221617")
        self.assertEqual(row["credentials"]["enamad_auth_code"], "94MqMPJEnuahlSHjb9kP")
        self.assertEqual(row["credentials"].get("verification_meta_tag", ""), "")

    def test_enamad_rejects_script_instead_of_storing_raw_html(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]),
            {
                "verification_meta_tag": '<meta name="x" content="y"><script>alert(1)</script>',
                "enamad_code": "",
            },
            follow=True,
        )
        self.assertContains(response, "فقط یک تگ meta ساده")
        store = Store.objects.get(slug="akhlaghi")
        rows = integration_service.connections_context(store=store)
        row = next(row for row in rows if row["provider"].code == "enamad")
        self.assertFalse(row["is_connected"])

    def test_connect_with_invalid_format_shows_error(self):
        response = self.client.post(
            reverse("dashboard:settings-integration-connect", args=["google_analytics"]),
            {"measurement_id": "not-valid"}, follow=True,
        )
        self.assertContains(response, "الگو")

    def test_disconnect_deactivates(self):
        store = Store.objects.get(slug="akhlaghi")
        integration_service.connect(store=store, provider_code="torob", values={"merchant_id": "m-1"}, actor=None)
        response = self.client.post(reverse("dashboard:settings-integration-disconnect", args=["torob"]))
        self.assertRedirects(response, "/admin-portal/settings/?section=integrations")
        rows = integration_service.connections_context(store=store)
        torob_row = next(row for row in rows if row["provider"].code == "torob")
        self.assertFalse(torob_row["is_connected"])

    def test_test_connection_shows_result(self):
        store = Store.objects.get(slug="akhlaghi")
        integration_service.connect(
            store=store, provider_code="ad_pixel", values={"pixel_id": "1234567890123456"}, actor=None,
        )
        response = self.client.post(reverse("dashboard:settings-integration-test", args=["ad_pixel"]), follow=True)
        self.assertContains(response, "پیکسلِ تبلیغاتی")

    def test_unknown_provider_404s(self):
        response = self.client.post(reverse("dashboard:settings-integration-connect", args=["not-a-provider"]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-integration-connect", args=["enamad"]))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_connecting_appears_in_the_existing_audit_log_page(self):
        """رخدادهای یکپارچه‌سازی نیازی به یک صفحه‌ی گزارشِ جداگانه ندارند —
        همان صفحه‌ی «گزارش رخدادها»ی موجود (AuditLogEntry) را بازاستفاده
        می‌کنند."""
        self.client.post(
            reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "m-999"},
        )
        response = self.client.get(reverse("dashboard:audit-log-list"))
        self.assertContains(response, "integration.connected")

    def test_credentials_never_appear_as_plaintext_in_encrypted_column(self):
        from apps.stores.models import StoreIntegrationConnection

        self.client.post(
            reverse("dashboard:settings-integration-connect", args=["enamad"]),
            {"enamad_id": "555444", "enamad_auth_code": "superUniqueCode999"},
        )
        connection = StoreIntegrationConnection.objects.get(store__slug="akhlaghi", provider_code="enamad")
        self.assertNotIn("superUniqueCode999", connection.encrypted_credentials)


_HOST_B = f"integration-view-store-b.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[_HOST_B, "testserver"])
class IntegrationTenantIsolationViewTests(TestCase):
    """یک کارمندِ فروشگاهِ B هرگز نباید بتواند اتصالِ فروشگاهِ A را از طریقِ
    این ویوها ببیند یا تغییر دهد — هر ویو از request.store (که staff_required
    resolve می‌کند) استفاده می‌کند، نه یک شناسه‌ی خامِ ارسالی."""

    def setUp(self):
        from apps.core.models import ShopSettings

        self.store_b = Store.objects.create(
            name="Store B", slug="integration-view-store-b", status=Store.Status.ACTIVE,
            admin_subdomain="integration-view-store-b",
        )
        ShopSettings.provision_for(self.store_b)
        integration_service.connect(
            store=Store.objects.get(slug="akhlaghi"), provider_code="enamad",
            values={"enamad_id": "111222", "enamad_auth_code": "akhlaghiSecretCode"}, actor=None,
        )
        self.staff_b = User.objects.create_user(username="09121197002", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store_b, user=self.staff_b, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def test_store_b_staff_sees_own_disconnected_state_not_akhlaghis(self):
        self.client.login(username="09121197002", password="pass12345")
        response = self.client.get(
            reverse("dashboard:settings") + "?section=integrations", HTTP_HOST=_HOST_B,
        )
        self.assertNotContains(response, "akhlaghiSecretCode")


class IntegrationAccordionTests(TestCase):
    """Accordion rows: closed by default, «connected» = the real is_active flag, toggle = disconnect / reconnect with saved data."""

    def setUp(self):
        self.staff = User.objects.create_user(username="09121197002", password="pass12345", is_staff=True)
        _grant_akhlaghi_membership(self.staff)
        self.client.login(username="09121197002", password="pass12345")
        self.url = reverse("dashboard:settings") + "?section=integrations"
        self.store = Store.objects.get(slug="akhlaghi")

    def row(self, code):
        return next(r for r in integration_service.connections_context(store=self.store) if r["provider"].code == code)

    def test_five_rows_closed_by_default_without_toggle_until_something_is_saved(self):
        html = self.client.get(self.url).content.decode()
        for code in ("enamad", "torob", "google_analytics", "google_tag_manager", "ad_pixel"):
            self.assertIn(f'id="int-{code}"', html)
        self.assertNotIn("au-acc is-open", html)
        self.assertNotIn('role="switch"', html)

    def test_toggle_off_keeps_credentials_and_toggle_on_restores_the_connection(self):
        self.client.post(reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "SHOP-77"})
        self.assertTrue(self.row("torob")["is_connected"])
        self.client.post(reverse("dashboard:settings-integration-toggle", args=["torob"]))
        row = self.row("torob")
        self.assertFalse(row["is_connected"])
        self.assertTrue(row["can_reenable"])                    # data kept; «connected» and «enabled» are the same real flag
        self.assertContains(self.client.get(self.url), "غیرفعال — اطلاعات ذخیره است")
        self.client.post(reverse("dashboard:settings-integration-toggle", args=["torob"]))
        self.assertTrue(self.row("torob")["is_connected"])
        self.assertEqual(self.row("torob")["credentials"]["merchant_id"], "SHOP-77")

    def test_toggle_on_without_saved_data_explains_and_stays_off(self):
        self.client.post(reverse("dashboard:settings-integration-toggle", args=["torob"]))
        self.assertFalse(self.row("torob")["is_connected"])

    def test_connect_error_reopens_the_row_with_the_message(self):
        self.client.post(reverse("dashboard:settings-integration-connect", args=["google_analytics"]), {"measurement_id": "bad"})
        page = self.client.get(self.url)
        self.assertContains(page, "au-acc is-open")
        self.assertContains(page, "الگو")

    def test_test_result_and_date_are_shown_and_say_no_external_call(self):
        self.client.post(reverse("dashboard:settings-integration-connect", args=["torob"]), {"merchant_id": "SHOP-77"})
        self.client.post(reverse("dashboard:settings-integration-test", args=["torob"]))
        page = self.client.get(self.url)
        self.assertContains(page, 'data-testid="int-last-test"')
        self.assertContains(page, "به سرویس بیرونی درخواستی نمی‌فرستد")

    def test_toggle_is_store_scoped_and_needs_authentication(self):
        anon = self.client_class()
        self.assertEqual(anon.post(reverse("dashboard:settings-integration-toggle", args=["torob"])).status_code, 302)
        self.assertEqual(self.client.post(reverse("dashboard:settings-integration-toggle", args=["nope"])).status_code, 404)
