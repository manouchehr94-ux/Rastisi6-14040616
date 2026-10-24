#!/usr/bin/env bash
# One-time host preparation for RastiSi (run as root on the VPS, AFTER review).
#   provision_host.sh [--dry-run]
# Creates ONLY RastiSi-owned users, directories and unit files. It never edits
# or removes anything that belongs to another site (rastiservice.ir), never
# touches PostgreSQL/Redis/nginx global configuration, and never overwrites an
# existing /etc/rastisi/env.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then echo "DRY-RUN: $*"; else "$@"; fi; }

[ "$(id -u)" = 0 ] || [ "$DRY" = 1 ] || { echo "run as root"; exit 1; }

id rastisi >/dev/null 2>&1 || run useradd --system --home /srv/rastisi --shell /usr/sbin/nologin rastisi
for d in /srv/rastisi /var/www/rastisi/staticfiles /var/www/rastisi/media /var/www/rastisi/acme \
         /var/lib/rastisi/private_media /var/log/rastisi /etc/rastisi /var/backups/rastisi; do
  run install -d -o rastisi -g rastisi -m 0750 "$d"
done
# nginx must be able to read static/media
run chmod 0755 /var/www/rastisi /var/www/rastisi/staticfiles /var/www/rastisi/media /var/www/rastisi/acme
run chgrp -R www-data /var/www/rastisi/media /var/www/rastisi/staticfiles
run chmod -R g+rX /var/www/rastisi/media /var/www/rastisi/staticfiles
run chmod 0750 /etc/rastisi; run chown root:rastisi /etc/rastisi

if [ ! -e /etc/rastisi/env ]; then
  run install -o root -g rastisi -m 0640 "$HERE/rastisi.env.example" /etc/rastisi/env
  echo "Created /etc/rastisi/env from the template: EDIT every CHANGE_ME value now."
else
  echo "/etc/rastisi/env already exists - left untouched."
fi

for u in rastisi-gunicorn.service rastisi-gunicorn.socket; do
  if [ -e "/etc/systemd/system/$u" ] && ! cmp -s "$HERE/systemd/$u" "/etc/systemd/system/$u"; then
    echo "WARNING: /etc/systemd/system/$u differs from the repository copy - not overwritten."
  else
    run install -m 0644 "$HERE/systemd/$u" "/etc/systemd/system/$u"
  fi
done
run systemctl daemon-reload
if [ ! -e /etc/nginx/sites-available/rastisi.conf ]; then
  run install -m 0644 "$HERE/nginx/rastisi.conf" /etc/nginx/sites-available/rastisi.conf
fi
echo "Next: edit /etc/rastisi/env, deploy the code, then see docs/rebuild/INSTALL_GUIDE.md."
echo "Nothing was enabled, started or reloaded by this script."
