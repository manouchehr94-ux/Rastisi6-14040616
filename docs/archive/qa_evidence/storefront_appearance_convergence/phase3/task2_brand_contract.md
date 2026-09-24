# Task 2 — Brand canonical preservation and capability truth

- Starting HEAD: `597872c2edd2bd19c3d59b16812300aa64dd7a15`
- Branch: `feature/storefront-vertical-slice-phase3`

## Production files changed
- `apps/storefront_builder/section_registry.py` — V01: added `brand_carousel` to `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS`; `_with_appearance_overrides` now carries a TRUSTED, already-present `appearance_overrides.variant_explicit is True` marker through validation (stripped before `validate_appearance_overrides` so it is never accepted as client-writable, re-attached only when input already had True). Common fix for BOTH R4 and legacy validate paths.
- `apps/storefront_builder/services/r4_mutation_service.py` — V02: `_validate_brand_view_all_enable` preflight in `_apply_section_update_settings` AFTER clean + source-ownership, BEFORE `section.save`. Rejects `R4MutationError("view_all_unsupported")` only when raw patch explicitly sets `show_view_all` truthy AND resulting variant∉{grid,carousel} OR trusted current+resulting `destination` does not resolve to non-None URL (store-scoped `resolve_destination_setting`). Variant-only switch never rejected.
- `apps/storefront_builder/r4_views.py` — V02 inspector: READ-ONLY filtering drops `show_view_all` from basic/advanced fields when active variant/destination cannot render an actionable anchor (`resolve_active_variant` + destination resolve). Never mutates stored settings.
- `apps/storefront_builder/views.py` — legacy Brand branch: preserves dormant stored `show_view_all` when checkbox hidden (via `show_view_all_field_present` marker, avoiding the checkbox→False trap) and carries trusted persisted `appearance_overrides` into `raw` so marker survives the legacy path.
- `apps/storefront_builder/templates/.../partials/section_settings_form.html` — gate "مشاهده همه" checkbox to grid/carousel; emit `show_view_all_field_present`. Destination authoring left intact.
- `apps/storefront_builder/static/storefront_builder/r4_editor.js` — re-open inspector after a successful display_mode change so control visibility reflects server state (read-side only).

NOT changed (allowed but unnecessary): `settings_schema.py` (kept DB-free — no destination resolution in the pure cleaner), `variant_contract.py`, `section_inspector.html` (filtering done in the view).

## Test files changed
- `test_r4_settings_schema.py` (+5 V01 schema tests), `test_r4_mutation_api.py` (+`BrandCarouselV01V02MutationTests`, 15), `test_r4_inspector.py` (+`BrandCarouselV02InspectorFilteringTests`, 4), `test_views.py` (+2 legacy marker/dormant tests).

## RED → GREEN
- V01: Task-1 `Phase3BrandPreservationTests.test_variant_intent_survives_title_patch` was FAIL (`AssertionError: None is not true`) before edit → **now `ok`** (controller-run). Marker survives title patch; display_mode stays carousel.
- V02 (b) grid/carousel absent/none/invalid dest: RED-first (previously 200) → now 400 `view_all_unsupported`.
- V02 (c) beauty_tabs + valid dest: RED-first → 400.
- V02 (d) supporting→beauty_tabs variant-only switch: RED-first (legacy wiped dormant) → now 200, value+destination preserved dormant.
- V02 (a)/(e)/(f): (a) already-GREEN success; (e) restore effective anchor (context view_all_url non-None); (f) spoofed key → 400 invalid_settings, foreign-brand dest → 400, blank external URL → 400 fail-closed.
- Every rejected mutation asserts settings + edit_revision + history count UNCHANGED (`_assert_unchanged`).

## Commands + results (controller-run, authoritative)
- `test_r4_settings_schema.Phase3BrandPreservationTests`: Ran 6, OK (V01 closed).
- `test_r4_mutation_api test_render_service`: Ran 118, OK (skipped=1 pre-existing).
- `test_r4_settings_schema test_r4_inspector test_phase1_appearance_authority test_shared_capabilities`: Ran 157, OK.
- `test_views` (full module): Ran 215; FAILED(failures=1, errors=1) — EXACTLY the 2 known baseline exceptions (#2 fullscreen button, #3 fullscreen StopIteration). No new failures.
- `git diff --check`: clean.

## Counts
- No new unexplained failures. Known baseline exceptions unchanged. V01 closed. V02 enforced.

## Browser
Deferred to Task 3 (Brand end-to-end) / Task 7 (full matrix) per plan. Task 2 is contract-level.

## Scope audit
Only the 6 allowed production files + 4 allowed test files changed. No lifecycle/authority/domain/edit_history edits. No DB access in the pure schema cleaner. No migration. Confirmed via `git diff --name-only`.

## Review
Independent semantic_reviewer verdict recorded below / in ledger.

## Readiness for Task 3
Brand settings/resource/capability contract GREEN (V01 closed, V02 enforced) before any Collection work. READY.
