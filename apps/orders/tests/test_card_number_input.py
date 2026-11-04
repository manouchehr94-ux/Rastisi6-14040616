"""Card-transfer settings: the card number is judged on its DIGITS, never on grouped/display characters.

Regression for: «6104 1234 1234 1234» / copy-pasted or RTL-typed numbers (ZWNJ, ZWSP, LRM, RLM, bidi isolates, Arabic comma, fullwidth digits) rejected with a
"16 digits" error although 16 digits were visible — and junk persisted into the stored card. One backend rule (``strip_display_formatting``); the browser mask mirrors it.
All numbers below are synthetic test values (Luhn-valid but not real accounts); no payment is made and no existing store data is touched."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.encryption import reset_fernet
from apps.orders.gateways import get_adapter
from apps.orders.gateways.card_to_card import card_number_error, clean_card_number, clean_sheba
from apps.orders.models import PaymentGatewayConfig
from apps.orders.services import card_transfer_service
from apps.orders.tests.test_card_transfer import CardTransferBase
from apps.stores.models import Store, StoreMembership

User = get_user_model()
SAVE = "/admin-portal/settings/gateway-config/card_to_card/save/"
PAGE = "/admin-portal/settings/?section=payment-config"
DIGITS = "6104123412341234"                  # the reported sample: 16 digits, Luhn-valid, synthetic
GROUPED = "6104 1234 1234 1234"
SHEBA = "IR062960000000100324200001"          # synthetic

SHAPES = {
    "plain": DIGITS, "grouped": GROUPED, "persian": "۶۱۰۴ ۱۲۳۴ ۱۲۳۴ ۱۲۳۴", "persian_plain": "۶۱۰۴۱۲۳۴۱۲۳۴۱۲۳۴", "arabic_indic": "٦١٠٤ ١٢٣٤ ١٢٣٤ ١٢٣٤",
    "fullwidth": "６１０４１２３４１２３４１２３４", "mixed_scripts": "6104 ۱۲۳۴ ١٢٣٤ 1234", "nbsp": "6104 1234 1234 1234", "thin_space": "6104 1234 1234 1234",
    "zwnj": "6104‌1234‌1234‌1234", "zwsp": "6104​1234​1234​1234", "lrm_rlm": "‎6104 1234 1234 1234‏", "bidi_isolates": "⁦6104 1234 1234 1234⁩",
    "dashes": "6104-1234-1234-1234", "en_dash": "6104–1234–1234–1234", "underscore": "6104_1234_1234_1234", "tab_newline": "6104\t1234\n1234\r1234", "arabic_comma": "6104،1234،1234،1234",
    "slashes_dots": "6104/1234.1234,1234", "padded": "   6104 1234 1234 1234   ", "double_spaces": "6104  1234   1234    1234",
}
INVALID = {
    "empty": ("", "را وارد کنید"), "spaces_only": ("   ", "را وارد کنید"),
    "fifteen_digits": ("610412341234123", "دقیقاً ۱۶ رقم"), "seventeen_digits": ("61041234123412345", "دقیقاً ۱۶ رقم"),
    "letters": ("abcdabcdabcdabcd", "فقط باید شامل رقم"), "letter_inside": ("6104 1234 12X4 1234", "فقط باید شامل رقم"),
    "symbol_inside": ("6104 1234 12#4 1234", "فقط باید شامل رقم"), "devanagari_digits": ("६१०४१२३४१२३४१२३४", "فقط باید شامل رقم"),
    "checksum_wrong": ("6104123412341235", "معتبر نیست"),
}


class NormalizerTests(SimpleTestCase):
    def test_every_formatting_shape_reduces_to_the_same_sixteen_ascii_digits(self):
        for name, raw in SHAPES.items():
            self.assertEqual(clean_card_number(raw), DIGITS, name)
            self.assertEqual(card_number_error(raw), "", name)

    def test_length_is_the_number_of_digits_not_of_characters(self):
        self.assertEqual(len(GROUPED), 19)
        self.assertEqual(card_number_error(GROUPED), "")
        self.assertEqual(card_number_error("6104  1234   1234    1234‌"), "")

    def test_invalid_input_gets_one_specific_reason_and_never_raises(self):
        for name, (raw, expected) in INVALID.items():
            message = card_number_error(raw)
            self.assertIn(expected, message, name)
        self.assertEqual(len({card_number_error(raw) for _n, (raw, _e) in INVALID.items() if raw.strip()}), 3)    # non-digit / length / checksum

    def test_the_checksum_and_the_exact_length_rules_are_not_weakened(self):
        self.assertTrue(card_number_error("6104123412341235"))                      # Luhn still enforced
        self.assertTrue(card_number_error(DIGITS[:-1]))                              # 15 digits still refused
        self.assertTrue(card_number_error(DIGITS + "0"))                             # 17 digits still refused
        self.assertTrue(card_number_error("6104 1234 ١٢٣x 1234"))                    # a stray letter is never silently dropped

    def test_sheba_gets_the_same_treatment(self):
        for raw in (SHEBA, "IR06 2960 0000 0010 0324 2000 01", "ir" + SHEBA[2:].translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")), "IR06‌2960‎0000 0010-0324 2000 01"):
            self.assertEqual(clean_sheba(raw), SHEBA, raw)
        self.assertNotEqual(clean_sheba("IR06 2960 0000 0010 0324 2000"), SHEBA)

    def test_only_the_card_adapter_normalizes_credentials(self):
        for code in ("zibal", "cod", "zarinpal", "pasargad", "snappay", "torobpay", "mellat"):
            creds = {"merchant": "a b‌ c", "merchant_id": "x y", "client_id": " 1 2 ", "destination_card": "6104 1234 1234 1234"}
            self.assertEqual(get_adapter(code).normalize_credentials(creds), creds, code)         # untouched for every other provider
        self.assertEqual(get_adapter("card_to_card").normalize_credentials({"destination_card": GROUPED})["destination_card"], DIGITS)


class SaveReloadEditTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.addCleanup(reset_fernet)
        self.store = Store.objects.get(slug="akhlaghi")
        owner = User.objects.create_user(username="cardinput-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.login(username="cardinput-owner", password="pass12345")

    def save(self, number, **extra):
        data = {"credential_destination_card": number, "credential_holder_name": "علی رضایی", "display_order": "1", "is_active": "on", **extra}
        return self.client.post(SAVE, data)

    def config(self):
        return PaymentGatewayConfig.objects.get(store=self.store, gateway_code="card_to_card")

    def card_input_value(self, html):
        start = html.index('name="credential_destination_card"')
        return html[start:start + 400].split('value="', 1)[1].split('"', 1)[0]

    def test_initial_save_of_every_shape_stores_canonical_digits_activates_and_displays_groups(self):
        for name, raw in SHAPES.items():
            PaymentGatewayConfig.objects.filter(store=self.store, gateway_code="card_to_card").delete()
            response = self.save(raw)
            self.assertEqual(response.status_code, 200, name)
            self.assertNotContains(response, "au-error", msg_prefix=name)
            config = self.config()
            self.assertTrue(config.is_active, name)
            self.assertEqual(config.get_credentials()["destination_card"], DIGITS, name)           # canonical digits, no display junk
            self.assertEqual(self.card_input_value(response.content.decode()), GROUPED, name)       # the UI shows four groups of four

    def test_reload_edit_and_resave_cycle_preserves_the_card(self):
        self.save(GROUPED)
        shown = self.card_input_value(self.client.get(PAGE).content.decode())                       # 1) reload the page
        self.assertEqual(shown, GROUPED)
        again = self.save(shown, credential_holder_name="نام تازه")                                  # 2) re-save exactly what the UI showed (+ edit another field)
        self.assertNotContains(again, "au-error")
        self.assertEqual((self.config().get_credentials()["destination_card"], self.config().get_credentials()["holder_name"], self.config().is_active), (DIGITS, "نام تازه", True))
        self.save("6037 9970 0000 0019")                                                              # 3) edit the number itself
        self.assertEqual(self.config().get_credentials()["destination_card"], "6037997000000019")
        self.assertEqual(self.card_input_value(self.client.get(PAGE).content.decode()), "6037 9970 0000 0019")

    def test_invalid_numbers_are_refused_with_a_specific_reason_not_activated_and_never_stored_with_junk(self):
        for name, (raw, expected) in INVALID.items():
            PaymentGatewayConfig.objects.filter(store=self.store, gateway_code="card_to_card").delete()
            response = self.save(raw)
            self.assertContains(response, expected, msg_prefix=name)
            config = self.config()
            self.assertFalse(config.is_active, name)
            self.assertNotIn("‌", config.get_credentials().get("destination_card", ""), name)
        self.assertNotContains(self.save("6104 1234 1234 12"), "ارقام را دوباره بررسی کنید")           # a length problem is never reported as a checksum problem

    def test_sheba_is_normalized_and_validated_without_touching_the_card(self):
        self.save(GROUPED, credential_sheba="ir06 2960 0000 0010 0324 2000 01")
        creds = self.config().get_credentials()
        self.assertEqual((creds["sheba"], creds["destination_card"]), (SHEBA, DIGITS))
        bad = self.save(GROUPED, credential_sheba="IR06 2960")
        self.assertContains(bad, "شماره شبا باید با IR شروع شود")

    def test_a_card_saved_earlier_with_junk_stays_readable_usable_and_untouched_until_resaved(self):
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="card_to_card", is_active=True)
        config.set_credentials({"destination_card": "6104‌ 1234‎ 1234 1234", "holder_name": "علی رضایی"})
        config.save()
        before = PaymentGatewayConfig.objects.get(pk=config.pk).encrypted_credentials
        fresh = PaymentGatewayConfig.objects.get(pk=config.pk)
        self.assertTrue(fresh.is_configured and fresh.can_activate and fresh.is_selectable_at_checkout)
        self.assertEqual(card_transfer_service.active_config(self.store).pk, fresh.pk)
        self.assertEqual(card_transfer_service.destination_for(fresh).card, DIGITS)
        self.assertEqual(self.card_input_value(self.client.get(PAGE).content.decode()), GROUPED)
        self.assertEqual(PaymentGatewayConfig.objects.get(pk=config.pk).encrypted_credentials, before)   # viewing destroyed nothing

    def test_other_gateways_save_flows_are_unaffected(self):
        zibal = self.client.post("/admin-portal/settings/gateway-config/zibal/save/", {"credential_merchant": "zbl merchant", "display_order": "1", "is_active": "on"})
        self.assertEqual(zibal.status_code, 200)
        self.assertEqual(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal").get_credentials()["merchant"], "zbl merchant")   # not "cleaned"
        cod = self.client.post("/admin-portal/settings/gateway-config/cod/save/", {"display_order": "2", "is_active": "on"})
        self.assertEqual(cod.status_code, 200)
        self.assertTrue(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="cod").is_active)


class CustomerPageTests(CardTransferBase):
    def test_the_customer_sees_the_destination_card_in_groups_even_when_it_was_stored_with_junk(self):
        self.config.set_credentials({"destination_card": "۶۰۳۷‌۹۹۷۰ ۰۰۰۰۰۰۱۹", "holder_name": "علی رضایی", "bank_name": "ملی"})
        self.config.save()
        order = self.make_order()
        with mock.patch("apps.orders.views.resolve_store_for_service", return_value=self.store), mock.patch(
            "apps.storefront_builder.services.storefront_context_service.build_universal_storefront_context", return_value={},
        ):
            client = Client()
            client.force_login(self.user)
            page = client.get(reverse("orders:card-transfer", args=[order.code]))
        self.assertContains(page, "6037 9970 0000 0019")
        self.assertNotContains(page, "‌6037")
