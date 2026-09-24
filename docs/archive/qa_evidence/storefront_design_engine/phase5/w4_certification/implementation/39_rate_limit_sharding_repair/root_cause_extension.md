# W4C Rate-Limit Sharding Repair — full root cause confirmation (Section 1)

Confirmed by direct source reading of `apps/core/services/rate_limit.py`,
`apps/storefront_builder/services/layout_service.py`,
`apps/storefront_builder/services/preset_service.py`, and
`apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`,
plus the runtime cache backend, before any implementation.

## A. `storefront_layout.new_draft`

```python
_NEW_DRAFT_RATE_LIMIT = dict(max_attempts=30, window_seconds=3600)
```
(`layout_service.py`) — confirmed exactly as Attempt 1's own root-cause
analysis (`38_full_campaign_attempt1_blocked/root_cause.md`) found.

## B. `storefront_layout.publish`

```python
_PUBLISH_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
```
(`layout_service.py`, alongside `_RESTORE_RATE_LIMIT = dict(max_attempts=20,
window_seconds=3600)` for `restore_version`, which the W4C harness never
calls).

## C. Attempt 1 consumed the `new_draft` budget first — confirmed exactly

`apply_preset_with_checkpoint` costs 2 `new_draft` calls per genuine
Template switch (outer `get_or_create_draft` + `checkpoint_draft_
before_replacement`'s own unconditional call). Attempt 1 recorded
exactly 15 Templates before crashing on the 16th's preset apply:
`15 × 2 = 30 == max_attempts` exactly — the 16th Template's very first
`new_draft` call was attempt #31.

## D. Even a `new_draft`-only fix would still hit `publish` later

`layout_service.publish(store)` is called **unconditionally** on every
Template application (`Command._apply_and_verify_published`, line
1647-1648) — 1 `publish` hit per Template, key-switch or not. A
50-Template campaign therefore needs at least 50 `publish` calls for
Base alone, already 2.5× over the 20/hour `publish` budget, entirely
independent of the `new_draft` limit. Raising or bypassing only
`new_draft` (which this repair explicitly does NOT do) would not have
prevented a later crash on `publish`.

## E. Theme execution multiplies both limits further — confirmed exactly

Traced the real call graph for `Command._run_one_theme_cell` (see
`mutation_budget_proof.md` for the full per-step breakdown): a single
Theme cell can cost up to 3 separate `publish()` calls in one Python
call —

1. Template re-publication/verification (`_ensure_published_with_recovery`
   → `_apply_and_verify_published`'s unconditional `publish()`),
2. Theme cleanup publication (`_ensure_theme_none_with_recovery` →
   `_theme_cleanup_and_verify`'s own `publish()`, triggered on nearly
   every cell after the very first Theme cell in the whole campaign,
   since applying an occasion theme always leaves it non-none for the
   next cell's drift check),
3. the actual occasion-theme-application publication (`_run_one_theme_cell`'s
   own final `publish()`).

— and up to 4 `new_draft` calls in the same worst case (key switch +
drift). A 104-Theme-cell all-in-one process would therefore need up to
`104 × 3 = 312` `publish` calls and `104 × 4 = 416` `new_draft` calls —
more than 15× and 13× the real budgets respectively. This confirms an
all-in-one 104-Theme-cell process is structurally incompatible with the
production per-process mutation budget, independent of how Base cells
are sharded.

## F. Cache backend — confirmed at runtime, exactly as required

```
CACHE BACKEND: django.core.cache.backends.locmem.LocMemCache
```

Confirmed via `django.core.cache.cache.__class__` and the explicit
`CACHES` setting (`{'default': {'BACKEND':
'django.core.cache.backends.locmem.LocMemCache'}}`) — process-local, so
a fresh `manage.py` process starts with a genuinely empty rate-limit
counter for every action/store pair, while the real Store/Draft/
Published-Version database state persists normally across process
restarts. This is **not** a distributed cache (Redis/memcached), so no
STOP was triggered by this check; the approved process-sharding design
(Section 6/10) depends on exactly this property and is valid.

## Conclusion

All six confirmations (A-F) match the directive's expectations exactly.
The repair proceeds as scoped: bounded process sharding
(`--w4c-tier2-budget`) plus a controlled diagnostic, never a change to
the real rate limiter.
