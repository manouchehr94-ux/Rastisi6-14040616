# Runtime Flow Index

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 08)
```

Index of the 15 reconstructed runtime flows. Full step-by-step detail lives in Phase 1
[`../phase1_code_discovery/08_RUNTIME_FLOWS.md`](../phase1_code_discovery/08_RUNTIME_FLOWS.md)
(authoritative source; this is the navigable index). Domain packs carry per-domain `FLOWS.md`.

---

| # | Flow | Entry → key service | Domains | Notes |
|---|---|---|---|---|
| 0 | Host → Store context | middleware → `resolve_store_for_request` | stores, portal | Sets `request.store`; fail-closed |
| 1 | Add to cart | cart view → `cart_service.add_item_to_cart` | cart, catalog | membership-fence locks |
| 2 | Order creation from cart | checkout → `order_service.create_order_from_cart` | orders, cart, catalog | atomic; idempotent (`checkout_token`); ORDER_PLACED SMS on_commit |
| 3a | Storefront payment — SIMULATION (legacy) | `payment-callback/<status>` → `payment_service.simulate_payment` | orders, sms | gated by `PAYMENTS_SIMULATION_ENABLED`; writes `payment_status` (H1) |
| 3b | Storefront payment — REAL GATEWAY | `gateway/callback/<attempt>` → `gateway_payment_service.process_callback_and_verify` | orders, sms | verify server-to-server; lock + conditional PENDING→PAID; creates legacy Transaction |
| 4 | Manual refund / return | dashboard → `refund_service` / `return_service` | orders | MANUAL refund only; returns own state machine |
| 5 | Trial store provisioning | portal store-create → `provisioning_service.provision_trial_store` | portal, stores, core, catalog, subscriptions | single atomic across 4 apps |
| 6 | Owner authentication (OTP + step-up) | portal login → `owner_otp_service` / `step_up_service` | portal, sms | hashed OTP; session step-up |
| 7 | SaaS billing → subscription activation | webhook → `webhook_service.ingest_webhook` → `confirmation_service.confirm_payment` → `subscription_service` | billing, subscriptions | verified idempotent inbox; browser return never proof |
| 8 | SaaS renewal + dunning (cron) | `generate_subscription_renewals` / `process_subscription_dunning` | billing, subscriptions | canonical lock order Subscription→ScheduledPlanChange |
| 9 | Subscription lifecycle scan (cron) | `evaluate_subscription_states` → `subscription_service` | subscriptions | guarded transitions |
| 10 | Storefront layout edit → publish (R4) | `r4/mutate/` → `r4_mutation_service`; `r4/publish/` → `layout_service.publish` | storefront_builder | optimistic `edit_revision`; pointer-swap publish |
| 11 | Public storefront render | `GET /` → `catalog.views.home` → `render_service.build_render_items` | storefront_builder, catalog, content | legacy fallback when `uses_visual_storefront_layout` False |
| 12 | Custom domain verification | portal → `domain_verification_service` | stores | real DNS TXT + SSL socket |
| 13 | SMS send | `send_event_sms`/`send_raw_sms` → `_dispatch` | sms, portal | single funnel; OTP routes to platform provider; device poll/ack |
| 14 | Store deletion (soft) → purge | portal delete → `deletion_service`; cron `purge_deleted_stores` | stores, portal, notifications | soft-delete then scheduled purge |

**Count:** 15 numbered flows (0–14); Flow 3 is documented as two sub-flows (3a simulation / 3b real
gateway), so the source document has 16 flow sections.

Graph: [`../phase1_code_discovery/graphs/major_runtime_flows.mmd`](../phase1_code_discovery/graphs/major_runtime_flows.mmd).

## Cross-flow observations (CURRENT CODE REALITY)
- Two payment confirmation designs coexist (3a vs 3b) writing the same `Order.payment_status` (H1).
- Consistency discipline is strong in gateway/billing/subscription/order-creation paths; weaker in
  the simulation/refund order-payment path (no Order lock). See
  [`TRANSACTION_AND_CONSISTENCY.md`](TRANSACTION_AND_CONSISTENCY.md).
