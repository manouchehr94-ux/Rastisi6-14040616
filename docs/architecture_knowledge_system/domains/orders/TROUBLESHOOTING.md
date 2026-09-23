# orders — Troubleshooting

```
domain_id: D6
code_baseline: 5883a140
```

Symptom → likely cause → where to look. Diagnostic only; do not fix code in this phase.

| Symptom | Likely cause | Where to look |
|---|---|---|
| Order marked paid twice / double `Transaction` | both simulation and gateway paths ran, or a new writer bypassed the conditional update | H1; `payment_service.simulate_payment`, `gateway_payment_service` (both create Transaction) |
| Payment verified at gateway but order still PENDING | callback not received, or `updated==0` (already paid concurrently), or verify failed | `process_callback_and_verify` (conditional update + `updated==0` return); gateway logs |
| `payment_status` in an "impossible" state | **no transition guard exists** (H1) — any of 3 writers can set it | STATE_MACHINES; MUTATION_AUTHORITY |
| Simulation callback returns 404 in production | intended — `PAYMENTS_SIMULATION_ENABLED` off; `status` path segment is client-controlled | ENTRY_POINTS; SECURITY |
| COD order never becomes paid | intended — COD stays PENDING (paid on delivery) | INVARIANTS #7; `gateways/cod.py` |
| Gateway refund fails / raises | intended — only MANUAL refunds implemented (ADR-33) | `refund_service` (GATEWAY raises) |
| "which gateway" mismatch on initiate | dual gateway model; `payment_initiate` fuzzy-matches config↔legacy slug | M4/DR-5; `views.payment_initiate` |
| Order status transition rejected | illegal transition per `ALLOWED_TRANSITIONS` (or terminal state) | `order_service.py:45,550` |
| Return cannot advance | illegal return transition | `ReturnRequest.ALLOWED_TRANSITIONS` (models.py:1047); `return_service._transition` |
| Stock not decremented at payment | intended — inventory decremented at **order creation**, not payment | ARCHITECTURE; catalog inventory_service |
| SMS not sent for a failed/rolled-back order | intended — SMS fires on `transaction.on_commit` | API_AND_EVENTS |
| Credentials error on startup (prod) | `PAYMENT_CREDENTIAL_KEY` missing → fail-closed | `encryption.py`; SECURITY |
| `select_for_update` "not locking" on SQLite | expected — SQLite whole-DB write lock; app-level guards are the boundary | TRANSACTIONS_AND_CONCURRENCY |
