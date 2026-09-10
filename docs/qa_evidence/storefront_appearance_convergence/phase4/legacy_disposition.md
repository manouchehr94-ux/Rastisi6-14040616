# Phase 4 legacy disposition ledger

Seeded from the architecture audit's §10/§13 findings. **Re-verified against current code at Task
9 time (commit `34c1fba9`, the Task-8 final checkpoint) — not trusted blindly from earlier tasks'
claims.** No production deletion happens outside Task 9, and never without a pre-deletion safety
backup (`backup/rastisi6-phase4-pre-legacy-retirement-20260910`, pointing at `34c1fba9`).

Full evidence for every row below: `docs/qa_evidence/storefront_appearance_convergence/phase4/task9_legacy_retirement.md`.

| Legacy surface | R4 equivalent today | Disposition | Phase-4 owning task |
|---|---|---|---|
| Undo / Redo / Publish | Yes — already the same shared `r4_mutation_service._run_history_command` / `layout_service.publish` | **KEEP AS FINAL** (already converged) | n/a |
| `storefront_discard` (bare discard HTTP surface) | Yes — `storefront-builder/r4/discard/`, same `layout_service.discard_draft`, stricter (atomic + stale-revision gated) | **RETIRED** — zero live UI callers found, proven R4 replacement, tests migrated | Task 9 |
| Settings save — 5 R4-schema-enabled section types | Yes, functionally equivalent | TEMPORARY ADAPTER, converging | Task 6 |
| Settings save — ~23 non-schema section types | No | **NOT SAFE TO REMOVE YET** — no R4 schema/write-path for these types yet; view remains live-linked from `editor.html` | Task 6, then Task 9 |
| Container/Cell/Row composition (add/settings/layout/move/remove, cell add-section/clear, row layout) | Pre-Task-10 remediation closed the two remaining gaps — `section.move_to_cell` (arbitrary/non-adjacent placement) and `container.update_settings` (gap/mobile_mode/vertical_align/height_mode/background_*) — reusing only existing canonical services | **NOT SAFE TO REMOVE YET** — R4 now has full functional parity here, but the legacy views remain live-linked from `editor.html`, which is still reachable (as the documented compatibility escape hatch for the Step-1B field gaps below) | Task 7, Pre-Task-10 remediation, then a future retirement pass |
| Section toggle/lock | Yes — `section.toggle_active`/`toggle_locked`, proven equivalent | **NOT SAFE TO REMOVE YET** — R4 has parity, but the legacy view remains live-linked from `editor.html`, the only reachable editor; deleting now removes working merchant UI | Task 7, then Task 9 |
| Section collapse (`storefront_section_collapse_toggle`) | No — editor-only UI convenience, no persisted R4 concept by design (not a capability gap) | **NOT SAFE TO REMOVE YET** — still live, functioning UI in the only reachable editor | Task 9 |
| Discard / Restore / History browser (HTTP surface) | Discard: yes (see row above). Restore/history browser: no R4 UI equivalent yet (services already atomic/safe underneath) | **NOT SAFE TO REMOVE YET** (restore/history) — live-linked from `editor.html`/`history.html`/`r3_toolbar.html` | Task 7, then Task 9 |
| Ready Template gallery / apply (curated templates) | No — Task 8 deliberately kept `apply_preset_with_checkpoint` (legacy) and `appearance.template.apply` (R4) as two separate, legitimate, already-tested orchestrations, not a duplicate pair | **CANONICAL KEEP** — not a retirement candidate | Task 8B (closed) |
| Internal/industry-vertical layout presets (`storefront_apply_industry_layout` and equivalents) | No | **NOT SAFE TO REMOVE YET** — no R4 equivalent, a distinct concept from Template-DNA switch; embedded as a plain form inside `editor.html`, so its retirement is coupled to the editor shell's own retirement | Task 9 |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | Yes — all six have proven R4 mutation-type equivalents | **NOT SAFE TO REMOVE YET** — all six legacy routes remain live-linked from `editor.html`/panel templates, the only reachable editor | Task 7, then Task 9 |
| Full Appearance/Header/Footer editor forms (fields beyond R4's allowlist) | Pre-Task-10 remediation closed the great majority of the gap — R4 now covers all 8 `color_overrides` keys, all 8 `theme_overrides` keys, all structural appearance fields (radius/button_radius/density/image_fit/image_hover/card_image_*/content_width/grid_density/card_shadow/card_hover/hero_style), all 6 header toggles + announcement_text + announcement_show_phone, and all 9 footer toggles. Only 3 repeater-shaped fields (`announcement_links`, header `extra_blocks`, footer `extra_blocks`) and the per-field responsive hide-on-tablet/mobile toggles remain R4-unreachable (compound multi-row/per-device UI, deliberately deferred — see `pre_task10_r4_cutover.md`) | **KEEP AS CANONICAL** (narrowed) — the remaining gap is genuinely small now (3 compound fields + responsive toggles, not "the majority of fields"), but the Master Prompt's bar ("only delete when *all* required capabilities have a valid replacement") is still not fully met, so the full legacy form stays reachable (as the documented compatibility escape hatch, no longer the primary nav target) rather than being deleted | Task 9, Pre-Task-10 remediation |
| Section-scoped media CRUD (Hero slides/Banners/Story items via `media_views.py`) | Yes — Task 7 confirmed `media_views.py` is the single shared authority reachable from both legacy `editor.html` and R4's Inspector | **CANONICAL KEEP** | Task 7 |
| Global Hero/Banner admin (`apps/dashboard/views.py` `hero_*`/`banner_*`, the "homepage" dashboard nav entry) | Full field parity confirmed with canonical `media_views.py` (superset, even) | **KEEP — legitimate compatibility mirror**, not a pure duplicate: still the primary/sole content-management path for any store not using the visual storefront layout, with its own full test suite | Task 9 |
| Legacy editor shell (`editor.html`) | Yes — Pre-Task-10 remediation made R4 the live default (`r4_editor_enabled` now defaults `True`; dashboard nav routes to R4) | **NOT SAFE TO REMOVE YET** (reclassified — no longer "sole live path"; now "still needed as the documented compatibility escape hatch" for the Step-1B field/repeater gaps and the still-unclosed items elsewhere in this table) — R4 is now the primary merchant editor, the legacy shell is a clearly-labeled secondary nav entry, not a co-equal editor | Task 3A precondition (met), Pre-Task-10 remediation (cutover done), full retirement left to a future task |
| `announcement_bar` preset-application gate | N/A — bug fix, not a duplicate-authority migration | **FIXED** — `preset_service._build_sections_for_page` now shares the same `hidden_from_library` gate `section_structure_service.add_section`/`duplicate_section` already enforce; `golden_reference_service._rebuild_home_composition` given the same defensive guard | Task 9 |
| `announcement_bar` section (registry entry / renderer) | `hidden_from_library`, superseded by header notification bar | **CANONICAL KEEP** — no live merchant-facing add path remains (Task 9 closed the last one, presets); existing/legacy instances still legitimately render | Task 9 |

**Structural precondition (carried from the audit, true through Task 9, CLOSED by the Pre-Task-10
remediation):** the legacy editor shell was the sole live, reachable merchant path through Task 9
— `r4_editor_enabled` defaulted `False` and no dashboard nav routed to R4. The Pre-Task-10
remediation closed this: `r4_editor_enabled` now defaults `True`, the dashboard nav's primary
storefront-appearance entries route to R4, and R4 gained the field/composition parity documented
in `pre_task10_r4_cutover.md`. **R4 is now the live default merchant editor — one primary editor,
not two co-equal ones.** The legacy editor remains reachable only as a clearly-labeled, secondary
"advanced settings" escape hatch for the narrow remaining field gap (3 repeater-shaped fields +
responsive toggles) documented there. Every legacy view still live-linked from `editor.html` in
this table is therefore **still NOT SAFE TO REMOVE YET** — but now for that narrower, explicitly
tracked reason, not because R4 is unreachable. A second retirement pass (re-evaluating each row
above once the remaining field gap closes) is left to a future task.

**Compatibility mirrors that are NOT retirement candidates** (legitimate shared logic, not
duplication): `appearance_authority_service` writing both the typed manifest and the legacy
`header_config`/`footer_config` JSON keys in one call; `r4_mutation_service`'s
`_LEGACY_SELECTOR_FAMILIES`/`_sync_manifest_from_live_selectors`; `settings_schema.clean_section_schema_patch`'s
Strangler-bridge deferral to legacy `validate_settings`; the global Hero/Banner admin
(`apps/dashboard/views.py`) for stores not on the visual storefront layout.
