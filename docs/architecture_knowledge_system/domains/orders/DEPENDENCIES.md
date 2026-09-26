# orders — Dependencies

```
domain_id: D6
code_baseline: 5883a140
```

## orders depends ON (calls/reads/writes out)
| Target | Type | What |
|---|---|---|
| `cart` | writes (cross-domain, M9) | reprice `CartItem.unit_price`; delete items; `Coupon.used_count += 1` |
| `catalog` | writes | inventory reserve/consume + `StockMovement` (via reservation/inventory service) |
| `sms` | calls (on_commit) | ORDER_* / PAYMENT_* events |
| Zibal / COD | external-call | payment create/verify |
| `core` | uses | `encryption.py` (Fernet) — actually orders OWNS encryption.py; `stores` reuses it |

## Depends on orders (who calls in)
| Source | Type | What |
|---|---|---|
| `dashboard` | calls | `order_service.change_order_status`, `refund_service`, `return_service`; reads orders for reports/CRM |
| `dashboard` | writes (direct, DR-3) | `ShippingZone/Method/RateRule`, `TaxClass/TaxRate`, `PaymentGatewayConfig` |
| checkout views | calls | `create_order_from_cart`, payment initiation |
| gateway (public) | routes-to | `gateway_callback` → `process_callback_and_verify` |
| `stores` | imports | `orders.encryption` (credential encryption reuse) |

## Import-cycle notes
- SMS imports inside `orders` services are **local** (inside functions) to defer the `sms` import
  to call time.
- orders does not import `storefront_builder`/`content`.

## Not a dependency (explicit)
- `billing` and `subscriptions` are the *other* money system; orders has no dependency on them.
- `customers` is read for the order's customer FK but customer identity is owned there.

See canonical [`../../canonical/DEPENDENCY_MAP.md`](../../canonical/DEPENDENCY_MAP.md).
