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

All run through `deploy/cron/run_job.sh`, which logs to `/var/log/rastisi/<name>.log` and runs `$RASTISI_ALERT_CMD` on a non-zero
exit. The six state-changing jobs also take a PostgreSQL advisory lock (`apps.core.job_lock.exclusive`): an overlapping run prints
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

## 4. Deployment checklist (operator, real server)

1. `crontab -u <app-user> deploy/cron/rastisi.crontab` after reviewing paths, `MAILTO`, `RASTISI_ALERT_CMD`. Confirm `crontab -l`.
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
