# Phase 1 — Task 2 Evidence: Preservation-Aware Appearance Authority Service

Task 2 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`),
"Introduce the Preservation-Aware Appearance Authority Service".

**Scope:** build ONE focused transformation service + its unit tests. NO route
wiring, NO renderer change, NO preset_service wiring, NO migration, NO
business-domain change. Those are later tasks (3–6).

## Branch / baseline

- Branch: `feature/storefront-appearance-convergence-phase1`
- HEAD before this task's commit: `794507241619e9741b702ecce1e8d67df2c883ae` (Task-1 commit)
- G2.3 baseline `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` verified ancestor of HEAD (exit 0)
- Interpreter / framework: Python 3.12.13, Django 5.2.17 (venv `/projects/rastisi5_phase1_venv`)

## Files changed

| File | Type | Note |
|---|---|---|
| `apps/storefront_builder/services/appearance_authority_service.py` | NEW production | The canonical transformation service. |
| `apps/storefront_builder/tests/test_phase1_appearance_authority.py` | MODIFIED test | Added `AppearanceAuthorityServiceTests` (10 unit tests) + one import line. |
| `docs/qa_evidence/storefront_appearance_convergence/phase1/task2_authority_service.md` | NEW doc | This evidence. |

`apps/storefront_builder/storefront_appearance/persistence.py` was **NOT**
modified — every primitive the service needs is already public, so no change
was genuinely required (per the plan's "leave it untouched" instruction).

## Authority service public functions

```python
apply_appearance_patch(*, version, patch)
apply_header_variant(*, version, header_variant)
apply_footer_variant(*, version, footer_variant=None, mobile_nav_variant=None)
apply_store_appearance_manifest(*, version, manifest)
apply_ready_template_appearance(*, version, preset)
```

The module owns ONLY preservation-aware transformation of Appearance state. It
does not own HTTP authorization, route behavior, Draft locking, `edit_revision`
/ stale-write detection, history snapshots, rendering, business-domain logic,
media lifetime, or Template composition replacement.

## Existing primitives reused (no duplication)

| Authority function | Delegates to existing primitive |
|---|---|
| `apply_appearance_patch` | `layout_service.validate_appearance_config` (managed-key validator) + `models.APPEARANCE_CONFIG_DEFAULTS` (the managed-key set). |
| `apply_store_appearance_manifest` | `storefront_appearance.persistence.persist_store_appearance_manifest` (validates, mirrors header/footer/nav/motion, single atomic save, Draft-only guard). |
| `apply_header_variant` / `apply_footer_variant` | `persistence.component_key_for_registry_reference` (inverse legacy→typed adapter) + `persistence.load_store_appearance_manifest` + `validation.manifest_to_primitive` + `persist_store_appearance_manifest`. |
| `apply_ready_template_appearance` | composes `apply_appearance_patch` + `apply_store_appearance_manifest`; uses `preset.appearance/header/footer/store_appearance`. |

No component-key or selector map is re-declared in the service. Legacy selector
values are translated to typed component keys exclusively through the existing
`component_key_for_registry_reference` adapter, using the same registry-reference
prefixes the persistence layer itself uses
(`global_region:header:`, `global_region:footer:`, `global_region:mobile_bottom_nav:`).

## How opaque canonical keys are preserved

`layout_service.validate_appearance_config` intentionally rebuilds ONLY the
managed keys (it starts from `dict(APPEARANCE_CONFIG_DEFAULTS)` and copies known
keys), which is exactly why the legacy Appearance editor drops
`store_appearance` (Task-1 finding A). The service therefore does NOT assign the
validator's output directly. Instead `_merge_appearance_config`:

1. builds a managed input = current managed values overlaid with the incoming patch;
2. validates it via `validate_appearance_config` (so an invalid managed field still fails, e.g. an unknown `font`);
3. copies the validated managed keys back onto a deep copy of the CURRENT config.

Keys outside `APPEARANCE_CONFIG_DEFAULTS` — the reserved `store_appearance`
typed manifest and any other opaque/canonical/provenance state — are never
touched. This is generic (it is NOT a `store_appearance` special-case): a probe
test seeds an arbitrary `__opaque_canonical_probe__` key and asserts it survives.

## How header/footer/nav mappings are reused rather than duplicated

`apply_header_variant` / `apply_footer_variant` read the version's current
effective manifest (`load_store_appearance_manifest`), replace only the target
family's selection with the typed component key resolved via
`component_key_for_registry_reference(..., family_key=...)`, and persist the
complete manifest via `persist_store_appearance_manifest`. Because persistence
re-derives and writes the legacy `header_config.header_variant` /
`footer_config.footer_variant` / `footer_config.mobile_nav_variant` mirrors from
the typed manifest in one validated atomic save, the legacy mirror and the typed
manifest cannot diverge, and unrelated families are preserved. Invalid selectors
raise `InvalidStoreAppearanceContract` before any write (no partial persistence).

## Ready Template appearance primitive (built, NOT wired)

`apply_ready_template_appearance` applies (1) the preset's ordinary appearance
overlay (preservation-aware), (2) merges preset header/footer config so unrelated
toggles/content survive, then (3) persists the COMPLETE declared
`preset.store_appearance` manifest LAST — so the typed manifest's compatibility
mirrors are the authoritative selector-sync step and cannot be overwritten by a
stale legacy overlay written earlier. It is unit-tested here but is **NOT**
called from `preset_service` — that wiring is Task 5.

## Service tests — RED before / GREEN after

New class `AppearanceAuthorityServiceTests` (10 tests):

- `test_apply_appearance_patch_preserves_typed_manifest`
- `test_apply_appearance_patch_preserves_unrelated_opaque_keys`
- `test_apply_appearance_patch_rejects_invalid_managed_field`
- `test_apply_header_variant_syncs_mirror_and_manifest`
- `test_apply_footer_variant_syncs_mirror_and_manifest`
- `test_apply_footer_variant_mobile_nav_syncs_bottom_nav`
- `test_apply_header_variant_rejects_unknown_selector`
- `test_apply_store_appearance_manifest_persists_validated_manifest`
- `test_apply_store_appearance_manifest_rejects_invalid_manifest`
- `test_apply_ready_template_appearance_persists_declared_manifest`

Command:

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  --verbosity 2
```

- **RED before:** running the new class before implementation produced
  `ImportError: cannot import name 'appearance_authority_service'` — the service
  did not exist (expected RED).
- **GREEN after:** all 10 new service tests pass (`Ran 10 tests ... OK`).

Full module run after Task 2: `Ran 18 tests ... FAILED (failures=7)` — this is
the intended state:

| Bucket | Count | Result | Classification |
|---|---|---|---|
| New authority service tests | 10 | ok | NEW SERVICE TEST GREEN |
| Task-1 D1 historical-unmarked precedence | 1 | ok | EXPECTED COMPATIBILITY GREEN |
| Task-1 Group A (2), Group B (2), Group C (2), D2 (1) | 7 | FAIL | EXPECTED OLD RED |
| Unexpected | 0 | — | none |

The 7 Task-1 characterization tests intentionally remain RED because Task 2
does not wire the legacy views, R4, preset_service, or change renderer
precedence:

- `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_typed_manifest`
- `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_effective_hero_selection`
- `LegacyHeaderFooterSyncTests.test_legacy_header_edit_updates_effective_manifest_selection`
- `LegacyHeaderFooterSyncTests.test_legacy_footer_edit_updates_effective_manifest_selection`
- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_replaces_all_declared_manifest_selections`
- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_persists_declared_manifest_key`
- `LocalVariantPrecedenceTests.test_explicit_local_variant_wins_store_default`

## Existing contract regression

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_r4_store_appearance_contracts \
  apps.storefront_builder.tests.test_r4_store_appearance_registry \
  apps.storefront_builder.tests.test_r4_store_appearance_validation \
  apps.storefront_builder.tests.test_r4_store_appearance_compatibility \
  --verbosity 1
```

Result: `Ran 42 tests ... OK` (GREEN).

## Django check / migration check

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

## Explicit confirmations

- NO route wiring (`views.py` unchanged).
- NO renderer change (`render_service.py` unchanged).
- NO preset_service wiring (`preset_service.py` unchanged).
- NO R4 wiring (`r4_mutation_service.py` unchanged).
- NO settings-schema change (`settings_schema.py` unchanged).
- NO migration created (`makemigrations --check` clean).
- NO business-domain change (only the new appearance authority service + tests).
- `persistence.py` left untouched (no real change required).
- `git diff --check` clean; only the allowed files changed.
