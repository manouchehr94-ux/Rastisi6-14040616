#!/usr/bin/env bash
# Rehearse the notifications migration integration in a DISPOSABLE git worktree.
#   - never pushes, never modifies your checkout, never touches a real database (SQLite file inside the worktree)
#   - merges the email-engine PR into the payment-engine integration branch, auto-resolving ONLY the two known textual
#     conflicts (anything else aborts so a human looks at it), then applies the chosen migration strategy and runs
#     verify_graph.py (seeded pre-existing data, forward, backward, forward) plus the notification test suites.
#
#   bash rehearse.sh [PR_REF] [INTEG_REF] [A|B]
#     A = keep both lineages and add a merge migration            (use when the email-engine PR lands SECOND)
#     B = re-point 0005's dependency onto 0004_inbox_engine        (use when the integration branch lands FIRST; linear graph)
#
# Environment: PYTHON (default: python). Set SKIP_TESTS=1 to run only the graph verification.
set -euo pipefail

PR_REF="${1:-origin/kiro/notifications-email-engine-20261104}"
INTEG_REF="${2:-origin/integration/payment-engine-unified-20261104}"
OPTION="${3:-B}"
PYTHON="${PYTHON:-python}"
SCRATCH="$(mktemp -d)/integ"
REPO="$(git rev-parse --show-toplevel)"

cleanup() { cd "$REPO"; git worktree remove --force "$SCRATCH" >/dev/null 2>&1 || true; }
trap cleanup EXIT

git worktree add --detach "$SCRATCH" "$INTEG_REF" >/dev/null
cd "$SCRATCH"
git -c user.name=scratch -c user.email=scratch@example.invalid merge --no-commit --no-ff "$PR_REF" >/dev/null 2>&1 || true

# Resolve exactly the two known conflicts; abort on anything unexpected.
"$PYTHON" - <<'PY'
import re, subprocess, sys
unmerged = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], text=True).split()
KNOWN = {"apps/dashboard/urls.py", "apps/stores/services/domain_verification_service.py", "deploy/cron/rastisi.crontab"}
if set(unmerged) - KNOWN:
    sys.exit(f"UNEXPECTED conflicts, resolve by hand: {sorted(set(unmerged) - KNOWN)}")
pat = re.compile(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", re.S)
def resolve(path, chooser):
    s = open(path, encoding="utf-8").read()
    s = pat.sub(lambda m: chooser(m.group(1), m.group(2)), s)
    assert "<<<<<<<" not in s, path
    open(path, "w", encoding="utf-8").write(s)
if "apps/dashboard/urls.py" in unmerged:   # keep their imports, add notification_admin_views to the `from . import` line
    resolve("apps/dashboard/urls.py", lambda ours, mine: ours.replace("journal_views, payment_reconciliation_views",
                                                                      "journal_views, notification_admin_views, payment_reconciliation_views"))
if "apps/stores/services/domain_verification_service.py" in unmerged:   # keep BOTH hooks, theirs first
    resolve("apps/stores/services/domain_verification_service.py", lambda ours, mine: ours + mine)
if "deploy/cron/rastisi.crontab" in unmerged:   # both sides add independent cron jobs in the same block: keep both
    resolve("deploy/cron/rastisi.crontab", lambda ours, mine: ours + mine)
print("conflicts resolved:", sorted(unmerged))
PY
git add -A >/dev/null

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-shop_core.settings}" DJANGO_DEBUG=True DJANGO_SECRET_KEY=scratch PYTHONPATH=.
M=apps/notifications/migrations

echo "== before: graph as merged =="
"$PYTHON" manage.py makemigrations --check --dry-run 2>&1 | grep -E "Conflicting|No changes" || true

case "$OPTION" in
  A) "$PYTHON" manage.py makemigrations --merge --noinput notifications >/dev/null
     echo "== option A: merge migration created =="; ls $M | grep -E '^0007_merge' ;;
  B) sed -i 's/("notifications", "0003_sms_log_mirror"),/("notifications", "0004_inbox_engine"),/' $M/0005_email_sender_identity_platform_templates.py
     grep -q '0004_inbox_engine' $M/0005_email_sender_identity_platform_templates.py || { echo "retarget failed"; exit 2; }
     echo "== option B: 0005 now depends on 0004_inbox_engine (linear graph) ==" ;;
  *) echo "OPTION must be A or B"; exit 2 ;;
esac

echo "== graph verification with seeded data =="
rm -f db.sqlite3
"$PYTHON" docs/notifications/migration-integration/verify_graph.py

if [ "${SKIP_TESTS:-0}" != "1" ]; then
  echo "== notification suites on the integrated tree =="
  rm -f db.sqlite3
  "$PYTHON" manage.py test apps.notifications apps.dashboard.tests.test_notification_admin \
      apps.portal.tests.test_platform_notification_admin apps.sms --parallel 4 2>&1 | grep -E "^(ERROR|FAIL):|^Ran |^OK|^FAILED|^AssertionError|^'apps/"
fi
echo "== rehearsal finished (worktree removed) =="
