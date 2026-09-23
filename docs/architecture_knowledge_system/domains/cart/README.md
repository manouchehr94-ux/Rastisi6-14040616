# Domain: cart (D5) — Cart & Pricing

```
domain_id: D5
app: apps/cart
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: POOR
code_baseline: 5883a140
open_decisions: —
known_risks: M9, L2
```

Owns the shopping cart, cart pricing/coupons, gift wrap, and the checkout idempotency token.
Readiness POOR (documentation): only ADR-15/32 + business defaults previously — this pack fills it.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[DEPENDENCIES](DEPENDENCIES.md) · [TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) ·
[CODE_MAP](CODE_MAP.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* STATE_MACHINES (none — Cart has no status), SECURITY/INVARIANTS/TRANSACTIONS/FLOWS/
API_AND_EVENTS/ARCHITECTURE/TROUBLESHOOTING/HISTORICAL_CONTEXT → SERVICES + MUTATION_AUTHORITY + this README.

## Orientation
- **Owns:** `Cart` (+ `checkout_token` idempotency anchor), `CartItem` (server `unit_price`
  snapshot), `Coupon` (store-owned, `uniq_coupon_code_per_store`).
- **Does NOT own:** the catalog price source (reads `catalog.pricing_service`); the order (orders
  reads/mutates cart at checkout — M9).
- **Canonical service:** `cart_service` (add/reprice under a membership-fence lock) + pricing/coupon/
  gift-wrap services.
- **⚠️ Cross-domain writers (M9):** `orders` reprices CartItem, deletes cart items, and increments
  `Coupon.used_count`; `customers.auth_service` merges guest carts. cart exposes no service for
  orders' deletions — orders reaches into `cart.items`.
- **Historical:** ADR-15 (checkout idempotency = server token on Cart), ADR-32 (coupon per-store).
