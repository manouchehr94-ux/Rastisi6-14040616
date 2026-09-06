# Phase 2 — Lifecycle & Safety: Preparation Baseline

Preparation for Phase 2 of the Storefront Appearance Convergence program
(`docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md`).
This is a preparation/architecture-lock artifact. **No production or test code was changed** during preparation.

## Official Phase-2 baseline

- Repository: `manouchehr94-ux/rastisi5`
- Official source branch: `docs/storefront-appearance-convergence`
- Official Phase-2 baseline SHA (merge of PR #1): `515518227c09f888972fa6eda756867097358dfb`
- Phase-1 feature HEAD incorporated in that merge: `8cea65e60d4afff40d43f8f14f3773ff5f071da2` (verified ancestor)
- Approved G2.3 ancestor: `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` (verified ancestor)

## Branch / worktree / environment

- Phase-2 branch: `feature/storefront-lifecycle-safety-phase2` (created from `515518227c09f888972fa6eda756867097358dfb`)
- Worktree: `/projects/rastisi5_phase2` (isolated; the Phase-1 worktree `/projects/rastisi5_phase1` is preserved and untouched)
- Virtual environment: `/projects/rastisi5_phase2_venv` (created outside the worktree)
- Python: `Python 3.12.13`
- Django: `5.2.17`
- Worktree clean at baseline (`git status --short` empty).

## Baseline health checks (fresh)

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

## Existing lifecycle test matrix (fresh, real module names)

```bash
/projects/rastisi5_phase2_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_layout_service \
  apps.storefront_builder.tests.test_storefront_page \
  apps.storefront_builder.tests.test_phase27_history_identity \
  apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization \
  apps.storefront_builder.tests.test_phase5_composition_lifecycle \
  apps.storefront_builder.tests.test_phase35a_publish_container_invariant \
  apps.storefront_builder.tests.test_preset_service \
  apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_stable_section_identity \
  --verbosity 1
```

Result: `Ran 216 tests ... OK`.

## Existing media test matrix (fresh)

```bash
/projects/rastisi5_phase2_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_media_asset_lifecycle \
  apps.storefront_builder.tests.test_media_views \
  apps.storefront_builder.tests.test_media_write_path \
  apps.storefront_builder.tests.test_g2_1_media_editability_roundtrip \
  apps.storefront_builder.tests.test_g22_preview_media_render_consistency \
  --verbosity 1
```

Result: `Ran 61 tests ... OK`.

## Known pre-existing failures (out of Phase-2 scope)

Carried from Phase 1, reproduced on earlier commits, unrelated to lifecycle/media state transformation:

- `apps.storefront_builder.tests.test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` (FAIL) — V3 topbar template markup assertion; reproduced at `28e48555…` (pre-Task-3, Phase 1).
- `apps.storefront_builder.tests.test_views.FullscreenEditorTests.test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` (ERROR) — same class.
- `apps.storefront_builder.tests.test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset` (FAIL) — read-only gallery label drift; reproduced at `dcff5651…` (pre-Task-5, Phase 1).

These are documented Phase-1 exceptions; Phase 2 does not touch templates/gallery. They are NOT in the Phase-2 in-scope lifecycle/media modules, all of which are GREEN above.

## Explicit statement

**NO production application code was changed during Phase-2 preparation.** The only changes are documentation/evidence files under `docs/superpowers/specs/`, `docs/superpowers/plans/`, and `docs/qa_evidence/storefront_appearance_convergence/phase2/`. Verified by `git status --short` / `git diff --name-only` at commit time (see final scope verification in the preparation report).
