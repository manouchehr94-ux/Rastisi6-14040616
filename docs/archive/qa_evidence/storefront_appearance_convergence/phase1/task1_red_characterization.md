# Phase 1 — Task 1 RED Characterization Evidence

Task 1 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`),
"Characterize the Three Phase-1 Authority Failures".

**This task adds TESTS ONLY. No production application code was modified.**
Task 1 success = "the intended defects are accurately characterized." It is
explicitly NOT a claim that the suite is GREEN — the intended defects are RED.

## Branch / baseline

- Branch: `feature/storefront-appearance-convergence-phase1`
- HEAD before the test commit: `65789d4bc74d8a32716c7bb8c718a8112a171aba`
- Approved G2.3 code baseline ancestor: `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` (verified ancestor of HEAD, exit 0)
- Interpreter / framework: Python 3.12.13, Django 5.2.17 (venv `/projects/rastisi5_phase1_venv`, outside the worktree)

## File added

- `apps/storefront_builder/tests/test_phase1_appearance_authority.py`

The tests subclass the existing `StorefrontBuilderViewsTestCase`
(`apps/storefront_builder/tests/test_views.py`) for the store + OWNER
membership + logged-in dashboard client with `STOREFRONT_LAYOUT_MANAGE`, and
reuse the established `_manifest_with(**selections)` fixture and
`persist_store_appearance_manifest` / `resolve_store_appearance_render_state`
public APIs used across the rest of the manifest suite. No parallel/fake
architecture was constructed; every test exercises real routes/services.

## Exact tests added

| # | Group | Test | Intent |
|---|---|---|---|
| 1 | A | `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_typed_manifest` | Legacy Appearance edit (font only) must preserve the persisted `store_appearance` manifest key. |
| 2 | A | `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_effective_hero_selection` | Same invariant at the effective-resolution level (Hero + Card selections must survive). |
| 3 | B | `LegacyHeaderFooterSyncTests.test_legacy_header_edit_updates_effective_manifest_selection` | Legacy Header selector edit must make the effective manifest header follow it; unrelated selections preserved. |
| 4 | B | `LegacyHeaderFooterSyncTests.test_legacy_footer_edit_updates_effective_manifest_selection` | Legacy Footer selector edit must make the effective manifest footer follow it; unrelated selections preserved. |
| 5 | C | `ReadyTemplateManifestFidelityTests.test_ready_template_apply_replaces_all_declared_manifest_selections` | After `apply_preset`, effective manifest selections == preset's COMPLETE declared selections (A02). |
| 6 | C | `ReadyTemplateManifestFidelityTests.test_ready_template_apply_persists_declared_manifest_key` | After `apply_preset`, the reserved `store_appearance` key holds the declared selections (A02, persistence view). |
| 7 | D1 | `LocalVariantPrecedenceTests.test_historical_unmarked_variant_keeps_legacy_inherited_behavior` | Protects current output: a non-default Store manifest variant wins for an unmarked historical section. |
| 8 | D2 | `LocalVariantPrecedenceTests.test_explicit_local_variant_wins_store_default` | Desired: an explicit-local marked section variant wins over the inherited Store default. |

## Exact command

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  --verbosity 2
```

## Result summary

```text
Ran 8 tests in ~3.0s
FAILED (failures=7)
System check identified no issues (0 silenced).
```

- Total tests: 8
- Expected GREEN: 1
- Expected RED: 7
- Unexpected failures / errors: 0

## Per-test result and classification

| # | Test | Result | Classification |
|---|---|---|---|
| 1 | `test_legacy_appearance_edit_preserves_typed_manifest` | FAIL | EXPECTED RED |
| 2 | `test_legacy_appearance_edit_preserves_effective_hero_selection` | FAIL | EXPECTED RED |
| 3 | `test_legacy_header_edit_updates_effective_manifest_selection` | FAIL | EXPECTED RED |
| 4 | `test_legacy_footer_edit_updates_effective_manifest_selection` | FAIL | EXPECTED RED |
| 5 | `test_ready_template_apply_replaces_all_declared_manifest_selections` | FAIL | EXPECTED RED |
| 6 | `test_ready_template_apply_persists_declared_manifest_key` | FAIL | EXPECTED RED |
| 7 | `test_historical_unmarked_variant_keeps_legacy_inherited_behavior` | ok | EXPECTED GREEN |
| 8 | `test_explicit_local_variant_wins_store_default` | FAIL | EXPECTED RED |

This matches the plan's expected shape exactly:
legacy Appearance preservation → RED; legacy Header/Footer sync → RED;
Ready Template complete manifest fidelity → RED; historical unmarked
precedence → GREEN; explicit-local precedence → RED.

## Root cause location for each reproduced failure

### Group A — legacy Appearance drops the typed manifest (tests 1, 2)

- `apps/storefront_builder/views.py` — `storefront_appearance_editor` (view at
  ~line 2248). It builds a `raw` dict from `request.POST` / current config for
  a fixed set of KNOWN appearance keys only (template/palette/font/radius/
  motion/type_scale/colors/… ) and then does
  `config = layout_service.validate_appearance_config(raw)` →
  `draft.appearance_config = config`. The reserved `store_appearance` key is
  never carried into `raw`.
- `apps/storefront_builder/services/layout_service.py` —
  `validate_appearance_config` starts from `dict(APPEARANCE_CONFIG_DEFAULTS)`
  and copies only known keys, so the previously persisted `store_appearance`
  manifest is discarded on save.
- Observed: after the edit, `appearance_config["store_appearance"]` is `None`
  (test 1), and the effective resolved Hero selection reverts to
  `hero.legacy_default.v1` instead of the persisted `hero.split.v1` (test 2,
  via `load_store_appearance_manifest` → `_legacy_manifest` fallback in
  `apps/storefront_builder/storefront_appearance/persistence.py`).

### Group B — legacy selector edit diverges from the typed manifest (tests 3, 4)

- `apps/storefront_builder/views.py` — `storefront_header_editor` (~2497) and
  `storefront_footer_editor` (~2537) write only `header_config.header_variant`
  / `footer_config.footer_variant` (+ `mobile_nav_variant`). They never
  synchronize the reserved `store_appearance` manifest.
- `apps/storefront_builder/storefront_appearance/persistence.py` —
  `load_store_appearance_manifest` returns the STORED manifest when the
  `store_appearance` key exists, and only derives from legacy selectors
  (`_legacy_manifest`) when it is absent. Because the Arrange step persists a
  manifest first, the subsequent legacy Header/Footer edit updates the legacy
  mirror but the canonical read path still returns the stale stored selection.
- Observed: after a valid (302) Header edit to `dark_tech`, the effective
  manifest header is still `header.legacy_default.v1` (test 3); after a valid
  (302) Footer edit to `marketplace_dense`, the effective manifest footer is
  still `footer.legacy_default.v1` (test 4). Legacy mirror and typed manifest
  diverge — the P1 gap.
- Note on payload fidelity: the real forms have required constraints
  (`validate_header_config` rejects `show_cart=False`; `validate_footer_config`
  rejects an all-empty footer). The tests send faithful valid payloads
  (`show_cart=on` for header; `show_about=on`, `show_copyright=on` for footer)
  so both POSTs genuinely succeed with 302 and the divergence is measured on a
  real successful edit — not on a rejected request.

### Group C — Ready Template Apply ignores the declared manifest (A02) (tests 5, 6)

- `apps/storefront_builder/services/preset_service.py` — `apply_preset(draft,
  preset, *, _record_baseline_snapshot=True)` writes appearance/palette/
  header/footer/provenance and rebuilds page composition, but contains **zero**
  references to `store_appearance` (`grep -c store_appearance
  preset_service.py` → 0). `preset.store_appearance` is never persisted via
  `persist_store_appearance_manifest`.
- Consequence: a Draft seeded with conflicting selections keeps them after
  Apply. The recipe used is `dense_marketplace` (latest version 3), whose
  declared selections are non-default across 8 families:
  `header.marketplace_search.v1`, `hero.promo_bento.v1`,
  `layout.dense_five.v1`, `product_view.dense_grid.v1`,
  `card.marketplace_price.v1`, `badge.sale.v1`, `motion.dynamic.v1`,
  `footer.marketplace_columns.v1` (+ `bottom_nav.five_item.v1`,
  `mega_menu.none.v1`). Tests compare the COMPLETE declared selection mapping
  (not just header/footer/bottom_nav/motion), so A02 is exposed on the
  hero/layout/product_view/card families that the partial legacy sync never
  touches.
- Observed: effective/persisted selections after Apply remain the seeded
  conflicting/legacy-default values, not the declared recipe selections.

### Group D2 — explicit-local variant precedence not yet honored (test 8)

- `apps/storefront_builder/services/render_service.py` —
  `_build_items_from_sections` (~714-761): when a non-default manifest supplies
  a section variant (`store_appearance_section_variant_for`), it sets
  `effective_settings[variant_setting_key] = appearance_variant.key` and uses
  `active_variant = appearance_variant or resolve_active_variant(...)`
  unconditionally. There is no check for
  `settings["appearance_overrides"]["variant_explicit"]`.
- Observed: with the marker present and a non-default Store Hero
  (`hero.split.v1`), the rendered `active_variant.key` is still `split`
  (Store default) rather than the local `overlay`. The marker behavior is NOT
  implemented (correct for Task 1 — Task 6 implements it).

## Expected-GREEN result (test 7)

- `test_historical_unmarked_variant_keeps_legacy_inherited_behavior` PASSES on
  the baseline: an unmarked historical Hero row with local `hero_style=overlay`
  plus a non-default Store manifest `hero.split.v1` renders `active_variant.key
  == "split"`. This is the current inherited-global behavior and must be
  protected from an accidental output flip when Task 6 introduces the explicit
  marker.

## Plan assumptions NOT reproduced / clarified

- **Preset function signature.** The plan's illustrative test used
  `apply_preset(version=version, preset=preset)`. The real signature is
  positional: `apply_preset(draft, preset, *, _record_baseline_snapshot=True)`
  (`preset_service.py`). The tests use the real positional call.
- **`dense_marketplace` Hero is not itself non-default in every version.** The
  plan text implied the chosen recipe has a non-default Hero. The latest
  registered `dense_marketplace` (v3) DOES declare a non-default Hero
  (`hero.promo_bento.v1`); regardless, the tests assert the COMPLETE declared
  selection mapping, so A02 is exercised across all declared families and does
  not depend on any single family's value.
- **Manifest primitive access.** `StoreAppearanceManifest` has no `.to_dict()`;
  the suite's canonical primitive conversion is
  `validation.manifest_to_primitive` (used via the shared `_manifest_with`
  helper). Effective selections are read through
  `resolve_store_appearance_render_state(version).manifest.selections`.
- **Group B legacy forms have required fields.** The legacy Header/Footer forms
  are plain function views (no Django `Form`) with hard validation rules
  (`show_cart` must stay on; footer cannot be fully empty). This is a real
  form contract, not a defect, and the tests satisfy it with faithful payloads.
- No supposed-defect test unexpectedly PASSED; no unrelated exceptions occurred.

## Production application code unchanged — confirmation

- `git status --short` shows only the new untracked test file
  (`apps/storefront_builder/tests/test_phase1_appearance_authority.py`) plus
  this evidence document.
- No production Python, template, CSS, JS, model, migration, requirements, or
  settings file was created or modified.
- `git diff --check` is clean.
