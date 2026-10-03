# W4C Pilot Findings Closure — Cart tablet remove reproduction (Section 7)

Per Section 7: three fresh repetitions, each a fresh external root,
`--only editorial_jewelry --w4c-tier2-budget 0` (safely below the
approved rate-limit budget), at HEAD `9f0d103e...` (the Home
expectation repair's own final source commit at the time of this
investigation).

## Command (identical for all three repetitions, only `--report-dir` differs)

```
manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo \
  --username w4c_qa_owner --w4c-all50 --only editorial_jewelry \
  --w4c-tier2-budget 0 --report-dir <fresh root> --settings=shop_core.settings
```

## Results

| Repetition | Root | Desktop | Tablet | Mobile | SQLite restore |
|---|---|---|---|---|---|
| 1 | `/tmp/rastisi_w4c_cart_diag_1` | `removed: true` | `removed: true` | `removed: true` | PASS |
| 2 | `/tmp/rastisi_w4c_cart_diag_2` | `removed: true` | `removed: true` | `removed: true` | PASS |
| 3 | `/tmp/rastisi_w4c_cart_diag_3` | `removed: true` | `removed: true` | `removed: true` | PASS |

All three repetitions: `real_remove: {"attempted": true, "before": 1,
"after": 0, "removed": true}` on every viewport. `cumulative_fail_count: 0`
in all three runs.

## Verdict

**The Tablet failure did NOT reproduce in 3/3 fresh repetitions.**

Per Section 7's explicit instruction ("If Tablet never fails again: do
NOT declare the issue solved. Treat it as suspected harness flakiness
and proceed to instrumentation"), this is treated as **suspected
harness synchronization flakiness, not a confirmed production defect,
and not yet solved**. Proceeding to Section 8 (diagnostic
observability instrumentation in `run.mjs`) to determine the actual
mechanism, per the directive's explicit warning that the existing
helper's `click().catch(() => {})` (swallows click errors) +
fixed-`waitForTimeout(500)` pattern is "insufficient evidence to call
this a production tablet bug."
