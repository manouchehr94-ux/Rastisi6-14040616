# State Machine Index

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 09) / Phase 2 (doc 04)
open_decisions: DR-1
```

Every lifecycle/status machine and whether it is guarded. Authoritative detail: Phase 1
[`../phase1_code_discovery/09_STATE_MACHINES.md`](../phase1_code_discovery/09_STATE_MACHINES.md);
Phase 2 verification [`../phase2_validation/04_STATE_MACHINE_VALIDATION.md`](../phase2_validation/04_STATE_MACHINE_VALIDATION.md).

`ALLOWED_TRANSITIONS` tables exist (VERIFIED) in exactly: `orders/services/order_service.py`,
`orders/models.py` (ReturnRequest), `orders/services/return_service.py`,
`subscriptions/services/subscription_service.py`, `catalog/models.py`,
`catalog/services/transfer_service.py`, and `dashboard/services/orders_admin_service.py`
(re-uses the orders table for display — not a competing definition).

---

## Guarded by explicit transition table
| Machine | States | Table location |
|---|---|---|
| **Order.status** | pending→{processing,canceled}; processing→{shipped,canceled}; shipped→{delivered,canceled}; delivered/canceled terminal | `order_service.py:45`, enforced `:550` in `change_order_status` |
| **ReturnRequest.status** | requested/under_review/approved/rejected/in_transit/received/inspected/completed/cancelled | `orders/models.py:1047` (model-level), enforced in `return_service._transition` |
| **StoreSubscription.status** | pending/trialing/active/grace_period/past_due/suspended/cancelled/expired (TERMINAL={cancelled,expired}) | `subscription_service` module (`ALLOWED_TRANSITIONS`, ADR-66) |
| **WarehouseTransfer** | draft→requested→in_transit→received/cancelled | `catalog/models.py` + `catalog/services/transfer_service.py` |

## ⚠️ NOT guarded by a transition table
| Machine | States | Note |
|---|---|---|
| **Order.payment_status** | pending/paid/failed/refunded | **No `ALLOWED_TRANSITIONS`.** 3 writers; only the gateway path uses lock+conditional update; simulate/refund do plain saves. **Finding H1 / decision DR-1.** |

## Guarded per-service (no table)
| Machine | States | Guard |
|---|---|---|
| SubscriptionInvoice.status | draft/open/payment_pending/paid/past_due/void/uncollectible/refunded/partially_refunded | `is_payable`/`is_financially_locked` frozensets per service |
| SubscriptionPaymentAttempt.status | created/pending/requires_action/succeeded/failed/cancelled/expired | `is_final` + confirmation idempotency |
| PaymentAttempt.status (orders) | created→requesting→redirect_ready→pending→{succeeded,failed,canceled,expired} | `is_final` checks |
| Refund.status (orders) | pending/approved/processing/succeeded/failed/cancelled | final-state checks; GATEWAY method raises |
| Store.status | provisioning→active→suspended→closed | `store_status_service` / `deletion_service` single-service writers |
| StorefrontLayoutVersion.status | draft→published→archived | `layout_service.publish` pointer-swap; per-draft appearance immutability guard |
| StoreDomain verification/routing/tls | unverified→pending→{verified,failed}; routing/tls unchecked/… | `domain_verification_service` + 5 DB CheckConstraints |
| BillingWebhookEvent.processing_status | received→{processed,failed,ignored} | `(provider, external_event_id)` unique dedup |
| StoreMembership.status | invited→active→revoked | constraints require accepted_at/revoked_at |
| WarehouseTransfer / InventoryReservation / IndustryTemplate.Readiness / StoreTemplateUpdate | (per doc 09) | service-guarded |

## Orthogonal / non-status lifecycles
- **Product** has two independent axes: `status` (draft/active/inactive) + `publish_at` +
  `visibility`; and `is_draft_placeholder` (True→False build lifecycle). Not a single machine.
- **Store.onboarding_stage** (identity→industry→branding→review→done) is a soft progress pointer,
  not a hard lock; only REVIEW sets `onboarding_completed_at`.

## Derived machine (OBSERVATION, MEDIUM)
"Is this store publicly visible?" is derived from ≥5 signals across 3 apps (`Store.status`,
`onboarding_completed_at`, `StoreDomain` verification/routing, `StoreSubscription`/entitlement),
reconciled by `stores.publication_service` which **fails open** (AccessState.NONE → ACTIVE_PAID).

---
The most important takeaway: **`Order.payment_status` is the one important lifecycle field with no
guarded transition machine (H1 / DR-1).** Any change touching payment state must account for all
three writers.
