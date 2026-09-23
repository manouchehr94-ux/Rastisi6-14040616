# Phase 8 — Deferred Documents

> **DRY RUN ONLY.** These documents receive no archive action. They are
> `DEFER_REVIEW`: a human must confirm completion/supersession before any future
> archive or keep decision.

## 1. Why defer

Plans, specs, roadmaps, and implementation charters describe *intended* work. In a
dry run we cannot reliably prove whether a given plan was:

- **executed and superseded** (safe to archive later), or
- **still open / partially done** (must stay), or
- **abandoned** (needs a human call).

Rather than guess, all such documents are `DEFER_REVIEW`,
`special_handling = PLAN_COMPLETION_UNVERIFIED`, `confidence = LOW`.

## 2. Count summary

| Sub-group | Count |
| --- | --- |
| `docs/superpowers/plans/**` | 26 |
| `docs/superpowers/specs/**` | 15 |
| Non-superpowers plans/roadmaps | 3 |
| **Total deferred** | **44** |

## 3. Non-superpowers plans / roadmaps (3)

| Document | Note for reviewer |
| --- | --- |
| `docs/architecture/STOREFRONT_BUILDER_V2_IMPLEMENTATION_PLAN.md` | V2 builder plan; confirm whether fully superseded by `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` before archiving |
| `docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_ARCHITECTURE_PLAN.md` | Architecture plan; check completion vs current builder architecture |
| `docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_IMPLEMENTATION_ROADMAP.md` | Roadmap; confirm items delivered before archiving |

## 4. Superpowers plans (26)

```
docs/superpowers/plans/2026-08-30-admin-v22-live-builder.md
docs/superpowers/plans/2026-08-30-admin-v2-phase2-prototype-alignment.md
docs/superpowers/plans/2026-08-30-claude-storefront-phase1-repair.md
docs/superpowers/plans/2026-08-30-claude-storefront-phase1-repair-prompt.md
docs/superpowers/plans/2026-08-31-storefront-builder-r4-phase0-phase1.md
docs/superpowers/plans/2026-09-01-storefront-design-engine-50-templates-implementation.md
docs/superpowers/plans/2026-09-02-storefront-design-engine-a8-50-template-dna.md
docs/superpowers/plans/2026-09-03-storefront-unified-implementation-roadmap.md
docs/superpowers/plans/2026-09-03-template-switch-preservation-implementation-plan.md
docs/superpowers/plans/2026-09-04-golden-reference-storefront-g1-plan.md          (also code-cited)
docs/superpowers/plans/2026-09-04-golden-reference-storefront-g2-plan.md          (also code-cited)
docs/superpowers/plans/2026-09-04-golden-reference-storefront-roadmap.md
docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md  (also code-cited)
docs/superpowers/plans/2026-09-06-storefront-lifecycle-safety-phase2-implementation-plan.md
docs/superpowers/plans/2026-09-06-storefront-vertical-slice-phase3-implementation-plan.md
docs/superpowers/plans/2026-09-08-storefront-phase4-builder-legacy-convergence.md
docs/superpowers/plans/2026-09-11-phase5-design-expansion-implementation-plan.md
docs/superpowers/plans/2026-09-14-phase5-task6-storefront-showcase-facade-implementation-plan.md
docs/superpowers/plans/2026-09-15-phase5-converged-completion-plan.md
docs/superpowers/plans/2026-09-16-phase5-w4a-public-shell-convergence-implementation.md
docs/superpowers/plans/2026-09-16-phase5-w4b-50-template-curation-implementation.md
docs/superpowers/plans/2026-09-17-phase5-w4c-all50-browser-certification.md       (also code-cited)
docs/superpowers/plans/2026-09-19-phase5-w5a-canonical-editor-safety.md
docs/superpowers/plans/2026-09-19-phase5-w5b-mobile-bottom-nav-r4-parity.md       (also code-cited)
docs/superpowers/plans/2026-09-19-phase5-w5c-ready-template-preview-ux.md
docs/superpowers/plans/2026-09-19-phase5-w5-merchant-design-experience-discovery.md
```

## 5. Superpowers specs (15)

```
docs/superpowers/specs/2026-08-30-claude-storefront-phase1-repair-design.md
docs/superpowers/specs/2026-08-31-storefront-builder-r4-design.md
docs/superpowers/specs/2026-09-01-storefront-design-engine-50-templates-design.md
docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-product-architecture.md
docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-unified-architecture-design.md
docs/superpowers/specs/2026-09-04-golden-reference-storefront-design.md            (also code-cited)
docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md
docs/superpowers/specs/2026-09-06-storefront-lifecycle-safety-phase2-design.md
docs/superpowers/specs/2026-09-06-storefront-vertical-slice-phase3-design.md
docs/superpowers/specs/2026-09-11-phase5-50-template-dna-design-lab-charter.md
docs/superpowers/specs/2026-09-11-phase5-design-expansion-charter.md
docs/superpowers/specs/2026-09-11-phase5-onboarding-demo-contextual-editor-charter.md
docs/superpowers/specs/2026-09-14-phase5-task6-storefront-showcase-facade-design.md
docs/superpowers/specs/2026-09-16-phase5-w4a-public-shell-convergence-design.md    (also code-cited)
docs/superpowers/specs/2026-09-16-phase5-w4b-50-template-curation-design.md        (also code-cited)
```

## 6. Reviewer guidance

1. For each plan/spec, confirm whether its deliverables are reflected in the
   current codebase (frozen baseline `5883a140`) and in the canonical layer.
2. If executed & superseded and **not** code-cited → may become
   `ARCHIVE_CANDIDATE` in a future pass.
3. If code-cited (marked *also code-cited* above) → keep in place regardless, or
   update the code citation deliberately in a separate change.
4. If open/ambiguous → keep as `KEEP_HISTORICAL_REFERENCE`.
5. Never delete.
