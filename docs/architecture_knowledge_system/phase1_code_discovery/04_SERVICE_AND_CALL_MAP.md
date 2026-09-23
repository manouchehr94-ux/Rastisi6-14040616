# 04 — Service and Call Map

Important services with responsibility, reads/writes, transaction boundary, external side
effects, and callers. Evidence class legend as in doc 01. There are 145 service files; this
document covers the architecturally significant ones (financial, tenancy, presentation).

---

## 1. Orders (storefront money) — `apps/orders/services/`

| Symbol | Responsibility | Writes | Txn / lock | Side effects | Called by |
|---|---|---|---|---|---|
| `order_service.create_order_from_cart` | **Only** production Order creator | Order, OrderItem, OrderStatusHistory(initial), Coupon.used_count(+=1), CartItem.unit_price | `@atomic`; `select_for_update` Product/Variant then Cart then CartItem (membership fence) | reserves+consumes inventory (catalog); ORDER_PLACED SMS on_commit | checkout views |
| `order_service.change_order_status` | **Canonical** Order.status transition | Order.status/tracking, OrderStatusHistory; on CANCELED → restock | `@atomic`; guards module `ALLOWED_TRANSITIONS` + FINAL_STATUSES | status SMS on_commit | dashboard `order_detail`, payment_service, gateway_payment_service |
| `payment_service.simulate_payment` *(LEGACY)* | Simulated payment | Transaction, **Order.payment_status** (direct save), calls change_order_status | `@atomic` (no select_for_update on Order) | PAYMENT_SUCCESS/FAILED SMS on_commit | simulation views (gated by `PAYMENTS_SIMULATION_ENABLED`) |
| `gateway_payment_service.initiate_payment` *(NEW)* | Start real gateway payment | PaymentAttempt | `@atomic` | adapter.create_payment (external) | payment_initiate view |
| `gateway_payment_service.process_callback_and_verify` *(NEW)* | **Authoritative** confirmation | conditional `Order.objects.filter(PENDING).update(payment_status=PAID)`; PaymentAttempt.status; legacy Transaction (back-compat) | `@atomic` + `select_for_update` re-lock; idempotent on `is_final` | adapter.verify_payment (server-to-server); PAYMENT_SUCCESS SMS | gateway callback view |
| `refund_service.execute_order_refund` | Manual refund | Refund(+Item); PAID→REFUNDED Order.payment_status; optional restock | `@atomic`; idempotent on key | — | dashboard refund, return_service.complete |
| `return_service.*` | Return lifecycle | ReturnRequest(+Item) guarded transitions | `@atomic` + `select_for_update` items | complete → refund_service | dashboard returns |
| `checkout_service.finalize_order` | Post-order cart teardown | **cart.items.all().delete()** (cross-domain) | within order flow | — | checkout |
| `tax_service`, `shipping_service`, `best_seller_service` | Pricing/quote/report helpers | (read-mostly) | — | — | order_service, dashboard |

**Adapters** `orders/gateways/`: abstract `PaymentGatewayAdapter` (create/build_redirect/verify;
adapters must NOT touch Order/PaymentAttempt state); `registry.get_adapter` (lazy zibal/cod, cached).

## 2. Subscriptions — `apps/subscriptions/services/`

| Symbol | Responsibility | Writes | Txn / lock | Called by |
|---|---|---|---|---|
| `subscription_service._transition` + public transitions (`create/start_trial/activate/enter_grace/mark_past_due/suspend/resume/cancel_*/expire/renew/change_plan_version`) | **The** StoreSubscription state machine (module `ALLOWED_TRANSITIONS`, ADR-66) | StoreSubscription.status/period/plan_version; SubscriptionEvent; sets `is_current=False` on terminal | `@atomic`; `select_for_update` subscription; legality check; idempotent no-op | billing services, plan_change_service, provisioning, cron command |
| `subscription_service.evaluate_subscription_states` | Cron scan → due actions | via transitions | `@atomic` per subscription | `evaluate_subscription_states` command |
| `subscription_service.provision_default_subscription` | Fail-open default plan | StoreSubscription | `@atomic` | provisioning_service |
| `plan_change_service.preview_plan_change` | Read-only preview + `_preview_token` fingerprint | none | — | billing plan-change, portal |
| `plan_change_service.execute_platform_admin_plan_override` | Staff override | delegates change_plan_version | `@atomic`, select_for_update | platform admin |
| `entitlement_service`, `enforcement`, `usage_service`, `legacy_service` | Entitlement resolution/enforcement/usage/legacy provisioning | UsageRecord (usage) | — | dashboard banners, export budget, provisioning |

## 3. Billing — `apps/billing/services/`

All mutation services use `@transaction.atomic` + `select_for_update` on the mutated aggregate.

| Symbol | Responsibility | Writes | Cross-domain | Called by |
|---|---|---|---|---|
| `invoice_service` (`create/open/void/add_line`) | Invoice lifecycle | SubscriptionInvoice(+Line) | — | renewal, plan_change_billing, admin |
| `attempt_service.create_attempt` | Billing payment attempt (idempotent) | SubscriptionPaymentAttempt | — | payment_flow |
| `confirmation_service.confirm_payment` | **The** "payment happened" path | attempt→SUCCEEDED; invoice amount_paid/PAID; then `_activate_or_renew` | **drives subscription_service** activate/renew/change_plan | payment_flow, admin mark-paid |
| `payment_flow_service` (`start_payment/confirm_from_provider_verification/process_webhook_event`) | Provider session + verification pull + webhook processing | attempt/invoice payment_pending | → confirmation_service | webhook view, portal checkout |
| `webhook_service.ingest_webhook` | Signature-verified idempotent inbox | BillingWebhookEvent | — | billing_webhook view |
| `renewal_service.generate_renewals` | Pre-due renewal invoices | invoice; applies+deletes ScheduledPlanChange | → subscription_service.change_plan_version | `generate_subscription_renewals` command |
| `dunning_service.process_dunning` | Retry/escalation | invoice past_due/uncollectible; DunningState | → subscription_service enter_grace/suspend | `process_subscription_dunning` command |
| `cancellation_service.cancel_subscription_billing` | Cancel + void unpaid | invoices void | → subscription_service cancel_* | portal/admin |
| `refund_service` (`request_refund/complete_refund_manually`) | Billing refund | SubscriptionRefund; invoice refunded/partially | provider.refund_payment (external) | admin |
| `credit_note_service`, `numbering_service`, `account_service`, `period_utils`, `consistency_service` | Credit notes / numbering (BillingSequence) / account snapshot / period math / read-only checks | — | — | various |
| `plan_change_billing_service.start_plan_change` | **Canonical merchant plan-change** entry | upgrade→PLAN_CHANGE invoice; downgrade→ScheduledPlanChange | — | portal billing |

**Providers** `billing/providers/`: `registry.get_provider`/`active_provider_code`/`webhook_secret`;
`manual` (default, no auto-capture), `zibal`.

## 4. Tenancy — `apps/stores/services/` + `resolution.py`

| Symbol | Responsibility | Writes | Side effects |
|---|---|---|---|
| `resolution.resolve_store_for_hostname` | **Sole** authoritative Host→Store resolver | none | — |
| `resolution.resolve_store_for_admin_host` | Admin-subdomain→Store (separate path) | none | — |
| `publication_service.is_publicly_visible` | **Sole** reader of `onboarding_completed_at` for visibility; combines Store.status + onboarding + subscription entitlement (fail-open) | none | local import subscriptions |
| `store_status_service.suspend_store/activate_store` | Suspension | Store.status/suspended_* | audit |
| `domain_verification_service.*` | Custom-domain verification lifecycle | StoreDomain verification/routing/tls fields | **real DNS TXT + SSL socket** (external) |
| `platform_code_service.generate_unique_platform_code` | 9-char code (collision-checked) | none | — |
| `deletion_service.request/cancel/purge` | Soft delete + scheduled purge | Store soft-delete fields; real delete on purge | PlatformAuditLogEntry; notify_security_event |
| `membership_service.add_staff_member/change_role/revoke/reactivate/transfer_ownership` | Staff/roles | StoreMembership; creates is_staff User | subscription seat enforcement; audit |
| `ownership_transfer_service.initiate/accept/cancel` | Two-party OTP transfer | StoreOwnershipTransfer; memberships | owner_auth_service (creates User); notify |
| `handle_service.claim/rename` | Platform subdomain handle | StoreDomain (VERIFIED PLATFORM_SUBDOMAIN) | — |

## 5. Portal — `apps/portal/services/`

| Symbol | Responsibility | Cross-domain writes |
|---|---|---|
| `provisioning_service.provision_trial_store` | Full trial store creation (single `@atomic`) | **stores + core(ShopSettings) + catalog(Warehouse/template) + subscriptions** |
| `owner_auth_service` | Owner email/password + `get_or_create_owner_by_phone` (shared identity) | creates auth User + OwnerProfile |
| `owner_otp_service.request_otp/verify_otp` | Owner OTP (hashed, rate-limited, single-use) | SMS (via owner_sms_service) |
| `step_up_service` | Session-scoped step-up OTP for sensitive actions | — |
| `owner_sms_service`, `platform_config_service`, `handoff_service`, `turnstile_service` | Central SMS provider / platform config accessor / admin handoff tickets / Turnstile verify | (owner_sms_service is the platform SMS path) |
| `session_service` | re-export of `core.services.session_service.apply_remember_me` (shim) | — |

## 6. Customers / Cart / Core / SMS / Notifications (key services)

| Symbol | Responsibility | Notes |
|---|---|---|
| `customers.auth_service.signup/create_account_for_guest/authenticate_*/merge_guest_cart` | Customer auth + guest cart merge | merge uses select_for_update fence; WELCOME SMS on_commit |
| `cart.cart_service.get_cart/add_item_to_cart/reprice_cart_items` | Cart mutation | `@atomic` + membership-fence locking; price from catalog resolver |
| `cart.pricing/coupon_service/gift_wrap_service` | Totals/coupons/gift wrap | server-authoritative |
| `core.export_service.run_export` | Synchronous CSV export | subscription export budget; formula-injection-safe CSV; audit |
| `dashboard.import_service` | Synchronous CSV import | writes catalog via catalog services + ImportJob (note: import lives in dashboard, export in core — asymmetric, doc 13) |
| `core.audit_service.record_audit_event` | Idempotent, redacting audit writer | "services (not views) must call this" |
| `sms.sms_service._dispatch` | **Single** Store-SMS funnel: create SmsLog, reserve credits, route OTP to platform, backend send, refund on fail | public: `send_event_sms`, `send_raw_sms`, `send_test_sms`, retries |
| `notifications.notification_service.enqueue/deliver_pending/notify_security_event` | Persistent outbox; `deliver_pending` is the only sender | driven by `process_notification_outbox` command |

## 7. Storefront presentation — `apps/storefront_builder/services/` (18 files)

| Symbol | Responsibility | Writes | Txn |
|---|---|---|---|
| `layout_service` (`get_or_create_draft/discard_draft/publish/restore_version/_clone_version_content`) | **Canonical** draft/publish/restore + header/footer/appearance validators | StorefrontLayoutVersion status/pointers, sections, edit history | `@atomic`; rate-limited |
| `r4_mutation_service` | **Single** optimistic mutation boundary for R4 editor (base_revision check, one allowlisted mutation, bump edit_revision, record history) | sections/containers/appearance | one `@atomic` per mutation |
| `preset_service` | Apply LayoutPreset / A8 Ready Template to a Draft | sections/containers, provenance, baseline | `@atomic`, validate-before-write |
| `appearance_authority_service` + `storefront_appearance.persistence.persist_store_appearance_manifest` | Typed appearance persistence (draft-only, `ImmutableStoreAppearanceError` otherwise); mirrors selectors into header/footer_config | appearance_config + mirrored header/footer keys | — |
| `render_service.build_render_items/build_page_render_items` | Read/render path | none | — (consumed by catalog.home + storefront preview) |
| `container_service`, `section_structure_service`, `section_data_service`, `bootstrap_service`, `edit_history_service`, `design_lab_service`, `golden_reference_service`, `template_preview_service`, `page_resolution_service`, `row_service`, `section_appearance_service` | container/cell CRUD, section structure, data-source resolution, first-draft seeding, undo/redo, design lab, golden reference, previews, page resolution, legacy 12-col rows | sections/containers | mixed |

## 8. Canonical call chain (representative)

```
HTTP request
  → PlatformHostRoutingMiddleware (choose urlconf)
  → StoreResolutionMiddleware (set request.store)
  → view (dashboard / storefront / portal)
      → domain service (order_service / subscription_service / layout_service / …)
          → model mutation (guarded, atomic, locked)
          → optional external adapter (payment gateway / DNS / SMS provider)
      → transaction.on_commit side effect (SMS)
  → response
```
