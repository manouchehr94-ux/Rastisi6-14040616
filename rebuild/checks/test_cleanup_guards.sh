#!/usr/bin/env bash
# Offline test of the cleanup safety predicates. Touches nothing on the host.
#   bash rebuild/checks/test_cleanup_guards.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../deployment/scripts/cleanup_guards.sh"
fail=0
yes() { if "$@"; then :; else echo "FAIL expected ALLOW: $*"; fail=1; fi; }
no()  { if "$@"; then echo "FAIL expected DENY : $*"; fail=1; fi; }

yes allowed_unit rastisi-gunicorn.service
yes allowed_unit rastisi-gunicorn.socket
yes allowed_unit gunicorn-rastisi.service
no  allowed_unit rastiservice.service
no  allowed_unit rastiservice-gunicorn.service
no  allowed_unit nginx.service
no  allowed_unit postgresql.service
no  allowed_unit redis-server.service

yes allowed_nginx_site rastisi.conf
yes allowed_nginx_site old-rastisi-site
no  allowed_nginx_site rastiservice.conf
no  allowed_nginx_site default
no  allowed_nginx_site rastiservice.ir

yes allowed_database rastisi
yes allowed_database rastisi_demo
no  allowed_database rastiservice
no  allowed_database rastiservice_prod
no  allowed_database postgres
no  allowed_database template1

yes allowed_path /srv/rastisi
yes allowed_path /srv/rastisi/venv
yes allowed_path /var/www/rastisi/media
yes allowed_path /var/lib/rastisi/private_media
yes allowed_path /var/log/rastisi
no  allowed_path /srv/rastiservice
no  allowed_path /srv/rastiservice/rastisi
no  allowed_path /var/www/rastiservice.ir
no  allowed_path /var/www
no  allowed_path /srv
no  allowed_path /
no  allowed_path /etc/nginx
no  allowed_path /etc/letsencrypt
no  allowed_path /home
no  allowed_path /srv/rastisi/../rastiservice
no  allowed_path ""

# symlink escape: a link inside an allowed root pointing at a protected tree
T="$(mktemp -d)"; ln -s /srv/rastiservice "$T/rastisi-link" 2>/dev/null
no  allowed_path "$T/rastisi-link"
rm -rf "$T"

# manifest dry-run must REFUSE protected entries and never remove anything
M="$(mktemp)"; printf 'service rastiservice.service\npath /srv/rastiservice\ndatabase rastiservice\nnginx_site /etc/nginx/sites-enabled/rastiservice.conf\n' > "$M"
out="$("$HERE/../deployment/scripts/cleanup_old_rastisi.sh" --execute "$M" 2>&1)"
echo "$out" | grep -q "WOULD" && { echo "FAIL dry-run proposed removal of a protected entry"; fail=1; }
[ "$(echo "$out" | grep -c REFUSED)" = 4 ] || { echo "FAIL expected 4 REFUSED lines"; echo "$out"; fail=1; }
rm -f "$M"

[ "$fail" = 0 ] && echo "PASS cleanup guards" || echo "FAIL cleanup guards"
exit $fail
