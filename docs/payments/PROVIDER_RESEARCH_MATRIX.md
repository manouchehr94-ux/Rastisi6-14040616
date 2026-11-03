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

### FEAT-004 research pass (2026-11-03) — re-verification result

The 8 remaining online providers (6 PSPs + 2 BNPL) were re-checked via
`web_fetch` against their mission entry-point URLs. Result of this pass:

- `https://www.sep.ir/` (Saman/SEP) — **reachable, but marketing-only**. The
  landing page describes the SEP internet-payment product in prose and exposes
  NO technical contract (no token/redirect/verify endpoint URLs, no
  request/response schemas, no currency unit, no error codes, no sandbox).
- `https://www.behpardakht.com/` (Mellat) — **unreachable** (request timeout).
- `https://pec.ir/` (Parsian) — **unreachable** (request timeout).
- `https://sadadpsp.ir/` (Sadad) — **unreachable** (request timeout).
- `https://irankish.com/` (Tejarat investigation) — **unreachable**
  (connection reset). The Tejarat↔PSP mapping remains unconfirmed; IranKish is
  NOT assumed.
- `https://academy.snapppay.ir/self-cms/` (SnappPay) — reachable only as an
  empty/listing shell; NO API contract (endpoints/OAuth/eligibility/installment
  terms/error codes/sandbox) exposed.
- `https://github.com/pep-ipg/Dorsa-IPG-pasargad` (Pasargad) and
  `https://wordpress.org/plugins/torobpay-for-woocommerce/` (TorobPay) — remain
  COMMUNITY / NON-authoritative evidence only; not used to assert any official
  contract.

Conclusion (FIRST pass): no authoritative CURRENT technical contract for any of
the 8 providers was obtainable in this environment, so each was implemented as a
`DOCUMENTATION_BLOCKED` skeleton.

> **CORRECTION — superseded by the SECOND investigation (see the next section).**
> The blanket sentence above ("no authoritative CURRENT technical contract for
> any of the 8 providers was obtainable") was the FIRST-pass conclusion. It is
> now **false for three providers**: a reachable, publisher-level contract was
> obtained on 2026-11-03 for **Pasargad/Dorsa**, **SnappPay**, and **TorobPay**,
> and each now has a REAL, contract-tested adapter (`documentation_blocked =
> False`). The statement remains accurate ONLY for the five remaining PSPs
> (Saman, Parsian, Mellat, Sadad, Tejarat). This block is kept rather than
> deleted so the record of the correction is explicit.

Base-commit reality check (verified in `apps/orders/gateways/registry.py` on the
base commit `7d311556`): the storefront registry registered ONLY `zibal` and
`cod` on base. There was no `zarinpal` adapter and no manual card-to-card adapter
on base; those were ADDED by this branch and are NOT pre-existing on the base
commit.

### SECOND investigation (2026-11-03) — reachability re-attempt and reclassification

This round re-attempted every official/publisher source and recorded the honest
outcome. **Three contracts became reachable and are now implemented; five PSP
official docs remain unreachable.**

Reachable, publisher-level contracts obtained on 2026-11-03 (now implemented):

- **Pasargad / Dorsa IPG** — publisher `pep-ipg` (Pasargad e-Payment):
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/api-reference.md`
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/usage-guides.md`
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/error-codes.md`
  - Recorded as the Dorsa IPG REST contract (username/password + Bearer token,
    NOT RSA). Implemented in `apps/orders/gateways/pasargad.py`.
- **SnappPay** — `https://academy.snapppay.ir/self-cms` (REST API v2.1, BNPL
  lifecycle: OAuth token → eligibility → payment token → verify → settle →
  cancel/status). Implemented in `apps/orders/gateways/snappay.py`.
- **TorobPay** — provider-published WooCommerce plugin source
  `https://plugins.svn.wordpress.org/torobpay-for-woocommerce/trunk/class-torobpay-api.php`
  (same Snapp-ecosystem BNPL endpoint PATHS; OAuth password grant). Implemented
  NATIVELY in Django in `apps/orders/gateways/torobpay.py` with NO WordPress /
  PHP dependency added.

Still unreachable on 2026-11-03 (kept `DOCUMENTATION_BLOCKED`, `documentation_blocked = True`):

| Provider | URL attempted (this round) | Outcome | Specific missing contract detail |
|----------|----------------------------|---------|----------------------------------|
| Saman (SEP) | `https://www.sep.ir/` | Reachable, **marketing-only** (services described in prose) | No token/redirect/verify endpoint URLs, no request/response schema, no currency unit, no error codes, no sandbox |
| Saman (SEP) | `https://sep.shaparak.ir/` | Timeout (historical) | same as above |
| Parsian (PEC) | `https://pec.ir/` | **Timeout** | SOAP/REST endpoints, pin/auth, confirm/reverse flow, currency unit, error codes, sandbox |
| Mellat | `https://www.behpardakht.com/` | **Timeout** | `bpPayRequest`-style endpoints, terminalId/username/password auth, verify/settle/reverse flow, currency unit, error codes, sandbox |
| Sadad (Bank Melli) | `https://sadadpsp.ir/` | **Timeout** | key/merchant signing, request/verify endpoints, currency unit, error codes, sandbox |
| Tejarat (display label) | `https://irankish.com/` | **Connection reset (ECONNRESET)** | technical PSP mapping unconfirmed (IranKish NOT assumed); endpoints, auth, signing, currency unit, error codes, sandbox all unverified |

None of the five invented endpoints/signatures/error-codes were introduced. Each
of the five keeps `documentation_blocked = True` and derives
`DOCUMENTATION_BLOCKED`, so none is selectable at real checkout.

---

## Summary table

| # | Display / provider | Technical PSP / type | Status | Official doc reachable here |
|---|--------------------|----------------------|--------|-----------------------------|
| 1 | Zarinpal           | Facilitator (IPG aggregator) | VERIFIED (REST v4 contract; adapter implemented, FEAT-003) | Yes (landing + connectToGateway + currency + errorList) |
| 2 | Zibal              | Facilitator / aggregator | VERIFIED (implemented adapter) | Yes |
| 3 | TorobPay           | BNPL (Torob)         | IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real adapter) | Yes — provider-published WooCommerce plugin source (2026-11-03) |
| 4 | SnappPay           | BNPL (Snapp!)        | IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real adapter) | Yes — academy.snapppay.ir/self-cms REST v2.1 (2026-11-03) |
| 5 | Pasargad           | PSP — Bank Pasargad (PEP / Dorsa IPG) | IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real adapter) | Yes — pep-ipg Dorsa IPG docs (2026-11-03) |
| 6 | Saman              | PSP — Saman / Sep    | DOCUMENTATION_BLOCKED (skeleton impl. FEAT-004) | Landing only (marketing, no contract) |
| 7 | Parsian            | PSP — Parsian / Pec  | DOCUMENTATION_BLOCKED (skeleton impl. FEAT-004) | No |
| 8 | Mellat             | PSP — Behpardakht Mellat | DOCUMENTATION_BLOCKED (skeleton impl. FEAT-004) | No |
| 9 | Sadad              | PSP — Sadad (Bank Melli) | DOCUMENTATION_BLOCKED (skeleton impl. FEAT-004) | No |
| 10| Tejarat (display)  | SEE §Tejarat — technical PSP to be confirmed (IranKish not assumed) | DOCUMENTATION_BLOCKED (skeleton impl. FEAT-004) | No |

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

## 3. TorobPay — IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real adapter, FEAT-003)

- **Type:** BNPL (buy-now-pay-later) under the Snapp! / Torob ecosystem.
- **Contract source + date (2026-11-03):** provider-published WooCommerce plugin
  source `https://plugins.svn.wordpress.org/torobpay-for-woocommerce/trunk/class-torobpay-api.php`.
  This is the provider's own published client; it was read to extract endpoint
  PATHS, auth scheme, and currency unit. No WordPress / PHP dependency is added;
  the adapter is implemented natively in Django.
- **Verified contract (implemented in `apps/orders/gateways/torobpay.py`):**
  - Base host `https://cpg.torobpay.com` (plugin `get_api_base_url` default).
  - OAuth: `POST api/online/v1/oauth/token` with `grant_type=password`,
    `scope=online-merchant`, username/password, `Authorization: Basic
    base64(client_id:client_secret)`; bearer TTL from `expires_in` (default
    3300s); on HTTP 401 the token is dropped and re-auth is attempted exactly
    once.
  - `check_bnpl_eligibility` → `GET api/online/offer/v1/eligible?amount=<IRR>`;
    returns the provider payload verbatim (installment terms never fabricated).
  - `create_payment` → `POST api/online/payment/v1/token` with `{amount (IRR),
    paymentMethodTypeDto:'INSTALLMENT', returnURL, transactionId, cartList[],
    discountAmount}`; response carries `paymentPageUrl` + payment token.
  - `verify_payment` → `POST api/online/payment/v1/verify {paymentToken}`.
  - `settle_payment` → `POST api/online/payment/v1/settle {paymentToken}` — a
    DISTINCT finalize step, capability-gated in the orchestrator before the order
    is marked paid.
  - `cancel_payment` → `POST api/online/payment/v1/cancel {paymentToken}`.
  - `inquire_payment` → `GET api/online/payment/v1/status` (SETTLE/CANCEL/VERIFY/
    PENDING/REVERT mapping).
  - **Currency:** amounts are IRR (Rial); Toman→Rial (×10) is isolated once at
    the adapter boundary; amount mismatch raises `GatewayAmountMismatchError`
    with evidence.
- **Capabilities declared:** `CREATE, VERIFY, SETTLE, CANCEL, INQUIRE`.
  `update`/`revert` intentionally NOT declared (revert not required; update is a
  multi-item follow-up).
- **Merchant credential requirements:** `client_id`, `client_secret`,
  `client_username`, `client_password` (Basic header + password-grant).
- **Contract test status:** `apps/orders/tests/test_torobpay_adapter.py`
  (deterministic mocked HTTP): OAuth + 401 re-auth, eligibility, create/verify/
  settle/cancel/status, amount mismatch, capabilities set, category BNPL,
  `documentation_blocked False`.
- **Sandbox / production readiness:** NOT sandbox- or live-verified here. The
  merchant must supply credentials and have the server IP whitelisted and the
  `returnURL` match the whitelisted base; `is_active` defaults `False`. Readiness
  derives `NOT_CONFIGURED` with no creds (→ `NEEDS_CREDENTIALS` when partial).

## 4. SnappPay — IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real adapter, FEAT-003)

- **Type:** BNPL operated under the Snapp! ecosystem.
- **Contract source + date (2026-11-03):** `https://academy.snapppay.ir/self-cms`
  (REST API v2.1, BNPL lifecycle).
- **Verified contract (implemented in `apps/orders/gateways/snappay.py`):**
  - Base host `https://api.snapppay.ir` (overridable; SnappPay provisions the
    stage/production host per-merchant).
  - OAuth: `POST /api/online/v1/oauth/token` (JWT, 3600s expiry, not cached
    beyond expiry; `Authorization: Basic base64(client_id:client_secret)`).
  - `check_bnpl_eligibility` → `GET /api/online/offer/v1/eligible?amount=<IRR>`;
    returns the provider payload verbatim (never computes installments
    client-side, per the doc).
  - `create_payment` → `POST /api/online/payment/v1/token` with `{amount (IRR),
    discountAmount, externalSourceAmount, mobile, returnURL, transactionId,
    cartList[]}`; response carries `paymentPageUrl` + payment token.
  - `verify_payment` → `POST /api/online/payment/v1/verify` with the documented
    30s read budget and a status fallback (`GET /api/online/payment/v1/status`;
    PENDING → re-verify; VERIFY/SETTLE → accept; else fail).
  - `settle_payment` → `POST /api/online/payment/v1/settle` — DISTINCT finalize,
    capability-gated in the orchestrator.
  - `cancel_payment` → `POST /api/online/payment/v1/cancel`;
    `inquire_payment` → `GET /api/online/payment/v1/status`.
  - **Currency:** IRR (Rial); Toman→Rial (×10) isolated once; amount mismatch
    raises `GatewayAmountMismatchError` with evidence.
- **Capabilities declared:** `CREATE, VERIFY, SETTLE, CANCEL, INQUIRE`.
  `update`/`revert` intentionally NOT declared.
- **Merchant credential requirements:** `client_id`, `client_secret`.
- **Contract test status:** `apps/orders/tests/test_snappay_adapter.py`
  (deterministic mocked HTTP) covering OAuth + 401 re-auth, eligibility, create/
  verify/settle/cancel/status, amount mismatch, capabilities, category BNPL,
  `documentation_blocked False`.
- **Sandbox / production readiness:** NOT sandbox- or live-verified here
  (SnappPay grants stage access first, production after a demo). Needs merchant
  credentials + IP whitelisting; `is_active` defaults `False`; readiness derives
  `NOT_CONFIGURED`/`NEEDS_CREDENTIALS` until configured.

## 5. Pasargad — IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS (real Dorsa IPG adapter, FEAT-002)

- **Type:** PSP — Bank Pasargad electronic payment (PEP), Dorsa IPG.
- **Contract source + date (2026-11-03, publisher `pep-ipg`):**
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/api-reference.md`
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/usage-guides.md`
  - `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/error-codes.md`
  - Recorded as the Dorsa IPG REST contract. The REAL contract uses
    username/password + Bearer token, NOT RSA signing; the earlier RSA
    assumption is corrected.
- **Verified contract (implemented in `apps/orders/gateways/pasargad.py`):**
  - Base host `https://pep.shaparak.ir/dorsa1`.
  - `getToken` → `POST /token/getToken {username, password}` → Bearer (10-min);
    on 401 re-authenticate; adapter is stateless (fresh token per call).
  - `create_payment` → `POST /api/payment/purchase` with `{amount (Rial),
    invoice (=order_code), invoiceDate (Jalali), serviceCode,
    serviceType:'PURCHASE', callbackApi, terminalNumber}`; success →
    `data.{urlId, url}`.
  - `build_redirect_url` → `data.url` (`pep.shaparak.ir/dorsa1/{urlId}`;
    merchant-domain `Referer` required by the provider, noted in docstring).
  - `verify_payment` → `POST /api/payment/payment-inquiry {invoiceId}` to read
    authoritative status+amount, then `POST /api/payment/verify-transactions
    {invoice, urlId}` to finalize (auto-reverts if not called within the
    deadline). Inquiry status 0/13029/13034 → paid; 13033/13025/2/other → not
    paid.
  - `inquire_payment` → payment-inquiry; `cancel_payment` → `POST
    /api/payment/reverse-transactions {invoice, urlId}`.
  - **Currency:** IRR (Rial); Toman→Rial (×10) isolated once; amount mismatch
    raises `GatewayAmountMismatchError` with evidence.
  - Self-contained Gregorian→Jalali helper added (no new pip dependency).
- **Capabilities declared:** `CREATE, VERIFY, INQUIRE, CANCEL`. `REFUND`/`SETTLE`
  intentionally NOT declared (no documented refund-after-settlement endpoint
  beyond reverse-within-deadline). VERIFY (not CONFIRM) is the finalize step.
- **Merchant credential requirements:** `username`, `password`, `terminalNumber`,
  `serviceCode` (default 8, configurable). RSA private key NOT required.
- **Contract test status:** `apps/orders/tests/test_pasargad_adapter.py`
  (deterministic mocked HTTP) covering token + 401 re-auth, create, verify
  happy-path, amount mismatch, unsuccessful/reversed inquiry, inquire/cancel,
  capabilities, category PSP, `documentation_blocked False`.
- **Sandbox / production readiness:** NOT sandbox- or live-verified here. Needs
  merchant credentials + terminal + IP whitelisting; `is_active` defaults
  `False`; readiness derives `NOT_CONFIGURED`/`NEEDS_CREDENTIALS` until
  configured.

## 6. Saman — DOCUMENTATION_BLOCKED

- **Type:** PSP — Saman Electronic Payment (Sep).
- **Gap (re-confirmed 2026-11-03):** the `https://www.sep.ir/` landing page is
  reachable but **marketing-only** — it lists products ("درگاه پرداخت اینترنتی
  سپ", "کارت‌خوان سپ", app 724) in prose and exposes NO technical contract (no
  token/redirect/verify endpoint URLs, no request/response schema, no currency
  unit, no error codes, no sandbox). `https://sep.shaparak.ir/` timed out.
  Legacy examples are not assumed to match current terminals.
- **FEAT-004 adapter:** `apps/orders/gateways/saman.py` — category PSP,
  `documentation_blocked = True`, declares NO capabilities, raises
  `GatewayUnsupportedOperationError` from create/build_redirect/verify. Required
  credential FIELD NAME only: `terminal_id`.

## 7. Parsian — DOCUMENTATION_BLOCKED

- **Type:** PSP — Parsian e-Commerce (Pec), SOAP-style historically.
- **Gap (re-confirmed 2026-11-03):** official current docs not reachable here
  (`https://pec.ir/` timed out again this round). Pin/auth, SOAP/REST endpoints,
  confirm/reverse flow, currency unit, error codes, and sandbox **not
  verified**.
- **FEAT-004 adapter:** `apps/orders/gateways/parsian.py` — category PSP,
  `documentation_blocked = True`, declares NO capabilities, raises
  `GatewayUnsupportedOperationError` from create/build_redirect/verify. Required
  credential FIELD NAME only: `login_account`. When the WSDL/contract becomes
  reachable, implement a maintainable tested SOAP/REST client and verify token
  create/confirm/reverse before declaring any capability.

## 8. Mellat — DOCUMENTATION_BLOCKED

- **Type:** PSP — Behpardakht Mellat.
- **Gap (re-confirmed 2026-11-03):** official current docs not reachable here
  (`https://www.behpardakht.com/` timed out again this round). `bpPayRequest`-style endpoints,
  terminalId/username/password auth, verify/settle/reverse flow, currency unit,
  error codes, and sandbox **not verified**.
- **FEAT-004 adapter:** `apps/orders/gateways/mellat.py` — category PSP,
  `documentation_blocked = True`, declares NO capabilities, raises
  `GatewayUnsupportedOperationError` from create/verify/settle. Required
  credential FIELD NAMES only: `terminal_id`, `username`, `password`. SETTLE
  (finalization) must be a DISTINCT capability, never conflated with verify,
  once the official contract is read.

## 9. Sadad — DOCUMENTATION_BLOCKED

- **Type:** PSP — Sadad Informatics (Bank Melli Iran).
- **Gap (re-confirmed 2026-11-03):** official current docs not reachable here
  (`https://sadadpsp.ir/` timed out again this round). Key/merchant signing,
  request/verify endpoints, currency unit, error codes, and sandbox **not
  verified**.
- **FEAT-004 adapter:** `apps/orders/gateways/sadad.py` — category PSP,
  `documentation_blocked = True`, declares NO capabilities, raises
  `GatewayUnsupportedOperationError` from create/build_redirect/verify. Required
  credential FIELD NAMES only: `merchant_id`, `terminal_id`, `key`. Request
  signing/encryption must be implemented strictly per the documented CURRENT
  crypto once read — never guessed.

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
  (`https://irankish.com/` was unreachable — connection reset — during the
  FEAT-004 pass, so the Tejarat↔PSP mapping remains unconfirmed.)
- **FEAT-004 adapter:** `apps/orders/gateways/tejarat.py` — category PSP,
  `documentation_blocked = True`, declares NO capabilities, raises
  `GatewayUnsupportedOperationError` from create/build_redirect/verify.
  `display_name` ("بانک تجارت") is the storefront LABEL only and asserts no
  technical PSP identity; `required_credentials` is a generic `terminal_id`
  placeholder until the real processor and its credential set are confirmed.

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
