# Platform coupons: late gateway callbacks and over-redemption (financial policy)

## Statement

`max_redemptions` and `max_per_store` are **strictly enforced when a coupon is applied or a reservation is (re)created**
(row lock on the coupon, counting redeemed plus unexpired reserved rows). They are **not strictly enforced at the moment a
payment is confirmed**. Confirmation of money already received never refuses the recorded discount. The over-quota event
is **detected and audited** (`over_redeemed` coupon audit event, `billing.platform_coupon_over_redeemed` audit log) for
finance follow-up. Auditing is detection, not prevention.

## When it can happen

Only when all of these hold for an invoice carrying a coupon:

1. The reservation lapsed (default lifetime 30 minutes) or was released, and no manual card claim pinned it.
2. Another invoice legitimately took the freed slot (so counted redemptions already equal the cap).
3. The payer's gateway confirmation (webhook or callback) for the first invoice then arrives late and settles it.

## Paths

| Path | Quota behaviour |
|------|-----------------|
| Manual card claim | Submitting a claim re-validates or renews the reservation under lock and pins it for the review window (7 days). If the slot is gone the claim is refused (`reservation_lost`). Over-redemption is not expected; it needs an operator release of the pinned reservation. |
| New gateway attempt | `ensure_reservation_active` runs before each attempt: renews, or re-reserves only if capacity and validity remain, else refuses. |
| Late gateway callback after lapse | **Can over-redeem.** The recorded discount is honoured, redemption is recorded, event is audited. |

## Maximum exposure

- Per invoice: one honoured discount, equal to the discount recorded on that invoice (`discount_amount`, already fixed and
  never recomputed). It cannot exceed the invoice amount.
- Per coupon: redeemed count can exceed the cap by at most the number of invoices whose reservation lapsed and whose slot
  was resold and which are then paid late. Each invoice has a single redemption row, so there is no multiplication per
  payment. Worst case overage L is bounded by the number of gateway payments in flight beyond 30 minutes while the coupon
  was at capacity (small in practice; the gateway session itself is short).
- Maximum financial exposure per coupon = `L x discount per redemption`. For a fixed-amount coupon that is
  `L x fixed amount`; for a percent coupon it is the sum of the recorded discounts on those L invoices (plan price x percent,
  subject to any `max_discount` cap).
- Per store (`max_per_store`) is bounded the same way, within that store.

## Why not refuse

The money has been received for the discounted price. Refusing means either keeping funds without service or an
automated refund per late event. The owner accepted bounded, audited over-redemption instead.

## Finance follow-up

Query `PlatformCouponAuditEvent` with `action="over_redeemed"` (detail: `scope` total|store, `from`, caps). Decide per
case: accept, or refund via the normal refund flow (`reverse_for_refund` returns the redemption).

## Not covered

True concurrent last-slot contention needs PostgreSQL row locks and was not executed (tests ran on SQLite, which
ignores `select_for_update`). A strict-at-settlement alternative (refund automatically) is not implemented and needs an owner decision.

Tests: `test_platform_coupon_review_fixes.OverRedemptionPolicyTests`, `test_platform_coupon_claim_failure_paths`.
