import datetime as dt, json
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from apps.catalog.models import Brand, Category, Product, ProductVariant, Vendor
from apps.core.jalali_utils import jalali_to_gregorian
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store, StoreMembership
U = get_user_model()
store = Store.objects.get(slug="akhlaghi")
store.admin_subdomain = "e2e"; store.save(update_fields=["admin_subdomain"])
shop = ShopSettings.load(store=store)
shop.gift_wrap_available = True; shop.gift_wrap_price = Decimal("20000"); shop.tax_percent = Decimal("0"); shop.free_shipping_threshold = Decimal("99999999999"); shop.save()
owner = U.objects.create_user(username="09120000000", password="pass12345", is_staff=True)
StoreMembership.objects.create(store=store, user=owner, role="owner", status="active", accepted_at=timezone.now())
vendor = Vendor.objects.create(store=store, name="v", slug="v-e2e")
bag = Category.objects.create(store=store, name="کیف", slug="bag-e2e"); shoe = Category.objects.create(store=store, name="کفش", slug="shoe-e2e")
nike = Brand.objects.create(store=store, name="Nike", slug="nike-e2e"); Brand.objects.create(store=store, name="Adidas", slug="adidas-e2e")
olive = Product.objects.create(store=store, vendor=vendor, category=bag, name="کیف زیتونی", slug="olive-bag", sku="OB1", price=Decimal("6000000"), stock=50)
ProductVariant.objects.create(product=olive, store=store, attribute="رنگ", value="زیتونی", value_hex="#808000", stock=50)
nshoe = Product.objects.create(store=store, vendor=vendor, category=shoe, brand=nike, name="کفش نایک", slug="nike-shoe", sku="NS1", price=Decimal("12000000"), stock=50)
cheap = Product.objects.create(store=store, vendor=vendor, category=bag, name="کیف ارزان", slug="cheap-bag", sku="CB1", price=Decimal("300000"), stock=50)
ship = ShippingMethod.objects.create(store=store, name="پست", slug="post-e2e", cost=Decimal("0")); gw = PaymentGateway.objects.create(store=store, name="g", slug="gw-e2e")
tz = ZoneInfo("Asia/Tehran")
def mk(name, phone, product, variant, when_j, city, qty=1, email="", sms=True):
    u = U.objects.create_user(username=phone, password="x12345678")
    c = Customer.objects.create(user=u, full_name=name, phone=phone, email=email, accepts_promotional_sms=sms)
    a = Address.objects.create(customer=c, receiver_name=name, phone=phone, province="فارس", city=city, postal_code="1111111111", full_address="x")
    cart = Cart.objects.create(customer=c)
    CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=qty, unit_price=product.final_price)
    o = create_order_from_cart(cart, customer=c, vendor=vendor, address=a, shipping_method=ship, payment_gateway=gw, store=store)
    g = jalali_to_gregorian(*when_j)
    Order.objects.filter(pk=o.pk).update(created_at=dt.datetime(g.year, g.month, g.day, 12, tzinfo=tz), status="processing", payment_status="paid")
    return c
ov = olive.variants.first()
mk("برنده زیتونی", "09121110001", olive, ov, (1405, 7, 10), "شیراز", qty=2, email="w1@example.com")
mk("برنده نایک", "09121110002", nshoe, None, (1405, 8, 30), "شیراز")
mk("تهرانی", "09121110003", nshoe, None, (1405, 7, 12), "تهران")
mk("کم‌خرید", "09121110004", cheap, None, (1405, 7, 12), "شیراز")
mk("خارج از بازه", "09121110005", nshoe, None, (1405, 9, 1), "شیراز")
c = Client(); assert c.login(username="09120000000", password="pass12345")
json.dump({"sessionid": c.cookies["sessionid"].value, "bag": bag.pk, "shoe": shoe.pk, "nike": nike.pk}, open("/tmp/e2e_state.json", "w"))
print("seeded")
