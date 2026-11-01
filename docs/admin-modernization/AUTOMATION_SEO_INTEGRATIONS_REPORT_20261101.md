# RastiSi — خودکارسازی راه‌اندازی، SEO و Integrations (گزارش نهایی ۱۴۰۵/۰۸/۱۰ — 2026-11-01)

> مبنا: HEAD محلی `888b2c5310b912d6dda327cad4ede6636052426d` (۵ Commit بازطراحی Integrations، بدون تغییر و بدون تکرار). Base ریموت: `4e01b21f6da685ddee80f0519f6f99da8f3ed521`.
> **Push / Merge / Deploy / Migration / Backfill انجام نشده؛ Migration جدید ساخته نشده.** Tracking، IndexNow و اتصال Search Console روشن نشد؛ هیچ درخواستی به Google، Bing، Meta، ترب یا اینماد ارسال نشد؛ DNS/HTTPS واقعی تغییر نکرد؛ Production، Windows QA و RastiService دست‌نخورده‌اند؛ دادهٔ Storeهای موجود بازنویسی نشد.
> تحقیق از مستندات زندهٔ سرویس‌ها: **به‌دلیل ممنوعیت هرگونه درخواست خارجی، مستندات زنده خوانده نشد**؛ هر ادعا دربارهٔ API/قرارداد بیرونی در جدول‌ها با برچسب «از دانش عمومی؛ باید در Google Cloud / پنل سرویس تأیید شود» آمده است.

## ۱. ماتریس Automation Audit (M1)

| قابلیت | الان واقعاً خودکار است؟ | بدون مجوز خارجی ممکن؟ | API / OAuth / قرارداد / زیرساخت | اقدام فروشنده | اقدام مدیر پلتفرم | همین حالا ساخته و تست شد | وابسته به Migration/مجوز/تصمیم |
|---|---|---|---|---|---|---|---|
| robots.txt | **بله** (هر درخواست، از سیاست واحد `seo_policy`) | بله | — | — | — | تست‌های موجود + Regression جدید | — |
| Sitemap | **بله** (از ردیف‌های زنده؛ بدون کش قدیمی) | بله | — | — | — | Regression: بازنشستگی/حذف کالا و تغییر دامنهٔ اصلی بلافاصله اثر می‌کند | — |
| Canonical | **بله** | بله | — | — | — | همان | — |
| JSON-LD | **بله** (قیمت/موجودی از مرجع Cart؛ ISO IRR، تومان×۱۰) | بله | — | — | — | تست‌های موجود | — |
| سیاست index/noindex | **بله** | بله | — | — | — | موجود | — |
| Search Console بدون حساب | RastiSi خودش Sitemap/robots را می‌دهد؛ ثبت دستی اختیاری | بله | — | اختیاری | — | راهنما و کپی Sitemap (قبلاً) | — |
| Search Console با حساب | **نه** (لایه آماده، خاموش) | فقط تا حد لایه‌های داخلی | OAuth client + مجوز Scope `webmasters` (احتمالاً نیازمند تأیید برنامهٔ OAuth توسط Google) | اعطای مجوز + مالکیت تأییدشدهٔ Property | ساخت OAuth Client در Google Cloud، تنظیم Redirect، فعال‌سازی پرچم | لایه سرویس + تست‌های Transport ساختگی (۱۳) | مسیرهای OAuth (URL) و پرچم؛ تأیید برنامه |
| Google Indexing API | **استفاده نمی‌شود** (برای صفحات محصول عمومی مناسب نیست) | — | — | — | — | تست: هیچ ارجاعی به آن در کد نیست | — |
| IndexNow | قبلاً فقط دستی؛ **اکنون** گذر خودکار تغییرمحور | بله (کلید و فایل کلید خودمان) | Endpoint عمومی IndexNow، بدون حساب | — | روشن‌کردن `RASTISI_INDEXNOW_ENABLED` + خط Cron | `indexnow_sync` + دستور + ۱۰ تست | پرچم پلتفرم؛ ردیف Cron در Rollout |
| Bing Webmaster API | **نه** | — | حساب/کلید API فروشنده؛ مستندات تأییدنشده | ثبت‌نام و اعطای دسترسی | — | — | تصمیم + مستندات رسمی |
| GA4 / GTM / Meta Pixel | شناسه ذخیره می‌شد؛ **اکنون** بارگذاری فقط با Consent واقعی | بله | — | شناسه از حساب خودش | روشن‌کردن `RASTISI_STOREFRONT_TRACKING_ENABLED` پس از تأیید حقوقی | موتور Consent + ۱۴ تست + Chromium | پرچم پلتفرم؛ بررسی حقوقی سیاست‌های منطقه‌ای |
| Merchant Center | **غیرقابل‌استفاده برای ایران** | — | — | — | — | وضعیت «پشتیبانی نمی‌شود» + تست | — |
| ترب | فقط ذخیرهٔ شناسه | داخلی: بله | قرارداد/روش رسمی Feed/API تأییدنشده | ثبت‌نام و تأیید در `torob.com/sell/` | — | بررسی آمادگی داده‌های کالا (عنوان/قیمت/تصویر/موجودی) + ۵ تست | Feed/API: نیاز به مشخصات رسمی ترب |
| اینماد | قرارگیری امن متاتگ/نماد **بله**؛ استعلام وضعیت **نه** | بله (قرارگیری) | API رسمی استعلام در اختیار نیست | درخواست نماد، وارد کردن اطلاعات | — | جریان دومرحله‌ای + کلید نمایش/پنهان‌سازی در فوتر + تست‌ها | استعلام وضعیت: مسدود (خارجی) |
| دامنه و TXT/A/CNAME | تولید TXT و رکوردهای A/CNAME موجود؛ بررسی فقط با کلیک | بله | — | افزودن رکوردها نزد DNS Provider خودش | تنظیم هدف‌های اتصال | **بررسی دوره‌ای فقط‌خواندنی** (`recheck_domains`) + ۱۰ تست | پرچم `RASTISI_DOMAIN_AUTOCHECK_ENABLED` + Cron |
| API DNS Provider / صدور گواهی | **نه** | — | OAuth/API هر Provider، زیرساخت صدور | رضایت مالک | — | — | خارج از این ماموریت (فعال‌سازی نهایی و Step-Up دست‌نخورده) |

## ۲. موتور مشترک عملیات خودکار (M2) — بدون Migration
`apps/core/automation.py` روی چیزهای موجود: Cron + دستورهای `manage.py` (زمان‌بند)، `AuditLogEntry` (ثبت پایدار، idempotent با `request_id`، Redact شده)، قفل Cache. هر عملیات: Store Scoping؛ پرچم فعال/غیرفعال (غیرفعال = هیچ اتفاقی نمی‌افتد)؛ محافظ Host عمومی (localhost / Host ناشناخته / فروشگاه منتشرنشده یا غیرفعال بلاک می‌شود)؛ Dry Run (بدون قفل/ثبت/Transport)؛ جلوگیری از اجرای تکراری (کلید) و هم‌زمان (قفل)؛ تلاش مجدد محدود با Back-off فقط برای خطای موقت؛ ثبت نتیجهٔ واقعی (`done/failed/skipped/blocked/disabled`)؛ فقط نام کلاس خطا لاگ می‌شود نه پیام (ممکن است Secret داشته باشد)؛ Transport تزریقی. ۱۱ تست.
**محدودیت**: صف پایدار (پایش `next_run_at`/payload) بدون Migration ساخته نمی‌شود. به‌جای آن «چه چیزی تغییر کرده» از ردیف‌های خود Store و یک Watermark در نتیجهٔ ثبت‌شده استخراج می‌شود. طرح Migration در بند ۸.

## ۳. SEO پایه (M3) و GSC / IndexNow (M4, M5)
- **SEO**: ممیزی نشان داد robots/Sitemap/Canonical/JSON-LD از قبل در هر درخواست از ردیف‌های زنده ساخته می‌شود (کش قدیمی ندارد). Regression اضافه شد: بازنویسی وضعیت کالا (Draft↔Active↔حذف) و تغییر دامنهٔ اصلی بلافاصله در Sitemap/robots/Canonical دیده می‌شود.
- **IndexNow خودکار** (`apps/core/indexnow_sync.py`): «چه چیزی تازه/تغییرکرده/بازنشسته شد» را از `lastmod` نقشهٔ سایت و کالاهای تغییرکرده‌ولی دیگر قابل‌نمایش، نسبت به Watermark، می‌سازد؛ در اجرای اول یا تغییر Host همه‌چیز؛ فقط https و همان Host و بدون مسیر خصوصی؛ Dedup؛ کلید و Host تأییدشدهٔ همان Store؛ ۴۲۹/۵xx تلاش مجدد، ۴۰۳/۴۲۲ نه؛ نتیجه «پذیرفته شد (۲۰۰/۲۰۲)» نه «ایندکس شد». پیش‌فرض خاموش؛ دستور `indexnow_sync` پیش‌فرض Dry Run. **حد**: کالای Hard-delete ردی برای ارسال «حذف» نمی‌گذارد (فقط از Sitemap بیرون می‌رود).
- **Search Console** (`apps/stores/integrations/search_console.py`): URL مجوز با `state` امضاشده و منقضی‌شونده متصل به یک Store؛ تبادل کد؛ توکن‌ها رمزنگاری‌شده در ردیف سرویسی (بدون فرم فروشنده)؛ انتخاب فقط Propertyٔ تأییدشدهٔ خود فروشنده (Owner/FullUser)؛ ثبت و خواندن وضعیت Sitemap؛ ۴۰۱→Refresh یک‌بار؛ `invalid_grant`→«دسترسی از دست رفته» و توقف تماس‌ها؛ پاسخ ۴۲۹/۵xx تلاش مجدد، ۴۰۳ نه. **مسیرهای OAuth (URL/View) عمداً وصل نشده‌اند**؛ پرچم و Client به عهدهٔ مدیر پلتفرم. ۱۳ تست.

## ۴. Consent و Tracking (M6)
سیاست محافظه‌کارانهٔ واحد (Opt-in): هیچ تگی در HTML چاپ نمی‌شود؛ فقط پیکربندی JSON اعتبارسنجی‌شده و `core/consent.js`. Consent Mode v2: چهار سیگنال (`ad_storage`, `analytics_storage`, `ad_user_data`, `ad_personalization`) به‌علاوهٔ functionality/personalization پیش‌فرض `denied` (فقط `security_storage` granted) **قبل از** هر تگ. بنر واقعی: «پذیرش همه» و «رد همه» هم‌وزن و ۴۴px، «انتخاب دسته‌ها» با دسته‌های بدون تیک اولیه (ضروری / آمار / تبلیغات)، لینک بازکردن مجدد، کوکی First-party نسخه‌دار (۱۸۰ روز)، احترام به Global Privacy Control (تبلیغات خاموش و قفل)، لغو رضایت = بازآغاز صفحه بدون ابزار. GTM بر GA4 مستقیم غالب است (بدون شمارش مضاعف)؛ `<noscript>` GTM حذف شد. Chromium (۱۷ بررسی): قبل از انتخاب **صفر** درخواست ردیاب؛ رد → هنوز صفر؛ پذیرش → `gtm.js` و `fbevents.js` (و نه `gtag/js`)؛ فقط آمار → GTM بدون Meta؛ لغو → بدون ردیاب؛ GPC → Meta بارگذاری نمی‌شود.
**هنوز**: `RASTISI_STOREFRONT_TRACKING_ENABLED` پیش‌فرض خاموش؛ بدون ID یا روی localhost/Preview/غیرمنتشر هیچ بنر و اسکریپتی رندر نمی‌شود. تفکیک سیاست بر اساس منطقه/قانون: **مسدود تا بررسی حقوقی** (یک سیاست Opt-in برای همه).

## ۵. ترب، اینماد، Merchant Center، دامنه (M7–M10)
- **ترب**: لینک `https://torob.com/sell/`؛ بررسی داخلی آمادگی داده‌های کالا (همان مرجع قیمت/موجودی JSON-LD)؛ Feed/API ساخته نشد چون قرارداد رسمی تأیید نشد. **پیشنهاد**: ثبت‌نام و پرسش از ترب دربارهٔ خزیدن Sitemap/JSON-LD؛ فقط اگر مشخصات رسمی Feed/API داده شد، Endpoint فقط‌خواندنی tenant-scoped از همان منبع ساخته شود (توکن→ممکن است Migration).
- **اینماد**: دو مرحلهٔ مستقل (متاتگ در `<head>` صفحهٔ اصلی؛ نمادِ صادرشده در فوتر)، فقط روی دامنهٔ اختصاصیِ تأییدشدهٔ همان Store؛ فروشنده می‌تواند نمایش نماد را بدون از دست‌دادن شناسه‌ها خاموش کند؛ وضعیت «پنهان» جدا از «ذخیره‌شده»؛ نماد Store دیگر هرگز نمایش داده نمی‌شود؛ HTML/JS رد می‌شود؛ هرگز «تأییدشده توسط اینماد» نشان داده نمی‌شود.
- **Merchant Center**: برای کسب‌وکارهای مستقر در ایران در دسترس نیست → وضعیت «پشتیبانی نمی‌شود» بدون فرم/دورزدن. کشور کسب‌وکار در Store ذخیره نمی‌شود؛ تمام Storeها بازار ایران فرض شده‌اند. Adapter برای کشورهای مجاز ساخته نشد (مشخصات Merchant API تأییدنشده؛ نیازمند فیلد کشور = Migration).
- **دامنه**: `recheck_domains` (پیش‌فرض Dry Run، خاموش با `RASTISI_DOMAIN_AUTOCHECK_ENABLED`): همان بررسی‌های فقط‌خواندنیِ دکمهٔ فروشنده را دوره‌ای اجرا می‌کند؛ **هرگز** `activate_custom_domain` یا Step-Up را دور نمی‌زند، DNS یا گواهی را تغییر نمی‌دهد (تست AST).

## ۶. تجربهٔ کاربری یکپارچه و QA-01 (M11, M12)
هر سرویس شناسه‌ای در صفحه سه پاسخ دارد: «راستی‌سی چه می‌کند؟ / شما چه کنید؟ / وضعیت و قدم بعدی» با برچسب‌های: نیازمند اقدام مشتری، منتظر مدیر پلتفرم، آماده، در حال بررسی، فعال، خطا، پشتیبانی نمی‌شود — همه از وضعیت واقعی (ذخیره؟ قالب معتبر؟ روشن؟ ردیابی زنده؟ دامنهٔ تأییدشده؟). دکمهٔ «فقط هیرو» از گالری قالب‌ها در Commit مستقل حذف شد؛ Backend (`hero.apply_template`)، Registry و Undo/Redo دست‌نخورده.

## ۷. تست و QA
- **Backend جدید (۷۵ تست؛ برابر افزایش ۱۲٬۱۴۵ → ۱۲٬۲۲۰)**: `test_automation_engine` (۱۱)، `test_indexnow_sync` (۱۰)، `test_search_console` (۱۳)، `test_consent_engine` (۱۴)، `test_domain_autocheck` (۱۰)، `test_channel_readiness` (۵)، `test_enamad_verification` (+۳)، `test_search_presence` (+۶)، Regression SEO (+۲)، Regression گالری (+۱). همه با Transport/DNS ساختگی؛ حفاظ `socket.connect`/`urlopen` در تست‌های صفحه؛ Tenant Isolation و بدون Secret در لاگ/ثبت.
- **Chromium**: Consent — ۱۷ بررسی (بنر، Consent Mode پیش‌فرض denied، عدم وجود هر درخواست ردیاب قبل از انتخاب، رد/پذیرش/فقط آمار/لغو، GPC، کیبورد، عرض ۳۹۰/۷۶۸/۱۴۴۰)؛ صفحهٔ Integrations — ۸۷ بررسی (۶ حالت × ۳۹۰/۷۶۸/۱۴۴۰) هنوز سبز بعد از همهٔ تغییرات؛ همهٔ میزبان‌های غیرمحلی در مرورگر مسدود و شمرده شد: **صفر درخواست خارجی**. Firefox و PostgreSQL اجرا نشد.
- **Full Suite روی `7d62f0f`** (`--parallel 4`، Python 3.11): **۱۲٬۲۲۰ تست** (+۷۵ نسبت به ۱۲٬۱۴۵). ۳۴ شناسهٔ شکست/خطا = **۳۳ شناسهٔ Baseline عیناً برابر با اجرای قبلی** + ۱ شناسهٔ جدید: `FaviconUploadTests.test_replacement_saves_new` (`apps.dashboard.tests.test_settings_views`). این تست روی فایل‌های Favicon/Media است و به کد این ماموریت ربطی ندارد؛ **به‌تنهایی سبز**، ماژول کامل با `--parallel 4` دو بار سبز (۱۱۵ تست) و کل `apps.dashboard` با `--parallel 4` سبز (۲٬۰۶۰ تست)؛ یعنی Flake برخورد نام فایل در MEDIA_ROOT مشترکِ Workerهای موازی، هم‌خانوادهٔ «شکست‌های فقط‌موازی» Baseline. پنهان یا skip نشد؛ توصیه: ایزوله‌سازی MEDIA_ROOT هر Worker در یک Commit جداگانهٔ تست.
- مقایسه با Baseline رسمی (۳۸ شناسه): هیچ شکست جدیدِ ناشی از این ماموریت نیست.

## ۸. جدول Acceptance
| قابلیت | وضعیت |
|---|---|
| حذف «فقط هیرو» از گالری (QA-01) | `Implemented & Tested` |
| موتور مشترک عملیات خودکار | `Implemented & Tested` |
| robots/Sitemap/Canonical/JSON-LD/Indexability (به‌روز با کالا و دامنه) | `Implemented & Tested` |
| بخش A و مدل وضعیت‌ها، راهنمای سه‌پرسشی سرویس‌ها | `Implemented & Tested` |
| موتور Consent (بنر، دسته‌ها، Consent Mode v2، GPC، بارگذاری پس از رضایت) | `Implemented & Tested` |
| بارگذاری واقعی GA4/GTM/Meta برای بازدیدکنندگان | `Implemented but Disabled Pending Approval` (پرچم پلتفرم + تأیید حقوقی) |
| سیاست Consent بر حسب منطقه/قانون | `Blocked by External Dependency` (بررسی حقوقی) |
| IndexNow خودکار تغییرمحور | `Implemented but Disabled Pending Approval` (پرچم + Cron) |
| لایهٔ Search Console (OAuth/API/Transport) | `Implemented but Disabled Pending Approval` |
| اتصال واقعی Search Console (Client، تأیید برنامه، مسیرهای OAuth) | `Blocked by External Dependency` |
| Bing Webmaster API | `Not Implemented` |
| آمادگی داده‌های کالا برای ترب | `Implemented & Tested` |
| Feed/API ترب | `Blocked by External Dependency` (قرارداد/مشخصات رسمی) |
| قرارگیری امن اینماد + کلید نمایش/پنهان‌سازی | `Implemented & Tested` |
| استعلام وضعیت نماد از اینماد | `Blocked by External Dependency` (API رسمی نیست) |
| Merchant Center برای فروشگاه‌های ایرانی (وضعیت «پشتیبانی نمی‌شود») | `Implemented & Tested` |
| Adapter Merchant برای کشورهای مجاز | `Not Implemented` |
| بررسی دوره‌ای فقط‌خواندنی دامنه | `Implemented but Disabled Pending Approval` (پرچم + Cron) |
| API DNS Provider، صدور خودکار گواهی | `Not Implemented` |
| صف پایدار عملیات (`next_run_at`، payload) | `Not Implemented` (نیازمند Migration؛ طرح بند ۹) |

## ۹. اقدامات و طرح Rollout / Migration
**مدیر فروشگاه**: وارد کردن شناسه‌ها (GA4/GTM/Meta/ترب/اینماد)، ثبت‌نام در ترب، درخواست نماد، اضافه‌کردن رکورد DNS، تأیید نهایی دامنه (Step-Up)، ثبت اختیاری Search Console و اعطای OAuth (در آینده).
**مدیر پلتفرم**: تصمیم حقوقی و روشن‌کردن `RASTISI_STOREFRONT_TRACKING_ENABLED`؛ `RASTISI_INDEXNOW_ENABLED` + خط Cron `indexnow_sync --send`؛ `RASTISI_DOMAIN_AUTOCHECK_ENABLED` + Cron `recheck_domains --run`؛ ساخت OAuth Client در Google Cloud (Consent Screen/تأیید)، `RASTISI_GSC_OAUTH_ENABLED`/Client ID/Secret و اتصال مسیرهای OAuth؛ هدف‌های A/CNAME.
**طرح Migration (اجرا نشده، نیازمند مجوز)**: جدول `AutomationJob` (store FK، operation، key یکتا به‌ازای store/operation، status، attempts، next_run_at، payload JSON بدون Secret، result، timestamps) برای صف پایدار و Retry خارج از چرخهٔ Cron؛ اختیاری: `Store.business_country` برای Merchant Center و سیاست Consent منطقه‌ای. Rollout: ۱) Migration روی Staging؛ ۲) ثبت Jobها از سیگنال‌های محصول/دامنه (Idempotent)؛ ۳) Worker Cron با `--limit`؛ ۴) روشن‌کردن پرچم‌ها یکی‌یکی با Dry Run قبلی؛ Rollback = خاموش‌کردن پرچم‌ها (جدول بی‌اثر می‌ماند).

## ۱۰. اسکرین‌شات‌ها (`screenshots_automation_20261101/`)
`integrations_{390,768,1440}.webp`، `integrations_{390,1440}_all_open.webp`، `consent_banner_{390,1440}.webp`، `consent_customize_gpc_390.webp`، `consent_after_choice_768.webp`.

## ۱۱. Commitها
| Commit | موضوع |
|---|---|
| `04fea22` | QA-01: حذف «فقط هیرو» از گالری قالب‌ها (مستقل) |
| `fce08fd` | موتور مشترک عملیات خودکار |
| `78bdaa0` | IndexNow خودکار تغییرمحور (خاموش) |
| `f01d393` | Regression SEO: بازنشستگی/حذف کالا و تغییر دامنه |
| `08ccda8` | لایهٔ Google Search Console (OAuth/API، خاموش) |
| `1acefcf` | موتور Consent (بدون تگ قبل از رضایت) |
| `0656355` | آمادگی داده‌های کالا (ترب) و وضعیت Merchant Center |
| `1a56ce3` | اینماد: نمایش/پنهان‌سازی نماد |
| `896f450` | بررسی دوره‌ای فقط‌خواندنی دامنه (خاموش) |
| `262007a` | راهنمای سه‌پرسشی هر سرویس |
| `7d62f0f` | نمایش وضعیت واقعی GSC و آخرین IndexNow در بخش A |
| (آخرین) | مستندات: گزارش، راهنمای Windows QA، تصاویر |

## ۱۲. راهنمای Windows QA
`WINDOWS_QA_GUIDE_AUTOMATION_20261101.md`

## ۱۳. Pre-Push Gate
| شرط | وضعیت |
|---|---|
| مبنا | HEAD قبل از ماموریت `888b2c5310b912d6dda327cad4ede6636052426d`؛ Base ریموت `4e01b21f6da685ddee80f0519f6f99da8f3ed521` (۵ Commit قبلی بدون تغییر) |
| Commitها | ۱۱ Commit کد/تست + ۱ مستندات بالای `888b2c5` (۵+۱۲=۱۷ بالای Base ریموت)؛ Fast-forward، بدون Merge |
| Migration / Model | **هیچ** (`makemigrations --check`: No changes؛ فایل `migrations/` و `models.py` در Diff نیست) |
| پرچم‌های جدید (همه پیش‌فرض خاموش) | `RASTISI_GSC_OAUTH_ENABLED`، `RASTISI_DOMAIN_AUTOCHECK_ENABLED`؛ `RASTISI_INDEXNOW_ENABLED`/`RASTISI_STOREFRONT_TRACKING_ENABLED` همچنان `False`؛ `RASTISI_CONSENT_POLICY_VERSION=1` |
| درخواست خارجی | هیچ (تست‌ها با Transport ساختگی؛ QA مرورگر با مسدودسازی هر میزبان غیرمحلی) |
| Production / Windows QA / RastiService / DNS / HTTPS | دست‌نخورده |
| داده Storeهای موجود | بازنویسی نشد (فقط خواندن؛ QA روی Store آزمایشی Sandbox خارج از Commit) |
| فایل‌های ممنوع | `graphify-out/`، `.graphify-venv/`، Secret، Media، دیتابیس در Commit نیستند |
| Full Suite | ۱۲٬۲۲۰ تست؛ ۳۳ شناسهٔ Baseline عیناً + ۱ Flake موازی (به‌تنهایی/ماژول/اپ سبز) |
| Push | **انجام نشد**؛ فقط پس از مجوز جداگانه به شاخهٔ موجود `feature/admin-panel-modernization-20261029` با RefSpec صریح و بدون Force؛ شاخهٔ محلی Claude هرگز Push نمی‌شود |

**HEAD نهایی** (شامل این گزارش): `git rev-parse HEAD` پس از Commit مستندات؛ آخرین Commit کد `7d62f0fdb225c472af65d779043da6960e0a15ed`.
