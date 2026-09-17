# W4C Accessibility Closure Round — exact-final-source-head full-suite identity comparison

Per Section 9 of the directive: after all Accessibility Closure Round
source changes were final and committed, the exact final source HEAD
was recorded, the full `apps.storefront_builder.tests` suite was run
ONCE on that exact SHA, and a genuine identity + reason level comparison
was performed against the same certified W4B baseline file repair
rounds 1 and 2 used. No source change followed this run (only the
evidence-only commit recording this comparison).

## Exact final source HEAD

`d58c2ff8f535afedae56ab925e2a724be7b196a3` -- `fix(storefront): repair
listing controls and PDP swatch accessibility`, the last commit
touching `qa_storefront_builder_r4.py`, `run.mjs`,
`test_w4c_all50_certification_harness.py`,
`test_w4c_accessibility_production_repair.py`,
`product_listing.html`, or `product_main.html` this round. The full
suite below ran against a worktree at `f6c278d9` (an evidence-only
child of `d58c2ff8`, confirmed via `git diff --name-status
d58c2ff8..f6c278d9` showing only new files under
`docs/qa_evidence/.../implementation/`), so the run's effective source
state is exactly `d58c2ff8`. Worktree confirmed clean
(`git status --short` empty) immediately before launch.

## Command and completion proof

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Found 3371 test(s).
...
Ran 3371 tests in 2207.516s

FAILED (failures=30, errors=2, skipped=4)
```

Complete (non-truncated) output captured in
`35_accessibility_closure_final_full_suite_output.txt` (4423 lines) --
confirmed genuinely complete by its own start marker (`Found 3371
test(s).`) and end marker (`Ran 3371 tests in 2207.516s` / `FAILED
(failures=30, errors=2, skipped=4)`).

`3371 - 3337 = 34`: exactly the new test cases added this round --
8 Phase A tests (`test_98`-`test_105` in
`test_w4c_all50_certification_harness.py`) + 26 Phase B tests (the
entire new `test_w4c_accessibility_production_repair.py` module) --
all of which pass. The failure/error/skipped counts (30/2/4) are
byte-for-byte identical to repair round 2's own full-suite run
(`24_repair_round2_full_suite_output.txt`), a first-pass confirmation
before the identity-level diff below.

## Baseline

Certified W4B baseline exact-head output (the same file every prior
round has compared against):
`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/05_full_storefront_builder_exact_head.txt`
-- 3235 tests / 30 failures / 2 errors / 4 skipped.

## Identity-level diff

```
baseline identity count: 32
current identity count: 32
NEW (in current, not baseline): 0
MISSING (in baseline, not current): 0
```

**NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0**

## Reason-level diff

Extracted the complete traceback+assertion block for each of the 32
matched identities from both outputs, truncated each block's own
trailing dumped-HTML-response content (the same non-deterministic-noise
adjustment repair rounds 1 and 2 already established as legitimate,
not a changed reason), then compared what remained byte-for-byte.

```
baseline blocks: 32
current blocks: 32
identical after truncation: 32
changed after truncation: 0
```

**CHANGED HISTORICAL FAILURE REASONS: 0**

## Conclusion

This is a complete, non-bounded, genuine identity- and reason-level
proof that every one of this round's changes -- Phase A (harness
accessibility gating: `a0967383`), Phase B (production template
repair: `d58c2ff8`), and their accompanying RED commits (`95a6afe1`,
`1a4afd64`) -- introduces zero new or changed failures in
`apps.storefront_builder.tests` against the certified baseline. This
comparison ran at the round's true final source HEAD, matching the
methodology repair round 2 established (unlike repair round 1's own
comparison, which ran against an earlier commit than its final source
head).
