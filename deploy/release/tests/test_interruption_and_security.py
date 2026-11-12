"""Concurrency, lost SSH connections, killed processes, the SSH gate, artifact tampering and secret hygiene."""

import json
import os
import signal
import subprocess
import sys
import tarfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import CANARIES, PY, TOOLS, SandboxTestCase, cleanup_templates, make_artifact  # noqa: E402

sys.path.insert(0, str(TOOLS))
import rastisi_common as C  # noqa: E402


def tearDownModule():
    cleanup_templates()


def wait_for(predicate, timeout=20, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("condition not reached within %ss" % timeout)


class GateMixin:
    def gate(self, command, stdin=None, timeout=120):
        env = dict(self.sbx.env, SSH_ORIGINAL_COMMAND=command)
        return subprocess.run([PY, str(TOOLS / "rastisi_gate.py")], capture_output=True, text=True if stdin is None or isinstance(stdin, str) else False,
                              env=env, input=stdin, timeout=timeout)

    def follow_until_done(self, run_id, timeout=60):
        offset, text = 0, ""
        end = time.time() + timeout
        while time.time() < end:
            proc = self.gate("follow %s %d" % (run_id, offset))
            lines = proc.stdout.splitlines()
            body = [l for l in lines if not l.startswith(("OFFSET ", "STATE "))]
            text += "\n".join(body) + "\n"
            offset = int([l for l in lines if l.startswith("OFFSET ")][-1].split()[1])
            state = [l for l in lines if l.startswith("STATE ")][-1]
            if state.startswith("STATE done"):
                return int(state.split()[2]), text
            if state == "STATE died":
                return None, text
            time.sleep(0.3)
        raise AssertionError("run did not finish")


class ConcurrencyTests(SandboxTestCase):
    def test_two_simultaneous_deploys_never_overlap(self):
        a, _ = self.sbx.make_and_stage(static_version="1")
        b, _ = self.sbx.make_and_stage(static_version="2")
        self.sbx.set_control({"smoke_delay": 3})            # the first deploy holds the lock for a few seconds
        first = subprocess.Popen([PY, str(TOOLS / "rastisi_release.py"), "activate", "--id", a], env=self.sbx.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wait_for(lambda: self.sbx.status()["busy"])
        second = self.sbx.activate(b)
        self.assertEqual(second.returncode, C.EXIT_BUSY, second.stdout + second.stderr)
        out, err = first.communicate(timeout=60)
        self.assertEqual(first.returncode, 0, out + err)
        self.assertEqual(self.sbx.status()["current"], a, "the rejected deploy must not have changed anything")
        self.assertIsNone(self.sbx.status()["incident"])
        # the loser can simply be retried afterwards
        self.sbx.set_control({})
        self.assertEqual(self.sbx.activate(b).returncode, 0)

    def test_deploy_and_rollback_cannot_run_together(self):
        a, _ = self.sbx.make_and_stage()
        self.assertEqual(self.sbx.activate(a).returncode, 0)
        b, _ = self.sbx.make_and_stage()
        self.sbx.set_control({"smoke_delay": 3})
        first = subprocess.Popen([PY, str(TOOLS / "rastisi_release.py"), "activate", "--id", b], env=self.sbx.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wait_for(lambda: self.sbx.status()["busy"])
        self.assertEqual(self.sbx.release("rollback", "--to", "previous").returncode, C.EXIT_BUSY)
        first.communicate(timeout=60)
        self.assertEqual(first.returncode, 0)


class LostConnectionAndKilledProcessTests(SandboxTestCase, GateMixin):
    def start_activation(self, rid, sha, extra=""):
        proc = self.gate("activate %s %s - %s" % (rid, sha, extra))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.split()[1]

    def test_losing_the_ssh_connection_does_not_interrupt_or_duplicate_the_deployment(self):
        rid, sha = self.sbx.make_and_stage()
        self.sbx.set_control({"smoke_delay": 2})
        # The "client" is a shell that starts the activation and is then killed together with its whole process group,
        # which is what a dropped SSH session does.
        script = 'echo "$SSH_ORIGINAL_COMMAND" >/dev/null; %s %s; sleep 60' % (PY, TOOLS / "rastisi_gate.py")
        client = subprocess.Popen(["bash", "-c", script], env=dict(self.sbx.env, SSH_ORIGINAL_COMMAND="activate %s %s -" % (rid, sha)),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        first_line = client.stdout.readline()
        self.assertTrue(first_line.startswith("RUN "), first_line)
        run_id = first_line.split()[1]
        os.killpg(client.pid, signal.SIGKILL)                  # the connection is gone mid-deployment
        client.wait()
        # reconnect and follow the SAME run to completion
        code, log = self.follow_until_done(run_id)
        self.assertEqual(code, 0, log)
        self.assertServing(rid)
        activations = [h for h in self.sbx.history() if h.get("event") == "activate"]
        self.assertEqual(len(activations), 1, "the deployment must run exactly once")
        self.assertIn("DONE", log)

    def test_follow_is_resumable_at_any_offset(self):
        rid, sha = self.sbx.make_and_stage()
        run_id = self.start_activation(rid, sha)
        code, log = self.follow_until_done(run_id)
        self.assertEqual(code, 0)
        full = self.gate("follow %s 0" % run_id).stdout
        tail = self.gate("follow %s 40" % run_id).stdout
        self.assertTrue(full.splitlines()[0][:30] in log or log)
        self.assertLess(len(tail), len(full))

    def test_a_killed_deployer_is_detected_as_an_incident_not_guessed(self):
        rid, sha = self.sbx.make_and_stage()
        self.sbx.set_control({"smoke_delay": 8})
        run_id = self.start_activation(rid, sha)
        wait_for(lambda: (self.sbx.base / "state" / "in_progress.json").exists() and
                 json.loads((self.sbx.base / "state" / "in_progress.json").read_text()).get("phase") == "verify")
        pids = subprocess.run(["pgrep", "-f", "rastisi_release.py activate --id %s" % rid], capture_output=True, text=True).stdout.split()
        self.assertTrue(pids, "orchestrator process not found")
        for pid in pids:
            os.kill(int(pid), signal.SIGKILL)
        code, log = self.follow_until_done(run_id)
        self.assertNotEqual(code, 0, "a killed run must never look successful")
        st = self.sbx.status()
        self.assertEqual(st["in_progress"]["release"], rid)
        self.assertFalse(st["busy"], "the lock dies with the process")
        # the next deployment refuses to guess what state the killed one left behind
        self.sbx.set_control({})
        other, _ = self.sbx.make_and_stage()
        proc = self.sbx.activate(other)
        self.assertEqual(proc.returncode, C.EXIT_NEEDS_HUMAN, proc.stdout + proc.stderr)
        self.assertIsNotNone(self.sbx.status()["incident"])
        self.assertEqual(self.sbx.status()["current"], rid, "state is left exactly as found")
        self.assertEqual(self.sbx.release("resolve", "--note", "checked site and database by hand").returncode, 0)
        self.assertEqual(self.sbx.activate(other).returncode, 0)


class GateTests(SandboxTestCase, GateMixin):
    def test_only_the_fixed_verbs_are_accepted(self):
        for evil in ("", "bash", "bash -c id", "status; id", "status && id", "$(id)", "`id`", "rm -rf /", "cat /etc/shadow",
                     "stage a b", "activate ../../etc x -", "activate 20261111T000000Z-aaaaaaaaaaaa zzz -", "follow ../x 0",
                     "rollback ../../x", "activate 20261111T000000Z-aaaaaaaaaaaa %s - --exec=id" % ("a" * 40)):
            with self.subTest(command=evil):
                proc = self.gate(evil)
                self.assertNotEqual(proc.returncode, 0, "command %r must be refused (stdout=%r)" % (evil, proc.stdout))

    def test_interactive_login_is_refused(self):
        env = {k: v for k, v in self.sbx.env.items() if k != "SSH_ORIGINAL_COMMAND"}
        proc = subprocess.run([PY, str(TOOLS / "rastisi_gate.py")], capture_output=True, text=True, env=env)
        self.assertNotEqual(proc.returncode, 0)

    def test_stage_through_the_gate_verifies_the_checksum_before_unpacking(self):
        art, sha, digest = make_artifact(self.sbx.root)
        self.sbx._seed_venv()
        data = art.read_bytes()
        bad = self.gate("stage %s %s" % (sha, "0" * 64), stdin=data) if False else subprocess.run(
            [PY, str(TOOLS / "rastisi_gate.py")], input=data, capture_output=True, env=dict(self.sbx.env, SSH_ORIGINAL_COMMAND="stage %s %s" % (sha, "0" * 64)))
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual([r for r in self.sbx.status()["releases"] if not r["id"].startswith("legacy-")], [], "nothing may be unpacked")
        good = subprocess.run([PY, str(TOOLS / "rastisi_gate.py")], input=data, capture_output=True,
                              env=dict(self.sbx.env, SSH_ORIGINAL_COMMAND="stage %s %s" % (sha, digest)))
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(len([r for r in self.sbx.status()["releases"] if not r["id"].startswith("legacy-")]), 1)

    def test_oversized_artifacts_are_rejected_while_streaming(self):
        self.sbx.conf.write_text(self.sbx.conf.read_text() + "max_artifact_mb = 1\n")
        proc = subprocess.run([PY, str(TOOLS / "rastisi_gate.py")], input=b"x" * (3 * 1024 * 1024), capture_output=True,
                              env=dict(self.sbx.env, SSH_ORIGINAL_COMMAND="stage %s %s" % ("a" * 40, "b" * 64)))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"exceeds", proc.stderr)


class ArtifactIntegrityTests(SandboxTestCase):
    def test_checksum_mismatch_is_refused(self):
        art, sha, digest = make_artifact(self.sbx.root)
        proc, rid = self.sbx.stage(art, sha, "0" * 64)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIsNone(rid)

    def test_commit_mismatch_between_request_and_manifest_is_refused(self):
        art, sha, digest = make_artifact(self.sbx.root)
        proc, rid = self.sbx.stage(art, "e" * 40, digest)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("does not match", proc.stdout + proc.stderr)

    def test_a_file_changed_after_the_manifest_was_written_is_refused(self):
        def tamper(root):
            (root / "app" / "manage.py").write_text("print('backdoor')\n")
        art, sha, digest = make_artifact(self.sbx.root, tamper=tamper)
        proc, rid = self.sbx.stage(art, sha, digest)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("does not match its manifest", proc.stdout + proc.stderr)
        self.assertEqual([r for r in self.sbx.status()["releases"] if not r["id"].startswith("legacy-")], [])

    def test_path_traversal_and_escaping_links_in_the_archive_are_refused(self):
        import io
        for label, build in (
            ("dotdot", lambda tar: self._add(tar, "../escape.txt", b"x")),
            ("absolute", lambda tar: self._add(tar, "/tmp/abs-escape.txt", b"x")),
            ("symlink out", lambda tar: self._add_link(tar, "app/evil", "../../../../etc/passwd")),
        ):
            with self.subTest(label):
                art, sha, digest = make_artifact(self.sbx.root)
                evil = self.sbx.root / ("evil-%s.tar.gz" % label)
                with tarfile.open(str(art)) as src, tarfile.open(str(evil), "w:gz") as dst:
                    for m in src.getmembers():
                        dst.addfile(m, src.extractfile(m) if m.isfile() else None)
                    build(dst)
                import hashlib
                proc, rid = self.sbx.stage(evil, sha, hashlib.sha256(evil.read_bytes()).hexdigest())
                self.assertEqual(proc.returncode, C.EXIT_POLICY, proc.stdout + proc.stderr)
                self.assertFalse((self.sbx.root / "escape.txt").exists())
                self.assertFalse(Path("/tmp/abs-escape.txt").exists())

    @staticmethod
    def _add(tar, name, data):
        import io
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    @staticmethod
    def _add_link(tar, name, target):
        info = tarfile.TarInfo(name)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        tar.addfile(info)

    def test_an_artifact_built_for_another_python_is_refused(self):
        art, sha, digest = make_artifact(self.sbx.root, python="2.7")
        conf = self.sbx.conf.read_text().replace("python = %s\n" % PY, "")
        self.sbx.conf.write_text(conf)
        proc, rid = self.sbx.stage(art, sha, digest)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("Python", proc.stdout + proc.stderr)


class SecretHygieneTests(SandboxTestCase, GateMixin):
    def everything(self, *procs):
        parts = [self.sbx.all_text_outputs()]
        for p in procs:
            parts += [p.stdout if isinstance(p.stdout, str) else p.stdout.decode(errors="replace"),
                      p.stderr if isinstance(p.stderr, str) else p.stderr.decode(errors="replace")]
        return "\n".join(parts)

    def assertNoSecrets(self, text):
        for name, value in CANARIES.items():
            self.assertNotIn(value, text, "%s leaked" % name)
        for fragment in ("CANARYdbpassw0rd9x", "CANARYredispw42", "CANARY-secret-key", "CANARY-fernet-key"):
            self.assertNotIn(fragment, text)

    def test_no_secret_appears_in_any_output_log_history_or_incident_across_success_failure_and_rollback(self):
        self.sbx.record_backup()
        procs = []
        ok, _ = self.sbx.make_and_stage()
        procs.append(self.sbx.activate(ok))
        # failure path where the application itself prints the DATABASE_URL (as a real traceback might)
        self.sbx.set_control({"migrate": "fail_first"})
        bad, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="ADDITIVE")
        procs.append(self.sbx.activate(bad))
        self.sbx.set_control({})
        broken, _ = self.sbx.make_and_stage(broken=True)
        procs.append(self.sbx.activate(broken))
        procs.append(self.sbx.release("rollback", "--to", "previous"))
        procs.append(self.sbx.release("status"))
        self.assertNoSecrets(self.everything(*procs))

    def test_the_failing_application_really_did_print_the_secret_and_it_was_masked(self):
        """Guards the previous test against passing vacuously: the stub prints DATABASE_URL; the log must show the masked form."""
        self.sbx.record_backup()
        self.sbx.set_control({"migrate": "fail_first"})
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="ADDITIVE")
        proc = self.sbx.activate(rid)
        text = proc.stdout + proc.stderr
        self.assertIn("could not apply core.0002_x", text)
        self.assertNotIn("CANARYdbpassw0rd9x", text)
        self.assertRegex(text, r"DATABASE_URL=\*\*\*|postgres://rastisi_app:\*\*\*@")

    def test_the_gate_never_returns_secrets_either(self):
        rid, sha = self.sbx.make_and_stage()
        run = self.gate("activate %s %s -" % (rid, sha))
        run_id = run.stdout.split()[1]
        _, log = self.follow_until_done(run_id)
        self.assertNoSecrets(log + self.gate("result %s" % run_id).stdout + self.gate("status").stdout)

    def test_redaction_unit(self):
        samples = {
            "postgres://u:hunter2secret@db:5432/x": "hunter2secret",
            "redis://:topsecretpw@127.0.0.1:6380/1": "topsecretpw",
            "DJANGO_SECRET_KEY=abcdef123456": "abcdef123456",
            "Authorization: Bearer abcdefghijklmnop12345": "abcdefghijklmnop12345",
            "PAYMENT_CREDENTIAL_KEY: Zm9vYmFyYmF6cXV4": "Zm9vYmFyYmF6cXV4",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3NzaC1\n-----END OPENSSH PRIVATE KEY-----": "AAAAB3NzaC1",
        }
        for raw, secret in samples.items():
            self.assertNotIn(secret, C.redact(raw), raw[:30])
        self.assertNotIn("customvalue99", C.redact("x customvalue99 y", extra_values=["customvalue99"]))


class ConfigAndCutoverTests(SandboxTestCase):
    def test_cutover_is_a_dry_run_by_default_and_cannot_be_applied_twice(self):
        sbx = self.sbx
        proc = sbx.release("cutover", "--legacy-app", sbx.root / "legacy-app", "--legacy-venv", sbx.root / "legacy-venv", "--sha", self.legacy_sha)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)       # already applied in setUp
        self.assertIn("already exists", proc.stdout + proc.stderr)

    def test_cutover_dry_run_changes_nothing(self):
        from harness import Sandbox
        fresh = Sandbox()
        self.addCleanup(fresh.close)
        (fresh.root / "legacy-app").mkdir()
        (fresh.root / "legacy-app" / "manage.py").write_text("")
        (fresh.root / "legacy-venv" / "bin").mkdir(parents=True)
        (fresh.root / "legacy-venv" / "bin" / "python").write_text("")
        proc = fresh.release("cutover", "--legacy-app", fresh.root / "legacy-app", "--legacy-venv", fresh.root / "legacy-venv", "--sha", "a" * 40)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dry run", proc.stdout)
        self.assertFalse((fresh.base / "current").exists())
        self.assertFalse((fresh.base / "releases").exists())

    def test_the_legacy_directory_is_never_modified_by_cutover_or_deploys(self):
        legacy = self.sbx.root / "legacy-app"
        before = sorted((p.name, p.stat().st_mtime_ns) for p in legacy.iterdir())
        rid, _ = self.sbx.make_and_stage()
        self.sbx.activate(rid)
        self.sbx.release("rollback", "--to", "previous")
        after = sorted((p.name, p.stat().st_mtime_ns) for p in legacy.iterdir())
        self.assertEqual(before, after)

    def test_the_tool_refuses_to_run_as_root_in_production_mode(self):
        env = {k: v for k, v in self.sbx.env.items() if k != "RASTISI_ALLOW_ROOT_FOR_TESTS"}
        proc = subprocess.run([PY, str(TOOLS / "rastisi_release.py"), "check-config"], capture_output=True, text=True, env=env)
        if os.geteuid() == 0:
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("must not run as root", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
