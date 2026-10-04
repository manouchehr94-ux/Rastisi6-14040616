# Phase 5 — Task 1: Non-Mutating Candidate Template Preview Primitive

Date: 2026-09-11
Branch: `feature/phase5-design-expansion`
Starting SHA: `392d477fcd2e99c923937d70d4218ee258ac72ee`

This document covers Task 1 **and** its final corrective gate (full candidate
Store Appearance parity + a second independent re-review), both landed as
part of the same Task-1 acceptance before Task 2 starts.

## Files changed

- `apps/storefront_builder/services/preset_service.py` — extracted the existing pure "validate + prepare" phase of `apply_preset()` into a new private `_prepare_preset_application(draft, preset)`; added `ResolvedPresetCandidatePage`/`ResolvedPresetCandidate` (frozen dataclasses), `resolve_preset_candidate(draft, preset)`, `resolve_preset_candidate_by_key(draft, key)`.
- `apps/storefront_builder/services/render_service.py` — added `build_candidate_render_items(sections, store, page_context=None, *, global_appearance=None, store_appearance=None)`, a thin public wrapper around the existing private `_build_items_from_sections`; added an `if section.pk is not None:` guard to `_scoped_hero_slides`, `_scoped_banners`, and `_story_rail_context` so a candidate's unsaved sections fall straight to the existing store-wide fallback query instead of Django rejecting an unsaved-instance FK filter.
- `apps/storefront_builder/storefront_appearance/rendering.py` — extracted the pure manifest→render-state resolution loop out of `resolve_store_appearance_render_state(version)` into a new `resolve_store_appearance_manifest_state(manifest, *, version_id)`, called by both the unchanged persisted-version path and the new candidate path.
- `apps/storefront_builder/tests/test_preset_candidate_preview.py` — 20 focused tests.
- This evidence document.

No other files changed. No new URL route, no new view, no new template, no new migration, no new model.

## Design decision: what "resolve without writing" reuses

`apply_preset()` already ran in two phases: (1) validate/prepare appearance, header, footer and every page's section composition — entirely in-memory, no writes — then (2) write everything, inside one `@transaction.atomic` block. Phase (1) is now `_prepare_preset_application()`, called by both the unchanged (behavior-preserving) `apply_preset()` and the new `resolve_preset_candidate()`. This is a pure extract-method refactor: the moved code is byte-identical to what was inline before (verified by direct diff read and by two independent reviewers). **One validation implementation, not two.**

`resolve_store_appearance_render_state(version)` (the persisted-version render path, used by Preview/Publish/Public) already resolved the typed hero/product_view/card/badge/mega_menu/motion/header/footer/bottom_nav/layout manifest into a `ResolvedStoreAppearance`, but only from a saved `StorefrontLayoutVersion`. Its `if version.pk is None: raise ValueError(...)` guard is **unchanged and still gates that path**. The pure resolution loop inside it (manifest → `ResolvedStoreAppearance`, no I/O) is now `resolve_store_appearance_manifest_state(manifest, *, version_id)`, and `resolve_preset_candidate()` calls that exact same function after validating `preset.store_appearance` through the exact same canonical validator the real (persisting) path already uses (`storefront_appearance.validation.validate_store_appearance_manifest`, the same function `persistence.persist_store_appearance_manifest` calls). **One manifest-to-render-state resolver, two callers — never two implementations.**

Rendering reuses the **existing** precedent already in `render_service.py`: `build_default_render_items()` already builds unsaved (`pk=None`) `StorefrontSection` instances for stores that have never published a Storefront V2, and passes them into the same private `_build_items_from_sections()` every other render path uses. `build_candidate_render_items()` is a thin public wrapper around that same private function — not a second renderer.

## RED → GREEN, part 1: the base candidate primitive

Initial test run (before any production code changed):

```
AttributeError: module 'apps.storefront_builder.services.preset_service' has no attribute 'resolve_preset_candidate'
```

9 of the 10 originally-written tests failed this way; the 10th (`test_apply_preset_still_writes_real_sections`) tests only pre-existing `apply_preset` behavior and correctly passed as a baseline anchor.

```
$ python manage.py test apps.storefront_builder.tests.test_preset_candidate_preview -v 2
Ran 10 tests in 0.603s
OK
```

## Review round 1: story_rail CRITICAL, fixed and re-verified

An independent, isolated reviewer (fresh agent, no shared context with the implementer) found **one CRITICAL issue**: `_story_rail_context` in `render_service.py` does the exact same per-section-scoped FK query pattern as `_scoped_hero_slides`/`_scoped_banners`, but only the first two were guarded. The reviewer proved this reachable via the real, registered `is_ready_template=True` preset `premium_boutique`.

**Fix applied:** the identical `if section.pk is not None:` guard added to `_story_rail_context`. **RED confirmed for the fix itself** (guard temporarily removed, exact reviewer-reported `ValueError: Model instances passed to related filters must be saved.` reproduced), then restored to GREEN. Regression test `test_candidate_renders_a_story_rail_bearing_template_without_crashing` added against the real `premium_boutique` preset.

```
$ python manage.py test apps.storefront_builder.tests.test_preset_candidate_preview -v 2
Ran 11 tests in 0.693s
OK
```

Review round 1 verdict: 1 CRITICAL → fixed → **CRITICAL = 0, IMPORTANT = 0.**

## Final corrective gate: full candidate Store Appearance parity

**Why:** the candidate previously resolved section composition and legacy header/footer config, but explicitly did **not** resolve `preset.store_appearance` (the typed manifest) — insufficient for downstream live Template Preview (Tasks 2/3), which need the candidate to represent everything a real Apply would make authoritative.

**What changed** (see "Design decision" above for the shared-resolver architecture):

1. `storefront_appearance/rendering.py`: `resolve_store_appearance_manifest_state(manifest, *, version_id)` extracted from `resolve_store_appearance_render_state(version)`; the latter's saved-version guard is untouched.
2. `preset_service.resolve_preset_candidate()`: when `preset.store_appearance` is truthy, validates it via `validate_store_appearance_manifest(raw, require_complete=True)` (the same canonical validator the real persisting path uses) and resolves the validated manifest via the same shared function. Result stored as a new `store_appearance: ResolvedStoreAppearance | None` field on `ResolvedPresetCandidate`.
3. `apply_preset()`'s own write path (`appearance_authority_service.apply_store_appearance_manifest(...)` and everything after it) is **completely untouched** — the new resolution only happens inside `resolve_preset_candidate()`.

**RED → GREEN** for the 7 new store-appearance tests: all initially failed with `AttributeError: 'ResolvedPresetCandidate' object has no attribute 'store_appearance'` (6 of 7) or an unrelated fixture-setup issue in the 7th, which was corrected in the test itself (the test needed a valid `layout_preset_key`, not a synthetic one — appearance-overlay validation checks that field before store_appearance validation is ever reached). After implementation: all 7 green.

**Strongest proof — candidate/real-apply parity**, `test_candidate_and_real_apply_resolve_identical_store_appearance_render_state`: resolves a candidate for `dense_marketplace` against one Draft, separately applies the exact same preset **for real** onto a **completely different Store's** Draft, and asserts the two independently-resolved `ResolvedStoreAppearance` states select identical components for every one of the 10 families. Green, both on the implementer's own run and independently re-run by the second reviewer.

**Render-level proof — candidate rendering consumes the candidate's state, not the Draft's persisted one**, `test_candidate_rendering_consumes_candidate_store_appearance_not_drafts_persisted_one`: applies `editorial_jewelry` (badge="none") for real onto the Draft, then resolves+renders a **candidate** for `dense_marketplace` (badge="sale") against that same, now-mutated Draft; asserts the rendered `product_section`'s card settings reflect the candidate's badge treatment, not the Draft's currently-persisted one.

## Review round 2: two IMPORTANT findings, fixed and re-verified

A second, fresh independent reviewer (no shared context, reviewing the complete diff from the starting SHA through this corrective) verified all store-appearance-parity claims directly (ran the tests, read both call sites of the shared resolver, confirmed the saved-version guard, confirmed the same validator function object is used on both paths, confirmed `apply_preset()`'s write phase is byte-identical). **Verdict: PASS, 0 CRITICAL, 2 IMPORTANT:**

1. **Container/row settings silently discarded.** `resolve_preset_candidate()` built `pages` from only the `rows` half of `prepared.pages_to_replace`, discarding `prepared_container_settings` — data already computed for free by `_prepare_preset_application`, needed by the real render path's row/column grouping (`render_service.build_container_render_items`, used by both `storefront_context_service.py` and `views.py`). Without it, a candidate could not be previewed faithfully for any multi-column/row-grouped template.
2. **Evidence doc stale relative to the store-appearance corrective** — this document (as it stood before this rewrite) still listed store_appearance resolution as a "Known limitation" after it had been implemented, and its test table omitted the 7 new tests.

**Fixes applied:**

1. New `ResolvedPresetCandidatePage` dataclass (`sections`, `container_settings`), replacing the bare list previously stored per page_type in `ResolvedPresetCandidate.pages`. `resolve_preset_candidate()` now passes through `prepared.pages_to_replace`'s container settings unchanged — a pure exposure fix, no new design, exactly as the reviewer characterized it. All existing test call sites updated (`candidate.pages["home"]` → `candidate.pages["home"].sections`). Two new tests added: `test_candidate_exposes_container_settings_alongside_sections` and `test_candidate_container_settings_match_what_a_real_apply_persists` (the latter, a parity test: candidate's container settings vs. what a real Apply onto a different Store's Draft actually persists onto `StorefrontContainer` rows — green).
2. This document rewritten to reflect the corrective (this rewrite).

```
$ python manage.py test apps.storefront_builder.tests.test_preset_candidate_preview -v 2
Ran 20 tests in 1.547s
OK
```

Review round 2 verdict after fixes: **CRITICAL = 0, IMPORTANT = 0.**

## Focused tests (20, all passing)

| Test | Proves |
|---|---|
| `test_candidate_header_variant_matches_declared_recipe` | Candidate reflects the previewed template's declared header variant |
| `test_candidate_hero_style_setting_matches_declared_recipe` | Candidate reflects the declared hero style (section-level settings) |
| `test_candidate_renders_a_story_rail_bearing_template_without_crashing` | Regression for review-round-1 CRITICAL, against a real registered preset |
| `test_candidate_renders_through_the_shared_renderer` | Candidate sections render through the exact same `render_service` pipeline; sections remain unsaved throughout |
| `test_two_different_templates_resolve_to_visibly_different_candidates` | Two different templates produce visibly different header/hero DNA, not just "no crash" |
| `test_candidate_store_appearance_matches_declared_manifest_selections` | Candidate's typed manifest equals the preset's declared, validated selections |
| `test_candidate_store_appearance_differs_for_a_different_template_in_a_render_affecting_family` | Two templates' candidates differ in a real, render-affecting family (badge) |
| `test_candidate_rendering_consumes_candidate_store_appearance_not_drafts_persisted_one` | Render call consumes the CANDIDATE's appearance state, not the Draft's persisted one |
| `test_candidate_resolution_with_store_appearance_still_leaves_draft_unchanged` | Draft unchanged even when store_appearance resolution is exercised |
| `test_real_apply_still_persists_the_same_typed_manifest` | Real Apply's persisted manifest is unaffected by this corrective |
| `test_invalid_store_appearance_manifest_fails_through_the_canonical_validator_and_does_not_mutate` | Invalid manifest fails via the same `InvalidStoreAppearanceContract`, non-mutating |
| `test_candidate_and_real_apply_resolve_identical_store_appearance_render_state` | Strongest parity proof: candidate == what a real Apply (on a different Store) would render |
| `test_candidate_exposes_container_settings_alongside_sections` | Candidate exposes container/row settings, not just a flat section list |
| `test_candidate_container_settings_match_what_a_real_apply_persists` | Candidate's container settings equal what a real Apply actually persists |
| `test_apply_preset_still_writes_real_sections` | Real (writing) Apply is unaffected by the refactor |
| `test_candidate_resolution_does_not_leak_into_a_subsequent_real_apply` | Candidate resolution never contaminates a later real Apply |
| `test_locked_section_conflict_raises_and_does_not_mutate` | Invalid candidate (locked-section conflict) fails through the same typed error `apply_preset` uses, non-mutating |
| `test_unknown_preset_key_raises_and_does_not_mutate` | Invalid candidate (unknown key) fails through the same typed error, non-mutating |
| `test_candidate_resolution_for_multiple_templates_still_leaves_draft_unchanged` | Draft unchanged across repeated candidate resolutions |
| `test_candidate_resolution_leaves_real_draft_byte_identical` | Full-field Draft snapshot unchanged after one candidate resolution |

## Regression

Required by the plan, all green (re-run after the final corrective):

```
$ python manage.py test apps.storefront_builder.tests.test_a8_ready_template_contracts \
    apps.storefront_builder.tests.test_a8_ready_template_catalog \
    apps.storefront_builder.tests.test_r4_appearance_overrides \
    apps.storefront_builder.tests.test_preset_service \
    apps.storefront_builder.tests.test_layout_preset_registry \
    apps.storefront_builder.tests.test_render_service -v 1
Ran 194 tests ... OK (skipped=1)
```

### Task-8 content-preserving template-switch/reset safety regression

Re-run after the final corrective:

```
$ python manage.py test apps.storefront_builder.tests.test_acceptance_batch2 \
    apps.storefront_builder.tests.test_phase1_appearance_authority \
    apps.storefront_builder.tests.test_r4_vertical_slice \
    apps.storefront_builder.tests.test_u10_ready_template_catalog \
    apps.storefront_builder.tests.test_u7_ready_template_baseline -v 1
Ran 312 tests ... FAILED (failures=1)
```

**Same single pre-existing failure as before this corrective, unchanged in identity/behavior:**
`test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary` — an R4 `appearance.update` mutation (a font patch, unrelated to Ready Template apply/preview) calls `layout_service.validate_appearance_config` twice instead of once expected. This code path (`r4_mutation_service.py`'s `appearance.update` handler) was never touched by this task's diff, at either the base implementation or this corrective. Previously reproduced identically in an isolated `git worktree` at the starting SHA `392d477`; re-confirmed identical (same call count, same traceback) after the corrective. Confirmed pre-existing, not a regression.

### Broader scan (own initiative, supplementary — not the acceptance authority)

A broader scan (run before this corrective, against the base Task-1 implementation) across `test_dark_digital_luxury_v2`, `test_dense_marketplace_beraito_v2`, `test_desktop_canvas_viewport`, `test_editorial_jewelry_saremi_v2` found 18 failures + 1 error, and a separate full `apps.storefront_builder` suite run (2908 tests, completed after ~50 minutes) found 30 failures + 2 errors total — all of the same class: stale characterization tests pinned to old recipe version numbers/compositions (e.g. asserting `preset.version == "2"` where the registry's current latest is `"3"`), in files this task's diff never touches (`a8_ready_templates.py`/`layout_preset_registry.py` content is untouched by any Task-1 commit). The first four-file cluster was reproduced identically in an isolated worktree at the starting SHA. Per the corrective task's own instruction, a second full 2908-test run was not repeated for this corrective — the explicitly required regression scope (above) is green, and no new failure class has appeared.

## Django check / migration check / whitespace check

Re-run after the final corrective:

```
$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
No changes detected

$ git diff --check
(no output, exit 0)
```

## Draft non-mutation proof

`_snapshot()` (used across every non-mutation test) captures `edit_revision`, `appearance_config`, `header_config`, `footer_config`, `template_provenance`, `template_baseline_snapshot`, the full ordered list of `(page_id, section_key, order, settings, is_locked)` for every section, the `StorefrontContainer` count, the `StorefrontLayoutVersion` count, the `StorefrontEditHistoryEntry` count, and the `StorefrontLayout.published_version_id`. Exercised both for the base primitive and — separately — for candidate resolution that now also performs store_appearance validation/resolution (`test_candidate_resolution_with_store_appearance_still_leaves_draft_unchanged`) and for an invalid manifest (`test_invalid_store_appearance_manifest_fails_through_the_canonical_validator_and_does_not_mutate`). All fields compare equal in every case.

## Renderer authority proof

`build_candidate_render_items()` is a thin wrapper whose entire body is one call into the existing private `_build_items_from_sections()` — the same function `build_page_render_items()` and `build_default_render_items()` already call. No new template resolution, no new context-building logic, no new render-item shape.

## Preset authority proof

`resolve_preset_candidate()`'s section/appearance/header/footer resolution is one call into `_prepare_preset_application()`, the same function `apply_preset()` calls. Its store_appearance resolution is `validate_store_appearance_manifest()` (same function `persist_store_appearance_manifest` calls) followed by `resolve_store_appearance_manifest_state()` (same function `resolve_store_appearance_render_state()` calls). `resolve_preset_candidate_by_key()` resolves the key via the same `layout_preset_registry.get_layout_preset()` lookup `apply_preset_by_key()` uses.

## No-persistence proof

`_PreparedPresetApplication`, `ResolvedPresetCandidatePage`, and `ResolvedPresetCandidate` are all plain `@dataclasses.dataclass(frozen=True)` — no Django `Model` base class, no `.save()` method. Grepped the complete diff for `.save(`, `bulk_create`, `bulk_update`, `.delete(`, `cache.set`, `request.session[` — zero occurrences inside any candidate-resolution code path (all real occurrences are inside `apply_preset()`'s own unchanged write phase). No new migration.

## Reviewer verdicts

- **Review round 1** (base primitive): FAIL → 1 CRITICAL (story_rail crash) → fixed, RED/GREEN re-verified → **CRITICAL = 0, IMPORTANT = 0.**
- **Review round 2** (store_appearance + container-settings corrective, full diff from starting SHA): PASS with 2 IMPORTANT (container settings discarded; evidence doc stale) → both fixed, tests added, doc rewritten → **CRITICAL = 0, IMPORTANT = 0.**

## Required gate labels (final corrective)

| Gate | Verdict |
|---|---|
| STORE APPEARANCE CANDIDATE PARITY | PASS |
| TRANSIENT MANIFEST VALIDATION REUSED | PASS |
| ONE MANIFEST-TO-RENDER RESOLVER | PASS |
| CANDIDATE VS APPLIED RENDER STATE PARITY | PASS |
| DRAFT NON-MUTATION | PASS |
| STORY_RAIL CORRECTIVE | PASS |
| INDEPENDENT RE-REVIEW | PASS |

## Known limitations

- No HTTP-layer consumer exists yet (no URL, no view) — intentionally out of scope per the task's own YAGNI instruction; Tasks 2 and 3 will build on this primitive.
- The full 2908-test `apps.storefront_builder` suite was not re-run to completion after this final corrective (its own ~50-minute runtime makes it supplementary evidence, not the acceptance gate, per this corrective task's own explicit instruction); the explicitly required regression scope is fully covered and green, and every full-suite failure observed to date (base implementation and this corrective alike) has traced to the same pre-existing, unrelated "stale recipe-version characterization test" class.
