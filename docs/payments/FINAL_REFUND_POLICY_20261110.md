# Final refund policy for platform payments (2026-11-10)

**Owner decision (approved):** no automatic refund after a successful platform payment. Every refund request for a platform-owned payment
(subscription purchase or renewal, SMS credit package, any other platform product) is reviewed and approved by the platform administrator.
Approval does not execute anything. The money is returned manually through an authorised banking channel, and the verified outcome is
recorded in RastiSi with a bank reference.

Not touched: tenant merchants' customer-order refunds (`apps/orders`), payment creation, server-side verification, settlement
reconciliation, webhook recovery, idempotent fulfilment, payment cancellation / authorisation reversal of an unsettled payment.
Only `refund_payment` of an already successful **platform** payment is governed.

## What enforces it (backend, not UI)

| Layer | File | Behaviour |
|---|---|---|
| Policy | `apps/billing/providers/bank_refund_policy.py` | `AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED = False` is a **code constant**. `automatic_refund_allowed(any provider)` is `False` while it is not exactly `True`. An environment variable can no longer enable a call. |
| Refund request | `refund_service._execute_with_provider` | Stops before the provider is resolved, for every provider. The row becomes `PENDING` with marker `automatic_refund_disabled`. |
| Duplicate-payment refund | `duplicate_payment_service.refund_duplicate` | Same stop. Outcome `pending_manual`, no provider call. |
| Provider | `AdapterBackedBillingProvider.refund_payment` | Stops before the adapter, credentials or network, for every adapter-backed gateway. |
| SMS package refund | `sms_purchase_payment_service.sms_refunds_enabled` | Needs `RASTISI_SMS_REFUND_ENABLED=True` **and** the constant. Credits are therefore never reversed by a configuration change alone. |
| Django admin | `SubscriptionRefundAdmin` | Read-only (no change permission), so a status cannot be edited around the service. |
| Recovery job | `recover_stale_refunds` | Only marks rows `unknown`; never calls a provider (unchanged). |

## Behaviour per gateway (platform payments)

| Gateway | Automatic refund / reverse | What a refund request does |
|---|---|---|
| Pasargad | **Disabled** (no call) | Recorded, awaits review |
| Saman | **Disabled** (no call) | Recorded, awaits review |
| Mellat | **Disabled** (no call) | Recorded, awaits review |
| Zarinpal, SnappPay and other adapter-backed gateways | **Disabled** (no call; previously not gated) | Recorded, awaits review |
| Zibal | No refund API exists in the integration (never called) | Recorded, awaits review |
| Manual / card-to-card | Manual by nature | Recorded, awaits review |

Nothing was tested against a bank. No real API was called.

## Manual review and completion workflow (no schema change)

States are derived from the existing `status` plus a marker in `failure_code` (the same interim approach already used for
`unknown_outcome`). `refund_service.review_state()` returns them; the invoice page in Platform Admin shows them.

| Administrator-facing state | `status` | `failure_code` | Reserved amount |
|---|---|---|---|
| Refund requested (transient) | `requested` | | yes |
| Awaiting manual review | `pending` | `automatic_refund_disabled` (or empty on historical rows) | yes |
| Approved for manual processing | `pending` | `manual_refund_approved` | yes |
| Externally completed and verified | `succeeded` | (marker kept) + reference in `failure_message` | counted as refunded |
| Rejected | `cancelled` | `manual_rejected` | released |
| Unknown / needs reconciliation | `pending` | `unknown_outcome` | yes |
| Failed / proven not executed | `failed` | | released |

1. **Request** (`payment-invoice-refund`): records the request. No provider call.
2. **Approve** (`payment-refund-approve`, `approve_refund_for_manual_processing`): records the decision and the actor. No provider call, no
   money movement, no change to the invoice, subscription, coupon or SMS credits. Idempotent. Not allowed for an unknown outcome.
3. **Pay out manually** in the bank's own panel, outside RastiSi.
4. **Complete** (`payment-refund-complete`, `complete_refund_manually`): allowed only for an approved refund (or an unknown one being
   reconciled) and only with a bank reference of at least 6 characters. Only this step moves the invoice to `REFUNDED` /
   `PARTIALLY_REFUNDED`, reverses the coupon where the coupon policy says so, and applies the F-08 subscription suspension. A repeat
   (same or different reference) returns the first completion and changes nothing.
5. **Reject** (`payment-refund-reject`, `reject_refund`): releases the reserved amount, needs a reason, no provider call. Not allowed for an
   unknown outcome.
6. **Not executed** (`resolution=not_executed` on the complete endpoint, `fail_refund_manually`): proof (reference) that nothing was paid
   releases the reservation. Unchanged.

Ambiguous or already initiated refunds stay parked: an `unknown_outcome` row cannot be approved or rejected, blocks any new refund request
for the invoice, is never retried automatically, and is closed only with a bank reference (completed or proven not executed).

Duplicate-payment surplus keeps its existing two-step flow: request (`pending_manual`, no call), then `mark_resolved` with a mandatory
reference.

## Intentionally disabled

* Every automatic post-payment refund / reverse call to any provider for platform payments.
* `RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS` has no effect while the constant is `False`. Do not set it.
* SMS package refunds (`RASTISI_SMS_REFUND_ENABLED` stays off; additionally locked by the constant). The existing form stays hidden.

## Remaining gaps

* **No migration was added.** Approval and rejection ride on `PENDING`/`CANCELLED` plus a marker in `failure_code`. A dedicated status, an
  approver and approval time, and a separate reference field need a schema change (see `PHASE2_MIGRATION_PROPOSAL_20261110.md`). Until
  then the approver and time are in the audit trail (`billing.refund_approved_for_manual`), and the reference is in `failure_message`.
* **SMS package refunds have no manual workflow.** A refund of an SMS package needs the credit-freeze design (migration) so credits are
  reversed only after a verified outcome. Nothing is exposed meanwhile.
* The same person can request and approve; there is no four-eyes rule (needs a role model decision).
* Historical `PENDING` rows with no marker now need the approval event before they can be completed (they were completable directly
  before). They are not modified.
* Re-enabling any automatic path needs a code change to the constant plus a written bank contract (idempotency and result inquiry) and a
  sandbox test.
