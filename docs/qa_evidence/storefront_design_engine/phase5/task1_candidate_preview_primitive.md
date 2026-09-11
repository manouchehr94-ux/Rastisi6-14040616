# Phase 5 — Task 1: Non-Mutating Candidate Template Preview Primitive

Date: 2026-09-11
Branch: `feature/phase5-design-expansion`
Starting SHA: `392d477fcd2e99c923937d70d4218ee258ac72ee`

## Files changed

- `apps/storefront_builder/services/preset_service.py` — extracted the existing pure "validate + prepare" phase of `apply_preset()` into a new private `_prepare_preset_application(draft, preset)`; added `ResolvedPresetCandidate` (frozen dataclass), `resolve_preset_candidate(draft, preset)`, `resolve_preset_candidate_by_key(draft, key)`.
- `apps/storefront_builder/services/render_service.py` — added `build_candidate_render_items(sections, store, page_context=None, *, global_appearance=None, store_appearance=None)`, a thin public wrapper around the existing private `_build_items_from_sections`; added an `if section.pk is not None:` guard to `_scoped_hero_slides`, `_scoped_banners`, and `_story_rail_context` (the last added after the independent review — see "Review findings and fix" below) so a candidate's unsaved sections fall straight to the existing store-wide fallback query instead of Django rejecting an unsaved-instance FK filter.
- `apps/storefront_builder/tests/test_preset_candidate_preview.py` — new, 11 focused tests.

No other files changed. No new URL route, no new view, no new template, no new migration, no new model.

## Design decision: what "resolve without writing" reuses, and what it deliberately does not touch

`apply_preset()` already ran in two phases: (1) validate/prepare appearance, header, footer and every page's section composition — entirely in-memory, no writes — then (2) write everything, inside one `@transaction.atomic` block. Phase (1) is now `_prepare_preset_application()`, called by both the unchanged (behavior-preserving) `apply_preset()` and the new `resolve_preset_candidate()`. This is a pure extract-method refactor: the moved code is byte-identical to what was inline before (verified by direct diff read and by the independent reviewer, see below); only the wrapping function boundary changed. **One validation implementation, not two.**

`resolve_preset_candidate()` deliberately does **not** resolve `preset.store_appearance` (the typed hero/product_view/card/badge/mega_menu/motion manifest) into a `ResolvedStoreAppearance`. That resolution is currently validate-and-persist in one call (`appearance_authority_service.apply_store_appearance_manifest` → `persist_store_appearance_manifest`), and splitting it into a non-writing variant was judged a materially larger, separate change than this task's minimal primitive needs. Every Ready Template's structural identity — which sections, in what order, with what per-section settings (including e.g. `hero_style`) — is already fully captured by the composition this primitive does resolve, which is sufficient to prove "the candidate reflects the template's declared DNA" per the task's own acceptance criteria (hero variant / header variant / footer-mobile-nav selection / composition-section selection). A future task may extend this once the manifest split is designed on its own merits, per the plan's own scope note for Task 1.

Rendering reuses the **existing** precedent already in `render_service.py`: `build_default_render_items()` already builds unsaved (`pk=None`) `StorefrontSection` instances for stores that have never published a Storefront V2, and passes them into the same private `_build_items_from_sections()` every other render path uses. `build_candidate_render_items()` is a thin, four-line public wrapper around that same private function — not a second renderer.

## RED evidence

Initial test run (before any production code changed), full traceback for one representative failure:

```
AttributeError: module 'apps.storefront_builder.services.preset_service' has no attribute 'resolve_preset_candidate'
```

9 of the 10 originally-written tests failed this way (the 10th, `test_apply_preset_still_writes_real_sections`, tests only pre-existing `apply_preset` behavior and correctly passed as a baseline anchor).

## GREEN evidence

```
$ python manage.py test apps.storefront_builder.tests.test_preset_candidate_preview -v 2
...
Ran 10 tests in 0.603s
OK
```

## Review findings and fix (CRITICAL → fixed → re-verified)

An independent, isolated reviewer (fresh agent, no shared context with the implementer) inspected the diff and found **one CRITICAL issue**: `_story_rail_context` in `render_service.py` does the exact same per-section-scoped FK query pattern as `_scoped_hero_slides`/`_scoped_banners` (its own docstring says so: "همان الگویِ hero_slides"), but the diff had only guarded the first two, not this third, structurally identical call site. The reviewer proved this was a real, reachable defect — not hypothetical — by identifying that `premium_boutique`, a real registered `is_ready_template=True` Ready Template, has a `story_rail` section in its Home composition, so `resolve_preset_candidate_by_key(draft, "premium_boutique")` followed by `build_candidate_render_items(...)` would raise `ValueError: Model instances passed to related filters must be saved.` None of the original 10 tests exercised a `story_rail`-bearing preset, so this slipped through.

**Fix applied:** the identical `if section.pk is not None:` guard added to `_story_rail_context`.

**RED confirmed for the fix itself** (not just trusted): the guard was temporarily removed and the new regression test re-run, reproducing the exact reviewer-reported traceback:

```
ValueError: Model instances passed to related filters must be saved.
  ... django/db/models/fields/related_lookups.py, get_normalized_value
```

The guard was then restored and the test re-run to GREEN. A new regression test, `test_candidate_renders_a_story_rail_bearing_template_without_crashing`, was added against the **real** `premium_boutique` preset (verified via a direct registry query that it currently resolves to the latest version and includes `story_rail` in its Home composition — not a synthetic fixture), so this exact defect class cannot silently regress.

**Re-verification after the fix:**

```
$ python manage.py test apps.storefront_builder.tests.test_preset_candidate_preview -v 2
...
Ran 11 tests in 0.693s
OK
```

No IMPORTANT findings. No other CRITICAL findings. The reviewer's independent architecture-gate cross-check (see below) matched the implementer's own, item for item.

## Focused tests (11, all passing)

| Test | Proves |
|---|---|
| `test_candidate_header_variant_matches_declared_recipe` | Candidate reflects the previewed template's declared header variant |
| `test_candidate_hero_style_setting_matches_declared_recipe` | Candidate reflects the declared hero style (section-level settings) |
| `test_candidate_renders_a_story_rail_bearing_template_without_crashing` | Regression for the CRITICAL finding above, against a real registered preset |
| `test_candidate_renders_through_the_shared_renderer` | Candidate sections render through the exact same `render_service` pipeline; sections remain unsaved throughout |
| `test_two_different_templates_resolve_to_visibly_different_candidates` | Two different templates produce visibly different header/hero DNA, not just "no crash" |
| `test_apply_preset_still_writes_real_sections` | Real (writing) Apply is unaffected by the refactor |
| `test_candidate_resolution_does_not_leak_into_a_subsequent_real_apply` | Candidate resolution never contaminates a later real Apply |
| `test_locked_section_conflict_raises_and_does_not_mutate` | Invalid candidate (locked-section conflict) fails through the same typed error `apply_preset` uses, non-mutating |
| `test_unknown_preset_key_raises_and_does_not_mutate` | Invalid candidate (unknown key) fails through the same typed error, non-mutating |
| `test_candidate_resolution_for_multiple_templates_still_leaves_draft_unchanged` | Draft unchanged across repeated candidate resolutions |
| `test_candidate_resolution_leaves_real_draft_byte_identical` | Full-field Draft snapshot (appearance/header/footer/provenance/baseline snapshot/sections/containers/version count/history count/published pointer) unchanged after one candidate resolution |

## Regression

Required by the plan, all green:

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

Required by this task's charter. Ran every test module in the repo referencing `switch_template_preserving_content`/`reset_storefront_to_baseline`/`TemplateBaselineVersionChangedError`:

```
$ python manage.py test apps.storefront_builder.tests.test_acceptance_batch2 \
    apps.storefront_builder.tests.test_phase1_appearance_authority \
    apps.storefront_builder.tests.test_r4_vertical_slice \
    apps.storefront_builder.tests.test_u10_ready_template_catalog \
    apps.storefront_builder.tests.test_u7_ready_template_baseline -v 1
Ran 312 tests ... FAILED (failures=1)
```

**One failure, classified as pre-existing, not caused by this task:**
`test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary` — asserts an R4 `appearance.update` mutation (a font patch, unrelated to Ready Template apply/preview) calls `layout_service.validate_appearance_config` exactly once; it is actually called twice. This code path (`r4_mutation_service.py`'s `appearance.update` handler) was never touched by this task's diff. **Reproduced identically in an isolated `git worktree` checked out at the starting SHA `392d477` before any Task-1 code existed** — same failure, same call count (2), same traceback shape. Confirmed pre-existing, not a regression from this task.

### Broader scan (own initiative, beyond the plan's minimum): two more pre-existing clusters found and classified

A broader scan across `apps.storefront_builder.tests.test_dark_digital_luxury_v2`, `test_dense_marketplace_beraito_v2`, `test_desktop_canvas_viewport`, `test_editorial_jewelry_saremi_v2` found 18 failures + 1 error — all stale characterization tests pinned to old recipe version numbers/compositions (e.g. asserting `preset.version == "2"` where the registry's current latest is `"3"`), unrelated to this task's diff (which never touches `a8_ready_templates.py`/`layout_preset_registry.py` content). **Reproduced identically (same 18 failures + 1 error) in the same isolated worktree at the starting SHA.** Confirmed pre-existing.

A full `apps.storefront_builder` suite run (2908 tests) was also started as an extra-thorough check beyond the plan's named scope; it ran for over 24 minutes without completing in this environment (this app's full suite is very large) but surfaced no additional failures beyond the two classified clusters above in everything it did cover. The plan's explicitly required regression scope (named suites + Task-8 safety tests) is fully green modulo the one classified pre-existing failure; this broader scan is supplementary evidence, not a blocking requirement.

## Django check / migration check / whitespace check

```
$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
No changes detected

$ git diff --check
(no output, exit 0)
```

No new migration. No system-check issue. No whitespace error.

## Draft non-mutation proof

`test_candidate_resolution_leaves_real_draft_byte_identical` and `test_candidate_resolution_for_multiple_templates_still_leaves_draft_unchanged` snapshot, before and after one-or-more candidate resolutions: `edit_revision`, `appearance_config`, `header_config`, `footer_config`, `template_provenance`, `template_baseline_snapshot`, the full ordered list of `(page_id, section_key, order, settings, is_locked)` for every section, the `StorefrontContainer` count, the `StorefrontLayoutVersion` count for the layout (no new version created), the `StorefrontEditHistoryEntry` count (no history entry created), and the `StorefrontLayout.published_version_id` (publish pointer untouched). All fields compare equal.

## Renderer authority proof

`build_candidate_render_items()` is a 10-line function whose entire body is one call into the existing private `_build_items_from_sections()` — the same function `build_page_render_items()` (Draft/Published) and `build_default_render_items()` (unpublished-store default content) already call. No new template resolution, no new context-building logic, no new render-item shape.

## Preset authority proof

`resolve_preset_candidate()`'s entire body is one call into `_prepare_preset_application()`, the same function `apply_preset()` calls. `resolve_preset_candidate_by_key()` resolves the key via the same `layout_preset_registry.get_layout_preset()` lookup `apply_preset_by_key()` uses, raising the same `UnknownPresetError` for an unknown key.

## No-persistence proof

`_PreparedPresetApplication` and `ResolvedPresetCandidate` are both plain `@dataclasses.dataclass(frozen=True)` — no Django `Model` base class, no `.save()` method, no cache/session/file write anywhere in either dataclass or the functions that build them. Grepped: no new migration, no new model, no `cache.set`/`request.session[...]`/file-write call anywhere in the diff.

## Reviewer verdict

Independent, isolated reviewer (separate agent, no shared context with the implementer). First pass: **FAIL**, 1 CRITICAL (see above), 0 IMPORTANT. Fix applied and re-verified by the implementer (RED reproduced for the fix itself, then GREEN); the reviewer's own architecture-gate cross-check (run before the fix, against the code that had the bug) already independently confirmed all 9 required labels PASS, since the bug was a crash in the render wrapper for one under-tested section type, not an architecture violation.

**Final state: CRITICAL = 0, IMPORTANT = 0.**

## Known limitations

- `resolve_preset_candidate()` does not resolve the `store_appearance` typed manifest (hero/product_view/card/badge/mega_menu/motion component selections) into a `ResolvedStoreAppearance` — see "Design decision" above. Section composition and per-section settings (including hero style) are resolved and proven sufficient for this task's DNA-reflection requirement; a future task should design the manifest-resolution split on its own merits before Random Mix/Design Lab (Task 14) needs it.
- No HTTP-layer consumer exists yet (no URL, no view) — intentionally out of scope per the task's own YAGNI instruction; Tasks 2 and 3 will build on this primitive.
- The full 2908-test `apps.storefront_builder` suite was not run to completion in this environment (>24 minutes, did not finish); the explicitly required regression scope is fully covered and green, and the partial full-suite scan found no failures beyond the two classified pre-existing clusters.
