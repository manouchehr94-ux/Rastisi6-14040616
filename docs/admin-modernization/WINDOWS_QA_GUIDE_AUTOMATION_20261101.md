# راهنمای QA ویندوز — خودکارسازی SEO، Consent، IndexNow، دامنه و Integrations (۱۴۰۵/۰۸/۱۰)

> پس از مجوز Push جداگانه و fetch. بدون Migration. هیچ پرچمی روشن نمی‌شود مگر در یک **کپی** دیتابیس و صراحتاً در همین راهنما. هیچ درخواست واقعی به Google/Bing/Meta/ترب/اینماد، هیچ DNS/HTTPS واقعی. پورت ۸۰۰۸ و دیتابیس QA فعلی را برای آزمون‌های نوشتنی استفاده نکنید.

## ۱. صفحهٔ یکپارچه‌سازی‌ها (عرض ۳۹۰، ۷۶۸، ۱۴۴۰)
`/admin-portal/settings/?section=integrations`
- بخش A: خلاصهٔ آمادگی با **یک** دکمهٔ اصلی؛ روی localhost پیام «این فروشگاه در محیط آزمایشی است…»؛ کارت «آدرس عمومی» باز و بقیه بسته؛ «کارهای خودکار» بدون «۰»: «۵ قابلیت ساخته شده و منتظر است»؛ IndexNow «غیرفعال توسط پلتفرم»؛ کارت گوگل «اتصال خودکار هنوز در دسترس نیست».
- هر سرویس (GA4/GTM/Meta/ترب/اینماد) سه پاسخ دارد و وضعیتش با برچسب‌های «نیازمند اقدام مشتری / منتظر مدیر پلتفرم / آماده / فعال / خطا». بدون شناسه = «نیازمند اقدام مشتری». شناسهٔ معتبر ذخیره‌شده با Tracking خاموش = «منتظر مدیر پلتفرم» (نه «فعال»).
- ترب: لینک `https://torob.com/sell/`؛ کارت «آمادگی اطلاعات کالاها» (کالاهای بدون تصویر/قیمت نام برده می‌شوند)؛ هیچ فیدی ساخته نمی‌شود.
- اینماد: دو مرحله؛ تیک «نمایش نماد در فوتر» (پیش‌فرض روشن)؛ `<script>` در متاتگ رد می‌شود؛ هرگز «اینماد تأییدشده».
- امکانات آینده: «Google Merchant Center — پشتیبانی نمی‌شود (برای کسب‌وکارهای مستقر در ایران)».

## ۲. Consent (روی یک کپی دیتابیس)
در محیط کپی: `RASTISI_STOREFRONT_TRACKING_ENABLED=1`، یک فروشگاه منتشرشده با دامنهٔ اختصاصی تأییدشدهٔ آزمایشی و شناسه‌های **آزمایشی**؛ درخواست‌های شبکه را در DevTools مسدود/ببینید.
1. اولین ورود: بنر «حریم خصوصی شما» دیده می‌شود؛ در Network **هیچ** درخواستی به `googletagmanager.com` یا `connect.facebook.net` نیست.
2. «رد همه» → کوکی `rs_consent`، بنر بسته، لینک «تنظیمات حریم خصوصی» پایین صفحه؛ صفحهٔ بعد بدون بنر و بدون ردیاب.
3. «پذیرش همه» → فقط `gtm.js` (و Meta `fbevents.js`) درخواست می‌شود؛ `gtag/js` درخواست **نمی‌شود** (GTM بر GA4 غالب است).
4. «انتخاب دسته‌ها»: هیچ دسته‌ای از قبل تیک ندارد؛ فقط آمار → GTM بدون Meta. لغو رضایت → صفحه بدون ردیاب بارگذاری مجدد می‌شود.
5. کیبورد: بنر فوکوس می‌گیرد؛ Tab روی دکمه‌ها؛ حلقهٔ فوکوس. عرض ۳۹۰ بدون اسکرول افقی؛ دکمه‌ها ≥۴۴px و هم‌اندازه.
6. با پرچم پیش‌فرض (خاموش) یا روی localhost: **هیچ** بنر و اسکریپتی نیست.

## ۳. IndexNow و دامنه (فقط Dry Run)
```powershell
python manage.py indexnow_sync            # Dry Run: فهرست URLهای تغییرکرده را می‌نویسد؛ چیزی ارسال نمی‌شود
python manage.py recheck_domains          # Dry Run: دامنه‌هایی که بررسی دوره‌ای لازم دارند
```
بدون پرچم‌های `RASTISI_INDEXNOW_ENABLED` / `RASTISI_DOMAIN_AUTOCHECK_ENABLED` حتی با `--send` / `--run` چیزی اجرا نمی‌شود («disabled»).

## ۴. Search Console
تا زمان فعال‌سازی توسط مدیر پلتفرم و ساخت OAuth Client، کارت «مدیریت حضور در گوگل» فقط راهنمای دستی و کپی آدرس Sitemap (روی آدرس عمومی) را دارد.

## ۵. گالری قالب‌ها
در «قالب‌ها» دکمهٔ «فقط هیرو (چیدمان هیرو)» وجود ندارد؛ انتخاب/ویرایش هیرو از Studio.

## ۶. تست‌های خودکار
```powershell
python manage.py test apps.core.tests.test_automation_engine apps.core.tests.test_indexnow_sync apps.core.tests.test_consent_engine apps.stores.tests.test_search_console apps.stores.tests.test_domain_autocheck apps.stores.tests.test_enamad_verification apps.dashboard.tests.test_search_presence apps.dashboard.tests.test_channel_readiness apps.catalog.tests.test_seo_policy_and_structured_data apps.catalog.tests.test_tracking_indexnow_visibility apps.storefront_builder.tests.test_template_gallery_policy --noinput
```

## ۷. محدودیت‌ها
اتصال واقعی Search Console، Feed/API ترب، استعلام اینماد، Merchant Center برای ایران، API DNS Provider و صف پایدار ساخته نشده یا مسدود است؛ دلیل و پیش‌نیاز در گزارش آمده.
