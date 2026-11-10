# Phase 2 financial security remediation: delivery report

Branch `kiro/financial-security-remediation-20261110`, built on the published baseline `kiro/financial-baseline-abab0041-20261110`
(`abab0041003d284c61c1990db7e865ce7a012bee`). **Draft. Not merged. No migration created or applied. Nothing deployed.**
Awaiting user QA and approval.

## 1. Findings

| Finding | Status | What changed |
|---|---|---|
| F-02 Paid invoice that can no longer be fulfilled | Resolved | `confirmation_service` parks the confirmed payment (`REQUIRES_ACTION`, code `fulfilment_blocked`) instead of applying or losing it. Savepoint around fulfilment. Manual and zero-due paths raise instead of reporting success. |
| F-05 Late / stale payments | Resolved | VOID and UNCOLLECTIBLE invoices never entitle (`late_payment_void`, `late_payment_uncollectible`). A plan-change invoice made stale by a later plan change is parked (`stale_decision`). Finance decides refund or allocation. |
| F-01 / F-10 Browser failure hint strands a payment | Resolved | A `gateway_declined` attempt stays verifiable (return page, status button, reconciler `--declined-max-age-hours 24`). A cache fault no longer turns the return page into a 500. |
| F-04 One bad row stops a financial batch | Resolved | Per-item transaction and isolation in renewals, dunning and the state evaluator. The run finishes, lists failed ids, and exits non-zero. |
| F-15 Concurrent webhook ingestion returned 500 | Resolved | Savepoint insert, re-query outside it. PostgreSQL: 12 simultaneous identical deliveries, 12 x 200, one row. |
| F-16 Unexpected webhook failure lost | Resolved | Failure recorded on the event (`unexpected:<ClassName>` only), HTTP 503 so a provider retries. New `reprocess_billing_webhooks` job (backoff 2^n min, 5 retries). Staff list shows stuck `received` events. |
| F-17 Terminal webhook state overwritten | Resolved | Conditional updates; `processed` cannot be rewritten. 8 simultaneous deliveries of one success event: one activation. |
| F-06 Refund transaction boundary, blank key, uncertain outcome | Resolved for subscription refunds and duplicate-payment refunds. **SMS purchase refund: BLOCKED** | Intent committed first, provider called with no transaction or lock, outcome recorded conditionally. Timeouts, transport errors, unexpected exceptions and lost responses are an unknown outcome: amount stays reserved, provider never called again for that row, new refunds on the invoice are refused, only a bank reference (6+ characters) resolves it. `recover_stale_refunds` never calls a provider. Form carries a per-render key. Interim `PENDING` + `failure_code="unknown_outcome"` stands in for the real `UNKNOWN` status (needs a migration). |
| F-13 Attempt key reused across invoices | Resolved | `get_or_create_attempt` rejects reuse for another invoice, store, provider or currency. |
| F-14 One key, many provider sessions | Resolved | An existing attempt returns `(attempt, None)`; no second session; a final attempt is never reopened. PostgreSQL: 5 simultaneous starts, 1 session (before: 5). |
| F-08 Full refund of the funded period | Resolved | Funded period recorded at fulfilment in `invoice-<pk>` event metadata. A confirmed full refund of the period in force suspends (`metadata.kind="financial"`) unless another settled invoice covers the present. Past period, future period, partial refund, upgrade differential and legacy invoices without a recorded period change nothing (audit entry for finance). `evaluate_subscription_states` restores when a paid period begins (idempotent, never touches dunning suspensions). Reinstatement by hand: platform superuser only, reason mandatory, audited. Generic resume and extend refuse a financial suspension. Nothing is deleted. |
| F-03 Billing jobs not scheduled | **Repository side resolved. Server side NOT verified** | Ten billing jobs added to `deploy/cron/rastisi.crontab`, advisory locks on the state-changing ones, `check_background_jobs` billing symptoms, `validate_jobs.sh` dry-runs, runbook and checklist. Whether any job runs on the production server is unknown (no server access). |
| F-07 Single-actor money controls | Partly resolved | The Django-admin bulk "mark paid" (no amount, reference or reason) is removed. **Not done:** a second-approver (maker/checker) control for refunds and manual payments. |
| F-12 Webhook secret strength | Resolved | Production system check `rastisi.W020` (warning). An empty secret already fails closed. |
| F-18 Return redirect trust | Resolved | Exact allowlist: platform host(s) and the paying store's own admin host; https and no port in production; `ALLOWED_HOSTS` is never trusted. Development/tests also accept exact (non-wildcard) `ALLOWED_HOSTS` entries. |
| F-19 Receipt read before size check | Resolved | `receipt.size` checked first; read bounded to limit + 1. |
| F-11 Reconciler window and visibility | Partly resolved | Visibility through health checks and the declined-attempt window. The 72 h `--max-age-hours` default is unchanged. |
| F-09 Adapter amount check | Not planned | Potential finding, not confirmed. |

## 2. Remaining blockers and open items

1. **SMS purchase refund / credit freeze (F-06, BLOCKED, needs a schema change).** `sms_purchase_payment_service.refund_purchase` is
   unchanged and **not production-ready for automatic-reversal providers** (Pasargad, Saman, Mellat): it reverses credits before the
   provider call. Its docstring now says so. Manual providers are not exposed. Do not enable automatic SMS refunds until the freeze
   design in the migration proposal is approved and built.
2. Real `PROCESSING` / `UNKNOWN` refund statuses and the new refund columns: need a migration. Interim behaviour is in place.
3. Production scheduler (F-03) must be installed and verified by an operator using the runbook checklist.
4. Bank refund idempotency / inquiry for Pasargad, Saman and Mellat is unverified; the code treats any doubtful call as unknown.
5. A paid RENEWAL invoice still resumes a financially suspended subscription through `renew_subscription`, even if that period starts
   later. Accepted residual risk (new money was received); not changed.
6. F-07 maker/checker, F-09 and the F-11 window are not implemented.

Proposal for the migration-dependent items: `docs/payments/PHASE2_MIGRATION_PROPOSAL_20261110.md` (not created, not applied).
Scheduler runbook: `docs/payments/PLATFORM_BILLING_JOBS_RUNBOOK_20261110.md`.

## 3. Tests

All synthetic gateways, disposable PostgreSQL 16.2 (started and removed inside one command), no real provider call.

| Run | Command scope | Result | Exit |
|---|---|---|---|
| New Phase 2 modules, PostgreSQL | 7 modules, serial | **142 run, OK, 0 skipped** | 0 |
| New Phase 2 modules, SQLite | same 7 modules | 142 run, OK, 10 skipped (PostgreSQL-only concurrency) | 0 |
| Regression, PostgreSQL (HEAD `5c372308`) | `apps.billing apps.subscriptions apps.portal --parallel 4` | 2499 run, 2 failures, 3 errors, 4 skipped | 1 |
| Regression, SQLite (HEAD `5c372308`) | `apps.billing apps.subscriptions apps.dashboard apps.portal apps.stores apps.core apps.sms --parallel 8` | 6050 run, 4 failures, 3 errors, 104 skipped | 1 |

New module counts: payment recovery 23, webhooks 16, refunds 37, attempt binding 8, financial suspension 24, scheduling 15, hardening 19.
Concurrency coverage on PostgreSQL: simultaneous webhook deliveries, concurrent reprocessing, simultaneous refund submissions (one
provider call), over-refund race, no lock and no transaction during the provider call, provider timeout with concurrent retries,
duplicate-refund race, concurrent attempt starts, concurrent revocation and restoration.

### Classification of the non-passing tests (none caused by this branch)

**Identical on the baseline `abab0041` (run on the baseline worktree, same result):**

* `apps.stores...RefreshRastiModeDemoVisualsCommandTests` (1 error, 1 failure)
* `apps.dashboard...SettingsPageQueryPerformanceTests...query_count` (1)
* `apps.portal.tests.test_seo...test_terms_and_privacy_are_indexable` (1, SQLite and PostgreSQL)
* `apps.portal.tests.test_public_site_theme_contract...literal_colors` (1, SQLite and PostgreSQL)
* `apps.portal.tests.test_owner_registration_hardening` `InFlightDeliveryConcurrencyTests`: 3 failures serially on PostgreSQL on both
  the baseline and this branch.

**Intermittent, order/parallelism dependent, not reproducible in isolation:**

* `setUpClass` UniqueViolation on `django_content_type` for TransactionTestCase classes under `--parallel`
  (`test_owner_registration_hardening` x3 on PostgreSQL, which also occurs on the baseline with `--parallel 4`;
  `apps.core ConcurrentRenderTests` and `apps.sms LiveProtocolTests` on SQLite, which pass when run alone: 16 tests OK).
* `apps.core...test_ensure_contrast_is_cheap_enough_for_the_request_path`: a timing test that failed once under load and passes alone.

**Caused by this branch and fixed:** `test_billing_admin.test_mark_paid_action` (the action was removed on purpose, test replaced);
a test-only leak (two new modules patched a provider inside threads; `mock.patch` is not thread-safe), fixed by patching once in the main thread.

### Limitation

The full suite was not run on PostgreSQL for `apps.dashboard`, `apps.stores`, `apps.core`, `apps.sms` (time limit of the execution
environment); those ran on SQLite. Remaining validation: run them on PostgreSQL in the QA environment.

## 4. Delivery checks

* Baseline `abab0041` is an ancestor of HEAD; `d61680db` is not.
* No migration files changed; `makemigrations --check --dry-run`: "No changes detected".
* No ZIP, bundle, SQLite, bytecode or binary file in the diff; none of the seven locally modified Windows QA UI files is touched;
  `apps/billing.zip` is not included; credential scan of added lines found nothing.
* 46 files changed, about 3590 insertions and 157 deletions over 20 commits (before this report).

## 5. File-change summary (by area)

* Payments: `confirmation_service`, `payment_flow_service`, `attempt_service`, `webhook_service`, `duplicate_payment_service`,
  `refund_service`, `renewal_service`, `dunning_service`, `manual_card_service`, `sms_purchase_payment_service` (docstring only),
  `providers/adapter_backed`, `views`, `admin`, `apps`, new `checks`.
* New services/commands: `financial_suspension_service`, `reprocess_billing_webhooks`, `recover_stale_refunds`.
* Subscriptions: `subscription_service` (metadata kwargs, financial-suspension helpers), `entitlement_service` (message),
  `evaluate_subscription_states` (restoration).
* Platform admin: refund/complete views, reinstatement view, URL, templates (`payment_invoice_detail`, `payment_reconciliation`,
  `duplicate_actions`, `store_detail`).
* Operations: `apps/core/job_lock.py`, `check_background_jobs`, `deploy/cron/rastisi.crontab`, `deploy/cron/validate_jobs.sh`.
* Tests: seven new `test_phase2_*` modules; two existing tests updated.
* Docs: this report, the migration proposal, the jobs runbook.
