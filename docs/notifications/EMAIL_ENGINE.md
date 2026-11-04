# Unified SMS + Email Notification Engine — Phase 1 delivery

Branch `kiro/notifications-email-engine-20261104`, base `origin/main` @ `7d3115564569509f1da442fdc4aeacc9f855a81d`.
No financial-owned file is modified (verified by path audit, see report). Nothing was merged or deployed.

## 1. What already existed on `main` and was REUSED (not rebuilt)
Event registry (`events.py`), transactional outbox (`NotificationOutbox`, dedupe unique constraint, claim/lock, exponential
backoff, DEAD state, manual retry), per-store templates (`NotificationTemplate`), consent enforcement, business-event hooks
(`business_events.py`), legacy-SMS bridge, store UI (list/edit/preview/test/history/retry). This audit corrected an earlier
assumption that the engine lived only on `gemini-dev`.

## 2. NEW in this change
| Area | Component |
|---|---|
| Provider-independent transport | `mail/base.py`, `mail/fake.py` (deterministic, no network), `mail/ses.py` (SESv2 via boto3, lazy import), `mail/registry.py` |
| Sender identity (per Store, own domain only) | `EmailSenderIdentity`, `mail/provisioning_service.py`, `mail/dns.py` (authorized auto-DNS interface), `refresh_email_identities` command |
| Provider events | `EmailProviderEvent`, `EmailSuppression`, `mail/events_service.py`, `mail/sns.py` (SNS signature verification), `webhook_views.py` → `/notifications/email/ses-events/` |
| Template inheritance | `PlatformNotificationTemplate` (platform default, optional lock) → `NotificationTemplate` (store override) → render; `NotificationTemplateRevision` (versions + audit) |
| HTML email | `services/html_sanitizer.py` (allowlist), HTML body per template, unified `render_email_document` |
| Delivery policy | sender gate, hold/recovery/expiry, rate limits, suppression, permanent-vs-transient classification |
| Platform admin | catalog, platform defaults editor, preview, controlled test-send, sender oversight (enable/disable), delivery/failure/usage, audit; granular permissions |
| Store admin | sender identity page, channel switches, HTML editor, inheritance badge, revisions, locks |
| Parity | `parity.py` (computed matrix) + `test_sms_email_parity.py` |

## 3. Policy as implemented
* **Store email is sent ONLY from the Store's own provider-verified custom domain** (`info@<domain>`). There is no
  fallback sender: `notification_service._store_sender_address` returns `""` unless an `EmailSenderIdentity` is `ACTIVE`.
* **Website-domain verification and email-sender verification are separate facts.** `StoreDomain.verification_status`
  (TXT ownership), routing and TLS describe the storefront; `EmailSenderIdentity` (provider DKIM verification) describes
  sending. Neither implies the other; the Store panel shows both (`#two-verifications`).
* **ACTIVE only after the provider says so** (`VerifiedForSendingStatus` + DKIM `SUCCESS`). A transient provider blip does
  not demote an ACTIVE sender until 3 consecutive failures.
* **Automatic DNS** happens only through a configured `DnsProvisioner` that `controls_zone(domain)`. The result is
  recorded as `dns_auto_requested` ("requested", never "succeeded"); success is claimed solely when the provider verifies.
  The panel additionally shows a per-record DNS *observation* (`published`: seen / not seen / unknown). No provisioner is
  shipped enabled (see §7).
* **Blocked-mail policy** (sender inactive / rate limit): the row is HELD (`PENDING`, no retry attempt consumed, retried every
  15 min). Transactional/security mail waits `RASTISI_EMAIL_HOLD_MAX_HOURS` (72h) and then becomes a visible `DEAD` row
  (`…_expired`) — never silently dropped — which is manually retryable and **auto-revived** (within 7 days) the moment the
  sender becomes ACTIVE (`release_held`). Promotional mail expires after 24h as `SKIPPED` (visible) and is not revived.
* **Only email is blocked** when the sender is unavailable; SMS and the business flow are unaffected (tested).
* Platform→store-admin notices (`platform.email_sender_active/_problem`) use the platform's own sender
  (`DEFAULT_FROM_EMAIL`), because they must work precisely when the Store's domain is broken. They are locked for stores
  and never substitute for a Store→customer send.
* Security-category mail cannot be disabled by a store *or* the platform and keeps protected variables (`required_variables`).
* OTP: phone-possession proof is never emailed (see matrix).

## 4. Permissions
Platform (host-isolated): superuser = all. Team members (`is_staff`) need granular permissions on
`notifications.PlatformNotificationTemplate`: `view_notification_catalog`, `manage_platform_templates`,
`view_notification_delivery`, `manage_email_senders`, `send_notification_tests`. Authenticated-but-unauthorized → 403
(platform-specific 403 page). A team member can sign in to the platform host and lands on the notification catalog; every
other platform section still requires superuser.
Store: existing `SETTINGS_MANAGE`; SMS text of legacy events additionally needs `SMS_SETTINGS_MANAGE`.
Precedence: store override → platform default (unless `locked_for_stores`) → code default. Reset removes the override.

## 5. SMS ↔ email parity matrix (computed from code by `apps/notifications/parity.py`)
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
Every row with a notification event has an email definition (40/40); 38 also have an SMS. The only SMS events without an
email counterpart are the two phone-possession OTPs (`otp`, `platform_owner_otp`), by design: an emailed code proves access
to a mailbox, not to the phone. The repository has no email-login/registration flow that would need an email-scoped
verification; if one is added it must use its own token/purpose, never the phone OTP.
`notification` / `platform_test` are plumbing (the outbox email row *is* the email counterpart).
Tests: `test_sms_email_parity.py` (inventory completeness, trigger call-sites exist in source, every dispatch site is
listed, per-event email row creation, no-recipient → no row, Persian RTL/plain+HTML rendering, OTP never emailed).

## 6. Activation checklist (platform-only, cannot be done from the repository)
1. `pip install boto3` on the deployment (already in `requirements.txt`).
2. Environment: `RASTISI_EMAIL_PROVIDER=ses`, `RASTISI_SES_REGION`, credentials via env **or** instance/task role,
   optional `RASTISI_SES_CONFIGURATION_SET` with an SNS event destination (Bounce, Complaint, Delivery).
3. Create an SNS topic, subscribe `https://<platform host>/notifications/email/ses-events/` (HTTPS), put the topic ARN in
   `RASTISI_SES_SNS_TOPIC_ARNS` (the endpoint rejects everything else), then confirm the subscription.
4. Request SES production access (out of sandbox) and size `RASTISI_EMAIL_*_LIMIT`.
5. Schedule `manage.py refresh_email_identities` (hourly) and `process_notification_outbox`.
6. Optional: implement `DnsProvisioner` for a DNS host RastiSi is authorized on and set `RASTISI_EMAIL_DNS_PROVISIONER`.

## 7. Known limitations / not claimed
* **No live email was sent.** The SES adapter is tested only against a stub shaped like the boto3 `sesv2` client
  (`test_ses_adapter.py`) and the SNS verifier against locally generated keys; neither was run against a real AWS account.
* No real DNS-provider adapter is shipped; DNS is manual unless a provisioner is configured.
* Legacy SMS templates (`SmsTemplate`) are global across stores (pre-existing); the channel page shows them read-only.
* The platform test-send covers email only and requires a target Store (so the correct sender is used).
* Customer e-mail addresses are not verified in this codebase; mail goes to the address on file.
* Owner password-reset mail still uses the platform sender via Django mail (unchanged).
* `boto3`-based bounce handling relies on the SES→SNS→webhook path; Tenant attribution uses only our own outbox rows.

## 8. Coordination with Claude Code
See the PR description (migration-graph conflict with `integration/payment-engine-unified-20261104`, shared files).
