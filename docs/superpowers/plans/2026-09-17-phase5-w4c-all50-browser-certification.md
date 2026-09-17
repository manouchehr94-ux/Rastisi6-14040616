# P5-W4C — All-50 Browser Certification — Implementation Plan

**Repair status:** Independent Review Repair Round 1 applied (CRITICAL 0 /
IMPORTANT 5, all five addressed below). Previous design head:
`bb04401a16dee905926e7ad0f6dfd0e9322a4e40`. This revision corrects: (1) the
browser-certification authority, (2) the Theme matrix cardinality, (3) an
explicit state-isolation contract, (4) the mandatory Home gallery (Desktop +
Mobile), (5) all TODO/TBD placeholders and the RED-test contract.

**Certified official base:** `3a4fe9070584655548bae5a9bb574f3415bbf580`
**Branch:** `feature/phase5-w4c-all50-certification`
**Companion document (read first):**
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/w4c_harness_inventory.md`
— full source citations, the complete 50-Template table, and the exact
extension-seam facts (§10 of that document) this plan's decisions are built
on.

**Status of this document:** plan/inventory only. No production code, Django
test code, or QA harness code changes are authorized by this document. Every
task below is deliverable only after a separate authorization round.

---

## 0. Scope recap

- Goal: real browser closure gate for **all 50** current merchant-facing Ready
  Templates (not a representative subset) — including Theme interaction,
  which must also reach all 50 (Repair Round 1, IMPORTANT 2).
- **Browser certification authority:** `tools/storefront_builder_r4_qa/run.mjs`
  — extended through one new, opt-in, additive `manifest.w4c`-gated block.
  No second harness.
- **Django orchestration authority:**
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`
  — extended with one new `--w4c-all50` flag and two new manifest keys
  (`w4c`, `w4c_fixture`), following the exact shape of the existing
  `--phase3`/`phase3_fixture` extension point.
- **`capture_ready_template_previews.py` role:** Gallery capture only —
  unchanged, never the certification PASS/FAIL authority, never invoked from
  within the `--w4c-all50` run.
- Evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.
- W5 remains frozen until this workstream merges with zero unresolved
  CRITICAL/IMPORTANT findings.

---

## 1. Exact matrix cardinality (repaired)

```
Base matrix:   50 Templates x 4 page classes (Home, Listing, PDP, Cart) x 3 viewports (Desktop 1440x900, Tablet 768x1024, Mobile 390x844)
             = 600 certification cells

Theme matrix:  Tier 1 (breadth, ALL 50)  — 1 deterministic occasion per Template (cycled nowruz/ramadan/muharram, see table below) x balanced intensity x Desktop only x 50 Templates = 50 cells
               Tier 2 (depth)            — 2 Templates (warm_boutique, beauty_dew) x 3 occasions x 3 intensities x 3 viewports = 54 cells
             = 104 additional cells

TOTAL:         704 certification cells
```

### 1.1 Tier 1 exact occasion assignment (deterministic, `_SPECS` source order, cycling `nowruz -> ramadan -> muharram`)

Computed via `for i, s in enumerate(_SPECS): occasion = ["nowruz","ramadan","muharram"][i % 3]`
— reproducible from source, never randomized at run time:

| Template key | Occasion | Template key | Occasion | Template key | Occasion |
|---|---|---|---|---|---|
| editorial_jewelry | nowruz | tower_department | nowruz | almas_luxury | nowruz |
| dense_marketplace | ramadan | beauty_dew | ramadan | roosta_zigzag | ramadan |
| warm_boutique | muharram | fashion_promo_catalog | muharram | mother_utility | muharram |
| premium_leather | nowruz | horizon_story | nowruz | aftab_price | nowruz |
| dark_digital | ramadan | mina_community | ramadan | mist_quiet | ramadan |
| cedar_home | muharram | silk_editorial | muharram | night_catalog | muharram |
| street_drop | nowruz | tuska_bento | nowruz | watchmaker_round | nowruz |
| premium_leather_noir | ramadan | rayan_tech | ramadan | kite_playful | ramadan |
| search_market | muharram | laleh_play | muharram | pine_eco | muharram |
| playful_lifestyle | nowruz | city_classic | nowruz | mirror_beauty | nowruz |
| utility_catalog | ramadan | collection_index | ramadan | charcoal_grill | ramadan |
| artisan_grain | muharram | kamand_artisan | muharram | calligraphy_paper | muharram |
| pixel_play | nowruz | | | harbor_imports | nowruz |
| simorgh_market | ramadan | | | parnian_editorial | ramadan |
| coastal_product | muharram | | | racer_tech | muharram |
| literary_catalog | nowruz | | | ferdowsi_department | nowruz |
| gallery_minimal | ramadan | | | anniversary_mosaic | ramadan |
| handmade_luxe | muharram | | | | |
| niloufar_glass | nowruz | | | | |
| tool_finder | ramadan | | | | |
| green_workshop | muharram | | | | |

(50 rows total, 17 `nowruz` / 17 `ramadan` / 16 `muharram` — exact counts,
verified programmatically.)

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
  guaranteed to exist because the seed command's `_seed_variants` step seeds
  at least one size/color-variable product.
- **Cart fixture:** add that same deterministic product (quantity 1) via the
  canonical `cart:add` route for every Cart cell — never direct DB session
  manipulation (repaired isolation contract, §5).
- **Theme:** applied/cleared via the canonical
  `appearance_authority_service.apply_theme` / `clear_theme` functions,
  called through the canonical R4 Draft lifecycle (`r4_mutation_service`'s
  `theme.apply`/`theme.clear` mutation types) and published through the
  canonical publish lifecycle — never a direct write to a published version,
  never a second Theme mechanism.
- Same merchant data used for every one of the 50 Templates — no per-template
  fixture variation, no fixture IDs written into any `_RecipeSpec`.

---

## 3. Canonical harness extension target (repaired — Important 1)

**Repair note:** the prior revision of this plan proposed extending
`capture_ready_template_previews.py` into the certification authority. The
Independent Architect rejected this: the authoritative plan explicitly names
`tools/storefront_builder_r4_qa/run.mjs` (and/or `tools/storefront_builder_qa/`)
as the harness to reuse. The corrected target below is binding.

### 3.1 `tools/storefront_builder_r4_qa/run.mjs` — browser certification authority

Exact insertion point (source-verified, harness inventory §10): inside
`main()`, immediately after the existing `if (manifest.phase3) { ... }`
block (source line 4138) and before the unconditional scenario 14 (source
line 4140):

```js
if (manifest.w4c) {
  await scenario('w4c-all50-certification', w4cAll50Certification);
}
```

`w4cAll50Certification` is one new function added to this file (not a new
file), reusing:
- The existing `browser`/top-level `context`/`page` variables already in
  scope inside `main()` for Home/Listing cells (fresh
  `browser.newContext()` per cell, cookied with `manifest.session` — the
  exact pattern the phase3 block's own public-route sub-contexts already
  use, 8 existing call sites, confirmed zero exceptions).
- A NEW, cookie-less `browser.newContext()` per PDP/Cart cell (no
  `manifest.session` injected), using `context.request.post(...)` /
  `context.request.get(...)` (Playwright's `APIRequestContext`, part of the
  already-shared `playwright-core` dependency) for the `cart:add`/
  `cart:item-update`/`cart:item-remove` mutations — copied from
  `tools/storefront_builder_qa/public_w1_qa.mjs`'s own already-proven
  anonymous cart-flow implementation (the one existing precedent for
  repeated, isolated, anonymous cart mutations in this repository), adapted
  into this new function, not duplicated into a second file.
- The existing module-level `result` object: `result.w4c = {...}` (mutated
  directly, exactly like every other scenario already does), landing in the
  single `r4-browser-result.json` write Django already reads for pass/fail.
  A dedicated sidecar `w4c-browser-result.json` (the full 704-cell
  `matrix.json`, §9) is additionally hand-written via a plain
  `fs.writeFileSync(path.join(manifest.report_dir, 'matrix.json'), ...)`,
  the same ad hoc way `metrics.json`/`task6_diagnostics.json` already are —
  there is no shared writer function to call.
- Zero lines of the existing 15 scenarios or the phase3/showcase functions
  are touched.

### 3.2 `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` — Django orchestration authority

- New flag in `add_arguments` (added alongside the existing 10, no existing
  flag changed): `--w4c-all50` (`action="store_true"`). Mutually exclusive
  with `--showcase` at validation time (mirroring the existing
  `--showcase` requires `--phase3` validation already present) — they
  target different host-resolution needs (§3.3).
- New method `_build_w4c_fixture(self, store)`, mirroring the shape of the
  existing `_prepare_phase3_brand_gate()`, returning a dict with: the exact
  50-Template key/version list (read live from
  `lpr.list_ready_templates()`, never hardcoded), the deterministic PDP
  fixture product id (§2), the Tier-1 occasion assignment (§1.1, computed
  the same deterministic way, not hardcoded as a literal 50-row dict, so it
  never drifts from `_SPECS` order), and the Tier-2 Template pair
  (`warm_boutique`, `beauty_dew`).
- `_build_manifest()`'s existing literal dict (lines 1267–1314) gains two
  new keys: `"w4c": bool(options["w4c_all50"])` and
  `"w4c_fixture": self._build_w4c_fixture(store) if options["w4c_all50"]
  else None` — no existing key in that dict is renamed or removed.
- Host resolution: when `--w4c-all50` is passed, `resolver_host` is computed
  as `f"shop-{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"`
  — the exact pattern `capture_ready_template_previews.py` already uses
  correctly for the real customer-facing public storefront — never the
  `showcase` mode's own, different, admin-host mapping.
- No change to the node-invocation mechanism (`subprocess.Popen`, temp-file
  manifest path as `argv[2]`) or the pass/fail read
  (`r4-browser-result.json`'s `summary.failed` OR nonzero exit code).

### 3.3 `apps/storefront_builder/management/commands/capture_ready_template_previews.py` — Gallery capture only, unchanged

Zero code changes. Used only as a deliberately-invoked, separately-recorded
step (§9/§14) to produce the mandatory Home Desktop + Home Mobile gallery
assets via its existing `--full-qa --only <key>` mode — never invoked from,
or by, the `--w4c-all50` run itself. Its exclusive ownership of
`apps/storefront_builder/static/ready_template_previews/<key>/v<version>.{webp,meta.json}`
is preserved; the `w4c` block in `run.mjs` never reads or writes anything
under that path.

No other file under `apps/`, `tools/`, or `migrations/` is touched by this
extension.

---

## 4. Pass/fail contract — Home

For every Template x viewport:

- [ ] HTTP 200 on the Store's public root.
- [ ] `<html dir="rtl">`.
- [ ] No horizontal overflow (`document.documentElement.scrollWidth <=
  document.documentElement.clientWidth + 2`).
- [ ] Exactly one `<header>` element (source-confirmed: every public-path
  header variant renders through `page_shell_header.html` or a
  `global_header/*` variant that itself emits exactly one `<header>`; the
  only other `<header>` tags in the template tree are confined to
  `dashboard/` admin templates, never reached by `home_visual.html`).
- [ ] Hero contract is data-driven (§6): for a Template whose canonical Home
  composition includes a `hero` token, Hero must render visibly and
  healthily (at least one visible media/copy element, no console/JS error);
  for a Template whose composition intentionally omits `hero`, the result is
  `N/A / expected absent`, never `FAIL`.
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
  console-error set for that Template, §12 — a pre-existing, already-known
  console warning is not a new W4C failure).
- [ ] Zero page (JS) errors.
- [ ] Zero unexpected failed requests (favicon 404s and the pre-existing
  "expected preview abort" pattern already excluded by the existing harness
  are excluded here too, never a new exclusion invented ad hoc).
- [ ] Accessibility-critical controls (§10) pass for every control actually
  present on Home for this Template.
- [ ] Session used: `browser.newContext()` + `manifest.session` cookie (§3.1)
  — read-only cell, no state-isolation risk (§5.2).

---

## 5. State isolation contract (new — Important 3)

### 5.1 Browser session isolation

Every one of the 600 base cells uses its own fresh
`browser.newContext()` — never a context shared across Templates, page
classes, or viewports. Concretely:

- **Home / Listing cells (read-only):** fresh `browser.newContext()` per
  cell, cookied with `manifest.session` (mirrors the existing phase3
  public-route pattern, §3.1). Read-only cells carry no mutation risk, so
  cookie reuse across these cells is safe — no cart/session state is ever
  written by a Home or Listing cell.
- **PDP / Cart cells (mutating):** fresh, cookie-less `browser.newContext()`
  per cell (no `manifest.session` injected). Django's session middleware
  issues a brand-new session (and therefore an empty cart) on that context's
  first request — this is the mechanism that guarantees "start empty"
  without any direct DB/session manipulation, per the repair directive's
  explicit prohibition. Each Cart cell independently: starts empty (fresh
  context, §above), adds exactly the deterministic fixture product via
  `context.request.post` to `cart:add`, exercises its bounded mutations
  (`cart:item-update`, `cart:item-remove`), reads the resulting DOM/totals
  via `page.goto('cart:detail')` in the SAME context, then the context is
  closed at the end of the cell — never reused for a later cell.
- PDP Add-to-Cart in one cell therefore cannot populate a later Cart cell:
  they never share a context, and a cookie-less context never resumes a
  prior session.

### 5.2 Template / Store state

- Before each Template's 12 base cells (4 page classes x 3 viewports):
  verify via `lpr.get_layout_preset(key).version` that the exact expected
  version is the one currently published on `rasti-mode-demo` (apply/publish
  it if not — idempotent, mirroring `capture_ready_template_previews.py`'s
  own idempotent skip-if-already-published check).
- Before every BASE-matrix batch (§10): verify the Store's published Theme
  selection is `theme.none.v1`. If it is not (e.g. a prior interrupted Theme
  cell left it non-none), run the Tier-1 cleanup lifecycle (§5.3) before
  proceeding, and record this as a recovered-state event in `matrix.json`'s
  `_meta`.
- The Store's published Template MAY persist across a Template's own 12 base
  cells (no per-cell re-apply needed once verified) — only the BROWSER
  SESSION must not persist (§5.1).

### 5.3 Theme cleanup must survive failures

Every Tier-1/Tier-2 Theme cell (§1) follows this exact, failure-safe
lifecycle:

```
1. get_or_create_draft(store)
2. apply_theme(draft, occasion_component_key, intensity)   # appearance_authority_service
3. layout_service.publish(store)
4. navigate + assert (occasion attributes, RTL, overflow, console/page errors, muharram-safety)
5. FINALLY (always runs, whether step 4 passed or raised):
     a. get_or_create_draft(store)
     b. clear_theme(draft)                                  # appearance_authority_service
     c. layout_service.publish(store)
     d. verify published state == theme.none.v1
6. IF the finally block's verification (5d) itself fails:
     mark the ENTIRE run BLOCKED, halt all subsequent base-matrix and
     Theme cells immediately, and require a manual/automated Store-state
     repair + re-verification before any further certification proceeds.
```

This is implemented in `w4cAll50Certification` as a JS
`try { ... } finally { ... }` block per Theme cell — never a bare
best-effort cleanup that can be silently skipped by an early return or an
uncaught exception. A Theme assertion/navigation failure (step 4) is
recorded as a FAIL for that cell but does NOT skip step 5 — cleanup always
runs regardless of step 4's outcome.

No direct writes to a published version at any point — every Theme mutation
goes through `get_or_create_draft` + the canonical mutation + `publish`.

---

## 6. Hero contract (new — data-driven, not key-special-cased)

Derived from source, not guessed: `_RecipeSpec.hero == "none"` for exactly 5
of the 50 Templates — `premium_leather`, `utility_catalog`, `tool_finder`,
`collection_index`, `mother_utility` (verified programmatically against
`_SPECS`; cross-checked against each of these 5 Templates' compiled Home
composition tuple, none of which contains a `hero` token — the two signals
agree for all 5, confirming `hero == "none"` is a reliable, render-facing
proxy).

- [ ] For the 45 Templates with a declared Hero: the Home contract's Hero
  check (§4) is `PASS`/`FAIL` based on real rendered health.
- [ ] For the 5 Templates listed above: the Home contract's Hero check
  result is `N/A` (recorded explicitly in `matrix.json`, never silently
  omitted, never coerced to `PASS`), and is excluded from any FAIL-counting
  logic for that field.
- [ ] No Template key is special-cased in browser code — the check queries
  the live `LayoutPresetDefinition.pages["home"]` section-key sequence for
  presence/absence of `"hero"` at execution time, deriving the expectation
  from data, not from a hardcoded key list (the 5-key list above is the
  CURRENT observed result of that data-driven query, recorded here for
  planning traceability, not the mechanism itself).

---

## 7. Pass/fail contract — Listing

Route: `catalog:product-list` (`/products/`). For every Template x viewport:

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
- [ ] Real product links (first product card's `href` resolves, HTTP 200,
  verified via an in-page `fetch()` from the SAME session-cookied context —
  Listing is a read-only cell, §5.1).
- [ ] No dead interaction (no `href="#"`, no disabled-looking control that
  is actually meant to be active).
- [ ] Accessibility-critical controls (§10) for filter/sort/pagination.
- [ ] Zero new console/page/request errors.

---

## 8. Pass/fail contract — PDP

Route: `catalog:product-detail` for the deterministic fixture product (§2).
Read-mostly (variant/quantity interaction is client-side; only Add-to-Cart
mutates), so PDP cells use the cookie-less fresh-context pattern (§5.1) for
consistency with the Cart cells that follow from them within the same cell's
Add-to-Cart check. For every Template x viewport:

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
  the in-flow CTA and the mobile Sticky-Add-to-Cart bar. This mutation uses
  the cell's own fresh, cookie-less context (§5.1) and is discarded with it.
- [ ] Mobile Sticky-Add-to-Cart bar present at Mobile viewport where the
  Template's `bottom_nav`/shell declares it (reusing `public_task8_qa.mjs`'s
  own hidden-on-desktop/visible-on-mobile/no-content-obscuration checks,
  never re-invented).
- [ ] Product Detail Tabs (Desktop, ARIA `role=tab`/`tabpanel`) or Accordion
  (Mobile, DOM source-order) contract — reusing `public_task5_qa.mjs`'s
  existing checks verbatim.
- [ ] Real navigation: at least one in-page link (e.g. back to Listing or a
  related-category link if present) resolves HTTP 200.
- [ ] Accessibility-critical controls (§10) for variant/quantity/Add-to-Cart.
- [ ] Zero new console/page/request errors.

---

## 9. Pass/fail contract — Cart

Route: `cart:detail`, after one canonical `cart:add` of the fixture product,
in a fresh, cookie-less context per cell (§5.1). For every Template x
viewport:

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
- [ ] Accessibility-critical controls (§10) for quantity/remove/checkout.
- [ ] Zero new console/page/request errors.
- [ ] Cell teardown: the context is closed at the end of this cell,
  discarding its session/cart — never reused, never explicitly "cleared" via
  DB/session manipulation (§5.1).

---

## 10. Accessibility-critical contract (bounded, technical — not a WCAG audit)

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
  what §1's Theme matrix already checks structurally).

---

## 11. Visual distinctness contract (repaired — uses Desktop AND Mobile)

Structural uniqueness (W4B's `recipe_signature()`/diversity contract) and
rendered visual certification are separate gates; both are required, and a
passing structural signature never substitutes for a rendered check here.

- [ ] Build one **rendered-identity matrix**: for all 50 Templates, tabulate
  (from real Home captures at BOTH Desktop and Mobile — repaired per
  Important 4, since Bottom Navigation is a mobile-only visual and cannot be
  certified from Desktop evidence alone) the actually-rendered Header
  family, Hero family (or intentional Hero absence, §6), layout/composition
  shape, Product Card style, density, typography, Footer family, and
  Bottom-Nav style.
- [ ] Cluster the 50 by this rendered-identity matrix. Any cluster of 2+
  Templates whose rendered identity differs ONLY by palette/font/radius
  (never by Header/Hero-or-absence/layout/Product-Card/density/typography/
  Footer/Bottom-Nav) is flagged `NEEDS REPAIR` — palette-only difference is
  explicitly insufficient per the plan's own text.
- [ ] Any `NEEDS REPAIR` finding STOPS the certification run for that pair/
  cluster and is returned for a separate, reviewed repair round before
  certification can close — it is never silently passed because
  `recipe_signature()` was already unique (W4B's structural test does not
  inspect rendered output).
- [ ] The rendered-identity matrix and cluster findings are published as
  `visual_distinctness_matrix.json` + a human-readable
  `visual_distinctness_matrix.md` (§12), both explicitly citing which
  viewport (Desktop or Mobile) evidenced each axis — Bottom-Nav rows always
  cite Mobile.

---

## 12. Evidence-volume contract (repaired — Important 4)

Canonical evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.

Required artifacts:

1. `matrix.json` — one machine-readable file covering every one of the 704
   certification cells (§1), schema in §13.
2. `home_gallery/` — **100 files** (repaired from 50): for each of the 50
   Templates, one Home Desktop screenshot (`<key>_home_desktop.jpg`, 1440
   wide) AND one Home Mobile screenshot (`<key>_home_mobile.jpg`, 390 wide)
   — mandatory, for W5 review, which explicitly requires Desktop + Mobile
   inspection including the Bottom Navigation axis. Produced via the
   existing Gallery authority's `--full-qa --only <key>` mode (§3.3), which
   already captures both at these exact viewports; W4C copies those two
   outputs per key into this folder rather than re-implementing capture.
   Home Tablet is exercised in `matrix.json` but not gallery-retained.
3. `gallery_index.md` — a single 100-row-referencing, 50-Template index
   (key, label_fa, Desktop thumbnail reference, Mobile thumbnail reference,
   rendered-identity summary including Bottom-Nav style) suitable for
   Product Owner/W5 review — no separate per-Template markdown files.
4. `representative_screenshots/` — one Desktop screenshot per Template for
   Listing, PDP, and Cart (50 x 3 = 150 files) for the passing, non-Home page
   classes; Tablet/Mobile screenshots for these page classes are NOT
   committed when `matrix.json` already proves the result — Tablet/Mobile
   checks still run and are still recorded in `matrix.json`, only their
   screenshots are not retained on success.
5. `failures/` — a screenshot for every FAILING non-Home cell, at the exact
   viewport that failed, named `<key>_<page_class>_<viewport>_FAIL.jpg`. Home
   failures reuse the mandatory `home_gallery/` assets (already committed,
   both Desktop and Mobile) and need no separate failure screenshot.
6. `theme_qa/` — Tier 1 failure-only screenshots (one per failing cell, of
   50) plus all Tier-2 cells retained in full (27 x 2 = 54, since Tier 2 is
   the small, deliberately deep sample).
7. `visual_distinctness_matrix.json` + `.md` (§11), citing Desktop and
   Mobile evidence explicitly.
8. `failure_summary.md` — every FAIL/BLOCKED cell across all 704, one row
   each, with the exact reason.
9. `browser_error_summary.md` — aggregated console/page/failed-request
   findings across the whole run, cross-referenced against the certified
   W4B/pre-existing baseline (§14) so only genuinely new errors are flagged.
10. `architecture_duplication_audit.md` — confirms zero new renderer/
    registry/section-type/Theme-mechanism/tenant-resolver/ProductCard-path/
    cart-path/Bottom-Nav-system/search-backend/parallel harness was
    introduced by the bounded extension (§3), and explicitly confirms
    `apps/storefront_builder/static/ready_template_previews/**` was touched
    only by the deliberate Gallery-refresh step (§3.3/§16), never by the
    `--w4c-all50` run itself.
11. `execution_report.md` — narrative tying together all of the above,
    modeled on W4B's own `10_implementation_report.md`.

Never committed: a screenshot for every passing Tablet/Mobile
Listing/PDP/Cart cell (proven instead by `matrix.json`).

---

## 13. Machine-readable matrix schema

Directly descended from W4B's `browser_qa_responsive_repair/summary.json`
shape (harness inventory §1.6), extended with a `page_class` dimension:

```json
{
  "key": "cedar_home",
  "version": "2",
  "page_classes": {
    "home": {
      "desktop": { "...": "see section 4 fields, plus hero_expected: true/false and hero_result: PASS/FAIL/N-A" },
      "tablet": { "...": "see section 4 fields" },
      "mobile": { "...": "see section 4 fields" }
    },
    "listing": { "desktop": {}, "tablet": {}, "mobile": {} },
    "pdp": { "desktop": {}, "tablet": {}, "mobile": {} },
    "cart": { "desktop": {}, "tablet": {}, "mobile": {} }
  },
  "theme": {
    "tier1_cell": { "occasion": "muharram", "intensity": "balanced", "result": "PASS", "cleanup_verified": true },
    "tier2": null
  }
}
```

Each per-viewport object carries, at minimum: `http_status`, `rtl`,
`overflow`, `header_count`, `footer_count`, `bottom_nav_present`,
`bottom_nav_display`, `rsec_count`, `expected_rsec_count`,
`product_cards_present`, `dead_href_count`, `console_errors` (list),
`page_errors` (list), `failed_requests` (list), `accessibility_checks`
(object, per §10), `session_mode` (`"cookied"` for Home/Listing,
`"anonymous"` for PDP/Cart, per §5.1), `result` (`"PASS"`/`"FAIL"`/
`"BLOCKED"`/`"N/A"`), `reason` (string, required when `result` is not
`PASS`), `screenshot` (path or `null` when not retained per §12).

A top-level `_meta` object records: `run_started_at`, `run_finished_at`,
`certified_base_sha`, `w4c_branch_head_sha`, `total_cells_expected` (704),
`total_cells_recorded`, `missing_cells` (list — must be empty for a valid
PASS report), `duplicate_cells` (list — must be empty), `recovered_state_events`
(list — any time §5.2's pre-batch Theme/Template verification found and
repaired unexpected state).

---

## 14. Regression / baseline comparison strategy

- [ ] Run `python manage.py check --settings=shop_core.settings` — expect
  clean.
- [ ] Run `python manage.py makemigrations --check --dry-run
  --settings=shop_core.settings` — expect "No changes detected". If W4C's
  bounded harness extension requires any production code or migration beyond
  the two files listed in §3, STOP for Architect review before proceeding —
  this workstream is QA/evidence, not a production-behavior change.
- [ ] Run `git diff --check` — expect clean.
- [ ] Re-run `apps.storefront_builder.tests` in full and compare failure/
  error identities against the certified W4B evidence
  (`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/09_full_suite_exact_head_base_comparison.md`
  and `05_full_storefront_builder_exact_head.txt` — 3235 tests / 30 failures
  / 2 errors / 4 skipped, W4B-only failures/errors = 0). Historical baseline
  failures are never automatically treated as W4C regressions; only a
  genuinely NEW failure/error identity, or a CHANGED reason for an existing
  one, counts as a W4C regression. Extending `qa_storefront_builder_r4.py` /
  `run.mjs` behind a new, default-off flag is not expected to change any
  existing test's identity or reason — this must still be verified, not
  assumed.
- [ ] Existing `test_ready_template_real_previews.py` must remain green
  unchanged (proves `capture_ready_template_previews.py`'s pre-existing
  behavior is untouched, §3.3).
- [ ] Existing R4 QA scenarios 01–15 and the phase3/showcase blocks must
  remain behaviorally identical when `--w4c-all50` is NOT passed (the new
  flag defaults to off; this is itself asserted by one of the RED-turned-
  GREEN tests, §16 Task 1).
- [ ] Expected migrations for this entire workstream: **0**.

---

## 15. Execution / resumability plan (repaired — 704 cells, state-aware resume)

The 704-cell campaign is chunked internally by Template batch
(implementation detail only — never a parallel Phase-5 workstream, never a
second harness invocation path):

- [ ] `--w4c-all50` accepts an additional `--only <key1,key2,...>` sibling
  flag (mirroring `capture_ready_template_previews.py`'s existing `--only`,
  extended to a comma-separated list) to run a subset of Templates per
  invocation.
- [ ] Each invocation appends its results into the SAME `matrix.json` (never
  overwrites it wholesale) — implemented as: read existing `matrix.json` if
  present, merge new/updated per-key entries by `key`, write back atomically
  (write to a temp file, then rename) so a crash mid-run cannot corrupt
  previously-recorded results.
- [ ] Ordering is stable and deterministic: Templates are processed in
  `_SPECS` source order, never randomized, so re-running an interrupted
  batch resumes at a predictable point.
- [ ] Every cell records the exact Template `key` + `version` and the exact
  `page_class`/`viewport` — no implicit/positional cell identity.
- [ ] A FAILing cell does not erase or roll back any other already-recorded
  cell (per-key, per-page-class, per-viewport entries are independent
  dictionary keys in the JSON structure, never a flat ever-growing list that
  could be corrupted by a partial write).
- [ ] **Resume state verification (repaired):** before continuing an
  interrupted campaign, the resuming invocation does NOT assume the previous
  batch left Store state clean. It explicitly re-verifies: (a) the published
  Template identity for the NEXT key to be processed (§5.2 — re-applies if
  drifted), and (b) the published Theme identity is `theme.none.v1` (§5.2/
  §5.3 — runs the Theme-cleanup lifecycle if not, before any further base or
  Theme cells run). Both checks are recorded in `matrix.json`'s
  `_meta.recovered_state_events` when they find and fix drift.
- [ ] A final aggregator step (run after all batches) reads `matrix.json` and
  verifies: `total_cells_recorded == 704`, `missing_cells == []`,
  `duplicate_cells == []`. A partially-completed run is reported as
  `INCOMPLETE`, never as `PASS` — this aggregator check is itself part of
  `execution_report.md` (§12).
- [ ] No parallel Phase-5 workstream is started to speed this up; internal
  batching is the only concurrency this plan allows.

---

## 16. Architecture constraints (restated, binding)

- [ ] No new renderer, Ready Template registry, version registry, section
  type, Store-Appearance family, Theme mechanism, tenant resolver,
  ProductCard path, cart/add-to-cart path, Bottom Navigation system,
  search backend, or browser-rendering/QA authority is introduced.
- [ ] The only files changed for the harness extension are
  `tools/storefront_builder_r4_qa/run.mjs` and
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`.
- [ ] `capture_ready_template_previews.py` is not modified; it is only
  invoked, unmodified, in its existing `--full-qa --only <key>` mode, as one
  explicitly-listed step (§3.3) to produce Gallery/W5 Home assets — this
  invocation is recorded in `execution_report.md` as a deliberate Gallery
  refresh, distinct from and never triggered by the `--w4c-all50` run.
- [ ] No new Node package is added — the extension reuses the
  `playwright-core` dependency `run.mjs` already borrows via `createRequire`
  from `tools/storefront_builder_qa/package.json`.
- [ ] Zero migrations.
- [ ] No merchant IDs or per-Template fake business data enter any
  `_RecipeSpec` or fixture.
- [ ] One PR, unmerged, base `feature/phase5-design-expansion`, head
  `feature/phase5-w4c-all50-certification`, Architect review, Product Owner
  approval, only then merge — identical lifecycle to W4A/W4B.

---

## 17. Task checklist (for the authorized implementation round — not this round)

- [ ] **Task 1 — RED contract tests asserting the DESIRED W4C behavior**
  (repaired — Important 5B: these assert the feature that should exist and
  currently fails because it does not, never "absence of a feature"):
  - `qa_storefront_builder_r4.py`'s `add_arguments` accepts `--w4c-all50`
    and `--only` (as a comma-list) — FAILS today (flag does not exist).
  - `_build_manifest()`'s returned dict contains `w4c` (bool) and, when
    `--w4c-all50` is passed, a `w4c_fixture` dict with keys
    `templates` (list of 50 `{key, version}`), `pdp_product_id`,
    `tier1_occasions` (dict of 50 `{key: occasion}` matching §1.1's cycling
    rule exactly), `tier2_keys` (`["warm_boutique", "beauty_dew"]`) — FAILS
    today (keys do not exist).
  - `run.mjs`'s `main()` contains an `if (manifest.w4c)` branch that invokes
    a `w4cAll50Certification` function — FAILS today (branch does not
    exist).
  - Passing `manifest.w4c = false`/absent produces byte-identical scenario
    execution (same `result.scenarios` order/content) to the certified W4B
    era baseline run — this test PASSES today (proving non-interference) and
    must keep passing after Task 2 (a regression guard, not a RED test).
  - The aggregator (new, small Python or JS utility introduced as part of
    Task 2, not a separate harness) rejects a `matrix.json` with
    `total_cells_recorded != 704`, rejects one with a non-empty
    `missing_cells`, and rejects one with a non-empty `duplicate_cells` —
    FAILS today (aggregator does not exist).
  - A Tier-1 Theme cell's recorded entry contains the exact
    `{key, version, occasion, intensity}` for its Template — FAILS today.
  - A Hero-`none` Template's (§6) Home cell records `hero_result: "N/A"`,
    never `"FAIL"` — FAILS today (contract does not exist).
  - A cookie-less PDP/Cart context, when it issues `cart:add` twice in two
    SEPARATE cell invocations, ends up with two independent, non-cumulative
    carts (proving isolation) — FAILS today (mechanism does not exist).
  All of the above FAIL on the current certified base because the `w4c`
  mode does not exist yet — this is the valid RED state.
- [ ] Task 2 — Implement the bounded `--w4c-all50` extension (§3) across
  `qa_storefront_builder_r4.py` and `run.mjs`: manifest keys, the
  `w4cAll50Certification` function (Home/Listing cookied cells,
  PDP/Cart cookie-less cells, Theme Tier 1/Tier 2 with the try/finally
  cleanup lifecycle of §5.3), the `matrix.json` writer/merger (§15), and the
  small aggregator utility (§15/Task 1).
- [ ] Task 3 — Prove GREEN on Task 1's tests, plus existing
  `test_ready_template_real_previews.py` and the existing R4 QA scenario
  suite (both must remain green and behaviorally unchanged when
  `--w4c-all50` is absent).
- [ ] Task 4 — Execute the 704-cell campaign in deterministic batches
  (§15), producing `matrix.json`.
- [ ] Task 5 — Run the visual-distinctness clustering pass (§11) against the
  real Home Desktop+Mobile captures; resolve or escalate any `NEEDS REPAIR`
  finding before proceeding.
- [ ] Task 6 — Deliberately run `capture_ready_template_previews.py
  --full-qa --only <key>` for all 50 keys against `rasti-mode-demo` (§3.3),
  and copy the resulting Home Desktop + Home Mobile assets into
  `home_gallery/` (§12); record exactly which versioned Gallery static
  assets were produced/refreshed by this step in `execution_report.md`.
- [ ] Task 7 — Produce all remaining evidence artifacts (§12).
- [ ] Task 8 — Full regression comparison (§14) against the certified W4B
  baseline; `manage.py check`/`makemigrations --check`/`git diff --check`.
- [ ] Task 9 — Architecture/duplication audit (§16) confirming the bounded
  extension introduced nothing beyond what this plan authorized, and
  confirming the Gallery static tree was touched only by Task 6's deliberate
  step.
- [ ] Task 10 — Final clean-status evidence sequence (temp-path capture,
  verify empty, then commit), mirroring W4B's own corrected methodology.
- [ ] Task 11 — Open the unmerged PR (base `feature/phase5-design-expansion`,
  head `feature/phase5-w4c-all50-certification`) and return for Independent
  Architect review.

No task above is started by this document. This document only defines them.
