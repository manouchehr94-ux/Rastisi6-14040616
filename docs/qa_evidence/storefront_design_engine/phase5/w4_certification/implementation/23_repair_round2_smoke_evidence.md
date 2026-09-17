# W4C Repair Round 2 — bounded browser smoke evidence (editorial_jewelry)

Section 10 of the round-2 directive: `--only editorial_jewelry` against a
fresh, empty, dedicated smoke root, after all round-2 GREEN code was
committed. Expected 12 Base + 1 Tier-1 Theme = 13 cells, 2 Node
invocations. Still NOT the 704-cell campaign.

## Attempt 1 — 13/13 recorded, 3 genuine FAILs (`21a_...txt`)

Run at HEAD `208100c0` (the round-2 GREEN implementation commit). Home,
Listing, Cart, Theme all PASS. PDP FAILed on all 3 viewports:
`variantTransition={"attempted":true,"changed":false,...}`.

Root cause: `w4cVariantTransitionCheck` tracked only the FIRST active
index across every `.opt-block .swatch, .opt-block .size` control
combined. The real fixture product (FSH-003) has two option axes -- رنگ
(color, a SINGLE value, trivially always "active") and سایز (size, 5
values) -- rendered as one color swatch followed by 5 size buttons. The
first active index was the color swatch (index 0); skipping only that
index and picking the next available one landed on index 1, which was
the SIZE axis's own already-selected value (the default variant's size).
Clicking an already-selected control changes nothing.

**Fixed** (`64dadb82`): track the full SET of active indices (one per
axis), pick a target outside that set. Added regression test `test_70b`.
Re-verified: 102/102 focused tests, fast gates clean.

## Attempt 2 — 13/13 recorded, 0 FAIL, but a real bug in the result
payload (`21b_...txt`)

Run at HEAD `208100c0eaf...` (actually the variant fix's own head --
see matrix for the exact `w4c_branch_head_sha`). All 13 cells PASS. On
inspection, `cart.accessibility_checks` was
`{"quantity_control":"n/a","remove_control":"n/a","checkout":"n/a"}` --
every one "n/a" despite the controls genuinely existing moments earlier.

Root cause: `w4cCartControlAccessibility` ran AFTER `w4cCartRealRemove`
had already emptied the (genuinely single-item) cart, so the controls
it inspected no longer existed by the time it ran.

**Fixed** (`5fedd509`): reordered to check accessibility BEFORE the
destructive remove step, matching the destructive-mutation-last pattern
already used elsewhere in this cell and in the PDP cell's own real
Add-to-Cart. Added regression test `test_84b`. Re-verified: 102/102
focused tests (one more than attempt 1's re-check, this new test),
fast gates clean.

## Attempt 3 — final, 13/13 PASS, 0 FAIL, 0 BLOCKED (`21c_...txt`)

```
W4C BATCH COMPLETE -- CAMPAIGN INCOMPLETE -- selected_keys=editorial_jewelry,
cells_recorded_this_run=13, cumulative_total_cells_recorded=13/704,
cumulative_missing=691, cumulative_fail_count=0, cumulative_blocked_count=0
Local database restored — pre=<sha256> post=<sha256> match=True
```

Full final matrix (`22_repair_round2_smoke_final_matrix.json`):

- **Home**: PASS/PASS/PASS (desktop/tablet/mobile), Home Desktop+Mobile
  screenshots staged under `screenshots/home/`.
- **Listing**: PASS/PASS/PASS. `listing_controls`: sort present and one
  bounded interaction performed (`interacted: true`, URL gained
  `?sort=`), category filter present, pagination present with a
  labelled `<nav>` and 1 numeric link (the fixture catalog only produces
  one page for this Template's category scope -- recorded honestly, not
  invented). Desktop representative screenshot staged.
  `accessibility_checks`: `search_input`/`product_card`/`quick_view`
  PASS; `sort_control`/`category_filter` **FAIL** (recorded, not
  gating -- see finding below).
- **PDP**: PASS/PASS/PASS. `variant_transition` genuinely changed
  (`activeIndices [0,1] -> [0,2]`, sku
  `FSH-003-آبی-روشن-39 -> -40`); `real_add_to_cart` genuinely changed
  (`#cart-count` `۰ -> ۲`, reflecting the quantity bump performed
  earlier in the same cell); `real_navigation` resolved (`href: "/"`,
  200). Desktop representative screenshot staged.
  `accessibility_checks`: `quantity_control`/`add_to_cart` PASS;
  `variant_control` **FAIL** (recorded, not gating -- see finding
  below).
- **Cart**: PASS/PASS/PASS. `real_remove` genuinely removed the item
  (`before: 1, after: 0`); `free_shipping_goal`: PASS (the fixture
  product's price is below `rasti-mode-demo`'s configured threshold,
  matching the Python-computed `expected_free_shipping_state: "goal"`
  -- verified, never recomputed, in run.mjs).
  `accessibility_checks`: `quantity_control`/`remove_control`/`checkout`
  all PASS (after the ordering fix). Desktop representative screenshot
  staged.
- **Theme (Tier 1, nowruz/balanced/desktop)**: PASS, `cleanup_verified:
  true`, `screenshot: null` (correct -- Tier 1 only stages a screenshot
  on FAIL/BLOCKED).
- `_meta.w4c_branch_head_sha`: `5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47`
  -- the exact HEAD this smoke ran at.
- `_meta.duplicate_cells`: `[]`.
- `_meta.recovered_state_events`: one genuine Template-drift-repair
  event (the fresh campaign root's first cell run found the Store's
  published Template state didn't match the preset and repaired it).
- Staged screenshots: 2 Home + 3 representative (Listing/PDP/Cart
  Desktop) = 5 files, matching the PASS-only staging contract; no
  `failures/` or `theme/` directories (nothing failed, Tier 1 passed).

**704-cell campaign was NOT run.** **No other Template was started.**
**Static Gallery refresh was NOT run.**

## Two genuine, pre-existing production accessibility gaps discovered

Both are RECORDED by the new accessibility checks (never silently
passed) but deliberately do NOT gate their cell's PASS/FAIL, per
section 8's "STOP and report" instruction -- fixing either needs a
production-template change outside this round's two authorized harness
files:

1. **Listing sort/category `<select>` controls carry no accessible
   name** (`storefront_builder/sections/product_listing.html`'s
   `select[name="sort"]`/`select[name="category"]`, in both
   `layout_variant` branches) -- no `<label for>`, `aria-label`, or
   `title`.
2. **PDP color-swatch controls are not keyboard-focusable**
   (`storefront_builder/sections/product_main.html`'s `.opt-block
   .swatch` renders a plain `<div>` with no `tabindex`, unlike the
   sibling `.opt-block .size` `<button>` elements) -- has a `title`
   (accessible name), but cannot receive keyboard focus.

Neither is a harness defect; both are flagged here for a separate,
authorized production-template repair round.
