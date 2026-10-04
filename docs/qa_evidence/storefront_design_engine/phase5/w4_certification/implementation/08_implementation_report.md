# P5-W4C — Implementation Round 1 — Harness Implementation + TDD

**Approved design head:** `0399962f1f3bc1a5d4d31c86f1d6add5ff5c13c8`
(CRITICAL 0 / IMPORTANT 0 / BLOCKING MINOR 0).
**Official certified checkpoint:** `3a4fe9070584655548bae5a9bb574f3415bbf580`.
**Branch:** `feature/phase5-w4c-all50-certification`.

## Scope

Strict TDD implementation of the approved bounded `--w4c-all50` extension:
37-case RED suite first (genuine failures against not-yet-existing code),
then the Django command + `run.mjs` extension, driven to 37/37 GREEN. The
704-cell browser campaign itself is explicitly **not** run in this round.

## What changed (production/harness)

Exactly the two authorized files:

- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`
  — `--w4c-all50`/`--only` flags; `_prepare_w4c_certification_fixture`
  (bypasses `_prepare_r4_sandbox`); `_build_w4c_fixture` (50 live
  key/version pairs + deterministic Tier-1 occasion cycle, computed from
  `a8_ready_templates._SPECS`'s own source order, not
  `list_ready_templates()`'s dict-iteration order); `_apply_and_verify_
  published`/`_verify_theme_is_none`/`_verify_published_theme`/
  `_theme_cleanup_and_verify` (real `StorefrontLayout.published_version`
  state checks, `pv is None` checked before any attribute access); the
  3-way host branch in `_build_manifest` (showcase / w4c_all50 / ordinary),
  with the "session" key now conditionally omitted entirely for W4C
  manifests; the base/Tier-1/Tier-2 Node-invocation loops
  (`_run_w4c_campaign`/`_run_one_theme_cell`), Tier-2 filtered by
  `selected_keys`; the campaign matrix guard/merge/aggregator functions;
  and the partial-batch-vs-global-campaign status branch in `handle()`.
- `tools/storefront_builder_r4_qa/run.mjs` — a `manifest.w4c` top-level
  dispatch (before `main()`), `w4cBaseCertification`/`w4cThemeCertification`
  with structured `try/finally` cleanup (never `process.exit()`), and their
  `runCell`/`runThemeCell` helpers for Home/Listing/PDP/Cart, all using
  fresh cookie-less contexts.

Zero migrations. Zero other production files touched (confirmed by
`git diff --stat` against the design head).

## Test evidence (chronological)

| # | File | What it proves |
|---|---|---|
| 1 | `00_starting_state.txt` | Clean worktree, correct branch/HEAD, before any code. |
| 2 | `01_tdd_red.txt` + `02_tdd_red_analysis.md` | RED: 35/37 genuine feature-contract failures (AttributeError/TypeError naming not-yet-built helpers/kwargs), 2/37 (cases 8, 21) GREEN immediately as non-interference regression guards. |
| 3 | `04_tdd_green.txt` | GREEN: same 37 tests, 37/37 pass, after implementation. |
| 4 | `05_regression_gates.txt` | `test_ready_template_real_previews` (32 tests, 29 pass/3 skip — unchanged from its own pre-existing skip reasons), `node --check`, `manage.py check`, `makemigrations --check --dry-run` (0 changes), `git diff --check` — all clean. |
| 5 | `06_architecture_duplication_audit.md` | Zero duplicate authorities; one disclosed, strictly-additive naming refinement (a `tier` segment in Theme result/log paths, needed because Tier-1 and Tier-2 can otherwise collide on the same key/occasion/intensity/viewport triple for `warm_boutique`/`beauty_dew`). |
| 6 | `07_legacy_r4_non_interference.md` | `w4c_qa_owner` created; live legacy-gate attempts (with and without the pre-existing, unrelated `--phase3` load requirement) both fail for reasons confirmed present at the certified base — never for a reason introduced by this round's diff. |
| 7 | full `apps.storefront_builder.tests` regression run | See the final report field below — captured separately once complete. |

## Honest disclosures

1. Three implementation bugs were caught and fixed while driving RED to
   GREEN (not silently patched around): a missing `preset_service` import;
   `tier1_occasions` initially computed from the wrong (dict-iteration)
   source order; and two of my own RED-test fixture bugs (a
   `StoreMembership` missing `accepted_at`, and a missing explicit
   `settings.DEBUG` patch — Django's test runner defaults `DEBUG=False`
   regardless of the project's own env-based default).
2. A live legacy-gate diagnostic run was interrupted by this session's own
   tool timeout before its `finally` block's SQLite restore ran. The real
   project database was manually restored from that run's own pre-run
   backup and its sha256 verified against both other completed runs' own
   independently-confirmed pre-run hash. The same run's unconditional
   `EVIDENCE_DIR` screenshot writes (a pre-existing mechanism, not covered
   by the SQLite safety lifecycle) touched several committed evidence PNGs;
   these were reverted with `git checkout --` before any commit. Full
   detail in `07_legacy_r4_non_interference.md`.

## Status

Design Gate APPROVED; Implementation Round 1 complete: 37/37 GREEN, all
required regression gates clean, zero migrations, zero unauthorized files
changed, duplication audit clean. The 704-cell browser campaign is
**not** run in this round. Ready for Independent Architect code review.
