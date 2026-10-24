# SERVER_CLEANUP_PLAN — پاک‌سازی اختصاصی RastiSi بدون دست‌زدن به RastiService

> **هیچ‌چیز از این سند در این مأموریت اجرا نشد.** ابزار: `rebuild/deployment/scripts/cleanup_old_rastisi.sh` (+ `cleanup_guards.sh`). اجرای هر دستور تخریبی یک مرحله‌ی جدا با مجوز صریح شماست.

## اصول حفاظت از `rastiservice.ir`

1. **حفاظت با نام:** هر مورد شامل `rastiservice` / `rasti-service` / `rasti_service` همیشه رد می‌شود.
2. **حفاظت با دامنه:** فقط موارد «اثبات‌شده‌ی مالک RastiSi» قابل حذف‌اند (allow-list)، نه «هر چه شبیه rastisi است»:
   - systemd: `rastisi*.service|socket|timer` و `gunicorn-rastisi*`
   - nginx: فایل‌های site/conf.d با نامِ شامل `rastisi` (نه `rastiservice`)
   - مسیر: فقط زیر `/srv/rastisi*`, `/var/www/rastisi*`, `/var/lib/rastisi`, `/var/log/rastisi`, `/etc/rastisi`, `/opt/rastisi*`, `/home/*/rastisi*` — **پس از resolve شدن symlink** (لینکی که به دایرکتوری RastiService اشاره کند رد می‌شود)
   - دیتابیس: فقط `rastisi` یا `rastisi_*`
3. **هرگز candidate نیستند:** خود PostgreSQL (cluster/roleهای مشترک)، Redis، تنظیمات سراسری nginx، `/etc/letsencrypt`، گواهی/دامنه‌ی سایت‌های دیگر، crontab، DNS.
4. تست آفلاین این قواعد: `bash rebuild/checks/test_cleanup_guards.sh` → `PASS cleanup guards` (شامل تلاش برای حذف `rastiservice` و symlink escape).

## مراحل (هر کدام جدا و با تأیید شما)

| # | مرحله | دستور | تخریبی؟ |
|---|---|---|---|
| 0 | قفل ورودی: نصب تازه‌ی جدید سالم است | `smoke_test.sh`, `verify_demo_integrity --http` = PASS | خیر |
| 1 | **Snapshot/Backup کامل** از وضعیت فعلی (DB قدیمی RastiSi، media، فایل‌های پیکربندی) | `backup.sh` (فقط DB `rastisi*`) + `tar` دستیِ مسیرهای قدیمی در `/var/backups/rastisi/<ts>` | خیر |
| 2 | **اثبات restore** | `restore.sh <backup> --verify` سپس `touch <backup>/RESTORE_VERIFIED` | خیر (DB موقت `rastisi_restoretest` ساخته و حذف می‌شود) |
| 3 | **Inventory فقط‌خواندنی** | `cleanup_old_rastisi.sh --inventory > cleanup_manifest.txt` | خیر |
| 4 | **بازبینی انسانی** manifest: هر خط را بخوانید؛ آنچه نباید حذف شود پاک کنید؛ هر ابهام را حذف کنید | ویرایش دستی | خیر |
| 5 | **تأیید مجدد سلامت** نصب جدید (بند ۰) و اینکه `https://rastiservice.ir` پاسخ می‌دهد (فقط GET) | `curl -sI https://rastiservice.ir` | خیر |
| 6 | **Dry-run** | `cleanup_old_rastisi.sh --execute cleanup_manifest.txt` → فقط `WOULD`/`REFUSED` چاپ می‌کند | خیر |
| 7 | **اجرا (مجوز صریح)** | `sudo cleanup_old_rastisi.sh --execute cleanup_manifest.txt --backup-dir /var/backups/rastisi/<ts> --i-confirm-rastisi-only` | **بله** |
| 8 | پس از اجرا: `nginx -t`، `systemctl --failed`، سلامت rastiservice و RastiSi جدید | دستی | خیر |

شرط‌های سخت مرحله‌ی ۷: اجرا با root؛ `SHA256SUMS` پشتیبان معتبر؛ فایل `RESTORE_VERIFIED` موجود؛ بدون `--i-confirm-rastisi-only` هیچ حذفی انجام نمی‌شود؛ پس از حذف nginx اگر `nginx -t` شکست خورد reload انجام نمی‌شود.

## Rollback پاک‌سازی
`restore.sh <backup> --apply --yes` دیتابیس و media را برمی‌گرداند؛ فایل‌های پیکربندی در `config.tar.gz` پشتیبان هستند (پوشه‌های کد قدیمی را باید در مرحله‌ی ۱ با `tar` دستی نگه دارید).

## چه چیزی عمداً دستی است
ورودی crontab قدیمی، رکوردهای DNS، گواهی‌های Let's Encrypt قدیمی، کاربرهای سیستمی/PostgreSQL قدیمی (`DROP ROLE` خودکار نیست)، Redis. برای هر کدام قبل از حذف ثابت کنید RastiService استفاده‌ای ندارد.
