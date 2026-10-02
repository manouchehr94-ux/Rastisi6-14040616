"""تاریخ تولدِ اختیاری در تسویه‌حساب و حسابِ کاربری + نمایش «کدهای تخفیف من»."""

import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Coupon
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()
CODE = "553311"


class CheckoutBirthDateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-bd")
        category = Category.objects.create(store=self.store, name="د", slug="cat-bd")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالا", slug="p-bd", sku="BD1",
            price=Decimal("200000"), stock=10,
        )
        ShippingMethod.objects.create(store=self.store, name="پست", slug="post-bd", cost=45_000)
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-bd")
        self.payload = {
            "receiver_name": "علی رضایی", "phone": "09123456789", "province": "تهران", "city": "تهران",
            "postal_code": "1415873920", "full_address": "خیابان ولیعصر", "note": "",
        }
        import apps.sms.services.otp_service as otp_service

        original = otp_service._generate_code
        otp_service._generate_code = lambda: CODE
        self.addCleanup(setattr, otp_service, "_generate_code", original)
        patcher = patch("apps.sms.services.otp_service.send_event_sms")
        mock = patcher.start()
        mock.return_value.status = "sent"
        mock.return_value.error_message = ""
        self.addCleanup(patcher.stop)

    def _login(self, birth_date=None):
        user = User.objects.create_user(username="09123456789", password="pass12345")
        customer = Customer.objects.create(user=user, full_name="علی", phone="09123456789", birth_date=birth_date)
        self.client.login(username="09123456789", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        return customer

    def test_field_is_optional_and_order_succeeds_without_it(self):
        customer = self._login()
        r = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertIn("HX-Redirect", r.headers)
        customer.refresh_from_db()
        self.assertIsNone(customer.birth_date)

    def test_valid_jalali_birth_date_saved_on_authenticated_checkout(self):
        customer = self._login()
        r = self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date="۱۳۷۰/۰۵/۲۳"))
        self.assertIn("HX-Redirect", r.headers)
        customer.refresh_from_db()
        self.assertEqual(customer.birth_date, dt.date(1991, 8, 14))
        self.assertEqual(customer.birth_month_day, 523)

    def test_empty_field_never_overwrites_existing_birth_date(self):
        customer = self._login(birth_date=dt.date(1991, 8, 14))
        self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date=""))
        customer.refresh_from_db()
        self.assertEqual(customer.birth_date, dt.date(1991, 8, 14))

    def test_existing_birth_date_is_shown_in_jalali_and_can_be_updated(self):
        customer = self._login(birth_date=dt.date(1991, 8, 14))
        r = self.client.get(reverse("orders:checkout-step1"))
        self.assertContains(r, "۱۳۷۰/۰۵/۲۳")
        self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date="1371/01/01"))
        customer.refresh_from_db()
        self.assertEqual(customer.birth_date, dt.date(1992, 3, 21))

    def test_invalid_birth_date_blocks_order_with_field_error(self):
        customer = self._login(birth_date=dt.date(1991, 8, 14))
        for bad in ("1404/12/30", "abc", "1500/01/01", "1371/13/01"):
            r = self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date=bad))
            self.assertNotIn("HX-Redirect", r.headers, bad)
            self.assertContains(r, "coup-err")
        self.assertEqual(Order.objects.count(), 0)
        customer.refresh_from_db()
        self.assertEqual(customer.birth_date, dt.date(1991, 8, 14))

    def test_new_guest_account_gets_birth_date(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        r = self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date="1370/05/23"))
        self.assertIn("HX-Redirect", r.headers)
        self.assertEqual(Customer.objects.get(phone="09123456789").birth_date, dt.date(1991, 8, 14))

    def test_birth_date_for_existing_account_is_applied_only_after_otp_verification(self):
        owner = User.objects.create_user(username="09123456789", password="pass12345")
        customer = Customer.objects.create(user=owner, full_name="مالک", phone="09123456789")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.client.post(reverse("orders:checkout-pay"), dict(self.payload, birth_date="1370/05/23"))
        customer.refresh_from_db()
        self.assertIsNone(customer.birth_date)  # مهمانِ تأییدنشده نمی‌تواند تولدِ دیگری را تغییر دهد
        self.client.post(reverse("orders:checkout-otp-verify"), {"code": CODE})
        customer.refresh_from_db()
        self.assertEqual(customer.birth_date, dt.date(1991, 8, 14))


class AccountProfileTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09125550001", password="pass12345")
        self.customer = Customer.objects.create(
            user=user, full_name="مشتری", phone="09125550001", birth_date=dt.date(1991, 8, 14),
        )
        self.client.login(username="09125550001", password="pass12345")

    def test_account_shows_saved_birth_date_in_jalali(self):
        r = self.client.get(reverse("customers:account"))
        self.assertContains(r, "۱۳۷۰/۰۵/۲۳")

    def test_update_birth_date_and_preferences(self):
        r = self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "مشتری", "email": "", "city": "", "birth_date": "1372/02/02", "prefs_submitted": "1",
            "accepts_promotional_email": "on",
        })
        self.assertEqual(r.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.birth_date, dt.date(1993, 4, 22))
        self.assertFalse(self.customer.accepts_promotional_sms)
        self.assertTrue(self.customer.accepts_promotional_email)

    def test_blank_birth_date_keeps_value_and_missing_prefs_marker_keeps_consent(self):
        self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "مشتری", "email": "", "city": "", "birth_date": "",
        })
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.birth_date, dt.date(1991, 8, 14))
        self.assertTrue(self.customer.accepts_promotional_sms)

    def test_invalid_birth_date_rejected(self):
        r = self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "مشتری", "email": "", "city": "", "birth_date": "1404/12/30",
        })
        self.assertContains(r, "coup-err")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.birth_date, dt.date(1991, 8, 14))

    def test_email_change_queues_security_notification(self):
        from apps.notifications.models import NotificationOutbox

        self.client.post(reverse("customers:account-profile-update"), {
            "full_name": "مشتری", "email": "new@example.com", "city": "",
        })
        row = NotificationOutbox.objects.get(event_key="account.sensitive_changed", channel="email")
        self.assertEqual(row.recipient_email, "new@example.com")
        self.assertTrue(row.is_security)

    def test_my_coupons_tab_shows_only_own_coupons(self):
        other = Customer.objects.create(
            user=User.objects.create_user(username="09125550002", password="x12345678"), full_name="دیگری", phone="09125550002",
        )
        Coupon.objects.create(store=self.store, code="MINE-1", type="percent", value=10, customer=self.customer)
        Coupon.objects.create(store=self.store, code="THEIRS-1", type="percent", value=10, customer=other)
        Coupon.objects.create(store=self.store, code="PUBLIC-1", type="percent", value=10)
        r = self.client.get(reverse("customers:account"))
        self.assertContains(r, "MINE-1")
        self.assertNotContains(r, "THEIRS-1")
        self.assertNotContains(r, "PUBLIC-1")
