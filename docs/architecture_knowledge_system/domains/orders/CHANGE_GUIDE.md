# orders — CHANGE GUIDE ★

```
domain_id: D6
code_baseline: 5883a140
open_decisions: DR-1, DR-5, DR-6
```

Task-oriented recipes for changing the orders/payment domain. Each recipe lists what to read, the
canonical owner, likely code affected, dependent domains, mutation paths, invariants, state
transitions, transaction/concurrency concerns, security, tests to run, regression risks, docs to
update, and any open decision that may block the change.

> **Before ANY payment change:** internalise that **`Order.payment_status` has three writers and no
> transition guard** (H1/DR-1): `gateway_payment_service.process_callback_and_verify`,
> `payment_service.simulate_payment`, `refund_service.execute_order_refund`. A change that assumes
> a single writer or a guarded transition is wrong at `5883a140`.

---

## Recipe: Add / change a payment provider
- **READ FIRST:** [SERVICES](SERVICES.md) (gateways), `apps/orders/gateways/base.py`, `registry.py`.
- **CANONICAL OWNER:** `gateways/` adapters + `gateway_payment_service`.
- **LIKELY CODE:** new `gateways/<name>.py` (implements `PaymentGatewayAdapter`); loader in
  `registry.py`; `GatewayCode` choice on `PaymentGatewayConfig`; a migration.
- **DEPENDENT DOMAINS:** dashboard (gateway-config UI), `stores` (integration credential pattern).
- **MUTATION PATHS:** adapter must NOT touch Order/PaymentAttempt state (service does).
- **INVARIANTS:** currency conversion inside the adapter only; verify server-to-server.
- **TX/CONCURRENCY:** none new in the adapter (stateless); the service owns locking.
- **SECURITY:** credentials encrypted (`PaymentGatewayConfig.encrypted_credentials`), never logged.
- **TESTS:** add `apps/orders/tests/test_gateway_payment_service.py` cases; run that + `test_order_service`.
- **REGRESSION RISKS:** `payment_initiate` fuzzy-matches config↔legacy `PaymentGateway` (M4/DR-5).
- **DOCS TO UPDATE:** this pack DATA_MODEL/SERVICES; `EXTERNAL_INTEGRATIONS.md`.
- **OPEN DECISION:** **DR-5** (dual gateway model) may block a clean "which gateway" mapping.

## Recipe: Change callback verification
- **READ FIRST:** [FLOWS](FLOWS.md) 3b, `gateway_payment_service.process_callback_and_verify`.
- **CANONICAL OWNER:** `gateway_payment_service`.
- **LIKELY CODE:** the SUCCESS `@atomic` block (`gateway_payment_service.py` ~290-360).
- **MUTATION PATHS:** conditional PENDING→PAID update; legacy Transaction create; change_order_status.
- **INVARIANTS:** browser return never proof; `is_final` idempotency; `updated==0` already-paid guard.
- **TX/CONCURRENCY:** keep external verify OUTSIDE the atomic block; keep the conditional update.
- **TESTS:** duplicate-callback-idempotent, failed-verification-does-not-mark-paid, already-paid-by-another-attempt.
- **REGRESSION RISKS:** breaking idempotency → double-paid orders; SQLite has no row locks (rely on conditional update).

## Recipe: Change `payment_status` semantics ⚠️
- **READ FIRST:** [STATE_MACHINES](STATE_MACHINES.md), [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md), [INVARIANTS](INVARIANTS.md).
- **CANONICAL OWNER:** *none* — 3 writers, no guard (H1). This is the crux.
- **LIKELY CODE (ALL THREE):** `gateway_payment_service.py:313-316`, `payment_service.py:86-98`,
  `refund_service.py:234` — plus every reader (dashboard reports/CRM/export filters on
  `payment_status`).
- **MUTATION PATHS:** all three are independent; there is no central chokepoint to enforce a rule.
- **INVARIANTS:** the "legal guarded transition" invariant does NOT exist yet.
- **TESTS:** there is no transition-legality test to update (gap — TESTING.md).
- **OPEN DECISION:** **DR-1 blocks this.** Introducing a guard/canonical writer is exactly the DR-1
  decision and must not be done without Product-Owner authorization.

## Recipe: Add a payment state (e.g. `partially_refunded`)
- **READ FIRST:** [STATE_MACHINES](STATE_MACHINES.md), [DATA_MODEL](DATA_MODEL.md).
- **LIKELY CODE:** `Order.PaymentStatus` choices; the 3 writers; every reader/filter; refund logic.
- **REGRESSION RISKS:** because there is no transition table, a new state can be entered/exited
  illegally from any writer. **DR-1 blocks a safe implementation.**

## Recipe: Change refund behavior
- **READ FIRST:** `refund_service`, [INVARIANTS](INVARIANTS.md) (ADR-33).
- **CANONICAL OWNER:** `refund_service`.
- **INVARIANTS:** amounts from immutable Order snapshot; MANUAL only (GATEWAY raises); idempotent.
- **MUTATION PATHS:** writes Refund(+Item) and Order.payment_status→REFUNDED (no Order lock — MEDIUM).
- **TESTS:** `test_refund_service.py`, `test_refund_service_tax.py`; return-triggered refund in `test_return_service.py`.
- **OPEN DECISION:** implementing real GATEWAY refunds is beyond ADR-33 scope — treat as a new decision.

## Recipe: Change COD behavior
- **READ FIRST:** `gateways/cod.py`, [FLOWS](FLOWS.md) 3b, [INVARIANTS](INVARIANTS.md) #7.
- **INVARIANT TO PRESERVE:** COD marks the attempt SUCCEEDED but must NOT mark the order PAID
  (paid on delivery; merchant confirms via DELIVERED).

## Recipe: Change retry / idempotency behavior
- **READ FIRST:** [TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md).
- **LIKELY CODE:** `idempotency_key`/`gateway_track_id` uniques; `is_final` checks; conditional update.
- **REGRESSION RISKS:** weakening any of these enables double-processing; SQLite relies on the
  application-level guards, not row locks.

## Recipe: Change `PaymentGatewayConfig`
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md), `dashboard.settings_gateway_config_save` (direct write).
- **CANONICAL OWNER:** ambiguous — config written directly by dashboard views (DR-3); `payment_initiate`
  fuzzy-matches to legacy `PaymentGateway` (DR-5).
- **OPEN DECISIONS:** DR-3 (service discipline) and DR-5 (dual gateway) both touch this.

## Recipe: Change checkout → payment handoff
- **READ FIRST:** [ENTRY_POINTS](ENTRY_POINTS.md) (`payment_start` → initiate vs simulation), [FLOWS](FLOWS.md).
- **LIKELY CODE:** `views.payment_start` (routing logic + gateway-config resolution/fallback).
- **DEPENDENT DOMAINS:** cart (checkout state), catalog (stock already consumed at order creation).
- **REGRESSION RISKS:** `payment_start` currently contains gateway-config resolution/idempotency-key
  construction logic in the view (business logic in the controller — INFERRED minor smell).

## Recipe: Retire the simulation payment path (part of DR-6)
- **READ FIRST:** [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md), `payment_service.py`, `views.payment_callback`.
- **LIKELY CODE:** `simulate_payment`, `payment_callback`, `payment_start` simulation branch,
  `PAYMENTS_SIMULATION_ENABLED`; ~1500 checkout/payment tests depend on it in dev/test.
- **OPEN DECISION:** **DR-6.** Removing it also removes one `Order.payment_status` writer (helps DR-1)
  but breaks the test harness that relies on it. Do not remove without authorization.

## Recipe: Retire legacy `Transaction` compatibility (part of DR-6)
- **READ FIRST:** [DATA_MODEL](DATA_MODEL.md) (Transaction), MUTATION_AUTHORITY.
- **LIKELY CODE:** the `Transaction.objects.create(...)` in both `simulate_payment` and
  `gateway_payment_service` (back-compat); dashboard views/reports that read `Transaction`.
- **REGRESSION RISKS:** dashboard payment listings read `Transaction`; removing it needs those
  readers migrated to `PaymentAttempt`. **DR-6 blocks.**

---

## Blocking-decision quick reference
| Change | Blocked/affected by |
|---|---|
| payment_status semantics / new state | **DR-1** |
| gateway config / which-gateway mapping | DR-3, DR-5 |
| retire simulation / legacy Transaction | **DR-6** |
| service discipline for shipping/tax/gateway config | DR-3 |
