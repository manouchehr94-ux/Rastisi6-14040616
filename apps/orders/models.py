from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel

# =============================================================================
# Shipping Zone / Method / Rate domain (Admin Panel Completion Program
# checkpoint 3B — نگاه کنید به ADR-41/ADR-42/ADR-43 در SAAS_DOMAIN_DECISIONS.md)
# =============================================================================


class ShippingZone(TimeStampedModel):
    """منطقه‌ی جغرافیاییِ ارسالِ Store-owned.

    این کدبیس فقط آدرسِ ایرانی دارد (استان/شهر/کدپستی — نگاه کنید به
    ``apps.customers.models.Address``؛ هیچ فیلدِ کشوری وجود ندارد) پس منطقه
    فقط با همین سه بُعد تطبیق داده می‌شود، نه زیرساختِ جغرافیاییِ جهانیِ
    اختراعی (ADR-41). دقیقاً یک منطقه‌ی «پیش‌فرض/ذخیره» (``is_fallback``) به
    ازای هر Store مجاز است — قیدِ دیتابیسِ شرطی، دقیقاً همان الگوی
    ``Warehouse.is_default``.
    """

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="shipping_zones",
    )
    name = models.CharField("نام منطقه", max_length=100)
    code = models.SlugField("کد", max_length=60, allow_unicode=True)
    is_active = models.BooleanField("فعال", default=True)
    priority = models.PositiveIntegerField("اولویت (کوچک‌تر = بالاتر)", default=0)
    provinces = models.JSONField("استان‌ها", default=list, blank=True)
    cities = models.JSONField("شهرها", default=list, blank=True)
    postal_codes = models.JSONField("کدهای پستی", default=list, blank=True)
    excluded_provinces = models.JSONField("استان‌های مستثنا", default=list, blank=True)
    excluded_cities = models.JSONField("شهرهای مستثنا", default=list, blank=True)
    is_fallback = models.BooleanField("منطقه‌ی پیش‌فرض/ذخیره", default=False)

    class Meta:
        verbose_name = "منطقه‌ی ارسال"
        verbose_name_plural = "مناطقِ ارسال"
        ordering = ["priority", "name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_shippingzone_code_per_store"),
            models.UniqueConstraint(
                fields=["store"], condition=models.Q(is_fallback=True), name="uniq_fallback_zone_per_store",
            ),
        ]

    def __str__(self):
        return self.name

    def matches(self, *, province: str = "", city: str = "", postal_code: str = "") -> bool:
        """آیا این آدرس (بدونِ در نظر گرفتنِ اولویت با سایرِ مناطق) با این
        منطقه تطبیق دارد — نگاه کنید به ADR-41 برای سیاستِ اولویتِ کاملِ
        انتخاب بین چند منطقه‌ی تطبیق‌یافته."""
        if postal_code and self.excluded_cities and city in self.excluded_cities:
            return False
        if province and province in self.excluded_provinces:
            return False
        if city and city in self.excluded_cities:
            return False
        if postal_code and postal_code in self.postal_codes:
            return True
        if city and city in self.cities:
            return True
        if province and province in self.provinces:
            return True
        return False


class ShippingMethod(TimeStampedModel):
    class MethodType(models.TextChoices):
        FLAT_RATE = "flat_rate", "نرخ ثابت"
        FREE = "free", "رایگان"
        PRICE_BASED = "price_based", "بر اساسِ مبلغ سفارش"
        WEIGHT_BASED = "weight_based", "بر اساسِ وزن"
        LOCAL_PICKUP = "local_pickup", "تحویل حضوری"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="shipping_methods",
    )
    # ``zone`` عمداً nullable است: مقدارِ خالی یعنی این روش سراسریِ Store است
    # (بدونِ محدودیتِ منطقه‌ای) — دقیقاً رفتارِ قبل از checkpoint 3B برای هر
    # ردیفِ موجود، چون این فیلد جدید و پیش‌فرضش None است (ADR-41).
    zone = models.ForeignKey(
        ShippingZone, verbose_name="منطقه‌ی ارسال", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="shipping_methods",
    )
    name = models.CharField("نام روش ارسال", max_length=100)
    # ``slug`` نقشِ «کد یکتا به‌ازای هر Store» را ایفا می‌کند (همان قیدِ
    # ``uniq_shippingmethod_slug_per_store`` پایین‌تر) — فیلدِ جداگانه‌ای برای
    # «کد» اضافه نشده تا داده تکراری نشود.
    slug = models.SlugField("اسلاگ", max_length=120, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    method_type = models.CharField(
        "نوعِ روش", max_length=20, choices=MethodType.choices, default=MethodType.FLAT_RATE,
    )
    cost = models.DecimalField("هزینه (تومان)", max_digits=12, decimal_places=0, default=0)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    # ``null=True`` یعنی «آستانه‌ی ارسالِ رایگان غیرفعال است» — صفحه‌ی
    # سادهٔ راه‌اندازیِ ارسال این فیلد را خالی می‌گذارد تا این حالت را
    # صراحتاً نشان دهد؛ رکوردهای قدیمی‌تر که قبلاً مقدار داشته‌اند دست‌نخورده
    # می‌مانند (این مهاجرت فقط nullable بودن را اضافه می‌کند، هیچ داده‌ای را
    # پاک نمی‌کند).
    free_over = models.DecimalField(
        "آستانه‌ی ارسال رایگان (تومان)", max_digits=12, decimal_places=0, null=True, blank=True,
    )
    display_order = models.PositiveIntegerField("ترتیبِ نمایش", default=0)
    min_delivery_days = models.PositiveIntegerField("حداقلِ روزِ تحویل", null=True, blank=True)
    max_delivery_days = models.PositiveIntegerField("حداکثرِ روزِ تحویل", null=True, blank=True)
    is_pickup = models.BooleanField("تحویلِ حضوری", default=False)
    pickup_warehouse = models.ForeignKey(
        "catalog.Warehouse", verbose_name="انبارِ بارگیریِ حضوری", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="pickup_shipping_methods",
    )
    cod_eligible = models.BooleanField("پرداخت در محل", default=False)

    class Meta:
        verbose_name = "روش ارسال"
        verbose_name_plural = "روش‌های ارسال"
        ordering = ["display_order", "cost"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_shippingmethod_slug_per_store"),
            models.CheckConstraint(
                check=(
                    models.Q(min_delivery_days__isnull=True) | models.Q(max_delivery_days__isnull=True)
                    | models.Q(min_delivery_days__lte=models.F("max_delivery_days"))
                ),
                name="shippingmethod_min_lte_max_days",
            ),
            models.CheckConstraint(check=models.Q(cost__gte=0), name="shippingmethod_cost_non_negative"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.zone_id and self.zone.store_id != self.store_id:
            errors["zone"] = "این منطقه متعلق به فروشگاه دیگری است."
        if self.pickup_warehouse_id:
            if self.pickup_warehouse.store_id != self.store_id:
                errors["pickup_warehouse"] = "این انبار متعلق به فروشگاه دیگری است."
            elif not self.pickup_warehouse.is_pickup_location:
                errors["pickup_warehouse"] = "این انبار برای بارگیریِ حضوری فعال نشده است."
        if errors:
            raise ValidationError(errors)


class ShippingRateRule(TimeStampedModel):
    """قاعده‌ی نرخِ ارسال برای یک ``ShippingMethod`` — نگاه کنید به ADR-42.

    وقتی هیچ ``ShippingRateRule`` فعالی برای یک روش وجود ندارد، محاسبه‌ی
    نرخ به رفتارِ قدیمیِ ``ShippingMethod.cost``/``free_over`` بازمی‌گردد —
    این کدبیس تنها یک ارز دارد (تومان)، پس ``currency`` همیشه با همان
    مقدارِ ثابت بررسی می‌شود، نه یک فیلدِ Storeِ چندارزی که وجود ندارد."""

    CURRENCY = "IRT"

    method = models.ForeignKey(
        ShippingMethod, verbose_name="روشِ ارسال", on_delete=models.CASCADE, related_name="rate_rules",
    )
    name = models.CharField("نام قاعده", max_length=100)
    priority = models.PositiveIntegerField("اولویت (کوچک‌تر = بالاتر)", default=0)
    is_active = models.BooleanField("فعال", default=True)
    min_subtotal = models.DecimalField("حداقلِ جمعِ سبد", max_digits=14, decimal_places=0, null=True, blank=True)
    max_subtotal = models.DecimalField("حداکثرِ جمعِ سبد", max_digits=14, decimal_places=0, null=True, blank=True)
    min_weight_grams = models.PositiveIntegerField("حداقلِ وزن (گرم)", null=True, blank=True)
    max_weight_grams = models.PositiveIntegerField("حداکثرِ وزن (گرم)", null=True, blank=True)
    rate_amount = models.DecimalField("مبلغِ نرخ (تومان)", max_digits=12, decimal_places=0, default=0)
    free_over = models.DecimalField(
        "آستانه‌ی ارسال رایگانِ این قاعده", max_digits=12, decimal_places=0, null=True, blank=True,
    )
    currency = models.CharField("ارز", max_length=6, default=CURRENCY)
    start_at = models.DateTimeField("زمانِ شروع", null=True, blank=True)
    end_at = models.DateTimeField("زمانِ پایان", null=True, blank=True)

    class Meta:
        verbose_name = "قاعده‌ی نرخِ ارسال"
        verbose_name_plural = "قواعدِ نرخِ ارسال"
        ordering = ["priority", "id"]
        constraints = [
            models.CheckConstraint(check=models.Q(rate_amount__gte=0), name="shippingrate_amount_non_negative"),
            models.CheckConstraint(
                check=(
                    models.Q(min_subtotal__isnull=True) | models.Q(max_subtotal__isnull=True)
                    | models.Q(min_subtotal__lte=models.F("max_subtotal"))
                ),
                name="shippingrate_min_lte_max_subtotal",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(min_weight_grams__isnull=True) | models.Q(max_weight_grams__isnull=True)
                    | models.Q(min_weight_grams__lte=models.F("max_weight_grams"))
                ),
                name="shippingrate_min_lte_max_weight",
            ),
        ]

    def __str__(self):
        return f"{self.method.name} — {self.name}"

    def clean(self):
        if self.currency != self.CURRENCY:
            raise ValidationError({"currency": f"این پلتفرم فقط از ارزِ {self.CURRENCY} پشتیبانی می‌کند."})

    def matches(self, *, subtotal, weight_grams: int) -> bool:
        if self.min_subtotal is not None and subtotal < self.min_subtotal:
            return False
        if self.max_subtotal is not None and subtotal > self.max_subtotal:
            return False
        if self.min_weight_grams is not None and weight_grams < self.min_weight_grams:
            return False
        if self.max_weight_grams is not None and weight_grams > self.max_weight_grams:
            return False
        return True

    @property
    def specificity(self) -> int:
        """تعدادِ محدودیت‌های مقداردهی‌شده — برای شکستنِ تساویِ اولویت بینِ
        قواعدی که هر دو تطبیق دارند (قاعده‌ی محدودتر برنده است، نگاه کنید
        به ADR-42)."""
        return sum(
            1 for bound in (self.min_subtotal, self.max_subtotal, self.min_weight_grams, self.max_weight_grams)
            if bound is not None
        )


# =============================================================================
# Tax Class / Tax Rate domain (Admin Panel Completion Program checkpoint 3B —
# نگاه کنید به ADR-44/ADR-45/ADR-46 در SAAS_DOMAIN_DECISIONS.md)
# =============================================================================


class TaxClass(TimeStampedModel):
    """دسته‌ی مالیاتیِ Store-owned (مثلاً «عمومی»، «معاف»، «کالای دیجیتال»).

    دقیقاً یک دسته‌ی پیش‌فرض به‌ازای هر Store مجاز است (قیدِ شرطی، همان الگوی
    ``Warehouse.is_default``/``ShippingZone.is_fallback``)."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="tax_classes",
    )
    name = models.CharField("نام", max_length=100)
    code = models.SlugField("کد", max_length=60, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    is_default = models.BooleanField("پیش‌فرض", default=False)

    class Meta:
        verbose_name = "دسته‌ی مالیاتی"
        verbose_name_plural = "دسته‌های مالیاتی"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_taxclass_code_per_store"),
            models.UniqueConstraint(
                fields=["store"], condition=models.Q(is_default=True), name="uniq_default_taxclass_per_store",
            ),
        ]

    def __str__(self):
        return self.name


class TaxRate(TimeStampedModel):
    """نرخِ مالیات برای یک دسته‌ی مالیاتی، اختیاراً محدود به یک استانِ خاص —
    نگاه کنید به ADR-45 برای سیاستِ تطبیق و بازگشت به نرخِ ثابتِ
    ``ShopSettings.tax_percent`` وقتی هیچ ``TaxRate``ای برای این Store ثبت
    نشده باشد."""

    MAX_RATE_PERCENT = 100

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="tax_rates",
    )
    tax_class = models.ForeignKey(
        TaxClass, verbose_name="دسته‌ی مالیاتی", on_delete=models.CASCADE, related_name="rates",
    )
    # خالی یعنی «همه‌ی استان‌ها» (سراسریِ Store) — این کدبیس فیلدِ کشور ندارد
    # (فقط ایران)، پس بُعدِ کشور از قصد حذف شده (ADR-45).
    province = models.CharField("استان", max_length=80, blank=True, default="")
    rate_percent = models.DecimalField("نرخ (٪)", max_digits=5, decimal_places=2)
    priority = models.PositiveIntegerField("اولویت (کوچک‌تر = بالاتر)", default=0)
    is_active = models.BooleanField("فعال", default=True)
    # None یعنی «طبقِ تنظیماتِ Store» (ارثیِ ShopSettings.shipping_taxable)؛
    # True/False یعنی این نرخ صراحتاً رفتارِ Store را بازنویسی می‌کند.
    applies_to_shipping = models.BooleanField("اعمال روی ارسال", null=True, blank=True)
    start_at = models.DateTimeField("زمانِ شروع", null=True, blank=True)
    end_at = models.DateTimeField("زمانِ پایان", null=True, blank=True)

    class Meta:
        verbose_name = "نرخِ مالیات"
        verbose_name_plural = "نرخ‌های مالیات"
        ordering = ["priority", "id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rate_percent__gte=0) & models.Q(rate_percent__lte=100),
                name="taxrate_percent_within_bounds",
            ),
        ]

    def __str__(self):
        return f"{self.tax_class.name} — {self.rate_percent}٪"

    def clean(self):
        if self.tax_class_id and self.store_id and self.tax_class.store_id != self.store_id:
            raise ValidationError({"tax_class": "این دسته‌ی مالیاتی متعلق به فروشگاه دیگری است."})


class PaymentGateway(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="payment_gateways",
    )
    name = models.CharField("نام درگاه", max_length=100)
    slug = models.SlugField("اسلاگ", max_length=120, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    fee_percent = models.DecimalField("کارمزد (٪)", max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "درگاه پرداخت"
        verbose_name_plural = "درگاه‌های پرداخت"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_paymentgateway_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSING = "processing", "در حال پردازش"
        SHIPPED = "shipped", "ارسال شده"
        DELIVERED = "delivered", "تحویل داده شده"
        CANCELED = "canceled", "لغو شده"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        FAILED = "failed", "ناموفق"
        REFUNDED = "refunded", "مسترد شده"

    code = models.CharField("شناسه‌ی سفارش", max_length=20, unique=True)
    # مالکیت Store مستقیم و صریح — نه فقط از طریق vendor.store. هر Order باید
    # دقیقاً یک Store داشته باشد که با vendor.store یکی است (این عدم‌تطابق در
    # لایه‌ی سرویس/فرم بررسی می‌شود؛ CheckConstraint نمی‌تواند بین دو جدول
    # مقایسه کند — نگاه کنید به clean() پایین‌تر و
    # apps.orders.services.order_service.create_order_from_cart).
    # on_delete=PROTECT (نه CASCADE مثل کاتالوگ) چون سفارش یک رکورد مالی/
    # تاریخی است؛ حذف یک Store هرگز نباید سفارش‌های آن را هم بی‌صدا حذف کند.
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="orders"
    )
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.PROTECT, related_name="orders"
    )
    vendor = models.ForeignKey(
        "catalog.Vendor", verbose_name="فروشنده", on_delete=models.PROTECT, related_name="orders"
    )

    # کلید یکتای درخواست تسویه‌حساب — برای idempotency ثبت سفارش (بخش ۸ مرحله‌ی
    # ۳). خالی یعنی «بدون کلید» (مثلاً ساخت مستقیم از تست/مهاجرت)؛ یکتایی فقط
    # وقتی مقدار دارد اجرا می‌شود (uniq_order_idempotency_key_when_set پایین‌تر) —
    # دقیقاً همان الگوی ProductVariant.sku (uniq_variant_sku_when_set).
    idempotency_key = models.CharField(
        "کلید یکتای درخواست تسویه‌حساب", max_length=64, blank=True, default=""
    )

    address = models.JSONField("آدرس (اسنپ‌شات)", default=dict)
    shipping_method = models.ForeignKey(
        ShippingMethod, verbose_name="روش ارسال", on_delete=models.PROTECT, related_name="orders"
    )
    payment_gateway = models.ForeignKey(
        PaymentGateway, verbose_name="درگاه پرداخت", on_delete=models.PROTECT, related_name="orders"
    )
    coupon = models.ForeignKey(
        "cart.Coupon", verbose_name="کد تخفیف", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="orders",
    )

    status = models.CharField("وضعیت سفارش", max_length=12, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(
        "وضعیت پرداخت", max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    items_total = models.DecimalField("جمع کالاها", max_digits=14, decimal_places=0, default=0)
    product_discount = models.DecimalField("تخفیف کالاها", max_digits=14, decimal_places=0, default=0)
    coupon_discount = models.DecimalField("تخفیف کد تخفیف", max_digits=14, decimal_places=0, default=0)
    shipping_cost = models.DecimalField("هزینه‌ی ارسال", max_digits=12, decimal_places=0, default=0)
    tax = models.DecimalField("مالیات", max_digits=12, decimal_places=0, default=0)
    grand_total = models.DecimalField("مبلغ نهایی", max_digits=14, decimal_places=0, default=0)

    # --- اسنپ‌شاتِ ارسال (checkpoint 3B، ADR-47) — همیشه در لحظه‌ی ساختِ
    # سفارش پر می‌شود؛ تغییر/آرشیوِ ShippingMethod/ShippingZone بعداً هرگز
    # این مقادیر را عوض نمی‌کند، چون سفارش دیگر به ردیفِ زنده وابسته نیست.
    shipping_method_name = models.CharField("نامِ روشِ ارسال (اسنپ‌شات)", max_length=100, blank=True, default="")
    shipping_method_code = models.CharField("کدِ روشِ ارسال (اسنپ‌شات)", max_length=120, blank=True, default="")
    shipping_zone_name = models.CharField("نامِ منطقه‌ی ارسال (اسنپ‌شات)", max_length=100, blank=True, default="")
    shipping_zone_code = models.CharField("کدِ منطقه‌ی ارسال (اسنپ‌شات)", max_length=60, blank=True, default="")
    shipping_rate_rule_label = models.CharField(
        "برچسبِ قاعده‌ی نرخ (اسنپ‌شات)", max_length=100, blank=True, default="",
    )
    min_delivery_days = models.PositiveIntegerField("حداقلِ روزِ تحویل (اسنپ‌شات)", null=True, blank=True)
    max_delivery_days = models.PositiveIntegerField("حداکثرِ روزِ تحویل (اسنپ‌شات)", null=True, blank=True)
    is_pickup = models.BooleanField("تحویلِ حضوری (اسنپ‌شات)", default=False)
    pickup_warehouse_name = models.CharField(
        "نامِ انبارِ بارگیری (اسنپ‌شات)", max_length=150, blank=True, default="",
    )
    pickup_address = models.CharField("آدرسِ بارگیری (اسنپ‌شات)", max_length=300, blank=True, default="")

    # --- اسنپ‌شاتِ مالیات (checkpoint 3B، ADR-47)
    prices_include_tax = models.BooleanField("قیمت‌ها شاملِ مالیات بودند (اسنپ‌شات)", default=False)
    tax_rounding_policy = models.CharField("سیاستِ گردکردنِ مالیات (اسنپ‌شات)", max_length=20, blank=True, default="")
    shipping_tax = models.DecimalField("مالیاتِ ارسال", max_digits=12, decimal_places=0, default=0)

    # --- کادوپیچی (اسنپ‌شاتِ سطحِ سفارش) — جدا از items_total نگه‌داری می‌شود.
    # ``gift_wrap_total`` مبلغِ ناخالصِ هزینه‌ی کادوپیچی؛ ``gift_wrap_discount``
    # سهمی از ``coupon_discount`` که روی کادوپیچی اعمال شده (فقط وقتی کد
    # ``applies_to_gift_wrap`` داشته باشد).
    gift_wrap_total = models.DecimalField("هزینه‌ی کادوپیچی", max_digits=12, decimal_places=0, default=0)
    gift_wrap_discount = models.DecimalField("تخفیفِ اعمال‌شده روی کادوپیچی", max_digits=12, decimal_places=0, default=0)
    gift_wrap_scope = models.CharField("مبنای محاسبه‌ی کادوپیچی (اسنپ‌شات)", max_length=10, blank=True, default="")

    note = models.TextField("توضیحات سفارش", blank=True)
    tracking_code = models.CharField("کد رهگیری مرسوله", max_length=60, blank=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_order_idempotency_key_when_set",
            ),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        """سفارش باید دقیقاً هم‌راستا با Store فروشنده‌اش باشد.

        این یک بررسی سطح دیتابیس نیست (CheckConstraint نمی‌تواند بین دو جدول
        Order و Vendor مقایسه کند) — دقیقاً همان محدودیت مستندشده در
        ``apps.catalog.models.Product.clean()``. اجرای واقعی و قطعی این
        عدم‌تطابق در لایه‌ی سرویس است
        (``apps.orders.services.order_service.create_order_from_cart``) که
        تنها مسیر تولید Order در Production است؛ این متد لایه‌ی دومِ دفاعی
        برای فرم/Admin/بررسی صریح است."""
        from django.core.exceptions import ValidationError

        if self.vendor_id and self.store_id and self.vendor.store_id != self.store_id:
            raise ValidationError({"vendor": "این فروشنده متعلق به فروشگاه دیگری است."})


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", verbose_name="کالا", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant", verbose_name="تنوع", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_items",
    )
    product_name = models.CharField("نام کالا (اسنپ‌شات)", max_length=220)
    # اسنپ‌شات‌های اضافی (بخش ۱۰) — تا حذف/تغییر Product یا ProductVariant
    # اصلی هرگز نمایش تاریخی این ردیف را عوض نکند. خالی یعنی «بدون تنوع» یا
    # «SKU نداشت» (هر دو معتبر و مورد انتظارند، نه یک حالت خطا).
    sku = models.CharField("کد کالا (SKU) (اسنپ‌شات)", max_length=64, blank=True, default="")
    variant_label = models.CharField("تنوع انتخاب‌شده (اسنپ‌شات)", max_length=150, blank=True, default="")
    quantity = models.PositiveIntegerField("تعداد", default=1)
    unit_price = models.DecimalField("قیمت واحد", max_digits=12, decimal_places=0)
    line_total = models.DecimalField("جمع ردیف", max_digits=12, decimal_places=0)

    # --- اسنپ‌شاتِ مالیاتِ این قلم (checkpoint 3B، ADR-47) — خالی/صفر یعنی
    # «مالیات فعال نبود یا هیچ نرخی تطبیق نداشت»، نه یک حالتِ خطا.
    discount_allocation = models.DecimalField("سهمِ تخفیف از این ردیف", max_digits=12, decimal_places=0, default=0)
    taxable_amount = models.DecimalField("مبلغِ مشمولِ مالیات", max_digits=12, decimal_places=0, default=0)
    tax_class_code = models.CharField("کدِ دسته‌ی مالیاتی (اسنپ‌شات)", max_length=60, blank=True, default="")
    tax_class_name = models.CharField("نامِ دسته‌ی مالیاتی (اسنپ‌شات)", max_length=100, blank=True, default="")
    tax_rate_percent = models.DecimalField(
        "نرخِ مالیات٪ (اسنپ‌شات)", max_digits=5, decimal_places=2, null=True, blank=True,
    )
    unit_tax = models.DecimalField("مالیاتِ واحد", max_digits=12, decimal_places=0, default=0)
    total_tax = models.DecimalField("مجموعِ مالیاتِ این ردیف", max_digits=12, decimal_places=0, default=0)

    # اسنپ‌شاتِ انبارِ تأمین‌کننده — واقعیِ همان انباری که در لحظه‌ی مصرفِ
    # رزرو موجودی از آن کم شد (نه لزوماً انبارِ پیش‌فرضِ فعلیِ Store، که ممکن
    # است بعداً تغییر کند — نگاه کنید به ADR-48). ``SET_NULL`` چون تاریخچه
    # نباید با حذفِ بعدیِ یک انبار از بین برود.
    fulfillment_warehouse = models.ForeignKey(
        "catalog.Warehouse", verbose_name="انبارِ تأمین‌کننده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="fulfilled_order_items",
    )

    # کادوپیچی (اسنپ‌شات) — دقیقاً از ``CartItem.gift_wrap_selected``/
    # ``gift_wrap_unit_price`` در لحظه‌ی ثبتِ سفارش کپی می‌شود (نگاه کنید به
    # ``order_service.create_order_from_cart``)؛ تغییرِ بعدیِ
    # ``ShopSettings.gift_wrap_price`` هرگز این ردیفِ تاریخی را عوض نمی‌کند.
    gift_wrap_selected = models.BooleanField("کادوپیچی انتخاب شده", default=False)
    gift_wrap_unit_price = models.DecimalField(
        "هزینه‌ی کادوپیچی (اسنپ‌شات)", max_digits=12, decimal_places=0, default=0,
    )

    # اسنپ‌شاتِ تاریخیِ برند/دسته/رنگ/سایز/ویژگی‌ها در لحظه‌ی خرید — منبعِ
    # حقیقتِ موتورِ قواعدِ کمپین؛ نگاه کنید به ``item_snapshot_service``.
    attributes_snapshot = models.JSONField("اسنپ‌شاتِ ویژگی‌های کالا", default=dict, blank=True)
    gift_wrap_option_code = models.CharField("گزینه‌ی کادوپیچی (اسنپ‌شات)", max_length=30, blank=True, default="")
    gift_message = models.CharField("پیامِ کارت‌هدیه", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        ordering = ["id"]

    @property
    def gift_wrap_line_total(self):
        if not self.gift_wrap_selected:
            return 0
        return self.gift_wrap_unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class OrderStatusHistory(TimeStampedModel):
    order = models.ForeignKey(
        Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        "از وضعیت", max_length=12, choices=Order.Status.choices, blank=True
    )
    to_status = models.CharField("به وضعیت", max_length=12, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="تغییردهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="order_status_changes",
    )
    note = models.TextField("توضیحات", blank=True)

    class Meta:
        verbose_name = "تاریخچه‌ی وضعیت سفارش"
        verbose_name_plural = "تاریخچه‌ی وضعیت سفارش‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.code}: {self.from_status or '—'} → {self.to_status}"


class Transaction(TimeStampedModel):
    class Status(models.TextChoices):
        OK = "ok", "موفق"
        PENDING = "pending", "در انتظار"
        FAIL = "fail", "ناموفق"
        REFUND = "refund", "مسترد"

    code = models.CharField("شناسه‌ی تراکنش", max_length=20, unique=True)
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="transactions")
    gateway = models.ForeignKey(
        PaymentGateway, verbose_name="درگاه", on_delete=models.PROTECT, related_name="transactions"
    )
    amount = models.DecimalField("مبلغ", max_digits=14, decimal_places=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    ref_id = models.CharField("شماره ارجاع بانکی", max_length=60, blank=True)

    class Meta:
        verbose_name = "تراکنش"
        verbose_name_plural = "تراکنش‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code



# ===========================================================================
# Payment Domain Foundation — PR1
# ===========================================================================


class PaymentGatewayConfig(TimeStampedModel):
    """Per-store configuration for a payment gateway.

    This is the operational configuration — merchant credentials, activation
    state, sandbox mode — while the existing ``PaymentGateway`` model remains
    the order-level record (what the customer chose at checkout time).

    Each store can have at most ONE configuration per gateway code
    (UniqueConstraint below). Credentials are stored encrypted via
    apps.orders.encryption.

    Relationship to PaymentGateway:
        PaymentGatewayConfig is the source of truth for "which gateways are
        available and configured for this store." When a customer selects a
        payment method at checkout, the Order references the legacy
        PaymentGateway for backwards compatibility. PaymentAttempt references
        this config for the actual payment lifecycle.
    """

    class GatewayCode(models.TextChoices):
        ZIBAL = "zibal", "زیبال"
        COD = "cod", "پرداخت در محل"

    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="gateway_configs",
    )
    gateway_code = models.CharField(
        "کد درگاه",
        max_length=30,
        choices=GatewayCode.choices,
    )
    display_title = models.CharField(
        "عنوان نمایشی",
        max_length=150,
        blank=True,
        help_text="عنوان نمایش‌داده‌شده در صفحه‌ی تسویه‌حساب (اختیاری — اگر خالی باشد از نام پیش‌فرض درگاه استفاده می‌شود)",
    )
    is_active = models.BooleanField("فعال", default=False)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_sandbox = models.BooleanField(
        "حالت آزمایشی (Sandbox)",
        default=False,
        help_text="فقط برای درگاه‌هایی که حالت آزمایشی پشتیبانی می‌کنند",
    )

    # Encrypted credentials stored as a single JSON-like text field.
    # Format: Fernet-encrypted JSON string of credential key/value pairs.
    # Empty string means "no credentials set."
    encrypted_credentials = models.TextField(
        "اعتبارنامه‌ی رمزنگاری‌شده",
        blank=True,
        default="",
        help_text="مقدار رمزنگاری‌شده — هرگز مستقیم خوانده نمی‌شود",
    )

    class Meta:
        verbose_name = "پیکربندی درگاه پرداخت"
        verbose_name_plural = "پیکربندی‌های درگاه پرداخت"
        ordering = ["display_order", "gateway_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "gateway_code"],
                name="uniq_gateway_config_per_store",
            ),
        ]

    def __str__(self):
        return f"{self.get_gateway_code_display()} — {self.store.name}"

    @property
    def effective_title(self) -> str:
        """Display title for checkout UI — custom title or gateway default."""
        if self.display_title:
            return self.display_title
        return self.get_gateway_code_display()

    def get_credentials(self) -> dict:
        """Decrypt and return credentials as a dict. Empty dict if none stored."""
        import json
        from .encryption import decrypt_credential

        if not self.encrypted_credentials:
            return {}
        plaintext = decrypt_credential(self.encrypted_credentials)
        if not plaintext:
            return {}
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_credentials(self, credentials: dict) -> None:
        """Encrypt and store a credentials dict."""
        import json
        from .encryption import encrypt_credential

        if not credentials:
            self.encrypted_credentials = ""
            return
        # Remove empty values
        clean = {k: v for k, v in credentials.items() if v}
        if not clean:
            self.encrypted_credentials = ""
            return
        plaintext = json.dumps(clean, ensure_ascii=False)
        self.encrypted_credentials = encrypt_credential(plaintext)

    @property
    def is_configured(self) -> bool:
        """Whether this gateway has all required credentials filled."""
        from .gateways import get_adapter

        try:
            adapter = get_adapter(self.gateway_code)
        except KeyError:
            return False
        if not adapter.required_credentials:
            return True  # COD needs no credentials
        creds = self.get_credentials()
        return all(creds.get(key) for key in adapter.required_credentials)

    @property
    def can_activate(self) -> bool:
        """Whether this config is eligible for activation (credentials complete)."""
        from .gateways import get_adapter

        try:
            adapter = get_adapter(self.gateway_code)
        except KeyError:
            return False
        errors = adapter.validate_credentials(self.get_credentials())
        return len(errors) == 0

    @property
    def is_online(self) -> bool:
        """Whether this is an online payment gateway."""
        from .gateways import get_adapter

        try:
            return get_adapter(self.gateway_code).is_online
        except KeyError:
            return False


class PaymentAttempt(TimeStampedModel):
    """A single payment attempt for an order.

    An Order may have multiple PaymentAttempts (failed attempt → retry).
    Each attempt is an independent, immutable record of what was sent to
    the gateway and what came back.

    State machine:
        CREATED → REQUESTING → REDIRECT_READY → PENDING → SUCCEEDED
                                                        → FAILED
                                                        → CANCELED
                                                        → EXPIRED

    Once in SUCCEEDED, FAILED, CANCELED, or EXPIRED, the attempt is final.
    """

    class Status(models.TextChoices):
        CREATED = "created", "ایجادشده"
        REQUESTING = "requesting", "در حال درخواست"
        REDIRECT_READY = "redirect_ready", "آماده‌ی هدایت"
        PENDING = "pending", "در انتظار"
        SUCCEEDED = "succeeded", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELED = "canceled", "لغوشده"
        EXPIRED = "expired", "منقضی‌شده"

    FINAL_STATUSES = frozenset({
        Status.SUCCEEDED,
        Status.FAILED,
        Status.CANCELED,
        Status.EXPIRED,
    })

    # --- Relationships ---
    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    gateway_config = models.ForeignKey(
        PaymentGatewayConfig,
        verbose_name="پیکربندی درگاه",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )

    # --- Immutable snapshots ---
    public_id = models.CharField(
        "شناسه‌ی عمومی",
        max_length=32,
        unique=True,
        editable=False,
        help_text="شناسه‌ی غیرترتیبی برای URLها و لاگ‌ها",
    )
    amount = models.DecimalField(
        "مبلغ (اسنپ‌شات)",
        max_digits=14,
        decimal_places=0,
        help_text="مبلغ دقیقاً در لحظه‌ی ایجاد تلاش — تغییرناپذیر",
    )
    currency = models.CharField(
        "واحد پول (اسنپ‌شات)",
        max_length=10,
        default="TOMAN",
        help_text="واحد پولی دقیقاً در لحظه‌ی ایجاد",
    )

    # --- Status ---
    status = models.CharField(
        "وضعیت",
        max_length=15,
        choices=Status.choices,
        default=Status.CREATED,
    )

    # --- Gateway interaction ---
    gateway_track_id = models.CharField(
        "شناسه‌ی پیگیری درگاه",
        max_length=100,
        blank=True,
        default="",
        help_text="trackId یا معادل آن از سمت درگاه",
    )
    gateway_ref_id = models.CharField(
        "شماره ارجاع بانکی",
        max_length=100,
        blank=True,
        default="",
    )
    idempotency_key = models.CharField(
        "کلید یکتایی",
        max_length=64,
        blank=True,
        default="",
        help_text="برای جلوگیری از ایجاد تلاش‌های تکراری",
    )

    # --- Failure info (safe to log/display) ---
    failure_code = models.CharField(
        "کد خطا",
        max_length=50,
        blank=True,
        default="",
    )
    failure_message = models.CharField(
        "پیام خطا (امن)",
        max_length=300,
        blank=True,
        default="",
        help_text="پیام امن بدون اطلاعات حساس — قابل نمایش به مدیر",
    )

    # --- Timestamps ---
    initiated_at = models.DateTimeField(
        "زمان ارسال درخواست",
        null=True,
        blank=True,
    )
    verified_at = models.DateTimeField(
        "زمان تأیید",
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField(
        "زمان انقضا",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "تلاش پرداخت"
        verbose_name_plural = "تلاش‌های پرداخت"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_payment_attempt_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["gateway_track_id"],
                condition=~models.Q(gateway_track_id=""),
                name="uniq_payment_attempt_track_id",
            ),
        ]
        indexes = [
            models.Index(fields=["order", "-created_at"], name="idx_attempt_order_date"),
            models.Index(fields=["store", "status"], name="idx_attempt_store_status"),
        ]

    def __str__(self):
        return f"PaymentAttempt {self.public_id} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.public_id:
            import secrets
            self.public_id = secrets.token_hex(16)
        super().save(*args, **kwargs)

    @property
    def is_final(self) -> bool:
        """Whether this attempt has reached a terminal state."""
        return self.status in self.FINAL_STATUSES

    @property
    def is_successful(self) -> bool:
        return self.status == self.Status.SUCCEEDED


# ===========================================================================
# Refund domain (Admin Panel Completion Program checkpoint 2 — ADR-33/34)
# ===========================================================================


class Refund(TimeStampedModel):
    """درخواست/اجرای استردادِ (کامل یا جزئیِ) یک سفارش.

    مبالغ این مدل از رویِ اسنپ‌شاتِ غیرقابل‌تغییرِ ``Order`` (نه قیمتِ فعلیِ
    Product) محاسبه می‌شوند — نگاه کنید به
    ``apps.orders.services.refund_service.plan_order_refund`` و ADR-33.
    هیچ درگاه پرداختِ واقعیِ این کدبیس، اجرای واقعیِ استرداد را پیاده‌سازی
    نکرده؛ ``refund_method=MANUAL`` صادقانه یعنی «واریزِ خارج از سیستم توسط
    مدیر»، نه انتقالِ خودکارِ پول — نگاه کنید به ADR-33.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        APPROVED = "approved", "تأییدشده"
        PROCESSING = "processing", "در حال پردازش"
        SUCCEEDED = "succeeded", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"

    class Method(models.TextChoices):
        MANUAL = "manual", "دستی (واریز خارج از سیستم)"
        GATEWAY = "gateway", "درگاه پرداخت"

    class Reason(models.TextChoices):
        CUSTOMER_REQUEST = "customer_request", "درخواست مشتری"
        DEFECTIVE_ITEM = "defective_item", "کالای معیوب"
        WRONG_ITEM_SHIPPED = "wrong_item_shipped", "ارسال کالای اشتباه"
        ORDER_CANCELLED = "order_cancelled", "لغو سفارش"
        OTHER = "other", "سایر"

    FINAL_STATUSES = {Status.SUCCEEDED, Status.FAILED, Status.CANCELLED}

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="refunds",
    )
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.PROTECT, related_name="refunds")

    requested_amount = models.DecimalField("مبلغ درخواستی", max_digits=14, decimal_places=0)
    approved_amount = models.DecimalField("مبلغ تأییدشده", max_digits=14, decimal_places=0, null=True, blank=True)
    shipping_refund_amount = models.DecimalField(
        "استردادِ هزینه‌ی ارسال", max_digits=12, decimal_places=0, default=0,
    )
    shipping_tax_refund_amount = models.DecimalField(
        "استردادِ مالیاتِ ارسال", max_digits=12, decimal_places=0, default=0,
    )
    currency = models.CharField("واحد پول", max_length=8, default="IRT")

    reason = models.CharField("علت", max_length=30, choices=Reason.choices, default=Reason.CUSTOMER_REQUEST)
    merchant_note = models.TextField("یادداشت مدیر", blank=True, default="")

    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.PENDING)
    refund_method = models.CharField("روش استرداد", max_length=10, choices=Method.choices, default=Method.MANUAL)
    gateway_transaction_ref = models.CharField("شماره ارجاعِ درگاه", max_length=100, blank=True, default="")

    restock = models.BooleanField("بازگرداندنِ موجودی", default=False)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="refunds_created",
    )
    completed_at = models.DateTimeField("زمان تکمیل", null=True, blank=True)
    failure_reason = models.TextField("علت شکست", blank=True, default="")
    idempotency_key = models.CharField("کلید یکتای درخواست", max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "استرداد"
        verbose_name_plural = "استردادها"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(requested_amount__gte=0), name="refund_requested_amount_non_negative"),
            models.CheckConstraint(
                check=models.Q(approved_amount__isnull=True) | models.Q(approved_amount__gte=0),
                name="refund_approved_amount_non_negative",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_refund_idempotency_key_when_set",
            ),
        ]

    def __str__(self):
        return f"استرداد #{self.pk} — {self.order.code} ({self.get_status_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.order_id and self.store_id and self.order.store_id != self.store_id:
            raise ValidationError({"order": "این سفارش متعلق به فروشگاه دیگری است."})


class RefundItem(TimeStampedModel):
    """سهم هر قلمِ سفارش از یک استرداد."""

    refund = models.ForeignKey(Refund, verbose_name="استرداد", on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(
        OrderItem, verbose_name="قلمِ سفارش", on_delete=models.PROTECT, related_name="refund_items",
    )
    quantity = models.PositiveIntegerField("تعداد")
    amount = models.DecimalField("مبلغ", max_digits=14, decimal_places=0)
    tax_amount = models.DecimalField("مبلغِ مالیاتِ استردادشده", max_digits=14, decimal_places=0, default=0)
    # سهمِ کادوپیچیِ این قلم (خالص از تخفیفِ کد) که در این استرداد برمی‌گردد.
    gift_wrap_amount = models.DecimalField("مبلغِ کادوپیچیِ استردادشده", max_digits=14, decimal_places=0, default=0)

    class Meta:
        verbose_name = "قلمِ استرداد"
        verbose_name_plural = "اقلامِ استرداد"
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="refund_item_quantity_positive"),
            models.CheckConstraint(check=models.Q(amount__gte=0), name="refund_item_amount_non_negative"),
            models.CheckConstraint(check=models.Q(tax_amount__gte=0), name="refund_item_tax_amount_non_negative"),
        ]

    def __str__(self):
        return f"{self.order_item.product_name} × {self.quantity}"


# ===========================================================================
# Return Request domain (Admin Panel Completion Program checkpoint 2 — ADR-34)
# ===========================================================================


class ReturnRequest(TimeStampedModel):
    """درخواستِ مرجوعیِ (کامل یا جزئیِ) یک سفارش — گردشِ وضعیتِ صریح.

    ``created_at`` (از ``TimeStampedModel``) همان «زمانِ درخواست» است؛
    زمان‌های approved/received/completed/rejected به‌صورت جداگانه ثبت
    می‌شوند چون یک درخواست ممکن است بین آن‌ها روزها فاصله بیفتد."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "درخواست‌شده"
        UNDER_REVIEW = "under_review", "در حال بررسی"
        APPROVED = "approved", "تأییدشده"
        REJECTED = "rejected", "ردشده"
        IN_TRANSIT = "in_transit", "در حال ارسال"
        RECEIVED = "received", "دریافت‌شده"
        INSPECTED = "inspected", "بازرسی‌شده"
        COMPLETED = "completed", "تکمیل‌شده"
        CANCELLED = "cancelled", "لغوشده"

    class Reason(models.TextChoices):
        CUSTOMER_REQUEST = "customer_request", "انصراف مشتری"
        DEFECTIVE_ITEM = "defective_item", "کالای معیوب"
        WRONG_ITEM_SHIPPED = "wrong_item_shipped", "ارسال کالای اشتباه"
        SIZE_OR_FIT = "size_or_fit", "عدم تطابق سایز/اندازه"
        OTHER = "other", "سایر"

    ALLOWED_TRANSITIONS = {
        Status.REQUESTED: {Status.UNDER_REVIEW, Status.APPROVED, Status.REJECTED, Status.CANCELLED},
        Status.UNDER_REVIEW: {Status.APPROVED, Status.REJECTED, Status.CANCELLED},
        Status.APPROVED: {Status.IN_TRANSIT, Status.RECEIVED, Status.CANCELLED},
        Status.IN_TRANSIT: {Status.RECEIVED, Status.CANCELLED},
        Status.RECEIVED: {Status.INSPECTED, Status.CANCELLED},
        Status.INSPECTED: {Status.COMPLETED, Status.CANCELLED},
        Status.REJECTED: set(),
        Status.COMPLETED: set(),
        Status.CANCELLED: set(),
    }
    FINAL_STATUSES = {Status.REJECTED, Status.COMPLETED, Status.CANCELLED}

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="return_requests",
    )
    order = models.ForeignKey(Order, verbose_name="سفارش", on_delete=models.PROTECT, related_name="return_requests")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.PROTECT, related_name="return_requests",
    )
    return_number = models.CharField("شماره مرجوعی", max_length=24)

    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField("علت", max_length=30, choices=Reason.choices, default=Reason.CUSTOMER_REQUEST)
    customer_explanation = models.TextField("توضیح مشتری", blank=True, default="")
    merchant_note = models.TextField("یادداشت مدیر", blank=True, default="")
    inspection_result = models.TextField("نتیجه‌ی بازرسی", blank=True, default="")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="آخرین انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="return_requests_handled",
    )
    refund = models.OneToOneField(
        Refund, verbose_name="استردادِ مرتبط", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="return_request",
    )

    approved_at = models.DateTimeField("زمان تأیید", null=True, blank=True)
    received_at = models.DateTimeField("زمان دریافت", null=True, blank=True)
    completed_at = models.DateTimeField("زمان تکمیل", null=True, blank=True)
    rejected_at = models.DateTimeField("زمان رد", null=True, blank=True)

    class Meta:
        verbose_name = "درخواست مرجوعی"
        verbose_name_plural = "درخواست‌های مرجوعی"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "return_number"], name="uniq_return_number_per_store"),
        ]

    def __str__(self):
        return f"{self.return_number} — {self.order.code}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.order_id and self.store_id and self.order.store_id != self.store_id:
            errors["order"] = "این سفارش متعلق به فروشگاه دیگری است."
        if errors:
            raise ValidationError(errors)


class ReturnItem(TimeStampedModel):
    class Condition(models.TextChoices):
        NEW = "new", "نو / بازکردنی نشده"
        OPENED = "opened", "بازشده، سالم"
        DAMAGED = "damaged", "آسیب‌دیده"
        DEFECTIVE = "defective", "معیوب"

    class Resolution(models.TextChoices):
        REFUND = "refund", "استرداد وجه"
        REPLACE = "replace", "تعویض"
        REJECT = "reject", "رد مرجوعی"

    return_request = models.ForeignKey(
        ReturnRequest, verbose_name="درخواست مرجوعی", on_delete=models.CASCADE, related_name="items",
    )
    order_item = models.ForeignKey(
        OrderItem, verbose_name="قلمِ سفارش", on_delete=models.PROTECT, related_name="return_items",
    )
    quantity_requested = models.PositiveIntegerField("تعداد درخواستی")
    quantity_approved = models.PositiveIntegerField("تعداد تأییدشده", null=True, blank=True)
    quantity_received = models.PositiveIntegerField("تعداد دریافت‌شده", null=True, blank=True)
    condition = models.CharField("وضعیت کالا", max_length=10, choices=Condition.choices, blank=True, default="")
    is_restockable = models.BooleanField("قابل بازگشت به موجودی", default=False)
    merchant_resolution = models.CharField(
        "تصمیمِ مدیر", max_length=10, choices=Resolution.choices, blank=True, default="",
    )
    refund_amount = models.DecimalField("مبلغ استردادیِ این قلم", max_digits=14, decimal_places=0, default=0)
    rejection_reason = models.TextField("علت رد", blank=True, default="")
    restocked_at = models.DateTimeField("زمان بازگشت به موجودی", null=True, blank=True)
    # انتخابِ صریحِ مدیر برای این‌که مرجوعی به کدام انبار بازگردد — خالی یعنی
    # سیاستِ پیش‌فرض اجرا شود (انبارِ تأمین‌کننده‌ی اصلی، سپس انبارِ پیش‌فرضِ
    # Store — نگاه کنید به ADR-48 و ``inventory_service.restock_return_item``).
    restock_warehouse = models.ForeignKey(
        "catalog.Warehouse", verbose_name="انبارِ بازگشتِ موجودی", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="return_restocks",
    )

    class Meta:
        verbose_name = "قلمِ مرجوعی"
        verbose_name_plural = "اقلامِ مرجوعی"
        constraints = [
            models.CheckConstraint(check=models.Q(quantity_requested__gt=0), name="return_item_quantity_requested_positive"),
            models.CheckConstraint(
                check=models.Q(quantity_approved__isnull=True) | models.Q(quantity_approved__lte=models.F("quantity_requested")),
                name="return_item_approved_lte_requested",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(quantity_received__isnull=True)
                    | (
                        models.Q(quantity_approved__isnull=False)
                        & models.Q(quantity_received__lte=models.F("quantity_approved"))
                    )
                ),
                name="return_item_received_lte_approved",
            ),
        ]

    def __str__(self):
        return f"{self.order_item.product_name} × {self.quantity_requested}"


class CouponRedemption(TimeStampedModel):
    """دفترِ استفاده از کدِ تخفیف — هر سفارش حداکثر یک ردیف دارد.

    چرخه‌ی عمر: ``RESERVED`` (در لحظه‌ی ثبتِ سفارش) → ``REDEEMED`` (پرداختِ
    موفق) → یا ``RELEASED`` (لغوِ سفارش / پرداختِ ناموفق؛ سهمیه به کد
    برمی‌گردد). ``REFUNDED``: استردادِ کاملِ سفارشِ پرداخت‌شده؛ سهمیه
    **برنمی‌گردد** (سیاستِ صریح: کدِ یک خریدِ تکمیل‌شده دوباره قابل‌استفاده
    نیست). ردیف‌هایِ ``RESERVED``/``REDEEMED``/``REFUNDED`` در سقفِ کل و سقفِ
    هر مشتری شمرده می‌شوند."""

    class Status(models.TextChoices):
        RESERVED = "reserved", "رزروشده"
        REDEEMED = "redeemed", "مصرف‌شده"
        RELEASED = "released", "آزادشده"
        REFUNDED = "refunded", "مستردشده"

    COUNTED_STATUSES = (Status.RESERVED, Status.REDEEMED, Status.REFUNDED)

    coupon = models.ForeignKey(
        "cart.Coupon", verbose_name="کد تخفیف", on_delete=models.PROTECT, related_name="redemptions",
    )
    order = models.OneToOneField(
        Order, verbose_name="سفارش", on_delete=models.CASCADE, related_name="coupon_redemption",
    )
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.PROTECT, related_name="coupon_redemptions",
    )
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.RESERVED, db_index=True)
    discount_amount = models.DecimalField("مبلغِ تخفیف", max_digits=12, decimal_places=0, default=0)
    redeemed_at = models.DateTimeField("زمانِ مصرف", null=True, blank=True)
    released_at = models.DateTimeField("زمانِ آزادسازی", null=True, blank=True)
    release_reason = models.CharField("دلیلِ آزادسازی", max_length=40, blank=True, default="")

    class Meta:
        verbose_name = "استفاده از کد تخفیف"
        verbose_name_plural = "استفاده‌های کد تخفیف"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["coupon", "customer", "status"], name="idx_redemption_coupon_cust"),
        ]

    def __str__(self):
        return f"{self.coupon.code} → {self.order.code} ({self.status})"
