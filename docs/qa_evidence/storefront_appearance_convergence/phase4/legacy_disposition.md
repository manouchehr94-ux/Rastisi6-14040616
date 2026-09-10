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
| Settings save — 5 R4-schema-enabled section types | Yes, functionally equivalent | **THIN NON-AUTHORITATIVE ADAPTER** (superseded — see next row) | Task 6 |
| Settings save — non-schema section types | **RE-VERIFIED this session, not trusted from the stale "~23" count**: `section_registry.list_definitions()` shows 21 of 36 families now schema-enabled; every one of the 15 remaining schema-less families is legitimately schema-less by design — CONTEXT-AWARE-DOMAIN-OWNED (`cart_items`/`cart_summary`/`product_main`/`product_description`/`product_video`/`related_products`/`collection_header`/`collection_products`/`product_listing`, no merchant-editable fields at all), HOME-ONLY (`catalog_product_wall`/`fashion_lifestyle_hero`), MARKETING-ALIAS (`featured_products`), explicit FIXED/STATIC (`single_banner`), media-only (`story_rail`), or LEGACY-RETIRE (`announcement_bar`) — see `family_certification_matrix.md`, all CERTIFIED. **Zero genuine remaining "no R4 write-path" gaps.** | **THIN NON-AUTHORITATIVE ADAPTER** — R4 is now the sole write authority for every family with real merchant-facing settings; the legacy Settings-save form is redundant, functioning UI still reachable from `editor.html` only because that shell itself must stay live for the two genuinely unreplaced capabilities below (restore/history, industry-layout-presets) | Task 6, Pre-Task-10 final remediation (Gap 1/Gap 2) |
| Container/Cell/Row composition (add/settings/layout/move/remove, cell add-section/clear, row layout) | Pre-Task-10 remediation closed the two remaining gaps — `section.move_to_cell` (arbitrary/non-adjacent placement) and `container.update_settings` (gap/mobile_mode/vertical_align/height_mode/background_*) — reusing only existing canonical services | **THIN NON-AUTHORITATIVE ADAPTER** — R4 has full functional parity and is the primary path; the legacy views are redundant, still-reachable only as part of the same `editor.html` shell kept live for restore/history + industry-layout-presets | Task 7, Pre-Task-10 remediation |
| Section toggle/lock | Yes — `section.toggle_active`/`toggle_locked`, proven equivalent | **THIN NON-AUTHORITATIVE ADAPTER** — R4 has full parity; redundant legacy UI, reachable only as part of the same `editor.html` shell | Task 7 |
| Section collapse (`storefront_section_collapse_toggle`) | No — editor-only UI convenience, no persisted R4 concept by design (not a capability gap) | **CANONICAL KEEP** — a local editor-session UI convenience with no persisted state either way, not a merchant-facing capability gap; legitimate to keep in whichever editor shell is open | Task 9 |
| Discard / Restore / History browser (HTTP surface) | Discard: yes (see row above, already RETIRED at the legacy `storefront_discard` level). Restore/history browser: **no R4 UI equivalent — re-verified this session** (`r4_views.py` has no view calling `layout_service.restore_version`; R4's own "history" is only session-scoped Undo/Redo via `apply_history_command`, a different capability from browsing/restoring an OLD PUBLISHED version) | **CANONICAL KEEP** (restore/history browser only — Discard itself already RETIRED) — a genuinely still-required merchant capability (recovering an old published layout) with no R4 replacement; this is the exact "remaining capability" reason the legacy editor shell cannot be deleted outright | Task 7, Pre-Task-10 final remediation (re-verified, not closed) |
| Ready Template gallery / apply (curated templates) | No — Task 8 deliberately kept `apply_preset_with_checkpoint` (legacy) and `appearance.template.apply` (R4) as two separate, legitimate, already-tested orchestrations, not a duplicate pair | **CANONICAL KEEP** — not a retirement candidate | Task 8B (closed) |
| Internal/industry-vertical layout presets (`storefront_apply_industry_layout` and equivalents) | No — **re-verified this session**: still only reachable from the legacy shell's own `templates/dashboard/storefront_builder/editor.html` (distinct file from R4's `r4/editor.html`), no R4 mutation type for it | **CANONICAL KEEP** — a genuinely still-required, distinct-from-Template-DNA-switch capability with no R4 equivalent; the second (and only other) reason the legacy editor shell cannot be deleted outright | Task 9, re-verified Pre-Task-10 final remediation |
| Granular reset family (section/field/page/header/footer/storefront-to-baseline) | Yes — all six have proven R4 mutation-type equivalents | **THIN NON-AUTHORITATIVE ADAPTER** — R4 has full parity; redundant legacy routes, reachable only as part of the same `editor.html` shell | Task 7 |
| Full Appearance/Header/Footer editor forms (fields beyond R4's allowlist) | **Pre-Task-10 final remediation (Gap 1) CLOSED the remaining gap in full**: R4 now covers all 8 `color_overrides` keys, all 8 `theme_overrides` keys, every structural appearance field, all 6 header toggles + announcement_text/announcement_show_phone, all 9 footer toggles, AND (this session) `announcement_links`, header `extra_blocks`, footer `extra_blocks`, and every per-component responsive hide-on-tablet/hide-on-mobile toggle for both Header and Footer — reusing the existing canonical validators/persistence authority unchanged. **Zero remaining Header/Footer/Appearance fields are R4-unreachable.** | **THIN NON-AUTHORITATIVE ADAPTER** (reclassified from "KEEP AS CANONICAL" now that the field gap is fully closed, not narrowed) — the legacy Appearance/Header/Footer form (`storefront_appearance_editor`) is now fully redundant with R4's Global Design panel; it is not independently URL-reachable outside the `editor.html` shell (embedded via `appearance_panel.html`), so it stays live as part of that shell (kept for the two CANONICAL-KEEP capabilities above), not because it itself is still needed | Task 9, Pre-Task-10 remediation, Pre-Task-10 final remediation (Gap 1 — CLOSED) |
| Section-scoped media CRUD (Hero slides/Banners/Story items via `media_views.py`) | Yes — Task 7 confirmed `media_views.py` is the single shared authority reachable from both legacy `editor.html` and R4's Inspector | **CANONICAL KEEP** | Task 7 |
| Global Hero/Banner admin (`apps/dashboard/views.py` `hero_*`/`banner_*`, the "homepage" dashboard nav entry) | Full field parity confirmed with canonical `media_views.py` (superset, even) | **KEEP — legitimate compatibility mirror**, not a pure duplicate: still the primary/sole content-management path for any store not using the visual storefront layout, with its own full test suite | Task 9 |
| Legacy editor shell (`editor.html`) | Yes for every field/composition/settings capability — Pre-Task-10 remediation made R4 the live default (`r4_editor_enabled` now defaults `True`; dashboard nav routes to R4) and Pre-Task-10 final remediation (Gap 1/Gap 2) closed the last remaining field/browser-certification gaps. No for exactly two capabilities: restore/history browser, industry-vertical layout presets (both re-verified above, both genuinely still legacy-only) | **THIN NON-AUTHORITATIVE ADAPTER** (final reclassification — not RETIRED, not CANONICAL KEEP as a co-equal editor) — R4 is the ONE primary merchant editor and sole write authority for composition/settings/appearance/header/footer; the legacy shell stays reachable, secondary-nav-only, solely as the compatibility path for the two CANONICAL-KEEP capabilities it hosts (restore/history, industry-layout-presets) — every OTHER capability it also happens to expose (settings save, composition, toggle/lock, reset family, appearance/header/footer forms) is redundant dead-weight UI, not a second write authority a merchant needs to reach it for | Task 3A precondition (met), Pre-Task-10 remediation (cutover done), Pre-Task-10 final remediation (final reclassification; physical removal of the now-redundant panels left to a future task — see note below) |
| `announcement_bar` preset-application gate | N/A — bug fix, not a duplicate-authority migration | **FIXED** — `preset_service._build_sections_for_page` now shares the same `hidden_from_library` gate `section_structure_service.add_section`/`duplicate_section` already enforce; `golden_reference_service._rebuild_home_composition` given the same defensive guard | Task 9 |
| `announcement_bar` section (registry entry / renderer) | `hidden_from_library`, superseded by header notification bar | **CANONICAL KEEP** — no live merchant-facing add path remains (Task 9 closed the last one, presets); existing/legacy instances still legitimately render | Task 9 |

**Structural precondition (carried from the audit, true through Task 9, CLOSED by the Pre-Task-10
remediation):** the legacy editor shell was the sole live, reachable merchant path through Task 9
— `r4_editor_enabled` defaulted `False` and no dashboard nav routed to R4. The Pre-Task-10
remediation closed this: `r4_editor_enabled` now defaults `True`, the dashboard nav's primary
storefront-appearance entries route to R4, and R4 gained the field/composition parity documented
in `pre_task10_r4_cutover.md`. **R4 is now the live default merchant editor — one primary editor,
not two co-equal ones.**

**Second retirement pass (Pre-Task-10 FINAL remediation, Gap 3 — this session):** the narrow field
gap the first pass deferred (`announcement_links`, header/footer `extra_blocks`, responsive
hide-on-tablet/mobile toggles) is now closed (Gap 1), and the browser-certification gap for the 15
remaining MIGRATE families is now closed (Gap 2) — so this pass re-verified every row above against
current code rather than trusting either earlier pass's claims. Result: every ONE capability R4
already had proven parity for (settings save, composition, toggle/lock, granular reset,
Appearance/Header/Footer fields) is reclassified from "NOT SAFE TO REMOVE YET" to **THIN
NON-AUTHORITATIVE ADAPTER** — R4 is their sole write authority now; the legacy views are redundant,
not a second editor a merchant needs. Exactly TWO capabilities remain genuinely legacy-only with no
R4 equivalent (restore/history browser; industry-vertical layout presets) — both re-verified live in
current code, both **CANONICAL KEEP**. Because both live inside the same `editor.html` shell as the
now-redundant panels, the shell itself cannot be physically deleted this pass; it is reclassified to
**THIN NON-AUTHORITATIVE ADAPTER** as a whole (see its own row above) rather than RETIRED or
CANONICAL KEEP as a co-equal editor. Physically removing the now-redundant panels from inside
`editor.html` (composition/settings/toggle-lock/reset/appearance-header-footer UI), while keeping
only the two still-needed panels, is real template-surgery work on a legacy shell this pass did not
open — correctly scoped to a future task rather than attempted here under time pressure with
insufficient regression coverage for a shell that still serves two live, required merchant paths.
No row in this table is UNKNOWN.

**Compatibility mirrors that are NOT retirement candidates** (legitimate shared logic, not
duplication): `appearance_authority_service` writing both the typed manifest and the legacy
`header_config`/`footer_config` JSON keys in one call; `r4_mutation_service`'s
`_LEGACY_SELECTOR_FAMILIES`/`_sync_manifest_from_live_selectors`; `settings_schema.clean_section_schema_patch`'s
Strangler-bridge deferral to legacy `validate_settings`; the global Hero/Banner admin
(`apps/dashboard/views.py`) for stores not on the visual storefront layout.
