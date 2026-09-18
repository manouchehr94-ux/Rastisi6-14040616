# Visual Distinctness Repair — exact-source full-suite identity comparison

Per this round's Section 20, run twice, each as a tracked
`run_in_background: true` Bash call against a confirmed-clean
worktree (`git status --short` empty immediately before launch).

## Baseline

Certified baseline (same file every prior W4C round has compared
against):
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/implementation/40_pilot_findings_closure/full_suite_output.txt`
— 3401 tests / 30 failures / 2 errors / 4 skipped / 32 failure+error
identities.

## Run 1 — REPAIR SOURCE HEAD `6074424b99cd922a28fe3187fef10a53931e535b`

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Ran 3418 tests in 3307.944s
FAILED (failures=33, errors=2, skipped=1)
```

Full output: `full_suite_output_attempt1_6074424b.txt`.

Identity-level diff: baseline 32 identities / current 35 identities.

```
NEW identities not in baseline (3):
test_all_21_curated_keys_are_now_version_two (...ExplicitVersionMapTests...) (key='green_workshop')
test_all_21_curated_keys_are_now_version_two (...ExplicitVersionMapTests...) (key='laleh_play')
test_all_21_curated_keys_are_now_version_two (...ExplicitVersionMapTests...) (key='parnian_editorial')

Baseline identities missing from current run: 0
```

Root cause: `test_w4b_template_curation.py`'s
`ExplicitVersionMapTests.test_all_21_curated_keys_are_now_version_two`
is a second, separate pre-existing contract (independent of
`test_a8_ready_template_catalog.py`'s `EXPECTED_LATEST_VERSIONS`,
which this round had already updated) that also pinned these exact 3
keys to version `"2"`. Missed when the version bump was made. Not a
behavioral regression — a bookkeeping gap in a second test file
covering the same fact.

## Fix commit

`c31e07ed8a5cab241e53d1ed7fb905637f1af79e` — updated the assertion so
these 3 keys expect `"3"` (the other 18 W4B-curated keys still expect
`"2"`, unchanged). Focused re-run:
`python manage.py test apps.storefront_builder.tests.test_w4b_template_curation --settings=shop_core.settings -v 2`
-> `Ran 19 tests ... OK`.

## Run 2 (final) — FULL SUITE EXACT SOURCE HEAD `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
Ran 3418 tests in 3295.186s
FAILED (failures=30, errors=2, skipped=1)
```

Full output: `full_suite_output_final_c31e07ed.txt`.

### Identity-level diff

```
baseline identity count: 32
current identity count: 32
NEW identities not in baseline: 0
Baseline identities missing from current run: 0
```

### Reason-level diff

Each of the 32 matched identities' full failure/error block body
(everything between the `----` separator and the next blank-blank
line, truncated to 2000 chars) compared byte-for-byte:

```
baseline blocks: 32
new blocks: 32
CHANGED/MISSING: 0
NEW-ONLY: 0
```

### Skipped-count note

Baseline: 4 skipped. Current: 1 skipped. The 3 no-longer-skipped tests
are all in `test_ready_template_real_previews.py`
(`CommittedScreenshotIntegrityTests`, `VersionedPreviewIdentityTests`)
and were skipped in the baseline only because not all current-version
real screenshots were committed yet at that historical point. Real
screenshots for all 50 Ready Templates were committed during the later
all-50 certification campaign (already-certified, prior work, not part
of this repair round), so by this round's source head those 3 tests
run and pass instead of skipping. `test_menu_from_another_store_never_leaks`
(the 4th baseline skip) still skips identically in both runs. This is
a coverage improvement carried over from already-certified prior work,
not an effect of — and not a masking of anything by — this round's
3-key repair.

## Conclusion

At the final source head `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`,
this round introduces **zero new failure/error identities** and
**zero changed historical failure reasons** against the certified
baseline. `3418 - 3401 = 17` accounts exactly for this round's new
`test_a8_visual_distinctness_repair.py` file (all 17 passing).
