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
- Regression sweep: same suite set as prior groups — **486 tests, 0 failures, 1 known skip**.
- `python manage.py check`: clean. `makemigrations --check --dry-run`: no changes.
- Real dev DB restored and SHA256-stable at `d53a687b...`.

### STOP conditions checked

Pure CSS-completeness fix. No new template, section registration, schema, or renderer
path. The desktop-only LTR-direction mirror is an existing, permanent Home design decision
(not a new visual variant introduced by this task) — mirrored, not invented.

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
findings fixed), and once-reviewed on A3. Proceeding to Group B.
