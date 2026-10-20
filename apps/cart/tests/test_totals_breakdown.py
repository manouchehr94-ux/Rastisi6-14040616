"""RS-11 — the money summary must reconcile: every number on cart/checkout comes from ``cart_totals`` and the displayed
rows add up to the payable total (owner screenshot: qty 6, 18 % product discount, 9 % VAT ⇒ 34,590,060)."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.cart.models import Cart, CartItem
from apps.cart.services.pricing import build_totals_breakdown, cart_totals
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.core.models import ShopSettings
from apps.orders.models import ShippingMethod
from apps.stores.models import Store


class BreakdownBase(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.vendor = Vendor.objects.create(store=self.store, name="V", slug="v-bd")
        self.category = Category.objects.create(store=self.store, name="C", slug="c-bd")
        self.cart = Cart.objects.create(session_key="bd")
        self.shop = ShopSettings.load(store=self.store)
        self.shop.tax_percent = Decimal("9")
        self.shop.free_shipping_threshold = Decimal("999999999")
        self.shop.save()

    def product(self, price, pct=0, sku="BD1", **kw):
        return Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کتانی", slug=f"s-{sku}", sku=sku,
            price=Decimal(price), discount_percent=pct, stock=50, **kw,
        )

    def add(self, product, qty, variant=None, unit=None):
        return CartItem.objects.create(
            cart=self.cart, product=product, variant=variant, quantity=qty,
            unit_price=unit if unit is not None else product.final_price,
        )

    def rows(self, totals):
        return {r["key"]: r for r in totals["breakdown"]["rows"]}


class OwnerScreenshotNumbersTests(BreakdownBase):
    def test_quantity_six_with_discount_and_vat_reconciles_to_the_screenshot_total(self):
        self.add(self.product("6450000", 18), 6)
        t = cart_totals(self.cart, store=self.store)
        self.assertEqual(t["items_total"], Decimal("31734000"))       # net of the discount (unit 5,289,000 × 6)
        self.assertEqual(t["product_discount"], Decimal("6966000"))
        self.assertEqual(t["tax"], Decimal("2856060"))
        self.assertEqual(t["grand_total"], Decimal("34590060"))
        r = self.rows(t)
        self.assertEqual(r["gross"]["amount"], Decimal("38700000"))   # 6 × 6,450,000
        self.assertEqual(r["product_discount"]["amount"], Decimal("6966000"))
        self.assertEqual(r["items_net"]["amount"], Decimal("31734000"))
        self.assertEqual(r["tax"]["amount"], Decimal("2856060"))
        self.assertTrue(t["breakdown"]["reconciles"], t["breakdown"])
        self.assertEqual(t["breakdown"]["checked_total"], t["grand_total"])

    def test_quantity_one_and_no_discount_has_no_discount_rows(self):
        self.add(self.product("100000", 0, sku="BD2"), 1)
        t = cart_totals(self.cart, store=self.store)
        r = self.rows(t)
        self.assertNotIn("product_discount", r)
        self.assertNotIn("items_net", r)
        self.assertEqual(r["gross"]["label"], "جمع کالاها")
        self.assertEqual(t["grand_total"], Decimal("109000"))
        self.assertTrue(t["breakdown"]["reconciles"])


class ReconciliationMatrixTests(BreakdownBase):
    def test_shipping_and_shipping_tax_are_part_of_the_tax_row_and_the_sum(self):
        self.shop.shipping_taxable = True
        self.shop.save()
        method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-bd", cost=Decimal("50000"))
        self.add(self.product("200000", 0, sku="BD3"), 2)
        t = cart_totals(self.cart, store=self.store, shipping_method=method)
        self.assertEqual(t["shipping_cost"], Decimal("50000"))
        self.assertGreater(t["shipping_tax"], 0)
        r = self.rows(t)
        self.assertEqual(r["tax"]["amount"], t["tax"] + t["shipping_tax"])
        self.assertTrue(t["breakdown"]["reconciles"], t["breakdown"])

    def test_inclusive_prices_show_vat_as_information_not_as_an_addend(self):
        self.shop.prices_include_tax = True
        self.shop.save()
        self.add(self.product("109000", 0, sku="BD4"), 1)
        t = cart_totals(self.cart, store=self.store)
        r = self.rows(t)
        self.assertEqual(r["tax_included"]["kind"], "info")
        self.assertIn("شامل در قیمت", r["tax_included"]["label"])
        self.assertEqual(t["grand_total"], Decimal("109000"))
        self.assertTrue(t["breakdown"]["reconciles"], t["breakdown"])

    def test_free_shipping_row_is_labelled_free_and_adds_nothing(self):
        self.shop.free_shipping_threshold = Decimal("1")
        self.shop.save()
        method = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-free-bd", cost=Decimal("50000"))
        self.add(self.product("100000", 0, sku="BD5"), 1)
        t = cart_totals(self.cart, store=self.store, shipping_method=method)
        self.assertEqual(self.rows(t)["shipping"]["kind"], "free")
        self.assertTrue(t["breakdown"]["reconciles"])

    def test_no_shipping_method_means_no_shipping_row(self):
        self.add(self.product("100000", 0, sku="BD6"), 1)
        t = cart_totals(self.cart, store=self.store)
        self.assertNotIn("shipping", self.rows(t))

    def test_variant_price_and_compare_at_discount_reconcile(self):
        product = self.product("1", 0, sku="BD7", product_type=Product.ProductType.VARIABLE)
        variant = ProductVariant.objects.create(
            product=product, attribute="سایز", value="۴۰", price=Decimal("100000"), compare_at_price=Decimal("150000"), stock=5,
        )
        self.add(product, 3, variant=variant, unit=Decimal("100000"))
        t = cart_totals(self.cart, store=self.store)
        self.assertEqual(self.rows(t)["gross"]["amount"], Decimal("450000"))
        self.assertEqual(self.rows(t)["product_discount"]["amount"], Decimal("150000"))
        self.assertTrue(t["breakdown"]["reconciles"], t["breakdown"])

    def test_expired_promotion_is_not_in_the_summary(self):
        p = self.product("100000", 30, sku="BD8")
        p.discount_starts_at = timezone.now() - timedelta(days=2)
        p.discount_ends_at = timezone.now() - timedelta(minutes=1)
        p.save()
        self.add(p, 1, unit=Decimal("100000"))  # the cart snapshot is re-priced at checkout; summary reads the snapshot
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["breakdown"]["reconciles"], t["breakdown"])


class BreakdownUnitTests(TestCase):
    def test_pure_function_rows_sum_to_grand_total_for_a_coupon_and_gift_wrap_case(self):
        totals = {
            "items_total": Decimal("900"), "product_discount": Decimal("100"), "coupon_item_discount": Decimal("90"),
            "gift_wrap_total": Decimal("20"), "gift_wrap_discount": Decimal("5"), "shipping_cost": Decimal("30"),
            "shipping_method_selected": True, "free_shipping": False, "tax": Decimal("81"), "shipping_tax": Decimal("0"),
            "tax_lines": [], "prices_include_tax": False, "grand_total": Decimal("900") - Decimal("90") + 20 - 5 + 30 + 81,
        }
        b = build_totals_breakdown(totals)
        self.assertEqual(b["checked_total"], Decimal("936"))
        self.assertTrue(b["reconciles"])
