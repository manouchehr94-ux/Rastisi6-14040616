# Provider Implementation Matrix

Purpose: an honest, per-provider record of **what was actually implemented**,
tested, and verified for the RastiSi storefront payment engine, using the
mission status vocabulary. This is the implementation-side companion to
`PROVIDER_RESEARCH_MATRIX.md` (which records the documentation research).

All provider HTTP is exercised with deterministic MOCKS and contract tests; no
real provider endpoint was ever contacted from this environment and no
real-money transaction was ever performed. No generic "integration complete"
claim is made anywhere in this document.

## Status vocabulary

| Status | Meaning |
|--------|---------|
| `IMPLEMENTED_AND_CONTRACT_TESTED` | A real adapter is implemented against a documented (or offline-by-design) contract and is covered by mocked contract tests. **No** authorized sandbox or live transaction evidence exists. |
| `SANDBOX_VERIFIED` | Additionally proven against the provider's real sandbox with authorized test evidence. **Not claimed for any provider here.** |
| `LIVE_VERIFIED` | Additionally proven with an authorized real-money production transaction. **Not claimed for any provider here.** |
| `NEEDS_CREDENTIALS` | Contract implemented, but the merchant has not yet supplied valid credentials. |
| `DOCUMENTATION_BLOCKED` | The provider's official current contract was unreachable/incomplete from this environment; only a registered skeleton exists. Never selectable at real checkout. |
| `PARTIALLY_IMPLEMENTED` | Some, but not all, documented capabilities are implemented. |

## Honest summary

- `zibal`, `zarinpal`, `cod`, `card_to_card` → **`IMPLEMENTED_AND_CONTRACT_TESTED`**.
  None is `SANDBOX_VERIFIED` or `LIVE_VERIFIED` (no authorized sandbox/live
  evidence is available in this environment).
- `pasargad`, `saman`, `parsian`, `mellat`, `sadad`, `tejarat` (PSP) and
  `snappay`, `torobpay` (BNPL) → **`DOCUMENTATION_BLOCKED`** (registered
  skeletons; never selectable at real checkout).

| # | Code | Category | Status | Adapter file | Contract tests | Sandbox | Production readiness |
|---|------|----------|--------|--------------|----------------|---------|----------------------|
| 1 | `zibal` | Facilitator | `IMPLEMENTED_AND_CONTRACT_TESTED` | `apps/orders/gateways/zibal.py` | `test_gateway_payment_service.py`, `test_payment_*` | Fixed `zibal` merchant (per docs); not exercised live | Needs authorized sandbox/live verification |
| 2 | `zarinpal` | Facilitator | `IMPLEMENTED_AND_CONTRACT_TESTED` | `apps/orders/gateways/zarinpal.py` | `test_zarinpal_adapter.py`, `test_payment_currency.py` | No verified sandbox host in docs read here | Needs authorized sandbox/live verification |
| 3 | `cod` | Offline | `IMPLEMENTED_AND_CONTRACT_TESTED` | `apps/orders/gateways/cod.py` | `test_cod_confirmation.py` | N/A (offline) | Operational (offline, manual confirm) |
| 4 | `card_to_card` | Offline | `IMPLEMENTED_AND_CONTRACT_TESTED` | `apps/orders/gateways/card_to_card.py` | `test_card_to_card.py` | N/A (offline) | Operational (offline, manual approval) |
| 5 | `pasargad` | PSP | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/pasargad.py` | `test_pasargad_adapter.py` | Not verified | Blocked |
| 6 | `saman` | PSP | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/saman.py` | `test_saman_adapter.py` | Not verified | Blocked |
| 7 | `parsian` | PSP | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/parsian.py` | `test_parsian_adapter.py` | Not verified | Blocked |
| 8 | `mellat` | PSP | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/mellat.py` | `test_mellat_adapter.py` | Not verified | Blocked |
| 9 | `sadad` | PSP | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/sadad.py` | `test_sadad_adapter.py` | Not verified | Blocked |
| 10 | `tejarat` | PSP (label) | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/tejarat.py` | `test_tejarat_adapter.py` | Not verified | Blocked |
| 11 | `snappay` | BNPL | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/snappay.py` | `test_snappay_adapter.py` | Not verified | Blocked |
| 12 | `torobpay` | BNPL | `DOCUMENTATION_BLOCKED` | `apps/orders/gateways/torobpay.py` | `test_torobpay_adapter.py` | Not verified | Blocked |

---

## 1. Zibal — `IMPLEMENTED_AND_CONTRACT_TESTED`

- **Documentation source + date:** `https://help.zibal.ir/ipg/` (reachable
  2026-11-03); historical `https://docs.zibal.ir/`.
- **API version:** Zibal IPG v1 (`/v1/request`, `/v1/verify`).
- **Adapter file:** `apps/orders/gateways/zibal.py`.
- **Implemented capabilities:** `CREATE`, `VERIFY`. Toman→Rial (×10) conversion
  isolated in the adapter; amount-mismatch raises `GatewayAmountMismatchError`
  with reconciliation evidence.
- **Unsupported capabilities:** `INQUIRE`, `CANCEL`, `REFUND`, `SETTLE` — no
  endpoint-level request/response contract was reachable, so they are not
  declared and raise `GatewayUnsupportedOperationError`.
- **Merchant credential requirements:** `merchant` (Merchant ID).
- **Contract test status:** mocked contract coverage via the gateway service
  tests and the payment safety/concurrency/discrepancy suites.
- **Sandbox test status:** fixed sandbox merchant `zibal` per docs; **not**
  exercised against a live sandbox in this environment.
- **Production readiness:** requires an authorized sandbox/live verification
  before production activation. `is_active` defaults `False`.
- **Known limitations:** refund/inquiry are platform features but lack a
  verified API contract here.
- **Next action:** obtain authorized sandbox credentials and run a sandbox
  transaction; read the refund/inquiry endpoint contract before declaring those
  capabilities.

## 2. Zarinpal — `IMPLEMENTED_AND_CONTRACT_TESTED`

- **Documentation source + date (all read 2026-11-03):**
  `https://www.zarinpal.com/docs/paymentGateway/connectToGateway`,
  `.../moreFeatures/currency`, `.../errorList`.
- **API version:** REST v4 (`/pg/v4/payment/request.json`,
  `/pg/v4/payment/verify.json`, `StartPay/{Authority}`).
- **Adapter file:** `apps/orders/gateways/zarinpal.py`.
- **Implemented capabilities:** `CREATE`, `VERIFY`. Amount normalized to
  integer Rial and `currency: "IRR"` sent explicitly on create (Toman→Rial ×10
  once, at the adapter boundary). Code `100` = success; `101` = already verified
  (idempotent); `-50` = amount mismatch → `GatewayAmountMismatchError`.
- **Unsupported capabilities:** `INQUIRE`, `CANCEL`, `REFUND`, `SETTLE` — the
  reachable pages reference a reverse family in the error list but expose no
  endpoint-level reverse/refund/inquiry request contract, so none is declared.
- **Merchant credential requirements:** `merchant_id` (exactly 36 characters).
- **Contract test status:** `apps/orders/tests/test_zarinpal_adapter.py` +
  `test_payment_currency.py` (create/verify serialization, 100/101, mismatch,
  credential leak, currency conversion).
- **Sandbox test status:** the docs read here exposed no dedicated sandbox host,
  so `supports_sandbox` is `False`; **no** sandbox transaction evidence.
- **Production readiness:** requires an authorized sandbox/live verification.
  `is_active` defaults `False`; no new production activation implied.
- **Known limitations:** reverse/refund not implemented; no sandbox host
  verified.
- **Next action:** run an authorized sandbox/live transaction; read the reverse
  endpoint contract before declaring `REFUND`/`CANCEL`.

## 3. COD (Cash on Delivery) — `IMPLEMENTED_AND_CONTRACT_TESTED`

- **Documentation source + date:** offline method by design (no external API).
- **API version:** N/A.
- **Adapter file:** `apps/orders/gateways/cod.py`.
- **Implemented capabilities:** none online by design; `is_online = False`,
  empty capability set. `verify_payment` returns `success=False` by design —
  the order is confirmed by a manual delivery/status transition, not a gateway.
- **Unsupported capabilities:** all online operations.
- **Merchant credential requirements:** none.
- **Contract test status:** `apps/orders/tests/test_cod_confirmation.py`.
- **Sandbox test status:** N/A (offline).
- **Production readiness:** operational (offline). Genuinely pre-existing on the
  base commit and preserved unchanged.
- **Known limitations:** no automatic money movement (by design).
- **Next action:** none required.

## 4. Manual Card-to-Card — `IMPLEMENTED_AND_CONTRACT_TESTED`

- **Documentation source + date:** offline method by design.
- **API version:** N/A.
- **Adapter file:** `apps/orders/gateways/card_to_card.py`.
- **Implemented capabilities:** none online by design; `is_online = False`,
  empty capability set. `verify_payment` returns `success=False` by design — a
  customer-submitted receipt never auto-verifies; a human merchant approval
  confirms the order.
- **Unsupported capabilities:** all online operations.
- **Merchant credential requirements:** `card_number` (16 digits, sensitive,
  stored encrypted), `cardholder_name`; optional `iban`, `bank_name`.
- **Contract test status:** `apps/orders/tests/test_card_to_card.py`.
- **Sandbox test status:** N/A (offline).
- **Production readiness:** operational (offline, manual approval). **NOT
  pre-existing** on the base commit — newly added by this mission.
- **Known limitations:** no server-to-server verification (by design).
- **Next action:** none required.

## 5–10. PSP skeletons — `DOCUMENTATION_BLOCKED`

`pasargad`, `saman`, `parsian`, `mellat`, `sadad`, `tejarat`.

- **Documentation source + date:** no authoritative CURRENT technical contract
  was reachable on 2026-11-03 (`behpardakht.com`, `pec.ir`, `sadadpsp.ir`,
  `irankish.com` timed out / reset; `sep.ir` was marketing-only; Pasargad only
  had community libraries). See `PROVIDER_RESEARCH_MATRIX.md` §§5–10.
- **API version:** not verified.
- **Adapter files:** `apps/orders/gateways/{pasargad,saman,parsian,mellat,sadad,tejarat}.py`.
- **Implemented capabilities:** none — each declares NO capabilities and raises
  `GatewayUnsupportedOperationError` from every money-moving method;
  `documentation_blocked = True`.
- **Unsupported capabilities:** all (CREATE/VERIFY/SETTLE/REFUND/INQUIRE/CANCEL).
- **Merchant credential requirements:** field NAMES only (not an assertion of
  the unverified contract), e.g. `mellat`: `terminal_id`, `username`,
  `password`; `sadad`: `merchant_id`, `terminal_id`, `key`; `tejarat`:
  `terminal_id` placeholder (display label only — technical PSP unconfirmed).
- **Contract test status:** `apps/orders/tests/test_{...}_adapter.py` assert the
  skeleton is registered, `documentation_blocked`, declares no capabilities, and
  raises on every operation.
- **Sandbox / production readiness:** blocked; never selectable at real checkout
  (readiness derives to `DOCUMENTATION_BLOCKED`).
- **Known limitations:** entire contract unverified.
- **Next action:** obtain each provider's official current contract, then
  implement and contract-test real adapters; for Mellat, SETTLE must be a
  DISTINCT capability (never conflated with verify); for Tejarat, confirm the
  real technical PSP before building.

## 11–12. BNPL skeletons — `DOCUMENTATION_BLOCKED`

`snappay`, `torobpay`.

- **Documentation source + date:** no official current API documentation was
  reachable on 2026-11-03 (SnappPay academy shell empty; TorobPay only a
  WordPress/community plugin — non-authoritative). See
  `PROVIDER_RESEARCH_MATRIX.md` §§3–4.
- **API version:** not verified.
- **Adapter files:** `apps/orders/gateways/{snappay,torobpay}.py`.
- **Implemented capabilities:** none — `documentation_blocked = True`, no
  capabilities declared, and `check_bnpl_eligibility` raises
  `GatewayUnsupportedOperationError` (installment offers never fabricated).
- **Unsupported capabilities:** all, including BNPL eligibility and SETTLE.
- **Merchant credential requirements:** field NAMES only: `client_id`,
  `client_secret`.
- **Contract test status:** `apps/orders/tests/test_{snappay,torobpay}_adapter.py`.
- **Sandbox / production readiness:** blocked; never selectable at real checkout.
- **Known limitations:** entire contract (OAuth, eligibility, installment
  terms, settle) unverified. BNPL settle is a DISTINCT capability-gated step in
  the orchestrator; a real BNPL adapter must declare and implement `SETTLE`
  before it can be routed.
- **Next action:** obtain official BNPL contracts, then implement OAuth +
  eligibility + create/verify/settle and contract-test before enabling.
