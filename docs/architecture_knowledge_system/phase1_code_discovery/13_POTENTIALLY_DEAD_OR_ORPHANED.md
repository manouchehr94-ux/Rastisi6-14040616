# 13 — Potentially Dead / Orphaned Code

Per governing rule §19, a component is marked `POTENTIALLY_DEAD` only after checking entry
mechanisms; nothing is deleted in Phase 1. Each item lists the checks performed.

Evidence class legend as in doc 01.

---

## D1 — `apps/blog` storefront wiring — POTENTIALLY_DEAD — VERIFIED

`BlogPost` model exists; `admin.py` registers it; `views.py` is a stub (`render` import + comment,
no views); `tests.py` is 20 LOC.

| Check | Result |
|---|---|
| `urls.py` present | **No** (`apps/blog/urls.py` does not exist) |
| Included in any URLconf | **No** — only appears as the boilerplate example comment in `shop_core/urls.py` |
| Views defined | No (stub) |
| Referenced by storefront/dashboard | Not found |
| Admin registration | Yes |
| Tests | Minimal |

**Conclusion:** the model is reachable via Django admin only; there is **no storefront/dashboard
integration**. Storefront blog wiring is POTENTIALLY_DEAD. The model itself is not orphaned (admin
edits it). **Do not delete.**

## D2 — `orders.payment_service.simulate_payment` + simulation callback flow — CONDITIONALLY LIVE — VERIFIED

Gated by `settings.PAYMENTS_SIMULATION_ENABLED` (defaults to `DEBUG`). `checkout/payment-callback/<status>`
returns Http404 in production. Fully live in dev/tests.

| Check | Result |
|---|---|
| Called by code | Yes (simulation views) |
| Route | Yes, but Http404 unless flag enabled |
| Tests | Yes (`test_payment_service.py`) |

**Conclusion:** NOT dead; it is a **production-disabled** parallel path (see doc 12 H1). Its
partner legacy `Transaction` model is still written by the live gateway path too.

## D3 — `stores.membership_service.transfer_ownership` vs `ownership_transfer_service` — AMBIGUOUS / POSSIBLY DEAD — INFERRED

Two ownership-transfer implementations exist (doc 12 M6). The OTP flow (`ownership_transfer_service`)
has portal views and tests (`test_ownership_transfer_views.py`). Whether the direct
`membership_service.transfer_ownership` has a live caller (vs being test-only / internal helper)
was **not conclusively confirmed**.

| Check | Result |
|---|---|
| Called by code | UNKNOWN (not conclusively traced) |
| Tests | Referenced in membership tests |

**Conclusion:** POTENTIALLY_DEAD relative to the OTP flow — **unconfirmed**. Requires a caller trace
in a later phase.

> **[PHASE 2 CORRECTION 2026-09-23 — DISPROVED as dead]** Caller tracing found a live caller:
> `apps/dashboard/urls.py:390` route `staff/<int:pk>/transfer-ownership/` →
> `apps/dashboard/views.py:5896 staff_transfer_ownership` calls `transfer_ownership(...)`. So
> `membership_service.transfer_ownership` is **LIVE**, not dead. Consequence: there are **two
> live** ownership-transfer paths (this dashboard-direct path + the portal OTP
> `ownership_transfer_service`), which *strengthens* the duplication smell (doc 12 M6 / doc 14
> A8) rather than removing it. See `../phase2_validation/06_PHASE1_CORRECTIONS.md` (C1).

## D4 — `core.ShopSettings` legacy SMS fields — POTENTIALLY_DEAD (data) — VERIFIED

`ShopSettings` carries `sms_backend`, `melipayamak_*`, `kavenegar_api_key`. `sms_service` ignores
these except for the `SMSRASTI` backend selection; real SMS credentials come from
`portal.PlatformConfiguration`.

**Conclusion:** the non-SMSRASTI legacy SMS fields are POTENTIALLY_DEAD data kept for migration
back-compat. **Do not delete** (schema/back-compat implications).

## D5 — Removed storefront registries `family_registry.py` / `preset_registry.py` — CONFIRMED ABSENT — VERIFIED

`file_search` confirms these files do **not** exist (retired in a prior "Phase 7"). They remain
referenced only in docstrings and tests. No dead *code file* exists; the references are
POTENTIALLY_DEAD *documentation/test references*, not live code.

## D6 — `stores.resolution.require_resolved_store` — POSSIBLY UNUSED SCAFFOLDING — INFERRED

A docstring in resolution.py notes "Nothing in this PR consumes this helper." Whether a later commit
added a consumer was not confirmed.

**Conclusion:** POTENTIALLY_DEAD scaffolding — unconfirmed.

## D7 — Reserved authorization permission keys — INERT FORWARD-DESIGN — VERIFIED

`stores.authorization` defines permission constants marked "reserved — no view yet"
(e.g. ATTRIBUTE_MANAGE, CUSTOMER_EDIT, DOMAIN_MANAGE) plus coarse back-compat aliases "nothing reads
anymore". These are intentional forward-design; currently unreferenced by any view/decorator.

**Conclusion:** POTENTIALLY_DEAD constants (intentional). Not code paths.

## D8 — `content` media-cleanup functions (MED-001 no-ops) — LIVE-BUT-INERT — VERIFIED

`delete_media_asset_if_unreferenced` / `cleanup_reusable_media_file` are deliberately no-ops; call
sites remain but perform no deletion. Not dead (called), but functionally inert by design.

---

## Items checked and found LIVE (not dead), correcting an earlier inference

- **PAYMENT_SUCCESS / PAYMENT_FAILED SMS events** — **LIVE**, VERIFIED via grep. Wired in
  `orders/services/payment_service.py:92-100` and `orders/services/gateway_payment_service.py:353-357`.
  (An earlier sub-agent pass flagged these as possibly dead; direct grep disproved that.)
- **Notification `enqueue`/`notify_security_event`** — **LIVE**, VERIFIED. Called from
  `stores.deletion_service`, `stores.handle_service`, `stores.ownership_transfer_service`.
  (An earlier pass reported callers "not found"; they were located in `stores` services.)

---

## Count reconciliation (STEP-0 repair)

This document holds **8 investigation records (D1–D8)**; they are not all POTENTIALLY_DEAD:

| Bucket | Count | Records |
|---|---:|---|
| Actual POTENTIALLY / POSSIBLY_DEAD candidates | 5 | D1, D3, D4, D6, D7 |
| Conditionally-live | 1 | D2 |
| Live-but-inert | 1 | D8 |
| Confirmed-removed / absent (not live code) | 1 | D5 |
| Confirmed-live corrections (separate section below) | 2 | payment SMS; notification callers |

Of the 5 candidates, **D3 and D6 are unconfirmed** (carried into Phase 2 for caller tracing);
D1, D4, D7 are VERIFIED as their stated (limited) kind of deadness. The Phase 1 master report
(doc 15, Part F / Part K item 17) uses these recalculated figures.

> **[PHASE 2 CORRECTION 2026-09-23]** After Phase 2 caller tracing, **D3 is DISPROVED as dead**
> (it is live — see the D3 note above). The post-Phase-2 buckets are therefore:
> **actual POTENTIALLY_DEAD candidates = 4** (D1, D4, D6, D7), of which **unconfirmed = 1** (D6
> only; no live caller found, possibly intentional API scaffolding). D1/D4/D7 remain CONFIRMED as
> their limited kind of deadness. See `../phase2_validation/06_PHASE1_CORRECTIONS.md` (C2).

## Method note
Signals were checked exhaustively (none exist), so no component can be "dead" merely for lacking a
signal receiver. Dynamic imports were not exhaustively enumerated; lazy/local imports are used
widely for cycle avoidance, so absence of a *module-level* import does not prove deadness. All
"POSSIBLY/POTENTIALLY" items above are explicitly non-conclusive and carried forward to doc 14.
