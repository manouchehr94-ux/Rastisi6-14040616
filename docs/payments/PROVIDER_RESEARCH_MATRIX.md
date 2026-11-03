# Provider Research Matrix

Purpose: record the **verified** technical contract for each of the 10 mission
providers, with official documentation URLs and verification dates. Where a
provider's official current contract is **unreachable or incomplete** from this
environment, it is marked `DOCUMENTATION_BLOCKED` with the exact gap recorded.

## Rules honored in this matrix

- **No invention.** Endpoints, request/response signatures, error codes, and
  sandbox credentials are recorded ONLY when read from an official, reachable
  source. Anything not verified is left as `DOCUMENTATION_BLOCKED` /
  "not verified", never fabricated.
- **Community sources are non-authoritative.** WordPress plugins (e.g. TorobPay)
  and community libraries (e.g. Pasargad/Dorsa helpers) are labeled as
  non-authoritative evidence and never used to assert an official contract.
- **Display label ≠ technical identity.** A storefront display name is kept
  separate from the actual technical PSP that settles the transaction.
- **Currency.** The application stores amounts in Toman (IRT, `decimal_places=0`).
  Most Iranian PSP APIs operate in Rial (IRR). Any Toman→Rial (×10) conversion
  is isolated inside the adapter.

Verification environment: this sandbox has **no external network access to
provider APIs**. Only two official docs were reachable via `web_fetch`:
Zarinpal `https://www.zarinpal.com/docs/paymentGateway/` and Zibal
`https://help.zibal.ir/ipg/`. All other official provider docs were not
reachable from here.

Verification date for all entries below: **2026-11-03**.

Base-commit reality check (verified in `apps/orders/gateways/registry.py`): the
storefront registry currently registers ONLY `zibal` and `cod`. There is no
`zarinpal` adapter and no manual card-to-card adapter yet; those are future
mission work and are documented here as NOT pre-existing on this base commit.

---

## Summary table

| # | Display / provider | Technical PSP / type | Status | Official doc reachable here |
|---|--------------------|----------------------|--------|-----------------------------|
| 1 | Zarinpal           | Facilitator (IPG aggregator) | VERIFIED (REST v4 contract; adapter implemented, FEAT-003) | Yes (landing + connectToGateway + currency + errorList) |
| 2 | Zibal              | Facilitator / aggregator | VERIFIED (implemented adapter) | Yes |
| 3 | TorobPay           | BNPL (Torob)         | DOCUMENTATION_BLOCKED | No (only community/WP plugin evidence) |
| 4 | SnappPay           | BNPL (Snapp!)        | DOCUMENTATION_BLOCKED | No |
| 5 | Pasargad           | PSP — Bank Pasargad (PEP / Pasargad e-Payment) | DOCUMENTATION_BLOCKED | No (only community libs) |
| 6 | Saman              | PSP — Saman / Sep    | DOCUMENTATION_BLOCKED | No |
| 7 | Parsian            | PSP — Parsian / Pec  | DOCUMENTATION_BLOCKED | No |
| 8 | Mellat             | PSP — Behpardakht Mellat | DOCUMENTATION_BLOCKED | No |
| 9 | Sadad              | PSP — Sadad (Bank Melli) | DOCUMENTATION_BLOCKED | No |
| 10| Tejarat (display)  | SEE §Tejarat — technical PSP to be confirmed (IranKish not assumed) | DOCUMENTATION_BLOCKED | No |

---

## 1. Zarinpal — VERIFIED (REST v4, implemented in FEAT-003)

- **Type:** Payment facilitator / aggregator (routes card payments over the
  Shaparak/Shetab network). Acts as an IPG for merchants ("پذیرنده").
- **Official docs read and verified on 2026-11-03:**
  - `https://www.zarinpal.com/docs/paymentGateway/` (landing — concepts).
  - `https://www.zarinpal.com/docs/paymentGateway/connectToGateway` (request /
    redirect / callback / verify flow and field tables).
  - `https://www.zarinpal.com/docs/paymentGateway/moreFeatures/currency`
    (currency selection).
  - `https://www.zarinpal.com/docs/paymentGateway/errorList` (status/error codes).
- **Verified contract (implemented in `apps/orders/gateways/zarinpal.py`):**
  - `merchant_id`: unique 36-character merchant code (validated for length).
  - `Authority`: unique UUID-form reference (36 chars, RFC form, starts with
    `A`) returned per purchase request; used as the adapter `track_id`.
  - `ref_id`: unique transaction id returned after a **successful** payment.
  - **create_payment** → `POST https://payment.zarinpal.com/pg/v4/payment/request.json`
    with `{merchant_id, amount (Integer), currency, callback_url, description,
    metadata.order_id}`. Response (on success) carries `data.code == 100` and
    `data.authority`.
  - **build_redirect_url** → `https://payment.zarinpal.com/pg/StartPay/{Authority}`.
  - **Callback**: Zarinpal appends a `Status` querystring of `OK`/`NOK`; verify
    is only meaningful when `Status == OK`.
  - **verify_payment** → `POST .../pg/v4/payment/verify.json` with
    `{merchant_id, amount (Integer, RIAL), authority}`. Response: `data.code`,
    `ref_id` (Integer), `card_pan` (masked), `card_hash`, `fee_type`, `fee`.
  - **Codes:** `100` success (occurs exactly once per transaction); a later
    verify of the SAME transaction returns `101` = already verified (also a
    successful, idempotent state). `-50` = verify amount mismatch; `-51` =
    unsuccessful payment; `-54` = invalid authority (full list in errorList).
  - **Currency (financial safety):** the official currency page documents a
    `currency` field of `IRR` (Rial) or `IRT` (Toman); the verify page
    specifies the verify `amount` is **in Rial**. RastiSi stores order amounts
    in **Toman** (`Order.grand_total` is `DecimalField(decimal_places=0)`,
    labeled تومان). The adapter converts Toman → Rial (×10) exactly once at the
    adapter boundary and **explicitly sends `currency = "IRR"`** on create, so
    `amount` is unambiguously Rial and there is no double conversion anywhere.
  - Timeouts: explicit `(connect=10, read=30)` seconds. Credentials never
    logged. Amount-mismatch on a confirmed payment raises
    `GatewayAmountMismatchError` with reconciliation evidence.
- **Capabilities declared:** `CREATE`, `VERIFY` only (category FACILITATOR).
- **inquire / cancel / refund / settle:** the error list references a
  PaymentReverse family (`-60..-63`), but the reachable pages do not expose an
  endpoint-level reverse/refund/inquiry request contract, so those operations
  are **not** implemented or declared and remain not-yet-verified at the API
  level.
- **documentation_blocked:** `False` — the REST v4 contract is officially
  documented. **No sandbox/live test evidence exists in this environment**, so
  the integration is NOT marked `SANDBOX_VERIFIED` / `LIVE_VERIFIED` /
  production-ready; `is_active` still defaults to `False` and no new production
  activation is implied.
- **Pre-existence:** NO Zarinpal adapter existed in the storefront registry on
  the base commit; this is a NEW implementation (FEAT-003), not a preserved one.

## 2. Zibal — VERIFIED (implemented)

- **Type:** Payment facilitator / aggregator.
- **Official doc:** `https://help.zibal.ir/ipg/` (reachable 2026-11-03);
  historical reference `https://docs.zibal.ir/` cited in the adapter.
- **Implemented contract (see `apps/orders/gateways/zibal.py`):**
  - Base: `https://gateway.zibal.ir`.
  - `create_payment` → `POST /v1/request` with
    `{merchant, amount, callbackUrl, orderId, description?}`.
  - `build_redirect_url` → `https://gateway.zibal.ir/start/{trackId}`.
  - `verify_payment` → `POST /v1/verify` with `{merchant, trackId}`.
  - Result codes: `100` success, `201` already verified; payment status `1`
    paid, `2` already verified.
  - **Currency:** API is in **Rial**; the app stores **Toman**, so the adapter
    converts Toman→Rial (×10) and performs amount-mismatch verification against
    the expected Rial amount.
  - Sandbox: fixed merchant value `zibal` per Zibal docs.
  - Timeouts: explicit `(connect=10, read=30)` seconds.
  - Credentials: `merchant` (never logged).
  - Amount-mismatch on a confirmed payment raises `GatewayAmountMismatchError`
    carrying reconciliation evidence; money may have moved so the order is not
    marked paid.
- **Capabilities declared:** `CREATE`, `VERIFY` only (category FACILITATOR).
- **inquire / cancel / refund / settle:** the Zibal product site lists refund
  ("استرداد وجه") and inquiry web-services as platform features, but the IPG
  landing page `https://help.zibal.ir/ipg/` (re-read on 2026-11-03 during
  FEAT-003) still does not expose their endpoint-level request/response
  contract, so these are **not** implemented or declared by the adapter and are
  recorded as not-yet-verified at the API level. The optional backward-compatible
  Zibal `inquire_payment` enhancement is therefore **NOT** added in FEAT-003
  (no documented inquiry endpoint reachable); Zibal's existing create/verify
  behavior and tests are left unchanged.

## 3. TorobPay — DOCUMENTATION_BLOCKED

- **Type:** BNPL (buy-now-pay-later) tied to the Torob price-comparison platform.
- **Gap:** no official current API documentation was reachable from this
  environment. The only readily available integration evidence is a **WordPress
  plugin / community** integration, which is **non-authoritative** and must not
  be used to assert an official contract. Technical PSP routing, endpoints,
  auth, currency unit, error codes, sandbox, and eligibility/settlement rules
  are **not verified**. Must not be selectable at real checkout until the
  official BNPL contract is obtained.

## 4. SnappPay — DOCUMENTATION_BLOCKED

- **Type:** BNPL operated under the Snapp! ecosystem.
- **Gap:** no official current API documentation reachable from this
  environment. Endpoints, OAuth/token auth, eligibility API, installment terms,
  currency unit, error codes, and sandbox are **not verified**. Not selectable
  at real checkout until the official contract is obtained.

## 5. Pasargad — DOCUMENTATION_BLOCKED

- **Type:** PSP — Bank Pasargad electronic payment (commonly "PEP" / Pasargad
  e-Payment).
- **Gap:** official current docs not reachable here. Available evidence is
  **community libraries** (e.g. Dorsa/Pasargad helpers), which are
  **non-authoritative**. RSA signing scheme, endpoint URLs, token/sign/verify
  flow, currency unit, error codes, and sandbox are **not verified**.

## 6. Saman — DOCUMENTATION_BLOCKED

- **Type:** PSP — Saman Electronic Payment (Sep).
- **Gap:** official current docs not reachable here. Token request, redirect,
  verify/reverse endpoints, currency unit, error codes, and sandbox **not
  verified**.

## 7. Parsian — DOCUMENTATION_BLOCKED

- **Type:** PSP — Parsian e-Commerce (Pec), SOAP-style historically.
- **Gap:** official current docs not reachable here. Pin/auth, SOAP/REST
  endpoints, confirm/reverse flow, currency unit, error codes, and sandbox
  **not verified**.

## 8. Mellat — DOCUMENTATION_BLOCKED

- **Type:** PSP — Behpardakht Mellat.
- **Gap:** official current docs not reachable here. `bpPayRequest`-style
  endpoints, terminalId/username/password auth, verify/settle/reverse flow,
  currency unit, error codes, and sandbox **not verified**.

## 9. Sadad — DOCUMENTATION_BLOCKED

- **Type:** PSP — Sadad Informatics (Bank Melli Iran).
- **Gap:** official current docs not reachable here. Key/merchant signing,
  request/verify endpoints, currency unit, error codes, and sandbox **not
  verified**.

## 10. Tejarat — DOCUMENTATION_BLOCKED (special handling)

- **Display label vs technical identity:** "Tejarat" here is a **display label**
  (associated with Bank Tejarat). The actual PSP that technically processes the
  transaction is a **separate question** and must be confirmed from an official
  source before any adapter is built.
- **IranKish investigated, not assumed:** IranKish (کارت اعتباری ایران کیش) is a
  frequently associated PSP, but this matrix does **not** assume IranKish is the
  processor for a "Tejarat" storefront option. No official source confirming the
  Tejarat↔PSP mapping was reachable from this environment.
- **Gap:** the real technical PSP, its endpoints, auth, currency unit, error
  codes, signing, and sandbox are **not verified**. Keep the storefront display
  label ("Tejarat") strictly separate from the technical provider identity in
  any future implementation. Not selectable at real checkout until confirmed.

---

## Cross-cutting items to verify per provider before implementation

For every `DOCUMENTATION_BLOCKED` / `PARTIAL` provider above, the following must
be read from an official, current source (never inferred) before an adapter is
written or marked selectable at real checkout:

- Actual technical PSP and API version, with evidence of currency (IRR vs IRT).
- Authentication protocol (merchant id / terminal credentials / OAuth / signing).
- Sandbox availability and exact sandbox base URLs/credentials.
- create / redirect / callback / verify / finalize / inquire / cancel / refund
  / settle endpoint URLs and request/response schemas.
- Error-code catalog and their meanings.
- Idempotency semantics and any request signing/encryption.
- Callback-domain / server-IP allowlisting constraints.
- Settlement timing and any separate settle/capture step.
