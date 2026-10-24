#!/usr/bin/env bash
# Backup RastiSi's OWN data: its dedicated PostgreSQL database, public media and
# the unit/nginx files. Never reads another site's database or directories.
#   backup.sh [--db-only]
# Output: $RASTISI_BACKUP_DIR/<UTC timestamp>/{db.dump,media.tar.gz,config.tar.gz,SHA256SUMS,MANIFEST.txt}
# The env file (secrets) is NOT copied.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
load_env; load_db
TS="$(date -u +%Y%m%dT%H%M%SZ)"; OUT="$RASTISI_BACKUP_DIR/$TS"
umask 077; mkdir -p "$OUT"
pg_dump --format=custom --no-owner --file "$OUT/db.dump" "$PGDATABASE"
if [ "${1:-}" != "--db-only" ]; then
  tar -C "$(dirname "${DJANGO_MEDIA_ROOT:-$RASTISI_MEDIA_ROOT_DEFAULT}")" -czf "$OUT/media.tar.gz" "$(basename "${DJANGO_MEDIA_ROOT:-$RASTISI_MEDIA_ROOT_DEFAULT}")"
  tar -czf "$OUT/config.tar.gz" /etc/systemd/system/rastisi-gunicorn.service /etc/systemd/system/rastisi-gunicorn.socket \
      /etc/nginx/sites-available/rastisi.conf 2>/dev/null || true
fi
( cd "$OUT" && sha256sum * > SHA256SUMS )
{ echo "database=$PGDATABASE"; echo "created_utc=$TS"; echo "git=$(git -C "$RASTISI_APP_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"; } > "$OUT/MANIFEST.txt"
# Prove the dump is readable (restore test target is a separate scratch database - see restore.sh --verify).
pg_restore --list "$OUT/db.dump" >/dev/null
info "backup written to $OUT"
echo "$OUT"
