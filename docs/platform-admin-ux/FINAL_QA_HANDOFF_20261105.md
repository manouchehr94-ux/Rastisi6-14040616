# تحویل برایِ QAِ ویندوز — PR #41 + PR #42 + PR #40 (ادغامِ نهایی؛ **هنوز merge نشود**)

> این درخت یک ادغامِ **integration/QA** است؛ تصمیمِ پذیرش پس از تستِ بصری/کارکردیِ مالک روی لپ‌تاپ گرفته می‌شود. هیچ‌چیز به main merge نشده، deploy نشده و هیچ migration روی محیطِ ماندگار اجرا نشده است.

## ۱. شاخه‌ها (commitِ کامل)
| شاخه | SHA | وضعیت |
|---|---|---|
| `pricing/dynamic-plans-20261105` (PR #41) | `287d8ccac075fd6f7946aaa2b20019e54bd24a54` | push‌شده؛ اصلاحِ `select_for_update` پستگرس |
| `ux/platform-admin-redesign-20261105` (PR #42) | `95cb0727c8ea52e5b6c8050b2d65ce2938278677` | push‌شده؛ اصلاحِ `.pa-sr` + شاملِ #41 |
| `integration/admin-ux-finance-20261105` | tipِ همین شاخه (در توضیحاتِ PR و پاسخِ نهایی با SHAِ کامل آمده) | شاملِ #41، #42 و #40 (`e6f57b93`) + هفت قالبِ مالیِ بازطراحی‌شده |

## ۲. اصلاح‌ها
1. **#41 — PostgreSQL:** `PricingFeature.entitlement` nullable است ⇒ `select_related` یک LEFT OUTER JOIN می‌سازد و `FOR UPDATE` روی آن در PostgreSQL خطا می‌داد (در SQLite پنهان بود) ⇒ «آمادگیِ فنی/وضعیتِ تجاری» قابلیت‌ها در production کار نمی‌کرد. اصلاح: `select_related("entitlement").select_for_update(of=("self",))` در `set_technical_status` و `set_commercial_status`. تست‌هایِ رگرسیون: (الف) نگهبانِ ایستا مستقل از دیتابیس (هیچ `select_for_update()+select_related()` بدونِ `of=` در سرویس‌هایِ اشتراک)، (ب) تست‌هایِ ویژه‌یِ PostgreSQL برایِ هر دو عملیات با بررسیِ SQLِ صادرشده (`FOR UPDATE OF "subscriptions_pricingfeature"`) و حفظِ گیتِ دسترسی. **اثبات:** بدونِ اصلاح روی PostgreSQL هر سه تست شکست می‌خورند (`NotSupportedError`)؛ با اصلاح می‌گذرند.
2. **#42 — `.pa-sr`:** عنصرِ مخفیِ صفحه‌خوان absolute است و بدونِ نیایِ positioned، موقعیتِ ایستایش در جدولِ عریض overflowِ افقیِ صفحه می‌ساخت. اصلاح: `.pa-tablewrap,.pa-card{position:relative}`؛ خودِ `.pa-sr` تغییر نکرد (clip، نه `display:none`) ⇒ صفحه‌خوان همچنان می‌خواند و `label for` همچنان کنترل را نام می‌دهد. **راستی‌آزمایی در مرورگر:** صفحه‌یِ واقعیِ `/payments/sms-purchases/` — بدونِ اصلاح ۱۲۰px (۳۹۰) و ۱۹۰px (۳۲۰) overflow؛ با اصلاح ۰ در هر دو. یک probeِ هم‌ساختار روی شاخه‌یِ UX همین را بازتولید می‌کند (۶۶/۱۳۶px ← ۰). تنها جدولِ دارایِ `.pa-sr`: خریدهایِ بسته‌یِ پیامک. دامنه‌یِ تغییر: فقط `apps/portal` + فایلِ سرویسِ #41؛ هیچ فایلی در داشبوردِ فروشنده/ویترین تغییر نکرد (diff خالی).

## ۳. نتایجِ تست
### PostgreSQL ۱۶ — درختِ ادغام‌شده
| اجرا | نتیجه |
|---|---|
| **سریال:** `apps.billing apps.subscriptions` + UX + lifecycle + قیمت‌گذاری + پنل‌ها + contrast (شاملِ gateway/تراکنش/تطبیق/card-to-card/بازپرداخت/خریدِ پیامک/مجوزها و **concurrency**ِ پرداخت) | **۷۷۶ تست — OK** |
| **موازی (۴ پردازش):** `subscriptions billing portal stores dashboard sms notifications core` | ۵۸۱۸ تست؛ ۱ failure + ۱۷ error — **همه خارج از حوزه‌یِ تغییرات** (بخشِ بعد) |
| PR #41 به‌تنهایی (PostgreSQL، همین مجموعه) | ۵۵۴۷ تست؛ ۱ failure + ۱۳ error — همان دسته‌هایِ از‌قبل‌موجود |

### خطاهایِ از قبل موجود (جدا از نتیجه؛ **همه‌یِ آزمون‌ها سبز نیستند**)
مقایسه‌یِ مستقیم روی PostgreSQL (سریال، ۱۱ ماژولِ مربوط): درختِ ادغام‌شده و **baseline `260c5555` (پیش از همه‌یِ تغییراتِ این مرحله)** دقیقاً **همان ۱۴ تستِ ناموفق** (۴ failure + ۱۰ error) را دارند؛ تفاضلِ دو مجموعه تهی است:
* `notifications…test_email_transport` — `asyncore` در Python 3.13 وجود ندارد.
* `stores…test_refresh_rasti_mode_demo_visuals_command` (۱ failure + ۱ error).
* `dashboard…test_export_views.LegacyRetainedExportTests` (۵) — «connection is closed».
* `dashboard…AttributeValueAddScopeTests` و `ProductOptionsLibraryAndSalesLimitTests` (۲) — `value too long for type character varying(9)` (داده‌یِ تست/ستونِ ساده).
* `portal…test_owner_registration_hardening` — failureهایِ concurrency (حتی روی baseline).
* `portal…test_public_site_v2…test_a_new_ready_template_appears_without_any_code_change` — وابسته به ترتیب.
* در اجرایِ **موازی** چند خطایِ `setUpClass` (`UNIQUE django_content_type`) هم دیده می‌شود (`ConcurrentRenderTests`، `ConcurrentSchedulingTests`، `ParallelPollTests`، `LiveProtocolTests`، …) که artifactِ اجرایِ موازیِ TransactionTestCase است و در اجرایِ سریال حذف می‌شود.

### مرورگر (Chromium، ۱۴۴۰/۱۲۸۰/۷۶۸/۳۹۰/۳۲۰) — همه‌یِ صفحه‌هایِ مالک روی درختِ ادغام‌شده
| معیار | نتیجه |
|---|---|
| صفحه‌هایِ GET × عرض | ۵۱ × ۵ = **۲۵۵ بررسی** (۹۵ مسیر؛ POST/API/فایل جدا) |
| پاسخ | همه ۲۰۰ |
| سایدبارِ یگانه/پوسته‌یِ مشترک | **۱ سایدبار در هر صفحه** |
| overflowِ افقی | **۰** |
| خطایِ JS/کنسول (جز ۴۰۴ِ تصاویرِ `extra01–16`) | **۰** |
| `style=""` درون‌خطی | **۰** |
| فیلدِ عددی با فلشِ مرورگر | **۰ از ۱۵۳** |
| ارتفاعِ دکمه‌ها | **۳۸px** (۳۹۱) — تنها استثنا: ۲۰ دکمه‌یِ «نمایشِ رمز» ۳۰px درونِ فیلد (مؤلفه‌یِ مشترکِ core) |
| سناریوهایِ رفتاری | اصلی ۲۳/۲۳ + مالی ۱۷/۱۷ + `.pa-sr` ✔ |

## ۴. نقص‌هایِ باقی‌مانده
* ۱۶ تصویرِ پیش‌فرضِ سایتِ عمومی (`extra01–16.webp`) در مخزن نیست — جدا بررسی می‌شود؛ asset ای اضافه نشد.
* دکمه‌یِ «نمایشِ رمز» ۳۰px (مؤلفه‌یِ مشترک)؛ ارقامِ جدول‌ها لاتین؛ کارتِ درگاه‌ها پیش‌فرض بسته (غیرِ فعال/پیش‌فرض).
* ۴ دکمه‌یِ Inbox: ۳۸px در این درخت؛ امّا قالبِ Inbox خودش (مشترک با داشبوردِ فروشنده) تغییر نکرد.
* تست‌هایِ مرورگر دستی‌اند (CI ندارند)؛ خطاهایِ از‌قبل‌موجودِ بالا هنوز باز است.
* `select_for_update().select_related(...)` در `apps/orders/services/*` (کدِ فروشگاه/سفارش، خارج از این کار) همان الگوی PostgreSQL-خطرناک را دارد اگر FK ای nullable باشد — فقط گزارش؛ دست نخورد.

## ۵. دستورالعملِ ساختِ worktreeِ ایزولهٔ QA روی ویندوز
**اصل‌ها:** worktree و دیتابیسِ `QA_PRICING_20261105` را **لمس نکنید** (فقط از دیتابیسش *کپی* بگیرید)؛ به production وصل نشوید؛ فایلِ `.env`/اعتبارنامه‌یِ production را کپی نکنید؛ هیچ push/merge انجام ندهید؛ برایِ درگاه‌ها فقط مقادیرِ ساختگی.
```powershell
# ۰) در clone اصلی (نه در worktreeِ QA_PRICING) فقط همین شاخه را بگیرید
cd D:\Projects\RastiSi\<clone-اصلی>
git fetch origin integration/admin-ux-finance-20261105
git rev-parse origin/integration/admin-ux-finance-20261105      # باید با SHAِ اعلام‌شده در PR یکی باشد

# ۱) worktreeِ جدید روی شاخه‌یِ محلیِ جدید (چیزی push نمی‌شود)
git worktree add D:\Projects\RastiSi\QA_ADMINUX_FINANCE_20261105 -b qa/admin-ux-finance-20261105 origin/integration/admin-ux-finance-20261105
cd D:\Projects\RastiSi\QA_ADMINUX_FINANCE_20261105
git status --short                                              # باید خالی باشد

# ۲) محیطِ مجازیِ تازه (نه venvِ worktreeِ دیگر)
py -3.13 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```
### دیتابیسِ محلیِ کپی‌شده (یکی را انتخاب کنید)
**الف) SQLite (پیش‌فرضِ پروژه — فایلِ `db.sqlite3` کنارِ `manage.py`):**
```powershell
$env:DATABASE_URL = ""                                           # فقط برایِ همین پنجره‌یِ PowerShell
Copy-Item D:\Projects\RastiSi\QA_PRICING_20261105\db.sqlite3 .\db.sqlite3   # کپی؛ مبدأ دست‌نخورده می‌ماند
Copy-Item .\db.sqlite3 .\db.sqlite3.before-migrate.bak          # پشتیبانِ پیش از migration
```
**ب) PostgreSQL محلی:**
```powershell
# منبع نباید اتصالِ فعال داشته باشد؛ کپیِ جدید با نامِ جدید
createdb -U <user> -T qa_pricing_20261105 qa_adminux_finance_20261105
$env:DATABASE_URL = "postgres://<user>:<pass>@localhost:5432/qa_adminux_finance_20261105"   # فقط همین پنجره
# (جایگزین: pg_dump qa_pricing_20261105 | psql qa_adminux_finance_20261105)
```
### migration (فقط روی کپی)
```powershell
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py showmigrations subscriptions billing portal | Select-String "\[ \]"   # آنچه اعمال خواهد شد
.\.venv\Scripts\python manage.py migrate --plan                 # پیش‌نمایش؛ تغییری نمی‌دهد
.\.venv\Scripts\python manage.py migrate                        # فقط روی کپی
.\.venv\Scripts\python manage.py makemigrations --check --dry-run   # باید «No changes detected» باشد
```
اگر دیتابیسِ `QA_PRICING` پیش‌تر `subscriptions 0013` را نداشت یا migrationهایِ مالیِ PR #40 را (`billing 0009–0010`، `portal 0015–0018`)، همین‌ها اعمال می‌شوند؛ همگی افزایشی‌اند. برای بازگشت: فایلِ `.bak` را جایگزین کنید یا دیتابیسِ کپی را حذف کنید.
### اجرا و بررسی
```powershell
.\.venv\Scripts\python manage.py createsuperuser                # کاربرِ آزمایشیِ جدید
.\.venv\Scripts\python manage.py runserver 18083                # پورتِ جدید؛ 18082 دست‌نخورده
# مرورگر: http://platformadmins.rastisi.localhost:18083/
```
چک‌لیست: یک سایدبارِ راست در همه‌یِ صفحه‌ها؛ منویِ موبایل (۳۹۰/۳۲۰)؛ بدونِ اسکرولِ افقی؛ فیلدهایِ عددی بدونِ فلش؛ دکمه‌هایِ هم‌قد؛ تأیید پیش از بایگانی/انتشار/لغو/بازپرداخت/تأییدِ claim؛ «اشتراک و قیمت‌گذاری» (پلن‌ها، کاتالوگ، تخصیص، چرخه‌یِ قابلیت)؛ «مالی و پرداخت» (درگاه‌ها با ماسکِ رمز و کارتِ جمع‌شونده، تراکنش‌ها، تطبیق، claimها، بازپرداخت، خریدِ پیامک).
تست‌ها (روی دیتابیسِ جداگانه‌یِ تست؛ به کپیِ QA دست نمی‌زنند):
```powershell
.\.venv\Scripts\python manage.py test apps.portal.tests.test_platform_admin_ux apps.portal.tests.test_feature_lifecycle apps.subscriptions apps.billing --noinput
```
برایِ پاک‌سازی: `git worktree remove D:\Projects\RastiSi\QA_ADMINUX_FINANCE_20261105` (و در صورتِ لزوم حذفِ دیتابیسِ کپی).
