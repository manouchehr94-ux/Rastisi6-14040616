# Unified SMS + Email Notification Engine — implementation report

PR #37, branch `kiro/notifications-email-engine-20261104`, base `origin/main` @ `7d3115564569509f1da442fdc4aeacc9f855a81d`.
**Not merged, not deployed. No email has been sent through a real provider.** Companion documents:
[ACTIVATION_CHECKLIST.md](ACTIVATION_CHECKLIST.md) (what is missing for production) and
[MIGRATION_INTEGRATION.md](MIGRATION_INTEGRATION.md) (collision with the payment-engine branch).

## 0. How to read the status words
| word | meaning |
|---|---|
| **IMPLEMENTED** | the code path exists |
| **TESTED** | automated tests exercise it — the *kind* of test is always named (unit / fake provider / botocore service-model stub / merged-tree rehearsal) |
| **LIVE-VERIFIED** | proven against a real external system (AWS, a real DNS server, a real mailbox). **Nothing in this PR is live-verified.** |

## 1. Reused vs new
Reused from `main` (not rebuilt): event registry, transactional outbox (dedupe constraint, claim/lock, exponential backoff, DEAD
state, manual retry), per-store templates, consent enforcement, business-event hooks, the legacy-SMS bridge and the store
list/edit/preview/test/history UI. New: provider-independent mail transport (fake + SES v2), per-store sender identity, DNS
automation contract, SNS/SES event ingestion + suppression, platform default templates + revisions, HTML email with an allowlist
sanitizer, **tenant-specific SMS overrides**, **expiry/validity policy**, platform + store admin pages with granular permissions.

## 2. Mandatory own-domain sender policy
* Store email is sent **only** from `info@<the store's own custom domain>` and only while the provider reports that identity
  verified. There is no shared-domain fallback anywhere (`notification_service._store_sender_address`).
* **Website-domain verification and email-sender verification are separate facts** (TXT ownership/routing/TLS vs. DKIM at the
  email provider). The panel shows both (`#two-verifications`); neither implies the other.
* `platform.email_sender_*` notices are RastiSi's own message *to* the store admin and use the platform sender, so they work exactly
  when the store's domain is broken. They are locked for stores and never substitute for a store→customer send.
* If the sender is not ACTIVE: **only email is held**; SMS and the business operation are unaffected.

## 3. Store-level SMS **and** email template management (gap 1)
Authorized store admins can now edit **both** channels for every event except the deliberately platform-managed ones.
Resolution order for any channel: **store override → platform default → code default** (`template_service.get_template`).

| aspect | behaviour |
|---|---|
| Where a store's SMS text lives | `NotificationTemplate(store, event_key, channel="sms")` — **never** the global `SmsTemplate` |
| Platform default | the global `SmsTemplate` (text, provider Pattern ids, platform switch) — unchanged, still edited in the platform SMS pages |
| Platform kill-switch | global `SmsTemplate.is_active=False` switches the event off for **everyone**; a store override cannot switch it back on |
| Store switch | per store (`is_enabled` on the override); other stores unaffected |
| Provider behaviour | **default text** → exactly as before (incl. Melipayamak Pattern/BodyId). **Customized text** → plain-text send (an approved Pattern no longer matches custom wording); credit reservation, refund-on-failure, `SmsLog`, history mirror, SmsRasti queue all unchanged |
| Validation | the same strict legacy renderer (`{ }` rules, allowed variables only, no attribute/index access) + ≤1000 chars + no NUL/CR; an unrenderable stored row falls back to the platform text instead of blocking the SMS |
| Permissions | legacy SMS events require the existing `SMS_SETTINGS_MANAGE`; a forged "seen" field on the channels page is ignored and counted as an error |
| Not overridable (by design) | OTP (`otp`, `platform_owner_otp`: no `EventDef`, lookup short-circuits), platform-managed campaign/occasion SMS (`PlatformManagedError`), `platform.*` notices, security events cannot be switched off |
| Auditing | every save/reset writes a `NotificationTemplateRevision` (version, actor) |

TESTED: `test_store_sms_overrides.py` (23 tests: tenant isolation, kill-switch bound, Pattern vs plain, billing/credit, SmsRasti queue,
history mirror, broken-row fallback, permission, forged fields, revisions) + the rewritten legacy suite (`test_legacy_sms_integration.py`, 23)
+ all of `apps.sms` (163) unchanged. LIVE-VERIFIED: no (no real SMS provider was contacted).

## 4. DNS: audit result and automation (gap 2)
**Audit of RastiSi's real domain-management architecture** (code, settings, `deploy/`, docs, and the payment-engine branch):
* A merchant custom domain is *bring-your-own*: the merchant owns the registrar/DNS account. RastiSi only **reads** DNS
  (`dnspython` TXT/A/CNAME lookups in `domain_verification_service`) and tells the merchant what to add.
* There is **no DNS-write integration, credential, API token or delegated zone anywhere** (no Cloudflare/ArvanCloud/Route 53/…
  client, no TSIG key, no setting). The payment-engine branch's domain wizard (`advance_domain_connection`) is also read-only
  and reports `routing_unconfigured` when even the A/CNAME targets are undeclared.
* Conclusion: **automatic record creation is impossible for every merchant domain today.** Nothing was invented.

What is implemented (`mail/dns.py`): a conservative contract that activates **only** where the platform owner has granted authority:
RFC 2136 dynamic update with a TSIG key against a nameserver authoritative for zones explicitly listed in
`RASTISI_EMAIL_DNS_ZONES`, or a custom `DnsProvisioner` class. Safety rules (all tested):
only `CNAME <token>._domainkey.<domain> → *.dkim.amazonses.com`; identical existing record = no-op; a *different* CNAME or any other
record type at that name = reported **conflict, nothing written**; a batch with one forbidden record writes nothing; the server's
acceptance is recorded as **`requested`, never "succeeded"** (ACTIVE requires the email provider's verification); secrets never appear
in stored details.
When automation is not possible the panel shows the **exact blocking reason in Persian** (`no_integration`, `zone_not_authorized`,
`record_conflict`, `dns_server_error`, …), the actionable instruction, five manual steps, the exact provider-generated records
(type / full name / relative name / value) and a per-record "seen in DNS" observation.
TESTED: `test_dns_provisioning.py` (28) with an in-memory authoritative server (no network). LIVE-VERIFIED: no.

## 5. Delivery validity: expiry, hold, recovery (gap 3)
Rules checked immediately before **every** send (worker, manual retry, revival) by `services/expiry.py`:
1. **Hard TTL** per event. Past it the row becomes `EXPIRED` — kept, listed in history and the platform "needs attention" filter,
   **never retried or revived**.
2. **Contextual validity** (read-only checks of current order/coupon/sender state). A message whose premise no longer holds is not sent
   and kept as `SKIPPED` with `stale:<reason>` — e.g. "payment failed" after the order was paid, "processing" after it shipped,
   "shipped" after cancellation, a coupon notice after the code expired / was deactivated / used up.
3. **Hold window** (sender inactive / rate limit): the row waits without consuming retries; after the window, transactional/security
   rows become a visible failed (`DEAD`) row an operator can retry, and are auto-revived when the sender recovers — **only while still valid**.
   Promotional rows are never revived.
* **OTPs are not part of this engine** (they use the dedicated OTP path with its own few-minute validity). Tests assert no event
  carries a code/token/reset-link variable and that OTP never enters the device queue even for stores using the phone gateway.
* The SmsRasti phone-gateway queue previously had no age limit (a phone offline for days would send stale texts). It now fails items
  older than `RASTISI_SMSRASTI_QUEUE_TTL_HOURS` (72) with an explicit reason.
* The cron health check no longer mistakes held mail for a dead cron (false CRITICAL) and now reports held mail, expired transactional
  rows, sender errors and a missing revalidation job separately.
* Validators only **read** `Order.status` / `Order.payment_status` / `Coupon`; they never write, and call no payment/refund logic.

| رویداد | دسته | مهلتِ اعتبار (TTL) | مهلتِ نگه‌داری (hold) | شرطِ اعتبارِ بافتاری |
|---|---|---|---|---|
| `account.registered` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `account.sensitive_changed` | امنیتی | 48 ساعت | 24 ساعت | — |
| `order.created` | تراکنشی | 168 ساعت | 72 ساعت | سفارش لغو نشده باشد |
| `payment.succeeded` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `payment.failed` | تراکنشی | 72 ساعت | 72 ساعت | پرداخت هنوز تعیین‌تکلیف نشده و سفارش لغو نشده باشد |
| `order.processing` | تراکنشی | 72 ساعت | 72 ساعت | سفارش هنوز «در حال پردازش» باشد |
| `order.shipped` | تراکنشی | 168 ساعت | 72 ساعت | سفارش لغو/تحویل نشده باشد |
| `order.delivered` | تراکنشی | 168 ساعت | 72 ساعت | سفارش لغو نشده باشد |
| `order.canceled` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `return.requested` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `return.approved` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `return.rejected` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `refund.completed` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `coupon.issued` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `coupon.expiring` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `coupon.redeemed` | تراکنشی | 72 ساعت | 72 ساعت | — |
| `campaign.activated` | تراکنشی | 72 ساعت | 72 ساعت | — |
| `reward.issued` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday_before` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday_after` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday_before_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.birthday_after_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic_before` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic_after` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic_before_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `occasion.generic_after_greeting` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `campaign.offer_percent` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `campaign.offer_fixed` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `campaign.offer_free_ship` | تبلیغاتی | 24 ساعت | 24 ساعت | کد تخفیف فعال، منقضی‌نشده و دارای سقفِ باقی‌مانده باشد |
| `campaign.announce` | تبلیغاتی | 24 ساعت | 24 ساعت | — |
| `staff.order_created` | تراکنشی | 72 ساعت | 72 ساعت | — |
| `staff.return_requested` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `staff.review_created` | تراکنشی | 72 ساعت | 72 ساعت | — |
| `staff.late_payment` | تراکنشی | 168 ساعت | 72 ساعت | — |
| `platform.email_sender_active` | تراکنشی | 72 ساعت | 72 ساعت | فرستنده‌ی ایمیل هنوز فعال باشد |
| `platform.email_sender_problem` | تراکنشی | 72 ساعت | 72 ساعت | مشکلِ فرستنده هنوز برطرف نشده باشد |

TESTED: `test_expiry.py` (34). LIVE-VERIFIED: n/a (pure application policy).

## 6. SMS ↔ email parity matrix (computed from code)
The matrix is produced by `apps/notifications/parity.py` from the registries and verified against the real trigger call sites
(a removed/renamed trigger, or a new unlisted dispatch site, fails the build).

| رویداد (شناسه) | عنوان | دسته | مخاطب | پیامک (منبع) | ایمیل | فرستنده | محرک (فایل) |
|---|---|---|---|---|---|---|---|
| `account.registered` | ثبت‌نام و خوش‌آمدگویی | transactional | customer | welcome (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/customers/services/auth_service.py` |
| `account.sensitive_changed` | تغییر اطلاعات حساس حساب | security | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/customers/views.py` |
| `order.created` | ثبت سفارش | transactional | customer | order_placed (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/orders/services/order_service.py` |
| `payment.succeeded` | پرداخت موفق | transactional | customer | payment_success (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/orders/services/lifecycle.py` |
| `payment.failed` | پرداخت ناموفق | transactional | customer | payment_failed (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/orders/services/payment_service.py` |
| `order.processing` | سفارش در حال پردازش | transactional | customer | order_processing (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `order.shipped` | ارسال سفارش و کد رهگیری | transactional | customer | order_shipped (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `order.delivered` | تحویل سفارش | transactional | customer | order_delivered (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `order.canceled` | لغو سفارش | transactional | customer | order_canceled (قدیمی (apps.sms / SmsTemplate)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `return.requested` | ثبت درخواست مرجوعی | transactional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/return_service.py` |
| `return.approved` | تأیید مرجوعی | transactional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/return_service.py` |
| `return.rejected` | رد مرجوعی | transactional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/return_service.py` |
| `refund.completed` | تکمیل استرداد وجه | transactional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/refund_service.py` |
| `coupon.issued` | صدور کد تخفیف اختصاصی | promotional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `coupon.expiring` | یادآوری نزدیک‌شدن انقضای کد | promotional | customer | camp_expiry_reminder (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `coupon.redeemed` | استفاده موفق از کد تخفیف | transactional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/coupon_redemption_service.py` |
| `campaign.activated` | فعال‌شدن کمپین (اعلان داخلی) | transactional | staff | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `reward.issued` | اعطای پاداش به مشتری | promotional | customer | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday_before` | تولد · پیش از روز تولد (با هدیه) | promotional | customer | occ_birthday_before (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday` | تولد · روز تولد (با هدیه) | promotional | customer | occ_birthday_on (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday_after` | تولد · پس از روز تولد (با هدیه) | promotional | customer | occ_birthday_after (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday_before_greeting` | تولد · پیش از روز تولد (فقط تبریک) | promotional | customer | occ_birthday_before_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday_greeting` | تولد · روز تولد (فقط تبریک) | promotional | customer | occ_birthday_on_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.birthday_after_greeting` | تولد · پس از روز تولد (فقط تبریک) | promotional | customer | occ_birthday_after_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic_before` | سایر مناسبت‌ها · پیش از مناسبت (با هدیه) | promotional | customer | occ_generic_before (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic` | سایر مناسبت‌ها · روز مناسبت (با هدیه) | promotional | customer | occ_generic_on (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic_after` | سایر مناسبت‌ها · پس از مناسبت (با هدیه) | promotional | customer | occ_generic_after (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic_before_greeting` | سایر مناسبت‌ها · پیش از مناسبت (فقط تبریک) | promotional | customer | occ_generic_before_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic_greeting` | سایر مناسبت‌ها · روز مناسبت (فقط تبریک) | promotional | customer | occ_generic_on_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `occasion.generic_after_greeting` | سایر مناسبت‌ها · پس از مناسبت (فقط تبریک) | promotional | customer | occ_generic_after_nogift (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `campaign.offer_percent` | کمپین تخفیف · تخفیف درصدی | promotional | customer | camp_offer_percent (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `campaign.offer_fixed` | کمپین تخفیف · تخفیف مبلغی | promotional | customer | camp_offer_fixed (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `campaign.offer_free_ship` | کمپین تخفیف · ارسال رایگان | promotional | customer | camp_offer_free_ship (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `campaign.announce` | کمپین تخفیف · اطلاع‌رسانی بدون کد | promotional | customer | camp_announce (پلتفرم‌محور (SmsTemplate سراسری)) | ✔ | store | `apps/engagement/services/campaign_service.py` |
| `staff.order_created` | سفارش جدید (اعلان به کارکنان) | transactional | staff | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `staff.return_requested` | درخواست مرجوعی جدید (اعلان به کارکنان) | transactional | staff | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/notifications/services/business_events.py` |
| `staff.review_created` | نظر جدید محصول (اعلان به کارکنان) | transactional | staff | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/catalog/views.py` |
| `staff.late_payment` | پرداخت/مغایرتِ نیازمندِ رسیدگی (اعلان به کارکنان) | transactional | staff | ✔ موتور اعلان (outbox) (موتور اعلان (outbox)) | ✔ | store | `apps/orders/services/gateway_payment_service.py` |
| `platform.email_sender_active` | فعال‌شدن ایمیلِ فروشگاه (اعلانِ پلتفرم) | transactional | staff | — (—) | ✔ | platform | `apps/notifications/mail/provisioning_service.py` |
| `platform.email_sender_problem` | مشکل در ایمیلِ فروشگاه (اعلانِ پلتفرم) | transactional | staff | — (—) | ✔ | platform | `apps/notifications/mail/provisioning_service.py` |
| — | OTP ثبت‌نام / ورود مالک فروشگاه (`platform_owner_otp`) | otp | — | قدیمی (apps.sms) | ✘ (عمدی) | — | — |
| — | تست زیرساخت پیامک (`platform_test`) | infra | — | قدیمی (apps.sms) | ✘ (عمدی) | — | — |
| — | اعلان عمومی / امنیتی (`notification`) | infra | — | قدیمی (apps.sms) | ✘ (عمدی) | — | — |
| — | کد ورود یکبار مصرف (`otp`) | otp | — | قدیمی (apps.sms) | ✘ (عمدی) | — | — |

40/40 notification events define an email; 38 also define an SMS. The only SMS events with no email counterpart are the two
**phone-possession OTPs** (`otp`, `platform_owner_otp`), deliberately: an emailed code proves access to a mailbox, not to the phone.
`notification`/`platform_test` are plumbing. The payment-engine branch adds one more *trigger* for an existing event
(`account_security_service` → `account.sensitive_changed`, password change); its SMS-verified password *set* still uses the phone OTP path.

## 7. Known limitations (unchanged or newly discovered)
* No real provider/DNS/mailbox was contacted. See the checklist.
* A custom domain is required for email; a store without one has no email channel (SMS is unaffected). Mail-From (SPF alignment) is
  not customized; DMARC alignment relies on DKIM signed by the merchant's own domain. The merchant's own DMARC/SPF records are not managed.
* Customer e-mail addresses are not verified in this codebase (mail goes to the address on file).
* Customized store SMS texts bypass provider Patterns (plain send) — a product consequence, not a bug.
* The webhook is served on `RASTISI_PLATFORM_HOSTS` only. (An earlier version of this document pointed at the wrong host; the routing is
  now fixed and covered by `test_endpoint_is_served_on_the_platform_host_only`.)
