# Simple subscription plan pricing — 2026-11-06

Branch `dev/pricing-simplify-20261106`, built on the Checkout branch `dev/platform-checkout-unify-20261106` (`8ad4b687…`).
Local only: not pushed, merged or deployed.

## 1. What the owner does now

In the existing Platform Admin plan form (`/plans/add/`, `/plans/<id>/edit/`) there is one pricing section:

1. **Monthly base price (TOMAN)** — entered once.
2. **Discount %** for 3, 6 and 12 months (default 0). Each period can be switched off ("offered").
3. A live preview per period: undiscounted total, discount %, discount amount, final price, effective monthly price.

The owner never enters four independent prices. A "free / trial" plan type (interval `none`) is an explicit choice, not a 100 % discount.

## 2. The formula and rounding policy

```
base_total   = monthly_price × months                      (months: 1 / 3 / 6 / 12)
final_price  = round_half_up( base_total × (1 − discount_percent / 100) )   → whole TOMAN
discount_amt = base_total − final_price                    (so the two always add up exactly)
effective_monthly = final_price / months                   (display only, never charged)
```

* All arithmetic is `Decimal` / integer. The browser preview uses BigInt basis points; it is display only.
* Rounding is **half-up to the whole toman**, applied once, to the exact decimal product. No float is involved anywhere.
* Brief example, monthly 1,000: 1 m → 1,000; 3 m @5 % → 2,850; 6 m @10 % → 5,400; 12 m @15 % → 10,200.
* Validation (server-side, authoritative): discount in `[0, 100)`, at most 2 decimals, Persian/Arabic digits accepted;
  `100 %` is rejected (free is a plan type, not a discount); monthly price must be a whole number > 0 for paid plans;
  a period whose final price would round to 0 is rejected; the monthly row never carries a discount.
* TOMAN ↔ RIAL is unchanged: the gateway amount is `final_price × 10`.

## 3. One calculation service

`apps/subscriptions/services/period_pricing.py` is the only place that computes or interprets period prices
(`compute_period`, `compute_all`, `validate_*`, `quote(s)`, `final_amount`, `invoice_metadata`, `owner_review`, `implied_discount`).

Consumers (all read through it; none recompute):

| Consumer | Path |
|---|---|
| Owner create/edit, draft recompute, publish validation | `plan_service.set_formula_pricing`, `_recompute_formula_rows`, `validate_for_publication` |
| Public pricing cards / comparison, merchant plan list, interval switcher | `pricing_page_service._period_options` |
| `PlanVersion.price_for` (used by invoices, renewal, plan change/upgrade, checkout, activation) | delegates to `period_pricing.final_amount` |
| Invoice lines (`metadata.pricing`: mode, months, discount %, base total, discount amount) | `invoice_service.plan_line_spec` |

`final_amount` refuses a formula row whose stored amount disagrees with the formula (corruption guard), so a wrong amount can never be charged silently.
Browser-submitted prices are ignored: the server recomputes from the monthly price and the discount percents.

## 3a. Storage and versioning

* New nullable column `PlanVersionPrice.discount_percent` (migration `0014`, additive, check constraint `0 ≤ d < 100` or NULL).
* **`discount_percent IS NOT NULL` → formula row**; the stored `price` is an immutable computed snapshot of the formula at save time.
  **`NULL` → legacy absolute price**; it is never recalculated.
* Published versions stay immutable. Editing a published plan creates a new draft version; drafts are edited in place; publishing keeps the
  existing immutable-version semantics. Active subscribers stay on their version (grandfathered); historical invoices are never touched.
* Changing the monthly price of a draft recomputes that draft's formula rows only.

## 4. Existing plans: safe owner-review path

Nothing is migrated or rewritten automatically (no data migration touches prices).
When the owner opens a plan with legacy prices, each legacy period shows a review panel:

* If an implied discount reproduces the stored price **exactly**, it is prefilled (e.g. 1,566,000 on a 290,000 monthly = 10 %).
* If not (e.g. 780,000 ≈ 10.34 %, 2,900,000 ≈ 16.67 %), the panel says so and **"keep current price (no formula)" is checked by default**.
  Converting such a period to the formula needs an explicit acknowledgement that the commercial value changes.
* Saving with the defaults keeps every legacy price byte-for-byte equal; the published version is untouched and an audit entry is written.

## 5. UI

Platform Admin design system (PR #42/#43): RTL, Persian digits/`fa-IR` currency formatting, responsive at 1440/768/390 (no horizontal overflow).
The price and discount fields are `type="text" inputmode="numeric"`. The design system forces `appearance: textfield` on the two remaining
`type="number"` inputs (display order, entitlement limits), so there are no native spinner arrows anywhere in the form.
No new pricing page was added.

## 6. Test evidence

PostgreSQL (`apps.subscriptions`, `apps.billing`, `apps.portal`, selected dashboard suites) — see the final report for exact counts.
New tests:

* `apps/subscriptions/tests/test_period_pricing.py` — 18 pure tests: brief example, defaults, Decimal-only, rounding (half, just below/above, float traps, large values),
  validation, 100 %/zero rejection, implied discount.
* `apps/portal/tests/test_plan_form_simple_pricing.py` — 33 tests: owner form, Persian digits, invalid input, tampering ignored, monthly change recompute, free plan, audit log,
  immutability, publish/versioning, legacy preservation and conversion, invoice == checkout == gateway RIAL per interval, activation keeps interval, renewal,
  grandfathering, upgrade preview/invoice, a regression test for formula + legacy plans on the public page, and one for free (`none`-interval) plans.

Browser E2E (`Chromium`, isolated PostgreSQL DB, fake gateway; 48/48 checks, 0 console errors): live preview (brief example), Persian digits, invalid-discount error,
JS-preview vs server parity on 8 rounding vectors, save → publish → immutable, public `/plans/` == merchant portal == unified checkout == invoice == gateway RIAL (10,200,000),
verified payment activates the yearly interval, legacy review UI + keep-legacy preservation, 1440/768/390 overflow + RTL.

The E2E found one real bug the unit tests missed (public `/plans/` raised `TypeError` when a formula plan and a legacy plan were published together:
`max()` over mixed `int`/`str` percents). Fixed and covered by a regression test.
The broader regression run found a second one: `price_for("none")` (free/trial plans, used by the invoice plan snapshot) raised `KeyError`
after the read path moved into the service. `final_amount`/`invoice_metadata` now charge a free version's stored zero price, as before.

## 7. Known limits / risks

* Legacy prices remain absolute until the owner converts them; the public page keeps the old "savings vs monthly" logic for those rows.
* A formula row is a snapshot: changing a *published* plan's monthly price always goes through a new draft version (by design).
* Rounding is half-up per period, so the effective monthly price of a period can be fractional (display only).
* The JS preview is not authoritative; the server result is final (parity checked on edge vectors, not proven exhaustively).
* No real gateway was contacted; the fake Zibal server verifies the RIAL amount only.
