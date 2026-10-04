# Pre-existing failures — reproduced on Python 3.12 via a CLEAN CLONE (no stash)

Runtime: **Python 3.12.13, Django 5.2.17**.

## Method (no stash, no reset, no clean)
1. W2 branch full suite: `python manage.py test apps.storefront_builder.tests`
   → `Ran 3159 tests — FAILED (failures=30, errors=2, skipped=4)`, exit 1.
   Sorted failure set → `15_w2_312_failures.txt` (32 lines).
2. A **separate clean clone** at `/projects/sandbox/base_repro`, checked out to
   the certified base `b7d8ac281389870877553f5a308af3e77dcdd7f0` (W2 code absent
   — `theme_catalog.py` does not exist there), own Python 3.12.13 venv.
   Full suite → `Ran 3102 tests — FAILED (failures=30, errors=2, skipped=4)`,
   exit 1. Sorted failure set → `14_base_312_failures.txt` (32 lines).
3. Set comparison (Python; `diff` unavailable in sandbox):

```
BASE count: 32 | W2 count: 32
W2-ONLY (must be empty): (none)
BASE-ONLY: (none)
EMPTY DIFF: True
```

## Reason-level comparison (not only test names)
Beyond the sorted test-name lists, the COMPLETE raw stdout/stderr of both runs
is preserved (`17_w2_full_suite_raw.txt`, `18_base_full_suite_raw.txt`) and
compared by failure REASON (exception type + searched token/operands + failing
`self.assert…` call, with the incidental embedded rendered-HTML haystack
stripped). Result: W2-only = none, base-only = none, changed-reason = none.
See `19_failure_reason_comparison.md`. This proves no already-failing test fails
for a *different* W2-induced reason.

## Result
The W2-branch failure set is **identical by test-identity AND by failure reason**
to the clean certified-base failure set on Python 3.12. **W2 introduces ZERO
regressions.**
The 30 failures + 2 errors are PRE-EXISTING at `b7d8ac28` (Ready-Template
reference-contract / mobile-nav / fullscreen-topbar / template-gallery /
validator-boundary tests asserting frozen preset versions & reference
silhouettes; none touch the Theme family or the appearance engine W2 modifies).

The W2 test count is higher (3159 vs 3102) purely because W2 ADDS 57 passing
`test_w2_theme_overlay` tests (and other minor additions); every W2 test passes.

Note on the Repair-A transient-candidate regression: it was found, fixed, and
locked with a regression test BEFORE this comparison — the earlier interim run
(21 preview errors) is fully resolved; the final diff above is empty.

Raw artifacts: `04_full_storefront_builder_suite.txt` (W2 tail),
`16_base_full_suite.txt` (base tail), `14_base_312_failures.txt`,
`15_w2_312_failures.txt`.
