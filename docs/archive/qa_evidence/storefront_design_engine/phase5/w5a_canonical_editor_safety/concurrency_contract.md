# W5A — Class C Concurrency Contract (Restore Version / Apply Industry Layout)

## Independent-Review repair (round 2) — the ABA finding

The Independent Architect proved the round-1 contract (`expected_base_revision`
alone) was vulnerable to an **ABA hazard**: `StorefrontLayoutVersion.edit_revision`
defaults to `0` on every newly created Draft row. If Draft A (revision 0) is
replaced by an unrelated Draft B that also happens to still be at revision 0
(every fresh Draft starts there), a stale client that only captured "revision
0" would incorrectly pass the precondition check against Draft B, silently
discarding it — even though the client never actually observed Draft B. A
revision-only check cannot distinguish "the Draft I saw is still current" from
"a DIFFERENT Draft that happens to share the same revision number is current".

**The fix: the precondition now binds to BOTH the expected Draft *identity*
(its primary key) and its revision — identity first, revision second.** No new
concurrency token or model was introduced; the existing Draft PK is reused as
the identity. This section documents the corrected contract; the "no TOCTOU
gap" reasoning from round 1 is unchanged and still holds — see below.

## Why `_lock_active_draft` cannot be reused as-is

Direct source read of `r4_mutation_service._lock_active_draft` (existing, used by every other whole-Draft-identity-replacing R4 action: `publish_draft`, `discard_draft`, `reset_page`, `reset_storefront`, `switch_template`):

```python
def _lock_active_draft(*, store, base_revision: int) -> StorefrontLayoutVersion:
    layout = StorefrontLayout.objects.select_for_update().get(store=store)
    if layout.draft_version_id is None:
        raise R4MutationError("no_active_draft")
    ...
```

It **unconditionally requires an active Draft to already exist** — every existing "replace Draft identity" action is only ever invoked from a state where a Draft is already open. Restore Version and Apply Industry Layout are different: both are legitimately reachable when **no** Draft currently exists (e.g. a Store with only a Published version, no open Draft, restoring an old version or installing an industry layout for the first time). Reusing `_lock_active_draft` unmodified would make the "no Draft yet" case impossible to express safely, which is exactly the gap the master plan's §9 requirement calls out.

## The new locking helper (corrected)

`r4_mutation_service._lock_layout_for_identity_replacement(*, store, expected_draft_id, expected_base_revision)`:

- `expected_draft_id`/`expected_base_revision` are **both** `None` (client believes there is no active Draft — Case B) **or both** set — a positive Draft pk and its non-negative `edit_revision` (client believes exactly that Draft is active at exactly that revision — Case A). Never one null and the other set — that shape is rejected as a `400 invalid_precondition` at the view layer, before this function is even called.
- Locks the Store's `StorefrontLayout` row with `select_for_update()` — the same row every other Draft-identity-replacing action locks.
- **Case B** (`expected_draft_id is None`): under the lock, if `layout.draft_version_id is not None`, another process has since created/replaced a Draft — raise `R4StaleRevision(current_revision, current_draft_id=<that Draft's pk>)`. If still `None`, proceed.
- **Case A** (`expected_draft_id` set): under the lock, if `layout.draft_version_id != expected_draft_id` — a DIFFERENT Draft is current, or none at all — raise `R4StaleRevision(current_revision_of_whatever_is_current_or_None, current_draft_id=layout.draft_version_id)` **regardless of what that Draft's own revision happens to be**. This is the line that closes the ABA hazard: identity mismatch is stale even when the revision number alone would have coincidentally matched. Only once identity matches does the function additionally verify `edit_revision == expected_base_revision`; a mismatch there raises the same exception.
- Returns the locked `layout` object. No Draft object is guaranteed to exist in the return value — callers do not assume one.

## No TOCTOU gap

The entire sequence — lock, precondition check, and the call into the existing `layout_service.restore_version()`/`apply_industry_layout()` — happens inside **one** `@transaction.atomic` block, with the `StorefrontLayout` row lock held from `_lock_layout_for_identity_replacement` through to the end of the wrapper function. `layout_service.restore_version()`/`apply_industry_layout()` each call `get_or_create_layout(store)` internally, which performs a plain (non-locking) read — but because it executes inside the *same* database transaction/connection that already holds the row lock, it observes the transaction's own consistent view and cannot race with a concurrent writer (any other transaction attempting to lock the same row blocks until this one commits or rolls back). There is no "check, release lock, then call service" gap of the forbidden shape. This reasoning is unaffected by the identity+revision fix — the fix only changed WHAT is compared under the lock, not WHEN.

## Wrapper functions — no business-logic duplication

```python
@transaction.atomic
def restore_version_safe(*, store, actor, base_draft_id, base_revision, version_id):
    _lock_layout_for_identity_replacement(
        store=store, expected_draft_id=base_draft_id, expected_base_revision=base_revision,
    )
    try:
        return layout_service.restore_version(store, version_id, user=actor)
    except layout_service.CrossStoreVersionError as exc:
        raise R4MutationError("version_not_found") from exc

@transaction.atomic
def apply_industry_layout_safe(*, store, actor, base_draft_id, base_revision, force=False):
    _lock_layout_for_identity_replacement(
        store=store, expected_draft_id=base_draft_id, expected_base_revision=base_revision,
    )
    installation = getattr(store, "industry_installation", None)
    if installation is None:
        raise R4MutationError("no_industry_installation")
    try:
        return layout_service.apply_industry_layout(
            store, installation.industry_template, user=actor, force=force,
        )
    except layout_service.StorefrontAlreadyPublishedError as exc:
        raise R4MutationError("storefront_already_published") from exc
```

Both wrappers call the **existing, unmodified** `layout_service.restore_version()`/`apply_industry_layout()` — the exact same functions the legacy (`r4_editor_enabled=False`) POST paths still use. No restore or industry-layout replacement logic is written twice.

## Wire contract (view layer) — corrected

`base_draft_id`/`base_revision` in the JSON request body (`_read_class_c_precondition`):
- Either key absent → `400 {"code": "invalid_precondition"}`.
- `base_draft_id=null` AND `base_revision=null` → Case B (client expects no active Draft).
- `base_draft_id=<positive int>` AND `base_revision=<non-negative int>` → Case A (client expects exactly that Draft at exactly that revision).
- Any other combination — one null paired with a non-null, a negative or non-integer id/revision — → `400 {"code": "invalid_precondition"}`, never a silent coercion or a 500.

Responses:
- `R4StaleRevision` → `409 {"ok": False, "code": "stale_revision", "current_revision": <int-or-null>, "current_draft_id": <int-or-null>}` (the `current_draft_id` field is new in this round — it lets a client distinguish "wrong revision, same Draft" from "an entirely different Draft is now current").
- `R4MutationError` (any other) → `400 {"ok": False, "code": str(exc)}`.
- `RateLimitExceeded` (the existing, unmodified `storefront_layout.restore`/`storefront_layout.new_draft` limits, enforced inside `layout_service.restore_version()`/`apply_industry_layout()` before any Draft row is touched) → `429 {"ok": False, "code": "rate_limited"}` — previously escaped as an unhandled 500; no limit was loosened and no second limiter was created.
- Success → `200 {"ok": True}` — client reloads (same convention as Reset Storefront/Switch Template; this is a whole-Draft-identity replacement, not an in-place edit).

## UI callers carry both values

`history.html`'s Restore button and `editor.html`'s Industry-Layout-Apply button both now render `data-r4-base-draft-id` alongside `data-r4-base-revision`, sourced from the same server-rendered Draft state the revision was already sourced from (`storefront_history`'s `current_draft_id`/`current_draft_revision` context, `draft.pk`/`draft.edit_revision` in the editor's minimal-compatibility surface) — never re-read immediately before the POST in a way that would defeat optimistic concurrency; both are the values captured at render time, exactly what the client believed when the page loaded.

## Cross-Store / tenant isolation

`store` is resolved once, per-request, via the existing `resolve_store_for_service(request)` (the sole tenant-resolution authority). The `StorefrontLayout` row locked and the `version_id` passed to `restore_version()` are both scoped to that `store` — `layout_service.restore_version()` already raises `CrossStoreVersionError` if the requested version does not belong to the resolved Store's own `layout.versions`, which the wrapper translates to `R4MutationError("version_not_found")` (400, not a data leak — matches the existing legacy view's own `Http404` convention for the same case, adapted to the JSON contract).
