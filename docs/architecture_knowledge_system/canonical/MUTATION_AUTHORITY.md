# Mutation Authority — WHO MUTATES WHAT

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 06) / Phase 2 (docs 01, 02)
open_decisions: DR-1, DR-2, DR-3, DR-4, DR-5
```

For each important persisted entity: every meaningful writer, classified. This is the reference a
future engineer/agent must consult **before changing how any entity is written**.

Classification: **CANONICAL** (intended primary boundary) · **SECONDARY** (legitimate additional
in-domain writer) · **DIRECT** (`.save()`/`.update()` bypassing the owning domain's service) ·
**CROSS-DOMAIN** (writer in a different domain than the owner).

---

## ⚠️ Highest-risk entities (read first)

### `Order.payment_status` — 3 writers, NO transition guard (finding H1 / decision DR-1)
| Writer | Class | Evidence |
|---|---|---|
| `orders.services.gateway_payment_service.process_callback_and_verify` | CANONICAL (intended) | conditional `Order.objects.filter(pk=…, payment_status=PENDING).update(payment_status=PAID)` after `select_for_update` re-lock (`gateway_payment_service.py:313-316`) |
| `orders.services.payment_service.simulate_payment` | SECONDARY | plain `order.save(update_fields=["payment_status",…])` PAID/FAILED (`payment_service.py:86-98`); **no Order lock**; production-gated by `PAYMENTS_SIMULATION_ENABLED` |
| `orders.services.refund_service.execute_order_refund` | SECONDARY | plain save → REFUNDED (`refund_service.py:234`) |

**There is no `ALLOWED_TRANSITIONS` table for `payment_status`.** The only such table
(`order_service.py:45`) governs `Order.status`. This is impossible-to-overlook by design; see
[`../domains/orders/`](../domains/orders/README.md).

### `content.*` (pages/menus/footer/media) — no content service; dashboard writes directly (H2 / DR-2)
All `ContentPage`/`Menu`/`MenuItem`/`FooterSettings`/`HeroSlide`/`PromotionalBanner`/`SocialLink`/
`FooterTrustBadge`/`FooterPaymentLogo`/`StoryRailItem` CRUD is performed by
`apps/dashboard/views.py` (DIRECT / CROSS-DOMAIN; 83 save/delete/clean sites app-wide). `apps/content`
has **no** write service (`content/services.py` is resolve/cleanup/newsletter only). See
[`../domains/content/`](../domains/content/README.md).

---

## Full mutation map

### `Order.status` (owner: orders) — LOW
- CANONICAL: `order_service.change_order_status` (guarded `ALLOWED_TRANSITIONS` + `FINAL_STATUSES`).
  All callers (`simulate_payment`, `gateway_payment_service`, dashboard `order_detail`) funnel here.

### `Transaction` (orders, legacy) — MEDIUM
- SECONDARY (create): `payment_service.simulate_payment` **and** `gateway_payment_service` ("for
  dashboard back-compat"). A gateway-paid order gets both a `PaymentAttempt` and a `Transaction`.

### `PaymentAttempt` (orders, new) — LOW
- CANONICAL: `gateway_payment_service` (initiate/process).

### `CartItem` / `Cart` (owner: cart) — MEDIUM (cross-domain)
- CANONICAL: `cart.cart_service.add_item_to_cart` / `reprice_cart_items` (membership-fence locks).
- CROSS-DOMAIN: `orders.order_service.create_order_from_cart` (reprice `unit_price`);
  `orders.checkout_service.finalize_order` (`cart.items.all().delete()`);
  `orders.views.checkout_item_update/remove`; `customers.auth_service.merge_guest_cart`.

### `Coupon.used_count` (owner: cart) — LOW-MED
- CROSS-DOMAIN: `orders.order_service.create_order_from_cart` (`+=1`).

### `StoreSubscription.status` (owner: subscriptions) — MEDIUM (funneled)
- CANONICAL: `subscription_service` transitions (`ALLOWED_TRANSITIONS`, `select_for_update`, idempotent).
- CROSS-DOMAIN **via canonical** (never direct): billing `confirmation_service`, `dunning_service`,
  `renewal_service`, `cancellation_service`; subscriptions `plan_change_service` override.

### `SubscriptionInvoice.status` (owner: billing) — MEDIUM (in-domain)
- CANONICAL: `invoice_service` (draft/open/void). SECONDARY: `confirmation_service` (→paid),
  `dunning_service` (→past_due/uncollectible), `refund_service` (→refunded/partially),
  `payment_flow_service` (→payment_pending). No single table; each guarded by `is_payable`/`is_financially_locked`.

### `Product` (owner: catalog) — MEDIUM
- CANONICAL: `catalog.product_draft_service` (draft placeholder), catalog services (attribute/brand/
  variant/…). DIRECT/CROSS-DOMAIN: `dashboard.views._save_product` + `dashboard.catalog_admin_service`
  bulk `.update()`. import + industry-template install also write.

### `Product.stock` / `ProductVariant.stock` (owner: catalog) — LOW
- CANONICAL (only): `catalog.inventory_service` (+ `StockMovement` ledger). QuerySet blocks bulk bypass.

### `ShopSettings` (owner: core) — MEDIUM (cross-domain / direct)
- CANONICAL: `core.ShopSettings.provision_for` (create). CROSS-DOMAIN/DIRECT:
  `dashboard.views.settings_*` (`shop.save()`); `sms.sms_service.regenerate_smsrasti_device_token`;
  portal onboarding (INFERRED).

### Orders commerce config (Shipping*/Tax*/PaymentGatewayConfig) (owner: orders) — MEDIUM (DR-3)
- CROSS-DOMAIN/DIRECT: `dashboard.views.settings_*` (direct `.save()`, incl. credential encryption);
  `dashboard.settings_admin_service.toggle_*`.

### Store tenancy entities (owner: stores) — MEDIUM
- `Store.status/suspension`: `store_status_service`, `deletion_service`, provisioning, platform_admin_views.
- `StoreMembership`: `membership_service` (incl. **`transfer_ownership` — LIVE**, dashboard route),
  `ownership_transfer_service.accept` (portal OTP), provisioning. **Two live owner-transfer paths (DR-4).**
- `StoreDomain` verification/routing/tls: `domain_verification_service`, `handle_service`, provisioning.

### `Customer` / auth `User` (owner: customers/portal) — MEDIUM
- `customers.auth_service` (signup/guest); `portal.owner_auth_service` (register / get_or_create_by_phone);
  `stores.membership_service.add_staff_member` (CROSS-DOMAIN, creates `is_staff` User).

### Storefront layout entities (owner: storefront_builder) — MEDIUM
- CANONICAL: `r4_mutation_service` (R4 optimistic boundary), `layout_service` (publish/draft/restore),
  `container_service`/`preset_service`. SECONDARY: legacy `views.py` (fail-closed when R4 active).
- appearance: `appearance_authority_service` / `storefront_appearance.persistence` (mirrors into
  header/footer_config — M1).

### SMS / Notifications — LOW
- `SmsLog`/credits/outbox: `sms_service._dispatch` (single funnel) + `gateway_views` (device poll/ack).
- `NotificationOutbox`: `notification_service.enqueue/notify_security_event` (callers in `stores` services).

---

## Summary — most at-risk
| Entity | Writers | Guarded? | Severity | Decision |
|---|---|---|---|---|
| **Order.payment_status** | 3 | **No transition table** | HIGH | DR-1 |
| **content.*** | dashboard views (no service) | model `clean()` only | HIGH | DR-2 |
| Shipping/Tax/GatewayConfig | dashboard direct | model validation | MEDIUM | DR-3 |
| StoreMembership owner transfer | 2 live paths | per-service | MEDIUM | DR-4 |
| Order gateway (dual model) | — | — | MEDIUM | DR-5 |
| Transaction (legacy) | 2 create paths | n/a | MEDIUM | DR-6 |
| Order.status / stock / Subscription.status | funneled | yes | LOW | — |

Mutation graph: [`../phase1_code_discovery/graphs/mutation_graph.mmd`](../phase1_code_discovery/graphs/mutation_graph.mmd).
