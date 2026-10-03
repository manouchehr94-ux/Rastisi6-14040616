# P5-W4A review-repair round — refreshed full-suite base comparison

Compares the **final repaired production code** on
`feature/phase5-w4a-public-shell-convergence` (after the IMPORTANT 1/4
production fixes — `apps/cart/context_processors.py`,
`apps/customers/templates/customers/wishlist.html`,
`apps/content/templates/content/page_detail.html`) against the certified
checkpoint `5628d6ee31e177d0b4fa1dddad550f894bca540a`.

Per the review's explicit instruction not to reuse pre-repair-round
evidence once production code changed, this is a fresh run of
`apps.storefront_builder.tests` at the final repaired head — not the
`09_full_storefront_builder_suite.txt` capture from the original
implementation round (head `73eb41c4`).

The certified base's own full-suite result was already captured and
independently verified as part of the W3 evidence
(`docs/qa_evidence/storefront_design_engine/phase5/w3_design_lab/19_final_full_storefront_builder_suite.txt`,
3210 tests, 30 failures, 2 errors, 4 skipped) and reused directly for the
comparison below, since the certified checkpoint IS that exact commit.

## Raw counts

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| Final repaired W4A head (`22_full_storefront_builder_suite_final.txt`) | 3216 | 30 | 2 | 4 |
| Certified base (`w3_design_lab/19_final_full_storefront_builder_suite.txt`) | 3210 | 30 | 2 | 4 |

Test count differs by exactly 6 — the `apps.storefront_builder.tests.test_w4a_shell_only_context`
module added by the original W4A implementation round. This repair round
added tests to `apps.customers.tests`/`apps.content.tests` (not part of
`apps.storefront_builder.tests`), so no further count drift here.

## Identity-level comparison

Extracted every `FAIL:`/`ERROR:` block from both raw logs (32 in each run)
and compared:

- **Failing/erroring test identities**: identical set, 32/32, both
  directions (`only in final` = `{}`, `only in base` = `{}`).
- **Content**: after masking traceback `File "..."` frame lines and any
  40-80 character alphanumeric run (the shape of a CSRF token), 31/32
  blocks are byte-identical. The one block that differed on a naive
  substring diff is the *last* failure in the file
  (`test_version_palette_and_global_variants`); the difference is
  confined entirely to the trailing per-run summary text captured after
  it (`Ran 3210/3216 tests in ...s`, plus this run's extra
  `[real_exit_code=1]` marker) — an artifact of block-extraction taking
  "everything up to the next FAIL:/ERROR: header, or end of file" for the
  final block. The actual failure body itself
  (`AssertionError: '3' != '2'`, same traceback line) is byte-identical
  between the two runs. **Zero actual content differences.**

## Verdict

```
W4A-only failures = 0
Changed pre-existing failure reasons = 0
```

The certified base's own 30 failures + 2 errors + 4 skips are the same
pre-existing, unrelated baseline documented in the W3 evidence
(`w3_design_lab/21_final_full_suite_base_comparison.md`) — Ready-Template
recipe/version-contract drift and pre-existing R4/editor UI expectations,
none related to Wishlist, CMS, the shell-only context contract, or this
repair round's cart_badge/stylesheet-link fixes. This repair does not
touch, worsen, or fix them.
