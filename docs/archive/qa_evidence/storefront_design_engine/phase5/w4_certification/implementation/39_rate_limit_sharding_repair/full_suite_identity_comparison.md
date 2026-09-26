# W4C Rate-Limit Sharding Repair — exact-final-source-head full-suite identity comparison

Per Section 11 of the directive: after the two-process pilot came back
clean, the exact final source HEAD was recorded, the full
`apps.storefront_builder.tests` suite was run ONCE on that exact SHA,
and a genuine identity + reason level comparison was performed against
the same certified W4B baseline every prior round has used.

## Exact final source HEAD

`5807847b3606ed36836e9f06ba2530c7c513b1a5` — `feat(phase5): add bounded
W4C Tier-2 process budget` (the last commit touching
`qa_storefront_builder_r4.py` or the test file this round; the pilot
revealed no defect in the sharding implementation itself, so no source
commit followed it). The full suite ran against a worktree at
`b2108697` (an evidence-only child of `5807847b` — `git diff
--name-status 5807847b..b2108697` shows only new files under
`docs/qa_evidence/.../39_rate_limit_sharding_repair/`), so the run's
effective source state is exactly `5807847b`. Worktree confirmed clean
(`git status --short` empty) immediately before launch.

## Command and completion proof

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Found 3383 test(s).
...
Ran 3383 tests in 3756.449s

FAILED (failures=30, errors=2, skipped=4)
```

Complete (non-truncated) output captured in `full_suite_output.txt`
(4435 lines) — confirmed genuinely complete by its own start marker
(`Found 3383 test(s).`) and end marker (`Ran 3383 tests in 3756.449s` /
`FAILED (failures=30, errors=2, skipped=4)`).

`3383 - 3371 = 12`: exactly this round's new test count (the 11
`W4CTier2BudgetShardingTests` cases + the 1
`W4CRateLimitControlledDiagnosticTests` case), all passing. The
failure/error/skipped counts (30/2/4) are byte-for-byte identical to
the Accessibility Closure Round's own full-suite run
(`35_accessibility_closure_final_full_suite_output.txt`), a first-pass
confirmation before the identity-level diff below.

## Baseline

Certified W4B baseline exact-head output (the same file every prior
round has compared against):
`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/05_full_storefront_builder_exact_head.txt`
— 3235 tests / 30 failures / 2 errors / 4 skipped.

## Identity-level diff

```
baseline identity count: 32
current identity count: 32
NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0
MISSING: 0
```

## Reason-level diff

Extracted the complete traceback+assertion block for each of the 32
matched identities from both outputs, truncated each block's own
trailing dumped-HTML-response content (the same non-deterministic-noise
adjustment every prior round's identity comparison has used), then
compared what remained byte-for-byte.

```
baseline blocks: 32
current blocks: 32
identical after truncation: 32
CHANGED HISTORICAL FAILURE REASONS: 0
```

## Note on the pilot's own findings

The bounded two-process pilot (`pilot_summary.md`) surfaced two genuine
browser-behavior findings (`premium_leather` Home rsec-count mismatch,
`editorial_jewelry` Cart tablet-only remove failure) — these are real
production/content findings from the W4C harness's own browser
assertions, not Python `unittest` failures, so they do not and cannot
appear in this Django-test-suite identity comparison. They are recorded
separately in `pilot_summary.md` and are explicitly out of scope for
this repair round.

## Conclusion

This is a complete, non-bounded, genuine identity- and reason-level
proof that this round's changes — the `--w4c-tier2-budget` option, its
validation, its threading into `_run_w4c_campaign`, and the controlled
`RateLimitExceeded` diagnostic (`059c1065` RED, `5807847b` GREEN) —
introduce zero new or changed failures in `apps.storefront_builder.tests`
against the certified baseline.
