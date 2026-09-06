# Phase 1 — Task 3 Evidence: Route Legacy Appearance/Header/Footer through the Authority Service

Task 3 of the Storefront Appearance Convergence Phase-1 plan
(`docs/superpowers/plans/2026-09-05-storefront-appearance-phase1-architecture-authority-implementation-plan.md`).

---

## TASK 2 REVIEW

- BASE SHA: `794507241619e9741b702ecce1e8d67df2c883ae`
- HEAD SHA: `28e48555b9225fd0dc01f418f6e6fde4e4170e01`
- Reviewed diff: the new `apps/storefront_builder/services/appearance_authority_service.py` + its unit tests.

Findings against the 8 required review dimensions:

1. **Scope discipline** — NONE. The service performs only appearance-state transformation; it imports the appearance validator (`layout_service.validate_appearance_config`) and the canonical persistence primitive only. No route/revision/render/business ownership.
2. **Preservation correctness** — NONE. `_merge_appearance_config` deep-copies current, validates the managed projection (`current managed ∪ patch`), and copies validated managed keys back — preserving every opaque/canonical key and NOT resetting unrelated managed fields (they are part of the validated input). Proven by opaque-probe + `layout_preset_key` tests.
3. **Partial-write safety** — NONE (design confirmed). Header/Footer/Nav helpers resolve+validate the typed key first (`_typed_key_for_selector` raises before any write), then persist a complete validated manifest via the single-`save` canonical path. Invalid manifest → raise before persistence.
4. **Mapping correctness** — NONE. Reuses `component_key_for_registry_reference(..., family_key=...)`; no duplicate selector maps; header/footer/bottom_nav translate correctly (tests confirm).
5. **Typed manifest correctness** — NONE. `apply_store_appearance_manifest` delegates to `persist_store_appearance_manifest`; targeted helpers preserve unrelated families.
6. **Ready-template primitive** — NONE (functional). Complete `preset.store_appearance` persisted LAST; appearance/header/footer merges are preservation-safe; no composition/provenance.
7. **Layering** — NONE. No authorization/revision/HTTP/history/render/media/business logic.
8. **Test quality** — NONE. Tests exercise public service behavior; invalid-input tests assert no partial persistence; opaque-key preservation is a behavioral probe.

- CRITICAL count: 0
- IMPORTANT count: 0
- MINOR count: 1
  - MINOR (carry-forward to Task 5): `apply_ready_template_appearance` issues multiple `save()` calls and is not itself wrapped in a transaction, so if a later step raised, the version could be partially updated. This is **by design** — the plan states the service must not own transaction/revision locking (plan line 40), and Task 5 will call this primitive inside `preset_service.apply_preset`, which is already `@transaction.atomic` (preset_service.py:274), providing the atomic boundary. No action in Task 2/3; noted for Task 5.

- REVIEW RESULT: **PASS** (no CRITICAL/IMPORTANT).

---

## TASK 3

- HEAD before: `28e48555b9225fd0dc01f418f6e6fde4e4170e01`
- Production file changed: `apps/storefront_builder/views.py` (only)
- Test files changed: none required — the Task-1 characterization tests already assert the RED→GREEN transitions. `test_r4_store_appearance_persistence.py` not extended (not needed).

### Legacy routes delegated (state transformation only)

| Route (view) | URL name | Authority helper used | Preserved as-is |
|---|---|---|---|
| Appearance (`storefront_appearance_editor`) | `dashboard:storefront-builder-appearance` | `apply_appearance_patch(version=draft, patch=config)` | form parsing, `validate_appearance_config`, error `messages.error` + redirect, success message, redirect, `@_record_edit_history("ویرایش ظاهر سایت")`, auth/store scoping, GET behavior. |
| Header (`storefront_header_editor`) | `dashboard:storefront-builder-header` | after saving full validated `header_config`, `apply_header_variant(version=draft, header_variant=config["header_variant"])` | full toggle/announcement/responsive/extra_blocks config, form error re-render (200), messages, redirect, history decorator, auth. |
| Footer (`storefront_footer_editor`) | `dashboard:storefront-builder-footer` | after saving full validated `footer_config`, `apply_footer_variant(version=draft, footer_variant=config["footer_variant"], mobile_nav_variant=config["mobile_nav_variant"])` | footer options, `mobile_nav_variant` legacy-preservation semantics, live FooterSettings ownership, form error re-render, messages, redirect, history decorator, auth. |

### Delegation design notes

- **Appearance:** the validated managed `config` is passed as the `patch` to `apply_appearance_patch`. The authority merge preserves the reserved `store_appearance` manifest and any opaque/canonical keys the legacy form never carries; the requested field still changes. Wholesale `appearance_config` replacement (the Task-1 defect) is removed.
- **Header/Footer:** the full validated config is still written first (so all content/toggle fields are preserved exactly as before, and live business/menu ownership is not moved into the authority service), then the authority helper synchronizes the typed manifest selection from the chosen variant. `persist_store_appearance_manifest` re-derives the legacy selector mirror from the typed manifest, so the mirror and the typed manifest agree after the edit.

### Legacy form/permission/history semantics preserved

- URL names, `@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)`, store scoping, GET behavior, POST redirect targets, `messages`, form validation contracts, and the `@_record_edit_history` decorators are all unchanged. Only the state-transformation lines changed.

### Task-1 RED → GREEN transitions (this task)

- `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_typed_manifest`: RED → GREEN
- `LegacyAppearancePreservationTests.test_legacy_appearance_edit_preserves_effective_hero_selection`: RED → GREEN
- `LegacyHeaderFooterSyncTests.test_legacy_header_edit_updates_effective_manifest_selection`: RED → GREEN
- `LegacyHeaderFooterSyncTests.test_legacy_footer_edit_updates_effective_manifest_selection`: RED → GREEN

### REDs intentionally remaining (Task 5 / Task 6 — NOT touched)

- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_replaces_all_declared_manifest_selections` (A02 — Task 5)
- `ReadyTemplateManifestFidelityTests.test_ready_template_apply_persists_declared_manifest_key` (A02 — Task 5)
- `LocalVariantPrecedenceTests.test_explicit_local_variant_wins_store_default` (explicit-local precedence — Task 6)

`LocalVariantPrecedenceTests.test_historical_unmarked_variant_keeps_legacy_inherited_behavior` remains GREEN (compatibility protected).

### Test results

Command:

```bash
/projects/rastisi5_phase1_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase1_appearance_authority --verbosity 2
```

Result: `Ran 18 tests ... FAILED (failures=3)` — 15 GREEN, 3 EXPECTED RED, 0 unexpected.

| Bucket | Count | Result |
|---|---|---|
| Authority service unit tests | 10 | GREEN |
| Legacy Appearance (2) + Header (1) + Footer (1) | 4 | GREEN (were RED) |
| Historical-unmarked compatibility | 1 | GREEN |
| Ready-Template fidelity (2) + explicit-local (1) | 3 | EXPECTED RED |

### Focused regression results

- **R4 persistence** (`test_r4_store_appearance_persistence`): `Ran 8 tests ... OK`.
- **Header/Footer/shell/views/g23** (`test_u2a_global_header_system`, `test_u2b_global_footer_system`, `test_page_shell`, `test_views`, `test_g23_builder_public_content_appearance`): `Ran 397 tests ... FAILED (failures=1, errors=1)`.
  - Both failures are `test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` (FAIL) and `...test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` (ERROR).
  - **Pre-existing and unrelated.** They assert V3 editor template markup (`sfb-v3-device-switcher`, `@click="fullscreen = !fullscreen"`, etc.). My Task-3 diff changes only three Python POST handlers and touches no template; `git diff` contains no fullscreen/topbar strings. Verified by running `FullscreenEditorTests` against the pre-Task-3 baseline commit `28e4855` in a throwaway detached worktree: identical `FAILED (failures=1, errors=1)`. Therefore not introduced or affected by Task 3.

### Django check / migration check

- `python manage.py check` → `System check identified no issues (0 silenced).`
- `python manage.py makemigrations --check --dry-run` → `No changes detected`.

### Explicit confirmations

- R4 changed: NO (`r4_mutation_service.py` untouched).
- preset_service changed: NO.
- renderer changed: NO (`render_service.py` untouched).
- business domain changed: NO.
- models/migrations/CSS/templates/JS: unchanged.
- Only `views.py` changed among production files; `git diff --check` clean.
