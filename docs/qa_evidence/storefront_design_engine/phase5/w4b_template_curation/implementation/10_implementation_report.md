# P5-W4B — 50-Template Curation — Implementation Report

**Approved design head:** `75decc08d9569b45744930044cc29a4dce65bb43`
(design gate: CRITICAL 0 / IMPORTANT 0 / BLOCKING MINOR 0).
**Certified official base:** `707dd631e851bdd13173bf3950489142f3e526b1`.
**Branch:** `feature/phase5-w4b-template-curation`.

## Scope

21 of the 50 Ready Templates made materially distinct by adding exactly
one new composition-token section to each, per the approved design's
final implementation matrix (design doc §15) and the newsletter-terminal
placement contract (design doc §16 / inventory §16). Zero new
architecture. Exactly 50 latest templates preserved. All 21 pre-curation
(v1) recipes preserved byte-for-byte as historical, resolvable versions.
Zero migrations. W4C untouched and not started.

## What changed (production)

`apps/storefront_builder/a8_ready_templates.py` only:

- One new `_STATIC_SECTIONS` entry: `"collection_tiles": "collection_tiles"`.
  The other two mechanisms used by this curation (`story_rail`,
  `brand_carousel`) already existed as `_STATIC_SECTIONS` tokens
  (`"community_gallery"` → `story_rail`, `"brands"` → `brand_carousel`);
  no second new token was needed.
- 21 `_RecipeSpec` rows edited in place (never appended): version bumped
  `"1"` → `"2"`, and exactly one new composition token inserted — appended
  at the end for 14 keys, inserted immediately before the terminal
  `"newsletter"` token for the 7 newsletter-terminal keys (`niloufar_glass`,
  `beauty_dew`, `laleh_play`, `almas_luxury`, `green_workshop`,
  `pine_eco`, `mirror_beauty`).
- A new `_HISTORICAL_SPECS` tuple (21 frozen rows, exact verbatim copies
  of the pre-curation v1 specs) registered through the same
  `register_layout_preset()` call used everywhere else, so they are
  resolvable via `get_layout_preset_version(key, "1")` but invisible to
  `list_ready_templates()`/`A8_READY_TEMPLATES` (which are built solely
  from `_SPECS`, i.e. the 50 latest rows) — this is what keeps the latest
  catalog at exactly 50 while making v1 fully preserved and queryable.

`apps/storefront_builder/layout_preset_registry.py` — byte-for-byte
unchanged (confirmed by `git diff` against the certified base showing no
hunks in that file); no new registry, renderer, section type, Theme
mechanism, tenant resolver, or other subsystem was introduced. Full
detail: `08_architecture_duplication_audit.md`.

## Test evidence (chronological)

| # | File | What it proves |
|---|---|---|
| 1 | `00_certified_w4a_fingerprints*.md/.txt` | 21 pre-curation v1 fingerprints captured at the certified base, before any production edit. |
| 2 | `01_red_w4b_contract_tests.txt` | RED: `test_w4b_template_curation.py` fails as expected (71 failures) before implementation. |
| 3 | `02_green_w4b_contract_tests.txt` | GREEN: same 19 tests pass after implementation — exact-50, explicit version map, full historical fingerprint match against evidence #1, historical forbidden-payload scan, exact composition matrix, newsletter-terminal contract, composition-token allowlist, rejected-mechanisms-absent, diversity contract, all-50 canonical apply regression. |
| 4 | `03_focused_green_existing_a8_u10_preset_suites.txt` | Existing A8/U10/preset contract suites (116 tests) still pass, including the one routine, design-authorized literal update to `EXPECTED_LATEST_VERSIONS` in `test_a8_ready_template_catalog.py`. |
| 5 | `04_additional_canonical_ready_template_suites.txt` | Broader canonical Ready-Template suites (327 tests); 1 failure, confirmed pre-existing (see below). |
| 6 | `05_full_storefront_builder_exact_head.txt` | Full `apps.storefront_builder.tests` at the implementation head: 3235 tests, 30 failures, 2 errors, 4 skipped. |
| 7 | `06_bounded_browser_qa_summary.md` + `browser_qa/`, `browser_qa_responsive/` | Bounded W4B browser QA: 21 templates × 3 viewports = 63/63 checks pass (RTL, no overflow, added section visible with a real primary link, no dead `href="#"`, no console/page/network errors); latest-vs-historical DOM comparison. |
| 8 | `07_django_check_migrations_gitdiff_gates.txt` | `manage.py check`, `makemigrations --check --dry-run`, `git diff --check` all clean. |
| 9 | `08_architecture_duplication_audit.md` | No new renderer/registry/section type/Theme mechanism/RandomMix engine/tenant resolver/ProductCard path/CMS or merchant-policy subsystem/browser authority; no merchant content in Template DNA; no new migrations. |
| 10 | `09_full_suite_exact_head_base_comparison.md` | Identity- and content-level comparison of the full suite against the certified base's own full-suite result (W4A's `32_full_storefront_builder_exact_head.txt`): 32/32 identical failing/erroring identities both directions; the only 2 blocks with any textual difference differ solely in a dumped HTML gallery body and a run-summary/exit-marker line, never in the assertion/failure reason itself. |

## Regression verdict

```
W4B-only failures/errors                    = 0
Changed pre-existing failure/error reasons  = 0
```

Test count grew by exactly 19 (the new `test_w4b_template_curation.py`
suite); failure/error/skip counts (30/2/4) are unchanged from the
certified base, and every one of those 32 pre-existing failures/errors
is the same identity with the same reason as at the certified base. The
one failure noted in evidence #5
(`test_u8_template_gallery::test_header_footer_variant_labels_shown_for_updated_preset`)
is this same pre-existing failure, not a new one — already confirmed
against the W4A baseline evidence (line 216 of
`w4a_public_shell_convergence/32_full_storefront_builder_exact_head.txt`)
and reconfirmed at assertion-reason granularity in evidence #10.

## Honest disclosure

One operational mistake occurred and was self-caught during browser QA
(an `rm -rf` on the wrong directory level briefly deleted 8 pre-existing,
already-committed preview files before anything was staged) — fully
reverted via `git checkout --`, zero data loss, no commit ever contained
the deletion. Documented in full in `06_bounded_browser_qa_summary.md`
under "Note on an operational mistake."

## Status

All 12 implementation-plan tasks complete. Ready for the final
clean-status evidence capture and PR creation. This report does not
authorize merge; W4B remains open pending Independent Architect review.
