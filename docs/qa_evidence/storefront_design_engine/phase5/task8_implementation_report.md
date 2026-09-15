# Phase 5 Task 8 — PDP Completion / Mobile Sticky Add-to-Cart (SATC) — Implementation Report

## Base checkpoint

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Certified base: `e1a1f0ac2e615729d5c684f36f357481041f1bb0` (official branch `feature/phase5-design-expansion`, HEAD = origin at start, clean tree).
- Implementation branch: `feature/phase5-task8-pdp-completion` (cut from the certified checkpoint).

## Classification

BOUNDED PDP HARDENING. The one missing production capability — mobile **Sticky Add-to-Cart (SATC)** — is implemented as **presentation only** inside the existing canonical purchase form. PDT and PDTX were reused and freshly regression-verified (not rebuilt). **No architecture escalation required.**

## What shipped

SATC is a mobile-only sticky purchase bar rendered by the canonical `product_main` section. It lives **inside the existing `variantSelector` Alpine scope**, so it reuses the SAME reactive purchase state as the in-flow CTA and submits the SAME canonical form.

1. **`product_main.html`**
   - The canonical purchase `<form>` now carries a deterministic, product-pk-namespaced id: `id="pdp-buy-form-{{ product.pk }}"`.
   - A new mobile-only `.pdp-satc` region (sibling of `.pinfo`, still inside the `.pdp` `x-data="variantSelector(...)"` root) shows the current price (via the existing `displayPrice` getter + existing `formatToman()`), and a submit button that targets the canonical form via `form="pdp-buy-form-<pk>"`.
   - The sticky button's `:disabled` and label bind to the SAME getters as the in-flow CTA (`canAddToCart`, `needsSelection`, `displayStock`).
   - **No** new Alpine component, **no** quantity control, **no** second form, **no** new variant/stock/price calculation. `x-cloak` hides it until Alpine boots; CSS keeps it hidden with no JS (the in-flow form still works).

2. **`storefront_builder.css`** (canonical mobile bottom-nav owner)
   - Added one presentation-only geometry token: `:root{--gmn-clearance:calc(88px + env(safe-area-inset-bottom,0px))}`. It expresses, once, the clearance any bottom-anchored mobile surface must sit above so it never collides with the bottom nav. No application state, no new owner.

3. **`product_detail.css`**
   - `.pdp-satc` styles: `display:none` by default; shown only at `@media(max-width:680px)`; `position:fixed; z-index:90; inset-inline:0; bottom:var(--gmn-clearance, <safe-area fallback>)`; safe-area aware; hidden on desktop.

4. **`tools/storefront_builder_qa/public_task8_qa.mjs`** — new Task-8 browser QA runner (same harness/approach as the Task-5 runner).

## Production files changed

- `apps/storefront_builder/templates/storefront_builder/sections/product_main.html`
- `apps/catalog/static/css/product_detail.css`
- `apps/storefront_builder/static/css/storefront_builder.css`

## Test / tooling files changed (added)

- `apps/storefront_builder/tests/test_views.py` — 6 new SATC architecture tests + a `_one_product_main()` fixture helper.
- `tools/storefront_builder_qa/public_task8_qa.mjs` — Task-8 browser QA runner.
- `docs/qa_evidence/storefront_design_engine/phase5/task8_browser_qa/` — report.json + screenshots.

## RED evidence

New SATC tests, run before implementation: **6 failures** (all the new SATC tests), while the existing PDT/section tests in the same class continued to pass:

- `test_satc_rendered_by_canonical_product_main`
- `test_satc_submits_the_same_canonical_form_no_second_form`
- `test_satc_has_no_second_quantity_owner`
- `test_satc_reuses_canonical_purchasability_state_no_second_calc`
- `test_satc_is_mobile_only_and_below_overlays_in_css`
- `test_bottom_nav_owner_exposes_presentation_clearance_token`

(RED was genuine — SATC markup/CSS/token did not exist. No working production code was broken to fake it.)

## GREEN evidence

After implementation: `ProductDetailContextAwareSectionsPreviewTests` — **24 tests OK** (18 pre-existing PDT/section + 6 SATC + the strengthened normal-CTA test).

## Regression results

All run with `python manage.py test --settings=shop_core.settings` (SQLite, Python 3.12):

- Focused + PDP regression (SATC + PDT + PDTX + U6 product types + variant service + product detail view + quick view + cart views + cart security + gift wrap): **161 tests OK**.
- Broader regression (render_service + section_registry + a8_ready_template_contracts + a8_component_coverage + phase2_universal_renderer + qa_harness_contract): **408 tests OK** (1 skipped).

## Browser QA results

Runner: `tools/storefront_builder_qa/public_task8_qa.mjs` (playwright-core + chromium), against the real seeded published tenant `rastisi-fashion-test` (100 products), RTL. Primary viewport **390×844**, narrow **360×800**, plus **1440×900** for the desktop-absence check. Evidence: `task8_browser_qa/report.json` + screenshots.

Result: **35 PASS / 0 FAIL / 0 WARN** on an in-stock product with the `five_item` (edge-to-edge) bottom nav; re-verified on the `floating_dock` (offset) nav; and on a sold-out product.

Verified in the live browser:

1. Normal in-flow PDP Add-to-Cart present and functional (desktop + mobile).
2. SATC visible on mobile (390 and 360).
3. SATC NOT a sticky bar on desktop (present in DOM, not visible).
4. Change main quantity to 3 → the single `name="quantity"` input reads 3 (SATC submits that same value).
5. Variant/stock/selection state: SATC label + disabled state AGREE with the canonical CTA (verified for sold-out "ناموجود" disabled, and in-stock "افزودن به سبد خرید" enabled).
6. Exactly ONE `cart:add` form and ONE quantity owner on the page.
7. SATC does not overlap the bottom nav — SATC bottom edge sits above the nav top edge on BOTH `five_item` (bottom 756 vs nav top 774 @390) and `floating_dock` (bottom 756 vs nav top 765 @390).
8. SATC works when the bottom nav is absent (token fallback keeps it clear of the safe area) and across nav variants (token-driven, no per-variant offset).
9. Safe-area spacing honored (`env(safe-area-inset-bottom)` in both the nav token and SATC fallback).
10. Mobile nav drawer covers SATC: drawer z-index 120 / backdrop 110 > SATC z-index 90.
11. SATC z-index 90 < login modal (100), drawer (110/120), quick view (1000/1001) → overlays cover it.
12. PDT: 3 tabs / 3 panels, no 390px horizontal overflow (`scrollWidth == clientWidth`).
13. PDTX: exactly one trust surface renders (fallback guarantee strip here).
14. Page scrolls to the normal purchase controls; no content permanently obscured.
15. End-to-end: clicking SATC after setting quantity=2 incremented the header cart count ۰ → ۲ and showed a success toast (real canonical `cart:add`, OOB count update + HX-Trigger toast).

## Bottom Navigation variants tested

Seven variants are registered (`bottom_nav.{four_item,five_item,raised_cart,floating_dock,glass_dock,minimal_icons,wide_cart}.v1`) plus `hidden` and a luxury floating cart — all rendered by ONE shared renderer (`_navigation.html`), differing only by the `gmn--<identity>` CSS class (one navigation engine, multiple presentations). SATC compatibility was browser-verified against **`five_item`** (edge-to-edge, the tightest collision case) and **`floating_dock`** (largest floating inset), and against the **absent** case. Because SATC derives its offset from the single canonical `--gmn-clearance` token (never per-variant/per-template offsets), the remaining presentations inherit the same clearance. **Note:** the currently seeded golden reference publishes `bottom_nav.hidden.v1` by default; the visual variety of bottom navigations is a separate design concern and was not expanded here (Task 8 scope is SATC compatibility with the canonical multi-style architecture, which is satisfied).

## PDT result

REUSE AS-IS. Fresh browser QA confirms 3 accessible tabs / 3 panels and no 390px overflow. No production PDT change in Task 8.

## PDTX result

REUSE AS-IS. One trust surface renders (canonical `trust_features` when present, else the backward-compatible guarantee fallback). PDTX owner/tests untouched and green.

## Physical vs digital product result

The existing `requires_shipping` gating (U6) is untouched; SATC introduces no shipping/stock copy of its own — its label mirrors the canonical CTA. `test_u6_pdp_product_types` remains green.

## Variant / stock / quantity result

- Variant: SATC reflects the canonical `current`/`needsSelection` (no second availability calc).
- Stock/sold-out: SATC disabled + "ناموجود", agreeing with the CTA (browser-verified).
- Quantity: ONE submitted owner; SATC submits the existing stepper value (browser-verified qty=3 and E2E qty=2 add).

## Overlay / drawer result

SATC (z-index 90) sits below all canonical page-covering overlays; the mobile nav drawer (120/backdrop 110) covers it. No new global overlay-state system was introduced (the canonical `sfbOverlay` primitive and stacking order are reused).

## Django check

`python manage.py check` → **System check identified no issues (0 silenced).**

## Migration check

`python manage.py makemigrations --check --dry-run` → **No changes detected.** Zero migrations.

## Git diff check

`git diff --check` → clean (no whitespace errors / conflict markers).

## Architecture audit — ONE CONCEPT = ONE CANONICAL OWNER

| Potential violation | Introduced? |
|---|---|
| Duplicate cart form | **NO** (one `hx-post` cart:add form; SATC uses HTML `form=`) |
| Duplicate quantity owner | **NO** (one `name="quantity"`; browser-verified count = 1) |
| Duplicate variant state | **NO** (reads existing `variantSelector` getters; no `x-data` in the SATC block) |
| Duplicate pricing state | **NO** (reuses `displayPrice` + `formatToman()`) |
| Duplicate stock state | **NO** (reuses `displayStock` / `canAddToCart`) |
| Duplicate trust state | **NO** (trust untouched) |
| Duplicate bottom-nav logic | **NO** (consumes `--gmn-clearance` token; nav renderer untouched) |
| Per-template PDP patching | **NO** (one shared `product_main.html`; no recipe edits) |
| New parallel renderer | **NO** |
| New persistence model / migration | **NO** |

Production diff footprint: 3 production files (+218/−2 lines total across all 4 tracked files), matching the expected surface.

TASK 8 IMPLEMENTATION COMPLETE: YES
TASK 8 ARCHITECTURE ESCALATION REQUIRED: NO
PR MERGED: NO



---

# Task 8 — Independent Review Repair Gate (addendum)

The first pass opened PR #5 with CRITICAL: 0, IMPORTANT: 3. All three IMPORTANT findings are now repaired on the same branch. PR #5 remains **unmerged**.

## IMPORTANT 1 — Canonical per-variant nav geometry (PASS)

The clearance is no longer a single global constant. `--gmn-clearance` is now owned and published by the canonical mobile bottom-nav CSS owner (`storefront_builder.css`) as ONE geometry source that distinguishes every active nav presentation and the absent case:

- `:root{--gmn-clearance:0px}` — default when NO bottom nav renders (SATC then hugs the safe area; it does not float ~88px up).
- Per active variant, keyed off the nav's own identity class via `:has()` on a common ancestor (the nav and SATC are cousins under the shell, so a plain custom-property cascade cannot reach SATC; `:has()` is an established pattern already used in this repo's `home.css`):
  - `:root:has(.gmn)` → `114px` (default / **luxury** floating cart — covers the raised orb crown)
  - `:root:has(.gmn--four_item)` → `84px`
  - `:root:has(.gmn--five_item)` → `78px` (edge-to-edge; matches the nav's own `.gmn-spacer--five_item`)
  - `:root:has(.gmn--raised_cart)` → `114px` (**covers the upward-extending cart orb**, per the review's specific warning)
  - `:root:has(.gmn--floating_dock)` → `88px`
  - `:root:has(.gmn--glass_dock)` → `94px`
  - `:root:has(.gmn--minimal_icons)` → `82px` (matches `.gmn-spacer--minimal_icons`)
  - `:root:has(.gmn--wide_cart)` → `86px`
  - all `+ env(safe-area-inset-bottom)`.

SATC consumes `var(--gmn-clearance, env(safe-area-inset-bottom,0px))`. No per-template offsets; no second geometry authority; no Ready Template edits. Values were tuned against real measured browser geometry (the raised-orb variants were corrected from 94/100 to 114 after QA measured the orb crown).

## IMPORTANT 2 — All-variant browser QA (PASS)

Fresh browser QA (playwright-core + chromium, real published tenant `rastisi-fashion-test`, RTL) was run for **every** registered presentation plus the luxury floating cart and the hidden/absent case, at **390×844** and **360×800**, plus a desktop absence check. Each run republishes the nav variant through the canonical layout draft→publish path and reads the live storefront.

Result: **each of the 9 presentations PASS with 0 FAIL** (`four_item, five_item, raised_cart, floating_dock, glass_dock, minimal_icons, wide_cart, luxury_floating_cart, hidden`). Committed machine-readable evidence: `task8_browser_qa/report_<variant>.json` (9 files) + `pdp_<variant>_mobile-390.png` / `pdp_<variant>_mobile-360.png` (18 screenshots). Each report records, per variant and viewport, the actual geometry (SATC top/bottom, nav top/bottom, raised-orb top, identity, resolved clearance, z-index) and an explicit `satc:no-bottom-nav-overlap` PASS/FAIL. Measured examples at 390×844 (SATC bottom vs nav top / orb top):

| Variant | clearance | SATC bottom | nav top (orb top) | overlap |
|---|---|---|---|---|
| four_item | 84px | 760 | 771 | PASS |
| five_item | 78px | 766 | 774 | PASS |
| raised_cart | 114px | 730 | 737 (orb 738) | PASS |
| floating_dock | 88px | 756 | 765 | PASS |
| glass_dock | 94px | 750 | 762 | PASS |
| minimal_icons | 82px | 762 | 776 | PASS |
| wide_cart | 86px | 758 | 769 | PASS |
| luxury_floating_cart | 114px | 730 | 737 (orb 738) | PASS |
| hidden | 0px | 844 | — (hugs bottom, gap 0) | PASS |

The initial repair pass caught a **real** overlap on `raised_cart` and `luxury_floating_cart` (SATC bottom 750/744 vs orb top 738) — the QA's raised-orb-aware overlap check exposed it, and the clearance was corrected to 114px so SATC now clears the orb crown.

## IMPORTANT 3 — No permanent content obscuration (PASS)

`.pdp` reserves bottom space equal to `--gmn-clearance` + SATC's own height (`--satc-height`) + a small gap, and `html:has(.pdp-satc)` sets a matching `scroll-padding-bottom` — both derived from canonical geometry, not a random per-template value. The browser QA scrolls to maximum page scroll, captures bounding rectangles, and asserts the final PDP content (review form / tabs / trust strip) is reachable above the SATC top edge: `content:final-reachable-above-satc` is **PASS** on every variant at both viewports. Screenshots at max scroll are committed per variant.

## Design simplification (SATC now inside the canonical form)

The preferred approved design is restored: SATC now lives **physically inside** the one canonical `cart:add` `<form>` as a plain `type="submit"` button. Because it is `position:fixed` it is removed from normal flow, so its in-form DOM position does not disturb layout. The `form=` attribute and the deterministic `pdp-buy-form-<pk>` id were **removed** — the coupling is gone. Still: one form, one submitted `quantity` owner (the existing stepper), one `cart:add` pipeline, no second Alpine component. `test_satc_submits_the_same_canonical_form_no_second_form` now asserts the `.pdp-satc` block is inside the single cart:add form, uses no `form=` attribute, and that no `pdp-buy-form-` id exists.

## Post-repair verification

- Task 8 focused + PDP/cart/variant/PDT/PDTX: **162 tests OK** (added `test_clearance_is_per_variant_and_zero_when_nav_absent`).
- Broader regression (render_service, section_registry, a8 ready-template contracts, a8 component coverage, universal renderer, qa harness, **r4_store_appearance_rendering**): **424 OK** (1 skipped).
- `python manage.py check`: no issues. `makemigrations --check --dry-run`: No changes detected. `git diff --check`: clean.

## Files changed by the repair (same branch)

- `apps/storefront_builder/static/css/storefront_builder.css` — per-variant canonical `--gmn-clearance` (`:root` default 0 + `:has()` variant rules).
- `apps/catalog/static/css/product_detail.css` — SATC bottom from `--gmn-clearance`; `--satc-height`; `.pdp` bottom reserve + `scroll-padding-bottom` (no-obscuration).
- `apps/storefront_builder/templates/storefront_builder/sections/product_main.html` — SATC moved inside the canonical form; `form=`/id coupling removed.
- `apps/storefront_builder/tests/test_views.py` — updated/added SATC tests.
- `tools/storefront_builder_qa/public_task8_qa.mjs` — all-variant geometry + no-obscuration runner; `tools/storefront_builder_qa/_publish_nav.py` — dev-only QA nav publisher.
- `docs/qa_evidence/storefront_design_engine/phase5/task8_browser_qa/` — per-variant reports + screenshots (regenerated).

REPAIR — CRITICAL FIXES COMPLETED: YES (none were open; 3 IMPORTANT repaired)
IMPORTANT 1 — CANONICAL NAV GEOMETRY: PASS
IMPORTANT 2 — ALL NAV VARIANTS BROWSER QA: PASS
IMPORTANT 3 — NO CONTENT OBSCURATION: PASS
TASK 8 TESTS: PASS
REGRESSION: PASS
MIGRATIONS: 0
PR MERGED: NO



---

# Task 8 — Review Repair Round 2 (addendum)

Re-review of PR #5 accepted IMPORTANT-1/IMPORTANT-2 (per-variant geometry, hidden behavior, all-variant evidence, SATC inside the canonical form). It left **1 IMPORTANT** (invalid no-obscuration proof) + **1 MINOR** (duplicate `.gmn` rule). Both are now fixed on the same branch. PR #5 remains **unmerged**.

## IMPORTANT — no-content-obscuration proof made valid (PASS)

Three defects were behind the invalid proof; all fixed:

1. **The QA check was not identifying the real final content.** It looped a fixed selector list and overwrote `last` for whichever selector existed, so `.guarantee` (mid-page) could be chosen, and it only asserted `finalContent.top < satcTop` — which can pass even when the element is >1000px above the viewport. The runner (`public_task8_qa.mjs`) now:
   - identifies the **true final meaningful content by absolute document position** (max `rect.bottom + scrollY` across meaningful leaves in ALL PDP sections, filtering hidden/zero-size/giant-wrapper nodes, tagging it `data-qa-final`);
   - **scrolls that element** so its bottom sits ~24px above the SATC top edge (the reachable position a user gets to via the bottom reserve);
   - asserts **bottom ≤ satcTop AND bottom ≤ innerHeight AND on-screen** (`top < innerHeight`, `bottom > 0`) — i.e. genuinely visible and clear of SATC, not merely "top above satcTop" and not scrolled entirely offscreen.
   The check is renamed `content:final-visible-above-satc` and records the final element + geometry in the JSON.

2. **The reserve was on the wrong owner.** `product_main` (`.pdp`) is the FIRST PDP section, so reserving inside `.pdp` did not protect the sections that follow (`product_description`, `product_video`, `related_products`). The reserve now lives on the **whole-PDP content container** — `catalog/product_detail.html`'s wrapper, which gained a stable `pdp-page` class and holds every PDP section. It adds **real scrollable height** via `padding-bottom` (not just `scroll-padding-bottom`, which cannot add document height).

3. **The reserve was being overridden.** `base.css` `.wrap{padding:0 18px}` set `padding-bottom:0`; a `.pdp-page:has(.pdp-satc)` selector tied/lost on the cascade and computed `0px`. The rule is now `.wrap.pdp-page:has(.pdp-satc){padding-bottom:calc(var(--gmn-clearance,...) + var(--satc-height) + 16px)}` (specificity beats `.wrap`); verified computed `padding-bottom = 158px` at 390px on `five_item`. The value is derived entirely from the canonical `--gmn-clearance` + `--satc-height` — no per-template/random number.

**Evidence (max-scroll-then-scroll-to-final), true final element = last related-product `.pcard` at document bottom 2182:**

| Variant | viewport | final content bottom | SATC top | innerHeight | visible+clear |
|---|---|---|---|---|---|
| five_item | 390×844 | 673 | 697 | 844 | PASS |
| five_item | 360×800 | 629 | 653 | 800 | PASS |
| raised_cart | 390×844 | 637 | 661 | 844 | PASS |
| hidden | 390×844 | 751 | 775 | 844 | PASS |

The same `content:final-visible-above-satc` check is PASS for every one of the 9 presentations at both 390×844 and 360×800. Screenshots per variant are committed.

## MINOR — duplicate `.gmn` rule removed

`storefront_builder.css` had two identical consecutive `.gmn{...}` declarations (an artifact of the earlier edit). The duplicate is removed (now exactly one).

## Reverification (round 2)

- All-variant browser QA regenerated: 9/9 presentations 0 FAIL (`report_<variant>.json` + `pdp_<variant>_mobile-390/360.png`).
- Tests: **558** OK across focused/PDP + cart + render_service + section_registry + a8 ready-template contracts + r4 store-appearance rendering (1 skipped). Focused SATC class: 25 OK.
- `python manage.py check`: no issues. `makemigrations --check --dry-run`: No changes detected. `git diff --check`: clean.

## Files changed by round 2 (same branch)

- `apps/catalog/templates/catalog/product_detail.html` — `pdp-page` class on the whole-PDP content container.
- `apps/catalog/static/css/product_detail.css` — reserve moved to `.wrap.pdp-page:has(.pdp-satc)` (real height, correct owner, wins the cascade).
- `apps/storefront_builder/static/css/storefront_builder.css` — removed the duplicate `.gmn` rule.
- `apps/storefront_builder/tests/test_views.py` — updated the reserve-owner assertion.
- `tools/storefront_builder_qa/public_task8_qa.mjs` — valid, document-position-based no-obscuration proof.
- `docs/qa_evidence/storefront_design_engine/phase5/task8_browser_qa/` — regenerated per-variant reports + screenshots.

ROUND 2 — CRITICAL: 0
IMPORTANT: 0
MINOR: 0
NO-CONTENT-OBSCURATION PROOF: PASS
ALL NAV VARIANTS QA: PASS
TASK 8 TESTS: PASS
REGRESSION: PASS
MIGRATIONS: 0
PR MERGED: NO
