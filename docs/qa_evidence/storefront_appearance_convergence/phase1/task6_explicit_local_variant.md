# Phase 1 — Task 6 Evidence: Explicit Local Variant Precedence (no historical output flip)

Task 6 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`).

---

## TASK 5 REVIEW

- BASE: `dcff5651bc1e1392b5f655517b4aafd2fb0b4971`
- HEAD: `0492ef90c6fe8aa8e44e33a3c8023c25be29b4ee`
- Reviewed diff: `preset_service.py` (complete manifest persist + baseline snapshot reorder), `r4_mutation_service.py` (redundant template-apply sync removed), tests, docs.

Findings against the 11 checks:

1. A02 closure — declared==persisted==effective proven per representative recipe over the complete family mapping; no leak from conflicting state. NONE.
2. Apply order & baseline snapshot — order is appearance/provenance/header/footer → complete manifest persist → snapshot from manifest-synced config → composition replacement; snapshot includes `store_appearance`; reset restores complete manifest; `_draft_already_matches_preset` correct; idempotence intact. NONE.
3. Transaction ownership — all writes inside `apply_preset`'s `@transaction.atomic`; rollback proven; nothing moved into the authority service. NONE.
4. Plan deviation (`apply_store_appearance_manifest` direct vs `apply_ready_template_appearance`) — see explicit conclusion below. MINOR (design debt).
5. R4 partial sync removal — only the template-apply-specific `_sync_manifest_from_live_selectors` + snapshot re-capture removed; `_LEGACY_SELECTOR_FAMILIES`, `_sync_manifest_from_live_selectors` (non-template motion/template path), and `preserve_live_legacy_siblings` (component reconciliation) retained. R4 still owns key/version validation, lock, base revision, stale rejection, rollback, history, revision increment. NONE.
6. Non-Ready presets — 5 non-Ready presets (`clean_minimal`, `editorial_story`, `dense_catalog`, `premium_boutique`, `v5_golden_homepage`) have no `store_appearance`; the `if preset.store_appearance:` guard skips manifest persistence for them (prior behavior preserved, no partial-manifest expectation). All Ready templates have a complete manifest. NONE.
7. 50-template test quality — `AllReadyTemplatesDeclareCompleteManifestTests` uses `set(COMPONENT_FAMILIES)` (canonical set, not a hardcoded list) and validates via `validate_store_appearance_manifest`; declaration-completeness only (no browser claim). NONE.
8. Representative DB fidelity — the 5 recipe tests seed conflicting state and compare complete declared/persisted/effective mappings. NONE.
9. Legacy vs R4 equivalence — compares selection semantics only (persisted + effective manifests), not object identity/composition IDs. NONE.
10. Rollback proof — exception injected via mocking `container_service.rebuild_page_from_legacy_rows`, which runs AFTER the appearance/manifest writes; proves transaction rollback. NONE.
11. Pre-existing gallery failure — `test_u8_template_gallery.test_header_footer_variant_labels_shown_for_updated_preset` is a read-only GET assertion (no `apply_preset`); reproduced identically at `dcff565`; the Task-5 diff cannot affect the label. Confirmed pre-existing.

- CRITICAL: 0
- IMPORTANT: 0
- MINOR: 2
  - `apply_ready_template_appearance` is now a dead-but-tested primitive (no production caller). Design debt; record for the Phase-1 final gate.
  - Pre-existing unrelated `test_u8_template_gallery` label-drift failure; record for the final gate.
- REVIEW RESULT: **PASS**

### APPLY_READY_TEMPLATE_PRIMITIVE decision (explicit)

- **A — correct architecture?** Yes. Direct full-manifest delegation via `apply_store_appearance_manifest(version=draft, manifest=preset.store_appearance)` is correct: `apply_preset` already owns richer validated palette/color-override/mobile-nav/header/footer/reset semantics; calling the broader `apply_ready_template_appearance` (which re-applies raw `preset.appearance/header/footer` via `apply_appearance_patch` + naive `dict.update`) would overwrite those cleaned values and regress palette/mobile-nav behavior. The plan's Step 5 ("use the typed manifest already declared by the preset") is satisfied.
- **B — duplicate/misleading dead API?** It is currently dead-but-tested (only its unit test calls it). It does not create active competing orchestration, but it is a latent confusion risk.
- **C — remain / narrow / remove?** Recommend narrowing or removing it in a later bounded cleanup (Phase-1 final gate). It has no legitimate production caller now that `apply_preset` is authoritative. Left unchanged in this task per the plan (MINOR, not IMPORTANT).

---

## TASK 6

- HEAD before: `0492ef90c6fe8aa8e44e33a3c8023c25be29b4ee`
- Production files changed: `apps/storefront_builder/settings_schema.py`, `apps/storefront_builder/views.py`, `apps/storefront_builder/services/render_service.py`
- Test file changed: `apps/storefront_builder/tests/test_phase1_appearance_authority.py`

### Pre-fix re-verification (Step 1)

`test_phase1_appearance_authority` before Task-6 code: `Ran 24 ... FAILED (failures=1)` — the sole RED was `test_explicit_local_variant_wins_store_default`; historical-unmarked GREEN. Recorded.

### Scope note — R4 path handled WITHOUT editing `r4_mutation_service.py`

The plan's Task-6 allowed-production list is exactly `settings_schema.py`, `views.py`, `render_service.py` (the committed plan's "Files" block and the strict scope-verification list both exclude `r4_mutation_service.py`, which is in the Task-6 "Do NOT modify" list). The plan's `File Structure` also assigns the R4 stamping to `settings_schema.py`. Therefore the R4 stamping is implemented INSIDE `settings_schema.clean_section_schema_patch` (which the R4 mutation service already calls): the marker is applied there after validation. `r4_mutation_service.py` is unchanged (verified `git diff` empty). This honors the allowed-file scope while satisfying Step 4's behavioral requirement.

### Exact variant-setting metadata rule

- New helper `settings_schema.mark_explicit_variant_override(*, settings, variant_setting_key, patch)`: returns `settings` unchanged if there is no registered `variant_setting_key` or the `patch` does not contain it; otherwise returns a deep copy with `settings["appearance_overrides"]["variant_explicit"] = True` (merging into any existing `appearance_overrides`, e.g. `typography`). Never mutates inputs.
- The marker key `variant_explicit` is NOT a member of the client-writable `appearance_overrides` contract — `validate_appearance_overrides` still rejects unknown keys. The marker is applied AFTER validation on the trusted server side, so a client cannot manufacture it directly.

### R4 marker path

`clean_section_schema_patch` (called by `_apply_section_update_settings`) now, after `definition.validate_settings(...)`, calls `mark_explicit_variant_override(settings=validated, variant_setting_key=definition.variant_setting_key, patch=raw_patch)`. An R4 `section.update_settings` mutation whose patch includes the variant key stamps the marker; a non-variant patch does not; an invalid variant value is rejected by the section validator before any persistence (no marker).

### Legacy marker path

`views.storefront_section_settings` (legacy POST): after `definition.validate_settings(raw)`, the marker is stamped ONLY when the section has a `variant_setting_key` AND the cleaned variant value DIFFERS from the previously stored value (`(section.settings or {}).get(variant_key)`). This is required because the legacy form always submits the variant control (e.g. `hero_style`) on every POST; presence is not intent. Content-only edits (same variant value) leave the marker state unchanged, preserving historical stores.

### Renderer precedence condition

`render_service._build_items_from_sections`: computed `effective_appearance_variant = None if variant_explicit else appearance_variant`. The manifest variant overlays `effective_settings[variant_setting_key]` and drives `active_variant` ONLY when not explicit. When `appearance_overrides.variant_explicit` is True, the saved local variant wins (both the settings mirror and `active_variant = effective_appearance_variant or resolve_active_variant(...)`). The Store manifest selection itself is not removed; non-variant settings precedence is unchanged; no Page Override.

### Results

- Historical unmarked preservation: `test_historical_unmarked_variant_keeps_legacy_inherited_behavior` GREEN (Store default still wins for unmarked rows).
- Explicit-local: `test_explicit_local_variant_wins_store_default` GREEN (previously the sole RED).
- R4 variant marker: `test_r4_variant_patch_marks_local_override_explicit` GREEN.
- R4 non-variant patch: `test_r4_non_variant_patch_does_not_mark` GREEN.
- R4 invalid patch: `test_r4_invalid_variant_patch_persists_no_marker` GREEN.
- R4 client cannot manufacture marker: `test_r4_client_cannot_manufacture_marker_via_appearance_overrides` GREEN.
- Legacy genuine variant change: `test_legacy_genuine_variant_change_marks_explicit` GREEN.
- Legacy content-only edit: `test_legacy_content_only_edit_does_not_mark` GREEN.
- Render end-to-end via real R4 edit: `test_marker_set_via_r4_makes_local_variant_win_at_render` GREEN.

### Clear-to-inherit operation

**DOES NOT EXIST.** There is no dedicated "inherit Store default / remove local variant override" merchant operation in the current UI/API. The existing `reset_section_to_baseline` / `reset_section_setting_to_baseline` reset to the *template baseline snapshot*, which is a different concept from "inherit Store Global default" and lives in the out-of-scope `preset_service.py`. Per Step 10, NO new UI/API was invented. **Product follow-up (later bounded UI task):** add an explicit clear-to-inherit control that removes `appearance_overrides.variant_explicit` and restores inherited Store behavior. Not a reason to change historical migration semantics.

### No bulk migration / no historical output flip

No bulk marker stamping, no bulk rewrite of existing rows, no automatic reinterpretation of historical saved local values. Existing sections without the marker render exactly as before. No DB migration (marker lives in existing settings JSON).

### Test matrix (Step 11) — results

1. historical unmarked + conflicting global → global wins: GREEN
2. explicit local + conflicting global → local wins: GREEN
3. R4 genuine variant change → marker True: GREEN
4. R4 non-variant edit → marker absent: GREEN
5. invalid R4 variant edit → no marker persistence: GREEN
6. legacy genuine variant change → marker True: GREEN
7. legacy content-only edit → historical marker state unchanged: GREEN
8. unrelated family/global selection → no impact on local marker semantics: covered by the render tests (manifest hero change does not alter the local marker); GREEN
9. existing inherit/reset operation → N/A (does not exist; recorded as product follow-up)

### Primary test

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  apps.storefront_builder.tests.test_r4_settings_schema \
  apps.storefront_builder.tests.test_u4_component_variants \
  --verbosity 1
```

Result: `Ran 107 tests ... OK`. TOTAL 107, GREEN 107, FAILURES 0. No intentional RED remains in `test_phase1_appearance_authority`.

### R4 / section regression

`test_r4_store_appearance_mutations + test_r4_mutation_api + test_section_registry + test_g23_builder_public_content_appearance` → `Ran 333 tests ... OK`.

`test_views` → `Ran 213 ... FAILED (failures=1, errors=1)` — the 2 failures are the known pre-existing `FullscreenEditorTests` (V3 topbar/fullscreen template-markup assertions), reproduced since Task 3 at earlier baselines and unrelated to this Python change (my diff touches no template). All section-settings view tests pass.

### Django check / migration check

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

### Explicit confirmations

- NO Page Override implemented.
- NO force-all Store policy implemented.
- NO preset changes (`preset_service.py` unchanged).
- NO authority-service changes (`appearance_authority_service.py` unchanged).
- NO `r4_mutation_service.py` change (R4 behavior achieved via `clean_section_schema_patch`).
- NO migration created.
- NO new variant.
- NO UI redesign (marker is internal, not a merchant field).
- NO business-domain change.
- `git diff --check` clean; only the 3 allowed production files + 1 allowed test file changed.
