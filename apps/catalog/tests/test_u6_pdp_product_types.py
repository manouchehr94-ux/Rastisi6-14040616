"""U6 — Universal PDP + Product Types.

Audit finding: `build_product_detail_context` (identity, media gallery,
variant/variant-image switching, price, stock, description/specs, reviews,
related products, product videos, gift wrap) was already comprehensive and
shared between the public PDP and the dashboard preview — no rework needed.

Real bug found and fixed this phase: the PDP purchase area
(`product_main.html`) unconditionally claimed physical shipping
("in stock — ready to ship", "fast, insured shipping") for *every* product,
regardless of `Product.requires_shipping` — a real "fabricated shipping
promise" for any store selling a digital/service item. Both facts are now
gated on the existing, real `requires_shipping` field (no new field, no
fabricated distinction between "digital" and "service" — the repository has
no data that actually distinguishes those two today, see the ledger's Known
limitations for why a `fulfillment_type` split was deliberately not
invented this phase).

Also audited (not fixed — documented as a real, deeper limitation): cart/
order submission still hard-requires a real `ShippingMethod` even for an
all-non-shippable cart, because `Order.shipping_method` is a mandatory
(non-nullable, `on_delete=PROTECT`) ForeignKey. `shipping_service
.cart_requires_shipping`/`cart_shippable_weight_grams` already exist and are
already correctly tested in isolation, but are not wired into
`checkout_service.submit_order`'s validation — fixing that safely needs a
schema migration touching every `order.shipping_method` consumer
(invoices/dashboard/notifications), out of scope for this phase.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.orders.models import ShippingMethod
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class PdpShippingClaimTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده یو۶", slug="u6-vendor")
        self.category = Category.objects.create(store=self.store, name="دسته یو۶", slug="u6-cat")

    def _make_product(self, *, slug, requires_shipping):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name=f"کالای یو۶ {slug}", slug=slug, sku=f"U6-SKU-{slug}",
            price=Decimal("200000"), stock=5, requires_shipping=requires_shipping,
        )

    def test_physical_product_still_claims_shipping_unchanged(self):
        """No regression: the default, physical case must render exactly
        the same copy as before this phase."""
        product = self._make_product(slug="physical", requires_shipping=True)
        ShippingMethod.objects.create(store=self.store, name="پست", slug="u6-post", is_active=True)   # FOLLOWUP-10: claimed only with a real method
        response = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertContains(response, "موجود در انبار — آماده ارسال")
        self.assertContains(response, "ارسال سفارش")
        self.assertNotContains(response, "ارسال سریع و بیمه‌شده")        # the speed/insurance promise is gone

    def test_physical_product_without_an_active_shipping_method_claims_nothing(self):
        product = self._make_product(slug="physical-no-method", requires_shipping=True)
        response = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertNotContains(response, "ارسال سفارش")
        self.assertNotContains(response, "ارسال سریع")

    def test_non_shippable_product_makes_no_shipping_claim(self):
        product = self._make_product(slug="non-shippable", requires_shipping=False)
        response = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertNotContains(response, "موجود در انبار — آماده ارسال")
        self.assertNotContains(response, "ارسال سفارش")

    def test_non_shippable_product_shows_honest_alternative_copy(self):
        """Not just removed — a real, honest fact about this exact product,
        not a blank gap in the trust-badge row."""
        product = self._make_product(slug="non-shippable-copy", requires_shipping=False)
        response = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertContains(response, "موجود — قابل خرید")
        self.assertContains(response, "بدون نیاز به ارسال فیزیکی")

    def test_out_of_stock_copy_unaffected_by_shipping_flag(self):
        """The "ناموجود" (out of stock) case is orthogonal to shipping —
        must not be touched by this change either way."""
        product = self._make_product(slug="oos-digital", requires_shipping=False)
        product.stock = 0
        product.save(update_fields=["stock"])
        response = self.client.get(reverse("catalog:product-detail", args=[product.slug]))
        self.assertContains(response, "ناموجود")
