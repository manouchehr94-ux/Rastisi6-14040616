"""The migration classifier: what may run automatically, what needs a human, what is refused without a phrase."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import migration_guard as G  # noqa: E402


def levels(src):
    return [f["level"] for f in G.analyze_source(src)]


def mig(ops):
    return "from django.db import migrations, models\nclass Migration(migrations.Migration):\n    operations = [\n%s\n    ]\n" % ops


class ClassificationTests(unittest.TestCase):
    def test_additive_operations(self):
        self.assertEqual(G.worst(levels(mig("migrations.CreateModel(name='X', fields=[])"))), "ADDITIVE")
        self.assertEqual(G.worst(levels(mig("migrations.AddField(model_name='a', name='b', field=models.CharField(max_length=5, null=True))"))), "ADDITIVE")
        self.assertEqual(G.worst(levels(mig("migrations.AddField(model_name='a', name='b', field=models.IntegerField(db_default=0))"))), "ADDITIVE")
        self.assertEqual(G.worst(levels(mig("migrations.AddField(model_name='a', name='b', field=models.ManyToManyField(to='x.Y'))"))), "ADDITIVE")
        self.assertEqual(G.worst(levels(mig("migrations.AddIndex(model_name='a', index=models.Index(fields=['b'], name='i'))"))), "ADDITIVE")

    def test_a_plain_default_is_not_safe_for_the_previous_release(self):
        """Django drops the DB default after adding the column: the N-1 code's INSERT would violate NOT NULL."""
        for field in ("models.CharField(max_length=5, default='x')", "models.BooleanField(default=False)", "models.IntegerField()"):
            with self.subTest(field=field):
                self.assertEqual(G.worst(levels(mig("migrations.AddField(model_name='a', name='b', field=%s)" % field))), "REVIEW")

    def test_destructive_operations(self):
        for op in ("migrations.RemoveField(model_name='a', name='b')", "migrations.DeleteModel(name='A')",
                   "migrations.RenameField(model_name='a', old_name='b', new_name='c')", "migrations.RenameModel(old_name='A', new_name='B')",
                   "migrations.AlterModelTable(name='a', table='b')"):
            with self.subTest(op=op):
                self.assertEqual(G.worst(levels(mig(op))), "DESTRUCTIVE")

    def test_review_operations(self):
        for op in ("migrations.AlterField(model_name='a', name='b', field=models.IntegerField())",
                   "migrations.AddConstraint(model_name='a', constraint=models.UniqueConstraint(fields=['b'], name='u'))",
                   "migrations.AlterUniqueTogether(name='a', unique_together={('b','c')})"):
            with self.subTest(op=op):
                self.assertEqual(G.worst(levels(mig(op))), "REVIEW")

    def test_data_migrations(self):
        self.assertEqual(G.worst(levels(mig("migrations.RunPython(forward, backward)"))), "REVIEW")
        self.assertEqual(G.worst(levels(mig("migrations.RunPython(forward)"))), "DESTRUCTIVE")                       # irreversible
        self.assertEqual(G.worst(levels(mig("migrations.RunPython(forward, migrations.RunPython.noop)"))), "REVIEW")

    def test_raw_sql(self):
        self.assertEqual(G.worst(levels(mig("migrations.RunSQL('DROP TABLE x', 'SELECT 1')"))), "DESTRUCTIVE")
        self.assertEqual(G.worst(levels(mig("migrations.RunSQL('DELETE FROM x WHERE 1=1', 'SELECT 1')"))), "DESTRUCTIVE")
        self.assertEqual(G.worst(levels(mig("migrations.RunSQL('CREATE INDEX i ON x(a)', 'DROP INDEX i')"))), "REVIEW")
        self.assertEqual(G.worst(levels(mig("migrations.RunSQL('CREATE INDEX i ON x(a)')"))), "DESTRUCTIVE")        # no reverse_sql

    def test_unparseable_migration_is_destructive(self):
        self.assertEqual(G.worst(levels("def broken(:\n")), "DESTRUCTIVE")

    def test_worst_wins(self):
        self.assertEqual(G.worst(["ADDITIVE", "REVIEW", "ADDITIVE"]), "REVIEW")
        self.assertEqual(G.worst(["REVIEW", "DESTRUCTIVE"]), "DESTRUCTIVE")
        self.assertEqual(G.worst([]), "NONE")


class GitRangeTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="guard-"))
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.repo)]))
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.repo / "apps" / "shop" / "migrations").mkdir(parents=True)
        (self.repo / "apps" / "shop" / "migrations" / "__init__.py").write_text("")
        self.write("0001_initial.py", mig("migrations.CreateModel(name='X', fields=[])"))
        self.base = self.commit("base")

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.repo)] + list(a), capture_output=True, text=True, check=True).stdout.strip()

    def write(self, name, text):
        (self.repo / "apps" / "shop" / "migrations" / name).write_text(text)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def test_no_migration_change_is_NONE_and_rollback_safe(self):
        (self.repo / "README").write_text("x")
        head = self.commit("docs")
        r = G.analyze_range(self.repo, self.base, head)
        self.assertEqual((r["level"], r["rollback_safe"], r["new_migrations"]), ("NONE", True, []))

    def test_a_new_additive_migration_is_listed_by_name(self):
        self.write("0002_add.py", mig("migrations.AddField(model_name='x', name='n', field=models.CharField(max_length=3, null=True))"))
        head = self.commit("add")
        r = G.analyze_range(self.repo, self.base, head)
        self.assertEqual((r["level"], r["rollback_safe"], r["new_migrations"]), ("ADDITIVE", True, ["shop.0002_add"]))

    def test_editing_a_published_migration_is_destructive(self):
        self.write("0001_initial.py", mig("migrations.CreateModel(name='X', fields=[('a', models.IntegerField())])"))
        head = self.commit("edit")
        r = G.analyze_range(self.repo, self.base, head)
        self.assertEqual(r["level"], "DESTRUCTIVE")
        self.assertTrue(r["requires_destructive_ack"])
        self.assertEqual(r["destructive_ack_phrase"], "I-ACCEPT-DESTRUCTIVE-MIGRATION-" + head[:12])

    def test_deleting_a_published_migration_is_destructive(self):
        (self.repo / "apps" / "shop" / "migrations" / "0001_initial.py").unlink()
        head = self.commit("rm")
        self.assertEqual(G.analyze_range(self.repo, self.base, head)["level"], "DESTRUCTIVE")

    def test_first_release_counts_every_migration_as_new(self):
        r = G.analyze_range(self.repo, "", self.base)
        self.assertEqual(r["new_migrations"], ["shop.0001_initial"])

    def test_review_level_needs_approval_and_blocks_auto_rollback(self):
        self.write("0002_data.py", mig("migrations.RunPython(f, g)"))
        head = self.commit("data")
        r = G.analyze_range(self.repo, self.base, head)
        self.assertEqual((r["level"], r["requires_allow_migrations"], r["rollback_safe"]), ("REVIEW", True, False))


class RealHistoryTests(unittest.TestCase):
    """Sanity check against the project's own history (skipped when the commits are not available)."""

    def test_the_captcha_release_has_no_migrations(self):
        repo = Path(__file__).resolve().parents[3]
        have = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", "fa416ddbf1ff31652dd7accb9576097fbab0405a"], capture_output=True).returncode == 0
        if not have:
            self.skipTest("captcha commit not present")
        r = G.analyze_range(repo, "6a6897b7f7b034d6b80d3e693a2aa4e82b1039f4", "fa416ddbf1ff31652dd7accb9576097fbab0405a")
        self.assertEqual((r["level"], r["new_migrations"]), ("NONE", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
