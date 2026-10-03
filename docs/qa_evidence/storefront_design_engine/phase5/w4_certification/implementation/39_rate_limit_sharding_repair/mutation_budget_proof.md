# W4C Rate-Limit Sharding Repair — mutation budget proof

Per Section 7 of the directive: a real-call-graph-derived safety proof
that the two approved batch shapes stay below the production limits
(`storefront_layout.new_draft`: max 30/hour; `storefront_layout.publish`:
max 20/hour) with margin. This is evidence/plan documentation only — the
real rate limiter in `apps/core/services/rate_limit.py` and its
constants in `apps/storefront_builder/services/layout_service.py`
remain the single, unchanged, authoritative source of truth.

## Cache backend (Section 1.F)

```
CACHE BACKEND: django.core.cache.backends.locmem.LocMemCache
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
```

Confirmed at runtime (explicit `CACHES` setting, not merely Django's
implicit default). This is process-local: a fresh `manage.py` process
starts with an empty rate-limit counter for every action/store pair.
The underlying Store/Draft/Published-Version DATABASE state persists
across process restarts as normal (it is a real DB, not cached) — only
the rate-limit COUNTER resets per process. This is exactly what makes
process sharding (rather than in-process pacing) a valid strategy here.

## Real call graph (confirmed by direct source reading)

- `layout_service.get_or_create_draft(store)` calls
  `enforce_rate_limit("storefront_layout.new_draft", ...)` **only if**
  `layout.draft_version_id` is falsy (i.e., only when it must genuinely
  create a new draft row).
- `layout_service.publish(store)` calls
  `enforce_rate_limit("storefront_layout.publish", ...)`
  **unconditionally**, every single call, even a no-op-content publish.
  Crucially, `publish()` also **clears** `layout.draft_version` — so the
  very next `get_or_create_draft` call on that Store is guaranteed to
  need a genuinely new draft again.
- `preset_service.apply_preset_with_checkpoint(store, preset)`:
  1. `layout_service.get_or_create_draft(store, user=user)` — 1
     `new_draft` hit if no draft currently exists (always true right
     after a `publish()`), 0 otherwise.
  2. If the (possibly just-created) draft already matches `preset`
     exactly → returns immediately (cheap path, same key re-applied).
  3. Otherwise `layout_service.checkpoint_draft_before_replacement(...)`
     — internally calls `get_or_create_draft` again (free, a draft now
     exists from step 1) and then, only if that draft has any real
     content, its own unconditional `enforce_rate_limit("new_draft", ...)`
     — 1 more `new_draft` hit (the common case: switching to a
     different Ready Template).
- `Command._apply_and_verify_published` (the QA harness's own wrapper):
  `apply_preset_with_checkpoint(...)` then **always**
  `layout_service.publish(store)` — 1 `publish` hit, even when step 2
  above short-circuited.
- `Command._theme_cleanup_and_verify`: `get_or_create_draft` (1
  `new_draft`, draft was just cleared by the prior publish) +
  `layout_service.publish(store)` (1 `publish`).
- `Command._run_one_theme_cell` (one Tier-1 or Tier-2 cell):
  1. `_ensure_published_with_recovery` → `_apply_and_verify_published`
     (as above: 1-2 `new_draft`, 1 `publish`).
  2. `_ensure_theme_none_with_recovery`: if the theme is currently
     drifted (non-`theme.none.v1` — true for every cell after the very
     first Theme cell touched in the whole campaign, since applying an
     occasion theme always leaves it non-none for the next check) →
     `_theme_cleanup_and_verify` (1 `new_draft`, 1 `publish`); otherwise
     free.
  3. `draft = layout_service.get_or_create_draft(store)` — 1 more
     `new_draft` (the prior step's cleanup publish cleared it).
  4. `appearance_authority_service.apply_theme(...)` — 0 rate-limited
     calls (pure in-memory/DB mutation on the already-fetched draft).
  5. `layout_service.publish(store)` — 1 more `publish`.

  **Worst case per Theme cell (key switch + drift, i.e. the very first
  cell for a newly-introduced key in this process): 4 `new_draft` + 3
  `publish`.**
  **Steady-state per Theme cell (same key re-used, drift still true,
  i.e. consecutive Tier-2 cells for one key): 3 `new_draft` + 3
  `publish`.**

- Base cells: `_ensure_published_with_recovery` is called **once per
  KEY** (not per cell — one Node invocation runs all ≤12 missing Base
  cells for that key in a single browser session): worst case 2
  `new_draft` + 1 `publish` per key.

## Batch A — "4 ordinary Base+Tier1 Template keys, `--w4c-tier2-budget 0`"

Worst case (every key switch, i.e. 4 genuinely different Ready
Templates applied in sequence in one process):

| phase | per unit | units | new_draft | publish |
|---|---|---|---|---|
| Base | 2 nd + 1 p | 4 keys | 8 | 4 |
| Tier-1 | 4 nd + 3 p (key switch + drift, worst case) | 4 keys | 16 | 12 |
| **Total** | | | **24** | **16** |

`24 < 30` (6 units of margin) and `16 < 20` (4 units of margin) — both
under budget, consistent with the directive's own warning that 5 keys
would land `24×5/4 = 30` and `16×5/4 = 20` — **exactly** at both
ceilings, with **zero** margin. This confirms 4 (not 5) is the correct,
deliberately conservative batch size from the real call graph, not an
arbitrary guess.

## Batch B — "one key (`warm_boutique`), `--w4c-tier2-budget 4`"

Base and Tier-1 for `warm_boutique` are already recorded from Batch A
(skipped entirely by the existing IMPORTANT-3 resume logic — 0 cost).
Four Tier-2 cells for the SAME key, in one process:

| cell | scenario | new_draft | publish |
|---|---|---|---|
| 1st | key switch (from whatever key a prior process/shard last published) + drift | 4 | 3 |
| 2nd–4th | same key, drift | 3 each | 3 each |
| **Total (4 cells)** | | **4 + 3×3 = 13** | **3×4 = 12** |

`13 < 30` (17 units of margin) and `12 < 20` (8 units of margin) — a
larger, comfortable margin than Batch A, because no Base/Tier-1 work
repeats and there is only one Template key switch at most in the whole
shard.

## Conclusion

Both approved batch shapes stay strictly below the real, unchanged
production limits with a genuine (non-zero) safety margin, derived from
reading the actual service call graph rather than assumed. This is not
a new rate-limit system — it is a documented execution-safety
calculation the harness's own process-sharding schedule (Section 6 of
the directive) is built around. `apps/core/services/rate_limit.py` and
`apps/storefront_builder/services/layout_service.py`'s constants remain
untouched and authoritative.
