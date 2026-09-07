# Task 6 â€” shared contracts proven by Brand and Collection

## Authority and scope

- Starting SHA: `064b81a78bd51e2f7ac826b5fe9d72e042ca18ce`.
- Starting tree: `ae96f051e5d366fc818903e018367985777a512e`.
- Workspace: `D:\Projects\RastiSi5_Phase3_Codex`.
- Branch: `feature/storefront-vertical-slice-phase3`; initial worktree clean.
- Official Phase-2 baseline `e244619f395ebf0dbebc77d2033841e17f1cd099` verified ancestor.
- Task 3 Brand and Task 5 Collection gates are closed and accepted; Tasks 1â€“5 are not reopened. Task 7 is not started.
- Current Task-6 execution instruction controls scope and permits only the named backup push after verified, reviewed, clean commit.
- Runtime: Python 3.12.10, Django 5.2.16, Windows PowerShell.

## Result

PASS: the two-family contract exposed a real Collection marker-preservation defect, the bounded production correction is applied, and all focused plus required regression gates are GREEN. Production correction: YES.

## Browser evidence reuse

No shared production rendering change; final family browser evidence remains applicable.

Reuse final `task3_brand_gate.md`, `task5_collection_gate.md`, and `browser/r4-browser-result.json`, `browser/metrics.json`, `browser/db-restore-proof.json`. Existing Task-5 evidence includes both families: 45 Brand variant checks, 36 Collection variant checks, real Cart HTMX, and wrapper projection. The saved browser result has no request failures; saved database restore proof has matching hashes. These are reused results, not a fresh Task-6 browser run. Rerun both affected families only if production rendering/CSS/wrapper/Cart presentation changes.

## Controller verification

- `python manage.py check`: PASS, no issues (0 silenced).
- `python manage.py makemigrations --check --dry-run`: PASS, no changes detected.
- Required regression Command 1: 301 tests, 300 passed, 1 pre-existing skip; Command 2: 77 tests, 77 passed. Django check PASS; migration check PASS; git diff --check PASS.

## Review and scope audit

Pending fresh independent review after controller verification. No commit or backup push until the gate passes.

## Historical RED and production correction

Controller independently reproduced the sequence through `clean_section_schema_patch` for both families. `brand_carousel` preserves `appearance_overrides.variant_explicit=True` after variant, title, and source changes. `collection_tiles` sets the marker on the variant patch, then loses it on the title patch and still lacks it after the source patch. The stored `tile_style` and ordered `collection_ids` survive, so omitting the marker assertion would hide the binding preservation gap.

The spec sections 12â€“14 require preserving server-derived explicit variant intent across compatible edits; Task 6 names common marker-preservation checks. Root cause: `collection_tiles` is absent from `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS` in `section_registry.py`, unlike Brand. Production correction: YES. Root cause was Collection being absent from APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS. The bounded correction adds only collection_tiles to that existing allowlist. No renderer, lifecycle, authority, domain-service, CSS, fragment-engine or migration change was required.

## New behavioral coverage

- `Phase3SharedPilotPreservationTests`: 3 methods, each covers both pilots. Variant â†’ title â†’ ordered manual source retains variant, source, and explicit marker; unsupported new marker writes reject; compatible persisted background/spacing/responsive values survive, with dormant Brand View-all retained across beauty_tabs and Collection's distinct capabilities preserved.
- `SharedPilotRenderContractTests`: 2 methods, both pilots in each. Real render-service manual resource order and two independent same-family instances with different resources, titles, and variants.
- `CombinedPilotCartFragmentContractTests`: 3 methods. One published Cart composition with Brand beauty_tabs and Collection carousel in distinct containers/cells; real update/remove versus full detail; stable section/container/cell identity, independent ordered resources/settings, no editor handles, quantity/totals/OOB counters, stock-error toast/removal semantics, and a separate never-published store's fallback.
- Publish hygiene: one `setUpTestData` publish on a dedicated active test store. Only that test store's publish cache key is removed at setup/cleanup to prevent rolled-back primary-key cache residue; production limiter remains enabled and unchanged. No lifecycle code change.

## Focused results and fixture diagnosis

- `python manage.py test apps.storefront_builder.tests.test_r4_settings_schema.Phase3SharedPilotPreservationTests.test_variant_title_source_sequence_preserves_marker_variant_and_source_order --noinput -v2`: implementer ran 1 method, 1 Collection subtest failure (`AssertionError: None is not true`); Brand passed.
- Four remaining schema/render methods: implementer ran 4, all passed.
- `python manage.py test apps.cart.tests.test_cart_views.CombinedPilotCartFragmentContractTests --noinput -v2`: implementer ran 3, all passed.
- Intermediate fixture mistakes were diagnosed before correction: unsupported spacing `compact` normalized to `normal` (corrected to supported `small`); default PROVISIONING test stores failed public routing (corrected to ACTIVE). Neither was a production RED. No production rate-limit failure occurred in the final focused Cart run.

## Required regression commands (controller)

No `--keepdb` or settings override was used. Django created and destroyed isolated in-memory SQLite test databases; production database migrations were not applied.

Command 1: **301 tests, 300 passed, 0 failures/errors, 1 pre-existing skip**, exit 0.

```text
python manage.py test apps.storefront_builder.tests.test_r4_settings_schema apps.storefront_builder.tests.test_shared_capabilities apps.storefront_builder.tests.test_phase1_appearance_authority apps.storefront_builder.tests.test_phase2_lifecycle_safety apps.storefront_builder.tests.test_render_service apps.storefront_builder.tests.test_stable_section_identity apps.content.tests.test_phase2_media_reachability --noinput -v2
```

Command 2: **77 tests, 77 passed, 0 failures/errors/skips**, exit 0.

```text
python manage.py test apps.cart.tests.test_cart_views apps.cart.tests.test_cart_security apps.storefront_builder.tests.test_phase2_universal_renderer --noinput -v2
```

Command 2 includes all 3 new combined Cart methods; no rate-limit error. Existing commerce/security and universal renderer assertions pass unchanged.

## Independent Architect review

- Review target: 9f94fa8c5544720356e40e356d1ace6dcdd6775d.
- SPEC COMPLIANCE: PASS.
- CODE / TEST QUALITY: PASS.
- CRITICAL: 0.
- IMPORTANT: 0.
- MINOR: 0.
- Production correction is bounded to section_registry.py: collection_tiles joins the existing trusted appearance-override preservation allowlist.
- Browser: reused Task-3/Task-5 evidence because no renderer, CSS, wrapper or Cart presentation-context code changed. Full browser certification remains Task 7.