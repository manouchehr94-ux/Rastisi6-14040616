"""Rate-limiter semantics: atomicity, window/expiry, key privacy, outage policy.

These run against the dev LocMem store and against scripted fake stores. They
do NOT prove Redis behaviour — see ``test_rate_limit_redis.py`` for the real
multi-process verification.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.core.cache import cache, caches
from django.test import SimpleTestCase, override_settings

from apps.core.services import rate_limit
from apps.core.services.rate_limit import (
    UNAVAILABLE_MESSAGE,
    RateLimitExceeded,
    RateLimitUnavailable,
    build_key,
    enforce_rate_limit,
)


class _ScriptedStore:
    """Records every call; behaviour is scripted per test."""

    def __init__(self, *, add=(), incr=(), touch=True):
        self.calls = []
        self._add, self._incr, self._touch = list(add), list(incr), touch

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

    def touch(self, key, timeout=None):
        self.calls.append(("touch", key, timeout))
        return self._touch

    def get(self, *a, **k):  # a read-modify-write implementation would end up here
        self.calls.append(("get",) + a)
        raise AssertionError("limiter must never read-modify-write")

    def set(self, *a, **k):
        self.calls.append(("set",) + a)
        raise AssertionError("limiter must never read-modify-write")


def _with_store(store):
    return mock.patch.object(rate_limit, "_store", return_value=store)


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

    def test_raw_identifier_never_reaches_the_store(self):
        store = _ScriptedStore(add=[True])
        with _with_store(store):
            enforce_rate_limit("t.priv", "secret@example.com", max_attempts=1, window_seconds=5)
        self.assertNotIn("secret", repr(store.calls))


class AtomicPrimitiveTests(SimpleTestCase):
    def test_first_call_is_a_single_atomic_add_with_the_window_ttl(self):
        store = _ScriptedStore(add=[True])
        with _with_store(store):
            enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=77)
        self.assertEqual([c[0] for c in store.calls], ["add"])
        self.assertEqual(store.calls[0][2:], (1, 77))

    def test_subsequent_calls_use_incr_only(self):
        store = _ScriptedStore(add=[False], incr=[2])
        with _with_store(store):
            enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=77)
        self.assertEqual([c[0] for c in store.calls], ["add", "incr"])

    def test_key_expiring_between_add_and_incr_restarts_the_window(self):
        store = _ScriptedStore(add=[False, True], incr=[ValueError("missing")])
        with _with_store(store):
            enforce_rate_limit("t.p", "k", max_attempts=1, window_seconds=9)  # counted as the first attempt
        self.assertEqual([c[0] for c in store.calls], ["add", "incr", "add"])

    def test_incr_that_recreated_an_expired_key_restores_its_ttl(self):
        # Django's Redis incr is EXISTS + INCR: if the key expires in between, INCR
        # creates it with value 1 and NO ttl — it must never become a permanent block.
        store = _ScriptedStore(add=[False], incr=[1])
        with _with_store(store):
            enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=33)
        self.assertEqual(store.calls[-1][0], "touch")
        self.assertEqual(store.calls[-1][2], 33)

    def test_unstable_counter_fails_closed(self):
        store = _ScriptedStore(add=[False] * 3, incr=[ValueError()] * 3)
        with _with_store(store), self.assertRaises(RateLimitUnavailable):
            enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=9)

    def test_wrapper_never_reads_then_writes(self):
        store = _ScriptedStore(add=[False, False], incr=[2, 6])
        with _with_store(store):
            enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=9)
            with self.assertRaises(RateLimitExceeded):
                enforce_rate_limit("t.p", "k", max_attempts=5, window_seconds=9)
        self.assertFalse([c for c in store.calls if c[0] in ("get", "set")])


class OutagePolicyTests(SimpleTestCase):
    def test_backend_error_fails_closed_with_a_persian_message(self):
        store = _ScriptedStore(add=[ConnectionError("redis://:topsecret@10.0.0.1:6379 refused")])
        with _with_store(store), self.assertRaises(RateLimitUnavailable) as ctx:
            enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)
        self.assertEqual(str(ctx.exception), UNAVAILABLE_MESSAGE)
        self.assertNotIn("topsecret", str(ctx.exception))

    def test_failure_is_logged_without_secrets(self):
        store = _ScriptedStore(add=[ConnectionError("redis://:topsecret@10.0.0.1:6379 refused")])
        with _with_store(store), self.assertLogs("apps.core.services.rate_limit", level=logging.ERROR) as logs:
            with self.assertRaises(RateLimitUnavailable):
                enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)
        joined = "\n".join(logs.output)
        self.assertIn("ConnectionError", joined)
        self.assertNotIn("topsecret", joined)

    def test_every_exception_type_is_classified_not_leaked(self):
        for exc in (OSError("x"), TimeoutError(), RuntimeError("boom"), KeyError("k")):
            with self.subTest(exc=exc.__class__.__name__):
                store = _ScriptedStore(add=[exc])
                with _with_store(store), self.assertRaises(RateLimitUnavailable):
                    enforce_rate_limit("t.out", "k", max_attempts=5, window_seconds=9)

    def test_outage_never_returns_as_if_allowed(self):
        store = _ScriptedStore(add=[False], incr=[ConnectionError()])
        with _with_store(store):
            with self.assertRaises(RateLimitUnavailable):
                enforce_rate_limit("t.out", "k", max_attempts=10**9, window_seconds=9)

    def test_fail_open_is_explicit_opt_in_and_still_logs(self):
        store = _ScriptedStore(add=[ConnectionError()])
        with _with_store(store), self.assertLogs("apps.core.services.rate_limit", level=logging.ERROR):
            enforce_rate_limit("t.out", "k", max_attempts=1, window_seconds=9, fail_open=True)

    def test_exceeded_is_not_swallowed_by_fail_open(self):
        store = _ScriptedStore(add=[False], incr=[99])
        with _with_store(store), self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.out", "k", max_attempts=1, window_seconds=9, fail_open=True)

    def test_unavailable_is_not_an_exceeded_subclass(self):
        self.assertFalse(issubclass(RateLimitUnavailable, RateLimitExceeded))


class StoreSelectionTests(SimpleTestCase):
    def test_uses_the_dedicated_alias(self):
        with override_settings(
            RASTISI_RATE_LIMIT_CACHE_ALIAS="ratelimit",
        ):
            self.assertIs(rate_limit._store(), caches["ratelimit"])

    def test_dev_aliases_share_storage_so_cache_clear_resets_limits(self):
        enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        with self.assertRaises(RateLimitExceeded):
            enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        cache.clear()  # default alias, as used throughout the suite
        enforce_rate_limit("t.share", "k", max_attempts=1, window_seconds=60)
        cache.clear()
