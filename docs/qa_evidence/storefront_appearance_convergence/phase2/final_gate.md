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
