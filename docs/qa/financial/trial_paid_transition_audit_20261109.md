# Trial-to-Paid transition audit (2026-11-09)

Phase one of the temporary financial-ownership exception. **Read-only.** No source file was changed before this report was committed.

## 0. Scope, environment and what could not be verified

| Item | Value |
|---|---|
| Repository | `manouchehr94-ux/Rastisi6-14040616` |
| Audit branch | `kiro/trial-paid-transition-20261109` (created from the review branch, nothing else changed) |
| Audited commit | `155ce8561f9e9021506ea50eef5b8d928d7d4d7a` (on top of integration `d4c74236`) |
| Database used by the audit | Disposable **SQLite test databases** created by Django's test runner, with synthetic data only |
| PostgreSQL | The pre-audit baseline suite (908 tests) ran on a throwaway PostgreSQL 16.2 cluster started inside the sandbox |
| Payments | In-process fake gateway. No real credentials, no network, no real transactions |

**Not verifiable from this environment (assumptions, not findings):**

1. **The QA database behind `qa_financial STORE` (public id `851eca48-…`).** The sandbox has no access to the Windows QA server or its database. Every statement below about the QA store is an *inference from code plus a synthetic reproduction*, not an observation of that database.
2. **Whether the QA server and the inspection scripts used the same database (section F).** Cannot be checked here. A read-only script to check it is in Appendix B.
3. **The exact interval of the plan `پایه` and its published price** on the QA database.

## 1. How the scenario was reproduced

A synthetic store was provisioned through the real Trial engine (`provision_trial_store`, 30-day Trial). A published plan and a 100% coupon were created. The purchase ran over real HTTP (plan preview, plan execute, platform checkout pay) with the in-process fake gateway, then every relevant record was dumped (probe scripts are kept outside the repo in `.out/audit/probes/`, not committed).

Result of the reproduction, matching the reported QA outcome:

* Invoice `INV-2026-000001`, `kind=plan_change`, subtotal = discount, `grand_total=0`, `amount_due=0`, status `open` then `paid`.
* One `manual` payment attempt, amount 0, `status=succeeded`, `provider_payment_id=zero-due-…`.
* One redemption, status `reserved` then `redeemed`.
* Subscription (same row, id 2): `trialing` → `active`, plan `trial` → purchased plan.
* Events: `created`, `trial_started`, `plan_changed`, `activated`.

## 2. Findings by section

### A. Trial lifecycle

| Question | Result | Status |
|---|---|---|
| Authoritative Trial state | `StoreSubscription` row: `status`, `trial_start_at`, `trial_end_at`, `plan_version` (internal plan `trial`). | Confirmed |
| Trial start/end timestamps | `trial_end_at − trial_start_at` is exactly 30 days (from `2026-11-09T07:55:32.866` to `2026-12-09T07:55:32.866`). | Confirmed |
| Converted or terminated on purchase | The **same subscription row** is converted: `status` goes `trialing → active` and `plan_version` changes. `trial_start_at` and `trial_end_at` are **retained as history**. No separate Trial row exists. | Confirmed, expected |
| Can Trial entitlements stay active after conversion | **No.** Entitlements are read from the current subscription's plan version. Before the purchase the product limit is 20 (Trial); after settlement it is unlimited (paid plan). Creating the invoice alone changes nothing. | Confirmed |
| Could the expiry job downgrade the paid subscription | **No.** The Trial branch of the evaluator requires `status == trialing`. A converted store stayed `active` with full access when the evaluator ran after the leftover `trial_end_at`. `trial_info` reports `converted`. `check_subscription_consistency()` returned no issues. | Confirmed |

### B. Paid subscription

| Question | Result | Status |
|---|---|---|
| Active record and plan | One current row, `active`, on the purchased plan version. | Confirmed |
| Period dates | `current_period_start` = purchase moment. `current_period_end` = purchase moment + the invoice interval, computed by `next_period_end`. The invoice's own `billing_period_*` are `NULL` for plan-change invoices. | Confirmed |
| Does the paid period use the old Trial end | **No.** Five cases: monthly on Trial day 0 and day 10, quarterly on day 5, yearly on day 0, semiannual after natural expiry. The period end always follows the purchase date and the interval, never `trial_end_at`. | Confirmed |
| Why QA shows `trial end = period end = 1405/09/18` | `1405/09/18` is 2026-12-09. A **30-day Trial bought on its first day with a monthly plan** ends on the same calendar date as the one-month paid period (reproduced: Trial end `2026-12-09T07:55:32`, period end `2026-12-09T07:55:33`). This is a **coincidence of the inputs, not a defect in the period calculation**. | Strongly supported by reproduction; the plan's actual interval on the QA database is **unverified** |
| Leftover `trial_end_at` is still displayed on a paid subscription | The overview shows "end of trial" whenever `trial_end_at` is non-null, regardless of plan. For a converted store this puts a stale Trial date next to the real period end. | **Confirmed display defect (D2)** |

### C. Invoice and settlement

| Question | Result | Status |
|---|---|---|
| Invoice linked to the subscription | Invoice `subscription_id` equals the subscription row id. | Confirmed |
| Zero-payable settlement legitimate | Server-derived only. `settle_zero_due_invoice` requires `grand_total`, `amount_due`, `amount_paid` and the **sum of line totals** all zero, a still-current plan-change decision token, and an active coupon reservation. The browser's method and amount are ignored. | Confirmed (code + tests) |
| Activation tied to the right invoice | Events carry idempotency keys `invoice-<pk>` (plan change) and `invoice-<pk>-activate` (activation). | Confirmed |
| Idempotency / duplicate fulfilment | A repeated settlement request changed nothing: same subscription fields, same number of events, one attempt, one redemption. Events have a unique `(subscription, idempotency_key)` constraint. The PostgreSQL concurrency suites (parallel callbacks, duplicate settlement) pass. | Confirmed |

### D. Subscription history

| Question | Result | Status |
|---|---|---|
| Are the statuses persisted | **Yes.** Persisted rows: `created ''→pending`, `trial_started pending→trialing`, `plan_changed trialing→trialing`, `activated trialing→active`. | Confirmed |
| Why are "From status" / "To status" empty | **Template defect.** `subscription_history.html` calls `event.get_from_status_display` and `event.get_to_status_display`. `SubscriptionEvent.from_status` and `to_status` are plain `CharField`s with **no `choices`**, so Django generates no such methods. The variable resolves to nothing and falls through to the `default:"—"` filter. **All four rendered rows showed "—" in both status columns** in the reproduction. | **Confirmed defect (D1)** |
| Event creation / persistence | Correct. Not part of the problem. | Confirmed |
| Is the transition adequately recorded | Partly. The pair `plan_changed` + `activated` records it, both keyed by the invoice id, but neither event's `metadata` carries the invoice number, and there is no explicit "Trial converted" marker. | Observation (O1), not a defect |
| Cosmetic: plan column on the `created` row | Shows "— ← آزمایشی" (an arrow with no previous plan). | Observation (O2) |

### E. Coupon interaction

| Question | Result | Status |
|---|---|---|
| Redemption record | One row, `reserved` → `redeemed`, with the discount equal to the invoice subtotal. | Confirmed |
| Repeated redemption for the same store | One redemption per invoice (unique), per-store/total caps counted under row lock, a settled free conversion now ends `initial` eligibility (commit `01f80a29`), and a second upgrade is classified `plan_change` and not discounted. | Confirmed (tests) |
| First-purchase enforcement | `first_purchase_only` still means "no **positive** payment yet". A store whose only purchase was a settled free conversion is therefore still accepted by a `first_purchase_only` coupon that also allows plan changes. | **Policy question (P1), not changed**: see section 4 |
| New real purchases created | None. Only synthetic test data. | Confirmed |

### F. Database consistency

* **Slug discrepancy.** `slugify("qa_financial STORE")` is exactly `qa_financial-store`, so a store named "qa_financial STORE" has slug `qa_financial-store`. The difference between the displayed name and the database slug is **explained by normal slug generation** and does not by itself indicate two databases. (Confirmed by running `slugify`.)
* **Same database for the server and the inspection scripts.** **Unverified.** See Appendix B.

## 3. Defects, severity and business impact

| ID | Defect | Severity | Money affected? | Status |
|---|---|---|---|---|
| D1 | History page never shows From/To status (every row renders "—") | Low–medium: audit trail unreadable for support and finance | No | Confirmed |
| D2 | Overview shows a stale "end of trial" date for a converted (paid) subscription | Low: misleading, and it looks like an unfinished conversion | No | Confirmed |
| O1 | Conversion events do not carry the invoice number in metadata | Informational | No | Observation |
| O2 | `created` event shows an arrow with no previous plan | Cosmetic | No | Observation |
| P1 | `first_purchase_only` ignores a settled zero-value first purchase | Business-policy decision | Indirectly (second discount) | Not a code defect |

**No defect was found in:** Trial-to-paid conversion, entitlement switching, the paid period calculation, expiry-job behaviour, zero-value settlement, coupon idempotency, or duplicate fulfilment.

## 4. Root causes and recommended corrections

* **D1.** Root cause: the template relies on Django-generated `get_<field>_display` methods that do not exist for fields declared without `choices`. Recommended: resolve the label from `StoreSubscription.Status` in the model and use it in the template. No schema change, no migration.
* **D2.** Root cause: the overview prints `trial_end_at` unconditionally. Recommended: show it only while the store is on the Trial (still `trialing`, or on the internal Trial plan after expiry). Do **not** clear `trial_end_at`: `trial_start_at`/`trial_end_at` are the history that stops a store from receiving a second Trial.
* **O1/O2.** Optional follow-ups. O2 is fixed together with D1 because it is the same template. O1 is not changed (it would alter the event contract).
* **P1.** The original coupon specification says a first-purchase coupon must be refused for a merchant that "has successfully purchased an eligible paid subscription", which would include a free conversion. The implementation (and the earlier explicit instruction to keep the positive-payment meaning) differs. **This is a business-policy decision, so it is documented here and not changed.** If the owner wants the stricter meaning, the change is one condition in `_evaluate_coupon` using `has_completed_initial_conversion`.

## 5. Tests relevant to this audit (before any change)

Baseline on the audited commit `155ce856`, PostgreSQL 16.2, parallel 3:

`python manage.py test apps.billing apps.subscriptions apps.portal.tests.test_billing_views apps.portal.tests.test_step_up_billing apps.dashboard.tests.test_platform_coupon_checkout` → **908 tests, OK, 0 skipped.**

Synthetic reproductions (SQLite, not committed): the full scenario, five period/interval cases, evaluator and entitlement checks after conversion, and the entitlement before/after snapshot. All behaved as described above.

## Appendix A. Reproduction facts used

* Trial: 2026-11-09T07:55:32.866 → 2026-12-09T07:55:32.866 (30 days).
* Settlement: subscription `trialing → active`, `current_period_start` 2026-11-09T07:55:33, `current_period_end` 2026-12-09T07:55:33 (monthly).
* Entitlements: products limit 20 (Trial) → unlimited (paid); effective plan `trial` → purchased plan only after settlement.

## Appendix B. Read-only check for the QA database (to run on the Windows QA side)

Run only against the QA database the QA server is actually using; it reads and never writes.

```
python manage.py shell -c "
from django.conf import settings
from django.db import connection
print('ENGINE', settings.DATABASES['default']['ENGINE'])
print('NAME  ', settings.DATABASES['default']['NAME'])
print('HOST/PORT', settings.DATABASES['default'].get('HOST'), settings.DATABASES['default'].get('PORT'))
from apps.stores.models import Store
s = Store.objects.get(public_id='851eca48-34ca-4804-88d2-0ccdc11fb1eb')
print('slug', s.slug, '| admin_subdomain', s.admin_subdomain)
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
for x in StoreSubscription.objects.filter(store=s): print('SUB', x.pk, x.status, x.is_current, x.plan_version.plan.code, x.plan_version.billing_interval, x.trial_end_at, x.current_period_start, x.current_period_end, x.billing_interval)
for e in SubscriptionEvent.objects.filter(store=s).order_by('created_at'): print('EVT', e.event_type, repr(e.from_status), repr(e.to_status), e.idempotency_key)
"
```

Compare `NAME`/`HOST`/`PORT` with the values the running QA server prints at start-up, and check that the plan `پایه` has billing interval `monthly` (which would explain the equal dates).
