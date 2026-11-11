# Privacy policy — draft, evidence and open decisions — 2026-11-06

**Status: DRAFT. Not legal advice. Not approved.** The text lives in `apps/portal/templates/portal/public/_privacy_{body,toc,notice}.html` (one source for the new and the legacy public design).
Until the platform owner switches on **Platform Admin → public site → "متن حریم خصوصی تأیید حقوقی و تجاری شده است" (`privacy.approved`)** the page shows a visible draft notice, is `noindex`, and is left out of
`sitemap.xml`. Do not switch it on before every *needs-confirm* marker is resolved and a lawyer has reviewed the text.

## What the draft claims, and where each fact comes from
| Statement in the draft | Evidence in the code |
|---|---|
| Owner account holds name, phone, optional email; password stored hashed | `apps/portal/models.py` `OwnerProfile(full_name, phone)`; Django auth user |
| Customers: name, phone, email, city, optional birth date; addresses (receiver, phone, province, city, postal code, full address) | `apps/customers/models.py` `Customer`, `Address` |
| Manual card-to-card payment keeps reference, transfer time, **last 4 digits** of the payer card, receipt image | `apps/billing/models.py` `PlatformManualPaymentClaim` (`payer_card_last4`, `receipt`, `receipt_sha256`) |
| Browser-notification subscription: hashed endpoint, device label, truncated user agent (120), timestamps | `apps/notifications/models.py` `WebPushSubscription` |
| Audit records deliberately keep **no IP / user agent** | docstring of the audit event model in `apps/core/models.py` (ADR-36: no approved retention policy exists for IP/UA) |
| Server-side math CAPTCHA on public account/contact forms (replaced Cloudflare Turnstile on 2026-11-11): the question is stored in the platform's own rate-limit cache bound to the session; no data goes to a third party | `apps/portal/services/captcha_service.py`, `RASTISI_CAPTCHA_*` |
| SMS providers Melipayamak, Kavenegar; SMTP email | `apps/sms`, `apps/notifications`, `shop_core/settings.py` (provider names only — *which are live is unknown*) |
| Payment gateways are redirects; card data is entered at the gateway | `apps/billing/providers`, `apps/orders/gateways` (redirect adapters) |
| Gateway credentials stored encrypted | `apps/orders/tests/test_payment_security.py` (credentials stored encrypted, never plaintext) |
| Per-store data isolation; role/permission-based panel access | tenant-isolation tests (`apps/customers/tests/test_account_store_isolation.py`, `apps/orders/tests/test_tenant_isolation_regression.py`) |
| OTP valid 2 minutes | `OTP_TTL_SECONDS = 120` (`owner_otp_service`, `sms/otp_service`) |
| Import files kept 30 days | `IMPORT_FILE_RETENTION_DAYS = 30` (`dashboard/services/import_service.py`) |
| Persistent session 30 days; otherwise until browser close | `AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS` / `..._DEFAULT_EXPIRY_SECONDS=0` |
| Consent cookie `rs_consent`, 180 days; analytics/marketing opt-in, default off; RastiSi sets no tracking cookie itself | `apps/core/consent.py` |
| Analytics/ads are store-level (GA4, GTM, Meta pixel) | `apps/core/consent.py`, integrations settings |
| OTP and login are rate-limited; forms bot-protected; sensitive actions audited | `owner_registration_hardening` tests, rate limiter, audit service |

Test `PrivacyTextContractTests.test_every_numeric_retention_fact_is_one_that_exists_in_code` fails if a number in the text stops matching the code.

## What the draft deliberately does NOT say (owner must decide)
1. **Legal entity**: registered name, registration numbers, address, official contact, privacy officer.
2. **Retention** of accounts, stores, orders, invoices, receipts, SMS logs, server logs and backups — the code has **no purge job** apart from import files, so any number would be invented.
3. **Account / store deletion and data export**: no self-service deletion or export flow was found in the code. How requests are received, verified, answered and within what time is a business decision.
4. **Hosting, processing location, cross-border transfer**, backup location and backup encryption.
5. **Which third parties are actually live**: payment gateways (the code supports more than are likely enabled — Zibal, Zarinpal, Pasargad, Saman, Mellat, SnappPay, TorobPay, Parsian, Sadad, Tejarat), SMS providers, the email provider.
6. **Server/access logs**: what is logged (IP?) and for how long. (The audit model avoids IP/UA by design; web-server and gateway logs are outside the code.)
7. **Cookies in production** (the session cookie also carries the CAPTCHA binding; no third-party widget cookie remains).
8. **Production cookie flags** (`DJANGO_SESSION_COOKIE_SECURE`, `DJANGO_CSRF_COOKIE_SECURE` default on only when `DEBUG` is off).
9. **Roles**: whether RastiSi is a "controller" or "processor" of store-customer data, and what merchants must tell their own customers.
10. **Children**: the policy position and age limit.
11. **Change notification** method and the official version/date to print.
12. **Applicable law.** Iranian e-commerce / personal-data rules and whether any EU/other regime applies to the actual operations is a legal question; the draft makes no compliance claim (no GDPR, ISO, PCI or similar statement).

## Release gate
Resolve items 1–12 → lawyer review → owner switches `privacy.approved` on. Until then the page must stay a draft and must not be presented as an approved policy.
