"""The single pricing calculation service: formula, rounding policy, validation, implied discounts. Pure functions — no I/O."""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.subscriptions.services import period_pricing as pp

D = Decimal


class SpecExampleTests(SimpleTestCase):
    """The exact table from the product brief (monthly 1,000 TOMAN)."""

    def test_the_four_periods_match_the_brief(self):
        amounts = pp.compute_all(1000, {"quarterly": 5, "semiannual": 10, "yearly": 15})
        rows = [(a.months, a.base_total, a.discount_percent, a.final_price) for a in amounts.values()]
        self.assertEqual(rows, [
            (1, D(1000), D("0.00"), D(1000)),
            (3, D(3000), D("5.00"), D(2850)),
            (6, D(6000), D("10.00"), D(5400)),
            (12, D(12000), D("15.00"), D(10200)),
        ])

    def test_discount_amount_plus_final_always_equals_the_base_total_and_effective_monthly_is_display_only(self):
        amounts = pp.compute_all(1000, {"quarterly": 5, "semiannual": 10, "yearly": 15})
        for a in amounts.values():
            self.assertEqual(a.discount_amount + a.final_price, a.base_total)
        self.assertEqual([a.effective_monthly for a in amounts.values()], [D(1000), D(950), D(900), D(850)])

    def test_discounts_default_to_zero(self):
        amounts = pp.compute_all(490000, {})
        for a in amounts.values():
            self.assertEqual((a.discount_percent, a.discount_amount, a.final_price), (D("0.00"), D(0), a.base_total))

    def test_every_amount_is_a_decimal_never_a_float(self):
        for a in pp.compute_all("1,234,567", {"quarterly": "7.5"}).values():
            for value in (a.monthly_price, a.base_total, a.discount_percent, a.discount_amount, a.final_price, a.effective_monthly):
                self.assertIsInstance(value, Decimal)

    def test_billing_interval_keys_are_unchanged(self):
        self.assertEqual(pp.PERIOD_MONTHS, {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12})
        self.assertEqual(pp.PERIODS, ("monthly", "quarterly", "semiannual", "yearly"))


class RoundingPolicyTests(SimpleTestCase):
    """Half-up to the whole toman from the exact decimal product; no floating-point drift."""

    def test_exact_half_rounds_up(self):
        self.assertEqual(pp.compute_period(1, "semiannual", "50").final_price, D(3))          # 6 × 0.5 = 3 (exact)
        self.assertEqual(pp.compute_period(5, "quarterly", "50").final_price, D(8))           # 15 × 0.5 = 7.5 → 8
        self.assertEqual(pp.compute_period(1, "quarterly", "50").final_price, D(2))           # 3 × 0.5 = 1.5 → 2

    def test_just_below_half_rounds_down_and_just_above_rounds_up(self):
        self.assertEqual(pp.compute_period(999, "quarterly", "5").final_price, D(2847))       # 2997 × .95 = 2847.15
        self.assertEqual(pp.compute_period(999, "quarterly", "5.5").final_price, D(2832))     # 2997 × .945 = 2832.165
        self.assertEqual(pp.compute_period(1001, "quarterly", "5").final_price, D(2853))      # 3003 × .95 = 2852.85

    def test_a_classic_float_trap_is_exact(self):
        # 0.1 + 0.2 style traps: 3 × 19.99 % … must never depend on binary floats
        a = pp.compute_period(333, "quarterly", "19.99")
        self.assertEqual((a.base_total, a.final_price), (D(999), D(799)))                    # 999 × 0.8001 = 799.3 → 799
        self.assertEqual(pp.compute_period(10, "yearly", "0.01").final_price, D(120))         # 120 × .9999 = 119.988 → 120

    def test_large_amounts_stay_exact(self):
        a = pp.compute_period("99999999999", "yearly", "33.33")
        self.assertEqual(a.base_total, D("1199999999988"))
        self.assertEqual(a.final_price, (D("1199999999988") * D("66.67") / 100).quantize(D(1), rounding="ROUND_HALF_UP"))


class ValidationTests(SimpleTestCase):
    def test_discount_accepts_persian_arabic_digits_separators_and_blank(self):
        self.assertEqual(pp.validate_discount("۱۵"), D("15.00"))
        self.assertEqual(pp.validate_discount("٧٫٥"), D("7.50"))
        self.assertEqual(pp.validate_discount(""), D("0.00"))
        self.assertEqual(pp.validate_discount(None), D("0.00"))
        self.assertEqual(pp.validate_discount("99.99"), D("99.99"))

    def test_invalid_discounts_are_rejected(self):
        for bad in ("-1", "-0.01", "100", "100.00", "101", "5.555", "abc", "NaN", "Infinity", "-Infinity", "1e2", "5%", "٪۵"):
            with self.assertRaises(pp.PricingError, msg=bad):
                pp.validate_discount(bad)

    def test_monthly_price_rules(self):
        self.assertEqual(pp.validate_monthly_price("۱٬۰۰۰"), D(1000))
        for bad in ("0", "-5", "100.5", "abc", "", "NaN", "100000000001"):
            with self.assertRaises(pp.PricingError, msg=bad):
                pp.validate_monthly_price(bad)
        self.assertEqual(pp.validate_monthly_price("0", allow_zero=True), D(0))

    def test_a_100_percent_discount_is_never_a_free_period(self):
        with self.assertRaises(pp.PricingError):
            pp.compute_period(1000, "yearly", "100")

    def test_a_period_that_would_round_to_zero_is_rejected(self):
        with self.assertRaises(pp.PricingError):
            pp.compute_period(1, "quarterly", "99.99")                                       # 3 × .0001 = .0003 → 0

    def test_the_monthly_base_period_has_no_discount_and_unknown_periods_are_rejected(self):
        with self.assertRaises(pp.PricingError):
            pp.compute_period(1000, "monthly", "5")
        with self.assertRaises(pp.PricingError):
            pp.compute_period(1000, "weekly", "0")
        with self.assertRaises(pp.PricingError):
            pp.compute_all(1000, {"weekly": 5})


class ImpliedDiscountTests(SimpleTestCase):
    def test_an_exactly_representable_legacy_price_round_trips(self):
        self.assertEqual(pp.implied_discount(100000, "yearly", 1020000), (D("15.00"), True))
        self.assertEqual(pp.implied_discount(1000, "quarterly", 2850), (D("5.00"), True))

    def test_a_price_that_the_formula_cannot_reproduce_is_flagged_not_silently_changed(self):
        percent, exact = pp.implied_discount(290000, "yearly", 2900000)                      # 16.67 % → 2,899,… not 2,900,000
        self.assertFalse(exact)
        self.assertEqual(percent, D("16.67"))
        self.assertNotEqual(pp.compute_period(290000, "yearly", percent).final_price, D(2900000))

    def test_a_period_dearer_than_the_base_or_free_needs_an_owner_decision(self):
        self.assertFalse(pp.implied_discount(1000, "quarterly", 3500)[1])
        self.assertFalse(pp.implied_discount(1000, "quarterly", 0)[1])
