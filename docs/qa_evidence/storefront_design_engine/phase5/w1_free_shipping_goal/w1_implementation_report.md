# P5-W1 — Cart Conversion Micro-Pass / Free-Shipping Goal — Implementation Report

## Base & branch
- **Certified base SHA:** `ef4f4e3397e9cdf7904f126aa877105e332dc0e0` (official `feature/phase5-design-expansion`).
- **Implementation branch:** `feature/phase5-w1-cart-free-shipping-goal` (cut from the certified base; verified HEAD before first change).
- **Authoritative plan:** `docs/superpowers/plans/2026-09-15-phase5-converged-completion-plan.md` (§P5-W1).

## What shipped
A cart Free-Shipping Goal / progress indicator, driven entirely by existing pricing/threshold data. **Presentation-only** feature; all math lives in the canonical pricing authority.

- **`apps/cart/services/pricing.py::cart_totals()`** — the sole owner of the goal math. Its return dict gains six precomputed, presentation-ready fields (existing outputs unchanged):
  - `free_shipping_threshold` — Store-scoped threshold (existing `_free_shipping_threshold(store)`, read **once** and reused for the existing comparison too).
  - `free_shipping_by_threshold` — `items_total >= threshold` (the existing `free_by_threshold`).
  - `free_shipping_by_coupon` — the existing coupon-granted free-shipping flag (so the reason is distinguishable).
  - `free_shipping_goal_applicable` — `shipping_service.cart_requires_shipping(items)` (canonical shippability owner; reuses the same `items` list). `False` for all-digital carts.
  - `free_shipping_goal_remaining` — `max(0, threshold − items_total)` (never negative).
  - `free_shipping_goal_progress_percent` — `0` when threshold ≤ 0 or empty cart, else `min(100, round(items_total*100/threshold))` (clamped `[0,100]`).
- **`apps/storefront_builder/templates/storefront_builder/sections/cart_summary.html`** — display-only `.fsg` block reading the precomputed values. Four states: (A) not applicable → block omitted; (B) below threshold → "X تومان دیگر تا ارسال رایگان" + progress bar (width = server percent); (C) threshold reached → "ارسال رایگان فعال شد"; (D) FREE_SHIP coupon below threshold → "ارسال رایگان با کد تخفیف فعال شد" (does not claim threshold; bar suppressed). No arithmetic in the template.
- **`apps/cart/static/css/cart.css`** — `.fsg` styles (RTL-safe logical properties; `.fsg-fill { max-width:100% }`; `prefers-reduced-motion` respected). Loaded by `apps/cart/templates/cart/cart_detail.html:16`.
- `render_service._cart_summary_context` is **unchanged** — it keeps passing the canonical `totals` object; it reads no `ShopSettings` and computes nothing.

## Canonical ownership
- Free-shipping math owner: `apps/cart/services/pricing.py::cart_totals()`.
- Shippability owner reused: `apps.orders.services.shipping_service.cart_requires_shipping` (`Product.requires_shipping`). No second shippability rule.
- No `ShopSettings.load()` / threshold read / arithmetic in view, render_service, template, JS, or CSS.

## TDD
- **RED (verified before implementation):** `red_pricing.txt` — 11 errors, all `KeyError` on the missing goal fields; no syntax/import/fixture errors. Correct RED cause.
- **GREEN:** implemented the fields in `cart_totals()` and the `.fsg` presentation.

## Test results
- **Focused pricing** (`green_pricing.txt`): `apps.cart.tests.test_pricing` → **41 passed**.
- **Focused W1** (`green_focused.txt`): `apps.cart.tests` + `apps.storefront_builder.tests.test_render_service` → **251 passed** (1 skipped).
- **Regression** (`regression.txt`): `apps.cart apps.storefront_builder.tests.test_views apps.orders.tests.test_checkout_correctness` → **408 tests; 1 failure + 1 error**, both in `FullscreenEditorTests` (R4 fullscreen editor — unrelated to W1). **Reproduced independently on the clean certified base `ef4f4e3` via a temporary git worktree with zero W1 changes** (same 1 failure + 1 error) → **PRE-EXISTING, not introduced by W1** (`regression_preexisting_note.txt`). All cart/pricing/render_service tests pass.

New tests:
- `apps/cart/tests/test_pricing.py` → `FreeShippingGoalTests` (11 cases: below/at/above threshold, FREE_SHIP-coupon-below-threshold, threshold-without-coupon, empty cart, progress-bounded, all-digital/mixed/physical-only applicability, existing-values-unchanged) + `FreeShippingGoalTwoStoreIsolationTests` (Store-scoped goal state, real two-Store).
- `apps/storefront_builder/tests/test_render_service.py` → `CartContextAwareSectionsTests` +2 (goal fields pass through untouched; source guard: `_cart_summary_context` has no `ShopSettings`/threshold/goal math) + `FreeShippingGoalTemplateTests` (5: 4 UI states + template-does-no-arithmetic).

## Gates
- `python manage.py check` → **no issues** (`django_check.txt`).
- `python manage.py makemigrations --check --dry-run` → **No changes detected** (`migration_check.txt`). **Zero migrations.**
- `git diff --check` → **clean** (`diff_check.txt`).

## Architecture duplication gate
`architecture_duplication_audit.txt` — ALL CLEAR: no second pricing function, no second threshold source, no manual `requires_shipping` rule, no shipping model/schema/checkout change, no JS/render/template pricing math, no Cross-Sell/recommendation, no W2 theme code, no unrelated polish. `ONE CONCEPT = ONE CANONICAL OWNER` holds.

## Browser QA
Runner `tools/storefront_builder_qa/public_w1_qa.mjs` (playwright-core + chromium) against the real published tenant `rastisi-fashion-test` (threshold 500,000), RTL, at **1440×900 / 768×1024 / 390×844**. Real session carts populated via the canonical `cart:add` endpoint (no HTML patched). Evidence: `browser_qa/report.json` + 12 screenshots. Result: **48 PASS / 0 FAIL / 3 WARN** (the 3 WARN are "empty cart has no checkout button" — correct). Verified per viewport:
- **below** (350k < 500k): goal "۱۵۰٬۰۰۰ تومان دیگر تا ارسال رایگان" + progress bar bounded (fill ≤ track width).
- **reached** (1,337k ≥ 500k): "ارسال رایگان فعال شد" success.
- **all-digital**: goal block absent.
- **empty**: no goal, no error/NaN.
- No horizontal overflow; RTL confirmed; checkout button usable; **0 console errors; 0 failed requests**.

State **D** (FREE_SHIP coupon below threshold) is verified by unit tests (`test_free_ship_coupon_below_threshold_not_reported_as_threshold`) and the template test (`test_state_d_coupon_below_threshold_does_not_claim_threshold`); it is not browser-exercised because the storefront cart has no coupon-entry UI surface (coupons apply at a different layer). A one-off QA-only digital product (`qa-digital-giftcard`, `requires_shipping=False`) was created in the **local dev DB** to exercise the all-digital state — it is not committed (DB is gitignored).

## Production files changed
- `apps/cart/services/pricing.py`
- `apps/storefront_builder/templates/storefront_builder/sections/cart_summary.html`
- `apps/cart/static/css/cart.css`

## Test files changed
- `apps/cart/tests/test_pricing.py`
- `apps/storefront_builder/tests/test_render_service.py`

## Evidence files
`docs/qa_evidence/storefront_design_engine/phase5/w1_free_shipping_goal/`: `red_pricing.txt`, `green_pricing.txt`, `green_focused.txt`, `regression.txt`, `regression_preexisting_note.txt`, `django_check.txt`, `migration_check.txt`, `diff_check.txt`, `architecture_duplication_audit.txt`, `browser_qa/report.json` + screenshots, this report.

## Migrations
**0.**

## Known limitations
- The FREE_SHIP-coupon cart state is unit/template-verified rather than browser-verified (no storefront coupon-entry UI). Behavior is fully covered by tests.
- Two pre-existing `FullscreenEditorTests` failures exist on the certified base (unrelated to W1); out of scope for W1.

## Scope statement
Production changes are confined to the three planned files. Cross-Sell was NOT implemented (BACKLOG per the converged plan). P5-W2 not started. Official Phase-5 branch remains at `ef4f4e3397e9cdf7904f126aa877105e332dc0e0` pending independent review and merge approval.
