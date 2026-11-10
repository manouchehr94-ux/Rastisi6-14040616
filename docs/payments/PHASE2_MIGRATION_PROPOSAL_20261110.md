# Phase 2: proposed schema changes (NOT created, NOT applied)

**Status: proposal only.** No migration file was created or applied on `kiro/financial-security-remediation-20261110`.
`manage.py makemigrations --check --dry-run` reports "No changes detected" on that branch. Nothing below may be created, applied
or deployed without separate explicit approval.

Everything that could be done safely without a schema change is already implemented (see the remediation report). This document
covers only the parts that were **paused** because they need a schema change, and the interim behaviour that is in the code today.

## 1. What is paused and why

| Item | Why it needs a migration | Interim behaviour in the code today |
|---|---|---|
| Real `PROCESSING` and `UNKNOWN` refund statuses | `SubscriptionRefund.status` choices change (Django records choices in migrations). | An ambiguous outcome is `PENDING` with `failure_code="unknown_outcome"`. It behaves as UNKNOWN will: the amount stays reserved, the provider is never called again for that row, new refunds on the invoice are refused, only a person with a bank reference of at least 6 characters can resolve it. |
| Stable provider request key, claim time, last provider outcome on a refund | New columns. | The existing unique `idempotency_key` doubles as the provider key. There is no claim timestamp: `created_at` is used by `recover_stale_refunds`. |
| SMS purchase refund: freeze credits before the provider call, reverse only after confirmed success | Needs a place to hold frozen credits (new column or table) and new ledger kinds. | **Unchanged and still unsafe.** `sms_purchase_payment_service.refund_purchase` reverses the credits first and calls the provider in the same transaction. A definite provider error rolls the reversal back (correct). An ambiguous outcome or a failure after a successful provider call can leave credits and money out of step. **Do not enable automatic SMS refunds with Pasargad, Saman or Mellat until this is done.** Zibal and other manual providers return "manual", so they are not exposed. |

## 2. Proposed changes

### 2.1 `billing.SubscriptionRefund`

* `Status` gains `PROCESSING = "processing"` and `UNKNOWN = "unknown"` (choices only, no DDL on PostgreSQL).
* New nullable or defaulted columns (additive, safe to deploy before the code uses them):
  * `provider_request_key` `CharField(100, blank=True, default="")`. Set to `idempotency_key` when the intent is committed. Index it.
  * `claimed_at` `DateTimeField(null=True, blank=True)`. Set when the provider call starts, so a stale `PROCESSING` row is recognised exactly.
  * `last_provider_outcome` `CharField(32, blank=True, default="")` (`success`, `declined`, `timeout`, `transport`, `lost_response`).
* `OPEN_STATUSES` and `refunded_total` include `PROCESSING` and `UNKNOWN`.
* Data migration (idempotent, reversible as a no-op): rows with `status="pending"` and `failure_code="unknown_outcome"` become `UNKNOWN`.
* Suggested index: `(status, failure_code)` for the health check and the recovery job.

### 2.2 SMS credit freeze (`sms`)

Preferred design (smallest change that is correct):

* `SmsCreditBalance.frozen_credits` `PositiveIntegerField(default=0)`. Spendable credits are `credits - frozen_credits`. Every consumer
  of credits (`balance_service` debit paths) must use the spendable amount.
* `SmsCreditLedger.Kind` gains `REFUND_HOLD = "refund_hold"` and `REFUND_RELEASE = "refund_release"`. `PURCHASE_REVERSAL` stays the
  final reversal and stays unique per purchase.
* `SmsPackagePurchase.Status` gains `REFUND_PENDING = "refund_pending"`.
* Flow once approved: (1) one transaction freezes the credits and records the refund intent (fails if the credits are already
  consumed: the existing finance-review path); (2) provider call with no transaction; (3) success: final reversal exactly once, release
  the hold; definite decline: release the hold; ambiguous: keep the hold, mark UNKNOWN, finance resolves with a bank reference.

Alternative: a separate `SmsRefundHold` table (purchase one-to-one, credits, state). Cleaner audit, but every credit read must join it.
Not preferred.

### 2.3 Not needed, and why

* **Permission `billing.reinstate_financial_suspension`.** Reinstatement is restricted to platform superusers, and a superuser holds
  every permission. The constant is checked with `has_perm` and no `Permission` row exists. Create the row (an `AlterModelOptions`
  migration) only if finance wants to delegate reinstatement to a non-superuser role, which contradicts the current decision.
* **A new `SubscriptionEvent` type or a `suspension_kind` column.** A financial suspension is the `suspended` event with
  `metadata.kind == "financial"` (event type stays within its 20-character limit). An indexed column would only be an optimisation.
* **Duplicate-payment resolution.** Stored in `provider_extra`, no change.

### 2.4 Optional indexes

* `BillingWebhookEvent(processing_status, created_at)` for `reprocess_billing_webhooks`.
* `SubscriptionEvent(subscription, event_type)` is already served by the existing relations at current volumes.

## 3. Rollout and rollback (when approved)

1. Release N: migrations only (all additive), code unchanged. Rollback: redeploy the previous release; columns are ignored.
2. Release N+1: code that writes the new statuses and columns, plus the data migration. Rollback: the data migration is a no-op
   in reverse; rows already `UNKNOWN` are shown by old code as an unlabelled status, and `recover_stale_refunds`/finance can still
   resolve them by hand, so deploy the code that understands `UNKNOWN` before creating any.
3. Release N+2 (SMS): enable the freeze flow behind a setting, default off, and switch on per environment after QA.

Back up the database before step 1. Run each step on a copy of production data first.

## 4. Test plan for the approved migration

PostgreSQL disposable database and synthetic gateways only: provider success then database failure; timeout after success;
concurrent refund submissions; over-refund race; stale `PROCESSING` recovery; SMS freeze then success; freeze then decline (hold
released); freeze then ambiguous (hold kept); consumed credits refused; credit reversal exactly once; migration forwards and backwards
on a copy of production-shaped data.

## 5. Still unverified regardless of schema

* Whether Pasargad, Saman and Mellat honour a refund idempotency key or offer a refund inquiry. Until verified, a provider call that
  may have succeeded must be treated as UNKNOWN and reconciled manually (this is what the code does).
* The production scheduler (F-03): see `PLATFORM_BILLING_JOBS_RUNBOOK_20261110.md`.
