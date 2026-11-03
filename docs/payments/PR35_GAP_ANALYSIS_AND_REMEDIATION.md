# PR #35 — Gap Analysis and Remediation

Independent audit, corrective documentation, and QA evidence for the RastiSi
storefront payment engine branch `feature/kiro-payment-engine-20261103`
(base `main` @ `7d311556`). This document is written for a reviewer who needs an
honest, evidence-backed account of what the mission asked for, what was actually
delivered, what remains blocked, and why.

Verification environment and date: the sandbox runs Django 5.2 on SQLite with
`psycopg 3.3.7` present but NO PostgreSQL server binaries. All reachability and
test evidence below was captured on **2026-11-03**. No real-money transaction
and no live provider endpoint call was ever performed from this environment; all
provider HTTP is exercised with deterministic mocks.

---

## 0. Corrective round 2 follow-up (v2, 2026-11-04)

The semantic review of corrective round 2 returned NEEDS_CHANGES with four
issues. Their resolution on this branch:

1. **Card-to-card merchant confirmation is now reachable end-to-end (was the
   blocking issue).** The round-2 `card_to_card_payment_service` (confirm /
   reject / can_confirm) previously had no production caller, so a card-to-card
   order could sit PENDING forever. It now has the full merchant surface,
   mirroring COD exactly:
   - View: `apps/dashboard/card_to_card_views.py::order_confirm_card_to_card_payment`
     and `order_reject_card_to_card_payment` (POST-only, `staff_required`,
     gated on `ORDER_VIEW` + `ORDER_CONFIRM_COD_PAYMENT`, store-scoped via
     `get_object_or_404(Order, code=..., store=request.store)`).
   - URLs: `orders/<code>/card-to-card-payment/`
     (`dashboard:order-card-to-card-payment`) and
     `orders/<code>/card-to-card-reject/` (`dashboard:order-card-to-card-reject`).
   - Dashboard context + template: the order-detail view adds
     `can_confirm_card_to_card` and `card_to_card_token`, and
     `order_detail.html` renders a confirm form plus a reject form, shown only
     when the order is a PENDING, non-canceled card-to-card order.
   - Authorization/tenant parity: card-to-card reuses the SAME permission COD
     uses (`order.confirm_cod_payment`, granted to Owner / Administrator /
     Order Manager) and the SAME store scoping, so no new permission or schema
     change was needed. Reusing the existing "confirm offline payment"
     permission is the faithful mirror of the COD pattern the review asked for.
   - Tests: `apps/orders/tests/test_card_to_card_confirmation.py::CardToCardDashboardTests`
     adds HTTP-level (`self.client.post`) coverage — permission matrix
     (Analyst/Catalog/Content get 403; Order Manager/Administrator/Owner confirm
     PENDING -> PAID), form visibility, reject leaves the order PENDING with no
     money, idempotent duplicate confirm, wrong-amount/online-order rejection,
     foreign-store 404, and GET-not-allowed (405).

2. **SQLite idempotency fallback no longer surfaces an uncaught IntegrityError
   (500).** `initiate_payment` now wraps the attempt insert in a savepoint and
   catches `IntegrityError`: it re-queries `_scoped_existing()` and returns the
   now-committed live attempt (no second external `create_payment` call); only
   if the collision was with a non-live row does it mint a fresh disambiguated
   key and insert again. This makes the create path safe on any backend
   (Postgres already serialized the race via the row lock; SQLite now degrades
   gracefully instead of 500ing). Test:
   `test_idempotency_tenant.ConcurrentInitiationTests.test_integrity_error_on_insert_requeries_live_attempt_instead_of_500`
   reproduces the loser's colliding insert deterministically (no threads) and
   asserts the winner is reused with zero extra charges and no duplicate row.

3. **Postgres concurrency guarantee remains an honestly-reported gap, not a
   pass.** The 16 `@skipUnless(connection.vendor == "postgresql")` row-lock
   contention tests still skip here (no Postgres binaries; see §9 and §10).
   This is documented as UNVERIFIED, not claimed as verified. No code change.

4. **`reject_transfer` confirmed to leave no stale verified state.**
   Card-to-card never stamps `verified_at` on the PENDING attempt (only the
   merchant confirm path verifies, via `apply_payment_success` on a separate
   transition), so rejection only moves the attempt to CANCELED and records the
   failure. An explicit `assert attempt.verified_at is None` now documents and
   guards that invariant so a future change cannot silently leave a
   canceled-yet-"verified" row that would mislead reconciliation.

---

## 1. Original mission requirements vs actual delivered functionality

| Mission requirement | Delivered | Status |
|---------------------|-----------|--------|
| Real, tenant-isolated storefront payment engine in `apps/orders/` | Adapter contract (`gateways/base.py`), single dispatch registry (`gateways/registry.py`), orchestrator (`services/gateway_payment_service.py`), readiness-derived admin UI | Delivered |
| Zarinpal + Zibal real adapters | `zarinpal.py`, `zibal.py` REST v4 / IPG v1, contract-tested | Delivered (contract-tested; not sandbox/live verified) |
| Offline methods (COD, card-to-card) | `cod.py`, `card_to_card.py`, server-to-server never auto-verifies | Delivered (operational offline) |
| Real adapters for the 8 remaining online providers | Pasargad, SnappPay, TorobPay implemented against reachable publisher contracts; the 5 remaining PSPs remain documentation-blocked | **Partially delivered** |
| Never fabricate endpoints/credentials/error codes | No invented contract anywhere; blocked providers stay honestly blocked | Delivered |
| Preserve existing payment methods and tenant isolation | Additive migrations only (0020-0022); store scoping intact | Delivered |
| Authorized sandbox / production verification of new providers | NOT possible here (no credentials, no reachable provider endpoints) | Not delivered (external dependency) |

Overall: the engine, the two facilitators, the two offline methods, and three of
the eight remaining providers are implemented and contract-tested. Five PSPs stay
blocked on unreachable official documentation, and no new provider is sandbox- or
production-verified. The project is therefore **PARTIALLY DELIVERED** (see §12).

---

## 2. Confirmed deficiencies in PR #35

The following were the substantive gaps identified in PR #35 as originally
submitted, and their remediation status on this branch:

1. **Three providers were shipped as documentation-blocked skeletons even though
   a reachable publisher contract existed.** Pasargad/Dorsa, SnappPay, and
   TorobPay had obtainable contracts on 2026-11-03. **Remediated:** all three are
   now real, contract-tested adapters (see §7).
2. **The research/implementation matrices carried a stale blanket claim** that
   "no authoritative current contract for any of the 8 providers was obtainable."
   **Remediated:** the claim is explicitly corrected in both matrices (kept, not
   silently deleted) and is now true only for the 5 remaining PSPs (see §3).
3. **A readiness-blind fallback in `payment_initiate`** could pick any active
   online config, including a not-ready one, as a fallback gateway.
   **Remediated** (see §6, defect D-1).
4. **A stale test assertion** expected `snappay` to remain
   `documentation_blocked`. After the reclassification this assertion was false.
   **Remediated** (see §6, defect D-2).

No evidence was found that any pre-existing merchant payment method was dropped,
renamed, duplicated, or disconnected (see §5).

---

## 3. Results of the second official-documentation investigation

Every official/publisher source was re-attempted on 2026-11-03. The outcome
splits cleanly into three reachable contracts (now implemented) and five still
unreachable PSPs (kept blocked).

### Reachable and implemented (verified 2026-11-03)

| Provider | Source | What it provides |
|----------|--------|------------------|
| Pasargad / Dorsa IPG | `https://raw.githubusercontent.com/pep-ipg/Dorsa-IPG-pasargad/main/docs/api-reference.md`, `.../usage-guides.md`, `.../error-codes.md` (publisher `pep-ipg`) | REST contract: getToken (Bearer) → purchase → payment-inquiry → verify-transactions → reverse-transactions; error-code table. Username/password + Bearer (NOT RSA). |
| SnappPay | `https://academy.snapppay.ir/self-cms` | REST API v2.1 BNPL lifecycle: OAuth token → eligibility → payment token → verify → settle → cancel/status. Amounts IRR. |
| TorobPay | `https://plugins.svn.wordpress.org/torobpay-for-woocommerce/trunk/class-torobpay-api.php` (provider-published WooCommerce plugin source) | Same Snapp-ecosystem BNPL endpoint PATHS, OAuth password grant, base `https://cpg.torobpay.com`. Implemented natively in Django, NO WordPress/PHP dependency. |

### Still unreachable — kept DOCUMENTATION_BLOCKED (re-attempted 2026-11-03)

| Provider | URL attempted | Outcome | Specific missing contract detail |
|----------|---------------|---------|----------------------------------|
| Saman (SEP) | `https://www.sep.ir/` | Reachable, **marketing-only** | No endpoint URLs, no request/response schema, no currency unit, no error codes, no sandbox (page lists products in prose only) |
| Saman (SEP) | `https://sep.shaparak.ir/` | Timeout | same |
| Parsian (PEC) | `https://pec.ir/` | **Timeout** | SOAP/REST endpoints, pin/auth, confirm/reverse flow, currency unit, error codes, sandbox |
| Mellat | `https://www.behpardakht.com/` | **Timeout** | `bpPayRequest`-style endpoints, terminalId/username/password auth, verify/settle/reverse, currency unit, error codes, sandbox |
| Sadad (Bank Melli) | `https://sadadpsp.ir/` | **Timeout** | key/merchant signing, request/verify endpoints, currency unit, error codes, sandbox |
| Tejarat (display label) | `https://irankish.com/` | **Connection reset (ECONNRESET)** | technical PSP mapping unconfirmed (IranKish NOT assumed); all contract detail unverified |

**Correction of the first-pass blanket claim.** The earlier conclusion that "no
authoritative current contract for any of the 8 providers was obtainable" was the
FIRST-pass result. It is now **false for Pasargad, SnappPay, and TorobPay** and
remains accurate ONLY for the five PSPs above. Both
`PROVIDER_RESEARCH_MATRIX.md` and `PROVIDER_IMPLEMENTATION_MATRIX.md` state this
correction explicitly rather than deleting the old text.

For Tejarat, the storefront display label ("بانک تجارت") is kept strictly
separate from the technical PSP identity; IranKish is investigated but NOT
assumed.

---

## 4. Provider-by-provider implementation status

Classification axes: **{official contract identified / adapter implemented /
contract tests passed / merchant credentials required / sandbox verified /
production verified}**.

| Provider | Contract identified | Adapter implemented | Contract tests passed | Merchant creds required | Sandbox verified | Production verified | Net status |
|----------|---------------------|---------------------|-----------------------|-------------------------|------------------|---------------------|------------|
| Zarinpal | Yes (REST v4, 2026-11-03) | Yes | Yes | Yes (merchant_id) | No | No | VERIFIED contract + implemented + contract-tested; NEEDS live/sandbox verification |
| Zibal | Yes (IPG v1) | Yes | Yes | Yes (merchant) | No | No | VERIFIED contract + implemented + contract-tested; NEEDS live/sandbox verification |
| COD | N/A (offline) | Yes | Yes | No | N/A | Operational | Offline, operational |
| card_to_card | N/A (offline) | Yes | Yes | Yes (card data) | N/A | Operational | Offline, operational |
| **Pasargad/Dorsa** | **Yes (2026-11-03)** | **Yes** | **Yes** | **Yes** | **No** | **No** | **IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS** |
| **SnappPay** | **Yes (2026-11-03)** | **Yes** | **Yes** | **Yes** | **No** | **No** | **IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS** |
| **TorobPay** | **Yes (2026-11-03)** | **Yes** | **Yes** | **Yes** | **No** | **No** | **IMPLEMENTED_AND_CONTRACT_TESTED + NEEDS_CREDENTIALS** |
| Saman | No | Skeleton | Honest-subset | names only | No | No | DOCUMENTATION_BLOCKED |
| Parsian | No | Skeleton | Honest-subset | names only | No | No | DOCUMENTATION_BLOCKED |
| Mellat | No | Skeleton | Honest-subset | names only | No | No | DOCUMENTATION_BLOCKED |
| Sadad | No | Skeleton | Honest-subset | names only | No | No | DOCUMENTATION_BLOCKED |
| Tejarat (label) | No | Skeleton | Honest-subset | names only | No | No | DOCUMENTATION_BLOCKED |

An adapter is NOT operational merely because it compiles. A provider with a
tested adapter but no credentials is `IMPLEMENTED_AND_CONTRACT_TESTED` +
`NEEDS_CREDENTIALS` (Pasargad, SnappPay, TorobPay). All unverified production
integrations stay disabled: `is_active` defaults `False` for every online
provider.

---

## 5. Explanation of the existing-payment-method discrepancy

This section lifts the FEAT-001 regression findings verbatim.

**Base-vs-HEAD gateway history (exact commands + outputs):**

- `git show 7d311556:apps/orders/migrations/0006_payment_gateway_config_and_attempt.py`
  — the `gateway_code` field on base commit `7d311556` was
  `models.CharField(choices=[('zibal', 'زیبال'), ('cod', 'پرداخت در محل')], max_length=30, verbose_name='کد درگاه')`.
  ONLY `zibal` and `cod` existed in the storefront engine on base.
- `git grep -l zarinpal 7d311556 -- apps/` — **(no output; exit code 1)**:
  `zarinpal` does NOT appear anywhere under `apps/` on base commit `7d311556`.
- `git grep -l card_to_card 7d311556` — **(no output; exit code 1)**:
  `card_to_card` does NOT appear ANYWHERE in the repo on base commit `7d311556`.
- `git grep -l zarinpal 7d311556` —
  `7d311556:docs/docs/product/Final Result At Last/novinshop-video-rich-products/payment-settings.html`
  AND `7d311556:docs/reference-kits/rastisi-11-families-v3/machine/reference-dna.json`:
  i.e. `zarinpal` appears on base ONLY in docs/static reference HTML + a
  reference DNA JSON, NOT in the storefront checkout engine (`apps/`).

**Migration 0006 → 0021 → 0022 choice mapping:**

- `0006_payment_gateway_config_and_attempt.py`: CreateModel/AddConstraint;
  `gateway_code` choices = `[('zibal','زیبال'),('cod','پرداخت در محل')]`; also
  `AddConstraint UniqueConstraint(fields=('store','gateway_code'), name='uniq_gateway_config_per_store')`
  at lines 63-66.
- `0021_alter_paymentgatewayconfig_gateway_code.py`: single `AlterField` on
  `paymentgatewayconfig.gateway_code`; choices widened ADDITIVELY to `[zibal, cod,
  zarinpal, card_to_card]`; `max_length` stays 30, not null; `zibal`/`cod` kept,
  nothing removed or renamed.
- `0022_alter_paymentgatewayconfig_gateway_code.py`: single `AlterField`; choices
  widened ADDITIVELY to `[zibal, cod, zarinpal, card_to_card, pasargad, saman,
  parsian, mellat, sadad, tejarat, snappay, torobpay]` (6 PSPs + 2 BNPL added);
  `max_length` stays 30; `zibal`/`cod` still the first two entries, nothing
  removed or renamed.
- Conclusion: 0021 and 0022 are choices-only `AlterField` migrations that
  strictly ADD gateway codes. `zibal` and `cod` are never dropped, renamed, or
  reordered-away. The change is additive and backward-compatible.

**Unique constraint intact:** `uniq_gateway_config_per_store` on
`(store, gateway_code)` is defined in `0006` lines 63-66 and still present in
`apps/orders/models.py` lines 696-699 (`PaymentGatewayConfig.Meta.constraints`),
unchanged by 0021/0022 (which only `AlterField` the choices).

**`apps/stores` zarinpal reference is unrelated:** `apps/stores/models.py`
line 725, class `StoreIntegrationConnection` — the mention of ZarinPal is a
Persian docstring, NOT a model field. The docstring explicitly states that
payment/installment gateways use `apps.orders.models.PaymentGatewayConfig` /
`apps.orders.gateways`, not `StoreIntegrationConnection` (which handles simple
id/code integrations such as eNamad, Torob, analytics, ad pixels).

**Regression test added:**
`apps.orders.tests.test_payment_migration_compat.LegacyConfigBackwardCompatTests.test_pre_upgrade_zibal_and_cod_configs_survive_additive_choice_extension`
— creates a pre-existing `zibal` (with credentials) + `cod` config, reloads both,
and asserts `gateway_code` is byte-identical (not renamed), credentials still
decrypt to the original payload, `readiness_status` derives `CONNECTED` (not
disconnected), exactly one row per `(store, gateway_code)` (not duplicated), and
`uniq_gateway_config_per_store` still raises `IntegrityError` on a duplicate
insert. Result after change: 9 tests, OK.

**Honest conclusion.** The reviewer's §2 screenshot baseline diverges from THIS
repo's base commit `7d311556`. On base, the storefront checkout engine had ONLY
`zibal` and `cod` as `PaymentGatewayConfig` gateway codes. `zarinpal` and
`card_to_card` did NOT pre-exist in the storefront engine on base (`zarinpal`
appeared only in docs/static reference HTML + `reference-dna.json`;
`card_to_card` appeared nowhere). This branch ADDED `zarinpal` and `card_to_card`
(migration 0021) and the 6 PSP + 2 BNPL codes (migration 0022) purely additively.
NO pre-existing merchant payment config/record/choice was dropped, renamed,
duplicated, or disconnected. We do NOT claim `zarinpal` pre-existed in the
storefront engine; it did not.

---

## 6. Actual code defects and corrected files

The full-PR audit (`git diff main...HEAD`) was run against the §4 checklist.
Positive file:line evidence for each clean item is recorded alongside the two
defects that were found and fixed.

### Defects found and fixed

- **D-1 — readiness-blind fallback gateway in `payment_initiate`**
  (`apps/orders/views.py`, the `payment_initiate` fallback block). Before: the
  fallback selected `PaymentGatewayConfig.objects.filter(store, is_active=True).exclude(gateway_code="cod").first()`,
  which could pick a not-ready (e.g. documentation-blocked or unconfigured)
  provider. **Fix:** the fallback now iterates active non-COD candidates and
  selects the first with `is_selectable_at_checkout` True (readiness-aware), so a
  not-ready provider can never be auto-selected. Verified by the Group B
  `test_payment_security` + `test_feat005_provider_integration` suites.

- **D-2 — stale test assertion after provider reclassification**
  (`apps/orders/tests/test_gateway_admin.py:250`). Before: asserted
  `rows["snappay"]["readiness_status"] == "documentation_blocked"`. Since SnappPay
  is now a real adapter with no credentials, its readiness derives
  `not_configured`. **Fix:** assertion updated to `not_configured` (category
  still `bnpl`); the `mellat` assertion at line 245 correctly stays
  `documentation_blocked`. Verified: Group A now 155 tests OK. No other stale
  `documentation_blocked`/`unsupported` assertions were found for the three
  reclassified providers (`grep -rn` across `apps/orders/tests/` and
  `apps/dashboard/`); every remaining occurrence refers to the 5 still-blocked
  PSPs or to framework constants and is correct.

### §4 checklist — positive evidence (clean items)

- **Historical payment compatibility.** Additive migrations 0020-0022; `zibal`
  and `cod` unchanged. See §5. `makemigrations --check --dry-run` → "No changes
  detected".
- **Tenant isolation / Store scoping.** `PaymentGatewayConfig.store`
  (`models.py:656`), `PaymentAttempt.store` (`models.py:911`),
  `PaymentReconciliation.store` (`models.py:1178`). The orchestrator guards
  `gateway_config.store_id != store.pk` in `initiate_payment`
  (`gateway_payment_service.py:124`). The callback path filters the attempt by
  store: `.filter(public_id=attempt_public_id, store=store)`
  (`gateway_payment_service.py:413`).
- **Credential encryption / access control.** `apps/orders/encryption.py` uses
  Fernet with a dedicated `PAYMENT_CREDENTIAL_KEY` (NOT `SECRET_KEY`), fails
  closed when `DEBUG=False` and the key is missing/invalid, and never logs
  plaintext (`encrypt_credential`/`decrypt_credential` log only the exception
  type). `get_credentials`/`set_credentials` at `models.py:712`/`727`. Adapters
  never log credentials (verified by the credential-leak tests in
  `test_payment_security.py` and per-adapter tests).
- **Payment-attempt ownership.** `process_callback_and_verify` filters by store
  (`gateway_payment_service.py:413`); a cross-tenant `public_id` yields "تلاش
  پرداخت یافت نشد". Covered by the cross-tenant tests in
  `test_feat005_provider_integration.py`.
- **Currency conversion (Toman → Rial ×10, exactly once per adapter).**
  `zarinpal.py:200` (and verify at `:336`), `zibal.py:147`/`:312`,
  `pasargad.py:428`/`:543`, `snappay.py:372`/`:430`/`:547`/`:747`,
  `torobpay.py:416`/`:474`/`:562`/`:684` — each multiplies
  `int(amount) * TOMAN_TO_RIAL` only at the adapter boundary. The service and
  views never convert (the only Rial reference in the service is the inverse
  `_toman_from_rial` helper at `gateway_payment_service.py:244`, used solely to
  record reconciliation evidence). No double conversion.
- **Callback authentication.** A browser callback never proves success:
  `_callback_claims_success` (`gateway_payment_service.py:386`) is used ONLY to
  flag a SUSPECTED reconciliation, never to mark an order paid; the
  server-to-server `adapter.verify_payment` result is authoritative.
- **Duplicate callbacks.** A `SUCCEEDED` attempt returns idempotently at
  `gateway_payment_service.py:419`; the status transition before verify is
  conditional (`filter(..., status__in=open_statuses).update(...)`), never a
  blind save; `_apply_verified_payment` re-checks `status == SUCCEEDED` under the
  lock at `:343`.
- **Settlement / verification semantics (BNPL).** SETTLE is a distinct,
  capability-gated step: `if adapter.supports(PaymentOperation.SETTLE)`
  (`gateway_payment_service.py:497`) runs `adapter.settle_payment` BEFORE
  `_apply_verified_payment`, and a settle failure calls `fail(...)` so the order
  is NOT marked paid. Ordinary PSPs/facilitators (no SETTLE capability) skip this
  entirely.
- **Unknown-payment recovery.** `PaymentReconciliation` with SUSPECTED/CONFIRMED
  evidence levels; `_record_discrepancy` persists amount-mismatch (CONFIRMED) and
  ambiguous-verify (SUSPECTED) cases; `_open_reconciliation`
  (`gateway_payment_service.py:264`) is idempotent via `get_or_create(attempt=...)`
  and upgrades SUSPECTED → CONFIRMED without creating a second record.
- **Double-finalization prevention.** `_apply_verified_payment` locks order then
  attempt with `select_for_update` (`:312`/`:313`, same order as
  `_record_discrepancy` `:341`/`:342`), and early-returns on
  `status == SUCCEEDED` (`:343`).
- **Transaction/inventory consistency.** `apply_payment_success` runs inside a
  nested `transaction.atomic()` savepoint (`gateway_payment_service.py:366`); on
  failure the evidence is preserved via `_open_reconciliation(PROCESSING_ERROR)`
  and the attempt stays SUCCEEDED (money moved) without creating a Transaction or
  touching order/coupon/inventory.
- **Existing checkout behavior.** No provider conditionals in
  `checkout_service.py` (grep shows only empty-string guards and coupon logic) or
  in the orchestrator. Routing is driven solely by `readiness_status`.
- **Admin activation / readiness correctness.** `readiness_status`
  (`models.py:~781`) derives UNAVAILABLE → DOCUMENTATION_BLOCKED → NOT_CONFIGURED
  → NEEDS_CREDENTIALS → READY_FOR_TEST → CONNECTED; `is_selectable_at_checkout`
  requires `is_active` AND (CONNECTED or READY_FOR_TEST+sandbox). The admin UI
  cannot activate a documentation-blocked provider (covered by
  `test_gateway_admin.test_save_can_not_activate_documentation_blocked_provider`
  and `test_toggle_...`).

No further safely-fixable defects were found.

---

## 7. Additional implementations completed (Pasargad, SnappPay, TorobPay)

- **Pasargad / Dorsa IPG** (`apps/orders/gateways/pasargad.py`,
  `documentation_blocked = False`). Base `https://pep.shaparak.ir/dorsa1`.
  getToken (Bearer 10-min, 401→re-auth, stateless) → purchase → payment-inquiry
  (authoritative read) → verify-transactions (finalize) → reverse-transactions
  (cancel). Capabilities `{CREATE, VERIFY, INQUIRE, CANCEL}`; REFUND/SETTLE
  intentionally not declared. Credentials `username`, `password`,
  `terminalNumber`, `serviceCode` (RSA NOT required — earlier assumption
  corrected). Self-contained Gregorian→Jalali helper, no new dependency.
  24 contract tests pass.
- **SnappPay** (`apps/orders/gateways/snappay.py`, `documentation_blocked =
  False`). REST v2.1; OAuth JWT via Basic `base64(client_id:client_secret)`;
  eligibility → payment token (`paymentPageUrl`) → verify (30s budget + status
  fallback) → settle (distinct finalize) → cancel/status. Capabilities
  `{CREATE, VERIFY, SETTLE, CANCEL, INQUIRE}`.
- **TorobPay** (`apps/orders/gateways/torobpay.py`, `documentation_blocked =
  False`). Base `https://cpg.torobpay.com`; OAuth password grant,
  scope `online-merchant`, Basic header, 401→re-auth once; same BNPL lifecycle.
  Capabilities `{CREATE, VERIFY, SETTLE, CANCEL, INQUIRE}`. Implemented natively
  in Django, NO WordPress/PHP dependency.

All three: Toman→Rial (×10) isolated once; amount mismatch raises
`GatewayAmountMismatchError` with evidence; explicit `(connect=10, read=30)`
timeouts; strict JSON parsing; credentials never logged; `is_active` default
`False`. SnappPay + TorobPay share the BNPL settle gate verified by
`test_feat005_provider_integration.test_bnpl_not_marked_paid_when_settle_fails`.

---

## 7A. Integration blockers B1-B5: root cause, fix, tests, evidence

A second review round drove the engine end-to-end (real Django views, the
orchestration service, persistence, the provider adapters, and order state
transitions) rather than only through per-adapter unit tests. That pass surfaced
five concrete integration blockers (B1-B5). Each is recorded below with its root
cause, the exact files changed, the fix, the tests added, the exact test command,
and the real pass/fail/skip counts. All provider HTTP is mocked; no external
network was used. Date 2026-11-03, Django 5.2, SQLite.

### B1: the authoritative gateway redirect URL was lost end-to-end

- **Root cause.** `create_payment` returned an authoritative payment-page URL
  (`PaymentCreationResult.gateway_url`), but the service persisted only
  `result.track_id`. The view then rebuilt a redirect from the bare track id, so
  providers that mint a distinct payment-page URL (Pasargad, SnappPay, TorobPay)
  could redirect the customer to a bare token instead of the real page.
- **Files changed.** `apps/orders/models.py` (new additive field
  `PaymentAttempt.gateway_redirect_url`), `apps/orders/migrations/0023_paymentattempt_gateway_redirect_url.py`
  (additive), `apps/orders/services/gateway_payment_service.py` (persist
  `gateway_url`, falling back to `extra['paymentPageUrl']`/`['url']`),
  `apps/orders/views.py` (`payment_initiate` prefers the persisted URL, falls
  back to `build_redirect_url` only when blank).
- **Fix.** The service now stores the authoritative URL in a field distinct from
  the tracking id. The view redirects to the persisted URL, and only derives from
  the track id (Zibal/Zarinpal) when no URL was returned. No URL is ever
  hardcoded or fabricated in production code.
- **Tests added.** `apps/orders/tests/test_payment_redirect_integration.py`:
  Pasargad/SnappPay/TorobPay redirect to the persisted `gateway_url`,
  Zibal/Zarinpal fall back to the derived URL with a blank persisted field, and
  two guards assert the production view and service contain no hardcoded
  `http(s)` URL.
- **Command + counts.** See the Group (a) command in §9. The redirect module
  contributes 9 tests, all passing.

### B2: gateway callback view rejected BNPL POST callbacks (HTTP 405)

- **Root cause.** `gateway_callback` was GET-only and returned
  `HttpResponseNotAllowed` for POST, reading only `request.GET`. BNPL providers
  (SnappPay/TorobPay) POST their callback body `{transactionId, state, amount}`
  to the returnURL, so their callbacks were rejected.
- **Files changed.** `apps/orders/views.py` (`gateway_callback` accepts GET and
  POST, merges GET+POST params as `callback_data`, narrow `@csrf_exempt` on this
  one public endpoint only).
- **Fix.** The callback accepts both verbs and merges params. The narrow
  `@csrf_exempt` is safe because callback fields are never trusted to confirm a
  payment: the server-to-server `verify_payment` (and capability-gated
  `settle_payment`) is the sole authority. A forged-success POST finalizes
  nothing.
- **Tests added.** `apps/orders/tests/test_callback_integration.py`: GET
  provider still finalizes, BNPL POST is not 405 and finalizes via verify+settle,
  a forged-success POST (verify mocked to fail, and verify raising) does NOT
  finalize, a duplicate POST is idempotent (one OK Transaction), and a
  cross-tenant callback returns 404 and leaves the foreign attempt untouched.
- **Command + counts.** See the Group (a) command in §9. The callback module
  contributes 9 tests, all passing (including the duplicate-callback and
  cross-tenant-rejection cases the reviewer asked to confirm are present).

### B3: card-to-card was treated as paid at selection

- **Root cause.** The offline card-to-card method risked being recorded as
  settled at selection, like COD, even though a customer bank transfer is not
  proven to have arrived.
- **Files changed.** `apps/orders/services/gateway_payment_service.py` (offline
  branch distinguishes `auto_collects_offline`), `apps/orders/gateways/card_to_card.py`,
  `apps/orders/services/card_to_card_payment_service.py` (merchant confirm/reject
  mirroring the COD confirmation pattern), `apps/orders/gateways/cod.py`
  (`auto_collects_offline=True`). v2 (2026-11-04) wired the merchant surface:
  `apps/dashboard/card_to_card_views.py`, two dashboard URLs, and the
  `can_confirm_card_to_card` context + confirm/reject forms in
  `order_detail.html` (see §0.1).
- **Fix.** Card-to-card stays `PENDING` at selection (no `verified_at`, order not
  paid, `card2card-` track id). An authorized merchant confirms the transfer
  exactly once via a conditional UPDATE from PENDING, writing a Transaction with
  `confirmed_by`, `advance_to_processing=False`, `send_sms=False`. COD keeps its
  SUCCEEDED-at-selection behavior (regression-guarded).
- **Tests added.** `apps/orders/tests/test_card_to_card_confirmation.py`:
  pending-at-selection, merchant confirmation pays once, rejection leaves the
  order pending without money, duplicate confirmation is idempotent, wrong amount
  rejected, canceled/non-card-to-card rejected, no SMS, and a COD
  non-regression case.
- **Command + counts.** See the Group (a) command in §9. The confirmation module
  contributes 16 tests, all passing.

### B4: idempotency was keyed globally, not by tenant + operation

- **Root cause.** The dedupe lookup matched by idempotency key alone, so a reused
  key could surface a foreign tenant's/operation's attempt, and a legitimate
  retry of a FAILED attempt could not proceed because the dead attempt still held
  the deterministic key (a verbatim re-persist collided on the global partial
  `unique(idempotency_key)` constraint).
- **Files changed.** `apps/orders/services/gateway_payment_service.py`
  (`initiate_payment`: dedupe scoped by store+order+gateway_config+amount with the
  key as an additional filter; order-row `select_for_update` plus in-lock
  re-check; `_key_to_persist` mints a distinct deterministic key whenever the
  supplied key is already held by any row (foreign reuse OR a prior final
  attempt), disambiguated by the per-identity attempt count so a retry after a
  FAILED attempt is never blocked).
- **Fix.** Tenant/operation isolation (a reused foreign key never returns a
  foreign attempt), single external charge on a legitimate same-operation retry,
  and retryability after a FAILED attempt (a fresh live attempt is created with a
  distinct deterministic key). Concurrency is serialized by the order-row lock
  plus the in-lock re-check; the partial unique constraint is the cross-session
  backstop.
- **Tests added.** `apps/orders/tests/test_idempotency_tenant.py` (reused key
  across tenants, amount-scoped non-reuse, single-charge retry, redirect-ready
  reuse, simulated-concurrent reuse, unique-constraint backstop) plus the retry
  cases in `apps/orders/tests/test_payment_integration_extra.py` (service-level
  retry after FAILED create, retry-then-callback finalizes once, and the
  end-to-end view retry).
- **Command + counts.** See the Group (a) command in §9. The idempotency module
  contributes 8 tests and the extra module contributes 3 retry tests, all
  passing.

### B5: BNPL cartList carried a single synthetic item

- **Root cause.** SnappPay and TorobPay built ONE synthetic cart item (count 1,
  amount = full total, shipping/tax 0), so real multi-item BNPL baskets were not
  represented and would not reconcile line-by-line.
- **Files changed.** `apps/orders/services/gateway_payment_service.py`
  (`build_order_cart_snapshot` forwards per-line OrderItem snapshots + order-level
  totals in TOMAN), `apps/orders/gateways/snappay.py` and
  `apps/orders/gateways/torobpay.py` (`_build_cart_list` builds real cartItems and
  allocates shipping/tax/discount to the documented cartList fields).
- **Fix.** The orchestrator forwards authoritative, immutable per-line snapshots
  for BNPL providers; the adapter still performs the single Toman -> Rial x10
  conversion. The built cartList reconciles EXACTLY to `int(grand_total) * 10`
  Rial for multi-item, discounted, and shipping+tax orders; a tampered line
  raises `GatewayAmountMismatchError` rather than sending a bad cart.
- **Tests added.** `apps/orders/tests/test_bnpl_cart_reconciliation.py`:
  per-line forwarding, real cartItem shape, exact Rial reconciliation across
  multi-item/discount/shipping+tax orders, and tamper detection.
- **Command + counts.** See the Group (a) command in §9. The reconciliation
  module contributes its tests, all passing.

### B1-B5: extra cross-blocker integration tests (this round)

`apps/orders/tests/test_payment_integration_extra.py` adds the two scenarios the
reviewer called out that were not yet directly proven end-to-end:

- **Payment retry** (3 tests): a FAILED attempt is retryable; the retry initiates
  a fresh live attempt (service and view), and a retry-then-callback finalizes the
  order exactly once with a single OK Transaction.
- **Failed BNPL settlement** (4 tests): for SnappPay/TorobPay, when
  `verify_payment` succeeds but `settle_payment` fails (returns failure OR raises)
  the order stays PENDING, the attempt is not SUCCEEDED, and no OK Transaction is
  written. A control test proves the SAME flow DOES finalize when settle succeeds,
  isolating the settle failure as the sole cause of non-finalization.

Duplicate callback and cross-tenant callback rejection are proven in
`test_callback_integration.py` and are not duplicated here.

**Exact command + counts.**
`python manage.py test apps.orders.tests.test_payment_integration_extra --verbosity 1`
→ **Ran 7 tests, OK. 0 failures, 0 errors, 0 skipped.**

---

## 8. Outstanding external dependencies

- **Pasargad, SnappPay, TorobPay — merchant credentials + IP whitelisting.** Each
  needs real merchant credentials, the merchant server IP whitelisted by the
  provider, and (for BNPL) the `returnURL` matching the whitelisted base. SnappPay
  grants stage access first and production only after a demo. Until then readiness
  stays `NOT_CONFIGURED`/`NEEDS_CREDENTIALS` and the provider is not selectable at
  real checkout. No sandbox or production verification was possible in this
  environment.
- **Saman, Parsian, Mellat, Sadad, Tejarat — official contracts.** Their official
  current documentation remained unreachable on 2026-11-03 (see §3). Each needs
  endpoints, auth, signing, currency unit, error codes, and sandbox details read
  from an official source before an adapter can be built. For Tejarat the real
  technical PSP must be confirmed (IranKish not assumed).
- **Authorized sandbox/live verification for Zarinpal and Zibal** before
  production activation (contract-tested only).

---

## 9. Test evidence

All commands run with `source .venv/bin/activate` active, Django 5.2, SQLite.
Date 2026-11-03.

**Build / config checks**

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

**Group A** (155 tests) —
`python manage.py test apps.orders.tests.test_gateway_admin apps.orders.tests.test_gateway_payment_service apps.orders.tests.test_payment_gateway_config apps.orders.tests.test_payment_service apps.orders.tests.test_payment_safety apps.orders.tests.test_payment_discrepancy apps.orders.tests.test_cod_confirmation --verbosity 1`
→ **Ran 155 tests, OK. 0 failures, 0 errors, 0 skipped.** (The one previously
failing test — the stale `snappay` assertion in `test_gateway_admin` — is green
after defect D-2.)

**Group B** (223 tests) —
`python manage.py test apps.orders.tests.test_pasargad_adapter apps.orders.tests.test_snappay_adapter apps.orders.tests.test_torobpay_adapter apps.orders.tests.test_saman_adapter apps.orders.tests.test_parsian_adapter apps.orders.tests.test_mellat_adapter apps.orders.tests.test_sadad_adapter apps.orders.tests.test_tejarat_adapter apps.orders.tests.test_zarinpal_adapter apps.orders.tests.test_card_to_card apps.orders.tests.test_checkout_readiness apps.orders.tests.test_payment_currency apps.orders.tests.test_payment_security apps.orders.tests.test_payment_migration_compat apps.orders.tests.test_feat005_provider_integration --verbosity 1`
→ **Ran 223 tests, OK. 0 failures, 0 errors, 0 skipped.**

**Second-round integration regression (B1-B5), grouped to finish under the
per-command timeout. Date 2026-11-03.**

- **Group (a), all new integration modules** (63 tests; v2 2026-11-04 added 6:
  5 HTTP-level card-to-card merchant-surface tests and 1 idempotency
  IntegrityError re-query test):
  `python manage.py test apps.orders.tests.test_payment_redirect_integration apps.orders.tests.test_callback_integration apps.orders.tests.test_card_to_card_confirmation apps.orders.tests.test_idempotency_tenant apps.orders.tests.test_bnpl_cart_reconciliation apps.orders.tests.test_payment_integration_extra --verbosity 1`
  -> **Ran 63 tests, OK. 0 failures, 0 errors, 0 skipped.**
- **Group (b), service + safety + security + currency + discrepancy**
  (86 tests):
  `python manage.py test apps.orders.tests.test_gateway_payment_service apps.orders.tests.test_payment_safety apps.orders.tests.test_payment_security apps.orders.tests.test_payment_currency apps.orders.tests.test_payment_discrepancy --verbosity 1`
  -> **Ran 86 tests, OK. 0 failures, 0 errors, 0 skipped.**
- **Group (c), card-to-card + COD confirmation** (32 tests):
  `python manage.py test apps.orders.tests.test_card_to_card apps.orders.tests.test_cod_confirmation --verbosity 1`
  -> **Ran 32 tests, OK. 0 failures, 0 errors, 0 skipped.**
- **Group (d), provider adapters** (145 tests):
  `python manage.py test apps.orders.tests.test_snappay_adapter apps.orders.tests.test_torobpay_adapter apps.orders.tests.test_pasargad_adapter apps.orders.tests.test_zarinpal_adapter apps.orders.tests.test_mellat_adapter apps.orders.tests.test_saman_adapter apps.orders.tests.test_sadad_adapter apps.orders.tests.test_parsian_adapter apps.orders.tests.test_tejarat_adapter --verbosity 1`
  -> **Ran 145 tests, OK. 0 failures, 0 errors, 0 skipped.**
- **Group (e), concurrency** (16 tests):
  `python manage.py test apps.orders.tests.test_payment_concurrency apps.orders.tests.test_coupon_concurrency --verbosity 2`
  -> **Ran 16 tests, OK (skipped=16).** All 16 skipped with reason
  `نیازمندِ PostgreSQL`; reported UNVERIFIED, never as passed (see §10).

Second-round totals: **326 passed, 0 failed, 16 skipped (Postgres-gated,
unverified)** (v2 2026-11-04: +6 over the original 320 from the card-to-card
merchant-surface and idempotency IntegrityError tests). No group timed out; a
timeout is never reported as a pass.
`python manage.py check` → `System check identified no issues (0 silenced).`;
`python manage.py makemigrations --check --dry-run` → `No changes detected`.

**Group C — concurrency** (16 tests, all skipped) —
`python manage.py test apps.orders.tests.test_payment_concurrency apps.orders.tests.test_coupon_concurrency --verbosity 2`
→ **Ran 16 tests, OK (skipped=16).** Every skip reason is verbatim
`نیازمندِ PostgreSQL` (the `@skipUnless(connection.vendor == "postgresql", ...)`
gate at `test_payment_concurrency.py:30` and `test_coupon_concurrency.py:25`
and `:142`). The skipped tests are:

`test_payment_concurrency.PaymentRaceTests`:
1. `test_callback_vs_cancellation_never_loses_or_double_counts_money`
2. `test_cod_confirmation_vs_cancellation_is_serialised`
3. `test_expiry_job_vs_callback_never_loses_money`
4. `test_mismatch_callback_vs_cancellation_keeps_evidence_and_restocks_once`
5. `test_parallel_checkouts_with_same_token_create_one_order_with_confirmed_amount`
6. `test_parallel_cod_confirmations_apply_exactly_once`
7. `test_parallel_duplicate_callbacks_apply_payment_once`
8. `test_parallel_duplicate_mismatch_callbacks_record_once`
9. `test_parallel_expiry_jobs_cancel_once`
10. `test_two_attempts_both_confirmed_pay_once_and_reconcile_the_other`

`test_coupon_concurrency`:
11. `ConcurrentCampaignExecutionTests.test_overlapping_runs_issue_each_customer_once`
12. `ConcurrentRedemptionTests.test_ledger_and_counters_stay_consistent_after_races`
13. `ConcurrentRedemptionTests.test_limit_n_allows_exactly_n`
14. `ConcurrentRedemptionTests.test_parallel_payment_success_applies_effects_exactly_once`
15. `ConcurrentRedemptionTests.test_per_customer_limit_holds_for_parallel_orders_of_one_customer`
16. `ConcurrentRedemptionTests.test_total_limit_one_is_never_exceeded_under_concurrency`

All 16 skips are reason `نیازمندِ PostgreSQL`. See §10 for why Postgres cannot be
provisioned here. A timeout is never reported as a pass; no group timed out.

**Admin / checkout verification against existing + new config records.** A Django
shell snippet (venv active, run inside a rolled-back transaction) exercised a
real `Store` with configs created and `readiness_status`/`is_selectable_at_checkout`
read:

```
DB vendor: sqlite
zibal    readiness= connected        selectable= True
cod      readiness= connected        selectable= True
pasargad readiness= not_configured   selectable= False
snappay  readiness= not_configured   selectable= False
torobpay readiness= not_configured   selectable= False
mellat   readiness= documentation_blocked selectable= False
```

This confirms a pre-existing `zibal` (configured) and `cod` config still render
`CONNECTED` and are selectable; the three newly implemented providers appear with
`NEEDS_CREDENTIALS`/`not_configured` readiness (NOT `documentation_blocked`) and
are NOT selectable until configured + activated; `mellat` stays
`documentation_blocked`. Adapter-level confirmation (`get_adapter`):

```
zibal    documentation_blocked= False caps= ['create','verify']
cod      documentation_blocked= False is_online= False caps= []
pasargad documentation_blocked= False caps= ['cancel','create','inquire','verify']
snappay  documentation_blocked= False caps= ['cancel','create','inquire','settle','verify']
torobpay documentation_blocked= False caps= ['cancel','create','inquire','settle','verify']
mellat   documentation_blocked= True  caps= []
saman    documentation_blocked= True  caps= []
```

**Browser QA.** The chrome-devtools MCP was not reachable from this execution
context, so browser QA of the admin finance page and checkout is
**environment-limited**. No simulated browser run is presented as real. The
admin/checkout behavior above was verified instead via the Django ORM and the
`test_gateway_admin` HTTP-client tests (which render
`/admin-portal/settings/?section=payment-config` and exercise activate/toggle).

---

## 10. Remaining security and concurrency risks

- **PostgreSQL row-level-lock concurrency is UNVERIFIABLE here.** This sandbox has
  `psycopg 3.3.7` in the venv but NO PostgreSQL server binaries — `which pg_ctl
  initdb postgres psql` returns none (exit 4) — and no reachable or launchable
  instance. The `select_for_update`-based race tests are therefore Postgres-gated
  and SKIP on SQLite (the 16 tests in §9). SQLite does NOT prove Postgres
  row-level locking, and this report makes no such claim. The orchestrator's
  locking design (order-then-attempt `select_for_update`, conditional status
  transitions, idempotent reconciliation) is reviewed statically in §6 but must be
  validated against a real PostgreSQL instance before production sign-off.
- **No provider is sandbox- or production-verified.** Zarinpal, Zibal, Pasargad,
  SnappPay, and TorobPay are contract-tested with mocks only. Real provider
  behavior (auth edge cases, timeout/settle semantics, IP whitelisting, error
  codes in the wild) is unverified. `is_active` stays `False` for all online
  providers.
- **Five PSPs remain blocked** on unreachable documentation; building them from
  guesses would be unsafe and is explicitly avoided.
- **Credential key operations.** Fernet key rotation would invalidate stored
  credentials by design (fail-closed); operators must follow the documented key
  lifecycle in `docs/deployment/PRODUCTION_CONFIGURATION.md`.

---

## 11. New commits and updated SHA

New commit subjects on `feature/kiro-payment-engine-20261103` above `83b2053d`
(oldest first):

1. `test(payments): regression proving pre-existing zibal/cod configs survive additive gateway_code extension` (`0379623b`, FEAT-001)
2. `feat(payments): real Pasargad/Dorsa IPG REST adapter + contract tests` (`ab56c263`, FEAT-002)
3. `feat(payments): real SnappPay + TorobPay BNPL REST adapters + contract tests` (`e1a6562f`, FEAT-003)
4. `fix(payments): refresh stale readiness test for reclassified providers` (FEAT-004)
5. `docs(payments): PR35 gap analysis + updated matrices + QA evidence` (FEAT-004, base of the B1-B5 round)
6. `fix(payments): persist authoritative gateway redirect URL end-to-end (B1)` (`c9e49ef5`)
7. `fix(payments): accept POST gateway callbacks with narrow csrf_exempt (B2)` (`4fc3f5f5`)
8. `fix(payments): keep card-to-card PENDING until merchant confirmation (B3)` (`407b01d7`)
9. `fix(payments): scope idempotency by tenant+operation and guard concurrency (B4)` (`3042a380`)
10. `fix(payments): forward real order-item cart snapshots to BNPL adapters (B5)` (`8d92f33a`)
11. `test+docs: extra payment integration tests and updated PR35 reports (B1-B5)` (FEAT-007, this round; also hardens the B4 retry-after-FAILED key path)

**Final head SHA: `<PLACEHOLDER — orchestrator fills this after the last commit>`.**

---

## 12. Updated Pull Request status

- **PR #35 remains UNDER REVIEW and is NOT authorized for merge.**
- Project classification: **PARTIALLY DELIVERED.** The payment engine, the two
  facilitators (Zarinpal, Zibal), the two offline methods (COD, card-to-card),
  and three additional providers (Pasargad, SnappPay, TorobPay) are implemented
  and contract-tested. Five PSPs remain documentation-blocked, and no new provider
  is sandbox- or production-verified. PostgreSQL row-lock concurrency is
  unverifiable in this environment.
- Outstanding before any merge/production authorization: merchant credentials +
  IP whitelisting and authorized sandbox verification for the implemented
  providers; official contracts for the five remaining PSPs; and a PostgreSQL run
  of the concurrency suite.
