# W5A — Independent Code Review

Review scope: `git diff feature/phase5-design-expansion..HEAD` on `feature/phase5-w5a-canonical-editor-safety`, run via the repository's `code-review` skill at effort level `high`, focused specifically on concurrency/transaction boundaries/row locking/TOCTOU, tenant isolation, Class A/B/C correctness, accidental route blocking, rollback preservation, duplicate business logic/authorities, response consistency, and Style Pack naming.

## Findings

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

CRITICAL: 0
IMPORTANT: 0 (after fixes — Findings 2 and 3 were fixed; Finding 1 is a documented, pre-existing, out-of-scope architectural gap, not a defect in this diff)

Affected tests re-run after fixes: `apps.storefront_builder.tests.test_phase5_w5a_canonical_editor_safety` (50/50 pass), `manage.py check` (clean).
