"""Currency truth: prices are stored, shown and charged in TOMAN ("IRT" is a platform convention, not an ISO code). Everything that leaves
for Google / Meta (schema.org, Open Graph) is ISO 4217 «IRR» with the amount × 10 — and nothing stored is ever changed."""

import json
import re
from decimal import Decimal

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Category, PriceMode, Product, ProductVariant, Vendor
from apps.core import currency
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

HOST = "cur-a.example.com"


class CurrencyUnitTests(SimpleTestCase):
    def test_the_conversion_matches_the_factor_the_payment_gateways_charge_with(self):
        from apps.billing.providers.zibal import TOMAN_TO_RIAL as billing_factor
        from apps.orders.gateways.zibal import TOMAN_TO_RIAL as gateway_factor
        self.assertEqual(currency.TOMAN_TO_RIAL, gateway_factor)
        self.assertEqual(currency.TOMAN_TO_RIAL, billing_factor)

    def test_values(self):
        for toman, rial in ((250000, 2500000), (1, 10), (0, 0), (Decimal("999000"), 9990000), ("1500", 15000)):
            self.assertEqual(currency.toman_to_rial(toman), rial)

    def test_the_stored_convention_is_not_an_iso_code_and_the_output_code_is(self):
        from apps.orders.models import ShippingRateRule
        self.assertEqual(currency.STORAGE_CURRENCY, "IRT")
        self.assertEqual(ShippingRateRule.CURRENCY, currency.STORAGE_CURRENCY)  # the platform's single stored unit is Toman
        self.assertEqual(currency.ISO_CURRENCY, "IRR")
        self.assertRegex(currency.ISO_CURRENCY, r"^[A-Z]{3}$")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class StructuredPriceTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(store=self.store, hostname=HOST, is_primary=True,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self.vendor = Vendor.objects.create(store=self.store, name="V", slug="cur-v")
        self.category = Category.objects.create(store=self.store, name="C", slug="cur-c", is_active=True)

    def product(self, slug, price, **kw):
        return Product.objects.create(store=self.store, vendor=self.vendor, category=self.category, name=f"P {slug}", slug=slug,
                                      sku=f"CUR-{slug}", price=Decimal(price), stock=kw.pop("stock", 3), status=Product.Status.ACTIVE, **kw)

    def html(self, slug):
        return self.client.get(f"/products/{slug}/", HTTP_HOST=HOST).content.decode()

    def offers(self, html):
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        node = next(n for b in blocks for n in b["@graph"] if n["@type"] == "Product")
        return node.get("offers")

    def test_simple_product_is_iso_rials_and_the_stored_price_is_untouched(self):
        p = self.product("simple", "250000")
        html = self.html("simple")
        offer = self.offers(html)
        self.assertEqual((offer["@type"], offer["priceCurrency"], offer["price"]), ("Offer", "IRR", "2500000"))
        self.assertIn('<meta property="product:price:amount" content="2500000">', html)
        self.assertIn('<meta property="product:price:currency" content="IRR">', html)
        self.assertNotIn('content="IRT"', html)
        p.refresh_from_db()
        self.assertEqual(p.price, Decimal("250000"))                              # nothing stored changed

    def test_the_visible_price_stays_in_toman(self):
        self.product("shown", "250000")
        html = self.html("shown")
        self.assertIn("تومان", html)

    def test_an_active_discount_is_applied_exactly_like_the_cart_does(self):
        p = self.product("disc", "1000000", discount_percent=10)
        offer = self.offers(self.html("disc"))
        self.assertEqual(offer["price"], "9000000")                                # 900 000 Toman → 9 000 000 Rial
        from apps.catalog.services.pricing_service import resolve_effective_price
        self.assertEqual(Decimal(offer["price"]), resolve_effective_price(p) * 10)

    def test_a_price_inquiry_product_has_no_price_anywhere(self):
        self.product("ask", "100000", price_mode_override=PriceMode.INQUIRY)
        html = self.html("ask")
        self.assertIsNone(self.offers(html))
        self.assertNotIn("product:price", html)

    def test_variable_product_with_different_variant_prices_is_an_aggregate_offer(self):
        p = self.product("var", "300000", product_type=Product.ProductType.VARIABLE)
        ProductVariant.objects.create(product=p, store=self.store, attribute="سایز", value="S", sku="V-S", stock=2, price=Decimal("250000"))
        ProductVariant.objects.create(product=p, store=self.store, attribute="سایز", value="L", sku="V-L", stock=0, price=Decimal("400000"))
        ProductVariant.objects.create(product=p, store=self.store, attribute="سایز", value="XL", sku="V-XL", stock=5, price=Decimal("500000"), is_active=False)
        html = self.html("var")
        offer = self.offers(html)
        self.assertEqual((offer["@type"], offer["priceCurrency"]), ("AggregateOffer", "IRR"))
        self.assertEqual((offer["lowPrice"], offer["highPrice"], offer["offerCount"]), ("2500000", "4000000", 2))   # inactive variant ignored
        self.assertEqual(offer["availability"], "https://schema.org/InStock")      # at least one active variant in stock
        self.assertIn('<meta property="product:price:amount" content="2500000">', html)   # lowest price

    def test_variable_product_whose_variants_share_one_price_is_a_plain_offer(self):
        p = self.product("same", "300000", product_type=Product.ProductType.VARIABLE)
        for sku in ("A", "B"):
            ProductVariant.objects.create(product=p, store=self.store, attribute="رنگ", value=sku, sku=f"S-{sku}", stock=1, price=Decimal("300000"))
        offer = self.offers(self.html("same"))
        self.assertEqual((offer["@type"], offer["price"]), ("Offer", "3000000"))

    def test_all_variants_out_of_stock_is_out_of_stock(self):
        p = self.product("oos", "300000", product_type=Product.ProductType.VARIABLE)
        ProductVariant.objects.create(product=p, store=self.store, attribute="رنگ", value="A", sku="O-A", stock=0, price=Decimal("300000"))
        self.assertEqual(self.offers(self.html("oos"))["availability"], "https://schema.org/OutOfStock")
