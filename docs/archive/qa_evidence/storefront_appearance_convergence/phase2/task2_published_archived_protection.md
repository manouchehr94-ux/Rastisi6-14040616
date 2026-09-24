# Phase 2 — Task 2: Published / Archived / Cross-store Mutation Protection (gap L05)

**Branch:** `feature/storefront-lifecycle-safety-phase2`
**Worktree:** `/projects/rastisi5_phase2`
**Task HEAD (pre-commit):** `cd33ba40bb6c5074cb344bca57935a418a2500bd` (Task 1 commit)

## Goal

Gap **L05** (P2): prove by negative test that EVERY active Appearance/Builder-owned
mutation family cannot mutate (a) a **PUBLISHED** version, (b) an **ARCHIVED**
version, or (c) a **FOREIGN** store's version. Add a production guard ONLY if a
path is found that CAN mutate a non-Draft/foreign version.

## Production change

**NONE.** Every mutation family is already safe by the existing scoping pattern.
No path was found that can mutate a Published/Archived/foreign version, so no
guard was added. This task adds **tests only**.

### Why no guard is needed (verified in code at Task-1 HEAD)

Two structural safety mechanisms cover every family:

1. **Draft+store scoping helpers** — target resolved through:
   - `_get_scoped_section` (`apps/storefront_builder/views.py:772`) —
     `pk` + `page__version__layout__store=store` + `page__version__status=DRAFT`.
   - `_get_scoped_container` (`views.py:323`) — same two conditions via `page__version__…`.
   - `_get_scoped_cell` (`views.py:333`) — `container__page__version__…` DRAFT+store.
   - `media_views` routes all begin with `_get_scoped_section` (`media_views.py:35,110,166,256,305,319,339`),
     then additionally scope the item via `get_object_or_404(model, pk=item_pk, section=section)`.
   - R4 `section.update_settings` resolves `pk` + `page__version=draft`
     (`r4_mutation_service.py:146`); R4 structural ops go through
     `section_structure_service._scoped_section` (`section_structure_service.py:39`),
     which pins `page__version=draft`.
   A Published/Archived/foreign target id is therefore indistinguishable from
   "does not exist" → **404** (or `SectionStructureError`/rejected in R4), mutating nothing.

2. **No target-version parameter at all** — the Appearance / header / footer /
   publish / undo / redo / discard / reset routes resolve the request store's
   ACTIVE Draft via `_resolve_store(request)` + `layout_service.get_or_create_draft(store)`.
   They are structurally incapable of naming a Published/Archived version; a
   foreign store is prevented by tenant host + `StoreMembership` resolution.

3. `storefront_restore(pk)` is the one legacy route accepting an explicit
   `version_id`. It **never mutates** the target — `layout_service.restore_version`
   looks the source up only within `layout.versions` (own store), raises
   `CrossStoreVersionError` → `Http404` for a foreign id, and clones the source
   into a **new** Draft (source untouched). `section_reorder` similarly builds its
   candidate set only from the active Draft's page and filters its final update
   by `page=page`, so foreign/non-Draft ids are silently dropped.

## Mutation-family protection matrix

Legend: **existing** = already proven by a prior test (reused, not duplicated);
**new** = proven by a test added in this task; **guard** = production guard added.

| Mutation family (route/path) | Published | Archived | Foreign | Coverage |
|---|---|---|---|---|
| Legacy `storefront_section_settings` | ✅ | ✅ | ✅ | Pub/Arch: existing Task-1 (`LegacyPublished/ArchivedVersionImmutabilityTests`); Foreign: **new** (`LegacySectionSettingsForeignProtectionTests`) |
| Legacy section remove / move / toggle / lock / collapse / duplicate | ✅ | ✅ | ✅ | **new** (`LegacyStructuralSectionProtectionTests`) |
| Legacy section reorder | ✅ | ✅ | ✅ | safe by construction (draft-page candidate set + `page=page` update filter); covered structurally, no id-targeted route |
| Legacy container settings / layout / move / remove | ✅ | ✅ | ✅ | **new** (`LegacyContainerProtectionTests`) |
| Legacy cell clear | ✅ | ✅ | ✅ | **new** (`LegacyCellAndBlockProtectionTests`) |
| Legacy block move / remove | ✅ | ✅ | ✅ | **new** (`LegacyCellAndBlockProtectionTests`) |
| Legacy section reset / section-field reset | ✅ | ✅ | ✅ | **new** (`LegacySectionSettingsForeignProtectionTests`) |
| Legacy appearance / header / footer editors | n/a¹ | n/a¹ | ✅ | **new** (`LegacyLifecycleRouteTargetingTests`) — no version-id target; foreign isolation via host+membership |
| Legacy preset apply / reset-to-baseline / page reset / header-footer reset | n/a¹ | n/a¹ | ✅ | operate on caller's own active Draft only; foreign isolation via host+membership (same mechanism proven in `LegacyLifecycleRouteTargetingTests`) |
| Legacy publish | n/a¹ | n/a¹ | ✅ | **new** (`LegacyLifecycleRouteTargetingTests.test_publish_only_touches_callers_own_draft…`) — publish archives the previous Published without editing its rows |
| Legacy undo / redo / discard | n/a¹ | n/a¹ | ✅ | **new** (`LegacyLifecycleRouteTargetingTests.test_undo_redo_discard_operate_on_own_draft_only`) |
| Legacy restore (`version_id`) | reads own² | reads own² | ✅ 404 | **new** (`LegacyRestoreCrossStoreViewProtectionTests`) — foreign id → 404, source never mutated |
| Media list/form/edit/delete/toggle/move/reorder | ✅ | ✅ | ✅ | Pub/Arch: **new** (`LegacyMediaLifecycleProtectionTests`); Foreign: existing (`test_media_views.TenantIsolationTests`) |
| Media background asset (JSON) tamper | — | — | ✅ | existing (`test_phase35_reference_editable_backgrounds.test_tampered_foreign_background_asset_is_rejected_without_mutation`) |
| R4 `section.update_settings` | ✅ | (same scope³) | ✅ | existing (`test_r4_mutation_api.PublishedVersionImmutabilityTests` / `TenantIsolationTests`) |
| R4 structural / appearance / header / footer / manifest / template | (same scope³) | (same scope³) | (same scope³) | R4 `_lock_active_draft` + `page__version=draft`; proven for `section.update_settings`, identical resolution for the rest |
| `layout_service.restore_version` (service) | reads own² | reads own² | ✅ raises | existing (`test_layout_service.RestoreTests.test_restore_rejects_cross_store_version`) |

¹ **n/a** = the route has no version-id parameter and can only ever resolve the
caller's own active Draft, so it is structurally incapable of targeting a
Published/Archived version. The reachable "wrong target" is a foreign store,
which is covered.
² Restoring the caller's OWN Published/Archived version is a legitimate feature;
it clones the source into a new Draft and never mutates the source (asserted in
`test_restore_of_own_published_creates_new_draft_without_mutating_source`).
³ All R4 mutations share the single `_lock_active_draft` boundary
(`select_for_update` on Layout+Version, `status=DRAFT`) and resolve any section
target via `page__version=draft`, so Published/Archived/foreign are rejected
identically to the proven `section.update_settings` case.

## Tests added (this task)

Extended `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py` with 7
new test classes (25 new test methods), all using real routes, the real
Draft/Publish lifecycle (`layout_service.get_or_create_draft`/`publish`), and the
existing `StorefrontBuilderViewsTestCase` base + a `_LifecycleTargetsMixin`
fixture (Published + Archived + foreign-store Draft, each with a real section and
container/cell):

- `LegacyStructuralSectionProtectionTests` — section toggle/lock/collapse/remove/move/duplicate rejected (404, no mutation) on Published, Archived, foreign; plus a foreign-owner-authenticated cross-store attempt.
- `LegacyContainerProtectionTests` — container settings/layout/move/remove rejected on all three.
- `LegacyCellAndBlockProtectionTests` — cell clear + block move/remove rejected on all three.
- `LegacySectionSettingsForeignProtectionTests` — foreign `section_settings` POST + section reset + section-field reset rejected on all protected targets.
- `LegacyMediaLifecycleProtectionTests` — media list/edit/delete/toggle on a Published/Archived version's section → 404, slide not mutated/deleted.
- `LegacyLifecycleRouteTargetingTests` — publish archives the previous Published without editing its rows; appearance editor GET does not expose/mutate a foreign draft; undo/redo/discard operate on the caller's own draft only.
- `LegacyRestoreCrossStoreViewProtectionTests` — restore of a foreign version id → 404 (nothing cloned, foreign draft intact); restore of own Published → new Draft without mutating the source.

Reused existing coverage without duplication: R4 published/foreign
(`test_r4_mutation_api`), service-level cross-store restore
(`test_layout_service`), foreign media (`test_media_views`), tampered foreign
background (`test_phase35_reference_editable_backgrounds`).

## Command + results

```
/projects/rastisi5_phase2_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase2_lifecycle_safety \
  apps.storefront_builder.tests.test_layout_service \
  apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_media_views --verbosity 1
```

Result: **Ran 137 tests** — `FAILED (failures=1)`.

The single failure is the **known, intended L01 RED**:
`test_phase2_lifecycle_safety.LegacyMutationAdvancesEditRevisionTests.test_legacy_real_mutation_advances_edit_revision_by_one`
(`edit_revision` does not advance on a legacy mutation; `AssertionError: 0 != 1`).
This is the Task-1-characterized desired-invariant test that belongs to **Task 3**
and MUST remain RED here. Its baseline-witness companion
(`test_baseline_legacy_mutation_does_not_advance_edit_revision`) remains GREEN.

**No new failures beyond the known L01 RED.** All 25 new negative tests PASS,
confirming every path is already safe by scoping.

## Scope confirmation

- Production change: **NO** (tests only).
- Files touched: `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`
  (test module) + this evidence file.
- No business-domain, model schema/migration, renderer, authority-service,
  settings-schema, or template/CSS/JS change.
- The L01 desired-invariant test and its baseline witness are left exactly as
  Task 1 authored them (out of scope for Task 2 — belongs to Task 3).
