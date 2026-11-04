# Payment Engine Audit (M0)

Base commit: `7d3115564569509f1da442fdc4aeacc9f855a81d`
Branch: `feature/kiro-payment-engine-20261103`
Scope: the **storefront** payment engine in `apps/orders/`. The SaaS merchant-billing engine in `apps/billing/` is a separate subsystem and is out of scope for this mission.

This document is grounded in the actual source on the base commit. All file paths and line numbers below were read directly from the tree, not inferred from the mission brief.

---

## 1. Verified baselines (re-run on this worktree)

| Check | Command | Result |
| --- | --- | --- |
| Orders test suite | `python manage.py test apps.orders` | **527 passed / 16 skipped** (≈116s) |
| Billing test suite | `python manage.py test apps.billing` | **147 passed / 1 skipped** (≈4s) |
| Pending migrations | `python manage.py makemigrations --check --dry-run` | **No changes detected** |

SQLite is the default DB in this worktree; Postgres is **not** installed. Real row-level-locking concurrency (the `select_for_update` behavior in the orchestrator) therefore **cannot be truly verified on SQLite** and must be marked NOT verified on this platform. We never claim SQLite proves Postgres concurrency semantics.

---

## 2. Current architecture

### 2.1 Adapter contract — `apps/orders/gateways/base.py`

Defines `PaymentGatewayAdapter` (ABC) and the supporting types:

- Result dataclasses (frozen):
  - `PaymentCreationResult` (`track_id`, optional `gateway_url`, `extra`).
  - `PaymentVerificationResult` (`success`, `ref_id`, `card_number`, `status_code`, `message`).
- Error hierarchy, rooted at `GatewayError` (carries `code` + safe-to-log `details`):
  - `GatewayConnectionError`, `GatewayResponseError`, `GatewayPaymentError`,
    `GatewayVerificationError`, `GatewayAmountMismatchError` (subclass of the verification error, carries reconciliation `details["evidence"]`), `GatewayCredentialError`.
- Abstract/declared members:
  - properties `code`, `display_name`, `is_online` (abstract); `required_credentials` (default `[]`).
  - abstract methods `validate_credentials`, `create_payment`, `build_redirect_url`, `verify_payment`.

Documented adapter rules in the module docstring: never log credentials/PII, always use explicit timeouts, return dataclasses (never raw dicts), raise `GatewayError` subclasses, and never mutate `Order`/`PaymentAttempt` state inside the adapter (that is the caller/orchestrator's responsibility).

### 2.2 Registry / dispatch — `apps/orders/gateways/registry.py`

The single dispatch point. No other module imports adapter classes directly.

- `_ADAPTER_LOADERS: dict[str, callable]` — maps code → lazy loader. Currently **only** `"zibal"` and `"cod"`.
- `_ADAPTER_CACHE` — caches stateless adapter instances.
- `GATEWAY_CHOICES` — currently `[("zibal", "زیبال"), ("cod", "پرداخت در محل")]`.
- `get_adapter(code)` (raises `KeyError` for unknown codes), `registered_codes()`, `is_online_gateway(code)`.

### 2.3 Reference adapters

- **`apps/orders/gateways/zibal.py` — gold-standard online adapter.**
  - Explicit timeouts `CONNECT_TIMEOUT = 10`, `READ_TIMEOUT = 30` passed as `timeout=(10, 30)` on every `requests.post`.
  - Toman→Rial conversion isolated here (`TOMAN_TO_RIAL = 10`); no other module converts.
  - Strict JSON parsing; missing `result` → `GatewayResponseError`.
  - Result codes `100` (success) / `201` (already verified); status `1`/`2`.
  - On a confirmed payment whose returned Rial amount ≠ expected Rial, raises `GatewayAmountMismatchError` carrying `details["evidence"]` (reported/expected Rial, ref id, masked card) so the caller can persist it. If a success result has an unreadable amount, raises `GatewayResponseError(code="amount_unavailable")` with the same evidence.
  - Never logs the merchant credential.
- **`apps/orders/gateways/cod.py` — offline pattern.**
  - `is_online = False`, no credentials, synthetic `track_id = "cod-{order_code}"`, no redirect URL.
  - `verify_payment` intentionally returns `success=False` — COD is confirmed at delivery via order-status transition, never marked paid at checkout.

### 2.4 Package docstring — `apps/orders/gateways/__init__.py`

The package docstring still lists `ZarinPal` only as a **"future"** adapter (line ~4). This corroborates the discrepancy in §6: there is no storefront ZarinPal today.

---

## 3. Payment models — `apps/orders/models.py`

| Model | Line | Notes |
| --- | --- | --- |
| `PaymentGateway` | ~311 | Legacy order-level record of the chosen method. |
| `Order` | ~334 | Nested `Status` (~335) and `PaymentStatus` (~342) TextChoices. `idempotency_key` (~370) with partial unique constraint `uniq_order_idempotency_key_when_set` (~438–440) active only when non-empty. |
| `OrderItem` | ~468 | |
| `OrderStatusHistory` | ~539 | |
| `Transaction` | ~562 | Nested `Status` (~563). |
| `PaymentGatewayConfig` | ~605 | Source of truth for which gateways are configured per store. Nested `GatewayCode` TextChoices (~624) currently `{ZIBAL, COD}` — **this is one of the enums to extend** when adding providers. `is_active` defaults **False** (safe default). Credentials stored in `encrypted_credentials` (Fernet JSON). Unique constraint `uniq_gateway_config_per_store` on `(store, gateway_code)` (~670). |
| `PaymentAttempt` | ~752 | Nested `Status` machine (~768) + `FINAL_STATUSES` frozenset (~778). `gateway_track_id` (~835) and `idempotency_key` (~848). Partial unique constraints: `uniq_payment_attempt_idempotency_key` (~894–896) and a unique `gateway_track_id`-when-set constraint (~899–900). `is_final()` ~921. |
| `PaymentReconciliation` | ~928 | Nested `Kind` (~937), `EvidenceLevel` (~945), `Status` (~951); `gateway_track_id` (~975). The durable record for ambiguous/mismatch outcomes. |
| `Refund` | ~1004 | Nested `Status` (~1015), `FINAL_STATUSES` (~1038), `idempotency_key` (~1070) with partial unique `uniq_refund_idempotency_key_when_set` (~1083–1085). |

Amounts are `Decimal` with `decimal_places=0` (Toman integer units). **Never use float.**

---

## 4. Provider registration mechanism

Adding a storefront gateway requires, in order:

1. A new adapter class in `apps/orders/gateways/<provider>.py` implementing the ABC.
2. A lazy loader + entry in `_ADAPTER_LOADERS` and a `GATEWAY_CHOICES` entry in `registry.py`.
3. A new member in `PaymentGatewayConfig.GatewayCode` (models.py ~624) + an additive migration (numbered after `0019_reconciliation_evidence_level.py`).
4. Dashboard wiring consumes the registry automatically (`apps/dashboard/services/settings_admin_service.py` iterates `GATEWAY_CHOICES`/`get_adapter`), so no per-provider conditionals belong in views.

Because dispatch is centralized, no checkout/view code needs to learn about the new class — it flows through `get_adapter(code)`.

---

## 5. Checkout, lifecycle, callback/verification, credentials, isolation

### 5.1 Checkout + order lifecycle
- `apps/orders/services/checkout_service.py` exposes `active_payment_gateways(store=...)` (~125) and selection helpers (`get_selected_payment_gateway` ~153, `set_shipping_method` ~141). It lists store-scoped, configured gateways.
- `apps/orders/services/lifecycle.py::apply_payment_success(...)` (~24) is the single transition that marks an order paid and releases downstream side effects.

### 5.2 Callback / verification flow — `apps/orders/services/gateway_payment_service.py`
- `initiate_payment(...)` (~84): produces a `PaymentAttempt` in `REDIRECT_READY` (online) or `SUCCEEDED` (COD) state.
- `process_callback_and_verify(...)` (~375): **idempotent** — if the attempt is already `SUCCEEDED` it returns immediately (~402) so duplicate callbacks are safe. A browser callback alone never proves payment; verification is server-to-server.
- `_apply_verified_payment(attempt_pk, result, store)` (~314): locks **order first, then attempt** via `select_for_update` (order ~324, attempt ~325), re-checks `attempt.status == SUCCEEDED` (~326) before applying — the lock-ordering + re-check guard against concurrent callbacks.
- `_record_discrepancy(...)` (~286) and `_open_reconciliation(...)` (~234): on ambiguous / amount-mismatch outcomes the attempt is set `SUCCEEDED` **but a `PaymentReconciliation` is opened and the order is NOT marked paid** (evidence preserved via `_sanitized_evidence` ~217). `_toman_from_rial` (~227) isolates the inverse conversion for evidence.

> Concurrency caveat: the `select_for_update` lock ordering is correct by construction, but it provides real row-level locking only on Postgres. On the SQLite test DB used here it is a no-op at the row level, so concurrency guarantees are **NOT verified on this platform**.

### 5.3 Credentials storage — `apps/orders/encryption.py`
- Fernet-based `encrypt_credential` / `decrypt_credential` / `mask_credential`, keyed by `PAYMENT_CREDENTIAL_KEY` (deliberately NOT Django `SECRET_KEY`).
- Fail-closed in production: missing/invalid key with `DEBUG=False` raises at import. A deterministic dev-only fallback key is used only under `DEBUG` (or the test-runner allowance flag). `PaymentGatewayConfig.get_credentials()/set_credentials()` store an encrypted JSON blob in `encrypted_credentials`.

### 5.4 Tenant isolation
- Every config/attempt is scoped by a `store` FK; `PaymentGatewayConfig` enforces one config per `(store, gateway_code)` via `uniq_gateway_config_per_store`. Checkout and dashboard querysets are store-scoped. CLAUDE.md mandates preserving tenant isolation, Store scoping, permissions and cross-host behavior — any new provider must keep this.

### 5.5 Idempotency protections (summary)
- `Order.idempotency_key` partial unique (when set).
- `PaymentAttempt`: partial unique on `idempotency_key` and on `gateway_track_id` (when set).
- `process_callback_and_verify` is idempotent on an already-`SUCCEEDED` attempt.
- `Refund.idempotency_key` partial unique (when set).

### 5.6 Retry / timeout behavior
- Zibal uses explicit `(10, 30)s` connect/read timeouts and wraps all `requests` exceptions into `GatewayConnectionError`. There is no automatic server-side retry loop; a failed verify leaves the attempt in a non-final state for a later callback/retry.

### 5.7 Inventory / payment interaction
- Successful payment application (via `lifecycle.apply_payment_success`) is where coupon redemption / reservation side effects are finalized; unsuccessful or reconciled-as-mismatch flows must not trigger those releases. (Coupon models: `CouponRedemption` ~1280.)

---

## 6. CRITICAL DISCREPANCY — Zarinpal and Manual Card-to-Card do NOT pre-exist

The mission brief (Section 4 / screenshot) claims three **existing** storefront methods: Zarinpal, COD, and Manual Card-to-Card. Verified on this base commit, that is **not accurate** for the storefront engine:

- `apps/orders/gateways/registry.py` registers **only** `"zibal"` and `"cod"` (`_ADAPTER_LOADERS` and `GATEWAY_CHOICES`).
- `PaymentGatewayConfig.GatewayCode` (models.py ~624) contains **only** `ZIBAL` and `COD`.
- Repo grep for `zarinpal` (case-insensitive) hits only:
  - `apps/content/tests/test_footer_config.py:350,619` (an unrelated footer-link fixture titled "ZarinPal"),
  - `apps/orders/gateways/__init__.py:4` (docstring: "future ZarinPal"),
  - `apps/stores/models.py:725` (a Persian comment listing ZarinPal/SnappPay/Zibal as examples that are *not* here).
- Repo grep for `card_to_card`, `destination_card`, `cardholder`, `manual_transfer` across `apps/**/*.py` returns **no matches**.

**Conclusion:** there is **no** storefront Zarinpal adapter and **no** manual card-to-card / offline bank-transfer adapter on this base commit. Therefore, in this mission Zarinpal and Manual Card Transfer must be **implemented** (Zarinpal online, Manual Card Transfer as an offline method following the COD pattern), honestly documented as **NOT pre-existing** — not falsely reported as "preserved." Only COD and Zibal are genuinely pre-existing and must be preserved. (Note: `apps/billing/providers/` has its own `manual.py`/`zibal.py` for the separate SaaS-billing engine; those are not the storefront engine and must not be conflated or modified.)

---

## 7. Missing capabilities

- **ABC lacks post-payment operations:** no `inquiry`, `cancel`, or `refund` methods on `PaymentGatewayAdapter`. Refunds exist as a model (`Refund`) and service but are not part of the adapter contract.
- **Only 2 adapters registered** (`zibal`, `cod`); the mission's 10-provider target is far from met.
- **Readiness is coarse:** `is_active` (bool) + presence of credentials. There is no richer "configured but not credentialed / documentation-blocked / sandbox-only" readiness state for the dashboard.
- **No capability declaration** on adapters (e.g. supports-inquiry, supports-refund, requires-manual-confirmation), so the UI cannot reason about what each provider can do.

---

## 8. Reusable components (lean on these, do not reinvent)

- `PaymentGatewayAdapter` ABC + result dataclasses + `GatewayError` hierarchy (`base.py`).
- The central registry (`registry.py`) — extend the two maps only.
- `encryption.py` Fernet helpers for every new provider's credentials.
- `gateway_payment_service.py` orchestration (locking, reconciliation, idempotency) — extend here, never put provider conditionals in views.
- `zibal.py` as the online template; `cod.py` as the offline template (Manual Card Transfer should follow the offline pattern).
- Dashboard finance wiring already iterates the registry, so new providers surface automatically once registered.

---

## 9. Security risks to respect

- Credentials must stay encrypted and never logged (follow Zibal/encryption patterns).
- Browser callback params must never be trusted as proof of payment — always server-to-server verify.
- Amount verification must raise `GatewayAmountMismatchError` with evidence; never mark paid on mismatch.
- New production integrations MUST default to **disabled** (`is_active` already defaults False) and must not be selectable at real checkout until configured; documentation-blocked providers must not be exposed as selectable.
- No real-money calls / no real provider endpoints in tests — use deterministic mocks + contract tests.

---

## 10. Proposed MINIMAL additive architecture changes

All additive; nothing that would break the green baseline or existing migrations:

1. **Extend the ABC additively** with optional capability declarations and optional `inquiry` / `cancel` / `refund` methods whose default implementation signals "unsupported" (so existing adapters need no change and dispatch stays backward compatible).
2. **Register new adapters** by adding loaders + `GATEWAY_CHOICES` entries in `registry.py` and new `GatewayCode` members in `models.py`, each with an additive migration numbered after `0019`.
3. **Implement Zarinpal** (online, Zibal-shaped) and **Manual Card Transfer** (offline, COD-shaped) as the first two new providers, documented as new — not preserved.
4. **Richer readiness state** surfaced through the existing dashboard registry iteration, without per-provider view conditionals.
5. **Contract tests + deterministic mocks** per provider; concurrency/row-lock tests explicitly marked NOT verified on SQLite.

### Backward-compatibility risks
- Changing `GatewayCode` or `GATEWAY_CHOICES` must remain purely additive (no renames/removals) to avoid breaking existing `PaymentGatewayConfig` rows and migrations.
- New ABC methods must have safe defaults so `ZibalAdapter`/`CodAdapter` keep passing without edits.
- Migrations must stay additive and numbered after `0019`; `makemigrations --check` must keep reporting "No changes detected" after each milestone.
- Tenant isolation, store scoping, permissions and cross-host behavior must be preserved per CLAUDE.md.
