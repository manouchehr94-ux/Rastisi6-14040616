#!/usr/bin/env bash
# Pure predicate functions used by cleanup_old_rastisi.sh. Sourced, never run.
# They decide whether a candidate is *provably RastiSi's own* and not part of
# rastiservice.ir or of shared infrastructure. They have no side effects, so
# they can be unit-tested (rebuild/checks/test_cleanup_guards.sh).

# Anything mentioning the protected site, or generic shared infrastructure.
is_protected() {
  local v="${1,,}"
  case "$v" in
    *rastiservice*|*rasti-service*|*rasti_service*) return 0;;
    postgres|postgresql|template0|template1|redis|redis-server|nginx|certbot|ssh|sshd|/|/etc|/etc/nginx|/etc/letsencrypt|/var|/var/www|/srv|/opt|/home|/root|/usr|/usr/*) return 0;;
  esac
  return 1
}

# systemd unit file name: rastisi-*.service|socket|timer or gunicorn-rastisi*.service
allowed_unit() {
  is_protected "$1" && return 1
  [[ "$1" =~ ^(rastisi|gunicorn-rastisi)[a-z0-9_.@-]*\.(service|socket|timer)$ ]]
}

# nginx site file name containing "rastisi" (never rastiservice)
allowed_nginx_site() {
  is_protected "$1" && return 1
  [[ "$1" =~ ^[a-z0-9_.-]*rastisi[a-z0-9_.-]*(\.conf)?$ ]]
}

# PostgreSQL database / role names dedicated to RastiSi
allowed_database() {
  is_protected "$1" && return 1
  [[ "$1" =~ ^rastisi(_[a-z0-9_]+)?$ ]]
}

# Filesystem paths. The REAL path (symlinks resolved) must sit under an
# approved RastiSi-owned root and must not be protected.
allowed_path() {
  local p="$1" real
  [ -n "$p" ] || return 1
  real="$(realpath -m -- "$p" 2>/dev/null)" || return 1
  is_protected "$p" && return 1
  is_protected "$real" && return 1
  case "$real" in
    /srv/rastisi|/srv/rastisi/*|/srv/rastisi_*|/srv/rastisi-*) return 0;;
    /var/www/rastisi|/var/www/rastisi/*|/var/www/rastisi_*|/var/www/rastisi-*) return 0;;
    /var/lib/rastisi|/var/lib/rastisi/*|/var/log/rastisi|/var/log/rastisi/*) return 0;;
    /etc/rastisi|/etc/rastisi/*|/opt/rastisi|/opt/rastisi/*|/opt/rastisi_*|/opt/rastisi-*) return 0;;
    /home/*/rastisi|/home/*/rastisi/*|/home/*/rastisi_*|/home/*/rastisi-*) return 0;;
  esac
  return 1
}
