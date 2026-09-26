# P5-W4A — full-suite base comparison

Compares the final W4A code (branch `feature/phase5-w4a-public-shell-convergence`)
against the certified checkpoint `5628d6ee31e177d0b4fa1dddad550f894bca540a`.

Since the certified checkpoint IS the W3 merge commit, its own full-suite
result was already captured and independently verified as part of the W3
evidence: `docs/qa_evidence/storefront_design_engine/phase5/w3_design_lab/19_final_full_storefront_builder_suite.txt`
(3210 tests, 30 failures, 2 errors, 4 skipped) — reused directly rather than
re-running, since it is the exact same checkpoint.

## Raw counts

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| Final W4A code (`09_full_storefront_builder_suite.txt`) | 3216 | 30 | 2 | 4 |
| Certified base (`w3_design_lab/19_final_full_storefront_builder_suite.txt`) | 3210 | 30 | 2 | 4 |

Test count differs by exactly 6 — the new
`apps.storefront_builder.tests.test_w4a_shell_only_context` module. No other
test module gained or lost tests.

## Identity-level comparison

Extracted every `FAIL:`/`ERROR:` block from both raw logs (32 in each run,
both generated from the same working directory path so no checkout-path
noise) and compared:

- **Failing/erroring test identities**: identical set, 32/32, both
  directions (`only in final` = `{}`, `only in base` = `{}`).
- **Content**: after masking traceback `File "..."` frame lines and any
  40-80 character alphanumeric run (the shape of a CSRF token), **all 32
  blocks are byte-identical** between the two runs — zero content diffs.

## Verdict

```
W4A-only failures = 0
Changed pre-existing failure reasons = 0
```

The certified base's own 30 failures + 2 errors + 4 skips are the same
pre-existing, unrelated baseline documented in the W3 evidence
(`w3_design_lab/21_final_full_suite_base_comparison.md`) — Ready-Template
recipe/version-contract drift and pre-existing R4/editor UI expectations,
none related to Wishlist, CMS, or the shell-only context contract. This
repair does not touch, worsen, or fix them.
