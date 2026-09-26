# W4C Pilot Findings Closure — code review gate (Section 13)

Ran `/code-review` (high effort, single-pass) against this round's full
diff (`0f952194..4ff0ab10`): the Home-expectation repair
(`9f0d103e`) and the Cart-remove diagnostics repair (`48fb3171`,
`4ff0ab10`).

## Findings and disposition

| # | File | Summary | Severity | Disposition |
|---|---|---|---|---|
| 1 | `run.mjs` `w4cCartRealRemove` | `elapsed_ms` was nulled on timeout, discarding exactly the "timed out immediately vs. at the boundary" distinction this diagnostic exists to preserve | Correctness (diagnostic value) | **Fixed** |
| 2 | `run.mjs` `w4cCartRealRemove` | `http_status`/etc. attributed to the LAST POST response observed, which could belong to an unrelated later request, not the click's own HTMX effect | Correctness | **Fixed** — now uses the FIRST POST observed |
| 3 | `run.mjs` `w4cCartRealRemove` | A failed click still ran the full ~5s wait/poll hoping for a DOM change a broken click could never produce | Efficiency (real campaign wall-clock cost) | **Fixed** — early return when `click_error` is set |
| 4 | `qa_storefront_builder_r4.py` | `_home_hero_expected`/`_home_hero_index`/`_home_product_cards_expected` are no longer called from the production manifest-writing path after `_canonical_home_contract` replaces those call sites, but remain in the `Command` class | Hygiene (dead code) | **Not fixed this round** — see below |
| 5 | `run.mjs` `w4cCartRealRemove` | Hand-rolled fixed-interval polling instead of a Playwright built-in wait primitive | Style/architecture preference | **Not fixed this round** — see below |

## Fixes applied (1-3)

All three are implemented in `tools/storefront_builder_r4_qa/run.mjs`'s
`w4cCartRealRemove`, verified by 3 new regression tests (`test_8`,
`test_9`, `test_10` in `W4CCartRemoveDiagnosticsTests`) added to the
same real-Node-execution suite, plus the original 7 tests re-confirmed
green. Full output: `cart_tdd_green.txt` (superseded by this round's
final `full_suite_output.txt`/focused-suite evidence for the
post-review state).

## Findings not fixed this round, with reasoning

**Finding 4 (dead raw-recipe Home helpers).** These three methods are
still directly exercised by a pre-existing, legitimate test
(`test_13_hero_none_templates_computed_live_not_hardcoded`) that
asserts their own "data-driven, not hardcoded" contract against the
RAW recipe as an independent, narrower fact (which Ready Templates
declare no `hero_banner` token at all) — unrelated to
`_canonical_home_contract`'s job of deriving the actual W4C manifest
expectation from the canonical published render. Removing them would
require also rewriting that untouched, unrelated existing test, which
is out of this round's authorized scope (Section 11 authorizes
`qa_storefront_builder_r4.py`/`run.mjs`/the harness test file, but this
round's actual mandate is the two named findings, not an unrelated
cleanup). This is dead-code hygiene, not a functional defect — no
scenario produces an incorrect W4C result because of it. Left as-is;
flagged for a future cleanup round if the Architect wants
`test_13` rewritten against the new canonical contract instead.

**Finding 5 (hand-rolled polling vs. Playwright built-ins).** A valid
architectural preference, not a defect — the current implementation's
retry/timeout contract (poll every 150ms, bounded at 5s, condition =
real `.citem` count) is behaviorally correct and fully covered by the
new tests. Switching to `page.waitForFunction`/`expect(...).not.toHaveCount(...)`
would be a reasonable follow-up but is a style change with no
behavioral difference proven by this review, not a fix required before
the closure pilot.

## Verification after fixes

- `node --check tools/storefront_builder_r4_qa/run.mjs`: PASS.
- `W4CCartRemoveDiagnosticsTests`: 10/10 (7 original + 3 new).
- Full harness suite and remaining fast gates re-run clean after these
  fixes (see `full_suite_output.txt` / the round's final report for the
  authoritative final counts).
