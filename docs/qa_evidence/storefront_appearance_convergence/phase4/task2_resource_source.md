# Task 2 — ResourceSource read/write + tenant ownership convergence

## Result: PASS

## Scope

Unify the two independently-maintained Store-ownership validators — legacy's
`views.py::_validate_universal_selection_ownership` (a per-model dict lookup) and R4's
`r4_mutation_service._validate_resource_source_ownership` (a `ResourceSource`-typed check that
no-opped for `category`) — into ONE shared, DB-backed implementation, while keeping
`resource_source.py` itself pure and DB-free (Ruling M).

## Characterization (evidence over claims)

Directly inspected both implementations before writing any fix:

| Family | Legacy checked | R4 checked |
|---|---|---|
| `product_section` manual (`product_ids`) | yes | yes |
| `product_section` auto single-reference (`source_id` for `data_source` ∈ {category, brand, collection}) | **no — real gap** | yes |
| `category_grid` manual (`category_ids`) | yes | n/a (no R4 schema for `category_grid` yet) |
| `brand_carousel` manual (`brand_ids`) | yes | yes |
| `collection_tiles` manual (`collection_ids`) | yes | yes |
| ResourceSource `kind="category"` (any caller) | n/a (legacy never built a `ResourceSource`) | **no-op, documented as "not exposed by the Task 10 UI yet"** |

## SECURITY STOP-condition investigation (required before treating this as routine)

Per the plan's Task 2 STOP condition and CLAUDE.md's tenant-isolation instruction, the
`product_section` gap above was investigated for real exploitability, not assumed safe or unsafe:

1. **Write side**: confirmed via direct reproduction (see RED tests below) that a staff user with
   `STOREFRONT_LAYOUT_MANAGE` could POST an arbitrary/foreign-Store `source_id` for
   `data_source="category"` (or brand/collection) and legacy would persist it — `views.py` never
   validated it.
2. **Read side**: confirmed via direct inspection of `section_data_service._resolve_category`/
   `_resolve_brand`/`_resolve_collection` that every one of them re-scopes by `store=store`
   independently at render time (`Category.objects.get(pk=source_id, store=store, ...)`) — a
   foreign-Store id resolves to `Category.DoesNotExist` and the section renders as empty, never
   leaking another Store's data.
3. **Conclusion: NOT a live, exploitable cross-tenant data-exposure vulnerability** — the
   independent read-time re-scoping is a real (if accidental) defense-in-depth layer. This is the
   "narrow but real" architectural gap the audit's §8/§9 concept G already characterized (write/read
   semantics independently re-derived), not a security incident. **No SECURITY STOP was triggered**;
   proceeding as the routine unification Task 2 already scopes. This finding and its reasoning are
   recorded here per the plan's explicit instruction to document the investigation either way.

## RED tests added

`apps/storefront_builder/tests/test_phase4_task2_resource_source_ownership.py` (10 tests):

| Test | Pre-fix result |
|---|---|
| `test_foreign_category_source_id_is_rejected` | **FAIL (302, silently accepted)** |
| `test_nonexistent_category_source_id_is_rejected` | **FAIL (302, silently accepted)** |
| `test_own_category_source_id_is_accepted` | pass (characterization) |
| `test_foreign_category_ids_still_rejected` (category_grid manual) | pass (regression guard for already-correct behavior) |
| `test_own_category_ids_still_accepted` | pass (regression guard) |
| `test_legacy_and_r4_call_the_same_shared_function` | new (proves unification) |
| `test_category_kind_is_no_longer_a_silent_noop` | new (proves the R4-side no-op is closed) |
| `test_manual_owned_category_id_passes` / `test_manual_foreign_category_id_rejected` / `test_auto_all_active_is_a_true_noop` | new unit coverage for the previously-no-op `category` kind |

RED confirmed empirically (not assumed): stashed the production fix, re-ran
`LegacyProductSectionSingleReferenceOwnershipTests` — both foreign-id and nonexistent-id tests
failed exactly as predicted (`302 != 200`, i.e. silently accepted), then restored the fix.

## Fix

1. **`resource_source.py`** (still DB-free — no Django model import added): added
   `category_resource_source_from_settings`/`category_resource_source_to_legacy_patch` (mirroring
   the existing brand/collection manual-ids-or-`all_active` pattern) and registered `category_grid`
   in `_SECTION_ADAPTERS` — `category_grid` now has a typed `ResourceSource` projection like the
   other 3 universal-selection sections.
2. **`services/section_data_service.py`** (the existing, already-documented home for this
   responsibility — its own module docstring already stated "Store ownership for `source_id`/
   `product_ids` is checked here, not in `section_registry.py`"): added the ONE shared, DB-backed
   `validate_resource_source_ownership(*, store, source)` function, covering all 4 kinds
   (product/brand/collection/category) × both modes, including the previously-uncovered
   `product` auto single-reference case and the previously-no-op `category` kind.
3. **`services/r4_mutation_service.py`**: removed the local `_require_owned_resource`/
   `_validate_resource_source_ownership` duplicate implementations; `_validate_resource_source_ownership`
   is now a thin delegation to `section_data_service.validate_resource_source_ownership`, translating
   its error into R4's existing `R4MutationError("invalid_resource_ownership")` external contract —
   zero behavior change for R4's existing schema-enabled families.
4. **`views.py::_validate_universal_selection_ownership`**: rewritten to project `cleaned` into a
   `ResourceSource` via `resource_source.resource_source_from_section_settings` and delegate to the
   same shared function, raising the same Persian error message on rejection (`"یک یا چند مورد
   انتخاب‌شده متعلق به این فروشگاه نیست"`) for zero user-facing behavior change on the paths that
   already worked, while closing the `source_id` gap above.

No new ResourceSource persistence was added; no generic cross-family business-query abstraction was
introduced — the fix reuses each kind's exact existing Store-scoped query pattern
(`searchable_products(store)` for product, plain `filter(store=store, pk__in=...)` for the other
three), matching Ruling M's "no generic abstraction" constraint.

## Verification

- New suite: `test_phase4_task2_resource_source_ownership` — **10/10 pass**.
- `test_universal_selection_pattern` — updated one brittle source-text-grep assertion (checked for
  the OLD inline implementation's literal substrings) to check for the new shared-function call
  sites instead, preserving its actual regression-guard intent; **10/10 pass**.
- Full regression sweep: `test_universal_selection_pattern`, `test_r4_resource_source`,
  `test_r4_resource_picker`, `test_r4_mutation_api`, `test_phase35_reference_editable_backgrounds`
  — **207/207 pass**, zero regressions (in particular R4's existing "unrelated field edit must not
  fail on dormant old resource state" guard in `test_r4_resource_picker` — untouched by this
  refactor — still passes).
- Full Phase-3 baseline Run A/B/C re-run verbatim:
  - Run A: **740 tests** (734 baseline + 6 carried forward from Task 1's `test_phase1_appearance_authority`
    additions), `FAILED (failures=1, skipped=1)` — identical known pre-existing signature.
  - Run B: **121 tests**, `FAILED (failures=2, errors=1)` — identical to baseline.
  - Run C: **77 tests**, `OK` — identical to baseline.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes detected (no
  schema change — this task is pure code-path unification, consistent with the plan's "no new
  ResourceSource persistence" constraint). `git diff --check`: clean.

## STOP conditions checked

No cross-tenant exposure was found exploitable (investigated explicitly above — negative result).
No second ResourceSource persistence/abstraction was created. `resource_source.py` remains free of
any Django model import (verified: no new imports were added to it beyond `dataclasses`/
`types`/`typing`, already present).
