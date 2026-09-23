# Phase 8 — Canonical Dependency Check

> **DRY RUN ONLY.** Verifies that the proposed archive set does not undermine the
> canonical Architecture Knowledge System. No changes made.

## 1. Purpose

Before any archive move is contemplated, we must prove that **nothing the
canonical layer depends on is scheduled for archive**. This document is that guard.

## 2. What the canonical layer references

The canonical/domain AKS scan found **14 distinct doc paths** referenced from the
canonical layer. Grouped by disposition:

| Referenced document | Disposition | Protected? |
| --- | --- | --- |
| `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/docs/product/architecture/SAAS_ARCHITECTURE.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` | `KEEP_CANONICAL_SUPPORT` | P1 |
| `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` | `KEEP_CANONICAL_SUPPORT` | — |
| `docs/reports/PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/reports/PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/reports/PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/docs/product/reports/ADMIN_PANEL_COMPLETION_REPORT.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md` | `KEEP_HISTORICAL_REFERENCE` | P3 |
| `docs/README.md` | `CORRECT_IN_PLACE_LATER` | — |

## 3. Guard result

| Check | Result |
| --- | --- |
| Any canonical-referenced doc in the `ARCHIVE_CANDIDATE` set? | **NO (0)** |
| Any canonical-referenced doc in `DEFER_REVIEW`? | **NO (0)** |
| Any canonical-referenced doc scheduled to move? | **NO (0)** |
| All 14 referenced docs retained in place? | **YES** |

**PASS.** Every document the canonical layer references is retained in place
(either `KEEP_CANONICAL_SUPPORT`, `KEEP_HISTORICAL_REFERENCE`, or
`CORRECT_IN_PLACE_LATER`). The archive-candidate set has **zero** overlap with
the canonical dependency set.

## 4. Protected canonical source docs — confirmation

All eight Tier-P1 protected source docs are present in the manifest with
`KEEP_CANONICAL_SUPPORT` and `special_handling = PROTECTED_CANONICAL_SOURCE`
(except the two V2 docs, which additionally anchor the storefront_builder domain
and are also referenced by code):

- `SAAS_DOMAIN_DECISIONS.md`, `SAAS_ARCHITECTURE.md`, `PAYMENT_ARCHITECTURE.md`,
  `SAAS_MIGRATION_PLAN.md` — under `docs/docs/product/architecture/`
- `00_PROJECT_MASTER_REFERENCE.md` — under `docs/docs/product/`
- `PRODUCTION_CONFIGURATION.md` — under `docs/docs/product/deployment/`
- `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md`,
  `STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` — under `docs/architecture/`

## 5. AKS tree self-protection

All rows under `docs/architecture_knowledge_system/**` are
`KEEP_CANONICAL_SUPPORT` with `special_handling = PROTECTED_AKS_TREE`. The archive
plan never targets its own knowledge system.

## 6. Conclusion

The proposed archive set is **canonically safe**: relocating the 417 archive
candidates cannot orphan any canonical reference. This check must be **re-run** if
any document is ever reclassified from a keep/defer disposition into
`ARCHIVE_CANDIDATE`.


---

## `[PHASE 8 CORRECTIVE REVIEW]` — canonical guard re-verified at exact-path level

The PASS verdict above (no canonical-referenced doc scheduled to move) is
**reaffirmed and strengthened**. The original guard checked the 14 distinct paths
the canonical layer references. The corrective exact-path scan additionally
confirmed that **files reachable only via a collection pseudo-row** are also not
canonically referenced-then-moved: where such a file *was* referenced by a
canonical/AKS/retained doc (11 files), it was **downgraded to
`KEEP_HISTORICAL_REFERENCE`** and removed from the execution set.

Re-verified guard results against `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`:

| Check | Result |
| --- | --- |
| Execution paths referenced by a canonical/domain AKS doc | **0** |
| Execution paths referenced by an AKS Phase-1…8 doc | **0** |
| Execution paths referenced by any retained (KEEP/legal/correct) doc | **0** |
| Execution paths referenced by live code/scripts/templates | **0** |
| Root mandatory docs (`SIX_NEW_FAMILIES_*`) dispositioned | **YES** (both `KEEP_HISTORICAL_REFERENCE`) |

**PASS (corrected).** The 3065-file execution set is canonically safe at exact-path
granularity.
