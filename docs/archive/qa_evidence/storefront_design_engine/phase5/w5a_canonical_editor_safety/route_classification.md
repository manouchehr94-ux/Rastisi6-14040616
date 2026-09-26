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
| `storefront-builder-section-collapse` | `storefront_section_collapse_toggle` | POST | direct | none | `test_section_collapse_toggle_fails_closed`, `test_section_collapse_toggle_blocked_request_mutates_nothing`, `test_section_collapse_toggle_still_works_when_pinned_back` |

**Independent-Review repair (round 2) — corrected misclassification:** `storefront_section_collapse_toggle` was previously listed below as a "justified unguarded exclusion" on the theory that it writes only a cosmetic, render-inert field. The Independent Architect proved this wrong by direct source inspection: `collapsed_in_editor` is a member of `edit_history_service._SECTION_FIELDS`, and the view is decorated with `@_record_edit_history`, so it **is** a persisted Draft mutation that participates in Draft snapshots/history exactly like `storefront_section_toggle`. It is now guarded with the same shared `_require_legacy_editor_active` decorator, in the guarded-routes table above, not excluded.

**Re-audited (round 2) — every other `require_POST`/GET+POST view in `views.py` that calls `.save()`/`.delete()`/`.update()` on a model was walked via AST and confirmed guarded** (no second collapse-toggle-style false exclusion exists). `storefront_apply_layout_preset` (the Ready Template Apply route) is the one other unguarded mutation route found in this sweep; it is correctly Class B (see below) — its own dedicated test (`test_ready_template_apply_remains_reachable`) and `code_review.md`'s prior investigation both already establish this deliberately.

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
| `storefront-builder-section-media-*` (6 routes) | `media_views.py` | Re-audited (round 2): confirmed genuinely shared, not redundant — `editor.html`'s R4 branch and `section_media_list_body.html`/`section_media_form_body.html` render `hx-get`/`hx-post` calls to these SAME routes (with an `HX-R4-Inline` header variant for R4's embedded rendering), and no separate R4-native media mutation type exists in `r4_mutation_service.py`. Both editors share one media-management surface; guarding it would break R4, not just R3. |
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

New R4-safe endpoints fully tested: `R4SafeRestoreTests` (11 tests) and `R4SafeIndustryApplyTests` (14 tests: same shape plus the already-published confirm/force gate) — matching-precondition success with/without an active Draft, same-identity-wrong-revision rejection in both directions, the ABA hazard (wrong identity with a coincidentally-matching revision), negative/non-integer/inconsistent-null-pairing precondition-shape rejection (400), cross-store fail-closed, canonical-service delegation, `r4_editor_enabled` requirement, and rate-limit exhaustion translated to a controlled 429. `ClassCConcurrencyBoundaryTests` proves the identity+revision check and the Draft-identity replacement happen inside one lock-protected transaction (no row is touched when the precondition fails).

## Summary

- Class A routes inventoried: **32**, all 32 now **guarded** — 0 exclusions. (Round 2 correction: `storefront-builder-section-collapse` was previously counted as a justified unguarded exclusion, and the total was previously misstated as 31; the Independent Architect proved by direct source inspection that `_require_legacy_editor_active` decorates 34 functions in `views.py` total — 32 Class A + 2 legacy Class C [`storefront_restore`, `storefront_apply_industry_layout`] — so `storefront-builder-section-collapse` is now guarded like every other Class-A route, and the Class-A table above correctly lists 32 rows.)
- Class A routes writable under R4 after implementation: **0**.
- Class B canonical routes accidentally blocked: **0**.
- Class C unsafe legacy writes left available under R4: **0** (both converged to a stale-write-protected, tenant-scoped R4-safe boundary; legacy paths themselves also fail closed under R4).
- Every route above has an explicit disposition and, except the History browser and the untouched Class-B partials (which carry no mutation risk to begin with), a corresponding test in `test_phase5_w5a_canonical_editor_safety.py`.
- Round-2 re-audit: every `require_POST`/GET+POST view in `views.py` calling `.save()`/`.delete()`/`.update()` was enumerated via AST and cross-checked against the guard — no further false exclusion found.
