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
| 1 | Zarinpal           | Facilitator (IPG aggregator) | PARTIAL (landing verified; endpoint detail pages not machine-readable) | Yes (landing) |
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

## 1. Zarinpal — PARTIAL

- **Type:** Payment facilitator / aggregator (routes card payments over the
  Shaparak/Shetab network). Acts as an IPG for merchants ("پذیرنده").
- **Official doc:** `https://www.zarinpal.com/docs/paymentGateway/`
  (landing page reachable and read on 2026-11-03).
- **Verified from the landing page (concepts only):**
  - `merchant_id`: unique 36-character merchant code issued per gateway.
  - `Authority`: a unique UUID-form reference (36 chars, RFC form, starts with
    `A`) returned per purchase request.
  - `ref_id`: unique transaction id returned after a **successful** payment,
    used for financial tracking.
  - `Code`: numeric transaction-status indicator returned by the web service.
  - `callback_url`: return URL the buyer is redirected to after payment.
  - Optional `mobile` and `email` buyer parameters; `description`.
  - **IP constraint:** merchant must register the main server IP with Zarinpal.
  - Transport: HTTPS/SSL; the merchant and Zarinpal never receive the buyer's
    card/PIN/balance (entered only on the gateway).
- **Gaps (why PARTIAL, not fully verified):** the request/verify endpoint detail
  pages (`.../paymentRequest.html`, `.../guide/`, the REST v4 reference) returned
  no machine-readable content from this environment, so the exact endpoint URLs,
  JSON request/response schemas, the full `Code` error-code list, the
  amount/currency unit (IRR vs IRT) expected by the request call, sandbox base
  URL, and any idempotency/signing details were **not** verifiable here and are
  deliberately NOT recorded. Resolve before implementing a Zarinpal adapter.
- **create / redirect / callback / verify:** conceptually documented (purchase
  request → redirect to Zarinpal → callback with Authority → verify) but exact
  contract pending the gaps above.
- **inquire / cancel / refund / settle:** not verified from the reachable page.
- **Pre-existence:** NO Zarinpal adapter exists in the storefront registry on
  this base commit.

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
  landing page read here does not expose their endpoint-level request/response
  contract, so these are **not** implemented or declared by the adapter and are
  recorded as not-yet-verified at the API level.

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
