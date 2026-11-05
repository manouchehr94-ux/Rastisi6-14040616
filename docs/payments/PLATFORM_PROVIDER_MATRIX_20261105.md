# Platform billing — evidence-based provider matrix (2026-11-05)

A gateway that works for **store orders** is *not* automatically approved for **SaaS platform billing** (RastiSi collecting
from store owners). Each row below separates: (a) is there a real adapter, (b) does the official contract cover a plain online
payment RastiSi can sell any product through, (c) can the adapter run with **independent platform credentials**, (d) are
request / redirect / callback / verification / reconciliation all supported, (e) what external authorisation is missing.

The matrix lives in code — `apps/portal/services/platform_gateway_matrix.py` — and is the **only** source for the allow-list
(`ELIGIBLE_CODES`). `apps/billing/tests/test_platform_provider_coverage.py` pins it to the adapters' own declarations, so it
cannot silently drift.

> Documentation access on 2026-11-05: `raw.githubusercontent.com` (Pasargad's published docs) was reachable. The hosts
> `academy.snapppay.ir`, `api.mellatbank.ir`, `sep.shaparak.ir`, `www.pec.ir`, `sadadpsp.ir` and `plugins.svn.wordpress.org`
> do **not resolve from this session** (outside the session's allowed network domains), and the provider hosts
> (`gateway.zibal.ir`, `payment.zarinpal.com`, `pep.shaparak.ir`) return HTTP 403 from the session proxy. Rows therefore rely on
> the 2026-11-03 research for those providers and are marked accordingly; no support is claimed that could not be evidenced.

| Provider | Real adapter | Platform status | Reusable with independent platform credentials | Request → redirect → callback → verify → reconcile | Sandbox (official) | Blocker / external prerequisite |
|---|---|---|---|---|---|---|
| **Zibal** | yes (`zibal.py`, CREATE+VERIFY) + bespoke platform provider | **approved** | yes (`PlatformGatewayConfig` / legacy fields; never `PaymentGatewayConfig`) | `/v1/request` → `/start/{trackId}` → `success,status,trackId` (hint) → `/v1/verify` (+ orderId cross-check) → `reconcile_platform_payments` | **yes** — fixed `zibal` merchant (docs) | callback domain registered in Zibal panel; refund = manual |
| **Zarinpal** | yes (`zarinpal.py`, CREATE+VERIFY) via `AdapterBackedBillingProvider` | **approved** | yes | `request.json` → `StartPay/{Authority}` → `Authority,Status` (hint) → `verify.json` (amount-bound) → reconcile | none documented (not invented) | 36-char merchant id; callback domain; refund = manual |
| **Pasargad (Dorsa)** | yes (`pasargad.py`, CREATE+VERIFY+INQUIRE+CANCEL) via `AdapterBackedBillingProvider` | **approved** (new) | yes — platform terminal, numeric invoice namespace (`1`/`2`/`9`+pk) separate from store orders | `getToken` → `purchase` → browser with **Referer** (interstitial) → `invoiceId,status,referenceNumber,trackId` (hint) → `payment-inquiry` + `verify-transactions` (urlId from **server-stored** session data) → reconcile every 5 min (25-min verify deadline) | **none documented** | platform terminal credentials from Bank Pasargad, server-IP whitelist, callback domain = contract domain (code 13028). Refund: documented `reverse-transactions` (full amount, within the deadline) else manual |
| **SnappPay (BNPL)** | yes (`snappay.py`: CREATE, VERIFY, SETTLE, CANCEL, INQUIRE) | **pending contract** | adapter could run with platform credentials, but not approved | cart-based BNPL flow exists for stores | not verified | published contract describes itemised carts + consumer installment contracts; **no evidence it covers selling SaaS subscriptions / SMS credit**. Needs SnappPay's written confirmation for the RastiSi platform merchant account + credentials + IP whitelist |
| **TorobPay (BNPL)** | yes (`torobpay.py`) | **pending contract** | as above | as above | not verified | same: SaaS coverage unverified → written confirmation required |
| **Saman (SEP)** | skeleton only | **not implemented** | n/a | none | n/a | official technical contract not obtained (sep.ir marketing-only; docs host unreachable) |
| **Parsian (PEC)** | skeleton only | **not implemented** | n/a | none | n/a | official contract/WSDL not obtained |
| **Mellat (Behpardakht)** | skeleton only | **not implemented** | n/a | none | n/a | official contract not obtained; settle must be a separate step |
| **Sadad** | skeleton only | **not implemented** | n/a | none | n/a | official contract not obtained |
| **Tejarat** | label skeleton | **not implemented** | n/a | none | n/a | underlying PSP unknown (IranKish **not** assumed) |
| Card-to-card, COD | offline adapters | **not eligible** | n/a | no server-verifiable payment | n/a | a platform manual-transfer workflow would be a new product/finance decision |

Only Zibal, Zarinpal and Pasargad are approved. **No documentation-blocked or unverified provider was enabled** to remove an
"unavailable" label; each shows its own specific status and blocker in Platform Admin.

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
