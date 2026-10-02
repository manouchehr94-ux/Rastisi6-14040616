"""موتورِ قواعدِ شمولِ کمپین — درختِ AND/OR تودرتو بر پایه‌ی رجیستریِ «برگ‌ها».

ساختار (JSON، قابلِ ساخت با UI بدونِ کد/SQL):

``{"type": "group", "op": "and"|"or", "negate": false, "children": [...]}``
``{"type": "<نوعِ برگ>", ...پارامترها}``

امنیت: فقط نوع‌هایِ برگِ ثبت‌شده در ``LEAVES`` و پارامترهایِ اعتبارسنجی‌شده
پذیرفته می‌شود؛ هیچ eval/SQLِ خام/عبارتِ آزاد وجود ندارد. شناسه‌هایِ ارجاعی
(کالا، دسته، برند، مشتری…) همیشه با ``store`` بررسی می‌شوند تا ارجاعِ
بین‌فروشگاهی ممکن نباشد.

معناشناسیِ دامنه (``scope``):

* ``aggregate`` (پیش‌فرض): برگ‌هایِ سطحِ سفارش روی **مجموعِ سفارش‌هایِ معتبرِ
  بازه** ارزیابی می‌شوند — «حداقل یک ردیفِ مطابق»، «حداقل یک سفارش با مقصدِ X»،
  «جمعِ مبلغِ فاکتورها». هر شرط می‌تواند با سفارشِ متفاوتی برقرار شود.
* ``same_order``: همه‌ی شرط‌ها باید با **یک سفارشِ واحد** برقرار شوند (مبلغ =
  مبلغِ همان سفارش).

``OR`` هرگز به ``AND`` تبدیل نمی‌شود: هر گره دقیقاً با عملگرِ خودش ارزیابی می‌شود
و گروهِ تودرتو مستقل است.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.core.jalali_utils import JalaliDateError, parse_jalali_date
from apps.core.utils import normalize_text

MAX_DEPTH = 6
MAX_NODES = 120
OPS = ("gt", "gte", "lt", "lte", "eq", "between")
OP_LABELS = {"gt": "بیشتر از", "gte": "حداقل", "lt": "کمتر از", "lte": "حداکثر", "eq": "برابر با", "between": "بین"}


class RuleError(ValueError):
    """قاعده‌ی نامعتبر — پیام برایِ نمایش به مدیر مناسب است."""


@dataclass
class EvalContext:
    facts: object                      # CustomerFacts
    orders: list                       # سفارش‌هایِ معتبرِ درونِ دامنه (OrderView)
    all_orders: list                   # همه‌ی وضعیت‌هایِ بازه (برایِ order_history)
    now: dt.datetime
    amount_basis: str = "net_total"
    period_start: dt.datetime | None = None


# ----------------------------------------------------------------- کمکیِ اعتبارسنجی


def _norm(value) -> str:
    return normalize_text(str(value or "")).lower().strip()


def _int_list(p, key, *, required=False):
    values = p.get(key)
    if values in (None, [], ""):
        if required:
            raise RuleError(f"«{key}» الزامی است.")
        return None
    if not isinstance(values, (list, tuple)) or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in values):
        raise RuleError(f"«{key}» باید فهرستی از شناسه‌هایِ عددی باشد.")
    return sorted(set(values))


def _str_list(p, key, *, required=False):
    values = p.get(key)
    if values in (None, [], ""):
        if required:
            raise RuleError(f"«{key}» الزامی است.")
        return None
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)) or not all(isinstance(v, str) and v.strip() for v in values):
        raise RuleError(f"«{key}» باید فهرستی از متن باشد.")
    return [v.strip() for v in values][:50]


def _decimal(value, key):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RuleError(f"«{key}» باید عدد باشد.") from exc
    if number.is_nan() or number.is_infinite():
        raise RuleError(f"«{key}» باید عدد باشد.")
    return number


def _op_value(p, *, integer=False, allow_zero=True):
    op = p.get("op", "gte")
    if op not in OPS:
        raise RuleError("عملگرِ مقایسه نامعتبر است.")
    out = {"op": op}
    keys = ("value", "value2") if op == "between" else ("value",)
    for key in keys:
        if p.get(key) in (None, ""):
            raise RuleError(f"«{key}» الزامی است.")
        number = _decimal(p[key], key)
        if number < 0:
            raise RuleError("مقدار نمی‌تواند منفی باشد.")
        if integer:
            if number != number.to_integral_value():
                raise RuleError("مقدار باید عددِ صحیح باشد.")
            number = int(number)
        out[key] = str(number)
    if op == "between" and Decimal(out["value"]) > Decimal(out["value2"]):
        raise RuleError("در بازه، حدِ پایین نباید بزرگ‌تر از حدِ بالا باشد.")
    return out


def _compare(actual, p) -> bool:
    actual = Decimal(actual)
    value = Decimal(p["value"])
    op = p["op"]
    if op == "gt":
        return actual > value
    if op == "gte":
        return actual >= value
    if op == "lt":
        return actual < value
    if op == "lte":
        return actual <= value
    if op == "eq":
        return actual == value
    return value <= actual <= Decimal(p["value2"])


def parse_date_param(raw) -> dt.date:
    """تاریخِ میلادی ``YYYY-MM-DD`` یا جلالی ``YYYY/MM/DD`` (سالِ <۱۷۰۰ ⇒ جلالی)."""
    if isinstance(raw, dt.date):
        return raw
    text = str(raw or "").strip()
    try:
        head = int(text.replace("-", "/").split("/")[0])
    except (ValueError, IndexError) as exc:
        raise RuleError("تاریخ نامعتبر است.") from exc
    try:
        if head >= 1700:
            return dt.date.fromisoformat(text.replace("/", "-"))
        return parse_jalali_date(text)
    except (ValueError, JalaliDateError) as exc:
        raise RuleError("تاریخ نامعتبر است.") from exc


def _date_cond(p, *, with_within=False):
    mode = p.get("mode", "between")
    out = {"mode": mode}
    if mode == "before" or mode == "after":
        out["date"] = parse_date_param(p.get("date")).isoformat()
    elif mode == "between":
        start, end = parse_date_param(p.get("start")), parse_date_param(p.get("end"))
        if start > end:
            raise RuleError("تاریخ شروع نباید بعد از پایان باشد.")
        out["start"], out["end"] = start.isoformat(), end.isoformat()
    elif mode == "within_days" and with_within:
        days = _decimal(p.get("days"), "days")
        if days < 0 or days != days.to_integral_value():
            raise RuleError("تعداد روز باید عددِ صحیحِ غیرمنفی باشد.")
        out["days"] = int(days)
    else:
        raise RuleError("حالتِ تاریخ نامعتبر است.")
    return out


def _date_matches(value: dt.datetime | None, p, now) -> bool:
    if value is None:
        return False
    if value.tzinfo is not None:
        from apps.core.jalali_utils import store_timezone

        value = value.astimezone(store_timezone())
    day = value.date()
    mode = p["mode"]
    if mode == "before":
        return day < dt.date.fromisoformat(p["date"])
    if mode == "after":
        return day > dt.date.fromisoformat(p["date"])
    if mode == "between":
        return dt.date.fromisoformat(p["start"]) <= day <= dt.date.fromisoformat(p["end"])
    return (now.date() - day).days <= p["days"]


# ----------------------------------------------------------------- رجیستری برگ‌ها


@dataclass(frozen=True)
class Leaf:
    key: str
    label: str
    level: str  # "line" | "order" | "customer" — برایِ تشخیصِ نیاز به سفارش‌ها
    validate: object
    evaluate: object
    category: str = ""
    help: str = ""


LEAVES: dict[str, Leaf] = {}


def leaf(key, label, level, *, category="", help=""):
    def deco(fn_pair):
        validate, evaluate = fn_pair
        LEAVES[key] = Leaf(key, label, level, validate, evaluate, category, help)
        return fn_pair
    return deco


def _check_store_ids(store, model, ids, label, *, store_field="store"):
    if not ids:
        return
    found = set(model.objects.filter(**{store_field: store}, pk__in=ids).values_list("pk", flat=True))
    missing = set(ids) - found
    if missing:
        raise RuleError(f"{label} با شناسه‌ی {sorted(missing)} در این فروشگاه یافت نشد.")


def _all_lines(ctx):
    for order in ctx.orders:
        yield from order.lines


# ---- برگِ ردیفِ کالا ---------------------------------------------------------

_LINE_KEYS = (
    "product_ids", "skus", "category_ids", "brand_ids", "brand_names", "colors", "sizes", "attributes",
    "price_min", "price_max",
)


def _line_validate(p, store):
    from apps.catalog.models import Brand, Category, Product

    out = {}
    if (ids := _int_list(p, "product_ids")) is not None:
        _check_store_ids(store, Product, ids, "کالا")
        out["product_ids"] = ids
    if (v := _str_list(p, "skus")) is not None:
        out["skus"] = v
    if (ids := _int_list(p, "category_ids")) is not None:
        _check_store_ids(store, Category, ids, "دسته")
        out["category_ids"] = ids
    if (ids := _int_list(p, "brand_ids")) is not None:
        _check_store_ids(store, Brand, ids, "برند")
        out["brand_ids"] = ids
    for key in ("brand_names", "colors", "sizes"):
        if (v := _str_list(p, key)) is not None:
            out[key] = v
    attrs = p.get("attributes")
    if attrs:
        if not isinstance(attrs, dict) or not all(isinstance(k, str) and k for k in attrs):
            raise RuleError("«attributes» باید نگاشتِ کدِ ویژگی به فهرستِ مقدارها باشد.")
        clean = {}
        for code, values in attrs.items():
            vals = _str_list({"v": values}, "v", required=True)
            clean[code] = vals
        out["attributes"] = clean
    for key in ("price_min", "price_max"):
        if p.get(key) not in (None, ""):
            number = _decimal(p[key], key)
            if number < 0:
                raise RuleError("قیمت نمی‌تواند منفی باشد.")
            out[key] = str(number)
    if not out:
        raise RuleError("حداقل یک فیلترِ کالا (کالا/SKU/دسته/برند/رنگ/سایز/ویژگی/قیمت) لازم است.")
    minq = p.get("min_quantity", 1)
    minq = _decimal(minq, "min_quantity")
    if minq < 1 or minq != minq.to_integral_value():
        raise RuleError("حداقل تعداد باید عددِ صحیحِ مثبت باشد.")
    out["min_quantity"] = int(minq)
    return out


def _line_matches(line, p) -> bool:
    snap = line.snapshot or {}
    if p.get("product_ids") and line.product_id not in set(p["product_ids"]):
        return False
    if p.get("skus") and _norm(line.sku) not in {_norm(s) for s in p["skus"]}:
        return False
    if p.get("category_ids"):
        cat = snap.get("category") or {}
        ids = ({cat["id"]} if cat.get("id") else set()) | set(cat.get("ancestor_ids", ()))
        if not ids & set(p["category_ids"]):
            return False
    brand = snap.get("brand") or {}
    if p.get("brand_ids") and brand.get("id") not in set(p["brand_ids"]):
        return False
    if p.get("brand_names") and _norm(brand.get("name")) not in {_norm(n) for n in p["brand_names"]}:
        return False
    if p.get("colors"):
        wanted = {_norm(c) for c in p["colors"]}
        have = set()
        for color in snap.get("colors", ()):
            have.add(_norm(color.get("label")))
            if color.get("hex"):
                have.add(_norm(color["hex"]))
        if not wanted & have:
            return False
    if p.get("sizes") and not {_norm(s) for s in p["sizes"]} & {_norm(s) for s in snap.get("sizes", ())}:
        return False
    for code, wanted in (p.get("attributes") or {}).items():
        have = {_norm(v) for v in (snap.get("attributes") or {}).get(code, ())}
        if not {_norm(w) for w in wanted} & have:
            return False
    if p.get("price_min") and line.unit_price < Decimal(p["price_min"]):
        return False
    if p.get("price_max") and line.unit_price > Decimal(p["price_max"]):
        return False
    return True


def _line_eval(p, ctx):
    quantity = sum(line.quantity for line in _all_lines(ctx) if _line_matches(line, p))
    return quantity >= p.get("min_quantity", 1)


leaf("line_match", "خرید کالایِ مشخص (ردیفِ سفارش)", "line", category="کالا",
     help="همه‌ی فیلترهایِ انتخاب‌شده باید روی یک ردیفِ سفارش برقرار باشند (AND)؛ برایِ «یا» از گروهِ OR استفاده کنید.")((_line_validate, _line_eval))


def _all_products_validate(p, store):
    from apps.catalog.models import Product

    ids = _int_list(p, "product_ids", required=True)
    _check_store_ids(store, Product, ids, "کالا")
    return {"product_ids": ids}


def _all_products_eval(p, ctx):
    bought = {line.product_id for line in _all_lines(ctx)}
    return set(p["product_ids"]) <= bought


leaf("all_products", "خریدِ همه‌ی کالاهایِ الزامی", "line", category="کالا")((_all_products_validate, _all_products_eval))

# ---- برگ‌هایِ سطحِ سفارش ---------------------------------------------------------


def _order_total_eval(p, ctx):
    total = sum((o.amount(p.get("basis", ctx.amount_basis)) for o in ctx.orders), Decimal("0"))
    return bool(ctx.orders) and _compare(total, p)


def _order_total_validate(p, store):
    out = _op_value(p)
    basis = p.get("basis") or ""
    if basis and basis not in ("net_total", "grand_total", "items_total"):
        raise RuleError("مبنای مبلغ نامعتبر است.")
    if basis:
        out["basis"] = basis
    return out


leaf("order_total", "جمعِ مبلغ فاکتورهایِ معتبر", "order", category="سفارش")((_order_total_validate, _order_total_eval))


def _any_order_total_eval(p, ctx):
    return any(_compare(o.amount(p.get("basis", ctx.amount_basis)), p) for o in ctx.orders)


leaf("any_order_total", "مبلغِ یک سفارشِ منفرد", "order", category="سفارش")((_order_total_validate, _any_order_total_eval))
leaf("order_count", "تعدادِ سفارش‌هایِ معتبرِ بازه", "order", category="سفارش")(
    (lambda p, store: _op_value(p, integer=True), lambda p, ctx: _compare(len(ctx.orders), p)))
leaf("item_count", "تعدادِ کلِ اقلامِ خریداری‌شده", "order", category="سفارش")(
    (lambda p, store: _op_value(p, integer=True), lambda p, ctx: _compare(sum(o.item_count for o in ctx.orders), p)))


def _text_values_validate(p, store):
    return {"values": _str_list(p, "values", required=True)}


leaf("shipping_province", "استانِ مقصدِ ارسال", "order", category="ارسال")(
    (_text_values_validate, lambda p, ctx: any(_norm(o.province) in {_norm(v) for v in p["values"]} for o in ctx.orders)))
leaf("shipping_city", "شهرِ مقصدِ ارسال", "order", category="ارسال")(
    (_text_values_validate, lambda p, ctx: any(_norm(o.city) in {_norm(v) for v in p["values"]} for o in ctx.orders)))


def _choice_validate(allowed):
    def validate(p, store):
        values = _str_list(p, "values", required=True)
        bad = [v for v in values if v not in allowed]
        if bad:
            raise RuleError(f"مقدارِ نامعتبر: {', '.join(bad)}")
        return {"values": values}
    return validate


_ORDER_STATUSES = ("pending", "processing", "shipped", "delivered", "canceled")
_PAYMENT_STATUSES = ("pending", "paid", "failed", "refunded")
leaf("order_status", "وضعیتِ سفارش", "order", category="سفارش")(
    (_choice_validate(_ORDER_STATUSES), lambda p, ctx: any(o.status in p["values"] for o in ctx.orders)))
leaf("payment_status", "وضعیتِ پرداخت", "order", category="پرداخت")(
    (_choice_validate(_PAYMENT_STATUSES), lambda p, ctx: any(o.payment_status in p["values"] for o in ctx.orders)))


def _gateway_validate(p, store):
    from apps.orders.models import PaymentGateway

    ids = _int_list(p, "ids", required=True)
    _check_store_ids(store, PaymentGateway, ids, "روشِ پرداخت")
    return {"ids": ids}


def _shipping_method_validate(p, store):
    from apps.orders.models import ShippingMethod

    ids = _int_list(p, "ids", required=True)
    _check_store_ids(store, ShippingMethod, ids, "روشِ ارسال")
    return {"ids": ids}


leaf("payment_method", "روشِ پرداخت", "order", category="پرداخت")(
    (_gateway_validate, lambda p, ctx: any(o.gateway_id in p["ids"] for o in ctx.orders)))
leaf("shipping_method", "روشِ ارسال", "order", category="ارسال")(
    (_shipping_method_validate, lambda p, ctx: any(o.shipping_method_id in p["ids"] for o in ctx.orders)))
leaf("shipping_cost", "هزینه‌ی ارسالِ یک سفارش", "order", category="ارسال")(
    (lambda p, store: _op_value(p), lambda p, ctx: any(_compare(o.shipping_cost, p) for o in ctx.orders)))


def _used_coupon_validate(p, store):
    from apps.cart.models import Coupon

    ids = _int_list(p, "coupon_ids")
    _check_store_ids(store, Coupon, ids or [], "کد تخفیف")
    return {"coupon_ids": ids or [], "used": bool(p.get("used", True))}


def _used_coupon_eval(p, ctx):
    used = any((o.coupon_id in p["coupon_ids"]) if p["coupon_ids"] else (o.coupon_id is not None) for o in ctx.orders)
    return used if p["used"] else not used


leaf("used_coupon", "استفاده از کدِ تخفیف در سفارش", "order", category="تخفیف")((_used_coupon_validate, _used_coupon_eval))
leaf("had_discount", "تخفیفِ قبلی روی سفارش", "order", category="تخفیف")(
    (lambda p, store: {}, lambda p, ctx: any(o.discount_total > 0 for o in ctx.orders)))


def _weekday_validate(p, store):
    values = p.get("values")
    if not isinstance(values, (list, tuple)) or not values or not all(isinstance(v, int) and 0 <= v <= 6 for v in values):
        raise RuleError("روزهایِ هفته باید اعدادِ ۰ (دوشنبه) تا ۶ (یکشنبه) باشند.")
    return {"values": sorted(set(values))}


def _hour_validate(p, store):
    start, end = p.get("start"), p.get("end")
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= 24):
        raise RuleError("بازه‌ی ساعت باید [شروع, پایان) بینِ ۰ تا ۲۴ باشد.")
    return {"start": start, "end": end}


leaf("order_weekday", "روزِ هفته‌ی ثبتِ سفارش", "order", category="زمان")(
    (_weekday_validate, lambda p, ctx: any(o.created_at.weekday() in p["values"] for o in ctx.orders)))
leaf("order_hour", "ساعتِ ثبتِ سفارش", "order", category="زمان")(
    (_hour_validate, lambda p, ctx: any(p["start"] <= o.created_at.hour < p["end"] for o in ctx.orders)))


def _history_validate(p, store):
    state = p.get("state")
    if state not in ("canceled", "returned", "refunded"):
        raise RuleError("حالتِ تاریخچه باید canceled/returned/refunded باشد.")
    return {"state": state, "exists": bool(p.get("exists", True))}


def _history_eval(p, ctx):
    pool = ctx.all_orders
    if p["state"] == "canceled":
        hit = any(o.status == "canceled" for o in pool)
    elif p["state"] == "returned":
        hit = any(o.has_return for o in pool)
    else:
        hit = any(o.refunded > 0 or o.payment_status == "refunded" for o in pool)
    return hit if p["exists"] else not hit


leaf("order_history", "سابقه‌ی لغو/مرجوعی/استرداد", "order", category="سفارش")((_history_validate, _history_eval))

# ---- برگ‌هایِ سطحِ مشتری ---------------------------------------------------------


def _customer_ids_validate(p, store):
    from apps.engagement.services.rule_data import store_customer_ids

    ids = _int_list(p, "ids", required=True)
    allowed = store_customer_ids(store)
    missing = set(ids) - allowed
    if missing:
        raise RuleError(f"مشتری با شناسه‌ی {sorted(missing)} در این فروشگاه یافت نشد.")
    return {"ids": ids}


leaf("customer_ids", "مشتریانِ مشخص", "customer", category="مشتری")(
    (_customer_ids_validate, lambda p, ctx: ctx.facts.customer.pk in p["ids"]))


def _segment_validate(p, store):
    from apps.customers.models import CustomerSegment

    ids = _int_list(p, "ids", required=True)
    _check_store_ids(store, CustomerSegment, ids, "گروه/سگمنت")
    return {"ids": ids}


def _tag_validate(p, store):
    from apps.customers.models import CustomerTag

    ids = _int_list(p, "ids", required=True)
    _check_store_ids(store, CustomerTag, ids, "برچسب")
    return {"ids": ids}


leaf("segment_ids", "عضویت در گروهِ مشتریان (سگمنت)", "customer", category="مشتری")(
    (_segment_validate, lambda p, ctx: bool(ctx.facts.segment_ids & set(p["ids"]))))
leaf("customer_tag_ids", "برچسبِ مشتری", "customer", category="مشتری")(
    (_tag_validate, lambda p, ctx: bool(ctx.facts.tag_ids & set(p["ids"]))))
leaf("registered", "تاریخِ ثبت‌نام", "customer", category="مشتری")(
    (lambda p, store: _date_cond(p, with_within=True),
     lambda p, ctx: _date_matches(ctx.facts.customer.created_at, p, ctx.now)))
leaf("customer_city", "شهرِ مشتری", "customer", category="مشتری")(
    (_text_values_validate,
     lambda p, ctx: _norm(ctx.facts.city or ctx.facts.customer.city) in {_norm(v) for v in p["values"]}))
leaf("customer_province", "استانِ مشتری (آدرسِ پیش‌فرض)", "customer", category="مشتری")(
    (_text_values_validate, lambda p, ctx: _norm(ctx.facts.province) in {_norm(v) for v in p["values"]}))


def _birthday_validate(p, store):
    mode = p.get("mode", "today")
    if mode not in ("today", "this_month", "month"):
        raise RuleError("حالتِ تولد نامعتبر است.")
    out = {"mode": mode}
    if mode == "month":
        month = p.get("month")
        if not (isinstance(month, int) and 1 <= month <= 12):
            raise RuleError("ماهِ تولد باید ۱ تا ۱۲ باشد.")
        out["month"] = month
    return out


def _birthday_eval(p, ctx):
    from apps.core.jalali_utils import birthday_month_day, gregorian_to_jalali, month_day_keys_for_date

    born = ctx.facts.customer.birth_date
    if born is None:
        return False
    today = ctx.now.date()
    if p["mode"] == "today":
        month, day = birthday_month_day(born)
        return (month * 100 + day) in month_day_keys_for_date(today)
    month = birthday_month_day(born)[0]
    target = gregorian_to_jalali(today)[1] if p["mode"] == "this_month" else p["month"]
    return month == target


leaf("birthday", "تولد", "customer", category="مشتری")((_birthday_validate, _birthday_eval))


def _age_validate(p, store):
    out = {}
    for key in ("min", "max"):
        if p.get(key) not in (None, ""):
            v = _decimal(p[key], key)
            if v < 0 or v > 130 or v != v.to_integral_value():
                raise RuleError("سن باید عددی صحیح بین ۰ تا ۱۳۰ باشد.")
            out[key] = int(v)
    if not out:
        raise RuleError("حداقل یکی از حدِ پایین/بالایِ سن لازم است.")
    if "min" in out and "max" in out and out["min"] > out["max"]:
        raise RuleError("حدِ پایینِ سن نباید بزرگ‌تر از حدِ بالا باشد.")
    return out


def _age_eval(p, ctx):
    born = ctx.facts.customer.birth_date
    if born is None:
        return False
    today = ctx.now.date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return p.get("min", 0) <= age <= p.get("max", 200)


leaf("age", "بازه‌ی سنی (در صورتِ ثبتِ تاریخِ تولد)", "customer", category="مشتری")((_age_validate, _age_eval))
leaf("lifetime_orders", "تعدادِ کلِ سفارش‌هایِ مشتری", "customer", category="مشتری")(
    (lambda p, store: _op_value(p, integer=True), lambda p, ctx: _compare(ctx.facts.lifetime_orders, p)))
leaf("lifetime_spent", "مجموعِ کلِ خریدِ مشتری", "customer", category="مشتری")(
    (lambda p, store: _op_value(p), lambda p, ctx: _compare(ctx.facts.lifetime_spent, p)))
leaf("average_order_value", "میانگینِ مبلغِ سفارشِ مشتری", "customer", category="مشتری")(
    (lambda p, store: _op_value(p),
     lambda p, ctx: ctx.facts.lifetime_orders > 0 and _compare(ctx.facts.average_order_value, p)))
leaf("first_purchase", "تاریخِ اولین خرید", "customer", category="مشتری")(
    (lambda p, store: _date_cond(p, with_within=True), lambda p, ctx: _date_matches(ctx.facts.first_purchase, p, ctx.now)))
leaf("last_purchase", "تاریخِ آخرین خرید", "customer", category="مشتری")(
    (lambda p, store: _date_cond(p, with_within=True), lambda p, ctx: _date_matches(ctx.facts.last_purchase, p, ctx.now)))


def _days_since_eval(p, ctx):
    last = ctx.facts.last_purchase
    if last is None:
        return False
    return _compare((ctx.now.date() - last.date()).days, p)


leaf("days_since_last_purchase", "روزهایِ گذشته از آخرین خرید", "customer", category="مشتری")(
    (lambda p, store: _op_value(p, integer=True), _days_since_eval))


def _customer_type_validate(p, store):
    if p.get("value") not in ("new", "returning"):
        raise RuleError("نوعِ مشتری باید new یا returning باشد.")
    return {"value": p["value"]}


leaf("customer_type", "مشتریِ جدید/بازگشتی", "customer", category="مشتری",
     help="جدید: کمتر از دو خریدِ معتبر؛ بازگشتی: دو خریدِ معتبر یا بیشتر.")(
    (_customer_type_validate,
     lambda p, ctx: (ctx.facts.lifetime_orders >= 2) == (p["value"] == "returning")))


def _activity_validate(p, store):
    if p.get("value") not in ("active", "inactive"):
        raise RuleError("وضعیتِ فعالیت باید active یا inactive باشد.")
    days = _decimal(p.get("days", 90), "days")
    if days < 1 or days != days.to_integral_value():
        raise RuleError("تعدادِ روز باید عددِ صحیحِ مثبت باشد.")
    return {"value": p["value"], "days": int(days)}


def _activity_eval(p, ctx):
    last = ctx.facts.last_purchase
    recent = last is not None and (ctx.now.date() - last.date()).days <= p["days"]
    return recent if p["value"] == "active" else not recent


leaf("activity", "مشتریِ فعال/غیرفعال", "customer", category="مشتری")((_activity_validate, _activity_eval))


def _participation_validate(p, store):
    from apps.engagement.models import Campaign

    ids = _int_list(p, "campaign_ids")
    _check_store_ids(store, Campaign, ids or [], "کمپین")
    return {"campaign_ids": ids or [], "participated": bool(p.get("participated", True))}


def _participation_eval(p, ctx):
    hit = bool(ctx.facts.campaign_ids & set(p["campaign_ids"])) if p["campaign_ids"] else bool(ctx.facts.campaign_ids)
    return hit if p["participated"] else not hit


leaf("campaign_participation", "مشارکت در کمپینِ قبلی", "customer", category="تخفیف")((_participation_validate, _participation_eval))


def _redemption_validate(p, store):
    from apps.cart.models import Coupon

    ids = _int_list(p, "coupon_ids")
    _check_store_ids(store, Coupon, ids or [], "کد تخفیف")
    return {"coupon_ids": ids or [], "redeemed": bool(p.get("redeemed", True))}


def _redemption_eval(p, ctx):
    hit = bool(ctx.facts.redeemed_coupon_ids & set(p["coupon_ids"])) if p["coupon_ids"] else bool(ctx.facts.redeemed_coupon_ids)
    return hit if p["redeemed"] else not hit


leaf("coupon_redemption", "استفاده‌ی قبلی از کدِ تخفیف", "customer", category="تخفیف")((_redemption_validate, _redemption_eval))


# ----------------------------------------------------------------- اعتبارسنجی و ارزیابی درخت


def validate_tree(tree, store) -> dict:
    """درخت را اعتبارسنجی و نرمال می‌کند؛ ``RuleError`` با مسیرِ گره در پیام."""
    if tree in (None, {}, ""):
        return {}
    count = {"n": 0}

    def walk(node, depth, path):
        count["n"] += 1
        if count["n"] > MAX_NODES:
            raise RuleError(f"تعدادِ گره‌هایِ قاعده بیش از {MAX_NODES} است.")
        if depth > MAX_DEPTH:
            raise RuleError(f"عمقِ تودرتوییِ قواعد بیش از {MAX_DEPTH} است.")
        if not isinstance(node, dict):
            raise RuleError(f"{path}: گره باید شیء باشد.")
        kind = node.get("type")
        if kind == "group":
            op = node.get("op", "and")
            if op not in ("and", "or"):
                raise RuleError(f"{path}: عملگرِ گروه باید and یا or باشد.")
            children = node.get("children")
            if not isinstance(children, list) or not children:
                raise RuleError(f"{path}: گروه باید حداقل یک شرط داشته باشد.")
            return {
                "type": "group", "op": op, "negate": bool(node.get("negate", False)),
                "children": [walk(c, depth + 1, f"{path}.{i + 1}") for i, c in enumerate(children)],
            }
        spec = LEAVES.get(kind)
        if spec is None:
            raise RuleError(f"{path}: نوعِ شرطِ «{kind}» مجاز نیست.")
        try:
            params = spec.validate(node, store)
        except RuleError as exc:
            raise RuleError(f"{path} ({spec.label}): {exc}") from exc
        return {"type": kind, **params}

    return walk(tree, 1, "شرط")


def iter_leaves(tree):
    if not tree:
        return
    if tree.get("type") == "group":
        for child in tree["children"]:
            yield from iter_leaves(child)
    else:
        yield tree


def needs_orders(tree) -> bool:
    return any(LEAVES[n["type"]].level in ("line", "order") for n in iter_leaves(tree))


def evaluate(node, ctx: EvalContext) -> bool:
    if not node:
        return True
    if node["type"] == "group":
        results = (evaluate(child, ctx) for child in node["children"])
        outcome = all(results) if node["op"] == "and" else any(results)
        return (not outcome) if node.get("negate") else outcome
    return bool(LEAVES[node["type"]].evaluate(node, ctx))


def is_eligible(tree, *, scope: str, facts, orders, all_orders, now, amount_basis="net_total") -> bool:
    """ارزیابیِ یک مشتری. در ``same_order`` همه‌ی شرط‌ها باید با *یک* سفارش برقرار شوند."""
    if not tree:
        return True
    if scope == "same_order" and needs_orders(tree):
        return any(
            evaluate(tree, EvalContext(facts=facts, orders=[order], all_orders=all_orders, now=now, amount_basis=amount_basis))
            for order in orders
        )
    return evaluate(tree, EvalContext(facts=facts, orders=orders, all_orders=all_orders, now=now, amount_basis=amount_basis))


def leaf_catalog() -> list[dict]:
    """فهرستِ برگ‌هایِ قابل‌استفاده برایِ UI (برچسب/دسته)."""
    return [{"key": s.key, "label": s.label, "category": s.category, "level": s.level, "help": s.help} for s in LEAVES.values()]
