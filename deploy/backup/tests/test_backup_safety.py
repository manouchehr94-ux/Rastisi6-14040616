"""Failure reporting and least-privilege state contract, no real service needed."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rastisi_backup as B


class BackupSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf = MagicMock()
        self.conf.state = Path(self.tmp.name)
        self.conf.get.side_effect = lambda key, default=None: default

    def test_timeouts_and_missing_executables_are_reportable_backup_errors(self):
        tools = B.Tools.__new__(B.Tools)
        tools.base_env = lambda: {}
        tools.secrets = set()
        for exc in (subprocess.TimeoutExpired('pg_dump', 1), FileNotFoundError('missing')):
            with self.subTest(exc=exc), patch.object(B.subprocess, 'run', side_effect=exc), self.assertRaises(B.BackupError):
                tools.run(['pg_dump'])

    def test_concurrent_backup_does_not_invalidate_active_backup(self):
        with patch.object(B, 'Conf', return_value=self.conf), patch.object(B, 'cmd_run', side_effect=B.BackupBusy()), patch.object(sys, 'argv', ['backup', 'run']), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(B.main(), 75)
        self.assertFalse((self.conf.state/'BACKUP_FAILED').exists())

    def test_backup_deploy_lock_is_shared_and_blocks_schema_transitions(self):
        import fcntl
        path = self.conf.state/'deploy.lock'
        path.touch()
        self.conf.get.side_effect = lambda key, default=None: str(path) if key == 'deploy_lock_file' else default
        locks = B.lock_file(self.conf)
        try:
            with path.open('r') as other:
                with self.assertRaises(BlockingIOError): fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            locks.close()
        with path.open('r') as other:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(B.BackupBusy): B.lock_file(self.conf)

    def test_failed_alert_delivery_leaves_a_visible_marker(self):
        self.conf.get.side_effect = lambda key, default=None: {'alert_cmd': 'mail -s', 'alert_to': 'operator@local.test'}.get(key, default)
        with patch.object(B.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1)), contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(B.alert(self.conf, 'failed', 'redacted body'))
        self.assertTrue((self.conf.state/'ALERT_DELIVERY_FAILED').exists())

    def test_backup_state_is_readable_by_deploy_without_secret_group_membership(self):
        B.write_state(self.conf, 'last_backup.json', {'verified':True, 'db_sha256':'abc'})
        self.assertEqual((self.conf.state/'last_backup.json').stat().st_mode & 0o777, 0o644)

    def test_weekly_verification_reads_all_data(self):
        (self.conf.state/'last_backup.json').write_text(json.dumps({'db_sha256':'abc'}))
        tools = MagicMock()
        with patch.object(B, 'Tools', return_value=tools), patch.object(B, 'verify_stored_dump'):
            self.assertEqual(B.cmd_verify(self.conf, types.SimpleNamespace()), 0)
        tools.restic_run.assert_called_once_with('check', '--read-data-subset', '100%', timeout=21600)

    def test_corrupt_backup_invalidates_deployment_readiness(self):
        (self.conf.state/'last_backup.json').write_text(json.dumps({'db_sha256':'abc', 'verified':True}))
        tools = MagicMock()
        tools.secrets = set()
        with patch.object(B, 'Tools', return_value=tools), patch.object(B, 'verify_stored_dump', side_effect=B.BackupError('corrupt')), patch.object(B, 'alert'):
            self.assertEqual(B.cmd_verify(self.conf, types.SimpleNamespace()), 1)
        self.assertFalse(json.loads((self.conf.state/'last_backup.json').read_text())['verified'])
        self.assertTrue((self.conf.state/'BACKUP_FAILED').exists())
