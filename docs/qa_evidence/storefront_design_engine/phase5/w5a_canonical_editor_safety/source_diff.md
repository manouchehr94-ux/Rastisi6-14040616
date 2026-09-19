# W5A — Source Diff Summary

Full diff: `git diff feature/phase5-design-expansion..feature/phase5-w5a-canonical-editor-safety` (or the equivalent PR diff), final HEAD after the Independent-Review repair round. 41 files changed, 3710 insertions(+), 20 deletions(-) overall.

## Production code (non-test, non-docs) — final, round 2

```
 apps/dashboard/urls.py                                          |  10 +
 apps/storefront_builder/r4_views.py                             | 158 +++++++
 apps/storefront_builder/services/r4_mutation_service.py         | 102 ++++
 apps/storefront_builder/storefront_appearance/families.py       |  22 +
 .../dashboard/storefront_builder/editor.html                    |  48 +-
 .../dashboard/storefront_builder/history.html                   |  49 +-
 .../dashboard/storefront_builder/r4/editor.html                 |   4 +-
 apps/storefront_builder/views.py                                |  88 +++
 8 files changed, 466 insertions(+), 15 deletions(-)
```

- **`apps/storefront_builder/views.py`** (+88): new `_require_legacy_editor_active` decorator (the single shared Class-A eligibility guard); applied to the explicit Class A route list (**32** functions, round 2 — see below) plus the two legacy Class C entry points (`storefront_restore`, `storefront_apply_industry_layout`) — **34 guarded functions total**, confirmed by direct AST enumeration. `storefront_history` gains `current_draft_id`/`current_draft_revision` in its render context for the new Restore button. **Round 2 addition**: `storefront_section_collapse_toggle` now also carries the guard — the Independent Architect proved the round-1 "cosmetic-only" exclusion was a misclassification (`collapsed_in_editor` is in `edit_history_service._SECTION_FIELDS` and the view is `@_record_edit_history`-decorated). This also corrects a metadata error in earlier evidence, which understated the Class-A total as 31.
- **`apps/storefront_builder/r4_views.py`** (+158): two thin endpoints, `storefront_r4_restore` and `storefront_r4_apply_industry_layout`, matching the exact existing Reset-Storefront/Switch-Template contract shape. **Round 2**: `_read_class_c_base_revision` renamed to `_read_class_c_precondition`, now validating BOTH `base_draft_id`/`base_revision` (the ABA fix — see `concurrency_contract.md`); both views additionally catch `RateLimitExceeded` from the existing, unmodified rate limits and translate it to a controlled `429`.
- **`apps/storefront_builder/services/r4_mutation_service.py`** (+102): `_lock_layout_for_identity_replacement` (the Class C locking helper, distinct from `_lock_active_draft`), `restore_version_safe`, `apply_industry_layout_safe` — thin wrappers delegating to the existing, byte-for-byte unmodified `layout_service.restore_version()`/`apply_industry_layout()`. **Round 2**: the locking helper now takes `expected_draft_id` in addition to `expected_base_revision` and compares identity before revision (closing the ABA hazard); `R4StaleRevision` gained an optional `current_draft_id` keyword (backward-compatible — every other existing call site is unaffected).
- **`apps/dashboard/urls.py`** (+10, unchanged since round 1): two new route registrations.
- **`apps/storefront_builder/storefront_appearance/families.py`** (+22, unchanged since round 1): non-behavioral reserved-disposition comments — no field/behavior change.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`** (48 lines changed): Industry-Layout-Apply button + inline `fetch()` script targeting the R4-safe endpoint; the R3-shell (legacy) branch is untouched. **Round 2**: the button now also renders/submits `data-r4-base-draft-id`.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/history.html`** (49 lines changed): Restore control conditional on `layout.r4_editor_enabled`. **Round 2**: the button now also renders/submits `data-r4-base-draft-id`.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`** (4 lines changed, unchanged since round 1): Style Pack label rename.

## Test code — final, round 2

- **`apps/storefront_builder/tests/test_phase5_w5a_canonical_editor_safety.py`** (+640 round 1, further extended round 2 to 60 tests total): the full RED-before-GREEN suite plus the round-2 repair coverage — collapse-toggle reclassification (3 tests), the ABA hazard for both Restore and Industry-Apply, precondition-shape rejection (negative/non-integer/inconsistent-null), and rate-limit-exhaustion controlled-response tests.
- **`apps/storefront_builder/tests/test_dark_digital_luxury_v2.py`** (+9, unchanged since round 1): `MobileBottomNavEditorTests`' fixture pins `r4_editor_enabled=False`.
- **17 other test files** (`test_appearance.py`, `test_g23_builder_public_content_appearance.py`, `test_media_asset_lifecycle.py`, `test_phase1_appearance_authority.py`, `test_phase2_lifecycle_safety.py`, `test_phase2c_content_preserving_layout_changes.py`, `test_phase4_task6_group_f_reconciliation.py`, `test_phase5_composition_lifecycle.py`, `test_phase7_family_retirement.py`, `test_preset_service.py`, `test_r4_mutation_api.py`, `test_stable_section_identity.py`, `test_storefront_page.py`, `test_u1a_preset_edit_history_characterization.py`, `test_u1b2_capability_metadata_wiring.py`, `test_u2a_global_header_system.py`, `test_u2b_global_footer_system.py`): pin `r4_editor_enabled=False` on the specific test methods that genuinely exercise a legacy Class-A route, surfaced by the exact-source full-suite regression after the Class-A guard closed the pre-W5A "legacy routes reachable regardless of the flag" compatibility bridge. Two rounds of correction applied here (see `code_review.md` §"Test-modification re-review" for the full account): the initial blanket per-method pin (commit `bf39b8fb`), then a precision pass (commit `6019a82e`) fixing a wrong module alias and 11 tests whose blanket pin broke their own cross-mode (legacy+R4-in-one-method) assertions. `git diff` against the pre-W5A base shows 581 insertions / 5 deletions across these 18 files combined — the 5 deletions are one deliberately-replaced assertion block (stronger, not weaker), zero others.

## Non-production, not part of this diff summary's risk surface

- Plan + 11 evidence documents under `docs/qa_evidence/.../w5a_canonical_editor_safety/`.
- `tools/storefront_builder_r4_qa/w5a_canonical_editor_safety_qa.mjs` (browser QA script, tooling only, not shipped application code, extended round 2 with the real R3-pinned scenario and the updated wire-contract payloads) and a `package-lock.json`/`node_modules` install under `tools/storefront_builder_qa/` (gitignored, not committed).

## Zero migrations

No model field was added, removed, or altered. `manage.py makemigrations --check --dry-run` reports "No changes detected" against the final HEAD.
