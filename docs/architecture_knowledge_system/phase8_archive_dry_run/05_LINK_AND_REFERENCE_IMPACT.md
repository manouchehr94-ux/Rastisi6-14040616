# Phase 8 — Link and Reference Impact

> **DRY RUN ONLY.** No links were rewritten. This is impact *analysis*.

## 1. Reference sources scanned

Two reference indexes were built (line-scan of Markdown links and code/string
occurrences; stdlib-only, no network):

| Index | What it captures | Distinct doc paths |
| --- | --- | --- |
| Canonical/domain AKS references | doc paths cited by the canonical layer + 15 domain packs | 14 |
| Code / template / script references | doc paths cited by `apps/**`, `templates/**`, scripts, specs | 41 |

## 2. Link-impact buckets

Every reference to a document targeted for archive is classified into one of the
four buckets defined for this phase:

| Bucket | Meaning | Phase-8 handling |
| --- | --- | --- |
| `LINK_CAN_UPDATE` | Markdown cross-link inside a doc that we control and may safely rewrite in a future execution | Rewrite `docs/…` → `docs/archive/…` during execution |
| `CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY` | Path cited from code/templates/scripts | **Never auto-changed**; target doc held in place |
| `HISTORICAL_REFERENCE` | Reference from an already-historical doc | No action; both may be archived together |
| `UNKNOWN` | Reference whose nature could not be determined | Held; escalate to review |

## 3. Headline safety result

**No archive candidate carries any incoming repository reference.**

| Metric | Value |
| --- | --- |
| `ARCHIVE_CANDIDATE` rows | 417 |
| …with `link_break_risk = HIGH` | **0** |
| …with `link_break_risk = MEDIUM` | **0** |
| …with `link_break_risk = LOW` | 417 |
| …with `incoming_repo_links_count > 0` | **0** |

This is by construction: the disposition engine downgrades **any** referenced
document out of `ARCHIVE_CANDIDATE` into `KEEP_HISTORICAL_REFERENCE` (Tier P3
reference back-pressure). Therefore the archive-candidate set is, by definition,
**reference-free**, and executing the archive moves cannot break a canonical
cross-link or a code path.

## 4. Documents held *because* they are referenced (22)

These would otherwise look archivable but were retained in place because a
reference points at them. They are `KEEP_HISTORICAL_REFERENCE`.

### 4.1 Held by canonical/domain AKS references (`REFERENCED_BY_CANONICAL`)

| Document | Canonical refs |
| --- | --- |
| `docs/reports/PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md` | 2 |
| `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md` | 2 |
| `docs/reports/PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md` | 2 |
| `docs/docs/product/reports/ADMIN_PANEL_COMPLETION_REPORT.md` | 2 |
| `docs/reports/PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` | 1 |
| `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md` | 1 |
| `docs/prototypes/README.md` | 1 |
| `docs/references/beraito-exact-frontend-v5/README.md` | 1 |
| `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/failures/README.md` | 1 |

### 4.2 Held by code/template/script references (`CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY`)

| Document | Reason |
| --- | --- |
| `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1A_REPORT.md` | cited by code/spec |
| `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_7_REPORT.md` | cited by code/spec |
| `docs/reports/PRODUCT_ENTRY_FULL_PAGE_ROOT_CAUSE.md` | cited by code (×2) |
| `docs/reports/PRODUCT_ENTRY_FINAL_FUNCTIONAL_REPAIR_AUDIT.md` | cited by code |
| `docs/qa_evidence/storefront_appearance_convergence/phase1/task6_explicit_local_variant.md` | cited by code |
| `docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md` | cited by code |
| `docs/qa_evidence/storefront_appearance_convergence/phase4/pre_task10_r4_cutover.md` | cited by code |
| `docs/qa_evidence/storefront_appearance_convergence/phase4/task9_legacy_retirement.md` | cited by code (×2) |
| `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/00_certified_w4a_fingerprints.md` | cited by code |
| `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/w4b_curation_inventory.md` | cited by code |
| `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/implementation/23_repair_round2_smoke_evidence.md` | cited by code |

(13 documents in §4.1 + §4.2 lists shown above are the referenced subset; the
remaining `KEEP_HISTORICAL_REFERENCE` docs without a live reference are retained
by conservative default.)

## 5. Stale code references observed (do NOT auto-fix)

The code scan surfaced doc citations that use **stale or relative paths** that no
longer resolve to the real file location, e.g. code cites
`docs/architecture/SAAS_DOMAIN_DECISIONS.md` (12×) while the actual current file
is `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`. Likewise
`docs/deployment/PRODUCTION_CONFIGURATION.md` (3×) vs the real
`docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md`.

These are **pre-existing** inaccuracies in code comments/strings. Phase 8:

- does **not** modify code to fix them (out of scope; production code frozen);
- does **not** treat them as a reason to move the real (protected) target;
- records them here so a future documentation-hygiene phase can address the code
  comments deliberately.

## 6. Link-rewrite plan (for the future execution phase only)

When (and only when) archive execution is approved:

1. For each moved doc, compute the prefix rewrite `docs/<rel>` → `docs/archive/<rel>`.
2. Apply rewrites **only** to Markdown links inside documents we control
   (`LINK_CAN_UPDATE`).
3. Never touch `CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY` targets — those docs
   are not in the archive set, so no rewrite is needed.
4. Re-run the validator; require PASS 0/0 before committing each batch.

Because the archive-candidate set is reference-free (§3), the expected number of
`LINK_CAN_UPDATE` rewrites required for the current candidate set is **0** — the
moves are self-contained. Any future re-classification that promotes a referenced
doc into the archive set would reintroduce rewrites and must re-run this analysis.
