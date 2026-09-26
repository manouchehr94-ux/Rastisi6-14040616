# 01 — Documentation Landscape

A map of *where* Rastisi's documentation lives and *what kind* of content each area holds. This
is orientation; per-document classification is in doc 03 and the CSV.

---

## 1. High-level shape

The corpus is **large but heavily skewed to evidence/assets**: of 3,182 files under `docs/**`,
only 513 are textual documents and just **5 are canonical-candidate architecture specs**. The
bulk (~2,669 files) is QA screenshots, reference design kits, and HTML/JS/CSS prototypes.

```
docs/
├── docs/product/               ← the CANONICAL product+architecture home (oldest, foundational)
│   ├── architecture/           ← SAAS_ARCHITECTURE, SAAS_DOMAIN_DECISIONS, PAYMENT_ARCHITECTURE, SAAS_MIGRATION_PLAN
│   ├── 00_PROJECT_MASTER_REFERENCE.md
│   ├── deployment/             ← PRODUCTION_CONFIGURATION
│   ├── spec/                   ← 01-PROJECT-SPEC, 02-BUILD-INSTRUCTIONS (+ prototype HTML)
│   ├── reports/                ← Phase 1B–1F + admin/prototype/storefront implementation reports
│   └── Final Result At Last/   ← reference product/site prototypes (novinshop, rastisi-site) + Blueprint Vol.1
├── architecture/               ← STOREFRONT_BUILDER_V2_* (spec, phase reports/audits, maps) + UNIVERSAL_STOREFRONT_*
├── architecture_audits/        ← 2026-09-05 appearance audit + final_closure_pack (7 docs)
├── architecture_decisions/     ← appearance convergence decision baseline
├── architecture_reviews/       ← kiro appearance convergence workflow review
├── audits/                     ← unified architecture gap audit; U3–U11 execution
├── reports/                    ← PRELAUNCH_PHASE1–5, PRODUCT_ENTRY_*, storefront template/builder audits+plans
├── specs/                      ← RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN
├── superpowers/                ← plans/ (27) + specs/ (14): dated implementation plans & designs (Aug–Sep 2026)
├── qa_evidence/                ← 340 textual + many assets: harness runs, previews, certification
├── reference-kits/, references/, template-references/  ← external/reference design kits (assets)
├── prototypes/                 ← RastiSi_Admin_V2.2 master prototype + storefront-builder-v2 assets
├── storefront_templates/       ← dark_digital_v2 design contract
├── third_party/                ← license/attribution notices (palettes, plugin, skill)
├── project_status/             ← 2026-09-20 phase5 status
└── README.md, docs/README.md
```

## 2. The three documentation "generations" (mirrors the code's generational layering)

The docs themselves show the same R3→R4→A8 evolution Phase 1/2 found in code:

1. **Foundation (2026-07-28 → 08-07):** `docs/docs/product/` — SaaS architecture, domain
   decisions (ADR record), payment architecture, migration plan, master reference. This is the
   canonical-candidate tier.
2. **Storefront V2 / Universal reset (2026-08-11 → 08-14):** `docs/architecture/UNIVERSAL_*`,
   `docs/specs/…FINAL_SPEC…`, the `STOREFRONT_BUILDER_V2_*` phase set — the "architecture reset"
   from coded families to one universal engine + presets.
3. **Design Engine / R4 / A8 / Phase-5 (2026-08-30 → 09-20):** `docs/superpowers/plans+specs`,
   `docs/architecture_audits/final_closure_pack`, `docs/project_status/…` — R4 editor, 50 Ready
   Templates, appearance convergence, canonical-editor safety.

## 3. Naming hazards (documents whose location/name misleads about status)
- **`docs/docs/`** double-nesting: the *real* canonical product docs are two levels deep
  (`docs/docs/product/…`), not at `docs/`. `docs/README.md` and `docs/docs/README.md` are near-empty stubs.
- **`docs/docs/product/Final Result At Last/`** — the folder name reads as authoritative ("final
  result") but the contents are **reference prototypes** (novinshop, rastisi-site) and a Blueprint,
  not the running system. High mis-read risk.
- **`docs/architecture/…_SPEC.md`** vs **`docs/specs/…FINAL_SPEC…`** vs
  **`docs/superpowers/specs/…`** — three different "spec" homes.
- **`reports/` vs `architecture_audits/` vs `audits/` vs `qa_evidence/`** — overlapping evidence
  homes; several "audit" documents are point-in-time QA, not living architecture.
- **`PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md`** — "final audit" naming suggests canonical status but is
  a dated pre-launch report.

## 4. Where architecture truth is *claimed* to live
`docs/docs/product/architecture/` (SaaS) + `docs/architecture/` (storefront V2) are the two homes
that read as authoritative architecture. Both are **point-in-time**: the SaaS set is dated
2026-07-28 with in-text PR-status narration ("PR 4.1 … open as a pull request"), and the storefront
V2 spec is labelled "Proposed / Architecture Reset." Neither is stamped with the code commit it
describes. This is the core reconciliation problem for Phase 4.

## 5. Root-level guidance
- `CLAUDE.md` — agent operating guidance (use `rastisi-code-map` skill, Graphify navigation,
  preserve tenant isolation, canonical remote `rastisi5`). Operational/agent-behavior doc, current
  in intent; references tooling (`.claude/skills`, `graphify-out/`) rather than architecture.
- `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` / `…_REPORT.md` — plan + implementation report for a
  "six new families" effort; historical given the subsequent universal-engine reset.
