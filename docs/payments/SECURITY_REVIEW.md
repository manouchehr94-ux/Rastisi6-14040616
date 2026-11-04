# Payment Engine Security Review

This review documents the security protections built into the RastiSi
storefront payment engine and references the exact code and tests that enforce
each. All provider HTTP is mocked in tests; no real endpoint is contacted and no
real-money transaction is performed.

Scope: `apps/orders/gateways/*` (adapters), `apps/orders/encryption.py`
(credential encryption), `apps/orders/services/gateway_payment_service.py`
(orchestrator), `apps/orders/models.py` (`PaymentGatewayConfig`,
`PaymentAttempt`, `PaymentReconciliation`), and the dashboard finance admin.

---

## 1. Duplicate processing / duplicate finalization

**Threat:** a duplicate or replayed callback causes the order to be paid twice,
or creates a second `ok` transaction / re-reserves the coupon.

**Protections:**
- Idempotent short-circuit: `process_callback_and_verify` returns immediately
  when the attempt is already `SUCCEEDED`, and does **not** re-call the gateway.
  (`apps/orders/services/gateway_payment_service.py`, `process_callback_and_verify`.)
- Conditional status transition (not a blind save): the attempt is moved to
  `PENDING` only via a filtered `UPDATE ... WHERE status IN (open_statuses)`, so
  a concurrent callback that already finalized the same attempt is not
  overwritten.
- `_apply_verified_payment` re-reads the attempt under `select_for_update` and
  returns early if it is already `SUCCEEDED` (the "another callback processed
  it" guard).
- A second confirmed attempt on an already-paid order is recorded as a
  `PaymentReconciliation` of kind `ALREADY_PAID`; it never creates a second
  `ok` transaction.
- Idempotency keys on `initiate_payment` return the existing attempt instead of
  creating a duplicate.

**Tests:**
- `apps/orders/tests/test_payment_security.py::ForgedCallbackTests::test_callback_replay_after_success_is_idempotent`
- `...::ForgedCallbackTests::test_second_attempt_on_paid_order_is_reconciled_not_double_paid`
- `...::ConcurrentVerificationLogicTests::test_double_apply_of_same_attempt_creates_single_transaction`
- `apps/orders/tests/test_payment_safety.py::LateGatewayPaymentTests::test_duplicate_late_callbacks_are_idempotent_and_do_not_reverify`
- `apps/orders/tests/test_payment_safety.py::LateGatewayPaymentTests::test_second_confirmed_attempt_for_paid_order_is_reconciled`

---

## 2. Cross-tenant access (Store isolation)

**Threat:** store B uses store A's gateway config/credentials, or resolves a
callback for an attempt that belongs to another store.

**Protections:**
- `initiate_payment` rejects any `gateway_config` whose `store_id` differs from
  the authoritative store (`PaymentConfigError`).
- `process_callback_and_verify` looks up the attempt with
  `filter(public_id=..., store=store)`; a mismatched store cannot resolve it and
  raises `PaymentVerificationFailed` before any gateway call.
- Credentials are stored per `PaymentGatewayConfig`
  (`UniqueConstraint(store, gateway_code)`) and encrypted per row; each store
  decrypts only its own ciphertext.
- Checkout option listing is store-scoped; another store's config never
  influences this store's selectable gateways.

**Tests:**
- `apps/orders/tests/test_payment_security.py::CrossTenantIsolationTests` (all three cases)
- `apps/orders/tests/test_feat005_provider_integration.py::CrossTenantTests` (config rejection, callback scoping, option list isolation)

---

## 3. Forged / replayed callbacks (server-to-server verify is authoritative)

**Threat:** a crafted browser callback with `success=1` (or a replayed one)
finalizes the order without a real payment.

**Protections:**
- A callback query parameter is NEVER treated as proof of payment. The order is
  only finalized after a server-to-server `verify_payment` returns
  `success=True`. The callback body's `success`/`status` is used only to decide
  whether to open a **suspected** reconciliation record when the verify result
  is ambiguous — it never finalizes.
  (`_callback_claims_success` is explicitly documented as "never proof".)
- Amounts and totals carried in the callback body are ignored; the verify uses
  the server-authoritative `PaymentAttempt.amount` (the order's `grand_total`
  from the DB).
- Adapters require a stored `gateway_track_id`; an attempt without one is never
  sent to the gateway.

**Tests:**
- `apps/orders/tests/test_payment_security.py::ForgedCallbackTests::test_callback_success_param_alone_does_not_finalize`
- `...::AmountTamperingTests::test_callback_body_amount_is_ignored_server_total_is_authoritative`
- `...::ExpiredAndFinalAttemptTests::test_attempt_without_track_id_is_not_sent_to_gateway`
- `apps/orders/tests/test_feat005_provider_integration.py::OrchestratorEndToEndTests::test_amount_tampering_in_callback_does_not_change_finalized_amount`

---

## 4. Credential exposure / secret leakage

**Threat:** merchant secrets appear in rendered HTML, logs, `str()`,
`__repr__`, exception messages, or persisted reconciliation evidence.

**Protections:**
- Credentials are encrypted at rest with Fernet in a dedicated key
  (`PAYMENT_CREDENTIAL_KEY`, NOT Django's `SECRET_KEY`); production fails closed
  if the key is missing. (`apps/orders/encryption.py`.)
- `PaymentGatewayConfig.encrypted_credentials` stores only ciphertext; decrypted
  credentials are read transiently via `get_credentials()`.
- Adapters never log credentials and never place them in error messages or
  `details` (verified for Zibal and Zarinpal).
- Reconciliation evidence is sanitized (`_sanitized_evidence`, `sanitize_error`)
  to carry only masked card / ref / status, never credentials or PII.
- The finance admin templates never render `encrypted_credentials` (static
  check: 0 occurrences in `settings_payment_config.html` /
  `settings_finance.html`); credential display uses masking
  (`mask_credential`).

**Tests:**
- `apps/orders/tests/test_payment_security.py::CredentialEncryptionTests` (encrypted-at-rest, round-trip, masking)
- `...::SecretLeakageTests` (not in exceptions, repr, logs, or reconciliation evidence — Zibal and Zarinpal)

---

## 5. Financial inconsistency (money moved but order state wrong)

**Threat:** the gateway confirms money moved but the order was canceled /
already paid / not payable, or verify is ambiguous — and the money is silently
lost or the wrong amount is applied.

**Protections:**
- Amount mismatch on a confirmed payment raises
  `GatewayAmountMismatchError`; the orchestrator records a
  `PaymentReconciliation` of kind `AMOUNT_MISMATCH` with evidence and marks the
  attempt `SUCCEEDED` (money moved) but creates **no** `ok` transaction and
  never marks the order paid.
- Late success on a canceled order → `ORDER_CANCELED` reconciliation (order not
  reopened, coupon not re-reserved, stock not re-decremented).
- Ambiguous verify (connection/response error) while the customer claims
  success → `VERIFY_AMBIGUOUS` **suspected** reconciliation for staff review;
  no success is asserted.
- Applying a verified payment is serialized by `select_for_update` on the order
  row first, then the attempt row (same lock order as cancellation and the
  expiry job), so a cancel racing a payment is resolved deterministically.
- The callback view never returns an uncaught 500; it redirects with a notice.

**Tests:**
- `apps/orders/tests/test_payment_security.py::AmountTamperingTests::test_gateway_confirmed_different_amount_never_marks_order_paid`
- `...::ConcurrentVerificationLogicTests::test_cancel_then_payment_records_reconciliation_not_double_state`
- `apps/orders/tests/test_payment_safety.py::LateGatewayPaymentTests` (late success recorded not applied; processing error preserves evidence; callback never 500)
- `apps/orders/tests/test_payment_discrepancy.py` (discrepancy/reconciliation paths)

---

## 6. Unsafe redirects (open redirect)

**Threat:** a crafted `track_id` or callback value redirects the customer to an
attacker-controlled host.

**Protections:**
- `build_redirect_url` composes the redirect from a FIXED provider origin
  (`https://gateway.zibal.ir/...`, `https://payment.zarinpal.com/...`) and only
  appends the track id to the fixed path; it can never move the authority off
  the provider domain.

**Tests:**
- `apps/orders/tests/test_payment_security.py::RedirectSafetyTests` (origins
  stay on provider domain; hostile track id is only appended).

---

## 7. Documentation-blocked providers cannot be routed

**Threat:** a provider whose contract is unverified is used for a real payment.

**Protections:**
- Readiness derivation returns `DOCUMENTATION_BLOCKED` for any adapter with
  `documentation_blocked = True`; `initiate_payment` refuses to route anything
  that is not `CONNECTED` (or sandbox `READY_FOR_TEST`), and such providers are
  excluded from the checkout option list.

**Tests:**
- `apps/orders/tests/test_payment_security.py::UnauthorizedConfigTests` (blocked / inactive / unconfigured cannot initiate)
- `apps/orders/tests/test_feat005_provider_integration.py::OrchestratorEndToEndTests::test_documentation_blocked_provider_cannot_be_routed` and `CheckoutOptionReadinessTests`

---

## Concurrency verification caveat (Postgres vs SQLite)

The orchestrator's strongest concurrency guarantee relies on
`SELECT ... FOR UPDATE` **row-level locking** (order row first, then attempt
row). The available test database in this environment is **SQLite**, which does
NOT implement row-level locking. The concurrency tests
(`test_payment_security.py::ConcurrentVerificationLogicTests`,
`test_payment_concurrency.py`) verify the **idempotency logic** (conditional
transitions, the already-`SUCCEEDED` guard) but do **NOT** prove the Postgres
row-lock serialization. This is called out explicitly here and in
`REGRESSION_RESULTS.md`; real row-level-locking concurrency must be validated
against Postgres before relying on it in production.
