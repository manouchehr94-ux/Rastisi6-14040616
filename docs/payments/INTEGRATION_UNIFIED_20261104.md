# Unified payment engine — integration record (2026-11-04)

Branch `integration/payment-engine-unified-20261104`, based on `feature/gemini-dev-20261102` (incl. the preserved Notifications / Tracking
commits `6ce0649`, `3426352`, `ae8008d`). The archived payment-engine work (`handoff/kiro-payment-20261104` @ `92b066f`) was integrated
**selectively and semantically** (3-way patch of `main...archive`, every conflict resolved by hand) — it was **not** merged as a branch. PR #35 is untouched.

## 1. What was integrated / adapted / rejected

| Source change | Decision | Notes |
|---|---|---|
| Adapter contract (`PaymentOperation`, `GatewayCategory`, capability flags), readiness model (`ReadinessStatus`), checkout + finance gating | **Integrated** | `active_payment_gateways` keeps the canonical manual-method guard AND adds the readiness filter |
| Zarinpal, Pasargad/Dorsa, SnappPay, TorobPay adapters + contract tests | **Integrated** | all remain `NEEDS_CREDENTIALS` until a merchant supplies real credentials; no live call was made |
| Saman, Parsian, Mellat, Sadad, Tejarat | **Integrated as `DOCUMENTATION_BLOCKED` skeletons** | no endpoint was invented; never selectable (see §4) |
| B1 persisted `gateway_redirect_url` | **Integrated + hardened** | HTTPS-only/no-userinfo, documented-host allowlist, ops override |
| B2 GET/POST callbacks, narrow `csrf_exempt` | **Integrated** | callback fields are never proof of payment |
| B4 tenant-scoped idempotency, in-flight handling, round-3 (`05698b0b`, `b5b968dc`, `92b066f7`) | **Integrated after independent review** | stale in-flight expiry is safe: the customer was never given a URL for such an attempt; no network call under a row lock |
| B5 BNPL cart snapshot / reconciliation | **Integrated** | ×10 Toman→Rial only inside the adapter |
| `PaymentTransactionEvent`, extended `PaymentAttempt` statuses, `gateway_redirect_url` field | **Integrated** | events are now written for settlement evidence; `UNKNOWN` is used (see §3) |
| `card_to_card_payment_service`, `dashboard/card_to_card_views.py`, its routes, order-detail form, tests | **Rejected (duplicate authority)** | `CardTransferSubmission` + `card_transfer_service` is the only finalizer |
| Alternate card-to-card credential naming (`card_number` / `cardholder_name` / `iban`) | **Adapted** | `credential_aliases`: such stored configs stay valid and usable; ciphertext untouched until the merchant saves again |
| Kiro `0020…0023` migrations | **Replaced** | one additive migration generated from the merged model state on top of `0020_card_transfer` (§5) |
| Kiro docs (`PR35_GAP_ANALYSIS…`, `FINAL_ACCEPTANCE_REPORT_FA`) | **Kept, marked outdated** | superseded by this file |

## 2. Authoritative flow

1. **Initiate** (`gateway_payment_service.initiate_payment`) — guards: order payable, config belongs to the store, active, configured, **ready**;
   no unresolved (`UNKNOWN`) attempt on the order; manual-confirmation methods → `card_transfer_service.ensure_attempt` (canonical, PENDING, never paid);
   COD → SUCCEEDED attempt, order stays pending. Online: tenant-scoped reuse of a live attempt, otherwise one attempt created under the order row lock;
   the provider `create_payment` runs **outside** any lock, exactly once per attempt. Provider URL is validated before it is stored.
2. **Callback** (`gateway_callback`, GET/POST, store-scoped) → `process_callback_and_verify`: server-to-server `verify_payment` is the only authority.
   Verify unsuccessful on a two-step provider is cross-checked with the provider status before it can be a failure.
3. **Settle** (only for providers declaring `SETTLE`): `_settle_after_verify` classifies — **ok** (settle success, or provider status SETTLED) ·
   **failed** (provider status CANCEL/REVERT) · **uncertain** (timeout, transport error, malformed answer, bare rejection the provider cannot confirm,
   no inquiry capability). Uncertain ⇒ attempt `UNKNOWN`, suspected `PaymentReconciliation(settlement_uncertain)`, append-only `PaymentTransactionEvent`,
   `payment.suspicious` alert. **Never** `payment.failed`, never PAID.
4. **Finalize** (`_apply_verified_payment` → `lifecycle.apply_payment_success`) under order+attempt locks, conditional PENDING→PAID, one Transaction.
5. **Recovery** (`resolve_unknown_payment`, `reconcile_unknown_payments` command / cron, also a late callback): inquiry SETTLED → step 4; CANCEL/REVERT → FAILED +
   reconciliation resolved `not_paid` + one `payment.failed`; anything else → stays UNKNOWN for the administrative reconciliation page. Never calls settle again.
   While any attempt of an order is `UNKNOWN`: no new chargeable operation for **any** provider (HTTP 409 on the payment page), the expiry job skips the order
   (`unresolved_settlement`), a repeated callback never re-verifies / re-settles.
6. **Card transfer** (canonical): customer selects → PENDING attempt → submits last-4 + tracking → merchant approve/reject (`card_transfer_service`) →
   approve is the single path to PAID (open unverified PENDING attempt of the same order, exact amount, duplicate-tracking guard, one Transaction).

## 3. Settlement-uncertainty semantics

| Case | Attempt | Order | `payment.failed` | Alert |
|---|---|---|---|---|
| definitive provider rejection (provider status CANCEL/REVERT) | FAILED | pending | **once** | — |
| timeout / transport / malformed / unknown outcome | **UNKNOWN** | pending | never | `payment.suspicious` |
| confirmed settlement (now or via inquiry) | SUCCEEDED | PAID once | never | — |
| verify ok, local finalization failed | SUCCEEDED + `PaymentReconciliation(processing_error)` (existing) | pending | never | `payment.suspicious` |
| duplicate / concurrent callback or recovery | unchanged / one winner | — | no duplicates | — |

## 4. Provider matrix (see tests in §7)

| Code | Provider | Status here | Verified capabilities (code + mocked contract tests) | Merchant needs | External blocker |
|---|---|---|---|---|---|
| `zibal` | Zibal | Operational (pre-existing) | create, verify | merchant id | none |
| `zarinpal` | Zarinpal | Implemented, `NEEDS_CREDENTIALS` | create, verify (REST v4) | 36-char merchant id | live/sandbox verification needs a real merchant |
| `pasargad` | Pasargad / Dorsa | Implemented, `NEEDS_CREDENTIALS` | create, verify, inquire, cancel | username, password, terminal no., service code | real merchant; Referer rule is the view's duty |
| `snappay` | SnappPay | Implemented, `NEEDS_CREDENTIALS` | create, verify, settle, cancel, inquire | client id/secret (+ provisioning by Snapp) | real merchant; payment-page domain not named by the contract (HTTPS-only enforced) |
| `torobpay` | TorobPay | Implemented, `NEEDS_CREDENTIALS` | create, verify, settle, cancel, inquire | client id/secret + username/password | real merchant; payment-page domain not named by the contract |
| `saman` | Saman / SEP | **DOCUMENTATION_BLOCKED** | none | — | official technical contract unreachable (marketing site only) |
| `parsian` | Parsian / PEC | **DOCUMENTATION_BLOCKED** | none | — | official docs unreachable |
| `mellat` | Mellat / Behpardakht | **DOCUMENTATION_BLOCKED** | none | — | official docs unreachable (and SOAP client not in the dependency set) |
| `sadad` | Sadad | **DOCUMENTATION_BLOCKED** | none | — | official docs unreachable |
| `tejarat` | Tejarat (label) | **DOCUMENTATION_BLOCKED** | none | — | the contracted underlying PSP must be identified first (IranKish NOT assumed) |
| `cod` | Cash on delivery | Operational | offline, attempt SUCCEEDED at selection, order pending until delivery confirmation | — | — |
| `card_to_card` | Card transfer | Operational (canonical workflow) | receipt + merchant approve/reject | destination card, holder | — |

No adapter declares `REFUND`: automated gateway refunds are **not** implemented (Refund P0 / `payment.refund_failed` untouched; `payment.refund_failed` stays PLANNED).

## 5. Migration graph

`orders`: `…0019_reconciliation_evidence_level` → `0020_card_transfer` (unchanged, never renumbered) → `0021_payment_engine_unified` (single leaf).
`0021` is additive and reversible: `AddField PaymentAttempt.gateway_redirect_url` (default `""`), `AlterField PaymentAttempt.status` (choices + varchar 15→20),
`AlterField PaymentGatewayConfig.gateway_code` (the union of all 12 codes), `AlterField PaymentReconciliation.kind` (+`settlement_uncertain`), `CreateModel PaymentTransactionEvent`.
`makemigrations --check` is clean. **Caveat:** if any persistent database had applied the PR #35 migrations (`0020_alter_paymentattempt…`–`0023`), this migration would
conflict with them; PR #35 was never merged, so none is expected — verify before applying anywhere persistent. **Nothing was applied to QA/production.**

## 6. Operations

* Cron (template only, not installed): `reconcile_unknown_payments` every 10 minutes (`deploy/cron/rastisi.crontab`).
* Unresolved items appear on the existing payment-reconciliation page (kind “تسویه نامشخص”) and as `payment.suspicious` inbox alerts.
* `PAYMENT_REDIRECT_EXTRA_HOST_SUFFIXES = {"<code>": ("domain.ir",)}` widens a provider's redirect-host allowlist without a code change.

## 7. Known limits (not hidden)

* No provider was called live; contract tests use documented shapes with mocked HTTP.
* A reconciled UNKNOWN attempt whose provider cannot be asked (no `INQUIRE`) needs the administrative resolution.
* `PaymentTransactionEvent` is written for settlement evidence only (not yet for every state change).
* Purchase tracking stays BLOCKED (see `docs/tracking/ECOMMERCE_TRACKING_20261103.md`).
