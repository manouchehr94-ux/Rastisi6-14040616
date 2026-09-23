# 03 — Stale Documents / Claims

`STALE` = the document was accurate when written but the code has since moved, OR the document is
incomplete relative to the current code in a way that would mislead. The document is **not wrong
in intent**; it is out of date or partial. Preserve both views (governing rule).

Claim IDs refer to `01_CLAIM_RECONCILIATION_MATRIX.csv`.

---

## S1 — CL-08 — PAYMENT_ARCHITECTURE §4 "State Ownership" omits two `Order.payment_status` writers

```
DOCUMENT CLAIM (PAYMENT_ARCHITECTURE.md §4):
  PaymentAttempt.status → owned by gateway_payment_service
  Order.payment_status  → updated by gateway_payment_service on success
  (state diagram shows only PENDING→PAID / →FAILED)

CODE REALITY (Phase 2 doc 01 H1, VERIFIED):
  Order.payment_status has THREE writers:
    1. gateway_payment_service.process_callback_and_verify (lock + conditional update)  [documented]
    2. payment_service.simulate_payment  (direct save PAID/FAILED)                       [OMITTED]
    3. refund_service.execute_order_refund (direct save → REFUNDED)                      [OMITTED]
  There is NO ALLOWED_TRANSITIONS guard for payment_status. The REFUNDED state is not in
  the document's diagram.

CLASSIFICATION: STALE (incomplete)
POSSIBLE EXPLANATION: The doc is scoped "PR1 Foundation" and describes the gateway path only;
  simulate_payment is legacy (gated) and refund_service was added separately.
DECISION REQUIRED: YES — this is Phase 1/2 HIGH finding H1 (duplicate mutation path + unguarded
  field). Any future canonical payment doc must enumerate all writers and the (missing) guard.
```

## S2 — CL-03 — SAAS_ARCHITECTURE PR-status prose is out of date

```
DOCUMENT CLAIM (SAAS_ARCHITECTURE.md header):
  "PR 4.1 (explicit Store context propagation ...) is implemented on branch
   claude/store-context-service-propagation and open as a pull request — not yet merged."

CODE REALITY:
  Store context propagation (explicit Store argument to pricing/SMS services) is present and
  wired in the frozen snapshot. The "open PR / not yet merged" narration is a 2026-07-28
  point-in-time status.

CLASSIFICATION: STALE (point-in-time status narration)
POSSIBLE EXPLANATION: Foundation-era doc written mid-migration; never restamped.
DECISION REQUIRED: NO (the architecture claim is fine; only the status line is stale). A future
  canonical doc should drop in-line PR-status prose or stamp the code commit it describes.
```

## S3 — CL-31 — Content/navigation ownership implies a service boundary the code lacks

```
DOCUMENT CLAIM (SAAS_MIGRATION_PLAN PR 8 + ADR-style domain-ownership framing):
  "Content, navigation, homepage, blog and media ownership" is a modeled Store-owned domain with
  the same service-mediated discipline applied elsewhere.

CODE REALITY (Phase 2 doc 01 H2, VERIFIED):
  content models ARE Store-owned, BUT apps/content has NO write service — all ContentPage/Menu/
  MenuItem/FooterSettings/Hero/Banner/Social CRUD is performed directly in apps/dashboard/views.py
  (83 save/delete/clean sites). The domain has data ownership but no service boundary.

CLASSIFICATION: STALE (ownership modeled; service discipline not realized)
POSSIBLE EXPLANATION: PR 8 delivered the ownership FKs but the service-layer extraction the rest
  of the platform follows was not applied to content.
DECISION REQUIRED: YES — this is HIGH finding H2. A future decision: introduce a content service
  boundary vs. accept dashboard-as-content-service.
```

---

## Summary
| ID | Doc | Why stale | Decision? |
|---|---|---|---|
| S1 | PAYMENT_ARCHITECTURE.md §4 | omits simulate_payment + refund writers + REFUNDED (H1) | YES |
| S2 | SAAS_ARCHITECTURE.md header | PR-status prose predates snapshot | NO |
| S3 | SAAS_MIGRATION_PLAN PR8 framing | content ownership modeled, no service boundary (H2) | YES |

Stale ≠ archive: S1/S2 belong to otherwise-accurate CURRENT_CANDIDATE docs; they should be
**updated** (a later canonical-rewrite phase), not archived. S3 reflects a real code gap, not a
doc error, and feeds the decisions in doc 08.
