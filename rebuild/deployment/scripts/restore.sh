#!/usr/bin/env bash
# Restore (rollback) from a backup made by backup.sh.
#   restore.sh <backup-dir> --verify            # restore into a scratch DB 'rastisi_restoretest', then drop it
#   restore.sh <backup-dir> --apply --yes       # replace the live 'rastisi' database (stop the app first!)
# Safety: only databases named rastisi / rastisi_* are ever touched; sha256 of
# every artifact is verified before anything is changed.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
B="${1:-}"; MODE="${2:-}"; [ -d "$B" ] || die "usage: restore.sh <backup-dir> --verify|--apply --yes"
load_env; load_db
( cd "$B" && sha256sum -c SHA256SUMS ) || die "backup checksum mismatch - refusing"
case "$MODE" in
  --verify)
    SCRATCH=rastisi_restoretest
    # Creating a scratch database needs CREATEDB: set RASTISI_PG_SUDO=1 to run these
    # four statements as the local postgres superuser instead of the app role.
    SU=(); [ "${RASTISI_PG_SUDO:-0}" = 1 ] && SU=(sudo -u postgres)
    "${SU[@]}" psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
    cat "$B/db.dump" | "${SU[@]}" pg_restore --no-owner --dbname "$SCRATCH"
    n=$("${SU[@]}" psql -d "$SCRATCH" -Atc "select count(*) from stores_store")
    "${SU[@]}" psql -d postgres -c "DROP DATABASE $SCRATCH"
    info "restore verified: $n store row(s) in the scratch restore"
    ;;
  --apply)
    [ "${3:-}" = "--yes" ] || die "add --yes to confirm replacing database '$PGDATABASE'"
    systemctl is-active --quiet rastisi-gunicorn.service && die "stop rastisi-gunicorn first (systemctl stop rastisi-gunicorn)"
    pg_restore --clean --if-exists --no-owner --dbname "$PGDATABASE" "$B/db.dump"
    if [ -f "$B/media.tar.gz" ]; then
      tar -C "$(dirname "${DJANGO_MEDIA_ROOT:-$RASTISI_MEDIA_ROOT_DEFAULT}")" -xzf "$B/media.tar.gz"
    fi
    info "restored database $PGDATABASE from $B; start the service and run healthcheck.sh"
    ;;
  *) die "mode must be --verify or --apply";;
esac
