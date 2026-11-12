#!/usr/bin/env python3
"""A tiny service manager for the real-application self-test: it plays the part of systemd for ONE unit.

  restart   stop the old gunicorn (SIGTERM, then SIGKILL), re-resolve <base>/current/{app,venv} NOW, start gunicorn there with the
            environment file loaded (systemd's EnvironmentFile) in a new session, return as soon as the process exists
  is-active active while the master process is alive
  show      MainPID

usage: fake_service_manager.py <state_dir> <base_dir> <env_file> <port> <verb> [...]
"""

import os
import signal
import subprocess
import sys
import time

state, base, env_file, port = sys.argv[1:5]
verb = sys.argv[5:]
pid_file = os.path.join(state, "gunicorn.pid")
os.makedirs(state, exist_ok=True)


def read_pid():
    try:
        return int(open(pid_file).read().strip())
    except (OSError, ValueError):
        return 0


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().split()[2] != "Z"
    except (OSError, IndexError):
        return False


def load_env():
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


if verb[:1] == ["restart"]:
    old = read_pid()
    if alive(old):
        os.killpg(old, signal.SIGTERM)
        for _ in range(100):
            if not alive(old):
                break
            time.sleep(0.1)
        if alive(old):
            os.killpg(old, signal.SIGKILL)
    app = os.path.realpath(os.path.join(base, "current", "app"))
    gunicorn = os.path.join(base, "current", "venv", "bin", "gunicorn")
    log = open(os.path.join(state, "gunicorn.log"), "ab")
    proc = subprocess.Popen([gunicorn, "shop_core.wsgi:application", "--bind", "127.0.0.1:%s" % port, "--workers", "2", "--timeout", "60",
                             "--pid", os.path.join(state, "gunicorn.master.pid")],
                            cwd=app, env=load_env(), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    open(pid_file, "w").write("%d\n" % proc.pid)
    time.sleep(0.5)
    sys.exit(0 if alive(proc.pid) else 1)
if verb[:1] == ["is-active"]:
    ok = alive(read_pid())
    print("active" if ok else "inactive")
    sys.exit(0 if ok else 3)
if verb[:1] == ["show"]:
    print(read_pid())
    sys.exit(0)
if verb[:1] == ["stop"]:
    pid = read_pid()
    if alive(pid):
        os.killpg(pid, signal.SIGTERM)
        for _ in range(100):
            if not alive(pid):
                break
            time.sleep(0.1)
        if alive(pid):
            os.killpg(pid, signal.SIGKILL)
    sys.exit(0)
sys.exit(2)
