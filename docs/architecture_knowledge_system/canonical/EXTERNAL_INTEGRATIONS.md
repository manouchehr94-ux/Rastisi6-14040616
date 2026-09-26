# External Integrations

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (docs 04/05/07)
```

External services the platform talks to, their integration points, and configuration.

---

## Payments

### Storefront payments (`orders`)
- **Adapters:** `apps/orders/gateways/` — abstract `PaymentGatewayAdapter` (`base.py`); `registry.py`
  (`get_adapter`, lazy zibal/cod, cached); `zibal.py`, `cod.py`.
- **Providers:** **Zibal** (online redirect flow: `/v1/request` + `/v1/verify`, Toman→Rial ×10 inside
  the adapter only), **COD** (offline; attempt SUCCEEDED, order stays PENDING).
- **Config:** `orders.PaymentGatewayConfig` (per-store, encrypted credentials via
  `apps/orders/encryption.py`, Fernet, key `PAYMENT_CREDENTIAL_KEY`). Note dual model with legacy
  `orders.PaymentGateway` (M4 / DR-5).
- **Callback:** public `checkout/gateway/callback/<attempt_id>` → `process_callback_and_verify`.

### Platform (SaaS) billing payments (`billing`)
- **Providers:** `apps/billing/providers/` — `registry.get_provider`/`active_provider_code`/
  `webhook_secret`; `manual` (default, no auto-capture), `zibal`.
- **Webhook:** public `billing/webhook/<provider_code>/` → `webhook_service.ingest_webhook`
  (signature-verified, idempotent inbox, `RASTISI_BILLING_WEBHOOK_SECRET`).
- **Config:** platform Zibal creds live on `portal.PlatformConfiguration` (encrypted).

## SMS (`sms` + `portal`)
- **Backends** (`apps/sms/services/backends.py`): `ConsoleBackend` (dev), `MelipayamakBackend`
  (text + Pattern/BodyId), `KavenegarBackend` (VerifyLookup), `SmsRastiBackend` (enqueues
  `SmsOutboxItem` for an Android device gateway), `UnavailableBackend`.
- **Store SMS** funnels through `sms_service._dispatch` (credit reservation + logging). Backend
  selected by `ShopSettings.sms_backend` (only `SMSRASTI` uses the store's own; otherwise the
  platform provider via `portal.owner_sms_service`).
- **Platform/owner OTP** uses `portal.owner_sms_service` (creds on `PlatformConfiguration`;
  `RASTISI_OWNER_SMS_*` settings), independent of any Store.
- **Device gateway:** `sms/` poll (`smsrasti_poll`, GET, `?token`) + ack (`smsrasti_ack`, POST),
  csrf-exempt, device-token-authenticated.

## DNS / TLS (`stores`)
- `domain_verification_service` performs **real** DNS TXT lookups (`dnspython`) and **real** SSL
  socket connects for custom-domain ownership + routing + TLS readiness. A merchant can never
  self-mark a domain verified. Targets configured via `RASTISI_CUSTOM_DOMAIN_*` settings.

## Email (SMTP) (`portal`/`core`)
- Owner-portal transactional email (password reset today). `EMAIL_BACKEND` defaults to console
  (dev); production sets the real SMTP backend + `DJANGO_EMAIL_HOST*`. Never a fake success.

## Bot protection
- **Cloudflare Turnstile** on public account/contact forms (`TURNSTILE_*` settings;
  `portal.context_processors.turnstile`, `portal.services.turnstile_service`).

## Configuration surface (settings.py)
`PAYMENT_CREDENTIAL_KEY`, `PAYMENTS_SIMULATION_ENABLED`, `RASTISI_BILLING_PROVIDER`,
`RASTISI_BILLING_WEBHOOK_SECRET`, `RASTISI_BILLING_DUNNING_SCHEDULE`, `RASTISI_OWNER_SMS_*`,
`RASTISI_CUSTOM_DOMAIN_*`, `TURNSTILE_*`, `DJANGO_EMAIL_*`.

## Secrets policy (CURRENT CODE REALITY)
Gateway/SMS credentials are encrypted at rest (`orders.encryption` Fernet) or come only from the
environment / `PlatformConfiguration`; never logged in full. `PAYMENT_CREDENTIAL_KEY` missing in
production → startup failure (fail-closed).

Graph: [`../phase1_code_discovery/graphs/system_context.mmd`](../phase1_code_discovery/graphs/system_context.mmd).
