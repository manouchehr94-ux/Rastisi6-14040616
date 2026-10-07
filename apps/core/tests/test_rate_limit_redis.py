"""REAL Redis, REAL multi-process verification of the shared rate limiter.

LocMem tests prove nothing about cross-worker behaviour, so these tests spawn
independent Python interpreters (each with its own Django + Redis connection
pool, i.e. what gunicorn workers are) against a real Redis server.

They are skipped unless ``RASTISI_TEST_REDIS_URL`` points at a *scratch* Redis
(the keys they create are namespaced and removed afterwards):

    redis-server --port 6390 --save "" --appendonly no &
    RASTISI_TEST_REDIS_URL=redis://127.0.0.1:6390/15 \\
        python manage.py test apps.core.tests.test_rate_limit_redis
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path

from django.test import SimpleTestCase

_URL = os.environ.get("RASTISI_TEST_REDIS_URL", "")
_WORKER = str(Path(__file__).with_name("redis_worker.py"))
_MANAGE = str(Path(__file__).resolve().parents[3] / "manage.py")


def _worker_env(url):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("DJANGO_", "RASTISI_", "TURNSTILE_")):
            env.pop(key)
    env["RASTISI_RATE_LIMIT_CACHE_URL"] = url
    return env


def _spawn(action, identifier, max_attempts, window, attempts, *, url=None, start_at=0.0):
    return subprocess.Popen(
        [sys.executable, _WORKER, action, identifier, str(max_attempts), str(window), str(attempts), str(start_at)],
        env=_worker_env(url or _URL), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _collect(proc, timeout=60):
    out, err = proc.communicate(timeout=timeout)
    if proc.returncode != 0:
        raise AssertionError(f"worker failed ({proc.returncode}): {err[-2000:]}")
    return json.loads(out.strip().splitlines()[-1])


def _run(*args, **kwargs):
    return _collect(_spawn(*args, **kwargs))


@unittest.skipUnless(_URL, "RASTISI_TEST_REDIS_URL not set — real-Redis verification not run")
class RealRedisRateLimitTests(SimpleTestCase):
    def setUp(self):
        import redis

        self.raw = redis.Redis.from_url(_URL)
        self.raw.ping()
        self.tag = uuid.uuid4().hex[:8]
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for key in self.raw.scan_iter(match="*rl:v1:*t_%s*" % self.tag):
            self.raw.delete(key)
        self.raw.close()

    def _action(self, name):
        return f"t_{self.tag}_{name}"

    def _redis_keys(self, action):
        return list(self.raw.scan_iter(match=f"*rl:v1:{action}:*"))

    # 1 -------------------------------------------------------------------
    def test_two_independent_processes_share_one_counter(self):
        action = self._action("shared")
        first = _run(action, "1.2.3.4", 5, 60, 3)
        second = _run(action, "1.2.3.4", 5, 60, 4)
        self.assertEqual((first["allowed"], first["blocked"]), (3, 0))
        self.assertEqual((second["allowed"], second["blocked"]), (2, 2))  # 3 + 2 = the 5 allowed overall

    # 2 -------------------------------------------------------------------
    def test_concurrent_multiprocess_burst_never_exceeds_the_budget(self):
        action = self._action("burst")
        workers, per_worker, budget = 8, 40, 50
        start_at = time.time() + 6  # interpreters need a few seconds to boot Django
        procs = [
            _spawn(action, "198.51.100.9", budget, 60, per_worker, start_at=start_at) for _ in range(workers)
        ]
        results = [_collect(p) for p in procs]
        allowed = sum(r["allowed"] for r in results)
        blocked = sum(r["blocked"] for r in results)
        self.assertEqual(sum(r["unavailable"] for r in results), 0)
        self.assertEqual(allowed, budget, results)  # exactly the budget: no overshoot, no undershoot
        self.assertEqual(allowed + blocked, workers * per_worker)
        self.assertGreater(sum(1 for r in results if r["allowed"]), 1, "burst did not actually interleave")

    def test_second_burst_shape_never_exceeds_the_budget(self):
        action = self._action("burst2")
        procs_start = time.time() + 6
        procs = [_spawn(action, "k", 30, 60, 25, start_at=procs_start) for _ in range(6)]
        results = [_collect(p) for p in procs]
        self.assertEqual(sum(r["allowed"] for r in results), 30)

    # 3 -------------------------------------------------------------------
    def test_fixed_window_expiry_is_anchored_to_the_first_attempt_and_never_extended(self):
        action = self._action("window")
        window = 4
        _run(action, "k", 2, window, 1)                       # t=0: window opens
        keys = self._redis_keys(action)
        self.assertEqual(len(keys), 1)
        ttl_first = self.raw.pttl(keys[0])
        self.assertTrue(0 < ttl_first <= window * 1000, ttl_first)
        time.sleep(2)
        self.assertEqual(_run(action, "k", 2, window, 1)["allowed"], 1)   # 2nd attempt, inside the window
        ttl_after_incr = self.raw.pttl(keys[0])
        self.assertLess(ttl_after_incr, ttl_first, "incr must not refresh the TTL (that would be a sliding window)")
        blocked = _run(action, "k", 2, window, 1)
        self.assertEqual(blocked["blocked"], 1)
        remaining = max(self.raw.pttl(keys[0]) / 1000, 0)
        time.sleep(remaining + 0.5)                            # original window is over
        self.assertEqual(self.raw.exists(*keys), 0)
        fresh = _run(action, "k", 2, window, 2)
        self.assertEqual((fresh["allowed"], fresh["blocked"]), (2, 0))

    def test_every_key_has_a_ttl_and_never_contains_the_identifier(self):
        action = self._action("ttl")
        _run(action, "victim@example.com", 3, 30, 3)
        keys = self._redis_keys(action)
        self.assertEqual(len(keys), 1)
        self.assertNotIn(b"victim", keys[0])
        self.assertNotIn(b"example", keys[0])
        self.assertGreater(self.raw.pttl(keys[0]), 0)
        self.assertEqual(self.raw.get(keys[0]), b"3")  # a plain integer, atomically INCR'ed

    # 4 -------------------------------------------------------------------
    def test_restarting_a_worker_does_not_reset_the_shared_counter(self):
        action = self._action("restart")
        before = _run(action, "k", 4, 60, 3)
        # that interpreter has exited ("worker restart"); a brand-new one continues the same budget
        after = _run(action, "k", 4, 60, 3)
        self.assertEqual(before["allowed"], 3)
        self.assertEqual((after["allowed"], after["blocked"]), (1, 2))

    # 5 -------------------------------------------------------------------
    def test_distinct_keys_remain_independent_across_processes(self):
        action = self._action("distinct")
        _run(action, "a", 1, 60, 1)
        self.assertEqual(_run(action, "a", 1, 60, 1)["blocked"], 1)
        self.assertEqual(_run(action, "b", 1, 60, 1)["allowed"], 1)
        self.assertEqual(_run(self._action("other_action"), "a", 1, 60, 1)["allowed"], 1)

    # TTL healing on real Redis ----------------------------------------------
    def test_key_that_expires_between_exists_and_incr_never_becomes_permanent(self):
        """Django's Redis ``incr`` is EXISTS + INCR. If the key expires in between,
        INCR recreates it with no TTL; the limiter must restore the TTL."""
        from unittest import mock

        import redis

        from django.core.cache import caches
        from apps.core.services import rate_limit

        action = self._action("heal")
        cfg = {
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
            "ratelimit": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _URL},
        }
        with self.settings(CACHES=cfg):
            caches._settings = caches.settings = caches.configure_settings(None)  # re-read CACHES
            store = caches["ratelimit"]
            key = rate_limit.build_key(action, "k")
            store.delete(key)
            # EXISTS lies (the key "existed" a microsecond ago), INCR then creates it TTL-less
            with mock.patch.object(redis.Redis, "exists", return_value=1), \
                    mock.patch.object(store, "add", return_value=False):
                rate_limit.enforce_rate_limit(action, "k", max_attempts=5, window_seconds=20)
            ttl = self.raw.pttl(store.make_key(key))
            self.assertTrue(0 < ttl <= 20_000, ttl)
            # genuinely-missing key at incr time: Django raises ValueError, the window restarts
            store.delete(key)
            real_add, calls = store.add, []
            def flaky_add(*a, **k):
                calls.append(1)
                return False if len(calls) == 1 else real_add(*a, **k)
            with mock.patch.object(store, "add", side_effect=flaky_add):
                rate_limit.enforce_rate_limit(action, "k", max_attempts=5, window_seconds=20)
            self.assertEqual(self.raw.get(store.make_key(key)), b"1")
            self.assertTrue(0 < self.raw.pttl(store.make_key(key)) <= 20_000)
            store.delete(key)

    # 6 -------------------------------------------------------------------
    def test_unreachable_redis_fails_closed_without_hanging(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()  # nothing listens here any more: connection refused
        result = _run(self._action("down"), "k", 5, 60, 5, url=f"redis://127.0.0.1:{port}/0")
        self.assertEqual(result["allowed"], 0)
        self.assertEqual(result["unavailable"], 5)
        self.assertLess(result["seconds"], 20)

    def test_unresponsive_redis_times_out_and_fails_closed(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        port = listener.getsockname()[1]
        held = []
        stop = threading.Event()

        def accept_and_stay_silent():
            listener.settimeout(0.2)
            while not stop.is_set():
                try:
                    held.append(listener.accept()[0])
                except OSError:
                    continue

        thread = threading.Thread(target=accept_and_stay_silent, daemon=True)
        thread.start()
        try:
            result = _run(self._action("blackhole"), "k", 5, 60, 2, url=f"redis://127.0.0.1:{port}/0")
        finally:
            stop.set()
            thread.join(2)
            for conn in held:
                conn.close()
            listener.close()
        self.assertEqual(result["allowed"], 0)
        self.assertEqual(result["unavailable"], 2)
        self.assertLess(result["seconds"], 15, "socket timeout is not bounding a stalled Redis")

    def test_wrong_password_fails_closed(self):
        bad = _URL.replace("//", "//:wrong-password-xyz@", 1) if "@" not in _URL else _URL.rsplit("@", 1)[0].rsplit(":", 1)[0] + ":wrong-password-xyz@" + _URL.rsplit("@", 1)[1]
        result = _run(self._action("auth"), "k", 5, 60, 2, url=bad)
        self.assertEqual((result["allowed"], result["unavailable"]), (0, 2))

    # management command + production boot against real Redis ------------------
    def test_verify_command_passes_and_prints_no_secret(self):
        proc = subprocess.run(
            [sys.executable, _MANAGE, "verify_rate_limit_cache"], env=_worker_env(_URL),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("rate-limit cache OK", proc.stdout)
        self.assertIn("RedisCache", proc.stdout)
        secret = _URL.split("@")[0].split(":")[-1] if "@" in _URL else None
        if secret:
            self.assertNotIn(secret, proc.stdout + proc.stderr)

    def test_verify_command_fails_nonzero_when_redis_is_down(self):
        proc = subprocess.run(
            [sys.executable, _MANAGE, "verify_rate_limit_cache"],
            env=_worker_env("redis://:s3cretpw@127.0.0.1:1/0"), capture_output=True, text=True, timeout=120,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("s3cretpw", proc.stdout + proc.stderr)

    def test_production_mode_boots_and_checks_against_real_redis(self):
        env = _worker_env(_URL)
        env.update({
            "DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "tmp-" + uuid.uuid4().hex,
            "DJANGO_ALLOWED_HOSTS": "rastisi.example.com", "DJANGO_CSRF_TRUSTED_ORIGINS": "https://rastisi.example.com",
            "TURNSTILE_SITE_KEY": "1x00000000000000000000AA", "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000AA",
            "TURNSTILE_EXPECTED_HOSTNAMES": "rastisi.example.com",
            "DJANGO_TRUSTED_PROXY_CIDRS": "10.0.0.0/8", "DJANGO_SECURE_PROXY_SSL_HEADER": "X-Forwarded-Proto:https",
        })
        for args in (["check"], ["verify_rate_limit_cache"]):
            proc = subprocess.run([sys.executable, _MANAGE, *args], env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
