"""رجیستریِ رویدادهایِ اعلان — تنها منبعِ حقیقتِ «کدام رویداد، با چه متغیرهایی،
برایِ چه مخاطبی، با چه دسته‌ای (تراکنشی/امنیتی/تبلیغاتی)».

* ``TRANSACTIONAL`` و ``SECURITY``: وابسته به رضایتِ تبلیغاتی نیستند (سفارش،
  پرداخت، امنیت حساب…).
* ``PROMOTIONAL``: فقط با رضایتِ مشتری برایِ همان کانال ارسال می‌شود.

هر رویداد فهرستِ صریحِ متغیرهایِ مجاز دارد؛ قالب‌ها فقط با همین متغیرها
اعتبارسنجی/رندر می‌شوند (``template_service``). هیچ متغیرِ حساس (رمز، توکن،
OTP، اطلاعاتِ پرداخت) در هیچ رویدادی تعریف نشده است.

رویدادهایی که ``legacy_sms_event`` دارند همچنان پیامکشان را از مسیرِ قدیمیِ
``apps.sms`` (قالبِ ``SmsTemplate``) می‌فرستند؛ این سیستم برایِ آن‌ها فقط
**ایمیل** (و در صورت تعریفِ مخاطبِ کارکنان، اعلانِ داخلی) را اضافه می‌کند تا
پیامکِ تکراری ارسال نشود.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TRANSACTIONAL = "transactional"
SECURITY = "security"
PROMOTIONAL = "promotional"

CATEGORY_LABELS = {
    TRANSACTIONAL: "تراکنشی",
    SECURITY: "امنیتی",
    PROMOTIONAL: "تبلیغاتی",
}

AUDIENCE_CUSTOMER = "customer"
AUDIENCE_STAFF = "staff"

SMS = "sms"
EMAIL = "email"
CHANNELS = (SMS, EMAIL)

COMMON_VARS = {"store_name": "نام فروشگاه"}
CUSTOMER_VARS = {"customer_name": "نام مشتری", **COMMON_VARS}
ORDER_VARS = {
    **CUSTOMER_VARS,
    "order_number": "شماره سفارش",
    "order_total": "مبلغ سفارش (تومان)",
    "order_status": "وضعیت سفارش",
    "order_url": "پیوند مشاهده‌ی سفارش",
}
SHIPPING_VARS = {
    **ORDER_VARS,
    "tracking_number": "کد رهگیری مرسوله",
    "tracking_url": "پیوند پیگیری سفارش",
}
DISCOUNT_VARS = {
    **CUSTOMER_VARS,
    "discount_code": "کد تخفیف",
    "discount_amount": "مقدار تخفیف (مثلاً ۳۰٪ یا ۵۰۰٬۰۰۰ تومان)",
    "discount_max": "سقف تخفیف (تومان)",
    "discount_expires_at": "تاریخ انقضای کد (شمسی)",
    "campaign_name": "نام کمپین/مناسبت",
}
OCCASION_VARS = {
    **DISCOUNT_VARS,
    "occasion_name": "نام مناسبت",
}


@dataclass(frozen=True)
class EventDef:
    key: str
    label: str
    category: str
    variables: dict
    audience: str = AUDIENCE_CUSTOMER
    default_sms: str = ""
    default_email_subject: str = ""
    default_email_body: str = ""
    sms_enabled_default: bool = True
    email_enabled_default: bool = True
    #: اگر مقدار داشته باشد، پیامکِ این رویداد از مسیرِ قدیمیِ apps.sms ارسال می‌شود.
    legacy_sms_event: str = ""
    sample: dict = field(default_factory=dict)


_SAMPLE = {
    "customer_name": "سارا احمدی", "store_name": "فروشگاه نمونه", "order_number": "DM-12345",
    "order_total": "۲٬۵۰۰٬۰۰۰", "order_status": "در حال پردازش", "order_url": "https://example.com/account/orders/DM-12345/",
    "tracking_number": "RX123456789IR", "tracking_url": "https://example.com/account/orders/DM-12345/",
    "discount_code": "GIFT-AB12CD", "discount_amount": "۳۰٪", "discount_max": "۴٬۰۰۰٬۰۰۰",
    "discount_expires_at": "۱۴۰۵/۰۹/۳۰", "campaign_name": "کمپین ویژه", "occasion_name": "تولد شما",
    "return_number": "RT-1001", "refund_amount": "۱٬۲۰۰٬۰۰۰", "product_title": "کیف چرم زیتونی",
    "rating": "۵", "reason": "—", "days_left": "۳",
}

EVENTS: dict[str, EventDef] = {}


def _register(*defs: EventDef) -> None:
    for d in defs:
        EVENTS[d.key] = EventDef(**{**d.__dict__, "sample": {k: _SAMPLE.get(k, "") for k in d.variables}})


_register(
    # ------------------------------------------------------------------ حساب کاربری
    EventDef(
        "account.registered", "ثبت‌نام و خوش‌آمدگویی", TRANSACTIONAL, CUSTOMER_VARS,
        default_sms="{customer_name} عزیز، به {store_name} خوش آمدید!",
        default_email_subject="به {store_name} خوش آمدید",
        default_email_body="{customer_name} عزیز،\nثبت‌نام شما در {store_name} با موفقیت انجام شد.\nاز خرید شما سپاسگزاریم.",
        legacy_sms_event="welcome",
    ),
    EventDef(
        "account.sensitive_changed", "تغییر اطلاعات حساس حساب", SECURITY, {**CUSTOMER_VARS, "changed_field": "اطلاعاتِ تغییرکرده"},
        default_sms="{customer_name} عزیز، {changed_field} حساب شما در {store_name} تغییر کرد. اگر شما نبودید با ما تماس بگیرید.",
        default_email_subject="تغییر اطلاعات حساب شما در {store_name}",
        default_email_body="{customer_name} عزیز،\n{changed_field} حساب شما در {store_name} تغییر کرد.\nاگر این تغییر را شما انجام نداده‌اید، فوراً با پشتیبانی تماس بگیرید.",
    ),
    # ------------------------------------------------------------------ سفارش و پرداخت
    EventDef(
        "order.created", "ثبت سفارش", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، سفارش {order_number} با مبلغ {order_total} تومان با موفقیت ثبت شد. {store_name}",
        default_email_subject="سفارش {order_number} ثبت شد",
        default_email_body="{customer_name} عزیز،\nسفارش شما با شماره {order_number} و مبلغ {order_total} تومان با موفقیت ثبت شد.\nپیگیری سفارش: {order_url}\nاز خرید شما سپاسگزاریم.",
        legacy_sms_event="order_placed",
    ),
    EventDef(
        "payment.succeeded", "پرداخت موفق", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، پرداخت سفارش {order_number} به مبلغ {order_total} تومان موفق بود. {store_name}",
        default_email_subject="پرداخت سفارش {order_number} موفق بود",
        default_email_body="{customer_name} عزیز،\nپرداخت سفارش {order_number} به مبلغ {order_total} تومان با موفقیت انجام شد.\n{order_url}",
        legacy_sms_event="payment_success",
    ),
    EventDef(
        "payment.failed", "پرداخت ناموفق", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، پرداخت سفارش {order_number} ناموفق بود. {store_name}",
        default_email_subject="پرداخت سفارش {order_number} ناموفق بود",
        default_email_body="{customer_name} عزیز،\nپرداخت سفارش {order_number} ناموفق بود. می‌توانید از حساب کاربری خود دوباره تلاش کنید.\n{order_url}",
        legacy_sms_event="payment_failed",
    ),
    EventDef(
        "order.processing", "سفارش در حال پردازش", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، سفارش {order_number} در حال پردازش و بسته‌بندی است. {store_name}",
        default_email_subject="سفارش {order_number} در حال پردازش است",
        default_email_body="{customer_name} عزیز،\nسفارش {order_number} در حال پردازش و بسته‌بندی است.\n{order_url}",
        legacy_sms_event="order_processing",
    ),
    EventDef(
        "order.shipped", "ارسال سفارش و کد رهگیری", TRANSACTIONAL, SHIPPING_VARS,
        default_sms="{customer_name} عزیز، سفارش {order_number} ارسال شد. کد رهگیری: {tracking_number} — {store_name}",
        default_email_subject="سفارش {order_number} ارسال شد",
        default_email_body="{customer_name} عزیز،\nسفارش {order_number} ارسال شد.\nکد رهگیری: {tracking_number}\nپیگیری: {tracking_url}",
        legacy_sms_event="order_shipped",
    ),
    EventDef(
        "order.delivered", "تحویل سفارش", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، سفارش {order_number} تحویل داده شد. از خرید شما سپاسگزاریم. {store_name}",
        default_email_subject="سفارش {order_number} تحویل داده شد",
        default_email_body="{customer_name} عزیز،\nسفارش {order_number} به شما تحویل داده شد. از خرید شما سپاسگزاریم.",
        legacy_sms_event="order_delivered",
    ),
    EventDef(
        "order.canceled", "لغو سفارش", TRANSACTIONAL, ORDER_VARS,
        default_sms="{customer_name} عزیز، سفارش {order_number} لغو شد. {store_name}",
        default_email_subject="سفارش {order_number} لغو شد",
        default_email_body="{customer_name} عزیز،\nسفارش {order_number} لغو شد. در صورت پرداخت، مبلغ طبق قوانین فروشگاه بازگردانده می‌شود.",
        legacy_sms_event="order_canceled",
    ),
    EventDef(
        "return.requested", "ثبت درخواست مرجوعی", TRANSACTIONAL, {**ORDER_VARS, "return_number": "شماره مرجوعی"},
        default_sms="{customer_name} عزیز، درخواست مرجوعی {return_number} برای سفارش {order_number} ثبت شد. {store_name}",
        default_email_subject="درخواست مرجوعی {return_number} ثبت شد",
        default_email_body="{customer_name} عزیز،\nدرخواست مرجوعی {return_number} برای سفارش {order_number} ثبت شد و در حال بررسی است.",
    ),
    EventDef(
        "return.approved", "تأیید مرجوعی", TRANSACTIONAL, {**ORDER_VARS, "return_number": "شماره مرجوعی"},
        default_sms="{customer_name} عزیز، مرجوعی {return_number} تأیید شد. {store_name}",
        default_email_subject="مرجوعی {return_number} تأیید شد",
        default_email_body="{customer_name} عزیز،\nدرخواست مرجوعی {return_number} برای سفارش {order_number} تأیید شد.",
    ),
    EventDef(
        "return.rejected", "رد مرجوعی", TRANSACTIONAL, {**ORDER_VARS, "return_number": "شماره مرجوعی", "reason": "دلیل رد"},
        default_sms="{customer_name} عزیز، مرجوعی {return_number} پذیرفته نشد. {store_name}",
        default_email_subject="مرجوعی {return_number} پذیرفته نشد",
        default_email_body="{customer_name} عزیز،\nدرخواست مرجوعی {return_number} برای سفارش {order_number} پذیرفته نشد.\nدلیل: {reason}",
    ),
    EventDef(
        "refund.completed", "تکمیل استرداد وجه", TRANSACTIONAL, {**ORDER_VARS, "refund_amount": "مبلغ استرداد (تومان)"},
        default_sms="{customer_name} عزیز، مبلغ {refund_amount} تومان بابت سفارش {order_number} بازگردانده شد. {store_name}",
        default_email_subject="استرداد وجه سفارش {order_number}",
        default_email_body="{customer_name} عزیز،\nمبلغ {refund_amount} تومان بابت سفارش {order_number} بازگردانده شد.",
    ),
    # ------------------------------------------------------------------ تخفیف و کمپین
    EventDef(
        "coupon.issued", "صدور کد تخفیف اختصاصی", PROMOTIONAL, DISCOUNT_VARS,
        default_sms="{customer_name} عزیز، کد تخفیف اختصاصی شما در {store_name}: {discount_code} ({discount_amount}) تا {discount_expires_at}",
        default_email_subject="کد تخفیف اختصاصی شما از {store_name}",
        default_email_body="{customer_name} عزیز،\nکد تخفیف اختصاصی شما: {discount_code}\nمقدار تخفیف: {discount_amount}\nاعتبار تا: {discount_expires_at}",
    ),
    EventDef(
        "coupon.expiring", "یادآوری نزدیک‌شدن انقضای کد", PROMOTIONAL, {**DISCOUNT_VARS, "days_left": "روزهای باقی‌مانده"},
        default_sms="{customer_name} عزیز، کد تخفیف {discount_code} شما {days_left} روز دیگر منقضی می‌شود. {store_name}",
        default_email_subject="کد تخفیف شما به‌زودی منقضی می‌شود",
        default_email_body="{customer_name} عزیز،\nکد تخفیف {discount_code} تا {discount_expires_at} ({days_left} روز دیگر) معتبر است.",
    ),
    EventDef(
        "coupon.redeemed", "استفاده موفق از کد تخفیف", TRANSACTIONAL, {**ORDER_VARS, "discount_code": "کد تخفیف", "discount_amount": "مقدار تخفیف"},
        default_sms="{customer_name} عزیز، کد {discount_code} روی سفارش {order_number} اعمال شد. {store_name}",
        default_email_subject="کد تخفیف {discount_code} اعمال شد",
        default_email_body="{customer_name} عزیز،\nکد تخفیف {discount_code} روی سفارش {order_number} اعمال شد.",
        sms_enabled_default=False, email_enabled_default=False,
    ),
    EventDef(
        "campaign.activated", "فعال‌شدن کمپین (اعلان داخلی)", TRANSACTIONAL,
        {"campaign_name": "نام کمپین", "eligible_count": "تعداد مشتریان مشمول", "store_name": "نام فروشگاه"},
        audience=AUDIENCE_STAFF,
        default_sms="کمپین «{campaign_name}» در {store_name} فعال شد.",
        default_email_subject="کمپین «{campaign_name}» فعال شد",
        default_email_body="کمپین «{campaign_name}» در {store_name} فعال شد.\nتعداد مشتریان مشمول: {eligible_count}",
        sms_enabled_default=False,
    ),
    EventDef(
        "reward.issued", "اعطای پاداش به مشتری", PROMOTIONAL, {**DISCOUNT_VARS, "reward_description": "شرح پاداش"},
        default_sms="{customer_name} عزیز، {reward_description} از {store_name} برای شما فعال شد.",
        default_email_subject="پاداش شما از {store_name}",
        default_email_body="{customer_name} عزیز،\n{reward_description}",
    ),
    # ------------------------------------------------------------------ مناسبت‌ها
    EventDef(
        "occasion.birthday_before", "یادآوری پیش از تولد", PROMOTIONAL, OCCASION_VARS,
        default_sms="{customer_name} عزیز، تولدتان نزدیک است! {store_name} هدیه‌ای برایتان دارد.",
        default_email_subject="تولدتان نزدیک است 🎂",
        default_email_body="{customer_name} عزیز،\nتولدتان نزدیک است و {store_name} هدیه‌ای برای شما آماده کرده است.",
    ),
    EventDef(
        "occasion.birthday", "تبریک تولد", PROMOTIONAL, OCCASION_VARS,
        default_sms="{customer_name} عزیز، تولدتان مبارک! کد هدیه شما: {discount_code} ({discount_amount}) تا {discount_expires_at} — {store_name}",
        default_email_subject="تولدتان مبارک 🎉",
        default_email_body="{customer_name} عزیز،\nتولدتان مبارک!\nکد هدیه شما: {discount_code}\nمقدار تخفیف: {discount_amount}\nاعتبار تا: {discount_expires_at}",
    ),
    EventDef(
        "occasion.birthday_after", "پیام پس از تولد", PROMOTIONAL, OCCASION_VARS,
        default_sms="{customer_name} عزیز، امیدواریم تولد خوبی داشتید! {store_name}",
        default_email_subject="امیدواریم تولد خوبی داشته باشید",
        default_email_body="{customer_name} عزیز،\nامیدواریم تولد خوبی داشته باشید. هدیه‌ی شما: {discount_code} تا {discount_expires_at}",
    ),
    EventDef(
        "occasion.generic", "مناسبت‌های دیگر (سالگرد، نقاط عطف، تعطیلات، مناسبت اختصاصی)", PROMOTIONAL, OCCASION_VARS,
        default_sms="{customer_name} عزیز، {occasion_name}! کد هدیه شما: {discount_code} ({discount_amount}) تا {discount_expires_at} — {store_name}",
        default_email_subject="{occasion_name} — هدیه‌ای از {store_name}",
        default_email_body="{customer_name} عزیز،\n{occasion_name}!\nکد هدیه شما: {discount_code}\nمقدار تخفیف: {discount_amount}\nاعتبار تا: {discount_expires_at}",
    ),
    # ------------------------------------------------------------------ داخلی / کارکنان
    EventDef(
        "staff.order_created", "سفارش جدید (اعلان به کارکنان)", TRANSACTIONAL,
        {"order_number": "شماره سفارش", "order_total": "مبلغ سفارش (تومان)", "customer_name": "نام مشتری", "store_name": "نام فروشگاه", "gift_wrap_note": "یادآوری کادوپیچی"},
        audience=AUDIENCE_STAFF,
        default_sms="سفارش جدید {order_number} به مبلغ {order_total} تومان از {customer_name}. {gift_wrap_note}",
        default_email_subject="سفارش جدید {order_number}",
        default_email_body="سفارش جدید {order_number} به مبلغ {order_total} تومان از {customer_name} ثبت شد.\n{gift_wrap_note}",
        sms_enabled_default=False, email_enabled_default=False,
    ),
    EventDef(
        "staff.return_requested", "درخواست مرجوعی جدید (اعلان به کارکنان)", TRANSACTIONAL,
        {"order_number": "شماره سفارش", "return_number": "شماره مرجوعی", "customer_name": "نام مشتری", "store_name": "نام فروشگاه"},
        audience=AUDIENCE_STAFF,
        default_sms="درخواست مرجوعی {return_number} برای سفارش {order_number} از {customer_name}.",
        default_email_subject="درخواست مرجوعی {return_number}",
        default_email_body="درخواست مرجوعی {return_number} برای سفارش {order_number} از {customer_name} ثبت شد.",
        sms_enabled_default=False, email_enabled_default=False,
    ),
    EventDef(
        "staff.review_created", "نظر جدید محصول (اعلان به کارکنان)", TRANSACTIONAL,
        {"product_title": "نام کالا", "rating": "امتیاز", "customer_name": "نام نظر‌دهنده", "store_name": "نام فروشگاه"},
        audience=AUDIENCE_STAFF,
        default_sms="نظر جدید با امتیاز {rating} برای «{product_title}» ثبت شد.",
        default_email_subject="نظر جدید برای «{product_title}»",
        default_email_body="{customer_name} برای «{product_title}» نظری با امتیاز {rating} ثبت کرد و در انتظار بررسی است.",
        sms_enabled_default=False, email_enabled_default=False,
    ),
)


def get_event(key: str) -> EventDef:
    try:
        return EVENTS[key]
    except KeyError as exc:
        raise KeyError(f"رویداد اعلانِ ناشناخته: {key}") from exc


def event_choices():
    return [(key, d.label) for key, d in EVENTS.items()]
