# SECURITY_NOTES — حساب‌ها، محرمانگی و تنظیمات ایمن

## ۱. هیچ رازی در GitHub نیست
- هیچ کاربر، رمز، توکن، کلید API، `SECRET_KEY` یا `PAYMENT_CREDENTIAL_KEY` ساخته/ثبت/commit نشده است. `rebuild/deployment/rastisi.env.example` فقط مقدار `CHANGE_ME` دارد.
- اسکریپت ZIP (`build_release_zip.py`) فایل‌های `.env*`، کلیدهای `*.pem/*.key`، SQLite، `media/` و نام‌های شبیه secret را رد می‌کند؛ ZIP فقط از فایل‌های **ردیابی‌شده‌ی Git** ساخته می‌شود.
- bundle داده (خارج از Git) نیز بدون اسرار است: ستون‌های اعتبارنامه‌ی پیامک (`melipayamak_*`, `kavenegar_api_key`, `smsrasti_device_token`) از `ShopSettings` در export حذف می‌شوند و validator هر bundle حاوی مقدار غیرخالی چنین فیلدی را رد می‌کند (تست: `test_credentials_on_shopsettings_are_dropped_at_export`، `test_validator_rejects_a_bundle_that_carries_credentials`).
  - این یافته در حین کار کشف شد: `ShopSettings` ستون‌های اعتبارنامه‌ی پیامک را (به‌صورت متن ساده) دارد. در نصب تازه باید دوباره از پنل وارد شوند.

## ۲. دو حساب نصب (تنها دو حساب)
| حساب | نقش | دسترسی |
|---|---|---|
| `platform_owner` | `is_superuser=True`, `is_staff=True`, بدون عضویت فروشگاه | فقط `https://platformadmins.rastisi.ir/login/` (دروازه‌ی `is_staff and is_superuser`) |
| `shops_admin` | `is_staff=False`, `is_superuser=False`; `StoreMembership(role=OWNER, status=ACTIVE)` روی `demo-v5` و `demo-arch02` | `https://rastisi.ir/login/` ← handoff امضاشده ← `/admin-portal/` همان فروشگاه |

- ابزار: `manage.py create_install_accounts` (کد: `apps/stores/services/demo_bundle/accounts.py`).
- رمز: فقط `getpass` (دو بار، بدون echo) یا نام یک **متغیر محیطی** (`--*-password-env VAR`) برای secret manager. آرگومان `--password` وجود ندارد (در history و `ps` نشت می‌کرد؛ تست `test_command_has_no_password_cli_argument`). بدون TTY و بدون env، فرمان خطا می‌دهد، رمز نمی‌سازد.
- رمز با اعتبارسنج‌های Django (`validate_password`) بررسی و فقط به‌صورت hash ذخیره می‌شود؛ هرگز چاپ/لاگ نمی‌شود (تست: خروجی فرمان رمز را ندارد).
- idempotent: اجرای دوباره رمز موجود را تغییر نمی‌دهد مگر `--reset-password`؛ حساب سومی نمی‌سازد؛ اگر فروشگاه مالک فعالِ دیگری دارد، آن را جابه‌جا نمی‌کند (خطا می‌دهد).
- مدل مجوز بدون تغییر ماند: دسترسی به پنل فروشگاه فقط با `StoreMembership` فعال و میزبان معتبر است؛ `platform_owner` بدون عضویت به پنل فروشگاه نمی‌رسد؛ `shops_admin` به پنل پلتفرم نمی‌رسد (هر دو با تست پوشش داده شده‌اند).

## ۳. ورود
- مسیر مدیر پلتفرم **دست نخورد**: `platformadmins.rastisi.ir/login/` (URLconf جداگانه؛ `/login/` همین مسیر روی host فروشگاه ۴۰۴ است و `/admin/` جنگو روی host پلتفرم‌ادمین ۴۰۴).
- ورود مرکزی مالک/عضو: `rastisi.ir/login/` با rate-limit مشترک (Redis الزامی در production) و **Cloudflare Turnstile fail-closed** (خالی‌بودن کلید/hostname در production باعث خطای startup می‌شود).
- انتقال به پنل: `enter_admin` یک ticket کوتاه‌عمر می‌سازد و به host خودِ فروشگاه می‌فرستد؛ کاربر بدون عضویت ۴۰۴ می‌گیرد.

## ۴. تنظیمات سرور
- `DJANGO_DEBUG=False`, `ALLOWED_HOSTS` دقیق (۵ نام، بدون wildcard)، `CSRF_TRUSTED_ORIGINS`، کوکی Secure، HSTS تدریجی.
- `DJANGO_SECURE_PROXY_SSL_HEADER=X-Forwarded-Proto:https` و `DJANGO_TRUSTED_PROXY_CIDRS=unix`؛ nginx هدرهای `X-Forwarded-For/Proto` را **بازنویسی** می‌کند (نه الحاق).
- gunicorn فقط روی unix socket (`0660`، گروه `www-data`) و با sandbox systemd (`ProtectSystem=strict`, `NoNewPrivileges`, `ReadWritePaths` محدود).
- `/media/` با `nosniff` و `Content-Security-Policy: default-src 'none'; sandbox`؛ `DJANGO_PRIVATE_MEDIA_ROOT` در nginx نگاشت نمی‌شود.
- PostgreSQL: role/DB اختصاصی؛ اسکریپت‌ها اگر نام DB با `rastisi`/`rastisi_*` شروع نشود **متوقف می‌شوند**. Redis: instance/DB/رمز جدا.
- ابزار backup فایل env (اسرار) را کپی نمی‌کند.

## ۵. ایمنی ابزارهای ریبیلد
- importer هیچ کاربر/رمز/سفارش/مشتری را نمی‌خواند یا نمی‌نویسد؛ فقط ردیف‌های همان Store؛ pk متعلق به Store دیگر = abort + rollback؛ مسیر رسانه‌ی خطرناک (`..`، مطلق، backslash) رد؛ فایل موجود با محتوای متفاوت بازنویسی نمی‌شود.
- ابزار پاک‌سازی: allow-list + حفاظت نام + resolve symlink، dry-run پیش‌فرض، نیاز به backup بررسی‌شده و flag صریح؛ در [`SERVER_CLEANUP_PLAN.md`](SERVER_CLEANUP_PLAN.md).
- `retire_seed_store` فقط Store خالیِ ساخته‌شده توسط migration (`akhlaghi`) را و فقط با `--confirm` حذف می‌کند و اگر داده‌ی واقعی داشته باشد رد می‌کند.

## ۶. مواردی که هنوز انسانی/عملیاتی است
چرخش کلیدها پس از هر نشت احتمالی؛ فعال‌سازی HSTS پس از اثبات HTTPS؛ تنظیم SMS/ایمیل production؛ بازبینی SPF/DKIM؛ نگهداری backup خارج از VPS؛ فعال‌بودن firewall. این موارد توسط کد قابل اثبات نیستند.
