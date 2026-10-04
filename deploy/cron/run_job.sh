#!/usr/bin/env bash
# Wrapper for every RastiSi cron job (existing management commands; no scheduler framework).
#   run_job.sh <name> <manage.py command and args...>
# - loads the environment (DATABASE_URL, DJANGO_SECRET_KEY, DJANGO_EMAIL_*, …) from /etc/rastisi/env  (override: RASTISI_ENV_FILE)
# - activates the virtualenv                                                             (override: RASTISI_VENV, default /srv/rastisi/venv)
# - appends timestamped output to /var/log/rastisi/<name>.log                            (override: RASTISI_LOG_DIR)
# - on a non-zero exit runs $RASTISI_ALERT_CMD (e.g. "mail -s rastisi-job-failed ops@example.com") with the job name + last log lines
# Exit codes are preserved so cron/MAILTO/monitoring see failures. Overlap is prevented by the commands themselves (PostgreSQL advisory lock).
set -u
name="$1"; shift
app_dir="${RASTISI_APP_DIR:-/srv/rastisi}"
env_file="${RASTISI_ENV_FILE:-/etc/rastisi/env}"
venv="${RASTISI_VENV:-/srv/rastisi/venv}"
log_dir="${RASTISI_LOG_DIR:-/var/log/rastisi}"
mkdir -p "$log_dir"
[ -f "$env_file" ] && { set -a; . "$env_file"; set +a; }
[ -f "$venv/bin/activate" ] && . "$venv/bin/activate"
cd "$app_dir" || { echo "app dir $app_dir missing" >&2; exit 97; }
export TZ="${TZ:-Asia/Tehran}"
log="$log_dir/$name.log"
( echo "=== $(date '+%F %T %Z') start $name"; python manage.py "$@"; rc=$?; echo "=== $(date '+%F %T %Z') end $name rc=$rc"; exit $rc ) >> "$log" 2>&1
rc=$?
if [ $rc -ne 0 ] && [ -n "${RASTISI_ALERT_CMD:-}" ]; then
  tail -n 20 "$log" | bash -c "$RASTISI_ALERT_CMD \"\$1\"" _ "rastisi job $name failed (rc=$rc)" || true  # subject is passed as the last argument; body on stdin
fi
exit $rc
