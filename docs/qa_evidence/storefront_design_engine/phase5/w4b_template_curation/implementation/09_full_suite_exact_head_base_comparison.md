# P5-W4B — full-suite exact-head base comparison

Compares `apps.storefront_builder.tests` at the W4B implementation head
(current branch `feature/phase5-w4b-template-curation`, evidence file
`05_full_storefront_builder_exact_head.txt`) against the certified base
`707dd631e851bdd13173bf3950489142f3e526b1`, whose full-suite result is the
W4A exact-head capture
(`docs/qa_evidence/storefront_design_engine/phase5/w4a_public_shell_convergence/32_full_storefront_builder_exact_head.txt`,
3216 tests / 30 failures / 2 errors / 4 skipped). That capture is a valid
pre-W4B baseline because none of the design-gate-repair commits between
the certified base and the implementation head touched any
`storefront_builder` production or test file — only the two design docs.

## Raw counts

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| W4B implementation head (`05_full_storefront_builder_exact_head.txt`) | 3235 | 30 | 2 | 4 |
| Certified base (`w4a/32_full_storefront_builder_exact_head.txt`) | 3216 | 30 | 2 | 4 |

Test count differs by exactly 19 — the 19 new tests added by
`apps/storefront_builder/tests/test_w4b_template_curation.py`. No other
test file gained or lost a test method.

## Identity-level comparison

Extracted every `FAIL:`/`ERROR:` block from both raw logs (32 in each
run) and compared the failing/erroring test identities:

```
only in W4B head  = {}
only in base      = {}
```

32/32 identical set, both directions.

## Content-level comparison

Compared the two 32-block sets pairwise. 30 of 32 blocks are byte-
identical. The remaining 2 differ only in content that is expected to
vary between two separate full-suite invocations and does not change the
failure's cause:

1. **`test_header_footer_variant_labels_shown_for_updated_preset`**
   (`test_u8_template_gallery.py`) — the assertion line, the exact
   `AssertionError` message, and the "Couldn't find '…' in the following
   response" reason are byte-identical between the two runs. Only the
   dumped HTML response body that follows differs, because the Template
   Gallery page renders the full, current state of all 50 templates
   (including the version bumps this workstream made) — expected, and
   already confirmed pre-existing and unrelated to Wishlist/CMS/shell
   context per the W4A baseline note
   (`w4a_public_shell_convergence/33_full_suite_exact_head_base_comparison.md`).
   Verified directly: the failure head, truncated at the
   `AssertionError:` line, is identical between base and current run.

2. **`test_version_palette_and_global_variants`**
   (`test_warm_boutique_lalerokh_v2.py`) — the entire failure body
   (`self.assertEqual(self.preset.version, "2")` / `AssertionError: '3'
   != '2'`) is byte-identical. `warm_boutique_lalerokh` is not one of the
   21 W4B-curated keys and its recipe was not touched. The only textual
   difference is in the trailing per-run summary that happens to follow
   this block because it is the last failure in each file (`Ran 3216
   tests in 2104.325s` / `[real_exit_code=1]` vs. `Ran 3235 tests in
   2090.668s` / `EXIT_CODE=1`) — run duration, total test count, and the
   exit-code marker text differ only because this capture used a
   differently-worded marker line than the W4A capture script; neither is
   part of the failure itself.

## Verdict

```
W4B-only failures/errors      = 0
Changed pre-existing failure/error reasons = 0
```

The certified base's 30 failures + 2 errors + 4 skips are the same
pre-existing, unrelated baseline already documented in
`w4a_public_shell_convergence/33_full_suite_exact_head_base_comparison.md`.
This workstream (21 templates edited in place in
`apps/storefront_builder/a8_ready_templates.py`, plus the 21 historical
v1 registrations) does not touch, worsen, or fix any of them.
