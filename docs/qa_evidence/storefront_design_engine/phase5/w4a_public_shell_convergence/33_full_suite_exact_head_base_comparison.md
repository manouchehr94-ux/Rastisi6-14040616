# P5-W4A — exact-head full-suite base comparison (round 4)

Compares `apps.storefront_builder.tests` at the **exact current PR head**
(`e321b1bc4bc376c0dd17e90e3df100212ed858a0` — the head reviewed in round 4,
which includes round 3's test-isolation fixture changes to
`apps/storefront_builder/tests/test_w4a_shell_only_context.py`) against the
certified checkpoint `5628d6ee31e177d0b4fa1dddad550f894bca540a`.

This supersedes `24_final_full_suite_base_comparison.md` (round 1's
comparison, captured before round 3 modified a `storefront_builder` test
file, so it was no longer exact-head evidence by round 4).

The certified base's own full-suite result was already captured and
independently verified as part of the W3 evidence
(`docs/qa_evidence/storefront_design_engine/phase5/w3_design_lab/19_final_full_storefront_builder_suite.txt`,
3210 tests, 30 failures, 2 errors, 4 skipped) and reused directly for the
comparison below, since the certified checkpoint IS that exact commit.

## Raw counts

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| Exact current head (`32_full_storefront_builder_exact_head.txt`) | 3216 | 30 | 2 | 4 |
| Certified base (`w3_design_lab/19_final_full_storefront_builder_suite.txt`) | 3210 | 30 | 2 | 4 |

Test count differs by exactly 6 — the
`apps.storefront_builder.tests.test_w4a_shell_only_context` module added
by the original W4A implementation round (unchanged in test *count* by
round 3's fixture-isolation change — that change only wrapped existing
`svc.publish()` calls, it added no new test methods).

## Identity-level comparison

Extracted every `FAIL:`/`ERROR:` block from both raw logs (32 in each run)
and compared:

- **Failing/erroring test identities**: identical set, 32/32, both
  directions (`only in final` = `{}`, `only in base` = `{}`).
- **Content**: after masking traceback `File "..."` frame lines, any
  40-80 character alphanumeric run (the shape of a CSRF token), and the
  trailing per-run summary text (`Ran N tests in ...s`, `[real_exit_code=...]`,
  `Destroying test database...`) that follows the *last* failure block in
  each file, **all 32 blocks are byte-identical** between the two runs.
  Zero content differences.

## Verdict

```
W4A-only failures/errors = 0
Changed pre-existing failure reasons = 0
```

The certified base's own 30 failures + 2 errors + 4 skips are the same
pre-existing, unrelated baseline documented in the W3 evidence
(`w3_design_lab/21_final_full_suite_base_comparison.md`) — Ready-Template
recipe/version-contract drift and pre-existing R4/editor UI expectations,
none related to Wishlist, CMS, the shell-only context contract, the
`cart_badge`/stylesheet-link fixes, the Browser QA strengthening, or the
round-3 test-fixture rate-limit isolation. This repair does not touch,
worsen, or fix them.
