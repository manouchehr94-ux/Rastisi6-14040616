# 08 — Runtime-Flow Reconstruction

Major runtime flows reconstructed from code. Each documents trigger, entry point, call path,
reads/writes, transaction boundary, side effects, state transitions, failure/idempotency, and
tests. Evidence class legend as in doc 01.

---

## Flow 0 — Every request: Host → Store context (VERIFIED)
```
request → SecurityMiddleware
       → StoreResolutionMiddleware: request.store = resolution.resolve_store_for_request(request)
       → PlatformHostRoutingMiddleware: pick urlconf (platform_admin / platform / ROOT)
       → StorefrontCanonicalRedirectMiddleware: 301 platform-subdomain → verified primary custom domain
       → Session/Auth/…
       → view
```
- **Reads:** Host header, `StoreDomain` (hostname lookup + eligibility: Store.ACTIVE + domain.VERIFIED + not retired).
- **Writes:** none.
- **Failure:** unresolved host → `request.store=None`; storefront views then `Http404`, or `403`
  if resolved-but-not-publicly-visible (`resolve_store_for_storefront`).
- **Tests:** `stores/tests/test_resolution.py`, `test_middleware.py`, `portal/tests/test_platform_host_routing.py`.

## Flow 1 — Add to cart (VERIFIED)
```
POST cart/… → cart.views → cart_service.add_item_to_cart
```
- **Txn/lock:** `@atomic`; `select_for_update` Product/Variant → Cart → CartItem (membership fence).
- **Writes:** CartItem (unit_price snapshot from catalog effective-price resolver).
- **Tests:** `cart/tests/test_cart_service.py`, `test_cart_security.py`, `test_pricing.py`.

## Flow 2 — Order creation from cart (VERIFIED)
```
checkout → orders.views → order_service.create_order_from_cart
```
- **Reads:** Cart/CartItem/Product/Variant/Coupon.
- **Txn/lock:** `@atomic`; locks Product/Variant then Cart then CartItem; raises
  `LivePriceChangedError`/`CartMembershipChangedError` on drift.
- **Writes:** Order, OrderItem, OrderStatusHistory(initial), `Coupon.used_count += 1`,
  CartItem.unit_price (reprice); reserves + consumes inventory (StockMovement).
- **Idempotency:** pre-check on `idempotency_key` (from cart `checkout_token`) + DB-unique fallback
  inside a savepoint catching IntegrityError.
- **Side effects:** ORDER_PLACED SMS via `transaction.on_commit`.
- **Tests:** `orders/tests/test_order_service.py`, `test_checkout_*.py`, `test_cat002_checkout_valuation.py`.

## Flow 3a — Storefront payment, SIMULATION (LEGACY, VERIFIED)
```
checkout/payment-start → (if no gateway config & PAYMENTS_SIMULATION_ENABLED)
    → checkout/payment-callback/<status>  (status is client-controlled path segment)
    → payment_service.simulate_payment
```
- **Writes:** Transaction; **Order.payment_status** = PAID/FAILED (direct save); on success →
  `change_order_status(PROCESSING)`.
- **Gate:** Http404 unless `PAYMENTS_SIMULATION_ENABLED` (defaults to DEBUG). Prod-disabled.
- **Concurrency:** `@atomic` but **no `select_for_update` on Order** before the already-paid check.
- **Side effects:** PAYMENT_SUCCESS/FAILED SMS on_commit.
- **Tests:** `orders/tests/test_payment_service.py`.

## Flow 3b — Storefront payment, REAL GATEWAY (NEW, VERIFIED)
```
checkout/payment-initiate → gateway_payment_service.initiate_payment → adapter.create_payment → redirect
gateway returns → checkout/gateway/callback/<attempt_id> → gateway_payment_service.process_callback_and_verify
```
- **initiate:** creates PaymentAttempt; guards already-paid/config/idempotency; COD marks attempt
  SUCCEEDED but does NOT mark order paid.
- **callback (authoritative):** pre-check outside atomic; idempotent if attempt `is_final`; if order
  already PAID → mark this attempt CANCELED; **server-to-server** `adapter.verify_payment`; on success
  `@atomic` + `select_for_update` re-lock + conditional `Order.objects.filter(...PENDING).update(payment_status=PAID)`;
  creates legacy Transaction (back-compat); `change_order_status(PROCESSING)`; PAYMENT_SUCCESS SMS.
- **Idempotency:** attempt `is_final` short-circuit; conditional update on PENDING only.
- **Tests:** `orders/tests/test_gateway_payment_service.py`.

## Flow 4 — Manual refund / return (VERIFIED)
```
dashboard refund → refund_service.execute_order_refund (idempotent on key; GATEWAY method raises)
return complete → return_service.complete_return → refund_service.execute_order_refund(key="return:<pk>")
```
- **Writes:** Refund(+Item); if fully refunded → Order.payment_status=REFUNDED; optional restock.
- **Tests:** `orders/tests/test_refund_service.py`, `test_return_service.py`.

## Flow 5 — Trial store provisioning (VERIFIED)
```
portal store-create view (session idempotency token) → provisioning_service.provision_trial_store
```
- **Single `@atomic` across 4 apps:** enforce per-owner store cap → create Store (ACTIVE + unique
  platform_code) → assert admin-subdomain namespace → ACTIVE OWNER StoreMembership → VERIFIED
  GENERATED_TRIAL StoreDomain `{code}.{suffix}` → `ShopSettings.provision_for` → default Warehouse →
  optional industry template → `provision_default_subscription` (fail-open) → audit.
- **Tests:** `portal/tests/test_provisioning.py`, `test_store_create_view.py`, `test_onboarding.py`.

## Flow 6 — Owner authentication (OTP + step-up) (VERIFIED)
```
portal login → owner_otp_service.request_otp (rate-limited, hashed code, SMS) → verify-OTP → verify_otp (single-use)
sensitive action → step_up_service.begin_challenge/confirm_challenge (session-scoped, TTL 900s)
```
- **Side effects:** OTP SMS via central platform provider.
- **Tests:** `portal/tests/test_owner_otp.py`, `test_owner_auth.py`, `test_unified_login.py`, `test_step_up_billing.py`.

## Flow 7 — SaaS billing: invoice → payment → subscription activation (VERIFIED)
```
plan purchase → plan_change_billing_service.start_plan_change → invoice_service.create/open
             → payment_flow_service.start_payment (provider session; invoice payment_pending)
provider webhook → billing/webhook/<provider> → webhook_service.ingest_webhook (verify sig, dedup)
             → payment_flow_service.process_webhook_event → confirmation_service.confirm_payment
             → _activate_or_renew → subscription_service.activate/renew/change_plan_version
```
- **Txn/lock:** every step `@atomic` + `select_for_update` on the mutated aggregate.
- **Idempotency:** attempt `idempotency_key` unique; webhook `(provider, external_event_id)` unique
  + `select_for_update` + IntegrityError race fallback; confirm short-circuits already-succeeded/paid;
  amount + currency validated against the invoice, not the browser.
- **Non-proof principle:** browser return is never proof; only signed webhook or server-side pull confirms.
- **Tests:** `billing/tests/test_confirmation_activation.py`, `test_webhook_inbox.py`, `test_plan_change_billing.py`.

## Flow 8 — SaaS renewal + dunning (cron) (VERIFIED)
```
generate_subscription_renewals → renewal_service.generate_renewals/_generate_one
    (@atomic; select_for_update subscription; apply+delete ScheduledPlanChange via change_plan_version;
     create+open renewal invoice; idempotent via uniq_renewal_invoice_per_period + IntegrityError fallback)
process_subscription_dunning → dunning_service.process_dunning/_process_invoice
    (stage 0 → invoice past_due + subscription enter_grace; final stage → subscription suspend + invoice uncollectible)
```
- **Lock order:** documented canonical Subscription → ScheduledPlanChange.
- **Tests:** `billing/tests/test_renewals.py`, `test_dunning_cancellation.py`.

## Flow 9 — Subscription lifecycle scan (cron) (VERIFIED)
```
evaluate_subscription_states → subscription_service.evaluate_subscription_states
    → _due_action / _apply_due_action → guarded transitions (trial end, grace, past_due, expire)
```
- **Tests:** `subscriptions/tests/test_state_machine.py`, `test_management_and_isolation.py`.

## Flow 10 — Storefront layout edit → publish (R4, VERIFIED)
```
R4 editor (JS) → storefront-builder/r4/mutate/ → r4_mutation_service
    (@atomic: lock StorefrontLayout, resolve draft, compare base_revision (optimistic),
     dispatch one allowlisted mutation, bump edit_revision, record edit history)
publish → storefront-builder/r4/publish/ → layout_service.publish
    (@atomic: ensure containers → delete edit history → compute fingerprint → DRAFT→PUBLISHED
     → previous PUBLISHED→ARCHIVED → swap layout pointers → uses_visual_storefront_layout=True)
```
- **Concurrency:** optimistic `edit_revision` token; publish is pointer-swap.
- **Restore:** always creates a NEW draft (never publishes directly).
- **Editor gate:** legacy `views.py` mutations fail-closed when `r4_editor_enabled=True` (default).
- **Tests:** `storefront_builder/tests/test_r4_*`, `test_layout_preset_registry.py`, `test_render_service.py`.

## Flow 11 — Public storefront render (VERIFIED)
```
GET / (resolved Store) → catalog.views.home → render_service.build_render_items(version, store)
    (reads published StorefrontLayoutVersion; falls back to legacy hard-coded home if
     uses_visual_storefront_layout is False) → storefront_shell.html + content context processors
```
- **Tests:** `storefront_builder/tests/test_render_service.py`, `test_storefront_page.py`.

## Flow 12 — Custom domain verification (VERIFIED)
```
portal custom-domain begin-verify → domain_verification_service.begin_dns_verification (PENDING + token)
check → check_dns_verification (real DNS TXT match → VERIFIED)
final-check → refresh_custom_domain_readiness (real A/CNAME routing + SSL socket)
activate → activate_custom_domain (set primary, retire old primary; keep old platform_subdomain for 301)
```
- **External:** DNS TXT (dnspython) + SSL socket connect; never self-marked verified.
- **Tests:** `stores/tests/test_domain_verification_service.py`, `portal/tests/test_custom_domain_views.py`.

## Flow 13 — SMS send (VERIFIED)
```
send_event_sms / send_raw_sms → _dispatch
    (create SmsLog PENDING → reserve credits (OTP overdraft) → OTP routes to platform provider,
     else resolved backend (SmsRasti enqueues SmsOutboxItem) → refund credits on failure)
SmsRasti device → sms/poll (claim PENDING → SENDING) → sms/ack (→ SENT/FAILED)
```
- **Tests:** `sms/tests/*` (send_event_sms, credit/overdraft, gateway poll/ack).

## Flow 14 — Store deletion (soft) → purge (VERIFIED)
```
portal delete (+step-up) → deletion_service.request_deletion (status→CLOSED, schedule purge, notify)
cron purge_deleted_stores --execute → deletion_service.purge_due_stores (real Store.delete per store,
    PlatformAuditLogEntry written BEFORE delete since store-owned AuditLogEntry cascades)
```
- **Tests:** `stores/tests/test_deletion_service.py`, `test_purge_deleted_stores_command.py`.

---

### Cross-flow observations
- **Two payment confirmation designs** coexist (Flow 3a vs 3b) writing the same `Order.payment_status`.
- **Non-happy-path discipline is strong** in billing/subscriptions/gateway paths (locks, idempotency,
  webhook dedup) but weaker in the simulation/refund order-payment path (no Order lock; doc 10).
