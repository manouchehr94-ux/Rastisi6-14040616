import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreMembership

User = get_user_model()


class SettingsViewsTestCase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-sv", is_active=True)
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست پیشتاز", slug="post-sv", is_active=True)
        self.staff = User.objects.create_user(username="09121192001", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121192001", password="pass12345")


class SettingsHomeViewTests(SettingsViewsTestCase):
    def test_renders_settings_page(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_default_section_is_general(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_finance_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=finance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مالی و مالیات")

    def test_delivery_payment_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=delivery-payment")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درگاه‌های پرداخت")
        self.assertContains(response, "زرین‌پال")
        self.assertContains(response, "پست پیشتاز")

    def test_sms_section(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اعتبار پیامک")

    def test_appearance_section_shows_visual_identity_form(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "هویت بصری")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "رنگ اصلی")

    def test_invalid_section_falls_back_to_general(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=nonexistent")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اطلاعات فروشگاه")

    def test_navigation_shows_all_sections(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, "اطلاعات فروشگاه")
        self.assertContains(response, "مالی و مالیات")
        self.assertContains(response, "ارسال و درگاه")
        self.assertContains(response, "پیامک")
        self.assertContains(response, "تم رنگی")

    def test_active_section_indicated(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=delivery-payment")
        self.assertContains(response, 'aria-current="page"')

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
class SettingsShopInfoViewTests(SettingsViewsTestCase):
    def test_valid_post_updates_shop_settings(self):
        response = self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "فروشگاه جدید", "tagline": "شعار جدید", "contact_phone": "021-1111",
            "contact_email": "new@example.com", "contact_address": "آدرس جدید", "description": "توضیح",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=general")
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "فروشگاه جدید")
        self.assertEqual(shop.contact_email, "new@example.com")

    def test_contact_update_does_not_overwrite_store_identity(self):
        """Updating contact fields preserves name/tagline/description."""
        # First set known identity values
        shop = ShopSettings.load()
        shop.name = "نام اصلی"
        shop.tagline = "شعار اصلی"
        shop.description = "توضیح اصلی"
        shop.save()

        # Submit form with all fields (single form approach)
        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "نام اصلی", "tagline": "شعار اصلی", "description": "توضیح اصلی",
            "contact_phone": "021-9999", "contact_email": "updated@test.com",
            "contact_address": "آدرس جدید",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "نام اصلی")
        self.assertEqual(shop.tagline, "شعار اصلی")
        self.assertEqual(shop.description, "توضیح اصلی")
        self.assertEqual(shop.contact_phone, "021-9999")

    def test_store_identity_update_does_not_overwrite_contact(self):
        """Updating identity fields preserves contact fields."""
        shop = ShopSettings.load()
        shop.contact_phone = "021-5555"
        shop.contact_email = "keep@test.com"
        shop.contact_address = "آدرس حفظ"
        shop.save()

        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "نام جدید", "tagline": "شعار جدید", "description": "توضیح جدید",
            "contact_phone": "021-5555", "contact_email": "keep@test.com",
            "contact_address": "آدرس حفظ",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.name, "نام جدید")
        self.assertEqual(shop.contact_phone, "021-5555")
        self.assertEqual(shop.contact_email, "keep@test.com")

    def test_updated_name_appears_on_storefront(self):
        self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "دیجی‌مارکت ویژه", "tagline": "", "contact_phone": "", "contact_email": "",
            "contact_address": "", "description": "",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "دیجی‌مارکت ویژه")

    def test_invalid_email_rejected(self):
        response = self.client.post(reverse("dashboard:settings-shop-info"), {
            "name": "فروشگاه", "tagline": "", "contact_phone": "", "contact_email": "not-an-email",
            "contact_address": "", "description": "",
        })
        self.assertEqual(response.status_code, 200)


class SettingsFinanceViewTests(SettingsViewsTestCase):
    def test_valid_post_updates_tax_and_threshold(self):
        response = self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "۷", "free_shipping_threshold": "۷۰۰۰۰۰",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=finance")
        shop = ShopSettings.load()
        self.assertEqual(shop.tax_percent, Decimal("7"))
        self.assertEqual(shop.free_shipping_threshold, Decimal("700000"))

    def test_updated_tax_percent_affects_pricing_service(self):
        from decimal import Decimal as D

        from apps.cart.models import Cart, CartItem
        from apps.cart.services.pricing import cart_totals
        from apps.catalog.models import Category, Product, Vendor
        from apps.stores.models import Store

        self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "5", "free_shipping_threshold": "1000000",
        })
        store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=store, name="فروشگاه", slug="shop-sf")
        category = Category.objects.create(store=store, name="دسته", slug="cat-sf")
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالا", slug="prod-sf",
            sku="SKU-SF1", price=D("100000"),
        )
        cart = Cart.objects.create(session_key="guest-sf")
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=product.final_price)
        totals = cart_totals(cart, store=store, shipping_method=self.shipping)
        self.assertEqual(totals["tax"], D("5000"))

    def test_out_of_range_tax_percent_rejected(self):
        response = self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "150", "free_shipping_threshold": "500000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تنظیمات مالی و مالیات")  # Stays on finance section


class SettingsGiftWrapViewTests(SettingsViewsTestCase):
    """Checkpoint — merchant-configurable gift wrap availability/price
    (toranj_gifting: optional_addon_checkbox_updates_total)."""

    def test_valid_post_enables_gift_wrap_and_sets_price(self):
        response = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_available": "on", "gift_wrap_price": "۱۵۰۰۰",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=finance")
        shop = ShopSettings.load()
        self.assertTrue(shop.gift_wrap_available)
        self.assertEqual(shop.gift_wrap_price, Decimal("15000"))

    def test_omitting_checkbox_disables_gift_wrap(self):
        shop = ShopSettings.load()
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("10000")
        shop.save(update_fields=["gift_wrap_available", "gift_wrap_price"])

        self.client.post(reverse("dashboard:settings-gift-wrap"), {"gift_wrap_price": "10000"})
        shop = ShopSettings.load()
        self.assertFalse(shop.gift_wrap_available)

    def test_negative_price_rejected(self):
        response = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_available": "on", "gift_wrap_price": "-500",
        })
        self.assertEqual(response.status_code, 200)
        shop = ShopSettings.load()
        self.assertFalse(shop.gift_wrap_available)  # unchanged — form rejected

    def test_finance_section_renders_gift_wrap_card(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=finance")
        self.assertContains(response, "کادوپیچی")


class SettingsGatewayToggleViewTests(SettingsViewsTestCase):
    def test_toggle_flips_is_active_and_persists(self):
        response = self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertEqual(response.status_code, 204)
        self.gateway.refresh_from_db()
        self.assertFalse(self.gateway.is_active)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("غیرفعال", trigger["toast"]["message"])

    def test_disabled_gateway_disappears_from_checkout_options(self):
        from apps.orders.services.checkout_service import active_payment_gateways

        self.client.post(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertNotIn(self.gateway, active_payment_gateways(store=self.store))

    def test_get_not_allowed(self):
        response = self.client.get(reverse("dashboard:settings-gateway-toggle", args=[self.gateway.pk]))
        self.assertEqual(response.status_code, 405)


class SettingsShippingToggleViewTests(SettingsViewsTestCase):
    def test_toggle_flips_is_active(self):
        response = self.client.post(reverse("dashboard:settings-shipping-toggle", args=[self.shipping.pk]))
        self.assertEqual(response.status_code, 204)
        self.shipping.refresh_from_db()
        self.assertFalse(self.shipping.is_active)

    def test_disabled_method_disappears_from_checkout_options(self):
        from apps.orders.services.checkout_service import active_shipping_methods

        self.client.post(reverse("dashboard:settings-shipping-toggle", args=[self.shipping.pk]))
        self.assertNotIn(self.shipping, active_shipping_methods(store=self.store))



class SettingsSMSSectionTests(SettingsViewsTestCase):
    """SMS actions preserve the SMS section state."""

    def test_sms_connection_save_redirects_to_sms_section(self):
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": True, "sms_backend": "console",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")

    def test_smsrasti_backend_choice_is_saved(self):
        """کاوه‌نگار/ملی‌پیامک دیگر انتخابِ Store نیستند (زیرساختِ پلتفرم) —
        تنها انتخابِ باقی‌مانده «درگاهِ پلتفرم» یا دستگاهِ اسمس‌راستیِ خودِ
        Store است."""
        from apps.core.models import ShopSettings

        self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": True, "sms_backend": "smsrasti",
        })
        shop = ShopSettings.load(store=self.store)
        self.assertEqual(shop.sms_backend, "smsrasti")

    def test_smsrasti_token_regeneration_creates_and_rotates_token(self):
        from apps.core.models import ShopSettings

        response = self.client.post(reverse("dashboard:settings-smsrasti-regenerate-token"))
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")
        first_token = ShopSettings.load(store=self.store).smsrasti_device_token
        self.assertTrue(first_token)

        self.client.post(reverse("dashboard:settings-smsrasti-regenerate-token"))
        second_token = ShopSettings.load(store=self.store).smsrasti_device_token
        self.assertNotEqual(first_token, second_token)

    def test_sms_test_send_redirects_to_sms_section(self):
        response = self.client.post(reverse("dashboard:sms-test-send"), {
            "phone": "09121234567", "event_key": "welcome",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")

    def test_sms_section_shows_connection_form(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "فعال‌سازی سیستم پیامک")
        self.assertContains(response, "ذخیره تنظیمات")

    def test_sms_section_shows_templates(self):
        from apps.sms.models import SmsTemplate
        SmsTemplate.ensure_defaults()
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "قالب‌های پیامک")


class SettingsGeneralFormTests(SettingsViewsTestCase):
    """General section has one unified form — no fragile hidden fields."""

    def test_general_section_has_one_form_action(self):
        """Only one form submits to settings-shop-info (no duplicate forms)."""
        response = self.client.get(reverse("dashboard:settings") + "?section=general")
        content = response.content.decode()
        # Count occurrences of the form action URL
        action_url = reverse("dashboard:settings-shop-info")
        self.assertEqual(content.count(f'action="{action_url}"'), 1)

    def test_general_section_has_no_hidden_name_field(self):
        """No fragile hidden fields for preserving other form's values."""
        response = self.client.get(reverse("dashboard:settings") + "?section=general")
        content = response.content.decode()
        self.assertNotIn('type="hidden" name="name"', content)
        self.assertNotIn('type="hidden" name="tagline"', content)



class VisualIdentityTests(SettingsViewsTestCase):
    """Tests for visual identity settings: colors, logo, favicon."""

    def test_valid_colors_save(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#1F2937",
            "accent_color": "#C59A45",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#1F2937")
        self.assertEqual(shop.accent_color, "#C59A45")

    def test_lowercase_hex_normalized_to_uppercase(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#aabbcc",
            "accent_color": "#112233",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#AABBCC")
        self.assertEqual(shop.accent_color, "#112233")

    def test_short_hex_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFF",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#RRGGBB")

    def test_non_hex_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "red",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#RRGGBB")

    def test_css_function_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "rgb(255,0,0)",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)

    def test_script_payload_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "<script>",
            "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 200)
        # Malicious value not stored
        shop = ShopSettings.load()
        self.assertNotEqual(shop.primary_color, "<script>")

    def test_appearance_save_redirects_to_appearance_section(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9",
            "accent_color": "#FF4D77",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")

    def test_appearance_validation_error_stays_on_appearance(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "invalid",
            "accent_color": "invalid",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "رنگ‌بندی")

    def test_storefront_uses_configured_colors(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#112233",
            "accent_color": "#445566",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-primary:#112233")
        self.assertContains(response, "--brand-accent:#445566")

    def test_empty_logo_uses_fallback(self):
        """When no logo is set, storefront uses the SVG mark fallback."""
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "class=\"mark\"")

    def test_empty_favicon_uses_static_fallback(self):
        """When no favicon is set, static favicon.ico is referenced."""
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "favicon.ico")

    def test_default_colors_are_valid(self):
        shop = ShopSettings.load()
        import re
        self.assertRegex(shop.primary_color, r"^#[0-9A-Fa-f]{6}$")
        self.assertRegex(shop.accent_color, r"^#[0-9A-Fa-f]{6}$")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#000000", "accent_color": "#000000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
import os
import re
import tempfile
import shutil

from django.test import override_settings

_TEMP_MEDIA_DIR = tempfile.mkdtemp()


def _make_image(fmt='PNG', size=(100, 100)):
    from io import BytesIO
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    buf = BytesIO()
    img = Image.new('RGBA' if fmt == 'PNG' else 'RGB', size, (255, 0, 0))
    img.save(buf, format=fmt)
    ext = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[fmt]
    ct = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[fmt]
    return SimpleUploadedFile(f'test.{ext}', buf.getvalue(), content_type=ct)


@override_settings(MEDIA_ROOT=_TEMP_MEDIA_DIR)
class LogoUploadTests(SettingsViewsTestCase):
    """Complete logo upload lifecycle tests with isolated media."""

    def tearDown(self):
        # Clean temp files after each test
        for f in os.listdir(_TEMP_MEDIA_DIR):
            path = os.path.join(_TEMP_MEDIA_DIR, f)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    def test_valid_png_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        self.assertRedirects(resp, "/admin-portal/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_valid_jpeg_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("JPEG"),
        })
        self.assertRedirects(resp, "/admin-portal/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_valid_webp_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("WEBP"),
        })
        self.assertRedirects(resp, "/admin-portal/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().logo)

    def test_oversized_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("big.png", b"x" * (3 * 1024 * 1024), content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": big,
        })
        self.assertEqual(resp.status_code, 200)

    def test_fake_content_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile("fake.png", b"not-image", content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": fake,
        })
        self.assertEqual(resp.status_code, 200)

    def test_svg_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        svg = SimpleUploadedFile("logo.svg", b"<svg></svg>", content_type="image/svg+xml")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": svg,
        })
        self.assertEqual(resp.status_code, 200)

    def test_empty_upload_preserves_current(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        old = ShopSettings.load().logo.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
        })
        self.assertEqual(ShopSettings.load().logo.name, old)

    def test_replacement_saves_new(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        old = ShopSettings.load().logo.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("JPEG"),
        })
        new = ShopSettings.load().logo.name
        self.assertNotEqual(old, new)

    def test_explicit_removal(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": _make_image("PNG"),
        })
        self.assertTrue(ShopSettings.load().logo)
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "remove_logo": "on",
        })
        self.assertFalse(ShopSettings.load().logo)

    def test_simultaneous_upload_and_remove_replacement_wins(self):
        """When both upload and remove are submitted, replacement wins."""
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "logo": _make_image("PNG"), "remove_logo": "on",
        })
        # Replacement wins — logo is set
        self.assertTrue(ShopSettings.load().logo)


@override_settings(MEDIA_ROOT=_TEMP_MEDIA_DIR)
class FaviconUploadTests(SettingsViewsTestCase):
    """Complete favicon upload lifecycle tests with isolated media."""

    def tearDown(self):
        for f in os.listdir(_TEMP_MEDIA_DIR):
            path = os.path.join(_TEMP_MEDIA_DIR, f)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

    def _fav(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = BytesIO()
        Image.new("RGBA", (32, 32), (0, 0, 255, 255)).save(buf, "PNG")
        return SimpleUploadedFile("fav.png", buf.getvalue(), content_type="image/png")

    def test_valid_png_saves(self):
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        self.assertRedirects(resp, "/admin-portal/settings/?section=appearance")
        self.assertTrue(ShopSettings.load().favicon)

    def test_oversized_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        big = SimpleUploadedFile("big.png", b"x" * (600 * 1024), content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": big,
        })
        self.assertEqual(resp.status_code, 200)

    def test_fake_content_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile("fake.png", b"not-image", content_type="image/png")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": fake,
        })
        self.assertEqual(resp.status_code, 200)

    def test_svg_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        svg = SimpleUploadedFile("f.svg", b"<svg></svg>", content_type="image/svg+xml")
        resp = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": svg,
        })
        self.assertEqual(resp.status_code, 200)

    def test_empty_upload_preserves_current(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        old = ShopSettings.load().favicon.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
        })
        self.assertEqual(ShopSettings.load().favicon.name, old)

    def test_replacement_saves_new(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        old = ShopSettings.load().favicon.name
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        new = ShopSettings.load().favicon.name
        self.assertNotEqual(old, new)

    def test_explicit_removal(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        self.assertTrue(ShopSettings.load().favicon)
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "remove_favicon": "on",
        })
        self.assertFalse(ShopSettings.load().favicon)

    def test_simultaneous_upload_and_remove_replacement_wins(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "favicon": self._fav(), "remove_favicon": "on",
        })
        self.assertTrue(ShopSettings.load().favicon)

    def test_configured_favicon_in_html(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "favicon": self._fav(),
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, 'rel="icon"')
        self.assertContains(resp, "shop/branding/")

    def test_fallback_favicon_when_not_set(self):
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "favicon.ico")


class ContrastAndSafetyTests(SettingsViewsTestCase):
    """Contrast calculation, model validation, and safe rendering tests."""

    def test_dark_primary_gets_white_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#1F2937", "accent_color": "#000000",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary-fg:#FFFFFF")

    def test_light_primary_gets_black_foreground(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFFFFF", "accent_color": "#FFFF00",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary-fg:#000000")
        self.assertContains(resp, "--brand-accent-fg:#000000")

    def test_invalid_stored_color_uses_default(self):
        ShopSettings.objects.filter(store__slug="akhlaghi").update(primary_color="invalid", accent_color="")
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary:#6D28D9")
        self.assertNotContains(resp, "invalid")

    def test_model_validator_rejects_invalid(self):
        from django.core.exceptions import ValidationError
        from apps.core.models import validate_hex_color
        with self.assertRaises(ValidationError):
            validate_hex_color("red")
        with self.assertRaises(ValidationError):
            validate_hex_color("#FFF")

    def test_brand_colors_in_storefront(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#AA1122", "accent_color": "#33BB44",
        })
        resp = self.client.get(reverse("catalog:home"))
        self.assertContains(resp, "--brand-primary:#AA1122")
        self.assertContains(resp, "--brand-accent:#33BB44")

    def test_layout_css_uses_foreground_vars(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "core", "static", "css", "layout.css"
        )
        with open(css_path) as f:
            css = f.read()
        self.assertIn("var(--brand-primary-fg", css)
        self.assertIn("var(--brand-accent-fg", css)

    def test_default_gradients_preserved(self):
        """Default brand colors preserve existing gradient depth via --violet-2 and --violet-3."""
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "core", "static", "css", "tokens.css"
        )
        with open(css_path) as f:
            css = f.read()
        # Secondary gradient stops are now theme-aware while preserving the
        # exact historical colours as CSS fallbacks when no brand-secondary
        # override is present.
        self.assertIn("--violet-2:var(--brand-secondary, #7c3aed)", css)
        self.assertIn("--violet-3:var(--brand-secondary, #8b5cf6)", css)


# ============================================================ PR3: SETTINGS NAVIGATION REGRESSION


class ThemeSectionNavigationTests(SettingsViewsTestCase):
    """پیمایش بین بخش‌های تنظیمات پس از بازآرایی به تب‌های افقی."""

    def test_each_valid_section_renders(self):
        for key in ("general", "finance", "delivery-payment", "sms", "appearance"):
            response = self.client.get(reverse("dashboard:settings") + f"?section={key}")
            self.assertEqual(response.status_code, 200, f"section={key} did not render")

    def test_active_tab_marked_correctly_for_each_section(self):
        for key in ("general", "finance", "delivery-payment", "sms", "appearance"):
            response = self.client.get(reverse("dashboard:settings") + f"?section={key}")
            self.assertEqual(response.context["active_section"], key)
            self.assertContains(response, 'aria-current="page"')

    def test_finance_validation_error_stays_on_finance_section(self):
        response = self.client.post(reverse("dashboard:settings-finance"), {
            "tax_percent": "150", "free_shipping_threshold": "500000",
        })
        self.assertEqual(response.context["active_section"], "finance")

    def test_appearance_validation_error_keeps_active_section_appearance(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "invalid", "accent_color": "#000000",
        })
        self.assertEqual(response.context["active_section"], "appearance")

    def test_delivery_payment_section_shows_both_shipping_and_gateways(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=delivery-payment")
        self.assertContains(response, "روش‌های ارسال")
        self.assertContains(response, "درگاه‌های پرداخت")


# ============================================================ PR3: APPEARANCE RENDERING REGRESSION


class AppearanceRenderingRegressionTests(SettingsViewsTestCase):
    """اثبات این‌که صفحه‌ی تم رنگی واقعاً کنترل‌های خودش را رندر می‌کند و هرگز خالی نیست."""

    def test_appearance_page_contains_presets(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        for label in ("بنفش دیجیتال", "رز صورتی", "سبز زمردی", "عسلی کهربایی", "فیروزه‌ای", "زرشکی قرمز"):
            self.assertContains(response, label)

    def test_appearance_page_contains_all_custom_color_fields(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        for label in (
            "رنگ اصلی", "رنگ مکمل", "رنگ ثانویه", "رنگ پس‌زمینه‌ی صفحه",
            "رنگ پس‌زمینه‌ی کارت‌ها", "رنگ متن اصلی", "رنگ متن کم‌رنگ",
        ):
            self.assertContains(response, label)

    def test_appearance_page_contains_live_preview(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertContains(response, "پیش‌نمایش زنده")
        self.assertContains(response, "theme-preview")

    def test_appearance_page_is_not_blank(self):
        """رگرسیون: صفحه‌ی تم رنگی باید محتوای واقعی و قابل‌توجه داشته باشد، نه یک ناحیه‌ی خالی."""
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 8000)
        self.assertContains(response, "پیش‌فرض‌های آماده")
        self.assertContains(response, "ویرایشگر رنگ سفارشی")
        self.assertContains(response, "ذخیره و اعمال در کل سایت")
        self.assertContains(response, "بازگردانی به پیش‌فرض")

    def test_appearance_page_renders_when_legacy_blank_tokens_present(self):
        """اگر مقادیر جدید (قبل از migrate/بازسازی) خالی/نامعتبر باشند، صفحه با پیش‌فرض‌های امن رندر می‌شود."""
        ShopSettings.objects.filter(store__slug="akhlaghi").update(background_color="", text_color="not-a-color")
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ویرایشگر رنگ سفارشی")


# ============================================================ PR3: PRESETS


class ThemePresetTests(SettingsViewsTestCase):
    def test_every_preset_has_required_token_values(self):
        from apps.core.theme_presets import THEME_PRESETS
        import re
        hex_re = re.compile(r"^#[0-9A-Fa-f]{6}$")
        self.assertEqual(len(THEME_PRESETS), 6)
        for preset in THEME_PRESETS:
            self.assertTrue(hex_re.match(preset.primary), preset.key)
            self.assertTrue(hex_re.match(preset.secondary), preset.key)
            self.assertTrue(hex_re.match(preset.accent), preset.key)
            self.assertTrue(hex_re.match(preset.background), preset.key)
            self.assertTrue(preset.label)

    def test_preset_keys_are_unique(self):
        from apps.core.theme_presets import THEME_PRESETS
        keys = [p.key for p in THEME_PRESETS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_selecting_each_preset_submits_valid_colors_and_saves(self):
        from apps.core.theme_presets import THEME_PRESETS
        for preset in THEME_PRESETS:
            response = self.client.post(reverse("dashboard:settings-appearance"), {
                "primary_color": preset.primary, "accent_color": preset.accent,
                "secondary_color": preset.secondary, "background_color": preset.background,
            })
            self.assertRedirects(response, "/admin-portal/settings/?section=appearance")
            shop = ShopSettings.load()
            self.assertEqual(shop.primary_color, preset.primary.upper())
            self.assertEqual(shop.secondary_color, preset.secondary.upper())
            self.assertEqual(shop.accent_color, preset.accent.upper())
            self.assertEqual(shop.background_color, preset.background.upper())

    def test_selected_preset_recognized_after_saving(self):
        from apps.core.theme_presets import THEME_PRESETS
        preset = THEME_PRESETS[0]
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": preset.primary, "accent_color": preset.accent,
            "secondary_color": preset.secondary, "background_color": preset.background,
        })
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.context["selected_preset_key"], preset.key)

    def test_manual_custom_colors_not_recognized_as_any_preset(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#123456", "accent_color": "#654321",
            "secondary_color": "#ABCDEF", "background_color": "#FEDCBA",
        })
        response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.context["selected_preset_key"], "")


# ============================================================ PR3: VALIDATION & CONTRAST


class ThemeValidationContrastTests(SettingsViewsTestCase):
    def test_valid_hex_for_new_token_fields_accepted(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "secondary_color": "#111111", "background_color": "#EEEEEE",
            "surface_color": "#FFFFFF", "text_color": "#000000", "muted_text_color": "#555555",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")
        shop = ShopSettings.load()
        self.assertEqual(shop.secondary_color, "#111111")
        self.assertEqual(shop.background_color, "#EEEEEE")
        self.assertEqual(shop.text_color, "#000000")
        self.assertEqual(shop.muted_text_color, "#555555")

    def test_malformed_hex_for_new_token_field_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "text_color": "not-a-color",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#RRGGBB")
        shop = ShopSettings.load()
        self.assertNotEqual(shop.text_color, "not-a-color")

    def test_css_injection_in_new_token_field_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "text_color": "javascript:alert(1)",
        })
        self.assertEqual(response.status_code, 200)
        shop = ShopSettings.load()
        self.assertNotEqual(shop.text_color, "javascript:alert(1)")

    def test_contrast_failure_text_vs_background_is_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "text_color": "#FFFFFF", "background_color": "#FFFFFF", "surface_color": "#FFFFFF",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کنتراست")

    def test_contrast_failure_leaves_shop_record_unchanged(self):
        original = ShopSettings.load()
        original_text = original.text_color
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "text_color": "#FEFEFE", "background_color": "#FFFFFF", "surface_color": "#FFFFFF",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.text_color, original_text)

    def test_contrast_failure_muted_vs_surface_is_rejected(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "muted_text_color": "#F8F8F8", "surface_color": "#FFFFFF",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کنتراست")

    def test_good_contrast_combination_saves_successfully(self):
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#111111", "accent_color": "#FF4D77",
            "text_color": "#241C3A", "background_color": "#F7F5FC", "surface_color": "#FFFFFF",
            "muted_text_color": "#8B86A3",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")

    def test_omitted_new_fields_keep_previously_saved_values(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77", "secondary_color": "#222222",
        })
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#111111", "accent_color": "#FF4D77",
        })
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#111111")
        self.assertEqual(shop.secondary_color, "#222222")

    def test_reset_action_restores_all_theme_defaults(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#111111", "accent_color": "#222222", "secondary_color": "#333333",
            "background_color": "#444444", "surface_color": "#555555",
        })
        response = self.client.post(reverse("dashboard:settings-appearance"), {"action": "reset"})
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")
        shop = ShopSettings.load()
        self.assertEqual(shop.primary_color, "#6D28D9")
        self.assertEqual(shop.accent_color, "#FF4D77")
        self.assertEqual(shop.secondary_color, "#7C3AED")
        self.assertEqual(shop.background_color, "#F7F5FC")
        self.assertEqual(shop.surface_color, "#FFFFFF")

    def test_reset_does_not_touch_logo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image
        from django.test import override_settings
        import tempfile

        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            buf = BytesIO()
            Image.new("RGBA", (50, 50), (255, 0, 0)).save(buf, "PNG")
            logo = SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")
            self.client.post(reverse("dashboard:settings-appearance"), {
                "primary_color": "#6D28D9", "accent_color": "#FF4D77", "logo": logo,
            })
            self.assertTrue(ShopSettings.load().logo)
            self.client.post(reverse("dashboard:settings-appearance"), {"action": "reset"})
            self.assertTrue(ShopSettings.load().logo)

    def test_reset_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-appearance"), {"action": "reset"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)
# ============================================================ PR3: STOREFRONT TOKEN INJECTION


class StorefrontThemeTokenInjectionTests(SettingsViewsTestCase):
    def test_default_new_tokens_present_on_storefront(self):
        response = self.client.get(reverse("catalog:home"))
        for var in (
            "--brand-secondary:", "--brand-secondary-fg:", "--brand-background:", "--brand-surface:",
            "--brand-text:", "--brand-muted:", "--brand-primary-hover:", "--brand-border:",
        ):
            self.assertContains(response, var)

    def test_changed_secondary_and_background_appear_in_storefront(self):
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "secondary_color": "#123123", "background_color": "#ABCABC",
        })
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-secondary:#123123")
        self.assertContains(response, "--brand-background:#ABCABC")

    def test_invalid_stored_new_token_uses_default_on_storefront(self):
        ShopSettings.objects.filter(store__slug="akhlaghi").update(background_color="invalid", text_color="")
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "--brand-background:#F7F5FC")
        self.assertContains(response, "--brand-text:#241C3A")
        self.assertNotContains(response, "invalid")

    def test_status_colors_remain_fixed_regardless_of_custom_theme(self):
        """رنگ‌های وضعیتی (موفقیت/هشدار) هرگز به رنگ برند تبدیل نمی‌شوند."""
        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#00FF00", "accent_color": "#FFA500",
        })
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "core", "static", "css", "tokens.css"
        )
        with open(css_path) as f:
            css = f.read()
        # status colours are fixed literals — never derived from the merchant's brand variables…
        self.assertRegex(css, r"--green:\s*#[0-9a-fA-F]{6}\s*;")
        self.assertRegex(css, r"--amber:\s*#[0-9a-fA-F]{6}\s*;")
        # …and the success green is usable both as a fill with white text and as text on white (>= 4.5:1)
        from apps.core.color_utils import contrast_ratio
        green = re.search(r"--green:\s*(#[0-9a-fA-F]{6})", css).group(1)
        self.assertGreaterEqual(contrast_ratio(green, "#FFFFFF"), 4.5)

    def test_border_color_derived_from_text_and_surface(self):
        from apps.core.color_utils import mix_hex
        response = self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#6D28D9", "accent_color": "#FF4D77",
            "text_color": "#111111", "surface_color": "#FFFFFF", "muted_text_color": "#555555",
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=appearance")
        expected = mix_hex("#111111", "#FFFFFF", 0.12)
        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, f"--brand-border:{expected}")

    def _storefront_vars(self):
        html = self.client.get(reverse("catalog:home")).content.decode()
        style = re.search(r'<html[^>]*style="([^"]*)"', html).group(1)
        return dict(item.split(":", 1) for item in style.split(";") if item.startswith("--"))

    def test_unsafe_brand_colours_stay_raw_but_text_usage_variables_are_accessible(self):
        """Merchant identity is stored/injected untouched (--brand-accent), while the colour text is actually
        painted with (--brand-accent-text) is derived by WCAG luminance so a pale gold accent is not 2.3:1 text."""
        from apps.core.color_utils import contrast_ratio

        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#FFE066", "accent_color": "#D3A13B",
            "background_color": "#FFFFFF", "surface_color": "#FFFFFF",
            "text_color": "#241C3A", "muted_text_color": "#8B86A3",
        })
        css_vars = self._storefront_vars()
        self.assertEqual(css_vars["--brand-accent"].upper(), "#D3A13B")  # identity untouched
        self.assertEqual(css_vars["--brand-primary"].upper(), "#FFE066")
        self.assertNotEqual(css_vars["--brand-accent-text"].upper(), "#D3A13B")
        for token in ("--brand-accent-text", "--brand-primary-text", "--brand-muted", "--theme-price-text"):
            self.assertGreaterEqual(contrast_ratio(css_vars[token], "#FFFFFF"), 4.5, token)
        # a pale primary needs dark label text; the hover state carries its OWN foreground
        self.assertEqual(css_vars["--brand-primary-fg"].upper(), "#000000")
        self.assertGreaterEqual(contrast_ratio(css_vars["--brand-primary-hover-fg"], css_vars["--brand-primary-hover"]), 4.5)

    def test_dark_brand_colours_get_light_foregrounds(self):
        from apps.core.color_utils import contrast_ratio

        self.client.post(reverse("dashboard:settings-appearance"), {
            "primary_color": "#0A0A23", "accent_color": "#1E1B4B",
            "background_color": "#FFFFFF", "surface_color": "#FFFFFF", "text_color": "#241C3A", "muted_text_color": "#6B6B80",
        })
        css_vars = self._storefront_vars()
        self.assertEqual(css_vars["--brand-primary-fg"].upper(), "#FFFFFF")
        self.assertGreaterEqual(contrast_ratio(css_vars["--brand-primary-fg"], css_vars["--brand-primary"]), 4.5)
        self.assertGreaterEqual(contrast_ratio(css_vars["--brand-gradient-fg"], css_vars["--brand-primary"]), 4.5)


# ============================================================ PR3: QUERY PERFORMANCE


class SettingsPageQueryPerformanceTests(SettingsViewsTestCase):
    def test_appearance_page_query_count_bounded(self):
        self.client.get(reverse("dashboard:settings") + "?section=appearance")  # warm-up
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("dashboard:settings") + "?section=appearance")
        self.assertEqual(response.status_code, 200)
        # Keep this as a regression ceiling, not an exact implementation
        # count. The shared settings context now includes the full operational
        # integration/industry/SMS state used by every tab, while nav_badges
        # contributes the two intentional COUNT queries. 26 is the measured
        # warm-cache ceiling for the current shared-context contract.
        self.assertLessEqual(len(ctx), 26)
