# W5A — Class C Concurrency Contract (Restore Version / Apply Industry Layout)

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

## The new locking helper

`r4_mutation_service._lock_layout_for_identity_replacement(*, store, expected_base_revision)`:

- `expected_base_revision` is `None` **or** a non-negative `int` — never any other type (validated at the view layer before this is called).
- Locks the Store's `StorefrontLayout` row with `select_for_update()` — the same row every other Draft-identity-replacing action locks.
- **`expected_base_revision is None`** (client believes there is no active Draft): under the lock, if `layout.draft_version_id is not None`, another process has since created/replaced a Draft — raise `R4StaleRevision(current_revision_of_that_draft)`. If still `None`, proceed.
- **`expected_base_revision` is an int** (client believes an active Draft exists with exactly this `edit_revision`): under the lock, if `layout.draft_version_id is None` (the Draft the client expected has since been discarded/replaced), or the located Draft's `edit_revision` doesn't match, raise `R4StaleRevision(current_or_None)`. Otherwise proceed.
- Returns the locked `layout` object. No Draft object is guaranteed to exist in the return value — callers do not assume one.

## No TOCTOU gap

The entire sequence — lock, precondition check, and the call into the existing `layout_service.restore_version()`/`apply_industry_layout()` — happens inside **one** `@transaction.atomic` block, with the `StorefrontLayout` row lock held from `_lock_layout_for_identity_replacement` through to the end of the wrapper function. `layout_service.restore_version()`/`apply_industry_layout()` each call `get_or_create_layout(store)` internally, which performs a plain (non-locking) read — but because it executes inside the *same* database transaction/connection that already holds the row lock, it observes the transaction's own consistent view and cannot race with a concurrent writer (any other transaction attempting to lock the same row blocks until this one commits or rolls back). There is no "check, release lock, then call service" gap of the forbidden shape.

## Wrapper functions — no business-logic duplication

```python
@transaction.atomic
def restore_version_safe(*, store, actor, base_revision, version_id):
    _lock_layout_for_identity_replacement(store=store, expected_base_revision=base_revision)
    try:
        return layout_service.restore_version(store, version_id, user=actor)
    except layout_service.CrossStoreVersionError as exc:
        raise R4MutationError("version_not_found") from exc

@transaction.atomic
def apply_industry_layout_safe(*, store, actor, base_revision, force=False):
    _lock_layout_for_identity_replacement(store=store, expected_base_revision=base_revision)
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

## Wire contract (view layer)

`base_revision` in the JSON request body:
- Absent, or any type other than `null`/non-negative-int → `400 {"code": "invalid_base_revision"}`.
- `null` → `expected_base_revision=None` (client expects no active Draft).
- Non-negative int → `expected_base_revision=<int>` (client expects the active Draft's `edit_revision` to match exactly).

Responses:
- `R4StaleRevision` → `409 {"ok": False, "code": "stale_revision", "current_revision": <int-or-null>}`.
- `R4MutationError` (any other) → `400 {"ok": False, "code": str(exc)}`.
- Success → `200 {"ok": True}` — client reloads (same convention as Reset Storefront/Switch Template; this is a whole-Draft-identity replacement, not an in-place edit).

## Cross-Store / tenant isolation

`store` is resolved once, per-request, via the existing `resolve_store_for_service(request)` (the sole tenant-resolution authority). The `StorefrontLayout` row locked and the `version_id` passed to `restore_version()` are both scoped to that `store` — `layout_service.restore_version()` already raises `CrossStoreVersionError` if the requested version does not belong to the resolved Store's own `layout.versions`, which the wrapper translates to `R4MutationError("version_not_found")` (400, not a data leak — matches the existing legacy view's own `Http404` convention for the same case, adapted to the JSON contract).
