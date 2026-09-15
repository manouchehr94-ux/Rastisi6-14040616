from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.cart.models import Cart, CartItem, Coupon
from apps.cart.services.pricing import cart_totals, coupon_is_applicable, product_final_price
from apps.core.models import ShopSettings
from apps.orders.models import ShippingMethod, ShippingRateRule, ShippingZone, TaxClass, TaxRate
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class PricingServiceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-p")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-p")
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست پیشتاز", slug="post-p", cost=Decimal("45000"))
        self.cart = Cart.objects.create(session_key="guest-p")

    def _add_item(self, price, discount_percent=0, quantity=1, sku="SKU-P"):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price), discount_percent=discount_percent,
        )
        return CartItem.objects.create(
            cart=self.cart, product=product, quantity=quantity, unit_price=product.final_price
        )

    def test_product_final_price_delegates_to_model_property(self):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالا", slug="p-final",
            sku="SKU-FINAL", price=Decimal("200000"), discount_percent=25,
        )
        self.assertEqual(product_final_price(product), Decimal("150000"))

    def test_cart_totals_empty_cart_without_shipping_method_is_zero(self):
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["items_total"], Decimal("0"))
        self.assertEqual(totals["grand_total"], Decimal("0"))
        self.assertFalse(totals["free_shipping"])

    def test_cart_totals_empty_cart_still_charges_shipping(self):
        # سبد خالی زیر آستانه‌ی ارسال رایگان است؛ اگر روش ارسال انتخاب شده باشد هزینه‌اش لحاظ می‌شود
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("0"))
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["grand_total"], Decimal("45000"))

    def test_cart_totals_no_discount_no_coupon_below_threshold(self):
        self._add_item(price=100_000, quantity=2)  # 200,000 total, below threshold
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("200000"))
        self.assertEqual(totals["product_discount"], Decimal("0"))
        self.assertEqual(totals["coupon_discount"], Decimal("0"))
        self.assertFalse(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["tax"], Decimal("18000"))  # 9% of 200,000
        self.assertEqual(totals["grand_total"], Decimal("263000"))

    def test_cart_totals_product_discount_calculated(self):
        self._add_item(price=200_000, discount_percent=10, quantity=1)  # final 180,000
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["items_total"], Decimal("180000"))
        self.assertEqual(totals["product_discount"], Decimal("20000"))

    def test_cart_totals_free_shipping_over_threshold(self):
        self._add_item(price=600_000, quantity=1)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertTrue(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_cart_totals_percent_coupon(self):
        self._add_item(price=100_000, quantity=2)  # items_total 200,000
        coupon = Coupon.objects.create(store=self.store, code="STYLE20", type=Coupon.Type.PERCENT, value=20)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertTrue(totals["coupon_applied"])
        self.assertEqual(totals["coupon_discount"], Decimal("40000"))

    def test_cart_totals_fixed_coupon_capped_at_items_total(self):
        self._add_item(price=100_000, quantity=1)  # items_total 100,000
        coupon = Coupon.objects.create(store=self.store, code="DIGI50", type=Coupon.Type.FIXED, value=500_000)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertEqual(totals["coupon_discount"], Decimal("100000"))
        self.assertEqual(totals["tax"], Decimal("0"))  # after_coupon == 0
        # fixed coupon does not force free shipping; items_total is below threshold
        self.assertFalse(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))
        self.assertEqual(totals["grand_total"], Decimal("45000"))

    def test_cart_totals_free_ship_coupon_forces_zero_shipping(self):
        self._add_item(price=100_000, quantity=1)  # below threshold
        coupon = Coupon.objects.create(store=self.store, code="FREESHIP", type=Coupon.Type.FREE_SHIP, value=0)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertTrue(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_coupon_not_applicable_when_inactive(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(store=self.store, code="OFF10", type=Coupon.Type.PERCENT, value=10, is_active=False)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertFalse(totals["coupon_applied"])
        self.assertEqual(totals["coupon_discount"], Decimal("0"))

    def test_coupon_not_applicable_when_expired(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(
            store=self.store, code="OLD10", type=Coupon.Type.PERCENT, value=10,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertFalse(coupon_is_applicable(coupon, Decimal("100000")))

    def test_coupon_not_applicable_below_min_order(self):
        self._add_item(price=50_000, quantity=1)
        coupon = Coupon.objects.create(store=self.store, code="BIG100", type=Coupon.Type.FIXED, value=100_000, min_order=200_000)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon, shipping_method=self.shipping)
        self.assertFalse(totals["coupon_applied"])

    def test_coupon_not_applicable_when_usage_limit_reached(self):
        self._add_item(price=100_000, quantity=1)
        coupon = Coupon.objects.create(
            store=self.store, code="LIMIT1", type=Coupon.Type.PERCENT, value=10, usage_limit=1, used_count=1
        )
        self.assertFalse(coupon_is_applicable(coupon, Decimal("100000")))

    def test_tax_and_threshold_are_configurable_via_shop_settings(self):
        """نرخ مالیات و آستانه‌ی ارسال رایگان از همان ShopSettings خوانده می‌شوند که پنل مدیریت ویرایش می‌کند."""
        shop = ShopSettings.load(store=self.store)
        shop.tax_percent = Decimal("5")
        shop.free_shipping_threshold = Decimal("1000000")
        shop.save()

        self._add_item(price=100_000, quantity=1)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["tax"], Decimal("5000"))
        self.assertFalse(totals["free_shipping"])


class VariantAwareCartTotalsTests(TestCase):
    """قیچیِ ایرانی/ایتالیایی: cart_totals باید از item.unit_price (اسنپ‌شاتِ
    آگاه از تنوع) استفاده کند، نه product.final_price ساده که تنوع را
    نادیده می‌گرفت."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-vac")
        self.category = Category.objects.create(store=self.store, name="ابزار", slug="tools-vac")
        self.cart = Cart.objects.create(session_key="guest-vac")

    def test_absolute_variant_price_used_in_items_total_not_product_base_price(self):
        from apps.catalog.models import ProductVariant

        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="scissors-vac", sku="SKU-SCISSORS-VAC", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE,
        )
        italian = ProductVariant.objects.create(
            product=product, attribute="کشور سازنده", value="ایتالیایی", price=Decimal("800000"),
        )
        CartItem.objects.create(cart=self.cart, product=product, variant=italian, quantity=1, unit_price=Decimal("800000"))

        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["items_total"], Decimal("800000"))

    def test_compare_at_price_reflected_as_product_discount_for_absolute_variant(self):
        from apps.catalog.models import ProductVariant

        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="scissors-vac2", sku="SKU-SCISSORS-VAC2", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE,
        )
        variant = ProductVariant.objects.create(
            product=product, attribute="کشور سازنده", value="ایرانی",
            price=Decimal("100000"), compare_at_price=Decimal("150000"),
        )
        CartItem.objects.create(cart=self.cart, product=product, variant=variant, quantity=1, unit_price=Decimal("100000"))

        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["items_total"], Decimal("100000"))
        self.assertEqual(totals["product_discount"], Decimal("50000"))


class PricingTwoStoreIsolationTests(TestCase):
    """اثبات این‌که ``cart_totals`` مقدار مالیات/ارسال رایگان Store دیگر را
    هرگز برنمی‌گرداند — با دو Store واقعی و دو ShopSettings واقعاً متفاوت،
    نه فقط mock کردن ``ShopSettings.load()``."""

    def setUp(self):
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)

        shop_a = ShopSettings.load(store=self.store_a)
        shop_a.tax_percent = Decimal("9")
        shop_a.free_shipping_threshold = Decimal("500000")
        shop_a.save()

        shop_b = ShopSettings.provision_for(self.store_b)
        shop_b.tax_percent = Decimal("20")
        shop_b.free_shipping_threshold = Decimal("100000")
        shop_b.save()

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="فروشگاه", slug="shop-two-store-a")
        self.category_a = Category.objects.create(store=self.store_a, name="پوشاک", slug="clothing-two-store-a")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="فروشگاه B", slug="shop-two-store-b")
        self.category_b = Category.objects.create(store=self.store_b, name="پوشاک B", slug="clothing-two-store-b")
        self.cart_a = Cart.objects.create(session_key="guest-a")
        self.cart_b = Cart.objects.create(session_key="guest-b")

    def _add_item(self, cart, price, sku, *, store):
        vendor = self.vendor_a if store == self.store_a else self.vendor_b
        category = self.category_a if store == self.store_a else self.category_b
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price),
        )
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=product.final_price)

    def test_store_a_pricing_uses_store_a_settings(self):
        self._add_item(self.cart_a, 200_000, "TWO-A", store=self.store_a)
        totals = cart_totals(self.cart_a, store=self.store_a)
        self.assertEqual(totals["tax"], Decimal("18000"))  # 9% of 200,000
        self.assertFalse(totals["free_shipping"])  # below 500,000 threshold

    def test_store_b_pricing_uses_store_b_settings(self):
        self._add_item(self.cart_b, 200_000, "TWO-B", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        self.assertEqual(totals["tax"], Decimal("40000"))  # 20% of 200,000
        self.assertTrue(totals["free_shipping"])  # above 100,000 threshold

    def test_distinct_tax_and_shipping_produce_distinct_results(self):
        self._add_item(self.cart_a, 200_000, "TWO-C", store=self.store_a)
        self._add_item(self.cart_b, 200_000, "TWO-D", store=self.store_b)
        totals_a = cart_totals(self.cart_a, store=self.store_a)
        totals_b = cart_totals(self.cart_b, store=self.store_b)
        self.assertNotEqual(totals_a["tax"], totals_b["tax"])
        self.assertNotEqual(totals_a["free_shipping"], totals_b["free_shipping"])

    def test_store_b_never_receives_store_a_settings(self):
        self._add_item(self.cart_b, 200_000, "TWO-E", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        # If Store A's settings had leaked in, tax would be 18000 (9%), not 40000 (20%).
        self.assertEqual(totals["tax"], Decimal("40000"))

    def test_explicit_store_none_is_rejected_not_silently_defaulted(self):
        self._add_item(self.cart_a, 200_000, "TWO-F", store=self.store_a)
        with self.assertRaises(ValueError):
            cart_totals(self.cart_a, store=None)

    def test_second_store_does_not_break_store_b_explicit_pricing(self):
        """با وجود دو Store (که حالت سازگاری موقت را غیرفعال می‌کند)، مسیر
        Store صریح باید همچنان کار کند — قطع سازگاری موقت نباید مسیر معتبر
        Store B را هم بشکند."""
        self._add_item(self.cart_b, 200_000, "TWO-G", store=self.store_b)
        totals = cart_totals(self.cart_b, store=self.store_b)
        self.assertTrue(totals["free_shipping"])


class PricingShippingRateIntegrationTests(TestCase):
    """اثبات این‌که ``cart_totals`` وقتی هیچ ``ShippingRateRule``ای برای یک
    روش ثبت نشده، دقیقاً به رفتارِ قدیمیِ ``method.cost`` بازمی‌گردد؛ و وقتی
    قاعده‌ای ثبت شده، از همان قاعده استفاده می‌کند — checkpoint 3B."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rate-int")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-rate-int")
        self.shipping = ShippingMethod.objects.create(
            store=self.store, name="پست پیشتاز", slug="post-rate-int", cost=Decimal("45000"),
        )
        self.cart = Cart.objects.create(session_key="guest-rate-int")

    def _add_item(self, price, quantity=1, sku="SKU-RATE-INT"):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price),
        )
        return CartItem.objects.create(cart=self.cart, product=product, quantity=quantity, unit_price=product.final_price)

    def test_no_rate_rules_falls_back_to_legacy_cost(self):
        self._add_item(price=100_000)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["shipping_cost"], Decimal("45000"))

    def test_matching_rate_rule_overrides_legacy_cost(self):
        ShippingRateRule.objects.create(method=self.shipping, name="ویژه", rate_amount=Decimal("15000"))
        self._add_item(price=100_000)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["shipping_cost"], Decimal("15000"))

    def test_rate_rule_free_over_threshold(self):
        ShippingRateRule.objects.create(
            method=self.shipping, name="آستانه", rate_amount=Decimal("15000"), free_over=Decimal("50000"),
        )
        self._add_item(price=100_000)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping)
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_zone_restricted_method_resolved_via_address(self):
        zone = ShippingZone.objects.create(store=self.store, name="تهران", code="tehran-rate-int", provinces=["تهران"])
        self.shipping.zone = zone
        self.shipping.save(update_fields=["zone"])
        self._add_item(price=100_000)
        totals = cart_totals(self.cart, store=self.store, shipping_method=self.shipping, province="تهران")
        self.assertEqual(totals["shipping_zone"], zone)


class PricingTaxClassIntegrationTests(TestCase):
    """اثبات این‌که ``cart_totals`` وقتی هیچ ``TaxRate``ای برای Store ثبت
    نشده، دقیقاً به فرمولِ قدیمیِ نرخِ ثابتِ ``ShopSettings.tax_percent``
    بازمی‌گردد؛ و وقتی دسته‌ی مالیاتی/نرخ پیکربندی شده، از آن استفاده
    می‌کند — checkpoint 3B."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-tax-int")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-tax-int")
        self.cart = Cart.objects.create(session_key="guest-tax-int")

    def _add_item(self, price, quantity=1, sku="SKU-TAX-INT", tax_class=None):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price), tax_class=tax_class,
        )
        return CartItem.objects.create(cart=self.cart, product=product, quantity=quantity, unit_price=product.final_price)

    def test_no_tax_rates_matches_legacy_flat_percent(self):
        self._add_item(price=200_000)
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["tax"], Decimal("18000"))  # 9% flat, unchanged

    def test_product_tax_class_rate_used_when_configured(self):
        tax_class = TaxClass.objects.create(store=self.store, name="ویژه", code="special-tax-int")
        TaxRate.objects.create(store=self.store, tax_class=tax_class, rate_percent=Decimal("4"))
        self._add_item(price=200_000, tax_class=tax_class)
        totals = cart_totals(self.cart, store=self.store)
        self.assertEqual(totals["tax"], Decimal("8000"))  # 4% of 200,000, not the flat 9%

    def test_multi_item_cart_with_coupon_discount_matches_legacy_total(self):
        self._add_item(price=100_000, sku="TAX-MULTI-A")
        self._add_item(price=250_000, sku="TAX-MULTI-B")
        coupon = Coupon.objects.create(store=self.store, code="TAXCUT", type=Coupon.Type.PERCENT, value=10)
        totals = cart_totals(self.cart, store=self.store, coupon=coupon)
        after_coupon = totals["items_total"] - totals["coupon_discount"]
        expected_tax = (after_coupon * Decimal("9") / Decimal("100")).quantize(Decimal("1"))
        self.assertEqual(totals["tax"], expected_tax)



class FreeShippingGoalTests(TestCase):
    """P5-W1 — the Free-Shipping Goal presentation state is computed once,
    canonically, inside ``cart_totals`` (pricing authority). All threshold /
    remaining / progress / shippability math lives here — never in a view,
    render_service, template, CSS, or JS. Uses the ``akhlaghi`` store whose
    ``free_shipping_threshold`` default is 500,000."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-fsg")
        self.category = Category.objects.create(store=self.store, name="پوشاک", slug="clothing-fsg")
        self.cart = Cart.objects.create(session_key="guest-fsg")
        # Deterministic threshold for the arithmetic assertions below.
        shop = ShopSettings.load(store=self.store)
        shop.free_shipping_threshold = Decimal("500000")
        shop.save(update_fields=["free_shipping_threshold"])

    def _add_item(self, price, *, quantity=1, sku="SKU-FSG", requires_shipping=True):
        product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای نمونه",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price), requires_shipping=requires_shipping,
        )
        return CartItem.objects.create(
            cart=self.cart, product=product, quantity=quantity, unit_price=product.final_price
        )

    # ---- 1. below threshold (physical) ----
    def test_physical_below_threshold(self):
        self._add_item(price=200_000)  # items_total 200,000 < 500,000
        t = cart_totals(self.cart, store=self.store)
        self.assertFalse(t["free_shipping_by_threshold"])
        self.assertEqual(t["free_shipping_threshold"], Decimal("500000"))
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("300000"))
        self.assertEqual(t["free_shipping_goal_progress_percent"], 40)
        self.assertTrue(0 <= t["free_shipping_goal_progress_percent"] <= 100)
        self.assertTrue(t["free_shipping_goal_applicable"])

    # ---- 2. exactly at threshold ----
    def test_exactly_at_threshold(self):
        self._add_item(price=500_000)
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["free_shipping_by_threshold"])
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("0"))
        self.assertEqual(t["free_shipping_goal_progress_percent"], 100)

    # ---- 3. above threshold ----
    def test_above_threshold_progress_clamped(self):
        self._add_item(price=800_000)
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["free_shipping_by_threshold"])
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("0"))
        self.assertEqual(t["free_shipping_goal_progress_percent"], 100)

    # ---- 4. FREE_SHIP coupon while below threshold ----
    def test_free_ship_coupon_below_threshold_not_reported_as_threshold(self):
        self._add_item(price=100_000)  # below 500,000
        coupon = Coupon.objects.create(
            store=self.store, code="FREESHIP-FSG", type=Coupon.Type.FREE_SHIP, value=0
        )
        t = cart_totals(self.cart, store=self.store, coupon=coupon)
        self.assertTrue(t["free_shipping"])
        self.assertTrue(t["free_shipping_by_coupon"])
        self.assertFalse(t["free_shipping_by_threshold"])  # must NOT claim threshold reached

    # ---- 5. threshold reached without coupon ----
    def test_threshold_reached_without_coupon(self):
        self._add_item(price=600_000)
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["free_shipping_by_threshold"])
        self.assertFalse(t["free_shipping_by_coupon"])

    # ---- 6. empty cart ----
    def test_empty_cart_goal_is_safe(self):
        t = cart_totals(self.cart, store=self.store)
        self.assertEqual(t["items_total"], Decimal("0"))
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("500000"))
        self.assertEqual(t["free_shipping_goal_progress_percent"], 0)
        self.assertTrue(0 <= t["free_shipping_goal_progress_percent"] <= 100)
        # An empty cart has no shippable item → the goal is not applicable.
        self.assertFalse(t["free_shipping_goal_applicable"])

    # ---- 8. arbitrarily high subtotal → progress clamped ----
    def test_progress_never_exceeds_100(self):
        self._add_item(price=50_000_000)
        t = cart_totals(self.cart, store=self.store)
        self.assertEqual(t["free_shipping_goal_progress_percent"], 100)
        self.assertTrue(t["free_shipping_goal_progress_percent"] <= 100)

    # ---- 8b. just below threshold must NEVER render a full (100%) bar ----
    # Invariant: 100% progress is reserved for the threshold-reached state; a
    # below-threshold cart (remaining > 0) must always be < 100. Nearest-integer
    # rounding (499000/500000 = 99.8% → 100) violated this — the fix truncates
    # below-threshold progress.
    def test_just_below_threshold_progress_is_99_not_100(self):
        self._add_item(price=499_000)  # 499,000 / 500,000
        t = cart_totals(self.cart, store=self.store)
        self.assertFalse(t["free_shipping_by_threshold"])
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("1000"))
        self.assertLess(t["free_shipping_goal_progress_percent"], 100)
        self.assertEqual(t["free_shipping_goal_progress_percent"], 99)

    def test_one_unit_below_threshold_progress_below_100(self):
        self._add_item(price=499_999)  # 499,999 / 500,000
        t = cart_totals(self.cart, store=self.store)
        self.assertFalse(t["free_shipping_by_threshold"])
        self.assertEqual(t["free_shipping_goal_remaining"], Decimal("1"))
        self.assertLess(t["free_shipping_goal_progress_percent"], 100)
        self.assertEqual(t["free_shipping_goal_progress_percent"], 99)

    # ---- 9. all-digital / non-shippable cart ----
    def test_all_digital_cart_goal_not_applicable(self):
        self._add_item(price=200_000, sku="DIGI-1", requires_shipping=False)
        self._add_item(price=150_000, sku="DIGI-2", requires_shipping=False)
        t = cart_totals(self.cart, store=self.store)
        self.assertFalse(t["free_shipping_goal_applicable"])

    # ---- 10. mixed cart (one physical + one digital) ----
    def test_mixed_cart_goal_applicable(self):
        self._add_item(price=200_000, sku="PHYS-1", requires_shipping=True)
        self._add_item(price=150_000, sku="DIGI-3", requires_shipping=False)
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["free_shipping_goal_applicable"])

    # ---- 11. physical-only cart ----
    def test_physical_only_cart_goal_applicable(self):
        self._add_item(price=200_000, sku="PHYS-2", requires_shipping=True)
        t = cart_totals(self.cart, store=self.store)
        self.assertTrue(t["free_shipping_goal_applicable"])

    # ---- 12. existing values remain unchanged (regression truth) ----
    def test_existing_totals_unchanged_when_goal_added(self):
        self._add_item(price=100_000, quantity=2)  # items_total 200,000
        t = cart_totals(self.cart, store=self.store)
        # Existing canonical outputs must be byte-identical to pre-W1 behavior.
        self.assertEqual(t["items_total"], Decimal("200000"))
        self.assertEqual(t["product_discount"], Decimal("0"))
        self.assertEqual(t["coupon_discount"], Decimal("0"))
        self.assertEqual(t["shipping_cost"], Decimal("0"))  # no shipping method passed
        self.assertIn("tax", t)
        self.assertIn("shipping_tax", t)
        self.assertIn("grand_total", t)
        self.assertFalse(t["free_shipping"])  # below threshold, no coupon
        self.assertFalse(t["coupon_applied"])


class FreeShippingGoalTwoStoreIsolationTests(TestCase):
    """P5-W1 — the goal threshold/remaining/progress are Store-scoped: two real
    Stores with different ``free_shipping_threshold`` yield different goal
    results, with no cross-Store leakage (real two-Store architecture, not a
    mocked ``ShopSettings.load``)."""

    def setUp(self):
        self.store_a = Store.objects.create(name="FSG Store A", slug="fsg-store-a", status=Store.Status.ACTIVE)
        self.store_b = Store.objects.create(name="FSG Store B", slug="fsg-store-b", status=Store.Status.ACTIVE)
        shop_a = ShopSettings.provision_for(self.store_a)
        shop_a.free_shipping_threshold = Decimal("500000")
        shop_a.save(update_fields=["free_shipping_threshold"])
        shop_b = ShopSettings.provision_for(self.store_b)
        shop_b.free_shipping_threshold = Decimal("100000")
        shop_b.save(update_fields=["free_shipping_threshold"])
        self.vendor_a = Vendor.objects.create(store=self.store_a, name="A", slug="fsg-vendor-a")
        self.category_a = Category.objects.create(store=self.store_a, name="A", slug="fsg-cat-a")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="B", slug="fsg-vendor-b")
        self.category_b = Category.objects.create(store=self.store_b, name="B", slug="fsg-cat-b")
        self.cart_a = Cart.objects.create(session_key="fsg-a")
        self.cart_b = Cart.objects.create(session_key="fsg-b")

    def _add(self, cart, price, sku, *, store):
        vendor = self.vendor_a if store == self.store_a else self.vendor_b
        category = self.category_a if store == self.store_a else self.category_b
        product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالا",
            slug=f"{sku}-slug", sku=sku, price=Decimal(price), requires_shipping=True,
        )
        CartItem.objects.create(cart=cart, product=product, quantity=1, unit_price=product.final_price)

    def test_two_stores_have_distinct_goal_state(self):
        self._add(self.cart_a, 200_000, "FSG-A", store=self.store_a)  # below 500k
        self._add(self.cart_b, 200_000, "FSG-B", store=self.store_b)  # above 100k
        ta = cart_totals(self.cart_a, store=self.store_a)
        tb = cart_totals(self.cart_b, store=self.store_b)
        self.assertEqual(ta["free_shipping_threshold"], Decimal("500000"))
        self.assertEqual(tb["free_shipping_threshold"], Decimal("100000"))
        self.assertFalse(ta["free_shipping_by_threshold"])
        self.assertTrue(tb["free_shipping_by_threshold"])
        self.assertEqual(ta["free_shipping_goal_remaining"], Decimal("300000"))
        self.assertEqual(tb["free_shipping_goal_remaining"], Decimal("0"))
        self.assertNotEqual(
            ta["free_shipping_goal_progress_percent"], tb["free_shipping_goal_progress_percent"]
        )
