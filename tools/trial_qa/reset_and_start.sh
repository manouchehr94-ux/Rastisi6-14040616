#!/bin/bash
# Disposable E2E environment: NEW database rs_trial_e2e on the local PostgreSQL, server on :8020. Touches nothing else.
set -e
REPO="$(cd "$(dirname "$0")/../.." && pwd)"; PY="${PY:-python}"
pkill -f "tools/trial_qa/server.py" || true; sleep 1
export PGPASSWORD="${PGPASSWORD:-rs}"
psql -h localhost -U "${PGUSER:-rs}" -d postgres -c "DROP DATABASE IF EXISTS rs_trial_e2e" -c "CREATE DATABASE rs_trial_e2e"
export DATABASE_URL="postgres://${PGUSER:-rs}:${PGPASSWORD}@localhost:5432/rs_trial_e2e" DJANGO_DEBUG=True RASTISI_DEV_OTP_CODE=123456 E2E_PORT=8020 REPO="$REPO"
cd "$REPO"; $PY manage.py migrate -v0 >/dev/null 2>&1; $PY tools/trial_qa/seed.py
nohup $PY tools/trial_qa/server.py > /tmp/trial_e2e_server.log 2>&1 &
sleep 6; cat /tmp/trial_e2e_server.log
