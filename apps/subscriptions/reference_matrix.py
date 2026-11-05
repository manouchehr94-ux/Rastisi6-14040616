"""ممیزیِ ۷۶ ردیفِ مرجعِ صفحه‌ی تعرفه (فایلِ مرجعِ ارسال‌شده توسطِ مالک) در برابرِ کدِ واقعیِ راستی‌سی.

این فایل **فقط ورودیِ ممیزی** است: نه مجوزِ کپیِ کد/طراحی/برند و نه وعده‌ی قابلیت. هر ردیف:

* ``status`` — یکی از ``IMPLEMENTED / PARTIAL / MISSING / EXTERNAL / NA`` (نگاشت به ``Implemented`` / ``Partially implemented`` /
  ``Missing`` / ``External integration required`` / ``Not applicable``)،
* ``catalog`` — کلیدِ ردیفِ کاتالوگِ کانونی (``feature_catalog``) که همان قابلیت را در ماتریسِ عمومیِ راستی‌سی نمایندگی می‌کند
  (خالی = قابلیتی که عمومی نمی‌شود چون وجود ندارد یا مخصوصِ سرویسِ مرجع است)،
* ``evidence`` — مسیرهایِ واقعیِ پیاده‌سازی (تستِ سازگاری وجودِ فایل‌ها را بررسی می‌کند)،
* ``tests`` — تست‌هایِ رفتاری/دسترسیِ Backend که قابلیت را پوشش می‌دهند،
* ``gating`` — ``plan`` (با Entitlementِ واقعی در پلن قابلِ‌کنترل و اعمال‌شده) | ``all`` (همراهِ همه‌ی پلن‌ها) | ``none`` (موجود نیست)،
* ``quota`` — سقف/سهمیه‌ی قابلِ‌تنظیم (اگر دارد)،
* ``migration`` — آیا پیاده‌سازیِ کاملِ شکاف مهاجرتِ دیتابیس می‌خواهد،
* ``impact`` — اثر بر مشترکانِ قبلی،
* ``decision`` — اقدامِ پیشنهادی / تصمیمِ مالک برایِ بستنِ شکاف.

مقدارِ ستون‌هایِ پلنِ سازیتو (حرفه‌ای/پیشرفته/پیشرفته+/اولترا) عمداً اینجا نیست و به پلن‌هایِ راستی‌سی کپی نمی‌شود."""

from dataclasses import dataclass

IMPLEMENTED, PARTIAL, MISSING, EXTERNAL, NA = "implemented", "partial", "missing", "external", "na"
STATUS_LABELS = {
    IMPLEMENTED: "Implemented", PARTIAL: "Partially implemented", MISSING: "Missing",
    EXTERNAL: "External integration required", NA: "Not applicable",
}
#: ردیف‌هایِ هر دسته‌ی مرجع (برایِ تستِ کامل‌بودنِ ۷۶ ردیف).
REFERENCE_CATEGORIES = {
    "store_operations": ("امکانات مدیریت و عملیات فروشگاه", 21),
    "infrastructure": ("امکانات فنی و زیرساختی", 10),
    "seo_content": ("امکانات سئو و محتوا", 6),
    "payments": ("امکانات پرداخت", 4),
    "design": ("امکانات طراحی", 7),
    "marketing": ("ابزارهای افزایش فروش", 20),
    "services": ("خدمات افزوده", 8),
}


@dataclass(frozen=True)
class Row:
    n: int
    category: str
    title: str
    status: str
    catalog: str = ""
    evidence: tuple = ()
    tests: tuple = ()
    gating: str = "none"
    quota: str = "—"
    migration: str = "—"
    impact: str = "—"
    decision: str = ""


S, I, SEO, P, D, M, V = "store_operations", "infrastructure", "seo_content", "payments", "design", "marketing", "services"
NEW_STAFF = "مالک تصمیم می‌گیرد"

ROWS: tuple[Row, ...] = (
    # ============================================================== امکانات مدیریت و عملیات فروشگاه (1–21)
    Row(1, S, "روش ثبت‌نام کاربران (ایمیل یا شماره موبایل)", PARTIAL, "customer_accounts",
        ("apps/customers/services/auth_service.py",), ("apps/customers/tests/test_three_identifier_login.py",), "all",
        decision="ثبت‌نامِ مشتری با موبایل+گذرواژه؛ ورود با موبایل/ایمیل/نامِ کاربری. ثبت‌نامِ فقط‌با‌ایمیل پشتیبانی نمی‌شود — تصمیمِ مالک: لازم است؟"),
    Row(2, S, "ایجاد فرم برای محصول", MISSING, decision="فیلدِ دلخواه/فرمِ سفارشی روی کالا وجود ندارد. نیازمندِ طراحیِ مدل (فیلدِ دلخواه) + سبد/سفارش + فروشگاه؛ migration دارد."),
    Row(3, S, "به‌روزرسانی گروهی محصولات", IMPLEMENTED, "bulk_actions",
        ("apps/dashboard/views.py", "apps/dashboard/urls.py"), ("apps/dashboard/tests/test_product_list_bulk_actions.py",), "all",
        decision="همراهِ همه‌ی پلن‌ها؛ در صورتِ نیاز می‌توان یک Entitlement بولی افزود."),
    Row(4, S, "خروجی فایل اکسل اطلاعات فروشگاه", IMPLEMENTED, "export",
        ("apps/core/services/export_service.py", "apps/core/services/xlsx_utils.py", "apps/subscriptions/services/enforcement.py"),
        ("apps/subscriptions/tests/test_import_export_limits.py",), "plan", quota="catalog.export + catalog.exports_monthly",
        decision="قابلِ کنترل در پلن (بولی + سقفِ ماهانه)."),
    Row(5, S, "تعیین حداقل مبلغ سبدخرید", PARTIAL, "min_order_rules",
        ("apps/cart/models.py", "apps/orders/models.py"), ("apps/cart/tests/test_pricing.py",), "all",
        decision="حداقل فقط برایِ کوپن و روشِ ارسال است؛ حداقلِ مبلغِ کلِ سبدِ فروشگاه نیازمندِ فیلد در تنظیماتِ فروشگاه + اعمال در checkout (migration)."),
    Row(6, S, "فعال‌سازی مالیات بر ارزش افزوده", IMPLEMENTED, "shipping_tax",
        ("apps/dashboard/views.py", "apps/dashboard/urls.py"), ("apps/cart/tests/test_pricing.py", "apps/catalog/tests/test_product_tax_class_isolation.py"), "all"),
    Row(7, S, "پیامک‌های سفارش (سهمیه‌ی پیامک رایگان)", PARTIAL, "order_sms",
        ("apps/sms/events.py", "apps/sms/models.py"), ("apps/sms/tests/test_sms_service.py", "apps/orders/tests/test_order_service.py"), "all",
        decision="پیامکِ رویدادهایِ سفارش موجود است؛ سهمیه‌ی پیامکِ رایگانِ هر پلن وجود ندارد. تصمیمِ مالک: تعیینِ Entitlementِ «اعتبارِ پیامکِ ماهانه‌ی همراهِ پلن» + اعتبارِ ماهانه در دفترِ SmsCreditLedger (migration)."),
    Row(8, S, "ویرایش سفارش", PARTIAL, "",
        ("apps/dashboard/views.py",), ("apps/dashboard/tests/test_order_views.py",), "all",
        decision="تغییرِ وضعیت و کدِ رهگیری موجود است؛ ویرایشِ اقلام/آدرسِ سفارش وجود ندارد (نیازمندِ سرویسِ بازمحاسبه‌ی سفارش + حسابرسی؛ پرمخاطره). تبلیغ نمی‌شود."),
    Row(9, S, "ورود گروهی محصولات از طریق فایل اکسل", IMPLEMENTED, "import",
        ("apps/dashboard/services/import_xlsx.py", "apps/dashboard/services/import_service.py", "apps/subscriptions/services/enforcement.py"),
        ("apps/subscriptions/tests/test_import_export_limits.py",), "plan", quota="catalog.import + catalog.import_rows_monthly",
        decision="قابلِ کنترل در پلن (بولی + سقفِ ردیفِ ماهانه)."),
    Row(10, S, "ایجاد جدول مشخصات برای محصول", IMPLEMENTED, "categories_brands",
        ("apps/catalog/models.py", "apps/catalog/services/attribute_service.py"), ("apps/catalog/tests/test_models.py",), "all"),
    Row(11, S, "جستجوی پیشرفته محصول", PARTIAL, "advanced_search",
        ("apps/catalog/services/search_service.py", "apps/catalog/views.py"), ("apps/catalog/tests/test_persian_search.py",), "all",
        decision="جستجوی فارسی‌محور + فیلترِ دسته/برند/قیمت/موجودی موجود است؛ فیلترِ ویژگی‌هایِ دلخواه نه."),
    Row(12, S, "اتصال به سرویس‌های ارسال", PARTIAL, "shipping_carriers",
        ("apps/orders/services/shipping_service.py", "apps/orders/models.py"), ("apps/cart/tests/test_pricing.py",), "all",
        decision="حامل‌هایِ پیش‌تنظیم و کدِ رهگیری هست؛ اتصالِ API (نرخ/ثبتِ مرسوله) وابسته به قراردادِ هر حامل است و ساخته نشده."),
    Row(13, S, "اطلاع از کاهش موجودی", IMPLEMENTED, "stock_alerts",
        ("apps/notifications/registry.py", "apps/catalog/services/inventory_service.py"),
        ("apps/catalog/tests/test_variant_engine_service.py", "apps/notifications/tests/test_inbox_wiring.py"), "all"),
    Row(14, S, "تاریخچه فعالیت‌ها", IMPLEMENTED, "audit_log",
        ("apps/dashboard/views.py", "apps/core/models.py"), ("apps/dashboard/tests/test_audit_log_views.py",), "all"),
    Row(15, S, "ویرایش کیف پول کاربر", MISSING, decision="کیف‌پولِ مشتری وجود ندارد (بدونِ مدلِ Wallet/دفتر). یک محصولِ مالی جدا؛ نیازمندِ دفترِ کل، تراکنشِ ایمن و تصمیمِ سیاستی."),
    Row(16, S, "فرم شخصی‌سازی شده در سبد خرید", MISSING, decision="فیلدِ دلخواهِ سبد/پرداخت وجود ندارد؛ هم‌خانواده با ردیفِ ۲."),
    Row(17, S, "ایجاد فرم برای تنوع محصول", MISSING, decision="هم‌خانواده با ردیفِ ۲؛ روی سطحِ تنوع."),
    Row(18, S, "اتصال به سیستم‌های حسابداری و انبارداری", MISSING, decision="هیچ کانکتوری ساخته نشده (فقط ورود/خروجِ فایل). نیازمندِ انتخابِ سیستم‌ها و قرارداد/API."),
    Row(19, S, "اتصال به دستیارهای هوش مصنوعی", MISSING, decision="وجود ندارد؛ نیازمندِ سیاستِ داده/حریمِ خصوصی و تأمین‌کننده."),
    Row(20, S, "قیمت‌گذاری پویا بر اساس قیمت لحظه‌ای ارز و طلا", MISSING, decision="قیمتِ لحظه‌ای/نرخ‌ارز وجود ندارد؛ نیازمندِ منبعِ نرخ، سیاستِ گرد‌کردن و بازمحاسبه‌ی قیمت‌ها."),
    Row(21, S, "نمایش ترافیک ورودی مشتریان", EXTERNAL, "analytics",
        ("apps/stores/services/tracking_service.py", "apps/stores/integrations/registry.py"), ("apps/core/tests/test_consent_engine.py",), "all",
        decision="ابزارهایِ Google (GA4/GTM) وصل می‌شوند و ترافیک در همان ابزار دیده می‌شود؛ گزارشِ ترافیکِ داخلیِ راستی‌سی وجود ندارد."),
    # ============================================================== امکانات فنی و زیرساختی (22–31)
    Row(22, I, "گواهینامه SSL", EXTERNAL, "",
        ("apps/stores/services/domain_guide_service.py", "apps/stores/services/domain_verification_service.py"), ("apps/stores/tests/test_domain_guide_service.py",), "all",
        decision="صدورِ گواهی در زیرساختِ استقرار انجام می‌شود (نه در Django)؛ کد فقط آمادگیِ DNS/HTTPS را می‌سنجد. ادعا مشروطِ تأییدِ عملیاتِ استقرار است."),
    Row(23, I, "اتصال آسان به ابزارهای Google", EXTERNAL, "analytics",
        ("apps/stores/services/tracking_service.py", "apps/stores/integrations/search_console.py", "apps/stores/integrations/registry.py"),
        ("apps/catalog/tests/test_tracking_indexnow_visibility.py", "apps/dashboard/tests/test_search_presence.py"), "all",
        decision="اتصالِ GA4/GTM/Search Console پیاده است ولی کارکردش به حسابِ Google خودِ فروشنده وابسته است."),
    Row(24, I, "پشتیبان‌گیری", EXTERNAL, "",
        ("apps/notifications/registry.py", "deploy/cron/rastisi.crontab"), (), "none",
        decision="رویدادِ اعلانِ infra.backup تعریف است امّا کارِ پشتیبان‌گیری در مخزن نیست. عملیات/استقرار باید تعریف و اثبات کند؛ تا آن زمان تبلیغ نمی‌شود."),
    Row(25, I, "فضای فروش فایل", MISSING, decision="کالایِ دیجیتال/فایلِ قابلِ‌دانلود وجود ندارد؛ نیازمندِ ذخیره‌سازیِ خصوصی، سهمیه‌ی حجم و دسترسیِ پس از پرداخت."),
    Row(26, I, "افزودن دامنه دوم", IMPLEMENTED, "custom_domain",
        ("apps/stores/models.py", "apps/stores/services/domain_verification_service.py"),
        ("apps/stores/tests/test_domain_verification_service.py", "apps/subscriptions/tests/test_pricing_dynamic.py"), "plan",
        decision="چند دامنه‌ی اختصاصی برایِ هر فروشگاه مجاز است؛ ثبتِ دامنه با Entitlementِ domains.custom (با grandfathering) کنترل می‌شود. سقفِ تعدادِ دامنه تعریف نشده."),
    Row(27, I, "اپلیکیشن PWA", MISSING, decision="ویترین manifest/service-worker ندارد (فقط Web Pushِ پنلِ مدیریت). نیازمندِ ساختِ PWA و تست."),
    Row(28, I, "استفاده از CDN", EXTERNAL, "", ("apps/stores/services/domain_guide_service.py",), (), "none",
        decision="CDN تصمیمِ استقرار است، نه قابلیتِ برنامه؛ تا اثباتِ عملیات تبلیغ نمی‌شود."),
    Row(29, I, "دامنه ir. رایگان", NA, decision="خدمتِ ثبتِ دامنه/ثبت‌کننده؛ قابلیتِ نرم‌افزاریِ راستی‌سی نیست. در صورتِ ارائه به‌عنوانِ «خدمتِ اختیاری» تعریف شود."),
    Row(30, I, "دسترسی به APIهای باز فروشگاه", MISSING, "api", ("apps/subscriptions/entitlements.py",), (), "none",
        decision="کلیدِ integrations.api فقط رزرو است؛ API عمومی وجود ندارد. نیازمندِ طراحیِ API، احرازِ هویت، rate limit و نسخه‌بندی."),
    Row(31, I, "کلید Client SDK", MISSING, decision="وجود ندارد؛ وابسته به ردیفِ ۳۰."),
    # ============================================================== امکانات سئو و محتوا (32–37)
    Row(32, SEO, "سئوی خودکار صفحات", IMPLEMENTED, "seo_basics",
        ("apps/core/seo.py", "apps/dashboard/services/search_visibility_service.py"),
        ("apps/catalog/tests/test_seo_policy_and_structured_data.py", "apps/core/tests/test_indexnow_sync.py"), "all"),
    Row(33, SEO, "ایجاد سایت‌مپ خودکار", IMPLEMENTED, "seo_basics", ("apps/core/seo.py",), ("apps/catalog/tests/test_seo.py",), "all"),
    Row(34, SEO, "امکان ریدایرکت صفحات", MISSING, "redirects", ("apps/stores/middleware.py",), (), "none",
        decision="فقط ریدایرکتِ canonicalِ میزبان وجود دارد؛ قاعده‌ی ۳۰۱ قابلِ‌تعریف نیست (اشتباهاً «پیاده‌سازی‌شده» فهرست شده بود و اصلاح شد). ساخت: مدلِ RedirectRule + middleware + مدیریت + تست؛ migration دارد."),
    Row(35, SEO, "شخصی‌سازی متاتگ‌ها در صفحات", IMPLEMENTED, "seo_fields",
        ("apps/catalog/models.py", "apps/content/models.py"), ("apps/catalog/tests/test_product_completion_service.py", "apps/catalog/tests/test_seo_policy_and_structured_data.py"), "all"),
    Row(36, SEO, "وبلاگ", IMPLEMENTED, "pages_blog", ("apps/blog/models.py", "apps/content/models.py"), ("apps/core/tests/test_seed_shop.py",), "all"),
    Row(37, SEO, "تجربه (دیدگاه مشتریان)", IMPLEMENTED, "reviews",
        ("apps/catalog/views.py", "apps/catalog/models.py"), ("apps/catalog/tests/test_product_detail_view.py",), "all"),
    # ============================================================== امکانات پرداخت (38–41)
    Row(38, P, "اتصال به درگاه‌های اقساطی", EXTERNAL, "bnpl",
        ("apps/orders/gateways/snappay.py", "apps/orders/gateways/torobpay.py"), ("apps/orders/tests/test_callback_integration.py",), "all",
        decision="آداپترِ اسنپ‌پی/ترب‌پی هست؛ فعال‌سازی نیازمندِ قراردادِ مستقلِ فروشنده است."),
    Row(39, P, "اتصال به درگاه‌های مستقیم بانکی و واسط", EXTERNAL, "gateways",
        ("apps/orders/gateways/zibal.py", "apps/orders/gateways/zarinpal.py", "apps/orders/gateways/pasargad.py"), ("apps/orders/tests/test_payment_redirect_safety.py",), "all",
        decision="زیبال/زرین‌پال/پاسارگاد پیاده‌اند؛ سایر بانک‌ها اسکلت یا (در PR #40) آداپترِ تأییدنشده‌اند. نیازمندِ مرچنتِ فروشنده."),
    Row(40, P, "ایجاد لینک پرداخت سریع", MISSING, decision="لینکِ پرداختِ مستقل از سفارش/سبد وجود ندارد؛ نیازمندِ مدلِ PaymentLink + صفحه‌ی عمومی + مسیرِ تأیید از درگاه (ایمنی/مبلغ)."),
    Row(41, P, "کارت‌به‌کارت پیشرفته", IMPLEMENTED, "card_to_card",
        ("apps/orders/services/card_transfer_service.py", "apps/dashboard/card_transfer_views.py"), ("apps/orders/tests/test_card_transfer.py",), "all"),
    # ============================================================== امکانات طراحی (42–48)
    Row(42, D, "شخصی‌سازی آسان پوسته", IMPLEMENTED, "storefront_builder",
        ("apps/storefront_builder/layout_preset_registry.py", "apps/storefront_builder/appearance_registry.py"), ("apps/storefront_builder/tests/test_r4_appearance_overrides.py",), "all"),
    Row(43, D, "حذف برندینگ سازیتو و شخصی‌سازی متن کپی‌رایت", PARTIAL, "menus_footer",
        ("apps/content/models.py", "apps/dashboard/templates/dashboard/footer_settings.html"), ("apps/content/tests/test_footer_config.py",), "all",
        decision="متنِ کپی‌رایتِ فروشگاه قابلِ‌تنظیم است؛ سیاستِ برندینگِ راستی‌سی در ویترین (حذف/نمایش) تصمیمِ مالک است."),
    Row(44, D, "مگا فوتر (فوتر ستونی)", PARTIAL, "menus_footer",
        ("apps/content/models.py", "apps/dashboard/templates/dashboard/footer_settings.html"), ("apps/content/tests/test_footer_config.py",), "all",
        decision="فوترِ بخش‌بندی‌شده (توضیح/تماس/ناوبری/شبکه‌ها/خبرنامه/نمادها)؛ سازنده‌ی ستونِ آزاد وجود ندارد."),
    Row(45, D, "تغییر رنگ پوسته", IMPLEMENTED, "branding",
        ("apps/storefront_builder/appearance_registry.py",), ("apps/core/tests/test_css_token_contrast.py",), "all"),
    Row(46, D, "تغییر فونت فروشگاه", IMPLEMENTED, "fonts",
        ("apps/storefront_builder/appearance_registry.py",), ("apps/storefront_builder/tests/test_r4_appearance_overrides.py",), "all"),
    Row(47, D, "پوسته‌های پیشرفته", IMPLEMENTED, "ready_templates",
        ("apps/storefront_builder/layout_preset_registry.py",), ("apps/portal/tests/test_onboarding_ready_template.py",), "all"),
    Row(48, D, "طراحی قالب اختصاصی", NA, decision="خدمتِ حرفه‌ای (نه قابلیتِ نرم‌افزار). در صورتِ ارائه به‌عنوانِ «خدمتِ اختیاری» تعریف شود."),
    # ============================================================== ابزارهای افزایش فروش (49–68)
    Row(49, M, "کد تخفیف (پیشرفته و گروهی)", IMPLEMENTED, "coupons",
        ("apps/cart/models.py", "apps/engagement/services/campaign_service.py"), ("apps/cart/tests/test_models.py", "apps/engagement/tests/test_promotional_delivery.py"), "all"),
    Row(50, M, "اتصال به سرویس‌های چت آنلاین", MISSING, decision="ویجتِ چت وجود ندارد (مسیرِ ساده: فیلدِ اسکریپتِ ثالث با رضایتِ کاربر)."),
    Row(51, M, "اتصال به ابزارهای نظرسنجی", MISSING, decision="وجود ندارد."),
    Row(52, M, "اتصال به اسنپ‌پی، دیجی‌پی، ترب‌پی، تارا و…", PARTIAL, "bnpl",
        ("apps/orders/gateways/snappay.py", "apps/orders/gateways/torobpay.py"), ("apps/orders/tests/test_callback_integration.py",), "all",
        decision="فقط اسنپ‌پی و ترب‌پی؛ دیجی‌پی و تارا نیستند. نیازمندِ قرارداد."),
    Row(53, M, "اتصال به ترب، ایمالز، شاپینو و…", PARTIAL, "torob_enamad",
        ("apps/stores/integrations/registry.py",), ("apps/dashboard/tests/test_integration_views.py",), "all",
        decision="فقط ترب؛ ایمالز/شاپینو نیستند."),
    Row(54, M, "اتصال به زی‌شاپ", MISSING, decision="وجود ندارد."),
    Row(55, M, "اتصال به پنل بازاریابی سازیتو", NA, decision="سرویسِ اختصاصیِ رقیب؛ برایِ راستی‌سی معنا ندارد."),
    Row(56, M, "پیام خودکار سبد خرید رها شده", MISSING, decision="تشخیصِ سبدِ رهاشده و ارسالِ پیام وجود ندارد؛ نیازمندِ شناسه‌ی سبد/مشتری، رضایتِ پیامک و job."),
    Row(57, M, "پیام خودکار به مشتریان غیرفعال", IMPLEMENTED, "occasions",
        ("apps/engagement/models.py", "apps/engagement/services/occasions.py"), ("apps/engagement/tests/test_occasions.py",), "all",
        decision="Occasion.REACTIVATION؛ ارسال از اعتبارِ پیامکِ فروشنده."),
    Row(58, M, "پیام خودکار خوش‌آمدگویی", IMPLEMENTED, "welcome_sms",
        ("apps/customers/services/auth_service.py", "apps/sms/events.py"), ("apps/sms/tests/test_sms_service.py",), "all"),
    Row(59, M, "ارسال کمپین‌های پیامکی", IMPLEMENTED, "campaigns",
        ("apps/engagement/services/campaign_service.py", "apps/dashboard/notification_admin_views.py"), ("apps/engagement/tests/test_promotional_delivery.py",), "all"),
    Row(60, M, "کیف پول کاربران", MISSING, decision="هم‌خانواده با ردیفِ ۱۵."),
    Row(61, M, "پیام خودکار بازگشت وجه خرید", PARTIAL, "",
        ("apps/orders/services/refund_service.py", "apps/notifications/registry.py"), ("apps/notifications/tests/test_inbox_wiring.py",), "all",
        decision="اعلانِ refund.completed برایِ کارکنان هست؛ پیامکِ بازگشتِ وجه به مشتری وجود ندارد (SmsEvent ندارد)."),
    Row(62, M, "هدیه تولد", IMPLEMENTED, "occasions",
        ("apps/engagement/models.py", "apps/sms/events.py"), ("apps/engagement/tests/test_occasions.py",), "all"),
    Row(63, M, "هدیه وفاداری", PARTIAL, "occasions",
        ("apps/engagement/models.py", "apps/engagement/services/occasions.py"), ("apps/engagement/tests/test_occasions.py",), "all",
        decision="نقطه‌ی عطفِ سفارش/خرید هدیه می‌دهد؛ برنامه‌ی امتیاز/سطحِ وفاداری وجود ندارد."),
    Row(64, M, "پیام خودکار ثبت دیدگاه", PARTIAL, "",
        ("apps/notifications/registry.py", "apps/notifications/services/business_events.py"), ("apps/notifications/tests/test_inbox_wiring.py",), "all",
        decision="اعلانِ review.pending به کارکنان هست؛ پیامِ خودکار به مشتری نیست."),
    Row(65, M, "پیام خودکار شخصی‌سازی شده پس از خرید", IMPLEMENTED, "",
        ("apps/sms/events.py",), ("apps/orders/tests/test_order_service.py",), "all"),
    Row(66, M, "پیام خودکار یادآوری انقضای اعتبار", PARTIAL, "occasions",
        ("apps/sms/events.py", "apps/engagement/services/campaign_service.py"), ("apps/engagement/tests/test_occasions.py",), "all",
        decision="یادآوریِ انقضای *کدِ تخفیف* هست؛ اعتبارِ کیف‌پول وجود ندارد (وابسته به ۱۵/۶۰)."),
    Row(67, M, "شارژ گروهی کیف پول کاربران", MISSING, decision="هم‌خانواده با ردیفِ ۱۵."),
    Row(68, M, "نمایش سبدهای خرید رهاشده", MISSING, decision="هم‌خانواده با ردیفِ ۵۶."),
    # ============================================================== خدمات افزوده (69–76)
    Row(69, V, "مشاوره سئو", NA, decision="خدمتِ حرفه‌ای انسانی؛ فقط به‌عنوانِ «خدمتِ اختیاری» (OptionalService) با قیمت/دسترسیِ مالک."),
    Row(70, V, "طراحی بنر", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(71, V, "معرفی ادمین", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(72, V, "طراحی لوگو", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(73, V, "بارگذاری محصولات", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(74, V, "عکاسی محصولات", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(75, V, "تولید محتوای سئو شده", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
    Row(76, V, "موشن گرافیک", NA, decision="خدمتِ حرفه‌ای انسانی؛ OptionalService."),
)

#: وضعیتِ مرجع → وضعیتِ مجازِ ردیفِ کاتالوگِ نمایندگی‌کننده (تا ادعایِ عمومی از واقعیت جلو نزند).
ALLOWED_CATALOG_AVAILABILITY = {
    IMPLEMENTED: {"implemented"}, PARTIAL: {"partial", "implemented", "external"}, EXTERNAL: {"external", "partial", "implemented"},
    MISSING: {"planned"}, NA: set(),
}


def by_status():
    out = {}
    for row in ROWS:
        out.setdefault(row.status, []).append(row)
    return out


def render_markdown() -> str:
    """سندِ ماتریسِ شکافِ ۷۶ ردیفی — از همین داده تولید می‌شود تا هرگز از کد جدا نشود (تستِ drift)."""
    counts = {k: len(v) for k, v in by_status().items()}
    lines = [
        "# راستی‌سی — ماتریسِ شکافِ ۷۶ ردیفِ مرجع (۲۰۲۶-۱۱-۰۵)",
        "",
        "> **این سند از `apps/subscriptions/reference_matrix.py` تولید می‌شود** (تستِ `test_reference_matrix.py` برابریِ آن را با کد بررسی می‌کند). "
        "منبعِ ردیف‌ها: فایلِ مرجعِ ارسال‌شده توسطِ مالک (استخراج از ZIP/HTML). این فهرست **ورودیِ ممیزی** است؛ مجوزِ کپیِ طراحی، متن، "
        "برند یا وعده‌ی قابلیت نیست و مقادیرِ پلن‌هایِ مرجع به پلن‌هایِ راستی‌سی (پایه/پیشرفته/الترا) نگاشت نشده است.",
        "",
        "## خلاصه",
        "",
        "| وضعیت | تعداد |",
        "|---|---:|",
    ]
    for status in (IMPLEMENTED, PARTIAL, EXTERNAL, MISSING, NA):
        lines.append(f"| {STATUS_LABELS[status]} | {counts.get(status, 0)} |")
    lines += [f"| **جمع** | **{len(ROWS)}** |", "", "راهنمایِ ستون‌ها: **کنترل** = `plan` (Entitlementِ اعمال‌شده و قابلِ‌تنظیم در پلن) | `all` (همراهِ همه‌ی پلن‌ها؛ قابلِ‌خاموش‌کردن نیست) | `none` (موجود نیست ⇒ هرگز تبلیغ نمی‌شود).", ""]
    for key, (label, count) in REFERENCE_CATEGORIES.items():
        rows = [r for r in ROWS if r.category == key]
        lines += [f"## {label} — {count} ردیف", "", "| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |", "|---:|---|---|---|---|---|---|---|"]
        for r in rows:
            ev = "<br>".join(f"`{e}`" for e in r.evidence) or "—"
            ts = "<br>".join(f"`{t}`" for t in r.tests) or "—"
            quota = f" ({r.quota})" if r.quota != "—" else ""
            lines.append(f"| {r.n} | {r.title} | {STATUS_LABELS[r.status]} | {('`' + r.catalog + '`') if r.catalog else '—'} | `{r.gating}`{quota} | {ev} | {ts} | {r.decision or '—'} |")
        lines.append("")
    gaps = [r for r in ROWS if r.status in (MISSING, PARTIAL, EXTERNAL)]
    lines += ["## شکاف‌هایِ واقعیِ محصول (نیازمندِ تصمیم/پیاده‌سازی پیش از پذیرشِ نهایی)", "",
              "هیچ‌کدام از این ردیف‌ها به‌عنوانِ قابلیتِ فعال تبلیغ نمی‌شود. «Missing» ⇒ ردیفِ کاتالوگ `planned` (عمومی نمی‌شود).", "",
              "| # | قابلیت | وضعیت | نیازِ migration | اثر بر مشترکانِ قبلی |", "|---:|---|---|---|---|"]
    for r in gaps:
        mig = "بله (در پیاده‌سازیِ کامل)" if r.status == MISSING else "بسته به تصمیم"
        lines.append(f"| {r.n} | {r.title} | {STATUS_LABELS[r.status]} | {mig} | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |")
    lines.append("")
    return "\n".join(lines) + "\n"
