# 04 — Documents/Claims That CONTRADICT Current Code

`CONTRADICTS_CODE` = the document asserts something that is **actively false** against the frozen
snapshot (not merely out of date). Both views are preserved; neither is assumed superior.

Claim IDs refer to `01_CLAIM_RECONCILIATION_MATRIX.csv`.

---

## X1 — CL-29 — `docs/README.md` describes a repository layout that does not exist

```
DOCUMENT CLAIM (docs/README.md):
  Repository layout:
    backend/   Django backend
    frontend/  Frontend source
    docs/      Official documentation
    prototypes/ HTML/UI references
    infra/     Infrastructure
    docker/    Containers
    scripts/   Utilities

CODE REALITY (VERIFIED via find):
  The repo is a single flat Django project at the root:
    apps/  shop_core/  templates/  static/  manage.py  requirements.txt  docs/  scripts/  tools/
  There is NO backend/, frontend/, infra/, or docker/ directory anywhere.

CLASSIFICATION: CONTRADICTS_CODE (structural)
POSSIBLE EXPLANATION: An aspirational/boilerplate README from an early multi-service layout idea
  that the project never adopted (it stayed a monolithic Django project).
DECISION REQUIRED: NO for architecture; the fix is a doc correction in a later phase. Low risk
  (README is a stub) but actively misleading to a newcomer.
```

## X2 — CL-22 — "Service-layer-only writes / no second write path" contradicted by the dashboard view layer

```
DOCUMENT CLAIM (ADR-58 + ADR-69):
  ADR-58: "Product Import Writes Only Through the Existing Service/Model Layer — Never a Second
           Product-Creation Path."
  ADR-69: "Limits Are Enforced in the Service Layer, So Imports and Bulk Actions Cannot Bypass Them."
  (General discipline: mutations go through the owning domain's service layer.)

CODE REALITY (Phase 2 doc 01 H2 + doc 02, VERIFIED):
  The merchant dashboard view layer (apps/dashboard/views.py) writes MANY other-domain models
  DIRECTLY, bypassing any owning-domain service:
    - core.ShopSettings (settings_* views: direct .save())
    - ALL content.* models (ContentPage/Menu/Footer/Hero/Banner/Social: direct .save()/.delete())
    - orders config (ShippingZone/Method/RateRule, TaxClass/TaxRate, PaymentGatewayConfig): direct
    - some catalog.Product / Category writes: direct
  content has NO write service at all. So a "second write surface" (the view layer) demonstrably
  exists for content, settings, shipping/tax, and gateway config.

CLASSIFICATION: CONTRADICTS_CODE (scope-limited)
NUANCE: The specific ADR-58 claim about *product import* is honored (import_service routes through
  catalog services). The CONTRADICTION is with the broader implied discipline: the code does have
  additional direct write paths at the view layer for content/settings/config (H2/M5). Inventory
  and order-status ARE service-mediated, so this is not a blanket contradiction.
POSSIBLE EXPLANATION: The service-layer discipline was applied to the high-risk domains
  (inventory, orders, subscriptions, billing) but not uniformly to content/settings/config.
DECISION REQUIRED: YES — HIGH finding H2 + MEDIUM M5. Future decision: extend service boundaries
  to content/settings/config, or explicitly document the dashboard-view-as-service pattern.
```

---

## Summary
| ID | Doc | Contradiction | Severity | Decision? |
|---|---|---|---|---|
| X1 | docs/README.md | claims backend/frontend/infra/docker layout; none exist | LOW (stub, misleading) | NO |
| X2 | ADR-58/69 (implied general discipline) | dashboard view layer directly writes content/settings/config (H2/M5) | HIGH (H2) | YES |

## Important interpretation (governing rule)
- X2 does **not** mean "the ADR is wrong and should be deleted." It means the code has a
  discipline gap relative to the documented intent. The ADR's *intent* (single service-mediated
  write path) is a legitimate design goal; the *code* currently violates it for
  content/settings/config. **Do not** resolve this by editing the ADR to match the code, nor by
  changing the code — that is a future remediation decision (doc 08), not Phase 4 work.
- X1 is a plain factual doc error safe to correct in a later documentation-rewrite phase.
