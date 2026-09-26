# W4C Repair Round 2 — exact-final-source-head full-suite identity comparison

Per section 11 of the round-2 directive: after all round-2 source
changes were final and committed, the exact final source HEAD was
recorded, the full `apps.storefront_builder.tests` suite was run ONCE
on that exact SHA, and a genuine identity + reason level comparison was
performed against the certified W4B baseline. No source change followed
this run.

## Exact final source HEAD

`5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47` -- the commit that fixed the
Cart accessibility ordering bug the bounded smoke found (the last commit
touching `qa_storefront_builder_r4.py`/`run.mjs`/the test file this
round). The full suite below was launched against exactly this
checked-out worktree state, confirmed clean
(`git status --short` empty) immediately before launch.

## Command and complete output

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Found 3337 test(s).
...
Ran 3337 tests in 2110.782s

FAILED (failures=30, errors=2, skipped=4)
```

Complete (non-tail-truncated) output captured in
`24_repair_round2_full_suite_output.txt` (4386 lines) -- confirmed
genuinely complete by its own start marker (`Found 3337 test(s).`) and
end marker (`Ran 3337 tests in 2110.782s` / `FAILED
(failures=30, errors=2, skipped=4)`), not a truncated tail.

## Baseline

Certified W4B baseline exact-head output:
`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/05_full_storefront_builder_exact_head.txt`
-- 3235 tests / 30 failures / 2 errors / 4 skipped.

`3337 - 3235 = 102`: the cumulative new W4C test cases across
Implementation Round 1 (37), repair round 1 (25), and this repair
round 2 (35 net: 33 new behavioral/provenance cases in the RED commit,
plus 2 more -- `test_70b`, `test_84b` -- added while fixing the two
real bugs the bounded smoke found), all of which pass. Confirmed
independently: `test_w4c_all50_certification_harness.py` alone has
102 tests, all green (section 6 below).

## Identity-level diff

```
$ grep "^FAIL:\|^ERROR:" 05_full_storefront_builder_exact_head.txt | sort > baseline_failures.txt
$ grep "^FAIL:\|^ERROR:" 24_repair_round2_full_suite_output.txt | sort > current_failures.txt
$ diff baseline_failures.txt current_failures.txt
(no output -- 32 identities, byte-for-byte identical)
```

**NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0**

## Reason-level diff

Extracted the complete traceback+assertion block for each of the 32
matched identities from both outputs and compared them, byte-for-byte
first, then with each block's own trailing dumped-HTML-response content
truncated out (the same non-deterministic-content adjustment repair
round 1's identity comparison already established as legitimate noise,
not a changed reason). Exactly 1 block showed any textual difference
after truncation -- the LAST block in both files
(`test_version_palette_and_global_variants`) -- and it differs only in
the trailing unittest summary line (`Ran 3235` vs `Ran 3337` tests, and
a Django-version-dependent test-database teardown message), an
artifact of that test being last in both output files. The actual
assertion content in both is byte-for-byte identical:

```
AssertionError: '3' != '2'
- 3
+ 2
```

**CHANGED HISTORICAL FAILURE REASONS: 0**

## Conclusion

This is a complete, non-bounded, genuine identity- and reason-level
proof that every one of this round's IMPORTANT-1-through-6 repairs
(`208100c0`, `64dadb82`, `5fedd509`) introduces zero new or changed
failures in `apps.storefront_builder.tests` against the certified
baseline. Unlike repair round 1's own full-suite comparison (which
ran against an EARLIER commit than its final source head, disclosed
in `13_repair_round1_full_suite_identity_comparison.md`), this
comparison ran at the round's true final source HEAD, with no source
change following it.
