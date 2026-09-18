# P5-W4C Rendered Visual Distinctness Repair — Final Report

## Summary

Targeted, minimal repair of exactly the 3 Ready Templates the
Independent Architect's rendered visual distinctness closure flagged
as materially indistinguishable above the fold from their pair anchor:
`green_workshop` (vs `pine_eco`), `laleh_play` (vs `playful_lifestyle`),
`parnian_editorial` (vs `silk_editorial`). Each target was bumped
`v2 -> v3` with a genuine above-the-fold structural change (a
different rendered hero component, not palette/font/radius alone). No
anchor was modified. Outgoing v2 history is preserved byte-for-byte and
independently resolvable for all 3, exactly like every prior version
bump in this file.

A mid-round code review caught a real defect in the first repair
attempt (`parnian_editorial`'s first hero choice rendered identically
to `artisan_grain`'s, recreating the same defect against a different,
unchecked sibling) and it was corrected before this report, with a new
test (`test_no_new_rendered_hero_style_collision_among_all_fifty`)
proven RED against the bug first.

Section 20's exact-source full regression (run against
`6074424b99cd922a28fe3187fef10a53931e535b`) surfaced 3 new failure
identities, all from a *second*, previously-missed pre-existing W4B
contract test file (`test_w4b_template_curation.py`) pinning these
same 3 keys to version `"2"` — the identical bookkeeping category
already updated once in `test_a8_ready_template_catalog.py`, just
missed for this file. Fixed as its own commit
(`c31e07ed8a5cab241e53d1ed7fb905637f1af79e`), re-verified GREEN
(19/19), and the full regression was re-run once more against that
corrected final head to produce a genuinely clean 0-new/0-changed
identity comparison (see below).

## Section 20 — exact-source full regression (final)

Ran twice, against two different exact source heads, both tracked
`run_in_background: true`:

1. **First run** — `6074424b99cd922a28fe3187fef10a53931e535b` (the
   REPAIR SOURCE HEAD). `Ran 3418 tests in 3307.944s` /
   `FAILED (failures=33, errors=2, skipped=1)`. Identity diff against
   baseline: 3 NEW failure identities, all
   `test_w4b_template_curation.ExplicitVersionMapTests.test_all_21_curated_keys_are_now_version_two`
   parameterized on `key='green_workshop'|'laleh_play'|'parnian_editorial'`.
   Root cause: a second, separate W4B contract test file this round
   had not yet updated for the intentional v2->v3 bump. 0 baseline
   identities went missing.

2. **Fix** — `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`: updated
   `test_all_21_curated_keys_are_now_version_two` to expect `"3"` for
   exactly these 3 keys (the other 18 W4B-curated keys still assert
   `"2"`). Focused re-run of `test_w4b_template_curation.py`: 19/19
   GREEN.

3. **Second (final) run** — `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`.
   `Ran 3418 tests in 3295.186s` / `FAILED (failures=30, errors=2, skipped=1)`.

   - **Identity-level diff** against the certified baseline
     (`40_pilot_findings_closure/full_suite_output.txt`, 3401 tests,
     32 identities): baseline 32 / current 32, **0 NEW**, **0 MISSING**.
   - **Reason-level diff** (full failure/error block body per
     identity, truncated to 2000 chars): 32/32 blocks matched
     byte-for-byte, **0 CHANGED**, **0 NEW-ONLY**.
   - Skipped count differs (baseline 4, current 1): all 3 of the
     difference are `test_ready_template_real_previews.py` tests that
     were skipped in the older baseline for lacking committed real
     screenshots — a pre-existing condition from earlier, already
     certified campaign work (real screenshots for all 50 committed
     during the all-50 certification campaign), unrelated to and
     unaffected by this repair round's 3 targeted key changes. Not a
     regression; strictly more coverage now executes and passes.
   - `3418 - 3401 = 17`: exactly this round's new test count
     (`test_a8_visual_distinctness_repair.py`), all passing.

   Conclusion: this round's production change (the 2 version bumps —
   initial and corrected — plus the 2 test bookkeeping updates)
   introduces **zero new or changed failures** against the certified
   baseline.

## Fields

```
P5-W4C VISUAL DISTINCTNESS REPAIR:
COMPLETE

STARTING HEAD:
0898c31bdca868f68f36a52021838201dfb2706f

REPAIR SOURCE HEAD:
6074424b99cd922a28fe3187fef10a53931e535b

FINAL BRANCH HEAD:
<recorded after this evidence commit — see commit log>

OFFICIAL BASE:
3a4fe9070584655548bae5a9bb574f3415bbf580

TARGETS MODIFIED:
green_workshop
laleh_play
parnian_editorial

ANCHORS MODIFIED:
0

LATEST VERSIONS:
green_workshop v3 / 3
laleh_play v3 / 3
parnian_editorial v3 / 3

OUTGOING V2 HISTORY PRESERVED:
YES

READY TEMPLATE COUNT:
50 / 50

ARCHITECTURAL DUPLICATION INTRODUCED:
0 / 0

CODE REVIEW:
CRITICAL 0
IMPORTANT 0

FOCUSED TESTS:
40/40 GREEN

TARGETED BROWSER CELLS:
78/78 / 78/78

TARGETED FAIL:
0 / 0

TARGETED BLOCKED:
0 / 0

TARGETED ACCESSIBILITY FAIL:
0 / 0

TARGETED BROWSER ERRORS:
0 / 0

SQLITE RESTORE:
PASS

green_workshop vs pine_eco:
DISTINCT

laleh_play vs playful_lifestyle:
DISTINCT

parnian_editorial vs silk_editorial:
DISTINCT

NEW COLLISIONS:
0 / 0

FULL SUITE EXACT SOURCE HEAD:
c31e07ed8a5cab241e53d1ed7fb905637f1af79e

NEW FAILURE/ERROR IDENTITIES:
0 / 0

CHANGED HISTORICAL FAILURE REASONS:
0 / 0

STATIC GALLERY REFRESH:
NOT RUN

NEW FINAL 704 CAMPAIGN:
NOT RUN

OLD 704 MATRIX MODIFIED:
NO

PR:
#12

PR STATE:
OPEN + UNMERGED

W5 STARTED:
NO

MERGED:
NO

FINAL STATUS:
READY FOR INDEPENDENT ARCHITECT VISUAL-REPAIR REVIEW

STOP.

Do not run the new 704 campaign.
Do not merge.
Do not start W5.
Return for Independent Architect review.
```
