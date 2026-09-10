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
| Container/Cell/Row composition (add/settings/layout/move/remove, cell add-section/clear, row layout) | Partial — Task 7 added `container.change_layout`/`cell.add_section`; arbitrary/non-adjacent placement and Container/Cell-level settings editing remain unclosed | **NOT SAFE TO REMOVE YET** — genuine remaining feature gap, and the legacy views are still the sole live path (`editor.html`) | Task 7, then Task 9 |
| Section toggle/lock | Yes — `section.toggle_active`/`toggle_locked`, proven equivalent | **NOT SAFE TO REMOVE YET** — R4 has parity, but the legacy view remains live-linked from `editor.html`, the only reachable editor; deleting now removes working merchant UI | Task 7, then Task 9 |
| Section collapse (`storefront_section_collapse_toggle`) | No — editor-only UI convenience, no persisted R4 concept by design (not a capability gap) | **NOT SAFE TO REMOVE YET** — still live, functioning UI in the only reachable editor | Task 9 |
| Discard / Restore / History browser (HTTP surface) | Discard: yes (see row above). Restore/history browser: no R4 UI equivalent yet (services already atomic/safe underneath) | **NOT SAFE TO REMOVE YET** (restore/history) — live-linked from `editor.html`/`history.html`/`r3_toolbar.html` | Task 7, then Task 9 |
| Ready Template gallery / apply (curated templates) | No — Task 8 deliberately kept `apply_preset_with_checkpoint` (legacy) and `appearance.template.apply` (R4) as two separate, legitimate, already-tested orchestrations, not a duplicate pair | **CANONICAL KEEP** — not a retirement candidate | Task 8B (closed) |
| Internal/industry-vertical layout presets (`storefront_apply_industry_layout` and equivalents) | No | **NOT SAFE TO REMOVE YET** — no R4 equivalent, a distinct concept from Template-DNA switch; embedded as a plain form inside `editor.html`, so its retirement is coupled to the editor shell's own retirement | Task 9 |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | Yes — all six have proven R4 mutation-type equivalents | **NOT SAFE TO REMOVE YET** — all six legacy routes remain live-linked from `editor.html`/panel templates, the only reachable editor | Task 7, then Task 9 |
| Full Appearance/Header/Footer editor forms (fields beyond R4's allowlist) | Partial — R4 covers only `{template_slug, palette_slug, font, type_scale, motion, button_style}` / `header_variant` / `footer_variant`; the majority of legacy fields (8 `color_overrides` keys, 8 `theme_overrides` keys, 6 header toggles + announcement fields + responsive + extra_blocks, 9 footer toggles + responsive + extra_blocks, several structural appearance fields) have no R4 write path | **KEEP AS CANONICAL** — field-by-field parity matrix completed at Task 9 (see `task9_legacy_retirement.md`); this is not "one or two" missing fields, so the Master Prompt's bar for deleting the whole form is not met | Task 9 |
| Section-scoped media CRUD (Hero slides/Banners/Story items via `media_views.py`) | Yes — Task 7 confirmed `media_views.py` is the single shared authority reachable from both legacy `editor.html` and R4's Inspector | **CANONICAL KEEP** | Task 7 |
| Global Hero/Banner admin (`apps/dashboard/views.py` `hero_*`/`banner_*`, the "homepage" dashboard nav entry) | Full field parity confirmed with canonical `media_views.py` (superset, even) | **KEEP — legitimate compatibility mirror**, not a pure duplicate: still the primary/sole content-management path for any store not using the visual storefront layout, with its own full test suite | Task 9 |
| Legacy editor shell (`editor.html`) | Yes (R4 shell exists), but `r4_editor_enabled` still defaults `False` and dashboard nav still routes to the legacy editor, not R4 | **NOT SAFE TO REMOVE YET** — re-verified at Task 9: still the sole live, reachable merchant path | Task 3A precondition (met structurally, not behaviorally), then Task 9 |
| `announcement_bar` preset-application gate | N/A — bug fix, not a duplicate-authority migration | **FIXED** — `preset_service._build_sections_for_page` now shares the same `hidden_from_library` gate `section_structure_service.add_section`/`duplicate_section` already enforce; `golden_reference_service._rebuild_home_composition` given the same defensive guard | Task 9 |
| `announcement_bar` section (registry entry / renderer) | `hidden_from_library`, superseded by header notification bar | **CANONICAL KEEP** — no live merchant-facing add path remains (Task 9 closed the last one, presets); existing/legacy instances still legitimately render | Task 9 |

**Structural precondition (carried from the audit, re-verified true at Task 9):** the legacy editor
shell remains the sole live, reachable merchant path — `r4_editor_enabled` defaults `False` and no
dashboard nav routes to R4. Every legacy view still live-linked from `editor.html` is therefore
**NOT SAFE TO REMOVE YET**, regardless of whether R4 has a proven service-level equivalent for it:
deleting the HTTP surface a merchant is still using today, before R4 is the live default, would
remove real capability rather than dead code. Closing this precondition (making R4 the default
reachable editor with full field/capability parity) is out of Task 9's scope — Task 9 is
deletion/convergence, not new-capability or default-routing work — and is left to a future task.

**Compatibility mirrors that are NOT retirement candidates** (legitimate shared logic, not
duplication): `appearance_authority_service` writing both the typed manifest and the legacy
`header_config`/`footer_config` JSON keys in one call; `r4_mutation_service`'s
`_LEGACY_SELECTOR_FAMILIES`/`_sync_manifest_from_live_selectors`; `settings_schema.clean_section_schema_patch`'s
Strangler-bridge deferral to legacy `validate_settings`; the global Hero/Banner admin
(`apps/dashboard/views.py`) for stores not on the visual storefront layout.
