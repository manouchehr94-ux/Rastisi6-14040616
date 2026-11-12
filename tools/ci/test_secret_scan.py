"""The secret scanner must catch real shapes and stay quiet on documentation and fixtures. Synthetic values are assembled at runtime so this
file itself never contains a credential-looking literal."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import secret_scan as S  # noqa: E402


def scan(path, text):
    return [rule for _, _, rule in S.scan_text(path, text)]


class ScannerTests(unittest.TestCase):
    def test_catches_real_shapes(self):
        pem = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
        aws = "AKIA" + "QWERTYUIOPASDFGH"
        gh = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        jwt = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "abcdefghijklmnop"
        url = "DATABASE_URL = 'postgres://app:" + "Zq8vK2mXr9Lp@db.internal:5432/prod'"
        assign = "STRIPE_SECRET = '" + "n4Kj82hdQp0wLx7TzYb3'"
        for path, text, rule in (("app/x.py", pem, "private-key"), ("app/x.py", "k = '%s'" % aws, "aws-access-key"),
                                 ("app/x.py", "t = '%s'" % gh, "github-token"), ("app/x.py", jwt, "jwt"),
                                 ("deploy/x.sh", url, "password-in-url"), ("app/settings.py", assign, "secret-assignment")):
            with self.subTest(rule=rule):
                self.assertIn(rule, scan(path, text))

    def test_stays_quiet_on_placeholders_documentation_and_synthetic_values(self):
        for path, text in (
            (".github/workflows/ci.yml", "DATABASE_URL: postgresql://postgres:" + "ci-service-pw-8841@127.0.0.1:5432/x"),
            (".env.example", "DJANGO_SECRET_KEY=CHANGE_ME_please_replace_me_now"),
            ("app/x.py", "# usage: postgres://user:pass@host:5432/dbname"),
            ("app/x.py", "DATABASE_URL = 'postgres://${USER}:${PASS}@localhost/db'"),
            ("app/x.py", "key = 'AKIA" + "IOSFODNN7EXAMPLE'"),
            ("app/x.py", "key = 'AKIA" + "A" * 16 + "'"),
            ("app/x.py", "SECRET_KEY = os.environ['SECRET_KEY']"),
            ("app/x.py", "password = 'a-placeholder-for-the-docs-123'"),
            ("app/tests/test_x.py", "password = 'a-long-fixture-password-1234'"),
            ("docs/a.md", "PASSWORD = 'some-long-example-value-here'"),
        ):
            with self.subTest(text=text[:40]):
                self.assertEqual(scan(path, text), [])

    def test_a_local_url_password_is_only_tolerated_in_workflow_files(self):
        text = "DATABASE_URL = 'postgresql://app:" + "Zq8vK2mXr9Lp@127.0.0.1:5432/prod'"
        self.assertEqual(scan(".github/workflows/ci.yml", text), [])
        self.assertIn("password-in-url", scan("deploy/x.sh", text))
        remote = "DATABASE_URL: postgresql://app:" + "Zq8vK2mXr9Lp@db.internal:5432/prod"
        self.assertIn("password-in-url", scan(".github/workflows/ci.yml", remote))

    def test_output_never_contains_the_secret(self):
        import io
        import subprocess
        import tempfile
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(repo)]))
        secret = "ghp_" + "Zx9Yw8Vv7Uu6Tt5Ss4Rr3Qq2Pp1Oo0Nn9Mm8"
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "a.py").write_text("T = '%s'\n" % secret)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e.c", "-c", "user.name=t", "commit", "-q", "-m", "x"], check=True)
        proc = subprocess.run([sys.executable, str(Path(S.__file__)), "--repo", str(repo)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("a.py:1  github-token", proc.stdout)
        self.assertNotIn(secret, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
