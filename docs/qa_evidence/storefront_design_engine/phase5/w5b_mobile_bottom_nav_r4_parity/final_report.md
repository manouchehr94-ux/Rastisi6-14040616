# P5-W5B — Mobile Bottom Navigation, R4 Parity — Final Report

## STATUS: COMPLETE

## Starting base

- Official integration branch: `feature/phase5-design-expansion`
- Exact HEAD at authorization: `e8a0a33841cf1eff289f76588d95491558ba9348`
  (W5A merge checkpoint, PR #13 merged as `01eee9f97114fa377b452634d8c6deb26ad9a93a`)

## Feature branch

`feature/phase5-w5b-mobile-bottom-nav-r4-parity`

## HEAD SHAs

- **Final production source HEAD:** `0359851b` (`feat(phase5): expose
  mobile bottom navigation in R4`) — no production file changed in any
  commit after this one.
- **Final evidence/branch HEAD:** `94193557` (`docs(phase5): execute W5B
  browser QA, fix QA-script-only bugs`)

## Registered variant count

**9** (`hidden`, `luxury_floating_cart`, `four_item`, `five_item`,
`raised_cart`, `floating_dock`, `glass_dock`, `minimal_icons`,
`wide_cart`) — derived from `GLOBAL_MOBILE_NAV_REGION`, unchanged.

## New variants / renderers / mutation types / migrations

**0 / 0 / 0 / 0.** `footer.update` remains the single mutation type;
`GLOBAL_MOBILE_NAV_REGION` remains the single registry; no new renderer
template; `manage.py makemigrations --check --dry-run` reports "No
changes detected" at the final HEAD.

## Contract checks (TDD plan A-S, 24 tests across 9 classes)

| # | Contract | Test | Result |
|---|---|---|---|
| 1 | Registry-driven read projection (every key+label listed) | `test_editor_response_lists_every_registered_variant_key_and_label` | PASS |
| 2 | Registered-variant count matches the canonical registry (never a 2nd hardcoded list) | `test_registered_variant_count_matches_the_canonical_registry` | PASS |
| 3 | Selector wired via existing `data-r4-global-field`/`data-r4-global-mutation="footer.update"` | `test_selector_uses_generic_global_field_and_mutation_attributes` | PASS |
| 4 | Selector shows current value as selected | `test_selector_shows_current_value_as_selected` | PASS |
| 5 | Merchant-facing Persian label present | `test_selector_carries_a_merchant_facing_persian_label` | PASS |
| 6 | `footer.update` accepts `mobile_nav_variant` | `test_footer_update_accepts_mobile_nav_variant` | PASS |
| 7 | Unknown variant fails closed | `test_unknown_mobile_nav_variant_fails_closed` | PASS |
| 8 | `validate_footer_config` remains the single validator boundary | `test_validate_footer_config_remains_the_single_validator_boundary` | PASS |
| 9 | Sibling isolation: `footer_variant` preserved | `test_changing_only_mobile_nav_preserves_footer_variant` | PASS |
| 10 | Sibling isolation: `FOOTER_TOGGLE_FIELDS`/`extra_blocks` preserved | `test_changing_only_mobile_nav_preserves_footer_toggles_and_blocks` | PASS |
| 11 | Sibling isolation: unrelated Store Appearance families + header preserved | `test_changing_only_mobile_nav_preserves_unrelated_appearance_and_header` | PASS |
| 12 | Typed `selections["bottom_nav"]` synchronized | `test_typed_bottom_nav_selection_is_synchronized` | PASS |
| 13 | Typed `selections["footer"]` NOT changed merely because Bottom Nav changed | `test_typed_footer_selection_does_not_change_merely_because_bottom_nav_changed` | PASS |
| 14 | Stale `base_revision` rejected | `test_stale_base_revision_is_rejected` | PASS |
| 15 | Exactly-one revision advance per change | `test_successful_change_advances_revision_exactly_once` | PASS |
| 16 | Undo restores previous selection | `test_undo_restores_previous_mobile_nav_selection` | PASS |
| 17 | Redo restores changed selection | `test_redo_restores_changed_mobile_nav_selection` | PASS |
| 18 | Draft Preview resolution / Published-unchanged-until-Publish / Public-after-Publish | `test_full_preview_publish_lifecycle` | PASS |
| 19 | `hidden` is the safe default, renders no nav markup | `test_hidden_variant_is_the_safe_default_and_renders_no_nav_markup` | PASS |
| 20 | Tenant isolation (mutation never touches a foreign Store's Draft) | `test_mutation_never_touches_a_foreign_stores_draft` | PASS |
| 21 | Zero migrations — round-trips through the existing `footer_config` JSONField | `test_mobile_nav_variant_round_trips_through_the_existing_footer_config_jsonfield` | PASS |
| 22 | Every registered variant appears in the editor projection | `test_every_registered_variant_appears_in_editor_projection` | PASS |
| 23 | Every registered variant is accepted by `footer.update` | `test_every_registered_variant_is_accepted_by_footer_update` | PASS |
| 24 | Every registered variant resolves to its own trusted renderer | `test_every_registered_variant_resolves_to_its_own_trusted_renderer` | PASS |

**24/24 PASS.** TDD RED confirmed genuine failures against the 4 gaps
before implementation (`tdd_red.txt`); GREEN confirmed all pass after the
minimal fix (`tdd_green.txt`).

## Focused/exact-source gates

- Focused sanity sweep (586 tests: `test_r4_vertical_slice`,
  `test_r4_mutation_api`, `test_u2b_global_footer_system`,
  `test_dark_digital_luxury_v2`, the W5B suite, `test_views`): 10
  failures + 1 error, **all confirmed pre-existing baseline identities**
  (`focused_tests.txt`).
- `manage.py check`: **clean, 0 issues.**
- `manage.py makemigrations --check --dry-run`: **"No changes detected."**

## Browser QA

**16/16 PASS** — full 18-step real mobile-viewport merchant journey
against the live R4 Builder (`browser_qa.md`, `browser_qa_console.txt`,
`browser_qa_results.json`): registry-driven options, independent-field
mutation acceptance, Footer-variant sibling isolation, Undo/Redo
round-trip, Draft-Preview/Public lifecycle around Publish, a second
Store's fresh-Draft `hidden` default, and stale-revision rejection all
demonstrated live.

## Independent code review

**CRITICAL: 0. IMPORTANT: 0.** Automated `code-review` skill pass:
zero findings. Manual verification against all 11 named checklist items
(duplicated authority, hardcoded variant choices, Footer sibling-state
corruption, manifest/footer_config divergence, stale-write bypass,
Undo/Redo divergence, Preview/Public mismatch, tenant leakage, new JS
mutation path, unnecessary migration, Design-Lab scope creep): all "None"
(`code_review.md`).

## Django check

Clean, 0 issues, at final HEAD.

## Full regression (exact-source)

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- **Result: `Ran 3502 tests in 3939.209s` — `FAILED (failures=30, errors=2, skipped=1)`.**
- Baseline (accepted W5A round-2, HEAD `128afd19`): 3478 tests, 30
  failures, 2 errors, 1 skipped.
- Test count increased by exactly 24 (3478 → 3502), matching the 24 new
  W5B tests, all of which pass.

## Identity-diff counts

- **NEW FAILURE/ERROR IDENTITIES: 0**
- **MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0**
- **CHANGED HISTORICAL FAILURE/ERROR REASONS: 0** (all 32 matched
  failure/error blocks byte-for-byte identical to baseline, including
  full tracebacks — see `full_suite_identity_comparison.md`)

## 704-cell Ready Template campaign

**NOT RUN** — renderer/Ready-Template architecture was not touched by
this diff (0 renderer/registry/template changes), per the directive's
policy.

## Architectural duplication count

**0.** `GLOBAL_MOBILE_NAV_REGION` remains the sole registry; no
parallel authority, hardcoded variant list, or second read/write path
was introduced anywhere in the chain (`authority_chain.md`,
`code_review.md`).

## Source diff

3 production files, 36 lines (`r4_mutation_service.py` +8/-1,
`r4_views.py` +7, `r4/editor.html` +20). Zero JavaScript changes. One
new test file (+454 lines, 24 tests). Zero migrations. Full breakdown:
`source_diff.md`.

## PR

Not yet opened as of this report — see push/PR step following this
document's commit.

## W5C started

**NO.**

## Worktree

**Clean** at final HEAD `94193557` (confirmed via `git status
--porcelain`).

## Final status

**COMPLETE.** All required gates pass: 24/24 new contract tests, 0 new/
missing/changed regression identities against the accepted W5A baseline,
16/16 browser QA, 0 CRITICAL/IMPORTANT code-review findings, clean
Django check, zero migrations, zero architectural duplication.

STOP. Do not merge. Do not start W5C. Return for Independent Architect
review.
