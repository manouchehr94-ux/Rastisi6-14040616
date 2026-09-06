# Task 1 — Brand RED characterization and existing QA setup

- Starting HEAD: `c34a04e71cc62d191d6fe8238ef4e6735fb6642f`
- Branch: `feature/storefront-vertical-slice-phase3`
- Type: TEST-ONLY / HARNESS-ONLY (no production code). Plan explicitly permits committing the single V01 test-only RED in this task.

## Files changed (6 allowed only)
- `apps/storefront_builder/tests/test_r4_settings_schema.py` — added `Phase3BrandPreservationTests.test_variant_intent_survives_title_patch` (V01 desired-invariant RED) + `get_definition` import.
- `apps/storefront_builder/tests/test_render_service.py` — extended `BrandCarouselRenderTests`: manual-order-preserved/foreign+inactive omitted across grid/carousel/beauty_tabs, sibling isolation, invalid persisted display_mode safe fallback (+ `_brand_fixture` helper creating a real second store).
- `apps/storefront_builder/tests/test_g22_preview_media_render_consistency.py` — `BrandCarouselWrapperConsistencyTests` (wrapper preserves resource links/title/background/hide flags; public vs preview envelope difference).
- `apps/storefront_builder/tests/test_qa_harness_contract.py` — `test_r4_runner_and_command_support_phase3_viewports` (existing assertions untouched).
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` — optional `--phase3` arg + `phase3` manifest field; no default-behavior change; backup/restore/fixture untouched.
- `tools/storefront_builder_r4_qa/run.mjs` — three-viewport phase3 capture to `manifest.report_dir` (off by default); `/usr/local/bin/chrome` added to launch candidate list. Single runner, no new package.

## Exact commands + results (controller-run, authoritative)
1. V01 RED: `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema.Phase3BrandPreservationTests --noinput -v2`
   → `FAIL: test_variant_intent_survives_title_patch` at line 523 `self.assertTrue(renamed.get('appearance_overrides', {}).get('variant_explicit'))` → `AssertionError: None is not true`. Ran 1, FAILED (failures=1). **Intended RED, correct reason (marker dropped after title-only patch; `display_mode` stays `carousel`).**
2. Focused suite: `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_qa_harness_contract --noinput`
   → **Ran 148 tests; FAILED (failures=1, skipped=1).** The single failure is the V01 RED. The single skip is the pre-existing `QuickLinksRenderTests.test_menu_from_another_store_never_leaks` (baseline exception, not introduced here).
3. `node --check run.mjs` → OK (exit 0). `git diff --check` → clean.

## RED signature
V01: `appearance_overrides.variant_explicit` marker is lost after a title-only `clean_section_schema_patch`, because `brand_carousel` is not in `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS` and `mark_explicit_variant_override` only re-stamps on a variant-key edit. This is the sole planned RED crossing the Task-1 boundary; it MUST be closed by Task 2.

## Counts
- Focused: 148 total / 147 pass / 1 fail (V01 planned) / 0 error / 1 skip (pre-existing).

## Browser
Harness prepared (phase3 mode + viewports + chrome path). No browser certification claimed in Task 1 (initial observation only per plan). Real browser matrix is Task 3/5/7.

## Scope audit
Only the 6 allowed test/harness files changed. No production source, no migration, no new file/module. Confirmed via `git diff --name-only`.

## Review
Independent semantic_reviewer verdict recorded below.

## Readiness for Task 2
V01 RED isolated and logged; characterization GREEN (not forced); harness available; no production edits. READY.
