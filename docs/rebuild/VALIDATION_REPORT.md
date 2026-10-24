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
| A4 | تست‌های ابزار ریبیلد (SQLite) | **PASS** | `manage.py test apps.stores.tests.test_demo_bundle` | `Ran 72 tests … OK` |
| A5 | همان تست‌ها روی PostgreSQL 16 | **PASS** | `DATABASE_URL=postgres://… manage.py test apps.stores.tests.test_demo_bundle` | `Ran 72 tests … OK` (از جمله reset دنباله‌ها؛ با حذفِ عمدیِ reset همان تست **FAIL** می‌شود: `duplicate key … catalog_product_pkey` ← تست معنادار است) |
| A6 | تست‌های موجودِ حساس به تغییرات من | **PASS** | `test apps.catalog.tests.test_price_inquiry apps.stores.tests.test_{golden_demo_owner_login_readiness,admin_host_enforcement,resolution,admin_superuser_gate}` | `Ran 153 tests … OK` |
| A7 | تست‌های seed موجود (`seed_ready_template_fashion_demo`) | **PASS** | `test apps.stores.tests.test_seed_ready_template_fashion_demo_command` | `Ran 55 tests … OK` (39 min زیر بار موازی) |
| A8 | تست email-transport (بازنویسی sink بدون `asyncore`) | **PASS** | `test apps.notifications.tests.test_email_transport` | `Ran 4 tests … OK`؛ این ماژول قبلاً روی Python ≥ 3.12 **import نمی‌شد** (`ModuleNotFoundError: asyncore`) |
| A9 | مجموعه‌ی کامل تست‌ها | **FAIL (همگی از پیش موجود، غیرمرتبط با این تغییرات)** | `manage.py test --noinput --parallel 4` | `Ran 11142 tests in 2646s — FAILED (failures=32, errors=5, skipped=124)`؛ **پس از افزودن مبدل (بخش F) دوباره اجرا شد:** `Ran 11201 tests in 2589s — FAILED (failures=32, errors=5, skipped=124)` با **دقیقاً همان مجموعه‌ی ۳۷ شناسه‌ی شکست‌خورده** (هیچ شکست تازه‌ای). **۳۵ مورد دقیقاً همان‌ها روی `main` دست‌نخورده نیز شکست می‌خورند** (اجرای ۱۵ ماژول مربوطه روی checkout اصلی `7d31155`: `Ran 233 tests — failures=32, errors=3`)؛ ماژول‌ها: onboarding_ready_template (4)، onboarding_template_fidelity، arch02b_gallery_unification، architecture_consolidation (2)، dense_marketplace_beraito_v2 (7)، editorial_jewelry_saremi_v2 (4)، phase28_canvas_first_ux، phase28c_direct_drawers، premium_leather_shokolati_v2 (3)، r411_image_display_contract (2)، r4_showcase_facade، warm_boutique_lalerokh_v2 (6)، refresh_rasti_mode_demo_visuals (2). ۲ مورد دیگر (`sms.test_gateway_live` setUpClass و `portal.test_public_site_v2…new_ready_template…`) فقط در اجرای **موازی** خطا دادند و هم روی شاخه‌ی من و هم روی `main` در اجرای جداگانه **PASS** هستند (`Ran 42 … OK` هر دو) ← ناپایداری ترتیب/موازی‌سازی. هیچ شکستی در تست‌های `apps.stores.tests.test_demo_bundle` یا ماژول‌های تغییرداده‌شده نبود. این ۳۵ مورد رفع نشدند (خارج از دامنه؛ علت ریشه‌ای بررسی نشده) |
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

## A+. اجرای مستقل در GitHub Actions (Ubuntu 24.04، Python 3.12)

| بررسی | وضعیت | مدرک |
|---|---|---|
| workflow `rebuild-package` (django check، migrations، محافظ‌های cleanup، ۷۲ تست ریبیلد، nginx syntax، ساخت ZIP کد-فقط) | **PASS** | run [40113626842](https://github.com/manouchehr94-ux/Rastisi6-14040616/actions/runs/40113626842) (push) و [40113646428](https://github.com/manouchehr94-ux/Rastisi6-14040616/actions/runs/40113646428) (PR) — `conclusion: success`؛ artifact `rastisi-release-code-only` (24.2 MB، sha256 `10ecdfc7…7e30`) |

| بررسی (بعد از افزودن مبدل) | وضعیت | مدرک |
|---|---|---|
| workflow `rebuild-package` روی کامیت مبدل `7678bba` (شامل ۵۸ تست مبدل و بررسی کامل scratch روی Python 3.12) | **PASS** | run [40124133675](https://github.com/manouchehr94-ux/Rastisi6-14040616/actions/runs/40124133675) (push) و [40124139049](https://github.com/manouchehr94-ux/Rastisi6-14040616/actions/runs/40124139049) (PR) — `success` |

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

## F. افزوده‌ی دوم: مبدل آفلاین دو SQLite مستقل + دو ZIP رسانه (`build_demo_bundle`)

ورودی: چهار فایل مالک پروژه (`demo_v5.sqlite3` + `demo_v5_media.zip`، `demo_arch02.sqlite3` + `demo_arch02_media.zip`) — **در دسترس من نیستند ⇒ اجرای واقعی BLOCKED**. همه‌ی ردیف‌های زیر روی **داده‌ی ساختگیِ هم‌ساختار با PKهای عمداً تکراری** اجرا شده‌اند و ثابت می‌کنند ابزار درست است، نه اینکه دموی واقعی درست است.

| # | بررسی | وضعیت | دستور | مدرک / محدودیت |
|---|---|---|---|---|
| F1 | تست‌های مبدل (SQLite) | **PASS** | `manage.py test apps.stores.tests.test_demo_bundle_converter` | `Ran 67 tests … OK` (۵۸ اولیه + ۹ رگرسیون کلید رسانه): دو SQLite مستقل با PK تکراری (تست `test_fixture_sources_really_collide`)، تبدیل، import، idempotency، رسانه، صفحه‌ی محصول، Studio |
| F2 | همان‌ها روی PostgreSQL | **PASS (محدود)** | `DATABASE_URL=… manage.py test …converter` | `Ran 130 (با test_demo_bundle) … OK (skipped=39)`؛ ۳۹ تستی که منبع را با dump دیتابیس تست SQLite می‌سازند روی PG عمداً skip می‌شوند؛ مسیر import روی PG جدا در F8 اجرا شد |
| F3 | همه‌ی انواع ارجاع بازنویسی می‌شوند | **PASS** | `test_every_reference_kind_is_rewritten_in_every_version` | `product_ids, source_id, category_ids, brand_ids, collection_ids, menu_id, media_asset_id, destination_id` در هر سه نسخه‌ی Studio (archived/published/draft)؛ FK محصول→دسته/برند، HeroSlide→asset/product؛ `combination_key` بازسازی می‌شود |
| F4 | هیچ نسخه/قالب/برندینگ/رسانه حذف نمی‌شود | **PASS** | `test_nothing_is_dropped`، `test_imported_files_match_the_sources_byte_for_byte` | ۳ نسخه‌ی Studio، ۱۸ صفحه، HeroSlide، ۲ MediaAsset، ShopSettings/FooterSettings، ۲ منو، واریانت‌ها؛ فایل‌های import‌شده بایت‌به‌بایت برابر ZIP |
| F5 | تضاد مسیر رسانه | **PASS** | `test_same_path_different_bytes_is_renamed_and_rewritten`، `test_identical_file_in_both_sources_is_shared_not_duplicated` | مسیر یکسان + بایت متفاوت ⇒ `shared-banner--demo_arch02.png` و ستون بازنویسی؛ بایت یکسان ⇒ یک فایل |
| F6 | ZIP: wrapper، `\`، NFD، رمزگذاری قدیمی OEM، junk، امنیت | **PASS** | `ConvertMediaTests`، `MediaZipUnitTests` (۷) | zip-slip/مسیر مطلق/درایو/symlink رد؛ ZIP ناقص ⇒ **BLOCKED** و هیچ bundleای ساخته نمی‌شود |
| F7 | امنیت و پاکیزگی | **PASS** | `test_convert_passes_and_originals_are_untouched`، `test_project_database_is_never_queried`، `test_secrets_never_reach_the_bundle` | sha256 چهار فایل ورودی قبل=بعد؛ **۰ query** روی دیتابیس پروژه؛ اسرار در bundle نیست |
| F8 | PostgreSQL E2E با bundle تبدیل‌شده | **PASS** | `migrate` → `import_demo_bundle` ×۲ → `verify_demo_integrity --http` روی PG 16 | هر دو فروشگاه (offset 1٬۰۰۰٬۰۰۰ برای دوم): ۱۴۷۵+۱۴۵۷ ردیف؛ import دوم `media_copied=0`؛ verify **PASS** (۵۵ URL پاسخ ۲۰۰ برای هر فروشگاه) |
| F9 | **E2E واقعی‌نما:** دو SQLite مستقل از seed مخزن (قالب‌های `warm_boutique` و `premium_leather`، PKهای یکسان، ZIP با/بدون wrapper) | **PASS** | `make_sample_sources.py` ← `build_demo_bundle` (بررسی کامل) | exit 0. فروشگاه دوم: ۱۴۵۷ ردیف، ۲٬۶۲۷ FK، ۳۶ ارجاع JSON، ۲۰۶ `combination_key` بازنگاشت شد. بررسی scratch: import دوم بدون تغییر؛ integrity PASS؛ **۶۱ صفحه برای هر فروشگاه از دیتابیس اصلی و از bundle import‌شده عیناً برابر** (متن، لینک، تصویر، CSS تم، ساختار) |
| F10 | قطعی‌بودن | **PASS** | دو بار اجرای مستقل (venv تازه) | `data.json` هر دو فروشگاه، همه‌ی رسانه و manifest (بدون زمان) بایت‌به‌بایت یکسان |
| F11 | حساسیت تست‌ها (mutation) | **PASS** | تخریب عمدی remap | حذف بازنویسی JSON ⇒ ۳۰ تست FAIL و مبدل خودش `remap.dangling_changed` می‌دهد؛ حذف بازسازی `combination_key` ⇒ ۲ تست FAIL |
| F12 | کلید ناشناس، منبع قدیمی‌تر، migration ناشناخته، چند فروشگاه | **PASS** | `ConvertSourceTests` (۱۱) | کلید `*_id` ناشناس ⇒ FAIL با مسیر (و `extra_scalar_keys`/`ignore_keys` اعمال می‌شود)؛ دیتابیس قدیمی‌تر ⇒ migration فقط روی **کپی** و اصل بی‌تغییر؛ migration ناشناخته ⇒ رد؛ دو فروشگاه دارای محصول ⇒ نیازمند slug صریح |
| F13 | راه‌انداز یک‌دستوری با venv تازه | **PASS (Linux)** | `build_bundle_offline.py --venv <جدید> …` | venv ساخته، requirements نصب، اجرا، `BUNDLE READY`؛ ≈ ۲ دقیقه |
| F14 | **اجرا روی Windows** (`.ps1`، `.bat`، مسیرهای طولانی/فارسی، کنسول cp1252) | **BLOCKED** | — | Windows و PowerShell در دسترس نیست: اسکریپت‌ها اجرا/syntax-check نشدند. منطق اصلی پایتونِ مستقل از OS است و فقط روی Linux تست شده؛ پیشوند `\\?\` و `reconfigure(errors="replace")` طراحی شده ولی روی Windows تأییدنشده |
| F14b | **رگرسیون اجرای واقعی:** `remap.unmapped_json_key … header_config.announcement_image_asset_id = 22` | **PASS** (ابزار) | `ConvertSourceTests` (۴ تست تازه)، `RemapUnitTests` (۵ تست تازه) | کلید در کد فعلی وجود ندارد (نسخه‌ی دیگری از page builder نوشته بود)؛ اکنون هر `*asset_id(s)` و هر کلید رسانه‌ای (`logo/banner/image/…_id`) با همان offset بازنگاشت و در validator به MediaAsset حل می‌شود؛ بعد از import به MediaAsset همان فروشگاه اشاره می‌کند؛ ارجاع از قبل شکسته شکسته می‌ماند و خطا نمی‌دهد؛ `ignore_keys` اولویت دارد؛ تست «drift guard» همه‌ی literalهای `*_id(s)` کد page-builder/content را پویش و الزام می‌کند هر کدام بازنگاشت‌شونده یا صراحتاً غیرذخیره‌ای باشد. حساسیت: غیرفعال‌کردن قاعده ⇒ ۵ تست FAIL |
| F15 | مصرف داده‌ی واقعی مالک | **BLOCKED – MISSING INPUT** | — | چهار فایل واقعی در محیط نیست |

## E. آنچه BLOCKED است (فهرست صریح)

| مورد | علت |
|---|---|
| اجرای مبدل روی چهار فایل واقعی (SQLite + ZIP) و `.ps1`/`.bat` روی Windows | فایل‌ها و Windows در دسترس نیستند (F14/F15) |
| وجود/تعداد ۱۰۰ محصول، ۳۰۱ تصویر، ۱۲۶ صفحه، ۳۳۵ فایل رسانه‌ی واقعی دو دمو | داده‌ی اصلی در Git نیست |
| تطابق بصری با دموهای اصلی | همان |
| ShopSettings/برندینگ/لوگو/رنگِ اصلی هر دمو | همان |
| اجرا روی VPS/systemd/Redis/Turnstile/TLS واقعی | دسترسی به سرور نداریم؛ فقط معادل‌های محلی تست شد |
| shellcheck، تست restore واقعی `restore.sh` روی دیتابیس production | ابزار/دسترسی موجود نیست (منطق `pg_dump/pg_restore` ساده است اما اجرا نشد) |
| اجرای `cleanup_old_rastisi.sh --execute` | عمداً اجرا نشد (فقط محافظ‌ها تست شدند) |
