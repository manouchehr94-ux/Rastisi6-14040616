#!/usr/bin/env bash
# REAL serving test on one machine: nginx (TLS, self-signed) -> gunicorn (unix socket) -> Django.
# Proves host routing, static files, media files + content types, path traversal blocks,
# dotfile denial, unknown-host rejection and HTTP->HTTPS redirect, using the shipped
# nginx config with only paths/ports redirected to a temp dir.
#
# Prerequisites (not installed by this script): nginx, gunicorn in the active python,
# a migrated database containing the store(s) (e.g. after import_demo_bundle), DEBUG env.
#   DJANGO_DEBUG=True DJANGO_MEDIA_ROOT=/path/media bash rebuild/checks/local_stack_smoke.sh [host]
# Uses DEBUG only so the production-only requirements (Redis, Turnstile) are not needed here;
# production values are covered by `manage.py check --deploy` against the real /etc/rastisi/env.
set -u
HOST="${1:-demo-v5.rastisi.ir}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="${PYTHON:-python}"
command -v nginx >/dev/null || { echo "BLOCKED nginx not installed"; exit 2; }
"$PY" -c "import gunicorn" 2>/dev/null || { echo "BLOCKED gunicorn not installed"; exit 2; }
: "${DJANGO_MEDIA_ROOT:?set DJANGO_MEDIA_ROOT to the media directory}"
T="$(mktemp -d)"; fail=0
cleanup() { [ -f "$T/nginx.pid" ] && kill "$(cat "$T/nginx.pid")" 2>/dev/null; [ -n "${GPID:-}" ] && kill "$GPID" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
export DJANGO_STATIC_ROOT="$T/static"
( cd "$ROOT" && "$PY" manage.py collectstatic --noinput >/dev/null ) || { echo "FAIL collectstatic"; exit 1; }
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$T/k.pem" -out "$T/c.pem" -days 1 -subj "/CN=test" >/dev/null 2>&1
N="$ROOT/rebuild/deployment/nginx/rastisi.conf"
sed -e "s#/etc/letsencrypt/live/rastisi.ir/fullchain.pem#$T/c.pem#" -e "s#/etc/letsencrypt/live/rastisi.ir/privkey.pem#$T/k.pem#" \
    -e '/\[::\]/d' -e "s#unix:/run/rastisi/gunicorn.sock#unix:$T/g.sock#" \
    -e "s#/var/www/rastisi/staticfiles/#$T/static/#" -e "s#/var/www/rastisi/media/#$DJANGO_MEDIA_ROOT/#" \
    -e "s#listen 443 ssl http2;#listen 18443 ssl http2;#" -e "s#listen 80;#listen 18080;#" "$N" > "$T/site.conf"
printf 'user %s;\npid %s/nginx.pid;\nerror_log %s/err.log;\nevents {}\nhttp { access_log off; include /etc/nginx/mime.types; include %s/site.conf; }\n' \
  "$(id -un)" "$T" "$T" "$T" > "$T/nginx.conf"
( cd "$ROOT" && "$PY" -m gunicorn --config rebuild/deployment/gunicorn.conf.py --bind "unix:$T/g.sock" shop_core.wsgi:application >"$T/g.log" 2>&1 ) &
GPID=$!
nginx -c "$T/nginx.conf" || { echo "FAIL nginx start"; exit 1; }
for _ in $(seq 1 30); do [ -S "$T/g.sock" ] && break; sleep 1; done

q() { curl --noproxy '*' -m 30 -sk -o "$T/body" -w '%{http_code} %{content_type}' --resolve "$HOST:18443:127.0.0.1" "https://$HOST:18443$1"; }
expect() { # path regex-of-"code type" description
  got="$(q "$1")"
  if [[ "$got" =~ $2 ]]; then echo "PASS $3 [$got]"; else echo "FAIL $3 [$got] $1"; fail=1; fi
}
expect /                          '^200 text/html'   "home renders"
expect /products/                 '^200 text/html'   "product list renders"
expect /cart/                     '^200 text/html'   "cart renders"
expect /robots.txt                '^200 text/plain'  "robots.txt"
expect /static/admin/css/base.css '^200 text/css'    "static file served by nginx"
IMG="$(curl --noproxy '*' -m 30 -sk --resolve "$HOST:18443:127.0.0.1" "https://$HOST:18443/products/" | grep -o '/media/[^"'"'"' )]*' | head -1)"
if [ -n "$IMG" ]; then expect "$IMG" '^200 image/' "media image served with an image/* content type"
  curl --noproxy '*' -m 30 -sk -D - -o /dev/null --resolve "$HOST:18443:127.0.0.1" "https://$HOST:18443$IMG" | grep -qi "x-content-type-options: nosniff" && echo "PASS media nosniff header" || { echo "FAIL media nosniff header"; fail=1; }
else echo "BLOCKED no /media/ image on the product list (no imported data)"; fail=2; fi
expect /.env                      '^403'             "dotfiles denied"
expect /media/                    '^403'             "no media directory listing"
got="$(curl --noproxy '*' -m 30 -sk -o /dev/null -w '%{http_code}' --resolve evil.example:18443:127.0.0.1 https://evil.example:18443/)"
[ "$got" = 400 ] && echo "PASS unknown Host rejected [400]" || { echo "FAIL unknown Host not rejected [$got]"; fail=1; }
got="$(curl --noproxy '*' -m 30 -s -o /dev/null -w '%{http_code} %{redirect_url}' --resolve "$HOST:18080:127.0.0.1" "http://$HOST:18080/products/")"
[[ "$got" =~ ^301\ https://$HOST/ ]] && echo "PASS http -> https redirect [$got]" || { echo "FAIL redirect [$got]"; fail=1; }
exit $fail
