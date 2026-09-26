# Phases 2–4 Master Report

**System:** Rastisi — multi-tenant SaaS storefront platform (Django 5.2, Persian/RTL).
**Branch:** `docs/architecture-knowledge-system` (used exclusively; no switch/merge/rebase).
**Scope of this report:** STEP 0 (Phase 1 report repairs) + Phase 2 (validation) + Phase 3
(documentation inventory) + Phase 4 (documentation↔code reconciliation).
**Governing document:** `docs/architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md`.

> This is the consolidated delivery for Phases 2–4. It does **not** begin canonical rewriting,
> Domain Knowledge Pack creation, archiving, deletion, remediation, or Phase 5+.

---

## 1. Immutable commit identifiers

```
frozen_production_snapshot (audited): 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb
governing_document_commit:            1bc347404194067c529652c0a56a6c1210b4c092
phase1_artifact_commit:               6e88c2c41448b2a7b6a73fb89bfb57e183b78147
phase1_metadata_followup_commit:      326c83c5822f5571f4f2bab68ff9d934ede76001
phase1_report_repair_commit (STEP 0): 684db7452cab74a853c23f00c044687dd9eadc2e
phase2_validation_commit:             3e3fd8c4596bece0f7de1f5fd5aa6dc219d3c273
phase3_inventory_commit:              852ada0290ab5a091a5c007ae23f93b2b0187cc8
phase4_reconciliation_commit:         cfd794d5a0cc28b1e9de51d8eeb9454d52d951f3
branch_HEAD_at_this_report:           cfd794d5… (this report adds a further commit; its SHA is
                                       recorded by Git, never embedded self-referentially)
```

Production code is **identical** to the frozen snapshot: `git diff --stat 5883a140 HEAD -- apps/
shop_core/ templates/ static/` is empty across all phases. Every code citation reflects `5883a140`.

---

## 2. STEP 0 — Phase 1 report repairs (commit 684db745)
Three bookkeeping corrections, applied transparently:
- **A. Commit/SHA terminology** — replaced the self-referential "ending HEAD" with explicit
  immutable identifiers (audited snapshot, governing-doc, artifact, metadata-followup,
  report-repair). No document claims to contain its own current commit SHA.
- **B. Potentially-dead count** — recalculated from doc 13: the "8 findings" figure was an
  *investigation-record* count (D1–D8), not a candidate count. Corrected buckets: at STEP 0,
  5 actual POTENTIALLY/POSSIBLY_DEAD candidates + 1 conditionally-live (D2) + 1 live-but-inert (D8)
  + 1 confirmed-removed (D5). (Phase 2 later refined this to 4 candidates — see §3.)
- **C. Flow count** — clarified 15 numbered flows / 16 flow sections (Flow 3a/3b).

## 3. Phase 2 — Independent validation (commit 3e3fd8c4)
Re-verified the highest-impact Phase 1 findings **directly against the frozen code** (exact file/
line/route citations), classifying each CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED /
UPGRADED / NOT_PROVEN / DISPROVED.

**Phase 1 findings confirmed:**
- **H1 CONFIRMED** — `Order.payment_status` has exactly 3 writers (`gateway_payment_service`
  conditional-locked; `payment_service.simulate_payment` direct save; `refund_service` direct
  save); no `ALLOWED_TRANSITIONS` guard (the sole such table governs `Order.status`). Gateway path
  also creates a legacy `Transaction` "for dashboard back-compat" (duplicate record).
- **H2 CONFIRMED** — `apps/content` has no write service (`services.py` is resolve/cleanup/
  newsletter only); `apps/dashboard/views.py` performs all content CRUD (83 save/delete/clean sites).
- **H3 CONFIRMED** — `r4_editor_enabled` defaults True; legacy R3 mutation routes fail-closed via
  `_require_legacy_editor_active` (Http404); `family_registry.py`/`preset_registry.py` confirmed
  absent; three generations (R3/R4/A8) present.
- All 9 AMBIGUOUS_OWNERSHIP items CONFIRMED (A8 UPGRADED); duplicate-source/parallel-impl claims
  CONFIRMED; the unguarded `payment_status` state machine CONFIRMED; no-signal design + cycle-
  avoidance edges CONFIRMED.

**Phase 1 findings corrected (transparent, in-place `[PHASE 2 CORRECTION]` annotations):**
- **C1 — D3 DISPROVED as dead.** `membership_service.transfer_ownership` IS live-called from
  `dashboard/views.py:5896` (route `staff/<pk>/transfer-ownership/`). Consequence: **two live**
  ownership-transfer paths exist (dashboard-direct + portal-OTP) → *upgrades* the M6/A8 duplication
  smell rather than removing it.
- **C2 — dead-count refinement.** Post-Phase-2 actual POTENTIALLY_DEAD candidates = **4**
  (D1, D4, D6, D7); unconfirmed remaining = **1** (D6 — `require_resolved_store`, no live caller,
  possibly intentional scaffolding).
- No substantive architecture risk finding was disproved; the only DISPROVED sub-claim was the
  *deadness* of D3, which strengthens the associated finding.

## 4. Phase 3 — Documentation inventory (commit 852ada02)
Existing docs treated as **evidence/history, not runtime truth**; READ only.
- **Corpus:** 3,182 files under `docs/**` (excl. knowledge system). 513 textual docs inventoried
  individually + 6 asset collections (~2,669 binary/asset files). Authored 2026-07-28 → 2026-09-20.
- **Machine-readable registry:** `phase3_document_inventory/02_DOCUMENT_INVENTORY.csv`.
- **Status-candidate totals (513 docs):** CURRENT_CANDIDATE 5, DESIGN_INTENT 20, SUPPORTING 17,
  HISTORICAL 39, PLAN_ONLY 31, QA_EVIDENCE 359, EVIDENCE_ONLY 42, UNKNOWN 0.
- **Key findings:** architecture-light/evidence-heavy corpus (only 5 authoritative-tier docs, all
  foundation-era 2026-07-28); storefront builder massively over-documented (Cluster C1: 60+ docs,
  4 generations); content/notifications/blog under- or un-documented; `SAAS_DOMAIN_DECISIONS.md`
  (the 106-ADR record) is the densest, most code-linked source; several naming hazards.

## 5. Phase 4 — Documentation↔code reconciliation (commit cfd794d5)
Reconciled 32 curated claims against the Phase 1/2 code-derived reality; disagreements preserve
both views. Classification: MATCHES_CODE / STALE / CONTRADICTS_CODE / HISTORICAL /
DESIGN_INTENT_ONLY / SUPERSEDED / DUPLICATE / UNVERIFIABLE.

**Totals:** MATCHES_CODE 22 · STALE 3 · CONTRADICTS_CODE 2 · DESIGN_INTENT_ONLY 2 · SUPERSEDED 1 ·
HISTORICAL 1 · UNVERIFIABLE 1 · DUPLICATE 0 (document-level). Claim-level `decision_required=YES`
flags: **6**; total architectural decisions requiring resolution (DR register): **8** (DR-1…DR-8).

**Contradictions with current code:**
- **X1 (`docs/README.md`)** — claims a `backend/ frontend/ infra/ docker/` layout; the repo is a
  flat Django project (`apps/`, `shop_core/`, …) with no such directories.
- **X2 (ADR-58/69 implied service-layer-only discipline)** — violated by the dashboard view layer's
  direct writes to content/settings/config (Phase 2 H2/M5). (Product *import* itself honors ADR-58.)

**Stale:** S1 (PAYMENT_ARCHITECTURE §4 omits 2 of 3 `payment_status` writers + REFUNDED — H1);
S2 (SAAS_ARCHITECTURE PR-status prose); S3 (content ownership modeled, no service boundary — H2).

**Historical-design-intent:** the Universal V2 spec + migration plan explain the *why* behind the
R4/universal engine (intent now realized; legacy removal pending — PR12).

**Superseded:** ADR-93 (email/password owner identity) → ADR-102 (mobile OTP, shared phone
identity), which the code follows.

**Unresolved architecture decisions identified (not made): DR-1…DR-8** — payment_status canonical
writer+guard (H1); content write boundary (H2); settings/config service discipline (M5); ownership-
transfer duplication (A8/M6); dual gateway model (M4); legacy-path removal (H1/H3/PR12); Store vs
Vendor (A1); `require_resolved_store` disposition (D6).

**Archive candidates (advisory only, nothing archived):** family-era + superseded V2 phase docs;
prelaunch/product-entry reports; QA-as-architecture audit sets; reference kits/prototypes.
`docs/README.md` should be **corrected**, not archived.

**Candidate canonical documents:** `SAAS_DOMAIN_DECISIONS.md` (Tier 1, 106 ADRs), `SAAS_ARCHITECTURE.md`,
`PAYMENT_ARCHITECTURE.md`, `00_PROJECT_MASTER_REFERENCE.md`, + storefront Tier 2 (Universal V2 spec +
legacy retirement map) + Tier 3 (migration plan, production config, third-party notices) — paired
with the Phase 1/2 code-derived layer as the authoritative "what."

## 6. Documentation readiness by domain (Phase 4 doc 08 Part C)

| Rating | Count | Domains |
|---|---:|---|
| READY | 1 | stores (D1) |
| PARTIAL | 7 | portal (D2), catalog (D4), orders (D6), subscriptions (D7), billing (D8), dashboard (D11), core (D14) |
| POOR | 4 | customers (D3), cart (D5), content (D10), SMS (D12) |
| MISSING | 2 | notifications (D13), blog (D15) |
| CONFLICTED | 1 | storefront_builder (D9 — over-documented across generations) |
| **TOTAL** | **15** | — |

> **[STEP-0 CORRECTION]** Earlier the PARTIAL row read "8 … (+1)" (D10 double-counted as
> POOR/MISSING), summing to 16. Corrected: D10 = POOR; PARTIAL = 7 (enumerated explicitly);
> totals sum to 15.

Highest-priority documentation gaps for future Domain Knowledge Packs: **content (D10)** (the H2
mutation authority is entirely undocumented), **storefront de-confliction (D9)**, and the
POOR/MISSING domains.

## 7. Files created / modified

**Created (this task, all under `docs/architecture_knowledge_system/`):**
- `phase2_validation/` (8 files: 00–07)
- `phase3_document_inventory/` (9 files: 00–08, incl. `02_DOCUMENT_INVENTORY.csv`)
- `phase4_reconciliation/` (12 files: 00–11, incl. `01_CLAIM_RECONCILIATION_MATRIX.csv`)
- `PHASES_2_TO_4_MASTER_REPORT.md` (this file)

**Modified (this task, transparent annotations only — no original conclusion deleted):**
- `phase1_code_discovery/12_ARCHITECTURE_SMELLS.md` (M6 `[PHASE 2 CORRECTION]`)
- `phase1_code_discovery/13_POTENTIALLY_DEAD_OR_ORPHANED.md` (D3 correction + count table)
- `phase1_code_discovery/14_AMBIGUITIES_AND_UNKNOWNS.md` (A8 + U2 resolution)
- `phase1_code_discovery/15_PHASE1_MASTER_ARCHITECTURE_REPORT.md` (STEP 0 repairs + Phase 2 dead-count)

Knowledge-system file count at this report: 53 (before this file).

## 8. Confirmations
- **No production code changed:** CONFIRMED — `git diff --stat 5883a140 HEAD -- apps/ shop_core/
  templates/ static/` is empty. Tests and migrations untouched.
- **No old documentation modified/deleted/moved:** CONFIRMED — `git diff --name-only 5883a140 HEAD
  -- docs/` restricted to `docs/architecture_knowledge_system/`; no other `docs/**` path appears.
- **Source freeze honored:** CONFIRMED — analysis is of `5883a140` only; the 2026-09-20 status
  doc's branch/commit (`feature/phase5-design-expansion` / `851181c3…`) was not merged, rebased,
  or read as code.
- **No PR, no merge, no deletion, no archive/move:** CONFIRMED.
- **Writes confined to `docs/architecture_knowledge_system/**`:** CONFIRMED.

## 9. Exact Git commits pushed to `docs/architecture-knowledge-system`
```
684db745  STEP 0  Phase 1 report repairs
3e3fd8c4  Phase 2 validation + transparent Phase 1 corrections
852ada02  Phase 3 documentation inventory
cfd794d5  Phase 4 documentation-vs-code reconciliation
(this report adds one further commit on the same branch)
```

## 10. Limitations & unknowns
- Phase 2 is static analysis (no runtime execution); dynamic-import reachability remains a
  theoretical unknown, though all validated items were resolved by explicit route/caller/config
  evidence.
- Phase 3 status candidates for QA_EVIDENCE/EVIDENCE_ONLY docs are directory/era heuristics, not
  per-file reads.
- Phase 4 reconciled 32 curated claims; the 106-ADR record was sampled at header level + targeted
  reads for HIGH-finding-relevant ADRs, not fully line-reconciled.
- Residual UNKNOWNs carried forward: Store vs `catalog.Vendor` role (A1/DR-7), `require_resolved_store`
  intentionality (D6/DR-8), R4 client-JS endpoint mapping (INFERRED), and internal doc-vs-doc
  PR-numbering (UNVERIFIABLE, CL-30).

---

## 11. STOP
Phases 2–4 are complete and pushed. Per the task instructions, work **STOPS here**. No canonical
documentation rewrite, Domain Knowledge Pack creation, archive execution, old-document deletion,
architecture remediation, production-code change, or Phase 5+ has been started. Awaiting
independent review before any next stage is authorized.

The central distinction remains preserved throughout:
> **WHAT THE CODE DOES** (Phase 1/2) ≠ **WHAT DOCUMENTATION CLAIMS** (Phase 3/4) ≠
> **WHAT THE ORIGINAL DESIGN INTENDED** ≠ **WHAT THE FUTURE CANONICAL ARCHITECTURE SHOULD BE**.
