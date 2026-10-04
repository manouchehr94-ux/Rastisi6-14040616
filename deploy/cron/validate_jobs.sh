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
echo
echo "Next, by hand: (a) crontab -l shows the installed entries; (b) after 5 min the log /var/log/rastisi/outbox.log has a new '=== … end outbox rc=0';"
echo "(c) stop the DB briefly (staging only) and confirm the alert command fires and check_background_jobs/exit codes are non-zero;"
echo "(d) run two copies of one job at once and confirm one prints 'skipped: another … is still running'."
[ $fail -eq 0 ] && echo "VALIDATION OK (hard failures: none)" || { echo "VALIDATION FAILED"; exit 1; }
