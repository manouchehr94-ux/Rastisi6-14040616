# 02 — Documents/Claims That MATCH Current Code

Claims reconciled as `MATCHES_CODE` (22 of 32). These are the documentation assets that a future
engineer can currently trust as describing the frozen snapshot `5883a140`. Claim IDs refer to
`01_CLAIM_RECONCILIATION_MATRIX.csv`.

---

## Tenancy & platform (foundation ADRs — strongly accurate)
- **CL-01 / CL-04 / CL-05** — Store is the authoritative tenant boundary; one explicit status
  (provisioning/active/suspended/closed); ownership via active OWNER `StoreMembership` (no
  `Store.owner`). Matches Phase 1 doc 03 + Phase 2.
- **CL-06 / CL-07** — Hostname-authoritative, fail-closed store resolution; middleware is not the
  complete auth boundary (auth via decorators). Matches Phase 1 Flow 0 + Phase 2 doc 05.
- **CL-20** — `admin_subdomain` platform-assigned, independent of `StoreDomain`; `/admin-portal/`
  canonical; `resolve_store_for_admin_request` enforcement. Matches.
- **CL-24** — `PlatformConfiguration` pk=1 singleton; owner identity mobile-OTP shared with
  customer phone identity (ADR-102). Matches Phase 1 doc 03 D2.

## Orders / payments (PAYMENT_ARCHITECTURE largely accurate)
- **CL-09** — Gateway success creates a `Transaction` + transitions order to PROCESSING (incl. the
  legacy Transaction "for dashboard back-compat"). Matches H1 code read exactly.
- **CL-10** — `select_for_update` + conditional PENDING→PAID update + `attempt.is_final`
  idempotency. Matches gateway_payment_service exactly.
- **CL-11** — Only MANUAL refund is real; gateway/automatic refunds not implemented (ADR-33).
  Matches (refund_service raises for GATEWAY).
- **CL-12** — COD marks attempt SUCCEEDED but order stays PENDING. Matches cod adapter.

## SaaS billing & subscriptions (ADR-72/73/75/76/77 accurate)
- **CL-14** — SaaS billing is a separate domain from merchant commerce payments (two money
  systems). Matches Phase 1 doc 02.
- **CL-15** — Webhooks land in a verified idempotent inbox before any business mutation;
  confirmation is one transactional idempotent service, never in the view. Matches
  webhook_service + confirmation_service exactly (Phase 1 Flow 7, doc 10).
- **CL-16** — Subscription transitions governed by `ALLOWED_TRANSITIONS` (ADR-66). Matches.

## Catalog / inventory (ADR-31/37/38 accurate)
- **CL-17** — Inventory is a `StockMovement` ledger; `Product/Variant.stock` is the single
  authoritative field; `WarehouseInventory` synced. Matches (QuerySet blocks bulk bypass).
- **CL-18** — Warehouse provisioning is an explicit idempotent service call, **never a Django
  signal**. Matches the codebase-wide 0-signals finding.
- **CL-19** — Checkout idempotency is a server-held token on `Cart`. Matches
  Cart.checkout_token → Order.idempotency_key.

## Returns / financial state (ADR-34/35 accurate)
- **CL-21** — `ReturnRequest` has its own state machine separate from `Order.status`; return/
  financial state lives in dedicated fields/rows. Matches model-level `ReturnRequest.ALLOWED_TRANSITIONS`.

## Storefront presentation (latest intent matches code)
- **CL-26** — `family_registry.py`/`preset_registry.py` deleted, replaced by
  `layout_preset_registry`. Matches (files confirmed absent; replacement present).
- **CL-27** — W5A canonical editor safety: one canonical mutation path, R3 rollback-only. Matches
  `r4_editor_enabled=True` + `_require_legacy_editor_active` fail-closed (H3).

## Partial-match with a recorded caveat
- **CL-02** — "Store is not Vendor; Vendor meaning deferred." The *documentation* accurately
  records the deferral; the code reflects the same unresolved ambiguity (A1). Classified
  MATCHES_CODE because doc and code agree that this is deferred — but `decision_required = YES`.
- **CL-13** — ADR-7/ADR-10 (provider vs store-config separation; direct models not a generic
  table) MATCHES, but the code additionally carries a **dual gateway representation**
  (`PaymentGateway` legacy + `PaymentGatewayConfig`) that the ADR does not fully resolve →
  `decision_required = YES` (see doc 08).

---

## Takeaway
The **SaaS foundation ADR record and the payment architecture doc are trustworthy** as
descriptions of the current code for the majority of their claims. This is unusually good
documentation fidelity for a foundation-era corpus. The exceptions are narrow and enumerated in
docs 03 (stale) and 04 (contradicts).
