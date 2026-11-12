#!/usr/bin/env bash
# Install root-owned. Pin code + venv to one release while holding a shared
# deployment lock. Deploy/rollback's exclusive lock cannot overlap these jobs.
set -euo pipefail
base="${RASTISI_RELEASE_BASE:-/srv/rastisi-releases}"
exec 9<"$base/state/deploy.lock"
flock -s -n 9 || { echo 'deployment in progress; job not started' >&2; exit 75; }
release="$(readlink -e "$base/current")"
case "$release" in "$base"/releases/*) ;; *) echo 'invalid current release' >&2; exit 96 ;; esac
export RASTISI_APP_DIR="$release/app"
export RASTISI_VENV="$release/venv"
exec /bin/bash "$release/app/deploy/cron/run_job.sh" "$@"
