"""سرویسِ صادراتِ اکسل (XLSX) — پنج نوعِ خروج (کالا/تنوع/موجودی/مشتری/سفارش)،
همه Store-scoped. نگاه کنید به ADR-52 در ``SAAS_DOMAIN_DECISIONS.md`` و
``docs/design/XLSX_IMPORT_EXPORT_V1.md``.

خروجی یک فایلِ واقعیِ ``.xlsx`` است (نه CSVِ تغییرنام‌یافته): یک شیتِ داده با
هدرِ فارسی، RTL، فریزِ هدر، فیلتر، سلول‌هایِ عددی/تاریخِ واقعی، و یک شیتِ
«راهنما». هر مقدارِ متنی از ``xlsx_utils.set_text`` عبور می‌کند، پس هرگز
فرمول نمی‌شود (ADR-51).

«خروج اطلاعات» مستقیم است: ``generate_export`` فایل را همگام می‌سازد و بایت‌هایش را
به ویو برمی‌گرداند تا در همان پاسخِ HTTP به‌صورتِ ضمیمه ارسال شود. هیچ فایلی در
``private_storage`` ذخیره نمی‌شود و دانلودِ بعدی وجود ندارد. ``ExportJob`` فقط
فرادادهٔ حسابرسی (نوع، تعدادِ ردیف، زمان، وضعیت) است. جزئیات: ``docs/design/DATA_TRANSFER_SAFETY_V1.md``.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from apps.core.models import AuditLogEntry, ExportJob
from apps.core.services.audit_service import record_audit_event
from apps.core.services.xlsx_utils import Column, new_workbook, workbook_to_bytes, write_info_sheet, write_table_sheet


class ExportError(Exception):
    """خطای قابل‌نمایشِ مستقیم به کاربر هنگامِ ساختِ یک صادرات."""


@dataclass
class ExportSpec:
    sheet_title: str
    columns: list
    rows: object  # iterable of row lists, aligned with ``columns``
    guide_intro: list = field(default_factory=list)
    empty_message: str = "هیچ رکوردی برایِ این خروجِ اطلاعات پیدا نشد؛ فروشگاه شما هنوز موردی برای این بخش ندارد."


def _yes_no(value) -> str:
    return "بله" if value else "خیر"


def _variant_option_summary(variant) -> str:
    """خلاصه‌ی محورهای تنوعِ یک ``ProductVariant`` به‌صورتِ ``محور: مقدار`` که با
    «، » جدا می‌شود — صریح و بدونِ ابهام، بدونِ ادغامِ مقادیرِ چندمحوره."""
    axis_pairs = list(
        variant.option_values.select_related("option", "option_value").values_list(
            "option__label", "option_value__label",
        )
    )
    if axis_pairs:
        return "، ".join(f"{axis}: {value}" for axis, value in axis_pairs)
    if variant.attribute or variant.value:
        return f"{variant.attribute}: {variant.value}"
    return ""


def _products_spec(store, filters):
    from apps.catalog.models import Product
    from apps.catalog.services.category_path_service import category_path

    qs = (
        Product.objects.filter(store=store)
        .select_related("brand", "category", "category__parent", "category__parent__parent", "tax_class")
        .order_by("pk")
    )
    status = (filters or {}).get("status")
    if status:
        qs = qs.filter(status=status)
    category_id = (filters or {}).get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    columns = [
        Column("نام کالا", width=34, wrap=True, note="نامی که مشتری در فروشگاه می‌بیند."),
        Column("SKU", width=16, text_format=True, note="کدِ کالا برایِ شناسایی و ورودِ اطلاعات."),
        Column("وضعیت", width=12, note="فعال، غیرفعال یا پیش‌نویس."),
        Column("برند", width=16),
        Column("دسته‌بندی", width=30, wrap=True, note="مسیرِ کاملِ دسته‌بندی؛ مثلاً «پوشاک > مردانه»."),
        Column("قیمت (تومان)", "money", note="قیمتِ فروشِ پایه‌ی کالا به تومان."),
        Column("موجودی", "int", note="موجودیِ کلِ فروشگاه (جمعِ همه‌ی انبارها)."),
        Column("بارکد", width=18, text_format=True),
        Column("وزن (گرم)", "int"),
        Column("نیاز به ارسال", width=13, note="بله برایِ کالایِ فیزیکی، خیر برایِ کالایِ دیجیتال/خدمات."),
        Column("دسته مالیاتی", width=16),
        Column("عنوان سئو", width=26, wrap=True, note="عنوانی که در نتایجِ گوگل نشان داده می‌شود."),
        Column("توضیحات سئو", width=38, wrap=True, note="توضیحِ کوتاهی که زیرِ عنوان در گوگل نشان داده می‌شود."),
        Column("تاریخ ایجاد", "datetime"),
        Column("آخرین بروزرسانی", "datetime"),
        Column("شناسه کالا", "id", tier="tech", note="شناسه‌ی داخلی؛ برایِ ردیابی و ورودِ اطلاعات."),
        Column("نشانی صفحه (اسلاگ)", width=26, tier="tech", note="بخشی از آدرسِ صفحه‌ی کالا در فروشگاه."),
    ]

    def rows():
        for p in qs.iterator(chunk_size=500):
            yield [
                p.name, p.sku, p.get_status_display(),
                p.brand.name if p.brand_id else "",
                category_path(p.category) if p.category_id else "",
                p.price, p.stock, p.barcode, p.weight_grams,
                _yes_no(p.requires_shipping),
                p.tax_class.name if p.tax_class_id else "",
                p.seo_title, p.seo_description, p.created_at, p.updated_at,
                p.pk, p.slug,
            ]

    return ExportSpec("کالاها", columns, rows(), guide_intro=[
        "هر ردیف یک کالاست. ستون‌هایِ خاکستری (شناسه و نشانیِ صفحه) فقط برایِ ردیابی‌اند.",
        "برایِ ویرایشِ گروهیِ کالاها می‌توانید همین فایل را ویرایش کنید و از بخشِ «ورود اطلاعات» دوباره بارگذاری کنید.",
    ])


def _variants_spec(store, filters):
    from apps.catalog.models import ProductVariant

    qs = (
        ProductVariant.objects.filter(store=store)
        .select_related("product")
        .prefetch_related("option_values__option", "option_values__option_value")
        .order_by("product_id", "display_order", "pk")
    )
    product_id = (filters or {}).get("product_id")
    if product_id:
        qs = qs.filter(product_id=product_id)

    columns = [
        Column("نام کالا", width=32, wrap=True),
        Column("ویژگی‌هایِ تنوع", width=30, wrap=True, note="ترکیبِ ویژگی‌ها؛ مثلاً «رنگ: قرمز، سایز: L»."),
        Column("SKU تنوع", width=18, text_format=True),
        Column("بارکد", width=18, text_format=True),
        Column("تغییرِ قیمت (تومان)", "money", note="مبلغی که به قیمتِ پایه‌ی کالا اضافه می‌شود (می‌تواند منفی باشد)."),
        Column("قیمت مقایسه‌ای (تومان)", "money", note="قیمتِ خط‌خورده‌ی قبل از تخفیف."),
        Column("بهای تمام‌شده (تومان)", "money", note="فقط برایِ شما؛ به مشتری نمایش داده نمی‌شود."),
        Column("موجودی", "int"),
        Column("وزن (گرم)", "int"),
        Column("فعال", width=9),
        Column("پیش‌فرض", width=10, note="تنوعی که هنگامِ ورود به صفحه‌ی کالا انتخاب شده است."),
        Column("منسوخ", width=9, note="تنوعی که دیگر با محورهایِ کالا هم‌خوانی ندارد."),
        Column("SKU کالا", width=16, tier="tech", text_format=True),
        Column("شناسه کالا", "id", tier="tech"),
        Column("شناسه تنوع", "id", tier="tech"),
        Column("کلید ترکیب", width=16, tier="tech", note="شناسه‌ی فنیِ ترکیبِ ویژگی‌ها."),
    ]

    def rows():
        for v in qs.iterator(chunk_size=500):
            yield [
                v.product.name, _variant_option_summary(v), v.sku, v.barcode,
                v.extra_price, v.compare_at_price, v.cost, v.stock, v.weight_grams,
                _yes_no(v.is_active), _yes_no(v.is_default), _yes_no(v.is_obsolete),
                v.product.sku, v.product_id, v.pk, v.combination_key,
            ]

    return ExportSpec("تنوع‌ها", columns, rows(), guide_intro=[
        "هر ردیف یک تنوعِ کالاست (مثلاً یک ترکیبِ رنگ و سایز).",
    ])


def _inventory_spec(store, filters):
    from apps.catalog.models import WarehouseInventory
    from apps.catalog.services.inventory_service import get_available_quantity

    qs = (
        WarehouseInventory.objects.filter(store=store)
        .select_related("warehouse", "product", "variant")
        .prefetch_related("variant__option_values__option", "variant__option_values__option_value")
        .order_by("warehouse_id", "product_id")
    )
    warehouse_id = (filters or {}).get("warehouse_id")
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    columns = [
        Column("انبار", width=20),
        Column("کالا", width=32, wrap=True),
        Column("SKU", width=16, text_format=True),
        Column("تنوع", width=24, wrap=True, note="اگر کالا تنوع دارد، ترکیبِ ویژگی‌ها؛ وگرنه خالی."),
        Column("موجودی فعلی", "int", note="تعدادِ کالا در همین انبار."),
        Column(
            "رزرو شده", "int",
            note="کالایی که برایِ سفارش‌هایِ در جریان نگه داشته شده. این عدد برایِ کلِ فروشگاه است، نه فقط همین انبار.",
        ),
        Column(
            "موجودی قابل فروش", "int",
            note="موجودیِ کلِ فروشگاه منهایِ رزروها. این عدد برایِ کلِ فروشگاه است، نه فقط همین انبار.",
        ),
        Column("آستانه هشدار کمبود", "int", note="اگر موجودی به این عدد یا کمتر برسد، هشدار کمبود داده می‌شود."),
        Column("آخرین بروزرسانی", "datetime"),
        Column("بارکد", width=18, tier="tech", text_format=True),
        Column("شناسه کالا", "id", tier="tech"),
        Column("شناسه تنوع", "id", tier="tech"),
    ]

    def rows():
        for balance in qs.iterator(chunk_size=500):
            available = get_available_quantity(product=balance.product, variant=balance.variant)
            on_hand_total = balance.variant.stock if balance.variant_id else balance.product.stock
            reserved_total = on_hand_total - available
            yield [
                balance.warehouse.name, balance.product.name,
                balance.variant.sku if balance.variant_id else balance.product.sku,
                _variant_option_summary(balance.variant) if balance.variant_id else "",
                balance.on_hand, reserved_total, available,
                balance.low_stock_threshold, balance.updated_at,
                balance.variant.barcode if balance.variant_id else balance.product.barcode,
                balance.product_id, balance.variant_id,
            ]

    return ExportSpec("موجودی انبار", columns, rows(), guide_intro=[
        "هر ردیف موجودیِ یک کالا (یا تنوعِ آن) در یک انبار است.",
        "«رزرو شده» و «موجودی قابل فروش» برایِ کلِ فروشگاه حساب می‌شوند، نه فقط انبارِ همان ردیف.",
        "برایِ تغییرِ موجودی از بخشِ «ورود اطلاعات ← موجودی انبار» استفاده کنید؛ تغییرِ عددِ این فایل به‌تنهایی اثری ندارد.",
    ], empty_message="هنوز موجودیِ ثبت‌شده‌ای در انبارهایِ این فروشگاه وجود ندارد.")


def _customers_spec(store, filters):
    from apps.customers.models import Customer
    from apps.orders.models import Order

    qs = (
        Customer.objects.filter(orders__store=store)
        .distinct()
        .annotate(
            order_count=Count("orders", filter=Q(orders__store=store), distinct=True),
            paid_total=Sum(
                "orders__grand_total",
                filter=Q(orders__store=store, orders__payment_status=Order.PaymentStatus.PAID),
            ),
            last_order_at=Max("orders__created_at", filter=Q(orders__store=store)),
        )
        .order_by("-created_at")
    )
    customer_ids = (filters or {}).get("customer_ids")
    if customer_ids:
        qs = qs.filter(pk__in=customer_ids)

    columns = [
        Column("نام مشتری", width=26),
        Column("موبایل", width=16, text_format=True),
        Column("ایمیل", width=28),
        Column("تعداد سفارش", "int", note="فقط سفارش‌هایِ همین فروشگاه."),
        Column("مجموع خرید (تومان)", "money", note="جمعِ سفارش‌هایِ پرداخت‌شده‌ی همین فروشگاه."),
        Column("آخرین سفارش", "datetime"),
        Column("تاریخ عضویت", "datetime"),
        Column("شناسه مشتری", "id", tier="tech"),
    ]

    def rows():
        for c in qs.iterator(chunk_size=500):
            yield [
                c.full_name, c.phone, c.email, c.order_count, c.paid_total or 0,
                c.last_order_at, c.created_at, c.pk,
            ]

    return ExportSpec("مشتریان", columns, rows(), guide_intro=[
        "این فایل شاملِ اطلاعاتِ تماسِ مشتریان است؛ آن را امن نگه دارید.",
        "فقط مشتریانی که حداقل یک سفارش در این فروشگاه داشته‌اند فهرست می‌شوند.",
    ], empty_message="هنوز مشتریی با سفارش در این فروشگاه ثبت نشده است.")


def _orders_spec(store, filters):
    from apps.orders.models import Order, Refund, ReturnRequest

    qs = (
        Order.objects.filter(store=store)
        .select_related("customer", "shipping_method")
        .order_by("-created_at")
    )
    status = (filters or {}).get("status")
    if status:
        qs = qs.filter(status=status)
    payment_status = (filters or {}).get("payment_status")
    if payment_status:
        qs = qs.filter(payment_status=payment_status)

    refund_totals = dict(
        Refund.objects.filter(store=store, status=Refund.Status.SUCCEEDED)
        .values("order_id").annotate(total=Sum("approved_amount")).values_list("order_id", "total")
    )
    return_status_by_order = dict(
        ReturnRequest.objects.filter(store=store).order_by("order_id", "-created_at")
        .values_list("order_id", "status")
    )
    return_labels = dict(ReturnRequest.Status.choices)

    columns = [
        Column("شماره سفارش", width=16, text_format=True),
        Column("تاریخ ثبت", "datetime"),
        Column("مشتری", width=24),
        Column("وضعیت سفارش", width=16),
        Column("وضعیت پرداخت", width=16),
        Column("جمع کالاها (تومان)", "money"),
        Column("تخفیف (تومان)", "money"),
        Column("هزینه ارسال (تومان)", "money"),
        Column("مالیات ارسال (تومان)", "money"),
        Column("مالیات (تومان)", "money"),
        Column("مبلغ نهایی (تومان)", "money"),
        Column("روش ارسال", width=20),
        Column("انبار تأمین‌کننده", width=18),
        Column("مجموع استرداد موفق (تومان)", "money"),
        Column("وضعیت آخرین مرجوعی", width=18),
    ]

    def rows():
        for o in qs.iterator(chunk_size=500):
            fulfillment_warehouse_name = (
                o.items.exclude(fulfillment_warehouse__isnull=True)
                .values_list("fulfillment_warehouse__name", flat=True).first() or ""
            )
            return_status = return_status_by_order.get(o.pk, "")
            yield [
                o.code, o.created_at, o.customer.full_name,
                o.get_status_display(), o.get_payment_status_display(),
                o.items_total, o.product_discount + o.coupon_discount,
                o.shipping_cost, o.shipping_tax, o.tax, o.grand_total,
                o.shipping_method_name, fulfillment_warehouse_name,
                refund_totals.get(o.pk, 0) or 0,
                return_labels.get(return_status, return_status),
            ]

    return ExportSpec("سفارش‌ها", columns, rows(), guide_intro=[
        "همه‌ی مبلغ‌ها به تومان هستند. هر ردیف یک سفارش است.",
    ], empty_message="هنوز سفارشی در این فروشگاه ثبت نشده است.")


_EXPORT_SPEC_BUILDERS = {
    ExportJob.ExportType.PRODUCTS: _products_spec,
    ExportJob.ExportType.VARIANTS: _variants_spec,
    ExportJob.ExportType.INVENTORY: _inventory_spec,
    ExportJob.ExportType.CUSTOMERS: _customers_spec,
    ExportJob.ExportType.ORDERS: _orders_spec,
}


def build_export_workbook(store, export_type: str, filters: dict | None = None):
    """کارپوشه‌ی (Workbook) یک صادرات را می‌سازد و ``(workbook, row_count)`` برمی‌گرداند."""
    spec = _EXPORT_SPEC_BUILDERS[export_type](store, filters)
    label = dict(ExportJob.ExportType.choices)[export_type]
    wb = new_workbook(f"خروجِ اطلاعات: {label} — {store.name}")
    data_sheet = wb.active
    data_sheet.title = spec.sheet_title
    row_count = write_table_sheet(data_sheet, spec.columns, spec.rows, empty_message=spec.empty_message)

    guide = wb.create_sheet("راهنما")
    write_info_sheet(
        guide, title="درباره‌ی این فایل",
        facts=[
            ("نوع خروجی", label),
            ("فروشگاه", store.name),
            ("تاریخ تهیه", timezone.now()),
            ("تعداد ردیف‌ها", row_count),
        ],
        paragraphs=[
            "این فایل از بخشِ «خروج اطلاعات» در راستی‌سی ساخته شده است و اطلاعاتِ همین فروشگاه را در لحظه‌ی تهیه نشان می‌دهد.",
            *spec.guide_intro,
            "ستون‌هایِ سبزِ تیره اطلاعاتِ اصلی‌اند و ستون‌هایِ خاکستری (در انتها) شناسه‌هایِ فنی‌اند که فقط برایِ ردیابی لازم می‌شوند.",
        ],
        table_header=("ستون", "توضیح"),
        table_rows=[(c.header, c.note or "—") for c in spec.columns],
    )
    return wb, row_count


@dataclass
class ExportResult:
    """خروجیِ یک «خروجِ مستقیم»: بایت‌هایِ XLSX فقط برایِ همین پاسخِ HTTP‌اند و هیچ‌جا
    ذخیره نمی‌شوند؛ ``job`` فقط فرادادهٔ سبکِ (نوع/تعداد ردیف/زمان) است."""

    content: bytes
    filename: str
    row_count: int
    job: ExportJob


def generate_export(store, export_type: str, *, requested_by, filters: dict | None = None) -> ExportResult:
    """فایلِ اکسلِ یک خروج را همگام می‌سازد و بایت‌هایش را برمی‌گرداند — *هیچ فایلی
    ذخیره نمی‌شود* (نه در ``private_storage`` و نه جایِ دیگر) و هیچ دانلودِ بعدی
    وجود ندارد.

    کنترل‌هایِ قبلی حفظ شده‌اند: گیتِ قابلیتِ خروج و سقفِ ماهانه *پیش از* ساخت
    بررسی می‌شوند؛ سهمیه فقط پس از ساختِ موفقِ فایل مصرف می‌شود (شکست مصرف
    نمی‌کند)؛ و هر تلاش، چه موفق و چه ناموفق، در گزارشِ رخدادها ثبت می‌شود.
    ``ExportJob`` فقط فرادادهٔ حسابرسی است: ``file`` همیشه خالی و ``expires_at``
    بدونِ مقدار می‌ماند (چیزی برایِ نگه‌داری/انقضا وجود ندارد)."""
    if export_type not in _EXPORT_SPEC_BUILDERS:
        raise ExportError(f"نوعِ خروجِ «{export_type}» پشتیبانی نمی‌شود.")

    from apps.subscriptions.services.enforcement import check_export_budget, enforce_export_allowed

    enforce_export_allowed(store)
    check_export_budget(store)

    job = ExportJob.objects.create(
        store=store, export_type=export_type, status=ExportJob.Status.PROCESSING,
        requested_by=requested_by, filters=filters or {}, started_at=timezone.now(),
    )
    try:
        workbook, row_count = build_export_workbook(store, export_type, filters)
        content = workbook_to_bytes(workbook)
    except Exception as exc:
        job.status = ExportJob.Status.FAILED
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at"])
        record_audit_event(
            store=store, actor=requested_by, action_code="export.failed",
            object_type="ExportJob", object_id=str(job.pk),
            object_label=f"خروجِ {job.get_export_type_display()} ناموفق",
            metadata={"error": str(exc)}, result=AuditLogEntry.ResultStatus.FAILURE,
        )
        raise

    job.row_count = row_count
    job.status = ExportJob.Status.COMPLETED
    job.completed_at = timezone.now()
    job.save(update_fields=["row_count", "status", "completed_at"])
    # سهمیه‌ی ماهانه فقط پس از ساخته شدنِ موفقِ فایل مصرف می‌شود.
    from apps.subscriptions.services.enforcement import consume_export

    consume_export(store)
    record_audit_event(
        store=store, actor=requested_by, action_code="export.completed",
        object_type="ExportJob", object_id=str(job.pk),
        object_label=f"خروجِ {job.get_export_type_display()} — {row_count} ردیف",
        after={
            "export_type": export_type, "row_count": row_count, "filters": filters or {},
            "format": "xlsx", "delivery": "direct_download", "retained": False,
        },
    )
    filename = f"rastisi-{export_type}-{timezone.localdate().isoformat()}.xlsx"
    return ExportResult(content=content, filename=filename, row_count=row_count, job=job)


def mark_expired_jobs(store=None, *, now=None):
    """هر ``ExportJob`` کامل‌شده‌ای که ``expires_at`` آن گذشته را ``expired``
    می‌کند و فایلِ آن را از دیسک حذف می‌کند (آزادسازیِ فضا) — منطقِ اصلیِ
    ``cleanup_expired_exports`` که هم از دستورِ مدیریتی و هم (اگر لازم شد)
    مستقیماً قابلِ فراخوانی است. هرگز کل جدول را در حافظه بارگذاری نمی‌کند
    (``iterator``)."""
    now = now or timezone.now()
    qs = ExportJob.objects.filter(status=ExportJob.Status.COMPLETED, expires_at__lt=now)
    if store is not None:
        qs = qs.filter(store=store)

    count = 0
    for job in qs.iterator(chunk_size=200):
        if job.file:
            job.file.delete(save=False)
        job.status = ExportJob.Status.EXPIRED
        job.save(update_fields=["status", "file"])
        count += 1
    return count
