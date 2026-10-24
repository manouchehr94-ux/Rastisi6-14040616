#!/usr/bin/env bash
# Offline checks runnable on any developer/CI machine (no server, no secrets).
#   bash rebuild/checks/run_all_checks.sh [python-executable]
set -u
PY="${1:-python}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"; rc=0
step() { echo; echo "== $*"; }

step "shell syntax of deployment scripts";    for f in rebuild/deployment/scripts/*.sh rebuild/checks/*.sh; do bash -n "$f" || rc=1; done
step "cleanup safety predicates";             bash rebuild/checks/test_cleanup_guards.sh || rc=1
step "django system check";                   "$PY" manage.py check || rc=1
step "migrations are in sync with models";    "$PY" manage.py makemigrations --check --dry-run || rc=1
step "targets manifest is valid JSON";        "$PY" -c "import json;d=json.load(open('rebuild/manifests/demo_stores.json'));assert set(d['stores'])=={'demo_v5','demo_arch02'}" || rc=1
step "rebuild tooling tests";                 "$PY" manage.py test apps.stores.tests.test_demo_bundle apps.stores.tests.test_demo_bundle_converter --noinput || rc=1
echo; [ $rc = 0 ] && echo "ALL OFFLINE CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $rc
