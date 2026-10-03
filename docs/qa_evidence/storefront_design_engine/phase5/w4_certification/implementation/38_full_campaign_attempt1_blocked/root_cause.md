# W4C Full 704-Cell Campaign — Attempt 1 — BLOCKED (infrastructure limit, not a harness/source defect)

## Summary

The first real, unbounded (`--w4c-all50`, no `--only`) 704-cell campaign
attempt crashed with an unhandled `RateLimitExceeded` exception after
successfully recording 15 Ready Templates (180 Base cells: 15 × 12).
It never reached the Theme Tier-1/Tier-2 phase. This is a genuine,
pre-existing production safety control that no prior W4C smoke ever
exercised, because every prior smoke used `--only <one-key>` and thus
only ever applied a single Ready Template preset per run.

## Exact failure

```
apps.core.services.rate_limit.RateLimitExceeded: تعداد تلاش برای
«storefront_layout.new_draft» بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید
```

Traceback origin: `handle()` → `_run_w4c_campaign()` →
`_ensure_published_with_recovery()` → `_apply_and_verify_published()` →
`preset_service.apply_preset_with_checkpoint()` →
`layout_service.get_or_create_draft()` →
`apps.core.services.rate_limit.enforce_rate_limit("storefront_layout.new_draft",
str(store.pk), max_attempts=30, window_seconds=3600)`.

Full output: `campaign_output_and_crash.txt`.

## Root cause

`apps/storefront_builder/services/layout_service.py`:

```python
_NEW_DRAFT_RATE_LIMIT = dict(max_attempts=30, window_seconds=3600)
```

`enforce_rate_limit` is a simple `django.core.cache`-backed fixed-window
counter, keyed on `f"ratelimit:storefront_layout.new_draft:{store.pk}"`.
This repository has no `CACHES` setting, so Django's default
`LocMemCache` (process-local, in-memory) backend is in effect — the
counter lives only for the lifetime of one `manage.py` process and is
NOT persisted across process restarts.

The W4C campaign applies each of the 50 Ready Template presets to the
SAME single Store (`rasti-mode-demo`) in sequence, in the same process,
and each preset-apply calls `get_or_create_draft` (a rate-limited
action) more than once (consistent with the observed numbers: exactly
15 Templates completed before the crash, and 15 × 2 = 30 == the
configured `max_attempts`, so the 16th Template's very first call was
attempt #31). This 30-attempts-per-hour limit is a legitimate anti-abuse
control designed for normal human/admin usage (repeatedly starting new
drafts through the editor UI) — it was never designed for, or tested
against, an automated campaign that intentionally applies 50 different
presets to one Store in rapid succession.

## Templates recorded before the crash (15 of 50, alphabetical-looking
but actually the fixture's own internal order)

1. dense_marketplace
2. premium_leather
3. warm_boutique
4. fashion_promo_catalog
5. playful_lifestyle
6. utility_catalog
7. editorial_jewelry
8. dark_digital
9. cedar_home
10. street_drop
11. premium_leather_noir
12. search_market
13. artisan_grain
14. pixel_play
15. simorgh_market

**Crashed applying preset #16: `coastal_product`** (confirmed by
reproducing `Command._build_w4c_fixture(store)`'s own internal
`templates` order in a Django shell — this key is exactly next in that
order, and no log/result file exists for it, consistent with the crash
occurring before any Node invocation for it).

## Why this is NOT repaired in this session

Per this round's directive (Section 1: "If a source/harness repair
becomes necessary at any point: STOP the campaign. Do NOT repair in
place... Any code change creates a new HEAD and requires a completely
fresh campaign root."), this is exactly that case. A genuine repair
here requires an Architect-level decision among several real
tradeoffs, none of which are mine to pick unilaterally mid-campaign:

- Raise `_NEW_DRAFT_RATE_LIMIT.max_attempts` (risks weakening a real
  anti-abuse control for production, not just QA).
- Add a QA-only bypass/allowance for the campaign's own service account
  (a new code path, a new security-relevant carve-out).
- Have the harness pace itself (sleep/backoff) to stay under the
  window, or split the 50-Template run into multiple sub-hour batches
  each in a fresh process (since the limiter is process-local
  `LocMemCache`, a fresh `manage.py` process gets a fresh budget) —
  viable operationally, but changes the harness's execution contract.
- Apply presets to per-Template throwaway Stores instead of one shared
  Store (a much larger architectural change).

None of these were authorized by this round's directive, so none were
attempted. **No harness file, no production template, and no Django
service file were modified in this attempt.**

## State of the world after the crash

- `git status --short`: empty (worktree unchanged throughout).
- Local database restore: `pre=<sha256> post=<sha256> match=True` —
  the harness's own exception-safe `finally`-equivalent restore ran
  correctly even on this unhandled crash, confirmed in
  `campaign_output_and_crash.txt`.
- `matrix.json` (preserved, NOT deleted, NOT hand-edited): records
  `w4c_branch_head_sha = bedcb3b0aac35b4b4db9689370b69a1fa9d04262`
  (exactly the approved campaign HEAD), `run_finished_at: null`, and
  the 15 Templates' 180 genuinely-recorded Base cells (`matrix_partial.json`
  in this same evidence folder).
- Every one of the 15 recorded Templates' 12 Base cells: all real
  browser-executed results (not fabricated), available in
  `w4c-results/base/*.json` and `logs/base/*.log` inside the (preserved,
  not deleted) campaign root `/tmp/rastisi_w4c_campaign_bedcb3b0`.
- No screenshots, evidence, or reports were materialized into the repo
  from this partial run (per Section 9, materialization only happens
  after matrix closure, which did not occur).
- No PR was opened (Section 20's conditions are unmet by a wide margin).

## What a resumed attempt needs

Per this round's own Section 5, a resume must reuse the SAME campaign
root and the SAME exact git HEAD, executing only missing cells. That
mechanism is intact and unaffected by this crash. However, blindly
resuming right now — or in any fresh process — will hit the identical
wall after roughly another 15 Templates (unless the resume is broken
into batches small enough, and spaced far enough apart in wall-clock
time, to stay under 30 draft-creation attempts per rolling hour on this
Store), because the underlying rate limit is a real per-Store
production control, not a harness artifact. That pacing/batching
decision — or a genuine rate-limit exemption for QA — needs Architect
authorization before either is attempted.
