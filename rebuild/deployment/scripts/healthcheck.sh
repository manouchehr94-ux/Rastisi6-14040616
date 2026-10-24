#!/usr/bin/env bash
# Quick health check: application self-check + each public host answers over the
# local socket path. Exit 0 healthy / 1 unhealthy.
set -uo pipefail
. "$(dirname "$0")/_common.sh"
load_env
rc=0
python manage.py rastisi_healthcheck || rc=1
SOCK=/run/rastisi/gunicorn.sock
for host in rastisi.ir platformadmins.rastisi.ir demo-v5.rastisi.ir demo-arch02.rastisi.ir; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --unix-socket "$SOCK" -H "Host: $host" -H 'X-Forwarded-Proto: https' "http://localhost/robots.txt" || echo 000)
  if [ "$code" = 200 ]; then echo "OK   $host robots.txt $code"; else echo "FAIL $host robots.txt $code"; rc=1; fi
done
exit $rc
