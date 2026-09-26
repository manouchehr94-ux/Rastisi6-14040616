# Phase 1 — Task 4 Evidence: Share Appearance Authority across R4 Mutations

Task 4 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`).

---

## TASK 3 REVIEW

- BASE: `28e48555b9225fd0dc01f418f6e6fde4e4170e01`
- HEAD: `a3838c7affe03258769836bb710e0e9127bf0853`
- Reviewed diff: `apps/storefront_builder/views.py` (three legacy POST handlers delegated to the authority service) + docs.

Findings against the required checks:

1. Legacy Appearance route — form parsing/validation/permissions/store-scoping/history/redirect/messages unchanged; only the two save lines replaced with `apply_appearance_patch(version=draft, patch=config)`; `store_appearance`/opaque keys preserved. NONE.
2. Legacy Header route — full validated `header_config` still saved (toggles/announcement/content preserved); selector sync delegated to `apply_header_variant`; no duplicate map; invalid-form re-render unchanged; mirror↔manifest cannot diverge after success. NONE.
3. Legacy Footer route — full `footer_config` preserved (incl. `mobile_nav_variant` legacy-preservation semantics); footer+bottom_nav delegated to `apply_footer_variant`; live FooterSettings ownership untouched; unrelated families preserved. NONE.
4. Persistence/write behavior — no partial invalid state (validation precedes writes); `_record_edit_history` snapshots once before / records once after the whole view, so the (minor) extra `save()` inside the view is transparent to history and the final state is correct. NONE (correctness).
5. Scope — no R4/preset/renderer/settings-schema/models/migrations/templates/CSS/JS/business changes. NONE.
6. Tests — the Task-1 legacy RED→GREEN transition is genuinely caused by route delegation; tests not weakened; the remaining REDs (fidelity, explicit-local) were not hidden/skipped. NONE.

Known pre-existing failures: `test_views.FullscreenEditorTests` (2) were reproduced on pre-Task-3 commit `28e4855` and are unrelated to the Python state changes — not classified as Task-3 regressions.

- CRITICAL: 0
- IMPORTANT: 0
- MINOR: 1 — Header/Footer routes now issue a second `save()` (via `persist_store_appearance_manifest`) after the initial config save; final state correct, history unaffected; acceptable redundant write within scope.
- REVIEW RESULT: **PASS**

---

## TASK 4

- HEAD before: `a3838c7affe03258769836bb710e0e9127bf0853`
- Production file changed: `apps/storefront_builder/services/r4_mutation_service.py` (only)
- Test file changed: `apps/storefront_builder/tests/test_r4_store_appearance_mutations.py`
- Authority service NOT modified (no contract defect surfaced during wiring).

### Exact R4 command paths changed → authority helper used

| R4 handler | Command | Change | Authority helper |
|---|---|---|---|
| `_apply_appearance_update` | `appearance.update` | Replaced wholesale `draft.appearance_config = cleaned; draft.save(...)` with delegation; retained all R4 candidate-building (template-owned field precedence, palette reset) and the trailing motion/template `_sync_manifest_from_live_selectors`. | `apply_appearance_patch(version=draft, patch=cleaned)` |
| `_apply_header_update` | `header.update` | Save full validated `header_config`, then delegate manifest selection sync (replacing `_sync_manifest_from_live_selectors`). | `apply_header_variant(version=draft, header_variant=cleaned["header_variant"])` |
| `_apply_footer_update` | `footer.update` | Save full validated `footer_config`, then delegate manifest footer/bottom_nav sync. | `apply_footer_variant(version=draft, footer_variant=..., mobile_nav_variant=...)` |
| `_persist_manifest_selection_updates` (used by `appearance.component.update` and live-selector sync) | `appearance.component.update` | Routed the final manifest persistence through the authority wrapper; all surrounding no-op / `preserve_live_legacy_siblings` reconciliation logic unchanged. | `apply_store_appearance_manifest(version=draft, manifest=primitive)` |
| `_apply_appearance_manifest` | `appearance.manifest.apply` | Routed the final manifest persistence through the authority wrapper; no-op short-circuit unchanged. | `apply_store_appearance_manifest(version=draft, manifest=primitive)` |

### Duplicated transformation removed

- The direct `appearance_config` assignment in `_apply_appearance_update` (which, like the legacy form, would have dropped the reserved `store_appearance` key) is replaced by the preservation-aware authority patch.
- The two direct `persist_store_appearance_manifest(draft, primitive)` calls now go through `apply_store_appearance_manifest`, giving one canonical state-transformation path. The now-unused direct import was removed.

### Transaction / revision / history ownership preserved

- `apply_mutation` remains `@transaction.atomic` and owns `_lock_active_draft` (select_for_update + base-revision check + stale detection), the before/after history snapshot via `edit_history_service`, the semantic-no-op short-circuit, the `edit_revision += 1` increment, and the response envelope. None of this moved into the authority service. The authority service's multiple saves run safely inside this atomic boundary.

### A02 deliberately NOT closed in Task 4

- `_apply_appearance_template` (the `appearance.template.apply` path) is UNCHANGED — its partial four-family `_sync_manifest_from_live_selectors` and "A6 predates A8's complete Ready-Template DNA" comment remain. Ready-Template full-manifest fidelity is Task 5.

### Test results

Primary command:

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_phase1_appearance_authority \
  --verbosity 2
```

Result: `Ran 71 tests ... FAILED (failures=3)` — 68 GREEN, 3 EXPECTED RED, 0 unexpected.

- **Stale-write:** `test_stale_revision_rejects_appearance_mutation_without_write`, `test_stale_base_revision_is_rejected_and_nothing_changes` → GREEN.
- **Tenant isolation:** `test_foreign_draft_id_is_rejected_without_cross_store_access`, `test_foreign_store_section_id_is_rejected_without_leaking_settings` → GREEN.
- **Rollback:** `test_invalid_manifest_is_fully_rolled_back`, `test_unsupported_manifest_schema_version_is_rejected_without_write`, `test_template_version_mismatch_is_rejected_before_any_write` → GREEN.
- **Revision/history:** `test_versioned_ready_template_applies_as_one_semantic_mutation`, `test_complete_manifest_applies_atomically_with_one_revision_and_history_entry`, `test_valid_noop_does_not_increment_revision_or_history`, `test_undo_redo_restores_template_metadata_and_slot_identity`, `test_successful_mutation_writes_one_history_entry` → GREEN.
- **New R4 authority preservation tests (3):** `test_r4_appearance_patch_preserves_manifest_and_unrelated_keys`, `test_r4_header_update_keeps_manifest_and_unrelated_families`, `test_r4_footer_update_keeps_manifest_and_unrelated_families` → GREEN.
- **Existing legacy-selector sync tests:** `test_legacy_header_update_keeps_manifest_in_sync_and_later_component_change_preserves_it`, `test_legacy_footer_update_keeps_typed_manifest_in_sync`, `test_legacy_motion_update_keeps_typed_manifest_in_sync`, `test_preexisting_a5_stale_legacy_sibling_is_preserved_by_component_update`, `test_template_switch_persists_owned_fields_when_manifest_sync_is_noop` → GREEN.
- **Legacy views + authority-service tests** (from Tasks 2–3) → GREEN.

RED tests intentionally remaining (untouched):
- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_replaces_all_declared_manifest_selections` (A02 — Task 5)
- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_persists_declared_manifest_key` (A02 — Task 5)
- `LocalVariantPrecedenceTests.test_explicit_local_variant_wins_store_default` (explicit-local — Task 6)

### Contract / persistence regression

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_r4_store_appearance_contracts \
  apps.storefront_builder.tests.test_r4_store_appearance_registry \
  apps.storefront_builder.tests.test_r4_store_appearance_validation \
  apps.storefront_builder.tests.test_r4_store_appearance_compatibility \
  apps.storefront_builder.tests.test_r4_store_appearance_persistence --verbosity 1
```

Result: `Ran 50 tests ... OK` (GREEN).

### Django check / migration check

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

### Explicit confirmations

- NO preset_service change.
- NO renderer change.
- NO Legacy view change (Task-3's `views.py` unchanged in Task 4).
- NO model/migration.
- NO business-domain change.
- NO template-apply fidelity work (A02 remains open; `_apply_appearance_template` untouched).
- `settings_schema.py` unchanged; authority service unchanged.
- `git diff --check` clean; only the two allowed files changed.
