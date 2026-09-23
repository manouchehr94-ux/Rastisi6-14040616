# orders — Open Decisions

```
domain_id: D6
code_baseline: 5883a140
```

Open architectural decisions (DRs) that affect this domain. **All OPEN.** Do not resolve. Full
detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects orders | Blocks which changes |
|---|---|---|---|
| **DR-1** | `Order.payment_status` canonical writer + guard | 3 writers, no transition table (H1) | changing payment_status semantics; adding a payment state |
| **DR-5** | Dual gateway representation | `PaymentGateway` (legacy) vs `PaymentGatewayConfig`; `payment_initiate` fuzzy-matches (M4) | gateway config changes; "which gateway" mapping |
| **DR-6** | Legacy-path removal | simulation path + legacy `Transaction` still present (PR12 unrealized) | retiring simulation; retiring legacy Transaction |

## Related findings (not DRs, but relevant)
- **M9** — orders→cart cross-domain mutation (reprice/delete/coupon).
- **L1** — `simulate_payment` lacks Order `select_for_update` (prod-gated).
- **L2** — `checkout_item_update/remove` mutate CartItem outside the checkout fence.
- **L4** — parallel "already paid" guards across the three payment entry points.

## Decision posture
This pack documents current reality precisely so that when DR-1/DR-5/DR-6 are eventually decided
(with Product-Owner authorization), the impact radius is already mapped. Nothing here selects an
option.
