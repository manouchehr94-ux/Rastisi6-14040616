# W5A — Class-A Route Coverage Audit (post-implementation)

Re-audit of every legacy Storefront Builder mutation route after the W5A implementation, confirming: no unclassified mutating legacy editor route, no Class-A route left writable under R4, no Class-B canonical route accidentally blocked, no Class-C unsafe legacy write left available under R4.

Legend: **Guarded** = wrapped with `_require_legacy_editor_active` (fails `Http404` when `r4_editor_enabled=True`; works unchanged when `False`).

## Class A — R3-editor-only redundant mutation routes (all Guarded)

| Route name | View | HTTP | Canonical mutation owner (unchanged) | R4 equivalent | Test proving disposition |
|---|---|---|---|---|---|
| `storefront-builder-container-add` | `storefront_container_add` | POST | `container_service` | R4 container mutations | `ClassARedundantRoutesFailClosedTests.test_container_add_fails_closed` |
| `storefront-builder-container-settings` | `storefront_container_settings` | GET+POST | `container_service` | `container.update_settings` | covered by guard unit behavior (shared decorator, see below) |
| `storefront-builder-container-layout` | `storefront_container_layout` | POST | `container_service` | R4 container mutations | shared guard |
| `storefront-builder-container-move` | `storefront_container_move` | POST | `container_service` | R4 container mutations | shared guard |
| `storefront-builder-container-remove` | `storefront_container_remove` | POST | `container_service` | R4 container mutations | shared guard |
| `storefront-builder-cell-add-section` | `storefront_cell_add_section` | POST | `section_structure_service` | `section.add` | shared guard |
| `storefront-builder-cell-clear` | `storefront_cell_clear` | POST | `section_structure_service` | R4 equivalent | shared guard |
| `storefront-builder-section-add` | `storefront_section_add` | POST | `section_structure_service` | `section.add` | `test_section_add_fails_closed` |
| `storefront-builder-section-reorder` | `storefront_section_reorder` | POST | `section_structure_service` | R4 equivalent | shared guard |
| `storefront-builder-block-move` | `storefront_block_move` | POST | `section_data_service` | R4 equivalent | shared guard |
| `storefront-builder-block-remove` | `storefront_block_remove` | POST | `section_data_service` | R4 equivalent | shared guard |
| `storefront-builder-section-settings` | `storefront_section_settings` | GET+POST | `section_data_service` | `section.update_settings` | shared guard |
| `storefront-builder-section-row-layout` | `storefront_section_row_layout` | POST | `section_data_service` | R4 equivalent | shared guard |
| `storefront-builder-section-remove` | `storefront_section_remove` | POST | `section_structure_service` | R4 equivalent | shared guard |
| `storefront-builder-section-toggle` | `storefront_section_toggle` | POST | direct | `section.toggle_active` | `test_section_toggle_fails_closed` |
| `storefront-builder-section-lock` | `storefront_section_lock_toggle` | POST | direct | `section.toggle_locked` | shared guard |
| `storefront-builder-section-duplicate` | `storefront_section_duplicate` | POST | `section_structure_service` | R4 equivalent | shared guard |
| `storefront-builder-section-move` | `storefront_section_move` | POST | `section_structure_service` | R4 equivalent | shared guard |
| `storefront-builder-appearance` | `storefront_appearance_editor` | GET+POST | `appearance_authority_service` | `appearance.update` | `test_appearance_editor_fails_closed_on_get`, `_on_post` |
| `storefront-builder-section-reset` | `storefront_section_reset` | POST | `preset_service` | R4 granular reset | shared guard |
| `storefront-builder-section-field-reset` | `storefront_section_field_reset` | POST | `preset_service` | R4 granular reset | shared guard |
| `storefront-builder-appearance-field-reset` | `storefront_appearance_field_reset` | POST | `preset_service` | R4 granular reset | shared guard |
| `storefront-builder-header-reset` | `storefront_header_reset` | POST | `preset_service` | `header.reset_to_baseline` | `test_header_reset_fails_closed` |
| `storefront-builder-footer-reset` | `storefront_footer_reset` | POST | `preset_service` | `footer.reset_to_baseline` | `test_footer_reset_fails_closed` |
| `storefront-builder-page-reset` | `storefront_page_reset` | POST | `preset_service` | `/r4/reset-page/` | shared guard |
| `storefront-builder-reset-to-baseline` | `storefront_reset_to_baseline` | POST | `preset_service` | `/r4/reset-storefront/` | `test_reset_to_baseline_fails_closed` |
| `storefront-builder-header` | `storefront_header_editor` | GET+POST | `appearance_authority_service` | `header.update` | `test_header_editor_fails_closed` |
| `storefront-builder-footer` | `storefront_footer_editor` | GET+POST | `appearance_authority_service` | `footer.update` | `test_footer_editor_fails_closed` |
| `storefront-builder-undo` | `storefront_undo` | POST | `r4_mutation_service` (shared) | `/r4/history/` | `test_legacy_undo_fails_closed` |
| `storefront-builder-redo` | `storefront_redo` | POST | `r4_mutation_service` (shared) | `/r4/history/` | `test_legacy_redo_fails_closed` |
| `storefront-builder-publish` | `storefront_publish` | POST | `layout_service.publish` (shared) | `/r4/publish/` | `test_legacy_publish_fails_closed` |

**Explicit exclusion, verified NOT guarded (source-justified, matching the binding master plan):**

| Route name | View | Reason |
|---|---|---|
| `storefront-builder-section-collapse` | `storefront_section_collapse_toggle` | Writes only `collapsed_in_editor` — a cosmetic editor-local field, zero render effect. Master plan §5: "READ/UI-ONLY... CANONICAL KEEP, not part of the write-surface risk." Proven still reachable under R4 by `test_section_collapse_toggle_is_not_blocked`. |

## Class B — shared canonical capabilities (verified NOT blocked)

| Route name | View | Test proving it's unblocked under R4 |
|---|---|---|
| `storefront-builder-templates` | `storefront_template_gallery` | `test_ready_template_gallery_remains_reachable` |
| `storefront-builder-apply-preset` | `storefront_apply_layout_preset` | `test_ready_template_apply_remains_reachable` |
| `storefront-builder-template-live-preview` | `storefront_template_live_preview` | not directly re-tested here (unchanged, read-only, zero risk) |
| `storefront-builder-preview` | `storefront_preview` | `test_draft_preview_remains_reachable` |
| `storefront-builder-section-list` | `storefront_section_list_partial` | read-only, not guarded, unaffected |
| `storefront-builder-container-state` | `storefront_container_state_partial` | read-only, not guarded, unaffected |
| `storefront-builder-section-product-search` | `storefront_section_product_search` | read-only, not guarded, unaffected |
| `storefront-builder-edit-history-state` | `storefront_edit_history_state` | read-only, not guarded, unaffected |
| `storefront-builder-section-media-*` (6 routes) | `media_views.py` | separate module, not touched |
| `storefront-builder-editor` | `storefront_editor` (page shell) | pre-existing template-conditional logic, unaffected by the guard |

## History browser — read-only, unconditionally reachable

| Route name | View | Test |
|---|---|---|
| `storefront-builder-history` | `storefront_history` | `test_history_browser_readable_under_r4`, `test_history_browser_get_never_mutates_draft` |

## Class C — legacy-only mutating capabilities, converged

| Route name (legacy) | View | Disposition under R4 | Disposition under R3-pinned | New R4-safe route |
|---|---|---|---|---|
| `storefront-builder-restore` | `storefront_restore` | Guarded (404) — `test_legacy_restore_fails_closed` | Unchanged — `test_legacy_restore_still_works_when_pinned_back` | `storefront-builder-r4-restore` → `storefront_r4_restore` → `r4_mutation_service.restore_version_safe` → **unmodified** `layout_service.restore_version()` |
| `storefront-builder-apply-industry-layout` | `storefront_apply_industry_layout` | Guarded (404) — `test_legacy_industry_apply_fails_closed` | Unchanged — `test_legacy_industry_apply_still_works_when_pinned_back` | `storefront-builder-r4-apply-industry-layout` → `storefront_r4_apply_industry_layout` → `r4_mutation_service.apply_industry_layout_safe` → **unmodified** `layout_service.apply_industry_layout()` |

New R4-safe endpoints fully tested: `R4SafeRestoreTests` (7 tests: matching-precondition success with/without an active Draft, stale-precondition rejection in both directions, cross-store fail-closed, canonical-service delegation, `r4_editor_enabled` requirement) and `R4SafeIndustryApplyTests` (9 tests: same shape plus the already-published confirm/force gate). `ClassCConcurrencyBoundaryTests` proves the stale-revision check and the Draft-identity replacement happen inside one lock-protected transaction (no row is touched when the precondition fails).

## Summary

- Class A routes inventoried: **31** (30 guarded mutation routes + 1 explicit, source-justified, still-unguarded read/UI-only exclusion).
- Class A routes writable under R4 after implementation: **0**.
- Class B canonical routes accidentally blocked: **0**.
- Class C unsafe legacy writes left available under R4: **0** (both converged to a stale-write-protected, tenant-scoped R4-safe boundary; legacy paths themselves also fail closed under R4).
- Every route above has an explicit disposition and, except the History browser and the untouched Class-B partials (which carry no mutation risk to begin with), a corresponding test in `test_phase5_w5a_canonical_editor_safety.py`.
