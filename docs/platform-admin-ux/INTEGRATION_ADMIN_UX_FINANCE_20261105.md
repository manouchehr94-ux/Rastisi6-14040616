# ادغامِ نهایی: Platform Admin UX + PR #41 (قیمت‌گذاری) + PR #40 (مالی) — ۲۰۲۶-۱۱-۰۵

شاخه‌ی **محلی و push‌نشده** `integration/admin-ux-finance-20261105` (worktree: `/home/user/rastisi-adminux-integ`)، روی `ux/platform-admin-redesign-20261105@361cd83b` + merge از `financial/platform-billing-20261105@e6f57b93`. هیچ‌یک از شاخه‌هایِ PR (#40، #41، #42) تغییر نکرد؛ هیچ push/merge/deploy/migration روی محیطِ ماندگار انجام نشد.

## ۱. ادغام
| مورد | نتیجه |
|---|---|
| conflictها | ۴ فایل: `platform_admin/base.html` (پوسته‌یِ UX نگه داشته شد؛ پنج آیتمِ مالی خودکار از رجیستری آمدند)، `payment_invoice_detail.html` (UX + کارتِ «بازپرداخت‌ها»یِ PR #40 در سیستمِ جدید بازنویسی)، `portal/views.py` و `app/billing_plans.html` (کیتِ `docs/pricing/pr40_integration/`، شاملِ اصلاحِ ادغامِ step-up) |
| گرافِ migration | بدونِ leafِ متعارض؛ `migrate` از صفر روی PostgreSQL ۱۶ و `makemigrations --check` ⇒ «No changes detected» |
| تستِ ترکیبیِ سه‌گانه (کیت) | `test_pricing_x_platform_billing_integration` اضافه شد و می‌گذرد |

## ۲. مهاجرتِ قالب‌هایِ مالی (بدونِ سیستمِ استایلِ جدا)
هفت قالب (شش قالبِ PR #40 + فاکتور): `payment_gateways`، `payment_transactions`، `payment_reconciliation`، `manual_claims`، `manual_claim_detail`، `sms_purchases`، `payment_invoice_detail` — همه `extends base.html` (سایدبارِ یگانه)، `pa-pagehead`، `pa-form/fieldset/formbar`، `pa-filters`، `pa-tablewrap` (ستونِ `pa-num`/`pa-actcol`)، `pa-badge`، `pa-empty`، `data-confirm` و `pa-ltr` برایِ شناسه‌ها. **هیچ فیلد، نامِ POST، action، گارد (can_review / is_self)، ماسکِ اعتبارنامه، یا ممیزی تغییر نکرد.**

| معیار (۷ صفحه × ۵ عرض = ۳۵ بررسی، همان خزش) | قبل (PR #40 همان‌گونه که هست) | بعد |
|---|---|---|
| `style=""`/`onclick`/`onsubmit`/حلقه‌یِ flash محلی (شمارشِ ایستا در قالب‌ها) | ۶۷ | **۰** |
| `[style]` در DOM (جمعِ بررسی‌ها) | ۱۲۹۰ | **۰** |
| بررسی‌هایِ دارایِ overflowِ افقی | ۷ | **۰** |
| فیلدِ عددی با فلشِ مرورگر | ۴۰ | **۰** |
| ارتفاعِ دکمه‌ها | ۳۶/۴۴/۴۶/۴۹/۷۶ | **۳۸** (+ ۸۰ دکمه‌یِ «نمایشِ رمز» ۳۰px درونِ فیلد؛ مؤلفه‌یِ مشترکِ core) |
| طولِ صفحه‌یِ درگاه‌ها (۱۴۴۰) | ≈۷۹۷۲px | ≈۱۶۲۰px (کارتِ هر درگاه جمع‌شونده؛ فعال/پیش‌فرض بازند؛ `#gw-<code>` باز می‌کند) |

نکته‌یِ طراحی: نسخه‌یِ نخستِ مهاجرت صفحه‌یِ درگاه‌ها را ≈۴۷٪ بلندتر کرد (همه‌یِ درگاه‌ها بازِ کامل)؛ با اسکرین‌شات‌ها پیدا شد و با کارتِ جمع‌شونده اصلاح شد.

## ۳. Inbox (قالبِ مشترک با داشبوردِ فروشنده)
بدونِ ویرایشِ قالب/`inbox.css`: فقط داخلِ `.pa` متغیرهایی که `inbox.css` می‌خواند (`--primary`، `--card`، …) به توکن‌هایِ پنل نگاشت شد (به‌جایِ fallbackِ بنفش)، دکمه‌ها ۳۸px، و `h2`ِ صفحه با `role=heading aria-level=1` به h1 معرفی می‌شود (JS در پوسته‌یِ پنل). داشبوردِ فروشنده `.pa` ندارد ⇒ بی‌تغییر (هیچ فایلی خارج از `apps/portal` تغییر نکرد).

## ۴. فلشِ فیلدهایِ عددی
خزش روی ۵۱ صفحه‌یِ ادغام‌شده: **۱۵۳ فیلدِ عددی، ۰ فیلد با فلش** (`appearance:textfield` + حذفِ `::-webkit-*-spin-button`؛ بدونِ دکمه‌یِ +/−؛ `min/max/step` و `direction:ltr` حفظ). تستِ خودکار + بررسیِ تصویری (قبل: فلش با hover، بعد: بدونِ فلش).

## ۵. پذیرشِ (acceptance) روی درختِ ادغام‌شده
| بررسی | نتیجه |
|---|---|
| خزشِ همه‌یِ مسیرهایِ مالک (۹۵ مسیر؛ ۵۱ صفحه‌یِ GET) × ۱۴۴۰/۱۲۸۰/۷۶۸/۳۹۰/۳۲۰ | **۲۵۵ بررسی: همه ۲۰۰، ۰ overflow، ۰ خطایِ JS/کنسول، ۱ سایدبارِ یگانه** (POST-onlyها ۴۰۵ مورد انتظار؛ ۴۰۴ِ تصاویرِ `extra01–16` در «تصاویرِ سایتِ عمومی» جدا گزارش می‌شود) |
| `test_platform_admin_ux` روی ادغام | **۳۱ تست OK** (رجیستری/ناوبری بدونِ صفحه‌یِ پنهان، smoke همه‌یِ routeهایِ GET شاملِ مالی، مجوز، CSRF، دکمه‌هایِ سیستم، قراردادِ قالب‌هایِ مالی، تأییدِ اقداماتِ پولی، ماسکِ اعتبارنامه) |
| مرورگر (اصلی، ۲۳ بررسی) + مالی (۱۷ بررسی: سایدبار/گروهِ فعال، ماسکِ اعتبارنامه، تأییدِ تأیید/رد/لغو، اعتبارسنجیِ دلیل، فاکتور، Inbox) | **ALL PASSED** |
| SQLite موازی: `portal subscriptions billing notifications core sms stores dashboard` | ۵۸۳۹ تست؛ ۲ failure + ۴ error — **همه از قبل/غیرمرتبط** (بخشِ ۷)؛ تنها مورد از کارِ من (متنِ نشانِ تطبیق) یافت و اصلاح شد و در ایزوله می‌گذرد |
| **PostgreSQL ۱۶** (`billing subscriptions` + UX + lifecycle + pricing + panel، شاملِ concurrencyِ پرداخت و card-to-card) | ۷۰۱ تست؛ ۳ error — **باگِ واقعی در PR #41 یافت شد** (بخشِ ۶)؛ پس از اصلاح ۱۶/۱۶ lifecycle OK |

## ۶. نقص‌هایِ واقعیِ یافت‌شده در شاخه‌هایِ push‌شده (در شاخه‌یِ ادغام اصلاح شد؛ اعمال روی #41/#42 نیازمندِ مجوزِ شماست)
1. **PR #41 (`feature_service.py`) — خطایِ PostgreSQL:** `select_for_update()` همراهِ `select_related("entitlement")` (FKِ nullable) روی PostgreSQL `NotSupportedError` می‌دهد؛ ⇒ «آمادگیِ فنی» و «وضعیتِ تجاری» قابلیت‌ها در production کار نمی‌کرد (روی SQLite پنهان بود). اصلاح: `select_related(...).select_for_update(of=("self",))` (۲ جا). تستِ lifecycle روی PG اکنون سبز.
2. **PR #42 (UX) — `.pa-sr` داخلِ جدولِ عریض overflowِ صفحه می‌ساخت** (۳۹۰/۳۲۰px، صفحه‌یِ خریدهایِ پیامک): اصلاح با `.pa-tablewrap,.pa-card{position:relative}` (در این شاخه؛ صفحه‌هایِ قیمت‌گذاری/UX‌ِ فعلی این الگو را نداشتند).
3. تستِ قراردادیِ PR #40 (`ادعاهایِ کارت‌به‌کارتِ در انتظار: 1`) به متنِ پیوسته نیاز داشت؛ نشانِ تطبیق متنِ ساده شد.

## ۷. خطاهایِ تستِ از قبل موجود/غیرمرتبط (جدا از نتایج)
* `apps.notifications.tests.test_email_transport` — `asyncore` در Python 3.13 وجود ندارد (import error).
* `stores…test_refresh_rasti_mode_demo_visuals_command` (۱ failure + ۱ error) — از قبل روی PR #40 هم شکست می‌خورد.
* `core…test_purchase_tracking.ConcurrentRenderTests` و `sms…test_gateway_live.LiveProtocolTests` (`setUpClass`، `UNIQUE django_content_type` زیرِ `--parallel` روی SQLite) — به‌صورتِ ایزوله OK؛ وابسته به ترتیب/حالتِ اشتراکی.
* `test_public_site_v2…test_a_new_ready_template_appears_without_any_code_change` — در اجرایِ موازی گاهی؛ ایزوله OK.

## ۸. نقص‌هایِ باقی‌مانده
* ۱۶ تصویرِ پیش‌فرضِ سایتِ عمومی (`extra01–16.webp`) در مخزن نیست — **جدا بررسی می‌شود؛ هیچ asset ای به این بازطراحی اضافه نشد** (جایگزینِ خنثی نمایش داده می‌شود؛ کنسول ۴۰۴ لاگ می‌کند).
* دکمه‌یِ «نمایشِ رمز» ۳۰px (مؤلفه‌یِ مشترکِ `core`، درونِ فیلد).
* ارقام در جدول‌ها لاتین‌اند (ورودی‌ها عمداً ltr/لاتین).
* کارتِ درگاه‌ها پیش‌فرض بسته است (غیرِ فعال/پیش‌فرض)؛ مالک برایِ پیکربندی یک کلیک اضافه می‌زند.
* تست‌هایِ مرورگر دستی‌اند (CI ندارند).

## ۹. دستورالعملِ امنِ QA روی ویندوز
**اصل‌ها:** فقط روی کپیِ محلی/SQLite یا PostgreSQLِ آزمایشی؛ هرگز `DATABASE_URL` یا اعتبارنامه‌یِ production؛ بدونِ push/merge/deploy؛ `Settings → Payment Gateways` فقط با مقادیرِ ساختگی.
1. شاخه‌یِ UX (push‌شده) را در یک worktreeِ جدا بگیرید:
   ```powershell
   git fetch origin ux/platform-admin-redesign-20261105
   git worktree add D:\Projects\RastiSi\QA_ADMINUX_20261105 origin/ux/platform-admin-redesign-20261105
   ```
2. برایِ **درختِ ادغام‌شده** (push نشده) از bundleِ محلی استفاده کنید که همراهِ این گزارش داده شد (فایلِ `integration-admin-ux-finance-20261105.bundle`):
   ```powershell
   cd D:\Projects\RastiSi\QA_ADMINUX_20261105
   git fetch D:\path\to\integration-admin-ux-finance-20261105.bundle integration/admin-ux-finance-20261105:integration/admin-ux-finance-20261105
   git switch integration/admin-ux-finance-20261105
   ```
3. محیط (SQLite، همان پیش‌فرض): `python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt; $env:DATABASE_URL=""`؛ `python manage.py migrate`؛ `python manage.py runserver 18082`. ابرکاربرِ آزمایشی بسازید (`createsuperuser`) و با `http://platformadmins.rastisi.localhost:18082/` وارد شوید.
4. داده‌یِ ساختگی (اختیاری): `docs/platform-admin-ux/qa-tools/ux_seed.py` و `finance_seed.py` را با `python manage.py shell -c "exec(open(r'...').read())"` اجرا کنید (فقط داده‌یِ نمونه).
5. چک‌لیستِ بصری در ۱۴۴۰/۱۲۸۰/۷۶۸/۳۹۰/۳۲۰: یک سایدبارِ راست؛ منویِ موبایل؛ بدونِ اسکرولِ افقیِ صفحه؛ فیلدهایِ عددی بدونِ فلش؛ دکمه‌هایِ هم‌قد؛ تأیید پیش از بایگانی/انتشار/لغو/بازپرداخت/تأییدِ claim؛ درگاه‌ها: ماسکِ رمز، کارتِ جمع‌شونده؛ Inbox سبز (نه بنفش).
6. تست‌ها: `python manage.py test apps.portal.tests.test_platform_admin_ux apps.portal.tests.test_feature_lifecycle apps.billing apps.subscriptions --noinput`
