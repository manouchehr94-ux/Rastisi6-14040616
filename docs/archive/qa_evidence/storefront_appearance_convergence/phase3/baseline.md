# Phase 3 preparation baseline

Date: 2026-09-06. NO production changes. NO test changes. No baseline failure was fixed.

## Workspace authorization

The first repository commands, executed with implicit current workspace, returned:

```text
git rev-parse --show-toplevel
D:/Projects/RastiSi5_Phase3
git branch --show-current
feature/storefront-vertical-slice-phase3
git rev-parse HEAD
e244619f395ebf0dbebc77d2033841e17f1cd099
git status --short
(empty)
```

This is the required official Phase-2 merge baseline. Repository reference: manouchehr94-ux/rastisi5; integration branch docs/storefront-appearance-convergence. No branch/worktree creation, checkout, push, PR, merge or rebase was performed. Windows slash spelling is immaterial to the verified Git identity.

## Runtime and health

|Command|Result|
|---|---|
|`python --version`|Python3.12.10|
|`python -c "import django; print(django.get_version())"`|5.2.16|
|`python manage.py check`|Exit0; System check identified no issues (0 silenced).|
|`python manage.py makemigrations --check --dry-run`|Exit0; No changes detected|

Tests use Django's created test database, not a populated local application database. Local read-only Store lookup failed `django.db.utils.OperationalError: no such table: stores_store`. No migrate/seed/browser request was run against that application database. Existing QA node_modules/playwright-core is absent. Browser readiness therefore requires the future plan's bounded setup; it is not evidence of application runtime certification today.

## Discovered focused matrix

Modules were located in the real test directories and source classes inspected before execution. All commands below start with `python manage.py test` and end with `--noinput --verbosity 1`. The three lists are the exact arguments used, not invented test labels.

### Run A — vertical/lifecycle/domain

```powershell
python manage.py test apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_section_data_service apps.storefront_builder.tests.test_u4_component_variants apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_r4_resource_source apps.storefront_builder.tests.test_r4_resource_picker apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_r4_mutation_api apps.storefront_builder.tests.test_phase1_appearance_authority apps.storefront_builder.tests.test_phase2_lifecycle_safety apps.storefront_builder.tests.test_stable_section_identity apps.storefront_builder.tests.test_responsive_rendering apps.storefront_builder.tests.test_g22_preview_media_render_consistency apps.storefront_builder.tests.test_public_homepage_integration apps.storefront_builder.tests.test_phase_1b_render_and_context apps.storefront_builder.tests.test_r4_store_appearance_rendering apps.catalog.tests.test_brand_service apps.catalog.tests.test_collection_service apps.catalog.tests.test_collection_public_views apps.catalog.tests.test_collection_integration --noinput --verbosity 1
```

Result: `Ran 633 tests in 525.445s`; `FAILED (failures=1, skipped=1)`; exit1. PASS631, FAIL1, ERROR0, SKIP1. Test database destroyed afterward; system check clean.

### Run B — capability/asset/QA and known baseline exceptions

```powershell
python manage.py test apps.storefront_builder.tests.test_views.FullscreenEditorTests apps.storefront_builder.tests.test_u8_template_gallery apps.storefront_builder.tests.test_u1b1_variant_runtime_wiring apps.storefront_builder.tests.test_u1b2_capability_metadata_wiring apps.storefront_builder.tests.test_shared_capabilities apps.storefront_builder.tests.test_r4_appearance_overrides apps.storefront_builder.tests.test_qa_harness_contract apps.content.tests.test_phase2_media_reachability --noinput --verbosity 1
```

Result: `Ran 119 tests in 47.180s`; `FAILED (failures=2, errors=1)`; exit1. PASS116, FAIL2, ERROR1, SKIP0. Test database destroyed afterward; system check clean.

### Run C — pilot-reachable Cart fragment regression baseline

Final topology review confirmed that Cart update/remove fragments can render placed Brand/Collection tiles. Existing tests were located and then run:

```powershell
python manage.py test apps.cart.tests.test_cart_views apps.cart.tests.test_cart_security apps.storefront_builder.tests.test_phase2_universal_renderer --noinput --verbosity 1
```

Result: `Ran 59 tests in 6.653s`; `OK`; exit0. PASS59, FAIL0, ERROR0, SKIP0. These tests preserve current cart behavior; they do not already prove container projection parity for both pilots. Source `_render_cart_container` omits render_containers/use_container_layout; future Task3 supplies Brand desired-invariant tests, Task5 Collection and Task6 the combined case.

**Combined RunA/B/C totals:811 test executions;806 pass;3 failures;1 error;1 skip.** These are runner counts, not a claim of unique methods: Django can discover imported test base classes. No unreported new failure appeared in the focused matrix. The matrix is deliberately not the entire repository suite.

Supplemental signature verification reran `python manage.py test apps.storefront_builder.tests.test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset --noinput --verbosity 1` through a subprocess output filter. First filter hit console `UnicodeEncodeError` while printing the Persian assertion (the selected test failure was already reported); retry with ASCII-escaped output completed: `Ran 1 test in 1.810s`, `FAILED (failures=1)`, test exit1. It reproduced exactly the Persian signature below. These two single-test reruns are supplemental, excluded from the811 matrix count; the output-filter encoding error is tooling, not another application test failure.

|Coverage|required evidence source in executed matrix|
|---|---|
|Brand Showcase/loader/order/isolation|test_render_service.BrandCarouselRenderTests; test_brand_service|
|Brand variants/schema/resources|test_u1b1_variant_runtime_wiring; test_r4_settings_schema; test_r4_resource_source; test_r4_resource_picker|
|Collection tiles/domain/detail|test_u4_component_variants; test_render_service.CollectionTilesRenderTests and CollectionContextAwareSectionsTests; catalog collection modules|
|Shared renderer/Preview/Public|test_render_service; test_phase_1b_render_and_context; test_public_homepage_integration; test_r4_store_appearance_rendering|
|Fragments/HTMX|Admin partial coverage in R4 modules; no dedicated Brand/Collection endpoint. Real Cart update/remove can render both placed pilots; RunC covers current cart/renderer behavior. Missing container-context and isolated Preview wrapper/browser replacement proof is V05, not a claimed baseline PASS.|
|CSS/assets/responsive/media|test_shared_capabilities; test_responsive_rendering; test_g22_preview_media_render_consistency; browser computed styles unexecuted|
|R4 mutation/Draft/Published/history/tenant|test_r4_mutation_api; test_phase2_lifecycle_safety; test_r4_vertical_slice|
|Appearance authority/resolution|test_phase1_appearance_authority; test_r4_appearance_overrides; test_r4_store_appearance_rendering|
|Stable identity|test_stable_section_identity|
|Phase2 media safety|apps.content.tests.test_phase2_media_reachability|
|Browser infrastructure contracts|test_qa_harness_contract; source inspection of existing R4 command/runner|

## Exact pre-existing failure signatures

These four method-level exceptions occur at the authorized baseline before documentation changes. Phase2 final_gate.md independently records the same exceptions and prior-baseline reproduction. No old worktree was created or Phase1/2 reopened to fix them.

1. `apps.storefront_builder.tests.test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`, line927: `AssertionError: Expected 'validate_appearance_config' to have been called once. Called 2 times.` Source assertion `mock_validate.assert_called_once()`.
2. `apps.storefront_builder.tests.test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`, line301: `AssertionError: ':aria-pressed="fullscreen"' not found in ...`; expected literal absent from editor HTML. Huge response body is omitted, not the diagnostic.
3. `apps.storefront_builder.tests.test_views.FullscreenEditorTests.test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`, line320: `StopIteration` at `next(line for line in html.splitlines() if marker in line)`.
4. `apps.storefront_builder.tests.test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset`: `AssertionError: False is not true : Couldn't find 'بازارگاهی (جستجو-محور)' in the following response`. Gallery response body omitted. This expectation concerns an unchanged gallery label.

The one RunA skip is `test_render_service.QuickLinksRenderTests.test_menu_from_another_store_never_leaks` at line843: `self.skipTest("no second store fixture available")`. A skip is not tenant proof; future pilot fixtures must create the second store explicitly.

## Additional nonmutating source/contract probes

Runtime SectionDefinition enumeration confirmed Brand capabilities background/columns/destination/motion/responsive/spacing, schema title/source/display_mode/show_view_all. Collection tiles has background/motion/responsive/spacing and no schema. Collection header has background/responsive/spacing; products card/columns/columns_visual/responsive; neither has schema. Runtime list_components enumeration found no Brand/Collection tile component aliases.

Pure Python schema probe (no database mutation):

```python
from apps.storefront_builder.section_registry import get_definition
from apps.storefront_builder.settings_schema import clean_section_schema_patch
d = get_definition('brand_carousel')
a = clean_section_schema_patch(d, {'display_mode': 'carousel'}, d.default_settings())
b = clean_section_schema_patch(d, {'title': 'Phase3'}, a)
print(a.get('appearance_overrides'))  # {'variant_explicit': True}
print(b.get('appearance_overrides'))  # None
```

This is V01 evidence, not a newly added test or a production fix. Source inspection also establishes V02 beauty_tabs View-all mismatch, V03 missing Collection adapter/ownership support, V06 asset-envelope mismatch. Their browser consequences remain future evidence.

## Preparation scope and verification

Only four approved Markdown files are permitted. Before commit, run `git status --short`, `git diff --check`, `git diff --name-only`, then explicit-path staging and `git diff --cached --name-only`/`--check`. Stop for any other tracked or untracked change. Test-generated ignored runtime/cache files are not production/test source edits. Commit message: `docs: lock storefront vertical slice phase3 plan`. Commit SHA is returned by Git in the final handoff (not embedded self-referentially here).

Preparation is complete only after the four-file commit and clean-status verification. Phase3 production implementation, browser certification, push and PR remain unperformed.
