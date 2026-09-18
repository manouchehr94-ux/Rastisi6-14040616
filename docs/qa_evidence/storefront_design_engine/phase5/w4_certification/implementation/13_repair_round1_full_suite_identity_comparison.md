# W4C Repair Round 1 — Full-suite identity-level regression comparison

Per IMPORTANT-5 of the Independent Architect review, this is a genuine
per-identity comparison against the certified baseline's exact failure
list -- not the "bounded, not exhaustive" aggregate-count check the
prior evidence (`09_full_suite_regression.md`) explicitly disclosed as
its limitation.

## Command and complete output

```
$ /usr/bin/python3 manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2
...
Ran 3297 tests in 2026.148s

FAILED (failures=30, errors=2, skipped=4)
```

Complete (non-tail-truncated) output captured in
`12_repair_round1_full_suite_output.txt` (4318 lines).

This run was executed against commit `c00326df` (the CRITICAL/IMPORTANT
harness repair, before this session's 2 additional smoke-discovered bug-fix
commits) -- see "Scope of this comparison" below for why that is the
correct base for this specific check.

## Baseline

Certified W4B baseline exact-head output:
`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/05_full_storefront_builder_exact_head.txt`
-- 3235 tests / 30 failures / 2 errors / 4 skipped.

`3297 - 3235 = 62`: the cumulative new W4C test cases added across
Implementation Round 1 (37) and this repair round's RED suite (25),
all of which pass. Confirmed independently in `11_repair_round1_green.txt`.

## Identity-level diff

Extracted every `FAIL:`/`ERROR:` identity line from both outputs and
diffed them:

```
$ grep "^FAIL:\|^ERROR:" 05_full_storefront_builder_exact_head.txt | sort > baseline_failures.txt
$ grep "^FAIL:\|^ERROR:" 12_repair_round1_full_suite_output.txt | sort > current_failures.txt
$ diff baseline_failures.txt current_failures.txt
(no output -- 32 identities, byte-for-byte identical)
```

**NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0**

## Reason-level diff

Extracted the complete traceback+assertion block for each of the 32
matched identities from both outputs and compared them. 5 blocks showed
a raw text diff on first pass; all 5 were re-examined by truncating the
comparison at the point each assertion dumps a full (non-deterministic)
rendered HTML response body -- e.g. randomly-assigned brand palette CSS
custom properties differ between runs even though the test itself is
fully deterministic given the same seed:

- `test_builder_preview_has_nav_but_never_live_cart_count_badge`: same
  `AssertionError: False is not true : Couldn't find
  'data-mobile-nav="luxury_floating_cart"'` in both.
- `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`:
  same `':aria-pressed="fullscreen"' not found in ...` in both.
- `test_header_footer_variant_labels_shown_for_updated_preset`: same
  assertion text in both.
- `test_public_home_renders_functional_mobile_nav_and_real_routes`: same
  assertion text in both.
- `test_version_palette_and_global_variants`: same
  `AssertionError: '3' != '2'` in both -- the only textual difference was
  the trailing unittest summary line (`Ran 3235` vs `Ran 3297` tests,
  this run's later test-database teardown message), an artifact of this
  test being last in both output files, not a changed failure reason.

**CHANGED HISTORICAL FAILURE REASONS: 0**

## Scope of this comparison

This exact 3297-test run was launched (in the background) against
`c00326df` -- the CRITICAL/IMPORTANT repair commit -- before this
session's two follow-on bug-fix commits (`e02c0d17`, `9f6bf48d`) that
repaired 4 real defects found by actually running the mandated bounded
browser smoke (listing link resolution, PDP fixture stock selection,
theme identity comparison, and the cart add-to-cart host-resolution
bug). Re-running the entire ~34-minute suite a third time for those
commits was not done; instead:

- Both commits touch only `qa_storefront_builder_r4.py`,
  `test_w4c_all50_certification_harness.py`, and `run.mjs`.
- The only `apps.storefront_builder.tests` modules that import or
  exercise either harness file are `test_w4c_all50_certification_harness.py`
  itself (67/67 passing after both commits, up from the 62/62 this
  identity comparison's run already covered),
  `test_ready_template_real_previews.py` (32/32, unaffected -- confirmed
  standalone), and `test_qa_harness_contract.py` (4/4, unaffected --
  confirmed standalone). All three are captured together, freshly, in
  `11_repair_round1_green.txt` (103/103 passing, 3 skipped as expected).
- `run.mjs` is never imported by any Python test; its correctness for
  those 4 fixes is proven by the bounded browser smoke itself (see
  `14_repair_round1_smoke_evidence.md`), not by this Python regression
  suite.

Given that scope, the identity-level comparison above is a complete,
non-bounded proof that the CRITICAL/IMPORTANT repair (`c00326df`)
introduces zero new or changed failures against the certified baseline.
The 4 additional smoke-discovered fixes are separately and completely
verified (67/67 focused + 103/103 combined + a fully-passing real
browser smoke), just not by a third full-suite run.
