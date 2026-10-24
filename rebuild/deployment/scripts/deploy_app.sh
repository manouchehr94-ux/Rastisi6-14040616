#!/usr/bin/env bash
# Install the application release into /srv/rastisi (run as the rastisi user).
#   deploy_app.sh <path-to-unpacked-release>
# Creates/updates the venv, installs pinned requirements, then runs
# migrate_and_collectstatic.sh. Does not start or restart any service.
set -euo pipefail
. "$(dirname "$0")/_common.sh"
SRC="${1:-}"; [ -d "$SRC" ] || die "usage: deploy_app.sh <unpacked-release-dir>"
[ "$(cd "$SRC" && pwd)" = "$(cd "$RASTISI_APP_DIR" && pwd 2>/dev/null || echo none)" ] || \
  rsync -a --delete --exclude 'venv/' --exclude 'db.sqlite3' --exclude 'media/' --exclude 'private_media/' \
        --exclude 'staticfiles/' --exclude '.git/' "$SRC"/ "$RASTISI_APP_DIR"/
[ -d "$RASTISI_VENV" ] || python3 -m venv "$RASTISI_VENV"
"$RASTISI_VENV/bin/pip" install --quiet --upgrade pip
"$RASTISI_VENV/bin/pip" install --quiet -r "$RASTISI_APP_DIR/rebuild/deployment/requirements-production.txt"
exec "$RASTISI_APP_DIR/rebuild/deployment/scripts/migrate_and_collectstatic.sh"
