import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import make_dropin as M  # noqa: E402

UNIT = """# /etc/systemd/system/rastisi-rc-20261111.service
[Unit]
Description=RastiSi RC
After=network.target postgresql.service

[Service]
User=rastisi
Group=rastisi
WorkingDirectory=/srv/rastisi-rc-20261111
EnvironmentFile=/etc/rastisi/rc-20261111.env
ExecStart=/srv/rastisi-rc-20261111/venv/bin/gunicorn shop_core.wsgi:application --bind 127.0.0.1:18082 --workers 3 --timeout 60 --access-logfile /var/log/rastisi/access.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
OLD, BASE = "/srv/rastisi-rc-20261111", "/srv/rastisi-releases"


class DropinTests(unittest.TestCase):
    def test_only_the_paths_change_every_flag_is_kept(self):
        dropin, d, before, after = M.build_dropin(UNIT, BASE, OLD)
        self.assertIn("ExecStart=/srv/rastisi-releases/current/venv/bin/gunicorn shop_core.wsgi:application --bind 127.0.0.1:18082 --workers 3 --timeout 60 "
                      "--access-logfile /var/log/rastisi/access.log", dropin)
        self.assertIn("WorkingDirectory=/srv/rastisi-releases/current/app", dropin)
        self.assertEqual(dropin.count("ExecStart="), 2, "the empty ExecStart= resets the original, then the new one is set")
        self.assertEqual(dropin.count("WorkingDirectory="), 2)

    def test_it_refuses_to_guess(self):
        for bad in (UNIT.replace("/venv/bin/gunicorn", "/venv/bin/uvicorn"),
                    UNIT.replace("ExecStart=/srv/rastisi-rc-20261111/venv", "ExecStart=/opt/other/venv"),
                    UNIT.replace("--timeout 60", "--config /srv/rastisi-rc-20261111/gunicorn.conf.py"),
                    UNIT.replace("WorkingDirectory=/srv/rastisi-rc-20261111", "WorkingDirectory=/srv/elsewhere"),
                    "[Service]\nUser=x\n"):
            with self.subTest(bad=bad[-80:]), self.assertRaises(SystemExit):
                M.build_dropin(bad, BASE, OLD)

    def test_cli_prints_the_dropin_and_changes_nothing(self):
        import tempfile
        f = Path(tempfile.mkdtemp()) / "unit.txt"
        f.write_text(UNIT)
        proc = subprocess.run([sys.executable, str(Path(M.__file__)), "--unit-file", str(f), "--base", BASE, "--old-app", OLD], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[Service]", proc.stdout)
        self.assertIn("BEFORE", proc.stderr)
        self.assertIn("User=rastisi", proc.stderr)


if __name__ == "__main__":
    unittest.main()
