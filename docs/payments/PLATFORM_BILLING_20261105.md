# Platform Owner Payment Gateway & SaaS Billing Integration (2026-11-05)

Branch `financial/platform-billing-20261105`, based on the verified integration reference
`0f95379af3e4364113003885d249f295dd3b9437` (= unified payment engine PR #36 line + Kiro Messaging/Notifications UX).
Draft only — **not merged, not deployed, no migration applied to any persistent database.**

Two financial contexts that must never mix:

| | Store payments | **Platform payments (this work)** |
|---|---|---|
| Payer → payee | shopper → one store | store owner → RastiSi |
| Credentials | `orders.PaymentGatewayConfig` (per store) | `portal.PlatformGatewayConfig` (+ legacy Zibal fields in `PlatformConfiguration`) |
| Attempt model | `orders.PaymentAttempt` | `billing.SubscriptionPaymentAttempt`, `sms.SmsPackagePaymentAttempt` |
| Engine | `orders.services.gateway_payment_service` | `billing.services.*` (reusing the verified `orders.gateways` adapters) |

---

## 1. Technical audit (what existed before this change)

### Already implemented and reused as-is
| Area | Where | Verdict |
|---|---|---|
| Subscription invoices, lines, numbering, credit notes, refunds, dunning, renewals, plan changes | `apps/billing` (models, `services/*`) | Complete and well tested — reused unchanged. |
| Subscription payment attempts, idempotent `confirm_payment` (locks attempt+invoice, amount/currency check, activate/renew/plan-change, audit) | `billing.services.confirmation_service` | Reused; one gap fixed (duplicate payment, §3.4). |
| Platform-only Zibal provider reading `PlatformConfiguration` (never store credentials), Toman→Rial at one boundary, server-to-server verify | `billing.providers.zibal` | Reused; credential source generalised. |
| Provider-neutral interface + registry, manual provider | `billing.providers.*` | Extended (`verify_attempt`, `callback_claims_failure`). |
| Platform admin: invoices list/detail, manual payment, Zibal settings page | `portal.platform_admin_views` | Kept; legacy page now delegates to the new service. |
| Superuser-only platform-admin host isolation, `PlatformAuditLogEntry`, Fernet credential encryption | `portal`, `orders.encryption` | Reused. |
| Merchant dashboard billing (overview, invoices, pay, cancel) and owner-portal plan purchase with OTP step-up | `dashboard`, `portal` | Reused; checkout wiring fixed (§2). |
| Verified gateway adapters with `CREATE`/`VERIFY` | `orders.gateways.{zibal,zarinpal}` | Reused through a bridge (`AdapterBackedBillingProvider`). |

### Defects / gaps found (all fixed here)
1. **The owner-portal subscription purchase never reached the gateway.** `portal.views._start_purchase` created the attempt and the provider session, then redirected to an internal status page instead of `session.redirect_url`. With a real provider the owner could never pay. Its `return_url` was also the plans page, not a verify endpoint.
2. **No callback endpoint.** Verification only ran in an authenticated dashboard view that depended on `request.session["billing_last_attempt"]`; the portal path never verified at all. Zibal has no webhook, so *nothing* could confirm a payment from the portal flow.
3. **The owner-portal host URLconf (`urls_platform`) did not include `billing/`.** Any gateway callback to the canonical platform host would have 404'd.
4. **SMS credit packages were manual-only.** `request_purchase` created a `pending` row; a superuser completed it in Django admin. No payment attempt, no ledger.
5. **`balance_service.complete_purchase` was racy**: it read the balance without a lock and wrote `credits = old + n`, losing concurrent deductions; it also left no credit-ledger row (only manual adjustments were recorded).
6. A provider failure during `start_payment` raised an unhandled `BillingProviderError` (HTTP 500) and rolled back the attempt.
7. A second successful payment against an already-paid invoice returned silently, leaving that attempt `pending` — money received with no trace.
8. Only Zibal (hard-wired to `PlatformConfiguration` fields) existed; no gateway selection, enable/disable, readiness, transactions or reconciliation views.

### Missing (now added)
Platform gateway registry/readiness/audit, adapter-backed Zarinpal, public callback, reconcile job, SMS online payment + immutable credit ledger + refund, Platform Admin UI (gateways, transactions, reconciliation, SMS purchases).

---

## 2. Design

### 2.1 Platform gateway management — `apps/portal/services/platform_gateway_service.py`
* **Eligibility is derived from the evidence matrix** (`platform_gateway_matrix.py`; see `PLATFORM_PROVIDER_MATRIX_20261105.md`): *approved* (Zibal, Zarinpal, Pasargad, platform card-to-card), *gated* (SnappPay, TorobPay, Saman, Mellat — implemented and mock-tested, **live use blocked until the owner records the readiness gates**), *not_implemented* (Parsian, Sadad, Tejarat). COD and the stores' own card-to-card are **not platform methods** and are refused everywhere (even by a forged POST).
* **State model:** *enabled* = owner's permission; *configured* = adapter credential validation passes; **ready = enabled ∧ configured ∧ eligible**. Only ready gateways reach checkout. Enabling an incomplete gateway is rejected with an actionable message.
* **Storage:** `portal.PlatformGatewayConfig` (no `store` column; Fernet-encrypted JSON; secrets are write-only — blank = unchanged — and never rendered, logged or audited; audit records only booleans).
* **Legacy compatibility:** existing QA data holds Zibal credentials in `PlatformConfiguration`. With no row present they are read through (`source="legacy"`); the first save through the new UI keeps the legacy merchant and mirrors writes back to the legacy fields so the previous code path still works (rollback-safe).
* **Default:** `PlatformConfiguration.default_payment_provider`; reassigned automatically (and audited) if that gateway stops being ready.
* **Callback origin:** `callback_base_url(request)` is always the canonical platform host (`RASTISI_PLATFORM_PRIMARY_HOST`, overridable by `RASTISI_BILLING_CALLBACK_BASE_URL`) — the domain registered with the gateway merchant — never a store/admin host.

### 2.2 Credential isolation (hard rules, enforced by tests)
* `apps/billing/**` and the platform gateway service never reference `PaymentGatewayConfig` (AST test).
* `apps/orders/**` never references `PlatformGatewayConfig`, `platform_gateway_service`, `credentials_and_mode` or `get_zibal_credentials` (AST test).
* Runtime tests: with store Zibal/Zarinpal configs present, every platform request carries only the platform merchant; every platform operation leaves store gateway rows byte-identical and does not change a store's checkout methods.

### 2.3 Explicit platform billing context
Rather than overloading `orders.PaymentAttempt` (tied to an `Order`), each platform product has its own attempt model with server-side amount/currency:
* `SubscriptionPaymentAttempt` ↔ `SubscriptionInvoice` (existing; + `return_to`).
* **new** `SmsPackagePaymentAttempt` ↔ `SmsPackagePurchase` (amount = server-side snapshot of the package price; `public_token` prefixed `sms_`).
* **new** `SmsCreditLedger`: immutable credit trail (`purchase` / `purchase_reversal`) with before/after balances, actor, purchase and attempt links, and `UNIQUE(purchase, kind)` — a **database-level** guarantee that credit is added once and reversed once.

### 2.4 Flow
```
owner → checkout (portal or dashboard) ── start_payment ──► attempt(PENDING) + gateway session (platform credentials)
      ──► gateway ──► GET/POST  https://<platform host>/billing/return/<attempt token>/
                       │  token only identifies OUR attempt; query params are hints, never proof
                       ├─ throttle (1 verify / 8 s / attempt), skip if attempt already final
                       ├─ provider.verify_attempt()  (server-to-server; Zibal also cross-checks orderId)
                       ├─ confirm (locks attempt→invoice|purchase→balance; amount+currency check; exactly-once effect)
                       └─ 302 → return_to?payment=ok|failed|action|pending   (relative path or ALLOWED_HOSTS-validated URL)
```
`reconcile_platform_payments` (cron, every ~10 min) re-verifies stale `created/pending` attempts — for users who never return.

Outcomes: verified+matching ⇒ fulfilled once · verified but amount/orderId mismatch ⇒ `requires_action` (no effect) · verify says unpaid and the return claims failure ⇒ `failed` (still recoverable by a later verified payment) · unpaid/unknown ⇒ stays `pending` (never failed by the job) · money for a cancelled/completed/refunded SMS purchase or an already-paid invoice ⇒ `requires_action` + audit (no second effect).

### 2.5 Refunds and cancellations
* Subscription refunds: existing `refund_service` (provider `refund_payment`; Zibal/Zarinpal expose no documented refund API ⇒ honest `pending` manual refund).
* **SMS refund** (`refund_purchase`): reverses the *whole* purchased credit once (ledger `purchase_reversal`, purchase → `refunded`), then asks the provider for a refund (manual-pending for the supported gateways). If any of the purchased credit was already consumed it **refuses** (see §7 – needs an owner policy decision). Cancel: only `pending` purchases; a payment that arrives later is flagged for reconciliation, not credited.

---

## 3. What changed (files)
New: `portal.PlatformGatewayConfig`; `portal/services/platform_gateway_service.py`; `billing/providers/adapter_backed.py`; `billing/services/sms_purchase_payment_service.py`; `billing/management/commands/reconcile_platform_payments.py`; `billing/templates/billing/payment_return.html`; Platform Admin pages `payment_gateways`, `payment_transactions`, `payment_reconciliation`, `sms_purchases`; `sms.SmsPackagePaymentAttempt`, `sms.SmsCreditLedger`.
Modified: `billing/views.py` (+`payment_return`), `billing/urls.py`, `billing/services/payment_flow_service.py` (central callback, safe failure handling, shared `verify_and_confirm`, `safe_return_to`), `confirmation_service.py` (duplicate payment flag), `providers/{base,zibal,registry}.py`, `sms/services/balance_service.py` (locked + ledgered `complete_purchase`, `reverse_purchase_credits`), `portal/views.py` (checkout redirects to the gateway; gateway choice; `billing_return_latest`), `dashboard/views.py` + templates (invoice pay, SMS purchase/pay), `shop_core/urls_platform.py` (`billing/` on the platform host), platform-admin nav.

## 4. Migrations and safe upgrade
All nine are reversible; only `portal.0018` touches data (idempotent, audited, no deletion). The first three shipped in the original PR #40 commit; the next three in the provider-coverage pass; the last three in the five-methods pass (new files, existing migrations untouched).

| Migration | Content |
|---|---|
| `portal.0015_platform_gateway_config` | create `PlatformGatewayConfig`; drop static `choices` on `PlatformConfiguration.default_payment_provider` (no DB change) |
| `billing.0008_attempt_return_to` | add `SubscriptionPaymentAttempt.return_to` (default `""`) |
| `sms.0010_sms_purchase_payments_and_ledger` | add `SmsPackagePurchase.refunded_at` + `refunded` status; create `SmsPackagePaymentAttempt`, `SmsCreditLedger` (+ indexes/constraints) |
| `portal.0016_platform_gateway_last_test` | add `last_test_at`, `last_test_ok`, `last_test_message` to `PlatformGatewayConfig` (nullable/blank) |
| `billing.0009_attempt_provider_extra` | add `SubscriptionPaymentAttempt.provider_extra` JSON (default `{}`) — server-side session data such as Pasargad `urlId` |
| `sms.0011_attempt_provider_extra` | add `SmsPackagePaymentAttempt.provider_extra` JSON (default `{}`) |
| `portal.0017_platform_gateway_gates` | add `PlatformGatewayConfig.purchase_types` (JSON, nullable) and `attestations` (JSON, default `{}`) — readiness gates |
| `portal.0018_platform_cod_removal` | **data migration**: remove `cod`/`card_to_card` from legacy platform configuration (default `cod` → `manual`), disable (keep) stray gateway rows, audit each change; idempotent; reverse = no-op (history stays in the audit log) |
| `billing.0010_platform_manual_payment_claims` | create `PlatformManualPaymentClaim` + append-only `PlatformManualPaymentClaimEvent` with DB constraints (one active claim per reference, exactly one target, positive amount, one pending claim per target) |

Upgrade (per environment, **after** owner approval — nothing has been applied by this work):
1. Back up the database. 2. Deploy code. 3. `python manage.py migrate portal billing sms` (applies `portal.0018`, which neutralises any stale COD reference; review the platform audit log afterwards). 4. `python manage.py makemigrations --check` (expect "No changes"). 5. Open Platform Admin → *درگاه‌های پرداختِ پلتفرم*. If Zibal was already configured it appears as `legacy` and **ready** with the same behaviour as before; press *Save* once to move it to the new store (the legacy fields stay mirrored). 6. Schedule `python manage.py reconcile_platform_payments` every **5 minutes** (Pasargad's verify deadline is 25 minutes; it also recovers verified-but-unsettled BNPL/Mellat payments) and `python manage.py expire_platform_card_claims` **hourly** (expires unreviewed card claims, no financial effect). 7. Roll back: revert code; the new tables are unused by old code and legacy Zibal fields are still current.

Historical note: SMS purchases completed *before* this change have no ledger rows (the ledger starts here). No backfill is performed (it would assert history we cannot prove).

## 5. Security notes
Secrets: encrypted at rest, write-only forms, absent from HTML/audit/logs/exceptions (tests grep every admin page and the audit trail for a typed secret). Callback: unguessable token (≥24 random bytes), CSRF-exempt only because it is token + server-to-server-verify protected, no state change from query params, per-attempt throttle, 404 for unknown tokens without any gateway call. Open-redirect: `return_to` is a relative path or an absolute URL whose host passes `ALLOWED_HOSTS`; `//`, backslash, control characters, userinfo and look-alike hosts are rejected. Platform Admin pages are superuser-only on the isolated admin host; every mutation is audited without secrets.

## 6. Windows QA instructions (platform's own payment flows)
Everything below uses a **sandbox / fake merchant**; no real money moves. Use the QA database copy, never production.

1. Pull the branch `financial/platform-billing-20261105`; activate the venv; `python manage.py migrate` (QA DB only).
2. Start: `python manage.py runserver 8000`. Hosts (add to `C:\Windows\System32\drivers\etc\hosts` if needed): `rastisi.localhost` (owner portal), `platformadmins.rastisi.localhost` (Platform Admin), `<store>.rastisi.localhost` (store admin).
3. **Configure the platform gateway:** log in to Platform Admin as superuser → *اشتراک‌ها ▸ درگاه‌های پرداختِ پلتفرم*. Every provider shows its own status (see `PLATFORM_PROVIDER_MATRIX_20261105.md`). For **Zibal**: tick *Sandbox* + *فعال* → Save → **تستِ پیکربندی** (must say تست موفق) → in the default selector choose Zibal → ثبتِ پیش‌فرض. The badge must read **آماده**, the merchant value must never appear, and the default selector must show non-ready gateways as disabled. (Sandbox uses Zibal's documented fixed test merchant; no secret is needed.)
   *Pasargad / Zarinpal* have **no documented sandbox**: configure them only with real terminal/merchant credentials from the bank/provider, use **تستِ پیکربندی** (auth check + one unpaid test request — no money moves), and perform the first real transaction yourself with the minimum amount. If the test says `13028` the callback domain does not match the contract domain.
4. **Subscription:** as a store owner open `http://rastisi.localhost:8000/app/stores/<store id>/billing/` → *خرید* on a paid plan (complete the OTP step-up if enabled). Expect a redirect to `gateway.zibal.ir/start/…`; pay with the Zibal sandbox page; you are returned to the plans page with *پرداخت تأیید شد*; the subscription turns **active**. Refresh/Back/re-open the return URL several times — nothing changes (applied once).
4b. **Pasargad redirect check (only with a real terminal):** the browser must pass through the short *«در حال انتقال به درگاه پرداخت…»* page (it carries `Referer = https://<platform host>/`, a Pasargad requirement) and then reach `pep.shaparak.ir`.
5. **SMS package:** store admin → *تنظیمات ▸ پیامک* → *خرید و پرداخت* on a package → pay in sandbox → returned with ✅; credit increases by exactly the package size; Platform Admin → *خریدهای بسته پیامک* shows the purchase *تکمیل‌شده* and *تراکنش‌های پلتفرم* shows the attempt *موفق*.
6. **Failure paths:** cancel on the gateway page → returned with ⛔, no credit/activation, retry works. Close the tab after paying (don't return) → after ≥5 minutes run `python manage.py reconcile_platform_payments` → fulfilled once.
7. **Isolation check:** configure a *different* Zibal merchant in the store's own finance settings; confirm the platform requests above still show only the platform flow (Platform Admin → *تراکنش‌های پلتفرم*), and that store checkout still uses the store's gateway.
8. **Reconciliation page:** *تطبیق و مغایرت‌ها* must list nothing after clean runs; use *بررسی با درگاه* only to re-verify.

Automated: `python manage.py test apps.billing apps.sms apps.portal apps.dashboard apps.orders` (SQLite) and, for concurrency, `DATABASE_URL=postgres://… python manage.py test apps.billing.tests.test_platform_payment_concurrency`.

## 7. Decisions requested from the owner / external blockers
Policy (not invented; implemented conservatively):
1. **SMS refund when some credits were consumed** — currently refused (manual financial decision). Options: pro-rata refund of unused credits, or no refund once used.
2. **Backfill** of ledger rows for historical manual completions — not done.
3. Automatic **subscription renewal charging** (saved-card / recurring) — not present in the product; renewals still create an invoice the owner pays.
4. Whether to expose a **gateway chooser** to owners when several are ready (implemented; default gateway is preselected).

External (live activation blockers — none are code defects):
* Live merchant credentials for Zibal and/or Zarinpal and the **callback domain registered** with each merchant account (`RASTISI_PLATFORM_PRIMARY_HOST`).
* Zibal / Zarinpal expose no documented automatic **refund** API in the verified adapters ⇒ money refunds remain manual in the gateway panel.
* **Pasargad/Dorsa** is now approved technically (official docs re-read 2026-11-05) but needs RastiSi's own terminal credentials, server-IP whitelisting and a callback domain matching the contract; no sandbox is documented.
* **SnappPay / TorobPay (BNPL)** are implemented for the platform but **gated**: live use needs (1) the providers' *written* confirmation that selling SaaS subscriptions / SMS credit on the RastiSi merchant account is permitted, recorded per purchase type in the `provider_approval` gate; (2) credentials, IP whitelist and the provider-supplied `api_base`; (3) one authorised live transaction (`live_verification`). Without (1) the method cannot start a payment even if enabled.
* **Saman (SEP)** and **Mellat (Behpardakht)** are implemented as contract-testable adapters, **but no official current technical document was reachable**; the contracts come from secondary sources. Live use needs the official document checked against the adapter (`contract_verification` gate), merchant credentials, IP whitelist and one authorised live transaction.
* **Platform card-to-card** needs a dedicated platform destination card (never a store's) and at least one finance admin (superuser) who is not a member of the store being reviewed.
* Parsian, Sadad and Tejarat stay *not implemented* (official contracts not obtained; Tejarat's underlying PSP unknown).
* This session could not reach provider documentation hosts or provider APIs (network policy), so **no real sandbox transaction was run here**; sandbox runs are part of the Windows QA below.
* A first live transaction must be performed by the owner with a minimal amount before announcing.

## 8. Test evidence (synthetic credentials, mocked gateways; no real payment, no persistent DB touched)

New tests: **140** — gateway service 20 · subscription payments 22 · SMS payments 24 · platform admin + reconcile 18 · PostgreSQL concurrency 5 · **provider coverage 51** (matrix pinned to adapters, status taxonomy, Pasargad end-to-end incl. Referer/urlId/refund-reverse/reconcile, secure config test, merchant availability, renewal + history, Zibal sandbox-mode flow, admin UI).
They cover: platform-admin configuration (eligibility, readiness, secret hygiene, default reassignment, legacy Zibal read-through, access control); merchant-credential isolation (runtime + AST); subscription **purchase and renewal** through Zibal, Zarinpal and Pasargad; SMS credit purchase; callback success/failure/declined/forged/amount-mismatch/order-mismatch/late-payment; duplicate and repeated callbacks; manual-completion-vs-online races; cancel-then-pay; refund lifecycle (once, blocked when credits consumed, Pasargad reverse, manual fallback, idempotent, audited); tenant and permission isolation; reconcile command; open-redirect hardening.

| Run | Result |
|---|---|
| Broad regression `billing sms subscriptions portal dashboard orders notifications core cart` (SQLite), provider-coverage pass | **6051 tests, 1 failure, 6 errors** (see below) |
| After fixing the 1 failure (sandbox + local callback domain), re-run `portal billing sms` | 1712 tests, **1 error** (the known order-dependent one) |
| PostgreSQL 16 (throwaway), each run on its own: platform concurrency 5 · ConcurrentRecoveryTests · ConcurrentMerchantApprovalTests · ConcurrentRenderTests | all OK |
| Migrations on throwaway PostgreSQL: fresh `migrate`, reverse `sms 0009` / `billing 0007` / `portal 0014`, re-apply (all six), `makemigrations --check` | OK / "No changes detected" |
| Mutation check (earlier): removing the row locks from `complete_purchase`/`confirm_payment` | concurrency test **fails** |
| Real-browser check (Chromium, throwaway PostgreSQL + dev server): Platform Admin gateways page at 1440 and 390 px | every provider shows its own status; default selector disables non-ready gateways (`docs/payments/screenshots_20261105/`) |

The failure found by this pass and fixed: `portal…BillingZibalSettingsViewTests.test_superuser_can_view_and_save` — the new "local callback domain" configuration check blocked a sandbox save in the test environment. Sandbox mode (no money) now tolerates a local callback domain; live mode still requires a real domain.

The 6 errors that remain in the large combined SQLite run are **not** caused by this work and the suite is **not** fully green: `notifications.test_email_transport` (`asyncore` missing in the runtime — pre-existing environment issue); `portal…test_public_site_v2…test_a_new_ready_template_appears…` (order-dependent; passes alone); four `setUpClass` errors in PostgreSQL-oriented concurrency classes (`django_content_type` duplicate while deserialising the test DB in the large mixed run) — each passes when run on its own.

Store changes made by this pass (all other store behaviour untouched): Pasargad store redirect now uses the Referer interstitial (two store tests that asserted the bare 302 were updated). Existing store suites (`apps.orders` incl. card-transfer and BNPL settlement) are in the regression run.

**Not demonstrated here (blocked by this session's network policy):** a real Zibal sandbox transaction. Provider hosts return HTTP 403 from the session proxy, so the Zibal sandbox flow is proven only against a mock here; the real sandbox run is the first step of the Windows QA (§6).

---

# Part 2 — Five additional platform payment methods (SnappPay, TorobPay, platform card-to-card, Saman, Mellat)

## 9. Readiness gates and the approval workflow

A method can be *implemented* and *enabled* without being *ready*. Platform Admin → درگاه‌های پرداختِ پلتفرم shows, per method, six dimensions — implemented · configured · eligible (contract) · provider-approved · operationally ready · enabled — plus the gate list.

| Gate | Methods | Meaning | Who / how |
|---|---|---|---|
| `provider_approval` | SnappPay, TorobPay | provider's **written** authorisation to sell the named purchase types (subscription / SMS package) on the RastiSi merchant account | superuser; document reference ≥ 6 chars; purchase types chosen explicitly |
| `contract_verification` | Saman, Mellat | the adapter was checked against the provider's *current official* technical document | superuser; reference of the document |
| `live_verification` | all four gated methods | one authorised real transaction with verify (+settle) success | superuser; **cleared automatically when credentials or the environment change**; a superuser-owned store may pilot the method meanwhile (only this gate is lifted for it) |

Rules enforced in code and tests: attestations are superuser-only, audited (`platform_gateway.gate_recorded` / `gate_revoked`), never created by mocked tests, never inferred; revoking a gate closes the method again and repairs a default that pointed at it; effective purchase types = admin choice ∩ provider-approved types (BNPL has **no** default purchase type); `AdapterBackedBillingProvider` re-checks the gates at session creation, so even a buggy view cannot start a payment on a closed method (`gate_closed`).

## 10. Settlement-aware verification (online methods)

`verify_attempt` for methods whose adapter declares `SETTLE` (SnappPay, TorobPay, Mellat): **verify → persist `verified` + `verified_ref` → settle → only then success**. A settle error or rejection leaves the attempt `pending` (never failed, never fulfilled); reconcile re-runs *inquire → settle* (never a second verify); an inquiry that proves the transaction will never complete (`terminal_negative`, e.g. Mellat `48` reversed, BNPL cancel/revert) fails the attempt for good (`provider_terminal_failure`). Subscription activation and SMS credit allocation happen only inside the existing locked, idempotent `confirm_payment` after that. Saman/Mellat expose a unique sale reference (`RefNum` / `SaleReferenceId`) stored as the attempt's `provider_payment_id`; a DB unique constraint makes a replayed receipt unable to fulfil a second attempt. Saman and Mellat redirect by **auto-submitting POST form** (`Token` / `RefId`; one-time token never persisted). Platform Admin → تطبیق shows verified-but-unsettled attempts with an "استعلام و تسویه" action, and the manual card queue.

## 11. Platform card-to-card — finance-approved manual payment

This is **not** the stores' card transfer and shares nothing with it (separate method code `platform_card`, separate destination card stored in `PlatformGatewayConfig`; an AST/DB test proves store settings are never read or written).

**Owner flow:** invoice page (or SMS purchase) → choose *کارت‌به‌کارت* → page shows the platform destination card + the exact server-side amount → owner transfers money, then submits a **claim**: bank tracking number (required), transfer time, optional last-4 of the paying card, optional receipt (JPEG/PNG/WEBP/PDF ≤ 5 MB, type sniffed from content, stored in private storage — never a public URL). Nothing is activated or credited. The owner can cancel a pending claim.

**Finance flow (Platform Admin → بررسیِ کارت‌به‌کارت):** queue → claim page (amount expected *by the server*, tracking number, flags such as `old_transfer` / `duplicate_receipt_file` / repeated rejections, receipt viewer, full append-only history) → the reviewer must type an **independent bank-statement reference** and the **exact amount seen on the statement** → *تأییدِ مالی* applies the payment through the existing `confirm_payment` / SMS credit ledger **exactly once**; or *رد* with a mandatory reason (the owner may then submit a corrected claim). Rules: superuser only; **no self-approval** and no approval by an active member of the store; amount must equal the expected amount (under/over rejected); a bank-statement reference can approve only one claim; an expired claim cannot be approved (`expire_platform_card_claims` hourly); a duplicate tracking number is refused *and audited*; one pending claim per invoice/purchase; if the invoice/purchase was settled elsewhere meanwhile the claim becomes `needs_action` with no second effect. Refunds use the existing refund ledger (subscription) / credit-reversal (SMS) and remain a manual bank transfer, honestly reported as `pending` until finance completes it.

## 12. Windows QA additions (QA database only; no real money; no production)

1. `python manage.py migrate` (QA DB) — confirm `portal.0017/0018`, `billing.0010`.
2. Platform Admin → درگاه‌های پرداختِ پلتفرم: confirm **no COD row** anywhere; SnappPay/TorobPay/Saman/Mellat show gate lists and cannot be selected as default until ready; entering credentials only changes the status to *awaiting gates* (never *ready*).
3. **Card-to-card walkthrough:** (a) Platform Admin → platform_card: enter a **test** destination card (Luhn-valid), holder name, tick purchase types, enable. (b) As a store owner (host `<store>.rastisi.localhost:8000/admin-portal/`) open a billing invoice → choose کارت‌به‌کارت → submit a claim with a made-up tracking number and a small PNG. Confirm the subscription is **not** active. (c) Log in to Platform Admin as a **different** superuser (not a member of that store) → بررسیِ کارت‌به‌کارت → open the claim → try a wrong amount (refused) → enter the exact amount + a bank reference → تأییدِ مالی → subscription becomes active; press approve again → no second effect. (d) Repeat with an SMS package: credit appears once with one ledger row. (e) Submit a claim with a duplicate tracking number → refused; reject a claim → owner can resubmit.
4. **Gated methods (mock-only on QA):** you cannot run a real SnappPay/TorobPay/Saman/Mellat transaction without live credentials and provider authorisation; the automated suite (below) is the evidence. To rehearse the workflow, record the gates with a clearly fake reference on a **QA copy** only, then clear them.
5. `python manage.py reconcile_platform_payments` and `python manage.py expire_platform_card_claims --dry-run` run cleanly.

Screenshots of the updated Platform Admin (desktop 1440 / mobile 390) are in `docs/payments/screenshots_20261105/` (`gateways-v2-*`, `manual-claims-queue-*`, `manual-claim-review-*`, `reconciliation-v2-*`, `owner-card-claim-*`, `owner-invoice-methods-*`).

## 13. Test evidence — five-methods pass (synthetic data, mocked transports; no real payment)

New test modules (all pass on SQLite **and** on a throwaway PostgreSQL 16):

| Module | Tests | Covers |
|---|---|---|
| `test_platform_card_to_card.py` | 37 | configuration (card validation, Persian digits, isolation from store card settings, never an online default); claim submission, server-side amount, private receipt (magic-byte sniffing, size, hash, no public URL), duplicate/replayed references (+audit), DB constraints, append-only events; approval (exactly once, finance-only, self-approval and store-member conflicts, exact amount, bank-reference uniqueness, expiry, reject/cancel, needs-action); SMS ledger exactly once; refund lifecycle; reconcile ignores manual attempts; expiry command |
| `test_platform_card_to_card_http.py` | 17 | owner pages (claim form, cancel, own-receipt, cross-store 404, method disabled), Platform Admin queue/detail/approve/reject/receipt, permission matrix, reconciliation page sections |
| `test_platform_gated_providers.py` | 31 | matrix classification and COD absence; every gate (isolation, per-purchase-type approval, superuser-only, audit, revoke, credential change clears live gate, mocks never open gates, closed-gate session refusal, pilot rules, default selector); COD data migration (neutralised, audited, idempotent, store COD untouched); SnappPay/TorobPay carts from real lines, eligibility, verify→settle, settle-failure recovery, inquiry, terminal negative, forged callbacks, reconcile, SMS cart and per-type approval |
| `test_platform_psp_bridge.py` | 17 | Saman and Mellat: POST-form redirect, order codes, verified activation once, forged/mismatched/replayed callbacks, unique sale reference, settle failure → pending → inquiry+settle, 43/45 idempotent, 48 reversed never settled, reconcile, refunds (reverse vs manual), SMS credit once |
| `test_platform_payment_concurrency.py` (+5) | 10 total | PostgreSQL threads: simultaneous approvals by 4 finance admins = one effect; approve vs reject vs cancel = one winner; same reference from 4 stores = one claim; one bank-statement line cannot approve 3 claims; SMS claim race credits once |

Defect found **only** by the PostgreSQL run and fixed: `select_for_update()` combined with `select_related` on nullable FKs raises `NotSupportedError` on PostgreSQL (SQLite hid it), which would have broken every claim approval in production → now `select_for_update(of=("self",))`.

Defence-in-depth added while testing: Saman verification also rejects a bank answer naming a different `ResNum`.

| Run | Result |
|---|---|
| New modules, SQLite | all pass (37 + 17 + 31 + 17) |
| New modules + concurrency, PostgreSQL 16 | 100 tests OK; each concurrency class run on its own: OK |
| Broad regression `billing sms subscriptions portal dashboard orders notifications core cart`, SQLite, `--parallel 4` | **6173 tests, 103 skipped (PostgreSQL-only), 3 errors — all pre-existing, none related to this work** |
| Migrations on throwaway PostgreSQL | fresh `migrate`; reverse `billing 0009` and `portal 0016`; re-apply; `makemigrations --check` → "No changes detected" |
| Chromium, scratch PostgreSQL + dev server | 6 pages × (1440, 390 px): HTTP 200, 0 px overflow, no JS errors (`screenshots_20261105/`) |

The 3 errors (the suite is **not** fully green): `notifications.tests.test_email_transport` — `asyncore` is missing from the Python 3.13 runtime (environmental, pre-existing); `portal…test_public_site_v2…test_a_new_ready_template_appears_without_any_code_change` — order-dependent, passes alone; `core…ConcurrentRenderTests.setUpClass` — `django_content_type` duplicate in the large mixed run, passes alone on PostgreSQL.

**Not demonstrated here:** any real transaction with SnappPay, TorobPay, Saman or Mellat (no credentials, provider hosts blocked, no provider authorisation), and any check of the Saman/Mellat contracts against official documents (none reachable). These are the remaining external blockers listed in §7.
