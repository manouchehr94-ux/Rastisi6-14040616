#!/usr/bin/env bash
# Wrapper for every RastiSi cron job (existing management commands; no scheduler framework).
#   run_job.sh <name> <manage.py command and args...>
#   run_job.sh --check-config        validate paths, environment file, virtualenv and alert setup; run nothing
#   run_job.sh --test-alert          same, then send a test alert (proves the notification path end to end)
#
# FAIL CLOSED. The job is NOT started (and nothing falls back to system python, SQLite or defaults) when any of these is wrong:
#   97 application directory missing / has no manage.py      98 environment file missing, unreadable or has a syntax error
#   99 virtualenv python missing, not executable or not a virtualenv interpreter
#   96 invalid production configuration (names only are printed, never values) or no usable alert path
#   95 --test-alert could not be delivered      64 bad usage
# Otherwise the exit code is EXACTLY the management command's exit code (cron/monitoring see it).
#
# Order of loading:
#   1. wrapper settings from the cron environment: RASTISI_APP_DIR, RASTISI_ENV_FILE, RASTISI_VENV, RASTISI_LOG_DIR
#   2. paths are validated (app dir, env file, venv python)
#   3. inherited DATABASE_URL is dropped, then the environment file is loaded (`set -a`): its values override anything inherited
#      from cron, and it is the ONLY source of DATABASE_URL (no accidental database)
#   4. critical configuration is validated (DJANGO_SECRET_KEY, PostgreSQL DATABASE_URL, DJANGO_DEBUG off, simulation off, alert
#      recipient/command); then `cd` into the app dir and the command runs with "$venv/bin/python" (absolute path, never PATH)
#
# Notification (on any non-zero exit, and on a configuration failure when an alert path is already known):
#   RASTISI_ALERT_TO   REQUIRED. Recipient address (not a placeholder). May live in the environment file or the crontab.
#   RASTISI_ALERT_CMD  mail-compatible command, default "mail -s". It is run WITHOUT a shell as:  <words…> "<subject>" "<recipient>"
#                      with the last 20 log lines on stdin. Any command with that calling convention works (mail, mailx, a script).
#   If delivery fails it is reported loudly instead of being swallowed: a line on stderr (cron mails it to MAILTO), a line in the job
#   log, a syslog entry (logger) and the marker file $RASTISI_LOG_DIR/ALERT_DELIVERY_FAILED (removed after the next delivered alert).
# Overlap is prevented by the commands themselves (PostgreSQL advisory lock, apps.core.job_lock).
set -u

mode="job"
case "${1:-}" in
  --check-config) mode="check"; name="_check" ;;
  --test-alert)   mode="alert"; name="_test_alert" ;;
  "")             echo "usage: run_job.sh <name> <manage.py command…> | --check-config | --test-alert" >&2; exit 64 ;;
  *)              name="$1" ;;
esac
shift
if ! [[ "$name" =~ ^[A-Za-z0-9_-]+$ ]]; then echo "run_job.sh: invalid job name" >&2; exit 64; fi
if [ "$mode" = "job" ] && [ $# -lt 1 ]; then echo "usage: run_job.sh <name> <manage.py command…>" >&2; exit 64; fi

app_dir="${RASTISI_APP_DIR:-/srv/rastisi}"
env_file="${RASTISI_ENV_FILE:-/etc/rastisi/env}"
venv="${RASTISI_VENV:-/srv/rastisi/venv}"
log_dir="${RASTISI_LOG_DIR:-/var/log/rastisi}"
py="$venv/bin/python"
stamp() { date '+%F %T %Z'; }

# ---- alert delivery -----------------------------------------------------------------------------------------------------------
alert_is_placeholder() {
  case "$1" in
    ""|*CHANGE_ME*|*change_me*|*@example.com|*@example.org|*@example.net) return 0 ;;
  esac
  return 1
}
alert_ready() {   # 0 when a recipient and an executable alert command are configured
  local to="${RASTISI_ALERT_TO:-}" words
  alert_is_placeholder "$to" && return 1
  [[ "$to" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || return 1
  read -r -a words <<< "${RASTISI_ALERT_CMD:-mail -s}"
  [ "${#words[@]}" -ge 1 ] && command -v "${words[0]}" >/dev/null 2>&1
}
report_alert_failure() {   # $1 = what failed (no secrets)
  local msg="rastisi cron: ALERT DELIVERY FAILED for $name: $1"
  echo "$msg" >&2
  [ -d "$log_dir" ] && { echo "=== $(stamp) $msg" >> "$log_dir/$name.log" 2>/dev/null; echo "$(stamp) $name $1" > "$log_dir/ALERT_DELIVERY_FAILED" 2>/dev/null; }
  command -v logger >/dev/null 2>&1 && logger -t rastisi-cron -p user.err "$msg" 2>/dev/null
  return 0
}
send_alert() {   # $1 = subject; body on stdin; never aborts the wrapper
  local subject="$1" words body rc
  body="$(cat)"
  if ! alert_ready; then report_alert_failure "no usable alert path (RASTISI_ALERT_TO / RASTISI_ALERT_CMD)"; return 1; fi
  read -r -a words <<< "${RASTISI_ALERT_CMD:-mail -s}"
  if command -v timeout >/dev/null 2>&1; then
    printf '%s\n' "$body" | timeout 60 "${words[@]}" "$subject" "$RASTISI_ALERT_TO" >/dev/null 2>&1
  else
    printf '%s\n' "$body" | "${words[@]}" "$subject" "$RASTISI_ALERT_TO" >/dev/null 2>&1
  fi
  rc=$?
  if [ $rc -ne 0 ]; then report_alert_failure "alert command exited $rc"; return 1; fi
  [ -d "$log_dir" ] && rm -f "$log_dir/ALERT_DELIVERY_FAILED" 2>/dev/null
  return 0
}
config_error() {   # $1 = exit code, $2 = message (never contains secret values)
  local msg="rastisi cron: $name NOT started: $2"
  echo "$msg" >&2
  mkdir -p "$log_dir" 2>/dev/null
  [ -d "$log_dir" ] && [ -w "$log_dir" ] && echo "=== $(stamp) $msg" >> "$log_dir/_wrapper.log" 2>/dev/null
  command -v logger >/dev/null 2>&1 && logger -t rastisi-cron -p user.err "$msg" 2>/dev/null
  if [ "$mode" = "job" ] && alert_ready; then printf '%s\n' "$msg" | send_alert "rastisi job $name NOT started (config)"; fi
  exit "$1"
}

# ---- 1-2. paths ---------------------------------------------------------------------------------------------------------------
[ -d "$app_dir" ] && [ -f "$app_dir/manage.py" ] || config_error 97 "application directory is missing or has no manage.py (RASTISI_APP_DIR=$app_dir)"
[ -f "$env_file" ] && [ -r "$env_file" ] || config_error 98 "environment file is missing or unreadable (RASTISI_ENV_FILE=$env_file)"
bash -n "$env_file" 2>/dev/null || config_error 98 "environment file has a shell syntax error (RASTISI_ENV_FILE=$env_file)"
[ -x "$py" ] || config_error 99 "virtualenv python is missing or not executable (RASTISI_VENV=$venv); the system python is never used"
"$py" -c 'import sys; sys.exit(0 if (sys.prefix != getattr(sys, "base_prefix", sys.prefix) or hasattr(sys, "real_prefix")) else 1)' >/dev/null 2>&1 \
  || config_error 99 "$py is not a virtualenv interpreter (RASTISI_VENV=$venv)"

# ---- 3. environment: the file overrides cron, and is the only source of DATABASE_URL ------------------------------------------
unset DATABASE_URL
set +u -a                                    # a reference to an unset variable inside the operator's file must not abort the wrapper
# shellcheck disable=SC1090
. "$env_file" || { set +a -u; config_error 98 "environment file could not be loaded (RASTISI_ENV_FILE=$env_file)"; }
set +a -u
log_dir="${RASTISI_LOG_DIR:-$log_dir}"       # the file may relocate the log directory (alert/log settings are re-read below)
mkdir -p "$log_dir" 2>/dev/null
[ -d "$log_dir" ] && [ -w "$log_dir" ] || config_error 96 "log directory is not writable (RASTISI_LOG_DIR=$log_dir)"

# ---- 4. critical configuration (names only; values are never printed) ---------------------------------------------------------
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }
problems=()
case "${DJANGO_SECRET_KEY:-}" in ""|*CHANGE_ME*|*change_me*) problems+=("DJANGO_SECRET_KEY (unset or placeholder)") ;; esac
[[ "${DATABASE_URL:-}" =~ ^postgres(ql)?:// ]] || problems+=("DATABASE_URL (must be set in the environment file and be a postgres:// URL; the advisory lock needs PostgreSQL)")
if [ "${RASTISI_JOB_ALLOW_DEBUG:-0}" != "1" ]; then
  case "$(lower "${DJANGO_DEBUG:-}")" in false|0|no|off) ;; *) problems+=("DJANGO_DEBUG (must be explicitly false)") ;; esac
  case "$(lower "${PAYMENTS_SIMULATION_ENABLED:-false}")" in 1|true|yes|on) problems+=("PAYMENTS_SIMULATION_ENABLED (must be off)") ;; esac
fi
alert_ready || problems+=("RASTISI_ALERT_TO / RASTISI_ALERT_CMD (a real recipient and an installed mail-compatible command are required)")
if [ "${#problems[@]}" -gt 0 ]; then
  joined=""; for p in "${problems[@]}"; do joined="${joined:+$joined; }$p"; done
  config_error 96 "invalid configuration: $joined"
fi

# ---- run ----------------------------------------------------------------------------------------------------------------------
export VIRTUAL_ENV="$venv" PATH="$venv/bin:$PATH" TZ="${TZ:-Asia/Tehran}"
unset PYTHONHOME
cd "$app_dir" || config_error 97 "cannot enter the application directory"
log="$log_dir/$name.log"

if [ "$mode" = "check" ]; then echo "run_job.sh: configuration OK"; exit 0; fi
if [ "$mode" = "alert" ]; then
  if echo "rastisi cron test alert from $(hostname 2>/dev/null) at $(stamp)" | send_alert "rastisi cron test alert"; then
    echo "run_job.sh: test alert delivered to the configured recipient"; exit 0
  fi
  exit 95
fi

( echo "=== $(stamp) start $name"; "$py" manage.py "$@"; rc=$?; echo "=== $(stamp) end $name rc=$rc"; exit $rc ) >> "$log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
  command -v logger >/dev/null 2>&1 && logger -t rastisi-cron -p user.err "rastisi job $name failed (rc=$rc); see $log" 2>/dev/null
  tail -n 20 "$log" | send_alert "rastisi job $name failed (rc=$rc)"
fi
exit $rc
