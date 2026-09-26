# 07 — Unverifiable Claims

`UNVERIFIABLE` = a documented claim that cannot be confirmed or refuted against the frozen code
snapshot alone — because it concerns process/history, environment/tooling, or another document
rather than a runtime code fact.

Claim IDs refer to `01_CLAIM_RECONCILIATION_MATRIX.csv`.

---

## U-1 — CL-30 — Foundational PR numbering (doc-vs-doc)
```
CLAIM: 00_PROJECT_MASTER_REFERENCE.md refers to foundational multi-tenant PRs as #19/#20/#21;
       SAAS_MIGRATION_PLAN.md numbers the same foundation work PR 1-14.
WHY UNVERIFIABLE: This is a process/history statement about PR sequencing, not a runtime code
  fact. The frozen snapshot cannot confirm which external PR number introduced which change (the
  branch's own commit history is doc-referenced, not part of the audited code semantics).
DISPOSITION: Record as an internal doc-vs-doc inconsistency to reconcile in a future canonical
  rewrite. Not a code defect.
```

## Other unverifiable-from-code categories (document-level)

### Process / history claims
- Statements in HISTORICAL reports about *when* something was done, *which* PR/branch delivered it,
  or *who* reviewed it (e.g. project-status branch/HEAD references, prelaunch phase sequencing).
  These are history, not runtime facts. (The 2026-09-20 status doc's branch/HEAD is HISTORICAL,
  doc 05 H-1, and deliberately not read as code.)

### Environment / tooling claims (`CLAUDE.md`)
- "The canonical Git remote is `rastisi5`." — an environment fact, not verifiable from the frozen
  source tree.
- "Use the `rastisi-code-map` skill / prefer Graphify when `graphify-out/graph.json` exists." —
  tooling guidance; `.claude/skills/rastisi-code-map` exists in the tree, but whether the skill/
  Graphify is *operational* is an environment property, not a code fact.
DISPOSITION: Treat `CLAUDE.md` as SUPPORTING agent-operating guidance; its claims are outside the
  code-reconciliation scope.

### Aspirational / QA-target claims
- QA_EVIDENCE and reference-kit docs assert "target" designs / expected visual outcomes. Whether a
  rendered storefront matches a reference kit is a runtime/visual-QA question, not statically
  verifiable from the frozen source. These stay EVIDENCE_ONLY.

### External-dependency claims
- Third-party notices (`docs/third_party/*`) assert licensing/attribution facts about external
  datasets (palettes, plugin, skill). Verifiable only against the external sources, not the code.

---

## Principle
Unverifiable ≠ false. These claims are simply outside what a static reconciliation against a frozen
code snapshot can adjudicate. They are recorded so a future phase (or a human with process/
environment context) can resolve them, and so they are never silently treated as either confirmed
or refuted.
