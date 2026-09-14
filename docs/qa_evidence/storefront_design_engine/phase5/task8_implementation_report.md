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
