# Phase 1 — Task 5 Evidence: Make Ready Template Apply Authoritative (A02 closure)

Task 5 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`).

---

## TASK 4 REVIEW

- BASE: `a3838c7affe03258769836bb710e0e9127bf0853`
- HEAD: `dcff5651bc1e1392b5f655517b4aafd2fb0b4971`
- Reviewed diff: `apps/storefront_builder/services/r4_mutation_service.py` (appearance/header/footer delegation + component/manifest persistence routed through the authority wrapper) + tests + docs.

Findings against the 8 required checks:

1. R4 ownership boundaries — `apply_mutation` retains `@transaction.atomic`, `_lock_active_draft`, base-revision/stale rejection, tenant checks, history snapshot/record, `edit_revision += 1`, response. Nothing moved into the authority service. NONE.
2. appearance.update preservation — delegated to `apply_appearance_patch`; `store_appearance`/opaque/unrelated-managed preserved; template/palette/motion precedence (`_TEMPLATE_OWNED_FIELDS`, palette reset) and trailing motion sync unchanged. NONE.
3. Header/Footer delegation — full validated config saved; mirror==manifest; unrelated families survive (verified by throwaway probe: `header.update` preserved a non-default footer + hero); no duplicate map; invalid selector → `InvalidStoreAppearanceContract` → `R4MutationError` before partial persist. NONE.
4. Legacy sibling reconciliation — component-update path (`preserve_live_legacy_siblings=True`) and template/motion sync (`_sync_manifest_from_live_selectors`) UNCHANGED; header/footer paths now do precise per-family updates. In the converged world (legacy views route through the authority since Task 3) live config and manifest stay consistent, so no reconciliation regression. Confirmed by code inspection + probe + all existing green tests. NONE.
5. Bottom Nav — `mobile_nav_variant` from `cleaned["mobile_nav_variant"]` (always present in effective footer config); syncs `bottom_nav` only. NONE.
6. component / whole-manifest — final persistence routed through `apply_store_appearance_manifest`; no-op short-circuits, `preserve_live_legacy_siblings`, schema validation unchanged. NONE.
7. Template Apply isolation — `_apply_appearance_template` was UNCHANGED in Task 4; preset_service not modified; A02 not fixed. NONE.
8. Tests — none weakened/skipped; new R4 preservation tests exercise the public mutation endpoint; 3 expected REDs genuine. NONE.

- CRITICAL: 0
- IMPORTANT: 0
- MINOR: 1 — header/footer paths narrowed from all-sibling `_sync_manifest_from_live_selectors` to precise per-family updates; a correct refinement, documented and probe-verified.
- REVIEW RESULT: **PASS**

---

## TASK 5

- HEAD before: `dcff5651bc1e1392b5f655517b4aafd2fb0b4971`
- Production files changed: `apps/storefront_builder/services/preset_service.py`, `apps/storefront_builder/services/r4_mutation_service.py`
- Test files changed: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`, `apps/storefront_builder/tests/test_a8_ready_template_contracts.py`
- `appearance_authority_service.py` NOT modified (no contract defect surfaced).

### Pre-fix re-verification (Step 1)

`test_phase1_appearance_authority` before Task-5 code changes: `Ran 18 ... FAILED (failures=3)` — the 3 RED were the 2 Ready-Template fidelity tests + the 1 explicit-local test (Task 6). Recorded.

### apply_preset order — BEFORE

```
@transaction.atomic
1) validate appearance/header/footer overlays (palette reset, mobile-nav reset) — no writes
2) prepare page rows + container settings + baseline snapshot pages — no writes
3) WRITE: appearance_config=cleaned_appearance; template_provenance;
         template_baseline_snapshot (from cleaned_* values); header_config; footer_config; save
4) replace page composition (delete containers/sections, bulk_create, rebuild containers)
```
Note: `store_appearance` was NEVER written (A02). The baseline snapshot captured the pre-manifest `cleaned_*` config.

### apply_preset order — AFTER

```
@transaction.atomic
1) validate appearance/header/footer overlays — no writes  (UNCHANGED)
2) prepare page rows + container settings + snapshot pages — no writes  (UNCHANGED)
3) WRITE: appearance_config=cleaned_appearance; template_provenance; header_config; footer_config; save
3b) if preset.store_appearance: appearance_authority_service.apply_store_appearance_manifest(
       version=draft, manifest=preset.store_appearance)   ← A02 CLOSURE, complete declared manifest
3c) if _record_baseline_snapshot: build template_baseline_snapshot from the NOW manifest-synced
       draft.appearance_config / header_config / footer_config (so reset restores full recipe DNA); save
4) replace page composition  (UNCHANGED)
```

- Authority primitive used: `apply_store_appearance_manifest(version=draft, manifest=preset.store_appearance)` (delegates to `persist_store_appearance_manifest`, which validates the complete manifest, writes `appearance_config["store_appearance"]`, and re-derives header/footer/bottom_nav/motion mirrors — one atomic save inside apply_preset's transaction).
- **Complete manifest persistence point:** step 3b, AFTER the ordinary appearance/header/footer writes so its mirrors are the authoritative final selector state and cannot be left stale.
- **Baseline reorder rationale:** the snapshot is now built (step 3c) AFTER the manifest persist so `snapshot["appearance"]` equals the final `appearance_config` (including `store_appearance`). This keeps reset-to-baseline returning to the fully-applied recipe (proven by `test_reset_to_baseline_returns_to_applied_recipe_manifest`) and keeps `_draft_already_matches_preset` (which compares `appearance_config` to `snapshot["appearance"]`) correct.

### R4 partial-template-sync — REMOVED (Step 6)

In `_apply_appearance_template`, the now-redundant post-apply `_sync_manifest_from_live_selectors(draft=draft)` (the "A6 predates A8's complete Ready-Template DNA" partial four-family sync) AND the post-apply `template_baseline_snapshot` re-capture were removed, because `preset_service.apply_preset` is now authoritative (persists the complete manifest and builds the snapshot from the manifest-synced state). `_LEGACY_SELECTOR_FAMILIES` and `_sync_manifest_from_live_selectors` are RETAINED (still used by the non-template `_apply_appearance_update` motion/template path and `preserve_live_legacy_siblings` component reconciliation). R4 still owns exact preset key/version validation, active-Draft locking, base revision, transaction, rollback, history, and revision increment.

### All-50 declaration completeness (Step 12)

`test_a8_ready_template_contracts.AllReadyTemplatesDeclareCompleteManifestTests.test_all_latest_ready_templates_declare_valid_complete_manifest` — enumerates `list_ready_templates()`, validates each `store_appearance` as a complete `StoreAppearanceManifest` (via `validate_store_appearance_manifest`, `require_complete=True`) and asserts its selection keys == the canonical `set(COMPONENT_FAMILIES)`. GREEN. (Declaration-completeness only; not browser certification.)

### Representative recipes (Step 13) — declared = persisted = effective

Exercised (all exist under these exact keys): `dense_marketplace` (v3), `premium_leather` (v3), `dark_digital` (v3), `warm_boutique` (v3), `anniversary_mosaic` (v1). No substitution needed.

`test_representative_recipes_declared_persisted_effective`: for each, a conflicting starting manifest → `apply_preset` → reload → `persisted selections == declared` AND `effective (resolve_store_appearance_render_state) selections == declared`, over the COMPLETE mapping. GREEN.

### Legacy vs R4 apply convergence (Step 8)

`test_legacy_and_r4_entry_paths_converge`: canonical `apply_preset` (store A) and R4 `_apply_appearance_template` (independent store B), both from conflicting starting manifests → both persisted == declared, both effective == declared, and A == B. Appearance fidelity (not object identity). GREEN.

### Conflicting state no-leak (Step 9)

`test_conflicting_starting_state_does_not_leak`: seed conflicting hero/layout/product_view/card/badge → apply `dense_marketplace` → persisted == declared for every family; no prior selection leaks. GREEN.

### Idempotence (Step 10)

`test_apply_same_recipe_twice_is_idempotent`: apply `dark_digital` twice to equivalent state → persisted and effective identical across applies. Deterministic replacement/reset semantics; NO content-preserving Switch claimed. GREEN.

### Atomic rollback (Step 11)

`test_apply_preset_failure_rolls_back_manifest_and_config`: with `container_service.rebuild_page_from_legacy_rows` mocked to raise mid-apply (AFTER the appearance/header/footer + manifest writes, inside apply_preset's `@transaction.atomic`), `apply_preset` raises and the whole transaction rolls back — `appearance_config`, `header_config`, `footer_config`, the typed manifest, and Home composition are all unchanged. Proves the non-transactional authority multi-save is safe inside the caller's transaction (NOT solved by adding a transaction inside the authority service). GREEN.

### Test results

Primary command:

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_a8_ready_template_contracts \
  --verbosity 2
```

Result: `Ran 62 tests ... FAILED (failures=1)`.

- TOTAL: 62
- GREEN: 61
- EXPECTED RED REMAINING: 1 — `LocalVariantPrecedenceTests.test_explicit_local_variant_wins_store_default` (Task 6). Not hidden/skipped/xpassed.
- UNEXPECTED FAILURES: 0
- Both previously-RED Ready-Template fidelity tests are now GREEN (A02 closed via both persistence-level and effective-resolution assertions).

### Preset / reset regression

`test_preset_service` + `test_u7_ready_template_baseline` + `test_phase2c_content_preserving_layout_changes`: `Ran 94 tests ... OK` (GREEN). These directly exercise apply/reset/baseline-snapshot/content-preserving behavior most affected by the change.

Broader preset/gallery set (`test_u8_template_gallery`, `test_u10_ready_template_catalog`, `test_ready_template_real_previews`, `test_g2_1_golden_apply_atomic` also run): one failure — `test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset`. **Pre-existing and unrelated:** it is a read-only gallery-view label assertion (no `apply_preset` call) checking the Persian header-variant label `"بازارگاهی (جستجو-محور)"`; the current registry declares the header variant as `marketplace_search` (label drift), independent of appearance-authority wiring. Verified by reproducing the identical failure at the pre-Task-5 baseline `dcff565` in a throwaway detached worktree.

### R4 / persistence regression

`test_r4_store_appearance_contracts` + `registry` + `validation` + `compatibility` + `persistence` + `test_r4_mutation_api`: `Ran 76 tests ... OK` (GREEN).

### Django check / migration check

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

### Explicit statements

- NO content-preserving Switch implemented (Apply remains deterministic replacement/reset).
- NO renderer precedence change (`render_service.py` unchanged).
- NO local variant marker implementation (explicit-local test remains the single Task-6 RED).
- NO new variants.
- NO business-domain changes.
- NO migrations.
- `appearance_authority_service.py` unchanged; `views.py`/`settings_schema.py`/models/templates/CSS/JS unchanged.
- `git diff --check` clean; only the four allowed files changed.
