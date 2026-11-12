#!/usr/bin/env python3
"""SSH forced command for the deploy user (standard library only). One fixed list of verbs, strictly validated. No shell, no
arbitrary commands, no file paths from the caller.

authorized_keys (see deploy/release/examples/authorized_keys.example):
    restrict,command="/usr/bin/python3 /usr/local/lib/rastisi/rastisi_gate.py" ssh-ed25519 AAAA... github-actions-deploy

Verbs (the original command line arrives in SSH_ORIGINAL_COMMAND):
    version
    status
    stage    <sha40> <sha256>                 artifact (tar.gz) is read from STDIN, verified, unpacked, venv built
    activate <release_id> <sha40> <from_sha40|-> [allow-migrations] [destructive-ack=<phrase>] [dry-run] [run=<run_id>]
    rollback [<release_id>|previous] [unsafe-ack=<phrase>] [run=<run_id>]
    follow   <run_id> <offset>                prints new log bytes, then a STATE line (reconnectable at any time)
    result   <run_id>

``run=<run_id>`` is the caller's idempotency key: when the connection drops after the server started a run but before the caller read
"RUN <id>", the caller repeats the same request with the same id and the server answers with the existing run instead of starting a second
one (a second ``rollback`` would flip the system back again).

``activate`` and ``rollback`` run DETACHED (own session, supervised): losing the SSH connection can neither interrupt nor
duplicate a deployment. The caller reconnects and keeps calling ``follow`` until STATE is 'done'.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rastisi_common as C  # noqa: E402

HERE = Path(__file__).resolve().parent
RELEASE_TOOL = HERE / "rastisi_release.py"
TOOL_VERSION_FILE = HERE / "TOOLING_VERSION"
MAX_FOLLOW_BYTES = 256 * 1024
PHRASE_RE = re.compile(r"^[A-Za-z0-9-]{10,120}$")


def out(line=""):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def fail(code, message):
    sys.stderr.write(C.redact(message) + "\n")
    return code


def tool_version():
    try:
        return TOOL_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def run_dir(cfg, run_id):
    if not C.RUN_ID_RE.match(run_id or ""):
        raise ValueError("invalid run id")
    return cfg.state / "runs" / run_id


def release_cmd(*args):
    return [sys.executable, str(RELEASE_TOOL)] + list(args)


def spawn_detached(cfg, run_id, argv):
    """Start ``argv`` under a supervisor in its own session. Returns immediately. The supervisor records the exit code even if the
    tool is killed, so a follower can always tell 'running' from 'done' from 'died'."""
    rd = cfg.state / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    log = open(str(rd / "log"), "ab", buffering=0)
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--supervise", run_id] + argv,
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, close_fds=True, start_new_session=True,
        env=dict(os.environ),
    )
    (rd / "pid").write_text("%d\n" % proc.pid, encoding="utf-8")
    return proc.pid


def supervise(run_id, argv):
    cfg = C.Config()
    rd = run_dir(cfg, run_id)
    proc = subprocess.run(argv)
    marker = rd / "exit_code"
    if not marker.exists():
        marker.write_text("%d\n" % (proc.returncode if proc.returncode >= 0 else 128 - proc.returncode), encoding="utf-8")
    return 0


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def v_stage(cfg, argv):
    if len(argv) != 2 or not C.SHA_RE.match(argv[0]) or not C.SHA256_RE.match(argv[1]):
        return fail(C.EXIT_POLICY, "usage: stage <sha40> <sha256>")
    incoming = cfg.staging
    incoming.mkdir(parents=True, exist_ok=True)
    target = incoming / ("incoming-%s-%d.tar.gz" % (C.utc_stamp(), os.getpid()))
    limit = cfg.int("max_artifact_mb", 400) * 1024 * 1024
    size = 0
    import hashlib
    h = hashlib.sha256()
    try:
        with open(str(target), "wb") as fh:
            while True:
                block = sys.stdin.buffer.read(1 << 20)
                if not block:
                    break
                size += len(block)
                if size > limit:
                    return fail(C.EXIT_POLICY, "artifact exceeds %d MB" % (limit // (1024 * 1024)))
                h.update(block)
                fh.write(block)
        if h.hexdigest() != argv[1]:
            return fail(C.EXIT_POLICY, "artifact checksum mismatch: received %s" % h.hexdigest())
        actor = os.environ.get("RASTISI_ACTOR", "")
        proc = subprocess.run(release_cmd("stage", "--artifact", str(target), "--sha", argv[0], "--sha256", argv[1], "--actor", actor))
        return proc.returncode
    finally:
        try:
            target.unlink()
        except FileNotFoundError:
            pass


def start_or_resume(cfg, given_run_id, cmd):
    """Start the run, or return the one already started under this id (idempotent)."""
    run_id = given_run_id or "%s-%s" % (C.utc_stamp(), os.urandom(4).hex())
    if (cfg.state / "runs" / run_id / "pid").exists():
        out("RUN %s" % run_id)
        return 0
    spawn_detached(cfg, run_id, cmd + ["--run-id", run_id])
    out("RUN %s" % run_id)
    return 0


def split_run_flag(argv):
    given = ""
    rest = []
    for a in argv:
        if a.startswith("run="):
            given = a.split("=", 1)[1]
            if not C.RUN_ID_RE.match(given):
                raise ValueError("invalid run id")
        else:
            rest.append(a)
    return given, rest


def v_activate(cfg, argv):
    given, argv = split_run_flag(argv)
    if len(argv) < 3 or not C.RELEASE_ID_RE.match(argv[0]) or not C.SHA_RE.match(argv[1]) or not (argv[2] == "-" or C.SHA_RE.match(argv[2])):
        return fail(C.EXIT_POLICY, "usage: activate <release_id> <sha40> <from_sha40|-> [flags]")
    cmd = release_cmd("activate", "--id", argv[0], "--expect-sha", argv[1])
    if argv[2] != "-":
        cmd += ["--from-sha", argv[2]]
    for flag in argv[3:]:
        if flag == "allow-migrations":
            cmd.append("--allow-migrations")
        elif flag == "dry-run":
            cmd.append("--dry-run")
        elif flag.startswith("destructive-ack=") and PHRASE_RE.match(flag.split("=", 1)[1]):
            cmd += ["--destructive-ack", flag.split("=", 1)[1]]
        else:
            return fail(C.EXIT_POLICY, "unknown flag: %s" % flag[:40])
    return start_or_resume(cfg, given, cmd)


def v_rollback(cfg, argv):
    given, argv = split_run_flag(argv)
    target = argv[0] if argv else "previous"
    if target != "previous" and not C.RELEASE_ID_RE.match(target):
        return fail(C.EXIT_POLICY, "usage: rollback [<release_id>|previous] [unsafe-ack=<phrase>]")
    cmd = release_cmd("rollback", "--to", target)
    for flag in argv[1:]:
        if flag.startswith("unsafe-ack=") and PHRASE_RE.match(flag.split("=", 1)[1]):
            cmd += ["--unsafe-ack", flag.split("=", 1)[1]]
        else:
            return fail(C.EXIT_POLICY, "unknown flag: %s" % flag[:40])
    return start_or_resume(cfg, given, cmd)


def v_follow(cfg, argv):
    if len(argv) != 2 or not argv[1].isdigit():
        return fail(C.EXIT_POLICY, "usage: follow <run_id> <offset>")
    rd = run_dir(cfg, argv[0])
    offset = int(argv[1])
    logfile = rd / "log"
    data = b""
    if logfile.exists():
        with open(str(logfile), "rb") as fh:
            fh.seek(offset)
            data = fh.read(MAX_FOLLOW_BYTES)
    sys.stdout.write(C.redact(data.decode("utf-8", "replace")))
    sys.stdout.flush()
    new_offset = offset + len(data)
    exit_file = rd / "exit_code"
    if exit_file.exists() and len(data) < MAX_FOLLOW_BYTES:
        out("OFFSET %d" % new_offset)
        out("STATE done %s" % exit_file.read_text(encoding="utf-8").strip())
        return 0
    pid_file = rd / "pid"
    alive = False
    if pid_file.exists():
        try:
            alive = pid_alive(int(pid_file.read_text(encoding="utf-8").strip()))
        except ValueError:
            alive = False
    out("OFFSET %d" % new_offset)
    if alive or len(data) >= MAX_FOLLOW_BYTES or exit_file.exists():
        out("STATE running")
    else:
        time.sleep(1.5)                       # a supervisor that just finished may not have flushed exit_code yet
        if exit_file.exists():
            out("STATE done %s" % exit_file.read_text(encoding="utf-8").strip())
        else:
            out("STATE died")
    return 0


def v_result(cfg, argv):
    if len(argv) != 1:
        return fail(C.EXIT_POLICY, "usage: result <run_id>")
    p = run_dir(cfg, argv[0]) / "result.json"
    out(C.redact(p.read_text(encoding="utf-8")) if p.exists() else "{}")
    return 0


def v_status(cfg, argv):
    if argv:
        return fail(C.EXIT_POLICY, "status takes no arguments")
    proc = subprocess.run(release_cmd("status"))
    return proc.returncode


def v_version(cfg, argv):
    if argv:
        return fail(C.EXIT_POLICY, "version takes no arguments")
    out(json.dumps({"tooling": tool_version(), "python": "%d.%d.%d" % sys.version_info[:3]}))
    return 0


VERBS = {"version": v_version, "status": v_status, "stage": v_stage, "activate": v_activate, "rollback": v_rollback,
         "follow": v_follow, "result": v_result}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--supervise":
        return supervise(argv[1], argv[2:])
    original = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    if not original:
        return fail(C.EXIT_POLICY, "interactive logins are not allowed; use a deploy verb")
    try:
        words = shlex.split(original)
    except ValueError:
        return fail(C.EXIT_POLICY, "unparseable command")
    if not words or words[0] not in VERBS:
        return fail(C.EXIT_POLICY, "unknown verb %r (allowed: %s)" % (words[0][:30] if words else "", ", ".join(sorted(VERBS))))
    try:
        cfg = C.Config()
        return VERBS[words[0]](cfg, words[1:])
    except C.ConfigError as exc:
        return fail(C.EXIT_POLICY, "configuration error: %s" % exc)
    except ValueError as exc:
        return fail(C.EXIT_POLICY, str(exc))


if __name__ == "__main__":
    sys.exit(main())
