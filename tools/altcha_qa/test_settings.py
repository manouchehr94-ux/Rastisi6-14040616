"""Preview settings must never migrate an inherited production DSN."""

import json
import os
import subprocess
import sys
from django.test import SimpleTestCase


class PreviewSettingsGuardTests(SimpleTestCase):
    def run_settings(self, **overrides):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("DJANGO_", "RASTISI_")) and key != "DATABASE_URL"
        }
        env.update(
            DJANGO_DEBUG="true",
            RASTISI_RATE_LIMIT_CACHE_URL="redis://127.0.0.1:6394/14",
        )
        env.update(overrides)
        return subprocess.run(
            [
                sys.executable,
                "-c",
                """import json
from tools.altcha_qa import settings as s
print(json.dumps({'database':str(s.DATABASES['default']['NAME']), 'captcha':s.RASTISI_CAPTCHA_ENABLED,
 'sms':s.RASTISI_OWNER_SMS_BACKEND, 'email':s.EMAIL_BACKEND}))""",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_preview_has_a_separate_local_database_and_no_real_delivery(self):
        result = self.run_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertTrue(
            values["database"]
            .replace("\\", "/")
            .endswith("/.altcha-qa/preview.sqlite3")
        )
        self.assertTrue(values["captcha"])
        self.assertEqual(values["sms"], "console")
        self.assertIn("locmem", values["email"])

    def test_production_mode_is_refused(self):
        result = self.run_settings(DJANGO_DEBUG="false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit DJANGO_DEBUG=true", result.stderr)

    def test_inherited_database_and_secret_are_refused_without_disclosure(self):
        for name in ("DATABASE_URL", "DJANGO_SECRET_KEY"):
            with self.subTest(name=name):
                result = self.run_settings(**{name: "private-dummy-guard-marker"})
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(
                    "private-dummy-guard-marker", result.stdout + result.stderr
                )
                self.assertIn("fresh local shell", result.stderr)

    def test_remote_or_wrong_database_redis_is_refused(self):
        for url in (
            "redis://private-dummy-guard-marker.invalid/14",
            "redis://127.0.0.1/0",
            "rediss://127.0.0.1/14",
        ):
            with self.subTest(url=url):
                result = self.run_settings(RASTISI_RATE_LIMIT_CACHE_URL=url)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("dedicated loopback Redis database /14", result.stderr)
                self.assertNotIn(
                    "private-dummy-guard-marker", result.stdout + result.stderr
                )
