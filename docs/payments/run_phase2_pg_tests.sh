#!/bin/bash
# usage: p2_runpg.sh <outfile> <parallel> <test labels...>
# Throwaway PostgreSQL 16 inside the sandbox; started AND stopped within this one invocation; data dir removed afterwards.
set -u
OUTF=$1; PAR=$2; shift 2
WT=${WT:-$(git rev-parse --show-toplevel)}
PGBIN=$(readlink -f /projects/sandbox/.venv/lib/python3.11/site-packages/pgserver/pginstall/bin)
PGD=/projects/sandbox/.pgp2_tmp
R="setpriv --reuid=65534 --regid=65534 --clear-groups"
rm -rf "$PGD" && mkdir -p "$PGD" && chown 65534:65534 "$PGD"
{
  echo "HEAD=$(git -C $WT rev-parse HEAD) dirty=$(git -C $WT status --short | wc -l)"
  $R $PGBIN/initdb -D $PGD/data -U rastisi_p2 -A trust --encoding=UTF8 >/dev/null 2>&1 || { echo "BLOCKER: initdb failed"; exit 90; }
  $R $PGBIN/pg_ctl -D $PGD/data -o "-c listen_addresses=127.0.0.1 -c port=55441 -c unix_socket_directories=$PGD -c max_connections=300" -l $PGD/log.txt -w start >/dev/null 2>&1 || { echo "BLOCKER: pg_ctl start failed"; exit 91; }
  $R $PGBIN/psql -h 127.0.0.1 -p 55441 -U rastisi_p2 -d postgres -Atc "create database rastisi_p2;" >/dev/null || { echo "BLOCKER: createdb failed"; exit 92; }
  echo "SERVER: $($R $PGBIN/psql -h 127.0.0.1 -p 55441 -U rastisi_p2 -d postgres -Atc "select 'PostgreSQL '||current_setting('server_version');")"
  export DATABASE_URL="postgresql://rastisi_p2@127.0.0.1:55441/rastisi_p2"
  cd $WT
  echo "CMD: manage.py test $* --parallel $PAR"
  /projects/sandbox/.venv/bin/python manage.py test "$@" --parallel $PAR > $OUTF 2>&1
  echo "TEST_EXIT=$?"
  $R $PGBIN/pg_ctl -D $PGD/data -m fast -w stop >/dev/null 2>&1
  echo "SERVER_STOPPED=$?"
} 
rm -rf "$PGD"
