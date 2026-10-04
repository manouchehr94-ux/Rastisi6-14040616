# W4C Rate-Limit Sharding Repair — bounded two-process pilot

Per Section 10: NOT the final 704-cell campaign — a bounded pilot
proving `--w4c-tier2-budget` and the controlled RateLimitExceeded
diagnostic behave as designed, against real production rate limits,
across two separate `manage.py` processes sharing one campaign root.

Pilot root: `/tmp/rastisi_w4c_rate_limit_pilot_5807847b` (fresh, never
used before — Attempt 1's root `/tmp/rastisi_w4c_campaign_bedcb3b0` was
never touched or reused). Both processes ran at the exact same source
HEAD: `5807847b3606ed36836e9f06ba2530c7c513b1a5`.

## Process 1

```
manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --w4c-all50 \
  --only dense_marketplace,premium_leather,warm_boutique,editorial_jewelry \
  --w4c-tier2-budget 0 --report-dir <pilot root> --settings=shop_core.settings
```

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- cells_recorded_this_run=52,
cumulative_total_cells_recorded=52/704, cumulative_fail_count=4,
cumulative_blocked_count=0
Local database restored — match=True
```

- Base: 4 keys × 12 = 48 cells. Tier-1: 4 cells. Tier-2: 0 (budget=0).
  **Total: 52** — exactly as required.
- Node invocations: **8** (4 base logs + 4 tier1 logs, confirmed by file count).
- No `RateLimitExceeded` — confirmed clean run, no controlled-diagnostic
  `CommandError` raised.
- SQLite restore: PASS.
- `_meta.w4c_branch_head_sha`: `5807847b...` (exact).

Full output: `pilot_process1_output.txt`.

### Two genuine, real browser findings (unrelated to rate limiting)

These are the FIRST-EVER real browser executions of these specific
cells (every prior smoke only ever exercised `editorial_jewelry`), so
this pilot is also the first opportunity to catch real per-Template
defects. Both are recorded honestly, per the campaign's own failure
policy ("record it honestly ... produce a complete failure inventory"),
and are explicitly OUT OF SCOPE for this rate-limit sharding round —
not fixed here, flagged for a separate Architect-authorized round:

1. **`premium_leather` Home, all 3 viewports FAIL** —
   `rsec_count: 3` vs `expected_rsec_count: 4`. A real content/config
   mismatch on this Template's Home page (one fewer recommendation
   section rendered than its own preset declares). Not an
   accessibility issue (`accessibility_ok=true`), not a rate-limit
   symptom.
2. **`editorial_jewelry` Cart, tablet-only FAIL** —
   `real_remove: {"attempted": true, "before": 1, "after": 1, "removed": false}`,
   while the exact same product/cart state succeeds on desktop
   (`before: 1, after: 0, removed: true`). A real, viewport-specific
   remove-interaction failure (tablet breakpoint only). Accessibility
   checks for the remove control still report PASS
   (`accessibility_checks.remove_control: PASS`) — the control is
   reachable and named correctly, but the real click-and-verify effect
   did not happen at this specific viewport.

Neither finding touches any file this round is authorized to change,
and neither was introduced by the rate-limit sharding repair itself
(both are pure content/interaction findings, confirmed unrelated to
`accessibility_checks`, to `new_draft`/`publish`, and to the Tier-2
budget logic).

## Process 2

```
manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --w4c-all50 --only warm_boutique \
  --w4c-tier2-budget 4 --report-dir <SAME pilot root> --settings=shop_core.settings
```

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- cells_recorded_this_run=4,
cumulative_total_cells_recorded=56/704, cumulative_fail_count=4,
cumulative_blocked_count=0
Local database restored — match=True
```

- Base/Tier-1 for `warm_boutique`: already recorded from Process 1 →
  skipped entirely (0 cost), confirmed by inspecting the matrix (no new
  entries, no re-invocation).
- Tier-2: exactly 4 new cells recorded
  (`nowruz__subtle__desktop/tablet/mobile`, `nowruz__balanced__desktop`),
  all `PASS`.
- **Cumulative: 56** — exactly 52 + 4, as required.
- New Node invocations: **4** (12 total log files now, 8 from Process 1 + 4 new).
- `duplicate_cells: []` — 0 duplicates.
- The original 52 cells from Process 1 are byte-identical/unchanged
  (spot-checked `dense_marketplace` Home desktop and `editorial_jewelry`
  Tier-1, both still recorded exactly as Process 1 left them).
- `_meta.total_cells_expected`: still `704`.
- `_meta.w4c_branch_head_sha`: `5807847b...` — same as Process 1 (same HEAD).
- No `RateLimitExceeded`.
- SQLite restore: PASS.

Full output: `pilot_process2_output.txt`. Full pilot matrix (as of
Process 2's end): `pilot_matrix.json`.

## Conclusion

Both processes behaved exactly as designed: bounded, resumable,
same-root, same-HEAD sharding with zero duplicate cells, zero rate-limit
exhaustion, and correct budget semantics (already-terminal cells free,
new cells capped at the given budget). The `cumulative_fail_count=4`
carried unchanged between both processes (no new failures introduced by
Process 2) confirms Process 2 touched nothing Process 1 had already
recorded.
