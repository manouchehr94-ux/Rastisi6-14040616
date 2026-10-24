#!/usr/bin/env bash
# Syntax-check rebuild/deployment/nginx/*.conf with the locally installed nginx,
# using throw-away self-signed certificates. Touches nothing outside a temp dir.
#   bash rebuild/checks/nginx_syntax_check.sh
set -eu
command -v nginx >/dev/null || { echo "BLOCKED nginx binary not installed"; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../deployment/nginx" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$T/k.pem" -out "$T/c.pem" -days 1 -subj "/CN=test" >/dev/null 2>&1
# IPv6 listeners are removed only because many CI sandboxes lack IPv6; paths are redirected to the temp dir.
sed -e "s#/etc/letsencrypt/live/rastisi.ir/fullchain.pem#$T/c.pem#" -e "s#/etc/letsencrypt/live/rastisi.ir/privkey.pem#$T/k.pem#" \
    -e '/\[::\]/d' "$HERE/rastisi.conf" > "$T/rastisi.conf"
sed -e '/\[::\]/d' "$HERE/rastisi-http-bootstrap.conf" > "$T/bootstrap.conf"
for f in rastisi bootstrap; do
  printf 'pid %s/%s.pid;\nerror_log %s/%s.err;\nevents {}\nhttp { access_log off; include %s/%s.conf; }\n' "$T" "$f" "$T" "$f" "$T" "$f" > "$T/main_$f.conf"
  nginx -t -c "$T/main_$f.conf" 2>&1 | tail -2
done
# Safety properties of the shipped config (comments ignored)
code() { grep -vE '^[[:space:]]*#' "$@"; }
code "$HERE"/*.conf | grep -q "default_server" && { echo "FAIL default_server present (would capture other sites)"; exit 1; }
code "$HERE"/*.conf | grep -qE "server_name +_;" && { echo "FAIL catch-all server_name"; exit 1; }
code "$HERE/rastisi.conf" | grep -q "private_media" && { echo "FAIL private media mapped"; exit 1; }
echo "PASS nginx syntax and safety properties"
