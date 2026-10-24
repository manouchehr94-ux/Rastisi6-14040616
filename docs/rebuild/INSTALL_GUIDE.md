# INSTALL_GUIDE — نصب تازه‌ی RastiSi روی VPS (صفر تا صد)

> ⚠️ این راهنما دستورهایی است که **شما** بعداً روی سرور اجرا می‌کنید. در این مأموریت هیچ‌کدام روی سرور اجرا نشده‌اند و `rastiservice.ir` در هیچ مرحله لمس نمی‌شود. هر مرحله‌ی «پاک‌سازی» جداست: [`SERVER_CLEANUP_PLAN.md`](SERVER_CLEANUP_PLAN.md).
>
> وضعیت داده: بدون `bundle` اصلی دو دمو، مرحله‌ی ۸ به‌درستی `BLOCKED` می‌شود و نصب فقط «کد آماده» است ([`MISSING_INPUTS.md`](MISSING_INPUTS.md)).

## پیش‌نیازها

| مورد | ملاحظه |
|---|---|
| OS | Ubuntu 22.04/24.04، Python ≥ 3.10، `postgresql`, `redis`, `nginx`, `certbot`, `rsync`, `curl` |
| DNS | رکورد A/AAAA برای ۵ نام: `rastisi.ir`, `www.rastisi.ir`, `platformadmins.rastisi.ir`, `demo-v5.rastisi.ir`, `demo-arch02.rastisi.ir` |
| PostgreSQL | **دیتابیس و role اختصاصی** `rastisi` / `rastisi_app`؛ هرگز دیتابیس یا role مربوط به rastiservice استفاده نشود |
| Redis | ترجیحاً instance جدا (پورت 6380 با رمز). اگر مجبور به اشتراک هستید: شماره‌ی DB جدا + رمز، و هرگز `FLUSHALL/FLUSHDB` |
| Turnstile | کلیدهای Cloudflare برای `rastisi.ir` و `platformadmins.rastisi.ir` (در production اجباری و fail-closed) |

## ۱. دریافت بسته از GitHub

```bash
# گزینه‌ی الف: clone شاخه
git clone --branch claude/rastisi-complete-rebuild-20261024 https://github.com/manouchehr94-ux/Rastisi6-14040616.git /tmp/rastisi-src
# گزینه‌ی ب: ZIP ساخته‌شده با rebuild/tools/build_release_zip.py (artifact یا ساخت محلی)
python rebuild/tools/build_release_zip.py --out dist/rastisi-release.zip      # بدون داده = CODE-ONLY
sha256sum -c dist/rastisi-release.zip.sha256
unzip dist/rastisi-release.zip -d /tmp/rastisi-release   # مسیر داخلی: rastisi/
```

## ۲. آماده‌سازی میزبان (root) — فقط فایل‌ها و کاربر RastiSi

```bash
sudo bash /tmp/rastisi-release/rastisi/rebuild/deployment/scripts/provision_host.sh --dry-run   # بخوانید
sudo bash /tmp/rastisi-release/rastisi/rebuild/deployment/scripts/provision_host.sh
```
کاربر سیستمی `rastisi`، مسیرهای `/srv/rastisi`, `/var/www/rastisi/{staticfiles,media,acme}`, `/var/lib/rastisi/private_media`, `/var/log/rastisi`, `/etc/rastisi`, `/var/backups/rastisi`، فایل‌های systemd و `/etc/nginx/sites-available/rastisi.conf` ساخته می‌شود. چیزی enable/start/reload نمی‌شود و `/etc/rastisi/env` موجود بازنویسی نمی‌شود.

## ۳. PostgreSQL اختصاصی

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE rastisi_app LOGIN;
\password rastisi_app          -- رمز را همین‌جا تایپ کنید (در history ثبت نمی‌شود)
CREATE DATABASE rastisi OWNER rastisi_app ENCODING 'UTF8' TEMPLATE template0;
SQL
```

## ۴. محیط (`/etc/rastisi/env`)

قالب: `rebuild/deployment/rastisi.env.example` (فقط placeholder). روی سرور ویرایش کنید و همه‌ی `CHANGE_ME` را بسازید:
```bash
sudoedit /etc/rastisi/env
python3 -c "from django.core.management.utils import get_random_secret_key as g; print(g())"   # DJANGO_SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"    # PAYMENT_CREDENTIAL_KEY
```
پرونده‌ی env هرگز commit/کپی در Git/ZIP نمی‌شود (`build_release_zip.py` آن را رد می‌کند).

## ۵. نصب برنامه و migration

```bash
sudo rsync -a /tmp/rastisi-release/rastisi/ /srv/rastisi/ && sudo chown -R rastisi:rastisi /srv/rastisi
sudo -u rastisi RASTISI_SKIP_BACKUP=1 bash /srv/rastisi/rebuild/deployment/scripts/deploy_app.sh /srv/rastisi
```
این اسکریپت venv می‌سازد، `requirements-production.txt` (Django + gunicorn) را نصب می‌کند، سپس `check --deploy`، `migrate`، `collectstatic` و `rastisi_healthcheck` را اجرا می‌کند. (در به‌روزرسانی‌های بعدی `RASTISI_SKIP_BACKUP` را نگذارید تا قبل از migrate پشتیبان گرفته شود.)

## ۶. systemd و nginx

```bash
sudo systemctl enable --now rastisi-gunicorn.socket
# گواهی TLS (یک بار): فایل rebuild/deployment/nginx/rastisi-http-bootstrap.conf را طبق توضیح خودش اجرا کنید
sudo cp /srv/rastisi/rebuild/deployment/nginx/rastisi.conf /etc/nginx/sites-available/rastisi.conf
sudo ln -s /etc/nginx/sites-available/rastisi.conf /etc/nginx/sites-enabled/rastisi.conf
sudo nginx -t && sudo systemctl reload nginx
```
`rastisi.conf` هیچ `default_server` ندارد و فقط ۵ نام را می‌گیرد؛ فایل‌های سایت‌های دیگر دست‌نخورده می‌مانند. اگر `nginx -t` خطا داد، reload نکنید.

## ۷. بررسی اولیه (هنوز بدون داده)

```bash
sudo -u rastisi bash /srv/rastisi/rebuild/deployment/scripts/healthcheck.sh
```

## ۸. ورود داده‌ی دو دمو (نیازمند bundle)

bundle را قبلاً روی لپ‌تاپ با `build_demo_bundle` از دو SQLite و دو ZIP بسازید ([`OFFLINE_WINDOWS_GUIDE.md`](OFFLINE_WINDOWS_GUIDE.md)). فقط پوشه‌ی نهایی به سرور منتقل می‌شود؛ SQLite و ZIP اصلی لازم نیست روی سرور بروند.

```bash
# bundle را به سرور منتقل کنید (scp/rsync)، سپس:
sudo -u rastisi python /srv/rastisi/manage.py validate_demo_bundle /srv/rastisi_bundle     # باید PASS باشد
sudo -u rastisi bash /srv/rastisi/rebuild/deployment/scripts/import_demo_stores.sh /srv/rastisi_bundle
```
ترتیب: validate → backup → import → provision → verify (`--http`). `validate` خروجی `2` (BLOCKED) یعنی ورودی ناقص، `1` یعنی خراب. بدون bundle: **این مرحله را رد نکنید؛ نصب «داده ندارد»**. import دوباره امن است (idempotent).

اگر قبلاً فروشگاهی بدون ShopSettings ساخته شده (علت قدیمیِ خطای ۵۰۰ `ShopSettingsNotProvisionedError`):
```bash
sudo -u rastisi python manage.py provision_shop_settings --store demo-v5 --store demo-arch02
```
(فقط ردیف خالیِ پیش‌فرض می‌سازد؛ برندینگ واقعی باید از bundle بیاید.)

## ۹. حذف فروشگاه خالی `akhlaghi` (ساخته‌شده توسط migration)

`stores.0002` در هر دیتابیس تازه یک Store خالی `akhlaghi` می‌سازد. برای «فقط دو فروشگاه»:
```bash
sudo -u rastisi python manage.py retire_seed_store            # dry-run
sudo -u rastisi python manage.py retire_seed_store --confirm  # فقط اگر فقط ردیف‌های provisioning داشته باشد
```

## ۱۰. ساخت دو حساب (تعاملی)

```bash
sudo -u rastisi python manage.py create_install_accounts
# رمز دو بار با getpass پرسیده می‌شود. برای secret manager: --platform-owner-password-env VAR --shops-admin-password-env VAR2
```
`platform_owner` فقط در `https://platformadmins.rastisi.ir/login/`؛ `shops_admin` در `https://rastisi.ir/login/` و سپس handoff به `https://demo-v5.rastisi.ir/admin-portal/` و `https://demo-arch02.rastisi.ir/admin-portal/`.

## ۱۱. شروع سرویس، تست دود، cron

```bash
sudo systemctl start rastisi-gunicorn.service
bash /srv/rastisi/rebuild/deployment/scripts/smoke_test.sh rastisi.ir
sudo -u rastisi python /srv/rastisi/manage.py verify_demo_integrity --http
sudo -u rastisi crontab /srv/rastisi/deploy/cron/rastisi.crontab    # ابتدا MAILTO/مسیرها را ببینید
```

## ۱۲. Backup و Rollback

```bash
sudo -u rastisi bash /srv/rastisi/rebuild/deployment/scripts/backup.sh                   # DB + media + پیکربندی
sudo RASTISI_PG_SUDO=1 bash /srv/rastisi/rebuild/deployment/scripts/restore.sh /var/backups/rastisi/<ts> --verify   # اثبات restore روی DB موقت
# Rollback واقعی (سرویس را متوقف کنید):
sudo systemctl stop rastisi-gunicorn
sudo bash /srv/rastisi/rebuild/deployment/scripts/restore.sh /var/backups/rastisi/<ts> --apply --yes
sudo systemctl start rastisi-gunicorn
```
برای rollback کد: نسخه‌ی قبلیِ ZIP را دوباره با `deploy_app.sh` نصب کنید (migrationهای جلو رفته را با `restore.sh` برگردانید).

## عیب‌یابی سریع

| نشانه | علت | راه‌حل |
|---|---|---|
| ۵۰۰ در جزئیات محصول / سبد، لاگ: `ShopSettingsNotProvisionedError` | Store بدون ردیف `core_shopsettings` | import از bundle یا `provision_shop_settings` (رفتار عمداً fail-closed است؛ به تنظیمات فروشگاه دیگر fallback نمی‌شود) |
| صفحه ۲۰۰ ولی ظاهر پیش‌فرض | `StorefrontLayout.published_version` خالی/نسخه‌ی اشتباه | `verify_demo_integrity` را ببینید (`studio.*`)؛ ورودی باید از bundle اصلی باشد |
| تصویر نمی‌آید | فایل روی دیسک نیست / مجوز nginx / `DJANGO_MEDIA_ROOT` متفاوت | `verify_demo_integrity` (`file.missing`)، `ls -l /var/www/rastisi/media`، alias در nginx |
| `DisallowedHost` | Host در `DJANGO_ALLOWED_HOSTS` نیست | env را اصلاح و gunicorn را reload کنید |
| ورود رد می‌شود | Turnstile/keys یا Redis | `rastisi_healthcheck` و لاگ gunicorn |
