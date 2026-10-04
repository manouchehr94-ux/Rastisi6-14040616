# usage: run.sh <tree> <tag> <port>
tree="$1"; tag="$2"; port="$3"; cd "$tree"
export DJANGO_DEBUG=True DJANGO_SECRET_KEY=r4-qa-secret-not-for-prod; unset DATABASE_URL
out=/tmp/claude-0/r4v/$tag; rm -rf $out; mkdir -p $out; rm -f db.sqlite3
PY=/usr/local/bin/python
$PY manage.py migrate -v0 >$out/migrate.log 2>&1 || { echo MIGRATE FAILED >$out/summary.txt; exit 3; }
$PY /tmp/claude-0/r4v/seed.py >$out/seed.log 2>&1 || { echo SEED FAILED >$out/summary.txt; exit 4; }
timeout 3000 $PY manage.py qa_storefront_builder_r4 --store-slug akhlaghi --username r4owner --port $port --phase3 --report-dir $out/report >$out/cmd.log 2>&1
echo "cmd rc=$?" >$out/summary.txt
echo done >>$out/summary.txt
