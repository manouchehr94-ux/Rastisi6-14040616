# Payment Engine Architecture (M1)

Status: M1 additive architecture extension. This document describes the
**storefront** payment engine in `apps/orders/` after FEAT-002. It does not
cover the separate SaaS merchant-billing engine in `apps/billing/`, which is an
unrelated subsystem and must not be confused with storefront checkout.

All changes in M1 are **additive and backward-compatible**: the existing
`zibal` and `cod` adapters and the full `apps.orders` test baseline (527 pass /
16 skip) continue to pass unchanged.

---

## 1. Layering overview

```
checkout views / dashboard finance UI   (NO provider conditionals)
        │
        ▼
services/ (orchestration)
  gateway_payment_service.py  initiate_payment / process_callback_and_verify
  payment_service.py          BIN detection, simulate, apply_payment_success
  cod_payment_service.py      offline confirmation
  lifecycle.py                apply_payment_success
        │
        ▼
gateways/registry.py   ← THE ONLY dispatch point (code → adapter)
        │
        ▼
gateways/base.py       PaymentGatewayAdapter ABC + result dataclasses
  gateways/zibal.py    gold-standard online FACILITATOR adapter
  gateways/cod.py      offline adapter
        │
        ▼
models.py              PaymentGatewayConfig, PaymentAttempt,
                       PaymentTransactionEvent, PaymentReconciliation, Refund
encryption.py          Fernet credential encryption
```

Key invariant: **provider-specific behavior lives only inside adapters (and,
where orchestration is required, inside `services/`).** Checkout views and the
dashboard finance UI never branch on a specific gateway code. Dispatch always
flows through `registry.get_adapter(code)`.

---

## 2. Extended adapter contract

`PaymentGatewayAdapter` (in `apps/orders/gateways/base.py`) keeps its original
four abstract methods unchanged:

| Abstract method        | Purpose                                            |
|------------------------|----------------------------------------------------|
| `validate_credentials` | Can this config initiate payments?                 |
| `create_payment`       | Server-to-server create of a payment session       |
| `build_redirect_url`   | Where to send the customer's browser               |
| `verify_payment`       | Authoritative server-to-server verification        |

M1 adds the following **non-abstract** surface so existing adapters keep
instantiating without change:

### 2.1 Capability declarations

- `capabilities -> frozenset[PaymentOperation]` — the operations an adapter
  actually implements. An operation is declared **only** when it has a real,
  documentation-backed body. Default: `{CREATE, VERIFY}`.
- `category -> GatewayCategory` — `PSP` / `FACILITATOR` / `BNPL` / `OFFLINE`.
- `documentation_blocked -> bool` — `True` when the provider's official current
  contract is unverifiable. A documentation-blocked adapter must not be
  selectable at a real (non-sandbox) checkout.
- `supports(operation) -> bool` — convenience membership check.

`PaymentOperation` members: `CREATE, VERIFY, INQUIRE, CANCEL, REFUND, SETTLE`.

### 2.2 Optional capability-gated operations

These are **not** `@abstractmethod`. Their default implementations raise
`GatewayUnsupportedOperationError` so an undeclared financial operation can
**never be silently emulated**. An adapter enables one by (a) listing the
matching `PaymentOperation` in `capabilities` **and** (b) overriding the method
with a real implementation.

| Method                   | Result dataclass          | Default behavior            |
|--------------------------|---------------------------|-----------------------------|
| `inquire_payment`        | `PaymentInquiryResult`    | raise unsupported           |
| `cancel_payment`         | `PaymentCancelResult`     | raise unsupported           |
| `refund_payment`         | `PaymentRefundResult`     | raise unsupported           |
| `settle_payment`         | `PaymentSettleResult`     | raise unsupported           |
| `check_bnpl_eligibility` | `dict`                    | raise unsupported (BNPL only) |

### 2.3 Error hierarchy

`GatewayError` is the base; existing subclasses are unchanged
(`GatewayConnectionError`, `GatewayResponseError`, `GatewayPaymentError`,
`GatewayVerificationError`, `GatewayAmountMismatchError`,
`GatewayCredentialError`). M1 adds `GatewayUnsupportedOperationError` whose
`code` carries the attempted `PaymentOperation` value.

### 2.4 Adapter rules (unchanged, restated)

- Never log credentials or customer PII.
- Always use explicit connect/read timeouts for external HTTP calls
  (zibal: `(10, 30)` seconds).
- Return structured result dataclasses, never raw dicts/responses.
- Raise `GatewayError` subclasses for all failure modes.
- Never modify `Order`/`PaymentAttempt` state directly (caller's job).
- Currency conversion (Toman → Rial ×10 for zibal) is isolated inside the
  adapter and performed nowhere else. Amounts are `Decimal` with
  `decimal_places=0` (Toman); never `float`.

### 2.5 Current adapter declarations

| Adapter | `category`   | `capabilities`   | `documentation_blocked` |
|---------|--------------|------------------|-------------------------|
| zibal   | FACILITATOR  | `{CREATE,VERIFY}`| False                   |
| cod     | OFFLINE      | `{}` (empty)     | False                   |

zibal does **not** declare INQUIRE/CANCEL/REFUND/SETTLE because this adapter
implements only the documented `/v1/request` and `/v1/verify` endpoints.

---

## 3. Readiness-state derivation

`PaymentGatewayConfig.readiness_status` (in `apps/orders/models.py`) derives one
of the mission readiness states from verified conditions. It is **derived, not
stored**, so no new persisted column was required. The states live in the
`PaymentGatewayConfig.ReadinessStatus` `TextChoices` to avoid magic strings.

Derivation precedence:

| # | Condition                                                     | Readiness               |
|---|---------------------------------------------------------------|-------------------------|
| 1 | No adapter registered for `gateway_code`                      | `UNAVAILABLE`           |
| 2 | Adapter present but `documentation_blocked`                   | `DOCUMENTATION_BLOCKED` |
| 3 | Online adapter, no required credentials present at all        | `NOT_CONFIGURED`        |
| 4 | Some but not all required credentials, or validation fails    | `NEEDS_CREDENTIALS`     |
| 5 | Fully configured (or offline) AND `is_sandbox`                | `READY_FOR_TEST`        |
| 6 | Fully configured for real (non-sandbox) operation             | `CONNECTED`             |
| — | Unexpected failure while deriving                             | `ERROR`                 |

Important guarantees:

- **A registered adapter alone is never `CONNECTED`.** Real credentials (or the
  offline contract for COD) are required first.
- **A `DOCUMENTATION_BLOCKED` provider is never selectable at real checkout.**
  `is_selectable_at_checkout` returns `True` only for `CONNECTED`, or
  `READY_FOR_TEST` while the config itself is in sandbox mode.
- Existing `is_configured`, `can_activate`, and `is_online` are left intact for
  backward compatibility; readiness derivation is layered on top of them.

---

## 4. Lifecycle state machine

### 4.1 Original core states (unchanged)

```
CREATED → REQUESTING → REDIRECT_READY → PENDING → SUCCEEDED
                                               → FAILED
                                               → CANCELED
                                               → EXPIRED
```

`PaymentAttempt.FINAL_STATUSES = {SUCCEEDED, FAILED, CANCELED, EXPIRED}` — its
membership and semantics are **unchanged**.

### 4.2 M1 additive states

New optional `Status` members were added without renaming or removing any
existing member:

| State                | Meaning                                              |
|----------------------|------------------------------------------------------|
| `VERIFIED`           | Gateway verification confirmed (pre-finalize)        |
| `FINALIZED`          | Order-side finalization applied (additional final)   |
| `UNKNOWN`            | Ambiguous verify result awaiting reconciliation      |
| `REFUND_PENDING`     | Refund requested but not confirmed                   |
| `REFUNDED`           | Full refund confirmed (additional final)             |
| `PARTIALLY_REFUNDED` | Partial refund confirmed (additional final)          |

The new terminal states are collected in a **separate**
`EXTENDED_FINAL_STATUSES = {FINALIZED, REFUNDED, PARTIALLY_REFUNDED}` set so the
original `FINAL_STATUSES` stays byte-for-byte unchanged. `is_final` recognizes
both sets.

The `status` column `max_length` was widened from 15 to 20 (additive
`AlterField`) to fit `partially_refunded`.

### 4.3 PaymentTransactionEvent (append-only audit trail)

`PaymentTransactionEvent` is a new append-only model recording one event per
row (status change, verification, inquiry, refund request/confirm, cancel,
settle, note). It is **scoped by both `store` and `order`** (and optionally the
originating `attempt`) to preserve tenant isolation, carries a nullable
`amount` (Toman), a safe `message`, and a `payload` JSON field that holds only
non-sensitive gateway evidence — never credentials, full card numbers, or
customer PII. It is written, never updated or deleted.

---

## 5. Payment orchestrator flow

Orchestration lives in `services/gateway_payment_service.py`:

1. `initiate_payment` — resolve the config, create a `PaymentAttempt`, call the
   adapter's `create_payment`, store the `track_id`, build the redirect URL.
2. Customer pays on the gateway page and is redirected back to the callback.
3. `process_callback_and_verify` — call the adapter's `verify_payment`
   (browser callback params alone never prove payment).
4. `_apply_verified_payment` — `select_for_update` order-then-attempt locking;
   on an ambiguous or amount-mismatch result it writes a
   `PaymentReconciliation` record (money may have moved) and never marks the
   order paid.

Provider conditionals never leak into checkout/views; everything provider
specific stays behind the adapter (dispatched via the registry) or inside the
service layer.

---

## 6. Environment notes

- SQLite is the local/test database. Postgres is not installed here, so
  row-level-locking concurrency behavior cannot be truly verified on this host;
  such tests are marked NOT verified on SQLite and never claimed as proof of
  Postgres behavior.
- No external calls to live provider APIs are made from tests; adapters are
  exercised against documented contracts with deterministic mocks.
- New production integrations are disabled by default (`is_active` defaults to
  `False`).
