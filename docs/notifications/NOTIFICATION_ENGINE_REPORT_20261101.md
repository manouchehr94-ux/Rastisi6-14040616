# گزارش نهایی — Universal Notification Engine (۱۴۰۵/۰۸/۱۱)

پایه: `cfed2bf9f68dacb478dcff4f826575ef5ad4ed10`. **Push/Merge/Deploy انجام نشده.** Migration فقط به‌صورت فایل محلی (`0004_inbox_engine`) و فقط روی دیتابیس آزمایشیِ یک‌بارمصرف اجرا شد؛ دیتابیس موجود دست‌نخورده (checksum قبل/بعد برابر). چهار Flag قبلی (Tracking/IndexNow/GSC OAuth/Domain Autocheck) و سه کانال جدید (Web Push/Email/Mobile) خاموش‌اند.

| بخش | فایل‌ها |
|---|---|
| الف) Audit | `docs/notifications/NOTIFICATION_ENGINE_AUDIT_20261101.md` |
| ب) موتور | `apps/notifications/{models,registry}.py`, `services/{inbox_engine,scope,inbox_service,channel_delivery,webpush,admin_events}.py`, `migrations/0004_inbox_engine.py`, فرمان‌های `process_inbox_deliveries`, `prune_notifications`, `generate_vapid_keys` |
| ج–د) صندوق و فوری | `inbox_views.py`, `context_processors.py`, `templates/notifications/*`, `static/notifications/{inbox.js,inbox.css,sw.js}` |
| ز) رویدادها | `docs/notifications/EVENT_CATALOG_20261101.md` (۲۴ نوع متصل؛ ۱۴ رویداد بدون منبعِ واقعی فقط مستند) + قلاب در ۱۴ فایل منبع |
| ط) راهنما | `WINDOWS_QA_GUIDE_NOTIFICATIONS_20261101.md` |
| ی) تصاویر | `docs/notifications/screenshots_20261101/` (زنگ، Dropdown، Inbox، Toast، تنظیمات، موبایل ۳۹۰/۳۲۰، خطا، خالی، پلتفرم) |

## رفتارِ تأییدشده در Chromium (دیتابیس آزمایشی)
Toast ≈ ۱۳۰ms بدون Reload؛ شمارنده ۷→۹؛ بحرانی `role=alert`؛ تب دوم Toast تکراری ندارد؛ «همه را خوانده کن» شمارنده را مخفی می‌کند؛ حالت خطای Dropdown؛ زنگ پلتفرم؛ مدیر فروشگاه روی Inbox پلتفرم ۴۰۴؛ بدون overflow در ۱۴۴۰/۱۰۲۴/۷۶۸/۳۹۰/۳۲۰؛ فوکوس در پنل و بازگشت با Escape. Firefox در این محیط نصب نیست (فقط Chromium).

## تست‌ها
- جدید: ۱۸۴ تست در `apps.notifications` (موتور، Tenant Isolation، IDOR، CSRF، Permission، Rollback، Dedupe، Retry/Backoff، Worker failure، Subscription، VAPID، XSS، Rate limit، قراردادِ JS/SW، اتصال Triggerها).
- **Full Suite (یک‌بار):** Found ۱۲۳۷۶ · Ran ۱۲۳۷۴ · failures=۳۰ · errors=۵ · skipped=۲۳۷. Gate قبلی: Ran ۱۲۲۶۵ · failures=۲۹ · errors=۵ · skipped=۲۳۷ ⇒ +۱۰۹ تست.
  - ۳۳ شکستِ قدیمیِ قالب‌ها/SMS live/refresh demo = همان فهرستِ Gate قبلی. ۱ خطای محیطیِ Python 3.13 (`asyncore` در `test_email_transport`؛ با 3.11 سبز).
  - **۱ رگرسیونِ واقعیِ ناشی از این مأموریت کشف و رفع شد:** `test_general_page_query_count_bounded…` (۲۷ > ۲۶ Query) چون زنگ یک Query عضویتِ اضافه می‌زد؛ اکنون از عضویتِ آماده‌ی Request استفاده می‌کند و تست سبز است (بدونِ اجرای دوباره‌ی Full Suite؛ فقط تست‌های هدفمند). همچنین `aria-expanded` ایستا باعث شکستنِ قراردادِ `test_gateway_accordion` شده بود؛ با افزودن در JS رفع شد.
