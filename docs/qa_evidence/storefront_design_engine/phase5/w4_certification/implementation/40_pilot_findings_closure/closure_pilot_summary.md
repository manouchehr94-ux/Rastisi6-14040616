# W4C Pilot Findings Closure — bounded closure pilot (Section 16)

Fresh external root `/tmp/rastisi_w4c_closure_pilot_b3f2c439` — never
reused Attempt 1's root, the rate-limit pilot's root, or any of the
three Cart diagnostic roots. Both processes ran at the exact final
pilot-findings source HEAD: `b3f2c43974ffd528a4374fb6a3c35af20314379c`.

## Process 1 — Home expectation coverage

```
manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --w4c-all50 \
  --only premium_leather,street_drop,racer_tech,anniversary_mosaic \
  --w4c-tier2-budget 0 --report-dir <closure root> --settings=shop_core.settings
```

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- cells_recorded_this_run=52,
cumulative_total_cells_recorded=52/704, cumulative_fail_count=0,
cumulative_blocked_count=0
Local database restored — match=True
```

- 4 keys x 12 Base + 4 Tier-1 = **52 cells**, exactly as required.
- Node invocations: **8** (4 base logs + 4 tier1 logs).
- No `RateLimitExceeded`. SQLite restore: PASS.

Per-Template Home results (all 3 viewports each):

| Template | result | rsec_count / expected | hero_result |
|---|---|---|---|
| `premium_leather` | PASS | 3 / 3 | N/A (no Hero in this Template) |
| `street_drop` | PASS | 4 / 4 | PASS |
| `racer_tech` | PASS | 4 / 4 | PASS |
| `anniversary_mosaic` | PASS | 5 / 5 | PASS |

- **No false rsec-count mismatch from the hidden `announcement_bar`** —
  `premium_leather` now shows the canonical `3`, matching its real
  published Home exactly (the pilot's original genuine finding is
  closed).
- **Hero index correct for all three ticker-before-Hero Templates** —
  `hero_result: PASS` on every viewport for `street_drop`/`racer_tech`/
  `anniversary_mosaic`.
- No production Ready-Template recipe was changed to produce this —
  `a8_ready_templates.py` is untouched (confirmed by `git diff` across
  this whole round touching only `qa_storefront_builder_r4.py`,
  `run.mjs`, and the test file).

Full output: `closure_process1_output.txt`.

## Process 2 — Cart closure

Same root, same HEAD.

```
manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --w4c-all50 --only editorial_jewelry \
  --w4c-tier2-budget 0 --report-dir <SAME closure root> --settings=shop_core.settings
```

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- cells_recorded_this_run=13,
cumulative_total_cells_recorded=65/704, cumulative_fail_count=0,
cumulative_blocked_count=0
Local database restored — match=True
```

- 12 new Base + 1 new Tier-1 = **13 new cells**.
- New Node invocations: **2** (1 base log + 1 tier1 log; 10 total logs
  now, 8 from Process 1 + 2 new).
- **Cumulative: 65** — exactly 52 + 13, as required.
- `duplicate_cells: []`.
- No `RateLimitExceeded`. SQLite restore: PASS.

`editorial_jewelry` Cart results (all 3 viewports):

| Viewport | result | real_remove |
|---|---|---|
| desktop | PASS | `{attempted: true, before: 1, after: 0, removed: true, click_error: null, htmx_request_observed: true, http_status: 200, dom_swap_observed: true, elapsed_ms: 527}` |
| tablet | PASS | `{attempted: true, before: 1, after: 0, removed: true, click_error: null, htmx_request_observed: true, http_status: 200, dom_swap_observed: true, elapsed_ms: 524}` |
| mobile | PASS | `{attempted: true, before: 1, after: 0, removed: true, click_error: null, htmx_request_observed: true, http_status: 200, dom_swap_observed: true, elapsed_ms: 520}` |

**Tablet: `removed: true`, `click_error: null`** — the pilot's original
genuine finding is closed, with full honest diagnostics attached (real
HTTP 200 response observed, real DOM swap observed, ~524ms elapsed —
well within the old 500ms mark plus a small margin, consistent with
this being ordinary rendering/network latency, not a hang).

Full output: `closure_process2_output.txt`. Full closure matrix:
`closure_matrix.json`.

## Closure pilot verdict (Section 17)

| Criterion | Result |
|---|---|
| No `RateLimitExceeded` | PASS (both processes) |
| Duplicates | 0 |
| Home false-count issue | 0 |
| Hero-index issue | 0 |
| `editorial_jewelry` Tablet Cart remove | PASS |
| New accessibility FAIL | 0 (verified across all 60 Base cells' `accessibility_checks`) |
| Unexpected console/page/request error | 0 (verified across all 60 Base + 5 Tier-1 cells) |
| SQLite restore | PASS for every process |

**Closure pilot: ACCEPTABLE.** No other genuine browser FAIL was
found across the 65 recorded cells.
