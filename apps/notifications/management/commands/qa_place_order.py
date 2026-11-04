
from django.core.management.base import BaseCommand, CommandError

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product
from apps.catalog.services.pricing_service import resolve_effective_price
from apps.customers.models import Address, Customer
from apps.notifications.models import NotificationOutbox
from apps.notifications.qa import require_qa
from apps.orders.models import PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store


class Command(BaseCommand):
    help = "QA only: place a cash-on-delivery order through the real order service (scenario L) and list the notifications it queued."

    def add_arguments(self, parser):
        parser.add_argument("--store", default="qa-bike")

    def handle(self, *args, **o):
        require_qa()
        store = Store.objects.filter(slug=o["store"]).first()
        customer = Customer.objects.filter(phone="09125550001").first()
        product = Product.objects.filter(store=store, slug="qa-bike-1").first() if store else None
        if not (store and customer and product):
            raise CommandError("run seed_qa_notifications first")
        before = set(NotificationOutbox.objects.values_list("pk", flat=True))
        address = Address.objects.create(customer=customer, receiver_name="مشتری QA", phone=customer.phone, province="تهران",
                                         city="تهران", postal_code="1111111111", full_address="خیابان QA")
        cart = Cart.objects.create(customer=customer)
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=resolve_effective_price(product, None))
        order = create_order_from_cart(
            cart, customer=customer, vendor=product.vendor, address=address,
            shipping_method=ShippingMethod.objects.get(store=store, slug="qa-post"),
            payment_gateway=PaymentGateway.objects.get(store=store, slug="qa-cod"), coupon=None, store=store)
        self.stdout.write(f"order {order.code} grand_total={order.grand_total} payment_status={order.payment_status}")
        for n in NotificationOutbox.objects.exclude(pk__in=before).order_by("pk"):
            self.stdout.write(f"  queued: {n.event_key} [{n.channel}] -> {n.status}")
