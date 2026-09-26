# 09 — State Machines

For each lifecycle/status concept: states, mutation sites, whether transitions are guarded,
terminal states, and tests. Evidence class legend as in doc 01.

Six `ALLOWED_TRANSITIONS` tables were located in code (VERIFIED via grep):
`apps/catalog/models.py`, `apps/catalog/services/transfer_service.py`,
`apps/dashboard/services/orders_admin_service.py` (re-uses orders' table),
`apps/orders/models.py`, `apps/orders/services/return_service.py`,
`apps/orders/services/order_service.py`, `apps/subscriptions/services/subscription_service.py`.

---

## 1. Order.status (orders) — GUARDED — VERIFIED
- **States:** pending → {processing, canceled}; processing → {shipped, canceled}; shipped →
  {delivered, canceled}; delivered/canceled terminal.
- **Guard:** module `ALLOWED_TRANSITIONS` + `FINAL_STATUSES` in `order_service.py`, enforced in
  `change_order_status` (the sole writer).
- **Transition sites:** create (initial pending), payment success (→processing),
  admin `order_detail`. On CANCELED → restock.
- **Tests:** `orders/tests/test_order_service.py` (valid/invalid/skip/same-state transitions).

## 2. Order.payment_status (orders) — **NOT GUARDED** — VERIFIED
- **States:** pending, paid, failed, refunded.
- **Guard:** NONE. No transition table; writers assign directly (simulate save; gateway conditional
  update on PENDING only; refund PAID→REFUNDED save).
- **Transition sites (3 writers):** `payment_service.simulate_payment`,
  `gateway_payment_service.process_callback_and_verify`, `refund_service.execute_order_refund`.
- **Smell:** the weakest state machine — see doc 06 §2, doc 13 (HIGH). Only the gateway path
  re-locks the Order; the other two do plain assignment.
- **Tests:** payment/refund service tests cover the individual writers but there is no single
  transition-legality test.

## 3. PaymentAttempt.status (orders) — GUARDED (via is_final) — VERIFIED
- **States:** created → requesting → redirect_ready → pending → {succeeded, failed, canceled, expired}
  (FINAL = the last four).
- **Guard:** `is_final` checks in `gateway_payment_service` short-circuit re-processing.
- **Tests:** `orders/tests/test_gateway_payment_service.py`.

## 4. ReturnRequest.status (orders) — GUARDED (model-level table) — VERIFIED
- **States:** requested/under_review/approved/rejected/in_transit/received/inspected/completed/cancelled.
- **Guard:** `ALLOWED_TRANSITIONS` + FINAL_STATUSES on the **model**, enforced in `return_service._transition`
  (`@atomic` + select_for_update).
- **Tests:** `orders/tests/test_return_service.py`.

## 5. Refund.status (orders) — GUARDED (final-state checks) — VERIFIED
- **States:** pending/approved/processing/succeeded/failed/cancelled; `method` manual/gateway
  (**gateway not implemented → raises**).
- **Guard:** guarded final states in `refund_service.record_refund_result`.
- **Tests:** `orders/tests/test_refund_service.py`.

## 6. StoreSubscription.status (subscriptions) — GUARDED (canonical) — VERIFIED
- **States:** pending/trialing/active/grace_period/past_due/suspended/cancelled/expired;
  TERMINAL = {cancelled, expired}.
- **Guard:** module `ALLOWED_TRANSITIONS` (ADR-66) in `subscription_service._transition`;
  `select_for_update`; idempotent no-op if same status + prior event key; sets `is_current=False`
  on terminal (backs the `uniq_current_subscription_per_store` partial constraint).
- **Cross-domain transition sites:** billing confirmation/dunning/renewal/cancellation — all call
  the service, never write status directly.
- **Tests:** `subscriptions/tests/test_state_machine.py`, `test_plan_change.py`, `test_manual_trial_controls.py`.

## 7. SubscriptionInvoice.status (billing) — GUARDED per-service (no single table) — VERIFIED
- **States:** draft/open/payment_pending/paid/past_due/void/uncollectible/refunded/partially_refunded.
- **Guard:** no single transition table; each service checks `is_payable` / `is_financially_locked`
  / status before writing (`FINANCIALLY_LOCKED_STATUSES`, `PAYABLE_STATUSES` frozensets).
- **Transition sites:** invoice_service (draft/open/void), confirmation (→paid), dunning
  (→past_due/uncollectible), refund (→refunded/partially), payment_flow (→payment_pending).
- **Tests:** `billing/tests/test_confirmation_activation.py`, `test_dunning_cancellation.py`, `test_credit_refund.py`.

## 8. SubscriptionPaymentAttempt.status (billing) — GUARDED (is_final + confirm idempotency) — VERIFIED
- **States:** created/pending/requires_action/succeeded/failed/cancelled/expired (FINAL set).
- **Tests:** `billing/tests/test_provider_and_attempts.py`.

## 9. BillingWebhookEvent.processing_status (billing) — VERIFIED
- **States:** received → {processed, failed, ignored}. Dedup via `(provider, external_event_id)` unique.
- **Tests:** `billing/tests/test_webhook_inbox.py`.

## 10. SubscriptionDunningState.status (billing) — VERIFIED
- **States:** active/resolved/exhausted; stage/attempt_count/next_retry_at.

## 11. Store.status (stores) — GUARDED-by-service (no table) — VERIFIED
- **States:** provisioning → active → suspended → closed.
- **Guard:** transitions via `store_status_service` (suspend/activate) and `deletion_service`
  (→closed); no explicit transition table but single-service writers.

## 12. Store.onboarding_stage (stores) — soft pointer — VERIFIED
- **States:** identity → industry → branding → review → done. Documented as a soft progress
  pointer, not a hard lock; only the REVIEW transition sets `onboarding_completed_at`.
- **Writer:** portal onboarding views (INFERRED).

## 13. StoreDomain verification lifecycle (stores) — GUARDED-by-constraints — VERIFIED
- **VerificationStatus:** unverified → pending → {verified, failed}; **RoutingStatus:**
  unchecked/connected/not_connected; **TlsStatus:** unchecked/ready/not_ready.
- **Guard:** 5 DB CheckConstraints tie status↔timestamps↔token; `domain_verification_service`
  performs real DNS/TLS checks; `retired_at` permanently removes routing eligibility.
- **Tests:** `stores/tests/test_domain_verification_service.py`.

## 14. StoreMembership.status / StoreOwnershipTransfer.status (stores) — VERIFIED
- Membership: invited → active → revoked (constraints require accepted_at/revoked_at).
  `uniq_active_owner_per_store` enforces one active owner.
- Ownership transfer: pending → {completed, expired, cancelled}.

## 15. Catalog lifecycles — VERIFIED
- **Product** — two orthogonal axes: `status` (draft/active/inactive) + `publish_at` + `visibility`
  (public/link_only) — publish-readiness gated by `validate_product_for_publish`; and
  `is_draft_placeholder` (True→False) build lifecycle (`product_draft_service`). Independent.
- **WarehouseTransfer** — `ALLOWED_TRANSITIONS` (draft→requested→in_transit→received/cancelled).
- **InventoryReservation** — active/consumed/released/expired/cancelled.
- **IndustryTemplate.Readiness** — draft→…→production_ready→deprecated/archived.
- **StoreTemplateUpdate** — pending→completed/failed.

## 16. StorefrontLayoutVersion.status (storefront_builder) — GUARDED-by-service — VERIFIED
- **States:** draft → published → archived.
- **Guard:** `layout_service.publish` (pointer swap, archives previous published); restore always
  makes a new draft; per-draft appearance immutability guard (`ImmutableStoreAppearanceError` if not draft).

## 17. ContentPage.status (content) — VERIFIED
- **States:** draft / published (CheckConstraint: published requires `published_at`).
- **Writer:** dashboard views directly (no service).

---

## Multiple-state-machine finding (AMBIGUOUS / smell — doc 13)
"Is this store publicly visible?" is derived from **≥5 interacting signals across 3 apps**:
`Store.status`, `Store.onboarding_completed_at`, `StoreDomain` verification/routing, and
`StoreSubscription.status`/entitlement. `stores.publication_service.PublicationState`
(onboarding/trial_private/trial_public/active_paid/restricted/suspended/inactive) is the
reconciliation point and the **only** authorized reader of `onboarding_completed_at` for visibility —
but it fails **open** (AccessState.NONE → ACTIVE_PAID) so legacy/test stores without a subscription
stay public. This derived machine is documented as a MEDIUM observation, not a defect, in doc 13.
