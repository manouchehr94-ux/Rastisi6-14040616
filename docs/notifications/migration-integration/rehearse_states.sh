#!/usr/bin/env bash
# Run the three persistent-state rehearsals (Option A) on a tree that already contains the merge migration. Never touches a real database:
# each scenario uses a throw-away SQLite file in the tree's root. PYTHON=<interpreter> to override.
set -euo pipefail
PYTHON="${PYTHON:-python}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-shop_core.settings}" DJANGO_DEBUG=True DJANGO_SECRET_KEY=scratch PYTHONPATH=.
for s in payment_db pr37_db fresh_db; do
  rm -f db.sqlite3
  "$PYTHON" docs/notifications/migration-integration/verify_persistent_states.py "$s"
done
rm -f db.sqlite3
