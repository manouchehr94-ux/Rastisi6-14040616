# 05 — Historical & Design-Intent Documents

Two related but distinct classes:
- **HISTORICAL** — describes past work / point-in-time state; valuable as the record of *how the
  system got here*, not as current runtime truth.
- **DESIGN_INTENT_ONLY** — describes what was *intended*; useful design rationale, and in Rastisi's
  case the intent has largely been realized by the code (or partially deferred).

Claim IDs refer to `01_CLAIM_RECONCILIATION_MATRIX.csv`. Document-level classifications draw on
Phase 3 doc 03.

---

## DESIGN_INTENT_ONLY

### DI-1 — CL-25 — Universal Storefront Builder V2 spec (the "architecture reset")
```
INTENT (UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md, "Proposed / Architecture Reset"):
  Replace multi-family coded storefronts with ONE universal engine + unified visual builder +
  reusable blocks + presets; freeze/archive families (do not delete) because they hold reusable work.
CODE REALITY:
  Realized. R4 is the canonical editor; layout_preset_registry + A8 (50 Ready Templates) provide
  presets; families retired (registries deleted). Phase 2 H3.
CLASSIFICATION: DESIGN_INTENT_ONLY — intent now implemented; the doc remains the best explanation
  of WHY the storefront architecture looks the way it does.
```

### DI-2 — CL-32 — SaaS Migration Plan (staged PR 1–14)
```
INTENT (SAAS_MIGRATION_PLAN.md):
  A staged PR sequence; PR12 = non-null enforcement + legacy-path removal; PR13 = PostgreSQL.
CODE REALITY:
  Foundation stages realized (Store, resolution, ownership, catalog, orders/payment separation),
  but legacy paths still coexist in the frozen code: simulate_payment (gated), R3 editor
  (fail-closed), legacy Transaction (written for back-compat). PR12 "legacy-path removal" is not
  fully done at 5883a140.
CLASSIFICATION: DESIGN_INTENT_ONLY — plan mostly executed; the "legacy removal" step is pending,
  which is consistent with the H1/H3 legacy-coexistence findings.
DECISION REQUIRED: YES — whether/when to complete legacy-path removal (future remediation).
```

## HISTORICAL

### H-1 — CL-28 — Phase-5 project status (2026-09-20)
```
CLAIM: Official branch feature/phase5-design-expansion, HEAD 851181c3...; W5A–W5C closed.
CODE REALITY: A different branch/commit than the audited 5883a140. The W5A "canonical editor
  safety" outcome DOES match code (r4_editor_enabled default True; R3 fail-closed).
CLASSIFICATION: HISTORICAL — a point-in-time status report. Its architectural outcomes match code;
  its Git references are not the audit baseline and were not read as code.
```

### Other HISTORICAL documents (document-level, from Phase 3 doc 03 §5)
- `docs/docs/product/reports/PHASE_1B…1F…`, `ADMIN_PANEL_COMPLETION_REPORT.md`, `PROTOTYPE_*`,
  `STOREFRONT_*` — implementation reports for the merchant-admin / catalog / storefront build.
- `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_*_REPORT.md` (10) — phase build reports.
- `docs/reports/PRELAUNCH_PHASE1–5…`, `PRODUCT_ENTRY_*` — pre-launch and product-entry reports.
- `docs/architecture_reviews/2026-09-05-…`, `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` (root).

These are the **record of how the system was built**. They should be retained as historical
evidence (candidate for an `archive/` grouping in a later phase — doc 10), not treated as current
architecture and not deleted.

---

## Why this distinction matters
Rastisi's documentation is unusually **intent-rich**: the ADR record + V2 spec explain the *why*
behind the code. A future canonical Architecture Knowledge System should **cite** these
design-intent docs as rationale while pointing to the Phase 1/2 code-derived docs as the
authoritative *what*. Historical reports should be archived-in-place with a clear "historical"
label, preserving the build narrative without competing with the canonical set.
