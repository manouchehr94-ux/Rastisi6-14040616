#!/usr/bin/env bash
# =============================================================================
# FUTURE, MANUAL, TWO-PHASE removal of OLD RastiSi leftovers on the VPS.
# NOT run by this repository, NOT run by any other script.
#
#   Phase 1 (read-only):  cleanup_old_rastisi.sh --inventory > cleanup_manifest.txt
#       Lists candidates that are provably RastiSi's own. Review and edit the file.
#   Phase 2 (destructive, separate decision):
#       cleanup_old_rastisi.sh --execute cleanup_manifest.txt \
#           --backup-dir /var/backups/rastisi/<ts> --i-confirm-rastisi-only
#       Without --i-confirm-rastisi-only it only prints what it WOULD do.
#
# rastiservice.ir is protected by name AND by scope: only entries that pass the
# allow-list predicates in cleanup_guards.sh are ever touched; the shared
# PostgreSQL cluster/roles, Redis, global nginx config and TLS material of other
# sites are never candidates.
# =============================================================================
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/cleanup_guards.sh"

die() { echo "ERROR: $*" >&2; exit 1; }

inventory() {
  echo "# RastiSi cleanup manifest generated $(date -u +%FT%TZ) - REVIEW EVERY LINE, delete what you want to keep."
  echo "# format: <type> <value>   (service | nginx_site | path | database)"
  command -v systemctl >/dev/null && systemctl list-unit-files --no-legend 2>/dev/null | awk '{print $1}' | \
    while read -r u; do allowed_unit "$u" && echo "service $u"; done
  for d in /etc/nginx/sites-available /etc/nginx/sites-enabled /etc/nginx/conf.d; do
    [ -d "$d" ] && ls -1 "$d" | while read -r f; do allowed_nginx_site "$f" && echo "nginx_site $d/$f"; done
  done
  for p in /srv/rastisi* /var/www/rastisi* /var/lib/rastisi* /var/log/rastisi* /opt/rastisi* /home/*/rastisi*; do
    [ -e "$p" ] && allowed_path "$p" && echo "path $p"
  done
  command -v psql >/dev/null && psql -d postgres -Atc "select datname from pg_database" 2>/dev/null | \
    while read -r db; do allowed_database "$db" && echo "database $db"; done
  echo "# crontab entries / DNS / certificates are never removed automatically - handle by hand."
}

verify_backup() {
  local b="$1"
  [ -d "$b" ] || die "--backup-dir missing"
  ( cd "$b" && sha256sum -c SHA256SUMS >/dev/null ) || die "backup checksum verification failed"
  [ -f "$b/RESTORE_VERIFIED" ] || die "no $b/RESTORE_VERIFIED marker: run 'restore.sh $b --verify' and then 'touch $b/RESTORE_VERIFIED'"
}

execute() {
  local manifest="$1" confirm="$2"
  [ -f "$manifest" ] || die "manifest not found"
  local rc=0 type value
  while read -r type value; do
    case "$type" in ''|\#*) continue;; esac
    local ok=0
    case "$type" in
      service)    allowed_unit "$value" && ok=1;;
      nginx_site) [[ "$value" =~ ^/etc/nginx/(sites-available|sites-enabled|conf\.d)/[^/]+$ ]] && allowed_nginx_site "$(basename "$value")" && ok=1;;
      path)       allowed_path "$value" && ok=1;;
      database)   allowed_database "$value" && ok=1;;
    esac
    if [ "$ok" != 1 ]; then echo "REFUSED  $type $value  (not provably RastiSi-only)"; rc=3; continue; fi
    if [ "$confirm" != 1 ]; then echo "WOULD    remove $type $value"; continue; fi
    case "$type" in
      service)    systemctl disable --now "$value" 2>/dev/null; rm -f "/etc/systemd/system/$value"; echo "removed service $value";;
      nginx_site) rm -f -- "$value"; echo "removed $value";;
      path)       rm -rf -- "$(realpath -m -- "$value")"; echo "removed $value";;
      database)   psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$value\"" ; echo "dropped database $value";;
    esac
  done < "$manifest"
  if [ "$confirm" = 1 ]; then
    command -v systemctl >/dev/null && systemctl daemon-reload
    if command -v nginx >/dev/null; then nginx -t && systemctl reload nginx || echo "nginx -t FAILED: do not reload; fix before continuing"; fi
  fi
  return $rc
}

case "${1:-}" in
  --inventory) inventory;;
  --execute)
    manifest="${2:-}"; shift 2 || die "usage: --execute <manifest> --backup-dir DIR [--i-confirm-rastisi-only]"
    confirm=0; backup=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --backup-dir) backup="$2"; shift;;
        --i-confirm-rastisi-only) confirm=1;;
        *) die "unknown option $1";;
      esac; shift
    done
    [ "$confirm" = 1 ] && { [ "$(id -u)" = 0 ] || die "run as root"; verify_backup "$backup"; }
    execute "$manifest" "$confirm";;
  *) sed -n '2,18p' "$0"; exit 2;;
esac
