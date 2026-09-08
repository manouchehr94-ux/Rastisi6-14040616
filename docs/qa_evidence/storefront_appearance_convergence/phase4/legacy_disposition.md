# Phase 4 legacy disposition ledger

Seeded from the architecture audit's §10/§13 findings (re-verify at Task 9 time, not trusted
blindly). Updated as each surface's replacement is proven and it is retired, kept as a thin
adapter, or ruled a genuine feature gap that is not yet a retirement candidate. No production
deletion happens outside Task 9, and never without a pre-deletion safety backup
(`backup/rastisi6-phase4-pre-legacy-retirement-20260908`).

| Legacy surface | R4 equivalent today | Disposition | Phase-4 owning task |
|---|---|---|---|
| Undo / Redo / Publish | Yes — already the same shared `r4_mutation_service._run_history_command` / `layout_service.publish` | **KEEP AS FINAL** (already converged) | n/a |
| Settings save — 5 R4-schema-enabled section types | Yes, functionally equivalent | TEMPORARY ADAPTER, converging | Task 6 |
| Settings save — ~23 non-schema section types | No | MIGRATE THEN RETIRE — needs schema/write-path work first | Task 6, then Task 9 |
| Container/Cell/Row composition (add/settings/layout/move/remove, cell add-section/clear, row layout) | No — R4 has no equivalent model | NOT A RETIREMENT CANDIDATE YET — genuine feature gap, needs real parity work | Task 7 |
| Section toggle/collapse/lock | No | MIGRATE THEN RETIRE | Task 7, then Task 9 |
| Discard / Restore / History browser (HTTP surface) | No (services already atomic/safe underneath) | MIGRATE THEN RETIRE | Task 7, then Task 9 |
| Ready Template gallery / apply (curated templates) | Partial — R4 covers the same catalog but with a weaker orchestration (no checkpoint/confirmation gate) | TEMPORARY ADAPTER → ONE ORCHESTRATION | Task 8B |
| Internal/industry-vertical layout presets (`storefront_apply_industry_layout` and equivalents) | No | LEGACY CANDIDATE (Ruling K) — retire/fold/document per current-code caller evidence, no production-traffic requirement | Task 9 |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | No (services already atomic/checkpointed) | MIGRATE THEN RETIRE | Task 7, then Task 9 |
| Full Appearance/Header/Footer editor forms (fields beyond R4's allowlist) | Partial | NEEDS FIELD-BY-FIELD PARITY MATRIX before disposition | Task 9 |
| Section-scoped media CRUD (Hero slides/Banners/Story items) | No | NOT A RETIREMENT CANDIDATE YET — genuine feature gap | Task 7 |
| Legacy editor shell (`editor.html`) | Yes (R4 shell exists), but `r4_editor_enabled` defaults `False` and no dashboard nav links to it | KEEP AS FINAL UNTIL R4 IS REACHABLE — retirement cannot be evidenced before Task 3A | Task 3A precondition, then Task 9 |
| `announcement_bar` section | `hidden_from_library`, superseded by header notification bar | RETIREMENT CANDIDATE — needs caller/route/template/test inventory | Task 9 |

**Structural precondition (carried from the audit):** every "NEEDS EVIDENCE" row above cannot be
honestly evidenced until R4 has a real dashboard entry point (Task 3A) — usage evidence gathered
while R4 is unreachable by construction would be meaningless. Task 9 does not start until Tasks
1–8 PASS.

**Compatibility mirrors that are NOT retirement candidates** (legitimate shared logic, not
duplication): `appearance_authority_service` writing both the typed manifest and the legacy
`header_config`/`footer_config` JSON keys in one call; `r4_mutation_service`'s
`_LEGACY_SELECTOR_FAMILIES`/`_sync_manifest_from_live_selectors`; `settings_schema.clean_section_schema_patch`'s
Strangler-bridge deferral to legacy `validate_settings`.
