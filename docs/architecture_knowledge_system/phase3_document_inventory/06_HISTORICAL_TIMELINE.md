# 06 — Historical Timeline

Documentation authored-date timeline (from `git log --diff-filter=A`, date range
**2026-07-28 → 2026-09-20**). This reconstructs the *documented* evolution and shows why several
authoritative-looking docs are point-in-time. Dates are Git author dates; filesystem mtimes are
the 2026-09-23 checkout and are not used.

---

## Era 1 — SaaS Foundation (2026-07-28 → 2026-08-07)
The oldest and most authoritative-tier documents.
- `SAAS_ARCHITECTURE.md`, `SAAS_DOMAIN_DECISIONS.md` (→07-31), `PAYMENT_ARCHITECTURE.md`,
  `SAAS_MIGRATION_PLAN.md`, `00_PROJECT_MASTER_REFERENCE.md` (→08-07),
  `docs/docs/product/spec/*`, early `reports/PHASE_1B…1F` admin/catalog reports.
- **Character:** defines Store as tenant boundary, ADR record (ADR-1…), payment PR1 foundation,
  staged migration plan. Written *during* the SaaS foundation build; contains in-text PR-status
  ("PR 4.1 … open as a pull request") that is now stale.

## Era 2 — Universal Storefront reset (2026-08-11 → 2026-08-14)
- `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` (08-11), `UNIVERSAL_STOREFRONT_PHASE1_ARCHITECTURE.md`,
  `…PHASE2_RENDERER.md`, `…U1A_TEMPLATE_REGISTRY_DECISION.md`,
  `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` (08-14).
- **Character:** the "architecture reset" from coded families → one universal engine + presets.
  Design intent. The code (R4/A8) has since implemented this direction.

## Era 3 — V2 phase build + families retirement (mid–late August 2026)
- `STOREFRONT_BUILDER_V2_PHASE_0_5…PHASE_8_*` report/audit pairs, `…LEGACY_RETIREMENT_MAP.md`,
  `…ROUTE_RENDERER_MAP.md`, `…REUSE_MATRIX.md`; root `SIX_NEW_FAMILIES_*`.
- **Character:** executes the reset; the retirement map documents deleting
  `family_registry.py`/`preset_registry.py` — which Phase 1/2 confirmed absent in code.

## Era 4 — Design Engine / R4 / A8 / Phase-5 (2026-08-30 → 2026-09-20)
- `docs/superpowers/plans/*` (2026-08-30 → 09-19) and `docs/superpowers/specs/*` — dated
  implementation plans/designs for R4 phase0/1, 50-template design engine, A8 template DNA,
  golden-reference storefront, appearance convergence, lifecycle safety, vertical slice,
  legacy convergence, and Phase-5 workstreams (W4a–W5c).
- `docs/architecture_audits/2026-09-05-…` + `final_closure_pack/*`,
  `docs/architecture_decisions/2026-09-05-…`, `docs/architecture_reviews/2026-09-05-…`.
- `docs/project_status/2026-09-20-rastisi-phase5-project-status.md` — the newest doc; references
  branch `feature/phase5-design-expansion` and HEAD `851181c3…` (a different ref than the frozen
  audit snapshot `5883a140`).
- **Character:** the R4-default, 50-Ready-Template, canonical-editor-safety world that Phase 1/2
  found in code. `r4_editor_enabled=True` and the fail-closed legacy guard match the W5A
  "canonical editor safety" plan.

---

## Why the timeline matters for reconciliation
1. **Foundation-era architecture docs (Era 1) are unstamped point-in-time snapshots.** Their
   PR-status prose predates the frozen snapshot by ~2 months. Core model claims likely still
   MATCH_CODE; their status narration is STALE.
2. **The storefront story spans Eras 2–4** and mirrors the code's R3→R4→A8 layering. The *latest*
   storefront intent (Era 4, R4-default) matches code; earlier family docs are SUPERSEDED.
3. **The newest status doc (2026-09-20) points at a different branch/commit** than the audited
   `5883a140` — a reminder that documentation Git references are not the audit baseline.

## Freeze reminder
This timeline is documentation history only. The **code** baseline under audit remains
`5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb`. Newer branches referenced by docs
(`feature/phase5-design-expansion`, HEAD `851181c3…`) are **not** merged, rebased, or read as code.
