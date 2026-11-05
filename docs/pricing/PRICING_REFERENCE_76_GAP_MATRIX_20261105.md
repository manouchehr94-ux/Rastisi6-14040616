# راستی‌سی — ماتریسِ شکافِ ۷۶ ردیفِ مرجع (۲۰۲۶-۱۱-۰۵)

> **این سند از `apps/subscriptions/reference_matrix.py` تولید می‌شود** (تستِ `test_reference_matrix.py` برابریِ آن را با کد بررسی می‌کند). منبعِ ردیف‌ها: فایلِ مرجعِ ارسال‌شده توسطِ مالک (استخراج از ZIP/HTML). این فهرست **ورودیِ ممیزی** است؛ مجوزِ کپیِ طراحی، متن، برند یا وعده‌ی قابلیت نیست و مقادیرِ پلن‌هایِ مرجع به پلن‌هایِ راستی‌سی (پایه/پیشرفته/الترا) نگاشت نشده است.

## خلاصه

| وضعیت | تعداد |
|---|---:|
| Implemented | 24 |
| Partially implemented | 14 |
| External integration required | 7 |
| Missing | 20 |
| Not applicable | 11 |
| **جمع** | **76** |

راهنمایِ ستون‌ها: **کنترل** = `plan` (Entitlementِ اعمال‌شده و قابلِ‌تنظیم در پلن) | `all` (همراهِ همه‌ی پلن‌ها؛ قابلِ‌خاموش‌کردن نیست) | `none` (موجود نیست ⇒ هرگز تبلیغ نمی‌شود).

## امکانات مدیریت و عملیات فروشگاه — 21 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 1 | روش ثبت‌نام کاربران (ایمیل یا شماره موبایل) | Partially implemented | `customer_accounts` | `all` | `apps/customers/services/auth_service.py` | `apps/customers/tests/test_three_identifier_login.py` | ثبت‌نامِ مشتری با موبایل+گذرواژه؛ ورود با موبایل/ایمیل/نامِ کاربری. ثبت‌نامِ فقط‌با‌ایمیل پشتیبانی نمی‌شود — تصمیمِ مالک: لازم است؟ |
| 2 | ایجاد فرم برای محصول | Missing | — | `none` | — | — | فیلدِ دلخواه/فرمِ سفارشی روی کالا وجود ندارد. نیازمندِ طراحیِ مدل (فیلدِ دلخواه) + سبد/سفارش + فروشگاه؛ migration دارد. |
| 3 | به‌روزرسانی گروهی محصولات | Implemented | `bulk_actions` | `all` | `apps/dashboard/views.py`<br>`apps/dashboard/urls.py` | `apps/dashboard/tests/test_product_list_bulk_actions.py` | همراهِ همه‌ی پلن‌ها؛ در صورتِ نیاز می‌توان یک Entitlement بولی افزود. |
| 4 | خروجی فایل اکسل اطلاعات فروشگاه | Implemented | `export` | `plan` (catalog.export + catalog.exports_monthly) | `apps/core/services/export_service.py`<br>`apps/core/services/xlsx_utils.py`<br>`apps/subscriptions/services/enforcement.py` | `apps/subscriptions/tests/test_import_export_limits.py` | قابلِ کنترل در پلن (بولی + سقفِ ماهانه). |
| 5 | تعیین حداقل مبلغ سبدخرید | Partially implemented | `min_order_rules` | `all` | `apps/cart/models.py`<br>`apps/orders/models.py` | `apps/cart/tests/test_pricing.py` | حداقل فقط برایِ کوپن و روشِ ارسال است؛ حداقلِ مبلغِ کلِ سبدِ فروشگاه نیازمندِ فیلد در تنظیماتِ فروشگاه + اعمال در checkout (migration). |
| 6 | فعال‌سازی مالیات بر ارزش افزوده | Implemented | `shipping_tax` | `all` | `apps/dashboard/views.py`<br>`apps/dashboard/urls.py` | `apps/cart/tests/test_pricing.py`<br>`apps/catalog/tests/test_product_tax_class_isolation.py` | — |
| 7 | پیامک‌های سفارش (سهمیه‌ی پیامک رایگان) | Partially implemented | `order_sms` | `all` | `apps/sms/events.py`<br>`apps/sms/models.py` | `apps/sms/tests/test_sms_service.py`<br>`apps/orders/tests/test_order_service.py` | پیامکِ رویدادهایِ سفارش موجود است؛ سهمیه‌ی پیامکِ رایگانِ هر پلن وجود ندارد. تصمیمِ مالک: تعیینِ Entitlementِ «اعتبارِ پیامکِ ماهانه‌ی همراهِ پلن» + اعتبارِ ماهانه در دفترِ SmsCreditLedger (migration). |
| 8 | ویرایش سفارش | Partially implemented | — | `all` | `apps/dashboard/views.py` | `apps/dashboard/tests/test_order_views.py` | تغییرِ وضعیت و کدِ رهگیری موجود است؛ ویرایشِ اقلام/آدرسِ سفارش وجود ندارد (نیازمندِ سرویسِ بازمحاسبه‌ی سفارش + حسابرسی؛ پرمخاطره). تبلیغ نمی‌شود. |
| 9 | ورود گروهی محصولات از طریق فایل اکسل | Implemented | `import` | `plan` (catalog.import + catalog.import_rows_monthly) | `apps/dashboard/services/import_xlsx.py`<br>`apps/dashboard/services/import_service.py`<br>`apps/subscriptions/services/enforcement.py` | `apps/subscriptions/tests/test_import_export_limits.py` | قابلِ کنترل در پلن (بولی + سقفِ ردیفِ ماهانه). |
| 10 | ایجاد جدول مشخصات برای محصول | Implemented | `categories_brands` | `all` | `apps/catalog/models.py`<br>`apps/catalog/services/attribute_service.py` | `apps/catalog/tests/test_models.py` | — |
| 11 | جستجوی پیشرفته محصول | Partially implemented | `advanced_search` | `all` | `apps/catalog/services/search_service.py`<br>`apps/catalog/views.py` | `apps/catalog/tests/test_persian_search.py` | جستجوی فارسی‌محور + فیلترِ دسته/برند/قیمت/موجودی موجود است؛ فیلترِ ویژگی‌هایِ دلخواه نه. |
| 12 | اتصال به سرویس‌های ارسال | Partially implemented | `shipping_carriers` | `all` | `apps/orders/services/shipping_service.py`<br>`apps/orders/models.py` | `apps/cart/tests/test_pricing.py` | حامل‌هایِ پیش‌تنظیم و کدِ رهگیری هست؛ اتصالِ API (نرخ/ثبتِ مرسوله) وابسته به قراردادِ هر حامل است و ساخته نشده. |
| 13 | اطلاع از کاهش موجودی | Implemented | `stock_alerts` | `all` | `apps/notifications/registry.py`<br>`apps/catalog/services/inventory_service.py` | `apps/catalog/tests/test_variant_engine_service.py`<br>`apps/notifications/tests/test_inbox_wiring.py` | — |
| 14 | تاریخچه فعالیت‌ها | Implemented | `audit_log` | `all` | `apps/dashboard/views.py`<br>`apps/core/models.py` | `apps/dashboard/tests/test_audit_log_views.py` | — |
| 15 | ویرایش کیف پول کاربر | Missing | — | `none` | — | — | کیف‌پولِ مشتری وجود ندارد (بدونِ مدلِ Wallet/دفتر). یک محصولِ مالی جدا؛ نیازمندِ دفترِ کل، تراکنشِ ایمن و تصمیمِ سیاستی. |
| 16 | فرم شخصی‌سازی شده در سبد خرید | Missing | — | `none` | — | — | فیلدِ دلخواهِ سبد/پرداخت وجود ندارد؛ هم‌خانواده با ردیفِ ۲. |
| 17 | ایجاد فرم برای تنوع محصول | Missing | — | `none` | — | — | هم‌خانواده با ردیفِ ۲؛ روی سطحِ تنوع. |
| 18 | اتصال به سیستم‌های حسابداری و انبارداری | Missing | — | `none` | — | — | هیچ کانکتوری ساخته نشده (فقط ورود/خروجِ فایل). نیازمندِ انتخابِ سیستم‌ها و قرارداد/API. |
| 19 | اتصال به دستیارهای هوش مصنوعی | Missing | — | `none` | — | — | وجود ندارد؛ نیازمندِ سیاستِ داده/حریمِ خصوصی و تأمین‌کننده. |
| 20 | قیمت‌گذاری پویا بر اساس قیمت لحظه‌ای ارز و طلا | Missing | — | `none` | — | — | قیمتِ لحظه‌ای/نرخ‌ارز وجود ندارد؛ نیازمندِ منبعِ نرخ، سیاستِ گرد‌کردن و بازمحاسبه‌ی قیمت‌ها. |
| 21 | نمایش ترافیک ورودی مشتریان | External integration required | `analytics` | `all` | `apps/stores/services/tracking_service.py`<br>`apps/stores/integrations/registry.py` | `apps/core/tests/test_consent_engine.py` | ابزارهایِ Google (GA4/GTM) وصل می‌شوند و ترافیک در همان ابزار دیده می‌شود؛ گزارشِ ترافیکِ داخلیِ راستی‌سی وجود ندارد. |

## امکانات فنی و زیرساختی — 10 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 22 | گواهینامه SSL | External integration required | — | `all` | `apps/stores/services/domain_guide_service.py`<br>`apps/stores/services/domain_verification_service.py` | `apps/stores/tests/test_domain_guide_service.py` | صدورِ گواهی در زیرساختِ استقرار انجام می‌شود (نه در Django)؛ کد فقط آمادگیِ DNS/HTTPS را می‌سنجد. ادعا مشروطِ تأییدِ عملیاتِ استقرار است. |
| 23 | اتصال آسان به ابزارهای Google | External integration required | `analytics` | `all` | `apps/stores/services/tracking_service.py`<br>`apps/stores/integrations/search_console.py`<br>`apps/stores/integrations/registry.py` | `apps/catalog/tests/test_tracking_indexnow_visibility.py`<br>`apps/dashboard/tests/test_search_presence.py` | اتصالِ GA4/GTM/Search Console پیاده است ولی کارکردش به حسابِ Google خودِ فروشنده وابسته است. |
| 24 | پشتیبان‌گیری | External integration required | — | `none` | `apps/notifications/registry.py`<br>`deploy/cron/rastisi.crontab` | — | رویدادِ اعلانِ infra.backup تعریف است امّا کارِ پشتیبان‌گیری در مخزن نیست. عملیات/استقرار باید تعریف و اثبات کند؛ تا آن زمان تبلیغ نمی‌شود. |
| 25 | فضای فروش فایل | Missing | — | `none` | — | — | کالایِ دیجیتال/فایلِ قابلِ‌دانلود وجود ندارد؛ نیازمندِ ذخیره‌سازیِ خصوصی، سهمیه‌ی حجم و دسترسیِ پس از پرداخت. |
| 26 | افزودن دامنه دوم | Implemented | `custom_domain` | `plan` | `apps/stores/models.py`<br>`apps/stores/services/domain_verification_service.py` | `apps/stores/tests/test_domain_verification_service.py`<br>`apps/subscriptions/tests/test_pricing_dynamic.py` | چند دامنه‌ی اختصاصی برایِ هر فروشگاه مجاز است؛ ثبتِ دامنه با Entitlementِ domains.custom (با grandfathering) کنترل می‌شود. سقفِ تعدادِ دامنه تعریف نشده. |
| 27 | اپلیکیشن PWA | Missing | — | `none` | — | — | ویترین manifest/service-worker ندارد (فقط Web Pushِ پنلِ مدیریت). نیازمندِ ساختِ PWA و تست. |
| 28 | استفاده از CDN | External integration required | — | `none` | `apps/stores/services/domain_guide_service.py` | — | CDN تصمیمِ استقرار است، نه قابلیتِ برنامه؛ تا اثباتِ عملیات تبلیغ نمی‌شود. |
| 29 | دامنه ir. رایگان | Not applicable | — | `none` | — | — | خدمتِ ثبتِ دامنه/ثبت‌کننده؛ قابلیتِ نرم‌افزاریِ راستی‌سی نیست. در صورتِ ارائه به‌عنوانِ «خدمتِ اختیاری» تعریف شود. |
| 30 | دسترسی به APIهای باز فروشگاه | Missing | `api` | `none` | `apps/subscriptions/entitlements.py` | — | کلیدِ integrations.api فقط رزرو است؛ API عمومی وجود ندارد. نیازمندِ طراحیِ API، احرازِ هویت، rate limit و نسخه‌بندی. |
| 31 | کلید Client SDK | Missing | — | `none` | — | — | وجود ندارد؛ وابسته به ردیفِ ۳۰. |

## امکانات سئو و محتوا — 6 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 32 | سئوی خودکار صفحات | Implemented | `seo_basics` | `all` | `apps/core/seo.py`<br>`apps/dashboard/services/search_visibility_service.py` | `apps/catalog/tests/test_seo_policy_and_structured_data.py`<br>`apps/core/tests/test_indexnow_sync.py` | — |
| 33 | ایجاد سایت‌مپ خودکار | Implemented | `seo_basics` | `all` | `apps/core/seo.py` | `apps/catalog/tests/test_seo.py` | — |
| 34 | امکان ریدایرکت صفحات | Missing | `redirects` | `none` | `apps/stores/middleware.py` | — | فقط ریدایرکتِ canonicalِ میزبان وجود دارد؛ قاعده‌ی ۳۰۱ قابلِ‌تعریف نیست (اشتباهاً «پیاده‌سازی‌شده» فهرست شده بود و اصلاح شد). ساخت: مدلِ RedirectRule + middleware + مدیریت + تست؛ migration دارد. |
| 35 | شخصی‌سازی متاتگ‌ها در صفحات | Implemented | `seo_fields` | `all` | `apps/catalog/models.py`<br>`apps/content/models.py` | `apps/catalog/tests/test_product_completion_service.py`<br>`apps/catalog/tests/test_seo_policy_and_structured_data.py` | — |
| 36 | وبلاگ | Implemented | `pages_blog` | `all` | `apps/blog/models.py`<br>`apps/content/models.py` | `apps/core/tests/test_seed_shop.py` | — |
| 37 | تجربه (دیدگاه مشتریان) | Implemented | `reviews` | `all` | `apps/catalog/views.py`<br>`apps/catalog/models.py` | `apps/catalog/tests/test_product_detail_view.py` | — |

## امکانات پرداخت — 4 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 38 | اتصال به درگاه‌های اقساطی | External integration required | `bnpl` | `all` | `apps/orders/gateways/snappay.py`<br>`apps/orders/gateways/torobpay.py` | `apps/orders/tests/test_callback_integration.py` | آداپترِ اسنپ‌پی/ترب‌پی هست؛ فعال‌سازی نیازمندِ قراردادِ مستقلِ فروشنده است. |
| 39 | اتصال به درگاه‌های مستقیم بانکی و واسط | External integration required | `gateways` | `all` | `apps/orders/gateways/zibal.py`<br>`apps/orders/gateways/zarinpal.py`<br>`apps/orders/gateways/pasargad.py` | `apps/orders/tests/test_payment_redirect_safety.py` | زیبال/زرین‌پال/پاسارگاد پیاده‌اند؛ سایر بانک‌ها اسکلت یا (در PR #40) آداپترِ تأییدنشده‌اند. نیازمندِ مرچنتِ فروشنده. |
| 40 | ایجاد لینک پرداخت سریع | Missing | — | `none` | — | — | لینکِ پرداختِ مستقل از سفارش/سبد وجود ندارد؛ نیازمندِ مدلِ PaymentLink + صفحه‌ی عمومی + مسیرِ تأیید از درگاه (ایمنی/مبلغ). |
| 41 | کارت‌به‌کارت پیشرفته | Implemented | `card_to_card` | `all` | `apps/orders/services/card_transfer_service.py`<br>`apps/dashboard/card_transfer_views.py` | `apps/orders/tests/test_card_transfer.py` | — |

## امکانات طراحی — 7 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 42 | شخصی‌سازی آسان پوسته | Implemented | `storefront_builder` | `all` | `apps/storefront_builder/layout_preset_registry.py`<br>`apps/storefront_builder/appearance_registry.py` | `apps/storefront_builder/tests/test_r4_appearance_overrides.py` | — |
| 43 | حذف برندینگ سازیتو و شخصی‌سازی متن کپی‌رایت | Partially implemented | `menus_footer` | `all` | `apps/content/models.py`<br>`apps/dashboard/templates/dashboard/footer_settings.html` | `apps/content/tests/test_footer_config.py` | متنِ کپی‌رایتِ فروشگاه قابلِ‌تنظیم است؛ سیاستِ برندینگِ راستی‌سی در ویترین (حذف/نمایش) تصمیمِ مالک است. |
| 44 | مگا فوتر (فوتر ستونی) | Partially implemented | `menus_footer` | `all` | `apps/content/models.py`<br>`apps/dashboard/templates/dashboard/footer_settings.html` | `apps/content/tests/test_footer_config.py` | فوترِ بخش‌بندی‌شده (توضیح/تماس/ناوبری/شبکه‌ها/خبرنامه/نمادها)؛ سازنده‌ی ستونِ آزاد وجود ندارد. |
| 45 | تغییر رنگ پوسته | Implemented | `branding` | `all` | `apps/storefront_builder/appearance_registry.py` | `apps/core/tests/test_css_token_contrast.py` | — |
| 46 | تغییر فونت فروشگاه | Implemented | `fonts` | `all` | `apps/storefront_builder/appearance_registry.py` | `apps/storefront_builder/tests/test_r4_appearance_overrides.py` | — |
| 47 | پوسته‌های پیشرفته | Implemented | `ready_templates` | `all` | `apps/storefront_builder/layout_preset_registry.py` | `apps/portal/tests/test_onboarding_ready_template.py` | — |
| 48 | طراحی قالب اختصاصی | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای (نه قابلیتِ نرم‌افزار). در صورتِ ارائه به‌عنوانِ «خدمتِ اختیاری» تعریف شود. |

## ابزارهای افزایش فروش — 20 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 49 | کد تخفیف (پیشرفته و گروهی) | Implemented | `coupons` | `all` | `apps/cart/models.py`<br>`apps/engagement/services/campaign_service.py` | `apps/cart/tests/test_models.py`<br>`apps/engagement/tests/test_promotional_delivery.py` | — |
| 50 | اتصال به سرویس‌های چت آنلاین | Missing | — | `none` | — | — | ویجتِ چت وجود ندارد (مسیرِ ساده: فیلدِ اسکریپتِ ثالث با رضایتِ کاربر). |
| 51 | اتصال به ابزارهای نظرسنجی | Missing | — | `none` | — | — | وجود ندارد. |
| 52 | اتصال به اسنپ‌پی، دیجی‌پی، ترب‌پی، تارا و… | Partially implemented | `bnpl` | `all` | `apps/orders/gateways/snappay.py`<br>`apps/orders/gateways/torobpay.py` | `apps/orders/tests/test_callback_integration.py` | فقط اسنپ‌پی و ترب‌پی؛ دیجی‌پی و تارا نیستند. نیازمندِ قرارداد. |
| 53 | اتصال به ترب، ایمالز، شاپینو و… | Partially implemented | `torob_enamad` | `all` | `apps/stores/integrations/registry.py` | `apps/dashboard/tests/test_integration_views.py` | فقط ترب؛ ایمالز/شاپینو نیستند. |
| 54 | اتصال به زی‌شاپ | Missing | — | `none` | — | — | وجود ندارد. |
| 55 | اتصال به پنل بازاریابی سازیتو | Not applicable | — | `none` | — | — | سرویسِ اختصاصیِ رقیب؛ برایِ راستی‌سی معنا ندارد. |
| 56 | پیام خودکار سبد خرید رها شده | Missing | — | `none` | — | — | تشخیصِ سبدِ رهاشده و ارسالِ پیام وجود ندارد؛ نیازمندِ شناسه‌ی سبد/مشتری، رضایتِ پیامک و job. |
| 57 | پیام خودکار به مشتریان غیرفعال | Implemented | `occasions` | `all` | `apps/engagement/models.py`<br>`apps/engagement/services/occasions.py` | `apps/engagement/tests/test_occasions.py` | Occasion.REACTIVATION؛ ارسال از اعتبارِ پیامکِ فروشنده. |
| 58 | پیام خودکار خوش‌آمدگویی | Implemented | `welcome_sms` | `all` | `apps/customers/services/auth_service.py`<br>`apps/sms/events.py` | `apps/sms/tests/test_sms_service.py` | — |
| 59 | ارسال کمپین‌های پیامکی | Implemented | `campaigns` | `all` | `apps/engagement/services/campaign_service.py`<br>`apps/dashboard/notification_admin_views.py` | `apps/engagement/tests/test_promotional_delivery.py` | — |
| 60 | کیف پول کاربران | Missing | — | `none` | — | — | هم‌خانواده با ردیفِ ۱۵. |
| 61 | پیام خودکار بازگشت وجه خرید | Partially implemented | — | `all` | `apps/orders/services/refund_service.py`<br>`apps/notifications/registry.py` | `apps/notifications/tests/test_inbox_wiring.py` | اعلانِ refund.completed برایِ کارکنان هست؛ پیامکِ بازگشتِ وجه به مشتری وجود ندارد (SmsEvent ندارد). |
| 62 | هدیه تولد | Implemented | `occasions` | `all` | `apps/engagement/models.py`<br>`apps/sms/events.py` | `apps/engagement/tests/test_occasions.py` | — |
| 63 | هدیه وفاداری | Partially implemented | `occasions` | `all` | `apps/engagement/models.py`<br>`apps/engagement/services/occasions.py` | `apps/engagement/tests/test_occasions.py` | نقطه‌ی عطفِ سفارش/خرید هدیه می‌دهد؛ برنامه‌ی امتیاز/سطحِ وفاداری وجود ندارد. |
| 64 | پیام خودکار ثبت دیدگاه | Partially implemented | — | `all` | `apps/notifications/registry.py`<br>`apps/notifications/services/business_events.py` | `apps/notifications/tests/test_inbox_wiring.py` | اعلانِ review.pending به کارکنان هست؛ پیامِ خودکار به مشتری نیست. |
| 65 | پیام خودکار شخصی‌سازی شده پس از خرید | Implemented | — | `all` | `apps/sms/events.py` | `apps/orders/tests/test_order_service.py` | — |
| 66 | پیام خودکار یادآوری انقضای اعتبار | Partially implemented | `occasions` | `all` | `apps/sms/events.py`<br>`apps/engagement/services/campaign_service.py` | `apps/engagement/tests/test_occasions.py` | یادآوریِ انقضای *کدِ تخفیف* هست؛ اعتبارِ کیف‌پول وجود ندارد (وابسته به ۱۵/۶۰). |
| 67 | شارژ گروهی کیف پول کاربران | Missing | — | `none` | — | — | هم‌خانواده با ردیفِ ۱۵. |
| 68 | نمایش سبدهای خرید رهاشده | Missing | — | `none` | — | — | هم‌خانواده با ردیفِ ۵۶. |

## خدمات افزوده — 8 ردیف

| # | قابلیتِ مرجع | وضعیت | ردیفِ کاتالوگ | کنترل | مدرک | تستِ رفتاری | تصمیم / اقدام برایِ بستنِ شکاف |
|---:|---|---|---|---|---|---|---|
| 69 | مشاوره سئو | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ فقط به‌عنوانِ «خدمتِ اختیاری» (OptionalService) با قیمت/دسترسیِ مالک. |
| 70 | طراحی بنر | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 71 | معرفی ادمین | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 72 | طراحی لوگو | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 73 | بارگذاری محصولات | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 74 | عکاسی محصولات | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 75 | تولید محتوای سئو شده | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |
| 76 | موشن گرافیک | Not applicable | — | `none` | — | — | خدمتِ حرفه‌ای انسانی؛ OptionalService. |

## شکاف‌هایِ واقعیِ محصول (نیازمندِ تصمیم/پیاده‌سازی پیش از پذیرشِ نهایی)

هیچ‌کدام از این ردیف‌ها به‌عنوانِ قابلیتِ فعال تبلیغ نمی‌شود. «Missing» ⇒ ردیفِ کاتالوگ `planned` (عمومی نمی‌شود).

| # | قابلیت | وضعیت | نیازِ migration | اثر بر مشترکانِ قبلی |
|---:|---|---|---|---|
| 1 | روش ثبت‌نام کاربران (ایمیل یا شماره موبایل) | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 2 | ایجاد فرم برای محصول | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 5 | تعیین حداقل مبلغ سبدخرید | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 7 | پیامک‌های سفارش (سهمیه‌ی پیامک رایگان) | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 8 | ویرایش سفارش | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 11 | جستجوی پیشرفته محصول | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 12 | اتصال به سرویس‌های ارسال | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 15 | ویرایش کیف پول کاربر | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 16 | فرم شخصی‌سازی شده در سبد خرید | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 17 | ایجاد فرم برای تنوع محصول | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 18 | اتصال به سیستم‌های حسابداری و انبارداری | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 19 | اتصال به دستیارهای هوش مصنوعی | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 20 | قیمت‌گذاری پویا بر اساس قیمت لحظه‌ای ارز و طلا | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 21 | نمایش ترافیک ورودی مشتریان | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 22 | گواهینامه SSL | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 23 | اتصال آسان به ابزارهای Google | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 24 | پشتیبان‌گیری | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 25 | فضای فروش فایل | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 27 | اپلیکیشن PWA | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 28 | استفاده از CDN | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 30 | دسترسی به APIهای باز فروشگاه | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 31 | کلید Client SDK | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 34 | امکان ریدایرکت صفحات | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 38 | اتصال به درگاه‌های اقساطی | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 39 | اتصال به درگاه‌های مستقیم بانکی و واسط | External integration required | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 40 | ایجاد لینک پرداخت سریع | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 43 | حذف برندینگ سازیتو و شخصی‌سازی متن کپی‌رایت | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 44 | مگا فوتر (فوتر ستونی) | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 50 | اتصال به سرویس‌های چت آنلاین | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 51 | اتصال به ابزارهای نظرسنجی | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 52 | اتصال به اسنپ‌پی، دیجی‌پی، ترب‌پی، تارا و… | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 53 | اتصال به ترب، ایمالز، شاپینو و… | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 54 | اتصال به زی‌شاپ | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 56 | پیام خودکار سبد خرید رها شده | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 60 | کیف پول کاربران | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 61 | پیام خودکار بازگشت وجه خرید | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 63 | هدیه وفاداری | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 64 | پیام خودکار ثبت دیدگاه | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 66 | پیام خودکار یادآوری انقضای اعتبار | Partially implemented | بسته به تصمیم | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 67 | شارژ گروهی کیف پول کاربران | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |
| 68 | نمایش سبدهای خرید رهاشده | Missing | بله (در پیاده‌سازیِ کامل) | افزودنی؛ مشترکانِ فعلی بدونِ تغییر (قابلیتِ تازه فقط با نسخه‌ی جدیدِ پلن گیت می‌شود) |

