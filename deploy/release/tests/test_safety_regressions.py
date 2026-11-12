"""Independent review regressions. These fail against cd7b668 (before remediation)."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import migration_guard as G
import rastisi_release as R
import rastisi_app_task as A


class ReviewRegressions(unittest.TestCase):
    def test_c1_alias_cannot_hide_a_drop(self):
        source = "from django.db import migrations\nfrom django.db.migrations import RunSQL as SQL\nclass Migration(migrations.Migration):\n operations = [SQL('DROP TABLE orders_order CASCADE')]\n"
        self.assertEqual(G.worst([f['level'] for f in G.analyze_source(source)]), 'DESTRUCTIVE')

    def test_c1_custom_operation_and_dynamic_operations_require_review(self):
        for operations in ('[CustomOperation()]', 'make_operations()', '[*other_operations]'):
            with self.subTest(operations=operations):
                source = 'from django.db import migrations\nclass Migration(migrations.Migration):\n operations = ' + operations
                self.assertNotIn(G.worst([f['level'] for f in G.analyze_source(source)]), ('NONE', 'ADDITIVE'))

    def test_c1_non_atomic_requires_review(self):
        source = 'from django.db import migrations\nclass Migration(migrations.Migration):\n atomic = False\n operations = [migrations.CreateModel(name="X", fields=[])]'
        self.assertNotIn(G.worst([f['level'] for f in G.analyze_source(source)]), ('NONE', 'ADDITIVE'))

    def test_custom_field_and_null_database_default_are_not_proven_additive(self):
        for field in ('CustomField(null=True)', 'models.IntegerField(db_default=None)'):
            source = 'from django.db import migrations, models\nclass Migration(migrations.Migration):\n operations=[migrations.AddField(model_name="x", name="y", field=%s)]' % field
            self.assertNotIn(G.worst([f['level'] for f in G.analyze_source(source)]), ('NONE', 'ADDITIVE'))

    def test_c2_rollback_rejects_interrupted_deploy_even_with_ack(self):
        for ack in ('', R.UNSAFE_ROLLBACK_PHRASE):
            state = MagicMock()
            state.incident.return_value = None
            state.active.return_value = {'current': 'B', 'previous': 'A', 'rollback_safe_to_previous': True}
            state.in_progress_file.exists.return_value = True
            runner = MagicMock()
            runner.finish.side_effect = lambda code, *a, **kw: code
            args = types.SimpleNamespace(run_id='20261112T000000Z-12345678', to='previous', ignore_incident=False, unsafe_ack=ack)
            with patch.object(R, 'State', return_value=state), patch.object(R, 'Lock') as lock, patch.object(R, 'Runner', return_value=runner), patch.object(R, 'current_release_id', return_value='C'), patch.object(R, 'read_release', return_value={'sha': 'a'*40}), patch.object(R, 'restore_link', return_value=True) as restore, patch.object(R, 'verify_release', return_value=(True, {})), contextlib.redirect_stdout(io.StringIO()):
                lock.return_value.acquire.return_value = True
                code = R.cmd_rollback(MagicMock(), args)
            self.assertEqual(code, R.C.EXIT_NEEDS_HUMAN)
            restore.assert_not_called()

    def test_c3_backup_imports_from_installed_layout(self):
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            import os
            result = subprocess.run(['bash', str(repo/'deploy/release/install.sh'), '--service', 'test.service', '--app-user', 'rastisi', '--base', '/srv/rastisi', '--env-file', '/etc/rastisi/test.env', '--port', '18082'], env=dict(os.environ, DESTDIR=tmp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, '-I', str(Path(tmp)/'usr/local/lib/rastisi-backup/rastisi_backup.py'), '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_selected_python_is_checked_even_when_configured(self):
        from harness import Sandbox, make_artifact
        with contextlib.ExitStack() as stack:
            sbx = Sandbox()
            stack.callback(sbx.close)
            art, sha, digest = make_artifact(sbx.root, python='2.7')
            proc, _ = sbx.stage(art, sha, digest)
            self.assertEqual(proc.returncode, R.C.EXIT_POLICY, proc.stdout + proc.stderr)
            self.assertIn('Python mismatch', proc.stderr + proc.stdout)

    def test_architecture_mismatch_is_rejected(self):
        import runtime_check
        result = types.SimpleNamespace(stdout=json.dumps({'python':'3.12','system':'Linux','machine':'aarch64'}))
        with patch.object(runtime_check.subprocess, 'run', return_value=result), self.assertRaisesRegex(ValueError, 'architecture'):
            runtime_check.check_runtime('/python', {'python':'3.12'})

    def test_health_probe_error_json_and_bad_structure_fail_closed(self):
        for rc, data in ((1, {'ok': False, 'error': 'OperationalError'}), (0, {}), (0, {'ok': True, 'failures': 'invalid'}), (1, {'ok': True, 'failures': [], 'checks': {}})):
            ctx = MagicMock()
            ctx.release_paths.return_value = (Path('/fake/app'), Path('/fake/python'))
            ctx.run.return_value = (rc, json.dumps(data))
            with contextlib.redirect_stdout(io.StringIO()):
                code = A.v_healthcheck(ctx, types.SimpleNamespace(post=False, expect_release=''))
            self.assertNotEqual(code, 0, (rc, data))


from harness import SandboxTestCase


class MigrationFailureRegression(SandboxTestCase):
    def test_c4_failed_unrecorded_migration_preserves_incident_and_marker(self):
        self.sbx.record_backup()
        self.sbx.set_control({'migrate': 'non_atomic_fail'})
        rid, _ = self.sbx.make_and_stage(migrations=['core.0002_partial'], level='ADDITIVE')
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, R.C.EXIT_NEEDS_HUMAN, proc.stdout + proc.stderr)
        status = self.sbx.status()
        self.assertIsNotNone(status['incident'])
        self.assertIsNotNone(status['in_progress'])
        self.assertNotIn('core.0002_partial', self.sbx.db_state()['applied'])
        self.assertIn('partial-write', self.sbx.db_state()['rows'])
        self.assertNotEqual(self.sbx.activate(rid).returncode, 0)
        self.assertNotEqual(self.sbx.release('rollback').returncode, 0)


if __name__ == '__main__':
    unittest.main()
