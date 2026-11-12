#!/usr/bin/env bash
# Installs the RastiSi release tooling on a server. Run ONCE by the owner/administrator as root (and again to upgrade the tooling).
#
#   sudo ./install.sh --service rastisi-rc-20261111.service --app-user rastisi --base /srv/rastisi-releases \
#                     --env-file /etc/rastisi/rc-20261111.env --port 18082 [--deploy-user rastisi-deploy] [--dry-run]
#
# What it does (and nothing else):
#   * copies the tooling into /usr/local/lib/rastisi, owned by root and not writable by anyone else (a release can never replace the
#     code that deploys it);
#   * creates the unprivileged deploy user (no password, no shell access other than the forced command);
#   * creates the base directory layout owned by the deploy user (group = the application user, read-only for it);
#   * writes /etc/rastisi/deploy.conf if it does not exist (never overwrites it) and a validated sudoers file with exactly two rules;
#   * prints what remains for a human: the authorized_keys line, the systemd drop-in, the first cutover.
# It does NOT touch the running application, nginx, PostgreSQL, Redis, certificates or any other site on the machine.
# DESTDIR=/some/dir installs into a directory tree instead (used by the tests); --dry-run prints and changes nothing.
set -euo pipefail

SERVICE=""; APP_USER=""; BASE=""; ENV_FILE=""; PORT=""; DEPLOY_USER="rastisi-deploy"; DRY=0
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTDIR="${DESTDIR:-}"
LIB="/usr/local/lib/rastisi"
PYTHON3="/usr/bin/python3"
SYSTEMCTL="/usr/bin/systemctl"

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --app-user) APP_USER="$2"; shift 2 ;;
    --base) BASE="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --deploy-user) DEPLOY_USER="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage ;;
  esac
done
for v in SERVICE APP_USER BASE ENV_FILE PORT; do [ -n "${!v}" ] || { echo "missing --${v,,}" >&2; usage; }; done
[[ "$SERVICE" =~ ^[A-Za-z0-9_.@-]+\.service$ ]] || { echo "--service must look like name.service" >&2; exit 2; }
[[ "$APP_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ && "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo "invalid user name" >&2; exit 2; }
[ "$DEPLOY_USER" != "root" ] && [ "$DEPLOY_USER" != "$APP_USER" ] || { echo "the deploy user must be neither root nor the application user" >&2; exit 2; }
[[ "$BASE" == /* && "$ENV_FILE" == /* ]] || { echo "paths must be absolute" >&2; exit 2; }
[[ "$PORT" =~ ^[0-9]{2,5}$ ]] || { echo "invalid --port" >&2; exit 2; }
if [ -z "$DESTDIR" ] && [ "$(id -u)" -ne 0 ] && [ "$DRY" -eq 0 ]; then echo "run as root (or use --dry-run)" >&2; exit 2; fi

run() { if [ "$DRY" -eq 1 ]; then printf 'DRY  %q' "$1"; shift; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }
dest() { printf '%s%s' "$DESTDIR" "$1"; }
as_root() { if [ -n "$DESTDIR" ]; then "$@"; else run "$@"; fi; }
chown_safe() { if [ -n "$DESTDIR" ]; then return 0; fi; run chown "$@"; }

echo "== tooling -> $(dest "$LIB")"
as_root install -d -m 0755 "$(dest "$LIB")" "$(dest "$LIB")/smoke.d"
for f in rastisi_common.py rastisi_release.py rastisi_app_task.py rastisi_gate.py rastisi_probe.py rastisi_smoke.py rastisi_edge_probe.py migration_guard.py make_dropin.py runtime_check.py TOOLING_VERSION; do
  as_root install -m 0644 "$SRC/$f" "$(dest "$LIB")/$f"
done
as_root install -m 0644 "$SRC"/smoke.d/*.py "$(dest "$LIB")/smoke.d/"
as_root install -m 0755 "$SRC/run_current_job.sh" "$(dest "$LIB")/run_current_job.sh"
chown_safe -R root:root "$LIB"
as_root install -d -m 0755 "$(dest /usr/local/lib/rastisi-backup)"
as_root install -m 0644 "$SRC/../backup/rastisi_backup.py" "$(dest /usr/local/lib/rastisi-backup)/rastisi_backup.py"
chown_safe -R root:root /usr/local/lib/rastisi-backup

echo "== deploy user $DEPLOY_USER"
if [ -z "$DESTDIR" ] && ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  run useradd --system --create-home --home-dir "/home/$DEPLOY_USER" --shell /bin/sh --comment "RastiSi release deployer" "$DEPLOY_USER"
fi

echo "== layout under $BASE (owned by $DEPLOY_USER, readable by group $APP_USER)"
for d in "" releases venvs staging state; do
  as_root install -d -m 2750 "$(dest "$BASE")/$d"
done
as_root install -d -m 2770 "$(dest "$BASE")/state/static-build"
chown_safe -R "$DEPLOY_USER:$APP_USER" "$BASE"
chown_safe "$DEPLOY_USER:$APP_USER" "$BASE/state/static-build"
if [ ! -e "$(dest "$BASE")/state/deploy.lock" ]; then
  as_root install -m 0644 /dev/null "$(dest "$BASE")/state/deploy.lock"
  chown_safe "$DEPLOY_USER:$APP_USER" "$BASE/state/deploy.lock"
fi

echo "== /etc/rastisi/deploy.conf"
CONF="$(dest /etc/rastisi/deploy.conf)"
as_root install -d -m 0755 "$(dest /etc/rastisi)"
if [ -e "$CONF" ]; then
  echo "exists, NOT overwritten: $CONF"
elif [ "$DRY" -eq 1 ]; then
  echo "DRY  would write $CONF"
else
  cat > "$CONF" <<EOF
[rastisi]
base_dir = $BASE
app_user = $APP_USER
service = $SERVICE
env_file = $ENV_FILE
port = $PORT
python = $PYTHON3
# Cron jobs MUST use the release-aware wrapper described in RELEASE_PIPELINE.md.
jobs_follow_current = false
app_runner = sudo -n -u $APP_USER $PYTHON3 $LIB/rastisi_app_task.py
systemctl = sudo -n $SYSTEMCTL
systemctl_show = $SYSTEMCTL
# the platform host name the application answers to (must be in DJANGO_ALLOWED_HOSTS); used by the HTTP smoke tests
smoke_host = CHANGE_ME_PLATFORM_HOST
edge_probe_enabled = true
edge_port = 443
# where the backup job records its last verified backup (rastisi_backup.py state_dir)
backup_record = /var/lib/rastisi-backup/last_backup.json
backup_max_age_minutes = 90
keep_releases = 5
health_timeout = 90
min_free_mb = 500
EOF
  chmod 0644 "$CONF"
fi

echo "== sudoers (two rules, validated before use)"
SUDOERS_TMP="$(mktemp)"
trap 'rm -f "$SUDOERS_TMP"' EXIT
cat > "$SUDOERS_TMP" <<EOF
# Managed by deploy/release/install.sh. The deploy user may do exactly these two things and nothing else.
Defaults:$DEPLOY_USER !requiretty
$DEPLOY_USER ALL=($APP_USER) NOPASSWD: $PYTHON3 $LIB/rastisi_app_task.py *
$DEPLOY_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart $SERVICE, $SYSTEMCTL is-active $SERVICE
EOF
if command -v visudo >/dev/null 2>&1; then visudo -cf "$SUDOERS_TMP" >/dev/null || { echo "generated sudoers file is invalid" >&2; exit 1; }; fi
as_root install -d -m 0750 "$(dest /etc/sudoers.d)"
as_root install -m 0440 "$SUDOERS_TMP" "$(dest /etc/sudoers.d/rastisi-deploy)"

cat <<EOF

== Done. What remains is deliberately manual (see docs/deployment/RELEASE_PIPELINE.md, section "First activation"):
  1. Put the GitHub Actions public key into /home/$DEPLOY_USER/.ssh/authorized_keys as ONE line:
       restrict,command="$PYTHON3 $LIB/rastisi_gate.py" ssh-ed25519 AAAA... github-actions-deploy
  2. Install examples/sshd_config.snippet for account-wide ForceCommand, validate with sshd -t, reload ssh.
  3. Edit /etc/rastisi/deploy.conf: smoke_host.
  3. Review, then apply, the systemd drop-in:  make_dropin.py --unit-file <(systemctl cat $SERVICE) --base $BASE --old-app <current app dir>
  4. Run the one-time cutover (dry run first):  sudo -u $DEPLOY_USER $PYTHON3 $LIB/rastisi_release.py cutover --legacy-app ... --legacy-venv ... --sha <commit running now>
EOF
