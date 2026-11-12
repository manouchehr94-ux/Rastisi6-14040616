#!/usr/bin/env bash
# Builds a disposable Ubuntu 24.04 runtime. Dependencies must be the tested
# lock/wheelhouse (CI: .ci-deps), not a fresh production dependency resolution.
set -euo pipefail
repo="$(git rev-parse --show-toplevel)"
deps="$(realpath "${1:-.ci-deps}")"
[ -f "$deps/requirements.lock" ] && [ -d "$deps/wheelhouse" ]
name="rastisi-installed-$$"
image="rastisi-installed-runtime"
docker build -f "$repo/deploy/release/selftest/Dockerfile" -t "$image" "$repo/deploy/release/selftest"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$name" --mount "type=bind,src=$repo,dst=/repo,readonly" --mount "type=bind,src=$deps,dst=/deps,readonly" "$image" sleep infinity >/dev/null
docker exec "$name" /opt/test-venv/bin/pip install --no-index --find-links /deps/wheelhouse --require-hashes --no-deps -r /deps/requirements.lock
docker exec "$name" /opt/test-venv/bin/pip check
docker exec "$name" python3 /repo/deploy/release/selftest/installed_layout_test.py
