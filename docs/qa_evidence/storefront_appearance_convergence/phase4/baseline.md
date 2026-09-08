# Phase 4 preparation baseline

Date: 2026-09-08. NO production changes. NO test changes. No baseline failure was fixed.

## Workspace authorization

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Branch: `feature/phase4-builder-legacy-convergence`, created from `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
  (Phase-4 architecture audit commit; parent `185166a138e47c012b3af7f53ea6bcb94fb84bd0`, Phase-3 final)
- `git rev-parse HEAD` at baseline time: `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
- `git status --short`: empty (worktree clean) at baseline time
- Preconditions verified: `origin/feature/phase4-architecture-audit` ==
  `969a9b411ca712928c2bf31416bdde2ee8aaabb5`; `origin/backup/rastisi6-phase4-architecture-audit-20260907`
  == same SHA; `origin/main` == `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged)
- Safety refs created: `feature/phase4-builder-legacy-convergence` and
  `backup/rastisi6-phase4-start-20260908`, both == `969a9b4`, both pushed and verified

## Runtime and health

|Command|Result|
|---|---|
|`python --version`|Python 3.11.15|
|`python -c "import django; print(django.get_version())"`|5.2.17|
|`python manage.py check`|Exit 0; System check identified no issues (0 silenced).|
|`python manage.py makemigrations --check --dry-run`|Exit 0; No changes detected|
|`git diff --check`|Exit 0; clean|

Environment: fresh Python virtualenv (`.venv`) created this session from `requirements.txt` (no
pre-existing venv was present in this container). Local disposable SQLite (`db.sqlite3`), created
by Django's test runner per-run — not a populated application database. This matches the DB
strategy authorized by Ruling B (no important real data; fresh deterministic DB/seed allowed).

## Baseline regression — Run A / B / C (exact commands from `phase3/baseline.md`, re-run verbatim)

No module list was reconstructed or substituted; the exact argument lists from Phase-3's
`baseline.md` were re-run byte-for-byte.

### Run A — vertical/lifecycle/domain

```
python manage.py test apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_section_data_service apps.storefront_builder.tests.test_u4_component_variants apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_r4_resource_source apps.storefront_builder.tests.test_r4_resource_picker apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_r4_mutation_api apps.storefront_builder.tests.test_phase1_appearance_authority apps.storefront_builder.tests.test_phase2_lifecycle_safety apps.storefront_builder.tests.test_stable_section_identity apps.storefront_builder.tests.test_responsive_rendering apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_public_homepage_integration apps.storefront_builder.tests.test_phase_1b_render_and_context apps.storefront_builder.tests.test_r4_store_appearance_rendering apps.catalog.tests.test_brand_service apps.catalog.tests.test_collection_service apps.catalog.tests.test_collection_public_views apps.catalog.tests.test_collection_integration --noinput --verbosity 1
```

Result: `Ran 734 tests in 269.315s`; `FAILED (failures=1, skipped=1)`; exit 1. Named failure:
`AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary` —
**exact same signature as Phase-3's `final_gate.md` Run A** (`validate_appearance_config` called 2
times instead of once). Skip count (1) consistent with the known
`QuickLinksRenderTests.test_menu_from_another_store_never_leaks` signature.

### Run B — capability/asset/QA and known baseline exceptions

```
python manage.py test apps.storefront_builder.tests.test_views.FullscreenEditorTests apps.storefront_builder.tests.test_u8_template_gallery apps.storefront_builder.tests.test_u1b1_variant_runtime_wiring apps.storefront_builder.tests.test_u1b2_capability_metadata_wiring apps.storefront_builder.tests.test_shared_capabilities apps.storefront_builder.tests.test_r4_appearance_overrides apps.storefront_builder.tests.test_qa_harness_contract apps.content.tests.test_phase2_media_reachability --noinput --verbosity 1
```

Result: `Ran 121 tests in 20.097s`; `FAILED (failures=2, errors=1)`; exit 1. Named failures/errors —
all three **exact same signatures as Phase-3's `final_gate.md` Run B**:
1. `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` — `:aria-pressed="fullscreen"` absent.
2. `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` — `StopIteration`.
3. `test_header_footer_variant_labels_shown_for_updated_preset` — Persian gallery label mismatch.

### Run C — pilot-reachable Cart fragment regression baseline

```
python manage.py test apps.cart.tests.test_cart_views apps.cart.tests.test_cart_security apps.storefront_builder.tests.test_phase2_universal_renderer --noinput --verbosity 1
```

Result: `Ran 77 tests in 7.418s`; `OK`; exit 0 — **exact same result as Phase-3's `final_gate.md` Run C**.

**Combined: 932 executions, 927 pass, 3 fail, 1 error, 1 skip.** Identical totals and identical
named signatures to Phase-3's Task-8 final gate. **No new regression exists anywhere in the
baseline matrix between the Phase-3 close and the Phase-4 start** — expected, since no production
code changed between `185166a1` (Phase-3 final) and `969a9b4` (the audit commit, docs-only).

## Django check / migration check / diff check

```
python manage.py check                              → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run    → No changes detected
git diff --check                                     → clean
```

No migration file exists anywhere in the cumulative Phase-3+Phase-4-audit diff (confirmed
consistent with the Phase-3 final gate's own finding).

## Browser availability

Not yet exercised at Task-0 time (browser certification happens per-task as families are
migrated, per the Master Prompt). `tools/storefront_builder_r4_qa/run.mjs` and
`qa_storefront_builder_r4.py` exist unchanged from Phase 3 (Task 4 will generalize them before any
new family's browser certification).
