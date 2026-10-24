# VALIDATION_REPORT — نتیجه‌ی واقعی تست‌ها

تاریخ اجرا: 2026-10-24 · محیط: Linux sandbox ابری، Python 3.13.17، Django 5.2.18، SQLite (پیش‌فرض) و PostgreSQL 16 (نصب‌شده در همان sandbox)، nginx 1.24، gunicorn 23، Chromium/Playwright.
هر ردیف: وضعیت · دستور · خروجی/مدرک · محدودیت. وضعیت‌ها: **PASS** (اجراشده و موفق) · **FAIL** · **BLOCKED** (ورودی/ابزار موجود نیست؛ هرگز PASS شمرده نشده).

## نتیجه‌ی کلی

| | |
|---|---|
| برچسب | **`CODE READY / DATA BLOCKED`** — `READY FOR DEPLOYMENT` **داده نشد** |
| دلیل | داده‌ی اصلی `demo-v5` / `demo-arch02` در GitHub/محیط ابری نیست ([`MISSING_INPUTS.md`](MISSING_INPUTS.md)). همه‌ی تست‌های «با داده» روی (الف) داده‌ی مصنوعیِ تست و (ب) کاتالوگ مرجعِ خود مخزن (`rasti-mode-demo`، ۵۰ محصول/۱۵۰ تصویر) اجرا شد؛ این‌ها **اثبات ابزارند، نه اثبات داده‌ی دمو** |

## A. بدون نیاز به داده‌ی دمو

| # | بررسی | وضعیت | دستور | مدرک / محدودیت |
|---|---|---|---|---|
| A1 | Django system check | **PASS** | `python manage.py check` | `System check identified no issues (0 silenced).` |
| A2 | migrationها با مدل‌ها هم‌خوان | **PASS** | `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| A3 | migrate از صفر روی SQLite و PostgreSQL 16 | **PASS** | `manage.py migrate` (هر دو) | هر دو بدون خطا؛ SQLite ≈ 50 s |
| A4 | تست‌های ابزار ریبیلد (SQLite) | **PASS** | `manage.py test apps.stores.tests.test_demo_bundle` | `Ran 71 tests … OK` |
| A5 | همان تست‌ها روی PostgreSQL 16 | **PASS** | `DATABASE_URL=postgres://… manage.py test apps.stores.tests.test_demo_bundle` | `Ran 71 tests … OK` (از جمله reset دنباله‌ها؛ با حذفِ عمدیِ reset همان تست **FAIL** می‌شود: `duplicate key … catalog_product_pkey` ← تست معنادار است) |
| A6 | تست‌های موجودِ حساس به تغییرات من | **PASS** | `test apps.catalog.tests.test_price_inquiry apps.stores.tests.test_{golden_demo_owner_login_readiness,admin_host_enforcement,resolution,admin_superuser_gate}` | `Ran 153 tests … OK` |
| A7 | تست‌های seed موجود (`seed_ready_template_fashion_demo`) | **PASS** | `test apps.stores.tests.test_seed_ready_template_fashion_demo_command` | `Ran 55 tests … OK` (39 min زیر بار موازی) |
| A8 | تست email-transport (بازنویسی sink بدون `asyncore`) | **PASS** | `test apps.notifications.tests.test_email_transport` | `Ran 4 tests … OK`؛ این ماژول قبلاً روی Python ≥ 3.12 **import نمی‌شد** (`ModuleNotFoundError: asyncore`) |
| A9 | مجموعه‌ی کامل تست‌ها | FULL_SUITE_RESULT | `manage.py test --noinput --parallel 4` | FULL_SUITE_DETAIL |
| A10 | پیکربندی production با env نمونه | **PASS** | `check --deploy` با `rastisi.env.example` (مقادیر جعلی موقت، `DEBUG=False`) | فقط هشدار `W004` (HSTS عمداً 0 در شروع) و `W009` (کلید جعلیِ کوتاهِ آزمایشی)؛ هیچ خطا |
| A11 | سینتکس اسکریپت‌های shell | **PASS** | `bash -n rebuild/deployment/scripts/*.sh rebuild/checks/*.sh` | همه OK (shellcheck نصب نبود → استاتیک‌آنالیز بیشتر **BLOCKED**) |
| A12 | محافظ‌های پاک‌سازی (RastiService) | **PASS** | `bash rebuild/checks/test_cleanup_guards.sh` | `PASS cleanup guards`: حذف `rastiservice*` (سرویس/nginx/DB/مسیر)، `/`, `/etc/nginx`, symlink escape همه رد؛ dry-run manifest حاوی ۴ مورد protected ← ۴ `REFUSED` و ۰ `WOULD` |
| A13 | nginx syntax + ویژگی‌های ایمنی | **PASS** | `bash rebuild/checks/nginx_syntax_check.sh` (nginx 1.24) | `test is successful` برای `rastisi.conf` و bootstrap؛ بدون `default_server`/catch-all؛ مسیر private media نگاشت نشده. (خطوط IPv6 فقط در کپی تست حذف می‌شوند.) |
| A14 | systemd unit ها | **PASS (محدود)** | `systemd-analyze verify` | تنها پیام: `/srv/rastisi/venv/bin/gunicorn is not executable` (در sandbox وجود ندارد)؛ هیچ خطای دستور/نحو. اجرا روی systemd واقعی **BLOCKED** |
| A15 | سرو واقعی nginx→gunicorn→Django | **PASS** | `bash rebuild/checks/local_stack_smoke.sh` | ۱۱ بررسی PASS: home/list/cart `200 text/html`، static `200 text/css`، media `200 image/webp` + `nosniff`، `/.env` 403، لیست‌شدن media 403، Host ناشناخته 400، http→https 301. (با داده‌ی مرجع مخزن، `DEBUG=True` برای حذف نیاز Redis/Turnstile) |
| A16 | ZIP: مسیر امتناع | **PASS** | `build_release_zip.py --bundle <bundle ناقص>` | `refusing to package: bundle validation exited 2`؛ هیچ فایل نیمه‌کاره‌ای باقی نماند |
| A17 | ZIP: مسیر موفق (کد-فقط) | **PASS** | `build_release_zip.py --out dist/rastisi-release.zip` | ≈ 24.5 MB، 2296 فایل، شامل MANIFEST.json + `.sha256`؛ **صفر** فایل `raw_user_catalog/qa_evidence/.env/sqlite` |
| A18 | ZIP با bundle (فقط با `--targets` تک‌فروشگاه تست) | **PASS** | `--targets one_target.json --bundle <bundle>` | 333 فایل زیر `data/bundle`؛ برای دو فروشگاه واقعی **BLOCKED** |
| A19 | PostgreSQL E2E واقعی | **PASS** | `migrate` → `retire_seed_store --confirm` → `import_demo_bundle` ×۲ → `create_install_accounts` → `verify_demo_integrity --http` → `rastisi_healthcheck` | import: 1319 ردیف، 330 فایل؛ import دوم: `media_copied=0`، همان شمارش؛ verify: **PASS** (55 URL پاسخ 200)؛ دقیقاً ۲ کاربر؛ هش `pbkdf2_sha256` |

## B. ۱۰ بررسی خواسته‌شده در دستور کار (§7)

| # | خواسته | وضعیت | مدرک |
|---|---|---|---|
| B1 | migration + system check | **PASS** | A1–A3 |
| B2 | import مجدد بدون داده‌ی تکراری | **PASS** (روی داده‌ی تست/مرجع) | `test_import_is_idempotent` (شمارش Store/Domain/Product/Image/Settings/Layout/Page/Section و فایل‌ها قبل=بعد)، A19 |
| B3 | یک ShopSettings معتبر برای هر فروشگاه | **PASS** (ابزار) / **BLOCKED** (دموی واقعی) | `test_exactly_one_shopsettings_and_footer_per_store`؛ دمو: `BLOCKED – MISSING INPUT` |
| B4 | روابط محصول–تصویر | **PASS** (ابزار) | `fk.closed`, `files` در validator/integrity؛ `test_missing_image_file_fails`, `test_empty_image_file_fails`, `test_cross_store_reference_fails` |
| B5 | نبود ۵۰۰ در صفحات محصول | **PASS** (ابزار) | `test_provision_command_fixes_the_page_and_is_idempotent`، `test_integrity_passes_after_import_including_http`، A19 (55 URL شامل 50 صفحه‌ی جزئیات) |
| B6 | رندر نسخه‌ی منتشرشده‌ی هر صفحه | **PASS** (ابزار) / **BLOCKED** (دموی واقعی) | validator: `studio.pages` (شش نوع)؛ integrity: `studio.published`؛ رندر `/`، `/products/`، `/collections/`، `/cart/`، جزئیات در HTTP check. تطابق با طرح اصلیِ دموها: **BLOCKED** |
| B7 | جداسازی اطلاعات دو فروشگاه | **PASS** | `test_two_demo_stores_stay_isolated` (شمارش و تنظیمات جدا؛ slug محصول فروشگاه دوم روی host اول 404)، `test_pk_owned_by_another_store_aborts_and_rolls_back`، `test_never_falls_back_to_another_stores_settings` |
| B8 | مسیر ورود مدیر پلتفرم | **PASS** | `HostAndRoleTests`: صفحه‌ی `platformadmins.rastisi.ir/login/` 200؛ `platform_owner` وارد می‌شود؛ `shops_admin` و رمز غلط رد؛ `/login/` روی host فروشگاه 404؛ `/admin/` روی host پلتفرم‌ادمین 404. (Turnstile در این مسیر اعمال نمی‌شود — طراحی موجود؛ کد تغییر نکرد) |
| B9 | مجوزهای دو نقش | **PASS** | `test_shops_admin_reaches_both_store_admin_panels`، `test_platform_owner_without_membership_gets_no_store_panel`، `test_enter_admin_hands_off_to_the_stores_own_host`، `test_enter_admin_for_unowned_store_is_404`، `test_anonymous_admin_portal_redirects_to_central_login`، `InstallAccountsTests` (۱۲ تست) |
| B10 | دسترسی واقعی به static و media | **PASS** | A15 (از طریق nginx)؛ `file.missing/file.empty/file.undecodable` در integrity |
| B11 | بررسی بصری | **PASS (محدود)** | Chromium/Playwright روی `demo-v5.rastisi.ir` با کاتالوگ مرجع مخزن: خانه/لیست/جزئیات/سبد × دسکتاپ 1280 و موبایل 390 → همه 200؛ **۰ درخواست ≥400**؛ **۰ تصویر قابل‌مشاهده‌ی خراب** (فقط تصاویر hover/lazy مخفی بارگذاری نشده)؛ فونت `Vazirmatn` و RTL اعمال شد (`docs/rebuild/evidence/*.png`). **مقایسه با ظاهر اصلی دموها: BLOCKED – MISSING INPUT** |

## C. خطاهای شناخته‌شده‌ی استقرار قبلی → رگرسیون

| خطا | ریشه‌ی علت (از کد) | رفع | تست رگرسیون |
|---|---|---|---|
| ۵۰۰ با `ShopSettingsNotProvisionedError` | `ShopSettings.load(store)` عمداً fail-closed است؛ ورودِ قبلی Store می‌ساخت ولی `provision_for` را صدا نمی‌زد (جدول خالی) | importer همیشه یک ShopSettings/FooterSettings می‌گذارد؛ `provision_shop_settings` برای فروشگاه‌های موجود؛ validator/verify آن را الزامی/FAIL می‌کند؛ fallback به تنظیمات فروشگاه دیگر همچنان ممنوع | `ShopSettingsProvisioningRegressionTests` (۶)، `test_missing_shopsettings_fails_http_and_singleton`، `test_missing_shopsettings_in_bundle_is_blocked` |
| تصاویر/تنظیمات بصری نمایش داده نمی‌شد | رکورد DB بدون فایل روی دیسک؛ فایل با مسیر/هش متفاوت؛ nginx بدون نگاشت `/media/`؛ MIME نادرست | validator (وجود/هش/decode/مسیر امن) + integrity (دیسک واقعی) + nginx با `alias` و CSP/nosniff؛ تست سرو واقعی | `ExportValidateTests` (media.*)، `IntegrityDetectionTests`، A15 |
| صفحات 200 ولی ظاهر پیش‌فرض | published layout/نسخه‌ها/صفحه‌های Studio و داده‌های وابسته (Hero/Banner/Story با section) منتقل نشده | دامنه‌ی export شامل همه‌ی نسخه‌ها (draft/published/archived)، صفحات، container/cell، section و رسانه‌ی section-scoped، با pk حفظ‌شده تا JSON ارجاعات سالم بماند؛ validator شش نوع صفحه را الزامی می‌کند | `test_roundtrip_restores_everything_for_the_target_store` (published_version، product_ids در section)، `test_studio_without_published_version_fails`، `test_published_version_missing_a_page_type_fails` |

> محدودیت: «ظاهر دقیقاً مطابق دموی اصلی» فقط با داده‌ی اصلی قابل اثبات است؛ این گزارش آن را ادعا **نمی‌کند**.

## D. یافته‌های جانبی (حین کار کشف و رفع/مستند شد)

1. `ShopSettings` ستون‌های اعتبارنامه‌ی پیامک را متن‌ساده نگه می‌دارد ← export آن‌ها را حذف می‌کند و validator رد می‌کند.
2. `stores.0002` در هر DB تازه یک Store خالی `akhlaghi` می‌سازد ← `retire_seed_store`. (۲۸۱ فایل تست به این Store اشاره می‌کنند؛ پس تغییری در migration داده نشد.)
3. `apps/notifications/tests/test_email_transport.py` روی Python ≥ 3.12 import نمی‌شد (`asyncore/smtpd`) و runner موازی را می‌شکست ← sink جایگزین با `socketserver`.
4. هیچ endpoint سلامت وجود نداشت ← `rastisi_healthcheck` + `healthcheck.sh`.
5. nginx: `http2 on;` در nginx 1.24 (Ubuntu 24.04) ناشناخته است ← `listen 443 ssl http2;`. و نبودِ `include mime.types` در پیکربندیِ آزمایشی باعث `text/plain` برای webp شد → در راهنما/اسکریپت تست لحاظ شد.

## E. آنچه BLOCKED است (فهرست صریح)

| مورد | علت |
|---|---|
| وجود/تعداد ۱۰۰ محصول، ۳۰۱ تصویر، ۱۲۶ صفحه، ۳۳۵ فایل رسانه‌ی واقعی دو دمو | داده‌ی اصلی در Git نیست |
| تطابق بصری با دموهای اصلی | همان |
| ShopSettings/برندینگ/لوگو/رنگِ اصلی هر دمو | همان |
| اجرا روی VPS/systemd/Redis/Turnstile/TLS واقعی | دسترسی به سرور نداریم؛ فقط معادل‌های محلی تست شد |
| shellcheck، تست restore واقعی `restore.sh` روی دیتابیس production | ابزار/دسترسی موجود نیست (منطق `pg_dump/pg_restore` ساده است اما اجرا نشد) |
| اجرای `cleanup_old_rastisi.sh --execute` | عمداً اجرا نشد (فقط محافظ‌ها تست شدند) |
