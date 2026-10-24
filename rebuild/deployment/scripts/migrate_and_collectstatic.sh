#!/usr/bin/env bash
# Apply migrations and collect static files. Takes a database backup first when
# there is anything to migrate (skip with RASTISI_SKIP_BACKUP=1 on first install).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
load_env
python manage.py check                      # errors abort
python manage.py check --deploy || true      # warnings (e.g. HSTS=0 during staged rollout) are informational
if [ "${RASTISI_SKIP_BACKUP:-0}" != 1 ]; then
  "$(dirname "$0")/backup.sh" --db-only
fi
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py rastisi_healthcheck
info "migrate + collectstatic done"
