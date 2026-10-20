"""Promotion window: a discount is valid only inside its optional
[discount_starts_at, discount_ends_at) window. One rule drives the card, price,
cart/checkout, listing filter, and the «پیشنهاد شگفت‌انگیز» countdown — and the
countdown deadline is a STORED instant, never "now + N hours" at render time."""

import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import pricing_service, promotion_service
from apps.catalog.services.product_card_service import build_product_card_data
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.storefront_builder.services import render_service
from apps.stores.models import Store

User = get_user_model()
EXPECTED_RE = re.compile(r'"expected_total":\s*"(\d+)"')


class PromotionBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-promo")
        self.cat = Category.objects.create(store=self.store, name="د", slug="cat-promo")
        self.now = timezone.now()

    def make(self, slug, *, discount=20, starts=None, ends=None, price=100000):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.cat, name=slug, slug=slug,
            sku=slug.upper(), price=Decimal(price), stock=5, discount_percent=discount,
            discount_starts_at=starts, discount_ends_at=ends,
        )


class WindowRuleTests(PromotionBase):
    def test_unscheduled_discount_is_always_active_as_before(self):
        p = self.make("plain")
        self.assertTrue(p.is_discount_active())
        self.assertEqual(p.final_price, Decimal("80000"))

    def test_inside_window_active_outside_inactive(self):
        live = self.make("live", starts=self.now - timedelta(hours=1), ends=self.now + timedelta(hours=1))
        future = self.make("future", starts=self.now + timedelta(hours=1))
        expired = self.make("expired", ends=self.now - timedelta(seconds=1))
        self.assertTrue(live.is_discount_active())
        self.assertFalse(future.is_discount_active())
        self.assertFalse(expired.is_discount_active())
        self.assertEqual(expired.final_price, Decimal("100000"))
        self.assertEqual(pricing_service.resolve_effective_price(expired), Decimal("100000"))
        self.assertEqual(pricing_service.resolve_effective_price(live), Decimal("80000"))

    def test_end_instant_is_exclusive(self):
        p = self.make("edge", ends=self.now)
        self.assertFalse(p.is_discount_active(now=self.now))
        self.assertTrue(p.is_discount_active(now=self.now - timedelta(seconds=1)))

    def test_card_does_not_advertise_an_expired_sale(self):
        expired = self.make("exp-card", ends=self.now - timedelta(minutes=1))
        data = build_product_card_data(expired)
        self.assertFalse(data.is_on_sale)
        self.assertEqual(data.discount_percent, 0)
        self.assertEqual(data.price, Decimal("100000"))
        self.assertIsNone(data.compare_at_price)

    def test_queryset_helper_matches_instance_rule(self):
        live = self.make("q-live", ends=self.now + timedelta(hours=2))
        self.make("q-exp", ends=self.now - timedelta(hours=2))
        self.make("q-fut", starts=self.now + timedelta(hours=2))
        self.assertEqual(
            list(promotion_service.with_active_discount(Product.objects.filter(store=self.store))),
            [live],
        )

    def test_listing_discounted_filter_excludes_expired(self):
        self.make("l-live")
        self.make("l-exp", ends=self.now - timedelta(minutes=5))
        response = self.client.get(reverse("catalog:product-list"), {"discounted": "1"})
        self.assertContains(response, "l-live")
        self.assertNotContains(response, "l-exp")


class AmazingOffersCountdownTests(PromotionBase):
    def section(self, **settings):
        return SimpleNamespace(settings={"item_limit": 4, "deadline_hours": 8, **settings})

    def test_deadline_is_the_stored_earliest_end_and_stable_across_renders(self):
        soon = self.now + timedelta(hours=3)
        self.make("a", ends=self.now + timedelta(hours=9))
        self.make("b", ends=soon)
        first = render_service._amazing_offers_context(self.store, self.section())
        second = render_service._amazing_offers_context(self.store, self.section())
        self.assertEqual(first["deadline"], soon.isoformat())
        self.assertEqual(first["deadline"], second["deadline"])

    def test_no_stored_end_means_no_timer_not_a_fake_eight_hours(self):
        self.make("c")
        context = render_service._amazing_offers_context(self.store, self.section())
        self.assertEqual([p.slug for p in context["products"]], ["c"])
        self.assertIsNone(context["deadline"])

    def test_deadline_hours_setting_is_never_consumed_at_render_time(self):
        self.make("d", ends=self.now + timedelta(hours=2))
        a = render_service._amazing_offers_context(self.store, self.section(deadline_hours=1))
        b = render_service._amazing_offers_context(self.store, self.section(deadline_hours=168))
        self.assertEqual(a["deadline"], b["deadline"])

    def test_expired_offer_leaves_the_section(self):
        self.make("e", ends=self.now - timedelta(seconds=1))
        context = render_service._amazing_offers_context(self.store, self.section())
        self.assertEqual(context["products"], [])
        self.assertIsNone(context["deadline"])


class CheckoutExpiryTests(PromotionBase):
    def setUp(self):
        super().setUp()
        shop = ShopSettings.load(store=self.store)
        shop.tax_percent = Decimal("0")
        shop.free_shipping_threshold = Decimal("999999999")
        shop.save()
        self.product = self.make("co", discount=25, ends=self.now + timedelta(hours=1))
        ShippingMethod.objects.create(store=self.store, name="پست", slug="post-promo", cost=Decimal("0"))
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-promo")
        user = User.objects.create_user(username="09127770002", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09127770002")
        self.client.login(username="09127770002", password="pass12345")
        self.payload = {
            "receiver_name": "علی", "phone": "09127770002", "province": "تهران", "city": "تهران",
            "postal_code": "1415873920", "full_address": "خیابان", "note": "",
        }

    def displayed_total(self):
        html = self.client.get(reverse("orders:checkout-step1")).content.decode()
        match = EXPECTED_RE.search(html)
        self.assertIsNotNone(match)
        return int(match.group(1))

    def test_offer_that_expires_after_cart_add_cannot_be_ordered_at_the_old_price(self):
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        shown = self.displayed_total()
        self.assertEqual(shown, 75000)
        Product.objects.filter(pk=self.product.pk).update(discount_ends_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(reverse("orders:checkout-pay"), dict(self.payload, expected_total=str(shown)))
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())
        self.assertNotIn("HX-Redirect", response.headers)
        self.assertEqual(self.displayed_total(), 100000)
