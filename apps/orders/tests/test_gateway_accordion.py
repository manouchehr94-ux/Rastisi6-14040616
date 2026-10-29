"""Payment-gateway settings as accordions: closed by default, honest toggles, per-field errors, no secret exposure."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.encryption import reset_fernet
from apps.orders.models import PaymentGateway, PaymentGatewayConfig
from apps.stores.models import Store, StoreMembership

User = get_user_model()
VALID_CARD = "6037997000000019"


class GatewayAccordionTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="acc-admin", password="pass123", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="acc-admin", password="pass123")
        self.save_url = reverse("dashboard:settings-gateway-config-save", args=["card_to_card"])
        self.toggle_url = reverse("dashboard:settings-gateway-config-toggle", args=["card_to_card"])

    def tearDown(self):
        reset_fernet()

    def test_page_has_one_closed_accordion_per_gateway_with_accessible_switches(self):
        page = self.client.get("/admin-portal/settings/?section=payment-config")
        for code in ("zibal", "cod", "card_to_card"):
            self.assertContains(page, f'id="gw-{code}"')
        html = page.content.decode()
        self.assertNotIn("au-acc is-open", html)
        self.assertEqual(html.count('aria-expanded="false"'), 3)
        self.assertIn('role="switch"', html)
        self.assertIn('aria-checked="false"', html)

    def test_activation_of_incomplete_card_to_card_is_refused_with_per_field_errors(self):
        res = self.client.post(self.save_url, {"is_active": "on", "credential_destination_card": "1234 5678 1234 5678"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "شماره کارت مقصد باید یک شماره کارت معتبر ۱۶ رقمی باشد.")
        self.assertContains(res, "نام صاحب کارت را وارد کنید.")
        self.assertContains(res, "au-acc is-open")                       # opened because of the error
        self.assertContains(res, 'aria-checked="false"')                 # the switch does not claim "on"
        self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card").is_active)
        self.assertIn("err", res["HX-Trigger"])

    def test_toggle_on_an_incomplete_gateway_explains_and_stays_off(self):
        res = self.client.post(self.toggle_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "شماره کارت مقصد را وارد کنید.")
        self.assertContains(res, "نیازمند تکمیل اطلاعات")
        self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card").is_active)

    def test_spaced_card_number_is_accepted_stored_clean_and_shown_grouped_ltr(self):
        res = self.client.post(self.save_url, {
            "is_active": "on", "credential_destination_card": "6037 9970 0000 0019", "credential_holder_name": "علی رضایی",
        })
        self.assertContains(res, 'aria-checked="true"')
        self.assertContains(res, 'value="6037 9970 0000 0019"')
        self.assertContains(res, 'dir="ltr"')
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card")
        self.assertTrue(config.is_active)
        self.assertEqual(config.get_credentials()["destination_card"], VALID_CARD)
        self.assertTrue(PaymentGateway.objects.get(store=self.store, slug="card_to_card").is_active)
        off = self.client.post(self.toggle_url)
        self.assertContains(off, 'aria-checked="false"')
        self.assertFalse(PaymentGateway.objects.get(store=self.store, slug="card_to_card").is_active)

    def test_zibal_merchant_is_never_echoed_back(self):
        url = reverse("dashboard:settings-gateway-config-save", args=["zibal"])
        res = self.client.post(url, {"credential_merchant": "SECRET-MERCHANT-XYZ", "is_active": "on"})
        self.assertNotContains(res, "SECRET-MERCHANT-XYZ")
        page = self.client.get("/admin-portal/settings/?section=payment-config")
        self.assertNotContains(page, "SECRET-MERCHANT-XYZ")

    def test_zibal_without_merchant_reports_the_missing_field(self):
        res = self.client.post(reverse("dashboard:settings-gateway-config-toggle", args=["zibal"]))
        self.assertContains(res, "شناسه‌ی مرچنت")
        self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal").is_active)

    def test_cod_toggles_without_credentials(self):
        url = reverse("dashboard:settings-gateway-config-toggle", args=["cod"])
        self.assertContains(self.client.post(url), 'aria-checked="true"')
        self.assertContains(self.client.post(url), 'aria-checked="false"')
