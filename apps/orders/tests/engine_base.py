"""پایه‌ی مشترکِ تست‌های موتورِ تخفیف/کمپین/کادوپیچی (Store ``akhlaghi`` seed‌شده)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Brand, Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


class EngineBase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="v-eng")
        self.cat_bag = Category.objects.create(store=self.store, name="کیف", slug="bag-eng")
        self.cat_shoe = Category.objects.create(store=self.store, name="کفش", slug="shoe-eng")
        self.nike = Brand.objects.create(store=self.store, name="Nike", slug="nike-eng")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-eng", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-eng")
        self.customer = self._customer("u1", "09120000001")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="ا", phone="09120000001", province="فارس", city="شیراز",
            postal_code="1111111111", full_address="خیابان",
        )
        shop = ShopSettings.load(store=self.store)
        shop.free_shipping_threshold = Decimal("999999999")
        shop.save()

    def _customer(self, username, phone):
        user = User.objects.create_user(username=username, password="x12345678")
        return Customer.objects.create(user=user, full_name=username, phone=phone)

    def _product(self, slug, price, category=None, brand=None, discount=0, **kw):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=category or self.cat_bag, brand=brand, name=slug,
            slug=slug, sku=slug.upper()[:40], price=Decimal(price), discount_percent=discount, stock=100, **kw,
        )

    def _cart(self, customer=None, lines=(), **line_kw):
        cart = Cart.objects.create(customer=customer or self.customer)
        for product, qty in lines:
            CartItem.objects.create(cart=cart, product=product, quantity=qty, unit_price=product.final_price, **line_kw)
        return cart

    def _coupon(self, code="C1", **kw):
        kw.setdefault("type", Coupon.Type.PERCENT)
        kw.setdefault("value", 10)
        return Coupon.objects.create(store=self.store, code=code, **kw)

    def _order(self, cart, coupon=None, customer=None):
        return create_order_from_cart(
            cart, customer=customer or self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, coupon=coupon, store=self.store,
        )

    def _totals(self, cart, coupon, customer=None):
        return cart_totals(cart, store=self.store, coupon=coupon, customer=customer or self.customer,
                           payment_gateway=self.gateway)
