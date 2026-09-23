# billing — Testing

```
domain_id: D8
code_baseline: 5883a140
source: apps/billing/tests/ (12 files)
```

| Behavior | Test file |
|---|---|
| Payment confirmation + activation/renewal; webhook activation; duplicate-webhook idempotency; amount/currency mismatch | `test_confirmation_activation.py` |
| Webhook inbox dedup | `test_webhook_inbox.py` |
| Renewals | `test_renewals.py` |
| Dunning + cancellation | `test_dunning_cancellation.py` |
| Credit notes / refunds | `test_credit_refund.py` |
| Plan-change billing | `test_plan_change_billing.py` |
| Providers & attempts | `test_provider_and_attempts.py` |
| Zibal platform provider | `test_zibal_platform_provider.py` |
| Invoice lines & numbering | `test_invoice_lines_numbering.py` |
| Consistency isolation | `test_consistency_isolation.py` |
| Account & invoice | `test_account_and_invoice.py` |
| Billing admin actions | `test_billing_admin.py` |

## Coverage posture
Billing has strong behavior coverage for the money-critical paths (confirmation, webhook dedup,
renewal idempotency, dunning escalation). See canonical
[`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
