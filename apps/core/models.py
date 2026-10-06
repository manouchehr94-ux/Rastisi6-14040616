import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.storage import private_storage

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ShopSettingsNotProvisionedError(Exception):
    """Raised by ``ShopSettings.load(store=...)`` when the given Store has
    no ``ShopSettings`` row yet.

    Provisioning is an explicit, separate step (``ShopSettings.provision_for``),
    never a silent read-time side effect — this is raised instead of
    auto-creating a row on read, so a missing row is a visible error, not a
    quietly-materializing default.
    """


def validate_hex_color(value):
    """اعتبارسنجی رنگ #RRGGBB در سطح مدل."""
    if not HEX_COLOR_RE.match(value):
        raise ValidationError("رنگ باید به فرمت #RRGGBB باشد")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ بروزرسانی", auto_now=True)

    class Meta:
        abstract = True


class ShopSettings(TimeStampedModel):
    """تنظیمات هر فروشگاه — دقیقاً یک رکورد به‌ازای هر Store.

    منبع واحد حقیقت برای هویت فروشگاه و قواعد قیمت‌گذاریِ همان Store؛ هم پنل
    مدیریت این رکورد را ویرایش می‌کند، هم سرویس pricing و context processor
    سراسری سایت همین رکورد را می‌خوانند — نه یک عدد جدا.

    ``store`` یک ``OneToOneField`` است: دقیقاً یک ``ShopSettings`` به ازای هر
    Store، نه یک رکورد تکی برای کل پلتفرم. برندینگ/تم (رنگ‌ها، لوگو، فاوآیکون)
    عمداً همچنان همین‌جا هستند — جداسازی این حوزه به مدل‌های اختصاصی یک
    تصمیم معماری جداگانه‌ی بعدی است، نه بخشی از این مرحله (نگاه کنید به
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md`` ADR-10).

    فیلدهای زیرساختِ پیامک (``sms_backend``/``melipayamak_*``/
    ``kavenegar_api_key``) به دلایلِ سازگاریِ عقب‌رو (migration بدون تغییرِ
    schema) هنوز همین‌جا تعریف شده‌اند، اما دیگر منبعِ واقعیِ اعتبارنامه
    نیستند — ``apps.sms.services.sms_service.get_backend`` این‌ها را
    نادیده می‌گیرد (به‌جز مقدارِ ``SMSRASTI``، دستگاهِ خودِ Store) و به‌جایش
    از ``apps.portal.models.PlatformConfiguration`` (رمزنگاری‌شده) می‌خواند؛
    نگاه کنید به گزارشِ «جداسازیِ تنظیماتِ پیامک» برایِ دلیلِ کامل.
    """

    store = models.OneToOneField(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="shop_settings",
    )

    name = models.CharField("نام فروشگاه", max_length=150, default="فروشگاه اینترنتی")
    tagline = models.CharField("شعار فروشگاه", max_length=200, blank=True)
    description = models.TextField("توضیحات فروشگاه (درباره ما)", blank=True)
    contact_phone = models.CharField("شماره تماس", max_length=30, blank=True)
    contact_email = models.EmailField("ایمیل فروشگاه", blank=True)
    contact_address = models.CharField("آدرس", max_length=300, blank=True)

    tax_percent = models.DecimalField("نرخ مالیات (٪)", max_digits=5, decimal_places=2, default=9)
    free_shipping_threshold = models.DecimalField(
        "آستانه‌ی ارسال رایگان (تومان)", max_digits=12, decimal_places=0, default=500_000
    )

    class TaxRoundingPolicy(models.TextChoices):
        ON_TOTAL = "on_total", "گردکردنِ مجموع"
        PER_LINE = "per_line", "گردکردنِ هر ردیف"

    # ``tax_enabled`` پیش‌فرضش True است — نه یک انتخابِ دلخواه، بلکه بازتابِ
    # رفتارِ همیشگیِ این کدبیس پیش از checkpoint 3B: tax_percent همیشه و
    # بدونِ قید روی هر سبدی اعمال می‌شد (نگاه کنید به ADR-44). خاموش‌کردنِ
    # آن اکنون یک اقدامِ صریحِ مدیر است، نه رفتارِ پیش‌فرضِ جدید.
    tax_enabled = models.BooleanField("فعال‌سازیِ مالیات", default=True)
    # False یعنی قیمت‌ها بدونِ مالیات‌اند و مالیات جداگانه افزوده می‌شود —
    # دقیقاً همان محاسبه‌ی قبلیِ ``cart_totals`` (مالیات روی after_coupon
    # افزوده می‌شد، نه جزئی از آن).
    prices_include_tax = models.BooleanField("قیمت‌ها شاملِ مالیات‌اند", default=False)
    # False یعنی هزینه‌ی ارسال مشمولِ مالیات نیست — دقیقاً رفتارِ قبلی
    # (``cart_totals`` مالیات را فقط روی after_coupon حساب می‌کرد، نه
    # shipping_cost).
    shipping_taxable = models.BooleanField("ارسال مشمولِ مالیات است", default=False)
    default_tax_class = models.ForeignKey(
        "orders.TaxClass", verbose_name="دسته‌ی مالیاتیِ پیش‌فرض", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="default_for_stores",
    )
    # پیش‌فرض «گردکردنِ مجموع» — دقیقاً همان رفتارِ قبلی (یک بارگردکردن روی
    # کلِ مبلغ، نه به‌ازای هر ردیف).
    tax_rounding_policy = models.CharField(
        "سیاستِ گردکردنِ مالیات", max_length=20, choices=TaxRoundingPolicy.choices, default=TaxRoundingPolicy.ON_TOTAL,
    )
    # خالی یعنی مالیات هنوز صراحتاً پیکربندی نشده — مدیر هنوز صفحه‌ی
    # «مالیات ندارم / مالیات دارم» را ذخیره نکرده، حتی اگر ``tax_enabled``
    # (که پیش‌فرضش True است) هنوز به مقدارِ پیش‌فرض دست‌نخورده باشد. این
    # فیلد تنها سیگنالِ «مدیر تصمیمِ صریح گرفت» است — نه یک موتورِ مالیاتیِ
    # تازه، فقط نشانه‌ی تکمیلِ مرحله‌ی چک‌لیست.
    tax_setup_confirmed_at = models.DateTimeField("زمانِ تاییدِ صریحِ تنظیماتِ مالیات", null=True, blank=True)

    # کادوپیچی (Gift wrap) — افزونه‌ی اختیاریِ سبد خرید که فقط با تنظیمِ صریحِ
    # مدیر در دسترسِ مشتری قرار می‌گیرد (toranj_gifting family:
    # ``optional_addon_checkbox_updates_total``). ``gift_wrap_available=False``
    # (پیش‌فرض) یعنی هیچ چک‌باکسِ کادوپیچی به مشتری نمایش داده نمی‌شود — نه در
    # این خانواده و نه در بقیه؛ این کنترل کاملاً مستقل از خانواده‌ی بصریِ
    # فروشگاه است (هر Storeای، با هر خانواده، می‌تواند این را فعال کند).
    # قیمت همیشه از همین رکورد (سمتِ سرور) خوانده می‌شود — سبد/سرور هرگز به
    # قیمتِ ارسال‌شده‌ی کلاینت برای این افزونه اعتماد نمی‌کند.
    gift_wrap_available = models.BooleanField("کادوپیچی در دسترس است", default=False)
    gift_wrap_price = models.DecimalField(
        "هزینه‌ی کادوپیچی (تومان؛ ۰ = رایگان)", max_digits=12, decimal_places=0, default=0,
    )

    class GiftWrapScope(models.TextChoices):
        PER_UNIT = "per_unit", "به‌ازای هر عددِ کالا"
        PER_LINE = "per_line", "به‌ازای هر ردیفِ سبد"
        PER_ORDER = "per_order", "یک‌بار برای کلِ سفارش"

    # سیاستِ صریحِ محاسبه‌ی هزینه‌ی کادوپیچی — پیش‌فرض ``per_unit`` تا رفتارِ
    # قبلی (تعداد × قیمت) حفظ شود. نگاه کنید به ``gift_wrap_service.gift_wrap_charge``.
    gift_wrap_pricing_scope = models.CharField(
        "مبنای محاسبه‌ی هزینه‌ی کادوپیچی", max_length=10, choices=GiftWrapScope.choices,
        default=GiftWrapScope.PER_UNIT,
    )
    gift_wrap_title = models.CharField("عنوان سرویسِ کادوپیچی", max_length=80, default="کادوپیچی")
    gift_wrap_description = models.CharField("توضیحِ سرویسِ کادوپیچی", max_length=300, blank=True, default="")
    gift_wrap_image = models.ImageField("تصویرِ نمونه‌ی کادوپیچی", upload_to="shop/gift_wrap/", blank=True)
    gift_wrap_message_enabled = models.BooleanField("امکانِ نوشتنِ پیامِ کارت‌هدیه", default=True)

    # --- انقضایِ سفارش‌هایِ پرداخت‌نشده‌ی آنلاین (پیش‌فرض: غیرفعال) ---
    unpaid_online_order_ttl_minutes = models.PositiveIntegerField(
        "مهلتِ پرداختِ سفارشِ آنلاین (دقیقه؛ ۰ = غیرفعال)", default=0,
        help_text="سفارشِ در انتظارِ پرداختِ آنلاین پس از این مدت لغو می‌شود (موجودی و ظرفیتِ کدِ تخفیف برمی‌گردد). "
                  "۰ یعنی هرگز. مقدارِ پیشنهادی ۶۰ — باید از طولِ عمرِ نشستِ درگاه بیشتر باشد.",
    )
    unpaid_online_order_grace_minutes = models.PositiveIntegerField(
        "مهلتِ تکمیلی برایِ پرداختِ در حال انجام (دقیقه)", default=30,
        help_text="سفارشی که تلاشِ پرداختِ بازی با فعالیتِ کمتر از این مدت دارد منقضی نمی‌شود.",
    )
    unpaid_expiry_notify_sms = models.BooleanField("ارسالِ پیامکِ لغو هنگامِ انقضا", default=False)

    class SmsBackend(models.TextChoices):
        CONSOLE = "console", "کنسول (فقط لاگ، برای توسعه)"
        MELIPAYAMAK = "melipayamak", "ملی‌پیامک"
        KAVENEGAR = "kavenegar", "کاوه‌نگار"
        # Store-scoped فقط — هیچ‌جای apps.portal.services.owner_sms_service
        # (OTP هویتِ مالک/کارمندِ پلتفرم) موردی برایِ این backend ندارد؛
        # صفی/async بودنِ آن (poll دستگاهِ اندروید) با نیازِ ارسالِ فوریِ
        # OTP هویت ناسازگار است (apps.sms.services.sms_service نیز آن را
        # برایِ SmsEvent.OTP رد می‌کند، نه فقط برایِ auth پلتفرم).
        SMSRASTI = "smsrasti", "اسمس‌راستی (گیت‌وی اندروید)"

    sms_enabled = models.BooleanField("فعال‌سازی سیستم پیامک", default=True)
    sms_backend = models.CharField(
        "درگاه پیامک", max_length=20, choices=SmsBackend.choices, default=SmsBackend.CONSOLE
    )
    sms_sender_number = models.CharField("شماره‌ی فرستنده", max_length=20, blank=True)
    melipayamak_username = models.CharField("نام کاربری ملی‌پیامک", max_length=100, blank=True)
    melipayamak_password = models.CharField("رمز عبور ملی‌پیامک", max_length=100, blank=True)
    kavenegar_api_key = models.CharField("کلید API کاوه‌نگار", max_length=100, blank=True)
    smsrasti_device_token = models.CharField(
        "توکنِ دستگاهِ اسمس‌راستی", max_length=64, blank=True, unique=True, null=True,
    )
    #: آخرین poll موفقِ دستگاهِ SmsRasti — تنها نشانه‌ی قابل‌اندازه‌گیریِ «دستگاه متصل است».
    smsrasti_last_seen_at = models.DateTimeField("آخرین اتصالِ دستگاهِ اسمس‌راستی", null=True, blank=True)

    # --- هویت بصری ---
    logo = models.ImageField("لوگوی فروشگاه", upload_to="shop/branding/", blank=True)
    favicon = models.ImageField("فاوآیکون", upload_to="shop/branding/", blank=True)
    primary_color = models.CharField("رنگ اصلی", max_length=7, default="#6D28D9", validators=[validate_hex_color])
    accent_color = models.CharField("رنگ مکمل", max_length=7, default="#FF4D77", validators=[validate_hex_color])
    secondary_color = models.CharField("رنگ ثانویه", max_length=7, default="#7C3AED", validators=[validate_hex_color])
    background_color = models.CharField(
        "رنگ پس‌زمینه‌ی صفحه", max_length=7, default="#F7F5FC", validators=[validate_hex_color]
    )
    surface_color = models.CharField(
        "رنگ پس‌زمینه‌ی کارت‌ها", max_length=7, default="#FFFFFF", validators=[validate_hex_color]
    )
    text_color = models.CharField("رنگ متن اصلی", max_length=7, default="#241C3A", validators=[validate_hex_color])
    muted_text_color = models.CharField(
        "رنگ متن کم‌رنگ", max_length=7, default="#8B86A3", validators=[validate_hex_color]
    )

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

    def __str__(self):
        return self.name

    @property
    def sms_delivery_method(self) -> str:
        """تنها دو روشِ ارسال برایِ پیامکِ مشتریانِ فروشگاه: ``phone`` (گیت‌وی اندرویدِ SmsRasti) یا
        ``platform`` (درگاهِ مرکزیِ پلتفرم). مقدارهایِ قدیمیِ console/melipayamak/kavenegar همگی «platform» اند
        (همان کاری که ``sms_service.get_backend`` همیشه می‌کرد)."""
        return "phone" if self.sms_backend == self.SmsBackend.SMSRASTI else "platform"

    @classmethod
    def load(cls, store=None) -> "ShopSettings":
        """تنظیمات یک Store مشخص، یا در حالت سازگاری موقت، تنظیمات Akhlaghi.

        ``store`` مشخص شود: فقط همان Store برگردانده می‌شود؛ اگر هنوز
        provision نشده باشد ``ShopSettingsNotProvisionedError`` raise
        می‌شود — هرگز تنظیمات یک Store دیگر را برنمی‌گرداند و رکورد جدید هم
        در زمان خواندن ساخته نمی‌شود (provisioning یک قدم صریح و جداست، نه
        اثر جانبی خواندن).

        ``store`` مشخص نشود (حالت سازگاری موقت): فقط وقتی دقیقاً یک Store
        فعال با اسلاگ ``"akhlaghi"`` در کل دیتابیس وجود داشته باشد کار
        می‌کند؛ در غیر این صورت — صفر یا بیش از یک Store — با
        ``apps.stores.resolution.CompatibilityFallbackUnavailableError``
        fail-closed می‌شود (به جای حدس زدن). همان قانون fail-closed منبع
        واحدی دارد که با تحلیل میزبان HTTP هم مشترک است
        (``apps.stores.resolution.resolve_compatibility_store``).
        """
        if store is not None:
            try:
                return cls.objects.get(store=store)
            except cls.DoesNotExist as exc:
                raise ShopSettingsNotProvisionedError(
                    f"Store {store.slug!r} has no ShopSettings row yet; "
                    "provision it explicitly via ShopSettings.provision_for(store)."
                ) from exc

        from apps.stores.resolution import resolve_compatibility_store

        compat_store = resolve_compatibility_store()
        try:
            return cls.objects.get(store=compat_store)
        except cls.DoesNotExist as exc:
            raise ShopSettingsNotProvisionedError(
                f"Store {compat_store.slug!r} has no ShopSettings row yet; "
                "provision it explicitly via ShopSettings.provision_for(store)."
            ) from exc

    @classmethod
    def provision_for(cls, store) -> "ShopSettings":
        """رکورد ShopSettings یک Store را می‌سازد؛ اگر از قبل وجود داشته باشد
        دست‌نخورده برمی‌گردد (idempotent) — هرگز مقادیر تاجر را بازنویسی
        نمی‌کند.

        ``name`` از ``store.name`` (مقدارِ واقعیِ داده‌شده توسطِ کاربر هنگامِ
        ساختِ فروشگاه) گرفته می‌شود، نه از ``settings.SHOP_NAME`` — آن
        تنظیمات فقط هویتِ عمومیِ *پلتفرم* (یک نمونه‌ی نوعی/مثالی، نه هیچ
        فروشگاهِ واقعی) است و هرگز نباید به‌عنوانِ دادهٔ واقعیِ یک Store تازه
        در دیتابیس ذخیره شود. مشابهاً ``tagline``/``contact_*`` برایِ یک
        فروشگاهِ تازه واقعاً خالی می‌مانند، نه مقدارِ نمونه‌ای/مثالیِ همان
        تنظیمات — تا مرچنت هیچ‌گاه محتوایِ مثالی را به‌اشتباه به‌عنوانِ دادهٔ
        واقعیِ خودش ذخیره نکند (ویزاردِ آنبوردینگ، ``OnboardingIdentityForm``،
        این مقادیرِ خالی را به‌عنوانِ placeholder نشان می‌دهد، نه value).
        مقادیرِ عددیِ کسب‌وکار (``tax_percent``/``free_shipping_threshold``)
        همچنان از settings.py می‌آیند — آن‌ها پیش‌فرضِ کسب‌وکاری‌اند، نه متنِ
        هویتی/مثالی.
        """
        from django.conf import settings as django_settings

        obj, _ = cls.objects.get_or_create(
            store=store,
            defaults={
                "name": store.name or "فروشگاه اینترنتی",
                "tagline": "",
                "contact_phone": "",
                "contact_email": "",
                "contact_address": "",
                "tax_percent": getattr(django_settings, "SHOP_TAX_PERCENT", 9),
                "free_shipping_threshold": getattr(
                    django_settings, "SHOP_FREE_SHIPPING_THRESHOLD", 500_000
                ),
            },
        )
        return obj


class AuditLogEntry(models.Model):
    """رخداد حسابرسیِ Store-owned — یک ردیفِ تغییرناپذیر به‌ازای هر عملیاتِ
    حساس (نگاه کنید به ADR-36 در ``SAAS_DOMAIN_DECISIONS.md``).

    فقط ``created_at`` دارد، نه ``updated_at`` — یک رخداد حسابرسی هرگز پس از
    ثبت ویرایش نمی‌شود؛ اگر لازم شود، یک رخداد اصلاحیِ جدید ثبت می‌شود، نه
    ویرایشِ رکورد قدیمی. ``object_type``/``object_id`` عمداً رشته/عدد ساده‌اند
    (نه ``ContentType`` جنگو) تا این مدل به هیچ اپ دیگری کوپل نشود و بتواند
    رخدادهایی که اصلاً به یک ردیفِ دیتابیسی خاص اشاره نمی‌کنند (مثلاً ورود
    ناموفق) را هم ثبت کند.

    ``ip_address``/``user_agent`` عمداً وجود ندارند: این کدبیس تاکنون هیچ
    سیاست حریم خصوصیِ مصوبی برای نگه‌داریِ IP/User-Agent کاربران ندارد
    (نگاه کنید به ADR-36) — افزودنِ این فیلدها بدون چنین تصمیمی، جمع‌آوریِ
    دادهٔ شخصیِ بی‌سیاست خواهد بود.
    """

    class ResultStatus(models.TextChoices):
        SUCCESS = "success", "موفق"
        FAILURE = "failure", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="audit_log_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_log_entries",
    )
    action_code = models.CharField("کد عملیات", max_length=60, db_index=True)
    object_type = models.CharField("نوع شیء", max_length=60, blank=True, default="")
    object_id = models.CharField("شناسه‌ی شیء", max_length=40, blank=True, default="")
    object_label = models.CharField("برچسبِ قابل‌خواندنِ شیء", max_length=200, blank=True, default="")
    before_summary = models.TextField("خلاصه‌ی پیش از تغییر", blank=True, default="")
    after_summary = models.TextField("خلاصه‌ی پس از تغییر", blank=True, default="")
    metadata = models.JSONField("فراداده", blank=True, default=dict)
    request_id = models.CharField("شناسه‌ی درخواست/idempotency", max_length=100, blank=True, default="")
    result = models.CharField(
        "نتیجه", max_length=10, choices=ResultStatus.choices, default=ResultStatus.SUCCESS,
    )
    created_at = models.DateTimeField("زمان", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "رخداد حسابرسی"
        verbose_name_plural = "گزارش رخدادها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "-created_at"], name="idx_audit_store_created"),
            models.Index(fields=["store", "action_code", "-created_at"], name="idx_audit_store_action"),
        ]

    def __str__(self):
        return f"{self.action_code} — {self.object_label or self.object_type} ({self.get_result_display()})"


def export_job_upload_path(instance, filename: str) -> str:
    """مسیرِ ذخیره‌ی فایلِ خروجیِ یک ``ExportJob`` را می‌سازد — عمداً نامِ
    فایلِ اصلی (``filename``) را در مسیر استفاده نمی‌کند و به‌جایِ آن یک
    نامِ تصادفیِ UUID تولید می‌کند، تا هیچ ورودیِ کاربر (حتی نامِ فایل)
    مستقیماً وارد مسیرِ دیسک نشود (محافظت در برابر Path Traversal — نگاه
    کنید به ADR-52). فایل‌ها زیرِ ``exports/<store_id>/`` جدا می‌شوند تا
    حتی در سطحِ فایل‌سیستم هم داده‌ی دو Store در یک پوشه مخلوط نشود."""
    # خروجی‌هایِ تازه همیشه XLSX‌اند؛ فایل‌هایِ CSVِ قدیمی با همان مسیرِ خود
    # ذخیره‌شده‌اند و دست‌نخورده می‌مانند.
    ext = "xlsx"
    return f"exports/{instance.store_id}/{uuid.uuid4().hex}.{ext}"


class ExportJob(models.Model):
    """یک درخواستِ صادراتِ CSV برای یک Store — نگاه کنید به ADR-52 و
    ``docs/architecture/SAAS_DOMAIN_DECISIONS.md``.

    از «خروجِ مستقیم» به بعد (data-transfer-safety-v1) این رکورد *فقط فرادادهٔ
    حسابرسی* است: فایلِ XLSX در همان پاسخِ HTTP برگردانده می‌شود و هیچ‌جا ذخیره
    نمی‌شود، پس برایِ خروجِ تازه ``file`` خالی و ``expires_at`` بدونِ مقدار است.
    فایل‌هایِ قدیمی (پیش از این تغییر) تا زمانِ انقضایِ خودشان با همین رکورد قابلِ
    دانلودند و ``cleanup_expired_exports`` آن‌ها را حذف می‌کند. فایلِ قدیمی، اگر
    وجود داشته باشد، در ``apps.core.storage.private_storage`` است — هرگز زیرِ
    ``MEDIA_ROOT``/``MEDIA_URL`` عمومی و فقط با ویوی authenticated و Store-scoped.
    """

    class ExportType(models.TextChoices):
        PRODUCTS = "products", "کالاها"
        VARIANTS = "variants", "تنوع‌ها"
        INVENTORY = "inventory", "موجودیِ انبار"
        CUSTOMERS = "customers", "مشتریان"
        ORDERS = "orders", "سفارش‌ها"

    class Status(models.TextChoices):
        PENDING = "pending", "در صف"
        PROCESSING = "processing", "در حالِ پردازش"
        COMPLETED = "completed", "تکمیل‌شده"
        FAILED = "failed", "ناموفق"
        EXPIRED = "expired", "منقضی‌شده"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="export_jobs",
    )
    export_type = models.CharField("نوعِ خروجِ اطلاعات", max_length=20, choices=ExportType.choices)
    status = models.CharField(
        "وضعیت", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="درخواست‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="export_jobs",
    )
    filters = models.JSONField("فیلترهای اعمال‌شده", blank=True, default=dict)
    selected_fields = models.JSONField("ستون‌های انتخاب‌شده", blank=True, default=list)
    file = models.FileField(
        "فایل خروجی", upload_to=export_job_upload_path, storage=private_storage,
        max_length=255, blank=True,
    )
    row_count = models.PositiveIntegerField("تعداد ردیف", default=0)
    error_message = models.TextField("پیام خطا", blank=True, default="")
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    started_at = models.DateTimeField("زمان شروع پردازش", null=True, blank=True)
    completed_at = models.DateTimeField("زمان پایان", null=True, blank=True)
    expires_at = models.DateTimeField("زمان انقضا", null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "درخواستِ خروجِ اطلاعات"
        verbose_name_plural = "درخواست‌هایِ خروجِ اطلاعات"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "-created_at"], name="idx_export_store_created"),
            models.Index(fields=["store", "status"], name="idx_export_store_status"),
        ]

    def __str__(self):
        return f"{self.get_export_type_display()} — {self.store.slug} ({self.get_status_display()})"


def import_job_upload_path(instance, filename: str) -> str:
    """مسیرِ ذخیره‌ی فایلِ منبعِ یک ``ImportJob`` را می‌سازد — دقیقاً همان
    استدلالِ ``export_job_upload_path``: نامِ فایلِ اصلی هرگز در مسیرِ دیسک
    استفاده نمی‌شود (محافظت در برابرِ Path Traversal، نگاه کنید به ADR-62).
    فقط *پسوندِ* فایل (از یک فهرستِ سفید: xlsx/csv) حفظ می‌شود تا فایلِ منبع در
    قالبِ اصلیِ خودش دانلود شود."""
    extension = "xlsx" if (filename or "").lower().endswith(".xlsx") else "csv"
    return f"imports/{instance.store_id}/{uuid.uuid4().hex}.{extension}"


def import_error_report_upload_path(instance, filename: str) -> str:
    extension = "xlsx" if (filename or "").lower().endswith(".xlsx") else "csv"
    return f"imports/{instance.store_id}/errors/{uuid.uuid4().hex}.{extension}"


class ImportJob(models.Model):
    """یک درخواستِ واردات CSV برای یک Store — نگاه کنید به ADR-55/ADR-56/ADR-62.

    مانندِ ``ExportJob``، هیچ صفِ کارِ پس‌زمینه‌ای پشتِ این نیست (ADR-49) —
    پیش‌نمایش و اجرا هر دو همگام، در همان چرخه‌ی درخواست/پاسخ انجام می‌شوند؛
    وضعیت‌ها همچنان برای تاریخچه/UI ثبت می‌شوند."""

    class ImportType(models.TextChoices):
        PRODUCTS = "products", "کالاها"
        VARIANTS = "variants", "تنوع‌ها"
        INVENTORY = "inventory", "موجودیِ انبار"

    class Mode(models.TextChoices):
        CREATE_ONLY = "create_only", "فقط ایجاد"
        UPDATE_ONLY = "update_only", "فقط به‌روزرسانی"
        UPSERT = "upsert", "ایجاد یا به‌روزرسانی (Upsert)"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "بارگذاری‌شده"
        VALIDATING = "validating", "در حالِ اعتبارسنجی"
        PREVIEW_READY = "preview_ready", "پیش‌نمایش آماده"
        PROCESSING = "processing", "در حالِ پردازش"
        COMPLETED = "completed", "تکمیل‌شده"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "تکمیل‌شده با خطا"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"

    FINAL_STATUSES = {Status.COMPLETED, Status.COMPLETED_WITH_ERRORS, Status.FAILED, Status.CANCELLED}

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="import_jobs",
    )
    import_type = models.CharField("نوعِ اطلاعاتِ ورودی", max_length=20, choices=ImportType.choices)
    original_filename = models.CharField("نامِ اصلیِ فایل", max_length=255, blank=True, default="")
    source_file = models.FileField(
        "فایلِ منبع", upload_to=import_job_upload_path, storage=private_storage,
        max_length=255, blank=True,
    )
    status = models.CharField(
        "وضعیت", max_length=22, choices=Status.choices, default=Status.UPLOADED, db_index=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="درخواست‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="import_jobs",
    )
    mode = models.CharField("حالتِ اجرا", max_length=12, choices=Mode.choices, default=Mode.UPSERT)
    dry_run = models.BooleanField("اجرای آزمایشی (Dry Run)", default=True)
    # خالی یعنی «بدون کلیدِ صریح» — یکتایی فقط وقتی مقدار دارد اجرا می‌شود،
    # دقیقاً همان الگویِ ``Order.idempotency_key``/``ProductVariant.sku``.
    idempotency_key = models.CharField("کلیدِ یکتایِ درخواست", max_length=64, blank=True, default="")

    total_rows = models.PositiveIntegerField("مجموعِ ردیف‌ها", default=0)
    valid_rows = models.PositiveIntegerField("ردیف‌هایِ معتبر", default=0)
    invalid_rows = models.PositiveIntegerField("ردیف‌هایِ نامعتبر", default=0)
    created_rows = models.PositiveIntegerField("ردیف‌هایِ ایجادشده", default=0)
    updated_rows = models.PositiveIntegerField("ردیف‌هایِ به‌روزرسانی‌شده", default=0)
    skipped_rows = models.PositiveIntegerField("ردیف‌هایِ ردشده", default=0)
    failed_rows = models.PositiveIntegerField("ردیف‌هایِ ناموفق", default=0)

    error_summary = models.TextField("خلاصه‌ی خطا", blank=True, default="")
    error_report_file = models.FileField(
        "فایلِ گزارشِ خطا", upload_to=import_error_report_upload_path, storage=private_storage,
        max_length=255, blank=True,
    )

    created_at = models.DateTimeField("زمانِ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("زمانِ به‌روزرسانی", auto_now=True)
    started_at = models.DateTimeField("زمانِ شروعِ پردازش", null=True, blank=True)
    completed_at = models.DateTimeField("زمانِ پایان", null=True, blank=True)

    class Meta:
        verbose_name = "درخواستِ ورودِ اطلاعات"
        verbose_name_plural = "درخواست‌هایِ ورودِ اطلاعات"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "-created_at"], name="idx_import_store_created"),
            models.Index(fields=["store", "status"], name="idx_import_store_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "idempotency_key"], condition=~models.Q(idempotency_key=""),
                name="uniq_importjob_idempotency_key_per_store",
            ),
        ]

    def __str__(self):
        return f"{self.get_import_type_display()} — {self.store.slug} ({self.get_status_display()})"


class ImportRowResult(models.Model):
    """نتیجه‌ی پردازشِ یک ردیفِ منفردِ یک ``ImportJob`` — نگاه کنید به ADR-56.

    ``normalized_data_summary`` عمداً یک خلاصه‌ی کوچک و امن است (نه کلِ
    ردیفِ خام) — هرگز رمز/توکن/دادهٔ حساس در آن ذخیره نمی‌شود."""

    class RowStatus(models.TextChoices):
        VALID = "valid", "معتبر"
        INVALID = "invalid", "نامعتبر"
        CREATED = "created", "ایجادشده"
        UPDATED = "updated", "به‌روزرسانی‌شده"
        SKIPPED = "skipped", "ردشده"
        FAILED = "failed", "ناموفق"

    import_job = models.ForeignKey(
        ImportJob, verbose_name="درخواستِ ورودِ اطلاعات", on_delete=models.CASCADE, related_name="row_results",
    )
    row_number = models.PositiveIntegerField("شماره‌ی ردیف")
    source_identifier = models.CharField("شناسه‌ی منبع", max_length=120, blank=True, default="")
    status = models.CharField("وضعیت", max_length=10, choices=RowStatus.choices)
    normalized_data_summary = models.JSONField("خلاصه‌ی داده‌ی نرمال‌شده", blank=True, default=dict)
    errors = models.JSONField("خطاها", blank=True, default=list)
    warnings = models.JSONField("هشدارها", blank=True, default=list)
    target_object_type = models.CharField("نوعِ شیءِ هدف", max_length=30, blank=True, default="")
    target_object_id = models.PositiveIntegerField("شناسه‌ی شیءِ هدف", null=True, blank=True)

    created_at = models.DateTimeField("زمانِ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("زمانِ به‌روزرسانی", auto_now=True)

    class Meta:
        verbose_name = "نتیجه‌ی ردیفِ ورودِ اطلاعات"
        verbose_name_plural = "نتایجِ ردیف‌هایِ ورودِ اطلاعات"
        ordering = ["import_job_id", "row_number"]
        indexes = [
            models.Index(fields=["import_job", "status"], name="idx_importrow_job_status"),
            models.Index(fields=["import_job", "row_number"], name="idx_importrow_job_rownum"),
            models.Index(fields=["import_job", "source_identifier"], name="idx_importrow_job_srcid"),
        ]

    def __str__(self):
        return f"ردیفِ {self.row_number} — {self.get_status_display()}"
