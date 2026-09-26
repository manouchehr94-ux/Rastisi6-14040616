# orders — Boundaries

```
domain_id: D6
code_baseline: 5883a140
```

## Owns
- **Order lifecycle** (`Order`, `OrderItem`, `OrderStatusHistory`) and its guarded status machine.
- **Storefront payment** — two implementations: legacy simulation (`Transaction` +
  `payment_service`) and real gateway (`PaymentAttempt` + `gateway_payment_service` + `gateways/`).
- **Payment gateway configuration** (`PaymentGatewayConfig`) and the legacy `PaymentGateway` model.
- **Refunds** (`Refund`/`RefundItem`, MANUAL only) and **returns** (`ReturnRequest`/`ReturnItem`).
- **Shipping & tax configuration** (`ShippingZone/Method/RateRule`, `TaxClass/TaxRate`).
- Credential encryption helper `apps/orders/encryption.py` (reused by `stores` integrations).

## Does NOT own
- **SaaS / platform billing** — that is the `billing` domain (`SubscriptionInvoice`,
  `SubscriptionPaymentAttempt`, `SubscriptionRefund`). Do not conflate: two separate money systems.
- **The cart** — `cart` owns `Cart`/`CartItem`/`Coupon`. orders *reads and mutates* cart items at
  checkout (cross-domain — M9), but does not own them.
- **Inventory truth** — `catalog.inventory_service` + `StockMovement` own stock. orders reserves/
  consumes via catalog.
- **Customer identity** — `customers` owns `Customer`.
- **SMS delivery** — `sms` owns sending; orders only triggers events via `transaction.on_commit`.
- **Order status transitions from the UI** — `dashboard` triggers them but only via
  `order_service.change_order_status`.

## Cross-domain writes OUT of orders (orders writes other domains)
- `cart.CartItem.unit_price` (reprice in `create_order_from_cart`).
- `cart` items deleted (`checkout_service.finalize_order`; `views.checkout_item_update/remove`).
- `cart.Coupon.used_count += 1`.
- `catalog` inventory reservation/consumption (+ `StockMovement`).

## Cross-domain writes INTO orders (other domains write orders)
- `dashboard.views` writes `ShippingZone/Method/RateRule`, `TaxClass/TaxRate`, `PaymentGatewayConfig`
  **directly** (DR-3), and triggers `Order.status` via `order_service.change_order_status`.

## Ambiguities at this boundary
- **Dual gateway representation** (M4/DR-5): `PaymentGateway` (legacy order-chosen slug) vs
  `PaymentGatewayConfig` (operational config). "Which gateway" is not single-sourced.
