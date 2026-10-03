# W4C Implementation Round 1 — TDD RED analysis

**Starting SHA (branch HEAD):** `0399962f1f3bc1a5d4d31c86f1d6add5ff5c13c8`
**Official certified checkpoint:** `3a4fe9070584655548bae5a9bb574f3415bbf580`
**Test command:**
```
/usr/bin/python3 manage.py test apps.storefront_builder.tests.test_w4c_all50_certification_harness --settings=shop_core.settings -v 2
```
**Result:** 37 tests, 35 errors, 2 ok. Exit code 1.

## Why this is genuine RED, not a stub/false failure

Every one of the 35 failing cases raises `AttributeError` or `TypeError`
naming a piece of the approved contract that does not exist yet on this
branch — never a syntax error, import error, or a deliberately-broken
assertion:

- `AttributeError: 'Command' object has no attribute '_build_w4c_fixture'`
  (and `_apply_and_verify_published`, `_verify_theme_is_none`,
  `_verify_published_theme`, `_theme_cleanup_and_verify`,
  `_prepare_w4c_certification_fixture`, `_run_w4c_campaign`,
  `_run_final_w4c_aggregator`, `_validate_or_init_campaign_matrix`,
  `_merge_base_into_matrix`, `_merge_theme_into_matrix`,
  `_planned_tier2_cells`, `_base_cell_matrix`, `_home_hero_expected`,
  `_w4c_base_result_path`, `_w4c_theme_result_path`,
  `_write_w4c_base_manifest`) — the approved bounded extension's own methods.
- `AttributeError: module '...qa_storefront_builder_r4' has no attribute
  'W4C_MATRIX_SCHEMA_VERSION'` (and `appearance_authority_service`, an import
  the module does not need yet) — the approved module-level constants/imports.
- `TypeError: Command._build_manifest() got an unexpected keyword argument
  'w4c_all50'` — the approved 3-way host branch (design doc §3.5) does not
  exist yet; today's `_build_manifest` only accepts the pre-W4C keyword set.
- `test_20` (static source-grep for `w4cBaseCertification`/
  `w4cThemeCertification` in `run.mjs`) fails with `FileNotFoundError`
  under the real repo-root path once the `parents[]` index bug was fixed —
  confirming the two W4C dispatch functions genuinely do not exist yet in
  `run.mjs` (the file itself exists; the two new functions inside it do not).
- `test_01`/`test_02` fail because `add_arguments` does not register
  `--w4c-all50`/`--only` yet (`argparse` raises for the unrecognized flags).

None of the 35 failures are "the test always fails" placeholders — each one
asserts the DESIRED future behavior (a flag accepting a value, a helper
returning a specific real result, a raised `CommandError` with a specific
message, an exact cell/invocation count) exactly as required by
Implementation Round 1 §3 ("NO W4C IMPLEMENTATION CODE BEFORE GENUINE
FAILING TESTS EXIST... never falsify RED with deliberately-broken
assertions").

## The two expected GREEN guards

- **Case 8** (`test_08_ordinary_manifest_unchanged_by_w4c_kwarg_default`) —
  calls the CURRENT `_build_manifest` signature (no `w4c_all50` kwarg at
  all) and asserts today's ordinary `origin`/`public_url`/`resolver_host`
  values. Passes today because it exercises only pre-existing code, and must
  keep passing once the new kwarg is added with a backward-compatible
  `False` default.
- **Case 21** (`test_21_non_w4c_manifest_still_carries_session_cookie`) —
  same reasoning: calls the current `_build_manifest` signature and asserts
  the session cookie is threaded through exactly as it is today. Passes
  today, must remain true once the W4C branch is added alongside it.

Both are non-interference/regression guards: they prove the ordinary R4 QA
path is architecturally independent of the not-yet-written W4C code from the
very first commit of this test file, per Implementation Round 1 §3's binding
interpretation ("Cases 8 and 21 remain the only two deliberate exceptions").

## Full failing-identity list (35)

test_01, test_02, test_03, test_04, test_05, test_06, test_07, test_09,
test_10, test_11, test_12, test_13, test_14, test_15, test_16, test_17,
test_18, test_19, test_20, test_22, test_23, test_24, test_25, test_26,
test_27, test_28, test_29, test_30, test_31, test_32, test_33, test_34,
test_35, test_36, test_37 — full tracebacks captured verbatim in
`01_tdd_red.txt`.
