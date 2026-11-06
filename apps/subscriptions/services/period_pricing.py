"""The ONE place where subscription period prices are calculated, validated and explained.

Model (owner view): a plan has a single **monthly base price** (TOMAN) and a **discount percentage** for each longer period.

    base_total   = monthly_price × months
    final_price  = base_total × (1 − discount_percent / 100)

Rounding policy (documented, deterministic, no floating point anywhere):
  * all amounts are whole TOMAN (``Decimal`` with no fractional part — matches ``PlanVersion.display_price`` /
    ``SubscriptionInvoice`` money columns and the ×10 TOMAN→RIAL conversion done at the gateway boundary);
  * ``final_price`` is rounded **half-up to the whole toman** from the exact decimal product
    (``base_total × (100 − discount_percent) / 100``);
  * ``discount_amount = base_total − final_price`` (so the three numbers always add up exactly);
  * ``effective_monthly = final_price / months`` is for DISPLAY ONLY (half-up to a whole toman) and is never charged.

Discount rules: ``0 ≤ discount < 100`` with at most 2 decimals; Persian/Arabic digits are accepted. 100 % is rejected — a free
plan is an explicit plan type (billing period «none», price 0), never an accidental 100 % discount; a period whose final price
would round to 0 is rejected too. The monthly price must be a positive whole number for a paid plan.

Storage: the calculated ``final_price`` is stored (``PlanVersionPrice.price`` + ``discount_percent``) when a DRAFT is saved and
becomes immutable with publication — invoices, renewals, plan changes and checkout all read that snapshot through
``final_amount`` / ``quote``; they never recompute a published price. Rows without ``discount_percent`` are LEGACY absolute prices:
they are shown and charged exactly as before and are only converted by an explicit owner decision."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.core.utils import normalize_digits

PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}
PERIODS = tuple(PERIOD_MONTHS)                      # monthly, quarterly, semiannual, yearly — billing-interval keys are unchanged
DISCOUNTED_PERIODS = ("quarterly", "semiannual", "yearly")
HUNDRED = Decimal("100")
TWO_PLACES = Decimal("0.01")
MAX_MONTHLY = Decimal("100000000000")               # 10^11 toman — far below the DecimalField(14) limit even × 12


class PricingError(ValueError):
    """Invalid price/discount input. Messages are Persian and safe to show to the owner."""


@dataclass(frozen=True)
class PeriodAmounts:
    interval: str
    months: int
    monthly_price: Decimal
    base_total: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    final_price: Decimal
    effective_monthly: Decimal


@dataclass(frozen=True)
class PeriodQuote:
    """What a stored version actually charges for one period (+ how it was derived)."""
    interval: str
    months: int
    final_price: Decimal
    base_total: Decimal | None            # monthly × months when a monthly base is known, else None
    discount_percent: Decimal | None      # stored percentage for formula rows; None for legacy/absolute
    discount_amount: Decimal
    effective_monthly: Decimal
    mode: str                              # "base" | "formula" | "legacy"
    consistent: bool                       # formula rows: stored price equals the recalculation
    compare_at: Decimal | None
    label: str


def _clean_number(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = normalize_digits(str(value if value is not None else "")).replace(",", "").replace("٬", "").replace("٫", ".").strip()
    if not text:
        raise InvalidOperation
    return Decimal(text)


def validate_monthly_price(value, *, allow_zero=False) -> Decimal:
    try:
        amount = _clean_number(value)
    except (InvalidOperation, ValueError):
        raise PricingError("قیمتِ ماهانه معتبر نیست.")
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise PricingError("قیمتِ ماهانه باید عددِ صحیح (تومان) باشد.")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise PricingError("قیمتِ ماهانه باید بزرگ‌تر از صفر باشد؛ پلنِ رایگان را با «بدونِ دوره» تعریف کنید.")
    if amount > MAX_MONTHLY:
        raise PricingError("قیمتِ ماهانه بیش از حد بزرگ است.")
    return amount


def validate_discount(value) -> Decimal:
    """``None``/empty ⇒ 0 (the default). Returns a Decimal with exactly 2 decimals in ``[0, 100)``."""
    if value is None or str(value).strip() == "":
        return Decimal("0.00")
    try:
        pct = _clean_number(value)
    except (InvalidOperation, ValueError):
        raise PricingError("درصدِ تخفیف معتبر نیست.")
    if not pct.is_finite():
        raise PricingError("درصدِ تخفیف معتبر نیست.")
    if pct != pct.quantize(TWO_PLACES):
        raise PricingError("درصدِ تخفیف حداکثر دو رقمِ اعشار دارد.")
    if pct < 0:
        raise PricingError("درصدِ تخفیف نمی‌تواند منفی باشد.")
    if pct >= HUNDRED:
        raise PricingError("درصدِ تخفیف باید کمتر از ۱۰۰ باشد؛ پلنِ رایگان را با «بدونِ دوره» تعریف کنید.")
    return pct.quantize(TWO_PLACES)


def compute_period(monthly_price, interval, discount_percent=0) -> PeriodAmounts:
    """The formula. Inputs are validated again here so no caller can bypass the rules."""
    if interval not in PERIOD_MONTHS:
        raise PricingError("دوره‌ی نامعتبر.")
    monthly = validate_monthly_price(monthly_price, allow_zero=True)
    pct = validate_discount(discount_percent)
    months = PERIOD_MONTHS[interval]
    if interval == "monthly" and pct != 0:
        raise PricingError("دوره‌ی ماهانه تخفیف ندارد.")
    base_total = monthly * months
    final = (base_total * (HUNDRED - pct) / HUNDRED).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if monthly > 0 and final < 1:
        raise PricingError("قیمتِ نهاییِ دوره باید حداقل یک تومان باشد.")
    effective = (final / months).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return PeriodAmounts(interval, months, monthly, base_total, pct, base_total - final, final, effective)


def compute_all(monthly_price, discounts: dict) -> dict:
    """``{interval: PeriodAmounts}`` for the four periods; ``discounts`` maps quarterly/semiannual/yearly → percent (default 0)."""
    unknown = set(discounts) - set(DISCOUNTED_PERIODS)
    if unknown:
        raise PricingError("دوره‌ی نامعتبر.")
    out = {"monthly": compute_period(monthly_price, "monthly", 0)}
    for interval in DISCOUNTED_PERIODS:
        out[interval] = compute_period(monthly_price, interval, discounts.get(interval, 0))
    return out


def implied_discount(monthly_price, interval, stored_price):
    """For the owner-review path: the discount that would reproduce ``stored_price`` from the monthly base.
    Returns ``(percent_2dp, exact)`` — ``exact`` is True only if recomputing from that percentage gives EXACTLY ``stored_price``."""
    monthly = validate_monthly_price(monthly_price, allow_zero=False)
    months = PERIOD_MONTHS[interval]
    base_total = monthly * months
    stored = Decimal(stored_price)
    raw = (HUNDRED * (base_total - stored) / base_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if raw < 0 or raw >= HUNDRED:
        return raw, False                                  # a period costing MORE than the base, or free: needs an owner decision
    try:
        return raw, compute_period(monthly, interval, raw).final_price == stored
    except PricingError:
        return raw, False


# ----------------------------------------------------------------------------------------------- stored versions

def monthly_base(version):
    """The version's monthly base price, or ``None`` when the structure has no monthly base (legacy yearly-primary etc.)."""
    options = version.price_options()
    monthly = options.get("monthly")
    return Decimal(monthly["price"]) if monthly else None


def quote(version, interval) -> PeriodQuote:
    """What ``version`` charges for ``interval`` (reads the immutable stored snapshot). ``KeyError`` for an unoffered period."""
    options = version.price_options()
    if interval not in options:
        raise KeyError(interval)
    option = options[interval]
    price = Decimal(option["price"])
    months = PERIOD_MONTHS[interval]
    base_monthly = Decimal(options["monthly"]["price"]) if "monthly" in options else None
    pct = option.get("discount_percent")
    base_total = base_monthly * months if base_monthly is not None else None
    if interval == "monthly" and interval == version.billing_interval:
        mode, consistent = "base", True
    elif pct is not None and base_monthly is not None and version.billing_interval == "monthly":
        mode, consistent = "formula", compute_period(base_monthly, interval, pct).final_price == price
    else:
        mode, consistent = "legacy", True
    discount_amount = (base_total - price) if (base_total is not None and base_total > price) else Decimal("0")
    return PeriodQuote(
        interval=interval, months=months, final_price=price, base_total=base_total,
        discount_percent=Decimal(pct) if pct is not None else None, discount_amount=discount_amount,
        effective_monthly=(price / months).quantize(Decimal("1"), rounding=ROUND_HALF_UP), mode=mode, consistent=consistent,
        compare_at=option.get("compare_at"), label=option.get("label", ""),
    )


def quotes(version) -> list:
    options = version.price_options()
    return [quote(version, interval) for interval in PERIODS if interval in options]


def final_amount(version, interval=None) -> Decimal:
    """The amount to charge for ``interval`` — the single read path used by invoices, renewals, plan changes and checkout.
    A formula row whose stored price disagrees with its recalculation is a data-integrity error and is refused, never charged."""
    interval = interval or version.billing_interval
    if interval == version.billing_interval == "none":
        return Decimal(version.display_price)           # a free/trial plan has no billing period: it charges its stored (zero) price
    q = quote(version, interval)
    if not q.consistent:
        raise PricingError("قیمتِ ذخیره‌شده‌ی این دوره با فرمولِ قیمت‌گذاری هم‌خوان نیست؛ با پشتیبانی تماس بگیرید.")
    return q.final_price


def invoice_metadata(version, interval) -> dict:
    """Audit snapshot written on the invoice line (JSON, no secrets): how the charged amount was derived."""
    if interval == version.billing_interval == "none":
        return {"pricing": {"mode": "free", "interval": "none", "months": 0, "final": str(Decimal(version.display_price)),
                            "base_total": None, "discount_percent": None, "discount_amount": "0"}}
    q = quote(version, interval)
    return {"pricing": {
        "mode": q.mode, "interval": interval, "months": q.months, "final": str(q.final_price),
        "base_total": str(q.base_total) if q.base_total is not None else None,
        "discount_percent": str(q.discount_percent) if q.discount_percent is not None else None,
        "discount_amount": str(q.discount_amount),
    }}


def owner_review(version) -> dict:
    """What the owner form shows for an existing version (``None`` = brand-new plan).

    ``structure``: ``new`` | ``formula`` (every extra period is a stored formula row on a monthly base) | ``legacy`` (anything
    else: absolute prices, or no monthly base). For legacy periods the form prefills the IMPLIED discount only when it reproduces
    the stored price exactly; otherwise the stored price is kept as-is unless the owner explicitly accepts the change."""
    labels = {"quarterly": "سه‌ماهه", "semiannual": "شش‌ماهه", "yearly": "سالانه"}
    if version is None:
        return {"structure": "new", "monthly": None, "free": False, "has_legacy": False, "rows": [
            {"interval": i, "label": labels[i], "months": PERIOD_MONTHS[i], "offered": True, "legacy": False, "discount": "0",
             "stored_price": None, "implied": None, "exact": None, "needs_review": False} for i in DISCOUNTED_PERIODS]}
    options = version.price_options()
    monthly = Decimal(options["monthly"]["price"]) if "monthly" in options else None
    free = version.billing_interval == "none"
    rows, has_legacy = [], False
    for interval in DISCOUNTED_PERIODS:
        option = options.get(interval)
        row = {"interval": interval, "label": labels[interval], "months": PERIOD_MONTHS[interval], "offered": option is not None,
               "legacy": False, "discount": "0", "stored_price": None, "implied": None, "exact": None, "needs_review": False}
        if option is not None:
            row["stored_price"] = Decimal(option["price"])
            if option.get("discount_percent") is not None and version.billing_interval == "monthly":
                row["discount"] = _fmt_percent(option["discount_percent"])
            else:
                row["legacy"], has_legacy = True, True
                if monthly:
                    implied, exact = implied_discount(monthly, interval, option["price"])
                    row.update(implied=implied, exact=exact, needs_review=not exact)
                    row["discount"] = _fmt_percent(implied) if exact else "0"
                else:
                    row["needs_review"] = True
        elif options and version.billing_interval != "none":
            row["offered"] = False
        rows.append(row)
    structure = "legacy" if (has_legacy or (not free and version.billing_interval != "monthly")) else ("formula" if options else "new")
    return {"structure": structure, "monthly": monthly, "free": free, "has_legacy": has_legacy, "rows": rows}


def _fmt_percent(value) -> str:
    text = format(Decimal(value).quantize(TWO_PLACES), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
