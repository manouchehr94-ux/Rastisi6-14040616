# گزارش بازطراحی صفحهٔ یکپارچه‌سازی‌ها — ۱۴۰۵/۰۸/۱۰

پایه: `47ac580922effec6dbeeb05d7503d589c8028862` · شاخه: `feature/admin-panel-modernization-20261029` · **هیچ Push/Merge/Migration/Deploy/Backfill انجام نشده.**
هر چهار قابلیت (ردیابی، IndexNow، Search Console OAuth، Domain Autocheck) پیش‌فرض خاموش مانده‌اند؛ هیچ درخواست واقعی بیرونی؛ Windows QA/DB دست‌نخورده (دیتابیس sandbox پس از QA به checksum اولیه برگردانده شد).

## کامیت‌های محلی
| SHA | محتوا |
|---|---|
| `3047f84` | بازطراحی UI + Backend (QA-05/06، اعتبارسنجی، Torob، eNamad) + تست‌ها |
| `90e303d` | **جداگانه:** ایزولاسیون MEDIA_ROOT تست‌های لوگو/Favicon (فقط تست) |
| `febb9d5` | IndexNow: URL کالای hard-delete‌شده بدون Migration |
| `774a3d6` | هدف لمسی ۴۴px برای «مدیریت» در موبایل |
| (بعدی) | این گزارش + راهنمای QA + اسکرین‌شات‌ها |

## معماری جدید UI و ارتباط با Backend
- **دسته‌های افقی:** شش `SubTab` واقعی با `?section=integrations&view=…` در نوار سطح ۳ مشترک (همان الگوی «مالی و پرداخت»)؛ فقط دستهٔ انتخاب‌شده رندر می‌شود؛ بدون JS هم کار می‌کند؛ منوی عمودی داخل صفحه حذف شد؛ Sidebar اصلی دست‌نخورده؛ دسته‌ها در جست‌وجوی تنظیمات ثبت شدند.
- **ترتیب سئو (اجباری):** ۱ وضعیت و اقدام لازم ← ۲ کار مشتری ← ۳ کار خودکار راستی‌سی ← ۴ سرویس‌های بیرونی.
- **کارت خلاصهٔ هر سرویس** (`settings_integration_card.html`): نام + وضعیت + یک جمله + قدم بعدی + «مدیریت»؛ توضیح تکراری حذف شد.
- **Drawer** (`<dialog>` بومی؛ `settings_integration_drawer.html`): فرم واقعی Django به همان endpointهای قبلی (CSRF، مجوز `can_manage_settings`، Store scoping)؛ خطای هر فیلد کنار همان فیلد؛ مقدار ذخیره‌شدهٔ قبلی با ردّ مقدار نامعتبر حفظ می‌شود؛ بازشدن خودکار پس از خطا؛ Escape/دکمهٔ بستن/کلیک روی backdrop؛ بازگشت فوکوس؛ تأیید در صورت تغییر ذخیره‌نشده؛ حالت «در حال ذخیره…»؛ trap فوکوس؛ ۵۲۰px / تمام‌عرض در موبایل؛ RTL برای فارسی و LTR برای شناسه‌ها؛ `prefers-reduced-motion`؛ بدون localStorage.
- Backend: `search_visibility_service.status_axes/tracking_guidance/VIEWS`، `integration_service` (`IntegrationError.field`، سقف طول)، `views._integration_rows_with_effect` (flash یک‌بارمصرف خطا)، ریدایرکت‌ها به همان دسته.

## وفاداری به HTML مرجع
دسته‌های pill افقی، کارت سرویس (نماد | متن | عملیات)، chipهای وضعیت، Drawer راست‌چین با head/body/foot و خطای فیلد، breakpointهای موبایل و reduced-motion پیاده شد — با داده/فرم/اعتبارسنج واقعی. داده/ID/شمارنده/localStorage نمونه کپی نشد. تفاوت آگاهانه: به‌جای state جاوااسکریپتی، دسته‌ها آدرس واقعی‌اند (قابل ذخیره/اشتراک، سازگار با مجوز).

## QA-05 و QA-06
- **QA-05:** چهار پاسخ جدا برای هر سرویس (ذخیره‌شده / استفاده روشن / آماده / همین حالا فعال) + دلیل (انتظار مدیر پلتفرم / آدرس عمومی / رضایت بازدیدکننده / دامنهٔ تأییدنشده) از Backend؛ «روشن است؟ بله» حذف شد. ترب هرگز «اتصال عملیاتی» ندارد؛ اینماد بدون دامنهٔ تأییدشده «آماده» نیست.
- **QA-06:** هشدار قرمز به راهنمای متناسب تبدیل شد (GA4 مستقیم / فقط GTM / هر دو؛ GTM اولویت دارد؛ ذخیرهٔ GTM تنها Analytics را روشن نمی‌کند؛ راستی‌سی محتوای کانتینر را نمی‌بیند). رفتار Consent بدون تغییر.
- **Chromium (Consent، شناسه‌های آزمایشی، همهٔ میزبان‌های بیرونی abort):** ۱۷/۱۷ موفق — قبل از انتخاب هیچ ردیاب؛ رد → هیچ؛ پذیرش → فقط `gtm.js` و `fbevents.js` (نه `gtag/js`)؛ فقط آمار → GTM بدون Meta؛ پس‌گرفتن رضایت؛ GPC؛ بدون overflow در ۳۹۰.

## اعتبارسنجی/ذخیرهٔ شناسه
سمت سرور (نه فقط JS): الگوی هر نوع شناسه، سقف ۶۰۰ نویسه، رد HTML/script، **شناسهٔ ترب اکنون الگوی محدود دارد** (قبلاً هر متنی)، خطا مقدار قبلی را پاک نمی‌کند، پیام موفقیت فقط «شناسه ذخیره شد… نه تأیید/اتصال»، مقدار escape می‌شود، audit شناسه را نمی‌نویسد، اینماد رمزنگاری‌شده و در دسته‌های دیگر echo نمی‌شود. تست: مجوز (۴ نقش بدون `can_manage_settings` → 403)، CSRF (۴ endpoint → 403)، ناشناس → 302، GET → 405، provider ناشناخته → 404، **ایزولاسیون tenant با Hostهای دو فروشگاه** (غریبه نه می‌خواند نه می‌نویسد؛ ذخیرهٔ هر فروشگاه مستقل).

## ترب
تعریف: «آماده» = عنوان + قیمت واقعی + تصویر شاخص؛ **ناموجود فقط اطلاع‌رسانی است و می‌تواند «آماده» باشد**؛ یک کالا می‌تواند هم «بدون تصویر» هم «ناموجود» باشد (توضیح اختلاف ۵۸/۵۰/۸/۱۰ QA)؛ «بدون قیمت» و «ناموجود» هرگز هم‌پوشان نیستند. افزوده شد: `ready_in_stock`، `ready_out_of_stock`، `out_of_stock` و یادداشت همپوشانی در UI. محدود به `storefront_listing_products(store)` (حذف‌شده/پیش‌نویس/فروشگاه دیگر شمرده نمی‌شود)؛ تعداد Query با اندازهٔ کاتالوگ رشد نمی‌کند (تست). فید/API ساخته نمی‌شود.

## اینماد
انتخاب فروشنده (تیک) از وضعیت واقعی نمایش جدا شد: کنار تیک «این فقط انتخاب شماست» + وضعیت واقعی و دلیل؛ بدون شناسه/کد یا روی localhost/دامنهٔ تأییدنشده → نمایش داده نمی‌شود؛ هیچ نشان/لینک ناقص؛ هرگز «تأییدشده»؛ مراحل فنی/نماد قبلی حفظ شد.

## Favicon
علت ریشه‌ای: `mkdtemp()` در import (پیش از fork) → یک MEDIA_ROOT مشترک بین workerها. اکنون هر تست پوشهٔ موقت خودش را دارد (کامیت جدا، فقط تست). در Full Suite `test_replacement_saves_new` دیگر شکست نمی‌خورد.

## IndexNow و hard-delete
پیاده‌سازی شد **بدون Migration**: هنگام commit حذف یک کالای قبلاً عمومی، یک ردیف audit (`product.hard_deleted`، فقط slug) ثبت می‌شود؛ `indexnow_sync` آدرس آن را «حذف‌شده» می‌فرستد (فقط همان فروشگاه؛ slug دوباره‌استفاده‌شده «حذف‌شده» نیست؛ پیش‌نویس‌ها ثبت نمی‌شوند؛ rollback ثبت نمی‌کند). تست با Fake transport + guard سوکت؛ پرچم پلتفرم خاموش = هیچ ارسالی.

## ۹.۳ جست‌وجوها
در ۱۴۴۰/۱۰۲۴/۷۶۸/۳۹۰/۳۲۰: هدر، نوار دسته‌ها، جست‌وجوی تنظیمات و محتوا روی هم نمی‌افتند؛ بدون اسکرول افقی؛ عرض صفحه هنگام بازشدن Drawer ثابت؛ Tab/focus-visible؛ ناحیهٔ لمسی دکمهٔ Drawer = ۴۴px. سایر صفحات تنظیمات: `test_settings_views` و تست‌های ناوبری/جست‌وجوی تنظیمات سبز.

## نتایج تست
- هدفمند (۲۰۲ تست: redesign، views، visibility، search-presence، readiness، stores، consent، navigation، settings-search): **همه موفق**؛ settings views (۱۱۷) ×۳ بار موازی: موفق.
- **Full Suite فقط یک‌بار:** ۱۲٬۲۶۵ تست، `failures=29, errors=5, skipped=237` (۳۴ شناسه).
  - **رگرسیون جدید ناشی از این مأموریت: ۰.** هیچ شکستی در dashboard/integrations/indexnow/catalog/stores-integrations نیست.
  - ۳۳ مورد همان شکست‌های قدیمیِ قالب‌ها/storefront_builder و SMS live و `refresh_rasti_mode_demo_visuals` (دقیقاً همان فهرست Gate قبلی `47ac580`).
  - ۱ مورد جدید در فهرست ولی **محیطی**: `apps.notifications.tests.test_email_transport` با Python 3.13 به‌دلیل حذف ماژول `asyncore` در import می‌شکند؛ با Python 3.11 همان ماژول ۴/۴ موفق است؛ فایل در این مأموریت دست نخورده.
  - **رفع‌شده:** `FaviconUploadTests.test_replacement_saves_new` (در Gate قبلی ناپایدار بود).
- Firefox و PostgreSQL در این محیط در دسترس نبودند؛ فقط Chromium + SQLite.

## فایل‌های تغییرکرده (۲۲ فایل کد/تست + مستندات)
`navigation.py`، `views.py`، `search_visibility_service.py`، `channel_readiness_service.py`، `admin_ui.css`، سه قالب جزئی integrations (کارت/Drawer/صفحه؛ `settings_integration_row.html` حذف)، `integration_service.py`، `registry.py`، `enamad_verification_service.py`، `catalog/signals.py`، `core/indexnow_sync.py`، تست‌ها (`test_integrations_redesign.py` جدید، `integration_pages.py`، به‌روزرسانی چهار فایل تست صفحه، `test_indexnow_sync.py`، `test_settings_views.py`).

## نیازمند مجوز / توسعهٔ مستقل
Push (مجوز جداگانه)؛ فعال‌سازی ردیابی/IndexNow/GSC/Domain Autocheck روی کپی QA؛ Search Console OAuth؛ فید/API ترب؛ استعلام رسمی اینماد؛ تست Firefox/PostgreSQL؛ رفع شکست‌های قدیمیِ قالب‌ها (خارج از دامنه)؛ پایدارسازی Python 3.13 برای `asyncore`.

## اسکرین‌شات‌های صفحهٔ واقعی Django
`docs/admin-modernization/screenshots_integrations_redesign_20261101/`: overview/seo/analytics/torob/enamad/future (۱۴۴۰)، Drawer GA4 و Drawer با خطا (۱۴۴۰ و ۳۹۰)، overview و analytics و torob در ۳۹۰، overview و analytics در ۳۲۰ + اسکریپت‌های Playwright. راهنمای ویندوز: `WINDOWS_QA_GUIDE_INTEGRATIONS_REDESIGN_20261101.md`.
