"""The web release and job interpreter are pinned under one deployment lock."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WRAPPER = Path(__file__).resolve().parent.parent / 'run_current_job.sh'


class CurrentJobTests(unittest.TestCase):
    def test_job_uses_matching_code_and_venv_and_prevents_deployment_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'state').mkdir()
            lock = open(root/'state/deploy.lock', 'w+')
            self.addCleanup(lock.close)
            release = root/'releases/version1'
            (release/'app/deploy/cron').mkdir(parents=True)
            (release/'venv').mkdir()
            ready, finish = root/'ready', root/'finish'
            script = release/'app/deploy/cron/run_job.sh'
            script.write_text('echo "$RASTISI_APP_DIR|$RASTISI_VENV"\ntouch "$READY"\nwhile [ ! -e "$FINISH" ]; do sleep .05; done\n')
            (root/'current').symlink_to(release)
            env = dict(os.environ, RASTISI_RELEASE_BASE=tmp, READY=str(ready), FINISH=str(finish), RASTISI_APP_DIR='/stale', RASTISI_VENV='/stale')
            proc = subprocess.Popen(['bash', str(WRAPPER)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                import time
                for _ in range(100):
                    if ready.exists(): break
                    if proc.poll() is not None: self.fail(proc.communicate())
                    time.sleep(.05)
                self.assertTrue(ready.exists())
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finish.touch()
                out, err = proc.communicate(timeout=10)
                self.assertEqual(proc.returncode, 0, err)
                self.assertEqual(out.strip(), '%s/app|%s/venv' % (release,release))
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                blocked = subprocess.run(['bash',str(WRAPPER)],env=env,capture_output=True,text=True)
                self.assertEqual(blocked.returncode,75)
            finally:
                finish.touch()
                if proc.poll() is None: proc.communicate(timeout=10)
