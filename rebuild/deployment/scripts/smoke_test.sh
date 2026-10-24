#!/usr/bin/env bash
# External smoke test of the live deployment (HTTPS, through nginx).
#   smoke_test.sh [base-domain]    (default rastisi.ir)
# Checks status codes, the platform-admin login host, static and media files.
# Read-only: only GET requests, no credentials are used or sent.
set -uo pipefail
D="${1:-rastisi.ir}"; fail=0
check() { # url expected-status-regex description
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$1" || echo 000)
  if [[ "$code" =~ ^($2)$ ]]; then echo "PASS $3 [$code]"; else echo "FAIL $3 [$code] $1"; fail=1; fi
}
check "https://$D/"                              200            "central site"
check "https://$D/login/"                        200            "central login (owners/members)"
check "https://platformadmins.$D/login/"         200            "platform admin login host"
check "https://platformadmins.$D/"               "200|301|302"  "platform admin requires login"
check "https://$D/admin/"                        "200|301|302|404" "no store-less django admin leak"
for h in demo-v5 demo-arch02; do
  check "https://$h.$D/"                         200            "$h home"
  check "https://$h.$D/products/"                200            "$h product list"
  check "https://$h.$D/cart/"                    200            "$h cart"
  check "https://$h.$D/robots.txt"               200            "$h robots"
  check "https://$h.$D/admin-portal/"            "200|302"       "$h admin-portal gated"
done
check "https://$D/static/admin/css/base.css"     200            "static files served"
# one real media file: first image referenced by a demo product page
img=$(curl -s --max-time 15 "https://demo-v5.$D/products/" | grep -o '/media/[^"'"'"' )]*' | head -1)
if [ -n "$img" ]; then check "https://demo-v5.$D$img" 200 "media file $img"; else echo "BLOCKED no /media/ image found on demo-v5 product list (data not imported?)"; fail=1; fi
exit $fail
