# Platform billing jobs: runbook and deployment checklist (F-03)

Status: repository side done and tested. **Server side not verified.** The audit had no access to the production server, so it is
unknown whether any billing job is scheduled there today. Treat every job below as "not running" until the checklist in section 4
has been completed on the real server by an operator.

## 1. Why these jobs are required

The application has no queue or scheduler (ADR-49). Everything that must happen "later" is a management command run by cron.
Without them:

| If this is not running | What goes wrong |
|---|---|
| `reconcile_platform_payments` | A payment whose customer never came back from the bank stays unapplied. The merchant paid and has no subscription or SMS credit. |
| `reprocess_billing_webhooks` | A webhook that failed once (database blip, worker restart) is never retried. |
| `recover_stale_refunds` | A refund whose process died stays "requested" forever and its amount stays reserved. |
| `evaluate_subscription_states` | Trials and grace periods never end, and a financially suspended subscription is not restored when its paid period begins. |
| `generate_subscription_renewals` | No renewal invoices are created. |
| `process_subscription_dunning` | Overdue invoices are never escalated. |
| `expire_platform_card_claims`, `release_expired_platform_coupon_reservations` | Expired claims and coupon quota reservations are never released (no money moves). |
| `verify_billing_consistency`, `verify_subscription_consistency` | Data drift is not detected. |

## 2. Schedule (in `deploy/cron/rastisi.crontab`, timezone Asia/Tehran)

| Job (command) | Cadence | Notes |
|---|---|---|
| `reconcile_platform_payments --min-age-minutes 5` | every 10 min | Also re-checks a browser-declined attempt for 24 h (`--declined-max-age-hours`). |
| `reprocess_billing_webhooks` | every 5 min | `received` older than 2 min; `failed` with backoff 2^n min, at most 5 retries. |
| `recover_stale_refunds` | every 10 min | Marks stale intents as unknown. **Never calls a provider.** Exits 1 while any refund waits in the unknown state. |
| `expire_platform_card_claims` | every 10 min | |
| `release_expired_platform_coupon_reservations` | every 10 min | |
| `evaluate_subscription_states` | hourly at :10 | Includes automatic restoration of financial suspensions. |
| `generate_subscription_renewals` | daily 02:30 | |
| `process_subscription_dunning` | daily 03:00 | |
| `verify_billing_consistency --strict` | daily 04:00 | Read-only. |
| `verify_subscription_consistency --strict` | daily 04:15 | Read-only. |

All run through `deploy/cron/run_job.sh`, which logs to `/var/log/rastisi/<name>.log`, preserves the command's exit code and sends an
alert (see 3.1) on a non-zero exit. The six state-changing jobs also take a PostgreSQL advisory lock (`apps.core.job_lock.exclusive`): an overlapping run prints
`skipped: another <job> is still running` and exits 0. The jobs are idempotent and row-lock safe in any case.

**Failure behaviour.** One failing record never stops the others. After the whole batch the command exits non-zero and prints the
failing item ids, so the alert fires and nothing is silently skipped.

## 3. Health symptoms (`manage.py check_background_jobs`, already scheduled every 15 min)

The check derives job health from the data (no heartbeat table). Exit 0 OK, 1 WARNING, 2 CRITICAL (CRITICAL also notifies platform
admins). New billing checks:

| Check | WARNING | CRITICAL | Meaning / action |
|---|---|---|---|
| `billing_stale_attempts` | online attempt pending > 30 min | > 3 h | Reconciliation is not running or the bank is unreachable. |
| `billing_requires_action` | confirmed money parked > 24 h | > 72 h | Finance must refund or allocate (Platform Admin > Reconciliation). |
| `billing_payment_pending_invoices` | > 24 h | > 72 h | Customer abandoned or reconciliation lag. |
| `billing_webhooks_stuck` | received/failed (retrying) > 15 min | > 2 h | Is `reprocess_billing_webhooks` scheduled? |
| `billing_webhooks_exhausted` | | any | Failed after 5 retries. A person must look at the event. |
| `subscription_transitions_overdue` | due > 2 h ago | > 24 h | Is `evaluate_subscription_states` scheduled? |
| `billing_financial_suspension_unrestored` | | any | A financially suspended subscription has a paid period in force. The evaluator should restore it. |
| `billing_refund_intent_stale` | requested > 30 min | | `recover_stale_refunds` is not running. |
| `billing_refund_unknown_outcome` | unknown > 1 h | > 24 h | Reconcile with the bank, then complete or fail the refund with a bank reference. Do not retry. |
| `billing_card_claims_waiting` | pending review > 3 days | | |

## 3.1 Wrapper safety and alerts (`deploy/cron/run_job.sh`)

The wrapper fails closed: the job is **not started** (and never runs on system python, SQLite or default settings) when something is wrong.

| Exit | Meaning |
|---|---|
| job's own code | The management command's exit code, unchanged. |
| 97 | Application directory missing or has no `manage.py`. |
| 98 | Environment file missing, unreadable or has a shell syntax error. |
| 99 | `$RASTISI_VENV/bin/python` missing, not executable or not a virtualenv interpreter. |
| 96 | Invalid configuration. Only the variable **names** are printed, never values: `DJANGO_SECRET_KEY`, `DATABASE_URL` (must come from the env file and be `postgres://`), `DJANGO_DEBUG` (explicitly false), `PAYMENTS_SIMULATION_ENABLED` (off), alert recipient/command, log directory. |
| 95 | `--test-alert` could not be delivered. |

Load order: wrapper paths from the cron environment, then path checks, then the env file (its values override cron's; any inherited
`DATABASE_URL` is dropped so the env file is the only source), then configuration checks, then the command via the venv's absolute python path.

**Operator must supply:** `RASTISI_APP_DIR`, `RASTISI_ENV_FILE`, `RASTISI_VENV`, `JOB` (real paths); `RASTISI_ALERT_TO` (real recipient,
crontab or env file); `MAILTO` (monitored mailbox for wrapper problems); an installed mail-compatible command (default `mail -s`, override with
`RASTISI_ALERT_CMD`, run without a shell as `<words> "<subject>" "<recipient>"`, last 20 log lines on stdin); in the env file
`DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`. Staging/test only: `RASTISI_JOB_ALLOW_DEBUG=1` skips the debug/simulation checks.

**The env file must be the full production environment, not just those three variables.** Every job starts `manage.py`, which loads the
production settings. Checked on 2026-11-11: with only `DATABASE_URL`, `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=False`, `manage.py check` stops with
`ImproperlyConfigured`. The additional variables that stop startup when missing are `DJANGO_ALLOWED_HOSTS`, `RASTISI_RATE_LIMIT_CACHE_URL`
(`redis://` or `rediss://`), `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` and `TURNSTILE_EXPECTED_HOSTNAMES`. `PAYMENT_CREDENTIAL_KEY` does not stop
startup, but without it stored gateway credentials cannot be decrypted, so payment reconciliation cannot verify anything. The simplest correct
setup is to point `RASTISI_ENV_FILE` at the same file the web application uses. `run_job.sh --check-config` does not start Django, so it
cannot detect these: also run `$RASTISI_VENV/bin/python manage.py check` with that environment (step 1 of the checklist below).

**Alert delivery failures are never silent:** they print `ALERT DELIVERY FAILED` on stderr (cron mails it to `MAILTO`), append a line to the
job log, write syslog (`logger -t rastisi-cron`) and create `/var/log/rastisi/ALERT_DELIVERY_FAILED` (removed after the next delivered
alert). Monitor that file or the syslog tag. The job's exit code is still the job's own.

Checks (no job is run): `deploy/cron/run_job.sh --check-config`; `deploy/cron/run_job.sh --test-alert` sends a test message.
Tests: `apps/billing/tests/test_cron_wrapper.py` (synthetic app, virtualenv and mailer; no real job or provider).

## 4. Deployment checklist (operator, real server)

1. Edit the crontab values listed in 3.1, run `run_job.sh --check-config` and `--test-alert` as the app user, then
   `crontab -u <app-user> deploy/cron/rastisi.crontab`. Confirm `crontab -l`. Before that, load the env file in a subshell
   (`set -a; . "$RASTISI_ENV_FILE"; set +a; "$RASTISI_VENV/bin/python" manage.py check --deploy`) and confirm it reports no errors.
2. Confirm the database is PostgreSQL (the advisory lock is a no-op elsewhere).
3. On staging run `bash deploy/cron/validate_jobs.sh`. Step 10 runs every billing job in dry-run or read-only mode.
4. After one hour confirm each `/var/log/rastisi/billing_*.log` has a new `=== ... end <job> rc=0`.
5. Break something on staging on purpose (stop the DB briefly) and confirm the alert command fires.
6. Run two copies of one job and confirm one prints `skipped: another ... is still running`.
7. Confirm `check_background_jobs --json` reports every `billing_*` check as OK on a healthy system.
8. Record who verified, when, and on which server. Until this is recorded, F-03 stays open.

## 5. Manual recovery

* Payment not applied: Platform Admin > Payments > "verify now", or `manage.py reconcile_platform_payments`.
* Webhook stuck: `manage.py reprocess_billing_webhooks` (add `--dry-run` first).
* Refund unknown: invoice detail page in Platform Admin. "Complete" needs a bank reference of at least 6 characters; "Not executed"
  needs documented proof and releases the reserved amount. Never re-request while an unknown refund exists (the system refuses).
* Financial suspension: restored automatically when a paid period begins. To lift it earlier: Platform Admin > store > Subscription
  tab > "Lift financial suspension" (platform superuser only, reason mandatory, audited).
