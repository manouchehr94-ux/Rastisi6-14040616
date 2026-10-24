#!/usr/bin/env bash
# Shared helpers. Sourced by the other scripts - never run directly.
# Every path below is RastiSi-specific; nothing here touches rastiservice.ir.

RASTISI_APP_DIR="${RASTISI_APP_DIR:-/srv/rastisi}"
RASTISI_VENV="${RASTISI_VENV:-/srv/rastisi/venv}"
RASTISI_ENV_FILE="${RASTISI_ENV_FILE:-/etc/rastisi/env}"
RASTISI_BACKUP_DIR="${RASTISI_BACKUP_DIR:-/var/backups/rastisi}"
RASTISI_MEDIA_ROOT_DEFAULT=/var/www/rastisi/media

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[rastisi] $*"; }

load_env() {
  [ -r "$RASTISI_ENV_FILE" ] || die "cannot read $RASTISI_ENV_FILE"
  set -a; . "$RASTISI_ENV_FILE"; set +a
  [ -f "$RASTISI_VENV/bin/activate" ] && . "$RASTISI_VENV/bin/activate"
  cd "$RASTISI_APP_DIR" || die "app dir $RASTISI_APP_DIR missing"
}

# Parse DATABASE_URL (postgres://user:pass@host:port/db) into PG* variables
# WITHOUT printing the password. Refuses to continue if the database name is
# not the dedicated RastiSi one.
load_db() {
  [ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL is not set"
  eval "$(python - <<'PY'
import os, shlex
from urllib.parse import urlparse, unquote
u = urlparse(os.environ["DATABASE_URL"])
for k, v in (("PGHOST", u.hostname or ""), ("PGPORT", str(u.port or 5432)),
             ("PGUSER", unquote(u.username or "")), ("PGPASSWORD", unquote(u.password or "")),
             ("PGDATABASE", u.path.lstrip("/"))):
    print(f"export {k}={shlex.quote(v)}")
PY
)"
  case "$PGDATABASE" in
    rastisi|rastisi_*) ;;
    *) die "refusing: database '$PGDATABASE' is not a dedicated RastiSi database (must be 'rastisi' or 'rastisi_*')";;
  esac
}
