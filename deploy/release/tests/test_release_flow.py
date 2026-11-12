"""Release flow: successful deploys, failed deploys, automatic and refused rollbacks, migrations policy, persistent data.

Run:  python -m unittest discover -s deploy/release/tests -t . -v      (or python deploy/release/tests/test_release_flow.py)
"""

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import CANARIES, SandboxTestCase, cleanup_templates, make_artifact  # noqa: E402

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import rastisi_common as C  # noqa: E402


def tearDownModule():
    cleanup_templates()


class SuccessfulDeployTests(SandboxTestCase):
    def test_deploy_switches_atomically_publishes_static_and_records_everything(self):
        before = self.sbx.data_fingerprint()
        rid, sha = self.sbx.make_and_stage(static_version="7")
        proc = self.sbx.activate(rid, "--expect-sha", sha, "--from-sha", self.legacy_sha)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertServing(rid)
        st = self.sbx.status()
        self.assertTrue(st["previous"].startswith("legacy-"))
        self.assertTrue(st["active"]["rollback_safe_to_previous"])
        self.assertEqual(st["active"]["migrations_applied"], [])
        self.assertIsNone(st["incident"])
        self.assertIsNone(st["in_progress"])
        self.assertEqual((self.sbx.static / "release-7.txt").read_text(), "v7\n")
        events = [h["event"] for h in self.sbx.history()]
        self.assertEqual(events[-2:], ["staged", "activate"])
        self.assertEqual(self.sbx.data_fingerprint(), before, "customer data/media must be untouched by a deployment")
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"], "no migration may run when none is pending")

    def test_release_directory_is_immutable_and_separate_from_data(self):
        rid, sha = self.sbx.make_and_stage()
        root = self.sbx.base / "releases" / rid
        self.assertTrue((root / "app" / "manage.py").exists())
        self.assertTrue((root / "venv").is_symlink())
        self.assertFalse(os.access(str(root / "app" / "manage.py"), os.W_OK) and os.geteuid() != 0, "code must be read-only")
        for forbidden in ("media", "db.sqlite3", ".env"):
            self.assertFalse((root / "app" / forbidden).exists())
        self.assertFalse((root / "wheelhouse").exists(), "the wheelhouse is only needed to build the venv")

    def test_deploying_the_active_release_again_only_verifies(self):
        rid, sha = self.sbx.make_and_stage()
        self.assertEqual(self.sbx.activate(rid).returncode, 0)
        restarts = self.sbx.restarts()
        again = self.sbx.activate(rid)
        self.assertEqual(again.returncode, 0)
        self.assertEqual(self.sbx.restarts(), restarts, "no restart for a no-op")

    def test_two_releases_in_a_row_keep_the_first_as_rollback_target(self):
        a, _ = self.sbx.make_and_stage()
        b, shb = self.sbx.make_and_stage(static_version="2")
        self.assertEqual(self.sbx.activate(a).returncode, 0)
        self.assertEqual(self.sbx.activate(b, "--expect-sha", shb).returncode, 0)
        st = self.sbx.status()
        self.assertEqual((st["current"], st["previous"]), (b, a))

    def test_wrong_approved_commit_is_refused_and_nothing_changes(self):
        rid, sha = self.sbx.make_and_stage()
        proc = self.sbx.activate(rid, "--expect-sha", "f" * 40)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertTrue(self.current().startswith("legacy-"))

    def test_a_stale_plan_is_refused(self):
        rid, sha = self.sbx.make_and_stage()
        proc = self.sbx.activate(rid, "--from-sha", "a" * 40)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("re-plan", proc.stdout + proc.stderr)
        self.assertTrue(self.current().startswith("legacy-"))

    def current(self):
        return self.sbx.status()["current"]


class FailedDeployTests(SandboxTestCase):
    def test_a_release_that_fails_verification_is_rolled_back_automatically(self):
        before = self.sbx.data_fingerprint()
        legacy_id = self.current()
        rid, sha = self.sbx.make_and_stage(broken=True)
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_FAILED_SAFE, proc.stdout + proc.stderr)
        self.assertServing(legacy_id)
        st = self.sbx.status()
        self.assertIsNone(st["incident"], "a clean automatic rollback is not an incident")
        self.assertIsNone(st["in_progress"])
        self.assertEqual({r["id"]: r["status"] for r in st["releases"]}[rid], "failed")
        self.assertEqual(self.sbx.data_fingerprint(), before)
        self.assertEqual(self.sbx.history()[-1]["result"], "rolled-back")

    def test_service_restart_failure_is_rolled_back(self):
        legacy_id = self.current()
        rid, _ = self.sbx.make_and_stage()
        self.sbx.set_flags(fail_restart=True)
        proc = self.sbx.activate(rid)
        # restart keeps failing even for the rollback target: the system must say so loudly instead of pretending
        self.assertEqual(proc.returncode, C.EXIT_NEEDS_HUMAN, proc.stdout + proc.stderr)
        self.assertIsNotNone(self.sbx.status()["incident"])

    def test_additive_migration_then_failed_verification_rolls_back_code_and_keeps_the_schema(self):
        legacy_id = self.current()
        self.sbx.record_backup()
        rid, _ = self.sbx.make_and_stage(broken=True, migrations=["core.0002_add_nullable"], level="ADDITIVE")
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_FAILED_SAFE, proc.stdout + proc.stderr)
        self.assertServing(legacy_id)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial", "core.0002_add_nullable"])
        self.assertIsNone(self.sbx.status()["incident"])

    def test_non_additive_migration_is_refused_before_any_online_change(self):
        self.sbx.record_backup()
        before = self.sbx.data_fingerprint()
        rid, _ = self.sbx.make_and_stage(broken=True, migrations=['core.0002_data_fix'], level='REVIEW')
        proc = self.sbx.activate(rid, '--allow-migrations')
        self.assertEqual(proc.returncode, C.EXIT_POLICY, proc.stdout + proc.stderr)
        self.assertIn('offline migration', proc.stdout)
        self.assertTrue(self.current().startswith('legacy-'))
        self.assertEqual(self.sbx.data_fingerprint(), before)
        self.assertIsNone(self.sbx.status()['in_progress'])

    def test_redis_down_before_the_switch_stops_the_deploy_without_touching_anything(self):
        legacy_id = self.current()
        rid, _ = self.sbx.make_and_stage()
        self.sbx.set_control({"redis_down": True})
        restarts = self.sbx.restarts()
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY, proc.stdout + proc.stderr)
        self.assertIn("redis", (proc.stdout + proc.stderr).lower())
        self.assertServing(legacy_id)
        self.assertEqual(self.sbx.restarts(), restarts)

    def test_a_release_that_cannot_reach_redis_after_the_switch_is_rolled_back(self):
        legacy_id = self.current()
        rid, _ = self.sbx.make_and_stage(extra_files={"REDIS_BREAKS": "1"})
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_FAILED_SAFE, proc.stdout + proc.stderr)
        self.assertIn("redis", (proc.stdout + proc.stderr).lower())
        self.assertServing(legacy_id)
        self.assertIsNone(self.sbx.status()["incident"])

    def test_database_down_blocks_the_deploy(self):
        rid, _ = self.sbx.make_and_stage()
        self.sbx.set_control({"database_down": True})
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertTrue(self.current().startswith("legacy-"))

    def test_manage_check_failure_blocks_the_deploy(self):
        rid, _ = self.sbx.make_and_stage()
        self.sbx.set_control({"check_fail": True})
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertTrue(self.current().startswith("legacy-"))

    def test_unsafe_environment_blocks_the_deploy(self):
        rid, _ = self.sbx.make_and_stage()
        env = self.sbx.env_file.read_text().replace("DJANGO_DEBUG=False", "DJANGO_DEBUG=True")
        self.sbx.env_file.write_text(env)
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("DJANGO_DEBUG", proc.stdout + proc.stderr)
        self.sbx.env_file.write_text(env.replace("DJANGO_DEBUG=True", "DJANGO_DEBUG=False") + "RASTISI_SMS_REFUND_ENABLED=true\n")
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("RASTISI_SMS_REFUND_ENABLED", proc.stdout + proc.stderr)


class MigrationPolicyTests(SandboxTestCase):
    def test_migration_failure_keeps_old_code_but_requires_database_investigation(self):
        legacy_id = self.current()
        self.sbx.record_backup()
        self.sbx.set_control({"migrate": "fail_first"})
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="ADDITIVE")
        restarts = self.sbx.restarts()
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_NEEDS_HUMAN, proc.stdout + proc.stderr)
        self.assertServing(legacy_id)
        self.assertEqual(self.sbx.restarts(), restarts, "the service must not be restarted when the migration failed")
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])
        self.assertIsNotNone(self.sbx.status()["incident"])
        self.assertIsNotNone(self.sbx.status()["in_progress"])

    def test_partial_failure_of_an_additive_batch_is_also_an_incident(self):
        self.sbx.record_backup()
        self.sbx.set_control({"migrate": "fail_after_first"})
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_a", "core.0003_b"], level="ADDITIVE")
        proc = self.sbx.activate(rid, "--allow-migrations")
        self.assertEqual(proc.returncode, C.EXIT_NEEDS_HUMAN, proc.stdout + proc.stderr)
        self.assertIsNotNone(self.sbx.status()["incident"])
        self.assertTrue(self.current().startswith("legacy-"))

    def test_additive_migrations_need_a_recent_verified_backup(self):
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="ADDITIVE")
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("backup", (proc.stdout + proc.stderr).lower())
        self.sbx.record_backup(minutes_ago=300)
        self.assertEqual(self.sbx.activate(rid).returncode, C.EXIT_POLICY, "an old backup is not enough")
        self.sbx.record_backup(verified=False)
        self.assertEqual(self.sbx.activate(rid).returncode, C.EXIT_POLICY, "an unverified backup is not enough")
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])
        self.sbx.record_backup(minutes_ago=5)
        self.assertEqual(self.sbx.activate(rid).returncode, 0)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial", "core.0002_x"])
        self.assertTrue(self.sbx.status()["active"]["rollback_safe_to_previous"])

    def test_review_level_needs_explicit_approval(self):
        self.sbx.record_backup()
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="REVIEW")
        self.assertEqual(self.sbx.activate(rid).returncode, C.EXIT_POLICY)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])
        proc = self.sbx.activate(rid, "--allow-migrations")
        self.assertEqual(proc.returncode, C.EXIT_POLICY, proc.stdout + proc.stderr)
        self.assertIn("offline migration", proc.stdout)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])

    def test_destructive_level_needs_the_exact_phrase(self):
        self.sbx.record_backup()
        rid, sha = self.sbx.make_and_stage(migrations=["core.0002_drop"], level="DESTRUCTIVE")
        self.assertEqual(self.sbx.activate(rid, "--allow-migrations").returncode, C.EXIT_POLICY)
        self.assertEqual(self.sbx.activate(rid, "--allow-migrations", "--destructive-ack", "yes").returncode, C.EXIT_POLICY)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])
        phrase = "I-ACCEPT-DESTRUCTIVE-MIGRATION-" + sha[:12]
        self.assertEqual(self.sbx.activate(rid, "--allow-migrations", "--destructive-ack", phrase).returncode, C.EXIT_POLICY)

    def test_migrations_the_report_did_not_announce_are_refused(self):
        """A database that is behind (a skipped release) must not be silently migrated by an unrelated deploy."""
        self.sbx.record_backup()
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_old", "core.0003_new"], level="ADDITIVE", new_migrations=["core.0003_new"])
        proc = self.sbx.activate(rid)
        self.assertEqual(proc.returncode, C.EXIT_POLICY)
        self.assertIn("core.0002_old", proc.stdout + proc.stderr)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])

    def test_dry_run_changes_nothing(self):
        self.sbx.record_backup()
        rid, _ = self.sbx.make_and_stage(migrations=["core.0002_x"], level="ADDITIVE")
        legacy = self.current()
        restarts = self.sbx.restarts()
        proc = self.sbx.activate(rid, "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.current(), legacy)
        self.assertEqual(self.sbx.restarts(), restarts)
        self.assertEqual(self.sbx.db_state()["applied"], ["core.0001_initial"])


class RollbackCommandTests(SandboxTestCase):
    def deploy(self, **kw):
        rid, sha = self.sbx.make_and_stage(**kw)
        proc = self.sbx.activate(rid, "--allow-migrations")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return rid

    def test_manual_rollback_to_previous_is_verified_and_preserves_data(self):
        legacy = self.current()
        before = self.sbx.data_fingerprint()
        rid = self.deploy()
        proc = self.sbx.release("rollback", "--to", "previous")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertServing(legacy)
        self.assertEqual(self.sbx.data_fingerprint(), before)
        # the data written while the new release was serving must survive a code rollback
        db = self.sbx.db_state()
        db["rows"].append("order-2001-created-on-new-release")
        self.sbx.db.write_text(json.dumps(db))
        again = self.sbx.release("rollback", "--to", rid, "--unsafe-ack", "I-UNDERSTAND-THE-DATABASE-MAY-NOT-MATCH-THE-OLD-CODE")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("order-2001-created-on-new-release", self.sbx.db_state()["rows"])

    def test_rollback_after_a_non_additive_migration_needs_the_unsafe_phrase(self):
        self.sbx.record_backup()
        self.deploy()
        # Model a manually completed offline schema change: compatibility must
        # be explicitly invalidated rather than inferred from a typed phrase.
        path = self.sbx.base / "state/active.json"
        state = json.loads(path.read_text())
        state.update(rollback_safe_to_previous=False, migrations_applied=["core.0002_data"])
        path.write_text(json.dumps(state))
        proc = self.sbx.release("rollback", "--to", "previous")
        self.assertEqual(proc.returncode, C.EXIT_POLICY, proc.stdout + proc.stderr)
        self.assertIn("not known to be database-compatible", proc.stdout + proc.stderr)
        ok = self.sbx.release("rollback", "--to", "previous", "--unsafe-ack", "I-UNDERSTAND-THE-DATABASE-MAY-NOT-MATCH-THE-OLD-CODE")
        self.assertEqual(ok.returncode, 0)

    def test_rollback_without_a_target_is_refused(self):
        proc = self.sbx.release("rollback", "--to", "previous")
        self.assertEqual(proc.returncode, C.EXIT_POLICY)

    def test_rollback_is_blocked_while_an_incident_is_open(self):
        self.deploy()
        (self.sbx.base / "state" / "INCIDENT").write_text('{"reason": "test"}\n')
        proc = self.sbx.release("rollback", "--to", "previous")
        self.assertEqual(proc.returncode, C.EXIT_NEEDS_HUMAN)
        self.assertEqual(self.sbx.release("resolve", "--note", "short").returncode, C.EXIT_POLICY)
        self.assertEqual(self.sbx.release("resolve", "--note", "verified database and site manually").returncode, 0)
        self.assertEqual(self.sbx.release("rollback", "--to", "previous").returncode, 0)


class PruneTests(SandboxTestCase):
    def test_old_releases_are_pruned_but_current_previous_and_legacy_are_kept(self):
        ids = []
        for i in range(6):
            rid, _ = self.sbx.make_and_stage(static_version=str(i))
            self.assertEqual(self.sbx.activate(rid).returncode, 0)
            ids.append(rid)
        remaining = {r["id"] for r in self.sbx.status()["releases"]}
        self.assertIn(ids[-1], remaining)
        self.assertIn(ids[-2], remaining)
        self.assertTrue(any(r.startswith("legacy-") for r in remaining), "the legacy release is never pruned")
        self.assertNotIn(ids[0], remaining)
        self.assertLessEqual(len(remaining), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
