# Task 5 — Cross-page CSS completeness

Append-only per-group record. Each group: browser RED → exact missing computed style →
smallest scoped fix in `storefront_builder.css` → prove Home unchanged → prove non-Home
envelopes → desktop/tablet/mobile → review → bounded commit.

## Setup facts (apply to every group in this task)

- Home CSS: `apps/catalog/static/css/home.css`, loaded ONLY by `catalog/templates/catalog/home.html`
  (confirmed: no `storefront_builder.css` reference anywhere in that template).
- Shared non-Home CSS: `apps/storefront_builder/static/css/storefront_builder.css`, loaded by
  all 5 non-Home public envelopes (product_detail, listing/search, collection, cart).
- Because Home never loads `storefront_builder.css`, every fix in this task is
  **structurally incapable** of affecting Home's own rendering — "prove Home unchanged" is
  verified by (a) confirming that structural fact and (b) a sanity request against
  `catalog:home` returning 200 with no console errors, rather than needing to diff Home's
  rendered output before/after (there is nothing for the fix to change there).
- Verification technique: computed-style RED/GREEN proof requires a real browser (a Django
  test client cannot evaluate `getComputedStyle`), so each group is verified with a small
  scratch Playwright script against a live `manage.py runserver` instance, run against the
  real dev DB with an explicit backup/restore around the fixture mutation (SHA256-verified
  clean afterward, matching the certified R4 QA harness's own backup/restore discipline).
  The scratch script itself is not committed to the repo — it is a verification tool, not a
  certified harness family (that is Task 6's job, via the Task 4 `PHASE3_FAMILIES`
  mechanism). The PERMANENT regression guard committed to the repo is a Django
  `TestCase` per group in `test_phase4_task5_cross_page_css.py` that (a) renders the section
  on a non-Home page via the real Draft→Publish→Public flow and asserts the markup appears,
  and (b) asserts the exact CSS declarations the fix depends on are present in
  `storefront_builder.css` — RED-verified via `git stash` on the CSS file only.
- **Process correction learned from Group A1's review (applies to every remaining group)**:
  `home.css` is not one clean per-feature block per selector — it carries at least two
  further, unconditioned, file-wide cascade passes layered on top of nearly every
  selector's "main" block: a comment-headed **"V3 universal dense-marketplace fidelity
  pass"** (~home.css:510-540) and a **"V4.2.2 readability calibration"** (~home.css:720-735),
  plus occasional narrowly-scoped extra resets (e.g. a second `@media(max-width:680px)`
  block specifically re-touching `.hero-text`). Because these are equal-specificity plain
  class rules, home.css's own file order — not just each rule's presence — decides the
  final computed style. From Group A2 onward (and Group A1's fix-up below), every group's
  CSS mirror is verified by `grep`-ing the selector name across the **entire** home.css
  file (not just its "main" comment-headed block) before considering the fix complete, and
  the mirrored rules are reproduced in the exact same relative order.

## Review outcomes and fix-up for Groups A1/A2 (Playwright-adjacent process note)

Group A1's review returned **FAIL** (3 IMPORTANT: the "V3"/"V4.2.2" passes above were not
mirrored for `.hero-text`/`.hero-cta`/`.hero-tabs`, so hero_banner/image_slider would render
structurally correct but with the wrong text color/shadow, CTA shape, and tabs gradient
above 680px; 3 MINOR: a stale `.hero-inner` border-radius/shadow, a test that baked in the
stale value, and an already-no-op density-reset omission). Fixed in a follow-up commit:
appended the missing V3 override block, the V3-era `.hero-text` mobile reset, and the
V4.2.2 override block, in the exact relative order home.css uses, plus a new test
(`test_storefront_builder_css_carries_the_later_hero_cascade_overrides`) asserting both the
override declarations AND that they appear textually after the base block (cascade order,
not just presence). Re-verified via real browser: `.hero-text` color/shadow/padding/bottom,
`.hero-cta` border-radius/min-width/height/font-size/box-shadow, `.hero-tabs`
background-image/padding-top, `.hero-tabs button` height/font-size, and `.hero-inner`
border-radius/box-shadow all now match home.css's actual final computed values exactly at
1440×900; the mobile (390×844) breakpoint correctly restores white text + shadow, matching
home.css's own mobile reset.

Group A2's review returned **PASS** (0 CRITICAL, 0 IMPORTANT, 1 MINOR — a dangling
`--accent` custom property referenced by the `data-palette-role="tone-3"` heading-accent
rule that is never defined anywhere in the live app, confirmed pre-existing in home.css
itself, not introduced by this commit). While applying Group A1's fix, the same systematic
whole-file `grep` was applied to Group A2's `product-spotlight`/`beauty-section-title`
selectors and found the identical class of gap the A2 review had not caught: V3's
`.product-spotlight-slider{border-radius:6px;border-color:#e0e2e6}`,
`.product-spotlight-head{padding:9px 10px 7px}`, `.product-spotlight-head h2{font-size:12px}`,
`.product-spotlight-dots{padding:5px 8px 7px}`; V4.2.2's
`.product-spotlight-head h2{font-size:13.5px}`; and `.beauty-section-title`'s own
`@media(max-width:680px)` breakpoint (`gap:10px;margin-bottom:14px`,`h2{font-size:13px}`).
Added proactively in the same follow-up commit, with a matching new test
(`test_storefront_builder_css_carries_the_later_spotlight_cascade_overrides`). Verified via
real browser that `.product-spotlight-slider`'s nested spotlight-mode override
(`.product-section--spotlight .product-spotlight-slider{border:0;border-radius:0}`, added in
the base A2 fix, specificity 0,2,0) correctly still wins over the new V3 addition
(specificity 0,1,0) for the spotlight display mode — i.e. `border-radius:0` — exactly
matching what the identical specificity relationship produces in home.css itself; the plain
(non-spotlight) `carousel` display mode is where the new V3 rule actually takes effect.

### Verification (fix-up)

- `test_phase4_task5_cross_page_css`: **9/9 pass** (4 Group A1 + 3 Group A2 + 2 new
  cascade-order tests).
- Regression sweep: same suite set as Group A2 — **484 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...` after this fix-up's own
  browser-verification fixture mutation.

## Group A1 — `hero_banner` (default `overlay` style) + `image_slider`

### Result: PASS

### Investigation

A background research pass (read-only) traced both section keys to their templates:
- `hero_banner`'s default style and `image_slider` (which has no `variants` at all) both
  render through the exact same 1-line include,
  `apps/storefront_builder/templates/storefront_builder/partials/hero_slider_body.html` —
  one root cause, not two, confirming the plan's grouping of these two together.
- The investigation also checked the plan's stated hypothesis that `product_section`'s
  spotlight mode and `amazing_offers` "share the same promo-card CSS root" (also listed
  under Group A) and found it **incorrect**: the two use completely disjoint CSS class
  families (`.product-spotlight-*` reusing the shared `.pcard` partial vs. `.special-*`
  hand-rolling its own markup, zero selector overlap). Per the plan's own explicit
  instruction ("re-verify this grouping ... split out if the root causes turn out
  unrelated"), Group A is therefore split into three independent, separately-verified,
  separately-committed fixes: **A1** (this entry, hero_banner + image_slider), **A2**
  (product_section campaign_band/spotlight), **A3** (amazing_offers).

### Browser RED (before fix)

Fixture: real dev DB (`db.sqlite3`), backed up first (SHA256 `d53a687b...`, matching every
prior harness run's baseline). Added a `hero_banner` section (default settings, `hero_style:
"overlay"`) to the `akhlaghi` store's Cart page via `section_structure_service.add_section`,
attached one `HeroSlide` (title only, no image — proving the container/text layout
independent of image decode), published, then loaded `http://127.0.0.1:<port>/cart/` in a
real headless Chromium (the same `/opt/pw-browsers/chromium-1194` binary the certified
harness uses) and read `getComputedStyle`:

| Selector | Property | Expected (per home.css) | Actual (RED) |
|---|---|---|---|
| `.hero-slide` | `position` | `absolute` | `static` |
| `.hero-slide` | `inset` | `0px` | `auto` |
| `.hero-media` | `display` | `block` | `inline` |

Confirms the section's HTML renders (shared Django template, unaffected by CSS), but its
layout is completely unstyled off-Home — matching the investigation's prediction exactly.

### Fix

Mirrored the base "universal image-first hero" block and the Phase-3.7
`data-text-position` rules verbatim from `home.css` (lines 7-43, 840-847) into
`storefront_builder.css`, placed just before the existing `.hero-luxury-*` block (the only
other hero-related CSS already in that file). Scoped narrowly: only the selectors the
`overlay`/no-variant hero body actually emits — `.hero`, `.hero-inner` (+
`[data-text-position]` variants), `.hero-slide`(`.single`), `.hero-media`(`img`),
`.hero-text`(`h1`/`p`), `.hero-cta`, `.hero-arrow`(`-prev`/`-next`), `.hero-tabs`(`button`) —
plus their two documented responsive breakpoints (`max-width:1000px`, `max-width:680px`).
Did NOT mirror the Home-only `.rcontainer:has(.hero):has(.product-section--spotlight)`
row-co-placement rule (a Home multi-column-row feature, not required for this section to
render correctly standalone) or the other hero style variants (`split`,
`beauty_editorial`, `chocolate_carousel`, `atelier_triptych` — out of this group's scope,
Group A explicitly covers only the default `overlay` style).

### Browser GREEN (after fix), desktop/tablet/mobile, two envelopes

Re-ran the same fixture flow (hero_banner on Cart, image_slider on Listing — a second,
independent placement proving the shared-template fix works identically) at
1440×900/768×1024/390×844:

| Viewport | `.hero-inner` position | `.hero-inner` height (aspect-ratio applied) | `.hero-slide` position/inset | Console errors |
|---|---|---|---|---|
| 1440×900 (Cart) | `relative` | 464px | `absolute` / `0px` | 0 |
| 768×1024 (Cart) | `relative` | 308px | `absolute` / `0px` | 0 |
| 390×844 (Cart) | `relative` | 300px | `absolute` / `0px` | 0 |
| 1440×900 (Listing, image_slider) | — | — | `absolute` / `0px` | 0 |

The changing height per viewport confirms the responsive `aspect-ratio` breakpoints are
also active, not just the base rule.

### Home unchanged

`catalog/templates/catalog/home.html` confirmed to never reference `storefront_builder.css`
(structural proof, not just an empirical non-diff). `catalog:home` returns 200 with 0
console errors both before and after the fix (sanity check, not a before/after diff, since
nothing could have changed).

### Cleanup

Dev server stopped; `db.sqlite3` restored from the pre-fixture backup, SHA256-verified
identical to the original (`d53a687b...`) — no residue left in the shared dev DB.

### Permanent regression guard

`apps/storefront_builder/tests/test_phase4_task5_cross_page_css.py`,
`HeroSliderNonHomeCssCompletenessTests` (4 tests): renders `hero_banner` on Cart and
`image_slider` on Listing via the real Draft→Publish→Public flow and asserts the markup
appears; asserts the load-bearing CSS declarations are present in
`storefront_builder.css` (RED-verified via `git stash` on the CSS file only — fails with
the exact missing-declaration `AssertionError` before the fix, passes after); asserts Home
never loads `storefront_builder.css` and still renders 200.

### Verification

- New suite: **4/4 pass**. RED confirmed via `git stash` (CSS-only) — the CSS-content
  assertion fails with the precise missing-declaration error; the markup-rendering
  assertions are unaffected by the CSS file (as expected — they test template rendering,
  not layout).
- Regression sweep: `test_phase4_task5_cross_page_css` + `test_qa_harness_contract` +
  `test_r4_settings_schema` + `test_section_registry` + `test_render_service` — **433
  tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes (no model
  touched).

### STOP conditions checked

Pure CSS-completeness fix — no new template, no new section registration, no schema
change, no new renderer path. Not a design expansion (Ruling D): mirrors existing,
already-shipped Home styling verbatim, adds no new visual variant.

## Group A2 — `product_section` (`spotlight` and `campaign_band` display modes)

### Result: PASS

### Investigation recap

Per Group A1's note above, this entry covers the two `product_section` display modes the
plan originally (incorrectly) grouped with `amazing_offers` under one "shared promo-card
CSS root." Confirmed disjoint: `product_section` reuses the shared `.pcard` product-card
partial inside `.product-spotlight-slide`/`.product-campaign-products`; `amazing_offers`
hand-rolls its own `.special-*` markup with zero selector overlap. Fixed independently here;
`amazing_offers` is Group A3.

A second investigation finding: `home.css` layers **two** separate
`.product-section--spotlight{...}` rules at different points in the file — a short one
(`height`/`display`/`flex-direction`) and a later one adding `border`/`border-top`/
`background`/`overflow` (CSS cascade — later wins for overlapping properties, but the
non-overlapping properties from BOTH rules are needed for a faithful mirror). Both are
mirrored here.

### Discovered along the way: a pre-existing, unrelated, deliberate rule

`render_service.hide_empty_public_sections` (Acceptance Batch 1, post-U11) hides
`product_section` (and several other "optional product data" section types) entirely on
the **public** page when it resolves zero products — by design, so an empty promotional
row never appears to a shopper, while the Builder/editor preview still shows its own
"nothing to show yet" empty state so a merchant understands why. This is why the fixture
for this group needed at least one real `Product` row (the hero fixture in Group A1 did
not need this, since `hero_banner`/`image_slider` render an explicit empty-state markup
unconditionally). Not a bug, not touched by this fix — noted here since it initially looked
like the section wasn't rendering at all.

### Browser RED (before fix)

Same dev-DB backup/restore discipline as Group A1. Created one real `Product` (via a
throwaway `Vendor`) for the `akhlaghi` store, placed `product_section` with
`display_mode="carousel", carousel_autoplay=True` (spotlight) on Cart and
`display_mode="campaign_band"` on Listing, published, loaded both public pages:

| Selector | Property | Expected | Actual (RED) |
|---|---|---|---|
| `.product-section--spotlight` (Cart) | `display` | `flex` | `block` |
| `.product-spotlight-track` (Cart) | `display` | `grid` | `block` |
| `.product-spotlight-slide` (Cart) | height (2 slides) | overlapping (`grid-area:1/1`) | stacked, combined height 1312px |
| `.product-campaign-band` (Listing) | `display` | `grid` (2-col) | `block` |
| `.beauty-section-title` (Listing) | `display` | `grid` (3-col) | `block` |

### Fix

Mirrored verbatim from `home.css`: the "Product spotlight carousel" block (base rules +
the second `.product-section--spotlight` override block), and the "Product campaign band"
block (`.beauty-section-title`, `.product-section--campaign-band`,
`.product-campaign-heading`, `.product-campaign-band`, `.product-campaign-copy`,
`.product-campaign-gift`, `.product-campaign-link`, `.product-campaign-products`, plus the
`data-palette-role="tone-3"` heading-accent companion — a generic, non-Home-specific
background/palette mechanism already used elsewhere), plus both selectors' documented
`max-width:1000px`/`max-width:680px` responsive breakpoints. Did not mirror
`html[data-sfb-density=...]` micro-tweaks, consistent with Group A1's scoping discipline.

### Browser GREEN (after fix), desktop/tablet/mobile, two envelopes

| Viewport | `.product-spotlight-track` (Cart) | `.product-campaign-band` (Listing) | Console errors |
|---|---|---|---|
| 1440×900 | `display:grid`, 1 track (`1162px`) | `display:grid`, 2 tracks (`196.8px 955.2px`) | 0 |
| 768×1024 | `display:grid`, `position:relative` | `display:grid`, 2 tracks (`145px 547px` — tablet breakpoint) | 0 |
| 390×844 | `display:grid`, `position:relative` | `display:grid`, 1 track (`336px` — mobile 1fr collapse) | 0 |

The tablet/mobile track-count changes confirm both documented responsive breakpoints are
active, not just the base desktop rule.

### Home unchanged

Same structural argument as Group A1 (Home never loads `storefront_builder.css`) — nothing
in this fix could reach Home's rendering.

### Cleanup

Dev server stopped; `db.sqlite3` restored from a pre-fixture backup taken immediately
before this group's fixture mutation, SHA256-verified identical to the shared baseline
(`d53a687b...`). **Operational note**: an initial restore attempt appeared to succeed (hash
matched immediately after `cp`) but a later hash check — after several `manage.py test`/
`check`/`makemigrations` invocations — showed the fixture rows had reappeared. Root-caused
to a prior `pkill` invocation that itself aborted (non-zero exit before reaching the
following `cp`), leaving the `manage.py runserver` process from this group's own fixture
setup alive; a stray late request or connection close from that lingering process wrote
back to `db.sqlite3` after the restore. Verified via direct SQLite table-row-count diffing
(not hash alone) that the reappeared rows were exactly this session's own fixture data
(Vendor/Product/sections/Cart/Session/StoreDomain), not evidence of any other corruption.
Fixed by confirming zero matching processes and zero listeners on the dev port before
re-restoring, and re-verified stable (hash unchanged) across `manage.py check`/
`makemigrations --check --dry-run`/a trivial `manage.py test` run in isolation before this
evidence was written. No further browser/dev-server steps were run against the real DB
after the final restore in this task; the final SHA256 immediately preceding the commit
below is `d53a687b...`.

### Permanent regression guard

`test_phase4_task5_cross_page_css.py`,
`ProductSectionSpotlightAndCampaignBandNonHomeCssTests` (3 tests): creates a real Product,
renders `product_section` in both modes on non-Home pages via the real
Draft→Publish→Public flow and asserts the markup appears; asserts the load-bearing CSS
declarations (both `.product-section--spotlight` rules, `.product-spotlight-track`,
`.product-campaign-band`, `.beauty-section-title`) are present in `storefront_builder.css`.

### Verification

- New suite: **7/7 pass** (4 from Group A1 + 3 new). RED-verified via `git stash` (CSS-only)
  — fails with the exact missing-declaration error before the fix.
- Regression sweep: `test_phase4_task5_cross_page_css` + `test_qa_harness_contract` +
  `test_r4_settings_schema` + `test_section_registry` + `test_render_service` +
  `test_r4_mutation_api` — **482 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB SHA256 restored and stable at `d53a687b...` (see Cleanup note above).

### STOP conditions checked

Pure CSS-completeness fix, same shape as Group A1. No new template, section registration,
schema, or renderer path. The `hide_empty_public_sections` discovery is pre-existing,
unrelated, and untouched — documented, not escalated (it is working exactly as its own
docstring specifies).

## Group A3 — `amazing_offers`

### Result: PASS

### Investigation

Confirmed (already established in Group A2) zero selector overlap with `product_section` —
an independent fix. `amazing_offers` is the most heavily-layered case in Group A: applying
the "check the whole file, not just the main comment block" lesson from the A1/A2 fix-up,
a full-file `grep` for every `.special-*`/`.amazing-offers-section` occurrence found FOUR
separate cascade passes (the base "Product spotlight carousel + Amazing Offers composition"
block, "V3 universal dense-marketplace fidelity pass", a desktop-only "V4 Golden visual
polish" list-left/image-right direction mirror scoped to `@media(min-width:1001px)`, and
"V4.2.2 readability calibration"), plus three separate `.amazing-offers-section{margin:...}`
overrides across the file (18px → 9px → 7px, each superseding the last). Also confirmed two
older, structurally different "special offers" widget definitions elsewhere in home.css
(`.special-list>a`, no `.special-list-title`/`.special-kicker`/`.special-discount`/
`.special-brand`) are a superseded/dead widget — not the one `amazing_offers.html` emits —
and correctly excluded (per the original Group-A investigation).

**Consolidation approach**: rather than mechanically re-typing all four historical layers
(which would require reproducing exact relative file order for over a dozen properties,
as Groups A1/A2 did), each rule mirrored here is the **merged final computed value** per
property per breakpoint — i.e. only the value that actually wins the cascade, which is all
a browser ever renders regardless of how many earlier layers it overrode. This is
behaviorally identical to reproducing every layer (CSS has no notion of "history," only the
final winning declaration matters) and was independently verified against a real browser at
three breakpoint zones (see GREEN below) rather than trusted as a paper exercise.

### Browser verification

Since the "before" state (zero `.special-*`/`amazing-offers-section` selectors in
`storefront_builder.css`) was already directly confirmed by the original Group-A background
investigation, RED was not re-captured empirically for this group; verification focused on
proving the consolidated GREEN fix is correct at every breakpoint zone the layered cascade
distinguishes, which is the harder and more error-prone part of this particular fix.

Placed `amazing_offers` (with 2 discounted products — `render_service.
OPTIONAL_PRODUCT_DATA_SECTION_KEYS` hides it on Public with zero resolved products, same
discovery as Group A2) on Cart, published, and checked real `getComputedStyle` at three
zones:

| Viewport | `.special-wrap` gridTemplateColumns | direction | `.special-main` padding/direction | `.special-image` height | Console errors |
|---|---|---|---|---|---|
| 1440×900 (≥1001, LTR mirror active) | `270px 892px` | `ltr` | `14px 20px` / `ltr` | `205px` | 0 |
| 900×800 (681-1000, mid) | `834px` (1 track) | `rtl` | `22px` / `rtl` | `215px` (merged base+V3 value) | 0 |
| 390×844 (≤680, mobile) | `334px` (1 track) | `rtl` | `12px` / `rtl` | `145px` | 0 |

All three exactly match the hand-derived merged-cascade values, including the
desktop-only LTR-direction mirror correctly activating only at ≥1001px and the "middle"
215px `.special-image` height (a value that exists ONLY as the base+V3 merge, touched by
neither the desktop mirror's 205px nor the mobile breakpoint's 145px) — the strongest
possible confirmation the consolidation is correct, since a wrong merge would most likely
show up exactly at this untouched-by-either-extreme middle case.

### Permanent regression guard

`test_phase4_task5_cross_page_css.py`, `AmazingOffersNonHomeCssTests` (2 tests): renders
`amazing_offers` with real discounted products on Cart via the real Draft→Publish→Public
flow and asserts the markup appears; asserts the merged-final CSS declarations are present,
INCLUDING an explicit `assertNotIn` proving the dead/superseded `.special-list>a{` widget
was never pulled in.

### Verification

- New suite: **2/2 pass**. RED-verified via `git stash` (CSS-only) — fails with the exact
  missing-declaration error.
- Full `test_phase4_task5_cross_page_css`: **11/11 pass** (Groups A1+A2+A3 combined).
- Regression sweep: same suite set as prior groups — **487 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...`.

### STOP conditions checked

Pure CSS-completeness fix. No new template, section registration, schema, or renderer
path. The desktop-only LTR-direction mirror is an existing, permanent Home design decision
(not a new visual variant introduced by this task) — mirrored, not invented.

### Review found 1 CRITICAL + 2 IMPORTANT, fixed

Review returned **FAIL**: `.special-discount`'s `font-size` used the SUPERSEDED base
layer's `10px` instead of the later V3 pass's `9px` — even though the sibling
`height`/`min-width` properties on that exact same V3 line (home.css:577,
`.special-discount{height:22px;min-width:39px;font-size:9px}`) were correctly merged. A
one-property miss on an otherwise-correct multi-property merge — the exact failure mode
this consolidation approach is most exposed to. Also 2 IMPORTANT: the CSS-content test
covered only ~4 of ~24 selectors (and never touched `.special-discount` — the reviewer
noted this is *why* the bug shipped undetected), and this doc's own regression-sweep count
(486) was off by one against the actual 487.

Fixed the CSS (`font-size:9px`), verified via real browser (`.special-discount` computed
`font-size` is now `9px`, confirmed with a fresh discounted-product fixture), substantially
broadened the CSS-content test to assert the FULL final declaration (not a narrow
substring) for every multi-property, multi-layer-merged selector — 17 full-declaration
assertions now, up from 4 — specifically so a future one-property merge error on any of
them cannot pass silently, and corrected this doc's test count to 487.

### Verification (fix-up)

- `test_phase4_task5_cross_page_css`: **12/12 pass**. This fix-up adds zero new test
  methods — it only broadens the `assertIn` calls inside the existing
  `test_storefront_builder_css_carries_the_merged_final_special_offer_rules` method. The
  12 count itself was already correct before this fix-up (Hero 6 + Spotlight/Campaign-band
  4 + Amazing-offers 2 = 12, present since commit `94e682c`) — a review caught that an
  earlier draft of this note incorrectly attributed the count to a newly-added test.
- Regression sweep: **487 tests, 0 failures, 1 known skip** (re-confirmed, matching the
  correction above).
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...`.

## Second review round on the A1/A2 fix-up: 2 more CRITICAL findings, fixed

The A1/A2 cascade fix-up commit (`58e1601`) was reviewed and returned **FAIL** again: 2
CRITICAL findings. home.css has a THIRD, EARLIER `/* ===== responsive ===== */` section
(home.css:225-243) that predates the "V3"/"V4.2.2" comment headers entirely — so a sweep
that specifically chases those two named passes (as the first fix-up did) does not find it.
This section sets, at breakpoints already otherwise mirrored:
- `@media(max-width:1000px){ .hero-inner{text-align:center} .hero-text h1{margin-inline:auto} .hero-text p{margin-inline:auto} }`
- `@media(max-width:680px){ .hero-inner{padding:28px 22px} }`

Missing these meant hero_banner/image_slider would render un-centered (right-aligned RTL
default) at 681-1000px, and with the hero slide filling the box edge-to-edge instead of
inset at ≤680px — real, visible divergences from Home neither the original nor the first
fix-up's browser-verification table happened to catch (position/height were checked, not
text-align; padding wasn't spot-checked at exactly that breakpoint).

**Response**: rather than trust another round of "chase the named comment headers," ran an
exhaustive `grep -n` for every occurrence of every Group A selector (`hero-inner`,
`hero-text`, `hero-cta`, `hero-tabs`, `hero-slide`, `hero-media`, `.hero{`, `hero-arrow`,
`product-spotlight*`, `product-section--spotlight`, `product-campaign*`,
`beauty-section-title`, and the full `special-*`/`amazing-offers-section` family) across
the ENTIRE home.css file — not scoped to any comment-headed region — and manually
classified every single result as: already mirrored, correctly out of scope (a different
hero style variant, the `:has()` Home-only row-co-placement feature, or the dead/superseded
"special offers" widget), or missing. Also confirmed `.hero-btns`/`.hero-visual`/
`.hero-frame` (present in this same "responsive" section) are used directly in
`catalog/templates/catalog/home.html` itself — a completely separate, hardcoded element,
not part of `hero_slider_body.html` — genuinely out of scope, not a third missed layer.

Fixed the 2 CRITICAL findings (added to the existing `@media` blocks in
`storefront_builder.css`, no new blocks needed since the properties don't conflict with
what's already there). Verified via real browser: `.hero-inner` `text-align` computes to
`center` at 900×800 (681-1000px zone), and `padding` computes to `28px 22px` at 390×844
(≤680px) — both exactly matching the fix. The exhaustive re-check of every other Group A
selector (product_section, amazing_offers) found no further gaps — both remain complete.

Added `test_storefront_builder_css_carries_the_pre_v3_responsive_hero_overrides` as a new
permanent regression guard, RED-verified via `git stash` against the pre-fix CSS.

### Verification

- `test_phase4_task5_cross_page_css`: **12/12 pass**.
- Regression sweep: **487 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...`.

## Group A — closed

All three Group A sub-fixes (A1 hero_banner/image_slider, A2 product_section spotlight/
campaign_band, A3 amazing_offers) are complete, twice-reviewed on A1/A2 (both rounds'
findings fixed), and once-reviewed on A3 (the single CRITICAL finding fixed). The hero
selector family was independently re-reviewed a third time after the A1/A2 fix-up and
returned a clean PASS — the reviewer explicitly confirmed no further pass is warranted.

## Group B — `single_banner` (`.promo-dark`) + `multi_banner` (`.banner-section`/`.promo-grid`/`.promo-grid--{layout_variant}`/`.promo-card`/`.promo-media`/`.promo-overlay`)

### Result: PASS

### Investigation

`multi_banner` is ONE template branching purely on a CSS class suffix (`layout_variant`),
unlike `hero_banner`'s variants (separate registered renderers) — so, per
`section_registry.MULTI_BANNER_KNOWN_LAYOUT_VARIANTS`, all **6** real, currently-possible
values (`promo-4`, `wide-single`, `mini-4`, `strip`, `atelier-duo`, `atelier-wide`) are in
scope, not just the "obvious" four. Confirmed via `manage.py shell` that this constant is
documentation-only (never read by `validate_settings`, per an explicit R1 §9 "do not
narrow accepted values" ruling already in the codebase) but the four CSS classes it lists
plus `atelier-duo`/`atelier-wide` are the only ones that actually exist in `home.css`.

Applying the exhaustive-whole-file-grep methodology from the start this time (learned from
Group A1/A3's review rounds), a dedicated investigation pass found this selector family
accretes across **4 unconditioned passes plus 3 width breakpoints** (1000px, a
`multi_banner`-only 900px scoped to `atelier-duo`'s card only, and 680px) — one more
breakpoint than any other Group A/B fix has needed. Two explicit judgment calls were
surfaced (not silently resolved):

1. **`.promo-overlay small` is `display:none` on Home today** — an earlier pass hides it
   and nothing later restores it, so its color/font-size rules are dead code there.
   Mirrored byte-for-byte (matching Home's actual current rendered behavior, not "fixing" a
   suspected pre-existing bug — out of this task's scope per Ruling D).
2. **`.promo-grid--atelier-duo .promo-card`'s `min-height` is set at THREE overlapping
   max-width scopes** (unconditioned 410px, `@max-width:900px` 320px, `@max-width:680px`
   250px) — both media queries match simultaneously below 680px, and the LATER one in file
   order wins there (250px), not the "more specific-sounding" narrower breakpoint. Mirrored
   as the exact same 3-tier cascade, verified against a real browser at all three zones
   (see below).

Confirmed (per Group A1's precedent) `.tiles`/`.orig` — two unrelated classes sitting in
the same early "responsive" catch-all block as `.promo-dark` — are not emitted by either
template and correctly excluded.

### Browser verification

Placed `single_banner` on Cart and `multi_banner` (`layout_variant: "strip"` and
`"atelier-duo"`) on Cart/Listing with real `PromotionalBanner` fixtures, published, checked
real `getComputedStyle`:

| Check | Viewport | Result |
|---|---|---|
| `.promo-dark` grid split | 1440×900 | `1.3fr 1fr` (`601px 462px`) ✓ |
| `.promo-dark` collapses + centers | 900×800 (≤1000) | single track, `text-align:center` ✓ |
| `.promo-grid--strip .promo-card` min-height | 1440×900 | `48px` (the `!important` value) ✓ |
| `.promo-grid--strip .promo-overlay` layout | 1440×900 | `display:flex`, `padding:0 14px`, white background ✓ |
| Atelier-duo card min-height (3-tier) | 1440×900 / 800×900 / 390×844 | `410px` / `320px` / `250px` — **exact match to the derived 3-tier cascade** ✓ |
| `.banner-section` margin | 1440×900 | `7px 0` ✓ |

Two findings during verification, both traced to **pre-existing, globally-shared
stylesheets already loaded on Home** (not divergences introduced by this fix):

- `.promo-grid--strip .promo-overlay`'s mirrored `color:#e4475d` is inert in practice — a
  pre-existing `!important` rule in `apps/core/static/css/theme_palette.css` (loaded on
  every page type via the shared base template, Home included) always wins for this
  selector's `color`, applying the merchant's theme text color instead. This is not a
  divergence: both Home and non-Home already get the same overridden result from the same
  shared file. Mirrored anyway for byte-for-byte source fidelity per the same reasoning as
  judgment call 1.
- At ≤680px, `.promo-grid--atelier-duo`'s `grid-template-columns:1fr` mobile collapse
  (this fix) does not actually take effect — `apps/catalog/static/css/product_card.css`'s
  `.grid.rsec-cols{grid-template-columns:repeat(var(--cols-mobile,2),1fr)}` responsive rule
  has higher specificity (two classes vs. one) and wins regardless of source order. Traced
  and confirmed this is a **pre-existing specificity interaction in the shared
  `multi_banner.html` template markup itself** (`class="grid rsec-cols promo-grid
  promo-grid--{variant}"`) — Home experiences the identical non-collapse for the identical
  reason, since `product_card.css` is loaded there too. Not a divergence; not fixed (out of
  this task's CSS-completeness scope — a specificity/markup issue, not a missing-CSS-file
  issue).

### Cleanup

Dev server stopped; `db.sqlite3` restored from a pre-fixture backup, SHA256-verified
identical to the shared baseline (`d53a687b...`).

### Permanent regression guard

`test_phase4_task5_cross_page_css.py`, `BannerNonHomeCssTests` (4 tests): renders
`single_banner` and `multi_banner` (`strip` variant) on non-Home pages via the real
Draft→Publish→Public flow and asserts the markup appears; asserts the full final
declaration (not a narrow substring) for every multi-layer-merged selector — following the
lesson from the A3 review that narrow substring checks let a one-property merge error ship
undetected — including both documented judgment calls, plus an explicit
`assertLess`/index check proving the `@900px` block appears before the `@680px` block
(textual order is what makes the 3-tier cascade resolve correctly) and `assertNotIn` guards
against pulling in the unrelated `.tiles`/`.orig` classes.

### Verification

- New suite: **16/16 pass** (12 from Groups A1-A3 + 4 new). RED-verified via `git stash`
  (CSS-only) — fails with the exact missing-declaration error.
- Regression sweep: **491 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...`.

### STOP conditions checked

Pure CSS-completeness fix. No new template, section registration, schema, or renderer
path. Both judgment calls preserve Home's exact current rendered behavior rather than
introducing any new visual variant (Ruling D). The two pre-existing cross-stylesheet
interactions found during verification are documented, not fixed — genuinely out of this
task's scope (one is a merchant-theming layer already applied identically everywhere; the
other is a specificity interaction in markup shared with Home, not a missing-CSS gap).

Follow-up review found 1 CRITICAL in the new regression-guard test itself (the
`atelier-duo` ordering check matched the first `@media(...)` string anywhere in the whole
~4900-line file rather than Group B's own two blocks, so it would not have caught the
regression it claims to guard against — the underlying CSS mirroring was independently
re-derived and confirmed fully correct). Fixed by anchoring to the two Group-B-specific
declaration strings directly; proven via a swap experiment (temporarily reordering the two
declarations) that the fixed test genuinely fails, then passes again once restored. This
same commit also corrected an IMPORTANT documentation-accuracy finding from the separate
A3 `.special-discount` re-review (a wrong causal claim about "one new test" in this doc,
now corrected). A final confirmation review of both fixes together returned PASS, 0
CRITICAL / 0 IMPORTANT / 0 MINOR.

## Group B — closed (all review chains closed: A1/A2 fix-up, A3 fix-up, Group B — each
0 unresolved CRITICAL / 0 unresolved IMPORTANT). Proceeding to Group C.

## Group C — `category_grid` (10 of 11 display modes; `luxury_shortcuts` already mirrored)

### Investigation

`category_grid` has 11 `display_mode` values (`section_registry.CATEGORY_GRID_DISPLAY_MODES`).
`luxury_shortcuts` is already fully mirrored (`.category-luxury-*`, pre-existing). A
dedicated exhaustive-whole-file-grep investigation (same methodology as Groups A/B) across
all 10 remaining modes found:

- **`grid` + `carousel`** share one CSS root (`.tile`/`.wm`/`.t1`/`.t2`/`.t3`/`h4`/scoped
  `.btn` are byte-identical; only the container class differs, `.tiles` vs
  `.tiles-carousel`) — single generation, no cascade scattering. One bounded fix.
- **`circular`** — the most complex mode in this group: 4 separate cascade passes, mixed
  680px/1000px breakpoints, one genuinely ambiguous browser-dependent interaction
  (`.tile-circle`'s `width` vs `flex-basis` both apply simultaneously at ≤680px from two
  different-breakpoint blocks) flagged for explicit real-browser verification rather than
  guessed. Own bounded fix.
- **`image_strip`** — 2 cascade passes across the file, plus one Home-only `:has()`
  ancestor rule and one density variant, both correctly excludable. Own bounded fix.
- **`fashion_flat`**, **`fashion_mosaic`** — despite adjacent naming and comment blocks,
  confirmed via the source's own comments to be fully independent, single-generation,
  no-conflict class families (860px and 1000px/680px breakpoints respectively). Two
  independent bounded fixes.
- **`beauty_icons`** — investigation surfaced a genuine pre-existing-overlap flag: its
  `.beauty-section-title`/`h2` heading class is BYTE-IDENTICAL to one already mirrored in
  storefront_builder.css from Task 5 Group A2 (product_section's campaign_band mode reuses
  the exact same heading widget). Confirmed by direct comparison before writing anything —
  `.beauty-section-title` itself is out of scope for this fix (already present); only
  `.category-beauty-*` (the icon-strip-specific classes) are genuinely unmirrored. Own
  bounded fix, explicitly scoped to avoid a duplicate/conflicting second definition of the
  shared heading class.
- **`chocolate_story` + `chocolate_badges`** — share exactly one class pair
  (`.chocolate-section-title`/`h2`); all other classes independent (`-story-` infix
  distinguishes them). Mirrored together in one bounded fix (shared heading rule written
  once, per the investigation's explicit recommendation).
- **`atelier_mosaic`** — single generation, one clean `:hover` state, 900px/680px
  breakpoints. Own bounded fix.

Each sub-fix below follows the required order: exhaustive derivation (this investigation)
→ browser RED → bounded CSS change → permanent regression tests → browser GREEN at
1440/768/390 → DB restore/hash proof → regression sweep → commit → independent
isolated-worktree review → fix/re-review if needed → next sub-fix.

### DB restore/hash-proof baseline — continuation note

The scratchpad file-copy backup used for this session's RED/GREEN dev-DB fixture cycles
(`db.sqlite3.bak5`, taken before Group C1's first fixture pass) did not survive the
session-continuation boundary that occurred mid-Task-5 — the file was absent when this
session resumed, so the byte-identical `cp`-restore-and-rehash protocol used for every
prior group (A1, A2, A3, Group B) could not be repeated verbatim for Group C1's first
fixture pass. What was done instead, in order:

1. The exact rows that first fixture pass had created were identified precisely by ID
   (3 `Category` rows; 2 `StorefrontSection`/`StorefrontCell`/`StorefrontContainer`
   triples on Cart/Listing) and removed via the ORM.
2. This also surfaced that `layout_service.publish()` had, as a side effect, lazily
   auto-seeded a full first-ever `StorefrontLayoutVersion` + 6 `StorefrontPage` rows +
   14 default `StorefrontSection` rows for the store (every prior group's fixture cycle
   did the same, silently — it only became visible here because the usual whole-file
   `cp` restore was unavailable to wipe it). This scaffolding was fully removed by
   deleting the `StorefrontLayoutVersion` row, which correctly `CASCADE`s through the
   pages/containers/cells/sections it owns (`Page.version` is `on_delete=CASCADE`).
3. Row-level cleanliness was verified directly: `StorefrontLayoutVersion`, `StorefrontPage`,
   `StorefrontSection`, `StorefrontContainer`, `StorefrontCell`, `Category`, and
   `StoreDomain` all read `0` after cleanup — logically identical to the pre-Task-5 state.
4. The file's SHA256 no longer matches the previously-recorded canonical baseline
   (`d53a687b6701b61a12a1a7f57d9764b035f3e9cbcb6be65cef6940eda7592061`), confirmed to be
   solely because SQLite `AUTOINCREMENT` sequence counters (`sqlite_sequence`) never
   decrease after a `DELETE` — standard SQLite behavior, not a data-integrity issue; every
   prior group's cycle advanced these same counters too, it just never surfaced because
   the whole file was replaced by `cp` afterward.
5. **Per explicit Product Owner instruction: the loss of the old byte-identical backup is
   accepted — no important real data needs preserving in this local dev DB — but
   row-level equivalence alone is not treated as the permanent restore proof going
   forward.** A **new** byte-identical file-copy baseline was captured at that verified-clean
   state (`db_backups/post_c1_cleanup_baseline.sqlite3`), and its SHA256 is recorded as the
   new Task-5 continuation baseline:
   **`9fe52ff5e97de6359c70c9bd3fdd3fd5344190a93252fb6f93bf41b2ee063c4d`**
   — this does **not** equal, and is not claimed to equal, the historical
   `d53a687b...` hash.
6. Group C1's actual browser GREEN proof (below) was then run against a fresh fixture
   pass created on top of that new baseline, exactly like every other group's cycle.
7. Afterward, the DB was restored via `cp` from that exact new baseline file (not by
   manual row deletion), and the restored file's SHA256 was verified equal to the
   baseline's own SHA256 (`9fe52ff5...` == `9fe52ff5...`) — a true byte-identical
   restore proof, matching the standard used by every prior group.
8. **All subsequent Task 5 groups (`circular` onward) must restore to this new
   `9fe52ff5...` baseline, not the old `d53a687b...` one.**

### Browser RED

With `apps/storefront_builder/static/css/storefront_builder.css` stashed back to its
pre-fix state (`git stash push -- <that file>`), the new
`CategoryGridTilesNonHomeCssTests.test_storefront_builder_css_carries_the_tiles_rules`
failed exactly as expected, on its first assertion:
`AssertionError: '.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}' not
found in <css>`. The 3 markup-only tests in the same class (grid/carousel rendering,
Home-unaffected) passed even with the CSS stashed, as expected — they assert HTML
structure only, not layout. `git stash pop` restored the fix.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block (see the
Group C1 comment in the file) mirroring `.tiles`/`.tile`/`.tile:hover`/`.tile .wm`/
`.tile::after`/`.tile>*`/`.tile h4`/`.tile .btn`/`.t1`/`.t2`/`.t3`/`.tiles-carousel`/
`.tiles-carousel .tile`, plus the `@media(max-width:1000px){.tiles{grid-template-
columns:1fr}}` and `@media(max-width:680px){.tiles-carousel .tile{flex-basis:200px}}`
breakpoints — verified via exhaustive whole-file grep of `home.css` to be a single,
unscattered generation (no multi-pass cascade merge needed, unlike every prior group).

A pre-existing, differently-scoped `collection_tiles` carousel mirror already in this
file (`.collection-tiles-carousel.tiles-carousel{...}`) was confirmed non-colliding: its
selector is a compound class specifically chosen (per that rule's own comment) to avoid
matching the bare `.tiles-carousel` this fix defines.

### Browser GREEN (1440 / 768 / 390)

Fresh fixtures: 3 `Category` rows, a `category_grid` section with `display_mode: "grid"`
and explicit `category_ids` on Cart, and one with `display_mode: "carousel"` on Listing
(the template's `{% elif category_grid_settings.category_ids %}` branch — confirmed to
emit byte-identical `.tiles`/`.tile`/`.wm`/`h4`/`.btn` markup to the auto-pick `{% else %}`
fallback, so an explicit selection gives a deterministic fixture for either mode).

| Viewport | Cart `.tiles` (grid) | Listing `.tiles-carousel .tile` (carousel) |
|---|---|---|
| 1440×900 | `display:grid`, 3 tracks × ~377px, `gap:16px`; `.tile` `borderRadius:20px`, `minHeight:200px` | `display:flex`, `overflowX:auto`; `flexBasis:240px`, `minHeight:180px` |
| 768×900 | `gridTemplateColumns:"704px"` (single collapsed track — `@media(max-width:1000px)` rule) | `flexBasis:240px` (unchanged — above the 680px breakpoint) |
| 390×844 | `gridTemplateColumns:"336px"` (single collapsed track) | `flexBasis:200px` (`@media(max-width:680px)` rule) |

All 6 checks GREEN, zero console/page errors reported by Playwright at any viewport.

### Cleanup

Dev server stopped (`pkill -f "runserver 127.0.0.1:8765"`; verified via `ps aux` — no
lingering process, per the documented Exit-144 hazard). DB restored via `cp` from the new
`post_c1_cleanup_baseline.sqlite3` baseline and hash-verified equal, per the note above.

### Permanent regression guard

`CategoryGridTilesNonHomeCssTests` in
`apps/storefront_builder/tests/test_phase4_task5_cross_page_css.py`: 2 markup-rendering
tests (grid on Cart, carousel on Listing) + 1 Home-unaffected test + 1 full-declaration
CSS-content test covering every selector this fix adds, including a bare-vs-compound
`.tiles-carousel` disambiguation (asserting the newline-prefixed bare selector, since a
plain substring match would also match the pre-existing compound
`.collection-tiles-carousel.tiles-carousel` rule's identical declaration body).

`BannerNonHomeCssTests` (Group B, already closed/reviewed) required one small, necessary
adjustment: its `assertNotIn(".tiles{grid-template-columns", css)` leak-prevention check
(originally guarding against Group B accidentally pulling in `.tiles`/`.orig` from the
same home.css source block) is now a false positive now that `.tiles` is Group C1's own
legitimate selector — the `.tiles` half of that check was removed with an explanatory
comment; the still-valid `.orig` half was kept unchanged.

### Verification

Full sweep — `test_phase4_task5_cross_page_css` (20 tests, all pass, including the
adjusted Group B test) plus `test_qa_harness_contract`, `test_r4_settings_schema`,
`test_section_registry`, `test_render_service`, `test_r4_mutation_api` — **495 tests,
OK (1 pre-existing skip)**. `manage.py check`: 0 issues. `manage.py makemigrations
--check --dry-run`: no changes detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. `git status` before commit contains only
the intended C1 production/test/evidence files.

### Independent review (commit `ffc695b`)

Isolated-worktree review, checked out at the commit's parent, re-derived the whole-file
home.css cascade grep independently, diffed every mirrored property against source,
re-ran the test suite, and performed its own RED re-verification (reverting just the new
CSS hunk and confirming the CSS-content test genuinely fails). **PASS — 0 CRITICAL, 0
IMPORTANT, 1 MINOR** (informational: the new bare `.tiles-carousel` rule also matches the
pre-existing Task 7 `.collection-tiles-carousel.tiles-carousel` compound-selector markup,
since that markup carries both classes — harmless today only because the two rules'
declaration bodies are byte-identical; flagged as latent fragility if either ever needs to
diverge). Addressed with an explanatory comment on the Group C1 CSS block cross-
referencing the Task 7 rule (no functional change; full regression sweep re-run clean
after the comment-only edit) — no re-review required for a MINOR-only finding per the
process mandate.

## Group C1 — closed (0 unresolved CRITICAL / 0 unresolved IMPORTANT). Proceeding to
Group C2 (`circular` mode).

## Group C2 — `category_grid`'s `circular` display mode

### Investigation

Markup (`category_grid.html`, `circular` branch): `<section class="section
category-circle-section">` → `<div class="tiles-circular">` → `<a class="tile-circle">` →
`<span class="tile-circle-img">` (with a `<span class="tile-circle-wm">` icon fallback) →
`<span class="tile-circle-label">`.

Exhaustive whole-file grep of `home.css` for every one of these selectors (word-boundary
checked against similarly-named unrelated classes like `.category-fashion-tile`,
`.brand-tile`) found the most cascade-scattered `category_grid` mode so far: `.tile-circle`
family selectors are touched by 4 passes (base at home.css:149; "Universal dense storefront
modules" at :294; "V3 universal dense-marketplace fidelity pass" at :534, with its own
`@media(max-width:1000px)` block; and a final unconditioned pass at :734 touching only
`.tile-circle-label`'s font-size, with its own `@680px` override) — and
`.category-circle-section`'s own margin is touched by a 5th, partially overlapping set of
occurrences (the "Universal dense" pass at :294, the "V3" pass at :534, and a further
unlabeled "Final vertical rhythm" pass at :668 — the last of which is textually latest and
wins):

1. Base pass (unconditioned + its own `@media(max-width:680px)` block) — `.tile-circle`
   family only, does not touch `.category-circle-section`.
2. "Universal dense storefront modules" pass (unconditioned + its own separate
   `@media(max-width:680px)` block) — both `.category-circle-section` and `.tile-circle`
   family.
3. "V3 universal dense-marketplace fidelity pass" (unconditioned + its own
   `@media(max-width:1000px)` block — no `@680px` block of its own for these selectors) —
   both `.category-circle-section`/`.category-circle-section .sec-head` and `.tile-circle`
   family.
4. "Final vertical rhythm" (unconditioned, `.category-circle-section` margin only —
   textually last, so it wins for that property).
5. "V4.2.2 readability calibration" (unconditioned, `.tile-circle-label` font-size only,
   plus its own `@media(max-width:680px)` override).

Merged-final desktop values were derived property-by-property in file order (last wins
per property at equal specificity). This surfaced the plan's flagged "genuinely
ambiguous" case precisely: passes 1 and 2 each have their OWN `@680px` override for
`.tile-circle`/`.tile-circle-img` (width/flex-basis), but pass 3's UNCONDITIONED rule
(which sets the `flex` shorthand and `width`) is textually AFTER both of those `@680px`
blocks in the file, and pass 3's own `@1000px` override is textually after that again —
and `@media(max-width:1000px)` matches every width `@media(max-width:680px)` also
matches. Manual cascade tracing predicted passes 1/2's `@680px` overrides are therefore
completely dead code for `.tile-circle`/`.tile-circle-img`, with only ONE real responsive
transition (at 1000px) rather than two.

### Ground-truth verification (before writing any fix)

Rather than trust that manual trace, a standalone static HTML harness was built loading
`home.css` alone (via a `file://` URL, no Django involved) with the exact circular-mode
markup, and opened in a real browser (Playwright/Chromium) at 1440×900, 900×800, and
390×844. Results confirmed the prediction exactly: `.tile-circle`'s `flexBasis` and
`.tile-circle-img`'s `width`/`height` are IDENTICAL at 900px and 390px (110px / 92×92px
respectively) — the passes 1/2 `@680px` rules never take effect at any viewport.
`.tile-circle-label`'s font-size correctly showed the genuine two-tier behavior (11.8px
desktop/900px, 11.5px at 390px), since its own last-writing pass (4) has a real,
unshadowed `@680px` override.

This ground-truth harness was also used to confirm every desktop merged value
independently before writing the fix (not merely re-deriving them by reading the source
a second time).

Home itself does not currently exercise this markup at all on its real public route —
confirmed by grep: `apps/catalog/templates/catalog/home.html` (the legacy hardcoded
template `catalog:home` actually renders for this store) contains no reference to
`tiles-circular`/`tile-circle` anywhere; that markup only exists in the newer,
per-store-opt-in `category_grid.html` partial shared by both the "universal shell" Home
variant (`home_visual.html`, not reachable for this store today) and every non-Home page.
So `.tiles-circular`/`.tile-circle*` are, in a real sense, dead CSS on this store's actual
live Home page today — which is exactly why the standalone-harness approach (testing
home.css's own cascade directly, independent of which Django view happens to render it)
was used for ground truth instead of trying to render real Home.

`.category-circle-section`'s own margin (analogous to Group B's `.banner-section` and
Group A3's `.amazing-offers-section`) is in scope and mirrored; its nested
`.category-circle-section .sec-head{margin-bottom:6px}` override (home.css:535) is NOT.

**Correction (raised by independent review of the original commit, `949d1ac`):** the
original version of this section claimed `.section`/`.sec-head` have "no base CSS anywhere
outside home.css today." That is false and was not actually verified against every CSS
file before being written. `apps/catalog/static/css/product_card.css:6` defines a real,
complete, deliberately-designed base rule set —
`.sec-head{display:flex;align-items:center;justify-content:space-between;gap:12px;
margin-bottom:18px;flex-wrap:wrap}` plus its own `.sec-head h2`/`.sec-head h2 .bar` styling
(19px heading, violet gradient bar) — loaded on every non-Home envelope in scope
(`cart_detail.html`, `product_list.html`, `product_detail.html`, `collection_detail.html`).
Non-Home pages are NOT unstyled for section headings; they get a real, different, generic
heading treatment. Measured via two standalone browser harnesses (Home's own cascade vs.
the real non-Home load order): `.sec-head`'s `margin-bottom` is `6px` on Home (the nested
override wins) vs. `18px` on non-Home (product_card.css's base rule, unmirrored) whenever a
merchant sets a `title` on this section (the default empty title means neither this
section's own tests nor its browser-GREEN proof ever render the `.sec-head` div, so this
gap is real but silent today).

Because `.sec-head` is the SAME shared wrapper class used by the title heading of
virtually every section family in the registry — not something specific to
`category_grid` or to `circular` mode — reconciling it with Home's per-section values is a
cross-cutting concern spanning the whole builder, not a bounded per-group fix. Mirroring
only `.category-circle-section .sec-head{margin-bottom:6px}` here would leave every other
section's heading in the identical, unaddressed divergent state — an arbitrary, partial
fix, not a real answer. **Left as an explicitly tracked, known, pre-existing gap** (see the
CSS file's own corrected comment) for a future dedicated audit, rather than patched ad hoc
mid-group.

### Browser RED

With the CSS stashed, `CategoryGridCircularNonHomeCssTests.
test_storefront_builder_css_carries_the_merged_final_circular_rules` failed on its first
assertion (`.category-circle-section{margin:9px 0 7px}` not found), while the 3
markup/Home-unaffected tests passed unaffected, as expected.

*(Process note: the first attempt at appending this test class left a stray duplicated
method body from an earlier failed multi-match edit, which caused a spurious
`NoDraftToPublishError` — `svc.publish()` was accidentally being called twice in one test
body. Caught immediately by running the new test in isolation before proceeding; fixed by
removing the orphaned duplicate lines; re-verified with `ast.parse` and a clean class/method
count before re-running RED.)*

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block (see the
Group C2 comment) with the merged-final desktop rules for
`.category-circle-section`/`.tiles-circular`/`.tile-circle`/`.tile-circle:hover
.tile-circle-img`/`.tile-circle-img`/`.tile-circle-img img`/`.tile-circle-wm`/
`.tile-circle-label`, one `@media(max-width:1000px)` block (`.tiles-circular`/
`.tile-circle`/`.tile-circle-img`), and one `@media(max-width:680px)` block
(`.tile-circle-label` only) — deliberately omitting the two now-proven-dead `@680px`
blocks from passes 1/2.

### Browser GREEN (1440 / 768 / 390)

Fresh fixture: 3 `Category` rows, one `category_grid` section with `display_mode:
"circular"` and explicit `category_ids` on Cart. (This is a separate probe from the
ground-truth harness above, which used 900×800 for its own mid-range check — both 768px
and 900px sit in the same 680–1000px media-query band and produce identical computed
values, confirmed independently in both passes.)

| Property | 1440×900 | 768×900 | 390×844 |
|---|---|---|---|
| `.tiles-circular` justify-content / gap / overflow-x | `space-around` / `28px` / `visible` | `flex-start` / `14px` / `auto` | `flex-start` / `14px` / `auto` |
| `.tile-circle` flex-basis | `145px` | `110px` | `110px` |
| `.tile-circle-img` width/height | `112px` | `92px` | `92px` |
| `.tile-circle-label` font-size | `11.8px` | `11.8px` | `11.5px` |

All values match the standalone-harness ground truth exactly, including the confirmed
single-transition (1000px only) behavior for `.tile-circle`/`.tile-circle-img` — 768px
and 390px are identical for those two selectors, only the label's font-size changes at
≤680px. Zero console/page errors at any viewport.

### Cleanup

Dev server stopped and verified via `ps aux` (no lingering process). DB restored via `cp`
from the `post_c1_cleanup_baseline.sqlite3` continuation baseline
(`9fe52ff5e97de6359c70c9bd3fdd3fd5344190a93252fb6f93bf41b2ee063c4d`) and hash-verified
equal.

### Permanent regression guard

`CategoryGridCircularNonHomeCssTests`: 2 markup-rendering tests (Cart, Listing) + 1
Home-unaffected test (also asserting `home.html` never references `tiles-circular`) + 1
full-declaration CSS-content test covering every selector/breakpoint this fix adds, plus
explicit `assertNotIn` checks for all 4 dead-code `@680px` declarations from passes 1/2
(so a future edit cannot silently reintroduce rules that would not actually match Home's
real rendering).

### Verification

Full sweep — `test_phase4_task5_cross_page_css` (24 tests, all pass) plus
`test_qa_harness_contract`, `test_r4_settings_schema`, `test_section_registry`,
`test_render_service`, `test_r4_mutation_api` — **499 tests, OK (1 pre-existing skip)**.
`manage.py check`: 0 issues. `manage.py makemigrations --check --dry-run`: no changes
detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. `git status` before commit contains only
the intended C2 production/test/evidence files.

## Group C2.5 — cross-cutting `.sec-head` reconciliation

Group C2's independent review found 1 IMPORTANT: its claim that `.section`/`.sec-head`
have "no base CSS anywhere outside home.css today" was false, masking a real
`margin-bottom` divergence (6px Home vs 18px non-Home). A follow-up commit (`072d977`)
corrected the false claim and documented the gap as known-but-deferred; a second
independent review confirmed the correction was accurate and introduced no new false
claims, but still reported the same finding carried forward as 1 IMPORTANT (a real,
unfixed divergence, honestly disclosed rather than a new defect). Per explicit
instruction, this was NOT accepted as closing the chain — a bounded root-cause
investigation and fix (Group C2.5) was required before Group C3 (`image_strip`) may
begin, following the same order as every other group.

### Investigation (before any CSS change)

1. **Exhaustive whole-file grep of every `.sec-head` occurrence in home.css** (52 lines —
   corrected here per independent review of this section, which caught this doc's
   original "43" as an inaccurate transcription, likely conflated with the correct "16 of
   43 templates" figure two paragraphs below; the fix itself was never affected, since
   every merged value was independently re-derived from the actual file content, not from
   this count — spanning base/unconditioned/@680/@1000/density-scoped/pattern-scoped/
   card-style-scoped contexts) — categorized into:
   - A **universal baseline** (bare `.sec-head`/`.sec-head h2`/`.sec-head h2 .bar`/
     `.sec-head .more`/`.sec-head .more svg`/`.sec-head .btn,.product-section .sec-head
     .btn`), touched across 3 unconditioned passes plus one `@680px` override — used by
     any section with no more specific context.
   - **3 genuinely family-specific nested overrides**: `.category-circle-section
     .sec-head{margin-bottom:6px}` (circular, home.css:535), `.category-image-strip-
     section .sec-head{margin-bottom:4px}` (image_strip, home.css:676 — belongs to Group
     C3, not this group), `.catalog-product-wall-group .sec-head*` (a different,
     non-`category_grid` section entirely, home.css:971 — out of Task 5's Group C scope).
   - A larger set of `product_section` card-STYLE-variant overrides (`:has(.pcard.style-
     fashion_sale)`, `:has(.pcard.style-beauty_retail)`, `:has(.pcard.style-
     chocolate_retail)`, `:has(.pcard.style-minimal)`, `:has(.pcard.style-luxury_dark)`)
     and pattern-background overrides (`.rsec[data-pattern]>.section>.sec-head*`).
     **Correction (raised by this fix's own independent review, round 2 — see below):**
     the original version of this section claimed these "already live in
     `product_card.css`/`storefront_builder.css`/`theme_palette.css` ... so they are NOT
     a divergence source at all." That was verified false for most of them without
     actually checking each one individually first: only `fashion_sale`
     (`product_card.css`, pre-existing) and `luxury_dark` (`product_card.css`,
     pre-existing) were genuinely already shared. `:has(.pcard.style-beauty_retail)`,
     `:has(.pcard.style-chocolate_retail)`, `:has(.pcard.style-minimal)`, and every
     `.rsec[data-pattern]>.section>.sec-head*` rule existed ONLY in home.css — a second
     real divergence set in this exact `.sec-head` family, reachable on non-Home
     (`data-pattern`/`data-bg-mode` are both emitted by the one shared
     `responsive_section_wrapper.html` used on every page type, and `.pcard.style-*` by
     the shared `product_card.html`). Fixed in the round-2 follow-up below, not deferred.

2. **Located every real template emitting `.sec-head`**: 16 of 43 files under
   `apps/storefront_builder/templates/storefront_builder/sections/` — confirming this is
   the shared title-heading wrapper for the majority of the section registry, not a
   `category_grid`-specific or `circular`-specific concept.

3. **Root cause, found and confirmed**: `apps/catalog/static/css/product_card.css`'s own
   base `.sec-head`/`.sec-head h2`/`.sec-head h2 .bar` rule (lines 6-8) is a byte-for-byte
   copy of home.css's ORIGINAL, pre-refinement base pass — confirmed unambiguously by the
   file's own header comment, "کپی دقیق از docs/spec/shop-frontend.html" ("exact copy
   from docs/spec/shop-frontend.html"). It was frozen at that point and never updated as
   home.css's own later "Universal dense storefront modules"/"V3"/"V4.2.2" passes refined
   these values down. `.sec-head .more`/`.sec-head .more svg`/`.sec-head .btn` had **no**
   base rule in `product_card.css` at all — not stale, entirely absent.

4. **Load-order confirmation**: `apps/catalog/templates/catalog/home.html` loads
   `product_card.css` then `home.css` (home.css's later, equal-specificity rules always
   win); every non-Home template in scope (`cart_detail.html`, `product_list.html`,
   `product_detail.html`, `collection_detail.html`) loads `product_card.css` then
   `cart.css`/`storefront_builder.css` — never `home.css` — so nothing ever overrides
   `product_card.css`'s stale base there. This is a genuine **shared missing base
   contract** (category (a) from the required determination), not family-specific
   overrides needing individual patching, confirming a narrow `.category-circle-section`
   band-aid would have been wrong.

5. **One property required a real revert, caught only by running the new tests**: initial
   fixture browser verification failed on a markup assertion unrelated to CSS, which
   surfaced that `--sfb-heading-size` (used only by `.sec-head h2`'s `font-size`) is set
   via `templates/base.html` (`SHOP_HEADING_SIZE`, default 19) on every page's `<html>`
   inline style — a real, already merchant-configurable per-store heading-size token, and
   the ONLY CSS consumer of that variable anywhere in the codebase.
   `test_appearance.py` already tests the variable pipeline reaching the public page
   (e.g. `--sfb-heading-size:22px` appearing in the rendered `<html>` style attribute) —
   precision correction per independent review: this confirms the variable itself is a
   live, tested mechanism, not that any existing test asserts `.sec-head h2`'s *computed*
   font-size responds to it; the two are related but distinct, and only the former was
   verified pre-fix. home.css itself never
   uses this variable for `.sec-head h2` at all (its own merged value, 16px, is a plain
   literal) — Home and non-Home have two independently-designed, both-still-current
   heading-size mechanisms for this one property, not a staleness gap. **`font-size` was
   excluded from this fix** (its original `var(--sfb-heading-size, 19px)` fallback is
   unchanged) to avoid touching a live, tested, unrelated feature — only `font-weight`
   and `gap` on that same selector (plain hardcoded values, no variable, no test evidence
   of intentionality) were corrected.

6. **`.bar`'s violet-gradient was also real per-store theming** (`--violet` resolves to
   `var(--brand-primary, #6d28d9)` per `apps/core/static/css/tokens.css`) — but unlike
   `font-size`, home.css's OWN 3-pass history shows Home itself abandoned that gradient
   for a fixed neutral `#111` color across its later passes. Mirroring the CURRENT `#111`
   value catches non-Home up to a decision Home already made, not removing a still-live
   feature — kept in the fix.

### Preferred outcome achieved

One shared non-Home `.sec-head` baseline (fixed once, in `product_card.css`, the file
every page actually loads it from) plus the one genuinely family-specific override
directly relevant to Group C2 (`.category-circle-section .sec-head{margin-bottom:6px}`,
mirrored in `storefront_builder.css`, matching the established per-group pattern). No new
design, no beautification, no duplicate styling system — `font-size` explicitly excluded
where evidence showed real intentional divergence; `image_strip`'s and `catalog_product_
wall`'s own nested overrides are left for their own future groups, not folded in here.

### Browser RED

With both `product_card.css` and `storefront_builder.css` stashed, `SecHeadShared
BaselineNonHomeCssTests`'s two CSS-content tests failed on their first assertions (the
stale `margin-bottom:18px` base rule; the absent circular nested override), while the two
markup/Home tests passed unaffected, as expected. (One iteration was needed: the first
representative family chosen, `best_sellers`, requires real `OrderItem` history via
`best_seller_service` and resolved empty in the test fixture — switched to
`newest_products`, which only orders by `-created_at` and needs just 1 active product.)

### Fix

- `apps/catalog/static/css/product_card.css` — corrected the stale base `.sec-head`/
  `.sec-head h2`/`.sec-head h2 .bar` rule in place (margin-bottom 18px→9px, h2
  font-weight 900→800 and gap 9px→6px, bar width/height/radius/color corrected, violet
  gradient→`#111`), and added the previously entirely-missing `.sec-head .more`/`.sec-
  head .more svg`/`.sec-head .btn,.product-section .sec-head .btn` base rules — all
  matching home.css's own current merged-final values, verified against the same
  real-browser ground-truth harness technique used throughout Task 5.
- `apps/storefront_builder/static/css/storefront_builder.css` — added `.category-circle-
  section .sec-head{margin-bottom:6px}` to the existing Group C2 block.

### Browser GREEN (1440×900 / 768×1024 / 390×844)

Fresh fixtures: 1 active `Product` + a `newest_products` section on Cart (representative
family #1, generic shared baseline, no nested override); 3 `Category` rows + a
`category_grid` section with `display_mode: "circular"` **and an explicit `title`**
(required — `category_grid.html` only renders its `.sec-head` div when a title is set,
default is empty, which is exactly why this gap was silent in Group C2's own
browser-GREEN proof) on Listing (representative family #2, the nested override).

| Selector | 1440×900 | 768×1024 | 390×844 |
|---|---|---|---|
| Cart `.sec-head` margin-bottom | `9px` | `9px` | `9px` |
| Cart `.sec-head h2` font-weight | `800` | `800` | `800` |
| Cart `.sec-head h2 .bar` width/height/color | `3px`/`17px`/`rgb(17,17,17)` | — | — |
| Listing `.category-circle-section .sec-head` margin-bottom | `6px` | `6px` | `6px` |

All values match home.css's own merged-final result exactly, at every viewport. Zero
console/page errors. Home itself re-verified: `curl` 200 OK on `/`.

### Home-unaffected proof (before writing the fix)

Before writing any CSS, a real-browser harness using Home's ACTUAL load order
(`product_card.css` then `home.css`, matching `home.html` exactly) was probed for
`.sec-head`/`.sec-head h2`/`.sec-head h2 .bar`/`.sec-head .more`/`.sec-head .more svg`
and the nested `.category-circle-section .sec-head` override, BOTH with the stashed
(pre-fix) `product_card.css` and with the fix applied. Every single computed value was
byte-identical in both runs (`marginBottom:9px`/`6px`, `fontWeight:800`,
`fontSize:16px`, bar `3px`/`17px`/`#111`, `.more` `10.5px`/`#333`, svg `16x16`) —
mathematically expected (home.css's later, equal-specificity rules already override
every property this fix touches) and now empirically confirmed, not merely assumed.

### Cleanup

Dev server stopped and verified via `ps aux` (no lingering process). DB restored via `cp`
from the `post_c1_cleanup_baseline.sqlite3` continuation baseline
(`9fe52ff5e97de6359c70c9bd3fdd3fd5344190a93252fb6f93bf41b2ee063c4d`) and hash-verified
equal.

### Permanent regression guard

`SecHeadSharedBaselineNonHomeCssTests`: 2 markup-rendering tests (`newest_products` on
Cart, Home-unaffected) + 1 full-declaration CSS-content test for `product_card.css`'s
corrected/added rules (including explicit `assertNotIn` guards for every stale pre-fix
value, and an explicit comment/assertion documenting why `font-size` is deliberately
excluded) + 1 CSS-content test for the new `storefront_builder.css` nested override.

### Verification

Full sweep — `test_phase4_task5_cross_page_css` (28 tests, all pass) plus
`test_qa_harness_contract`, `test_r4_settings_schema`, `test_section_registry`,
`test_render_service`, `test_r4_mutation_api`, and **`test_appearance`** (added to this
sweep specifically since this fix touches `.sec-head h2`'s font-weight/gap on the same
selector `--sfb-heading-size` theming tests exercise, to catch any interaction) —
**581 tests, OK (1 pre-existing skip)**. `manage.py check`: 0 issues. `manage.py
makemigrations --check --dry-run`: no changes detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. `git status` before commit contains only
the intended C2.5 production/test/evidence files.

### Independent review (commit `c5c884b`)

Isolated-worktree review independently re-derived every merged-final value from home.css
by its own exhaustive grep (not trusting cited line/count numbers — correctly catching
this doc's "43 lines" transcription error, fixed above), confirmed the load-order
mechanism and byte-for-byte-copy root cause from source, and built its OWN independent
real-browser harness matching Home's exact load order — deliberately stress-tested with
non-default `--brand-primary`/`--sfb-heading-size` values (beyond what this fix's own
harness described) to rule out variable-dependent divergence, confirming ZERO computed-
style differences before/after the fix for every touched selector. Also independently
confirmed both judgment calls (excluding `font-size`, including the `.bar` color change)
are supported by home.css's own cascade history, not post-hoc rationalization, and
verified RED honestly reproduces (reverting just this commit's CSS hunks fails exactly
the 2 CSS-content tests, not the 2 markup tests). **PASS — 0 CRITICAL, 0 IMPORTANT, 2
MINOR** (the "43 lines" doc transcription error above, and an "already-tested" claim
narrowed above to precisely what `test_appearance.py` actually covers — the live
variable-pipeline mechanism, not `.sec-head h2`'s computed style specifically). Both
addressed with documentation-only corrections; no code or test change required, no
re-review needed for MINOR-only findings per the process mandate.

## Group C2 (and its C2.5 addendum) — closed (0 unresolved CRITICAL / 0 unresolved
IMPORTANT across both the original Group C2 review and this root-cause follow-up).
Proceeding to Group C3 (`image_strip`).

## Group C3 — `category_grid`'s `image_strip` display mode

### Investigation

Markup (`category_grid.html`, `image_strip` branch): `<section class="section
category-image-strip-section">` → `<div class="category-image-strip">` → `<a
class="category-image-tile">` → `<span class="category-image-media">` (with a `<span
class="category-image-fallback">` icon fallback) → `<span class="category-image-label">`.

Exhaustive whole-file grep of home.css found TWO passes: "V4.1 reference polish — visual
category strip" (base, plus its own `@1000px`/`@680px` blocks) and a later, unlabeled
pass under the "Phase 3.7 — top-of-page professional composition" header (unconditioned,
plus its own separate `@680px` block touching only `.category-image-strip`'s `gap`).

Manual cascade tracing surfaced the same class of "later unconditioned rule shadows an
earlier breakpoint-scoped rule" pattern found in Group C2: the "Phase 3.7" pass's
unconditioned `.category-image-media{height:106px}` and `.category-image-label{font-
size:10.5px}` are textually AFTER the V4.1 pass's own `@1000px`/`@680px` overrides for
those same properties (98px/78px height; 8.5px font-size) — predicting those responsive
transitions never actually occur.

### Ground-truth verification (before writing any fix)

A standalone HTML harness loading home.css alone with the exact `image_strip` markup was
opened in a real browser at 1440×900, 900×800, and 390×844. Results confirmed the
prediction: `.category-image-media`'s `height` is `106px` at ALL THREE viewports (never
98px or 78px), and `.category-image-label`'s `font-size` is `10.5px` at all three (never
8.5px) — both V4.1 responsive overrides are dead code, fully shadowed by the later "Phase
3.7" pass. `.category-image-tile`'s own `flex-basis` responsive values (untouched by
"Phase 3.7") were confirmed genuinely live (126px at 900px, 96px at 390px), as was "Phase
3.7"'s own separate `@680px` `.category-image-strip{gap:12px}` override.

`.category-image-strip-section .sec-head{margin-bottom:4px}` (home.css:676) is mirrored,
matching the Group C2.5 pattern for nested title-heading overrides.

**A wrong initial assumption, caught by the tests themselves**: `.rcontainer:has
(.category-image-strip-section){margin-bottom:5px}` (home.css:884) was first assumed to
be inert on the 5 public non-Home envelopes, on the theory that `.rcontainer` belonged
only to a separate Container/Cell preview/editor rendering path. Running the new
`test_image_strip_renders_on_cart` markup test immediately disproved this — the real Cart
page HTML genuinely wraps every section in `.rcontainer`/`.rcontainer-cell`/`.rsec` divs.
Corrected before writing the final CSS: `.rcontainer`'s own base rule (`margin:0`) already
exists in `storefront_builder.css` from earlier work (confirmed: `home_visual.html`, the
"universal shell" Home variant, loads `product_card.css` → `home.css` →
`storefront_builder.css`, so home.css's higher-specificity `:has()` override already wins
there via specificity regardless of load order) — only the one narrow, genuinely
family-specific `:has()` margin exception needed adding here, which was verified via a
real browser to be entirely absent (`marginBottom:"0px"`) before the fix.

### Browser RED

With the CSS stashed, `CategoryGridImageStripNonHomeCssTests.
test_storefront_builder_css_carries_the_merged_final_image_strip_rules` failed on its
first assertion, while the 3 markup/Home-unaffected tests passed unaffected, as expected.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block (see the
Group C3 comment) with the merged-final desktop rules for `.category-image-strip-
section`/`.category-image-strip-section .sec-head`/`.rcontainer:has(.category-image-
strip-section)`/`.category-image-strip`/`.category-image-tile`/`.category-image-media`(+
`img`)/`.category-image-fallback`/`.category-image-label`/hover state, one
`@media(max-width:1000px)` block (`.category-image-strip`/`.category-image-tile`), and
one `@media(max-width:680px)` block (`.category-image-tile`/`.category-image-strip`) —
deliberately omitting the two now-proven-dead V4.1-pass responsive overrides.

### Browser GREEN (1440 / 768 / 390)

Fresh fixture: 3 `Category` rows, one `category_grid` section with `display_mode:
"image_strip"` and explicit `category_ids` on Cart.

| Property | 1440×900 | 768×1024 | 390×844 |
|---|---|---|---|
| `.category-image-strip` display/gap | `grid` / `14px` | `flex`, `overflowX:auto` | `gap:12px` |
| `.category-image-tile` flex-basis | — | `126px` | `96px` |
| `.category-image-media` height | `106px` | `106px` | `106px` |
| `.category-image-label` font-size | `10.5px` | `10.5px` | `10.5px` |
| `.category-image-strip-section` margin | `8px 0px 7px` | — | — |
| `.rcontainer:has(.category-image-strip-section)` margin-bottom | `5px` | — | — |

All values match the standalone-harness ground truth exactly, including the confirmed
dead-responsive-code behavior for `.category-image-media`/`.category-image-label` (fully
constant across all three viewports) alongside `.category-image-tile`'s genuinely live
responsive transitions. Zero console/page errors at any viewport.

### Cleanup

Dev server stopped and verified via `ps aux` (no lingering process). DB restored via `cp`
from the `post_c1_cleanup_baseline.sqlite3` continuation baseline
(`9fe52ff5e97de6359c70c9bd3fdd3fd5344190a93252fb6f93bf41b2ee063c4d`) and hash-verified
equal.

### Permanent regression guard

`CategoryGridImageStripNonHomeCssTests`: 2 markup-rendering tests (Cart, Listing —
including an explicit `assertIn('class="rcontainer"', html)` proving the wrapper genuinely
renders, after the wrong initial assumption) + 1 Home-unaffected test + 1
full-declaration CSS-content test covering every selector/breakpoint this fix adds, with
explicit `assertNotIn` guards for the two dead V4.1-pass responsive declarations.

### Verification

Full sweep — `test_phase4_task5_cross_page_css` (32 tests, all pass) plus
`test_qa_harness_contract`, `test_r4_settings_schema`, `test_section_registry`,
`test_render_service`, `test_r4_mutation_api`, `test_appearance` — **585 tests, OK (1
pre-existing skip)**. `manage.py check`: 0 issues. `manage.py makemigrations --check
--dry-run`: no changes detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. `git status` before commit contains only
the intended C3 production/test/evidence files.

## Post-closure correction — a second, independent C2.5 review found 2 unresolved IMPORTANT findings

**Process note**: a second Claude Code session was working this same branch concurrently
with the review/Group-C3 work above, unaware of it (both sessions started from the same
continuation-guard instructions). That second session dispatched its own fresh isolated-
worktree reviewer against commit `c5c884b` *before* the "Independent review (commit
`c5c884b`)" verdict above was pushed, and it returned materially different, more severe
findings. Per the standing instruction to never discard verified work, both sessions'
results are preserved here in full, in the order they actually happened: Group C2/C2.5 was
closed and Group C3 completed above, and this section is a retroactive correction applied
after that closure, not a fix folded into C2.5 before C3 began. It does not touch or
conflict with Group C3's own selectors (`.category-image-strip-*`/`.rcontainer:has(...)`),
which remain exactly as committed above.

### Independent review, round 1 (commit `c5c884b`)

Fresh isolated-worktree review (no context carried over from the implementer). Independently
re-derived the entire `.sec-head` cascade via brace-depth-aware parsing of all 52
occurrences in home.css (not trusting indentation), cross-checked every property this
commit's `product_card.css` changes touch against that independent derivation, ran the full
regression sweep (confirmed exactly **581 tests, OK, skipped=1**), RED-verified by reverting
just the CSS with the tests kept, and did real-browser `getComputedStyle` verification of
Home pre-fix vs post-fix (byte-identical on every property) and Home vs non-Home post-fix
(converges everywhere except the one deliberately-excluded `h2` `font-size`).

**Verdict: CRITICAL 0, IMPORTANT 2, MINOR 4.** All 6 architecture questions answered yes/no
correctly and the commit's own actual CSS changes were confirmed correct, bounded, and
well-guarded — both IMPORTANT findings were about the evidence doc's investigation section
overreaching, not about the shipped fix being wrong:

1. **IMPORTANT** — the doc's claim (corrected above) that all card-style/pattern-background
   `.sec-head` overlays besides fashion_sale/luxury_dark were "already shared" was false;
   `beauty_retail`/`chocolate_retail`/`minimal` and every `.rsec[data-pattern]` rule existed
   only in home.css, a second real non-Home divergence in the same `.sec-head` family.
2. **IMPORTANT** — `product_card.css`'s new `.sec-head .btn` base rule matches home.css's
   DEFAULT-density merged value only; home.css also has a real, higher-specificity
   `html[data-sfb-density="compact"]` override for the identical selector
   (height/min-height 24px vs 23px, font-size 9.4px vs 10px) that was entirely missing here.
3. **MINOR** — the "43 lines" whole-file-grep count (corrected above to 52) undercounted,
   which is what let the density-scoped rules in finding 2 go uncategorized.
4. **MINOR** — `product_card.css`'s pre-existing fashion_sale comment still asserted the
   shared rule's "own default 18px margin" after this fix corrected that default to 9px.
5. **MINOR** — the test file's `assertNotIn` guarding against an @680px `h2` `font-size`
   override pinned an exact, artificially-indented multi-line string that would pass
   vacuously against this file's real minified formatting.
6. **MINOR** — the file header's `--sfb-heading-size` rationale overstated what
   `test_appearance.py` actually verifies (only that the custom property appears in HTML,
   never a rendered `font-size`) — a rationale-accuracy issue, not a wrong decision.

Per the same standard this project has already applied once to Group C2 itself (a false
claim masking a real, verified divergence is not accepted as closing the review chain by
documenting it as "known but deferred"), both IMPORTANT findings were treated as requiring
an actual root-cause fix, not a documentation-only correction, since the reviewer's own
real-browser measurements confirmed both were genuine, currently-shipping divergences in
the exact `.sec-head` family this fix already exists to reconcile — not a new, unrelated
feature area.

### Round-2 fix-up (this commit)

**Fix for IMPORTANT 1** — mirrored every missing `.sec-head`-family declaration found by
the reviewer, at its established shared-owner location (alongside each card style's other
existing rules in `product_card.css`, matching the fashion_sale/luxury_dark precedent):
- `.rsec[data-bg-mode="palette"]:has(.pcard.style-beauty_retail) .sec-head h2`/`.sec-head
  .btn`, plus `.product-section:has(.pcard.style-beauty_retail) .sec-head`/`h2`/`h2 .bar`
  (home.css:1110-1111,1116-1118).
- `.product-section:has(.pcard.style-chocolate_retail) .sec-head`/`h2`/`h2 .bar`
  (home.css:1308-1310).
- `.product-section:has(.pcard.style-minimal) .sec-head`/`h2`/`h2 .bar`
  (home.css:1375-1377).
- A brand-new `.rsec[data-pattern]>.section>.sec-head` block (base + `h2`/`h2 .bar`/`.btn`
  + one `@media(max-width:680px)` override + one `html[data-sfb-density="compact"]`
  override for `h2`) — this selector had NO rule anywhere in `product_card.css` before.
  Merged-final values were independently re-derived by hand from home.css's full occurrence
  list (home.css:563-565, 616-623, 706-707, 740-741, 755-756, 764) — the compact-density
  override is genuinely required as its own rule (not foldable into the `@680px` block)
  because it wins by SPECIFICITY over the plain `@680px` rule regardless of viewport, a
  subtlety a real-browser ground-truth harness (loading home.css alone, `data-sfb-density`
  toggled via `document.documentElement`) confirmed exactly at 1440×900/390×844 × default/
  compact density (4 combinations, all matching the hand-derivation) before being written
  into `product_card.css`, then re-confirmed producing byte-identical computed values when
  `product_card.css` is loaded standalone.

**Fix for IMPORTANT 2** — added the missing `html[data-sfb-density="compact"] .sec-head
.btn,html[data-sfb-density="compact"] .product-section .sec-head .btn{font-size:9.4px;
min-height:24px;height:24px}` rule to `product_card.css` (home.css:699-700), verified via
the same real-browser technique (home.css alone vs product_card.css alone, both densities)
to produce byte-identical `.btn` height/font-size.

**Fixes for MINOR 3-6**: corrected the "43 lines" count to 52 (above); reworded the
fashion_sale comment to state the corrected 9px shared default and note this card style has
no home.css counterpart to re-derive a value from; replaced the vacuous multi-line
`assertNotIn` with `assertNotRegex(css, r"(?m)^\.sec-head h2\{font-size:\d")` — a line-start
anchor that only forbids a BARE, non-`:has()`/non-`[data-...]`-scoped `.sec-head h2` rule
from using a literal numeric `font-size` (guarding the real regression: the
`--sfb-heading-size` variable being dropped or shadowed) without colliding with the
legitimate scoped companions added in this same fix (e.g. `:has(.pcard.style-
beauty_retail) .sec-head h2{font-size:15px}`) — this collision was caught by actually
re-running the suite after the substring-based version was first tried, not assumed safe;
reworded the file header's `--sfb-heading-size` rationale to state precisely what
`test_appearance.py` checks (HTML custom-property presence, not rendered font-size) and
that this makes the merchant setting already inert on Home while remaining the live
mechanism on non-Home.

### RED/GREEN verification (round-2 fix-up)

RED: with `git stash push -- apps/catalog/static/css/product_card.css` (test file changes
kept), the 3 new test methods
(`test_product_card_css_carries_the_compact_density_btn_override`,
`test_product_card_css_carries_the_patterned_rail_sec_head_baseline`,
`test_product_card_css_carries_the_missing_card_style_sec_head_companions`) failed on their
first assertions with the exact missing-declaration `AssertionError`; the pre-existing 4
tests in the same class passed unaffected. `git stash pop` restored the fix.

GREEN: `apps/storefront_builder/tests/test_phase4_task5_cross_page_css` — **31/31 pass**
(28 prior + 3 new). Same regression sweep as the original C2.5 commit (`test_phase4_
task5_cross_page_css` + `test_qa_harness_contract` + `test_r4_settings_schema` +
`test_section_registry` + `test_render_service` + `test_r4_mutation_api` +
`test_appearance`) — **584 tests, OK (1 pre-existing skip)**. `manage.py check`: 0 issues.
`manage.py makemigrations --check --dry-run`: no changes detected.

Real-browser ground truth (home.css alone vs product_card.css alone, both densities, two
viewports where relevant) confirmed byte-identical computed values for: the base compact
`.btn` override; the full `.rsec[data-pattern]>.section>.sec-head` family at
1440×900/390×844 × default/compact density (4 combinations); `beauty_retail` (including
its `data-bg-mode="palette"` variant); `chocolate_retail`; `minimal`. Home-unaffected proof
re-run via product_card.css-then-home.css (Home's real load order) for both the pattern
family and `beauty_retail`: both produce values identical to home.css loaded alone,
confirming home.css's own later, equal-specificity rules still win for every property this
fix-up touches — Home's rendering remains provably unaffected.

### DB baseline note (session continuation)

This fix-up's own work required no dev-DB fixture mutation (pure static-CSS + standalone
browser-harness verification, no Django views exercised beyond the existing `manage.py
test` suite, which uses its own ephemeral test database). Separately, at the start of this
continuation session, the container's dev `db.sqlite3` and the previously-recorded
`9fe52ff5...` continuation-baseline backup file were both confirmed absent (container
restart, not assumed to have survived). Per the standing DB-baseline instruction: verified
current DB logical cleanliness by running `manage.py migrate --no-input` from a fully empty
database (clean run, no errors; confirms the `akhlaghi` store via the `0002_create_
akhlaghi_store` data migration, and zero domains/layout-versions/pages/sections/categories/
products — a genuinely clean slate, cleaner than the old baseline which carried
accumulated fixture rows). Captured a durable file-copy backup at
`db_backups/task5_c2_5_continuation_baseline.sqlite3` (gitignored, not committed) and
recorded its SHA256 as the new Task-5 continuation baseline:
**`bde91d0a91caec058b229ff7a92be008df5cbc555af33875be817cff1e0e614e`**
— superseding the `9fe52ff5...` baseline (which is not claimed to still exist anywhere).
**All subsequent Task 5 groups (`image_strip`/Group C3 onward) must restore to this new
baseline, not `9fe52ff5...`.**

### STOP conditions checked (round-2 fix-up)

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. Every change is inside the `.sec-head`
family (or its own regression tests/evidence) already in this fix's declared scope — no
unrelated Phase-5 design change introduced. `git status` before commit contains only the
intended round-2 production/test/evidence files.

## Group C2.5 — now closed for real (0 unresolved CRITICAL / 0 unresolved IMPORTANT across
both reviews and this correction). Group C3 (`image_strip`, above) was already completed
and remains valid — its own selectors are disjoint from everything touched here. Proceeding
to Group C4.

## Group C3 — independent review (process gap closed)

Group C3 (`image_strip`, commit `8b4a99c`) was implemented, committed, and pushed without
ever going through its own isolated-worktree independent review — the session that did it
moved directly on to closing the Task-5 evidence for that group without dispatching one, a
process gap. This section is that missing gate, run after the fact, before Group C4 begins.

Fresh isolated-worktree reviewer, no context from the implementer. Independently
re-derived the whole-file home.css cascade for every `.category-image-*` selector (found a
THIRD pass beyond the two named in the commit — a density-scoped `.category-image-label`
rule at home.css:701, numerically a no-op here) and built its own real-browser harness
(home.css alone; home.css+storefront_builder.css matching the real published-Home stack
via `home_visual.html`; storefront_builder.css alone for non-Home) across ~50 computed
properties × 4 viewports — **0 differences** between published-Home and non-Home,
confirming the mirror is complete and Home is unaffected. Independently confirmed the
`.rcontainer` claim (base rule pre-exists, home.css override value correct, and
`.rcontainer`/`.rcontainer-cell`/`.rsec` genuinely wrap sections on the real non-Home
template chain — not just trusting the doc's account of the caught wrong assumption). Ran
the 4 new tests, RED-reproduced by reverting just this commit's CSS (fails on the expected
missing-declaration assertion), and ran the full 7-module regression sweep — exactly
**585 tests, OK (skipped=1)**, matching the commit's own claim. Also ran all 17 other test
modules touching `storefront_builder.css` as an extra check beyond what was asked: found
17 failures + 1 error, but confirmed they reproduce identically at the parent commit
(`d3bd5b6`) — pre-existing ready-template preset-version mismatches unrelated to CSS, not
introduced by C3.

**Verdict: CRITICAL 0, IMPORTANT 0, MINOR 4.** Two were addressed here (see below); two
were left as accepted, pre-existing patterns:

1. Addressed — the "TWO passes" investigation language undercounted a third, density-scoped
   pass (home.css:701) that happens to be a numeric no-op against the mirrored value here.
   `storefront_builder.css`'s Group C3 comment block now names it explicitly, per this
   file's own established density-exclusion precedent (`.sec-head`/`.tile-circle`), so a
   future group reusing this pass-inventory approach doesn't inherit the blind spot on a
   family where the density value does differ.
2. Addressed — the `@media(max-width:1000px)` mirror correctly omits the V4.1 pass's
   `padding-inline:3px` (also dead, shadowed by the later unconditioned `padding:2px 6px
   4px`, independently re-confirmed via a real-browser check: padding stays `2px 6px 4px`
   at 1440/900/390px) but had no `assertNotIn` guard for it and no comment justifying the
   omission alongside the height/font-size ones. Added both.
3. Not addressed (accepted, pre-existing) — `test_home_page_is_unaffected_since_it_never_
   loads_storefront_builder_css` is misnamed for the real published-Home route
   (`home_visual.html` does load `storefront_builder.css`, after `home.css`; only the
   legacy `catalog/home.html` file is checked). This exact name/scope pattern is used
   identically by 3 other test classes in this same file (Groups A1, C1, C2), so renaming
   it only here would be inconsistent rather than a real fix; a whole-file rename across
   all 4 occurrences is out of this single group's bounded scope. The reviewer separately
   confirmed via real browser that Group C3 itself produces zero computed-style
   differences on the actual published-Home stack, so this is a naming/coverage-scope
   defect in a pre-existing convention, not a live divergence.
4. Not addressed (accepted, pre-existing) — the `assertNotIn` guards match home.css's exact
   minified spelling and would not catch a reintroduction written in a different but
   equivalent formatting. This matches the guard style used identically throughout this
   entire test file; changing it only for Group C3 would be inconsistent, not a fix.

### Verification (Group C3 MINOR fix-up)

`test_phase4_task5_cross_page_css`: 35/35 pass. Same 7-module regression sweep: 588 tests,
OK (1 pre-existing skip — unchanged from before this fix-up, since it only added a comment
and one `assertNotIn` line). `manage.py check`: 0 issues. `manage.py makemigrations
--check --dry-run`: no changes detected.

## Group C3 — closed (0 unresolved CRITICAL / 0 unresolved IMPORTANT). Proceeding to
Group C4.

## Group C, remaining 6 modes — `fashion_flat`, `fashion_mosaic`, `beauty_icons`,
`chocolate_story`, `chocolate_badges`, `atelier_mosaic`

**Process note**: per a simplified execution instruction covering all remaining Task-5 CSS
work as one implementation batch, this and the following groups (D, E, `beauty_tabs`) are
implemented and evidenced together, with one combined verification and one combined
independent review at the end, rather than a separate review gate per group.

### Investigation

Markup for all 6 (`category_grid.html`): `fashion_flat` → `.category-fashion-rail-section`
→ `.category-fashion-rail` → `.category-fashion-tile` → `.category-fashion-media`(+
`.category-fashion-fallback`) → `.category-fashion-label`. `fashion_mosaic` →
`.category-fashion-mosaic-section` → `.category-fashion-mosaic` → `.category-mosaic-tile`
→ `.category-mosaic-heading`(+`.category-mosaic-chevron`) + `.category-mosaic-media`(+
`.category-mosaic-fallback`). `beauty_icons` → `.category-beauty-strip-section` →
`.beauty-section-title` (shared, already mirrored from Group A2) + `.category-beauty-strip`
→ `.category-beauty-tile` → `.category-beauty-media`(+`.category-beauty-fallback`) →
`.category-beauty-label`. `chocolate_story`/`chocolate_badges` → `.category-chocolate-
story-section`/`.category-chocolate-section`, sharing one `.chocolate-section-title` →
their own rail/grid → tile → media(+fallback) → label. `atelier_mosaic` →
`.category-atelier-section` → `.atelier-section-title` → `.category-atelier-mosaic` →
`.category-atelier-tile` → `.category-atelier-media`(+`.category-atelier-fallback`) +
`.category-atelier-shade` → `.category-atelier-label`.

Exhaustive whole-file grep of home.css for every one of these selector families (unlike
`circular`'s 4-pass or `image_strip`'s 2-pass cascade) found each is a single, unscattered
generation — confirmed no other occurrence anywhere else in the file for any of them. No
cascade merge needed; values mirrored verbatim from their one source block.
`.beauty-section-title` is the exact same shared heading class already mirrored in Group
A2 (`product_section` campaign_band) — not duplicated here. `.chocolate-section-title` is
shared by `chocolate_story`/`chocolate_badges` and written once.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block (see the
"remaining Group C" comment) with the merged (here: simply copied) rules for all 6 modes,
their `@860px`/`@1000px`/`@900px`/`@680px` breakpoints exactly as they appear in home.css.

### Ground-truth verification

A standalone real-browser harness (Playwright/Chromium) loaded home.css alone and
`storefront_builder.css` alone against each mode's exact markup at 1440/900/390px and
diffed every explicitly-set computed-style property (`display`, `gridTemplateColumns`,
`gap`, `width`/`height`, `fontSize`, `fontWeight`, `margin`, `padding`, `borderRadius`,
`color`, `backgroundColor`, etc.) — byte-identical for all 6 modes at every viewport (the
only differences found were each section's own auto/intrinsic `height`, which neither file
sets explicitly — an artifact of the two harnesses' unrelated global baseline CSS, not a
divergence in any rule this fix adds).

### Browser RED

With `apps/storefront_builder/static/css/storefront_builder.css` stashed,
`CategoryGridRemainingModesNonHomeCssTests`'s 5 CSS-content tests failed on their first
assertions with the exact missing-declaration error; the 6 markup-rendering tests and the
Home-unaffected test passed unaffected, as expected (exactly 5 failures out of 12 tests).
(Process note: the first pass at the markup tests forgot the `@override_settings
(ALLOWED_HOSTS=...)` class decorator every sibling test class in this file carries,
producing a `DisallowedHost` 400 unrelated to the CSS fix — caught immediately by running
the new class in isolation before RED-verifying, and fixed. A second pass then found 4
markup tests asserting the presence of `beauty-section-title`/`chocolate-section-title`/
`atelier-section-title` failing for an unrelated reason: like `.sec-head` itself (Group
C2.5's finding), these title elements only render when `category_grid_settings.title` is
set — the fixture helper now sets an explicit title, matching the established pattern.)

### Fix

`git stash pop` restored the CSS fix; full re-run confirmed 47/47 pass in
`test_phase4_task5_cross_page_css` (35 prior + 12 new).

### Browser GREEN (1440×900 / 768×1024 / 390×844), live dev server

Real Draft→Publish→Public flow: `beauty_icons` (with an explicit title) on Cart,
`atelier_mosaic` on Listing, against a `127.0.0.1`-hostname `StoreDomain` fixture (the real
dev-DB backup/restore discipline applied around this mutation, see below).

| Property | 1440×900 | 768×1024 | 390×844 |
|---|---|---|---|
| `.category-beauty-strip` display / grid-template-columns | `grid` / 6×170.66px | `grid` / 6×94px (`@1000px`) | `grid` / 6×78px (`@680px`) |
| `.category-beauty-media` width | `96px` | `80px` | `66px` |
| `.category-beauty-label` font-size | `12px` | `12px` | `10px` (`@680px`) |
| `.beauty-section-title` margin-bottom | `24px` | `24px` | `14px` (`@680px`) |
| `.category-atelier-mosaic` grid-template-columns | 4×279px | 3×226.66px (`@900px`) | 2×163.5px (`@680px`) |
| `.category-atelier-tile` aspect-ratio | `0.83/1` (constant) | `0.83/1` | `0.83/1` |
| `.category-atelier-label` font-size | `25.92px` (`clamp` vw-based) | `16px` (clamp floor) | `16px` (`@680px` explicit) |

All values match the standalone-harness ground truth exactly, confirming every documented
responsive breakpoint (`@1000px`/`@680px` for beauty_icons; `@900px`/`@680px` for
atelier_mosaic) is genuinely active. Zero console/page errors at any viewport.

### Cleanup

Dev server stopped (`pkill -f "runserver 127.0.0.1:8765"`, non-zero exit per the documented
Exit-144 hazard — verified via `ps aux` that no process actually remained, then re-ran the
`cp` restore since the first attempt inside the same aborted shell invocation had not taken
effect). DB restored via `cp` from `db_backups/task5_c2_5_continuation_baseline.sqlite3`
(`bde91d0a91caec058b229ff7a92be008df5cbc555af33875be817cff1e0e614e`) and hash-verified
equal.

### Permanent regression guard

`CategoryGridRemainingModesNonHomeCssTests` (12 tests): 6 markup-rendering tests (one per
mode, split across Cart/Listing) + 5 full-declaration CSS-content tests (one per mode,
`chocolate_story`/`chocolate_badges` share one since they share `.chocolate-section-title`)
+ 1 Home-unaffected test (asserts `home.html` never references any of these classes and
still renders 200).

### Verification

`test_phase4_task5_cross_page_css`: **47/47 pass** (35 prior + 12 new). Regression sweep
(`test_phase4_task5_cross_page_css` + `test_qa_harness_contract` + `test_r4_settings_schema`
+ `test_section_registry` + `test_render_service` + `test_r4_mutation_api` +
`test_appearance`): **600 tests, OK (1 pre-existing skip)**. `manage.py check`: 0 issues.
`manage.py makemigrations --check --dry-run`: no changes detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. No Phase-5 design expansion — every value
is copied verbatim from home.css's own existing, already-shipped rendering.

## Group C — closed (all 11 `category_grid` display modes now covered: `grid`/`carousel`
[C1], `circular` [C2/C2.5], `image_strip` [C3], and these final 6 — 0 unresolved CRITICAL /
0 unresolved IMPORTANT across every reviewed sub-group). Proceeding to Group D.

## Group D — `promo_cards` + `image_text` + `blog_posts`

### Investigation

`promo_cards.html` needs no new CSS at all: its markup (`<section class="section"><div
class="tiles">` → `.tile`/`.wm`/`h4`/`.btn`) is byte-for-byte identical to `category_grid`'s
`grid`/`carousel` modes, already mirrored from Group C1 — confirmed by direct template
comparison. `image_text` (`.cream`) is a single, unscattered home.css generation (base +
one `@1000px` block, confirmed via whole-file grep). `blog_posts` (`.blog-grid`/
`.blog-card`) has TWO unconditioned passes (home.css:199-210 base, home.css:365-372 a
later, unlabeled pass overriding a subset of properties) plus its own `@1000px`/`@680px`
blocks.

### Ground-truth verification

A real-browser harness (Playwright/Chromium) loaded `product_card.css`+home.css with the
exact `blog_posts` markup at 1440/900/390px and read every explicitly-set computed-style
property for `.blog-grid`/`.blog-card`(+`.th`/`.bd`/`.meta`/`.meta .cat`/`h4`/`.read`) —
confirmed every manually-derived merged-final value exactly, including the non-obvious
`h4`/`small` computed `line-height` pixel values (cross-checked against `font-size ×
line-height` arithmetic) and the `:hover` state.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block: `.cream`
family verbatim; `.blog-grid`/`.blog-card` family at merged-final per-property values
(later pass wins; properties the later pass never touches keep the base value) plus its
`@1000px`/`@680px` blocks.

### Browser RED

With the new block stashed, the 2 new CSS-content tests (`image_text`, `blog_posts`)
failed on their first assertions with the exact missing-declaration error; the 4 markup
tests (`promo_cards`/`image_text`/`blog_posts`/Home-unaffected) passed unaffected —
confirming `promo_cards` genuinely needs no CSS change (exactly 2 failures out of 6 tests).

### Permanent regression guard

`GroupDNonHomeCssTests` (6 tests): 3 markup-rendering tests (one per family) + 2
full-declaration CSS-content tests (`image_text`, `blog_posts` — with `assertNotIn` guards
against the superseded base-only `blog_posts` values) + 1 Home-unaffected test.

### Verification

`test_phase4_task5_cross_page_css`: **53/53 pass** (47 prior + 6 new). `manage.py check`:
0 issues. `manage.py makemigrations --check --dry-run`: no changes detected.

## Group E — `faq` + `testimonials` + `trust_features` + `video_section`

### Investigation

`faq`/`testimonials`/`video_section` (home.css's "checkpoint 12" block, lines 252-270) are
a single, unscattered generation — confirmed via whole-file grep, no other occurrence
anywhere else in the file. `trust_features` (`.features`/`.feat`) is the most
cascade-scattered family in this entire task — genuinely live on Home's own hardcoded
`home.html` template (unlike every `category_grid` mode, which is dead there) — 30
occurrences across 5 unconditioned passes plus density scoping:

1. Base pass (home.css:216-223, + its own `@1000px`/`@680px` block at 236/242).
2. "Universal dense storefront modules"-era unconditioned pass (home.css:302-307, + its own
   separate `@1000px`/`@680px` block at 375/385).
3. "V3 universal dense-marketplace fidelity pass" (home.css:542-545, unconditioned).
4. "Final vertical rhythm" pass (home.css:669, `.features` margin only).
5. "V4.2.2 readability calibration" (home.css:735-736, `.feat b`/`.feat small` font-size
   only, + its own `@680px` override at 763).
Plus `html[data-sfb-density]` compact/relaxed scoping at 217-218 for `.features` itself.

### Ground-truth verification (before writing any fix)

A real-browser harness (home.css alone, exact `trust_features` markup) at 1440/900/390px,
both default and compact density, confirmed every manually-derived merged-final value
exactly, including two non-obvious findings:

1. **The same "later unconditioned rule shadows an earlier breakpoint override" pattern
   found in Group C2/C3**: pass 2's own `@680px` block sets `.features{display:flex;
   overflow-x:auto;gap:8px}` — since this is textually AFTER pass 1's `@680px`
   `grid-template-columns:1fr` and pass 2's own `@1000px` `repeat(3,1fr)`, the element is
   no longer `display:grid` at all at ≤680px, making both of those `grid-template-columns`
   values dead (confirmed: the browser still computes a stale, inert `gridTemplateColumns`
   value at ≤680px, exactly like `.tile-circle`'s dead overrides in Group C2). Separately,
   pass 2's `@680px` `.feat{min-height:56px}` is ALSO dead — pass 3 (V3, unconditioned,
   textually AFTER pass 2's `@680px` block) sets `.feat{min-height:54px}` unconditionally,
   which wins at every viewport regardless of the `@680px` rule's specificity-tying
   media-query scope.
2. **A genuine (non-coincidental) compact-density divergence**: unlike every prior
   density-scoped rule found in this task (which turned out to be exact numeric no-ops,
   e.g. Group C2.5's pattern-background `.btn`), `.features`'s own
   `html[data-sfb-density="compact"]` gap/margin (10px / 18px 0) genuinely differs from
   default density's merged-final gap/margin (9px / 7px 0 8px) — confirmed via the same
   harness toggling `data-sfb-density` on `document.documentElement`. Mirrored per the
   Group C2.5 precedent (density is mirrored when a real gap is found, not reflexively
   excluded) rather than left out — `data-sfb-density` is set on every page via
   `templates/base.html`, so this is reachable on non-Home too.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block: the
`faq`/`testimonials`/`video_section` family verbatim, plus `.features`/`.feat`'s
merged-final values (display:grid/5-col/gap:9px/margin:7px 0 8px base; the one genuine
compact/relaxed density override; the one genuinely-live `@1000px` 3-col override; the one
genuinely-live `@680px` block for display/overflow-x/gap and `.feat`'s `flex`/`b`/`small`
font-size — deliberately omitting the two now-proven-dead `@680px`
grid-template-columns/min-height values from passes 1/2).

### Browser RED

With the new block stashed, the 2 new CSS-content tests failed on their first assertions
with the exact missing-declaration error; the 5 markup/Home-unaffected tests passed
unaffected (exactly 2 failures out of 7 tests). (Process note: an initial `assertNotIn`
guard against the dead `grid-template-columns:repeat(2,1fr)` value used an unscoped
substring that collided with an unrelated, pre-existing `.gf--promo .gf-promo-grid` rule
elsewhere in the file — caught immediately by re-running GREEN and seeing the false
failure; fixed by anchoring the guard to the full `.features{...}` selector.)

### Permanent regression guard

`GroupENonHomeCssTests` (7 tests): 4 markup-rendering tests (one per family) + 2
full-declaration CSS-content tests (with `assertNotIn` guards for both dead `@680px`
values, correctly scoped to avoid the false-positive above) + 1 Home-unaffected test.

### Verification

`test_phase4_task5_cross_page_css`: **60/60 pass** (53 prior + 7 new). `manage.py check`:
0 issues. `manage.py makemigrations --check --dry-run`: no changes detected.

## Plus: `brand_carousel`'s `beauty_tabs` display-mode cosmetic gap

### Investigation

`brand_carousel` is already Phase-3 CERTIFY-ONLY (its base `.brand-carousel`/`.brand-tile`/
`.brand-tile-name`/`.grid` rules already mirrored). Per the Task-0 plan's disposition table
(row 12: "`beauty_tabs` cosmetic CSS gap fixed alongside Task 5"), the `beauty_tabs`
display mode's own selectors
(`.brand-section--beauty-tabs`/`.beauty-brand-title`/`.brand-beauty-tabs`/`.brand-beauty-
tabs .brand-beauty-tab`/`.brand-beauty-tabs .brand-tile-name`) were never mirrored at all
— a single, unscattered home.css generation (confirmed via whole-file grep). The mode's
title div also carries `.beauty-section-title` (already mirrored, Group A2/beauty_icons
reuse) alongside the new `.beauty-brand-title`.

### Fix

`apps/storefront_builder/static/css/storefront_builder.css` — one new block mirroring the
5 selectors verbatim plus their `@680px` override.

### Browser RED

With the new block stashed, the 1 new CSS-content test failed on its first assertion with
the exact missing-declaration error; the markup/Home-unaffected tests passed unaffected
(exactly 1 failure out of 3 tests).

### Permanent regression guard

`BrandCarouselBeautyTabsNonHomeCssTests` (3 tests): 1 markup-rendering test (Cart, with a
real active `Brand`) + 1 full-declaration CSS-content test + 1 Home-unaffected test.

### Verification

`test_phase4_task5_cross_page_css`: **63/63 pass** (60 prior + 3 new). `manage.py check`:
0 issues. `manage.py makemigrations --check --dry-run`: no changes detected.

## Combined browser GREEN (1440×900 / 768×1024 / 390×844), live dev server — Groups D, E, `beauty_tabs`

Real Draft→Publish→Public flow against a `127.0.0.1`-hostname `StoreDomain` fixture:
`image_text`/`blog_posts`/`beauty_tabs` on Cart, `faq`/`testimonials`/`trust_features` on
Listing.

| Property | 1440×900 | 768×1024 | 390×844 |
|---|---|---|---|
| `.cream` grid-template-columns | 2×532px | 1×624px (`@1000px`) | 1×256px |
| `.blog-grid` grid-template-columns | 5×223.2px | 3×226.66px (`@1000px`) | 2×164px (`@680px`) |
| `.blog-card` border-radius | `7px` | `7px` | `7px` |
| `.brand-beauty-tabs` display | `flex` | `flex` | `flex` |
| `.brand-beauty-tab` min-height | `64px` | `64px` | `56px` (`@680px`) |
| `.testimonial-list` grid-template-columns | 3×377.3px | 2×344px (`@1000px`) | 1×336px (`@680px`) |
| `.features` display | `grid` | `grid` | `flex` (`@680px`, confirmed dead grid-cols leftover) |
| `.features` grid-template-columns | 5 cols | 3 cols (`@1000px`) | — (inert, `display:flex`) |
| `.feat` min-height | `54px` | `54px` | `54px` (confirmed the `@680px` 56px override is dead) |

All values match every ground-truth harness exactly, including both confirmed
dead-responsive-code predictions. Zero console/page errors at any viewport.

### Cleanup

Dev server stopped (`pkill -f "runserver 127.0.0.1:8765"`, non-zero exit per the documented
Exit-144 hazard; verified via `ps aux` that no process remained). DB restored via `cp` from
`db_backups/task5_c2_5_continuation_baseline.sqlite3`
(`bde91d0a91caec058b229ff7a92be008df5cbc555af33875be817cff1e0e614e`) and hash-verified
equal.

## Combined final regression sweep (Groups D, E, `beauty_tabs`)

`test_phase4_task5_cross_page_css` (63 tests) + `test_qa_harness_contract` +
`test_r4_settings_schema` + `test_section_registry` + `test_render_service` +
`test_r4_mutation_api` + `test_appearance`: **616 tests, OK (1 pre-existing skip)**.
`manage.py check`: 0 issues. `manage.py makemigrations --check --dry-run`: no changes
detected.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. No Phase-5 design expansion — every value
copied verbatim from home.css's own existing, already-shipped rendering. `git status`
before commit contains only the intended production/test/evidence files.

## Task 5 — ALL groups implemented (A, B, C, D, E, plus `beauty_tabs`). Per the simplified
execution instruction covering all remaining Task-5 CSS work as one batch, dispatching ONE
fresh isolated-worktree independent review covering Groups D, E, and `beauty_tabs`
together (Groups A/B/C were already independently reviewed and closed above). Required
verdict: CRITICAL 0, IMPORTANT 0 before Task 6 begins.

## Independent review (commit `79c53c6`) and round-2 fix-up

Fresh isolated-worktree reviewer, no context from the implementer. Independently
re-derived the whole-file home.css cascade for the two multi-pass families
(`trust_features`, `blog_posts`) via its own brace-tracked media-context map (not trusting
this doc's line numbers), built its own real-browser harness (home.css alone vs the new
`storefront_builder.css` block alone, full computed-style diff across 9 density/viewport
combinations) for every family in the batch, verified the `promo_cards` "no new CSS
needed" claim by direct template diff, RED-verified all new tests (parent's CSS + this
commit's tests → exactly the 10 expected missing-declaration failures, 0 unrelated
errors), and ran the full regression sweep (**616 tests, OK, skipped=1** — exact match)
plus `manage.py check`/`makemigrations --check --dry-run` (both clean). Confirmed the
diff is 258 insertions / 0 deletions of CSS+tests+doc only, and that every one of the 139
newly-added CSS declarations appears verbatim in home.css (no Phase-5 design invented).

**Verdict: CRITICAL 0, IMPORTANT 2, MINOR 4.** Both IMPORTANT findings were the *same
failure mode this batch's own methodology was built to catch* (a later, unconditioned
home.css rule shadowing an earlier one this commit mirrored) — missed specifically because
a per-selector whole-file grep cannot see shadowing that happens through a *different*
selector matching the *same* multi-class element:

1. **IMPORTANT** — `.brand-section--beauty-tabs{margin:19px 0 22px}` and `.beauty-brand-
   title{margin-bottom:16px}` (the `beauty_tabs` title div carries BOTH
   `beauty-section-title` and `beauty-brand-title`, and the section itself carries BOTH
   `section` and `brand-section--beauty-tabs`) are dead code on Home: the generic,
   textually-LATER `.section{margin:14px 0}` (home.css:514) and the already-mirrored,
   textually-LATER `.beauty-section-title{margin-bottom:24px}`/`{margin-bottom:14px}`
   (home.css:1067/1093) win at every viewport. Mirroring the dead values gave this ONE
   element active margins Home never renders — a genuine regression, not merely a missed
   opportunity.
2. **IMPORTANT** — the `@680px` block's `.features{...gap:8px}` is ALSO dead code, missed
   despite the very same block's `grid-template-columns`/`.feat` `min-height` dead values
   (correctly caught) sharing the identical root cause: home.css's later, unconditioned V3
   pass (`.features{gap:9px;...}`, home.css:542) wins at every viewport, including ≤680px.

Both fixed by REMOVING the dead declarations (not inventing replacement values):
`.brand-section--beauty-tabs`/`.beauty-brand-title` margins are gone entirely (the
already-mirrored `.beauty-section-title` and the *separate*, pre-existing `.section`
base-margin gap — see MINOR below — now correctly govern this element exactly as they do
on Home); `.features`'s `@680px` block keeps `display:flex;overflow-x:auto` but drops
`gap`, since the base rule's `gap:9px` already applies unconditionally.

**MINOR (2 addressed, 2 recorded for Task 6):**

- Addressed — `html[data-sfb-density="compact"] .feat b{font-size:11px}`/`.feat
  small{font-size:9.5px}` were missing: home.css:751-752 (specificity 0-2-2) outrank the
  plain `@680px` rule (home.css:763, 0-1-1), so Home renders 11px/9.5px under compact
  density at ≤680px, not 10.8px/9.4px. `compact` is a real, shipped merchant density
  (`appearance_registry.DENSITY_CHOICES`), reachable on non-Home via
  `templates/base.html:4`. Added.
- Addressed — `test_promo_cards_renders_on_cart_reusing_group_c1_tiles_css` asserted
  markup only, never the `.tiles`/`.tile .wm`/`.tile h4`/`.tile .btn` CSS declarations
  themselves, leaving the "no new CSS needed" claim unguarded within this test class (it
  was indirectly covered by `CategoryGridTilesNonHomeCssTests`, so risk was low, but the
  guard belongs where the claim is made). Added.
- **Recorded, not fixed (out of this batch's bounded scope, per the reviewer's own
  recommendation)**: `storefront_builder.css` has no `.section{margin}` base rule at all
  (home.css's own real merged-final value, after its 4-pass cascade — 34px→22px→16px
  `@680px` (dead)→14px unconditioned, wins — is `margin:14px 0` at every viewport) and no
  `html[data-sfb-density=...] .section` rules either. This is a **pre-existing, cross-
  cutting gap affecting every section mirrored across the ENTIRE Task 5 effort** (Groups
  A-E, not just `beauty_tabs`), not something this batch introduced or should patch
  narrowly for one family. **Flagged here explicitly so Task 6 does not re-discover it as
  a "new" defect** — a dedicated fix (mirroring `.section`'s real merged-final base
  contract once, at whatever file already owns the shared `.section` wrapper concept,
  matching the Group C2.5 precedent for `.sec-head`) is recommended before/during Task 6,
  scoped as its own bounded change.
- **Recorded (methodology note)**: a per-selector whole-file grep is structurally unable
  to detect shadowing that happens via a *different* class on the same multi-class
  element, or via a shared wrapper class. Future groups with multi-class elements (any
  section combining a family-specific class with a shared one, e.g. `.section`,
  `.sec-head`-family, `.beauty-section-title`) need a per-element cascade check (or a
  real-browser harness run at the whole-element level, not just per individual
  declaration) — not just a per-selector grep — before considering the investigation
  exhaustive.

### RED/GREEN verification (round-2 fix-up)

RED: checked out the reviewed commit's own (pre-fix) `apps/storefront_builder/static/css/
storefront_builder.css` with this fix-up's test changes kept — exactly the 2 tests guarding
the 2 IMPORTANT fixes (`BrandCarouselBeautyTabsNonHomeCssTests.
test_storefront_builder_css_carries_the_beauty_tabs_rules`,
`GroupENonHomeCssTests.test_storefront_builder_css_carries_the_merged_final_trust_features_rules`)
failed, both on the exact assertion guarding the fix (an `assertNotIn` catching the real
dead value; an `assertIn` for the corrected `@680px` block), 0 unrelated failures out of 16
tests in the 3 affected classes. Restored the fix.

(Process note: the first version of the `assertNotIn(".brand-section--beauty-tabs{margin",
css)` guard collided with this fix's OWN explanatory comment, which quoted that exact
substring — caught immediately by running the suite and seeing the guard fail against the
now-correct CSS; fixed by rewording the comment.)

GREEN: `test_phase4_task5_cross_page_css` **63/63 pass** (unchanged count — this fix-up
only corrects/adds declarations inside existing test methods and adds 2 new assertions to
`test_promo_cards_...`, no new test methods). Full 7-module regression sweep: **616 tests,
OK (1 pre-existing skip)** — unchanged. `manage.py check`: 0 issues. `manage.py
makemigrations --check --dry-run`: no changes detected. Real-browser re-verification
(home.css alone vs the corrected `storefront_builder.css` alone) confirmed byte-identical
computed values for the `beauty_tabs` title margin-bottom (24px/14px, both densities) and
`.features`/`.feat b`/`.feat small` at ≤680px under both default and compact density.

### STOP conditions checked

`main` = `973c1dc00bacb6f2f7d2604fa3880bb4d6250579` (unchanged). Start safety ref
`backup/rastisi6-phase4-start-20260908` = `969a9b411ca712928c2bf31416bdde2ee8aaabb5`
(unchanged). No destructive git operation used. Every change is a removal of a dead-code
mirror, an addition already fully specified by home.css, or a test fix — no unrelated
Phase-5 design change. `git status` before commit contains only the intended round-2
production/test/evidence files.

## Task 5 — closed (0 unresolved CRITICAL / 0 unresolved IMPORTANT across every group's
review, including this round-2 correction). One pre-existing, cross-cutting `.section`
base-margin gap is explicitly recorded above for Task 6's attention, not silently
forgotten. Proceeding to Task 6.
