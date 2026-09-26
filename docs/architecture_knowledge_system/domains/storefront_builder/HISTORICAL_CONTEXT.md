# storefront_builder — Historical Context

```
domain_id: D9
code_baseline: 5883a140
open_decisions: DR-6
```

This domain has the largest historical documentation footprint (Cluster C1: 60+ docs across four
generations). Evidence/history only — not modified/moved/archived here.

| Document(s) | Level | Relationship to code | Label |
|---|---|---|---|
| `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` | L3 design intent | Realized: R4 + universal engine + presets (CL-25). "Proposed" label is now stale (realized). | DESIGN-INTENT-REALIZED |
| `docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` | L3 support | MATCHES_CODE — documents deleting `family_registry.py`/`preset_registry.py` (confirmed absent). The **de-confliction key** for old family docs. | AUTHORITATIVE-MAP |
| `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_0_5..PHASE_8_*` (report/audit pairs, ~24) | L4 | HISTORICAL — phase build records | HISTORICAL |
| `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` | L3 spec | DESIGN_INTENT (one of 3 spec homes) | DESIGN-INTENT |
| `docs/superpowers/plans+specs/**` (R4, design engine, A8, appearance convergence, W4/W5) | L3/L4 | Plans/designs; the latest (W5A canonical-editor-safety) MATCHES code (r4_editor_enabled + fail-closed) | PLAN/DESIGN |
| `docs/architecture_audits/final_closure_pack/**`, `docs/project_status/2026-09-20-…` | L4 | QA/status; W5A–W5C outcomes match code | QA/STATUS |
| root `SIX_NEW_FAMILIES_*` | L4/L5 | SUPERSEDED — family era, retired | SUPERSEDED |

## Key historical narrative
1. **Families** (coded per-family storefronts) → demonstrated a structural limitation.
2. **Universal V2 reset** (2026-08) → one engine + presets; families frozen/archived (not deleted
   then; registries later deleted).
3. **R4 + A8 Design Engine + Phase-5** (2026-08→09) → the current R4-default, 50-Ready-Template,
   canonical-editor-safety world.

The code at `5883a140` reflects generation 3 as current, with R3 retained fail-closed for rollback.

## De-confliction guidance for readers
When an old storefront doc contradicts the current path, trust [GENERATIONS](GENERATIONS.md) + the
retirement map. Family-era docs are SUPERSEDED. The V2 spec explains WHY, not the current WHAT.
