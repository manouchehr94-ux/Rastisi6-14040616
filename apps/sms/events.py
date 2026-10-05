"""تعریف رویدادهای پیامکی، متغیرهای مجاز هر رویداد، و متن پیش‌فرض قالب‌ها.

این ماژول تنها منبع حقیقت برای «کدام متغیر در کدام رویداد مجاز است» است؛ هم
اعتبارسنجی قالب (apps.sms.services.sms_service) و هم نمایش راهنما در پنل
مدیریت از همین دیکشنری‌ها می‌خوانند — چیزی در تمپلیت هاردکد نشده.
"""

from django.db import models


class SmsEvent(models.TextChoices):
    PLATFORM_OWNER_OTP = "platform_owner_otp", "OTP ثبت‌نام / ورود مالک فروشگاه"
    PLATFORM_TEST = "platform_test", "تست زیرساخت پیامک"
    NOTIFICATION = "notification", "اعلان عمومی / امنیتی"
    WELCOME = "welcome", "ثبت‌نام / خوش‌آمدگویی"
    OTP = "otp", "کد ورود یکبار مصرف"
    ORDER_PLACED = "order_placed", "ثبت سفارش"
    PAYMENT_SUCCESS = "payment_success", "پرداخت موفق"
    PAYMENT_FAILED = "payment_failed", "پرداخت ناموفق"
    ORDER_PROCESSING = "order_processing", "سفارش در حال پردازش"
    ORDER_SHIPPED = "order_shipped", "ارسال سفارش"
    ORDER_DELIVERED = "order_delivered", "تحویل سفارش"
    ORDER_CANCELED = "order_canceled", "لغو سفارش"
    # --- کمپین و مناسبت: متن را فقط راستی‌سی مدیریت می‌کند (فروشنده فقط روشن/خاموش می‌کند) ---
    OCC_BIRTHDAY_BEFORE = "occ_birthday_before", "مناسبت · تولد · پیش از روز تولد (با هدیه)"
    OCC_BIRTHDAY_ON = "occ_birthday_on", "مناسبت · تولد · روز تولد (با هدیه)"
    OCC_BIRTHDAY_AFTER = "occ_birthday_after", "مناسبت · تولد · پس از روز تولد (با هدیه)"
    OCC_BIRTHDAY_BEFORE_NOGIFT = "occ_birthday_before_nogift", "مناسبت · تولد · پیش از روز تولد (فقط تبریک)"
    OCC_BIRTHDAY_ON_NOGIFT = "occ_birthday_on_nogift", "مناسبت · تولد · روز تولد (فقط تبریک)"
    OCC_BIRTHDAY_AFTER_NOGIFT = "occ_birthday_after_nogift", "مناسبت · تولد · پس از روز تولد (فقط تبریک)"
    OCC_GENERIC_BEFORE = "occ_generic_before", "مناسبت · سایر مناسبت‌ها · پیش از مناسبت (با هدیه)"
    OCC_GENERIC_ON = "occ_generic_on", "مناسبت · سایر مناسبت‌ها · روز مناسبت (با هدیه)"
    OCC_GENERIC_AFTER = "occ_generic_after", "مناسبت · سایر مناسبت‌ها · پس از مناسبت (با هدیه)"
    OCC_GENERIC_BEFORE_NOGIFT = "occ_generic_before_nogift", "مناسبت · سایر مناسبت‌ها · پیش از مناسبت (فقط تبریک)"
    OCC_GENERIC_ON_NOGIFT = "occ_generic_on_nogift", "مناسبت · سایر مناسبت‌ها · روز مناسبت (فقط تبریک)"
    OCC_GENERIC_AFTER_NOGIFT = "occ_generic_after_nogift", "مناسبت · سایر مناسبت‌ها · پس از مناسبت (فقط تبریک)"
    CAMP_OFFER_PERCENT = "camp_offer_percent", "کمپین تخفیف · تخفیف درصدی"
    CAMP_OFFER_FIXED = "camp_offer_fixed", "کمپین تخفیف · تخفیف مبلغی"
    CAMP_OFFER_FREE_SHIP = "camp_offer_free_ship", "کمپین تخفیف · ارسال رایگان"
    CAMP_ANNOUNCE = "camp_announce", "کمپین تخفیف · اطلاع‌رسانی بدون کد"
    CAMP_EXPIRY_REMINDER = "camp_expiry_reminder", "کمپین/مناسبت · یادآوری نزدیک‌شدن انقضای کد"


# متغیرهای مجاز هر رویداد: کد متغیر -> برچسب فارسی (برای راهنمای پنل مدیریت)
EVENT_VARIABLES: dict[str, dict[str, str]] = {
    SmsEvent.PLATFORM_OWNER_OTP: {"otp_code": "کد یکبار مصرف", "expire_minutes": "دقیقه اعتبار"},
    SmsEvent.PLATFORM_TEST: {},
    SmsEvent.NOTIFICATION: {"message": "متن اعلان"},
    SmsEvent.WELCOME: {"customer_name": "نام مشتری", "shop_name": "نام فروشگاه"},
    SmsEvent.OTP: {"otp_code": "کد یکبار مصرف", "expire_minutes": "دقیقه اعتبار", "shop_name": "نام فروشگاه"},
    SmsEvent.ORDER_PLACED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.PAYMENT_SUCCESS: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ پرداخت‌شده", "shop_name": "نام فروشگاه",
    },
    SmsEvent.PAYMENT_FAILED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "amount": "مبلغ سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_PROCESSING: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_SHIPPED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش",
        "tracking_code": "کد رهگیری مرسوله", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_DELIVERED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
    SmsEvent.ORDER_CANCELED: {
        "customer_name": "نام مشتری", "order_code": "کد سفارش", "shop_name": "نام فروشگاه",
    },
}

DEFAULT_TEMPLATES: dict[str, str] = {
    SmsEvent.PLATFORM_OWNER_OTP: "کد تأیید راستیسی: {otp_code}\nاین کد تا {expire_minutes} دقیقه معتبر است.",
    SmsEvent.PLATFORM_TEST: "پیامک آزمایشی راستیسی",
    SmsEvent.NOTIFICATION: "{message}",
    SmsEvent.WELCOME: "{customer_name} عزیز، به {shop_name} خوش آمدید! از این پس می‌توانید با کد یکبار مصرف هم وارد حساب خود شوید.",
    SmsEvent.OTP: "کد ورود شما به {shop_name}: {otp_code}\nاین کد تا ۲ دقیقه معتبر است.",
    SmsEvent.ORDER_PLACED: "{customer_name} عزیز، سفارش {order_code} به مبلغ {amount} تومان با موفقیت ثبت شد. {shop_name}",
    SmsEvent.PAYMENT_SUCCESS: "{customer_name} عزیز، پرداخت سفارش {order_code} به مبلغ {amount} تومان با موفقیت انجام شد. {shop_name}",
    SmsEvent.PAYMENT_FAILED: "{customer_name} عزیز، پرداخت سفارش {order_code} ناموفق بود. برای پیگیری به حساب کاربری خود مراجعه کنید. {shop_name}",
    SmsEvent.ORDER_PROCESSING: "{customer_name} عزیز، سفارش {order_code} شما در حال پردازش و بسته‌بندی است. {shop_name}",
    SmsEvent.ORDER_SHIPPED: "{customer_name} عزیز، سفارش {order_code} ارسال شد. کد رهگیری: {tracking_code} — {shop_name}",
    SmsEvent.ORDER_DELIVERED: "{customer_name} عزیز، سفارش {order_code} به شما تحویل داده شد. از خرید شما سپاسگزاریم. {shop_name}",
    SmsEvent.ORDER_CANCELED: "{customer_name} عزیز، سفارش {order_code} لغو شد. {shop_name}",
}


# ---------------------------------------------------------------------------
# پیامک‌های کمپین و مناسبت — «متنِ پلتفرم‌محور»
#
# قالبِ این رویدادها فقط توسط مدیرانِ راستی‌سی (پنلِ ادمین پلتفرم) ویرایش می‌شود. فروشنده
# هرگز نمی‌تواند آن را ویرایش یا جایگزین کند (نه از فرمِ کمپین، نه از «قالب‌هایِ اعلان»،
# نه از «تنظیماتِ پیامک»). پیش‌نمایشِ فرمِ کمپین و ارسالِ واقعی هر دو از همین ردیف‌ها
# خوانده می‌شوند. قالب‌هایِ «فقط تبریک» عمداً متغیرِ هدیه/کد ندارند تا وعده‌یِ
# هدیه‌یِ ناموجود ممکن نباشد.
# ---------------------------------------------------------------------------

_V_BASE = {"customer_name": "نام مشتری", "shop_name": "نام فروشگاه"}
_V_OCC = {**_V_BASE, "occasion_name": "نام مناسبت"}
_V_GIFT = {
    **_V_OCC, "discount_code": "کد تخفیف", "discount_amount": "مقدار هدیه (مثلاً ۱۵٪ یا ارسال رایگان)",
    "discount_expires_at": "مهلت استفاده (تاریخ شمسی)",
}
_V_CAMP = {**_V_BASE, "campaign_name": "نام کمپین"}
_V_CAMP_GIFT = {
    **_V_CAMP, "discount_code": "کد تخفیف", "discount_amount": "مقدار هدیه (مثلاً ۱۵٪ یا ارسال رایگان)",
    "discount_expires_at": "مهلت استفاده (تاریخ شمسی)",
}

_E = SmsEvent
EVENT_VARIABLES.update({
    _E.OCC_BIRTHDAY_BEFORE: _V_GIFT, _E.OCC_BIRTHDAY_ON: _V_GIFT, _E.OCC_BIRTHDAY_AFTER: _V_GIFT,
    _E.OCC_GENERIC_BEFORE: _V_GIFT, _E.OCC_GENERIC_ON: _V_GIFT, _E.OCC_GENERIC_AFTER: _V_GIFT,
    _E.OCC_BIRTHDAY_BEFORE_NOGIFT: _V_BASE, _E.OCC_BIRTHDAY_ON_NOGIFT: _V_BASE, _E.OCC_BIRTHDAY_AFTER_NOGIFT: _V_BASE,
    _E.OCC_GENERIC_BEFORE_NOGIFT: _V_OCC, _E.OCC_GENERIC_ON_NOGIFT: _V_OCC, _E.OCC_GENERIC_AFTER_NOGIFT: _V_OCC,
    _E.CAMP_OFFER_PERCENT: _V_CAMP_GIFT, _E.CAMP_OFFER_FIXED: _V_CAMP_GIFT, _E.CAMP_OFFER_FREE_SHIP: _V_CAMP_GIFT,
    _E.CAMP_ANNOUNCE: _V_CAMP,
    _E.CAMP_EXPIRY_REMINDER: {
        **_V_CAMP, "discount_code": "کد تخفیف", "discount_expires_at": "مهلت استفاده (تاریخ شمسی)",
        "days_left": "روزهای باقی‌مانده",
    },
})

DEFAULT_TEMPLATES.update({
    _E.OCC_BIRTHDAY_BEFORE: "{customer_name} عزیز، تولدتان نزدیک است! {shop_name} هدیه‌ای برایتان کنار گذاشته: کد تخفیف {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_BIRTHDAY_ON: "{customer_name} عزیز، تولدتان مبارک! هدیه شما از {shop_name}: کد تخفیف {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_BIRTHDAY_AFTER: "{customer_name} عزیز، امیدواریم تولد خوبی داشتید! هدیه تولد شما از {shop_name}: کد تخفیف {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_BIRTHDAY_BEFORE_NOGIFT: "{customer_name} عزیز، تولدتان نزدیک است! {shop_name} برایتان روزی پر از شادی آرزو می‌کند.",
    _E.OCC_BIRTHDAY_ON_NOGIFT: "{customer_name} عزیز، تولدتان مبارک! {shop_name} برایتان سالی سرشار از شادی آرزو می‌کند.",
    _E.OCC_BIRTHDAY_AFTER_NOGIFT: "{customer_name} عزیز، امیدواریم تولد خوبی داشتید! {shop_name}",
    _E.OCC_GENERIC_BEFORE: "{customer_name} عزیز، «{occasion_name}» نزدیک است! هدیه شما از {shop_name}: کد تخفیف {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_GENERIC_ON: "{customer_name} عزیز، به مناسبت «{occasion_name}» هدیه‌ای از {shop_name} دارید: کد {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_GENERIC_AFTER: "{customer_name} عزیز، امیدواریم «{occasion_name}» خوش گذشته باشد. هدیه شما از {shop_name}: کد {discount_code}، {discount_amount}، اعتبار تا {discount_expires_at}.",
    _E.OCC_GENERIC_BEFORE_NOGIFT: "{customer_name} عزیز، «{occasion_name}» نزدیک است و {shop_name} به یاد شماست.",
    _E.OCC_GENERIC_ON_NOGIFT: "{customer_name} عزیز، به مناسبت «{occasion_name}» {shop_name} به یاد شماست و برایتان روزی خوب آرزو می‌کند.",
    _E.OCC_GENERIC_AFTER_NOGIFT: "{customer_name} عزیز، امیدواریم «{occasion_name}» برایتان خوش گذشته باشد. {shop_name}",
    _E.CAMP_OFFER_PERCENT: "{customer_name} عزیز، «{campaign_name}» در {shop_name}: {discount_amount} تخفیف با کد {discount_code}، اعتبار تا {discount_expires_at}.",
    _E.CAMP_OFFER_FIXED: "{customer_name} عزیز، «{campaign_name}» در {shop_name}: {discount_amount} تخفیف با کد {discount_code}، اعتبار تا {discount_expires_at}.",
    _E.CAMP_OFFER_FREE_SHIP: "{customer_name} عزیز، «{campaign_name}» در {shop_name}: ارسال رایگان با کد {discount_code}، اعتبار تا {discount_expires_at}.",
    _E.CAMP_ANNOUNCE: "{customer_name} عزیز، «{campaign_name}» در {shop_name} آغاز شد. برای دیدن جزئیات به حساب کاربری‌تان سر بزنید.",
    _E.CAMP_EXPIRY_REMINDER: "{customer_name} عزیز، کد تخفیف {discount_code} شما در {shop_name} تا {discount_expires_at} ({days_left} روز دیگر) معتبر است.",
})

#: رویدادهایی که متنشان فقط در اختیارِ پلتفرم است؛ هرگز در صفحه‌هایِ ویرایشِ قالبِ فروشگاه نمایش یا ویرایش نمی‌شوند.
PLATFORM_MANAGED_EVENTS = frozenset({
    _E.OCC_BIRTHDAY_BEFORE, _E.OCC_BIRTHDAY_ON, _E.OCC_BIRTHDAY_AFTER,
    _E.OCC_BIRTHDAY_BEFORE_NOGIFT, _E.OCC_BIRTHDAY_ON_NOGIFT, _E.OCC_BIRTHDAY_AFTER_NOGIFT,
    _E.OCC_GENERIC_BEFORE, _E.OCC_GENERIC_ON, _E.OCC_GENERIC_AFTER,
    _E.OCC_GENERIC_BEFORE_NOGIFT, _E.OCC_GENERIC_ON_NOGIFT, _E.OCC_GENERIC_AFTER_NOGIFT,
    _E.CAMP_OFFER_PERCENT, _E.CAMP_OFFER_FIXED, _E.CAMP_OFFER_FREE_SHIP, _E.CAMP_ANNOUNCE, _E.CAMP_EXPIRY_REMINDER,
})

#: رویدادهایی که هرگز در فهرستِ قالب‌هایِ پیامکِ فروشگاه دیده نمی‌شوند (پلتفرم‌محور + اختصاصیِ پلتفرم).
STORE_HIDDEN_EVENTS = frozenset({
    SmsEvent.PLATFORM_OWNER_OTP, SmsEvent.PLATFORM_TEST, SmsEvent.NOTIFICATION, *PLATFORM_MANAGED_EVENTS,
})
