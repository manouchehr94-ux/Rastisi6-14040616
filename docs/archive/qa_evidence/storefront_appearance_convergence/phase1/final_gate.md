# Phase 1 — Architecture & Authority Final Gate

## Result

**PASS**

## Baseline

- Approved G2.3 code baseline ancestor: `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` (verified ancestor of HEAD, exit 0)
- Docs handoff branch: `origin/docs/storefront-appearance-convergence`
- Phase-1 starting commit: `b5a15272a2488e4cb0d7dbed9a0d5b1697a8da33` (verified ancestor of HEAD, exit 0)
- Final HEAD (pre-gate commit): `3eeac5b6118ad70a130e0d25f8b25d883cc672bb`
- Branch: `feature/storefront-appearance-convergence-phase1`
- Interpreter / framework: Python 3.12.13, Django 5.2.17

## Cumulative Architecture Review

A fresh independent behavioral review of the whole Phase-1 production diff
(`git diff b5a1527..HEAD -- apps/storefront_builder`, 6 production files) was
performed (semantic reviewer + Kiro cumulative review).

- CRITICAL: 0
- IMPORTANT: 0
- MINOR: 2 (dead-but-tested `apply_ready_template_appearance` primitive + stale module/primitive docstrings)
- Conclusion: **APPROVED.** Write ownership genuinely converges; layer boundaries hold; A02 closed; precedence consistent; internal marker safe. No active competing Appearance authority remains for the Phase-1 scoped concepts.

Independent-review conclusions on the 6 architecture questions:

1. **One canonical authority** — NONE (no active competing path). Legacy views (`views.py`), R4 mutations (`r4_mutation_service.py`), and preset apply (`preset_service.py`) all route state transformation through `appearance_authority_service` (`apply_appearance_patch` / `apply_header_variant` / `apply_footer_variant` / `apply_store_appearance_manifest`). The only direct `persist_store_appearance_manifest` calls live inside the authority module; the remaining `_sync_manifest_from_live_selectors` call is the motion/template compatibility mirror on the ordinary appearance-update path, not a competing authority.
2. **Layer ownership** — NONE. Authority service owns only state transformation + one delegated save; `apply_mutation` retains `@transaction.atomic`/lock/base-revision/stale-rejection/tenant/history/revision increment/response; `preset_service` owns apply orchestration/composition/baseline/apply transaction; `render_service` owns effective resolution; `settings_schema` owns validated merge + trusted marker stamping; views own HTTP/forms/auth/messages/redirects. No crossover.
3. **Ready Template A02** — NONE. `apply_preset` persists the COMPLETE `preset.store_appearance` after the ordinary appearance/header/footer writes, builds the baseline snapshot from the manifest-synced state, all inside one `@transaction.atomic`; R4's partial four-family sync + post-apply re-capture removed.
4. **Precedence / historical safety** — NONE. `render_service._build_items_from_sections` derives one `effective_appearance_variant` gate applied consistently to BOTH the `effective_settings` overlay and `active_variant`; explicit-local wins, unmarked preserves inherited/global overlay (no flip).
5. **Internal marker** — NONE. `appearance_overrides.variant_explicit` is server-derived, stamped after validation, outside the client-writable contract (rejected by `validate_appearance_overrides`), preserved through persistence, not a public control; no bulk migration.
6. **Multi-save sequences** — NONE. All multi-save sequences run inside a caller-owned `@transaction.atomic`; partial writes roll back. (Informational, not a regression: the two legacy header/footer view paths rely on request-level atomicity, as they did pre-Phase-1.)

## Canonical Ownership

Final converged write architecture (Phase-1 scoped concepts):

```
Legacy merchant routes (views.py)  ─┐
R4 mutations (r4_mutation_service)  ─┼─> appearance_authority_service ─> persist_store_appearance_manifest (single validated save + mirrors)
Ready Template Apply (preset_service)┘        apply_appearance_patch / apply_header_variant / apply_footer_variant / apply_store_appearance_manifest
```

- Ordinary appearance patches → `apply_appearance_patch` (preserves `store_appearance` + opaque keys).
- Header/Footer/Nav selection → `apply_header_variant` / `apply_footer_variant` (mirror == typed manifest).
- Complete typed manifests → `apply_store_appearance_manifest`.
- Ready Template Apply → persists complete `preset.store_appearance`.
- Compatibility mirrors (`header_variant`/`footer_variant`/`mobile_nav_variant`/`motion`) remain re-derived projections, not co-equal authorities.

## Recipe Fidelity

Ready Template Apply proven: **Declared manifest selections = Persisted manifest selections = Effective resolved selections**, over the complete canonical family mapping, for representative recipes `dense_marketplace` (v3), `premium_leather` (v3), `dark_digital` (v3), `warm_boutique` (v3), `anniversary_mosaic` (v1). Conflicting starting state cannot leak; apply is idempotent; canonical and R4 entry paths converge; reset/baseline restores the complete applied recipe DNA; all latest Ready Templates declare complete manifests. See `recipe_fidelity.md`.

## Variant Precedence

Approved normal precedence realized for section variants: Store family selection = inherited/default; an EXPLICIT local Section variant (`appearance_overrides.variant_explicit=True`, server-stamped on a genuine merchant variant edit) is the stronger normal override and wins. Historical unmarked sections preserve their prior effective output (inherited Store/global variant still wins) — no bulk migration, no hidden visual flip. Both renderer decision points (settings overlay + `active_variant`) honor the marker consistently. No Page Override, no force-all Store policy.

## Lifecycle Safety Preserved

Only claims proven within Phase 1 (Phase-2 lifecycle convergence is NOT claimed):

- R4 revision / stale-write rejection: PASS (`test_stale_revision_...`, `test_stale_base_revision_is_rejected_and_nothing_changes`)
- Tenant isolation: PASS (`test_foreign_draft_id_...`, `test_foreign_store_section_id_...`)
- Atomic rollback: PASS (`test_invalid_manifest_is_fully_rolled_back`, `test_apply_preset_failure_rolls_back_manifest_and_config`)
- History / revision monotonicity: PASS (`test_...one_revision_and_history_entry`, `test_valid_noop_does_not_increment_revision_or_history`, `test_undo_redo_restores_template_metadata_and_slot_identity`)

## Core Test Matrix

Command:

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  apps.storefront_builder.tests.test_r4_store_appearance_contracts \
  apps.storefront_builder.tests.test_r4_store_appearance_registry \
  apps.storefront_builder.tests.test_r4_store_appearance_validation \
  apps.storefront_builder.tests.test_r4_store_appearance_compatibility \
  apps.storefront_builder.tests.test_r4_store_appearance_persistence \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_r4_settings_schema \
  apps.storefront_builder.tests.test_u4_component_variants \
  apps.storefront_builder.tests.test_a8_ready_template_contracts \
  apps.storefront_builder.tests.test_preset_service \
  apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_section_registry \
  apps.storefront_builder.tests.test_g23_builder_public_content_appearance \
  --verbosity 1
```

- TOTAL: 551
- PASS: 551
- FAIL: 0
- ERROR: 0

## Legacy View Baseline Exceptions

`test_views` → `Ran 213 tests ... FAILED (failures=1, errors=1)`.

- `test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` (FAIL)
- `test_views.FullscreenEditorTests.test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` (ERROR)

These assert V3 editor template/topbar markup (`sfb-v3-device-switcher`, `@click="fullscreen = !fullscreen"`, etc.) — unrelated to Phase-1 Python state transformation (no template changed in Phase 1). Reproduced FRESH on pre-Task-3 commit `28e48555b9225fd0dc01f418f6e6fde4e4170e01` in a temporary detached worktree: identical `FAILED (failures=1, errors=1)`, same two tests. **PRE-EXISTING / OUTSIDE PHASE-1 BLOCKING SCOPE.** No additional `test_views` failures.

## Gallery Baseline Exception

`test_u8_template_gallery` → `Ran 11 tests ... FAILED (failures=1)`.

- `test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset` (FAIL)

Read-only gallery-view label assertion (does not call `apply_preset`); asserts a Persian header-variant label that drifted vs the current registry (`marketplace_search`). Reproduced FRESH on pre-Task-5 commit `dcff5651bc1e1392b5f655517b4aafd2fb0b4971` in a temporary detached worktree: identical signature, same single test, no additional gallery failures. **PRE-EXISTING / OUTSIDE PHASE-1 BLOCKING SCOPE.**

## Django Integrity

`python manage.py check` → `System check identified no issues (0 silenced).`

## Migration Integrity

`python manage.py makemigrations --check --dry-run` → `No changes detected`.

## Scope Audit

`git diff --check b5a1527..HEAD` → clean. Cumulative production change is confined to `apps/storefront_builder/`:
`services/appearance_authority_service.py` (new), `services/preset_service.py`, `services/r4_mutation_service.py`, `services/render_service.py`, `settings_schema.py`, `views.py` (+ 3 test files, + Phase-1 docs).

Phase 1 did NOT introduce: new renderer, business-domain rewrite, models/migrations, new visual variants, Template 51+, Page Override, Store force-all policy, content-preserving Template Switch, Phase-2 media-lifetime redesign, Brand/Collection vertical-slice migration, non-Home R4 expansion, or legacy route deletion (all verified by `git diff --name-only`).

## Known Non-Blocking Follow-ups

- **Dead-but-tested `apply_ready_template_appearance` primitive** — no production caller (preset apply uses `apply_store_appearance_manifest` directly, correctly). Narrow/remove or wire it in a later bounded cleanup. Not an active competing authority; not a correctness risk. MINOR.
- **Stale module/primitive docstrings** in `appearance_authority_service` still describe delegation as future "Task 5" work. Refresh in a later cleanup. MINOR.
- **Redundant Header/Footer double save** — legacy Header/Footer routes save the full config then persist the manifest (second save re-derives the mirror). Correctness/history/transaction semantics are safe; performance/cleanup note only. MINOR.
- **No explicit "clear local variant → inherit Store default" merchant operation** exists (baseline-reset is a different concept). Bounded product/UI follow-up; deliberately NOT invented in Phase 1.
- **Pre-existing FullscreenEditor test drift** (2 `test_views` tests) — unrelated template assertions; reproduced at `28e4855`.
- **Pre-existing gallery label drift** (1 `test_u8_template_gallery` test) — read-only label assertion; reproduced at `dcff565`.

## Explicit Non-Goals

- Phase 2 not started.
- No media-lifetime redesign.
- No Brand/Collection vertical slice.
- No legacy retirement / route deletion.
- No new variants / Template 51+.
- No browser/mobile 50-template certification (this gate proves Store Appearance DNA fidelity only).
- No content-preserving Template Switch.
- No Page Override / force-all Store policy.

## Completion Checklist

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Legacy Appearance preserves typed manifest and opaque canonical keys | PASS | `test_legacy_appearance_edit_preserves_typed_manifest`, `..._preserves_effective_hero_selection` |
| 2 | Legacy Header/Footer synchronize typed selections | PASS | `test_legacy_header_edit_updates_effective_manifest_selection`, `..._footer_...` |
| 3 | Legacy + R4 share the canonical Appearance transformation layer | PASS | cumulative review Q1; `AppearanceAuthorityServiceTests`, `R4AppearanceAuthorityPreservationTests` |
| 4 | Ready Template Apply persists complete declared manifest | PASS | `test_ready_template_apply_replaces_all_declared_manifest_selections`, `..._persists_declared_manifest_key`, `test_representative_recipes_declared_persisted_effective` |
| 5 | R4 no longer performs Template-Apply-specific partial four-family sync | PASS | cumulative review Q3 (r4 `_apply_appearance_template` sync removed); `test_legacy_and_r4_entry_paths_converge` |
| 6 | Conflicting old manifest values cannot leak through Ready Apply | PASS | `test_conflicting_starting_state_does_not_leak` |
| 7 | Explicit local Section variant intent is represented separately | PASS | `ExplicitLocalVariantMarkerTests.test_r4_variant_patch_marks_local_override_explicit`, `test_legacy_genuine_variant_change_marks_explicit` |
| 8 | Historical unmarked sections preserve old effective output | PASS | `test_historical_unmarked_variant_keeps_legacy_inherited_behavior`, `test_legacy_content_only_edit_does_not_mark` |
| 9 | Explicit local variant beats inherited Store default | PASS | `test_explicit_local_variant_wins_store_default`, `test_marker_set_via_r4_makes_local_variant_win_at_render` |
| 10 | R4 stale-write behavior remains intact | PASS | `test_stale_revision_rejects_appearance_mutation_without_write`, `test_stale_base_revision_is_rejected_and_nothing_changes` |
| 11 | Tenant isolation remains intact | PASS | `test_foreign_draft_id_is_rejected_without_cross_store_access`, `test_foreign_store_section_id_...` |
| 12 | Atomic rollback remains intact | PASS | `test_invalid_manifest_is_fully_rolled_back`, `test_apply_preset_failure_rolls_back_manifest_and_config` |
| 13 | History/revision behavior remains intact | PASS | `test_...one_revision_and_history_entry`, `test_valid_noop_does_not_increment_revision_or_history`, `test_undo_redo_restores_template_metadata_and_slot_identity` |
| 14 | Reset/baseline restores authoritative Ready DNA | PASS | `test_reset_to_baseline_returns_to_applied_recipe_manifest`, `test_template_baseline_snapshot_matches_final_typed_appearance` |
| 15 | No DB migration | PASS | `makemigrations --check --dry-run` → No changes detected |
| 16 | No new renderer | PASS | scope audit (no new renderer file; `render_service` hardened only) |
| 17 | No business-domain rewrite | PASS | scope audit (no `apps/catalog|cart|orders|stores|checkout` change) |
| 18 | No visual variant expansion | PASS | scope audit (no registry variant additions; no Template 51+) |

## Final Decision

**PHASE 1 PASS**

All fresh verification complete: cumulative review 0 CRITICAL / 0 IMPORTANT; core matrix 551/551 GREEN; recipe fidelity fully GREEN (0 expected RED); only verified pre-existing UI/gallery exceptions remain; Django check clean; migrations clean; all 18 completion criteria PASS. Phase 2 is NOT started.
