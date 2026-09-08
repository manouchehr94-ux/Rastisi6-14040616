# Task 4 — Generalize the certified R4 QA browser certification harness

## Result: PASS

## Scope (plan's 3 required generalizations)

1. Extract the duplicated Brand/Collection browser assertion block in `run.mjs` into one
   shared parameterized helper covering every listed assertion category.
2. Restructure `manifest.phase3`'s single boolean into a real per-family gate-registration
   loop so new families register their own gate instead of piggybacking on the Brand/
   Collection flag.
3. Backfill the R4-schema-enable guard test across all non-schema-enabled families.

## Investigation — deriving the exact 45/36 baseline before touching anything

Per the plan's explicit requirement ("must preserve Brand 45/45 and Collection 36/36"), the
harness was run in `--phase3` mode BEFORE any code change to establish the exact current
counts, rather than trusting the number from Phase-3 prose:

```
.venv/bin/python manage.py qa_storefront_builder_r4 --store-slug akhlaghi \
  --username phase3_qa_owner --browser-channel auto --phase3 \
  --report-dir <scratch>/task4_baseline_phase3
```

Result: 16/16 scenarios PASS (`phase3-brand-gate` included), DB restore SHA256
`d53a687b...` match=True. The saved `metrics.json` shows exactly:

- `phase3.variant_checks.length === 45` — the Brand matrix (3 `PHASE3_VIEWPORTS` ×
  5 envelopes [home/product_detail/listing/collection/cart] × 3 `display_mode` variants
  [grid/carousel/beauty_tabs]).
- `phase3.collection.variant_checks.length === 36` — the Collection matrix (3 viewports ×
  6 envelopes [home/product_detail/listing/search/collection/cart] × 2 `tile_style` variants
  [grid/carousel]).
- `phase3.collection.known_red_findings === []` (0 — both pilot families are fully green
  today; the CSS gaps documented in the Task 7 code comments were fixed in a later Phase-3
  task and no longer trigger).
- `phase3.errors === []`, `phase3.collection.errors === []` (0 console/page/request errors).
- Scenario-level "16/16 PASS" is a DIFFERENT, coarser count (one row per top-level scenario
  function) and is explicitly NOT treated as a substitute for the 45/36 per-assertion
  matrices — both are captured and reported separately here, as required.

This baseline `metrics.json` was copied out of the scratch report dir before any `run.mjs`
edit, to diff against after the refactor.

### Execution environment (recorded per instruction, not assumed identical run-to-run)

- Python: 3.11.15 (`.venv`), Django 5.2.17.
- Node: v22.22.2, `playwright-core` resolved from `tools/storefront_builder_qa/node_modules`
  (the shared dependency `run.mjs` reuses via its own `createRequire` trick).
- Browser: pre-installed Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
  (`--browser-channel auto`).
- No version drift between the pre-refactor and post-refactor runs — both executed in the
  same container/session, same `.venv`, same Node/Chromium binaries, same dev DB fixture
  (store slug `akhlaghi`, staff user `phase3_qa_owner`). Recorded explicitly rather than
  assumed identical.

## Implementation

### 1. Shared parameterized helper (`tools/storefront_builder_r4_qa/run.mjs`)

Added `phase3FamilyPublicMatrix(cfg)` — the ONE implementation of the per
envelope × variant × viewport browser matrix: browser context/cookie setup, console/
page/request error collection (with the shared broken-image noise exemption), the asset
envelope check (`storefront_builder.css`/htmx/alpine exactly once, no duplicate URLs, no
`home.css` off-Home), document horizontal-overflow check, RTL `dir` assertion, computed
`display`/`gridTemplateColumns`/`gap`/`overflowX` layout check (both the "container is
grid/flex" half AND the "resolved tracks/overflow" half — never either alone), image
`objectFit` assertion, native horizontal `scrollLeft` proof, keyboard-focus proof, per-
variant screenshot capture, and the final zero-error gate.

Family-specific business logic is injected via config, not duplicated:
- `selectSection` — Brand disambiguates candidates by exact 5-tile count (the BASE fixture
  also has a brand_carousel on Home); Collection takes the first match.
- `tileSelector` / `imgSelector` / `extractTileData` — the two families' tile DOM shapes are
  unrelated (`a.brand-tile` + `?brand=<slug>` href vs `a.pcard[href*="/collections/"]` +
  `/collections/<slug>/` href) and are passed as standalone (no-closure) functions for
  `evaluateAll`.
- `classifyTiles` — Brand's decode-or-name-fallback rule (plus a bounded-logo-height
  assertion Collection has no equivalent for) vs Collection's decode-or-glyph-fallback rule
  (plus the broken-image-collection skip-and-record branch Brand has no equivalent for) and
  each family's own order/uniqueness assertion (Brand cross-checks all 3 variants agree and
  optionally matches an expected slug list; Collection asserts newest-first per variant).
- `afterClassify` — Brand's V02 View-all-anchor truth check; a no-op for Collection.
- `onLayoutIssue` — Brand's grid/rail layout mismatch is a hard `assert(false, …)` (never
  observed in practice); Collection's is recorded into `known_red_findings` instead of
  thrown, preserving the exact pre-existing "collect all evidence, gate at the end"
  behavior documented in the original code's comments (a real, still-live CSS-cascade gap
  on non-Home envelopes that predates this task and is not being silently re-labeled or
  removed here).
- `afterVariants` — Brand's cross-variant order-equality check; a no-op for Collection
  (whose order check is already per-variant, inside `classifyTiles`).

`phase3PublicMatrix(fx, envelopes)` and `phase3CollectionPublicMatrix(c, envelopes)` are now
thin wrappers that build the config object and delegate — both function names/signatures are
unchanged so every existing caller (`phase3BrandGate`, `phase3CollectionGate`) needed no edit
beyond the registry change in item 2 below.

One real bug caught by re-running the harness after the extraction (not by static review):
Playwright's `Locator.evaluate(fn, arg)` accepts exactly one extra argument, not two — an
early draft passed `(containerSel, imgSelector)` positionally, which Playwright rejects
outright (`locator.evaluate: Too many arguments`). Fixed by bundling both into one object
argument (`{ sel, imgSel }`), destructured in the page-side function. Caught immediately by
the post-refactor `--phase3` re-run (`FAIL phase3-brand-gate`), confirming the parity-proof
step below is load-bearing, not a formality.

### 2. Per-family gate-registration loop

Added `PHASE3_FAMILIES` — an array of `{ key, run, knownRedFindings }` entries. `brand`'s
`run` wraps its existing fixture/envelope/matrix/extras call sequence (`phase3PublicMatrix`
+ `phase3WrapperProjection` + `phase3CartHtmx` + `phase3BrandBrokenImage`); `collection`'s
`run` wraps `phase3CollectionGate`. `phase3BrandGate` now loops
`for (const family of PHASE3_FAMILIES) { await family.run(fx); }` instead of the two
hand-written sequential call blocks, and the final known-red gate assertion is
`PHASE3_FAMILIES.flatMap((f) => f.knownRedFindings())` instead of reading
`phase3.collection.known_red_findings` directly. A Task 6 family registers here — supplying
its own `run()`/`knownRedFindings()` — rather than editing `phase3BrandGate`'s body again.
`phase3CombinedCartHtmx` (which spans Brand+Collection by design, proving they coexist on
one Cart page) deliberately stays outside the per-family loop, called once after it.

`manifest.phase3` itself (the one opt-in flag threaded from the Python command) and the
`phase3-brand-gate` scenario name are both unchanged — this task restructures what happens
*inside* that one opt-in scenario, not the opt-in mechanism itself or its historical name
(which Phase-3 evidence docs already reference).

### 3. Schema-enable guard backfill

`NoOtherSectionBecomesSchemaEnabledTests` (added in Phase 3) only ever spot-checked two
families (`image_slider`, `faq`) against accidental schema-enablement. Added
`SchemaEnablementRegistryGuardTests` in `test_r4_settings_schema.py`: enumerates every
`section_registry.list_definitions()` entry and asserts `settings_schema is not None` for
exactly the 5 keys registered as schema-enabled today (`hero_banner`, `brand_carousel`,
`rich_text`, `product_section`, `collection_tiles`) and `is None` for every other of the 36
registered keys. As Task 6 gives a MIGRATE family its own R4 schema, this test fails
immediately unless that family's key is deliberately moved into
`EXPECTED_SCHEMA_ENABLED` in the same change — no family can become schema-enabled (or
silently regress) without this guard noticing, which is what "needs this guard from the
start" requires.

## Verification

### Parity proof — the refactor changes structure, not outcome

Re-ran the identical `--phase3` command against the refactored `run.mjs` (same store/user/
fixture, same environment) and diffed the new `metrics.json` against the saved pre-refactor
baseline:

| Metric | Pre-refactor | Post-refactor | Match |
|---|---|---|---|
| `variant_checks` (Brand) | 45 | 45 | ✅ identical (order-insensitive by envelope/viewport/variant) |
| `variant_checks` (Collection) | 36 | 36 | ✅ identical |
| `v02_anchor` (Brand) | 45 | 45 | ✅ identical |
| `known_red_findings` (Collection) | 0 | 0 | ✅ identical (still empty) |
| `errors` (Brand / Collection) | 0 / 0 | 0 / 0 | ✅ identical |
| `broken_image_records` (Collection) | 36 | 36 | ✅ identical |
| `combined_cart_htmx` | 3 | 3 | ✅ identical |
| `envelopes` (Brand / Collection) | 15 / 18 | 15 / 18 | ✅ identical |
| `asset_envelope` (Brand) | — | — | ✅ byte-identical |
| `asset_envelope` (Collection) | no `clientWidth` field | has `clientWidth` field | ⚠️ additive only |
| DB restore SHA256 | `d53a687b...` | `d53a687b...` | ✅ match=True |
| Scenario-level count | 16/16 PASS | 16/16 PASS | ✅ identical |

The one difference (`clientWidth` newly present on Collection's `asset_envelope` records) is
a side effect of the two families now sharing one asset-envelope-recording code path — Brand
already recorded `clientWidth`; Collection did not. This is a strictly additive field on a
metrics record, not a weakened, narrowed, or removed assertion, and it does not change any
pass/fail outcome or any of the 45/36 counts. No assertion was weakened to make the
refactored harness pass; the one real behavior difference (the `.evaluate()` two-argument
bug) was caught as a FAIL by this exact parity re-run and fixed before this evidence was
written, not discovered after the fact.

### Test suites

- `test_r4_settings_schema` (includes the new `SchemaEnablementRegistryGuardTests`):
  **64/64 pass**.
- `test_qa_harness_contract` + `test_r4_mutation_api` + `test_phase3_v5_golden`:
  **78/78 pass**.
- Official Phase-3 baseline Run A/B/C (`phase4/baseline.md`'s exact command lists):
  - Run A: **755 tests, 1 failure + 1 skip** — the failure is the known pre-existing
    signature `test_validate_appearance_config_is_the_validator_boundary`.
  - Run B: **121 tests, 2 failures + 1 error** — two are the known pre-existing
    fullscreen-topbar signatures (`test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`,
    `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`). The third
    (`test_header_footer_variant_labels_shown_for_updated_preset` in
    `test_u8_template_gallery.py`) had not been previously documented in any Phase 4
    evidence doc, so it was explicitly classified rather than assumed benign: reproduced
    in isolation (fails standalone, not a test-ordering artifact), then reproduced again
    against the clean, committed `HEAD` (`9bacc80`) via `git stash` with every Task 4 edit
    removed — it fails identically there. This is a pre-existing gap unrelated to Task 4
    (which touches only `run.mjs` and `test_r4_settings_schema.py`, neither related to
    template-gallery header/footer variant labels), confirmed exact, not a new regression,
    and out of Task 4's scope to fix.
  - Run C: **77/77 pass**, clean.
  - Combined: 953 tests, 3 failures + 1 error, all four matching known-or-now-classified
    pre-existing signatures, 1 skip — zero new regressions from this task's changes.
- `python manage.py check`: clean. `python manage.py makemigrations --check --dry-run`:
  clean (no model changes in this task).
- `node --check tools/storefront_builder_r4_qa/run.mjs`: clean, both before and after the
  fix.

### Execution environment note (Run A/B/C)

Same `.venv` (Python 3.11.15, Django 5.2.17) and same working tree as the harness runs
above; no environment drift between the targeted-suite runs and the harness runs in this
task.

## STOP conditions checked

No second harness, command, package, or endpoint was created — this is a structural
refactor of the one existing `run.mjs`/`qa_storefront_builder_r4.py` pair. No assertion
category was weakened, removed, or silently relabeled to make the generalized code pass;
the one pre-existing "known RED, recorded not thrown" policy (Collection's CSS-cascade gap)
is preserved exactly, including its documented rationale. The schema-enable guard addition
does not itself schema-enable any new family — it only backfills coverage of the registry
as it exists today, ahead of Task 6.
