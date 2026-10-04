from decimal import Decimal

from django.test import Client
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.cart.services.cart_service import add_item_to_cart
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.dashboard.tests.test_coupon_views import HOST, CouponViewsTestCase
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.customers.models import Address, Customer
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store, StoreMembership
from django.contrib.auth import get_user_model

User = get_user_model()


class GiftWrapStorefrontViewTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="v-gwv2")
        self.category = Category.objects.create(store=self.store, name="ک", slug="c-gwv2")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="هدیه", slug="gift-gwv2",
            sku="GWV2", price=Decimal("100000"), stock=10,
        )
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("15000")
        shop.gift_wrap_title = "بسته‌بندی هدیه"
        shop.gift_wrap_description = "کاغذ کادو و روبان"
        shop.save()
        self.shop_client = Client()  # default host → Store akhlaghi
        self.shop_client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.item = CartItem.objects.get()

    def test_toggle_on_with_message_then_off(self):
        url = reverse("cart:item-gift-wrap", args=[self.item.pk])
        r = self.shop_client.post(url, {"gift_wrap": "1", "gift_message": "  تولدت مبارک  "})
        self.assertEqual(r.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.gift_wrap_selected)
        self.assertEqual(self.item.gift_wrap_unit_price, Decimal("15000"))
        self.assertEqual(self.item.gift_message, "تولدت مبارک")
        self.assertContains(r, "بسته‌بندی هدیه")
        self.assertContains(r, 'name="gift_message"')
        r = self.shop_client.post(url, {})
        self.item.refresh_from_db()
        self.assertFalse(self.item.gift_wrap_selected)
        self.assertEqual(self.item.gift_message, "")
        self.assertEqual(self.item.gift_wrap_unit_price, 0)

    def test_client_cannot_force_price(self):
        url = reverse("cart:item-gift-wrap", args=[self.item.pk])
        self.shop_client.post(url, {"gift_wrap": "1", "gift_wrap_unit_price": "1"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.gift_wrap_unit_price, Decimal("15000"))

    def test_disabled_product_rejected(self):
        self.product.gift_wrap_enabled = False
        self.product.save()
        r = self.shop_client.post(reverse("cart:item-gift-wrap", args=[self.item.pk]), {"gift_wrap": "1"})
        self.assertIn("کادوپیچی برای این کالا در دسترس نیست", r["HX-Trigger"].encode().decode("unicode_escape") if "\\u" in r["HX-Trigger"] else r["HX-Trigger"])
        self.item.refresh_from_db()
        self.assertFalse(self.item.gift_wrap_selected)

    def test_other_cart_item_is_404(self):
        other = Client()
        other.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        r = other.post(reverse("cart:item-gift-wrap", args=[self.item.pk]), {"gift_wrap": "1"})
        self.assertEqual(r.status_code, 404)

    def test_cart_page_shows_option_and_total(self):
        self.shop_client.post(reverse("cart:item-gift-wrap", args=[self.item.pk]), {"gift_wrap": "1"})
        r = self.shop_client.get(reverse("cart:detail"))
        self.assertContains(r, "بسته‌بندی هدیه")
        self.assertContains(r, "کاغذ کادو و روبان")
        self.assertEqual(r.context["totals"]["gift_wrap_total"], Decimal("15000"))

    def test_pdp_shows_product_aware_option(self):
        r = self.shop_client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertContains(r, 'name="gift_wrap"')
        self.product.gift_wrap_enabled = False
        self.product.save()
        r = self.shop_client.get(reverse("catalog:product-detail", args=[self.product.slug]))
        self.assertNotContains(r, 'name="gift_wrap"')


class GiftWrapAdminViewTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        vendor = Vendor.objects.create(store=self.store, name="ف", slug="v-gwa")
        cat = Category.objects.create(store=self.store, name="ک", slug="c-gwa")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=cat, name="کالای کادویی", slug="p-gwa", sku="GWA1",
            price=Decimal("100000"), stock=10,
        )
        self.vendor = vendor

    def test_list_and_update(self):
        r = self.client.get(reverse("dashboard:gift-wrap-products"))
        self.assertContains(r, "کالای کادویی")
        r = self.client.post(
            reverse("dashboard:gift-wrap-product-update", args=[self.product.pk]),
            {"gift_wrap_price": "25000"},  # checkbox absent → disabled
        )
        self.assertEqual(r.status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.gift_wrap_enabled)
        self.assertEqual(self.product.gift_wrap_price, Decimal("25000"))
        r = self.client.get(reverse("dashboard:gift-wrap-products") + "?filter=disabled")
        self.assertContains(r, "کالای کادویی")

    def test_invalid_price_rejected(self):
        for bad in ("abc", "-5", "10.5"):
            self.client.post(
                reverse("dashboard:gift-wrap-product-update", args=[self.product.pk]),
                {"gift_wrap_enabled": "on", "gift_wrap_price": bad},
            )
            self.product.refresh_from_db()
            self.assertIsNone(self.product.gift_wrap_price, bad)

    def test_other_store_product_404(self):
        other = Store.objects.create(name="دیگر", slug="gwa-other", status=Store.Status.ACTIVE)
        v = Vendor.objects.create(store=other, name="x", slug="v-gwa-o")
        c = Category.objects.create(store=other, name="x", slug="c-gwa-o")
        p = Product.objects.create(store=other, vendor=v, category=c, name="x", slug="p-gwa-o", sku="GWAO", price=1, stock=1)
        r = self.client.post(reverse("dashboard:gift-wrap-product-update", args=[p.pk]), {"gift_wrap_enabled": "on"})
        self.assertEqual(r.status_code, 404)

    def test_analyst_cannot_update(self):
        self._login_as(StoreMembership.Role.ANALYST, "201")
        r = self.client.post(reverse("dashboard:gift-wrap-product-update", args=[self.product.pk]), {"gift_wrap_enabled": "on"})
        self.assertIn(r.status_code, (302, 403, 404))
        self.product.refresh_from_db()
        self.assertTrue(self.product.gift_wrap_enabled)  # default unchanged (and price stays None)
        self.assertIsNone(self.product.gift_wrap_price)

    def test_settings_form_saves_new_fields(self):
        r = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_available": "on", "gift_wrap_price": "12000", "gift_wrap_pricing_scope": "per_order",
            "gift_wrap_title": "کادو", "gift_wrap_description": "توضیح", "gift_wrap_message_enabled": "on",
        })
        self.assertEqual(r.status_code, 302)
        shop = ShopSettings.load(store=self.store)
        self.assertTrue(shop.gift_wrap_available)
        self.assertEqual(shop.gift_wrap_pricing_scope, "per_order")
        self.assertEqual(shop.gift_wrap_title, "کادو")
        r = self.client.post(reverse("dashboard:settings-gift-wrap"), {
            "gift_wrap_price": "1", "gift_wrap_pricing_scope": "bogus",
        })
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        shop.refresh_from_db()
        self.assertEqual(shop.gift_wrap_pricing_scope, "per_order")

    def test_admin_order_detail_shows_fulfilment_instructions_and_invoice_lines(self):
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("15000")
        shop.save()
        user = User.objects.create_user(username="cust-gwa", password="x12345678")
        customer = Customer.objects.create(user=user, full_name="مشتری", phone="09125550000")
        address = Address.objects.create(
            customer=customer, receiver_name="م", phone="09125550000", province="فارس", city="شیراز",
            postal_code="1111111111", full_address="x",
        )
        shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-gwa", cost=Decimal("0"))
        gateway = PaymentGateway.objects.create(store=self.store, name="g", slug="g-gwa")
        cart = Cart.objects.create(customer=customer)
        add_item_to_cart(cart, self.product, None, 2, gift_wrap_requested=True, gift_message="با عشق")
        order = create_order_from_cart(
            cart, customer=customer, vendor=self.vendor, address=address, shipping_method=shipping,
            payment_gateway=gateway, store=self.store,
        )
        self.assertEqual(order.gift_wrap_total, Decimal("30000"))
        r = self.client.get(reverse("dashboard:order-detail", args=[order.code]))
        self.assertContains(r, "دستورالعمل کادوپیچی")
        self.assertContains(r, "با عشق")
        r = self.client.get(reverse("dashboard:invoice-detail", args=[order.code]))
        self.assertContains(r, "هزینه کادوپیچی")
        self.assertContains(r, "با عشق")
