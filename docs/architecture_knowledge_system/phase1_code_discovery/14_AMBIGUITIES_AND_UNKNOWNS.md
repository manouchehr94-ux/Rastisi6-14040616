# 14 — Ambiguities and Unknowns

Explicit record of ambiguous ownership, unconfirmed claims, and verification limits. Nothing here
is hidden behind confident prose (governing rule §31).

---

## 1. AMBIGUOUS_OWNERSHIP

| # | Concept | Competing owners | Why ambiguous |
|---|---|---|---|
| A1 | "Seller/tenant" entity | `stores.Store` vs `catalog.Vendor` | Store docstring says they are distinct (ADR-1) and Vendor is not replaced, but the coexistence/relationship contract is not fully expressed in code; Vendor's ongoing role was not fully traced. |
| A2 | Footer configuration | `StorefrontLayoutVersion.footer_config` vs `content.FooterSettings` vs `global_region_registry` footer variant | Three representations, no single authority (doc 12 M2). |
| A3 | "Page" | `storefront_builder.StorefrontPage` vs `content.ContentPage` | Two distinct "page" models (doc 12 M3). |
| A4 | Order payment gateway | `orders.PaymentGateway` (legacy slug) vs `orders.PaymentGatewayConfig` (config) | `payment_initiate` fuzzy-matches; "which gateway" is not single-sourced (doc 12 M4). |
| A5 | `ShopSettings` write authority | `core` (owner) vs `dashboard` views + `sms_service` (writers) | Owned by core, mutated elsewhere directly (doc 06 §11). |
| A6 | Subscription lifecycle | `subscriptions` (owner) vs `billing` (driver) | Funneled through subscription_service, but effectively co-owned (doc 12 M7). |
| A7 | Storefront write surface | legacy R3 views vs R4 mutation service | Both wired; legacy fail-closed by flag; which is canonical depends on `r4_editor_enabled` (doc 12 H3). |
| A8 | Ownership transfer | `membership_service.transfer_ownership` vs `ownership_transfer_service` | Two implementations (doc 12 M6 / doc 13 D3). |
| A9 | Section placement | `StorefrontCell.section` vs `StorefrontSection.cell` vs `row_key/row_span` | Three coexisting mechanisms (doc 12 M12). |

## 2. UNKNOWN — not established from available evidence

| # | Question | Why unknown |
|---|---|---|
| U1 | Exact client→server endpoints hit by R4 editor JavaScript | `static/` JS not read line-by-line; `r4/mutate/` is INFERRED from server design. |
| U2 | Whether `membership_service.transfer_ownership` has a live (non-test) caller | Not conclusively traced (doc 13 D3). |
| U3 | Whether `resolution.require_resolved_store` is consumed anywhere | Docstring says unused "in this PR"; later consumers not confirmed (doc 13 D6). |
| U4 | Full bodies of several smaller services (orders tax/shipping/best_seller; subscriptions entitlement/enforcement/usage; billing account/consistency/period_utils; stores domain_consistency/namespace/typo/enamad/integration; portal handoff/owner_sms/platform_config/turnstile/rate_limit) | Characterized from signatures/docstrings/callers, not read line-by-line (INFERRED responsibilities). |
| U5 | Exact assertion content of individual tests | Test *existence* verified; bodies not opened for most (mapping INFERRED). |
| U6 | Whether any external deployment relies on the simulation payment path | Cannot be established from repo; requires deployment knowledge. |
| U7 | Precise line numbers in `orders/models.py` beyond ~640 | File exceeded single-read; ranges marked `~`. |
| U8 | Dynamic-import reachability of otherwise-unreferenced modules | Lazy/local imports are pervasive (cycle avoidance); a module lacking a module-level import is not necessarily dead. |
| U9 | Whether `catalog.Vendor` is still actively created/used at runtime vs vestigial | Not traced in this phase. |

## 3. INFERRED claims that would benefit from confirmation
- Portal onboarding views are the writers of `Store.onboarding_stage` / `onboarding_completed_at`
  (inferred from onboarding routes + Store docstring; onboarding views not read line-by-line).
- Platform-admin views mutate user activation/suspension and domain primary (inferred from URL names).
- The R4 editor persists via `r4/mutate/` (inferred from `r4_mutation_service` single-boundary design).

## 4. Verification limitations (method)
- ~214k LOC; not every file read. High-risk financial and storefront paths read in depth; other
  services characterized from signatures/callers.
- Persian/RTL content occasionally defeated ripgrep line matching; enumeration in those files used
  `read_file`/`bash grep`.
- Existing documentation was **not** consulted (governing rule §6), so any design intent stated only
  in `docs/**` is intentionally absent from this discovery and will be reconciled in a later phase.

## 5. Nothing was resolved by assumption
Where ownership was unclear it is labeled `AMBIGUOUS_OWNERSHIP`; where reachability was unclear it is
labeled `POTENTIALLY_DEAD` or `UNKNOWN`. No canonical architecture decision was made (governing
rule §26); the future architecture is explicitly out of scope for Phase 1.
