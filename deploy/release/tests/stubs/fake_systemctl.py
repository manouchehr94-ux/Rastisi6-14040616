#!/usr/bin/env python3
"""Test double for systemctl. Behaves like systemd where it matters to the release tool:

  * ``restart`` re-resolves <base>/current at THAT moment (a running service keeps serving the directory it started in);
  * ``show -p MainPID --value`` returns the pid of the 'running' service whose /proc/<pid>/cwd is that resolved directory;
  * flags in <dir>/flags.json can make restart fail or make the service report inactive.

usage: fake_systemctl.py <fake_dir> <verb> [...]
"""

import json
import os
import sys
import time

fake = sys.argv[1]
verb = sys.argv[2:]
flags_path = os.path.join(fake, "flags.json")
state_path = os.path.join(fake, "service.json")
flags = json.load(open(flags_path)) if os.path.exists(flags_path) else {}
state = json.load(open(state_path)) if os.path.exists(state_path) else {"pid": 0, "restarts": 0}
log = open(os.path.join(fake, "calls.log"), "a")
log.write("%s %s\n" % (time.time(), " ".join(verb)))
log.close()

if verb[:1] == ["restart"]:
    if flags.get("restart_delay"):
        time.sleep(float(flags["restart_delay"]))
    if flags.get("fail_restart"):
        sys.stderr.write("Job for service failed (simulated)\n")
        sys.exit(1)
    cwd = os.path.realpath(os.path.join(flags["base"], "current", "app"))
    state["pid"] = state.get("pid", 0) + 1 + 1000
    state["restarts"] = state.get("restarts", 0) + 1
    proc_dir = os.path.join(fake, "proc", str(state["pid"]))
    os.makedirs(proc_dir, exist_ok=True)
    link = os.path.join(proc_dir, "cwd")
    if os.path.lexists(link):
        os.unlink(link)
    os.symlink(cwd, link)
    json.dump(state, open(state_path, "w"))
    sys.exit(0)
if verb[:1] == ["is-active"]:
    if flags.get("service_inactive") or not state.get("pid"):
        print("inactive")
        sys.exit(3)
    print("active")
    sys.exit(0)
if verb[:1] == ["show"]:
    print(state.get("pid", 0))
    sys.exit(0)
sys.stderr.write("unsupported verb: %s\n" % verb)
sys.exit(2)
