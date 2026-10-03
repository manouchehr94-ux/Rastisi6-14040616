# W4C Implementation Round 1 — Full `apps.storefront_builder.tests` regression

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings
...
Ran 3272 tests in 2029.939s

FAILED (failures=30, errors=2, skipped=4)
```

**Certified baseline** (design doc section 14, citing W4B's own
`09_full_suite_exact_head_base_comparison.md`/
`05_full_storefront_builder_exact_head.txt`): 3235 tests / 30 failures /
2 errors / 4 skipped.

**This round:** 3272 tests / 30 failures / 2 errors / 4 skipped.

`3272 - 3235 = 37` — exactly the new `test_w4c_all50_certification_harness.py`
suite added by this round, all 37 of which pass (confirmed separately in
`04_tdd_green.txt`). The failure/error/skip counts are otherwise
**identical** to the certified baseline.

## Verification scope and its limit (disclosed)

This round's diff touches exactly three files: the two harness files and
the one new test module (`06_architecture_duplication_audit.md`). Neither
harness file is imported or exercised by any other test in
`apps.storefront_builder.tests` except:

- The new 37-case suite itself (37/37 pass).
- `test_qa_harness_contract.py`'s four static source-grep tests, which
  check for specific markers inside `qa_storefront_builder_r4.py`/
  `run.mjs` — re-run standalone and confirmed 4/4 pass (this round's
  additions did not disturb any pre-existing marker those tests check
  for).

Given that scope, and that the aggregate failure/error/skip counts are
identical to the certified baseline, this is treated as sufficient
evidence of zero regression for this round. A full per-identity diff
against the certified baseline's exact failure list (as W4B performed for
its own, structurally different change to `a8_ready_templates.py`, a file
every Ready-Template-resolution test transitively depends on) was not
re-run in full for every failing identity in this round, because doing so
would require re-executing this same ~34-minute suite a second time to
capture complete (non-tail-truncated) output, and the two sampled failures
visible at the end of this run's own output
(`test_warm_boutique_lalerokh_v2.WarmBoutiqueV2ContractTests
.test_version_palette_and_global_variants` expecting preset version `"2"`
but finding `"3"`, and a second Content-composition list-mismatch in the
same area) are template-version-literal assertions with no relationship to
either harness file this round touches — the same category of pre-existing,
content-brittle failure W4B's own evidence already documented finding in
this suite. This is disclosed as a bounded, not exhaustive, verification
rather than claimed as a full identity-level match.
