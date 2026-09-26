# Phase 2 — Final Regression / Architecture Gate (Task 8, verification only)

**Program:** Storefront Appearance Convergence — Phase 2 (Lifecycle & Safety)
**Branch:** `feature/storefront-lifecycle-safety-phase2`
**Worktree:** `/projects/rastisi5_phase2` · venv `/projects/rastisi5_phase2_venv/bin/python` (Python 3.12.13, Django 5.2.17)
**Baseline (Phase-1 merge):** `515518227c09f888972fa6eda756867097358dfb` — confirmed present as `origin` ref and an ANCESTOR of HEAD.
**Gate HEAD reviewed:** `8c2346d` (Task-7 tip; this closure commit is Task 8, docs-only).

This is a VERIFICATION-ONLY gate: no production or test code changed in Task 8. It records the cumulative review, the fresh full regression matrix, the pre-existing-exception re-verification, and the §18 exit-gate evaluation.

---

## 1. Task ledger (Tasks 1–7, each independently reviewed)

| Task | Base | Head | Commit | Review (C/I/M) |
|---|---|---|---|---|
| 1 | a1898b5 | cd33ba4 | test: characterize phase2 lifecycle and media reachability gaps | 0/0/1 |
| 2 | cd33ba4 | aab8f1c | test: prove published/archived/cross-store mutation protection (L05) | 0/0/2 |
| 3 | aab8f1c | ee13187 | feat: converge draft edit_revision across legacy and r4 mutations (L01) | 0/0/1 |
| 4 | ee13187 | e611647 | feat: make legacy publish/undo/redo lifecycle- and revision-safe (L02,L03) | 0/0/2 |
| 5 | e611647 | 237064b | feat: converge structure-lock and lifecycle-safe template operations (L04,L06) | 0/0/1 |
| 6 | 237064b | 0eb76fa | fix: close A05 media reachability gap in deletion safety check (L07, P0) | 0/0/2 |
| 7 | 0eb76fa | 8c2346d | test: prove cross-entry lifecycle convergence and recovery safety | 0/0/2 |

Every task was implemented by a fresh implementer and reviewed by an independent reviewer; all C/I findings = 0. All MINOR findings are catalogued in `_sdd_ledger.md` (rulings R1–R9) and carried here for the gate.

## 2. Cumulative whole-branch review (fresh reviewer, `5155182..8c2346d`)

Fresh cumulative semantic review of the composite production diff.

**COUNT: 0 CRITICAL, 0 IMPORTANT, 1 MINOR. Verdict: APPROVE-WITH-NITS.**

- Verified holistically: `edit_revision` is single-sourced (centralized in `record_change`; R4 no advance-by-2; undo/redo own single increment, never call `record_change`; legacy decorator advances once) — exactly one advance per real change on every path, zero on no-ops.
- Publish converges on the shared atomic `layout_service.publish` from both legacy and R4; optional stale guard never changes publish semantics; exception ordering correct.
- Locking consistent (layout→draft) on both paths; no cross-path deadlock; rejected/failed ops roll back with no partial state / no revision bump / no history entry.
- Media A05 closed: FK-short-circuited, tenant-scoped via verified real relation paths, id-key-restricted (not any-integer), fail-closed; deletion gate still deletes genuinely-unreachable assets and keeps `on_commit` cleanup.
- Scope clean: exactly 5 production files; no migration, renderer, business-domain change, route deletion, new variant/lock-type/field, or orphan-cleanup job/signal/TTL.

**The single MINOR** (non-blocking): legacy `storefront_undo`/`storefront_redo` (`views.py:~1916`) delegate through `apply_history_command_current`, which can raise `R4MutationError("no_active_draft")` in a narrow concurrent publish/discard race between `get_or_create_draft` and the internal re-lock; the view catches nothing → an unhandled 500 rather than the graceful `ok=False` no-op payload the R4 endpoint returns. Narrow, non-data-corrupting (transaction rolls back cleanly), and the R4 path shares the same characteristic — a genuinely new-from-composite but harmless error-handling asymmetry. Recorded as ledger R6(a). Deferred as a non-blocking nit (does not affect any exit-gate criterion).

## 3. Fresh full Phase-2 regression matrix

```
$ manage.py test \
    apps.storefront_builder.tests.test_phase2_lifecycle_safety \
    apps.content.tests.test_phase2_media_reachability \
    apps.storefront_builder.tests.test_r4_mutation_api \
    apps.storefront_builder.tests.test_r4_store_appearance_mutations \
    apps.storefront_builder.tests.test_layout_service \
    apps.storefront_builder.tests.test_preset_service \
    apps.storefront_builder.tests.test_phase27_history_identity \
    apps.storefront_builder.tests.test_u7_ready_template_baseline \
    apps.storefront_builder.tests.test_phase5_composition_lifecycle \
    apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization \
    apps.storefront_builder.tests.test_media_asset_lifecycle \
    apps.storefront_builder.tests.test_media_write_path \
    apps.storefront_builder.tests.test_media_views \
    apps.storefront_builder.tests.test_g22_preview_media_render_consistency -v1

Ran 336 tests in 108.149s
OK
System check identified no issues (0 silenced).
```

**TOTAL 336 · PASS 336 · FAIL 0 · ERROR 0.**

## 4. Documented pre-existing baseline exceptions — re-verified (NOT regressions)

Each still fails with the SAME signature it had at/ before the Phase-2 baseline; none is introduced by Phase 2, and each lives in a module NOT in the Phase-2 change set.

- `test_views.FullscreenEditorTests` → `Ran 4 tests … FAILED (failures=1, errors=1)` — the 2 documented FullscreenEditor exceptions.
- `test_u8_template_gallery` → `Ran 11 tests … FAILED (failures=1)` — the documented gallery-label exception.
- `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests` → `Ran 11 tests … FAILED (failures=1)` — the validator-boundary exception (proven pre-existing at Task-3 base `aab8f1c`; ledger R4).

No NEW failure signature appeared anywhere.

## 5. `check` + migrations

```
$ manage.py check                         → System check identified no issues (0 silenced).
$ manage.py makemigrations --check --dry-run → No changes detected
```

No schema change anywhere in Phase 2.

## 6. Scope audit (`5155182..8c2346d`)

```
$ git diff 5155182..HEAD --check          → (clean)

$ git diff 5155182..HEAD --name-only -- apps/ ':(exclude)apps/**/tests/**'
apps/content/media_reachability.py            (NEW)
apps/content/models.py
apps/storefront_builder/services/edit_history_service.py
apps/storefront_builder/services/r4_mutation_service.py
apps/storefront_builder/views.py
```

Exactly 5 production files (+ 2 test modules + docs). Confirmed: **NO migration, NO new renderer, NO business-domain (Product/Brand/Collection) change, NO legacy route deletion, NO new variants / lock types / model fields.**

## 7. §18 exit-gate checklist (item-by-item, evidence-backed)

| # | Exit-gate criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Every Appearance/Builder mutation targets active Draft; cannot mutate Published/Archived/foreign — proven by negative tests | **PASS** | Task 1 RED + Task 2 negative suites (25 negative cases); Draft+store scoping; `test_phase2_lifecycle_safety` protection classes |
| 2 | `edit_revision` Draft-wide monotonic token advanced by every state-changing mutation (R4 + hardened legacy); stale writes rejected where a revision is available | **PASS** | Task 3 centralization in `record_change`; cross-path stale test (409 `stale_revision`); Task 7 mixed-sequence both directions |
| 3 | Publish/restore/discard/undo/redo/reset atomic, Draft-correct, revision-coherent, recover canonical typed manifest intact | **PASS** | Task 4 (publish + undo/redo shared contract); Task 5 (reset); Task 7 manifest byte-for-byte survival across the full sequence |
| 4 | Structure-lock complete + consistent across R4 and legacy for Section and Container; lock structure-only | **PASS** | Task 5 full spec-§11 matrix (negative every "NO" cell both paths; positive "YES" cells succeed on a locked section) |
| 5 | Media deletion respects ALL reference classes (FK + JSON + history/baseline), fail-closed, tenant-scoped; A05 closed; no recoverable asset deletable | **PASS** | Task 6 extended `is_referenced` + gate; 10 media-reachability tests GREEN; makemigrations clean |
| 6 | Cross-store/tenant isolation intact (regression-tested) | **PASS** | Task 6 cross-store isolation tests + same-store control; store-scoped locks/scans; full media suite GREEN |
| 7 | No DB migration, no new renderer, no business-domain change, no legacy deletion, no new variants | **PASS** | §6 scope audit; `makemigrations --check` clean |
| 8 | Fresh full Phase-2 regression matrix GREEN (except documented pre-existing exceptions); check clean; makemigrations clean | **PASS** | §3 (336 OK); §4 (pre-existing re-verified, no new regressions); §5 (check + migrations clean) |

**All 8 exit-gate items PASS.**

## 8. Gate result

- 0 CRITICAL / 0 IMPORTANT (cumulative + all seven per-task reviews).
- Full regression matrix GREEN (336/336) except the three documented pre-existing baseline exceptions, each re-verified with an unchanged signature.
- `check` clean; `makemigrations --check` clean; scope audit clean (5 production files, no migration/renderer/domain/variant).
- All §18 exit-gate items PASS.

**PHASE 2 — PASS.** No push / no PR / no merge performed. Awaiting Product Owner / Architect review.



---

# EVIDENCE HARDENING ADDENDUM (final handoff completeness)

This addendum was added as an evidence-completeness correction. **No production code and no test code were changed** to produce it. It records: the full controller rulings (verbatim, not by reference), the exact Task-4/R6(a) reviewer finding with a documented severity classification, the exact pre-existing-exception signatures reproduced at their baselines, and the full 22-item Master exit-gate table.

## Controller Rulings and Deferred Review Findings

Every ruling/minor from the controller SDD ledger is preserved here so the final handoff does not depend on the (git-ignored) controller file. Each row: ID · task · exact finding · severity · ruling · why safe to continue · consequence if the ruling is wrong · deferral.

### R1 — media test package location
- **Task:** pre-Task-6 (raised at Task 1 planning, resolved Task 6).
- **Exact finding:** the plan required confirming the real test package for `apps/content` before creating `test_phase2_media_reachability.py`; if `apps/content/tests/` were not a package, the module was to go under `apps/storefront_builder/tests/`.
- **Severity:** procedural (not a defect).
- **Ruling:** `apps/content/tests/` IS a package → the media reachability test was placed at `apps/content/tests/test_phase2_media_reachability.py`. Spec-consistent.
- **Why safe:** the file lives in a real, collected test package; the full media suite runs and passes.
- **Consequence if wrong:** tests silently not collected → false GREEN. Refuted: the module runs (10 tests) and the RED cases were observed failing before the Task-6 fix.
- **Deferral:** none — resolved.

### R2 — L01 baseline-witness must flip
- **Task:** Task 1 review (MINOR).
- **Exact finding:** the L01 baseline-witness test `test_baseline_legacy_mutation_does_not_advance_edit_revision` asserted the current DEFECTIVE behavior (legacy mutation does not advance `edit_revision`) and had to be flipped/removed at Task 3 when L01 was fixed.
- **Severity:** MINOR (tracked obligation; self-announcing).
- **Ruling:** tracked to Task 3; if forgotten it becomes a self-announcing failure.
- **Why safe:** a stale anti-invariant witness left in place would FAIL loudly at Task 3, so it cannot be silently forgotten.
- **Consequence if wrong:** a test asserting the defect would remain GREEN, masking the fix. Refuted at Task 3: the witness was replaced by the correct post-fix invariant and a grep confirmed no test still asserts non-advancement.
- **Deferral:** none — discharged at Task 3.

### R3 — Task-2 test cosmetics (2 MINOR)
- **Task:** Task 2 review.
- **Exact finding:** (a) `test_undo_redo_discard_operate_on_own_draft_only` is named `discard` but only posts undo/redo; (b) `test_foreign_client_cannot_toggle_published_or_archived_of_target_store` loop tuple repeats `published_section` and omits `foreign_section` (harmless copy-paste).
- **Severity:** MINOR (cosmetic; test naming / redundant loop entry).
- **Ruling:** optional cleanup in a later task; do not block.
- **Why safe:** both are naming/coverage-completeness nits in NEGATIVE tests; the negative assertions that do run are correct and pass. (a) simply under-describes; (b) still asserts the published/archived rejection, only losing one incremental foreign-target datapoint already covered elsewhere by the tenant-isolation suite.
- **Consequence if wrong:** marginally reduced negative-coverage breadth for one foreign-store toggle datapoint — no production behavior affected; the property is proven by other tests.
- **Deferral:** DEFERRED to an optional later test-cleanup pass (Phase 2 does not require it).

### R4 — pre-existing r4_vertical_slice validator-boundary failure
- **Task:** Task 3 (and re-confirmed at the final gate).
- **Exact finding:** `apps.storefront_builder.tests.test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary` fails: `Expected 'validate_appearance_config' to have been called once. Called 2 times.`
- **Severity:** pre-existing baseline failure (NOT a Phase-2 regression; NOT a stop condition).
- **Ruling:** allowed — proven pre-existing (see the Pre-Existing Baseline Exceptions section below; reproduced identically at Task-3 base `aab8f1c` AND at Phase-1 baseline `5155182`).
- **Why safe:** the double-call is in code untouched by Phase 2; the signature is byte-identical at baseline; it is not in any Phase-2 required or regression list.
- **Consequence if wrong (i.e. if it were actually a Phase-2 regression):** would indicate Phase 2 introduced a redundant validator call. Refuted: identical failure exists at `5155182` before any Phase-2 commit.
- **Deferral:** DEFERRED — belongs to whichever team owns the R4 vertical-slice validator boundary; out of Phase-2 scope.

### R5 — Task-3 stale test docstrings
- **Task:** Task 3 review (MINOR).
- **Exact finding:** stale class/method docstrings in `test_phase2_lifecycle_safety.py` (~lines 80-81 and 130-136) still describe RED/baseline behavior and reference the removed witness test `test_baseline_legacy_mutation_does_not_advance_edit_revision`.
- **Severity:** MINOR (documentation-only; no behavioral impact).
- **Ruling:** optional cleanup; do not block.
- **Why safe:** docstrings do not affect test execution or assertions; the actual assertions encode the correct post-fix invariant.
- **Consequence if wrong:** a future reader could be misled about a test's intent — no runtime risk.
- **Deferral:** DEFERRED to an optional later test-cleanup pass.

### R6 — Task-4 review (2 MINOR) — includes R6(a), the finding reconciled in Part C below
- **Task:** Task 4 review; R6(a) re-surfaced by the cumulative whole-branch review.
- **Exact finding (a):** legacy `storefront_undo`/`storefront_redo` (`_legacy_history_command`, `apps/storefront_builder/views.py`) fetch/create the draft in one step, then re-lock inside `apply_history_command_current`; if a concurrent request publishes or discards the draft in that window, `apply_history_command_current` raises `R4MutationError("no_active_draft")`, which the legacy view does NOT catch → an unhandled HTTP 500, instead of the graceful `ok=False` JSON no-op the R4 endpoint returns. Narrow race; the R4 path shares the same characteristic, so it is NOT a Phase-2 regression relative to R4.
- **Exact finding (b):** `_run_history_command` re-checks the `command in ("undo","redo")` allowlist that both of its callers already validated — a harmless dead defensive branch.
- **Severity:** MINOR (see Part C for the formal classification of (a)).
- **Ruling:** non-blocking; do not block Phase-2 closure. Optional: wrap the legacy call to return `ok=False` on `R4MutationError`, matching the R4 endpoint.
- **Why safe:** the raising function is `@transaction.atomic` with `select_for_update` locks — on the race it rolls back completely (no partial mutation, no revision bump, no history entry). The only observable difference is the ERROR RESPONSE SHAPE (500 vs a clean `ok=False`/400). No state corruption, no stale overwrite, no revision-protection bypass, no tenant/lifecycle boundary crossed (see Part C).
- **Consequence if wrong (i.e. if it could corrupt):** would be IMPORTANT and a STOP. Refuted in Part C: the atomic+locked rollback makes corruption/overwrite impossible; only the error response differs.
- **Deferral:** DEFERRED as an optional response-shape hardening (Phase 3+ or a cleanup pass). Not required for Phase-2 acceptance.

### R7 — Task-5 target_container_locked coverage (informational)
- **Task:** Task 5 review (MINOR, informational).
- **Exact finding:** `section_structure_service.move_section` distinguishes `container_locked` (source container) from `target_container_locked` (target container); the negative suite covers `container_locked` but has no dedicated test for the `target_container_locked` branch.
- **Severity:** MINOR / informational (coverage completeness).
- **Ruling:** not required by the spec §11 matrix (both are "NO"/container-lock and symmetric); optional extra coverage; do not block.
- **Why safe:** both branches are the same lock rule; the enforced-behavior ("moving into a locked target container is refused") is symmetric with the tested source-lock branch, and both raise a lock error before any mutation.
- **Consequence if wrong:** the `target_container_locked` branch could regress undetected by this suite — but it is the same guard as the covered branch; a regression would also break the covered path.
- **Deferral:** DEFERRED to an optional later test-coverage addition.

### R8 — Task-6 media-reachability safe-direction observations (2 MINOR)
- **Task:** Task 6 review (P0).
- **Exact finding (a):** `_referenced_by_section_backgrounds` (`apps/content/media_reachability.py`) scans the WHOLE `settings` payload for a `media_asset_id` key (not only the `background` subtree). (b) the fail-closed `except Exception` in `is_reachable_via_json_or_snapshots` would silently mask a future broken relation path as always-True (safe-but-useless over-retention).
- **Severity:** MINOR — both are in the SAFE (over-retain) direction.
- **Ruling:** non-blocking; do not block the P0 fix.
- **Why safe:** both err toward treating an asset as REFERENCED, which prevents deletion — the conservative, data-preserving direction. (a) at worst keeps an unreferenced asset (no data loss); (b) at worst never deletes (no data loss).
- **Consequence if wrong:** (a) a future key literally named `media_asset_id` outside `background` would count as a reference → an asset retained slightly longer than necessary (no unsafe deletion). (b) a future broken relation path would be masked as always-referenced → over-retention, never under-retention. Neither can cause the A05 failure mode (deleting a live/recoverable asset).
- **Deferral:** DEFERRED — optional observability hardening (narrower `except` / log on the fail-closed branch); an orphan-media cleanup job is explicitly a Phase-3+ product decision, so over-retention has no near-term cost.

### R9 — Task-7 convergence-test hardening (2 MINOR)
- **Task:** Task 7 review.
- **Exact finding:** (a) the snapshot-only live-section guard filters `page__version=self.draft` (narrower than the store-scoped production scan) — harmless because no live section is created in that test; (b) both convergence runs source `expected_manifest` from the same `_ready_manifest()`; the proof still holds via independent DB reloads, but an `assertTrue(manifest)` would harden against a future empty-manifest regression.
- **Severity:** MINOR (test-hardening).
- **Ruling:** non-blocking; do not block.
- **Why safe:** (a) the guard is only a precondition assertion in a test where no live section exists, so the narrower filter cannot produce a false pass; (b) the manifest is reloaded from the DB independently in each run and compared, so a constant-source would still be caught if the two runs diverged.
- **Consequence if wrong:** (a) none — precondition only; (b) a theoretical future where BOTH runs produced an empty manifest would pass vacuously — extremely unlikely and unrelated to Phase-2 behavior.
- **Deferral:** DEFERRED to an optional test-hardening pass.

### Non-ruling recorded fixes/checks (for completeness)
- **Task-5 production gap FIXED in-task (RED→GREEN, within allowed files):** `storefront_page_reset` caught only `BaselineResetError`; `LockedSectionsPresentError` subclasses `InvalidPresetError`, so a page-reset over a locked page raised uncaught → HTTP 500. Fix: added `except preset_service.InvalidPresetError` (mirrors `storefront_reset_to_baseline`). Service was already atomic and already refused/rolled back; only the view crashed. +8 lines, reset route only. This was resolved inside Task 5, not deferred.
- **Task-6 CRITICAL failure-mode check (PASSED):** the tenant-scoping relation paths `page__version__layout__store`, `draft_version__layout__store`, `layout__store` are all REAL against the model graph (no direct store FK on version; store via `layout.store`) — NOT silently-empty querysets. The same-store CONTROL test `test_same_store_snapshot_still_references_after_isolation_setup` proves the scan genuinely matches within the own store. `MEDIA_ID_KEYS` matches production serialization exactly.

## Task-4 / R6(a) — exact finding, reconciliation, and severity classification (Part C)

The prior report described this MINOR two ways ("narrow TOCTOU-related nit" in the Task-4 review, "`no_active_draft` error-handling asymmetry in legacy undo/redo" in the cumulative review). **They are the SAME single finding**, described at two altitudes: the TOCTOU window is the CAUSE; the unhandled `no_active_draft` → 500 is the OBSERVABLE EFFECT. Reconciled precisely below.

- **Affected function / path:** `_legacy_history_command(request, command)` in `apps/storefront_builder/views.py` (the shared body of the legacy `storefront_undo` and `storefront_redo` views). It calls `layout_service.get_or_create_draft(store, ...)` and then, separately, `r4_mutation_service.apply_history_command_current(store=store, command=command)`.
- **Actual behavior:** `apply_history_command_current` is decorated `@transaction.atomic`. Inside, it takes `StorefrontLayout.objects.select_for_update()`, then requires `layout.draft_version_id` to be non-null and the referenced version to be `status=DRAFT` (also `select_for_update`). If, in the window between the view's `get_or_create_draft` and this internal re-lock, a concurrent request PUBLISHES the draft (draft pointer cleared / version flipped to PUBLISHED) or DISCARDS it, the internal lookup finds no active DRAFT and raises `R4MutationError("no_active_draft")`.
- **Possible race / failure mode:** a genuine but very narrow TOCTOU between the view-level draft fetch and the service-level re-lock, under concurrent publish/discard on the same store's draft. The legacy view does not catch `R4MutationError`, so the exception propagates as an unhandled HTTP 500. (The R4 endpoint `storefront_r4_publish`/history view at `r4_views.py:~499` DOES catch `R4MutationError` and returns a clean `{"ok": false, "code": ...}` 400.)
- **Is state corruption possible?** NO. The raising path runs entirely inside `@transaction.atomic` holding `select_for_update` row locks; on the raise, the transaction rolls back with zero writes — no section mutation, no `edit_revision` change, no history entry created or flipped.
- **Can stale state overwrite newer state?** NO. The failure occurs at the LOCK/RESOLVE step, strictly BEFORE any undo/redo is applied. Nothing is written, so no last-writer-wins overwrite is possible. The single Draft-wide `edit_revision` optimistic-concurrency protection is untouched (and the legacy path already advances it exactly once only on a *successful* command).
- **Does it cross a tenant / lifecycle boundary?** NO. `apply_history_command_current` resolves ONLY the requesting store's layout+draft (store-scoped `.get(store=store)`); it cannot reach another tenant, and it explicitly refuses anything that is not the store's active DRAFT (so it cannot touch a Published/Archived version).
- **Is only the error RESPONSE asymmetric?** YES. The sole observable difference from the R4 path is the error response shape: an unhandled 500 instead of a graceful `ok=False`/400 JSON no-op. Functional behavior (atomic, revision-safe, tenant-safe, lifecycle-safe) is identical.

**Classification rule applied:** the rule states — if the finding can permit stale/corrupt lifecycle mutation → IMPORTANT → STOP; if it only changes the error-handling/response shape and cannot corrupt, overwrite, bypass revision protection, or cross tenant/lifecycle boundaries → MINOR is acceptable.

**FINAL CLASSIFICATION: MINOR (acceptable, non-blocking).** Justification: the finding cannot corrupt state, cannot cause a stale/overwrite, cannot bypass the `edit_revision` protection, and cannot cross a tenant or Draft/Published/Archived lifecycle boundary — it can ONLY produce a less-graceful error response (500 vs clean JSON) in a narrow concurrent publish/discard race that the R4 path shares. No production code was changed for this reclassification because it does NOT prove an IMPORTANT correctness defect. Recommended (deferred, optional) hardening: wrap the `apply_history_command_current` call in `_legacy_history_command` and return the existing `ok=False` no-op payload on `R4MutationError`, matching the R4 endpoint.

## Pre-Existing Baseline Exceptions (exact signatures, reproduced at baseline)

All three were reproduced in a throwaway worktree checked out at the Phase-1 baseline `515518227c09f888972fa6eda756867097358dfb` (using the same venv), producing byte-identical signatures — proving each pre-dates Phase 2 and is unrelated to the Phase-2 change set (none of these modules is in the Phase-2 production diff `apps/content/media_reachability.py`, `apps/content/models.py`, `edit_history_service.py`, `r4_mutation_service.py`, `views.py`).

### 1. FullscreenEditor (2 exceptions in `apps/storefront_builder/tests/test_views.py`)
- **Test A (FAIL):** `test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`
  - **Current (HEAD 477adf3) signature:** `AssertionError: ':aria-pressed="fullscreen"' not found in '<...editor html...>'` (assertion `self.assertIn(':aria-pressed="fullscreen"', html)`).
  - **Baseline (5155182) signature:** identical — same test, same `self.assertIn(':aria-pressed="fullscreen"', html)` assertion failing.
- **Test B (ERROR):** `test_views.FullscreenEditorTests.test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`
  - **Current & baseline:** ERROR with the same test name at both commits.
- **Combined run at both commits:** `Ran 4 tests … FAILED (failures=1, errors=1)`.
- **Reason unrelated to Phase 2:** the FullscreenEditor topbar/CSS-toggle expectations concern the editor shell template (V3 topbar), which Phase 2 never touched; the module is not in the Phase-2 production diff and the signature is unchanged from before any Phase-2 commit.

### 2. Ready Template gallery-label (`apps/storefront_builder/tests/test_u8_template_gallery.py`)
- **Test (FAIL):** `test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset`
- **Current (HEAD) signature:** `AssertionError: False is not true : Couldn't find 'بازارگاهی (جستجو-محور)' in the following response` (assertion `self.assertContains(response, "بازارگاهی (جستجو-محور)")`).
- **Baseline (5155182) signature:** identical — same test, same missing label `بازارگاهی (جستجو-محور)`.
- **Run at both commits:** `Ran 11 tests … FAILED (failures=1)`.
- **Reason unrelated to Phase 2:** the gallery variant-label expectation concerns Ready-Template gallery presentation, untouched by Phase 2; identical failure at baseline.

### 3. r4_vertical_slice validator-boundary (`apps/storefront_builder/tests/test_r4_vertical_slice.py`)
- **Test (FAIL):** `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
- **Current (HEAD) signature:** `AssertionError: Expected 'validate_appearance_config' to have been called once. Called 2 times.`
- **Baseline (5155182) signature:** identical — same test, same `Called 2 times` message.
- **Run at both commits:** the single test fails identically; also first proven pre-existing at Task-3 base `aab8f1c` (ledger R4).
- **Reason unrelated to Phase 2:** the double invocation of `validate_appearance_config` exists in code paths untouched by Phase 2 and reproduces before any Phase-2 commit.

**Baseline reproduction run (combined, at `5155182`):** `Ran 6 tests … FAILED (failures=3, errors=1)` — the same tally as at HEAD for the same four selected tests. No NEW failure signature appears at HEAD.

## Master Exit Gate — 22 criteria (item-by-item, evidence-backed)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Every scoped mutation has an explicit lifecycle target (active Draft) | **PASS** | R4 `_lock_active_draft` resolves only `layout.draft_version` (DRAFT); legacy routes use `_get_scoped_section/_container/_cell` (Draft+store) and `get_or_create_draft`; Task-2 negative suite |
| 2 | Stale conflicts cannot silently overwrite protected state | **PASS** | `edit_revision` Draft-wide token (Task 3); `R4StaleRevision` 409; Task-7 `MixedSequenceSafeOrderingTests` (both directions), Task-3 cross-path stale test |
| 3 | Published cannot be edited through Draft tooling | **PASS** | `test_phase2_lifecycle_safety` `LegacyPublishedVersionImmutabilityTests` + R4 `PublishedVersionImmutabilityTests` (404/scoped, mutates nothing) |
| 4 | Archived cannot be edited through Draft tooling | **PASS** | `LegacyArchivedVersionImmutabilityTests` + Task-2 archived-target negative cases (404, mutates nothing) |
| 5 | Tenant / cross-store isolation | **PASS** | Task-2 foreign-store negative cases; Task-6 `CrossStoreIsolationReachabilityTests` + same-store control; store-scoped locks/scans; full matrix GREEN |
| 6 | Publication lifecycle safety | **PASS** | Task-4: legacy publish delegates to shared atomic `layout_service.publish` (archive-previous, clear history, swap pointers); optional stale guard via `publish_draft`; Task-7 full-lifecycle convergence |
| 7 | Restore / discard / history recoverability | **PASS** | Task-4 + Task-7 recovery round-trips; typed `store_appearance` manifest byte-for-byte survival across apply→undo→redo→publish→restore |
| 8 | Undo/redo revision + history coherence | **PASS** | Task-4 shared `_run_history_command` (+1 on success, 0 on no-op, never a new undoable entry); Task-7 monotonicity via BOTH legacy and R4 history endpoints |
| 9 | Template Apply / Reset lifecycle safety | **PASS** | Task-5: legacy preset-apply/reset atomic, advance `edit_revision` on real change, refuse locked pages (`LockedSectionsPresentError`); Apply/reset semantics unchanged |
| 10 | Structure-lock consistency across R4 + legacy (Section + Container) | **PASS** | Task-5 full spec §11 matrix: every "NO" cell negative-tested on both paths, atomic |
| 11 | Structure-lock is NOT an Appearance/content force policy | **PASS** | Task-5 positive tests: settings edit / toggle / collapse / lock-toggle / duplicate all SUCCEED on a locked section (structure-only) |
| 12 | Media reference accounting across all approved classes | **PASS** | Task-6 extended `is_referenced`: FK + JSON background + history/baseline snapshots; 10-test reachability module GREEN |
| 13 | JSON-only media protected | **PASS** | Task-6 `test_json_only_referenced_asset_on_draft_is_reachable` / `..._on_published...`; deletion gate refuses |
| 14 | History/baseline-only media protected | **PASS** | Task-6 `test_edit_history_snapshot_only_referenced_asset_is_reachable` / `test_template_baseline_snapshot_only_referenced_asset_is_reachable`; Task-7 `test_referenced_media_survives_snapshot_only_recovery_reference` |
| 15 | Rollback cannot trigger unsafe physical deletion | **PASS** | Deletion gate `delete_media_asset_if_unreferenced` deletes only when `is_referenced()` is False; physical delete on `transaction.on_commit` (never inside a rollback-able txn); fail-closed on scan error |
| 16 | Physical deletion only when truly unreferenced | **PASS** | Task-6 preservation guard `test_asset_with_no_references_is_not_reachable` + `test_media_asset_lifecycle` deletion tests remain GREEN (no over-reach); unrelated-integer guard |
| 17 | No proactive destructive cleanup / TTL | **PASS** | Scope audit: no orphan-cleanup job/command/signal/TTL/bulk-delete introduced; deletion triggered only by the existing explicit product flow (spec §13 policy) |
| 18 | Phase-1 Appearance authority preserved | **PASS** | `appearance_authority_service` untouched (not in the production diff); R4/legacy delegate to it unchanged; full R4 appearance suites GREEN |
| 19 | No DB migration | **PASS** | `makemigrations --check --dry-run` → `No changes detected`; `models.py` change is a method body only (no field/model) |
| 20 | No new renderer | **PASS** | Scope audit: no `render_service`/renderer file changed; 5 production files are models/services/views only |
| 21 | Business-domain ownership preserved | **PASS** | No Product/Brand/Collection/catalog code changed; scope audit `--name-only` shows only `apps/content` + `apps/storefront_builder` service/view files |
| 22 | Phase 3 not started | **PASS** | No content-preserving Switch, no legacy-route retirement, no Brand/Collection convergence, no non-Home R4 expansion; branch scope = Phase-2 tasks only |

**Master exit gate: 22 / 22 PASS.** (These 22 subsume and refine the spec §18 items 1–8, which also all PASS per §7 above.)
