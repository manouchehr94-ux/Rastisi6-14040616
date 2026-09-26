# cart — Testing

```
domain_id: D5
code_baseline: 5883a140
source: apps/cart/tests/
```

| Behavior | Test file |
|---|---|
| Cart service (add/reprice, membership fence) | `test_cart_service.py` |
| Pricing / totals / coupons | `test_pricing.py` |
| Cart security (tenant/session) | `test_cart_security.py` |
| Gift wrap (server-authoritative) | `test_gift_wrap.py` |

Cross-domain cart mutation (reprice/delete at checkout) is additionally exercised in
`apps/orders/tests/` (checkout/order-service tests). See canonical
[`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
