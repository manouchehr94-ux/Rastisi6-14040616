"""رجیستریِ کلیدهایِ Entitlement و Usage Metric — تنها منبعِ حقیقتِ
کلیدهایِ ماشین‌خوانِ پایدار (Checkpoint 5A). نگاه کنید به ADR-64.

هیچ‌جایِ کدبیس نباید یک کلیدِ Entitlement را به‌صورتِ رشته‌ی خام هاردکد کند؛
همیشه از این ثابت‌ها استفاده کنید تا غلطِ املایی به یک بررسیِ همیشه-غلط
تبدیل نشود."""

from apps.subscriptions.models import EntitlementDefinition

_T = EntitlementDefinition.EntitlementType

# --- کلیدهایِ قابلیت (boolean) و محدودیت (integer_limit) ---
# هر تعریف: (key, name, type, default_enabled)
ENTITLEMENT_DEFINITIONS = [
    # قابلیت‌هایِ کاتالوگ
    ("catalog.products", "کالاها", _T.INTEGER_LIMIT, True),
    ("catalog.variants", "تنوع‌ها", _T.INTEGER_LIMIT, True),
    ("catalog.attributes", "ویژگی‌ها", _T.BOOLEAN, True),
    ("catalog.industry_templates", "قالب‌هایِ صنف", _T.BOOLEAN, True),
    ("catalog.import", "ورود اطلاعات (Import)", _T.BOOLEAN, True),
    ("catalog.export", "خروج اطلاعات (Export)", _T.BOOLEAN, True),
    # سفارش‌ها
    ("orders.management", "مدیریتِ سفارش", _T.BOOLEAN, True),
    ("orders.refunds", "استرداد", _T.BOOLEAN, True),
    ("orders.returns", "مرجوعی", _T.BOOLEAN, True),
    # موجودی
    ("inventory.warehouses", "انبارها", _T.INTEGER_LIMIT, True),
    ("inventory.transfers", "انتقالِ انبار", _T.BOOLEAN, True),
    # ارسال/مالیات
    ("shipping.advanced", "ارسالِ پیشرفته", _T.BOOLEAN, True),
    ("tax.advanced", "مالیاتِ پیشرفته", _T.BOOLEAN, True),
    # مشتریان
    ("customers.crm", "CRM مشتری", _T.BOOLEAN, True),
    ("customers.segments", "سگمنت‌هایِ مشتری", _T.INTEGER_LIMIT, True),
    # محتوا/گزارش
    ("content.cms", "مدیریتِ محتوا (CMS)", _T.BOOLEAN, True),
    ("reports.basic", "گزارش‌هایِ پایه", _T.BOOLEAN, True),
    ("reports.advanced", "گزارش‌هایِ پیشرفته", _T.BOOLEAN, True),
    # کارکنان
    ("staff.members", "اعضایِ تیم", _T.INTEGER_LIMIT, True),
    ("staff.management", "مدیریتِ کارکنان", _T.BOOLEAN, True),
    # دامنه/یکپارچه‌سازی (رزرو برایِ آینده — کلیدها واقعی، سقف/رفتارشان بعداً)
    ("domains.custom", "دامنه‌ی اختصاصی", _T.BOOLEAN, False),
    ("integrations.api", "API", _T.BOOLEAN, False),
    ("integrations.webhooks", "Webhookها", _T.BOOLEAN, False),
    # محدودیت‌هایِ دوره‌ای (period-based؛ سنجش در usage_service)
    ("catalog.import_rows_monthly", "ردیف‌هایِ ورود اطلاعات در ماه", _T.INTEGER_LIMIT, True),
    ("catalog.exports_monthly", "دفعاتِ خروج اطلاعات در ماه", _T.INTEGER_LIMIT, True),
]

# دسترسیِ سریع به کلیدها به‌عنوانِ ثابت (برایِ استفاده در سرویس‌ها بدونِ رشته‌ی خام)
CATALOG_PRODUCTS = "catalog.products"
CATALOG_VARIANTS = "catalog.variants"
CATALOG_IMPORT = "catalog.import"
CATALOG_EXPORT = "catalog.export"
CATALOG_IMPORT_ROWS_MONTHLY = "catalog.import_rows_monthly"
CATALOG_EXPORTS_MONTHLY = "catalog.exports_monthly"
INVENTORY_WAREHOUSES = "inventory.warehouses"
CUSTOMERS_SEGMENTS = "customers.segments"
STAFF_MEMBERS = "staff.members"

#: کلیدهایِ Entitlement که یک «متریکِ مصرفِ شمارشی» متناظر دارند — نگاشت
#: کلید → توضیحِ کوتاه (برایِ UIِ Usage). سنجشِ واقعی در ``usage_service``.
COUNT_METRIC_KEYS = {
    CATALOG_PRODUCTS: "کالاها",
    CATALOG_VARIANTS: "تنوع‌ها",
    STAFF_MEMBERS: "اعضایِ تیم",
    INVENTORY_WAREHOUSES: "انبارها",
    CUSTOMERS_SEGMENTS: "سگمنت‌ها",
}

#: کلیدهایِ متریکِ دوره‌ای (بر اساسِ دوره‌ی صورتحساب صفر می‌شوند).
PERIOD_METRIC_KEYS = {
    CATALOG_IMPORT_ROWS_MONTHLY: "ردیف‌هایِ ورود اطلاعات (این دوره)",
    CATALOG_EXPORTS_MONTHLY: "دفعاتِ خروج اطلاعات (این دوره)",
}


def sync_entitlement_definitions():
    """``EntitlementDefinition``هایِ استاندارد را idempotent می‌سازد/به‌روز
    می‌کند — از یک data migration و از تست فراخوانی می‌شود. کلیدِ موجود را
    فقط در نام/نوع/پیش‌فرض به‌روزرسانی می‌کند، هرگز حذف نمی‌کند."""
    for key, name, etype, default_enabled in ENTITLEMENT_DEFINITIONS:
        EntitlementDefinition.objects.update_or_create(
            key=key,
            defaults={"name": name, "entitlement_type": etype, "default_enabled": default_enabled, "is_active": True},
        )
