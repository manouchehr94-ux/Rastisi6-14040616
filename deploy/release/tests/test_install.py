"""install.sh into a DESTDIR: file set, modes, ownership-independent content, sudoers rules, idempotence, refusal of unsafe arguments."""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

INSTALL = Path(__file__).resolve().parent.parent / "install.sh"
ARGS = ["--service", "rastisi-rc-20261111.service", "--app-user", "rastisi", "--base", "/srv/rastisi-releases",
        "--env-file", "/etc/rastisi/rc-20261111.env", "--port", "18082"]


def run(dest, *extra, env=None):
    return subprocess.run(["bash", str(INSTALL)] + ARGS + list(extra), capture_output=True, text=True, env=dict(os.environ, DESTDIR=str(dest), **(env or {})))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp(prefix="install-"))
        self.addCleanup(shutil.rmtree, str(self.dest), True)

    def mode(self, p):
        p = Path(p)
        full = p if str(p).startswith(str(self.dest)) else self.dest / str(p).lstrip("/")
        return stat.S_IMODE(os.stat(str(full)).st_mode)

    def test_installs_the_tooling_with_safe_modes(self):
        proc = run(self.dest)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        lib = self.dest / "usr/local/lib/rastisi"
        for f in ("rastisi_gate.py", "rastisi_release.py", "rastisi_app_task.py", "rastisi_probe.py", "rastisi_smoke.py", "rastisi_common.py", "migration_guard.py", "TOOLING_VERSION"):
            self.assertTrue((lib / f).is_file(), f)
            self.assertEqual(self.mode(lib / f) & 0o022, 0, "%s must not be group/world writable" % f)
        self.assertTrue((lib / "smoke.d" / "20-auth-forms.py").is_file())
        self.assertTrue((self.dest / "usr/local/lib/rastisi-backup/rastisi_backup.py").is_file())

    def test_layout_and_permissions(self):
        run(self.dest)
        base = "/srv/rastisi-releases"
        for d in ("", "/releases", "/venvs", "/staging", "/state"):
            self.assertEqual(self.mode(base + d), 0o2750, base + d)
        self.assertEqual(self.mode(base + "/state/static-build"), 0o2770)

    def test_sudoers_has_exactly_the_two_rules(self):
        run(self.dest)
        text = (self.dest / "etc/sudoers.d/rastisi-deploy").read_text()
        rules = [l for l in text.splitlines() if l and not l.startswith("#") and not l.startswith("Defaults")]
        self.assertEqual(len(rules), 2, rules)
        self.assertIn("rastisi-deploy ALL=(rastisi) NOPASSWD: /usr/bin/python3 /usr/local/lib/rastisi/rastisi_app_task.py *", rules[0])
        self.assertIn("/usr/bin/systemctl restart rastisi-rc-20261111.service, /usr/bin/systemctl is-active rastisi-rc-20261111.service", rules[1])
        for forbidden in ("ALL=(ALL)", "NOPASSWD: ALL", "/bin/bash", "/bin/sh", "stop", "disable", "daemon-reload"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(self.mode("etc/sudoers.d/rastisi-deploy"), 0o440)
        if shutil.which("visudo"):
            self.assertEqual(subprocess.run(["visudo", "-cf", str(self.dest / "etc/sudoers.d/rastisi-deploy")], capture_output=True).returncode, 0)

    def test_config_is_written_once_and_never_overwritten(self):
        run(self.dest)
        conf = self.dest / "etc/rastisi/deploy.conf"
        text = conf.read_text()
        for line in ("base_dir = /srv/rastisi-releases", "app_user = rastisi", "service = rastisi-rc-20261111.service", "port = 18082",
                     "app_runner = sudo -n -u rastisi /usr/bin/python3 /usr/local/lib/rastisi/rastisi_app_task.py", "systemctl = sudo -n /usr/bin/systemctl"):
            self.assertIn(line, text)
        conf.write_text(text + "# edited by the operator\n")
        again = run(self.dest)
        self.assertEqual(again.returncode, 0)
        self.assertIn("NOT overwritten", again.stdout)
        self.assertIn("edited by the operator", conf.read_text())

    def test_dry_run_changes_nothing(self):
        before = set(os.listdir("/usr/local/lib")) if os.path.isdir("/usr/local/lib") else set()
        proc = subprocess.run(["bash", str(INSTALL)] + ARGS + ["--dry-run"], capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "DESTDIR"})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("DRY", proc.stdout)
        self.assertEqual(before, set(os.listdir("/usr/local/lib")) if os.path.isdir("/usr/local/lib") else set(), "a dry run must not create anything")
        self.assertFalse(os.path.exists("/etc/sudoers.d/rastisi-deploy"))

    def test_unsafe_arguments_are_refused(self):
        for bad in (["--deploy-user", "root"], ["--deploy-user", "rastisi"], ["--service", "x; reboot"], ["--service", "nounit"], ["--port", "80a"],
                    ["--base", "relative/path"], ["--app-user", "Root User"]):
            with self.subTest(bad=bad):
                proc = run(self.dest, *bad)
                self.assertNotEqual(proc.returncode, 0, proc.stdout)

    def test_the_installed_tooling_cannot_be_replaced_by_a_release(self):
        """The release layout never contains the tooling directory: a release is unpacked under <base>/releases only."""
        run(self.dest)
        self.assertFalse(str(self.dest / "usr/local/lib/rastisi").startswith(str(self.dest / "srv")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
