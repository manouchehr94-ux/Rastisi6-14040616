# 07 — Unclassified or Ambiguous Documents

Documents whose status/ownership/naming is ambiguous or whose classification required judgement.
None were left `UNKNOWN` in the CSV, but the following warrant explicit flags for Phase 4.

---

## 1. Misleading names / locations (status-by-name hazard)

| Doc / group | Name implies | Actually is | Assigned |
|---|---|---|---|
| `docs/docs/product/Final Result At Last/**` | authoritative "final result" | reference prototypes (novinshop, rastisi-site) + Blueprint Vol.1 | EVIDENCE_ONLY |
| `docs/reports/PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` | canonical "final audit" | dated pre-launch consolidated report | HISTORICAL |
| `docs/architecture/*_PHASE_*_AUDIT.md` (10) | living architecture audits | point-in-time phase QA | QA_EVIDENCE |
| `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` | the "final spec" | one of three spec homes; design intent, unstamped | DESIGN_INTENT |
| `docs/architecture_audits/final_closure_pack/**` | "final closure" | 2026-09-05 appearance-convergence audit set (point-in-time) | QA_EVIDENCE |
| `docs/docs/` (double nest) + `docs/README.md` | top-level docs home | canonical docs are two levels deep; READMEs are stubs | SUPPORTING (stubs) |

## 2. Docs with no clear owning domain
- `docs/superpowers/**` — 41 dated plans/specs. Owner is "the storefront/design-engine effort"
  broadly, but individual charters span appearance, lifecycle, onboarding, showcase, mobile-nav.
  Grouped under storefront_presentation but several are cross-cutting IA/UX.
- `docs/audits/universal_storefront_engine_u3_u11_execution.md` — an execution log; audit vs plan
  hybrid. Classified QA_EVIDENCE.
- `docs/template-references/live-audit/**` and `lightweight-package-reference/**` — reference vs
  audit hybrid; classified EVIDENCE_ONLY.

## 3. `docs/README.md` factual mismatch (flag for Phase 4 CONTRADICTS_CODE)
`docs/README.md` describes a repository layout of `backend/ frontend/ infra/ docker/ scripts/`.
The **actual** repo is a single flat Django project (`apps/`, `shop_core/`, `templates/`,
`static/`, `manage.py`) with **no** `backend/`, `frontend/`, `infra/`, or `docker/` directories.
This is a concrete documentation-vs-code contradiction (structural), carried to Phase 4.

## 4. Root-level guidance ambiguity
- `CLAUDE.md` — states the canonical Git remote is `rastisi5` and references a `rastisi-code-map`
  skill + `graphify-out/` navigation. This is **agent operating guidance**, current in intent, but
  its claims (remote name, skill availability) are environment/tooling facts not verifiable from
  the frozen code snapshot. Classified SUPPORTING (agent-behavior); not an architecture doc.

## 5. Ambiguity that Phase 3 deliberately does NOT resolve
- Whether a CURRENT_CANDIDATE doc actually MATCHES the frozen code (e.g. does
  `PAYMENT_ARCHITECTURE.md`'s "State Ownership" section match the 3-writer reality?). This is a
  **Phase 4** reconciliation question, not a Phase 3 classification question.
- Whether foundation-era ADRs (ADR-1…ADR-101) are all still honored by code. Phase 4 will
  reconcile the specific ADRs that code docstrings cite.

## 6. Nothing left UNKNOWN
Every individually-inventoried textual doc received a non-UNKNOWN status candidate. The 6
collection rows are all reference/evidence. Residual ambiguity is captured above and forwarded to
Phase 4.
