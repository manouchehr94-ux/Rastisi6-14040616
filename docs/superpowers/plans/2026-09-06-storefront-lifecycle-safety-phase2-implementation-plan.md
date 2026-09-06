# Storefront Appearance Convergence — Phase 2: Lifecycle & Safety Implementation Plan

> **For agentic workers:** Execute task-by-task, in order. Each task ends with tests + evidence + a bounded commit. RED before GREEN where behavior changes. No `TODO`/`TBD`. No invented APIs or test modules. No destructive Git. No push unless separately authorized.

**Goal:** Give every Appearance/Builder-owned mutation an explicit, safe lifecycle contract — active-Draft targeting, `edit_revision` stale-write coherence, atomicity, history/recovery integrity, structure-lock consistency, and complete media reachability (close A05) — WITHOUT rewriting the canonical Phase-1 write authority, business domains, or the renderer, and WITHOUT deleting legacy routes.

**Spec:** `docs/superpowers/specs/2026-09-06-storefront-lifecycle-safety-phase2-design.md`
**Baseline:** `515518227c09f888972fa6eda756867097358dfb` (merged Phase-1). Branch `feature/storefront-lifecycle-safety-phase2`, worktree `/projects/rastisi5_phase2`, venv `/projects/rastisi5_phase2_venv` (Python 3.12.13 / Django 5.2.17).

**Tech stack:** Python 3.12, Django 5.2, Django TestCase/SimpleTestCase, existing storefront_builder + content services. All test commands use `/projects/rastisi5_phase2_venv/bin/python manage.py test ...`.

---

## Global constraints

- Phase scope is **Phase 2 — Lifecycle & Safety only**. Phase 1 canonical Appearance authority is CLOSED; do not reopen it unless a direct Phase-2 lifecycle defect proves it necessary (then STOP).
- Preserve Products, Brands, Categories, Collections, pricing, stock, Cart, Orders, Auth, tenant/store authorization, ShopSettings, and the shared render engine.
- **No DB migration is expected.** `edit_revision` already exists on `StorefrontLayoutVersion`; media reachability is a read-time check. If any task appears to require a schema migration, STOP and escalate — do NOT create a migration.
- No new renderer, no new component families/variants, no Template 51+, no legacy route deletion, no Page Override, no Store force-all Appearance policy, no content-preserving Template Switch, no orphan-cleanup job, no media TTL, no bulk/destructive media deletion.
- Physical media file deletion stays on `transaction.on_commit`; reachability checks are fail-closed and tenant-scoped.
- Every behavior change follows RED → GREEN → focused regression → evidence → commit.

## File map (authoritative, verified at baseline)

**Production (in scope — may be modified where a task allows):**
- `apps/storefront_builder/services/layout_service.py` — lifecycle (draft/publish/discard/restore/checkpoint/clone).
- `apps/storefront_builder/services/r4_mutation_service.py` — R4 strong mutation boundary.
- `apps/storefront_builder/services/edit_history_service.py` — undo/redo/snapshot/restore.
- `apps/storefront_builder/services/preset_service.py` — template apply/reset/baseline.
- `apps/storefront_builder/services/section_structure_service.py` — R4 structural ops + lock checks.
- `apps/storefront_builder/services/container_service.py` — container/cell ops + lock checks.
- `apps/storefront_builder/views.py` — legacy dashboard mutation/lifecycle/reset routes.
- `apps/storefront_builder/media_views.py` — media placement CRUD + deletion trigger.
- `apps/content/models.py` — `MediaAsset.is_referenced`, placements.
- `apps/content/services.py` — `delete_media_asset_if_unreferenced`, `resolve_background_media_url`.

**Out of scope / forbidden to modify (Phase 2):** `appearance_authority_service.py` (Phase 1; touch ONLY on a proven contract defect → STOP first), `render_service.py`, `settings_schema.py`, `models.py` schema/migrations, catalog/cart/orders/stores/accounts business domains, templates/CSS/JS.

**Test modules (existing, reuse where they cover an invariant):** `test_r4_mutation_api`, `test_r4_store_appearance_mutations`, `test_layout_service`, `test_storefront_page`, `test_phase27_history_identity`, `test_u1a_preset_edit_history_characterization`, `test_phase5_composition_lifecycle`, `test_phase35a_publish_container_invariant`, `test_preset_service`, `test_u7_ready_template_baseline`, `test_stable_section_identity`, `test_media_asset_lifecycle`, `test_media_write_path`, `test_media_views`, `test_g2_1_media_editability_roundtrip`, `test_g22_preview_media_render_consistency`.

**New Phase-2 test modules (create only for genuinely new invariants):**
- `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py` (characterization + convergence: Tasks 1–5, 7)
- `apps/content/tests/test_phase2_media_reachability.py` (media A05: Task 6) — or `apps/storefront_builder/tests/test_phase2_media_reachability.py` if the content app has no `tests/` package; the executor MUST confirm the real test package location before creating it (do not invent a package).

**Evidence directory:** `docs/qa_evidence/storefront_appearance_convergence/phase2/`.

## Gap register (from `lifecycle_media_inventory.md`)

| ID | Sev | Gap | Task |
|---|---|---|---|
| L01 | P1 | Legacy view mutations do not advance `edit_revision`; concurrent legacy tab / legacy-vs-R4 can silently overwrite newer Draft state (last-writer-wins). | Task 3 |
| L02 | P1 | Legacy `storefront_publish` has no base-revision/stale guard (unlike R4 `publish_draft`); a stale tab can publish over newer Draft state. | Task 4 |
| L03 | P2 | Legacy `storefront_undo`/`storefront_redo` call `edit_history_service` directly with no revision guard and no `edit_revision` advance. | Task 4 |
| L04 | P2 | Preset apply + reset endpoints (legacy) advance no `edit_revision`; a concurrent client is unaware the Draft changed. | Task 5 |
| L05 | P2 | No explicit negative test that a legacy/R4 editing path cannot mutate a Published or Archived version (behavior is correct by scoping, but untested for several paths). | Task 1 (RED) + Task 2 |
| L06 | P2 | Structure-lock enforcement is not proven complete/consistent across BOTH R4 (`section_structure_service`) and legacy views for Section and Container (matrix untested). | Task 5 |
| L07 | **P0** | **A05:** `MediaAsset.is_referenced()` is blind to JSON `settings.background.media_asset_id` and to history/baseline snapshots; `delete_media_asset_if_unreferenced` can physically delete a still-referenced/recoverable asset. | Task 6 |
| L08 | P2 | No test proves atomic rollback for legacy mutation / publish / reset paths (Phase-1 proved it only for preset apply and R4). | Task 1 (RED) + relevant task |
| L09 | P3 (DEFERRED → Phase 4) | Legacy routes remain co-active with R4; retirement/deletion is Phase 4, not Phase 2. | DEFERRED |
| L10 | P3 (DEFERRED → later) | No proactive orphan-media cleanup job / retention TTL. Phase 2 only makes deletion *safe*. | DEFERRED |

Every non-deferred gap maps to a task below. Deferred gaps are explicitly out of Phase-2 scope.

---

# Task 0 — Baseline, Decision Lock, Inventory (COMPLETE in preparation)

**Status:** DONE during Phase-2 preparation. Artifacts: this plan, the spec, `docs/qa_evidence/storefront_appearance_convergence/phase2/baseline.md`, `docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md`.

**Master-run note:** The master execution begins at Task 1. Task 0 requires no further work beyond confirming pre-flight at Task 1 start.

---

# Task 1 — RED Lifecycle & Media Characterization (tests only)

**Preconditions:** clean worktree at `feature/storefront-lifecycle-safety-phase2`; HEAD = the preparation commit or a documented descendant; G2.3 ancestor (exit 0).

**Allowed production files:** NONE (tests only).
**Forbidden:** all production files.
**Test files:** create `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`; create the media reachability test module in the confirmed `content` (or storefront_builder) test package.

**Steps:**
1. Characterize L05: a legacy `storefront_section_settings` / structural POST scoped to a **Published** version's section must be rejected/not-found (assert no mutation). Add for R4 too if not already covered by `test_r4_mutation_api.test_section_on_published_version_is_not_mutable_via_r4`.
2. Characterize L01: two sequential legacy mutations on the same Draft — assert current behavior that `edit_revision` does NOT advance on a legacy mutation (RED against the desired invariant). Record baseline value.
3. Characterize L07 (media A05) — the core RED: create a `MediaAsset`, reference it ONLY via `StorefrontSection.settings["background"]["media_asset_id"]` (no FK placement), assert `MediaAsset.is_referenced()` currently returns `False` (the defect) — i.e. a JSON-only-referenced asset is currently deletable. Add a second case: asset referenced only by an edit-history/baseline snapshot.
4. Run only the new module(s) `--verbosity 2`. Expected: intentional REDs for L01/L07 desired-invariant tests; GREEN for the Published-immutability characterization (already-correct behavior).

**Exact RED expectation:** L01 desired-invariant assertion FAILS (edit_revision unchanged); L07 desired-invariant assertions FAIL (`is_referenced()` False for JSON-only / snapshot-only). Published-immutability tests PASS.
**Exact GREEN expectation:** no unexpected errors; only the intended REDs.
**Review dimensions:** tests use real routes/services and real fixtures; no fabricated APIs; each RED maps to a specific gap id.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task1_red_characterization.md`.
**Commit:** `test: characterize phase2 lifecycle and media reachability gaps`
**Stop conditions:** unexpected unrelated failure/exception → STOP. A "defect" test unexpectedly PASSING → do NOT force-fail; investigate and report (the baseline may already be safe).
**Next-task readiness:** REDs recorded, evidence committed, worktree clean.

---

# Task 2 — Published/Archived/Cross-store Mutation Protection (negative-test convergence)

**Preconditions:** Task 1 committed.
**Allowed production files:** `views.py`, `r4_mutation_service.py` — ONLY if a genuine missing guard is found (a path that CAN mutate Published/Archived/foreign). If all paths are already safe by scoping, this task adds tests only.
**Forbidden:** business domains, models schema, renderer, authority service.
**Test files:** extend `test_phase2_lifecycle_safety.py` (+ `test_layout_service`, `test_media_views` if a specific path needs a negative test).

**Steps:**
1. For every mutation family in the inventory (section settings/structural, container/cell, appearance/header/footer, media, publish/restore/discard, undo/redo, preset/reset), add a negative test that a Published version, an Archived version, and a foreign store's version cannot be mutated through that path.
2. If a path is found that CAN mutate a non-Draft/foreign version, add the minimal scoping guard (matching the existing `_get_scoped_*` / `_lock_active_draft` pattern) — RED test first, then fix.
3. Run the negative-test suite + `test_layout_service` + `test_r4_mutation_api` + `test_media_views`.

**RED expectation:** any newly-discovered unsafe path FAILS its negative test before the guard.
**GREEN expectation:** all negative tests GREEN after (if any) guard added; existing suites GREEN.
**Review dimensions:** no over-broad guard that breaks legitimate Draft edits; tenant scoping preserved; no business-domain change.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task2_published_archived_protection.md`.
**Commit:** `test: prove published/archived/cross-store mutation protection` (or `fix: guard <path> against non-draft mutation` if a guard was needed).
**Stop conditions:** a required guard would need a schema/model change → STOP. A path mutates business-domain data → STOP.
**Next-task readiness:** all negative tests GREEN; evidence committed.

---

# Task 3 — Draft-wide `edit_revision` Stale-Write Convergence (L01)

**Preconditions:** Task 2 committed.
**Allowed production files:** `views.py` (legacy mutation views), `layout_service.py` (a shared helper to advance revision if introduced), and `r4_mutation_service.py` only if refactoring the increment into a shared helper. Prefer a single small helper (e.g. in `layout_service` or `edit_history_service`) that advances `edit_revision` atomically, reused by legacy paths.
**Forbidden:** authority service, renderer, models schema/migration, business domains.
**Test files:** extend `test_phase2_lifecycle_safety.py`.

**Steps:**
1. GREEN the L01 desired invariant: every state-changing legacy Appearance/Builder mutation advances the Draft's `edit_revision` exactly once on success, inside its transaction, and NOT on a semantic no-op. Reuse the existing `@_record_edit_history` boundary (which already detects real change via before/after snapshot) as the natural place to advance the revision when a change is recorded — so revision advance and history recording stay coherent.
2. Ensure R4 and legacy now share the same monotonic token semantics: a change via legacy makes a concurrent R4 client's `base_revision` stale (rejected), and vice-versa.
3. Do NOT add a mandatory client-supplied base-revision to legacy form POSTs (no UI change); the guarantee is: atomic + revision-advance + history. Document the residual "two legacy tabs" last-writer-wins as accepted/bounded.
4. Run `test_phase2_lifecycle_safety` + `test_r4_mutation_api` + `test_r4_store_appearance_mutations` + `test_phase27_history_identity` + `test_u1a_preset_edit_history_characterization`.

**RED→GREEN:** L01 test flips to GREEN; no-op edits still do not advance revision or write history.
**Review dimensions:** revision advance is coherent with history (advances iff a history entry is recorded); no double-increment; R4 revision semantics unchanged; atomic; no migration.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task3_revision_convergence.md`.
**Commit:** `feat: converge draft edit_revision across legacy and r4 mutations`
**Stop conditions:** achieving revision advance requires a model/schema change → STOP (it must not; `edit_revision` exists). R4 revision tests regress → STOP.
**Next-task readiness:** L01 GREEN; R4 + history suites GREEN.

---

# Task 4 — Publish / Undo / Redo / Restore / Discard Lifecycle Safety (L02, L03)

**Preconditions:** Task 3 committed.
**Allowed production files:** `views.py` (`storefront_publish`, `storefront_undo`, `storefront_redo`, `storefront_discard`, `storefront_restore`), `layout_service.py`, `r4_mutation_service.py` (only to expose/reuse the shared publish/history lifecycle contract).
**Forbidden:** authority service, renderer, models schema/migration, business domains.
**Test files:** extend `test_phase2_lifecycle_safety.py` (+ `test_layout_service`, `test_phase27_history_identity`).

**Steps:**
1. L02: make legacy `storefront_publish` reach the same lifecycle guarantee as R4 `publish_draft` — publish is atomic, archives the previous published, clears draft history/pointer (already in `layout_service.publish`); ensure the legacy entry cannot publish a Draft whose `edit_revision` advanced under it without detection where a revision is available, or at minimum is fully atomic and lifecycle-correct. Prefer delegating legacy publish to the same lifecycle path R4 uses.
2. L03: make legacy `storefront_undo`/`storefront_redo` atomic and revision-coherent (advance `edit_revision` on a successful undo/redo, matching R4 `apply_history_command`), so undo/redo through either entry point is revision-monotonic.
3. Prove restore/discard remain atomic, Draft-lifecycle-correct, and recover canonical Appearance (typed manifest) intact; add round-trip tests (apply template → undo → redo → restore) asserting the typed `store_appearance` manifest survives.
4. Run `test_phase2_lifecycle_safety` + `test_layout_service` + `test_phase27_history_identity` + `test_u7_ready_template_baseline`.

**RED→GREEN:** L02/L03 invariants GREEN; recovery round-trip preserves the manifest and is revision-coherent.
**Review dimensions:** publish still archives previous published + clears history + swaps pointers atomically; undo/redo still never create a new undoable edit; revision monotonic; no business-domain change.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task4_publish_history_recovery.md`.
**Commit:** `feat: make legacy publish/undo/redo lifecycle- and revision-safe`
**Stop conditions:** publish/undo change would alter recovery semantics or require migration → STOP.
**Next-task readiness:** L02/L03 GREEN; lifecycle + history suites GREEN.

---

# Task 5 — Structure Lock + Lifecycle-Safe Template/Reset Operations (L04, L06)

**Preconditions:** Task 4 committed.
**Allowed production files:** `views.py` (reset/preset/lock routes), `section_structure_service.py`, `container_service.py`, `preset_service.py` (only to advance revision / confirm lock enforcement — NOT to change Apply semantics).
**Forbidden:** authority service, renderer, models schema/migration, business domains, new lock types.
**Test files:** extend `test_phase2_lifecycle_safety.py` (+ `test_preset_service`, `test_phase5_composition_lifecycle`).

**Steps:**
1. L06: prove the structure-lock operation matrix (spec §11) is complete and consistent across BOTH R4 (`section_structure_service`) and legacy views, for `Section.is_locked` and `Container.is_locked`. Add negative tests for every "NO" cell; add positive tests confirming lock does NOT block settings/appearance edits, toggle, or duplicate (structure-only). If a "NO" operation is found unguarded on either path, add the guard (RED first).
2. L04: ensure legacy preset apply + reset endpoints are atomic and advance `edit_revision` on real change (reuse Task-3 helper), and continue to refuse locked pages (`LockedSectionsPresentError`). Do NOT change Apply/reset semantics.
3. Run `test_phase2_lifecycle_safety` + `test_preset_service` + `test_u7_ready_template_baseline` + `test_phase5_composition_lifecycle`.

**RED→GREEN:** any unguarded lock operation FAILS then GREEN; preset/reset revision-coherence GREEN; lock stays structure-only (positive tests confirm settings edits allowed on locked sections).
**Review dimensions:** lock matrix identical on R4 and legacy; no content/appearance lock introduced; Apply semantics unchanged; atomic.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task5_lock_template_lifecycle.md`.
**Commit:** `feat: converge structure-lock and lifecycle-safe template operations`
**Stop conditions:** lock hardening would require a new lock field/migration or would lock content/appearance → STOP.
**Next-task readiness:** lock matrix + preset/reset suites GREEN.

---

# Task 6 — Media Reachability / Retention / Deletion Guard (L07 — A05, P0)

**Preconditions:** Task 5 committed. This is the P0 task.
**Allowed production files:** `apps/content/models.py` (`MediaAsset.is_referenced` — extend the check), `apps/content/services.py` (`delete_media_asset_if_unreferenced` — consume the extended check; keep `on_commit` file deletion). Optionally a small helper module in `content` for the JSON/snapshot scans. `media_views.py` only if the trigger needs to pass tenant context.
**Forbidden:** models SCHEMA change/migration (this is a read-time query change, not a field), business domains, renderer, authority service, any orphan-cleanup job.
**Test files:** the Phase-2 media reachability module created in Task 1; extend `test_media_asset_lifecycle` / `test_media_write_path`.

**Steps:**
1. Extend the reachability check so an asset is considered referenced if ANY of: (a) the 5 FK placement relations (existing), (b) any of the store's `StorefrontSection.settings["background"]["media_asset_id"]` across Draft/Published/Archived versions, (c) any `StorefrontEditHistoryEntry.before_state`/`after_state` payload referencing the asset id, (d) any `template_baseline_snapshot` referencing the asset id. Tenant-scoped; fail-closed (on query error/ambiguity, treat as referenced).
2. Keep `delete_media_asset_if_unreferenced` as the single deletion gate; it now calls the complete check. Physical file deletion stays on `transaction.on_commit`.
3. GREEN the Task-1 L07 REDs: JSON-only, Draft/Archived-JSON-only, and history/baseline-only referenced assets are NOT deleted; a genuinely unreachable asset still IS deleted (preserve existing FK behavior — do not regress `test_media_write_path` deletion tests).
4. Run `test_phase2_media_reachability` + `test_media_asset_lifecycle` + `test_media_write_path` + `test_media_views` + `test_g22_preview_media_render_consistency`.

**RED→GREEN:** L07 invariants flip to GREEN; existing media deletion/reference tests remain GREEN.
**Review dimensions:** no schema change/migration; tenant-scoped; fail-closed; no bulk/proactive deletion; `on_commit` file deletion preserved; check performance is bounded (store-scoped queries, not a full-table scan of all stores).
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task6_media_reachability.md`.
**Commit:** `fix: close A05 media reachability gap in deletion safety check`
**Stop conditions:** closing A05 appears to need a schema migration → STOP. The check would require deleting media to prove correctness → STOP (use non-destructive assertions on `is_referenced`/the guard). Any physical deletion of a referenced asset observed → STOP.
**Next-task readiness:** A05 closed; media suites GREEN; `makemigrations --check` clean.

---

# Task 7 — Cross-Entry Lifecycle Convergence + Recovery Proof

**Preconditions:** Task 6 committed.
**Allowed production files:** NONE expected (verification/convergence-proof task). If a cross-entry inconsistency is discovered, make the minimal fix in the owning service with a RED test first.
**Test files:** extend `test_phase2_lifecycle_safety.py` with end-to-end cross-entry scenarios.

**Steps:**
1. Prove R4 and legacy entry points converge on identical lifecycle behavior for: mutate → revision advance → publish → archive-previous → restore → undo/redo, with the typed manifest and media placements intact throughout.
2. Prove a mixed sequence (legacy edit, then R4 edit with the now-stale base_revision) is safely ordered/rejected — no silent overwrite.
3. Prove recovery after each operation restores canonical Appearance (Phase-1 manifest) and does not orphan or delete referenced media.
4. Run the full `test_phase2_lifecycle_safety` + media reachability module.

**RED→GREEN:** all cross-entry scenarios GREEN; no unexpected divergence.
**Review dimensions:** no new production behavior beyond minimal fixes; no scope creep; recovery + media integrity end-to-end.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/task7_cross_entry_convergence.md`.
**Commit:** `test: prove cross-entry lifecycle convergence and recovery safety`
**Stop conditions:** a discovered inconsistency needs an authority-service/renderer/schema change → STOP.
**Next-task readiness:** all scenarios GREEN.

---

# Task 8 — Final Phase-2 Regression / Architecture Gate (verification only)

**Preconditions:** Tasks 1–7 committed.
**Allowed production files:** NONE (evidence only).
**Test files:** NONE (run existing).

**Steps:**
1. Cumulative fresh code review of the Phase-2 production diff (`git diff 5155182..HEAD -- apps/`), using a fresh reviewer. Classify CRITICAL/IMPORTANT/MINOR/NONE.
2. Run the full Phase-2 regression matrix fresh (all lifecycle + media + R4 + preset + history modules from the File map). Record TOTAL/PASS/FAIL/ERROR.
3. Re-verify any pre-existing baseline exceptions (2 `FullscreenEditor` `test_views` + 1 gallery label) against their documented earlier commits; confirm no NEW regressions.
4. `manage.py check`; `makemigrations --check --dry-run` (expect clean / No changes).
5. Scope audit: `git diff --check`, `--stat`, `--name-only` from `5155182`; confirm NO migration, NO new renderer, NO business-domain change, NO legacy deletion, NO new variants.
6. Evaluate the §18 exit-gate checklist item-by-item with evidence (PASS/FAIL, no "assumed").

**Exit expectation:** 0 CRITICAL / 0 IMPORTANT; full matrix GREEN except documented pre-existing exceptions; check + migrations clean; all exit-gate items PASS.
**Evidence:** `docs/qa_evidence/storefront_appearance_convergence/phase2/final_gate.md`.
**Commit:** `docs: close storefront lifecycle safety phase2`
**Stop conditions:** any CRITICAL/IMPORTANT finding, any unexplained failure, any scope violation → do NOT write a PASS/closure commit; STOP and report.
**Next-task readiness:** Phase 2 PASS; awaiting Product Owner / Architect review before push/PR.

---

# Part M — Master Execution Readiness

This plan is written so a single later master run can execute Task 1 → Task 8 sequentially without architecture rediscovery. Each task above already specifies: starting preconditions, allowed/forbidden production files, test files, exact RED/GREEN expectation, review dimensions, evidence filename, commit message, stop conditions, and next-task readiness.

## Global STOP conditions (apply to every task in the master run)

STOP immediately (do NOT continue to the next task; report and await review) on any of:

- A CRITICAL architecture finding, or an IMPORTANT unresolved code-review finding.
- A required DB migration not pre-approved by this plan (none is; `edit_revision` exists, media reachability is read-time).
- Any need to migrate Product/Brand/Collection/ShopSettings ownership into Builder version snapshots.
- Any need for a new renderer or to modify `render_service.py` / `appearance_authority_service.py` / `settings_schema.py`.
- A tenant/cross-store boundary regression.
- Any unrecoverable/destructive media operation, or physical deletion of a still-referenced/recoverable asset.
- An unclear physical-deletion authorization (deletion must stay gated by the existing explicit product flow).
- Unexpected baseline divergence (HEAD not descended from `5155182`, or `origin/docs/storefront-appearance-convergence` moved unexpectedly).
- A production change outside the current task's allowed-files list.
- A test failure not explained by a proven pre-existing baseline issue (reproduce it against the documented earlier commit before classifying pre-existing).

Otherwise the master run may proceed task-to-task automatically, committing after each task (no push until separately authorized).

## Per-task quick reference (master run)

| Task | Focus | Allowed production files | New/extended tests | Commit |
|---|---|---|---|---|
| 1 | RED characterization | none | new phase2 lifecycle + media modules | `test: characterize phase2 lifecycle and media reachability gaps` |
| 2 | Published/Archived/cross-store protection | views/r4 (only if unguarded path found) | phase2 lifecycle + layout/media | `test: prove published/archived/cross-store mutation protection` |
| 3 | `edit_revision` convergence (L01) | views, layout_service (shared helper), r4 (helper reuse) | phase2 lifecycle + r4/history | `feat: converge draft edit_revision across legacy and r4 mutations` |
| 4 | publish/undo/redo/restore/discard (L02,L03) | views, layout_service, r4 | phase2 lifecycle + layout/history | `feat: make legacy publish/undo/redo lifecycle- and revision-safe` |
| 5 | lock matrix + template/reset (L04,L06) | views, section_structure_service, container_service, preset_service | phase2 lifecycle + preset/composition | `feat: converge structure-lock and lifecycle-safe template operations` |
| 6 | media reachability A05 (L07, P0) | content/models.py, content/services.py, media_views (context only) | media reachability + media lifecycle/write-path | `fix: close A05 media reachability gap in deletion safety check` |
| 7 | cross-entry convergence + recovery | none expected | phase2 lifecycle e2e | `test: prove cross-entry lifecycle convergence and recovery safety` |
| 8 | final gate | none | run existing | `docs: close storefront lifecycle safety phase2` |

## Task-count justification

Eight tasks (0–8) map 1:1 to the program-spec Phase-2 concerns and to the gap register. No artificial tasks were added: Task 0 is preparation (done), Tasks 1–7 are the engineering slices (RED → protection → revision → publish/history → lock/template → media A05 → cross-entry proof), and Task 8 is the verification gate. The media A05 gap (L07, P0) is isolated in its own task (Task 6) because it lives in a different app (`apps/content`) and is the single highest-severity gap.

---

# Self-review checklist (satisfied by this plan)

1. Every §18 exit criterion maps to task(s): tenant/lifecycle target → T2; stale-write → T3; publish/recovery → T4; lock → T5; media reachability → T6; cross-store regression → T2/T7; no-migration/no-renderer → global constraints + T8; final regression → T8. ✓
2. Every gap L01–L08 maps to a task; L09/L10 explicitly DEFERRED. ✓
3. Every task has exact test/evidence/commit gate + stop conditions. ✓
4. No placeholder text (no TODO/TBD). ✓
5. No Phase-3/4/5 scope creep (deferred items listed). ✓
6. No contradiction with Phase-1 canonical authority (authority service forbidden to modify except on proven defect → STOP). ✓
7. No invented media deletion policy (safe policy = retain-while-referenced/recoverable; no TTL/job). ✓
8. No invented DB migration (read-time checks; `edit_revision` pre-exists). ✓
9. Business-domain ownership preserved (forbidden-files list + stop conditions). ✓
10. One master prompt can execute the plan without architecture rediscovery (Part M + per-task specs). ✓
