# Known Architecture Risks

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (docs 12/13) / Phase 2 (docs 01-06)
open_decisions: DR-1..DR-8
```

Consolidated Phase 1/2 findings. Severity is change-risk/correctness/duplication impact, not
inflated. Findings were re-verified directly against code in Phase 2. **These are recorded, not
repaired** (remediation is a separately-authorized future phase).

---

## HIGH
- **H1 — Duplicate order-payment + unguarded `Order.payment_status`.** Two payment implementations
  (legacy `Transaction`+`simulate_payment` vs new `PaymentAttempt`+`gateway_payment_service`); 3
  writers of `payment_status`; **no transition guard**. CONFIRMED (Phase 2 doc 01). → DR-1, DR-6.
  Detail: [`../domains/orders/`](../domains/orders/README.md).
- **H2 — `content` has no write service; dashboard views mutate it directly** (83 sites).
  CONFIRMED. → DR-2. Detail: [`../domains/content/`](../domains/content/README.md).
- **H3 — Three storefront editor/template generations coexist** (R3 legacy fail-closed / R4 default
  / A8 ready templates). CONFIRMED. → DR-6. Detail:
  [`../domains/storefront_builder/`](../domains/storefront_builder/README.md).

## MEDIUM (M1–M15)
- **M1** duplicate appearance/theme/palette sources (`appearance_registry`, `palette_pack_64`,
  `theme_catalog`, mirrored into header/footer_config). **M2** footer represented 3 ways.
  **M3** two "page" concepts. **M4** dual gateway representation (`PaymentGateway` vs
  `PaymentGatewayConfig`) → DR-5. **M5** dashboard direct writes to settings/config → DR-3.
  **M6** two ownership-transfer implementations (**both live** — Phase 2 C1) → DR-4.
  **M7** billing co-owns subscription state machine (funneled). **M8** derived store-visibility
  spans ≥5 signals, fails open. **M9** orders→cart cross-domain mutation. **M10** dual settings
  validation (Strangler). **M11** dual media representation on placements. **M12** dual/parallel
  section-placement mechanisms. **M13** latent circular-dependency management. **M14** asymmetric
  import/export placement. **M15** `is_staff` overloaded three ways.

## LOW (L1–L4)
- **L1** `simulate_payment` lacks Order `select_for_update` (prod-gated). **L2**
  `checkout_item_update/remove` mutate CartItem outside the checkout fence. **L3** duplicated
  PageType strings kept in sync by a test. **L4** parallel "already paid" guards.

## OBSERVATION (O1–O4)
- **O1** no signals anywhere (deliberate explicit-coupling). **O2** MED-001 media-cleanup no-ops.
  **O3** reserved authorization permission keys (inert). **O4** historical tenant-bleed fixed.

## Potentially dead / orphaned register (post-Phase-2)
| ID | Item | Status |
|---|---|---|
| D1 | `apps/blog` storefront wiring | POTENTIALLY_DEAD (admin-only model; no urls/views) |
| D2 | `simulate_payment` + sim callback | CONDITIONALLY LIVE (prod-gated) |
| D3 | `membership_service.transfer_ownership` | **LIVE** (Phase 2 disproved dead — dashboard route) |
| D4 | `ShopSettings` legacy SMS fields | POTENTIALLY_DEAD (data) |
| D5 | removed `family_registry.py`/`preset_registry.py` | CONFIRMED ABSENT (doc/test refs only) |
| D6 | `resolution.require_resolved_store` | POTENTIALLY_DEAD (no live caller; maybe intentional API) → DR-8 |
| D7 | reserved authorization permission keys | inert forward-design |
| D8 | `content` MED-001 no-ops | LIVE-BUT-INERT |

Post-Phase-2 actual POTENTIALLY_DEAD candidates = **4** (D1, D4, D6, D7); unconfirmed = **1** (D6).

## Risk → decision map
| Risk | Decision |
|---|---|
| H1, L1, L4, Transaction dup | DR-1, DR-6 |
| H2 | DR-2 |
| M5 | DR-3 |
| M6 (two live transfer paths) | DR-4 |
| M4 | DR-5 |
| H3 legacy coexistence | DR-6 |
| A1 Store vs Vendor | DR-7 |
| D6 require_resolved_store | DR-8 |

See [`ARCHITECTURAL_DECISION_REGISTER.md`](ARCHITECTURAL_DECISION_REGISTER.md).
