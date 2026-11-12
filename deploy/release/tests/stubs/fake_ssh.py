#!/usr/bin/env python3
"""Test double for `ssh host <command>`: runs the real gate with SSH_ORIGINAL_COMMAND, with injectable network faults.

usage: fake_ssh.py <fault_file> <command>      (stdin is passed through)
faults (JSON, decremented as used):
  refuse: N               the next N calls fail with 255 before reaching the server (connection refused / timeout)
  lose_response_for: "activate"|"rollback"|"stage"|"follow"
                          the NEXT call whose verb matches reaches the server and is executed, but the response is lost (255)
"""

import json
import os
import subprocess
import sys

fault_file, command = sys.argv[1], sys.argv[2]
faults = json.load(open(fault_file)) if os.path.exists(fault_file) else {}
verb = command.split()[0]

if faults.get("refuse", 0) > 0:
    faults["refuse"] -= 1
    json.dump(faults, open(fault_file, "w"))
    sys.stderr.write("ssh: connect to host: Connection refused\n")
    sys.exit(255)

data = sys.stdin.buffer.read() if verb == "stage" else b""
proc = subprocess.run([sys.executable, os.environ["GATE"]], input=data, capture_output=True, env=dict(os.environ, SSH_ORIGINAL_COMMAND=command))
if faults.get("lose_response_for") == verb:
    del faults["lose_response_for"]
    json.dump(faults, open(fault_file, "w"))
    sys.stderr.write("client_loop: send disconnect: Broken pipe\n")
    sys.exit(255)
sys.stdout.buffer.write(proc.stdout)
sys.stderr.buffer.write(proc.stderr)
sys.exit(proc.returncode)
