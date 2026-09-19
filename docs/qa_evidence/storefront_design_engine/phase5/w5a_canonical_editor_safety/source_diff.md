# W5A — Source Diff Summary

Full diff: `git diff feature/phase5-design-expansion..feature/phase5-w5a-canonical-editor-safety` (or the equivalent PR diff). Summary by file, in the order changes were made across four commits (plan → RED tests → implementation → code-review fixes):

```
 apps/dashboard/urls.py                                          |  10 +
 apps/storefront_builder/r4_views.py                             | 116 ++++
 apps/storefront_builder/services/r4_mutation_service.py         |  71 +++
 apps/storefront_builder/storefront_appearance/families.py       |  22 +
 .../dashboard/storefront_builder/editor.html                    |  43 +-
 .../dashboard/storefront_builder/history.html                   |  46 +-
 .../dashboard/storefront_builder/r4/editor.html                 |   4 +-
 apps/storefront_builder/tests/test_dark_digital_luxury_v2.py    |   9 +
 .../tests/test_phase5_w5a_canonical_editor_safety.py            | 640 +++++++++++++++++++++
 apps/storefront_builder/views.py                                |  68 +++
 (+ 5 documentation/plan/evidence files, ~370 lines, docs-only)
 15 files changed, 1384 insertions(+), 11 deletions(-)
```

## Production code (non-test, non-docs)

- **`apps/storefront_builder/views.py`** (+68): new `_require_legacy_editor_active` decorator (the single shared Class-A eligibility guard); applied to the explicit Class A route list (30 functions) plus the two legacy Class C entry points (`storefront_restore`, `storefront_apply_industry_layout`); `storefront_history` gains `current_draft_revision` in its render context for the new Restore button.
- **`apps/storefront_builder/r4_views.py`** (+116): two new thin endpoints, `storefront_r4_restore` and `storefront_r4_apply_industry_layout`, matching the exact existing Reset-Storefront/Switch-Template contract shape; a shared `_read_class_c_base_revision` helper (accepts `null` or a non-negative int); strict-boolean validation for `force`.
- **`apps/storefront_builder/services/r4_mutation_service.py`** (+71): `_lock_layout_for_identity_replacement` (the new Class C locking helper, distinct from `_lock_active_draft`), `restore_version_safe`, `apply_industry_layout_safe` — both thin wrappers delegating to the existing, byte-for-byte unmodified `layout_service.restore_version()`/`apply_industry_layout()`.
- **`apps/dashboard/urls.py`** (+10): two new route registrations (`storefront-builder-r4-restore`, `storefront-builder-r4-apply-industry-layout`).
- **`apps/storefront_builder/storefront_appearance/families.py`** (+22): non-behavioral reserved-disposition comments on the `layout` and `mega_menu` `ComponentFamilyDefinition` entries — no field/behavior change.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`** (43 lines changed): the R4-active minimal-compatibility surface's Industry-Layout-Apply form replaced with a button + inline `fetch()`-based script targeting the new R4-safe endpoint; the R3-shell (legacy, `r4_editor_enabled=False`) branch is untouched (confirmed by diff scope).
- **`apps/storefront_builder/templates/dashboard/storefront_builder/history.html`** (46 lines changed): the Restore control is now conditional — the new button + inline script when `layout.r4_editor_enabled`, the original unchanged `<form>` otherwise.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`** (4 lines changed): the 10-item `appearance_registry` style-token selector's label changed from "قالب" to "بستهٔ سبک" (Style Pack); the 50-item Ready Template switcher section (a separate part of the same file) is untouched.

## Test code

- **`apps/storefront_builder/tests/test_phase5_w5a_canonical_editor_safety.py`** (+640, new file): the full RED-before-GREEN suite (54 tests across 12 test classes) — see `tdd_red.txt`/`tdd_green.txt`.
- **`apps/storefront_builder/tests/test_dark_digital_luxury_v2.py`** (+9): `MobileBottomNavEditorTests`' fixture now explicitly pins `r4_editor_enabled=False`, matching the legacy-editor scenario its own two tests were already testing (see `code_review.md`/commit history for the full rationale).

## Non-production, not part of this diff summary's risk surface

- 5 documentation files (plan + 4 evidence docs at commit time of writing this summary; more evidence added after).
- `tools/storefront_builder_r4_qa/w5a_canonical_editor_safety_qa.mjs` (new browser QA script, tooling only, not shipped application code) and a `package-lock.json`/`node_modules` install under `tools/storefront_builder_qa/` (gitignored, not committed).

## Zero migrations

No model field was added, removed, or altered. `manage.py makemigrations --check --dry-run` reports "No changes detected" against the final HEAD.
