"""ابزارِ مشترکِ تست‌هایِ کمپین/مناسبت: ساختِ فروشگاه، کالا (با رنگ/برند)،
مشتری و سفارشِ تاریخی."""

import datetime as dt
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Brand, Category, Product, ProductVariant, Vendor
from apps.core.jalali_utils import jalali_to_gregorian
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()
TEHRAN = ZoneInfo("Asia/Tehran")
_seq = count(1)


def jdt(year, month, day, hour=12, minute=0, second=0):
    """لحظه‌ای در منطقه‌ی تهران از تاریخِ شمسی."""
    g = jalali_to_gregorian(year, month, day)
    return dt.datetime(g.year, g.month, g.day, hour, minute, second, tzinfo=TEHRAN)


class EngagementBase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="v-eng2")
        self.cat_bag = Category.objects.create(store=self.store, name="کیف", slug="bag-e2")
        self.cat_shoe = Category.objects.create(store=self.store, name="کفش", slug="shoe-e2")
        self.cat_other = Category.objects.create(store=self.store, name="لباس", slug="cloth-e2")
        self.nike = Brand.objects.create(store=self.store, name="Nike", slug="nike-e2")
        self.adidas = Brand.objects.create(store=self.store, name="Adidas", slug="adidas-e2")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-e2", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-e2")
        from apps.core.models import ShopSettings

        shop = ShopSettings.load(store=self.store)
        shop.free_shipping_threshold = Decimal("99999999999")
        shop.tax_percent = Decimal("0")
        shop.save()

    # --- ساخت داده --------------------------------------------------------
    def customer(self, name="مشتری", *, email="", birth_date=None, sms=True, mail=True, city=""):
        n = next(_seq)
        user = User.objects.create_user(username=f"c{n}", password="x12345678")
        return Customer.objects.create(
            user=user, full_name=name, phone=f"0912{n:07d}", email=email, birth_date=birth_date,
            accepts_promotional_sms=sms, accepts_promotional_email=mail, city=city,
        )

    def product(self, name, price, *, category=None, brand=None, color=None, size=None, store=None):
        n = next(_seq)
        store = store or self.store
        vendor = self.vendor if store == self.store else Vendor.objects.create(store=store, name="v", slug=f"v-{n}")
        product = Product.objects.create(
            store=store, vendor=vendor, category=category or self.cat_other, brand=brand, name=name,
            slug=f"p{n}", sku=f"SKU{n}", price=Decimal(price), stock=1000,
        )
        variants = []
        if color:
            variants.append(ProductVariant.objects.create(
                product=product, store=store, attribute="رنگ", value=color[0], value_hex=color[1], stock=1000,
            ))
        elif size:
            variants.append(ProductVariant.objects.create(
                product=product, store=store, attribute="سایز", value=size, stock=1000,
            ))
        product._variant = variants[0] if variants else None
        return product

    def order(self, customer, lines, *, when, city="شیراز", province="فارس", status="processing", payment="paid",
              store=None, coupon=None, gateway=None):
        """سفارشِ تاریخی با ``created_at`` دلخواه. ``lines``: ``[(product, qty)]``."""
        store = store or self.store
        address = Address.objects.create(
            customer=customer, receiver_name="گ", phone=customer.phone, province=province, city=city,
            postal_code="1111111111", full_address="x",
        )
        cart = Cart.objects.create(customer=customer)
        for product, qty in lines:
            variant = getattr(product, "_variant", None)
            from apps.catalog.services.pricing_service import resolve_effective_price

            CartItem.objects.create(
                cart=cart, product=product, variant=variant, quantity=qty,
                unit_price=resolve_effective_price(product, variant),
            )
        shipping = self.shipping if store == self.store else ShippingMethod.objects.create(
            store=store, name="پست", slug=f"post-{next(_seq)}", cost=Decimal("0"))
        gw = gateway or (self.gateway if store == self.store else PaymentGateway.objects.create(
            store=store, name="g", slug=f"gw-{next(_seq)}"))
        vendor = lines[0][0].vendor
        order = create_order_from_cart(
            cart, customer=customer, vendor=vendor, address=address, shipping_method=shipping,
            payment_gateway=gw, coupon=coupon, store=store,
        )
        Order.objects.filter(pk=order.pk).update(created_at=when, status=status, payment_status=payment)
        order.refresh_from_db()
        return order
