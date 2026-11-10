#!/usr/bin/env bash
# Operator validation of the cron setup on a STAGING server (safe: dry-run/no-op/read-only commands, no customer messages sent).
#   bash deploy/cron/validate_jobs.sh      (same env as the cron user: RASTISI_* variables optional)
set -u
here="$(cd "$(dirname "$0")" && pwd)"
fail=0
step() { echo "--- $*"; }
run() { name="$1"; shift; "$here/run_job.sh" "validate-$name" "$@"; rc=$?; echo "rc=$rc"; [ $rc -le "${ALLOW:-0}" ] || fail=1; }
step "1. DB connection / config";               run check check
step "2. delivery readiness (reports real backends)";  ALLOW=1 run delivery verify_delivery_channels
step "3. expiry stays a no-op (TTL 0)";        run expiry expire_unpaid_orders --dry-run
step "4. reservations";                        run reservations expire_inventory_reservations
step "5. segments";                            run segments refresh_customer_segments
step "6. engagement (queue only)";             run engagement run_engagement_jobs --no-deliver
step "7. health";                              ALLOW=1 run health check_background_jobs
step "8. second run of the idempotent jobs must create nothing new"; run engagement2 run_engagement_jobs --no-deliver
step "9. e-mail sender identities (provider identity API only; RASTISI_EMAIL_PROVIDER=fake is a no-op)"; run email-senders refresh_email_identities
step "10. platform billing jobs (dry-run / read-only; nothing is charged, refunded, invoiced or changed)"
run billing-recon         reconcile_platform_payments --dry-run
run billing-webhooks      reprocess_billing_webhooks --dry-run
run billing-states        evaluate_subscription_states --dry-run
run billing-renewals      generate_subscription_renewals --dry-run
run billing-dunning       process_subscription_dunning --dry-run
run billing-claims        expire_platform_card_claims --dry-run
run billing-coupons       release_expired_platform_coupon_reservations --dry-run
ALLOW=1 run billing-verify verify_billing_consistency
ALLOW=1 run subs-verify    verify_subscription_consistency
step "11. billing health symptoms (exit 1 WARNING / 2 CRITICAL is a finding, not a script failure)"; ALLOW=2 run billing-health check_background_jobs
echo
echo "Next, by hand: (a) crontab -l shows the installed entries; (b) after 5 min the log /var/log/rastisi/outbox.log has a new '=== … end outbox rc=0';"
echo "(c) stop the DB briefly (staging only) and confirm the alert command fires and check_background_jobs/exit codes are non-zero;"
echo "(d) run two copies of one job at once and confirm one prints 'skipped: another … is still running'."
[ $fail -eq 0 ] && echo "VALIDATION OK (hard failures: none)" || { echo "VALIDATION FAILED"; exit 1; }
