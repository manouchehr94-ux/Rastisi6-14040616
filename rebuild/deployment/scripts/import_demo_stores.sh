#!/usr/bin/env bash
# Import the two demo stores from a bundle, then verify. Run as the rastisi user.
#   import_demo_stores.sh /path/to/bundle
# Order: validate (no DB) -> backup -> import -> provision settings -> verify.
# The accounts are created separately and interactively (create_install_accounts).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
B="${1:-}"; [ -d "$B" ] || die "usage: import_demo_stores.sh <bundle-dir>"
load_env
python manage.py validate_demo_bundle "$B" || { rc=$?; die "bundle validation did not PASS (exit $rc); nothing imported"; }
"$(dirname "$0")/backup.sh" --db-only
python manage.py import_demo_bundle "$B"
python manage.py provision_shop_settings --store demo-v5 --store demo-arch02
python manage.py verify_demo_integrity --http
