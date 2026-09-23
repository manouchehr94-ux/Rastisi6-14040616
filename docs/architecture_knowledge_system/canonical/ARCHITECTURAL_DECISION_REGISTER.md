# Architectural Decision Register (OPEN)

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 2 / Phase 4 (doc 08)
open_decisions: DR-1, DR-2, DR-3, DR-4, DR-5, DR-6, DR-7, DR-8
```

The canonical register of unresolved architectural decisions carried forward from Phase 4. **All
are OPEN.** Nothing here is resolved. No option may be selected without explicit Product-Owner
authorization in a later, separately-authorized phase.

> **Count note (STEP-0):** the Phase 4 claim matrix has **6** `decision_required=YES` flags; this
> DR register has **8** items (DR-1…DR-8) because several DRs originate from Phase 1/2 findings
> rather than a reconciled document claim. Do not conflate the two counts.

---

## DR-1 — `Order.payment_status`: single canonical writer + transition guard
- **Problem:** `Order.payment_status` has 3 writers and no `ALLOWED_TRANSITIONS` guard.
- **Current code reality:** `gateway_payment_service` (lock+conditional PENDING→PAID);
  `payment_service.simulate_payment` (direct save, no Order lock, prod-gated); `refund_service`
  (direct save → REFUNDED). Only `Order.status` has a transition table.
- **Existing design intent:** `PAYMENT_ARCHITECTURE.md §4` documents only the gateway writer
  (STALE/incomplete — Phase 4 S1).
- **Why a decision is needed:** money field with duplicate mutation paths and no guard; correctness/
  financial-integrity risk.
- **Affected domains:** orders (primary), cart/sms (side effects).
- **Affected models/services:** `Order`, `Transaction`, `PaymentAttempt`; `payment_service`,
  `gateway_payment_service`, `refund_service`, `order_service`.
- **Risk if ignored:** inconsistent/undetected illegal payment-state transitions; divergent writers.
- **Options identified:** (a) guarded `payment_status` transition service all writers call;
  (b) reduce to gateway+refund writers with an explicit guard, simulate→test-only; (c) document & accept.
- **Required evidence before deciding:** production reachability of `simulate_payment`; whether any
  deployment relies on it; downstream consumers of each transition.
- **Decision status: OPEN.**

## DR-2 — `content` domain write boundary
- **Problem:** content is Store-owned data but has no write service; `dashboard/views.py` mutates it
  directly (83 sites) — finding H2.
- **Current code reality:** `apps/content/services.py` is resolve/cleanup/newsletter only.
- **Existing design intent:** SAAS_MIGRATION_PLAN PR-8 frames content as a Store-owned domain
  (implies service discipline) — Phase 4 S3.
- **Why needed:** no service/transaction boundary; business logic in the controller layer.
- **Affected:** content (all models), dashboard.
- **Risk if ignored:** uncontrolled multi-object writes, no atomic boundary, ownership blur.
- **Options:** (a) extract a content service layer; (b) formally sanction dashboard-as-content-service
  and document; (c) partial extraction of highest-risk writes.
- **Required evidence:** transaction/atomicity needs of multi-object footer/menu edits; volume of
  affected view code.
- **Decision status: OPEN.**

## DR-3 — Service-layer write discipline for settings/config
- **Problem:** `ShopSettings`, shipping/tax, `PaymentGatewayConfig` written directly by dashboard
  views, against ADR-58/69 service-layer intent (Phase 4 X2 / M5).
- **Current code reality:** direct `.save()` in `dashboard/views.py` (incl. credential encryption).
- **Existing design intent:** ADR-58/ADR-69 (service-layer-only writes).
- **Why needed:** documented discipline vs actual second write surface.
- **Affected:** core (ShopSettings), orders (config), dashboard.
- **Options:** (a) route through owning-domain services; (b) document the exception explicitly.
- **Required evidence:** which config writes carry invariants that a service should enforce.
- **Decision status: OPEN.**

## DR-4 — Ownership-transfer duplication
- **Problem:** TWO **live** owner-transfer paths (Phase 2 C1).
- **Current code reality:** `stores.membership_service.transfer_ownership` (dashboard route
  `staff/<pk>/transfer-ownership/`, synchronous) **and** `stores.ownership_transfer_service`
  (portal two-party OTP-gated).
- **Existing design intent:** ADR-30 (staff mgmt immediate access) + ownership-transfer ADRs;
  intent unclear on which is canonical.
- **Why needed:** duplicate mutation path for `StoreMembership` owner reassignment with different
  guarantees (synchronous vs OTP-gated).
- **Affected:** stores, portal, dashboard.
- **Options:** (a) OTP flow canonical, route dashboard through it; (b) keep both with documented
  division; (c) deprecate one.
- **Required evidence:** intended security posture for owner transfer; UI entry points in use.
- **Decision status: OPEN.**

## DR-5 — Dual gateway representation
- **Problem:** `orders.PaymentGateway` (legacy order-chosen slug) vs `orders.PaymentGatewayConfig`
  (operational config); `payment_initiate` fuzzy-matches — finding M4.
- **Current code reality:** both models exist; ambiguity in "which gateway."
- **Existing design intent:** ADR-7/ADR-10 separate provider from config but don't resolve the dual model.
- **Options:** (a) converge on `PaymentGatewayConfig`; (b) formal mapping contract; (c) document.
- **Required evidence:** all read/write sites of both models; migration cost.
- **Decision status: OPEN.**

## DR-6 — Legacy-path removal
- **Problem:** SAAS_MIGRATION_PLAN PR12 = "legacy-path removal," but legacy paths coexist:
  `simulate_payment` (gated), R3 editor (fail-closed), legacy `Transaction` (back-compat).
- **Current code reality:** all present at `5883a140` (H1, H3).
- **Existing design intent:** PR12 (DESIGN_INTENT_ONLY, unrealized — Phase 4 DI-2).
- **Options:** (a) complete removal; (b) keep as intentional rollback/compat and document policy+guards.
- **Required evidence:** whether R3/simulation/Transaction still have consumers; rollback needs.
- **Decision status: OPEN.**

## DR-7 — `Store` vs `catalog.Vendor` ownership
- **Problem:** ADR-1 defers Vendor's final meaning; ambiguity persists in code (A1).
- **Current code reality:** both models exist; `Order` FKs `Vendor`; coexistence contract not
  fully expressed.
- **Options:** (a) dedicated catalog-domain review to define Vendor; (b) record permanent coexistence contract.
- **Required evidence:** Vendor's live runtime role (creation sites, multi-seller semantics).
- **Decision status: OPEN.**

## DR-8 — `stores.resolution.require_resolved_store` disposition
- **Problem:** no live caller found; may be intentional API scaffolding (D6).
- **Current code reality:** only its own docstring/exception references it.
- **Options:** (a) adopt at intended boundaries; (b) remove; (c) document as reserved API.
- **Required evidence:** intended consumers; whether a later commit adds one.
- **Decision status: OPEN.**

---

## Decision → affected-domain quick map
| DR | Primary domain(s) | Finding |
|---|---|---|
| DR-1 | orders | H1 |
| DR-2 | content, dashboard | H2 |
| DR-3 | core, orders, dashboard | M5/X2 |
| DR-4 | stores, portal, dashboard | M6/A8 |
| DR-5 | orders | M4 |
| DR-6 | orders, storefront_builder | H1/H3/DI-2 |
| DR-7 | catalog, stores | A1 |
| DR-8 | stores | D6 |

Each domain pack's `OPEN_DECISIONS.md` lists the DRs affecting it.
