"""کاتالوگِ کانونیکِ قابلیت‌هایِ صفحه‌ی تعرفه و ماتریسِ مقایسه.

قاعده‌ی طلایی: **ماتریسِ عمومی از همین کاتالوگ + مقادیرِ واقعیِ ``PlanEntitlement`` ساخته می‌شود** و
هیچ ادعایی نمی‌کند که در کد وجود ندارد.

هر ردیف یکی از سه حالت است:

* ``entitlement`` پر است ⇒ **قابلِ کنترل در پلن**: کلیدِ Entitlement واقعاً در لایه‌ی سرویس اعمال می‌شود
  (فهرستِ ``ENFORCED_ENTITLEMENT_KEYS``؛ تستِ رفتاری برایِ تک‌تکِ آن‌ها وجود دارد) و ماتریس مقدارِ هر پلن را
  (✓ / عدد / نامحدود / —) از نسخه‌ی منتشرشده می‌خواند.
* ``entitlement`` خالی و ``availability`` در (implemented / partial / external) ⇒ **همراهِ همه‌ی پلن‌ها**:
  قابلیتی که در محصول هست و بر اساسِ پلن بسته نمی‌شود. ماتریس آن را «همه‌ی پلن‌ها» نشان می‌دهد؛ مدیر نمی‌تواند
  آن را برایِ یک پلن خاموش کند، چون کد چنین چیزی را اعمال نمی‌کند.
* ``availability == planned`` ⇒ در محصول نیست؛ **هرگز عمومی نمی‌شود** (فقط در گزارشِ شکافِ مدیر دیده می‌شود).

``evidence`` مسیرِ کدی است که قابلیت را پیاده می‌کند (برایِ ممیزی و گزارشِ شکاف). ردیف‌هایِ مرجعِ خارجی
(۷۶ ردیفِ مقایسه) پس از دریافتِ فایلِ مرجع با افزودنِ ردیف به همین فهرست و اجرایِ ``sync_feature_catalog`` اضافه می‌شوند."""

from dataclasses import dataclass

from apps.subscriptions import capability_registry
from apps.subscriptions import entitlements as ekeys

STORE, INFRA, SEO, PAY, DESIGN, MARKETING, SERVICES = (
    "store_operations", "infrastructure", "seo_content", "payments", "design", "marketing", "services",
)
IMPL, PARTIAL, EXTERNAL, PLANNED = "implemented", "partial", "external", "planned"

DOMAINS_CUSTOM = capability_registry.DOMAINS_CUSTOM

#: کلیدهایِ اعمال‌شده = رجیستریِ کد (``capability_registry``). *Snapshot* در زمانِ import؛ کدی که باید قابلیت‌هایِ ثبت‌شده‌یِ
#: همین لحظه را ببیند از ``capability_registry.registered_keys()`` استفاده می‌کند.
ENFORCED_ENTITLEMENT_KEYS = capability_registry.registered_keys()

@dataclass(frozen=True)
class Feature:
    key: str
    category: str
    title: str
    description: str
    availability: str = IMPL
    entitlement: str = ""          # فقط برایِ کلیدهایِ ENFORCED
    unit: str = ""
    note: str = ""                 # شفاف‌سازی (مثلاً «نیازمندِ قرارداد با درگاه»)
    evidence: str = ""             # مسیرِ پیاده‌سازی (برایِ ممیزی)


CATALOG: tuple[Feature, ...] = (
    # ------------------------------------------------------------------ عملیاتِ فروشگاه
    Feature("products", STORE, "تعدادِ کالا", "حداکثرِ تعدادِ کالایِ فعال در فروشگاه. ساختِ کالا (دستی، سریع، واردات) همگی از همین سقف عبور می‌کنند.", entitlement=ekeys.CATALOG_PRODUCTS, unit="کالا", evidence="apps/subscriptions/services/enforcement.py::enforce_can_create_product"),
    Feature("variants", STORE, "تعدادِ تنوعِ کالا", "سقفِ تنوع‌هایِ (رنگ/سایز/…) فروشگاه؛ موتورِ تنوع هنگامِ ساخت آن را اعمال می‌کند.", entitlement=ekeys.CATALOG_VARIANTS, unit="تنوع", evidence="apps/catalog/services/variant_engine_service.py"),
    Feature("categories_brands", STORE, "دسته‌بندی، برند و ویژگی‌هایِ کالا", "ساختارِ کاتالوگ با دسته‌ها، برندها، ویژگی‌ها و مجموعه‌ها.", evidence="apps/catalog; dashboard categories/brands/attributes/collections"),
    Feature("orders", STORE, "مدیریتِ سفارش، مرجوعی و استرداد", "فهرست و جزئیاتِ سفارش، فاکتور، مرجوعی و استرداد مبلغ.", evidence="apps/orders; dashboard orders/returns/refund"),
    Feature("inventory", STORE, "موجودی و انتقالِ انبار", "موجودیِ هر کالا/تنوع، رزرو و انتقال بینِ انبارها.", evidence="apps/catalog inventory; dashboard transfers"),
    Feature("warehouses", STORE, "تعدادِ انبار", "سقفِ انبارهایِ فروشگاه.", entitlement=ekeys.INVENTORY_WAREHOUSES, unit="انبار", evidence="apps/catalog/services/warehouse_service.py"),
    Feature("shipping_tax", STORE, "ارسال و مالیات", "مناطق و روش‌هایِ ارسال، هدفِ ارسالِ رایگان، کلاس‌هایِ مالیاتی.", evidence="dashboard shipping/tax"),
    Feature("customers", STORE, "مشتریان و برچسب‌گذاری", "فهرست و پروفایلِ مشتری، برچسب و تاریخچه‌ی سفارش.", evidence="apps/customers; dashboard customers"),
    Feature("segments", STORE, "سگمنت‌هایِ مشتری", "گروه‌بندیِ پویایِ مشتریان برایِ بازاریابیِ هدفمند.", entitlement=ekeys.CUSTOMERS_SEGMENTS, unit="سگمنت", evidence="enforcement.enforce_can_create_segment"),
    Feature("staff", STORE, "اعضایِ تیم و نقش‌ها", "افزودنِ کارمند با نقش و مجوزِ جداگانه؛ سقفِ تعدادِ اعضا از پلن می‌آید.", entitlement=ekeys.STAFF_MEMBERS, unit="عضو", evidence="apps/stores/services/membership_service.py"),
    Feature("import", STORE, "ورودِ گروهیِ اطلاعات (Import)", "آپلودِ فایلِ کالا با پیش‌نمایش؛ اجرا مصرفِ ماهانه دارد.", entitlement=ekeys.CATALOG_IMPORT, evidence="apps/dashboard/services/import_service.py"),
    Feature("import_rows", STORE, "ردیفِ ورودیِ ماهانه", "سقفِ مجموعِ ردیف‌هایِ واردات در هر دوره‌ی صورتحساب.", entitlement=ekeys.CATALOG_IMPORT_ROWS_MONTHLY, unit="ردیف در ماه", evidence="enforcement.check_import_row_budget"),
    Feature("export", STORE, "خروجیِ اطلاعات (Export)", "دریافتِ فایلِ کالا/سفارش؛ اجرا مصرفِ ماهانه دارد.", entitlement=ekeys.CATALOG_EXPORT, evidence="apps/core/services/export_service.py"),
    Feature("exports_monthly", STORE, "دفعاتِ خروجیِ ماهانه", "سقفِ دفعاتِ تکمیل‌شده‌ی خروجی در هر دوره.", entitlement=ekeys.CATALOG_EXPORTS_MONTHLY, unit="بار در ماه", evidence="enforcement.check_export_budget"),
    Feature("reports", STORE, "گزارش‌هایِ فروش", "گزارش‌هایِ داشبورد با بازه‌ی زمانی.", evidence="dashboard reports"),
    Feature("industry_templates", STORE, "قالب‌هایِ آماده‌ی صنف", "راه‌اندازیِ سریعِ کاتالوگ بر اساسِ صنف (۱۱ خانواده‌ی صنفی).", evidence="dashboard settings/industry"),
    # ------------------------------------------------------------------ زیرساختِ فنی
    Feature("tenant_isolation", INFRA, "فضایِ مستقل برایِ هر فروشگاه", "داده، کاربران و تنظیماتِ هر فروشگاه از دیگران کاملاً جداست (چندمستاجری).", evidence="apps/stores resolution + tenant scoping tests"),
    Feature("platform_subdomain", INFRA, "نشانیِ رایگانِ ویترین/پنل روی راستی‌سی", "هر فروشگاه یک زیردامنه‌ی ویترین و یک نشانیِ پنل می‌گیرد.", evidence="provisioning_service + StoreDomain"),
    Feature("custom_domain", INFRA, "دامنه‌یِ اختصاصی", "اتصالِ دامنه‌ی خودِ فروشگاه با تأییدِ مالکیتِ DNS (دامنه‌یِ دوم هم ممکن است).", entitlement=DOMAINS_CUSTOM, note="مشترکانِ نسخه‌هایِ منتشرشده پیش از تاریخِ اعمال دسترسیِ فعلی را حفظ می‌کنند؛ DNS را مالکِ دامنه تنظیم می‌کند.", evidence="apps/stores/services/domain_verification_service.py"),
    Feature("access_control", INFRA, "ورودِ امن و تأییدِ دو مرحله‌ای", "ورودِ مالک با کدِ پیامکی، محدودیتِ تلاش و تأییدِ گامِ دوم برایِ عملیاتِ حساس.", evidence="apps/portal owner auth + step-up"),
    Feature("audit_log", INFRA, "گزارشِ فعالیت‌ها (Audit Log)", "ثبتِ عملیاتِ مهمِ فروشگاه برایِ پیگیری.", evidence="apps/core audit + dashboard audit_log"),
    Feature("api", INFRA, "API و Webhook برایِ توسعه‌دهندگان", "رابطِ برنامه‌نویسیِ فروشگاه.", availability=PLANNED, entitlement="", evidence="کلیدِ integrations.api/webhooks فقط رزرو است؛ پیاده‌سازی ندارد"),
    # ------------------------------------------------------------------ سئو و محتوا
    Feature("seo_basics", SEO, "سئویِ فنیِ خودکار", "نقشه‌ی سایت، robots.txt، canonical و داده‌ی ساخت‌یافته (JSON-LD) برایِ ویترین.", evidence="apps/core/seo.py"),
    Feature("seo_fields", SEO, "ویرایشِ عنوان و توضیحِ سئو", "عنوان/توضیحِ متا برایِ کالا، دسته و صفحه‌ها.", evidence="catalog/content seo fields"),
    Feature("indexnow", SEO, "اطلاعِ فوریِ تغییرات به موتورهایِ جستجو (IndexNow)", "ارسالِ خودکارِ نشانیِ تغییرکرده.", evidence="apps/core IndexNow pipeline"),
    Feature("redirects", SEO, "ریدایرکتِ ۳۰۱ قابلِ‌تعریف توسطِ فروشنده", "تعریفِ قاعده‌ی تغییرمسیر برایِ نشانی‌هایِ قدیمی.", availability=PLANNED, evidence="apps/stores/middleware.py::StorefrontCanonicalRedirectMiddleware فقط ریدایرکتِ هستِ canonical است؛ قاعده‌ی قابلِ‌تعریف وجود ندارد"),
    Feature("pages_blog", SEO, "صفحه‌هایِ محتوا و مجله", "ساختِ صفحه‌هایِ ثابت و مقاله‌هایِ مجله.", evidence="apps/content, apps/blog"),
    Feature("analytics", SEO, "GA4، GTM و Meta Pixel با رضایتِ کاربر", "اتصالِ ابزارهایِ ردیابی با مدیریتِ رضایتِ بازدیدکننده.", availability=EXTERNAL, note="نیازمندِ حسابِ شخصِ ثالث.", evidence="settings/integrations; core consent engine"),
    Feature("torob_enamad", SEO, "ترب و اینماد", "نقشه/فیدِ ترب و ثبتِ نشانِ اینماد.", availability=EXTERNAL, note="نیازمندِ ثبت‌نام در سرویس‌هایِ مربوط.", evidence="settings/integrations (Torob, eNamad)"),
    # ------------------------------------------------------------------ پرداخت
    Feature("gateways", PAY, "درگاهِ پرداختِ آنلاین فروشگاه", "اتصالِ درگاهِ خودِ فروشگاه (مثلاً زیبال، زرین‌پال، پاسارگاد) با اعتبارنامه‌ی خودِ فروشگاه؛ پولِ مشتریان مستقیم به حسابِ فروشگاه می‌رود.", availability=EXTERNAL, note="نیازمندِ قرارداد/مرچنتِ فروشگاه با درگاه.", evidence="apps/orders/gateways"),
    Feature("card_to_card", PAY, "کارت‌به‌کارت", "پرداختِ دستی با تأییدِ مالکِ فروشگاه.", evidence="apps/orders card transfer"),
    Feature("cod", PAY, "پرداخت در محل", "گزینه‌ی پرداختِ هنگامِ تحویل برایِ سفارشِ فروشگاه.", evidence="apps/orders cod adapter"),
    Feature("bnpl", PAY, "پرداختِ اقساطی (اسنپ‌پی/ترب‌پی)", "آداپتر موجود است.", availability=EXTERNAL, note="فعال‌سازی نیازمندِ قراردادِ مستقلِ فروشگاه با ارائه‌دهنده است.", evidence="apps/orders/gateways/snappay.py, torobpay.py"),
    Feature("store_gateway_isolation", PAY, "جداییِ پرداختِ فروشگاه از پرداختِ اشتراکِ راستی‌سی", "اعتبارنامه‌یِ درگاه‌هایِ فروشگاه هرگز با درگاهِ پلتفرم قاطی نمی‌شود.", evidence="PlatformGatewayConfig vs PaymentGatewayConfig (AST tests)"),
    # ------------------------------------------------------------------ طراحی و شخصی‌سازی
    Feature("storefront_builder", DESIGN, "سازنده‌ی ویترین با بخش‌هایِ آماده", "چیدمانِ صفحه‌ی اصلی با بخش‌ها، پیش‌نمایش، تاریخچه و بازگشت.", evidence="apps/storefront_builder"),
    Feature("ready_templates", DESIGN, "قالب‌هایِ آماده‌ی ویترین", "قالب‌هایِ آماده‌ی صنفی با اعمالِ یک‌کلیکی.", evidence="storefront_builder templates"),
    Feature("branding", DESIGN, "هویتِ بصری (لوگو، رنگ، پالت)", "تنظیمِ لوگو، رنگِ برند، هدر و فوتر و عرضِ صفحه.", evidence="settings identity-assets; global design"),
    Feature("homepage_media", DESIGN, "بنر و هیروی صفحه‌ی اصلی", "مدیریتِ بنرها و بخشِ هیرو.", evidence="dashboard homepage hero/banners"),
    Feature("menus_footer", DESIGN, "منوها و فوتر", "منوهایِ قابلِ‌ویرایش، نمادهایِ اعتماد و لوگویِ پرداخت.", evidence="dashboard menus/footer"),
    Feature("rtl_mobile", DESIGN, "ویترینِ فارسی، راست‌چین و واکنش‌گرا", "طراحیِ RTL با نمایشِ مناسبِ موبایل.", evidence="storefront templates"),
    # ------------------------------------------------------------------ بازاریابی و رشدِ فروش
    Feature("coupons", MARKETING, "کدِ تخفیفِ پیشرفته و گروهی", "کوپن با حداقلِ سفارش، سقفِ استفاده، بازه‌ی اعتبار و تخصیصِ اختصاصیِ مشتری؛ کمپین‌ها برایِ گروهی از مشتریان کدِ جداگانه صادر می‌کنند.", evidence="apps/cart/models.py::Coupon; apps/engagement/services/campaign_service.py"),
    Feature("campaigns", MARKETING, "کمپین‌هایِ تخفیفی", "کمپین و کمپینِ مجموعه.", evidence="dashboard campaigns"),
    Feature("free_shipping_goal", MARKETING, "هدفِ ارسالِ رایگان", "نمایشِ پیشرفتِ سبد تا ارسالِ رایگان.", evidence="cart free_shipping"),
    Feature("gift_wrap", MARKETING, "بسته‌بندیِ هدیه", "افزودنِ گزینه‌ی هدیه به کالا.", evidence="dashboard gift-wrap"),
    Feature("messaging", MARKETING, "اعلان و پیامک", "قالب‌هایِ اعلان، پیامک و ایمیل؛ اعتبارِ پیامک جداگانه خریداری می‌شود.", availability=PARTIAL, note="اعتبارِ پیامک خریدِ جدا دارد.", evidence="apps/notifications, apps/sms"),
    Feature("social_links", MARKETING, "شبکه‌هایِ اجتماعی", "لینکِ شبکه‌هایِ اجتماعی در ویترین.", evidence="dashboard social-links"),
    Feature("bulk_actions", STORE, "عملیاتِ گروهی روی کالاها", "انتخابِ چند کالا و اعمالِ همزمانِ وضعیت/عملیات از فهرستِ کالاها.", evidence="apps/dashboard/views.py::product_bulk_action"),
    Feature("order_sms", STORE, "پیامکِ وضعیتِ سفارش به مشتری", "ثبت، پرداختِ موفق/ناموفق، پردازش، ارسال (با کدِ رهگیری)، تحویل و لغو؛ متن‌ها با متغیر شخصی‌سازی می‌شوند.", availability=PARTIAL, note="اعتبارِ پیامک خریدِ جدا دارد؛ سهمیه‌ی رایگانِ هر پلن تعریف نشده است.", evidence="apps/sms/events.py (SmsEvent.ORDER_*)"),
    Feature("stock_alerts", STORE, "هشدارِ کاهش و اتمامِ موجودی", "اعلان برایِ کالایی که از آستانه‌ی موجودی عبور می‌کند.", evidence="apps/notifications/registry.py (stock.low / stock.out)"),
    Feature("reviews", STORE, "دیدگاهِ مشتریان با تأییدِ فروشنده", "ثبتِ امتیاز و متن در صفحه‌ی کالا؛ نمایش پس از تأییدِ فروشنده.", evidence="apps/catalog/views.py::product_review_create; apps/catalog/models.py::Review"),
    Feature("advanced_search", STORE, "جستجوی فارسی‌محورِ کالا با فیلتر", "جستجوی مقاوم به ی/ک، نیم‌فاصله و خط‌تیره با فیلترِ دسته، برند، قیمت و موجودی.", availability=PARTIAL, note="فیلترِ ویژگی‌هایِ دلخواهِ کالا هنوز در جستجو نیست.", evidence="apps/catalog/services/search_service.py; apps/catalog/views.py::_filtered_products"),
    Feature("shipping_carriers", STORE, "پیش‌تنظیمِ حامل‌هایِ ارسال و کدِ رهگیری", "انتخابِ حاملِ آماده (تیپاکس، چاپار، اسنپ‌باکس و…) و ثبتِ کدِ رهگیریِ مرسوله.", availability=PARTIAL, note="نرخ‌گیری و ثبتِ مرسوله با API حامل‌ها وجود ندارد.", evidence="apps/orders/services/shipping_service.py; apps/orders/models.py (tracking_code)"),
    Feature("min_order_rules", STORE, "حداقلِ مبلغِ سفارش (کد تخفیف و روشِ ارسال)", "حداقلِ سبد برایِ اعمالِ کد تخفیف و برایِ دسترسی‌پذیریِ هر روشِ ارسال.", availability=PARTIAL, note="حداقلِ مبلغِ کلِ سبدِ فروشگاه (مستقل از کوپن/ارسال) تعریف نشده است.", evidence="apps/cart/models.py (Coupon.min_order); apps/orders/models.py (min_subtotal)"),
    Feature("customer_accounts", STORE, "حسابِ مشتری (موبایل/ایمیل)", "ثبت‌نامِ مشتری با موبایل و گذرواژه؛ ورود با موبایل، ایمیل یا نامِ کاربری.", availability=PARTIAL, note="ثبت‌نامِ صرفاً با ایمیل (بدونِ موبایل) پشتیبانی نمی‌شود.", evidence="apps/customers/services/auth_service.py"),
    Feature("fonts", DESIGN, "انتخابِ فونتِ ویترین", "انتخابِ فونت از فهرستِ تعریف‌شده (۷ گزینه).", evidence="apps/storefront_builder/appearance_registry.py::FONT_CHOICES"),
    Feature("occasions", MARKETING, "کمپینِ مناسبتی و بازگشتِ مشتری", "ارسالِ تبریک/هدیه‌ی تولد، سالگرد، نقطه‌ی عطفِ سفارش/خرید و بازگشتِ مشتریِ غیرفعال، با یادآوریِ انقضای کد.", evidence="apps/engagement/models.py::Campaign.Occasion; apps/engagement/services/occasions.py"),
    Feature("welcome_sms", MARKETING, "پیامِ خوش‌آمدگویی", "پیامکِ خوش‌آمدگویی پس از ثبت‌نامِ مشتری.", note="اعتبارِ پیامک خریدِ جدا دارد.", evidence="apps/customers/services/auth_service.py; apps/sms/events.py (SmsEvent.WELCOME)"),
    # ------------------------------------------------------------------ خدماتِ حرفه‌ایِ اختیاری
    # عمداً ردیفی ساخته نمی‌شود: خدمات را مدیر در «خدماتِ اختیاری» تعریف می‌کند (بخشِ جدا در صفحه‌ی عمومی).
)

BY_KEY = {f.key: f for f in CATALOG}

#: کلیدهایِ Entitlementِ تعریف‌شده که هنوز در کد اعمال *نمی‌شوند* — در فرمِ پلن غیرفعال و در صفحه‌ی عمومی نیستند.
UNENFORCED_ENTITLEMENT_KEYS = frozenset(k for k, *_ in ekeys.ENTITLEMENT_DEFINITIONS) - ENFORCED_ENTITLEMENT_KEYS


def sync_feature_catalog():
    """ردیف‌هایِ ``PricingFeature`` را idempotent با کاتالوگِ کد همگام می‌کند.

    * فیلدهایِ ساختاری (دسته/اتصال/طبقه‌بندیِ ممیزی/یادداشت) و برایِ ردیف‌هایِ *کد-مالک* آمادگیِ فنی از کد می‌آیند.
    * متنِ نمایشی، ترتیب، نمایشِ عمومی، وضعیتِ تجاری، تاریخِ انتشار و راهنما **مالِ مدیر** است و فقط هنگامِ ساخت مقدار می‌گیرد.
    * ردیفِ ساخته‌شده توسطِ مالک (``is_custom``) هرگز بازنویسی نمی‌شود. ردیفی که از کاتالوگ حذف شده پنهان می‌شود (حذف نمی‌شود)."""
    from apps.subscriptions.models import EntitlementDefinition, PricingFeature

    TS, CS, VT = PricingFeature.TechnicalStatus, PricingFeature.CommercialStatus, PricingFeature.ValueType
    seen = set()
    for order, f in enumerate(CATALOG, start=1):
        definition = EntitlementDefinition.objects.filter(key=f.entitlement).first() if f.entitlement else None
        ready = f.availability != PLANNED
        value_type = VT.BOOLEAN
        if definition is not None and definition.entitlement_type == "integer_limit":
            value_type = VT.INTEGER_LIMIT
        obj, created = PricingFeature.objects.get_or_create(
            key=f.key,
            defaults={"category": f.category, "title": f.title, "description": f.description, "unit_label": f.unit,
                      "display_order": order * 10, "is_visible": ready, "value_type": value_type,
                      "technical_status": TS.READY if ready else TS.PLANNED,
                      "commercial_status": CS.AVAILABLE if ready else CS.PLANNED},
        )
        if obj.is_custom:
            seen.add(f.key)
            continue
        obj.category, obj.entitlement, obj.availability, obj.note = f.category, definition, f.availability, f.note
        if not created:
            if ready and obj.technical_status == TS.PLANNED:
                obj.technical_status = TS.READY            # توسعه‌دهنده ردیف را «پیاده‌شده» کرد
            if not ready and obj.technical_status == TS.READY:
                obj.technical_status = TS.PLANNED          # عقب‌گرد در کد ⇒ دیگر آماده نیست
                if obj.commercial_status == CS.AVAILABLE:
                    obj.commercial_status = CS.PLANNED
        obj.save()
        seen.add(f.key)
    PricingFeature.objects.exclude(key__in=seen).filter(is_custom=False).update(is_visible=False)
