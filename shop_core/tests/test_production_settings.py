"""End-to-end checks that shop_core/settings.py actually wires env_config's
functions correctly.

settings.py is imported exactly once by this very test process (Django is
already running), so its module-level code cannot be re-exercised with a
different environment inside this process — these tests spawn a fresh
`python manage.py check` subprocess with a controlled environment instead.
This is slower than a plain unit test, so it is used sparingly, only to
confirm the wiring in settings.py itself; the parsing/validation logic is
covered exhaustively (and fast) in test_env_config.py.
"""

import os
import subprocess
import sys

from django.test import SimpleTestCase

from shop_core.env_config import DEV_INSECURE_SECRET_KEY

MANAGE_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "manage.py")


def _run_check(extra_env):
    """Run ``manage.py check`` with controlled *application* config.

    On Windows, stripping the child process environment down to PATH and
    PYTHONPATH also removes OS networking/runtime variables that CPython's
    ``_overlapped``/``asyncio`` stack may need, causing WinError 10106 before
    Django settings are imported. Preserve the operating-system environment
    and remove only variables that can configure this application.
    """
    env = os.environ.copy()
    controlled_prefixes = (
        "DJANGO_", "RASTISI_", "STORES_", "AUTH_", "SHOP_", "PAYMENT_", "TURNSTILE_",
    )
    controlled_exact = {
        "DATABASE_URL", "LOG_LEVEL", "PAYMENTS_SIMULATION_ENABLED",
    }
    for key in list(env):
        upper = key.upper()
        if upper.startswith(controlled_prefixes) or upper in controlled_exact:
            env.pop(key, None)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, MANAGE_PY, "check"],
        cwd=os.path.dirname(MANAGE_PY),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


#: A complete, safe production environment (placeholders only — no real secrets).
_PROD_ENV = {
    "DJANGO_DEBUG": "False",
    "DJANGO_SECRET_KEY": "a-real-unique-production-secret",
    "DJANGO_ALLOWED_HOSTS": "example.com,www.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.com",
    "RASTISI_RATE_LIMIT_CACHE_URL": "rediss://:placeholder-pw@cache.example.internal:6380/0",
    "TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
    "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000AA",
    "TURNSTILE_EXPECTED_HOSTNAMES": "example.com,www.example.com",
}


class DevelopmentDefaultsRemainUsableTests(SimpleTestCase):
    def test_no_env_vars_at_all_still_passes_check(self):
        result = _run_check({})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("System check identified no issues", result.stdout + result.stderr)


class ProductionSafetyEnforcedEndToEndTests(SimpleTestCase):
    def test_debug_false_without_secret_key_fails_fast(self):
        result = _run_check({"DJANGO_DEBUG": "False", "DJANGO_ALLOWED_HOSTS": "example.com"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is required", result.stderr)

    def test_debug_false_with_dev_secret_key_fails_fast(self):
        result = _run_check(
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_ALLOWED_HOSTS": "example.com",
                "DJANGO_SECRET_KEY": DEV_INSECURE_SECRET_KEY,
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("known development-only insecure key", result.stderr)

    def test_debug_false_without_allowed_hosts_fails_fast(self):
        result = _run_check(
            {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "a-real-unique-production-secret"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS must be set", result.stderr)

    def test_debug_false_fully_configured_passes(self):
        result = _run_check(dict(_PROD_ENV))
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("System check identified no issues", result.stdout + result.stderr)

    def test_invalid_boolean_env_var_fails_with_clear_message(self):
        result = _run_check({"DJANGO_SECURE_SSL_REDIRECT": "maybe"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not a valid boolean", result.stderr)

    def test_invalid_database_url_fails_with_clear_message(self):
        result = _run_check({"DATABASE_URL": "mysql://user:pass@host/db"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL scheme", result.stderr)


class ProductionAuthInfrastructureEnforcedEndToEndTests(SimpleTestCase):
    """A real ``DJANGO_DEBUG=False`` process must refuse to start (or fail
    ``check``) with an unsafe auth-infrastructure configuration — each case
    removes/breaks exactly one thing from an otherwise valid environment."""

    def _fails(self, drop=(), **override):
        env = {k: v for k, v in _PROD_ENV.items() if k not in drop}
        env.update(override)
        result = _run_check(env)
        self.assertNotEqual(result.returncode, 0, msg="unsafe production config was accepted")
        return result.stderr

    def test_missing_shared_cache_url_fails(self):
        self.assertIn("RASTISI_RATE_LIMIT_CACHE_URL is required", self._fails(drop=["RASTISI_RATE_LIMIT_CACHE_URL"]))

    def test_malformed_cache_url_fails_without_leaking_the_password(self):
        for url in ("memcached://host:11211", "redis://:LEAKME@host:6379/0?ssl_cert_reqs=none", "redis://:LEAKME@:6379/0"):
            with self.subTest(url=url):
                stderr = self._fails(RASTISI_RATE_LIMIT_CACHE_URL=url)
                self.assertIn("RASTISI_RATE_LIMIT_CACHE_URL", stderr)
                self.assertNotIn("LEAKME", stderr)

    def test_turnstile_disabled_or_incomplete_fails(self):
        self.assertIn("TURNSTILE_ENABLED must be true", self._fails(TURNSTILE_ENABLED="false"))
        self.assertIn("TURNSTILE_SITE_KEY is required", self._fails(drop=["TURNSTILE_SITE_KEY"]))
        self.assertIn("TURNSTILE_SECRET_KEY is required", self._fails(drop=["TURNSTILE_SECRET_KEY"]))
        self.assertIn("TURNSTILE_EXPECTED_HOSTNAMES is required", self._fails(drop=["TURNSTILE_EXPECTED_HOSTNAMES"]))

    def test_malformed_trusted_proxy_cidr_fails(self):
        self.assertIn("DJANGO_TRUSTED_PROXY_CIDRS", self._fails(DJANGO_TRUSTED_PROXY_CIDRS="10.0.0.0/99"))

    def test_secure_proxy_header_without_trusted_proxies_is_contradictory(self):
        self.assertIn(
            "DJANGO_TRUSTED_PROXY_CIDRS is empty",
            self._fails(DJANGO_SECURE_PROXY_SSL_HEADER="X-Forwarded-Proto:https"),
        )

    def test_insecure_auth_cookies_fail(self):
        self.assertIn("SESSION_COOKIE_SECURE", self._fails(DJANGO_SESSION_COOKIE_SECURE="false"))
        self.assertIn("CSRF_COOKIE_SECURE", self._fails(DJANGO_CSRF_COOKIE_SECURE="false"))

    def test_proxy_and_tls_configuration_passes(self):
        result = _run_check({
            **_PROD_ENV,
            "DJANGO_TRUSTED_PROXY_CIDRS": "10.0.0.0/8,2001:db8::/32",
            "DJANGO_SECURE_PROXY_SSL_HEADER": "X-Forwarded-Proto:https",
            "DJANGO_SECURE_SSL_REDIRECT": "true",
        })
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_development_still_needs_none_of_it(self):
        result = _run_check({"DJANGO_DEBUG": "True"})
        self.assertEqual(result.returncode, 0, msg=result.stderr)


class DevOtpStartupGuardEndToEndTests(SimpleTestCase):
    """RASTISI_DEV_OTP_CODE is local-QA only: production must refuse to start with it."""

    def test_debug_false_with_a_dev_otp_code_fails_startup(self):
        result = _run_check({**_PROD_ENV, "RASTISI_DEV_OTP_CODE": "123456"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RASTISI_DEV_OTP_CODE", result.stderr)
        self.assertNotIn("123456", result.stderr)

    def test_a_malformed_dev_otp_code_fails_even_in_debug(self):
        for bad in ("12345", "abcdef", "1234567"):
            with self.subTest(bad=bad):
                result = _run_check({"DJANGO_DEBUG": "True", "RASTISI_DEV_OTP_CODE": bad})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exactly 6 ASCII digits", result.stderr)

    def test_a_valid_dev_otp_code_in_debug_passes_check(self):
        result = _run_check({"DJANGO_DEBUG": "True", "RASTISI_DEV_OTP_CODE": "123456"})
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_unset_is_the_default_and_passes(self):
        self.assertEqual(_run_check({"DJANGO_DEBUG": "True"}).returncode, 0)

    def test_the_console_otp_flag_is_not_a_production_escape_hatch(self):
        result = _run_check({**_PROD_ENV, "RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP": "true"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP", result.stderr)

    def test_the_console_otp_flag_in_debug_still_works_for_local_use(self):
        result = _run_check({"DJANGO_DEBUG": "True", "RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP": "true"})
        self.assertEqual(result.returncode, 0, msg=result.stderr)
