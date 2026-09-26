# W5A — Independent Code Review

Review scope: `git diff feature/phase5-design-expansion..HEAD` on `feature/phase5-w5a-canonical-editor-safety`, run via the repository's `code-review` skill at effort level `high`, focused specifically on concurrency/transaction boundaries/row locking/TOCTOU, tenant isolation, Class A/B/C correctness, accidental route blocking, rollback preservation, duplicate business logic/authorities, response consistency, and Style Pack naming.

## Round 2 — Independent Architect Final Review Repair

The Independent Architect's PR review found IMPORTANT 2 / BLOCKING MINOR 1 this round-1 review missed:

### 4. `storefront_section_collapse_toggle` misclassified as a justified Class-A exclusion — FIXED

**Architect's claim**: `collapsed_in_editor` is a member of `edit_history_service._SECTION_FIELDS` and the view is decorated with `@_record_edit_history`, so it is a real, persisted Draft mutation that participates in Draft history — the round-1 "cosmetic-only, zero render effect" justification for leaving it unguarded was wrong.

**Verification**: direct source read confirmed both claims exactly as stated.

**Fix applied**: guarded with the same shared `_require_legacy_editor_active` decorator as every other Class-A route, in the same position (`@permission_required` → `@_require_legacy_editor_active` → `@_record_edit_history`). The round-1 test `test_section_collapse_toggle_is_not_blocked` (asserting it stayed reachable) was replaced with three tests proving the opposite: `test_section_collapse_toggle_fails_closed` (R4-enabled → 404), `test_section_collapse_toggle_blocked_request_mutates_nothing` (the blocked POST changes neither `collapsed_in_editor`, `edit_revision`, nor the edit-history entry count), and `test_section_collapse_toggle_still_works_when_pinned_back` (R3-pinned → unchanged). `route_classification.md`/`final_report.md` updated: Class A exclusions for persisted Draft writes is now **0**.

### 5. Class-C precondition was revision-only — an ABA hazard — FIXED

**Architect's claim**: `edit_revision` defaults to `0` on every new Draft row. A stale client that captured Draft A's identity+revision-0 could incorrectly pass the precondition check against an unrelated Draft B that replaced A and also happens to be at revision 0 — the round-1 contract checked revision alone, never Draft identity.

**Verification**: confirmed by direct source read of `_lock_layout_for_identity_replacement` (round 1) and reproduced the exact scenario in a new regression test before fixing it (genuine RED).

**Fix applied**: the precondition now binds to BOTH the expected Draft identity (its PK, reusing the existing Draft PK — no new token/model) and its revision; see `concurrency_contract.md` for the full corrected wire contract. Both `restore_version_safe`/`apply_industry_layout_safe`, `_read_class_c_precondition` (renamed from `_read_class_c_base_revision`), and both `storefront_r4_restore`/`storefront_r4_apply_industry_layout` views were updated; both UI callers (`history.html`, `editor.html`) now render and submit `base_draft_id` alongside `base_revision`, sourced from the same server-rendered Draft state. New regression coverage: `test_r4_safe_restore_rejects_wrong_draft_id_with_coincidentally_equal_revision` / `test_r4_safe_industry_apply_rejects_aba_stale_draft_identity_even_with_matching_revision` (the exact ABA scenario — Draft A revision 0 replaced by Draft B also at revision 0, stale request against A rejected, B untouched), plus explicit precondition-shape rejection tests (negative/non-integer values, inconsistent null pairing) and a same-identity/different-identity split of the pre-existing stale-precondition tests. The lock/transaction boundary itself (no TOCTOU gap) is unchanged by this fix — only the comparison performed under the existing lock changed.

### 6. `RateLimitExceeded` from the existing, unmodified rate limits escaped as an unhandled 500 — FIXED

**Architect's claim**: `layout_service.restore_version()`/`apply_industry_layout()` both call `enforce_rate_limit(...)` (existing, unmodified — `storefront_layout.restore`/`storefront_layout.new_draft`), which can raise `RateLimitExceeded`; the new R4 Class-C JSON endpoints did not translate it, so exceeding the pre-existing limit would surface as an unhandled 500.

**Verification**: confirmed — no `RateLimitExceeded` handling existed anywhere in `r4_views.py`, and the rate limit itself is enforced as the very first statement inside both `layout_service` functions, before any Draft row is touched.

**Fix applied**: both views now catch `RateLimitExceeded` and return a controlled `429 {"ok": False, "code": "rate_limited"}` — no existing limit was loosened, no new limiter was created, the translation is purely at the HTTP boundary. New regression tests (`test_r4_safe_restore_rate_limit_exhaustion_returns_controlled_response`, `test_r4_safe_industry_apply_rate_limit_exhaustion_returns_controlled_response`) reuse the repository's own established convention for simulating exhaustion (temporarily monkeypatching `layout_service._RESTORE_RATE_LIMIT`/`_NEW_DRAFT_RATE_LIMIT` to `max_attempts=0` in a try/finally, the same pattern `test_layout_service.py`'s own rate-limit tests already use) and assert no Draft is created/replaced on rejection.

### Test-modification re-review (§11)

Re-reviewed every one of the 88 tests the round-1 `bf39b8fb` patch pinned to `r4_editor_enabled=False` (across 17 files), per the Architect's rule: pin only where a test genuinely exercises a legacy/R3 route; for tests that deliberately cross R3 and R4 in one method, flip the flag only around the corresponding call, preserving the original cross-mode semantics; never weaken an assertion to force green.

- `git diff e88ebac0..HEAD` on the 18 affected test files shows **581 insertions, 5 deletions** — the 5 deletions are exactly the 4-line block replaced in `_run_lifecycle_via_r4`'s Restore step (swapped for the new R4-safe endpoint call, per Finding 5, with a *stronger* assertion added — `resp.json()["ok"]` — not a weaker one). No other line in any of the 17 pinned files was deleted or altered; every other change is a pure line-insertion.
- This round's own investigation (triggered by an uncontended exact-source full-suite run showing 25 spurious identities) already found and fixed 3 latent bugs from the blanket-pin approach — a wrong module alias (14 tests) and 11 tests whose blanket pin broke their own R4-path assertions (2 of which additionally targeted the wrong Store fixture) — see the `full_suite_identity_comparison.md`/commit `6019a82e` history for the full account. Those fixes already apply the exact per-call-site flag-flip discipline this rule requires.
- Empirical confirmation: the clean, uncontended exact-source full-suite run at the final HEAD (`full_suite_identity_comparison.md`) shows **0** new failure/error identities versus the accepted baseline — if any further test among the 88 had a latent cross-mode or wrong-target bug of this class, it would present as a new failure identity in that same run. None does.

## Round 1 Findings

### 1. Ready Template Apply (Class B) has no stale-write check on its legacy entry point

**Reviewer's claim**: `storefront_apply_layout_preset` mutates the Draft with no `base_revision` check, the same hazard class W5A converged Restore/Industry-Layout away from; the reviewer additionally claimed the route-classification doc's justification ("converges on the same canonical `preset_service.apply_preset()` authority `appearance.template.apply` (R4) uses") didn't match the source, comparing it against `switch_template_preserving_content` instead.

**Verification**: direct source read of `r4_mutation_service.py::_apply_appearance_template` (the `appearance.template.apply` mutation handler) confirms it calls `preset_service.apply_preset(draft, preset)` directly — the exact same low-level function the legacy `apply_preset_with_checkpoint()` wraps. The route-classification doc's claim is factually correct; the reviewer compared against the wrong R4 capability (`switch_template_preserving_content` is a separate, content-preserving DNA-only switch with no legacy equivalent at all, not the full-apply counterpart).

**Disposition: considered, not actioned.** The underlying safety observation (no stale-write check on the legacy Apply-Preset path) is real, but it is not a defect introduced by W5A — it is a pre-existing property of `apply_preset()`, already identified in the very first W5 discovery round's `gap_matrix.md` ("Stale-write protection... absent for legacy R3 form POSTs"), and the Independent Architect's own binding Class A/B/C model (established across two prior review rounds) deliberately scoped the required Restore/Industry-Layout conversion to the two operations that **replace the Draft's identity** (delete the row, create a new one) — a structurally more dangerous class of operation than `apply_preset()`, which mutates fields on the *existing* Draft row in place. Ready Template Apply was explicitly classified Class B — "CANONICAL KEEP... not a retirement candidate" — by the Phase-4 legacy-disposition audit and reaffirmed in the approved master plan this workstream implements. The master plan instructs: "Treat the approved Class A/B/C classification... as binding. Do not silently redesign it," and forbids expanding scope beyond the plan without stopping to report it. Converting Apply-Preset would (a) contradict that binding classification, (b) expand W5A's scope into Ready-Template-recipe/apply territory explicitly listed as forbidden in the master plan's §19, and (c) risk destabilizing the Gallery's shared, both-editors entry point. **Recorded here as a residual, pre-existing, already-known-and-accepted architectural gap for a future, explicit Architect/Product-Owner decision — not fixed in W5A.**

### 2. `force` parameter accepted a truthy non-boolean string — FIXED

**Reviewer's claim**: `force = bool(payload.get("force", False))` coerces any non-empty string (including the literal string `"false"`) to `True` in Python, silently defeating the "never silently overwrite an already-published storefront" confirm gate.

**Verification**: confirmed by direct read — `bool("false")` is `True`. A client sending `{"force": "false"}` intending *not* to force would have force applied anyway.

**Fix applied**: `storefront_r4_apply_industry_layout` now requires `force` to be a strict JSON boolean (`isinstance(force_raw, bool)`); any other type is rejected with `400 {"code": "invalid_force"}`, never silently coerced. A regression test (`test_r4_safe_industry_apply_rejects_truthy_string_force`) proves the string `"false"` is rejected outright and the published storefront/Draft state is left untouched.

### 3. Unanchored CSRF-cookie regex in the two new inline scripts — FIXED

**Reviewer's claim**: the new `document.cookie.match(/csrftoken=([^;]+)/)` (in `history.html` and one block in `editor.html`) is unanchored, unlike the pre-existing safe pattern already used elsewhere in the same template family (`editor.html`'s own `csrfToken()` helper: `/(?:^|; )csrftoken=([^;]+)/`), risking a match against an unrelated cookie whose name/value happens to contain the substring `csrftoken=`.

**Verification**: confirmed — a plain, unanchored substring match is a real (if narrow) inconsistency with the codebase's own established-safe convention for exactly this operation.

**Fix applied**: both new occurrences now use the same anchored pattern (`/(?:^|; )csrftoken=([^;]+)/`) as the pre-existing `csrfToken()` helper.

## Concurrency / transaction / row-locking review (self-verified, no findings)

- `_lock_layout_for_identity_replacement` and both Class C wrapper functions were re-read line-by-line against the concurrency contract (`concurrency_contract.md`): the `StorefrontLayout` row lock (`select_for_update()`) is acquired once, the precondition check happens under that lock, and the call into `layout_service.restore_version()`/`apply_industry_layout()` happens before the lock is released (both wrapper functions are `@transaction.atomic`, and the row is never re-queried outside that transaction) — no release-then-call gap.
- Confirmed via `test_r4_safe_restore_rejects_stale_active_draft_precondition`/`..._industry_apply_rejects_stale_precondition` (and the two `ClassCConcurrencyBoundaryTests`) that a stale precondition leaves the newer Draft completely untouched — not partially mutated.

## Tenant isolation review (self-verified, no findings)

- Every Class C entry point resolves `store` once via `resolve_store_for_service(request)`; the `StorefrontLayout` row locked and the `version_id`/`industry_installation` used are both derived from that resolved Store only. `restore_version_safe` translates a cross-Store `CrossStoreVersionError` into a 400, never leaking whether the requested version PK exists under a different Store. `apply_industry_layout_safe`'s installation lookup (`getattr(store, "industry_installation", None)`) is a `OneToOneField` from the resolved Store — structurally incapable of resolving another Store's installation. Both paths are covered by `test_r4_safe_restore_cross_store_fails_closed`/`test_r4_safe_industry_apply_cross_store_fails_closed`.

## Class A/B/C correctness, accidental blocking, rollback (self-verified, no findings beyond Finding 1)

- Full route audit in `route_classification.md`; every Class A route confirmed guarded, every Class B route confirmed unguarded (with a passing test for the merchant-visible ones), History browser confirmed read-only and unconditionally reachable, both Class C legacy routes confirmed gated closed under R4 and unchanged under R3-pinned.
- No module-wide guard exists — `_require_legacy_editor_active` is applied only to the explicit, named Class A + legacy-Class-C list; `test_ready_template_gallery_remains_reachable`/`test_ready_template_apply_remains_reachable`/`test_draft_preview_remains_reachable` directly prove Class B survives.

## Duplicate business logic / authorities (self-verified, no findings)

- `restore_version_safe`/`apply_industry_layout_safe` call the existing, byte-for-byte unmodified `layout_service.restore_version()`/`apply_industry_layout()` — confirmed by `git diff` showing zero changes to `layout_service.py`.
- No second Draft model, renderer, Ready Template registry, mutation dispatcher, tenant resolver, or stale-write contract introduced — `r4_mutation_service.R4StaleRevision`/`R4MutationError` (already existing) are reused verbatim.
- No second R3/R4 editor-state flag — the existing `StorefrontLayout.r4_editor_enabled` is the sole switch consulted by both the new guard and the new Class C endpoints.

## Outcome

**Round 1**: CRITICAL 0, IMPORTANT 0 (Findings 2 and 3 fixed; Finding 1 documented, pre-existing, out-of-scope, not a defect in this diff).

**Round 2 (Independent Architect PR review)**: CRITICAL 0, IMPORTANT 2, BLOCKING MINOR 1 at review time — all three (Findings 4, 5, 6) fixed and verified in this round; test-modification re-review (§11) completed with no further latent issues found.

**Final**: CRITICAL 0, IMPORTANT 0, BLOCKING MINOR 0.

Affected tests re-run after round-2 fixes: `apps.storefront_builder.tests.test_phase5_w5a_canonical_editor_safety` (60/60 pass), `manage.py check` (clean), plus the clean exact-source full-suite regression (`full_suite_identity_comparison.md`, round 2) confirming 0 new failure/error identities.
