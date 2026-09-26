# 08 — Phase 3 Master Report (Documentation Inventory)

**Phase:** 3 — Complete documentation inventory.
**Baseline (code):** frozen at `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb` (unchanged).
**Rule:** existing docs are **evidence/history, not runtime truth**; they were READ only.

---

## 1. What Phase 3 produced
A comprehensive inventory of the repository documentation corpus with a machine-readable registry
(`02_DOCUMENT_INVENTORY.csv`), a landscape map, a status-candidate classification, duplicate/overlap
clusters, a domain→document map, a historical timeline, and an ambiguity register.

## 2. Corpus at a glance (VERIFIED)

| Metric | Value |
|---|---|
| Files under `docs/**` (excl. knowledge system) | 3,182 |
| Textual docs inventoried individually | 513 |
| Asset files (inventoried as 6 collections) | ~2,669 |
| Root guidance docs inventoried | 3 |
| Authored date range | 2026-07-28 → 2026-09-20 |
| CURRENT_CANDIDATE (authoritative-tier) docs | 5 |

## 3. Status-candidate totals (513 individual docs)

| status_candidate | count |
|---|---:|
| QA_EVIDENCE | 359 |
| EVIDENCE_ONLY | 42 |
| HISTORICAL | 39 |
| PLAN_ONLY | 31 |
| DESIGN_INTENT | 20 |
| SUPPORTING | 17 |
| CURRENT_CANDIDATE | 5 |
| UNKNOWN | 0 |

## 4. Key findings
1. **The corpus is evidence-heavy, architecture-light.** 78% (401/513) is QA/reference evidence;
   only 5 documents read as authoritative current architecture, all foundation-era (2026-07-28).
2. **The storefront builder is massively over-documented** (Cluster C1: 60+ docs, 4 generations,
   3–4 homes) — mirroring the R3→R4→A8 code layering. The *latest* intent (universal engine /
   R4-default) matches code; family-era docs are superseded.
3. **Several domains are under-documented** (doc 05): content (D10 — the H2 mutation-authority
   smell has no doc), notifications (D13), blog (D15), and thin coverage for customers, cart, and
   the SMS device gateway.
4. **The authoritative architecture docs are unstamped point-in-time snapshots** predating the
   frozen code by ~2 months, with in-text PR-status prose that is now stale.
5. **`SAAS_DOMAIN_DECISIONS.md` (4508L, ADR record)** is the densest and most code-referenced
   architecture source (code docstrings cite ADR-1…ADR-101); it is the top Phase-4 reconciliation
   target.
6. **Naming hazards** (doc 07): "Final Result At Last", "FINAL_AUDIT", multiple "spec"/"audit"
   homes, and a `docs/README.md` describing a `backend/frontend/infra/docker` layout that does
   **not** exist in the repo (structural contradiction → Phase 4).

## 5. Duplicate / overlap hot-spots (doc 04)
C1 storefront builder (heaviest), C2 spec fragmentation (3 homes), C3 audit/evidence sprawl
(4 homes), plus C4–C7 (payment vs billing audiences, master-ref vs SaaS-arch, product-entry
reports, reference kits).

## 6. Handoff to Phase 4
Phase 4 will reconcile document **claims** against the Phase 1/2 code-derived reality, assigning
MATCHES_CODE / STALE / CONTRADICTS_CODE / HISTORICAL / DESIGN_INTENT_ONLY / SUPERSEDED / DUPLICATE
/ UNVERIFIABLE. Priority targets:
- `SAAS_DOMAIN_DECISIONS.md` (ADRs cited by code), `SAAS_ARCHITECTURE.md`, `PAYMENT_ARCHITECTURE.md`
  (H1 state-ownership reconciliation), `SAAS_MIGRATION_PLAN.md`, `00_PROJECT_MASTER_REFERENCE.md`.
- `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` + `LEGACY_RETIREMENT_MAP.md` (H3 storefront reality).
- `docs/README.md` (structural contradiction).
- Family-era storefront docs (SUPERSEDED candidates).
- Under-documented domains → readiness = POOR/MISSING (doc 08 readiness in Phase 4).

## 7. Compliance
- No `docs/**` file outside the knowledge system was modified/moved/renamed/merged/deleted.
- No production code touched. Baseline `5883a140` unchanged. No merge/rebase; no other branch read.
- A temporary generator worktree (`_p3work`) was used to build the CSV and **removed**; it was
  never committed.

## 8. Limitations
- QA_EVIDENCE/EVIDENCE_ONLY status candidates are directory/era heuristics, not per-file reads.
- Deep reads focused on CURRENT_CANDIDATE + key DESIGN_INTENT/SUPPORTING docs carrying reconcilable
  claims. Individual claim extraction for Phase 4 is limited to the architecturally-significant set.
