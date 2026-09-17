# P5-W4C — All-50 Browser Certification — Implementation Plan

**Certified official base:** `3a4fe9070584655548bae5a9bb574f3415bbf580`
**Branch:** `feature/phase5-w4c-all50-certification`
**Companion document (read first):**
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/w4c_harness_inventory.md`
— contains the full source citations, the complete 50-Template table, and the
harness-classification reasoning this plan's decisions are built on. This plan
does not repeat those citations; it only restates the conclusions needed to
execute.

**Status of this document:** plan/inventory only. No production code, Django
test code, or QA harness code changes are authorized by this document. Every
task below is deliverable only after a separate authorization round.

---

## 0. Scope recap

- Goal: real browser closure gate for **all 50** current merchant-facing Ready
  Templates (not a representative subset).
- Reuse-only: extend
  `apps/storefront_builder/management/commands/capture_ready_template_previews.py`
  (Classification B, bounded extension — see harness inventory §3). No second
  harness, no second Playwright package, no second browser launcher, no second
  public-storefront renderer, no parallel Apply/Publish authority, no
  separate W4C-only route system.
- Evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.
- W5 remains frozen until this workstream merges with zero unresolved
  CRITICAL/IMPORTANT findings.

---

## 1. Exact matrix cardinality

```
Base matrix:   50 Templates × 4 page classes (Home, Listing, PDP, Cart) × 3 viewports (Desktop 1440x900, Tablet 768x1024, Mobile 390x844)
             = 600 certification cells

Theme matrix:  Tier 1 (breadth) — 3 occasions (nowruz, ramadan, muharram) x balanced intensity x Desktop only x 40 representative Templates = 120 cells
               Tier 2 (depth)   — 2 Templates x 3 occasions x 3 intensities x 3 viewports = 54 cells
             = 174 additional cells

TOTAL:         774 certification cells
```

The 40-Template Theme representative set (union of one Template per distinct
`(header, footer, bottom_nav)` triple — 33 triples — and all 21 W4B-curated
keys, deduplicated):

```
almas_luxury, anniversary_mosaic, artisan_grain, beauty_dew, cedar_home,
city_classic, coastal_product, collection_index, dark_digital,
dense_marketplace, editorial_jewelry, fashion_promo_catalog, green_workshop,
handmade_luxe, harbor_imports, horizon_story, kamand_artisan, laleh_play,
literary_catalog, mina_community, mirror_beauty, night_catalog,
niloufar_glass, parnian_editorial, pine_eco, pixel_play, playful_lifestyle,
premium_leather_noir, racer_tech, rayan_tech, roosta_zigzag, search_market,
silk_editorial, simorgh_market, street_drop, tool_finder, tuska_bento,
utility_catalog, warm_boutique, watchmaker_round
```

Tier 2's 2 Templates: `warm_boutique` (one of W2's own original certified
Templates, for continuity) and `beauty_dew` (a W4B-curated Template whose new
`community_gallery`/`story_rail` section family postdates W2's own Theme
certification — closes the gap the harness inventory identifies).

No reduction of the 600-cell base matrix was found to be architecturally
required (harness inventory §5). If execution later discovers a genuine
architectural impossibility for one page class on one Template, that specific
cell is marked `BLOCKED — <reason>` in the JSON matrix and escalated to
Architect review; the matrix is never silently shrunk.

---

## 2. Shared certification fixture

- **Store:** `rasti-mode-demo`.
- **Seed command:** `python manage.py seed_ready_template_fashion_demo`
  (idempotent — safe to re-run before each execution batch).
- **PDP fixture product:** the first product returned by
  `Product.objects.filter(store=store, product_type=Product.ProductType.VARIABLE).order_by("id").first()`
  from the seeded catalog — deterministic (ordered by `id`, not random),
  guaranteed to exist because `_seed_variants` seeds at least one
  size/color-variable product.
- **Cart fixture:** add that same deterministic product (quantity 1) via the
  canonical `cart:add` route for every Cart cell — never direct DB session
  manipulation.
- **Theme:** applied/cleared via the canonical
  `appearance_authority_service.apply_theme` / `clear_theme` functions only
  (same functions R4's own Theme panel calls) — never a second Theme
  mechanism.
- Same merchant data used for every one of the 50 Templates — no per-template
  fixture variation, no fixture IDs written into any `_RecipeSpec`.

---

## 3. Canonical harness extension target

`apps/storefront_builder/management/commands/capture_ready_template_previews.py`
gains, in a later authorized implementation round:

- A new flag, e.g. `--certify` (name TBD-by-implementer within this file only,
  not a new file/command), that runs the existing per-template apply/publish/
  navigate loop plus:
  - The existing Home/Listing/PDP captures, **plus** a new Cart capture
    (navigate to `cart:detail` after a canonical `cart:add`).
  - A new Tablet viewport alongside the existing Desktop/Mobile ones.
  - The assertion logic of §4–§7 below, using the Python `playwright` package
    this file already imports (`sync_playwright`) — no new dependency.
  - JSON result emission (§8 schema) alongside the existing screenshot
    capture — the existing screenshot behavior (used by the Gallery UI cache)
    is preserved unchanged when `--certify` is not passed.
- Reuses, unchanged: `_find_chromium_executable`, the
  `ThreadPoolExecutor(max_workers=1)` ORM-thread-safety wrapper, the
  `--host-resolver-rules=MAP <public_host> 127.0.0.1` navigation pattern, the
  fresh-Chromium-per-Template isolation, and the existing `--only <key>`
  per-Template filter (extended to accept a comma-separated list for batch
  execution, §11).

No other file under `apps/`, `tools/`, or `migrations/` is touched by this
extension.

---

## 4. Pass/fail contract — Home

For every Template × viewport:

- [ ] HTTP 200 on the Store's public root.
- [ ] `<html dir="rtl">`.
- [ ] No horizontal overflow (`document.documentElement.scrollWidth <=
  document.documentElement.clientWidth + 2`).
- [ ] Exactly one `<header>` element (source-confirmed: every public-path
  header variant renders through `page_shell_header.html` or a
  `global_header/*` variant that itself emits exactly one `<header>`; the
  only other `<header>` tags in the template tree are confined to
  `dashboard/` admin templates, never reached by `home_visual.html`).
- [ ] Hero healthy: the Template's own declared `hero` variant partial
  rendered without a JS/console error and produced at least one visible
  media/copy element (checked via the existing `.rsec` positional index for
  the `hero_banner`/hero-carrying composition token — reusing the exact
  `.rsec` NodeList-index technique W4B's browser repair already proved,
  never a new DOM marker).
- [ ] Home composition rendered: `.wrap.sfb-preview-sections .rsec` count ==
  `len(preset.pages["home"])` (the exact registry-known composition length —
  same technique as W4B's `browser_qa_responsive_repair` script).
- [ ] Product Cards present and healthy: at least one `article.pcard` (or the
  Template's declared `card` variant's own real card selector) present
  wherever the Home composition includes a product-bearing section
  (`product_grid`/`product_rail`/`bento_products`/`featured_products`/etc.),
  each card resolving a real `href` (never `#`).
- [ ] Exactly one `<footer>` element (same source-confirmed reasoning as
  Header).
- [ ] Bottom Navigation follows the canonical responsive contract: `.gmn`
  (or the Template's declared `bottom_nav` variant class) computes
  `display:none` at Desktop/Tablet and a non-`none` display at Mobile — the
  exact `@media(max-width:680px)` breakpoint already in
  `storefront_builder.css`, never a new breakpoint.
- [ ] No duplicate shell: header/footer/bottom-nav counts above are exactly
  1/1/(0 or 1), never more.
- [ ] No duplicate functional sections: for every section family present in
  the Template's composition more than once by design (e.g. `harbor_imports`'
  two `product_section` rows — a pre-existing, approved duplication, not a
  W4C regression), the count matches the registry-declared composition
  exactly; any COUNT MISMATCH against the registry is a FAIL.
- [ ] No placeholder primary `href="#"` anywhere in the rendered Home page.
- [ ] Zero new console errors (compared against the certified W4B baseline
  console-error set for that Template, §10 — a pre-existing, already-known
  console warning is not a new W4C failure).
- [ ] Zero page (JS) errors.
- [ ] Zero unexpected failed requests (favicon 404s and the pre-existing
  "expected preview abort" pattern already excluded by
  `capture_ready_template_previews.py`'s sibling tools are excluded here
  too, never a new exclusion invented ad hoc).
- [ ] Accessibility-critical controls (§7) pass for every control actually
  present on Home for this Template (mobile-nav opener if the Template's
  header variant has one; search control if present).

---

## 5. Pass/fail contract — Listing

Route: `catalog:product-list` (`/products/`). For every Template × viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4 (reused, not
  redefined).
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Product cards rendered via the Template's declared `card` variant
  (same `article.pcard`/`a.pcard-hitarea` canonical markers
  `product_card.html` already emits for every card style).
- [ ] Search/filter/sort/pagination controls present and usable where the
  Listing page renders them (reusing the exact `<nav>`-labelled pagination
  and `form[role=search]` contract already proven by
  `public_task7_qa.mjs` — never a new selector).
- [ ] Real product links (first product card's `href` resolves, HTTP 200).
- [ ] No dead interaction (no `href="#"`, no disabled-looking control that
  is actually meant to be active).
- [ ] Accessibility-critical controls (§7) for filter/sort/pagination.
- [ ] Zero new console/page/request errors.

---

## 6. Pass/fail contract — PDP

Route: `catalog:product-detail` for the deterministic fixture product (§2).
For every Template × viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4.
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Product gallery renders at least one image element.
- [ ] Price displayed.
- [ ] Stock/availability state displayed (in-stock, since the fixture
  product is in stock — an out-of-stock cell is out of this matrix's scope,
  covered instead by existing unit/contract tests).
- [ ] Variant controls present and change the displayed price/availability
  when a different Size/Color option is selected (the fixture product is
  guaranteed variant-bearing, §2).
- [ ] Quantity control present and adjustable.
- [ ] Add-to-Cart path: submitting the canonical `hx-post="/cart/add/..."`
  form succeeds (cart count increments) — the exact form
  `public_task8_qa.mjs` already proved is the single shared form for both
  the in-flow CTA and the mobile Sticky-Add-to-Cart bar.
- [ ] Mobile Sticky-Add-to-Cart bar present at Mobile viewport where the
  Template's `bottom_nav`/shell declares it (reusing `public_task8_qa.mjs`'s
  own hidden-on-desktop/visible-on-mobile/no-content-obscuration checks,
  never re-invented).
- [ ] Product Detail Tabs (Desktop, ARIA `role=tab`/`tabpanel`) or Accordion
  (Mobile, DOM source-order) contract — reusing `public_task5_qa.mjs`'s
  existing checks verbatim.
- [ ] Real navigation: at least one in-page link (e.g. back to Listing or a
  related-category link if present) resolves HTTP 200.
- [ ] Accessibility-critical controls (§7) for variant/quantity/Add-to-Cart.
- [ ] Zero new console/page/request errors.

---

## 7. Pass/fail contract — Cart

Route: `cart:detail`, after one canonical `cart:add` of the fixture product.
For every Template × viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4.
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Cart item(s) rendered (the fixture product's line item visible).
- [ ] Quantity control present; incrementing via `cart:item-update` reflects
  in the displayed line total and cart total (no duplicated commerce math —
  the displayed total matches `apps/cart/services/pricing.py`'s own
  computed total, read from the same context the template renders, never a
  second client-side recomputation).
- [ ] Remove mechanic (`cart:item-remove`) present and functional.
- [ ] Totals displayed.
- [ ] Checkout CTA present.
- [ ] Free-Shipping Goal widget (from W1) rendered in its below-threshold or
  above-threshold state consistent with the fixture product's price vs. the
  Store's configured threshold — reusing `public_w1_qa.mjs`'s own
  progress-bar-bounded-width/RTL/overflow checks, never re-invented. The
  all-digital and empty-cart states are out of scope for this per-Template
  matrix (already certified once, fixture-independently, by W1 — see harness
  inventory §6).
- [ ] Accessibility-critical controls (§7) for quantity/remove/checkout.
- [ ] Zero new console/page/request errors.

---

## 8. Accessibility-critical contract (bounded, technical — not a WCAG audit)

Only the controls actually exercised above are checked; nothing broader is
claimed. For each control below, present-and-exercised implies these checks
run; absent-for-this-Template implies the check is skipped (recorded as
`n/a`, never silently passed):

- [ ] Mobile navigation opener/closer: accessible name, `aria-expanded`
  state toggles, keyboard-focusable, Escape closes (reusing
  `public_task5_qa.mjs`'s Drawer focus-trap/return contract).
- [ ] Search control: `form[role=search]`, `input[name=q]` accessible name
  (reusing `public_task7_qa.mjs`).
- [ ] Product Card primary link / Quick View trigger: accessible name,
  keyboard-focusable (reusing `public_task5_qa.mjs`'s Quick-View focus
  containment/return contract where the Template's card style exposes one).
- [ ] PDP variant and quantity controls: accessible name, semantic
  `<select>`/`<input type=number>` or ARIA-equivalent, keyboard-operable.
- [ ] Add-to-Cart: accessible name, disabled state exposed via
  `aria-disabled`/`disabled` (never a purely visual-only disabled state) for
  out-of-stock (verified once against a deliberately out-of-stock fixture
  product, not per-Template).
- [ ] Cart quantity/remove/checkout controls: accessible name,
  keyboard-operable.
- [ ] Theme controls: not exercised (Theme's own R4 controls are an
  admin-editor concern, not exposed on the public certification path — this
  contract explicitly does not claim public-path Theme accessibility beyond
  what §9's Theme matrix already checks structurally).

---

## 9. Theme interaction contract

See harness inventory §8 for the full source justification. Execution
contract:

- [ ] Tier 1 — for each of the 40 representative Templates (§1): apply
  `nowruz`/`ramadan`/`muharram` at `balanced` intensity (one occasion per
  Template-occasion cell, cycling through the 3 occasions across the 40
  Templates so each occasion is exercised roughly evenly — exact assignment
  recorded in the JSON matrix, not left to run-time randomness), Desktop
  only: verify `data-occasion-theme`/`data-occasion-tone`/
  `data-occasion-intensity` attributes appear on `<html>`, zero new console/
  page/overflow errors, and (wherever the occasion applied is `muharram`) no
  festive/sale/countdown marker is visibly introduced. Then `clear_theme`
  and re-capture Home: the resulting DOM must match the Template's own
  pre-Theme baseline Home capture (byte-identical `.rsec` sequence and
  section content — Theme touches only shell attributes/CSS vars per its own
  Reversibility guarantee).
- [ ] Tier 2 — for `warm_boutique` and `beauty_dew`: full 3 occasions × 3
  intensities × 3 viewports sweep (mirroring W2's own certified 54-case
  shape), same pass criteria as Tier 1 plus per-intensity attribute-value
  verification (`data-occasion-intensity` matches the applied intensity
  exactly).
- [ ] Any Tier-1 or Tier-2 FAIL is a certification blocker for the Template
  involved and is reported per §13 — it does not silently reduce to a
  "known limitation."

---

## 10. Visual distinctness contract

Structural uniqueness (W4B's `recipe_signature()`/diversity contract) and
rendered visual certification are separate gates; both are required, and a
passing structural signature never substitutes for a rendered check here.

- [ ] Build one **rendered-identity matrix**: for all 50 Templates, tabulate
  (from real Home Desktop captures, not from source) the actually-rendered
  Header family, Hero family, layout/composition shape, Product Card style,
  density, typography, Footer family, and Bottom-Nav style — i.e. the same
  axes already in the harness-inventory §4 table, but confirmed against the
  rendered screenshot, not merely the recipe.
- [ ] Cluster the 50 by this rendered-identity matrix. Any cluster of 2+
  Templates whose rendered identity differs ONLY by palette/font/radius
  (never by Header/Hero/layout/Product-Card/density/typography/Footer/
  Bottom-Nav) is flagged `NEEDS REPAIR` — palette-only difference is
  explicitly insufficient per the plan's own text.
- [ ] Any `NEEDS REPAIR` finding STOPS the certification run for that pair/
  cluster and is returned for a separate, reviewed repair round before
  certification can close — it is never silently passed because
  `recipe_signature()` was already unique (W4B's structural test does not
  inspect rendered output).
- [ ] The rendered-identity matrix and cluster findings are published as
  `visual_distinctness_matrix.json` + a human-readable
  `visual_distinctness_matrix.md` (§11).

---

## 11. Evidence-volume contract

Canonical evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.

Required artifacts:

1. `matrix.json` — one machine-readable file covering every one of the 774
   certification cells (§1), schema in §12.
2. `home_gallery/` — exactly 50 files, one canonical Home Desktop screenshot
   per Template (mandatory, for W5 review), named `<key>_home_desktop.jpg`.
3. `gallery_index.md` — a single 50-row index (key, label_fa, thumbnail
   reference, rendered-identity summary) suitable for Product Owner/W5
   review — no separate per-Template markdown files.
4. `representative_screenshots/` — one Desktop screenshot per Template for
   Listing, PDP, and Cart (50 × 3 = 150 files) for the passing, non-Home page
   classes; Tablet/Mobile screenshots for these page classes are NOT
   committed when `matrix.json` already proves the result (per the plan's
   own "do not commit thousands of redundant screenshots" instruction) —
   Tablet/Mobile checks still run and are still recorded in `matrix.json`,
   only their screenshots are not retained on success.
5. `failures/` — a screenshot for every FAILING non-Home cell, at the exact
   viewport that failed, named `<key>_<page_class>_<viewport>_FAIL.jpg`. Home
   failures reuse the mandatory `home_gallery/` asset (already committed) and
   need no separate failure screenshot.
6. `theme_qa/` — Tier 1/Tier 2 screenshots (§9): one per Tier-1 cell that
   fails (failure-only) plus all Tier-2 cells (27 × 2 = 54, retained in full
   since Tier 2 is the small, deliberately deep sample).
7. `visual_distinctness_matrix.json` + `.md` (§10).
8. `failure_summary.md` — every FAIL/BLOCKED cell across all 774, one row
   each, with the exact reason.
9. `browser_error_summary.md` — aggregated console/page/failed-request
   findings across the whole run, cross-referenced against the certified
   W4B/pre-existing baseline (§13) so only genuinely new errors are flagged.
10. `architecture_duplication_audit.md` — confirms zero new renderer/
    registry/section-type/Theme-mechanism/tenant-resolver/ProductCard-path/
    cart-path/Bottom-Nav-system/search-backend/parallel harness was
    introduced by the bounded extension (§3).
11. `execution_report.md` — narrative tying together all of the above,
    modeled on W4B's own `10_implementation_report.md`.

Never committed: a screenshot for every passing Tablet/Mobile
Listing/PDP/Cart cell (450 of the 600 base cells' potential screenshots are
intentionally not retained — proven instead by `matrix.json`).

---

## 12. Machine-readable matrix schema

Directly descended from W4B's `browser_qa_responsive_repair/summary.json`
shape (harness inventory §1.6), extended with a `page_class` dimension:

```json
{
  "key": "cedar_home",
  "version": "2",
  "page_classes": {
    "home": {
      "desktop": { "...": "see §4 fields" },
      "tablet": { "...": "see §4 fields" },
      "mobile": { "...": "see §4 fields" }
    },
    "listing": { "desktop": {}, "tablet": {}, "mobile": {} },
    "pdp": { "desktop": {}, "tablet": {}, "mobile": {} },
    "cart": { "desktop": {}, "tablet": {}, "mobile": {} }
  },
  "theme": {
    "tier1_cell": { "occasion": "nowruz", "intensity": "balanced", "...": "..." },
    "tier2": null
  }
}
```

Each per-viewport object carries, at minimum: `http_status`, `rtl`,
`overflow`, `header_count`, `footer_count`, `bottom_nav_present`,
`bottom_nav_display`, `rsec_count`, `expected_rsec_count`,
`product_cards_present`, `dead_href_count`, `console_errors` (list),
`page_errors` (list), `failed_requests` (list), `accessibility_checks`
(object, per §8), `result` (`"PASS"`/`"FAIL"`/`"BLOCKED"`), `reason` (string,
required when `result != "PASS"`), `screenshot` (path or `null` when not
retained per §11).

A top-level `_meta` object records: `run_started_at`, `run_finished_at`,
`certified_base_sha`, `w4c_branch_head_sha`, `total_cells_expected` (774),
`total_cells_recorded`, `missing_cells` (list — must be empty for a valid
PASS report), `duplicate_cells` (list — must be empty).

---

## 13. Regression / baseline comparison strategy

- [ ] Run `python manage.py check --settings=shop_core.settings` — expect
  clean.
- [ ] Run `python manage.py makemigrations --check --dry-run
  --settings=shop_core.settings` — expect "No changes detected". If W4C's
  bounded harness extension requires any production code or migration beyond
  the one management command listed in §3, STOP for Architect review before
  proceeding — this workstream is QA/evidence, not a production-behavior
  change.
- [ ] Run `git diff --check` — expect clean.
- [ ] Re-run `apps.storefront_builder.tests` in full and compare failure/
  error identities against the certified W4B evidence
  (`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/09_full_suite_exact_head_base_comparison.md`
  and `05_full_storefront_builder_exact_head.txt` — 3235 tests / 30 failures
  / 2 errors / 4 skipped, W4B-only failures/errors = 0). Historical baseline
  failures are never automatically treated as W4C regressions; only a
  genuinely NEW failure/error identity, or a CHANGED reason for an existing
  one, counts as a W4C regression. Extending
  `capture_ready_template_previews.py` is not expected to change any
  existing test's identity or reason (it is additive, opt-in behind a new
  flag) — this must still be verified, not assumed.
- [ ] Expected migrations for this entire workstream: **0**.

---

## 14. Execution / resumability plan

The 774-cell campaign is chunked internally by Template batch (implementation
detail only — never a parallel Phase-5 workstream, never a second harness
invocation path):

- [ ] The extended `--only <key1,key2,...>` flag (§3) allows running a subset
  of Templates per invocation.
- [ ] Each invocation appends its results into the SAME `matrix.json` (never
  overwrites it wholesale) — implemented as: read existing `matrix.json` if
  present, merge new/updated per-key entries by `key`, write back atomically
  (write to a temp file, then rename) so a crash mid-run cannot corrupt
  previously-recorded results.
- [ ] Ordering is stable and deterministic: Templates are processed in
  `_SPECS` source order (the same order the harness inventory's table uses),
  never randomized, so re-running an interrupted batch resumes at a
  predictable point.
- [ ] Every cell records the exact Template `key` + `version` and the exact
  `page_class`/`viewport` — no implicit/positional cell identity.
- [ ] A FAILing cell does not erase or roll back any other already-recorded
  cell (per-key, per-page-class, per-viewport entries are independent
  dictionary keys in the JSON structure, never a flat ever-growing list that
  could be corrupted by a partial write).
- [ ] A final aggregator step (run after all batches) reads `matrix.json` and
  verifies: `total_cells_recorded == 774`, `missing_cells == []`,
  `duplicate_cells == []`. A partially-completed run is reported as
  `INCOMPLETE`, never as `PASS` — this aggregator check is itself part of
  `execution_report.md` (§11).
- [ ] No parallel Phase-5 workstream is started to speed this up; internal
  batching is the only concurrency this plan allows.

---

## 15. Architecture constraints (restated, binding)

- [ ] No new renderer, Ready Template registry, version registry, section
  type, Store-Appearance family, Theme mechanism, tenant resolver,
  ProductCard path, cart/add-to-cart path, Bottom Navigation system,
  search backend, or browser-rendering/QA authority is introduced.
- [ ] The only file changed under `apps/` for the harness extension is
  `apps/storefront_builder/management/commands/capture_ready_template_previews.py`.
- [ ] No file under `tools/` is changed (the extension is Python-side only,
  reusing the already-imported `playwright` package — it does not touch the
  Node/`playwright-core` tools at all).
- [ ] Zero migrations.
- [ ] No merchant IDs or per-Template fake business data enter any
  `_RecipeSpec` or fixture.
- [ ] One PR, unmerged, base `feature/phase5-design-expansion`, head
  `feature/phase5-w4c-all50-certification`, Architect review, Product Owner
  approval, only then merge — identical lifecycle to W4A/W4B.

---

## 16. Task checklist (for the authorized implementation round — not this round)

- [ ] Task 1 — Write RED contract tests proving the current
  `capture_ready_template_previews.py` has no `--certify` mode / no JSON
  result schema / no Cart capture / no Tablet viewport (documents the gap
  this workstream closes).
- [ ] Task 2 — Implement the bounded `--certify` extension (§3) in
  `capture_ready_template_previews.py`: Tablet viewport, Cart capture,
  assertion logic (§4–§7), JSON schema emission (§12), `--only` comma-list
  support, resumable-merge write (§14).
- [ ] Task 3 — Implement the Theme Tier 1/Tier 2 driver as an additional,
  narrowly-scoped code path in the same file (reusing `apply_theme`/
  `clear_theme`), gated behind a `--certify-theme` flag so a plain
  `--certify` run never pays the Theme-matrix cost.
- [ ] Task 4 — Prove GREEN on the extension's own focused tests + existing
  `test_ready_template_real_previews.py` (must remain green — the existing
  screenshot-only behavior is unchanged when `--certify` is not passed).
- [ ] Task 5 — Execute the 774-cell campaign in deterministic batches
  (§14), producing `matrix.json`.
- [ ] Task 6 — Run the visual-distinctness clustering pass (§10) against the
  real Home captures; resolve or escalate any `NEEDS REPAIR` finding before
  proceeding.
- [ ] Task 7 — Produce all evidence artifacts (§11).
- [ ] Task 8 — Full regression comparison (§13) against the certified W4B
  baseline; `manage.py check`/`makemigrations --check`/`git diff --check`.
- [ ] Task 9 — Architecture/duplication audit (§15) confirming the bounded
  extension introduced nothing beyond what this plan authorized.
- [ ] Task 10 — Final clean-status evidence sequence (temp-path capture,
  verify empty, then commit), mirroring W4B's own corrected methodology.
- [ ] Task 11 — Open the unmerged PR (base `feature/phase5-design-expansion`,
  head `feature/phase5-w4c-all50-certification`) and return for Independent
  Architect review.

No task above is started by this document. This document only defines them.
