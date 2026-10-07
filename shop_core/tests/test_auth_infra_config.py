"""Unit tests for the production auth-infrastructure configuration helpers and
system checks (shared rate-limit cache, trusted proxies, Turnstile, cookies)."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from shop_core import checks
from shop_core.env_config import (
    PRODUCTION_RATE_LIMIT_BACKENDS,
    RATE_LIMIT_CACHE_ALIAS,
    REDIS_CACHE_BACKEND,
    build_cache_config,
    cookie_security_problems,
    rate_limit_cache_problems,
    resolve_trusted_proxy_cidrs,
    resolve_turnstile_settings,
    trusted_proxy_problems,
    validate_redis_cache_url,
)

_URL = "RASTISI_RATE_LIMIT_CACHE_URL"
_SECRET_URL = "rediss://:p%40ss-w0rd-SECRET@cache.internal.example:6380/2"


class BuildCacheConfigTests(SimpleTestCase):
    def test_debug_without_url_uses_shared_local_locmem_for_both_aliases(self):
        caches = build_cache_config(True, environ={})
        self.assertIn("locmem", caches["default"]["BACKEND"])
        self.assertIn("locmem", caches[RATE_LIMIT_CACHE_ALIAS]["BACKEND"])
        # same LOCATION => same storage => cache.clear() on default resets rate limits in tests
        self.assertEqual(caches["default"]["LOCATION"], caches[RATE_LIMIT_CACHE_ALIAS]["LOCATION"])

    def test_production_without_url_is_refused_and_never_falls_back(self):
        for environ in ({}, {_URL: ""}, {_URL: "   "}):
            with self.subTest(environ=environ), self.assertRaises(ImproperlyConfigured) as ctx:
                build_cache_config(False, environ=environ)
            self.assertIn(_URL, str(ctx.exception))

    def test_url_selects_djangos_builtin_redis_backend_with_timeouts(self):
        caches = build_cache_config(False, environ={_URL: _SECRET_URL})
        config = caches[RATE_LIMIT_CACHE_ALIAS]
        self.assertEqual(config["BACKEND"], REDIS_CACHE_BACKEND)
        self.assertEqual(config["LOCATION"], _SECRET_URL)
        self.assertGreater(config["OPTIONS"]["socket_timeout"], 0)
        self.assertGreater(config["OPTIONS"]["socket_connect_timeout"], 0)
        self.assertIn("locmem", caches["default"]["BACKEND"])  # default is never Redis

    def test_url_is_honoured_in_debug_too(self):
        caches = build_cache_config(True, environ={_URL: "redis://127.0.0.1:6379/0"})
        self.assertEqual(caches[RATE_LIMIT_CACHE_ALIAS]["BACKEND"], REDIS_CACHE_BACKEND)

    def test_malformed_urls_fail_without_echoing_the_secret(self):
        bad = [
            "memcached://host:11211", "http://host/0", "redis://", "redis:///0", "redis://:pw@/0",
            "redis://host:notaport/0", "redis://host:99999/0", "redis://host/abc",
            "redis://host:6379/0?ssl_cert_reqs=none", "rediss://:SECRETPW@host/0#frag",
            "just-a-string", "redis://[::1", "redis://:SECRETPW@host:70000/0",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured) as ctx:
                build_cache_config(False, environ={_URL: url})
            self.assertNotIn("SECRETPW", str(ctx.exception))
            self.assertNotIn(url, str(ctx.exception))

    def test_valid_urls(self):
        for url in (
            "redis://localhost", "redis://localhost:6379/0", "rediss://:pw@cache.example:6380/3",
            "redis://user:pw@10.0.0.5:6379", "redis://[::1]:6379/0",
        ):
            with self.subTest(url=url):
                validate_redis_cache_url(url, name=_URL)


class EffectiveCacheProblemTests(SimpleTestCase):
    def test_redis_is_acceptable(self):
        caches = build_cache_config(False, environ={_URL: "redis://127.0.0.1:6379/0"})
        self.assertEqual(rate_limit_cache_problems(caches), [])

    def test_process_local_and_dummy_backends_are_rejected(self):
        for backend in (
            "django.core.cache.backends.locmem.LocMemCache", "django.core.cache.backends.dummy.DummyCache",
            "django.core.cache.backends.filebased.FileBasedCache", "django.core.cache.backends.db.DatabaseCache",
            "",
        ):
            with self.subTest(backend=backend):
                caches = {RATE_LIMIT_CACHE_ALIAS: {"BACKEND": backend, "LOCATION": "x"}}
                self.assertTrue(rate_limit_cache_problems(caches))

    def test_missing_alias_or_location_is_rejected(self):
        self.assertTrue(rate_limit_cache_problems({}))
        self.assertTrue(rate_limit_cache_problems({"default": {"BACKEND": REDIS_CACHE_BACKEND, "LOCATION": "x"}}))
        self.assertTrue(rate_limit_cache_problems({RATE_LIMIT_CACHE_ALIAS: {"BACKEND": REDIS_CACHE_BACKEND}}))

    def test_only_redis_is_in_the_allow_list(self):
        self.assertEqual(PRODUCTION_RATE_LIMIT_BACKENDS, {REDIS_CACHE_BACKEND})

    def test_check_errors_in_production_only(self):
        locmem = {RATE_LIMIT_CACHE_ALIAS: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "x"}}
        with override_settings(RASTISI_PRODUCTION_MODE=True, CACHES=locmem):
            self.assertEqual([e.id for e in checks.check_rate_limit_cache(None)], ["rastisi.E001"])
        with override_settings(RASTISI_PRODUCTION_MODE=False, CACHES=locmem):
            self.assertEqual(checks.check_rate_limit_cache(None), [])
        redis = {RATE_LIMIT_CACHE_ALIAS: {"BACKEND": REDIS_CACHE_BACKEND, "LOCATION": "redis://h:1/0"}}
        with override_settings(RASTISI_PRODUCTION_MODE=True, CACHES=redis):
            self.assertEqual(checks.check_rate_limit_cache(None), [])


class TrustedProxyConfigTests(SimpleTestCase):
    _NAME = "DJANGO_TRUSTED_PROXY_CIDRS"

    def test_unset_means_nothing_is_trusted(self):
        self.assertEqual(resolve_trusted_proxy_cidrs(environ={}), ())
        self.assertEqual(resolve_trusted_proxy_cidrs(environ={self._NAME: " , "}), ())

    def test_parses_ipv4_ipv6_hosts_and_unix_token(self):
        raw = "10.0.0.0/8, 192.168.1.5, 2001:db8::/32 ,fd00::1,UNIX,10.0.0.0/8"
        self.assertEqual(
            resolve_trusted_proxy_cidrs(environ={self._NAME: raw}),
            ("10.0.0.0/8", "192.168.1.5/32", "2001:db8::/32", "fd00::1/128", "unix"),
        )

    def test_host_bits_are_tolerated_and_normalised(self):
        self.assertEqual(resolve_trusted_proxy_cidrs(environ={self._NAME: "10.1.2.3/8"}), ("10.0.0.0/8",))

    def test_invalid_entries_fail_clearly(self):
        for raw in ("10.0.0.0/33", "garbage", "10.0.0.0/8,oops", "1.2.3", "10.0.0.0/8;11.0.0.0/8", "2001:db8::/129"):
            with self.subTest(raw=raw), self.assertRaises(ImproperlyConfigured) as ctx:
                resolve_trusted_proxy_cidrs(environ={self._NAME: raw})
            self.assertIn(self._NAME, str(ctx.exception))

    def test_contradictions(self):
        header = ("HTTP_X_FORWARDED_PROTO", "https")
        self.assertTrue(trusted_proxy_problems(trusted_cidrs=(), secure_proxy_ssl_header=header))
        self.assertEqual(trusted_proxy_problems(trusted_cidrs=("10.0.0.0/8",), secure_proxy_ssl_header=header), [])
        self.assertEqual(trusted_proxy_problems(trusted_cidrs=(), secure_proxy_ssl_header=None), [])
        # trust-everything networks defeat the whole model
        for cidr in ("0.0.0.0/0", "::/0"):
            with self.subTest(cidr=cidr):
                self.assertTrue(trusted_proxy_problems(trusted_cidrs=(cidr,), secure_proxy_ssl_header=None))
        self.assertTrue(trusted_proxy_problems(
            trusted_cidrs=(), secure_proxy_ssl_header=None, use_x_forwarded_host=True,
        ))

    def test_check_reports_contradiction_and_invalid_state(self):
        with override_settings(
            RASTISI_TRUSTED_PROXY_CIDRS=(), SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        ):
            self.assertIn("rastisi.E003", [e.id for e in checks.check_trusted_proxy(None)])
        with override_settings(RASTISI_TRUSTED_PROXY_CIDRS=("not-a-cidr",), SECURE_PROXY_SSL_HEADER=None):
            self.assertIn("rastisi.E003", [e.id for e in checks.check_trusted_proxy(None)])
        with override_settings(RASTISI_PRODUCTION_MODE=True, USE_X_FORWARDED_HOST=True, RASTISI_TRUSTED_PROXY_CIDRS=()):
            self.assertIn("rastisi.E003", [e.id for e in checks.check_trusted_proxy(None)])


_TS_OK = {
    "TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
    "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000AA",
    "TURNSTILE_EXPECTED_HOSTNAMES": "rastisi.ir, WWW.rastisi.ir.",
}


class TurnstileConfigTests(SimpleTestCase):
    def test_development_may_run_with_turnstile_off(self):
        result = resolve_turnstile_settings(True, environ={})
        self.assertFalse(result["enabled"])

    def test_development_may_explicitly_enable_it(self):
        result = resolve_turnstile_settings(True, environ={"TURNSTILE_ENABLED": "true", **_TS_OK})
        self.assertTrue(result["enabled"])

    def test_production_correct_configuration_passes_and_defaults_to_enabled(self):
        result = resolve_turnstile_settings(False, environ=dict(_TS_OK))
        self.assertTrue(result["enabled"])
        self.assertEqual(result["expected_hostnames"], ("rastisi.ir", "www.rastisi.ir"))

    def test_production_disabled_is_refused_even_if_explicit(self):
        for value in ("false", "0", "off", "no"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                resolve_turnstile_settings(False, environ={"TURNSTILE_ENABLED": value, **_TS_OK})

    def test_production_with_nothing_set_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_turnstile_settings(False, environ={})

    def test_production_missing_each_required_value_is_refused(self):
        for missing in _TS_OK:
            with self.subTest(missing=missing), self.assertRaises(ImproperlyConfigured):
                resolve_turnstile_settings(False, environ={k: v for k, v in _TS_OK.items() if k != missing})
        with self.assertRaises(ImproperlyConfigured):
            resolve_turnstile_settings(False, environ={**_TS_OK, "TURNSTILE_EXPECTED_HOSTNAMES": " , "})

    def test_malformed_hostnames_are_refused(self):
        for bad in ("https://rastisi.ir", "rastisi.ir:443", "rastisi.ir/login", "*.rastisi.ir", "ras tisi.ir"):
            with self.subTest(bad=bad), self.assertRaises(ImproperlyConfigured):
                resolve_turnstile_settings(False, environ={**_TS_OK, "TURNSTILE_EXPECTED_HOSTNAMES": bad})

    def test_enabled_in_development_still_requires_keys(self):
        with self.assertRaises(ImproperlyConfigured):
            resolve_turnstile_settings(True, environ={"TURNSTILE_ENABLED": "true"})

    def test_errors_never_contain_secret_values(self):
        try:
            resolve_turnstile_settings(False, environ={
                "TURNSTILE_ENABLED": "false", "TURNSTILE_SECRET_KEY": "SUPERSECRETVALUE",
            })
        except ImproperlyConfigured as exc:
            self.assertNotIn("SUPERSECRETVALUE", str(exc))

    def test_system_check_mirrors_the_startup_rules(self):
        base = dict(
            RASTISI_PRODUCTION_MODE=True, TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="k",
            TURNSTILE_SECRET_KEY="s", TURNSTILE_EXPECTED_HOSTNAMES=("rastisi.ir",),
        )
        with override_settings(**base):
            self.assertEqual(checks.check_turnstile(None), [])
        for override in (
            {"TURNSTILE_ENABLED": False}, {"TURNSTILE_SITE_KEY": ""}, {"TURNSTILE_SECRET_KEY": ""},
            {"TURNSTILE_EXPECTED_HOSTNAMES": ()},
        ):
            with self.subTest(override=override), override_settings(**{**base, **override}):
                self.assertTrue(checks.check_turnstile(None))
        with override_settings(**{**base, "RASTISI_PRODUCTION_MODE": False, "TURNSTILE_ENABLED": False}):
            self.assertEqual(checks.check_turnstile(None), [])


class CookieSecurityTests(SimpleTestCase):
    _OK = dict(
        session_secure=True, csrf_secure=True, session_httponly=True, session_samesite="Lax",
        csrf_samesite="Lax", session_domain=None, csrf_domain=None,
    )

    def test_ok(self):
        self.assertEqual(cookie_security_problems(**self._OK), [])
        self.assertEqual(cookie_security_problems(**{**self._OK, "session_samesite": "Strict"}), [])

    def test_each_unsafe_setting_is_reported(self):
        for override in (
            {"session_secure": False}, {"csrf_secure": False}, {"session_httponly": False},
            {"session_samesite": None}, {"session_samesite": "None"}, {"csrf_samesite": False},
            {"session_domain": ".rastisi.ir"}, {"csrf_domain": ".rastisi.ir"},
        ):
            with self.subTest(override=override):
                self.assertTrue(cookie_security_problems(**{**self._OK, **override}))

    def test_system_check(self):
        with override_settings(
            RASTISI_PRODUCTION_MODE=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
            SESSION_COOKIE_DOMAIN=None, CSRF_COOKIE_DOMAIN=None,
        ):
            self.assertEqual(checks.check_auth_cookies(None), [])
        with override_settings(RASTISI_PRODUCTION_MODE=True, SESSION_COOKIE_DOMAIN=".rastisi.ir"):
            self.assertTrue(checks.check_auth_cookies(None))
        with override_settings(RASTISI_PRODUCTION_MODE=False, SESSION_COOKIE_SECURE=False):
            self.assertEqual(checks.check_auth_cookies(None), [])
