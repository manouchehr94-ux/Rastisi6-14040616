# Task 1 — Appearance + Ready-Template authority convergence

## Result: PASS

## Scope

Fix `preset_service.apply_preset` so a non-Ready structural preset's header/footer overlay
updates the canonical Store Appearance manifest (the actual render authority) instead of only the
legacy `header_config`/`footer_config` compatibility mirror — closing audit defects (a)/(b)/(h)
(§8, concepts A/B/H) without creating a second appearance authority.

## RED investigation (evidence over claims — empirically verified, not assumed from the audit prose)

Before writing any test, the audit's claim ("non-Ready preset apply can silently erase the typed
`store_appearance` manifest") was checked directly against running code:

1. **The manifest key itself is NOT erased** by a non-Ready preset apply — `validate_appearance_config`
   already special-cases the opaque `STORE_APPEARANCE_CONFIG_KEY` (layout_service.py:473) and
   `effective_appearance_config()` includes it in the merged config passed through
   `preset_service._validate_appearance_overlay`. Verified via direct shell reproduction: applying
   `dense_marketplace` (Ready) then `clean_minimal` (non-Ready) left `store_appearance` present in
   `appearance_config`. This half of the audit's framing does not reproduce today — protected as an
   explicit regression-guard test (`test_non_ready_preset_apply_does_not_erase_store_appearance_key`).
2. **The real, reproducible, currently-live defect** is narrower and worse than "erased": applying a
   non-Ready preset's `header_variant`/`footer_variant` overlay updates the legacy
   `header_config.header_variant`/`footer_config.footer_variant` mirror fields, but never updates the
   typed manifest's `selections.header`/`selections.footer`. Confirmed via direct trace that
   `storefront_context_service.py` derives the actually-rendered `header_variant_template`/
   `footer_variant_template` from `render_service.resolve_store_appearance_render_state` (the
   manifest), **not** from `header_config`/`footer_config` directly. Empirical reproduction: apply
   `dense_marketplace` (header → `marketplace_search`), then apply `clean_minimal` (header overlay →
   `legacy_default`) — `draft.header_config.header_variant` becomes `legacy_default` (looks correct),
   but `resolve_store_appearance_render_state(draft).manifest.selections["header"]` still resolves to
   `header.marketplace_search.v1`. **A merchant who explicitly switches to a non-Ready preset's header
   sees no visible change on the actual storefront** — their choice is silently ignored by the real
   render authority.

## RED tests added (`apps/storefront_builder/tests/test_phase1_appearance_authority.py`)

New classes `NonReadyPresetHeaderFooterAuthorityTests` and
`ResetAppearanceSettingToBaselineAuthorityTests` (5 tests):

| Test | Pre-fix result | Property covered |
|---|---|---|
| `test_non_ready_preset_header_variant_updates_manifest_not_just_mirror` | **FAIL** (RED) | header mirror/manifest divergence |
| `test_non_ready_preset_footer_variant_updates_manifest_not_just_mirror` | **FAIL** (RED) | footer mirror/manifest divergence |
| `test_non_ready_preset_without_variant_overlay_preserves_manifest` | pass (characterization) | a toggle-only preset (`v5_golden_homepage`) must not disturb an unrelated manifest selection |
| `test_non_ready_preset_apply_does_not_erase_store_appearance_key` | pass (characterization) | Task-1 property 1 regression guard |
| `test_reset_appearance_setting_to_baseline_preserves_manifest` | pass (characterization) | Task-1 property 3 regression guard |

## Fix

`apps/storefront_builder/services/preset_service.py::apply_preset` — after writing the validated
legacy `header_config`/`footer_config` overlay (unchanged, still needed for non-selector toggle
fields such as `announcement_enabled`/`sticky`/`show_newsletter`), and only for **non-Ready**
presets (`not preset.store_appearance` — Ready Templates already get a full, authoritative manifest
declare immediately after, which supersedes this), route the explicit `header_variant`/
`footer_variant`/`mobile_nav_variant` overlay keys (when present in the preset's raw overlay dict)
through `appearance_authority_service.apply_header_variant`/`apply_footer_variant` — the same
canonical primitives the legacy Header/Footer editors and R4 already use (`test_legacy_and_r4_entry_paths_converge`,
`test_apply_header_variant_syncs_mirror_and_manifest`). No second appearance authority was created;
no new persistence surface was added — the fix is exactly "route through the existing canonical
primitive" per Ruling A.

## RED properties verified (Task 1's 5 required properties)

1. **Non-Ready preset apply cannot erase manifest** — held before the fix (characterization test,
   protected going forward).
2. **Ready Template transformation uses the canonical authority primitive** — already true
   (`apply_store_appearance_manifest` call for `preset.store_appearance`); untouched by this fix.
3. **Unrelated appearance state survives managed-field writes** — held for
   `reset_appearance_setting_to_baseline` before the fix (characterization test); the header/footer
   case was the actual gap, now fixed.
4. **Legacy+R4 Template Apply resolve through ONE orchestration** — already true: both
   `views.py`'s legacy entry and `r4_mutation_service._apply_appearance_template` call the same
   `preset_service.apply_preset` (confirmed by the pre-existing, still-passing
   `test_legacy_and_r4_entry_paths_converge`). Fixing `apply_preset` once therefore fixes the defect
   for both entry points simultaneously — no per-caller duplication was needed or added.
5. **Internal/seed use cannot become a second merchant-facing authority** — `golden_reference_service.py`
   calls the same `preset_service.apply_preset` (line 475), a documented one-off internal exception
   per Ruling G, not a separate authority; unaffected by this fix.

## Verification

- Targeted suite: `python manage.py test apps.storefront_builder.tests.test_phase1_appearance_authority`
  — **36 tests, OK** (31 pre-existing + 5 new, zero regressions, both new failing tests now pass).
- Full Phase-3 baseline Run A/B/C re-run verbatim:
  - Run A: **739 tests** (734 + 5 new), `FAILED (failures=1, skipped=1)` — the one failure is the
    exact same known pre-existing signature (`test_validate_appearance_config_is_the_validator_boundary`).
  - Run B: **121 tests**, `FAILED (failures=2, errors=1)` — identical to the Phase-3/Task-0 baseline.
  - Run C: **77 tests**, `OK` — identical to baseline.
- Additional check: the wider golden-reference "v2" contract suites
  (`test_warm_boutique_lalerokh_v2`, `test_premium_leather_shokolati_v2`, `test_dark_digital_luxury_v2`,
  `test_dense_marketplace_beraito_v2`, `test_editorial_jewelry_saremi_v2`, plus
  `test_r4_vertical_slice`/`test_acceptance_batch2`/`test_u7_ready_template_baseline`/
  `test_u10_ready_template_catalog`/`test_u9_advanced_settings`) show **252 tests, 28 failures + 1
  error both with and without this fix** (verified via `git stash`/`git stash pop` A-B comparison) —
  pre-existing, unrelated to this change (version-provenance drift in those fixture presets, not
  covered by the official Phase-3 baseline module list), not introduced by Task 1, and out of Task
  1's scope to fix.
- `python manage.py check`: System check identified no issues (0 silenced).

## STOP conditions checked

No second appearance/lifecycle engine was created. No cross-tenant exposure found. No migration
was needed (pure code-path fix inside an existing service). Not applicable: this task's own
Security STOP condition belongs to Task 2 (ResourceSource), not Task 1.
