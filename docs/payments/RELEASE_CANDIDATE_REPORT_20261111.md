# RastiSi release-candidate report (code level)

Date: 2026-11-11. Branch `kiro/financial-security-remediation-20261110`. Draft PR #45 (unmerged). Parent commit `3346aedd`.
Scope: final consolidation only. No audit, no redesign, no new provider, no migration, no deployment, no production access.

**Production is not verified by anything in this report.** Everything below was run in a disposable sandbox against SQLite and a
throwaway PostgreSQL 16.2. No real bank, SMS gateway or server was contacted.

## 0. Test-run environment

* Python 3.11.15, Django 5.2.19 (dependencies from `requirements.txt`), Linux.
* SQLite for the default runs. PostgreSQL 16.2 (the `pgserver` pip package, started and stopped inside one command, data removed) for the
  PostgreSQL-only concurrency tests. Provider interaction in every test is mocked or simulated in-process.

## A. Verified and ready at code level

### A1. `apps.sms.tests.test_gateway_live` (closed)

* **Symptom.** `ERROR: setUpClass (apps.sms.tests.test_gateway_live.LiveProtocolTests)`, `UNIQUE constraint failed: django_content_type.app_label,
  django_content_type.model`. Passes alone, fails only in large or parallel runs. Recorded in the repository since 2026-10-29.
* **Cause: test-order dependence through shared database state. Not an application defect, not mocking, not environment, not a port clash.**
  `LiveProtocolTests` sets `serialized_rollback = True`: before its first test Django replays a snapshot of the migration-seeded rows taken when the
  test database was built. Any earlier *plain* `TransactionTestCase` (no `serialized_rollback`) flushes all tables on teardown and lets the flush fire
  `post_migrate`, which re-creates `django_content_type` and `auth_permission` rows with NEW primary keys. The snapshot replay then collides
  with them. The earlier test does not need to execute anything: a test that calls `self.skipTest(...)` inside its body (PostgreSQL-only tests
  on SQLite) still runs the flush. A class skipped by decorator does not.
* **Reproduction (SQLite, serial, deterministic).**
  * `manage.py test apps.billing.tests.test_platform_coupon_engine apps.sms.tests.test_gateway_live` fails (minimal pair).
    Poisoner: `PostgresContentionTests` (added by this branch's coupon work). Victim: `LiveProtocolTests`.
  * Alone: pass. `apps.sms` alone (163 tests) and with `--parallel 4`: pass (no poisoner in the same process).
  * Same signature for the other `serialized_rollback` classes: `apps.core...ConcurrentRenderTests`, `apps.orders...ConcurrentRecoveryTests`,
    `ConcurrentMerchantApprovalTests`. Further poisoners confirmed: `customers.test_promotional_consent`, `dashboard.test_tax_upgrade`,
    `notifications.test_inbox_engine`, `storefront_builder.test_default_published_provisioning`.
  * Original large combination `apps.billing` + `test_gateway_live`: 908 run, `errors=1` (this exact error).
* **Fix (tests only).** New `apps/core/tests/serialized_rollback.py` (`SerializedRollbackSafeMixin`): before the snapshot is replayed it deletes the
  content-type rows `post_migrate` may have re-created (cascade removes their permissions; the snapshot restores all of them with the original
  keys). When the database is already empty it does nothing. Applied as the first base of 15 `serialized_rollback` `TransactionTestCase`
  classes in 12 test modules (each change: one import line and one class line). No application code, schema or setting changed.
* **After the fix.** All minimal pairs pass. `apps.billing` + `test_gateway_live` + `test_purchase_tracking`: 924 run, OK, 37 skipped (all
  PostgreSQL-only). The PostgreSQL-only classes now also run for real (see A4).
* **Remaining uncertainty.** The old failing run (11 992 tests, `--parallel 4`) was not repeated, by instruction. The mechanism is reproduced
  and removed for every poisoner/victim combination found, but a different untested order cannot be excluded. The mixin is order independent by design.
  The ~30 plain `TransactionTestCase` classes were not individually paired with each of the 15 victims; the mixin makes that unnecessary.

### A2. Financial invariants (existing tests, re-run; none weakened)

| Invariant | Evidence (all pass on SQLite and on PostgreSQL 16.2) |
|---|---|
| Exactly-once fulfilment | `test_phase2_webhooks` (redelivery activates once), `test_platform_duplicate_settlement` (simultaneous settlements), `test_platform_payment_concurrency`, `test_confirmation_activation`, `test_phase2_financial_suspension` (evaluator activates once). PostgreSQL race tests ran, 0 skipped. |
| Tenant isolation | `test_platform_card_to_card` (a store cannot claim another store's invoice), `..._http` (other store's invoices 404), `test_phase2_financial_suspension.test_another_store_is_never_affected`, `apps.orders.tests.test_tenant_isolation_regression`. |
| Unknown payment results | `test_phase2_payment_recovery`, `test_bank_refund_disabled` (timeout, error and unusual success code are UNKNOWN, amount stays reserved, never retried), `test_phase2_refunds`, orders BNPL settlement-uncertainty suite. |
| No automatic post-payment refund | `apps/billing/providers/bank_refund_policy.py`: `AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED = False` is a code constant, not an environment flag. Checked in code: `refund_service._execute_with_provider`, `duplicate_payment_service.refund_duplicate`, `AdapterBackedBillingProvider.refund_payment` stop before resolving a provider or credential. Zibal and manual providers have no refund API (return "manual"). SMS `refund_purchase` raises as its first statement. Tests: `test_refund_review_policy.NoAutomaticRefundTests`, `test_bank_refund_disabled`. |
| No HTTP or service-level bypass | Only five platform refund endpoints exist (request, approve, reject, complete, duplicate action). All `POST`-only and superuser-only (`_is_platform_staff` = staff and superuser). Test: forged requests to every decision endpoint change nothing; Django admin cannot change a refund state; no template action targets a gateway refund. Callers of `refund_purchase`/`complete_refund_manually` in non-test code: only `platform_admin_views.py`. |
| Approval separate from verified completion | `ApprovalTests` (approval calls no provider and changes neither money nor entitlement), `CompletionTests` (completion requires prior approval and a bank reference; entitlement revoked only by verified completion, only once). |
| No duplicate completion | `test_phase2_refunds` (finished refund cannot be completed or failed again), `PostgresConcurrentDecisionTests` (eight simultaneous completions apply the refund and the suspension once). |
| No premature subscription or SMS-credit change | `test_refund_review_policy` (approval and rejection change neither), `SmsCreditsAreNeverRevokedByTheFlagAloneTests`, `test_phase2_financial_suspension` (a pending or unknown refund does not suspend). |
| 30-day default trial, platform-configurable | `test_trial_to_paid_transition.test_default_trial_is_30_days_on_the_internal_trial_plan`, `test_seed_default_plans.test_trial_plan_trial_days_comes_from_platform_configuration`, `subscriptions.test_trial_engine` (once per store, PostgreSQL race included). `default_trial_days` is a `PlatformConfiguration` field validated by `trial_service.validate_days`. |
| No accidental free paid plan | Trial plan is internal and not purchasable (`0015_trial_plan_is_internal`); `test_platform_checkout.test_a_paid_invoice_can_never_be_settled_as_free`; `test_trial_purchase_flow`; `test_trial_to_paid_transition` (creating an invoice alone converts nothing; failed payment leaves the trial untouched). |
| Legitimate zero-payable invoices | `test_trial_to_paid_transition.test_zero_value_conversion_...`, `test_platform_checkout.test_a_zero_invoice_shows_the_free_state_without_any_method_or_gateway`, `test_platform_coupon_engine.ZeroValueSettlementTests`. |
| Tenant merchants' order refunds unchanged | The PR diff against its base contains no file under `apps/orders` outside tests (`git diff origin/kiro/financial-baseline-abab0041-20261110..HEAD -- apps/orders ':!apps/orders/tests'` is empty). |

### A3. Release-critical configuration (no migration applied)

* `manage.py makemigrations --check --dry-run`: "No changes detected". `manage.py check`: no issues.
* Production-like environment (`DEBUG=False`, dummy values): `manage.py check --deploy` reports only `security.W005` (HSTS subdomains) and
  `security.W021` (HSTS preload). Both are deliberate staged-rollout choices documented in `.env.example`.
* Safe defaults confirmed from the loaded production settings: `PAYMENTS_SIMULATION_ENABLED=False`, `RASTISI_SMS_REFUND_ENABLED=False`,
  `RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS=''`, `RASTISI_QA_PAYMENT_SIMULATOR=False`, `RASTISI_DEV_OTP_CODE=''`, `RASTISI_BILLING_PROVIDER='manual'`,
  session and CSRF cookies Secure.
* PostgreSQL compatibility: the whole PostgreSQL run below created the test database from all migrations on PostgreSQL 16.2 and ran the
  `select_for_update` / advisory-lock tests.
* Cron deployment configuration: all 20 management commands in `deploy/cron/rastisi.crontab` exist, and every `--dry-run`/`--strict`/`--limit`/`--min-age-minutes`
  option used in the crontab and `validate_jobs.sh` is defined by its command.

### A4. Tests run (final numbers)

| Run | Database | Tests | Result |
|---|---|---|---|
| `test_gateway_live` alone | SQLite | 2 | OK |
| `apps.sms` serial / `--parallel 4` | SQLite | 163 / 163 | OK, 1 skipped / OK, 1 skipped |
| Reproduction: `test_platform_coupon_engine` + `test_gateway_live` (before fix) | SQLite | 46 | **1 error** (the target error) |
| Same pair, and 9 other poisoner/victim pairs (after fix) | SQLite | small | all OK (10 pairs) |
| `apps.billing` + `test_gateway_live` + `test_purchase_tracking` (after fix) | SQLite | 924 | OK, 37 skipped |
| `test_cron_wrapper`, `test_phase2_scheduling`, `test_background_jobs` (after the crontab/runbook edits) | SQLite | 40 and 34 | OK |
| `apps.billing apps.subscriptions apps.sms test_background_jobs test_purchase_tracking`, `--parallel 4` | **PostgreSQL 16.2** | 1 316 | **OK, 0 skipped** |
| `apps.orders` + engagement/notifications/portal-registration/stores-migration/content-media suites touched by the mixin, serial | **PostgreSQL 16.2** | 1 226 | 4 failures, all pre-existing baseline (B1, B2) |

The full ~12 000-test suite was not run again.

## B. Remaining code defects

None that block staging. Pre-existing, not caused by this PR, not payment-related (identical result with this change stashed; both are listed as
baseline in `docs/qa/FINAL_VALIDATION_20261106.md`):

* **B1** `apps.orders.tests.test_coupon_concurrency.ConcurrentCampaignExecutionTests.test_overlapping_runs_issue_each_customer_once` (PostgreSQL only). The
  exactly-once assertions (6 issuances, 6 coupons) pass; only the count of `coupon.issued` e-mail outbox rows is 0 instead of 6. The test predates
  the promotional-consent gate (customers in the test have no consent). Merchant campaign module, outside the platform-payment policy. Needs the test updated or the expectation
  confirmed by the owner. Not changed here.
* **B2 (RESOLVED in the follow-up commit)** `apps.portal.tests.test_owner_registration_hardening.InFlightDeliveryConcurrencyTests` (3 failures, PostgreSQL only).
  Cause: stale test expectations, not an application defect. Commit `f8c9c3d8` (2026-10-09) deliberately changed the policy: a failed OTP delivery no longer deletes the
  accepted request's row; it stays as a never-verifiable marker (`PENDING_EXPIRES_AT`) so provider failures cannot reset the 120 s cooldown or the per-phone budget.
  That commit updated the sibling tests but not these three, which are skipped on SQLite. The three tests were rewritten to the current policy with stronger assertions
  (details in `docs/payments/OTP_CONCURRENCY_RESOLUTION_20261111.md`).

Confirmed documentation defect, fixed in this commit: the runbook and crontab said the cron env file needs only `DATABASE_URL`, `DJANGO_SECRET_KEY`
and `DJANGO_DEBUG=False`. With only those, every job fails at startup (`DJANGO_ALLOWED_HOSTS`, then `RASTISI_RATE_LIMIT_CACHE_URL`, then
`TURNSTILE_*` are required; verified). Runbook section 3.1 and step 1, and the crontab header, now say the env file must be the full production environment.

## C. Production operational checks that require real server access (NOT verified)

* Cron is not installed or verified on any server. Nothing in this report proves it.
* Real alert delivery (`mail`/`mailx`, MTA, MAILTO mailbox), real log files and permissions, real advisory-lock behaviour between two processes on the production database.
* Real PostgreSQL version, backups, restore test, migration timing on production-sized data.
* Real Zibal credentials, callback URL reachability, merchant ID, a real small payment on staging, and server-side verification against the real bank.
* Real Redis for the rate-limit cache, Turnstile keys, SES or SMS provider settings.
* TLS, reverse proxy headers, `DJANGO_TRUSTED_PROXY_CIDRS`, HSTS staging.
* The banking channel and the internal procedure for executing an approved refund manually.

## D. Non-blocking improvements deferred

* `validate_jobs.sh` does not exercise `recover_stale_refunds` or `reconcile_unknown_payments` (neither has a `--dry-run`). Run them once by hand on staging (checklist step 9).
* `.env.example` does not list `RASTISI_SMS_REFUND_ENABLED`, `RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS`, `RASTISI_BILLING_*`. They must stay unset; adding them as commented warnings is optional.
* `.env.example` points to `docs/deployment/PRODUCTION_CONFIGURATION.md`; the file is at `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md`.
* SMS package refunds remain disabled until the credit-freeze design (needs a migration, separate approval).
* Updating the stale expectation in B1.
* A shared parallel-run guard for plain `TransactionTestCase` classes (a base class that restores state) would remove the whole poisoner class; the mixin is the smallest fix.

## Operator checklist (staging first; every step is by a human, on the real server)

Environment variables (names only; never put values in tickets or logs):

* Required for every web process and every cron job: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DATABASE_URL` (`postgres://`), `DJANGO_ALLOWED_HOSTS`,
  `DJANGO_CSRF_TRUSTED_ORIGINS`, `RASTISI_RATE_LIMIT_CACHE_URL`, `TURNSTILE_ENABLED`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `TURNSTILE_EXPECTED_HOSTNAMES`,
  `PAYMENT_CREDENTIAL_KEY`, `DJANGO_STATIC_ROOT`, `DJANGO_MEDIA_ROOT`.
* Wrapper (crontab or env file): `MAILTO`, `RASTISI_ALERT_TO`, `RASTISI_ALERT_CMD`, `RASTISI_APP_DIR`, `RASTISI_ENV_FILE`, `RASTISI_VENV`, `RASTISI_LOG_DIR`, `JOB`, `CRON_TZ`.
* As applicable: `DJANGO_TRUSTED_PROXY_CIDRS`, `DJANGO_SECURE_PROXY_SSL_HEADER`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_HSTS_SECONDS`, `RASTISI_EMAIL_PROVIDER` and `RASTISI_SES_*`,
  `RASTISI_OWNER_SMS_*`, `RASTISI_BILLING_WEBHOOK_SECRET` (only if a billing webhook provider is used).
* Must be absent or at the safe value: `PAYMENTS_SIMULATION_ENABLED` (off), `RASTISI_QA_PAYMENT_SIMULATOR` (off), `RASTISI_DEV_OTP_CODE` (empty),
  `RASTISI_SMS_REFUND_ENABLED` (unset), `RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS` (unset), `RASTISI_JOB_ALLOW_DEBUG` (unset).

Cron enablement and validation (staging, then production), as the application user:

1. Load the env file in a subshell and run `manage.py check --deploy` with the venv python; expect no errors (only the two HSTS warnings until HSTS is staged).
2. Edit the crontab placeholders (`MAILTO`, `RASTISI_ALERT_TO`, paths). The wrapper refuses to run while any is a placeholder.
3. `deploy/cron/run_job.sh --check-config` must print `configuration OK` (exit 0).
4. `deploy/cron/run_job.sh --test-alert` must exit 0 and the recipient must actually receive the message. Exit 95 means alert delivery is broken: stop.
5. Confirm the database is PostgreSQL (`DATABASE_URL`), because the concurrency lock is a no-op elsewhere.
6. `bash deploy/cron/validate_jobs.sh` on staging: dry-run or read-only. Expect `VALIDATION OK`.
7. Install: `crontab -u <app-user> deploy/cron/rastisi.crontab`, then `crontab -l` and compare.
8. Logging: after 10 minutes, `/var/log/rastisi/outbox.log` and `billing_recon.log` each contain a new `=== ... end <job> rc=0`.
9. Run once by hand: `run_job.sh refunds-check recover_stale_refunds` (never calls a provider; exit 1 means a refund is waiting in the unknown state) and `run_job.sh unknown-check reconcile_unknown_payments --limit 5` on staging only.
10. Alert delivery under failure (staging only): stop the database briefly, wait for one job, confirm an alert arrives; restore the database; confirm `/var/log/rastisi/ALERT_DELIVERY_FAILED` does not exist.
11. Concurrency lock: start two copies of one job at once; one must print `skipped: another ... is still running`.
12. Health: `manage.py check_background_jobs --json` reports every `billing_*` check as OK on a healthy system; the `*/15` cron entry keeps running.
13. Record who verified, when and on which server. Until recorded, production cron is unverified.

## Deployment and rollback (human operator; nothing here was executed)

Deploy (staging first, same steps for production after staging sign-off):

1. Announce a window. Take a database backup and prove it restores to a scratch database. Record the current commit SHA and the current migration state (`showmigrations`).
2. Review the migration plan on the target without applying it: `manage.py migrate --plan`. This PR was checked with `makemigrations --check` (no model changes); the migrations listed are those already in the repository.
3. Put the new code in a new release directory; install `requirements.txt` into a new virtualenv. Do not overwrite the running release.
4. Run `manage.py check --deploy` with the production environment. Stop on any error.
5. Disable the cron entries (comment them out or `crontab -r` after saving `crontab -l > crontab.backup`), so no job runs during the migration.
6. Apply migrations: `manage.py migrate`. Watch for errors; do not retry blindly.
7. Switch the application to the new release and restart the application servers. Smoke test: log in, view an invoice, start a payment on the staging gateway only, return from the bank, confirm the service is activated once.
8. Re-enable cron following the checklist above (steps 3 to 12).
9. Confirm refund controls: a refund request on a paid test invoice must stay "pending manual", no bank call, no subscription change until approval and completion with a bank reference.

Rollback:

1. Disable cron entries first (restore the saved empty crontab).
2. Point the application servers back to the previous release directory and restart. This PR adds no migrations of its own, so the schema does not need to go back for this change; if an earlier migration in the same deployment must be reversed, do it only from the backup taken in step 1, because several billing migrations carry data.
3. Restore the previous crontab (`crontab crontab.backup`) only after the application is healthy.
4. Do not hand-edit payment, invoice, subscription or refund rows. Anything left in "unknown" is reconciled with the bank through the Platform Admin payment pages.
5. Record the incident and the commit SHA that was rolled back.

## Conclusion

**GO for staging deployment**, under these conditions: the cron and staging checks above are completed and recorded; the merchant payment gateway runs against the bank's staging environment first. **Production is NOT approved by this report.**
