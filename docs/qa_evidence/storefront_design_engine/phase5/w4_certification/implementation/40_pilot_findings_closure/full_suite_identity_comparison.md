# W4C Pilot Findings Closure — exact-final-source-head full-suite identity comparison

Per Section 18: after the closure pilot came back clean, the exact
final source HEAD was recorded, the full `apps.storefront_builder.tests`
suite was run ONCE on that exact SHA, and a genuine identity + reason
level comparison was performed against the same certified W4B baseline
every prior round has used.

## Exact final source HEAD

`b3f2c43974ffd528a4374fb6a3c35af20314379c` — `fix(phase5): apply code
review fixes to W4C cart-remove diagnostics` (the last commit touching
`qa_storefront_builder_r4.py`, `run.mjs`, or the harness test file this
round; the closure pilot revealed no defect, so no source commit
followed it). The full suite ran against a worktree at `54697774` (an
evidence-only child of `b3f2c439` — `git diff --name-status
b3f2c439..54697774` shows only new files under
`docs/qa_evidence/.../40_pilot_findings_closure/`), so the run's
effective source state is exactly `b3f2c439`. Worktree confirmed clean
(`git status --short` empty) immediately before launch.

## Command and completion proof

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Found 3401 test(s).
...
Ran 3401 tests in 3792.167s

FAILED (failures=30, errors=2, skipped=4)
```

Complete (non-truncated) output captured in `full_suite_output.txt`
(4466 lines) — confirmed genuinely complete by its own start marker
(`Found 3401 test(s).`) and end marker (`Ran 3401 tests in
3792.167s` / `FAILED (failures=30, errors=2, skipped=4)`).

`3401 - 3383 = 18`: exactly this round's new test count (8
`W4CCanonicalHomeExpectationTests` + 10 `W4CCartRemoveDiagnosticsTests`,
including the 3 code-review-fix regression tests), all passing. The
failure/error/skipped counts (30/2/4) are byte-for-byte identical to
the Rate-Limit Sharding Repair's own full-suite run, a first-pass
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

```
baseline blocks: 32
current blocks: 32
identical after truncation: 32
CHANGED HISTORICAL FAILURE REASONS: 0
```

## Note on the pilot's own findings

Both genuine findings this round closed (`premium_leather` Home
rsec-count mismatch, `editorial_jewelry` Cart tablet remove) are real
production/browser findings from the W4C harness's own assertions, not
Python `unittest` failures, so they never appeared in — and their
closure is not visible in — this Django-test-suite identity
comparison. Their closure is recorded separately in
`closure_pilot_summary.md`.

## Conclusion

This is a complete, non-bounded, genuine identity- and reason-level
proof that this round's changes — the canonical Home render
expectation (`9f0d103e`), the Cart-remove synchronization repair
(`48fb3171` RED, `4ff0ab10` GREEN, `b3f2c439` code-review fixes) —
introduce zero new or changed failures in `apps.storefront_builder.tests`
against the certified baseline.
