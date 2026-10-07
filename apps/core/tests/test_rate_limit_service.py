"""Rate-limiter semantics: window/expiry, key privacy, outage policy, backend selection.

These run against the dev LocMem store and against scripted fakes. They do NOT
prove Redis behaviour — ``test_rate_limit_redis`` does that against a real Redis
server with multiple independent processes.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.core.services import rate_limit
from apps.core.services.rate_limit import (
    _LUA_HIT,
    UNAVAILABLE_MESSAGE,
    RateLimitExceeded,
    RateLimitUnavailable,
    _CacheCounter,
    _RedisCounter,
    build_key,
    enforce_rate_limit,
    get_counter,
)
from shop_core.env_config import REDIS_CACHE_BACKEND


class _ScriptedCounter:
    """Stands in for the counter: ``hit`` results (ints or exceptions) are scripted."""

    def __init__(self, *results):
        self.calls = []
        self._results = list(results)

    def hit(self, key, window_seconds):
        self.calls.append((key, window_seconds))
        item = self._results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _with_counter(counter):
    return mock.patch.object(rate_limit, "get_counter", return_value=counter)


class _ScriptedStore:
    """A Django-cache-like store for the LocMem ``_CacheCounter`` path."""

    def __init__(self, *, add=(), incr=()):
        self.calls = []
        self._add, self._incr = list(add), list(incr)

    def _next(self, queue):
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def add(self, key, value, timeout=None):
        self.calls.append(("add", key, value, timeout))
        return self._next(self._add)

    def incr(self, key, delta=1):
        self.calls.append(("incr", key))
        return self._next(self._incr)

    def get(self, *a, **k):  # a read-modify-write implementation would end up here
        self.calls.append(("get",) + a)
        raise AssertionError("limiter must never read-modify-write")

    def set(self, *a, **k):
        self.calls.append(("set",) + a)
        raise AssertionError("limiter must never read-modify-write")


class BasicSemanticsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_allows_up_to_max_then_blocks(self):
        for _ in range(3):
            enforce_rate_limit("t.basic", "1.2.3.4", max_attempts=3, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.basic", "1.2.3.4", max_attempts=3, window_seconds=60)

    def test_distinct_actions_and_identifiers_are_independent(self):
        for _ in range(3):
            enforce_rate_limit("t.a", "x", max_attempts=3, window_seconds=60)
        enforce_rate_limit("t.b", "x", max_attempts=3, window_seconds=60)
        enforce_rate_limit("t.a", "y", max_attempts=3, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.a", "x", max_attempts=3, window_seconds=60)

    def test_fixed_window_expires_and_is_not_extended_by_later_attempts(self):
        clock = {"now": 1_000_000.0}
        with mock.patch("django.core.cache.backends.locmem.time.time", side_effect=lambda: clock["now"]):
            enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)  # window opens at t0
            clock["now"] += 50
            enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)  # incr must NOT refresh TTL
            with self.assertRaises(RateLimitExceeded):
                enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)
            clock["now"] += 11  # t0 + 61s: the original window is over
            enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)
            enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)
            with self.assertRaises(RateLimitExceeded):
                enforce_rate_limit("t.win", "k", max_attempts=2, window_seconds=60)

    def test_concurrent_burst_in_one_process_never_overshoots(self):
        # NOT a multi-worker proof (that is the Redis test); guards the algorithm shape.
        def attempt(_):
            try:
                enforce_rate_limit("t.burst", "k", max_attempts=10, window_seconds=60)
                return 1
            except RateLimitExceeded:
                return 0

        with ThreadPoolExecutor(max_workers=16) as pool:
            allowed = sum(pool.map(attempt, range(200)))
        self.assertEqual(allowed, 10)


class KeyPrivacyTests(SimpleTestCase):
    def test_identifier_is_hashed_and_namespaced(self):
        secret = "victim@example.com|hunter2|123456"
        key = build_key("login_password_identifier", secret)
        self.assertTrue(key.startswith("rl:v1:login_password_identifier:"))
        for fragment in ("victim", "example", "hunter2", "123456", "@", "|"):
            self.assertNotIn(fragment, key)
        self.assertLessEqual(len(key), 250)

    def test_key_is_deterministic_and_identifier_sensitive(self):
        self.assertEqual(build_key("a", "x"), build_key("a", "x"))
        self.assertNotEqual(build_key("a", "x"), build_key("a", "y"))

    def test_invalid_action_is_a_programming_error(self):
        for bad in ("", "has space", "new\nline", "x" * 101, "ünï"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_key(bad, "x")

    def test_raw_identifier_never_reaches_the_backend(self):
        counter = _ScriptedCounter(1)
        with _with_counter(counter):
            enforce_rate_limit("t.priv", "secret@example.com", max_attempts=1, window_seconds=5)
        self.assertNotIn("secret", repr(counter.calls))


class CacheCounterTests(SimpleTestCase):
    """The LocMem (development/tests only) path."""

    def test_first_call_is_a_single_add_with_the_window_ttl(self):
        store = _ScriptedStore(add=[True])
        self.assertEqual(_CacheCounter(store).hit("k", 77), 1)
        self.assertEqual([c[0] for c in store.calls], ["add"])
        self.assertEqual(store.calls[0][2:], (1, 77))

    def test_subsequent_calls_use_incr_only(self):
        store = _ScriptedStore(add=[False], incr=[2])
        self.assertEqual(_CacheCounter(store).hit("k", 77), 2)
        self.assertEqual([c[0] for c in store.calls], ["add", "incr"])

    def test_key_expiring_between_add_and_incr_restarts_the_window(self):
        store = _ScriptedStore(add=[False, True], incr=[ValueError("missing")])
        self.assertEqual(_CacheCounter(store).hit("k", 9), 1)
        self.assertEqual([c[0] for c in store.calls], ["add", "incr", "add"])

    def test_unstable_counter_fails_closed(self):
        store = _ScriptedStore(add=[False] * 3, incr=[ValueError()] * 3)
        with self.assertRaises(RateLimitUnavailable):
            _CacheCounter(store).hit("k", 9)

    def test_never_reads_then_writes(self):
        store = _ScriptedStore(add=[False, False], incr=[2, 6])
        counter = _CacheCounter(store)
        counter.hit("k", 9)
        counter.hit("k", 9)
        self.assertFalse([c for c in store.calls if c[0] in ("get", "set")])


class _FakeRedis:
    """Records every command the production counter sends (no network)."""

    commands = []

    def __init__(self, *a, **k):
        pass

    @classmethod
    def from_url(cls, url, **options):
        cls.url, cls.options = url, options
        return cls()

    def register_script(self, source):
        _FakeRedis.source = source

        def script(keys=(), args=()):
            _FakeRedis.commands.append(("EVALSHA", tuple(keys), tuple(args)))
            return 3

        return script

    def __getattr__(self, name):  # any direct command (incr/expire/get/set/exists/...) is a failure
        def forbidden(*a, **k):
            _FakeRedis.commands.append((name.upper(), a))
            raise AssertionError(f"direct Redis command {name!r}: INCR and EXPIRE must run inside the Lua script")

        return forbidden


_REDIS_CFG = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "x"},
    "ratelimit": {
        "BACKEND": REDIS_CACHE_BACKEND, "LOCATION": "redis://:pw@cache.example:6379/0",
        "OPTIONS": {"socket_timeout": 2, "socket_connect_timeout": 2},
    },
}


class RedisCounterContractTests(SimpleTestCase):
    def setUp(self):
        _FakeRedis.commands = []
        rate_limit._redis_counters.clear()
        self.addCleanup(rate_limit._redis_counters.clear)

    def test_script_does_increment_and_first_expiry_as_one_unit(self):
        # Both commands live in ONE server-side script; the client never sends them separately.
        for command in ("redis.call('INCR'", "redis.call('EXPIRE'", "PTTL"):
            self.assertIn(command, _LUA_HIT)
        self.assertEqual(_LUA_HIT.count("redis.call('INCR'"), 1)
        self.assertIn("count == 1", _LUA_HIT)

    def test_one_round_trip_per_hit_and_no_direct_commands(self):
        with override_settings(CACHES=_REDIS_CFG), mock.patch("redis.Redis", _FakeRedis):
            count = get_counter().hit("rl:v1:a:b", 60)
        self.assertEqual(count, 3)
        self.assertEqual(_FakeRedis.commands, [("EVALSHA", ("rl:v1:a:b",), (60,))])
        self.assertEqual(_FakeRedis.source, _LUA_HIT)

    def test_connection_options_come_from_settings_and_no_network_at_selection_time(self):
        with override_settings(CACHES=_REDIS_CFG), mock.patch("redis.Redis.from_url", side_effect=AssertionError("connected")):
            counter = get_counter()  # must not connect
        self.assertIsInstance(counter, _RedisCounter)
        with override_settings(CACHES=_REDIS_CFG), mock.patch("redis.Redis", _FakeRedis):
            counter.hit("k", 5)
        self.assertEqual(_FakeRedis.options, {"socket_timeout": 2, "socket_connect_timeout": 2})
        self.assertEqual(_FakeRedis.url, "redis://:pw@cache.example:6379/0")

    def test_counter_is_reused_per_configuration(self):
        with override_settings(CACHES=_REDIS_CFG):
            self.assertIs(get_counter(), get_counter())

    def test_local_cache_selects_the_cache_counter(self):
        self.assertIsInstance(get_counter(), _CacheCounter)

    def test_url_is_never_in_repr_or_error_logs(self):
        class Boom(_FakeRedis):
            def register_script(self, source):
                raise ConnectionError("cannot reach redis://:pw@cache.example:6379/0")

        with override_settings(CACHES=_REDIS_CFG), mock.patch("redis.Redis", Boom), \
                self.assertLogs("apps.core.services.rate_limit", level=logging.ERROR) as logs:
            with self.assertRaises(RateLimitUnavailable) as ctx:
                enforce_rate_limit("t.leak", "k", max_attempts=1, window_seconds=5)
        self.assertNotIn("pw@", "\n".join(logs.output) + str(ctx.exception))

    def test_zero_or_negative_window_is_refused_before_touching_the_backend(self):
        counter = _ScriptedCounter()
        with _with_counter(counter):
            for bad in (0, -5):
                with self.assertRaises(ValueError):
                    enforce_rate_limit("t.win0", "k", max_attempts=1, window_seconds=bad)
        self.assertEqual(counter.calls, [])


class OutagePolicyTests(SimpleTestCase):
    def test_backend_error_fails_closed_with_a_persian_message(self):
        counter = _ScriptedCounter(ConnectionError("redis://:topsecret@10.0.0.1:6379 refused"))
        with _with_counter(counter), self.assertRaises(RateLimitUnavailable) as ctx:
            enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)
        self.assertEqual(str(ctx.exception), UNAVAILABLE_MESSAGE)
        self.assertNotIn("topsecret", str(ctx.exception))

    def test_failure_is_logged_without_secrets(self):
        counter = _ScriptedCounter(ConnectionError("redis://:topsecret@10.0.0.1:6379 refused"))
        with _with_counter(counter), self.assertLogs("apps.core.services.rate_limit", level=logging.ERROR) as logs:
            with self.assertRaises(RateLimitUnavailable):
                enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)
        joined = "\n".join(logs.output)
        self.assertIn("ConnectionError", joined)
        self.assertNotIn("topsecret", joined)

    def test_every_exception_type_is_classified_not_leaked(self):
        for exc in (OSError("x"), TimeoutError(), RuntimeError("boom"), KeyError("k")):
            with self.subTest(exc=exc.__class__.__name__):
                with _with_counter(_ScriptedCounter(exc)), self.assertRaises(RateLimitUnavailable):
                    enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)

    def test_outage_never_returns_as_if_allowed(self):
        with _with_counter(_ScriptedCounter(ConnectionError())), self.assertRaises(RateLimitUnavailable):
            enforce_rate_limit("t.out", "k", max_attempts=10**9, window_seconds=9)

    def test_fail_open_is_explicit_opt_in_and_still_logs(self):
        with _with_counter(_ScriptedCounter(ConnectionError())), \
                self.assertLogs("apps.core.services.rate_limit", level=logging.ERROR):
            enforce_rate_limit("t.out", "k", max_attempts=1, window_seconds=9, fail_open=True)

    def test_exceeded_is_not_swallowed_by_fail_open(self):
        with _with_counter(_ScriptedCounter(99)), self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.out", "k", max_attempts=1, window_seconds=9, fail_open=True)

    def test_unavailable_is_not_an_exceeded_subclass(self):
        self.assertFalse(issubclass(RateLimitUnavailable, RateLimitExceeded))


class StoreSelectionTests(SimpleTestCase):
    def test_dev_aliases_share_storage_so_cache_clear_resets_limits(self):
        enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        cache.clear()  # default alias, as used throughout the suite
        enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        cache.clear()
