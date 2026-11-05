# Platform billing — evidence-based provider matrix (2026-11-05)

A gateway that works for **store orders** is *not* automatically approved for **SaaS platform billing** (RastiSi collecting
from store owners). Each row below separates: (a) is there a real adapter, (b) does the official contract cover a plain online
payment RastiSi can sell any product through, (c) can the adapter run with **independent platform credentials**, (d) are
request / redirect / callback / verification / reconciliation all supported, (e) what external authorisation is missing.

The matrix lives in code — `apps/portal/services/platform_gateway_matrix.py` — and is the **only** source for the allow-list
(`ELIGIBLE_CODES` / `GATED`). `apps/billing/tests/test_platform_provider_coverage.py` pins it to the adapters' own declarations, so it
cannot silently drift.

> Documentation access on 2026-11-05: `raw.githubusercontent.com` (Pasargad's published docs) was reachable. The hosts
> `academy.snapppay.ir`, `api.mellatbank.ir`, `sep.shaparak.ir`, `www.pec.ir`, `sadadpsp.ir` and `plugins.svn.wordpress.org`
> do **not resolve from this session** (outside the session's allowed network domains), and the provider hosts
> (`gateway.zibal.ir`, `payment.zarinpal.com`, `pep.shaparak.ir`) return HTTP 403 from the session proxy. Rows therefore rely on
> the 2026-11-03 research for those providers and are marked accordingly; no support is claimed that could not be evidenced.

Platform classes (code: `platform_gateway_matrix.MATRIX`):

* **approved** — real adapter + verified contract covering a plain online payment → ready once configured and enabled.
* **gated** — a real adapter / workflow exists and is fully tested with mocks, but **live use is blocked** until the platform owner (superuser) records evidence in the readiness gates: `provider_approval` (written provider authorisation, **per purchase type**), `contract_verification` (adapter checked against the provider's *current official* document), `live_verification` (one authorised real transaction with verify/settle success). Every attestation needs a ≥ 6-character document reference and is audited. **Mocked tests never open a gate**, and changing credentials/environment clears `live_verification`.
* **not_implemented** — no functional adapter.
* Store-only methods (cash on delivery, the stores' own card-to-card) are **not platform billing methods at all** (`STORE_ONLY`); see "COD removal" below.

Readiness is six separate dimensions, shown in Platform Admin: *implemented · configured · eligible/contract-verified · provider-approved · operationally ready · enabled*. `ready` = enabled ∧ configured ∧ no configuration problems ∧ all gates attested ∧ purchase type allowed (admin choice ∩ provider-approved types). A superuser-owned store may *pilot* a gated method (only the `live_verification` gate is lifted for it — never contract/approval gates) to produce the live evidence.

| Provider | Class | Implemented components | Gates before live use | Request → redirect → callback → verify (→ settle) → reconcile | Refund | Mocked tests | Remaining external prerequisite |
|---|---|---|---|---|---|---|---|
| **Zibal** | approved | `zibal.py` + bespoke platform provider | — | `/v1/request` → `/start/{trackId}` → `success,status,trackId` (hint) → `/v1/verify` + orderId → reconcile | manual | yes | callback domain registered; live merchant |
| **Zarinpal** | approved | `zarinpal.py` via bridge | — | `request.json` → `StartPay/{Authority}` → `Authority,Status` (hint) → `verify.json` (amount-bound) → reconcile | manual | yes | 36-char merchant id; callback domain |
| **Pasargad (Dorsa)** | approved | `pasargad.py` via bridge | — | `getToken` → `purchase` → **Referer interstitial** → callback (hint) → `payment-inquiry` + `verify-transactions` → reconcile ≤ 25 min | `reverse-transactions` (full, in window) else manual | yes | platform terminal credentials, IP whitelist, callback domain = contract domain |
| **SnappPay (BNPL)** | **gated** (new platform path) | cart from **real invoice lines only** (refuses discount/credit lines, partial payment, mismatching totals), eligibility check (blocks only an explicit `eligible: false`), `verify` → **`settle`** → fulfilment; ambiguity ⇒ pending; reconcile = inquire → settle; terminal-negative ⇒ failed | `provider_approval` (+purchase types) · `live_verification` | `payment/token` → provider page → POST `transactionId,state,amount` (hint) → verify → settle | manual (never automatic for BNPL) | yes (adapter-level scripted fake + adapter contract tests) | **written SnappPay authorisation for selling SaaS subscriptions / SMS credit to the RastiSi merchant account**; client_id/secret; IP whitelist; provider-supplied `api_base`. Host not resolvable from this session ⇒ contract is from the 2026-11-03 research |
| **TorobPay (BNPL)** | **gated** (new platform path) | same bridge as SnappPay | `provider_approval` · `live_verification` | token → page → callback (hint) → verify → settle | manual | yes | written TorobPay authorisation; four credentials; IP whitelist |
| **Saman (SEP)** | **gated** (new adapter + bridge) | token request, **POST-form redirect** (`Token`), callback `State/RefNum/ResNum`, `VerifyTransaction` (RefNum + exact original amount, + optional ResNum cross-check), unique sale reference (`RefNum` can fulfil only one attempt), `ReverseTransaction` | **`contract_verification`** · `live_verification` | alnum order code (`B`/`S`+9 digits) = `ResNum` | reverse (full amount) else manual | yes | **No official SEP document was reachable** — encoded from secondary sources (see Evidence disclosure). Needs the official current document, TerminalId, IP whitelist |
| **Mellat (Behpardakht)** | **gated** (new adapter + bridge) | SOAP `bpPayRequest` → **POST-form** (`RefId`) → callback `ResCode,SaleOrderId,SaleReferenceId` (hint) → `bpVerifyRequest` → **`bpSettleRequest`** (distinct step; 43/45 idempotent; 48 reversed is never settled) → `bpInquiryRequest` on ambiguity; reversal | **`contract_verification`** · `live_verification` | numeric order id (`1`/`2`/`9` + pk) | `bpReversalRequest` else manual | yes | **No official Behpardakht document was reachable**; encoded from secondary sources. Needs the official document, terminal credentials, IP whitelist |
| **Platform card-to-card** | **approved (manual)** | first-class manual method `platform_card`: owner submits a *claim*; an authorised finance admin approves/rejects; approval goes through `confirm_payment` / the SMS credit ledger exactly once | — (finance approval is per claim) | claim → review queue → independent bank-statement reference + exact amount → approve/reject/expire/cancel | manual (refund ledger, then manual transfer) | yes (service, HTTP, PostgreSQL races) | a dedicated platform destination card (separate from store cards) and an authorised finance admin |
| **Parsian / Sadad / Tejarat** | not_implemented | skeletons only | n/a | none | n/a | n/a | official contract/WSDL not obtained (Tejarat's PSP unknown; IranKish not assumed) |
| **COD / store card-to-card** | **not a platform method** | removed from platform billing | n/a | n/a | n/a | absence + migration tests | none — store checkout keeps both |

## Evidence disclosure (Saman and Mellat)

On 2026-11-05 `sep.ir` is marketing-only, and `sep.shaparak.ir`, `api.mellatbank.ir` and `behpardakht.com` do not resolve from this session. **No official technical document for either provider was read.** The encoded contracts come from secondary sources only: `pkg.go.dev/github.com/aliworkshop/samanpayment`, the `shetabit/multipay` Saman and Behpardakht drivers (read via `raw.githubusercontent.com`), a third-party copy of a 2013 "Mellat PGW User Manual Rev 1.1", and the WSDL location `bpm.shaparak.ir/pgwchannel/services/pgw?wsdl`. Whether those match the providers' *current* APIs is **unverified**; for that reason both adapters keep `documentation_blocked = True` (never selectable for store checkout) and platform billing holds them behind the `contract_verification` gate. Adapter tests prove fail-closed behaviour and internal consistency, **not** conformance.

The production-safety verdict is therefore: Zibal, Zarinpal, Pasargad and platform card-to-card are production-eligible once their external prerequisites are met; SnappPay/TorobPay are production-safe **only** after written provider authorisation for each purchase type; Saman and Mellat are **not production-ready** until the official documents are checked, the gate recorded and one real live transaction verified.

## COD removal

`cod` and the store-only `card_to_card` were never eligible, and now cannot appear anywhere in platform billing: not in the matrix (`STORE_ONLY`), the gateway catalog, the default selector, readiness counts, checkout options or the admin UI. `portal.0018_platform_cod_removal` is a data-safe, idempotent migration: legacy `enabled_payment_providers` lists are filtered, a default of `cod` falls back to `manual`, stray `PlatformGatewayConfig` rows are disabled (kept), and each change is written to the platform audit log; store COD (`apps.orders`) is untouched.

## Status taxonomy (Platform Admin → Payment Gateways)
`ready` · `disabled_by_admin` (complete but switched off) · `missing_credentials` · `missing_configuration` (e.g. callback domain is
still `localhost` outside DEBUG) · `pending_contract` (BNPL) · `not_implemented` (5 PSP skeletons) · `not_eligible` (offline).
Each card shows the specific reason, setup steps, external prerequisites, sandbox availability, verification/reconciliation/refund
notes and contractual evidence. The default-gateway selector lists every approved gateway but **disables** the ones that are not
ready; the server independently refuses a non-ready default.

## Secure configuration test
`Test configuration` performs no payment and stores no payment row: it checks credentials are complete, runs the provider's
side-effect-free authentication when documented (Pasargad `getToken`), then creates one *unpaid* test request through the **same
platform provider code path** (never redirected, never stored, order code in a separate `9…` namespace). Only a provider error
**code** and a fixed Persian sentence are shown/stored/audited — never provider messages or any credential value. Changing
credentials invalidates the previous test result; "untested" is distinct from "not ready".

## Pasargad specifics implemented
* **Referer:** the contract requires `Referer = merchant domain` on the customer redirect. Django's default
  `Referrer-Policy: same-origin` would strip it on a cross-origin 302, so Pasargad is reached through an interstitial
  (`<meta name="referrer" content="origin">` + `<meta http-equiv="refresh">`, no inline script).
* **urlId stays server-side** (`provider_extra`): `verify-transactions` uses the stored value; a browser-supplied `urlId` is ignored.
* **Verify deadline:** unverified payments auto-revert after the merchant deadline (default 25 min) → run
  `reconcile_platform_payments` every **5 minutes** (default min-age is now 5 min).
* **Amount mismatch** is detected from `payment-inquiry` *before* `verify-transactions`, so a wrong amount is never finalised.
* **Refund:** full-amount refund of a recent payment uses the documented `reverse-transactions`; otherwise (partial, deadline
  passed, provider refusal) an honest *pending manual* refund — never an exception or a fabricated success.

## Findings in the **store** payment engine (reported; deliberately not changed except where stated)
1. **Pasargad Referer (changed):** the store flow redirected with a bare 302 (no Referer under the default policy). Now uses the
   same interstitial for adapters that declare `redirect_requires_referer` (Pasargad only). Two existing store tests that
   asserted the bare 302 were updated; every other provider keeps a plain 302. Revert = one line in `orders/views.py`.
2. **Pasargad `urlId` (not changed):** the store verify path falls back to `inquiry.data.url` (a URL) when `callback_data` lacks
   `urlId`; the id is not persisted per attempt there. Needs live evidence of the `data.url` format before touching store verify.
