"""توصیفِ فیلدهایِ UI برایِ هر برگِ قاعده — سازنده‌ی بصریِ قواعد (rule builder) از
این ساختار می‌خوانَد؛ هیچ منطقِ اعتبارسنجی این‌جا نیست (مرجعِ حقیقت:
``rules.LEAVES[...].validate`` سمتِ سرور)."""

from apps.customers.models import CustomerSegment, CustomerTag
from apps.engagement.models import Campaign
from apps.engagement.services import rules

OP_CHOICES = [(k, v) for k, v in rules.OP_LABELS.items()]
DATE_MODES = [("between", "بینِ دو تاریخ"), ("before", "پیش از"), ("after", "پس از"), ("within_days", "در N روزِ اخیر")]
ORDER_STATUS = [("pending", "در انتظار"), ("processing", "در حال پردازش"), ("shipped", "ارسال‌شده"), ("delivered", "تحویل‌شده"), ("canceled", "لغوشده")]
PAYMENT_STATUS = [("pending", "در انتظار پرداخت"), ("paid", "پرداخت‌شده"), ("failed", "ناموفق"), ("refunded", "مسترد")]
WEEKDAYS = [(5, "شنبه"), (6, "یکشنبه"), (0, "دوشنبه"), (1, "سه‌شنبه"), (2, "چهارشنبه"), (3, "پنج‌شنبه"), (4, "جمعه")]


def _op(integer=False, basis=False):
    fields = [
        {"name": "op", "type": "select", "label": "شرط", "options": OP_CHOICES, "default": "gte"},
        {"name": "value", "type": "number", "label": "مقدار", "integer": integer},
        {"name": "value2", "type": "number", "label": "تا (برایِ «بین»)", "integer": integer, "show_if": {"op": "between"}},
    ]
    if basis:
        fields.append({"name": "basis", "type": "select", "label": "مبنای مبلغ", "options": [
            ("", "طبقِ تنظیمِ کمپین"), ("net_total", "خالص"), ("grand_total", "مبلغ فاکتور"), ("items_total", "جمعِ کالاها")]})
    return fields


def _date():
    return [
        {"name": "mode", "type": "select", "label": "نوعِ تاریخ", "options": DATE_MODES, "default": "between"},
        {"name": "date", "type": "date", "label": "تاریخ (شمسی ۱۴۰۵/۰۷/۰۱)", "show_if": {"mode": ["before", "after"]}},
        {"name": "start", "type": "date", "label": "از تاریخ", "show_if": {"mode": "between"}},
        {"name": "end", "type": "date", "label": "تا تاریخ", "show_if": {"mode": "between"}},
        {"name": "days", "type": "int", "label": "روز", "show_if": {"mode": "within_days"}},
    ]


def _ids(name, source, label):
    return {"name": name, "type": "ids", "source": source, "label": label}


FIELDS = {
    "line_match": [
        _ids("category_ids", "categories", "دسته (شاملِ زیرمجموعه‌ها)"), _ids("brand_ids", "brands", "برند"),
        {"name": "brand_names", "type": "text_list", "label": "نامِ برند (جداشده با ویرگول)"},
        {"name": "colors", "type": "text_list", "label": "رنگ (مثلاً زیتونی)"},
        {"name": "sizes", "type": "text_list", "label": "سایز"},
        {"name": "skus", "type": "text_list", "label": "SKU"},
        {"name": "product_ids", "type": "int_list", "label": "شناسه‌ی کالا (عدد، با ویرگول)"},
        {"name": "price_min", "type": "number", "label": "حداقل قیمتِ واحد"}, {"name": "price_max", "type": "number", "label": "حداکثر قیمتِ واحد"},
        {"name": "min_quantity", "type": "int", "label": "حداقل تعداد", "default": 1},
    ],
    "all_products": [{"name": "product_ids", "type": "int_list", "label": "شناسه‌ی کالاهایِ الزامی (با ویرگول)"}],
    "order_total": _op(basis=True), "any_order_total": _op(basis=True),
    "order_count": _op(True), "item_count": _op(True),
    "shipping_province": [{"name": "values", "type": "text_list", "label": "استان‌ها (با ویرگول)"}],
    "shipping_city": [{"name": "values", "type": "text_list", "label": "شهرها (با ویرگول؛ مثلاً شیراز)"}],
    "order_status": [{"name": "values", "type": "multi", "label": "وضعیت‌ها", "options": ORDER_STATUS}],
    "payment_status": [{"name": "values", "type": "multi", "label": "وضعیت‌ها", "options": PAYMENT_STATUS}],
    "payment_method": [_ids("ids", "gateways", "روش‌هایِ پرداخت")],
    "shipping_method": [_ids("ids", "shipping", "روش‌هایِ ارسال")],
    "shipping_cost": _op(),
    "used_coupon": [_ids("coupon_ids", "coupons", "کدهایِ تخفیف (خالی = هر کد)"), {"name": "used", "type": "bool", "label": "استفاده کرده باشد", "default": True}],
    "had_discount": [],
    "order_weekday": [{"name": "values", "type": "int_multi", "label": "روزهایِ هفته", "options": WEEKDAYS}],
    "order_hour": [{"name": "start", "type": "int", "label": "از ساعت"}, {"name": "end", "type": "int", "label": "تا ساعت (۱–۲۴)"}],
    "order_history": [
        {"name": "state", "type": "select", "label": "سابقه", "options": [("canceled", "لغو"), ("returned", "مرجوعی"), ("refunded", "استرداد")]},
        {"name": "exists", "type": "bool", "label": "وجود داشته باشد", "default": True},
    ],
    "customer_ids": [{"name": "ids", "type": "int_list", "label": "شناسه‌ی مشتریان (با ویرگول)"}],
    "segment_ids": [_ids("ids", "segments", "گروه‌هایِ مشتری")],
    "customer_tag_ids": [_ids("ids", "tags", "برچسب‌ها")],
    "registered": _date(), "first_purchase": _date(), "last_purchase": _date(),
    "customer_city": [{"name": "values", "type": "text_list", "label": "شهرها"}],
    "customer_province": [{"name": "values", "type": "text_list", "label": "استان‌ها"}],
    "birthday": [
        {"name": "mode", "type": "select", "label": "تولد", "options": [("today", "امروز"), ("this_month", "در این ماه"), ("month", "در ماهِ مشخص")], "default": "today"},
        {"name": "month", "type": "int", "label": "ماه (۱–۱۲)", "show_if": {"mode": "month"}},
    ],
    "age": [{"name": "min", "type": "int", "label": "حداقل سن"}, {"name": "max", "type": "int", "label": "حداکثر سن"}],
    "lifetime_orders": _op(True), "lifetime_spent": _op(), "average_order_value": _op(),
    "days_since_last_purchase": _op(True),
    "customer_type": [{"name": "value", "type": "select", "label": "نوع", "options": [("new", "جدید"), ("returning", "بازگشتی")]}],
    "activity": [
        {"name": "value", "type": "select", "label": "وضعیت", "options": [("active", "فعال"), ("inactive", "غیرفعال")]},
        {"name": "days", "type": "int", "label": "در N روزِ اخیر", "default": 90},
    ],
    "campaign_participation": [_ids("campaign_ids", "campaigns", "کمپین‌ها (خالی = هر کمپین)"), {"name": "participated", "type": "bool", "label": "مشارکت کرده باشد", "default": True}],
    "coupon_redemption": [_ids("coupon_ids", "coupons", "کدها (خالی = هر کد)"), {"name": "redeemed", "type": "bool", "label": "استفاده کرده باشد", "default": True}],
}


def build_schema(store) -> dict:
    """داده‌ی کاملِ سازنده: برگ‌ها + گزینه‌هایِ وابسته به Store (فقط همین Store)."""
    from apps.cart.models import Coupon
    from apps.catalog.models import Brand, Category
    from apps.orders.models import PaymentGateway, ShippingMethod

    def opts(qs, label="name"):
        return [[obj.pk, getattr(obj, label)] for obj in qs[:500]]

    sources = {
        "categories": opts(Category.objects.filter(store=store).order_by("name")),
        "brands": opts(Brand.objects.filter(store=store).order_by("name")),
        "gateways": opts(PaymentGateway.objects.filter(store=store).order_by("name")),
        "shipping": opts(ShippingMethod.objects.filter(store=store).order_by("name")),
        "segments": opts(CustomerSegment.objects.filter(store=store).order_by("name")),
        "tags": opts(CustomerTag.objects.filter(store=store, is_active=True).order_by("name")),
        "campaigns": opts(Campaign.objects.filter(store=store).order_by("name")),
        "coupons": [[c.pk, c.code] for c in Coupon.objects.filter(store=store).order_by("-created_at")[:500]],
    }
    leaves = [
        {**leaf, "fields": FIELDS.get(leaf["key"], [])} for leaf in rules.leaf_catalog()
    ]
    return {"leaves": leaves, "sources": sources}
