# Phase 1 Recipe Fidelity Evidence

Task 7 (verification / evidence consolidation) of the Storefront Appearance
Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`).

This is a **verification gate**: no production code was changed in Task 7. It
proves the Phase-1 recipe invariant still holds AFTER Task 6's explicit-local
variant precedence change, reusing the existing Task-5 fidelity tests (no
duplicate tests were added).

## Baseline

- Current HEAD: `47cf8a5655bf6e351620b3dd6c61cb95043893dc`
- Branch: `feature/storefront-appearance-convergence-phase1`
- Approved G2.3 code baseline `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` verified ancestor of HEAD (exit 0).
- Interpreter / framework: Python 3.12.13, Django 5.2.17.

## Representative recipes

All exist under these exact current registry keys (no substitution required):

- dense_marketplace (v3)
- premium_leather (v3)
- dark_digital (v3)
- warm_boutique (v3)
- anniversary_mosaic (v1)

## Proven invariant

> Ready Template Apply: **Declared Store Appearance selections = Persisted manifest selections = Effective resolved selections**, over the COMPLETE canonical family mapping.

This concerns **Store Appearance DNA** only.

## Existing tests reused (no duplication)

| Property | Test |
|---|---|
| 5 recipes declared=persisted=effective (from conflicting start) | `ReadyTemplateApplyAuthorityTests.test_representative_recipes_declared_persisted_effective` |
| Complete declared manifest replaces all families | `ReadyTemplateManifestFidelityTests.test_ready_template_apply_replaces_all_declared_manifest_selections` |
| Reserved `store_appearance` key persisted | `ReadyTemplateManifestFidelityTests.test_ready_template_apply_persists_declared_manifest_key` |
| Conflicting starting state does not leak | `ReadyTemplateApplyAuthorityTests.test_conflicting_starting_state_does_not_leak` |
| Idempotence | `ReadyTemplateApplyAuthorityTests.test_apply_same_recipe_twice_is_idempotent` |
| Legacy/canonical vs R4 apply convergence | `ReadyTemplateApplyAuthorityTests.test_legacy_and_r4_entry_paths_converge` |
| Atomic rollback (authority multi-save inside apply's txn) | `ReadyTemplateApplyAuthorityTests.test_apply_preset_failure_rolls_back_manifest_and_config` |
| Reset-to-baseline restores complete recipe manifest | `ReadyTemplateApplyAuthorityTests.test_reset_to_baseline_returns_to_applied_recipe_manifest` |
| All latest Ready Templates declare complete manifests | `AllReadyTemplatesDeclareCompleteManifestTests.test_all_latest_ready_templates_declare_valid_complete_manifest` |

No new tests were added in Task 7 — the existing Task-5 coverage is sufficient and remains GREEN after Task 6.

## Entry paths

- canonical preset service (`preset_service.apply_preset`)
- R4 template apply (`r4_mutation_service._apply_appearance_template` / `appearance.template.apply`)
- legacy/Ready Template application path where currently exercised (`apply_preset` is the shared canonical writer for both the gallery/legacy apply and R4)

## Fresh command evidence

### Primary fidelity tests

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  apps.storefront_builder.tests.test_a8_ready_template_contracts \
  --verbosity 1
```

Result: `Ran 42 tests ... OK`.

- TOTAL: 42
- GREEN: 42
- FAILURES: 0
- EXPECTED RED: 0 (Task 6 closed the final characterization RED)

### Preset / baseline / R4 regression

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_preset_service \
  apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_r4_mutation_api \
  --verbosity 1
```

Result: `Ran 103 tests ... OK`. No pre-existing failures encountered in these modules.

### Django integrity

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

## Conflicting starting state

PASS — `test_conflicting_starting_state_does_not_leak` proves that conflicting old selections for `hero`, `layout`, `product_view`, `card`, `badge` do not survive Apply when the recipe declares different values (full mapping compared).

## Idempotence

PASS — `test_apply_same_recipe_twice_is_idempotent`. Apply remains deterministic replacement/reset; no content-preserving Switch claimed.

## Atomic rollback

PASS — `test_apply_preset_failure_rolls_back_manifest_and_config` (failure injected after appearance/manifest writes inside `apply_preset`'s `@transaction.atomic` rolls back appearance/header/footer/manifest/composition).

## Reset / Baseline

PASS — `test_reset_to_baseline_returns_to_applied_recipe_manifest` (reset restores the complete applied recipe manifest, including `store_appearance`).

## All-latest declaration completeness

PASS — `test_all_latest_ready_templates_declare_valid_complete_manifest` validates every `list_ready_templates()` entry as a complete `StoreAppearanceManifest` whose selection keys equal the canonical `set(COMPONENT_FAMILIES)`.

## Task 6 non-regression

Task 6's explicit-local variant precedence did NOT regress recipe fidelity: the
above fidelity tests (which exercise Ready Template Apply and effective
resolution) all remain GREEN after Task 6, and the explicit-local marker only
changes render precedence for sections a merchant explicitly marked — never the
recipe-applied manifest DNA.

## Explicit non-goals

- content-preserving Switch NOT implemented
- browser / mobile certification NOT claimed
- visual uniqueness NOT claimed
- Page Override NOT implemented
- force-all Store policy NOT implemented
- "50 browser-certified stores" NOT claimed (this evidence is Store Appearance DNA fidelity only)
