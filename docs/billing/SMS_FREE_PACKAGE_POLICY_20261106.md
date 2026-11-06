# Zero-price SMS packages — audit and policy (final validation, item 1)

## Finding (reproduced)
Any active `SmsPackage` with `price = 0` could be redeemed **without limit** by any member of a store that holds the SMS-settings permission: `settings_sms_package_purchase` created a new
pending purchase each time the previous one was completed, and `settle_free_purchase` credited it with no gateway. Reproduced with the old code: six repeats took a store from 100 to **400 credits**
(+300 free). The "reuse the pending purchase" lookup was also unlocked, so concurrent requests could create two pending rows.

## Audit
| Aspect | Before | After |
|---|---|---|
| Eligibility | none beyond "package active" | zero-price package = **one-time grant per store and package** (`free_package_already_redeemed`: any COMPLETED or REFUNDED free purchase of that package by that store) |
| Purchase limit | none | enforced in `request_purchase` (creation) **and** re-checked in `settle_free_purchase` (settlement), both under the same row lock |
| Authorization | `SMS_SETTINGS_MANAGE` + store scoping (unchanged, now covered by tests: analyst role, anonymous, other store's owner all fail) | unchanged |
| Concurrency | no lock on the pending lookup | `select_for_update` on the store's `SmsBalance` row serializes request/settle; PostgreSQL tests: 8 simultaneous redemptions by one store → 1 grant; 2 stores × 4 → exactly 1 each |
| Redemption history | ledger row per grant + `billing.sms_free_purchase_settled` audit | + `billing.sms_free_purchase_blocked` audit for every refused repeat; a stale second pending row stays PENDING and the checkout page shows "already activated" instead of a settle button |
| Refund | — | a refunded free grant does **not** reopen redemption |
| Paid packages | unchanged | unchanged (each purchase still needs a real, server-verified payment) |
| Platform finance manual grant | `complete_purchase` (audited) | unchanged — still the way to grant extra credits deliberately |

## Existing contracts are not changed
No migration, no data rewrite. Free purchases already completed — including repeats made before this fix — keep their credits, ledger rows and statuses exactly as they are
(`test_legacy_repeat_redemptions_already_on_record_are_left_exactly_as_they_are`). Only **new** repeats are refused.

## Owner decision (not assumed)
If the owner wants a *repeatable* free allowance (for example "50 credits every month"), that needs an explicit rule (cadence, per-period cap, who can change it). Until it is decided, repeat
redemption stays **disabled**. The safe default needs no decision to ship.

## Tests
`apps/billing/tests/test_sms_free_package_policy.py` — 15 tests (13 HTTP/service + 2 PostgreSQL concurrency). The exploit test fails on the old code (`400 != 150`) and passes now.
Adjacent suites (checkout, duplicate settlement, payment concurrency, SMS, billing views): 268 run; the only errors are the two known `django_content_type` flush artifacts, which pass alone.
