#!/usr/bin/env python3
"""Stand-in for rastisi_smoke.py: a release whose app/ contains a file named BROKEN fails its smoke test."""

import argparse
import json
import os
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--base-url")
ap.add_argument("--host", default="")
ap.add_argument("--release-dir", default="")
ap.add_argument("--expect-release", default="")
args = ap.parse_args()
control = json.load(open(os.environ["STUB_CONTROL"])) if os.path.exists(os.environ.get("STUB_CONTROL", "")) else {}
time.sleep(float(control.get("smoke_delay", 0)))
hold = control.get("smoke_wait_for_file")          # deterministic "deployment in progress": block until the test creates this file
if hold:
    deadline = time.time() + 120
    while not os.path.exists(hold) and time.time() < deadline:
        time.sleep(0.05)
if os.path.exists(os.path.join(args.release_dir, "BROKEN")):
    print(json.dumps({"ok": False, "failures": ["login page 200: status 500"], "passed": []}))
    sys.exit(1)
print(json.dumps({"ok": True, "passed": ["stub"], "failures": []}))
