# Bank refund safety: Pasargad, Saman, Mellat (2026-11-10)

**Decision: automatic bank reversal/refund is DISABLED by default for all three gateways.** No official, current contract was found that
proves the reverse call is idempotent or that a timed-out call can be queried afterwards. Nothing was tested against a bank (no sandbox
or live call was allowed or made).

## Status of each gateway

| | Pasargad | Saman | Mellat |
|---|---|---|---|
| Operation the code calls | `POST /api/payment/reverse-transactions {invoice, urlId}` (reverse within the deadline; no refund-after-settlement is implemented) | `ReverseTransaction {RefNum, TerminalNumber}` | `bpReversalRequest` (SOAP) |
| Client idempotency key supported (documented) | Not found | Not found | Not found. The manual makes `orderId` unique per pay/refund request but says nothing about reversal repeats |
| Query the result of a timed-out reverse | Not found | Not found | Not found for a reversal. A refund-inquiry call exists only for `bpRefundRequest`, which the code does not use |
| Reverse window | Deadline only (public SDK text: about 2 hours) | Not found | Not settled and within 2 hours of the sale (manual) |
| Repeat-call signal | `13033` "reversed" (code treats as success) | Code `2` treated as success; documented only for verify | `48` "Transaction Has Been Reversed", `41` duplicate order id (manual) |
| Verified safe for automatic execution | **No** | **No** | **No** |
| Production status | **Automatic refund disabled.** Manual path only | **Automatic refund disabled.** Manual path only | **Automatic refund disabled.** Manual path only |

Sources and limits. Mellat: "Mellat PGW User Manual" v1.0 (August 2010), only reachable through a third-party mirror
(`storage.sepidan.net`), so it may be out of date; reversal text is in section 2.4.5, refund calls in 2.4.6 to 2.4.8, codes in table 10.
Pasargad: the repository's `PROVIDER_RESEARCH_MATRIX.md` (no refund-after-settlement endpoint documented) and the public Pasargad SDK README.
Saman: no accessible official page; the adapter's own constants are the only evidence. Findings from reading the adapter code:
* The platform's Mellat flow runs verify and then settle before reporting success (`adapter_backed.py`), while the manual allows reversal only
  for not-yet-settled sales. A Mellat reversal after confirmation is therefore expected to be refused (`45`/`46` family) in normal operation.
* Mellat's reversal reuses the sale's order id as the reversal `orderId`; the manual describes a separate id for each call.
* Saman code `2` and Pasargad code `13033` were counted as reverse success. Neither is documented as proof that this call reversed the payment.

## What is disabled, and how

`RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS` (environment, comma separated, **default empty**) is the only way to allow a bank call. Unknown or
malformed values enable nothing. **Do not set it in production** until a bank contract proves idempotency and result inquiry.

Enforced at three layers, so a direct service or provider call cannot bypass it (`apps/billing/providers/bank_refund_policy.py`):
1. `refund_service._execute_with_provider` stops before the provider is resolved.
2. `duplicate_payment_service.refund_duplicate` stops before the provider is resolved.
3. `AdapterBackedBillingProvider.refund_payment` stops before the adapter, credentials or network are touched. This also covers the SMS
   purchase refund (which is separately disabled by `RASTISI_SMS_REFUND_ENABLED`).

While disabled, a refund request for a payment taken through these gateways:
* creates a `SubscriptionRefund` row (or a duplicate-payment `pending_manual` resolution) in `PENDING` with `failure_code="automatic_refund_disabled"`;
* sends nothing to the bank, reserves the amount (a second key cannot refund it again), never sets `SUCCEEDED`, never sets the invoice to
  `REFUNDED`, and therefore never suspends the subscription (the F-08 effect happens only when finance completes the refund);
* does not release the reservation; finance either completes it or proves it did not happen.

## Manual reconciliation path (finance)

1. Platform Admin > invoice > the refund shows the warning. Refund the customer in the bank's merchant panel.
2. Complete it with the bank's reference (at least 6 characters; mandatory for this marker and for unknown outcomes):
   `payment-refund-complete` (`reference`). Only then does the invoice become `REFUNDED` and the F-08 suspension logic run.
3. If the bank panel shows no refund happened, record `resolution=not_executed` with proof to release the reserved amount.
4. Duplicate-payment surplus: refund in the panel, then `mark_resolved(... reference=...)`.

## Ambiguous or already-initiated refunds (rules that stay in force)

* One bank call per refund row, ever; a repeat with the same key returns the row without a call.
* A timeout, transport error, unexpected exception, lost response, process crash after the intent, or (new) any answer other than a plain
  success code `0` is `UNKNOWN`: the amount stays reserved, no new refund can be requested for the invoice, and the call is never retried
  automatically. `recover_stale_refunds` only marks rows; it never calls a bank.
* Existing rows created before this change are untouched.

## Verified here

Tests: `apps/billing/tests/test_bank_refund_disabled.py` (disabled default for each gateway, repeat/different key, direct provider call,
service-layer stop with a replaced registry, duplicate-payment refund, HTTP post, manual completion needing a reference, release with proof,
enabled path: success once, timeout, unexpected error, non-OK and unusual success codes, per-gateway enabling; PostgreSQL threads for
concurrent same-key and different-key requests, disabled and enabled). `test_phase2_refunds.AdapterUnknownOutcomeTests` now enables the
gateway explicitly.

## Still required before enabling any gateway (not done, not approved)

A written bank contract for reverse/refund covering idempotency by a client key (or a result inquiry), the exact success and "already
done" codes, and the window; then a sandbox test against the bank. A dedicated `UNKNOWN` refund status needs a schema change (see the
migration proposal); the interim marker is `failure_code="unknown_outcome"`.
