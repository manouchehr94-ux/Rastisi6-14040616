# ممیزی زیرساخت اعلان‌ها — RastiSi (۱۴۰۵/۰۸/۱۰)

پایه: `cfed2bf9f68dacb478dcff4f826575ef5ad4ed10` (= شاخهٔ `feature/admin-panel-modernization-20261029` روی ریموت). نتیجهٔ این ممیزی مستقیماً مبنای ساخت شد.

## ۱ تا ۱۰ — پاسخ‌ها (با فایل/تابع واقعی)

| # | پرسش | یافته |
|---|---|---|
| ۱ | چه زیرساختی هست؟ | اپ `apps/notifications` با **`NotificationOutbox`** (`models.py`)، `dispatcher.dispatch_event/safe_dispatch`، `notification_service.deliver_pending/_process/retry_notification/notify_security_event`، رجیستری رویداد `events.py` (`EVENTS`، ~۴۰ رویداد مشتری/کارکنان)، قالب‌ها `NotificationTemplate`/`template_service`، نقاط اتصال `business_events.py`، فرمان `process_notification_outbox`، `verify_delivery_channels`. بیرون از آن: `apps/sms` (`SmsLog`, `sms_service`, `otp_service`, `backends`), `core.AuditLogEntry` + `audit_service.record_audit_event`, `portal.PlatformAuditLogEntry`, Django Messages + Toast Alpine در `base_admin.html`. |
| ۲ | چه ماژول‌هایی رویداد تولید می‌کنند؟ | `business_events.*` از: `orders/order_service.py:576,633`، `orders/payment_service.py:100`، `orders/lifecycle.py:53`، `return_service.py:82,130,148`، `refund_service.py:309`، `gateway_payment_service.py:272,281` (پرداخت مشکوک/مغایرت)، `coupon_redemption_service.py:80`، `catalog/views.py:530` (نظر جدید)، `customers/auth_service.py`, `account_security_service.py`. فرمان‌های Cron: `check_background_jobs`, `indexnow_sync`, `recheck_domains`, `process_subscription_dunning`. |
| ۳ | Inbox واقعی برای **مدیران** هست؟ | **خیر.** `Channel.IN_APP` و `read_at` در `NotificationOutbox` وجود دارد اما فقط `notify_security_event` یک ردیف می‌سازد و هیچ ویو/قالب/شمارنده‌ای آن را نمی‌خواند (`grep IN_APP` فقط مدل و سرویس). صفحهٔ `notification_history` تاریخچهٔ ارسال پیامک/ایمیل **مشتری** است نه صندوق مدیر. |
| ۴ | پیام‌ها در دیتابیس ذخیره می‌شوند؟ | بله، برای ارسال‌های SMS/Email در `NotificationOutbox` (PENDING/SENDING/SENT/FAILED/DEAD/SKIPPED، `dedupe_key` یکتا، `attempts`, `next_attempt_at`). برای مدیران: خیر. |
| ۵ | ارسال مرورگری؟ | **ندارد.** نه Service Worker، نه Web Push/VAPID، نه `pywebpush`، نه Notification API (جست‌وجوی `serviceworker|vapid|webpush|EventSource|WebSocket` فقط نتایج نامرتبط داد). |
| ۶ | Backend ایمیل؟ | Django SMTP/Console از env (`settings.py:568-576`، پیش‌فرض Console) + `notification_service._send_email` (قالب `notifications/email/base.html`) + تست `test_email_transport` (در Python 3.13 به‌خاطر `asyncore` import نمی‌شود؛ با 3.11 سبز). فقط برای مشتری/کارکنان از مسیر Outbox. |
| ۷ | صف، Retry، وضعیت تحویل، خطا؟ | **بله و قابل‌استفادهٔ مجدد:** `_claim_batch` (select_for_update skip_locked + بازپس‌گیری claim کهنه)، `BACKOFF_MINUTES=(1,5,30,120,360)`، `max_attempts`، `DEAD`، `sanitize_error` (ماسک موبایل/ایمیل)، `single_instance` lock (`apps/core/job_lock.py`)، Cron هر ۵ دقیقه (`deploy/cron/rastisi.crontab`)، پایش `check_background_jobs`. هیچ Celery/Redis Queue/Channels نیست (ADR-49: فقط Cron). |
| ۸ | ناقص/غیرفعال | صندوق مدیر، شمارندهٔ Header، Toast زنده، اعلان مرورگر، تنظیمات شخصی، محدودهٔ **پلتفرم** (Outbox فقط `store` دارد؛ `store=None` فقط برای امنیتی)، گیرنده‌یابی بر اساس Permission برای صندوق (فقط ایمیل کارکنان در `_staff_recipients`)، رویدادهای انبار/ایمپورت/دامنه/اشتراک/نقش/پلتفرم هیچ اعلانی ندارند. |
| ۹ | قابل استفادهٔ مجدد | الگوی Outbox/claim/backoff/sanitize، `single_instance`، Cron wrapper، `business_events` به‌عنوان **نقطهٔ اتصال یکتا**، `membership_has_permission` و `ROLE_PERMISSIONS`، `encrypt_credential` (Fernet) برای ذخیرهٔ Subscription، `record_audit_event`، الگوی Toast `HX-Trigger`/`@toast.window`، قراردادهای تست tenant (`PermissionEnforcementTestCase`). |
| ۱۰ | معماری پیشنهادی | زیر. |

## معماری انتخاب‌شده
`Domain Event (نقطهٔ اتصال موجود) → publish() [همان تراکنش] → Registry/Policy → Recipient Resolver (Store/Platform + Permission) → InboxItem (پایدار، به‌ازای گیرنده) + NotificationDelivery (Outbox کانال‌های بیرونی) → Worker (Cron + claim/backoff موجود) → Channel (WebPush / Email‑interface / Mobile‑interface)`.

* **همان اپ** `apps/notifications` گسترش یافت (مدل‌های جدید + Migration محلی `0004`)؛ `NotificationOutbox` برای SMS/ایمیل **مشتری/کارکنان** دست‌نخورده می‌ماند و Inbox جدید جایگزین آن نیست (دو مفهوم جدا: «ارتباط با مشتری» در برابر «صندوق مدیر»). دلیل: خطر صفر برای پیامک/ایمیل فعلی و مرز تمیز مخاطب.
* **رویداد از وضعیت هر گیرنده جدا است:** `NotificationEvent` (یک‌بار) ← `InboxItem` (خوانده/بایگانی/Snooze/سنجاق به‌ازای کاربر) ← `NotificationDelivery` (وضعیت هر کانال).
* **Realtime:** بدون Channels/Redis ⇒ **Polling کنترل‌شده** (فقط تب قابل‌مشاهده، backoff، `since_id`، Dedupe چندتبی با `BroadcastChannel`/`localStorage` کلیددار به کاربر).
* **Web Push:** بدون وابستگی جدید؛ VAPID با `cryptography` (موجود) و **Push بدون Payload** (محتوا را Service Worker با نشست خودش می‌گیرد ⇒ هیچ داده حساسی از Push Service عبور نمی‌کند). پیش‌فرض خاموش (`RASTISI_WEBPUSH_ENABLED=False`)، بدون کلید در Repo.
* **Email/Mobile:** فقط قرارداد کانال (`channels/base.py`)، Email با Locmem/Fake قابل‌تست، پیش‌فرض خاموش؛ ارسال واقعی در مأموریت بعدی.
* **سرکوب بار:** `publish` فقط برای رویدادهای ثبت‌شدهٔ معنادار؛ Dedupe یکتا روی `(scope, dedupe_key)`؛ گروه‌بندی با `group_key` (شمارنده به‌جای ردیف تکراری)؛ سیاست نگهداری/Prune.
